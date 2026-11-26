"""FastAPI server for the Technowitch Grimoire & Delphic Oracle.

Exposes REST endpoints for the Markdown Scriptorium (`YYYY-MM-DD.md`), live brass
ribbon telemetry, LM Studio vessel lifecycle, and multi-stage SSE ritual streams.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from grimoire.entrails import gather_full_entrails, gather_header_telemetry
from grimoire.haruspex import distill_smoke_packet
from grimoire.journal_store import JournalStore
from grimoire.oracle_store import OracleStore
from grimoire.pythia import (
    banish_vessel,
    ensure_vessel_awake,
    get_vessel_status,
    stream_chat,
    stream_omen,
)
from grimoire.sortilege import cast_spread

logger = logging.getLogger("grimoire.app")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"

app = FastAPI(
    title="Grimoire // Technowitch",
    version="0.1.0",
    description="Symbolist Scriptorium & Three-Tier Delphic Oracle",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

journal_store = JournalStore()
oracle_store = OracleStore()

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class JournalSaveRequest(BaseModel):
    content: str = ""


class JournalInscribeRequest(BaseModel):
    text: str
    source: str | None = "The Pythia"
    spread_summary: str | None = None
    timestamp: str | None = None


class VesselWakeRequest(BaseModel):
    ttl: int = Field(default=1800, ge=60, le=86400)
    context_length: int = Field(default=8192, ge=1024, le=65536)


class CreateSessionRequest(BaseModel):
    date_key: str | None = None
    title: str | None = None


class OmenRequest(BaseModel):
    date_key: str | None = None
    session_id: str | None = None
    spread_mode: Literal["daily", "trinity"] = "daily"
    question: str | None = None
    force_new: bool = False


class ChatRequest(BaseModel):
    message: str
    cast_extra: Literal["card", "rune", "iching"] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _session_id_of(session: dict[str, Any]) -> str:
    sid = session.get("id") or session.get("session_id")
    if not sid:
        raise RuntimeError("Session object missing id")
    return str(sid)


def _extract_quiet_count(entrails: Any, smoke_packet: str = "") -> int:
    if isinstance(entrails, dict):
        if isinstance(entrails.get("quiet_count"), int):
            return entrails["quiet_count"]
        for key in ("quiet_whispers", "quiet_items", "whispers"):
            val = entrails.get(key)
            if isinstance(val, list):
                return len(val)
        digests = entrails.get("digests")
        if isinstance(digests, dict) and isinstance(digests.get("quiet_count"), int):
            return digests["quiet_count"]
        if isinstance(digests, list):
            return sum(str(item).lower().count("[quiet]") for item in digests)
    if smoke_packet:
        return smoke_packet.lower().count("[quiet]")
    return 0


def _build_entrails_summary(
    entrails: Any,
    *,
    quiet_count: int,
    question: str | None = None,
    haruspex_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"quiet_count": quiet_count}
    if question and question.strip():
        summary["question"] = question.strip()
    if haruspex_meta:
        summary["haruspex"] = haruspex_meta
    if isinstance(entrails, dict):
        tel = entrails.get("telemetry") if isinstance(entrails.get("telemetry"), dict) else entrails
        for k in ("tub", "plant", "lights", "celestial"):
            if k in tel:
                summary[k] = tel[k]
        for tk in ("gathered_at", "captured_at"):
            if tk in entrails:
                summary["captured_at"] = entrails[tk]
                break
        if isinstance(entrails.get("somatic_weather"), dict):
            summary["somatic_weather"] = entrails["somatic_weather"].get("summary")
    return summary


def _derive_spread_title(spread: dict[str, Any], question: str | None = None) -> str:
    if question and question.strip():
        q = question.strip()
        return q if len(q) <= 68 else q[:65].rstrip() + "…"
    parts: list[str] = []
    cards = spread.get("cards") or []
    if cards:
        if len(cards) == 1:
            parts.append(str(cards[0].get("name", "Thoth")))
        else:
            parts.append(" / ".join(str(c.get("name", "")) for c in cards[:3] if c.get("name")))
    iching = spread.get("iching")
    if isinstance(iching, dict) and isinstance(iching.get("primary"), dict):
        prim = iching["primary"]
        num = prim.get("number")
        name = prim.get("name")
        if num and name:
            parts.append(f"Hex {num} {name}")
    runes = spread.get("runes") or []
    if runes and isinstance(runes[0], dict) and runes[0].get("name"):
        parts.append(str(runes[0]["name"]))
    return " · ".join(p for p in parts if p) or "Oracle Consultation"


# ---------------------------------------------------------------------------
# Static Entry Point
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(
        path=str(index_path),
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Telemetry & Vessel Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/telemetry")
async def api_telemetry() -> dict[str, Any]:
    telemetry_res, vessel_res = await asyncio.gather(
        gather_header_telemetry(),
        get_vessel_status(),
        return_exceptions=True,
    )
    payload: dict[str, Any] = {}
    if isinstance(telemetry_res, Exception):
        logger.warning("Header telemetry partial failure: %s", telemetry_res)
        payload = {
            "tub": None,
            "plant": None,
            "lights": {"summary": "Telemetry unreachable", "ambient_hex": "#A88948", "rooms": {}},
            "celestial": None,
            "telemetry_error": str(telemetry_res),
        }
    elif isinstance(telemetry_res, dict):
        payload.update(telemetry_res)

    if isinstance(vessel_res, Exception):
        logger.warning("Vessel status check failed: %s", vessel_res)
        payload["vessel"] = {
            "state": "server_off",
            "model_id": "",
            "loaded_models": [],
            "detail": str(vessel_res),
        }
    else:
        payload["vessel"] = vessel_res

    payload["fetched_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return payload


@app.get("/api/vessel/status")
async def api_vessel_status() -> dict[str, Any]:
    return await get_vessel_status()


@app.post("/api/vessel/wake")
async def api_vessel_wake(req: VesselWakeRequest | None = None) -> dict[str, Any]:
    params = req or VesselWakeRequest()
    return await ensure_vessel_awake(ttl=params.ttl, context_length=params.context_length)


@app.post("/api/vessel/banish")
async def api_vessel_banish() -> dict[str, Any]:
    return await banish_vessel()


# ---------------------------------------------------------------------------
# Scriptorium Journal Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/journal")
async def api_journal_list(q: str | None = Query(default=None)) -> dict[str, Any]:
    entries = journal_store.list_entries(query=q)
    return {"entries": entries, "count": len(entries), "query": q or ""}


@app.get("/api/journal/{date}")
async def api_journal_get(date: str) -> dict[str, Any]:
    try:
        return journal_store.get_entry(date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/journal/{date}")
async def api_journal_save(date: str, req: JournalSaveRequest) -> dict[str, Any]:
    try:
        return journal_store.save_entry(date, req.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/journal/{date}/inscribe")
async def api_journal_inscribe(date: str, req: JournalInscribeRequest) -> dict[str, Any]:
    try:
        return journal_store.inscribe(
            date,
            req.text,
            source=req.source,
            spread_summary=req.spread_summary,
            timestamp=req.timestamp,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Oracle Session CRUD Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/oracle/sessions")
async def api_oracle_list_sessions(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    sessions = await _maybe_await(oracle_store.list_sessions(limit=limit))
    return {"sessions": sessions}


@app.get("/api/oracle/sessions/{session_id}")
async def api_oracle_get_session(session_id: str) -> dict[str, Any]:
    session = await _maybe_await(oracle_store.get_session(session_id))
    if not session:
        raise HTTPException(status_code=404, detail=f"Oracle session {session_id!r} not found.")
    return session


@app.get("/api/oracle/by-date/{date}")
async def api_oracle_by_date(date: str) -> dict[str, Any]:
    session = await _maybe_await(oracle_store.get_latest_for_date(date))
    return {"date": date, "session": session}


@app.post("/api/oracle/sessions")
async def api_oracle_create_session(req: CreateSessionRequest | None = None) -> dict[str, Any]:
    body = req or CreateSessionRequest()
    date_key = body.date_key or _today_key()
    session = await _maybe_await(oracle_store.create_session(date_key, title=body.title))
    return session


@app.delete("/api/oracle/sessions/{session_id}")
async def api_oracle_delete_session(session_id: str) -> dict[str, Any]:
    deleted = await _maybe_await(oracle_store.delete_session(session_id))
    return {"deleted": bool(deleted if deleted is not None else True), "session_id": session_id}


# ---------------------------------------------------------------------------
# Multi-Stage SSE Ritual Streams
# ---------------------------------------------------------------------------


@app.post("/api/oracle/omen")
async def api_oracle_omen(req: OmenRequest) -> StreamingResponse:
    date_key = req.date_key or _today_key()
    question = req.question.strip() if req.question and req.question.strip() else None

    if req.force_new and not req.session_id:
        session = await _maybe_await(
            oracle_store.create_session(date_key, title=question[:68] if question else None)
        )
    elif req.session_id:
        session = await _maybe_await(oracle_store.get_session(req.session_id))
        if not session:
            session = await _maybe_await(
                oracle_store.create_session(date_key, title=question[:68] if question else None)
            )
    else:
        session = await _maybe_await(oracle_store.get_or_create_daily_session(date_key))
        # If existing daily session already holds a completed omen and force_new was requested, mint a new thread
        if req.force_new and session.get("omen_markdown"):
            session = await _maybe_await(
                oracle_store.create_session(date_key, title=question[:68] if question else None)
            )

    session_id = _session_id_of(session)

    async def event_generator() -> AsyncIterator[str]:
        try:
            # Stage 1: Hardware Entropy Sortilege (flips cards/hexagram/rune immediately)
            yield _sse(
                {
                    "event": "stage",
                    "stage": "sortilege",
                    "label": "Casting hardware entropy (Thoth, Yarrow & Elder Futhark)…",
                }
            )
            await asyncio.sleep(0)

            spread = await _maybe_await(cast_spread(req.spread_mode))
            yield _sse(
                {
                    "event": "spread",
                    "spread": spread,
                    "session_id": session_id,
                }
            )
            await asyncio.sleep(0)

            # Stage 2: Mycelial, Ambient & Vault Entrails
            yield _sse(
                {
                    "event": "stage",
                    "stage": "entrails",
                    "label": "Gathering mycelial breath, house lights & whispered digests…",
                }
            )
            await asyncio.sleep(0)

            entrails = await gather_full_entrails()

            # Stage 3: Concurrent Haruspex Smoke Distillation + Pythia Vessel Awakening
            vessel_status = await get_vessel_status()
            vessel_awake = isinstance(vessel_status, dict) and vessel_status.get("state") == "awake"

            if vessel_awake:
                yield _sse(
                    {
                        "event": "stage",
                        "stage": "haruspex",
                        "label": "High Haruspex (Neon) distilling ritual smoke…",
                    }
                )
                await asyncio.sleep(0)
                haruspex_res = await distill_smoke_packet(spread, entrails, question)
            else:
                yield _sse(
                    {
                        "event": "stage",
                        "stage": "awakening",
                        "label": "High Haruspex distilling smoke & waking Fallen Gemma in the chasm…",
                    }
                )
                await asyncio.sleep(0)
                haruspex_out, wake_out = await asyncio.gather(
                    distill_smoke_packet(spread, entrails, question),
                    ensure_vessel_awake(),
                    return_exceptions=True,
                )
                if isinstance(haruspex_out, Exception):
                    raise haruspex_out
                haruspex_res = haruspex_out
                if isinstance(wake_out, Exception):
                    logger.warning("Vessel wake warning during parallel stage: %s", wake_out)

            smoke_packet = (
                haruspex_res.get("smoke_packet", "")
                if isinstance(haruspex_res, dict)
                else str(haruspex_res or "")
            )
            haruspex_meta = (
                {
                    "model": haruspex_res.get("model"),
                    "duration_ms": haruspex_res.get("duration_ms"),
                    "used_fallback": haruspex_res.get("used_fallback"),
                }
                if isinstance(haruspex_res, dict)
                else {}
            )
            quiet_count = _extract_quiet_count(entrails, smoke_packet)

            yield _sse(
                {
                    "event": "smoke",
                    "smoke_packet": smoke_packet,
                    "quiet_count": quiet_count,
                    "haruspex": haruspex_meta,
                }
            )
            await asyncio.sleep(0)

            # Stage 4: The Pythia Speaks
            yield _sse(
                {
                    "event": "stage",
                    "stage": "pythia",
                    "label": "The Pythia speaks from the chasm…",
                }
            )
            await asyncio.sleep(0)

            omen_chunks: list[str] = []
            async for chunk in stream_omen(smoke_packet, spread, question):
                if chunk:
                    omen_chunks.append(chunk)
                    yield _sse({"event": "delta", "text": chunk})

            omen_markdown = "".join(omen_chunks).strip()
            entrails_summary = _build_entrails_summary(
                entrails,
                quiet_count=quiet_count,
                question=question,
                haruspex_meta=haruspex_meta,
            )
            derived_title = session.get("title") or _derive_spread_title(spread, question)

            updated_session = await _maybe_await(
                oracle_store.save_omen(
                    session_id,
                    spread=spread,
                    entrails_summary=entrails_summary,
                    smoke_packet=smoke_packet,
                    omen_markdown=omen_markdown,
                    title=derived_title,
                )
            )
            if not isinstance(updated_session, dict):
                updated_session = await _maybe_await(oracle_store.get_session(session_id))

            yield _sse({"event": "done", "session": updated_session})
        except Exception as exc:
            logger.exception("Error during /api/oracle/omen ritual stream")
            yield _sse({"event": "error", "message": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.post("/api/oracle/sessions/{session_id}/chat")
async def api_oracle_chat(session_id: str, req: ChatRequest) -> StreamingResponse:
    user_text = (req.message or "").strip()
    if not user_text and not req.cast_extra:
        raise HTTPException(status_code=400, detail="Message or talisman draw required.")
    if not user_text and req.cast_extra:
        user_text = f"Interpret this {req.cast_extra} drawn into our thread."

    initial_session = await _maybe_await(oracle_store.get_session(session_id))
    if not initial_session:
        raise HTTPException(status_code=404, detail=f"Oracle session {session_id!r} not found.")

    async def event_generator() -> AsyncIterator[str]:
        try:
            extra_cast: dict[str, Any] | None = None
            if req.cast_extra:
                yield _sse(
                    {
                        "event": "stage",
                        "stage": "sortilege",
                        "label": f"Drawing {req.cast_extra} from hardware entropy…",
                    }
                )
                await asyncio.sleep(0)
                extra_cast = await _maybe_await(cast_spread(req.cast_extra))
                yield _sse({"event": "extra_cast", "cast": extra_cast})
                await asyncio.sleep(0)

            # Snapshot session history prior to appending user turn to avoid duplicate
            # user turn if stream_chat appends user_message onto session['messages'].
            session_prior = await _maybe_await(oracle_store.get_session(session_id)) or initial_session

            await _maybe_await(
                oracle_store.append_message(
                    session_id,
                    "user",
                    user_text,
                    cast_data=extra_cast,
                )
            )

            vessel_status = await get_vessel_status()
            if not (isinstance(vessel_status, dict) and vessel_status.get("state") == "awake"):
                yield _sse(
                    {
                        "event": "stage",
                        "stage": "waking",
                        "label": "Waking Fallen Gemma in the chasm…",
                    }
                )
                await asyncio.sleep(0)
                await ensure_vessel_awake()

            yield _sse(
                {
                    "event": "stage",
                    "stage": "pythia",
                    "label": "The Pythia answers…",
                }
            )
            await asyncio.sleep(0)

            reply_chunks: list[str] = []
            async for chunk in stream_chat(session_prior, user_text, extra_cast=extra_cast):
                if chunk:
                    reply_chunks.append(chunk)
                    yield _sse({"event": "delta", "text": chunk})

            reply_markdown = "".join(reply_chunks).strip()
            if reply_markdown:
                await _maybe_await(
                    oracle_store.append_message(
                        session_id,
                        "assistant",
                        reply_markdown,
                    )
                )

            updated_session = await _maybe_await(oracle_store.get_session(session_id))
            yield _sse({"event": "done", "session": updated_session})
        except Exception as exc:
            logger.exception("Error during /api/oracle/sessions/%s/chat stream", session_id)
            yield _sse({"event": "error", "message": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=SSE_HEADERS)
