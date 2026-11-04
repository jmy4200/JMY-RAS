import hashlib
import secrets
import time
import uuid
from datetime import datetime, timezone

from .db import connect

PAIRING_TTL_SECONDS = 300


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
        row = conn.execute(
            "SELECT expires_at, used FROM pairing_codes WHERE code_hash=?",
            (code_digest,),
        ).fetchone()
        if not row or row["used"] or row["expires_at"] < time.time():
            return None
        conn.execute("UPDATE pairing_codes SET used=1 WHERE code_hash=?", (code_digest,))
        conn.execute(
            """INSERT INTO devices(id,name,platform,token_hash,created_at,last_seen)
               VALUES(?,?,?,?,?,?)""",
            (device_id, name[:80], platform_name[:80], hash_secret(token), now_iso(), now_iso()),
        )
        conn.execute(
            "INSERT INTO audit_events(event,device_id,details,timestamp) VALUES(?,?,?,?)",
            ("device_paired", device_id, '{"result":"success"}', now_iso()),
        )
    return {"device_id": device_id, "access_token": token, "token_type": "bearer"}


def authenticate_token(token: str):
    digest = hash_secret(token)
    with connect() as conn:
        row = conn.execute(
            "SELECT id,name,platform FROM devices WHERE token_hash=?", (digest,)
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE devices SET last_seen=? WHERE id=?", (now_iso(), row["id"]))
        conn.execute(
            "INSERT INTO audit_events(event,device_id,details,timestamp) VALUES(?,?,?,?)",
            ("authenticated_request", row["id"], "{}", now_iso()),
        )
        return dict(row)
