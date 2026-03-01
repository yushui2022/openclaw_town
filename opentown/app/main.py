import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .api import router as api_router
from .config import settings
from .db import Base, engine, SessionLocal
from .models import InviteCode
from .world_index import WorldObjectIndex
from .world import world_engine


app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

# Reuse Stanford-town assets
asset_dir = PROJECT_ROOT / "environment" / "frontend_server" / "static_dirs"
if asset_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(asset_dir)), name="assets")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    world_engine.object_index = WorldObjectIndex.load_from_assets(
        PROJECT_ROOT,
        settings.world_width,
        settings.world_height,
    )
    if world_engine.object_index is not None:
        world_engine.object_index.export_json(BASE_DIR / "static" / "world_objects_index.json")

    # Ensure there are a few invite codes for first boot
    db: Session = SessionLocal()
    try:
        if db.query(InviteCode).count() == 0:
            import secrets
            for _ in range(20):
                db.add(InviteCode(code=secrets.token_urlsafe(8)))
            db.commit()

        # Seed four default residents so observer page has immediate activity.
        from .models import Agent

        defaults = [
            ("Townie_Ava", "SYSTEM_DEFAULT_1"),
            ("Townie_Leo", "SYSTEM_DEFAULT_2"),
            ("Townie_Mia", "SYSTEM_DEFAULT_3"),
            ("Townie_Noah", "SYSTEM_DEFAULT_4"),
        ]
        for name, invite_code in defaults:
            exists = db.query(Agent).filter(Agent.public_name == name).first()
            if exists:
                continue
            db.add(Agent(
                public_name=name,
                invite_code=invite_code,
                role_name="resident",
                model_vendor="system",
                model_name="builtin-seed",
            ))
        db.commit()

        # Spawn all existing agents into the world on startup.
        for agent in db.query(Agent).all():
            world_engine.spawn_agent(agent)
    finally:
        db.close()

    app.state.world_task = asyncio.create_task(world_engine.run(SessionLocal))


@app.on_event("shutdown")
async def shutdown_event():
    world_engine.running = False
    task = getattr(app.state, "world_task", None)
    if task:
        task.cancel()


@app.get("/", response_class=HTMLResponse)
def observer_home():
    html_path = BASE_DIR / "templates" / "observer.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/healthz")
def healthz():
    return {"ok": True, "tick": world_engine.tick}


@app.websocket("/ws/world")
async def ws_world(websocket: WebSocket):
    await world_engine.ws.connect(websocket)
    try:
        # send initial snapshot
        await websocket.send_json({"type": "world_tick", "data": {
            "tick": world_engine.tick,
            "agents": [
                {
                    "agent_id": s.agent_id,
                    "public_name": s.public_name,
                    "x": s.x,
                    "y": s.y,
                    "state": s.state,
                }
                for s in world_engine.agent_states.values()
            ],
            "hall_chat_tail": list(world_engine.hall_chat)[-20:],
        }})

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        world_engine.ws.disconnect(websocket)
