import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

from backend import db
from backend.security import hash_secret, pair_device


def test_init_db_migrates_legacy_devices_table(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.sqlite3"
    legacy_connection = sqlite3.connect(database_path)
    legacy_connection.execute(
        """CREATE TABLE devices (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            last_seen TEXT
        )"""
    )
    legacy_connection.execute(
        """INSERT INTO devices
           (id,name,platform,token_hash,created_at,last_seen)
           VALUES(?,?,?,?,?,?)""",
        ("existing-device", "Existing phone", "Android", "a" * 64, "2026-01-01T00:00:00+00:00", None),
    )
    legacy_connection.commit()
    legacy_connection.close()

    monkeypatch.setattr(db, "DB_PATH", database_path)
    db.init_db()

    with db.connect() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(devices)")}
        device = connection.execute(
            "SELECT id,name,is_active FROM devices WHERE id=?",
            ("existing-device",),
        ).fetchone()

    assert "is_active" in columns
    assert device["name"] == "Existing phone"
    assert device["is_active"] == 1


def test_pairing_code_can_only_be_claimed_once_concurrently(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "pairing.sqlite3")
    db.init_db()

    with db.connect() as connection:
        connection.execute(
            "INSERT INTO pairing_codes(code_hash,expires_at) VALUES(?,?)",
            (hash_secret("123456"), time.time() + 300),
        )

    def claim(index):
        return pair_device("123456", f"device-{index}", "Linux")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, range(2)))

    assert sum(result is not None for result in results) == 1

    with db.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    assert count == 1
