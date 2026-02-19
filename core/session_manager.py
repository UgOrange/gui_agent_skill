"""Session management for GUI Agent Skill."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Session:
    session_id: str
    device_id: str
    provider: str
    task: str
    created_at: float
    updated_at: float
    status: str = "active"  # active, completed, expired
    step_count: int = 0
    last_result: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(**data)


class SessionManager:
    """Manage persistent GUI agent task sessions."""

    def __init__(self, storage_dir: Path | str | None = None, expire_seconds: int = 3600):
        if storage_dir is None:
            storage_dir = Path.home() / ".gui_agent_skill" / "sessions"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.expire_seconds = expire_seconds
        self._sessions: dict[str, Session] = {}
        self._load_sessions()

    def _get_session_file(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.json"

    def _load_sessions(self) -> None:
        """Load all sessions from disk."""
        for session_file in self.storage_dir.glob("*.json"):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                if time.time() - session.updated_at > self.expire_seconds:
                    session.status = "expired"
                self._sessions[session.session_id] = session
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

    def _save_session(self, session: Session) -> None:
        """Save one session to disk."""
        session_file = self._get_session_file(session.session_id)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    def create_session(
        self,
        device_id: str,
        provider: str,
        task: str,
    ) -> Session:
        """Create a new active session."""
        session_id = str(uuid.uuid4())[:8]
        now = time.time()
        session = Session(
            session_id=session_id,
            device_id=device_id,
            provider=provider,
            task=task,
            created_at=now,
            updated_at=now,
        )
        self._sessions[session_id] = session
        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if time.time() - session.updated_at > self.expire_seconds:
            session.status = "expired"
            self._save_session(session)
        return session

    def update_session(
        self,
        session_id: str,
        result: dict[str, Any],
        status: str | None = None,
    ) -> Session | None:
        """Update result/status for one session."""
        session = self._sessions.get(session_id)
        if session is None:
            return None

        session.updated_at = time.time()
        session.step_count += 1
        session.last_result = result
        session.history.append({
            "step": session.step_count,
            "timestamp": session.updated_at,
            "result": result,
        })

        if status:
            session.status = status

        self._save_session(session)
        return session

    def complete_session(self, session_id: str) -> Session | None:
        """Mark a session as completed."""
        return self.update_session(session_id, {}, status="completed")

    def list_active_sessions(self) -> list[Session]:
        """Return all non-expired active sessions."""
        now = time.time()
        active = []
        for session in self._sessions.values():
            if session.status == "active":
                if now - session.updated_at > self.expire_seconds:
                    session.status = "expired"
                    self._save_session(session)
                else:
                    active.append(session)
        return active

    def get_latest_session(self, device_id: str | None = None) -> Session | None:
        """Get latest active session, optionally filtered by device."""
        active = self.list_active_sessions()
        if device_id:
            active = [s for s in active if s.device_id == device_id]
        if not active:
            return None
        return max(active, key=lambda s: s.updated_at)

    def cleanup_expired(self) -> int:
        """Remove expired sessions from memory and disk."""
        now = time.time()
        expired_ids = []
        for session_id, session in self._sessions.items():
            if now - session.updated_at > self.expire_seconds:
                expired_ids.append(session_id)

        for session_id in expired_ids:
            session_file = self._get_session_file(session_id)
            if session_file.exists():
                session_file.unlink()
            del self._sessions[session_id]

        return len(expired_ids)

    def delete_session(self, session_id: str) -> bool:
        """Delete one session."""
        if session_id not in self._sessions:
            return False
        session_file = self._get_session_file(session_id)
        if session_file.exists():
            session_file.unlink()
        del self._sessions[session_id]
        return True
