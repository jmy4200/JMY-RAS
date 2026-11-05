import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("JMY_DATABASE_PATH", "./jmy_ras.db")).expanduser()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            last_seen TEXT
        );
        CREATE TABLE IF NOT EXISTS pairing_codes (
            code_hash TEXT PRIMARY KEY,
            expires_at REAL NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            device_id TEXT,
            details TEXT NOT NULL DEFAULT '{}',
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sync_events (
            event_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            note TEXT NOT NULL,
            client_created_at TEXT NOT NULL,
            received_at TEXT NOT NULL,
            FOREIGN KEY(device_id) REFERENCES devices(id)
        );
        CREATE INDEX IF NOT EXISTS idx_sync_events_received
            ON sync_events(received_at);
        """)
