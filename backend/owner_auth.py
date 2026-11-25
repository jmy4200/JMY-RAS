"""Owner login sessions and password-attempt throttling."""

import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timezone

from .db import connect

OWNER_SESSION_TTL_SECONDS = 8 * 60 * 60
OWNER_LOGIN_ATTEMPT_LIMIT = 5
OWNER_LOGIN_WINDOW_SECONDS = 15 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def record_owner_action(event: str, session_id: str) -> None:
    """Append an owner action to the system audit trail without exposing its token."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_events(event,device_id,details,timestamp) VALUES(?,NULL,?,?)",
            (
                event,
                json.dumps({"owner_session_id": session_id}),
                _now_iso(),
            ),
        )


def consume_owner_login_attempt(client_host: str) -> tuple[bool, int]:
    """Atomically count login attempts so concurrent requests cannot bypass the limit."""
    host = (client_host or "unknown")[:255]
    now = time.time()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT window_started,attempts FROM owner_login_limits WHERE client_host=?",
            (host,),
        ).fetchone()
        if row is None or now - row["window_started"] >= OWNER_LOGIN_WINDOW_SECONDS:
            conn.execute(
                """INSERT INTO owner_login_limits(client_host,window_started,attempts)
                   VALUES(?,?,1)
                   ON CONFLICT(client_host) DO UPDATE SET
                     window_started=excluded.window_started, attempts=1""",
                (host, now),
            )
            limited, retry_after = False, 0
        elif row["attempts"] >= OWNER_LOGIN_ATTEMPT_LIMIT:
            limited = True
            retry_after = max(
                1,
                int(OWNER_LOGIN_WINDOW_SECONDS - (now - row["window_started"])),
            )
        else:
            conn.execute(
                "UPDATE owner_login_limits SET attempts=attempts+1 WHERE client_host=?",
                (host,),
            )
            limited, retry_after = False, 0
        conn.execute(
            "DELETE FROM owner_login_limits WHERE window_started < ?",
            (now - 86400,),
        )
    return limited, retry_after


def clear_owner_login_attempts(client_host: str) -> None:
    host = (client_host or "unknown")[:255]
    with connect() as conn:
        conn.execute("DELETE FROM owner_login_limits WHERE client_host=?", (host,))

def create_owner_session() -> tuple[str, int]:
    token = secrets.token_urlsafe(48)
    expires_at = int(time.time()) + OWNER_SESSION_TTL_SECONDS
    with connect() as conn:
        conn.execute(
            """INSERT INTO owner_sessions(id,token_hash,created_at,expires_at,last_seen,revoked_at)
               VALUES(?,?,?,?,?,NULL)""",
            (
                str(uuid.uuid4()),
                _token_hash(token),
                _now_iso(),
                expires_at,
                _now_iso(),
            ),
        )
    return token, expires_at


def authenticate_owner_session(token: str):
    now = int(time.time())
    with connect() as conn:
        row = conn.execute(
            """SELECT id,created_at,expires_at
               FROM owner_sessions
               WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?""",
            (_token_hash(token), now),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE owner_sessions SET last_seen=? WHERE id=?",
            (_now_iso(), row["id"]),
        )
        return dict(row)


def revoke_owner_session(session_id: str) -> bool:
    with connect() as conn:
        result = conn.execute(
            "UPDATE owner_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
            (_now_iso(), session_id),
        )
    return result.rowcount == 1
