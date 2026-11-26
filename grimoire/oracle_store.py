"""SQLite persistence store for Delphic Oracle sessions and multi-turn threads.

Keeps oracle consultations, hardware-entropy spreads, Haruspex smoke packets,
and Pythia dialogues in WAL-mode SQLite (`data/oracle.db`), strictly separate
from the pure Markdown journal directory.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "oracle.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS oracle_sessions (
    id TEXT PRIMARY KEY,
    date_key TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    spread_json TEXT,
    entrails_summary_json TEXT,
    smoke_packet TEXT NOT NULL DEFAULT '',
    omen_markdown TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_oracle_sessions_date_key
    ON oracle_sessions(date_key, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_oracle_sessions_updated_at
    ON oracle_sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS oracle_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES oracle_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    cast_data_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_oracle_messages_session_id
    ON oracle_messages(session_id, id ASC);
"""


def _now_iso() -> str:
    """ISO-8601 local timestamp with millisecond precision for deterministic ordering."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _summarize_spread(spread: dict[str, Any] | None) -> str:
    """Build a compact talisman summary line for session list sidebars."""
    if not isinstance(spread, dict) or not spread:
        return ""

    parts: list[str] = []

    cards = spread.get("cards")
    if isinstance(cards, list) and cards:
        card_names = [
            str(c.get("name")).strip()
            for c in cards[:3]
            if isinstance(c, dict) and c.get("name")
        ]
        if card_names:
            parts.append(" / ".join(card_names))
    elif isinstance(spread.get("card"), dict) and spread["card"].get("name"):
        parts.append(str(spread["card"]["name"]).strip())

    iching = spread.get("iching")
    if isinstance(iching, dict):
        raw_primary = iching.get("primary")
        primary: dict[str, Any] = raw_primary if isinstance(raw_primary, dict) else iching
        num = primary.get("number")
        name = primary.get("name")
        raw_transformed = iching.get("transformed")
        transformed = raw_transformed if isinstance(raw_transformed, dict) else None
        if num and name:
            hex_label = f"Hex {num} {name}"
            if transformed and transformed.get("number"):
                hex_label += f" -> {transformed['number']}"
            parts.append(hex_label)
        elif name:
            parts.append(str(name))

    runes = spread.get("runes")
    if isinstance(runes, list) and runes:
        first_rune = runes[0]
        if isinstance(first_rune, dict) and first_rune.get("name"):
            glyph = str(first_rune.get("glyph") or "").strip()
            rname = str(first_rune["name"]).strip()
            parts.append(f"{glyph} {rname}".strip())
    elif isinstance(spread.get("rune"), dict) and spread["rune"].get("name"):
        rune_obj = spread["rune"]
        glyph = str(rune_obj.get("glyph") or "").strip()
        rname = str(rune_obj["name"]).strip()
        parts.append(f"{glyph} {rname}".strip())

    return " · ".join(p for p in parts if p)


class OracleStore:
    """WAL-mode SQLite store for Oracle sessions, spreads, omens, and chat threads."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.executescript(_SCHEMA_SQL)

    def _row_to_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        spread = _json_loads(row["spread_json"])
        omen_md = row["omen_markdown"] or ""
        return {
            "id": row["id"],
            "date_key": row["date_key"],
            "title": row["title"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "has_omen": bool(omen_md.strip()),
            "card_summary": _summarize_spread(spread),
            "message_count": int(row["message_count"] or 0),
        }

    def _fetch_session_unlocked(self, conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT
                s.id,
                s.date_key,
                s.title,
                s.spread_json,
                s.entrails_summary_json,
                s.smoke_packet,
                s.omen_markdown,
                s.created_at,
                s.updated_at
            FROM oracle_sessions s
            WHERE s.id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None

        msg_rows = conn.execute(
            """
            SELECT id, role, content, cast_data_json, created_at
            FROM oracle_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

        messages: list[dict[str, Any]] = [
            {
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "cast_data": _json_loads(m["cast_data_json"]),
                "created_at": m["created_at"],
            }
            for m in msg_rows
        ]

        spread = _json_loads(row["spread_json"])
        entrails_summary = _json_loads(row["entrails_summary_json"])
        omen_markdown = row["omen_markdown"] or ""

        return {
            "id": row["id"],
            "date_key": row["date_key"],
            "title": row["title"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "has_omen": bool(omen_markdown.strip()),
            "card_summary": _summarize_spread(spread),
            "message_count": len(messages),
            "spread": spread,
            "entrails_summary": entrails_summary,
            "smoke_packet": row["smoke_packet"] or "",
            "omen_markdown": omen_markdown,
            "messages": messages,
        }

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        capped_limit = max(1, int(limit))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id,
                    s.date_key,
                    s.title,
                    s.spread_json,
                    s.omen_markdown,
                    s.created_at,
                    s.updated_at,
                    COUNT(m.id) AS message_count
                FROM oracle_sessions s
                LEFT JOIN oracle_messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC, s.rowid DESC
                LIMIT ?
                """,
                (capped_limit,),
            ).fetchall()
            return [self._row_to_summary(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        if not session_id:
            return None
        with self._lock, self._connect() as conn:
            return self._fetch_session_unlocked(conn, str(session_id))

    def get_latest_for_date(self, date_key: str) -> dict[str, Any] | None:
        clean_date = (date_key or "").strip()
        if not clean_date:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM oracle_sessions
                WHERE date_key = ?
                ORDER BY updated_at DESC, rowid DESC
                LIMIT 1
                """,
                (clean_date,),
            ).fetchone()
            if row is None:
                return None
            return self._fetch_session_unlocked(conn, row["id"])

    def create_session(self, date_key: str, title: str | None = None) -> dict[str, Any]:
        clean_date = (date_key or "").strip() or datetime.now().strftime("%Y-%m-%d")
        clean_title = (title or "").strip()
        session_id = f"ora_{clean_date.replace('-', '')}_{uuid.uuid4().hex[:8]}"
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO oracle_sessions (
                    id, date_key, title, spread_json, entrails_summary_json,
                    smoke_packet, omen_markdown, created_at, updated_at
                )
                VALUES (?, ?, ?, NULL, NULL, '', '', ?, ?)
                """,
                (session_id, clean_date, clean_title, now, now),
            )
            created = self._fetch_session_unlocked(conn, session_id)
            if created is None:
                raise RuntimeError(f"Failed to load newly created oracle session {session_id}")
            return created

    def get_or_create_daily_session(self, date_key: str) -> dict[str, Any]:
        clean_date = (date_key or "").strip() or datetime.now().strftime("%Y-%m-%d")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM oracle_sessions
                WHERE date_key = ?
                ORDER BY updated_at DESC, rowid DESC
                LIMIT 1
                """,
                (clean_date,),
            ).fetchone()
            if row is not None:
                existing = self._fetch_session_unlocked(conn, row["id"])
                if existing is not None:
                    return existing
        return self.create_session(clean_date)

    def save_omen(
        self,
        session_id: str,
        *,
        spread: dict[str, Any],
        entrails_summary: dict[str, Any],
        smoke_packet: str,
        omen_markdown: str,
        title: str | None = None,
    ) -> dict[str, Any]:
        if not session_id:
            raise ValueError("session_id is required")
        now = _now_iso()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT title FROM oracle_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(f"Oracle session {session_id!r} not found")

            resolved_title = (
                title.strip()
                if title is not None and title.strip()
                else (existing["title"] or "")
            )

            conn.execute(
                """
                UPDATE oracle_sessions
                SET title = ?,
                    spread_json = ?,
                    entrails_summary_json = ?,
                    smoke_packet = ?,
                    omen_markdown = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    resolved_title,
                    _json_dumps(spread),
                    _json_dumps(entrails_summary),
                    smoke_packet or "",
                    omen_markdown or "",
                    now,
                    session_id,
                ),
            )
            updated = self._fetch_session_unlocked(conn, session_id)
            if updated is None:
                raise RuntimeError(f"Oracle session {session_id!r} vanished after save_omen")
            return updated

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        cast_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not session_id:
            raise ValueError("session_id is required")
        clean_role = (role or "").strip()
        if not clean_role:
            raise ValueError("role is required")
        now = _now_iso()
        with self._lock, self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM oracle_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if exists is None:
                raise KeyError(f"Oracle session {session_id!r} not found")

            cur = conn.execute(
                """
                INSERT INTO oracle_messages (session_id, role, content, cast_data_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, clean_role, content or "", _json_dumps(cast_data), now),
            )
            conn.execute(
                "UPDATE oracle_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            msg_id = cur.lastrowid
            return {
                "id": msg_id,
                "role": clean_role,
                "content": content or "",
                "cast_data": cast_data,
                "created_at": now,
            }

    def delete_session(self, session_id: str) -> bool:
        if not session_id:
            return False
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM oracle_sessions WHERE id = ?",
                (str(session_id),),
            )
            return cur.rowcount > 0
