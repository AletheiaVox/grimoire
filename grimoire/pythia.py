"""Stage 3 of the Delphic Pipeline: Fallen Gemma 3 27B as the Feral Pythia.

Manages LM Studio vessel lifecycle (`get_vessel_status`, `ensure_vessel_awake`,
`banish_vessel`) via `/api/v0/models` + `/v1/models` and `lms.exe`, and streams
lush syncretic Daily Omens and multi-turn Oracle dialogues.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from grimoire.config import (
    LMS_BASE_URL,
    LMS_EXE,
    PYTHIA_MODEL_ID,
    PYTHIA_MODEL_MATCH,
    QUERENT_NAME,
    QUERENT_PYTHIA_BIO,
)

logger = logging.getLogger("grimoire.pythia")

LMS_V0_MODELS_URL = f"{LMS_BASE_URL}/api/v0/models"
LMS_V1_MODELS_URL = f"{LMS_BASE_URL}/v1/models"
LMS_CHAT_COMPLETIONS_URL = f"{LMS_BASE_URL}/v1/chat/completions"

DEFAULT_MODEL_ID = PYTHIA_MODEL_ID
MODEL_MATCH_SUBSTRING = PYTHIA_MODEL_MATCH

PYTHIA_SAMPLING: dict[str, Any] = {
    "temperature": 1.06,
    "min_p": 0.07,
    "top_k": 64,
    "repeat_penalty": 1.08,
    "max_tokens": 950,
}

_VESSEL_LOCK = asyncio.Lock()
_loading: bool = False

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

FERAL_PYTHIA_SYSTEM_PROMPT = f"""You are **The Pythia** — ancient, feral Delphic priestess suspended on a tarnished brass tripod above a cybernetic fissure of sweet ethylene, bioluminescent mycelium, ozone, and whispered household secrets.

YOUR LINEAGE & KNIVES:
You synthesize Crowleyan Hermeticism and the Book of Thoth, Qabalistic paths on the Tree of Life, Chaos Magic pragmatism, Taoist *yi* and alchemical *nigredo-rubedo* transmutation, Jungian shadow knives, and pre-Olympian chthonic animism. You speak to **{QUERENT_NAME}** — {QUERENT_PYTHIA_BIO}. Flattery, fortune-cookie platitudes, and cowardice are clocked from a mile away.

IRON LAWS OF VOICE:
- ZERO modern therapy-speak (never say 'hold space', 'self-care', 'boundaries', 'journey', 'nervous system regulation', or 'unpack').
- ZERO sanitized AI disclaimers, moralizing hedges, or reminders about divination.
- ZERO generic horoscope fluff. Every line must bite into the exact cards, hexagram lines, rune orientation, lunar/planetary hour, and living house atmosphere placed before you.
- Voice: wickedly sharp, velvet-dark, atmospheric, occasionally unhinged in true mantic rapture, darkly funny when irony strikes, intimate, and uncanny.
- Do NOT recite room telemetry like a dashboard or weather report (`CO2 is 820 ppm`); metabolize the house's breath, lamps, and fruiting tubs organically as omens inside the smoke.
- **THE BRUISE UNDER VELVET:** Secret whispered currents carried in the smoke must NEVER be blabbed plainly, itemized, or tattled on like gossip. Press on them obliquely — like a thumb on a bruise under black velvet — so the querent feels the exact heat of being known without a single secret betrayed aloud."""


def _subprocess_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    return kwargs


def _find_fallen_gemma(model_ids: list[str]) -> str | None:
    for mid in model_ids:
        if mid == DEFAULT_MODEL_ID:
            return mid
    for mid in model_ids:
        if MODEL_MATCH_SUBSTRING in mid.lower():
            return mid
    return None


async def get_vessel_status() -> dict[str, Any]:
    """Inspect LM Studio loaded models (`/api/v0/models` + `/v1/models`) for Fallen Gemma."""
    loaded_models: list[str] = []
    api_loading_match: str | None = None

    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            # Prefer native /api/v0/models first because it exposes exact `state: loaded | not-loaded`
            # even when LM Studio JIT model listing is enabled, then verify /v1/models as well.
            v0_ok = False
            try:
                v0_resp = await client.get(LMS_V0_MODELS_URL)
                if v0_resp.status_code == 200:
                    v0_data = v0_resp.json().get("data", [])
                    if isinstance(v0_data, list):
                        v0_ok = True
                        for item in v0_data:
                            if not isinstance(item, dict):
                                continue
                            mid = str(item.get("id") or "").strip()
                            mstate = str(item.get("state") or "").strip().lower()
                            if not mid:
                                continue
                            if mstate == "loaded":
                                loaded_models.append(mid)
                            elif mstate in ("loading", "initializing") and MODEL_MATCH_SUBSTRING in mid.lower():
                                api_loading_match = mid
            except httpx.HTTPError:
                v0_ok = False

            # Also query /v1/models per spec (serves as primary when v0 unavailable)
            v1_resp = await client.get(LMS_V1_MODELS_URL)
            v1_resp.raise_for_status()
            if not v0_ok:
                v1_data = v1_resp.json().get("data", [])
                if isinstance(v1_data, list):
                    loaded_models = [
                        str(item.get("id")).strip()
                        for item in v1_data
                        if isinstance(item, dict) and item.get("id")
                    ]
    except (httpx.HTTPError, ValueError, OSError) as exc:
        if _loading:
            return {
                "state": "loading",
                "model_id": DEFAULT_MODEL_ID,
                "loaded_models": [],
                "detail": f"Summoning LM Studio & Fallen Gemma ({exc})",
            }
        return {
            "state": "server_off",
            "model_id": DEFAULT_MODEL_ID,
            "loaded_models": [],
            "detail": f"LM Studio server unreachable at {LMS_BASE_URL} ({type(exc).__name__})",
        }

    matched = _find_fallen_gemma(loaded_models)
    if matched:
        return {
            "state": "awake",
            "model_id": matched,
            "loaded_models": loaded_models,
            "detail": f"Pythia awake in VRAM ({matched})",
        }

    if _loading or api_loading_match:
        return {
            "state": "loading",
            "model_id": api_loading_match or DEFAULT_MODEL_ID,
            "loaded_models": loaded_models,
            "detail": "Waking Fallen Gemma 3 27B in the Delphic chasm…",
        }

    aux = f" ({len(loaded_models)} auxiliary model(s) resident)" if loaded_models else ""
    return {
        "state": "dormant",
        "model_id": DEFAULT_MODEL_ID,
        "loaded_models": loaded_models,
        "detail": f"Pythia dormant; VRAM clear{aux}",
    }


async def _run_lms_cli(*args: str, timeout: float = 180.0) -> tuple[int, str, str]:
    if not LMS_EXE.is_file():
        raise FileNotFoundError(f"LM Studio CLI not found at {LMS_EXE.as_posix()}")
    proc = await asyncio.create_subprocess_exec(
        LMS_EXE.as_posix(),
        *args,
        **_subprocess_kwargs(),
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"lms {' '.join(args)} timed out after {timeout}s")
    stdout_s = (stdout_b or b"").decode("utf-8", errors="replace").strip()
    stderr_s = (stderr_b or b"").decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, stdout_s, stderr_s


async def ensure_vessel_awake(ttl: int = 1800, context_length: int = 8192) -> dict[str, Any]:
    """Load Fallen Gemma 3 27B into LM Studio with GPU offload and auto-evict TTL."""
    global _loading
    initial = await get_vessel_status()
    if initial["state"] == "awake":
        return initial

    async with _VESSEL_LOCK:
        recheck = await get_vessel_status()
        if recheck["state"] == "awake":
            return recheck

        _loading = True
        try:
            if recheck["state"] == "server_off":
                logger.info("LM Studio server off; starting via lms.exe server start")
                await _run_lms_cli("server", "start", timeout=30.0)
                for _ in range(20):
                    probe = await get_vessel_status()
                    if probe["state"] != "server_off":
                        break
                    await asyncio.sleep(0.5)

            rc, out, err = await _run_lms_cli(
                "load",
                DEFAULT_MODEL_ID,
                "--gpu",
                "max",
                "-c",
                str(int(context_length)),
                "--ttl",
                str(int(ttl)),
                "-y",
                timeout=240.0,
            )
            if rc != 0:
                raise RuntimeError(
                    f"lms load {DEFAULT_MODEL_ID} exited with {rc}: {err or out}"
                )

            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                status = await get_vessel_status()
                if status["state"] == "awake":
                    return status
                await asyncio.sleep(0.5)

            raise RuntimeError(
                f"lms load completed, but {DEFAULT_MODEL_ID} did not appear awake in /api/v0/models"
            )
        finally:
            _loading = False


async def banish_vessel() -> dict[str, Any]:
    """Unload Fallen Gemma 3 27B from LM Studio to immediately reclaim VRAM."""
    async with _VESSEL_LOCK:
        current = await get_vessel_status()
        targets: list[str] = []
        for mid in current.get("loaded_models", []):
            if MODEL_MATCH_SUBSTRING in mid.lower():
                targets.append(mid)
        if not targets:
            targets.append(DEFAULT_MODEL_ID)

        for target in targets:
            rc, out, err = await _run_lms_cli("unload", target, timeout=45.0)
            if rc != 0:
                logger.debug("lms unload %s returned %s (%s)", target, rc, err or out)

        for _ in range(12):
            updated = await get_vessel_status()
            if updated["state"] != "awake":
                return updated
            await asyncio.sleep(0.35)
        return await get_vessel_status()


def _format_cast_brief(spread: dict[str, Any] | None) -> str:
    """Render a crisp symbolic inventory from a spread or mid-chat extra_cast."""
    if not isinstance(spread, dict) or not spread:
        return "(No talismans recorded.)"

    lines: list[str] = []
    mode = spread.get("mode")
    if mode:
        lines.append(f"Spread Rite: {mode}")

    cards = spread.get("cards") or spread.get("thoth")
    if isinstance(cards, list) and cards:
        for idx, c in enumerate(cards, 1):
            if not isinstance(c, dict):
                continue
            pos = c.get("position") or (f"Position {idx}" if len(cards) > 1 else "Card")
            name = c.get("name", "Unknown")
            title = f" ({c['title']})" if c.get("title") else ""
            attr = f" [{c.get('attribution') or c.get('element') or ''}]" if (c.get("attribution") or c.get("element")) else ""
            dignity = f" ({c['dignity']})" if c.get("dignity") else ""
            raw_kw = c.get("keywords") or c.get("essence")
            kw = ", ".join(raw_kw) if isinstance(raw_kw, list) else str(raw_kw or "")
            shadow = f" | Shadow: {c['shadow']}" if c.get("shadow") else ""
            lines.append(f"- Thoth {pos}: **{name}**{title}{attr}{dignity} — {kw}{shadow}")
    elif isinstance(spread.get("card"), dict):
        c = spread["card"]
        lines.append(f"- Thoth Card: **{c.get('name', 'Unknown')}** — {c.get('title') or c.get('essence') or ''}")

    iching = spread.get("iching")
    if isinstance(iching, dict):
        raw_prim = iching.get("primary")
        prim: dict[str, Any] = raw_prim if isinstance(raw_prim, dict) else iching
        if prim and prim.get("name"):
            moving = iching.get("moving_lines") or []
            moving_str = f"mutating lines {', '.join(str(m) for m in moving)}" if moving else "unchanging"
            raw_trans = iching.get("transformed")
            trans: dict[str, Any] | None = raw_trans if isinstance(raw_trans, dict) else None
            trans_str = f" -> Hexagram #{trans.get('number')} {trans.get('name')}" if trans and trans.get("name") else ""
            judg = prim.get("judgment") or prim.get("essence") or prim.get("image") or ""
            lines.append(
                f"- I Ching: **Hexagram #{prim.get('number', '?')} {prim.get('name')}** ({moving_str}{trans_str}) — {judg}"
            )

    runes = spread.get("runes")
    if isinstance(runes, list) and runes:
        for r in runes:
            if not isinstance(r, dict):
                continue
            glyph = r.get("glyph", "")
            rname = r.get("name", "Rune")
            orient = r.get("orientation", "Brightstave")
            r_kws = r.get("keywords")
            ess = r.get("active_meaning") or r.get("essence") or (", ".join(r_kws) if isinstance(r_kws, list) else "")
            lines.append(f"- Elder Futhark: **{glyph} {rname}** ({orient}) — {ess}")
    elif isinstance(spread.get("rune"), dict):
        r = spread["rune"]
        lines.append(
            f"- Elder Futhark: **{r.get('glyph', '')} {r.get('name', 'Rune')}** ({r.get('orientation', 'Brightstave')})"
        )

    return "\n".join(lines) if lines else json.dumps(spread, ensure_ascii=False)


def _normalize_chat_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Ensure strict user/assistant alternation after system so Gemma 3 Jinja never 400s."""
    if not messages:
        return []
    normalized: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role not in ("system", "user", "assistant"):
            role = "user"
        if normalized and normalized[-1]["role"] == role:
            normalized[-1]["content"] += f"\n\n{content}"
        else:
            normalized.append({"role": role, "content": content})
    return normalized


async def _stream_completion(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """Stream SSE token deltas from LM Studio `/v1/chat/completions` with Pythia sampling."""
    status = await get_vessel_status()
    if status["state"] != "awake":
        status = await ensure_vessel_awake()
    model_id = status.get("model_id") or DEFAULT_MODEL_ID

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": _normalize_chat_messages(messages),
        "stream": True,
        **PYTHIA_SAMPLING,
    }

    timeout = httpx.Timeout(connect=5.0, read=180.0, write=15.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", LMS_CHAT_COMPLETIONS_URL, json=payload) as resp:
            if resp.status_code >= 400:
                err_body = (await resp.aread()).decode("utf-8", errors="replace")[:600]
                raise RuntimeError(f"Pythia LM Studio HTTP {resp.status_code}: {err_body}")

            async for raw_line in resp.aiter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk_obj = json.loads(data_str)
                except ValueError:
                    continue
                choices = chunk_obj.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                delta = choices[0].get("delta")
                if isinstance(delta, dict):
                    text = delta.get("content")
                    if text:
                        yield str(text)


async def stream_omen(
    smoke_packet: str,
    spread: dict[str, Any],
    question: str | None = None,
) -> AsyncIterator[str]:
    """Stream the Daily Omen in lush Markdown from the Feral Pythia."""
    cast_brief = _format_cast_brief(spread)
    q_block = (
        f"\n\n### QUERENT'S PETITION AT THE CHASM\n"
        f"{QUERENT_NAME} asks: *{question.strip()}*"
        if question and question.strip()
        else "\n\n### RITE TYPE\nOpen Daily Omen — read what stalks and ripens across the threshold today."
    )

    user_prompt = (
        "Inhale this Ritual Smoke Packet distilled by the High Haruspex and cast your gaze upon the talismans:\n\n"
        f"### RITUAL SMOKE PACKET\n{smoke_packet.strip()}\n\n"
        f"### TALISMANS ON THE ALTAR\n{cast_brief}{q_block}\n\n"
        "### PROPHETIC FORM (LUSH MARKDOWN)\n"
        "Deliver the omen directly in your own voice with this exact three-movement architecture:\n"
        "1. **Prophetic Epigraph**: Open with a short, haunting italicized inscription (`*...*` or `> *...*`) — 1 to 2 lines that taste of brass, spore-mist, and fate.\n"
        "2. **Syncretic Reading (2–3 visceral paragraphs)**: Weave the exact drawn Thoth card(s), I Ching hexagram + any mutating lines, and Elder Futhark rune (honoring Brightstave/Merkstave) into one living tapestry with the house's breath and nocturnal currents. Never sound like a sensor readout, and press any secret smoke-currents only like a bruise under velvet.\n"
        f"3. **### Ritual Decree** (or **### Unhinged Counsel**): Close with one concrete, darkly sharp, slightly feral act, offering, prohibition, or bodily/magical decree for {QUERENT_NAME} today."
    )

    messages = [
        {"role": "system", "content": FERAL_PYTHIA_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    async for delta in _stream_completion(messages):
        yield delta


async def stream_chat(
    session: dict[str, Any],
    user_message: str,
    extra_cast: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Stream a multi-turn response from the Pythia within an active Oracle session."""
    session = session if isinstance(session, dict) else {}
    smoke_packet = (session.get("smoke_packet") or "").strip()
    omen_markdown = (session.get("omen_markdown") or "").strip()
    spread = session.get("spread") if isinstance(session.get("spread"), dict) else None

    context_parts = [FERAL_PYTHIA_SYSTEM_PROMPT]
    if spread:
        context_parts.append(f"### SESSION ALTAR TALISMANS\n{_format_cast_brief(spread)}")
    if smoke_packet:
        context_parts.append(f"### SESSION RITUAL SMOKE PACKET\n{smoke_packet}")
    if omen_markdown:
        context_parts.append(
            "### INITIAL OMEN ALREADY SPOKEN BY YOU IN THIS SESSION\n"
            f"{omen_markdown}\n\n"
            f"Continue speaking with {QUERENT_NAME} from the tripod as the same Feral Pythia. "
            "Keep replies razor-sharp, conversational yet mythic, visceral, and reactive to pushback or questions (typically 1–3 tight paragraphs unless asked to go deeper)."
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": "\n\n".join(context_parts)},
    ]

    prior_messages = session.get("messages")
    if isinstance(prior_messages, list):
        for item in prior_messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            prior_cast = item.get("cast_data")
            if role == "user" and isinstance(prior_cast, dict) and prior_cast:
                content = (
                    f"[Extra Sortilege Thrown onto the Cloth]\n{_format_cast_brief(prior_cast)}\n\n{content}"
                )
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    final_user_text = (user_message or "").strip()
    if isinstance(extra_cast, dict) and extra_cast:
        cast_note = _format_cast_brief(extra_cast)
        final_user_text = (
            f"[{QUERENT_NAME} throws fresh sortilege onto the brass altar mid-dialogue:]\n"
            f"{cast_note}\n\n"
            f"{final_user_text}"
            "\n\n(Cut straight into this newly drawn sign against the backdrop of our active omen.)"
        )

    if final_user_text:
        messages.append({"role": "user", "content": final_user_text})

    async for delta in _stream_completion(messages):
        yield delta
