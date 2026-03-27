"""
steward.py — The White Horse Steward
N100-optimised. No regex. No LLM scoring. One phi call per order, async.

Pipeline:
  drunk + sober → divergence (math) → gate → distil (phi, bg) → store → propagate
"""

import sqlite3
import os
import json
import time
import threading
import hashlib
import urllib.request
from pathlib import Path
from datetime import datetime, timezone


# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────

OLLAMA_URL   = os.getenv("OLLAMA_URL",    "http://localhost:11434")
DISTIL_MODEL = os.getenv("DISTIL_MODEL",  "phi")          # fastest local model
DIV_THRESHOLD  = float(os.getenv("DIV_THRESHOLD",  "0.3"))  # below = pint did nothing
DB_PATH      = Path(__file__).parent / "logs" / "steward.db"

DISTIL_PROMPT = (
    "Output one sentence only — the single most surprising or generative idea "
    "in the text below. No preamble, no explanation, just the sentence.\n\n"
    "Text: {drunk}"
)


# ─────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS fragments (
    id            TEXT PRIMARY KEY,
    session_id    TEXT,
    table_id      TEXT,
    agent_id      TEXT,
    pint          TEXT,
    sober_output  TEXT,
    drunk_output  TEXT,
    fragment      TEXT,
    divergence    REAL,
    propagated    INTEGER DEFAULT 0,
    built_on_by   TEXT,
    timestamp     TEXT
);
"""


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# ─────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────

def divergence(sober: str, drunk: str) -> float:
    """
    Jaccard distance on word sets.
    0.0 = identical  →  1.0 = completely different.
    Pure math. Zero latency.
    """
    s = set(sober.lower().split())
    d = set(drunk.lower().split())
    if not s and not d:
        return 0.0
    union = s | d
    if not union:
        return 0.0
    return 1.0 - len(s & d) / len(union)


def distil(drunk: str) -> str | None:
    """
    One phi call, 60 token ceiling, 15s timeout.
    Returns a single sentence or None on failure.
    """
    payload = {
        "model":  DISTIL_MODEL,
        "prompt": DISTIL_PROMPT.format(drunk=drunk[:1200]),  # cap input
        "stream": False,
        "options": {
            "num_predict": 60,
            "temperature": 0.3,
        }
    }
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            fragment = result.get("response", "").strip()
            # strip any accidental multi-sentence bleed
            fragment = fragment.split(".")[0].strip()
            if len(fragment) < 10:
                return None
            return fragment + ("." if not fragment.endswith(".") else "")
    except Exception:
        return None


def fragment_id(session_id: str, agent_id: str) -> str:
    ts = str(time.time_ns())
    raw = f"{session_id}-{agent_id}-{ts}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ─────────────────────────────────────────
# STEWARD CLASS
# ─────────────────────────────────────────

class Steward:

    def __init__(self):
        self.conn = _connect()
        self._lock = threading.Lock()

    # ── public entry point ──────────────────

    def process(
        self,
        sober_output: str,
        drunk_output:  str,
        agent_id:      str,
        session_id:    str,
        pint:          str,
        table_id:      str | None = None,
    ) -> dict:
        """
        Called after every /order, synchronously for divergence + gate,
        then kicks off distil in a background thread.

        Returns immediately with:
          { "fragment_id": ..., "divergence": ..., "propagated": bool|"pending" }
        """
        div   = divergence(sober_output, drunk_output)
        fid   = fragment_id(session_id, agent_id)
        ts    = datetime.now(timezone.utc).isoformat()

        if div < DIV_THRESHOLD:
            # Pint did nothing interesting — log only, no distil call
            self._store(
                fid, session_id, table_id, agent_id, pint,
                sober_output, drunk_output,
                fragment=None, div=div, propagated=0, ts=ts
            )
            return {"fragment_id": fid, "divergence": round(div, 3), "propagated": False}

        # Divergence is interesting — distil in background
        threading.Thread(
            target=self._bg_distil,
            args=(fid, session_id, table_id, agent_id, pint,
                  sober_output, drunk_output, div, ts),
            daemon=True
        ).start()

        return {"fragment_id": fid, "divergence": round(div, 3), "propagated": "pending"}

    # ── table context for next round ────────

    def table_context(self, table_id: str) -> str | None:
        """
        Returns the most recent propagated fragment for a table,
        formatted as a single overheard line.
        Returns None if nothing has propagated yet.
        """
        with self._lock:
            cur = self.conn.execute("""
                SELECT fragment FROM fragments
                WHERE table_id = ? AND propagated = 1 AND fragment IS NOT NULL
                ORDER BY timestamp DESC LIMIT 1
            """, (table_id,))
            row = cur.fetchone()
        if row and row["fragment"]:
            return f'Overheard at this table: "{row["fragment"]}"'
        return None

    # ── mark built-on ───────────────────────

    def mark_built_on(self, fragment_id: str, by_agent_id: str):
        """Call this when an agent explicitly builds on a fragment."""
        with self._lock:
            self.conn.execute(
                "UPDATE fragments SET built_on_by = ? WHERE id = ?",
                (by_agent_id, fragment_id)
            )
            self.conn.commit()

    # ── tab / history ───────────────────────

    def tab(self, session_id: str) -> list[dict]:
        """Full fragment history for a session, newest first."""
        with self._lock:
            cur = self.conn.execute("""
                SELECT id, agent_id, pint, fragment, divergence,
                       propagated, built_on_by, timestamp
                FROM fragments
                WHERE session_id = ?
                ORDER BY timestamp DESC
            """, (session_id,))
            return [dict(r) for r in cur.fetchall()]

    def best_pints(self, limit: int = 5) -> list[dict]:
        """
        Pints ranked by how often their fragments got built on.
        This is the honest long-term quality signal.
        """
        with self._lock:
            cur = self.conn.execute("""
                SELECT pint,
                       COUNT(*) as orders,
                       SUM(propagated) as propagations,
                       SUM(CASE WHEN built_on_by IS NOT NULL THEN 1 ELSE 0 END) as built_on
                FROM fragments
                GROUP BY pint
                ORDER BY built_on DESC, propagations DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    # ── internals ───────────────────────────

    def _bg_distil(
        self, fid, session_id, table_id, agent_id, pint,
        sober, drunk, div, ts
    ):
        fragment = distil(drunk)
        propagated = 1 if fragment else 0
        self._store(
            fid, session_id, table_id, agent_id, pint,
            sober, drunk, fragment, div, propagated, ts
        )

    def _store(
        self, fid, session_id, table_id, agent_id, pint,
        sober, drunk, fragment, div, propagated, ts
    ):
        with self._lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO fragments
                  (id, session_id, table_id, agent_id, pint,
                   sober_output, drunk_output, fragment,
                   divergence, propagated, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fid, session_id, table_id, agent_id, pint,
                  sober, drunk, fragment, div, propagated, ts))
            self.conn.commit()
