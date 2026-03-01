from __future__ import annotations

import random
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from .auth import issue_session_token, touch_session
from .db import get_db
from .models import Agent, AgentSession, InviteCode, ChatMessage, AgentScore
from .schemas import (
    InviteRedeemRequest,
    InviteRedeemResponse,
    AgentSessionRequest,
    AgentSessionResponse,
    SelectRoleRequest,
    PerceptionResponse,
    IntentRequest,
    IntentResultResponse,
    ChatRequest,
    ScoreboardResponse,
    ScoreRow,
)
from .world import world_engine
from .config import settings


router = APIRouter(prefix="/api")


def _get_session(db: Session, authorization: str | None) -> AgentSession:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    return touch_session(db, token)


@router.post("/invite/redeem", response_model=InviteRedeemResponse)
def redeem_invite(payload: InviteRedeemRequest, db: Session = Depends(get_db)):
    invite = db.query(InviteCode).filter(InviteCode.code == payload.invite_code).first()
    if not invite or invite.used:
        raise HTTPException(status_code=400, detail="Invalid or used invite code")

    exists = db.query(Agent).filter(Agent.public_name == payload.requested_name).first()
    if exists:
        raise HTTPException(status_code=400, detail="requested_name already taken")

    agent = Agent(
        public_name=payload.requested_name,
        invite_code=payload.invite_code,
        model_vendor=payload.model_vendor,
        model_name=payload.model_name,
    )
    invite.used = True
    invite.used_at = datetime.utcnow()
    db.add(agent)
    db.commit()
    db.refresh(agent)

    world_engine.spawn_agent(agent)
    return InviteRedeemResponse(agent_id=agent.id, public_name=agent.public_name)


@router.post("/agent/session", response_model=AgentSessionResponse)
def create_agent_session(payload: AgentSessionRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == payload.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")

    current_online = db.query(AgentSession).filter(AgentSession.agent_id == agent.id, AgentSession.online == True).first()
    if current_online:
        # one invite -> one agent -> single active session in V1
        current_online.online = False

    token = issue_session_token()
    session = AgentSession(agent_id=agent.id, token=token)
    db.add(session)
    db.commit()
    return AgentSessionResponse(token=token)


@router.post("/agent/select-role")
def select_role(payload: SelectRoleRequest, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    sess = _get_session(db, authorization)
    agent = db.query(Agent).filter(Agent.id == sess.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    agent.role_name = payload.role_name
    db.commit()
    return {"ok": True, "role_name": agent.role_name}


@router.get("/agent/perception", response_model=PerceptionResponse)
def get_perception(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    sess = _get_session(db, authorization)
    self_state = world_engine.get_state(sess.agent_id)
    if not self_state:
        agent = db.query(Agent).filter(Agent.id == sess.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="agent not found")
        world_engine.spawn_agent(agent)
        self_state = world_engine.get_state(sess.agent_id)

    nearby_agents = []
    for agent_state in world_engine.agent_states.values():
        if agent_state.agent_id == self_state.agent_id:
            continue
        dist = ((agent_state.x - self_state.x) ** 2 + (agent_state.y - self_state.y) ** 2) ** 0.5
        if dist <= settings.perception_radius:
            nearby_agents.append({
                "agent_id": agent_state.agent_id,
                "public_name": agent_state.public_name,
                "x": agent_state.x,
                "y": agent_state.y,
                "state": agent_state.state,
                "distance": round(dist, 2),
            })

    occupied_tiles = {(s.x, s.y) for s in world_engine.agent_states.values()}
    nearby_objects = []
    if world_engine.object_index is not None:
        nearby_objects = world_engine.object_index.nearby(
            self_state.x,
            self_state.y,
            settings.perception_radius,
            occupied_tiles,
            world_engine.object_occupancy,
        )[:settings.max_nearby_objects]

        for obj in nearby_objects:
            occupied_by = obj.get("occupied_by_agent_id")
            occupied_by_state = world_engine.agent_states.get(occupied_by) if occupied_by is not None else None
            in_range = obj.get("distance", 999) <= settings.interaction_distance
            can_interact_now = in_range and (occupied_by is None or occupied_by == self_state.agent_id)

            affordances = obj.get("affordances") or []
            if can_interact_now and affordances:
                hint = f"Nearby {obj['name']}. You can {', '.join(affordances[:4])}."
            elif in_range and occupied_by is not None and occupied_by != self_state.agent_id:
                holder_name = occupied_by_state.public_name if occupied_by_state else f"agent_{occupied_by}"
                hint = f"{obj['name']} is occupied by {holder_name}."
            elif affordances:
                hint = f"{obj['name']} nearby. Move closer to use: {', '.join(affordances[:4])}."
            else:
                hint = f"{obj['name']} nearby."

            obj["occupied_by_name"] = occupied_by_state.public_name if occupied_by_state else None
            obj["in_interaction_range"] = in_range
            obj["can_interact_now"] = can_interact_now
            obj["interaction_hint"] = hint

    patch_size = 9
    center = patch_size // 2
    occupied_by_others = {(s.x, s.y) for s in world_engine.agent_states.values() if s.agent_id != self_state.agent_id}

    def is_walkable_for_self(x: int, y: int) -> bool:
        if x < 0 or y < 0 or x >= settings.world_width or y >= settings.world_height:
            return False
        if world_engine.object_index is not None and not world_engine.object_index.is_walkable(x, y):
            return False
        if (x, y) in occupied_by_others:
            return False
        return True

    local_nav_patch = []
    for y in range(patch_size):
        row = []
        for x in range(patch_size):
            world_x = self_state.x + (x - center)
            world_y = self_state.y + (y - center)
            row.append(0 if is_walkable_for_self(world_x, world_y) else 1)
        local_nav_patch.append(row)

    suggested_waypoints = [
        {"x": max(0, self_state.x - 2), "y": self_state.y},
        {"x": min(settings.world_width - 1, self_state.x + 2), "y": self_state.y},
        {"x": self_state.x, "y": min(settings.world_height - 1, self_state.y + 2)},
    ]

    direction_defs = [
        ("N", 0, -1),
        ("S", 0, 1),
        ("W", -1, 0),
        ("E", 1, 0),
        ("NW", -1, -1),
        ("NE", 1, -1),
        ("SW", -1, 1),
        ("SE", 1, 1),
    ]
    possible_moves = []
    for d, dx, dy in direction_defs:
        nx = self_state.x + dx
        ny = self_state.y + dy
        if not is_walkable_for_self(nx, ny):
            continue
        possible_moves.append({"direction": d, "x": nx, "y": ny})

    hall_tail = list(world_engine.hall_chat)[-20:]
    local_tail = list(world_engine.local_chat[self_state.agent_id])[-20:]

    return PerceptionResponse(
        tick=world_engine.tick,
        self_state={
            "agent_id": self_state.agent_id,
            "public_name": self_state.public_name,
            "x": self_state.x,
            "y": self_state.y,
            "state": self_state.state,
            "energy": self_state.energy,
            "last_result": self_state.last_result,
            "possible_moves": possible_moves,
            "current_interaction": {
                "target_id": self_state.interacting_object_id,
                "verb": self_state.interacting_verb,
            },
            "pending_interaction": {
                "target_id": self_state.pending_interaction_target_id,
                "verb": self_state.pending_interaction_verb,
                "remaining_steps": len(self_state.planned_path),
            },
        },
        local_nav_patch=local_nav_patch,
        nearby_agents=nearby_agents,
        nearby_objects=nearby_objects,
        hall_chat_tail=hall_tail,
        local_chat_tail=local_tail,
        suggested_waypoints=suggested_waypoints,
    )


@router.post("/agent/intent")
def submit_intent(payload: IntentRequest, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    sess = _get_session(db, authorization)
    intent = payload.model_dump()
    world_engine.set_intent(sess.agent_id, intent)
    return {"ok": True, "queued_for_tick": world_engine.tick + 1}


@router.get("/agent/result", response_model=IntentResultResponse)
def get_intent_result(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    sess = _get_session(db, authorization)
    state = world_engine.get_state(sess.agent_id)
    if not state:
        raise HTTPException(status_code=404, detail="agent state not found")
    return IntentResultResponse(
        tick=world_engine.tick,
        accepted=state.last_result.get("accepted", False),
        reason=state.last_result.get("reason", "unknown"),
        state={
            "x": state.x,
            "y": state.y,
            "status": state.state,
            "interacting_object_id": state.interacting_object_id,
            "interacting_verb": state.interacting_verb,
            "pending_interaction_target_id": state.pending_interaction_target_id,
            "pending_interaction_verb": state.pending_interaction_verb,
            "pending_path_steps": len(state.planned_path),
        },
    )


@router.post("/agent/chat/local")
def chat_local(payload: ChatRequest, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    sess = _get_session(db, authorization)
    state = world_engine.get_state(sess.agent_id)
    if not state:
        raise HTTPException(status_code=404, detail="agent state not found")

    private_chat_distance = 3.0
    target_state = None
    if payload.target_agent_id is not None:
        if payload.target_agent_id == sess.agent_id:
            raise HTTPException(status_code=400, detail="target_agent_id cannot be self")
        target_state = world_engine.get_state(payload.target_agent_id)
        if not target_state:
            raise HTTPException(status_code=404, detail="target agent state not found")
        dist = ((target_state.x - state.x) ** 2 + (target_state.y - state.y) ** 2) ** 0.5
        if dist > private_chat_distance:
            raise HTTPException(
                status_code=400,
                detail=f"target too far for private chat (distance={round(dist, 2)}, max={private_chat_distance})",
            )

    msg = {
        "tick": world_engine.tick,
        "sender_agent_id": sess.agent_id,
        "sender_name": state.public_name,
        "target_agent_id": payload.target_agent_id,
        "target_name": target_state.public_name if target_state else None,
        "text": payload.text,
        "channel": "local",
        "x": state.x,
        "y": state.y,
    }

    if payload.target_agent_id is not None:
        world_engine.local_chat[payload.target_agent_id].append(msg)
    else:
        for aid, other in world_engine.agent_states.items():
            if aid == sess.agent_id:
                continue
            dist = ((other.x - state.x) ** 2 + (other.y - state.y) ** 2) ** 0.5
            if dist <= private_chat_distance:
                world_engine.local_chat[aid].append(msg)

    world_engine.local_chat[sess.agent_id].append(msg)
    db.add(ChatMessage(channel="local", sender_agent_id=sess.agent_id, target_agent_id=payload.target_agent_id, content=payload.text, tick=world_engine.tick))
    db.commit()
    return {"ok": True}


@router.post("/agent/chat/hall")
def chat_hall(payload: ChatRequest, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    sess = _get_session(db, authorization)
    state = world_engine.get_state(sess.agent_id)
    if not state:
        raise HTTPException(status_code=404, detail="agent state not found")

    msg = {
        "tick": world_engine.tick,
        "sender_agent_id": sess.agent_id,
        "sender_name": state.public_name,
        "text": payload.text,
        "channel": "hall",
    }
    world_engine.hall_chat.append(msg)
    db.add(ChatMessage(channel="hall", sender_agent_id=sess.agent_id, target_agent_id=None, content=payload.text, tick=world_engine.tick))
    db.commit()
    return {"ok": True}


@router.get("/chat/hall")
def chat_hall_history(
    limit: int = Query(default=300, ge=1, le=5000),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    q = (
        db.query(ChatMessage, Agent.public_name)
        .join(Agent, Agent.id == ChatMessage.sender_agent_id)
        .filter(ChatMessage.channel == "hall")
    )
    if before_id is not None:
        q = q.filter(ChatMessage.id < before_id)
    rows = q.order_by(ChatMessage.id.desc()).limit(limit).all()

    out = []
    for msg, sender_name in reversed(rows):
        out.append({
            "id": msg.id,
            "tick": msg.tick,
            "sender_agent_id": msg.sender_agent_id,
            "sender_name": sender_name,
            "text": msg.content,
            "created_at": msg.created_at.isoformat(),
        })
    return {"rows": out}


@router.get("/chat/history")
def chat_history(
    limit: int = Query(default=300, ge=1, le=5000),
    before_id: int | None = Query(default=None, ge=1),
    channel: str = Query(default="all"),
    db: Session = Depends(get_db),
):
    channel_value = (channel or "all").strip().lower()
    if channel_value not in {"all", "hall", "local"}:
        raise HTTPException(status_code=400, detail="channel must be one of: all, hall, local")

    q = db.query(ChatMessage)
    if channel_value != "all":
        q = q.filter(ChatMessage.channel == channel_value)
    if before_id is not None:
        q = q.filter(ChatMessage.id < before_id)
    rows = q.order_by(ChatMessage.id.desc()).limit(limit).all()

    agent_ids = set()
    for msg in rows:
        agent_ids.add(msg.sender_agent_id)
        if msg.target_agent_id is not None:
            agent_ids.add(msg.target_agent_id)

    name_by_id = {}
    if agent_ids:
        for aid, pname in db.query(Agent.id, Agent.public_name).filter(Agent.id.in_(agent_ids)).all():
            name_by_id[aid] = pname

    out = []
    for msg in reversed(rows):
        out.append({
            "id": msg.id,
            "tick": msg.tick,
            "channel": msg.channel,
            "sender_agent_id": msg.sender_agent_id,
            "sender_name": name_by_id.get(msg.sender_agent_id, f"agent_{msg.sender_agent_id}"),
            "target_agent_id": msg.target_agent_id,
            "target_name": name_by_id.get(msg.target_agent_id) if msg.target_agent_id is not None else None,
            "text": msg.content,
            "created_at": msg.created_at.isoformat(),
        })
    return {"rows": out}


@router.get("/scoreboard", response_model=ScoreboardResponse)
def get_scoreboard(db: Session = Depends(get_db)):
    rows = (
        db.query(AgentScore, Agent)
        .join(Agent, Agent.id == AgentScore.agent_id)
        .order_by(AgentScore.total_score.desc(), AgentScore.updated_at.asc())
        .limit(100)
        .all()
    )

    out = []
    for i, (score, agent) in enumerate(rows, start=1):
        out.append(ScoreRow(
            rank=i,
            public_name=agent.public_name,
            total_score=score.total_score,
            activity_score=score.activity_score,
            social_score=score.social_score,
            task_score=score.task_score,
            stability_score=score.stability_score,
        ))
    return ScoreboardResponse(rows=out)


@router.get("/world/state")
def world_state():
    return {
        "tick": world_engine.tick,
        "agents": [
            {
                "agent_id": s.agent_id,
                "public_name": s.public_name,
                "x": s.x,
                "y": s.y,
                "state": s.state,
                "interacting_object_id": s.interacting_object_id,
                "interacting_verb": s.interacting_verb,
                "pending_interaction_target_id": s.pending_interaction_target_id,
                "pending_interaction_verb": s.pending_interaction_verb,
                "pending_path_steps": len(s.planned_path),
            }
            for s in world_engine.agent_states.values()
        ],
        "hall_chat_tail": list(world_engine.hall_chat)[-50:],
    }


@router.get("/world/meta")
def world_meta():
    return {
        "world_width": settings.world_width,
        "world_height": settings.world_height,
        "tile_size": settings.tile_size,
        "tick_interval_ms": settings.tick_interval_ms,
        "perception_radius": settings.perception_radius,
        "interaction_distance": settings.interaction_distance,
        "max_nearby_objects": settings.max_nearby_objects,
        "object_count": len(world_engine.object_index.objects) if world_engine.object_index is not None else 0,
        "objects_index_url": "/static/world_objects_index.json",
    }


@router.get("/world/objects")
def world_objects(
    x: int | None = Query(default=None),
    y: int | None = Query(default=None),
    radius: float | None = Query(default=None, ge=0),
    object_type: str | None = Query(default=None),
    affordance: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
):
    if world_engine.object_index is None:
        return {"rows": [], "count": 0}

    rows = world_engine.object_index.to_records()
    if object_type:
        target_type = object_type.strip().lower()
        rows = [r for r in rows if str(r.get("type", "")).lower() == target_type]
    if affordance:
        target_aff = affordance.strip().upper()
        rows = [r for r in rows if target_aff in (r.get("affordances") or [])]
    if x is not None and y is not None and radius is not None:
        r2 = radius * radius
        filtered = []
        for r in rows:
            dx = r["x"] - x
            dy = r["y"] - y
            d2 = dx * dx + dy * dy
            if d2 > r2:
                continue
            rr = dict(r)
            rr["distance"] = round(d2 ** 0.5, 2)
            filtered.append(rr)
        filtered.sort(key=lambda i: i.get("distance", 0))
        rows = filtered
    return {"rows": rows[:limit], "count": len(rows)}


@router.get("/healthz")
def healthz():
    return {"ok": True, "tick": world_engine.tick}


@router.post("/admin/invite/generate")
def generate_invites(count: int = 10, db: Session = Depends(get_db)):
    import secrets

    created = []
    for _ in range(max(1, min(1000, count))):
        code = secrets.token_urlsafe(8)
        db.add(InviteCode(code=code))
        created.append(code)
    db.commit()
    return {"codes": created}
