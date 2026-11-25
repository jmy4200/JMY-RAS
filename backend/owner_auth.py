"""Owner login sessions and password-attempt throttling."""

import hashlib
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


def owner_login_limit(client_host: str) -> tuple[bool, int]:
    host = (client_host or "unknown")[:255]
    now = time.time()
    with connect() as conn:
        row = conn.execute(
            "SELECT window_started,attempts FROM owner_login_limits WHERE client_host=?",
            (host,),
        ).fetchone()
        if row is None or now - row["window_started"] >= OWNER_LOGIN_WINDOW_SECONDS:
            return False, 0
        if row["attempts"] >= OWNER_LOGIN_ATTEMPT_LIMIT:
            retry_after = max(
                1,
                int(OWNER_LOGIN_WINDOW_SECONDS - (now - row["window_started"])),
            )
            return True, retry_after
        return False, 0


def record_owner_login_failure(client_host: str) -> None:
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
        else:
            conn.execute(
                "UPDATE owner_login_limits SET attempts=attempts+1 WHERE client_host=?",
                (host,),
            )
        conn.execute(
            "DELETE FROM owner_login_limits WHERE window_started < ?",
            (now - 86400,),
        )


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
