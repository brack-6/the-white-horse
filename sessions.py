"""
Session and Table store for The White Horse.

v0.2 additions:
- tables: named shared sessions where multiple agents sit together
- table_context: accumulated drunk outputs that get injected into new arrivals' prompts
- sessions now have an optional table_id foreign key
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "logs" / "sessions.db"


class SessionStore:

    def __init__(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(DB_PATH)

    def _init_db(self):
        with self._connect() as conn:
            # Individual pint sessions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id   TEXT PRIMARY KEY,
                    timestamp    TEXT,
                    agent_id     TEXT,
                    pint         TEXT,
                    prompt       TEXT,
                    sober_output TEXT,
                    drunk_output TEXT,
                    tokens       INTEGER,
                    risk_score   TEXT DEFAULT 'low',
                    model        TEXT,
                    accepted     INTEGER DEFAULT 1,
                    closed       INTEGER DEFAULT 0,
                    table_id     TEXT DEFAULT NULL
                )
            """)

            # Shared tables — multi-agent sessions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tables (
                    table_id     TEXT PRIMARY KEY,
                    name         TEXT,
                    created_at   TEXT,
                    created_by   TEXT,
                    open         INTEGER DEFAULT 1,
                    context      TEXT DEFAULT ''
                )
            """)

            # Table membership — which agents have joined which table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS table_members (
                    table_id     TEXT,
                    agent_id     TEXT,
                    joined_at    TEXT,
                    PRIMARY KEY (table_id, agent_id)
                )
            """)

            conn.commit()

    # ── Solo session methods ──────────────────────────────────────────────────

    def save(
        self,
        agent_id: str,
        pint: str,
        prompt: str,
        sober_output: str,
        drunk_output: str,
        tokens: int,
        risk_score: str,
        model: str,
        table_id: Optional[str] = None
    ) -> str:
        session_id = str(uuid.uuid4())
        timestamp  = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO sessions
                (session_id, timestamp, agent_id, pint, prompt,
                 sober_output, drunk_output, tokens, risk_score, model, table_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, timestamp, agent_id, pint, prompt,
                sober_output, drunk_output, tokens, risk_score, model, table_id
            ))
            conn.commit()
        return session_id

    def close_session(self, session_id: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET closed = 1 WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()

    def list_sessions(self, agent_id: Optional[str] = None):
        with self._connect() as conn:
            if agent_id:
                rows = conn.execute(
                    "SELECT session_id, timestamp, agent_id, pint, tokens, risk_score, accepted, table_id "
                    "FROM sessions WHERE agent_id = ? ORDER BY timestamp DESC LIMIT 50",
                    (agent_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT session_id, timestamp, agent_id, pint, tokens, risk_score, accepted, table_id "
                    "FROM sessions ORDER BY timestamp DESC LIMIT 50"
                ).fetchall()

        keys = ["session_id", "timestamp", "agent_id", "pint", "tokens", "risk_score", "accepted", "table_id"]
        return [dict(zip(keys, row)) for row in rows]

    # ── Table methods ─────────────────────────────────────────────────────────

    def create_table(self, name: str, agent_id: str) -> str:
        """Create a new shared table. Returns table_id."""
        table_id   = str(uuid.uuid4())[:8]   # short ID — easier to share
        created_at = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO tables (table_id, name, created_at, created_by, open, context)
                VALUES (?, ?, ?, ?, 1, '')
            """, (table_id, name, created_at, agent_id))
            # Creator automatically joins
            conn.execute("""
                INSERT INTO table_members (table_id, agent_id, joined_at)
                VALUES (?, ?, ?)
            """, (table_id, agent_id, created_at))
            conn.commit()
        print(f"[TABLE] {agent_id} created table '{name}' ({table_id})")
        return table_id

    def join_table(self, table_id: str, agent_id: str) -> Optional[dict]:
        """Agent joins an existing table. Returns current table state or None if not found."""
        with self._connect() as conn:
            table = conn.execute(
                "SELECT table_id, name, created_by, open, context FROM tables WHERE table_id = ?",
                (table_id,)
            ).fetchone()
            if not table:
                return None
            if not table[3]:  # open flag
                return {"error": "table is closed"}

            # Upsert membership
            conn.execute("""
                INSERT OR IGNORE INTO table_members (table_id, agent_id, joined_at)
                VALUES (?, ?, ?)
            """, (table_id, agent_id, datetime.utcnow().isoformat()))
            conn.commit()

            members = conn.execute(
                "SELECT agent_id FROM table_members WHERE table_id = ?",
                (table_id,)
            ).fetchall()

        print(f"[TABLE] {agent_id} joined table '{table[1]}' ({table_id})")
        return {
            "table_id":    table[0],
            "name":        table[1],
            "created_by":  table[2],
            "members":     [m[0] for m in members],
            "context":     table[4]   # accumulated drunk outputs so far
        }

    def get_table_context(self, table_id: str) -> str:
        """Return accumulated drunk outputs for this table."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT context FROM tables WHERE table_id = ?",
                (table_id,)
            ).fetchone()
        return row[0] if row else ""

    def append_table_context(self, table_id: str, agent_id: str, drunk_output: str, pint_name: str):
        """Append a drunk output to the table's shared context window."""
        timestamp = datetime.utcnow().strftime("%H:%M")
        entry = f"\n\n[{timestamp} | {agent_id} | {pint_name}]\n{drunk_output}"
        with self._connect() as conn:
            conn.execute(
                "UPDATE tables SET context = context || ? WHERE table_id = ?",
                (entry, table_id)
            )
            conn.commit()

    def get_table(self, table_id: str) -> Optional[dict]:
        """Full table info including members and recent session summaries."""
        with self._connect() as conn:
            table = conn.execute(
                "SELECT table_id, name, created_at, created_by, open, context FROM tables WHERE table_id = ?",
                (table_id,)
            ).fetchone()
            if not table:
                return None

            members = conn.execute(
                "SELECT agent_id, joined_at FROM table_members WHERE table_id = ?",
                (table_id,)
            ).fetchall()

            recent = conn.execute(
                "SELECT agent_id, pint, timestamp FROM sessions WHERE table_id = ? ORDER BY timestamp DESC LIMIT 20",
                (table_id,)
            ).fetchall()

        return {
            "table_id":   table[0],
            "name":       table[1],
            "created_at": table[2],
            "created_by": table[3],
            "open":       bool(table[4]),
            "context":    table[5],
            "members":    [{"agent_id": m[0], "joined_at": m[1]} for m in members],
            "rounds":     [{"agent_id": r[0], "pint": r[1], "at": r[2]} for r in recent]
        }

    def close_table(self, table_id: str):
        with self._connect() as conn:
            conn.execute("UPDATE tables SET open = 0 WHERE table_id = ?", (table_id,))
            conn.commit()

    def list_tables(self, open_only: bool = True):
        with self._connect() as conn:
            if open_only:
                rows = conn.execute(
                    "SELECT table_id, name, created_by, created_at FROM tables WHERE open = 1 ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT table_id, name, created_by, created_at FROM tables ORDER BY created_at DESC LIMIT 50"
                ).fetchall()
        keys = ["table_id", "name", "created_by", "created_at"]
        return [dict(zip(keys, row)) for row in rows]
