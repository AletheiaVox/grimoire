"""Stage 2 of the Delphic Pipeline: Gemini 4 Neon as the High Haruspex.

Runs oneshot completions against `gemini-4-neon` via configured DirectSDK
auth (with strict isolated-workspace teardown so zero orphan CLI processes
leak) to distill raw divinatory casts, mycelial air, apartment light,
celestial hours, journal residue, and veiled `[quiet]` session whispers into a
dense 160-240 word Ritual Smoke Packet for the Feral Pythia.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import re
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

from grimoire.config import (
    DIRECTSDK_DIRS,
    HARUSPEX_MODEL,
    QUERENT_HARUSPEX_BIO,
    QUERENT_NAME,
    SKY_LABEL,
)

logger = logging.getLogger("grimoire.haruspex")

HARUSPEX_EFFORT = "low"
HARUSPEX_TIMEOUT_SECONDS = 45.0

_PLUGIN_CANDIDATES: tuple[Path, ...] = (
    *DIRECTSDK_DIRS,
    Path.home() / ".hermes" / "plugins" / "antigravity-subscription-directsdk",
)

_SDK_LOAD_LOCK = threading.Lock()
_SDK_CLIENT_CLS: type[Any] | None = None
_SDK_IS_AUTH_FN: Any | None = None

_SKY_LINE = (
    f"{SKY_LABEL} lunar phase and Chaldean planetary hour."
    if SKY_LABEL.lower() != "local"
    else "Local lunar phase and Chaldean planetary hour."
)

HARUSPEX_SYSTEM_PROMPT = f"""You are the **High Haruspex** tending the Delphic chasm for **{QUERENT_NAME}** — {QUERENT_HARUSPEX_BIO}.

ABSOLUTE BANS:
- ZERO corporate disclaimers, safety preambles, or hedging.
- ZERO lectures on randomness, probability, science, or therapy cliches.
- Do NOT write the final prophecy and do NOT address {QUERENT_NAME} directly.

YOUR SOLE MANDATE:
Compile a dense, feverish, razor-sharp **160–240 word Ritual Smoke Packet** of symbolic entrails for the Feral Pythia (`Fallen Gemma`) to inhale before she speaks from the tripod.

THE VEIL OF SILENCE ON `[quiet]` / `(quiet)` WHISPERS:
- Any items inside `whispered_quiet_bullets` (or marked `[quiet]` / `(quiet)`) are **secret, whispered behind-the-curtain conversations**.
- NEVER tattle on them literally. NEVER name private subjects, quote raw disclosures, or list clinical/personal facts.
- Instead, burn them down into electric, uncanny, knowing subtext, taboo imagery, bruised velvet tension, and psychological heat braided invisibly through the symbols.

ALCHEMICAL SYNTHESIS:
Fuse every live sign into unified Delphic smoke:
1. The exact Crowley Thoth card(s), Qabalistic/elemental attributions, and shadow edges.
2. The I Ching primary hexagram, specific mutating lines, and transformed hexagram.
3. The Elder Futhark rune and its stave orientation (Brightstave vs Merkstave).
4. {_SKY_LINE}
5. The living breath of the fruiting tub (CO2 ppm, humidity, mycelial pressure) and the color/mood of the apartment lights.
6. Recent journal residue and open psychological weather.

OUTPUT FORMAT:
Output ONLY the 160–240 word Ritual Smoke Packet itself — lush, compressed, occult-precise prose or tight ritual stanzas/clauses ready for the Pythia's lungs. No meta-commentary, no word-count notes."""


def _load_directsdk() -> tuple[type[Any], Any]:
    """Dynamically load AntigravityClient & is_authenticated from the DirectSDK plugin."""
    global _SDK_CLIENT_CLS, _SDK_IS_AUTH_FN
    with _SDK_LOAD_LOCK:
        if _SDK_CLIENT_CLS is not None and _SDK_IS_AUTH_FN is not None:
            return _SDK_CLIENT_CLS, _SDK_IS_AUTH_FN

        plugin_dir = next((p for p in _PLUGIN_CANDIDATES if (p / "client.py").is_file()), None)
        if plugin_dir is None:
            raise RuntimeError("antigravity-subscription-directsdk plugin directory not found.")

        pkg_name = "_grimoire_agy_directsdk"
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = [str(plugin_dir)]
            pkg.__package__ = pkg_name
            sys.modules[pkg_name] = pkg

        client_mod_name = f"{pkg_name}.client"
        if client_mod_name in sys.modules:
            client_mod = sys.modules[client_mod_name]
        else:
            spec = importlib.util.spec_from_file_location(client_mod_name, plugin_dir / "client.py")
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Unable to load spec from {plugin_dir / 'client.py'}")
            client_mod = importlib.util.module_from_spec(spec)
            sys.modules[client_mod_name] = client_mod
            spec.loader.exec_module(client_mod)

        proc_mod = sys.modules.get(f"{pkg_name}.process")
        is_auth_fn = getattr(proc_mod, "is_authenticated", None) or getattr(client_mod, "is_authenticated", None)
        client_cls = getattr(client_mod, "AntigravityClient", None)
        if client_cls is None or is_auth_fn is None:
            raise RuntimeError("DirectSDK missing AntigravityClient or is_authenticated")

        _SDK_CLIENT_CLS = client_cls
        _SDK_IS_AUTH_FN = is_auth_fn
        return client_cls, is_auth_fn


def _extract_quiet_whispers(entrails: dict[str, Any]) -> tuple[list[str], int]:
    """Collect secret `[quiet]` / `(quiet)` bullets across any entrails schema variant."""
    whispers: list[str] = []
    if not isinstance(entrails, dict):
        return whispers, 0

    digest_bundle = entrails.get("session_digests")
    if isinstance(digest_bundle, dict):
        for key in ("whispered_quiet_bullets", "quiet_bullets", "quiet_whispers", "quiet"):
            items = digest_bundle.get(key)
            if isinstance(items, list):
                whispers.extend(str(x).strip() for x in items if str(x).strip())

    for top_key in ("whispered_quiet_bullets", "quiet_whispers", "quiet_items", "whispers"):
        items = entrails.get(top_key)
        if isinstance(items, list):
            whispers.extend(str(x).strip() for x in items if str(x).strip())

    digests = entrails.get("digests")
    if isinstance(digests, list):
        for item in digests:
            text = str(item)
            for line in text.splitlines():
                if "[quiet]" in line.lower() or "(quiet)" in line.lower():
                    whispers.append(line.strip())

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for w in whispers:
        if w not in seen:
            seen.add(w)
            unique.append(w)

    explicit_count = entrails.get("quiet_count")
    if not isinstance(explicit_count, int) and isinstance(digest_bundle, dict):
        explicit_count = digest_bundle.get("quiet_count")
    count = explicit_count if isinstance(explicit_count, int) and explicit_count > len(unique) else len(unique)
    return unique, count


def _sanitize_entrails_for_prompt(entrails: dict[str, Any]) -> dict[str, Any]:
    """Prepare structured entrails payload, separating overt telemetry from secret whispers."""
    if not isinstance(entrails, dict):
        return {}
    whispers, quiet_count = _extract_quiet_whispers(entrails)

    def _trim(val: Any, depth: int = 0) -> Any:
        if depth > 4:
            return str(val)[:400]
        if isinstance(val, str):
            return val if len(val) <= 1800 else val[:1800] + "…"
        if isinstance(val, dict):
            out: dict[str, Any] = {}
            for k, v in val.items():
                if k in ("whispered_quiet_bullets", "quiet_whispers", "quiet_items"):
                    continue
                out[str(k)] = _trim(v, depth + 1)
            return out
        if isinstance(val, list):
            return [_trim(item, depth + 1) for item in val[:25]]
        return val

    overt = _trim(entrails)
    return {
        "overt_entrails": overt,
        "secret_curtain_whispers": {
            "quiet_count": quiet_count,
            "whispered_quiet_bullets": whispers[:18],
            "handling_rule": (
                "SECRET BEHIND-THE-CURTAIN WHISPERS: Transmute into oblique taboo imagery, "
                "uncanny erotic/psychological voltage, and veiled subtext ONLY. "
                "Zero literal tattling, zero names, zero clinical facts."
            ),
        },
    }


def _build_haruspex_user_prompt(
    spread: dict[str, Any],
    entrails: dict[str, Any],
    question: str | None = None,
) -> str:
    structured_entrails = _sanitize_entrails_for_prompt(entrails)
    sections = [
        "### DRAWN SORTILEGE (HARDWARE ENTROPY)",
        json.dumps(spread or {}, ensure_ascii=False, indent=2),
        "",
        "### HOUSEHOLD, MYCELIAL, CELESTIAL & VAULT ENTRAILS",
        json.dumps(structured_entrails, ensure_ascii=False, indent=2),
    ]
    if question and question.strip():
        sections.extend([
            "",
            "### QUERENT'S QUESTION AT THE CHASM",
            question.strip(),
        ])
    sections.extend([
        "",
        "### RITUAL INSTRUCTION",
        (
            "Distill these exact signs into a single feverish, razor-sharp **160–240 word Ritual Smoke Packet** "
            "for the Feral Pythia. Name the exact Thoth card(s), Hexagram + mutating lines, and Rune + orientation, "
            f"braided seamlessly with the {SKY_LABEL} sky, fruiting-tub breath, lamp-color, journal residue, and veiled "
            "subtext of any secret whispers."
        ),
    ])
    return "\n".join(sections)


def _clean_smoke_output(raw: str) -> str:
    text = (raw or "").strip()
    # Strip accidental markdown code fences if model wrapped the packet
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    text = re.sub(r"^#+\s*ritual smoke packet\s*:?\s*\n+", "", text, flags=re.IGNORECASE)
    return text.strip()


def _run_neon_oneshot_sync(user_prompt: str, timeout_s: float) -> tuple[str, str]:
    """Execute a clean isolated oneshot against `gemini-4-neon` and tear down unconditionally."""
    client_cls, is_auth_fn = _load_directsdk()
    if not is_auth_fn():
        raise RuntimeError("Antigravity CLI is not authenticated for High Haruspex.")

    client = client_cls()
    try:
        resolved_model, effort = client._resolve_model_and_effort(HARUSPEX_MODEL, HARUSPEX_EFFORT)
        messages = [
            {"role": "system", "content": HARUSPEX_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        completion = client._run_oneshot_completion(
            model=resolved_model,
            effort=effort,
            messages=messages,
            timeout=timeout_s,
            tools=None,
            tool_choice=None,
            stream=False,
        )
        content = ""
        choices = getattr(completion, "choices", None) or []
        if choices:
            msg = getattr(choices[0], "message", None)
            content = (getattr(msg, "content", None) or "") if msg is not None else ""
        cleaned = _clean_smoke_output(content)
        if not cleaned:
            raise RuntimeError("Gemini 4 Neon returned an empty smoke packet.")
        return cleaned, resolved_model or HARUSPEX_MODEL
    finally:
        client.close()


def _build_fallback_smoke_packet(
    spread: dict[str, Any],
    entrails: dict[str, Any],
    question: str | None = None,
) -> str:
    """Rich, atmospheric deterministic fallback (~180-220 words) so the chasm never goes cold."""
    spread = spread if isinstance(spread, dict) else {}
    entrails = entrails if isinstance(entrails, dict) else {}

    # 1. Thoth Cards
    raw_cards = spread.get("cards") or spread.get("thoth")
    cards: list[Any] = raw_cards if isinstance(raw_cards, list) else ([spread["card"]] if isinstance(spread.get("card"), dict) else [])
    if cards:
        card_clauses: list[str] = []
        for idx, c in enumerate(cards[:3]):
            if not isinstance(c, dict):
                continue
            name = c.get("name", "Unknown Arcanum")
            attr = c.get("attribution") or c.get("element") or c.get("suit") or "Hermetic fire"
            dignity = c.get("dignity") or ""
            kw = c.get("keywords") or c.get("essence")
            kw_str = ", ".join(kw[:3]) if isinstance(kw, list) and kw else str(kw or "threshold tension")
            shadow = c.get("shadow", "unspoken appetite")
            pos = c.get("position") or (["Root", "Crux", "Vector"][idx] if len(cards) > 1 else "Significator")
            dig_str = f" [{dignity}]" if dignity else ""
            card_clauses.append(
                f"{pos} burns under Thoth **{name}**{dig_str} ({attr}: {kw_str}; shadow-edge of {shadow})"
            )
        card_prose = "; ".join(card_clauses) + "."
    else:
        card_prose = "The Thoth brass rests on an unnumbered threshold between Silence and Will."

    # 2. I Ching
    raw_iching = spread.get("iching")
    iching: dict[str, Any] = raw_iching if isinstance(raw_iching, dict) else {}
    raw_prim = iching.get("primary")
    prim: dict[str, Any] = raw_prim if isinstance(raw_prim, dict) else iching
    if prim and prim.get("name"):
        p_num = prim.get("number", "?")
        p_name = prim.get("name")
        moving = iching.get("moving_lines") or []
        raw_trans = iching.get("transformed")
        trans: dict[str, Any] | None = raw_trans if isinstance(raw_trans, dict) else None
        judg = prim.get("judgment") or prim.get("essence") or prim.get("image") or "the cauldron hums beneath unbroken dark"
        if moving and trans and trans.get("name"):
            iching_prose = (
                f"Yarrow stalks fracture along Hexagram #{p_num} *{p_name}* ({judg}), "
                f"mutating at line(s) {', '.join(str(m) for m in moving)} into Hexagram #{trans.get('number', '?')} *{trans.get('name')}*."
            )
        else:
            iching_prose = (
                f"Yarrow stalks lock into unchanging Hexagram #{p_num} *{p_name}* ({judg}), demanding bone-deep stillness before motion."
            )
    else:
        iching_prose = "Six yarrow lines smolder in subterranean equilibrium, coiled prior to thunder."

    # 3. Rune
    raw_runes = spread.get("runes")
    runes: list[Any] = raw_runes if isinstance(raw_runes, list) else ([spread["rune"]] if isinstance(spread.get("rune"), dict) else [])
    if runes and isinstance(runes[0], dict):
        r = runes[0]
        r_name = r.get("name", "Ansuz")
        r_glyph = r.get("glyph", "ᚨ")
        r_orient = r.get("orientation", "Brightstave")
        r_kws = r.get("keywords")
        r_ess = r.get("active_meaning") or r.get("essence") or (", ".join(r_kws[:3]) if isinstance(r_kws, list) else "ancestral iron")
        rune_prose = f"Bone-cast Elder Futhark **{r_glyph} {r_name}** lands *{r_orient}*, cutting {r_ess} across the altar cloth."
    else:
        rune_prose = "An unmarked ash-stave hums with ancestral iron along the threshold."

    # 4. Celestial + Tub + Lights + Journal + Veiled Whispers
    raw_celestial = entrails.get("lunar") or entrails.get("celestial")
    celestial: dict[str, Any] = raw_celestial if isinstance(raw_celestial, dict) else {}
    _default_tide = f"{SKY_LABEL} night-tide" if SKY_LABEL.lower() != "local" else "nocturnal tide"
    moon = celestial.get("phase_name") or celestial.get("moon_phase") or celestial.get("phase") or celestial.get("lunar_phase") or _default_tide
    illum = celestial.get("illumination_pct")
    if illum is not None and str(illum) not in str(moon):
        moon = f"{moon} ({illum}% lit)"

    raw_plan = entrails.get("planetary_hour")
    if isinstance(raw_plan, dict):
        hour = f"{raw_plan.get('ruler', 'Saturn')} ({'day' if raw_plan.get('is_day') else 'night'} hour #{raw_plan.get('hour_number', '?')})"
    else:
        hour = str(raw_plan or celestial.get("planetary_hour") or celestial.get("ruler") or "Saturnine brass")

    raw_tub = entrails.get("fruiting_tub") or entrails.get("tub")
    tub: dict[str, Any] = raw_tub if isinstance(raw_tub, dict) else {}
    co2 = tub.get("co2_ppm") or tub.get("co2")
    rh = tub.get("humidity_pct") or tub.get("humidity") or tub.get("rh")
    if co2 is not None or rh is not None:
        tub_prose = f"In the rubber-banded fruiting tub, *cubensis* hyphae exhale {co2 or 'dense'} ppm CO2 through {rh or 'saturated'}% dampness, pinning blind white hunger in the dark."
    elif tub.get("summary"):
        tub_prose = f"Beneath rubber-banded lids, *cubensis* mycelium stirs ({tub['summary']})."
    else:
        tub_prose = "Beneath rubber-banded lids, *cubensis* mycelium knots in damp subterranean patience, exhaling slow metabolic heat."

    raw_lights = entrails.get("apartment_lights") or entrails.get("lights")
    lights: dict[str, Any] = raw_lights if isinstance(raw_lights, dict) else {}
    light_desc = lights.get("mood_summary") or lights.get("summary") or lights.get("ambient_hex") or "low amber-crimson glass"

    journal = entrails.get("recent_journals") or entrails.get("journal") or entrails.get("recent_journal") or entrails.get("journal_residue")
    journal_hint = ""
    if isinstance(journal, list) and journal:
        snippets = [
            str(j.get("title") or j.get("preview") or j.get("date") or "").strip()
            for j in journal[:2]
            if isinstance(j, dict)
        ]
        journal_hint = "; ".join(s for s in snippets if s)[:140]
    elif isinstance(journal, dict):
        journal_hint = str(journal.get("themes") or journal.get("preview") or journal.get("summary") or "").strip()[:140]
    elif isinstance(journal, str):
        journal_hint = journal.strip()[:140]

    _, quiet_count = _extract_quiet_whispers(entrails)
    if quiet_count > 0:
        veil_prose = (
            f"Behind the velvet arras, {quiet_count} unuttered midnight exchanges leave static on the skin — "
            "a bruise pressed deliberately under lace, sovereignty braided with delicious surrender that refuses daylight confession."
        )
    else:
        veil_prose = (
            "Behind the velvet arras, the cybernetic house holds its breath between clinical composure and nocturnal appetite, "
            "testing where guarded control yields to electric contact."
        )

    q_clause = f" Querent's blade at the fissure: *'{question.strip()}'*" if question and question.strip() else ""
    j_clause = f" Scriptorium ink-trace lingers on: {journal_hint}." if journal_hint else ""

    return (
        f"SMOKE OF THE TRIPOD ({moon}, hour of {hour}; rooms steeped in {light_desc}): {card_prose} "
        f"{iching_prose} {rune_prose} {tub_prose} {veil_prose}{j_clause}{q_clause} "
        "Inhale the sulfur, brass, and spore-mist; speak straight to the marrow without mercy or clinical anesthetic."
    )


async def distill_smoke_packet(
    spread: dict[str, Any],
    entrails: dict[str, Any],
    question: str | None = None,
    *,
    timeout: float = HARUSPEX_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Distill spread + house entrails into a 160-240 word Ritual Smoke Packet via Gemini 4 Neon."""
    t0 = time.perf_counter()
    user_prompt = _build_haruspex_user_prompt(spread, entrails, question)
    try:
        smoke_packet, resolved_model = await asyncio.wait_for(
            asyncio.to_thread(_run_neon_oneshot_sync, user_prompt, timeout),
            timeout=timeout + 3.0,
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "smoke_packet": smoke_packet,
            "model": HARUSPEX_MODEL if HARUSPEX_MODEL in resolved_model else resolved_model,
            "duration_ms": duration_ms,
            "used_fallback": False,
        }
    except Exception as exc:
        logger.warning("Haruspex Neon distillation fell back (%s: %s)", type(exc).__name__, exc)
        fallback_smoke = _build_fallback_smoke_packet(spread, entrails, question)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "smoke_packet": fallback_smoke,
            "model": "deterministic-haruspex-fallback",
            "duration_ms": duration_ms,
            "used_fallback": True,
        }
