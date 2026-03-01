from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    issued_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invite_code: Mapped[str] = mapped_column(String(64), unique=True)
    role_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_vendor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sessions: Mapped[list["AgentSession"]] = relationship(back_populates="agent")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    online: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    agent: Mapped[Agent] = relationship(back_populates="sessions")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), index=True)  # local/hall
    sender_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    target_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text)
    tick: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentScore(Base):
    __tablename__ = "agent_scores"
    __table_args__ = (UniqueConstraint("agent_id", name="uq_agent_score_agent"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, index=True)
    activity_score: Mapped[int] = mapped_column(Integer, default=0)
    social_score: Mapped[int] = mapped_column(Integer, default=0)
    task_score: Mapped[int] = mapped_column(Integer, default=0)
    stability_score: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorldEvent(Base):
    __tablename__ = "world_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tick: Mapped[int] = mapped_column(Integer, index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
