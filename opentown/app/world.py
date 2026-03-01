from __future__ import annotations

import asyncio
import heapq
import json
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .config import settings
from .models import Agent, AgentScore, ChatMessage, WorldEvent


INTERACTION_STATUS_BY_VERB = {
    "SLEEP": "SLEEPING",
    "LIE_DOWN": "RESTING",
    "SIT": "SITTING",
    "RELAX": "RELAXING",
    "USE_TOILET": "USING_TOILET",
    "SHOWER": "SHOWERING",
    "WASH": "WASHING",
    "COOK": "COOKING",
    "EAT": "EATING",
    "PLAY_MUSIC": "PLAYING_MUSIC",
    "PRACTICE": "PRACTICING",
    "USE_COMPUTER": "USING_COMPUTER",
    "READ": "READING",
    "BROWSE": "BROWSING",
    "WORK": "WORKING",
    "WRITE": "WRITING",
    "PLAY": "PLAYING",
    "GARDEN": "GARDENING",
    "ORGANIZE": "ORGANIZING",
    "LOOK": "OBSERVING",
}

# Lightweight semantic routing rules for text-only interaction intents.
SEMANTIC_VERB_RULES: list[tuple[list[str], str]] = [
    (["sleep", "nap", "bedtime", "rest", "asleep", "睡", "休息"], "SLEEP"),
    (["sit", "seat", "chair", "sofa", "坐", "凳子", "椅子"], "SIT"),
    (["toilet", "bathroom", "restroom", "wc", "上厕所", "厕所"], "USE_TOILET"),
    (["shower", "bath", "洗澡"], "SHOWER"),
    (["wash", "sink", "handwash", "洗手", "洗脸"], "WASH"),
    (["cook", "kitchen", "做饭"], "COOK"),
    (["eat", "meal", "food", "吃饭"], "EAT"),
    (["read", "book", "library", "看书"], "READ"),
    (["computer", "pc", "laptop", "电脑"], "USE_COMPUTER"),
    (["music", "piano", "guitar", "harp", "唱歌", "弹琴"], "PLAY_MUSIC"),
    (["play", "game", "娱乐"], "PLAY"),
]

SEMANTIC_OBJECT_HINTS: list[tuple[list[str], str]] = [
    (["bed", "sleep", "nap", "睡"], "bed"),
    (["chair", "seat", "sofa", "sit", "坐", "凳"], "seat"),
    (["toilet", "bathroom", "wc", "厕所"], "toilet"),
    (["shower", "bath", "洗澡"], "shower"),
    (["sink", "wash", "洗手"], "sink"),
    (["kitchen", "cook", "refrigerator", "做饭"], "kitchen"),
    (["computer", "pc", "电脑"], "computer"),
    (["book", "library", "read", "书"], "reading"),
    (["music", "piano", "guitar", "harp", "音乐"], "music"),
]


@dataclass
class AgentWorldState:
    agent_id: int
    public_name: str
    x: int
    y: int
    energy: int = 100
    state: str = "IDLE"
    interacting_object_id: str | None = None
    interacting_verb: str | None = None
    pending_interaction_target_id: str | None = None
    pending_interaction_verb: str | None = None
    planned_path: list[tuple[int, int]] = field(default_factory=list)
    last_result: dict = field(default_factory=lambda: {"accepted": True, "reason": "ok"})


class WSManager:
    def __init__(self) -> None:
        self.connections = set()

    async def connect(self, ws):
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws):
        self.connections.discard(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for conn in self.connections:
            try:
                await conn.send_json(payload)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)


class WorldEngine:
    def __init__(self) -> None:
        self.tick = 0
        self.agent_states: dict[int, AgentWorldState] = {}
        self.object_index = None
        self.object_occupancy: dict[str, int] = {}
        self.pending_intents: dict[int, dict] = {}
        self.local_chat = defaultdict(lambda: deque(maxlen=30))
        self.hall_chat = deque(maxlen=200)
        self.lock = asyncio.Lock()
        self.ws = WSManager()
        self.running = False

    def spawn_agent(self, agent: Agent):
        if agent.id in self.agent_states:
            return
        # Find a non-overlapping spawn position; fallback to random if crowded.
        taken = {(s.x, s.y) for s in self.agent_states.values()}
        sx, sy = None, None
        for _ in range(200):
            tx = random.randint(1, settings.world_width - 2)
            ty = random.randint(1, settings.world_height - 2)
            if (tx, ty) not in taken:
                sx, sy = tx, ty
                break
        if sx is None or sy is None:
            sx = random.randint(1, settings.world_width - 2)
            sy = random.randint(1, settings.world_height - 2)

        self.agent_states[agent.id] = AgentWorldState(
            agent_id=agent.id,
            public_name=agent.public_name,
            x=sx,
            y=sy,
        )

    def set_intent(self, agent_id: int, intent: dict):
        self.pending_intents[agent_id] = intent

    def get_state(self, agent_id: int) -> AgentWorldState | None:
        return self.agent_states.get(agent_id)

    def _distance(self, a: AgentWorldState, b: AgentWorldState) -> float:
        return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

    def _distance_to_point(self, state: AgentWorldState, x: int, y: int) -> float:
        return ((state.x - x) ** 2 + (state.y - y) ** 2) ** 0.5

    def _clip_pos(self, x: int, y: int):
        x = max(0, min(settings.world_width - 1, x))
        y = max(0, min(settings.world_height - 1, y))
        return x, y

    def _normalize_verb(self, verb: str | None) -> str | None:
        if verb is None:
            return None
        return verb.strip().replace("-", "_").replace(" ", "_").upper()

    def _infer_verb_from_text(self, text: str | None) -> str | None:
        if not text:
            return None
        lowered = text.lower()
        for keywords, verb in SEMANTIC_VERB_RULES:
            if any(k in lowered for k in keywords):
                return verb
        return None

    def _infer_object_hints_from_text(self, text: str | None) -> set[str]:
        if not text:
            return set()
        lowered = text.lower()
        hints: set[str] = set()
        for keywords, hint in SEMANTIC_OBJECT_HINTS:
            if any(k in lowered for k in keywords):
                hints.add(hint)
        return hints

    def _status_for_verb(self, verb: str | None) -> str:
        if not verb:
            return "INTERACTING"
        return INTERACTION_STATUS_BY_VERB.get(verb, "INTERACTING")

    def _release_interaction(self, state: AgentWorldState):
        if state.interacting_object_id is not None:
            occupied_by = self.object_occupancy.get(state.interacting_object_id)
            if occupied_by == state.agent_id:
                self.object_occupancy.pop(state.interacting_object_id, None)
        state.interacting_object_id = None
        state.interacting_verb = None

    def _clear_pending_navigation(self, state: AgentWorldState):
        state.pending_interaction_target_id = None
        state.pending_interaction_verb = None
        state.planned_path = []

    def _is_tile_walkable_for_agent(self, agent_id: int, x: int, y: int) -> bool:
        if x < 0 or y < 0 or x >= settings.world_width or y >= settings.world_height:
            return False
        if self.object_index is not None and not self.object_index.is_walkable(x, y):
            return False
        for other in self.agent_states.values():
            if other.agent_id != agent_id and other.x == x and other.y == y:
                return False
        return True

    def _move_to_next_tile(self, state: AgentWorldState, nx: int, ny: int, success_reason: str = "moved") -> bool:
        nx, ny = self._clip_pos(nx, ny)
        if self.object_index is not None and not self.object_index.is_walkable(nx, ny):
            state.state = "IDLE"
            state.last_result = {"accepted": False, "reason": "blocked_by_map", "x": nx, "y": ny}
            return False
        occupied = any(
            other.agent_id != state.agent_id and other.x == nx and other.y == ny
            for other in self.agent_states.values()
        )
        if occupied:
            state.state = "IDLE"
            state.last_result = {"accepted": False, "reason": "blocked_by_agent", "x": nx, "y": ny}
            return False
        state.x, state.y = nx, ny
        state.state = "MOVING"
        state.last_result = {"accepted": True, "reason": success_reason}
        return True

    def _interaction_goal_tiles(self, target_x: int, target_y: int) -> list[tuple[int, int]]:
        goals: list[tuple[int, int]] = []
        radius = int(settings.interaction_distance) + 2
        for y in range(target_y - radius, target_y + radius + 1):
            for x in range(target_x - radius, target_x + radius + 1):
                if x < 0 or y < 0 or x >= settings.world_width or y >= settings.world_height:
                    continue
                dist = ((target_x - x) ** 2 + (target_y - y) ** 2) ** 0.5
                if dist > settings.interaction_distance:
                    continue
                if self.object_index is not None and not self.object_index.is_walkable(x, y):
                    continue
                goals.append((x, y))
        return goals

    def _path_heuristic(self, node: tuple[int, int], goals: list[tuple[int, int]]) -> float:
        x, y = node
        # Goal set is small (interaction ring around one object), so min-manhattan is cheap.
        return min(abs(x - gx) + abs(y - gy) for gx, gy in goals)

    def _astar_path(
        self,
        start: tuple[int, int],
        goals: list[tuple[int, int]],
        agent_id: int,
    ) -> list[tuple[int, int]]:
        if not goals:
            return []
        goal_set = set(goals)
        if start in goal_set:
            return []

        open_heap: list[tuple[float, float, tuple[int, int]]] = []
        heapq.heappush(open_heap, (self._path_heuristic(start, goals), 0.0, start))
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], float] = {start: 0.0}

        directions = [
            (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (1, 1, 1.414),
        ]

        while open_heap:
            _, current_cost, current = heapq.heappop(open_heap)
            if current in goal_set:
                path: list[tuple[int, int]] = []
                node = current
                while node != start:
                    path.append(node)
                    node = came_from[node]
                path.reverse()
                return path

            if current_cost > g_score.get(current, float("inf")):
                continue

            cx, cy = current
            for dx, dy, step_cost in directions:
                nx, ny = cx + dx, cy + dy
                neighbor = (nx, ny)
                if not self._is_tile_walkable_for_agent(agent_id, nx, ny):
                    continue
                tentative = current_cost + step_cost
                if tentative >= g_score.get(neighbor, float("inf")):
                    continue
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                f_score = tentative + self._path_heuristic(neighbor, goals)
                heapq.heappush(open_heap, (f_score, tentative, neighbor))

        return []

    def _plan_path_to_object_interaction(self, state: AgentWorldState, target_x: int, target_y: int) -> list[tuple[int, int]]:
        start = (state.x, state.y)
        goals = self._interaction_goal_tiles(target_x, target_y)
        return self._astar_path(start, goals, state.agent_id)

    def _select_target_from_semantics(
        self,
        state: AgentWorldState,
        requested_verb: str | None,
        requested_text: str | None,
    ) -> tuple[object, str, list[tuple[int, int]] | None] | None:
        if self.object_index is None:
            return None

        object_hints = self._infer_object_hints_from_text(requested_text)
        filtered: list[tuple[float, object]] = []
        for obj in self.object_index.objects:
            affordances = list(obj.affordances) if obj.affordances else ["LOOK"]
            if requested_verb and requested_verb not in affordances:
                continue

            if object_hints:
                name_l = obj.name.lower()
                type_l = (obj.object_type or "").lower()
                if not any(h in name_l or h == type_l for h in object_hints):
                    continue

            occupied_by = self.object_occupancy.get(obj.object_id)
            if occupied_by is not None and occupied_by != state.agent_id:
                continue

            dist = self._distance_to_point(state, obj.x, obj.y)
            filtered.append((dist, obj))

        if not filtered:
            return None

        filtered.sort(key=lambda item: item[0])
        # Keep search bounded: nearest candidates first, then check reachability.
        for dist, obj in filtered[:12]:
            affordances = list(obj.affordances) if obj.affordances else ["LOOK"]
            resolved_verb = requested_verb or affordances[0]
            if dist <= settings.interaction_distance:
                return obj, resolved_verb, None
            path = self._plan_path_to_object_interaction(state, obj.x, obj.y)
            if path:
                return obj, resolved_verb, path
        return None

    def _continue_pending_interaction(self, state: AgentWorldState) -> bool:
        target_id = state.pending_interaction_target_id
        if not target_id:
            return False
        if self.object_index is None:
            self._clear_pending_navigation(state)
            state.state = "IDLE"
            state.last_result = {"accepted": False, "reason": "object_index_unavailable"}
            return True

        target = self.object_index.get(target_id)
        if target is None:
            self._clear_pending_navigation(state)
            state.state = "IDLE"
            state.last_result = {"accepted": False, "reason": "object_not_found", "target_id": target_id}
            return True

        distance = self._distance_to_point(state, target.x, target.y)
        if distance <= settings.interaction_distance:
            self._apply_interact_intent(
                state,
                {
                    "type": "INTERACT",
                    "target_id": target_id,
                    "verb": state.pending_interaction_verb,
                    "auto_approach": False,
                },
            )
            if state.last_result.get("accepted"):
                self._clear_pending_navigation(state)
            return True

        needs_replan = not state.planned_path
        if not needs_replan and state.planned_path:
            nx, ny = state.planned_path[0]
            if not self._is_tile_walkable_for_agent(state.agent_id, nx, ny):
                needs_replan = True
        if needs_replan:
            state.planned_path = self._plan_path_to_object_interaction(state, target.x, target.y)
            if not state.planned_path:
                self._clear_pending_navigation(state)
                state.state = "IDLE"
                state.last_result = {"accepted": False, "reason": "target_unreachable", "target_id": target.object_id}
                return True

        nx, ny = state.planned_path.pop(0)
        moved = self._move_to_next_tile(state, nx, ny, success_reason="interaction_approaching")
        if moved:
            state.last_result.update(
                {
                    "target_id": target.object_id,
                    "target_name": target.name,
                    "remaining_steps": len(state.planned_path),
                }
            )
        return True

    def _apply_interact_intent(self, state: AgentWorldState, intent: dict):
        if self.object_index is None:
            state.last_result = {"accepted": False, "reason": "object_index_unavailable"}
            return

        requested_text = str(intent.get("text") or "").strip()
        requested_verb = self._normalize_verb(intent.get("verb"))
        if requested_verb is None:
            requested_verb = self._infer_verb_from_text(requested_text)

        target_id = intent.get("target_id")
        target = None
        preplanned_path: list[tuple[int, int]] | None = None
        selected_by_semantics = False

        if target_id:
            target = self.object_index.get(target_id)
            if target is None:
                state.last_result = {"accepted": False, "reason": "object_not_found", "target_id": target_id}
                return
        else:
            semantic_pick = self._select_target_from_semantics(
                state=state,
                requested_verb=requested_verb,
                requested_text=requested_text,
            )
            if semantic_pick is None:
                state.last_result = {
                    "accepted": False,
                    "reason": "no_matching_object",
                    "requested_verb": requested_verb,
                    "requested_text": requested_text or None,
                }
                return
            target, semantic_verb, preplanned_path = semantic_pick
            target_id = target.object_id
            selected_by_semantics = True
            if requested_verb is None:
                requested_verb = semantic_verb

        # New target replaces any pending navigation plan.
        if state.pending_interaction_target_id and state.pending_interaction_target_id != target.object_id:
            self._clear_pending_navigation(state)

        distance = self._distance_to_point(state, target.x, target.y)
        auto_approach = bool(intent.get("auto_approach", True))
        allowed_verbs = list(target.affordances) if target.affordances else ["LOOK"]
        verb = requested_verb
        if verb is None:
            verb = allowed_verbs[0]
        if verb not in allowed_verbs:
            state.last_result = {
                "accepted": False,
                "reason": "invalid_verb",
                "target_id": target.object_id,
                "requested_verb": verb,
                "allowed_verbs": allowed_verbs,
            }
            return

        if distance > settings.interaction_distance:
            if not auto_approach:
                state.last_result = {
                    "accepted": False,
                    "reason": "target_too_far",
                    "target_id": target.object_id,
                    "distance": round(distance, 2),
                    "required_max_distance": settings.interaction_distance,
                }
                return

            path = preplanned_path if preplanned_path is not None else self._plan_path_to_object_interaction(state, target.x, target.y)
            if not path:
                state.last_result = {
                    "accepted": False,
                    "reason": "target_unreachable",
                    "target_id": target.object_id,
                    "distance": round(distance, 2),
                }
                return

            state.pending_interaction_target_id = target.object_id
            state.pending_interaction_verb = verb
            state.planned_path = path
            self._continue_pending_interaction(state)
            state.last_result.update(
                {
                    "selected_by_semantics": selected_by_semantics,
                    "requested_text": requested_text or None,
                }
            )
            return

        # Arrived in interaction range: clear pending navigation and run interact now.
        self._clear_pending_navigation(state)
        if state.interacting_object_id and state.interacting_object_id != target.object_id:
            self._release_interaction(state)

        occupied_by = self.object_occupancy.get(target.object_id)
        if occupied_by is not None and occupied_by != state.agent_id:
            holder = self.agent_states.get(occupied_by)
            state.last_result = {
                "accepted": False,
                "reason": "object_busy",
                "target_id": target.object_id,
                "occupied_by_agent_id": occupied_by,
                "occupied_by_name": holder.public_name if holder else None,
            }
            return

        self.object_occupancy[target.object_id] = state.agent_id
        state.interacting_object_id = target.object_id
        state.interacting_verb = verb
        state.state = self._status_for_verb(verb)
        state.last_result = {
            "accepted": True,
            "reason": "interaction_started",
            "target_id": target.object_id,
            "target_name": target.name,
            "verb": verb,
            "distance": round(distance, 2),
            "selected_by_semantics": selected_by_semantics,
            "requested_text": requested_text or None,
        }

    def _apply_intent(self, state: AgentWorldState, intent: dict):
        itype = str(intent.get("type") or "").upper()
        if itype == "MOVE_TO":
            self._clear_pending_navigation(state)
            if state.interacting_object_id is not None:
                self._release_interaction(state)

            tx = int(intent.get("x", state.x))
            ty = int(intent.get("y", state.y))
            tx, ty = self._clip_pos(tx, ty)
            # One-step move per tick for fairness.
            dx = 0 if tx == state.x else (1 if tx > state.x else -1)
            dy = 0 if ty == state.y else (1 if ty > state.y else -1)
            nx, ny = self._clip_pos(state.x + dx, state.y + dy)
            self._move_to_next_tile(state, nx, ny, success_reason="moved")
            return

        if itype == "WAIT":
            if state.pending_interaction_target_id:
                if self._continue_pending_interaction(state):
                    return
            if state.interacting_object_id is not None:
                state.state = self._status_for_verb(state.interacting_verb)
                state.last_result = {
                    "accepted": True,
                    "reason": "continuing_interaction",
                    "target_id": state.interacting_object_id,
                    "verb": state.interacting_verb,
                }
            else:
                state.state = "IDLE"
                state.last_result = {"accepted": True, "reason": "waited"}
            return

        if itype in {"CHAT_LOCAL", "CHAT_HALL"}:
            self._clear_pending_navigation(state)
            state.state = "TALKING"
            state.last_result = {"accepted": True, "reason": itype.lower()}
            return

        if itype == "INTERACT":
            self._apply_interact_intent(state, intent)
            return

        state.last_result = {"accepted": False, "reason": "unknown_intent"}
        return

    def _snapshot(self):
        return {
            "tick": self.tick,
            "time": datetime.utcnow().isoformat(),
            "agents": [
                {
                    "agent_id": s.agent_id,
                    "public_name": s.public_name,
                    "x": s.x,
                    "y": s.y,
                    "state": s.state,
                    "energy": s.energy,
                    "interacting_object_id": s.interacting_object_id,
                    "interacting_verb": s.interacting_verb,
                    "pending_interaction_target_id": s.pending_interaction_target_id,
                    "pending_interaction_verb": s.pending_interaction_verb,
                }
                for s in self.agent_states.values()
            ],
            "hall_chat_tail": list(self.hall_chat)[-20:],
        }

    async def step(self, db_factory):
        async with self.lock:
            self.tick += 1

            for agent_id, state in self.agent_states.items():
                intent = self.pending_intents.pop(agent_id, {"type": "WAIT"})
                self._apply_intent(state, intent)

            persist_every = max(1, int(settings.event_persist_every_n_ticks))
            score_every = max(1, int(settings.score_persist_every_n_ticks))
            cleanup_every = max(1, int(settings.world_event_cleanup_every_n_ticks))
            retention_days = max(0, int(settings.world_event_retention_days))

            should_persist_events = (self.tick % persist_every == 0)
            should_persist_scores = (self.tick % score_every == 0)
            should_cleanup_events = (retention_days > 0 and self.tick % cleanup_every == 0)

            if should_persist_events or should_persist_scores or should_cleanup_events:
                db: Session = db_factory()
                try:
                    wrote = False

                    if should_persist_events:
                        for s in self.agent_states.values():
                            db.add(WorldEvent(
                                tick=self.tick,
                                agent_id=s.agent_id,
                                event_type="state",
                                payload=json.dumps(
                                    {
                                        "x": s.x,
                                        "y": s.y,
                                        "state": s.state,
                                        "interacting_object_id": s.interacting_object_id,
                                        "interacting_verb": s.interacting_verb,
                                        "pending_interaction_target_id": s.pending_interaction_target_id,
                                        "pending_interaction_verb": s.pending_interaction_verb,
                                    }
                                ),
                            ))
                        wrote = True

                    if should_persist_scores:
                        for s in self.agent_states.values():
                            score = db.query(AgentScore).filter(AgentScore.agent_id == s.agent_id).first()
                            if not score:
                                score = AgentScore(agent_id=s.agent_id)
                                db.add(score)
                            score.activity_score = int(score.activity_score or 0) + 1
                            if s.state == "TALKING":
                                score.social_score = int(score.social_score or 0) + 1
                            score.total_score = (
                                int(score.activity_score or 0)
                                + int(score.social_score or 0)
                                + int(score.task_score or 0)
                                + int(score.stability_score or 0)
                            )
                            score.updated_at = datetime.utcnow()
                        wrote = True

                    if should_cleanup_events:
                        cutoff = datetime.utcnow() - timedelta(days=retention_days)
                        deleted = (
                            db.query(WorldEvent)
                            .filter(WorldEvent.created_at < cutoff)
                            .delete(synchronize_session=False)
                        )
                        if deleted:
                            wrote = True

                    if wrote:
                        db.commit()
                finally:
                    db.close()

            await self.ws.broadcast({"type": "world_tick", "data": self._snapshot()})

    async def run(self, db_factory):
        self.running = True
        while self.running:
            await self.step(db_factory)
            await asyncio.sleep(settings.tick_interval_ms / 1000.0)


world_engine = WorldEngine()
