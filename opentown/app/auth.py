import secrets
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import AgentSession


def issue_session_token() -> str:
    return secrets.token_urlsafe(32)


def touch_session(db: Session, token: str) -> AgentSession:
    session = db.query(AgentSession).filter(AgentSession.token == token, AgentSession.online == True).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")
    session.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session
