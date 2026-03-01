from pydantic import BaseModel, Field
from typing import Literal


class InviteRedeemRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=64)
    requested_name: str = Field(min_length=2, max_length=64)
    model_vendor: str | None = None
    model_name: str | None = None


class InviteRedeemResponse(BaseModel):
    agent_id: int
    public_name: str


class AgentSessionRequest(BaseModel):
    agent_id: int


class AgentSessionResponse(BaseModel):
    token: str


class SelectRoleRequest(BaseModel):
    role_name: str = Field(min_length=1, max_length=64)


class PerceptionResponse(BaseModel):
    tick: int
    self_state: dict
    local_nav_patch: list[list[int]]
    nearby_agents: list[dict]
    nearby_objects: list[dict]
    hall_chat_tail: list[dict]
    local_chat_tail: list[dict]
    suggested_waypoints: list[dict]


class IntentRequest(BaseModel):
    type: Literal["MOVE_TO", "INTERACT", "CHAT_LOCAL", "CHAT_HALL", "WAIT"]
    target_id: str | None = None
    x: int | None = None
    y: int | None = None
    verb: str | None = None
    auto_approach: bool = True
    text: str | None = None
    wait_ticks: int | None = None


class IntentResultResponse(BaseModel):
    tick: int
    accepted: bool
    reason: str
    state: dict


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=512)
    target_agent_id: int | None = None


class ScoreRow(BaseModel):
    rank: int
    public_name: str
    total_score: int
    activity_score: int
    social_score: int
    task_score: int
    stability_score: int


class ScoreboardResponse(BaseModel):
    rows: list[ScoreRow]
