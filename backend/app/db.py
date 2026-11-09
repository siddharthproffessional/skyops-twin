"""SQLite persistence and audit trail (no ORM)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_default_db = "/tmp/skyops.db" if os.getenv("VERCEL") else Path(__file__).resolve().parent.parent / "data" / "skyops.db"
DB_PATH = Path(os.getenv("SKYOPS_DB", _default_db))
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, created REAL, label TEXT, disruption TEXT,
  status TEXT, recommendation TEXT, ai_mode TEXT);
CREATE TABLE IF NOT EXISTS agent_events (id INTEGER PRIMARY KEY AUTOINCREMENT, incident TEXT, ts REAL,
  type TEXT, agent TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS recovery_plans (incident TEXT, plan_id TEXT, name TEXT, levers TEXT, metrics TEXT,
  objective REAL, feasible INTEGER, recommended INTEGER, PRIMARY KEY (incident, plan_id));
CREATE TABLE IF NOT EXISTS approvals (id INTEGER PRIMARY KEY AUTOINCREMENT, incident TEXT, plan_id TEXT,
  decision TEXT, note TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, action TEXT, detail TEXT);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.executescript(SCHEMA)
    return c


_c = _conn()


def execute(sql: str, args: tuple = ()) -> None:
    with _lock:
        _c.execute(sql, args)
        _c.commit()


def query(sql: str, args: tuple = ()) -> list[tuple]:
    with _lock:
        return _c.execute(sql, args).fetchall()


def audit(action: str, detail: dict | str) -> None:
    execute("INSERT INTO audit_events (ts, action, detail) VALUES (?, ?, ?)",
            (time.time(), action, json.dumps(detail, default=str) if not isinstance(detail, str) else detail))


def log_event(incident: str, ev: dict) -> None:
    execute("INSERT INTO agent_events (incident, ts, type, agent, payload) VALUES (?, ?, ?, ?, ?)",
            (incident, time.time(), ev.get("type"), ev.get("agent") or ev.get("from"),
             json.dumps(ev, default=str)))
