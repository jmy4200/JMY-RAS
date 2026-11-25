import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timezone

from .db import connect

PAIRING_TTL_SECONDS = 300
PAIRING_ATTEMPT_LIMIT = 10
PAIRING_ATTEMPT_WINDOW_SECONDS = 300


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def check_pairing_rate_limit(client_host: str) -> tuple[bool, int]:
    """Allow a bounded number of pairing claims per source during each window."""
    host = (client_host or "unknown")[:255]
    now = time.time()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT window_started,attempts FROM pairing_attempt_limits WHERE client_host=?",
            (host,),
        ).fetchone()

        if row is None or now - row["window_started"] >= PAIRING_ATTEMPT_WINDOW_SECONDS:
            conn.execute(
                """INSERT INTO pairing_attempt_limits(client_host,window_started,attempts)
                   VALUES(?,?,1)
                   ON CONFLICT(client_host) DO UPDATE SET
                     window_started=excluded.window_started, attempts=1""",
                (host, now),
            )
            limited = False
            retry_after = 0
        elif row["attempts"] >= PAIRING_ATTEMPT_LIMIT:
            limited = True
            retry_after = max(
                1,
                int(PAIRING_ATTEMPT_WINDOW_SECONDS - (now - row["window_started"])),
            )
        else:
            conn.execute(
                "UPDATE pairing_attempt_limits SET attempts=attempts+1 WHERE client_host=?",
                (host,),
            )
            limited = False
            retry_after = 0

        # Bound table growth without deleting active rate-limit windows.
        conn.execute(
            "DELETE FROM pairing_attempt_limits WHERE window_started < ?",
            (now - 86400,),
        )
    return limited, retry_after


def create_pairing_code():
    code = f"{secrets.randbelow(1_000_000):06d}"
    with connect() as conn:
        conn.execute("DELETE FROM pairing_codes WHERE expires_at < ?", (time.time(),))
        conn.execute(
            "INSERT INTO pairing_codes(code_hash, expires_at) VALUES (?, ?)",
            (hash_secret(code), time.time() + PAIRING_TTL_SECONDS),
        )
    return code


def pair_device(code: str, name: str, platform_name: str):
    code_digest = hash_secret(code)
    token = secrets.token_urlsafe(32)
    device_id = str(uuid.uuid4())
    with connect() as conn:
        # Claim the code with one conditional write. SQLite serializes writers,
        # so concurrent requests cannot both change the same unused code.
        claimed = conn.execute(
            """UPDATE pairing_codes
               SET used=1
               WHERE code_hash=? AND used=0 AND expires_at>=?""",
            (code_digest, time.time()),
        )
        if claimed.rowcount != 1:
            return None

        created_at = now_iso()
        conn.execute(
            """INSERT INTO devices
               (id,name,platform,token_hash,created_at,last_seen,is_active)
               VALUES(?,?,?,?,?,?,1)""",
            (
                device_id,
                name[:80],
                platform_name[:80],
                hash_secret(token),
                created_at,
                created_at,
            ),
        )
        conn.execute(
            "INSERT INTO audit_events(event,device_id,details,timestamp) VALUES(?,?,?,?)",
            ("device_paired", device_id, '{"result":"success"}', created_at),
        )
    return {"device_id": device_id, "access_token": token, "token_type": "bearer"}


def authenticate_token(token: str):
    digest = hash_secret(token)
    with connect() as conn:
        row = conn.execute(
            """SELECT id,name,platform FROM devices
               WHERE token_hash=? AND is_active=1""",
            (digest,),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE devices SET last_seen=? WHERE id=?", (now_iso(), row["id"]))
        conn.execute(
            "INSERT INTO audit_events(event,device_id,details,timestamp) VALUES(?,?,?,?)",
            ("authenticated_request", row["id"], "{}", now_iso()),
        )
        return dict(row)


def revoke_device(device_id: str, actor: str = "device", actor_id: str | None = None) -> bool:
    """Revoke a device credential and record who initiated the action."""
    timestamp = now_iso()
    with connect() as conn:
        result = conn.execute(
            "UPDATE devices SET is_active=0 WHERE id=? AND is_active=1",
            (device_id,),
        )
        if result.rowcount != 1:
            return False
        conn.execute(
            "INSERT INTO audit_events(event,device_id,details,timestamp) VALUES(?,?,?,?)",
            ("device_revoked", device_id, json.dumps({"actor": actor, "actor_id": actor_id}), timestamp),
        )
    return True
