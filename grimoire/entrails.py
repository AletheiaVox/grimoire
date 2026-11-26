"""Live household telemetry, somatic weather, journal residue & session entrails.

Reads asynchronously from optional configured surfaces:
- Home Assistant REST API (`HASS_URL` / `HASS_TOKEN` via `.env` or environment)
- Optional e-ink companion `line.json` (`GRIMOIRE_MAGTAG_LINE_PATH`)
- Biometrics bridge (`GRIMOIRE_BIOMETRICS_URL` with JSON archive fallback)
  translated strictly into qualitative somatic prose (zero raw sleep scores)
- Markdown Scriptorium (`GRIMOIRE_JOURNAL_DIR/YYYY-MM-DD.md`)
- Session digests (`GRIMOIRE_DIGESTS_DIR/<channel>/*.md`)
  with strict separation of `(quiet)` / `[quiet]` behind-the-curtain whispers.
"""

from __future__ import annotations

import asyncio
import colorsys
import json
import math
import os
import re
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from grimoire.config import (
    BIOMETRICS_ARCHIVE_DIR,
    BIOMETRICS_URL,
    DIGEST_CHANNELS,
    DIGESTS_DIR,
    EXTRA_ENV_FILES,
    HA_CO2_ENTITIES,
    HA_HEAT_AUTO_ENTITY,
    HA_PLUG_ENTITY,
    HA_POWER_ENTITY,
    HA_RH_ENTITIES,
    HA_TEMP_ENTITIES,
    JOURNAL_DIR,
    MAGTAG_LINE_PATH,
    PLANT_LABEL,
    SOIL_SENSOR_HINTS,
    parse_dotenv_file,
)
from grimoire.sortilege import _local_tz, celestial_state

ENV_PATHS = EXTRA_ENV_FILES

DEFAULT_AMBIENT_HEX = "#A88948"

QUIET_FRAMING_NOTE = (
    "`whispered_quiet_bullets` hold secret, behind-the-curtain exchanges marked `(quiet)` "
    "or `[quiet]` during veiled stretches across the household. They are private "
    "nocturnal subtext — transmute only into oblique symbolic resonance and atmospheric "
    "voltage, never literal disclosure or daylight quoting."
)

_QUIET_RE = re.compile(r"(\(quiet\)|\[quiet\])", re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", re.DOTALL)
_JOURNAL_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
_DIGEST_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


# ===========================================================================
# CREDENTIALS & HTTP HELPERS (ZERO HARDCODED SECRETS)
# ===========================================================================


def _parse_dotenv_file(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if not path.is_file():
        return parsed
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export ") and "=" in line:
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            parsed[key] = val
    except OSError:
        pass
    return parsed


def _load_hass_credentials() -> tuple[str | None, str | None]:
    url = (os.environ.get("HASS_URL") or "").strip() or None
    token = (os.environ.get("HASS_TOKEN") or "").strip() or None
    if url and token:
        return url.rstrip("/"), token

    for env_path in ENV_PATHS:
        vals = parse_dotenv_file(env_path)
        if not url and vals.get("HASS_URL"):
            url = vals["HASS_URL"].strip()
        if not token and vals.get("HASS_TOKEN"):
            token = vals["HASS_TOKEN"].strip()
        if url and token:
            break

    return (url.rstrip("/") if url else None), token


async def _async_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 2.0,
) -> Any:
    if httpx is not None:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def _sync_fetch() -> Any:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return await asyncio.to_thread(_sync_fetch)


# ===========================================================================
# HOME ASSISTANT: FRUITING CHAMBER, BOTANICAL & POETIC LIGHTS
# ===========================================================================


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in ("", "unavailable", "unknown", "none", "null"):
        return None
    try:
        num = float(s)
        return round(num, 2) if math.isfinite(num) else None
    except (ValueError, TypeError):
        return None


def _clean_state_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("unavailable", "unknown", "none"):
        return None
    return s


def _kelvin_to_rgb(kelvin: float) -> tuple[int, int, int]:
    """Convert color temperature in Kelvin (1500..12000) to sRGB tuple."""
    temp = max(1500.0, min(12000.0, float(kelvin))) / 100.0
    if temp <= 66.0:
        r = 255.0
        g = 99.4708025861 * math.log(temp) - 161.1195681661
        b = 0.0 if temp <= 19.0 else 138.5177312231 * math.log(temp - 10.0) - 305.0447927307
    else:
        r = 329.698727446 * ((temp - 60.0) ** -0.1332047592)
        g = 288.1221695283 * ((temp - 60.0) ** -0.0755148492)
        b = 255.0
    return (
        max(0, min(255, int(round(r)))),
        max(0, min(255, int(round(g)))),
        max(0, min(255, int(round(b)))),
    )


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _poetic_tone_for_light(
    rgb: tuple[int, int, int] | None,
    kelvin: int | None,
    brightness: int | None,
    color_mode: str | None = None,
) -> str:
    bri_prefix = ""
    if brightness is not None:
        if brightness < 55:
            bri_prefix = "low "
        elif brightness > 205:
            bri_prefix = "bright "

    use_kelvin_first = (color_mode == "color_temp" and kelvin is not None)
    if rgb is not None and not use_kelvin_first:
        h, s, _ = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
        hue = h * 360.0
        if s < 0.16:
            tone = "warm parchment-white" if (kelvin or 3000) < 3600 else "pale moon-ivory"
        elif hue < 16.0 or hue >= 348.0:
            tone = "warm ember-rose" if rgb[2] >= 100 else "ember-crimson"
        elif hue < 36.0:
            tone = "candlelit amber"
        elif hue < 58.0:
            tone = "tarnished gold"
        elif hue < 155.0:
            tone = "moss-verdigris"
        elif hue < 215.0:
            tone = "sea-glass cyan"
        elif hue < 275.0:
            tone = "nocturnal indigo"
        elif hue < 320.0:
            tone = "bruised plum-violet"
        else:
            tone = "warm ember-rose"
        return f"{bri_prefix}{tone}".strip()

    if kelvin is not None:
        if kelvin <= 2400:
            return f"{bri_prefix}candlelit amber".strip()
        if kelvin <= 3000:
            return f"{bri_prefix}warm hearth-gold".strip()
        if kelvin <= 4200:
            return f"{bri_prefix}parchment-ivory".strip()
        return f"{bri_prefix}clear daylight-silver".strip()

    return f"{bri_prefix}warm hearth-glow".strip()


_APARTMENT_LIGHT_SPECS = (
    ("living_room", "light.living_room_living_room", "Living room"),
    ("office", "light.office_office", "Office"),
    ("kitchen", "light.kitchen_kitchen", "Kitchen"),
    ("bedroom", "light.bedroom_bedroom", "Bedroom"),
)


def _parse_lights(state_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not state_map:
        return {
            "summary": "Hearth unreachable — tarnished gold reserve",
            "ambient_hex": DEFAULT_AMBIENT_HEX,
            "rooms": {},
        }

    rooms: dict[str, dict[str, Any]] = {}
    weighted_rgb: list[tuple[tuple[int, int, int], float]] = []
    tone_groups: dict[str, list[str]] = {}
    dark_rooms: list[str] = []

    for slug, entity_id, label in _APARTMENT_LIGHT_SPECS:
        ent = state_map.get(entity_id, {})
        st = str(ent.get("state", "unavailable")).lower()
        attrs = ent.get("attributes") or {}
        bri_raw = attrs.get("brightness")
        brightness = int(bri_raw) if isinstance(bri_raw, (int, float)) else None
        kelvin_raw = attrs.get("color_temp_kelvin")
        kelvin = int(kelvin_raw) if isinstance(kelvin_raw, (int, float)) else None

        rgb_raw = attrs.get("rgb_color")
        rgb_tuple: tuple[int, int, int] | None = None
        if isinstance(rgb_raw, (list, tuple)) and len(rgb_raw) == 3:
            try:
                rgb_tuple = (int(rgb_raw[0]), int(rgb_raw[1]), int(rgb_raw[2]))
            except (ValueError, TypeError):
                rgb_tuple = None

        active_rgb: tuple[int, int, int] | None = None
        if st == "on":
            if rgb_tuple is not None:
                active_rgb = rgb_tuple
            elif kelvin is not None:
                active_rgb = _kelvin_to_rgb(kelvin)
            else:
                active_rgb = (212, 168, 92)
            weight = max(0.25, (brightness if brightness is not None else 128) / 255.0)
            weighted_rgb.append((active_rgb, weight))
            color_mode = str(attrs.get("color_mode", "")).lower() or None
            tone = _poetic_tone_for_light(rgb_tuple, kelvin, brightness, color_mode)
            tone_groups.setdefault(tone, []).append(label)
        else:
            dark_rooms.append(label)

        rooms[slug] = {
            "entity_id": entity_id,
            "name": label,
            "state": st,
            "brightness": brightness,
            "color_temp_kelvin": kelvin,
            "rgb_color": list(rgb_tuple) if rgb_tuple is not None else None,
            "hex": _rgb_to_hex(active_rgb) if active_rgb is not None else None,
        }

    if weighted_rgb:
        total_w = sum(w for _, w in weighted_rgb)
        avg_r = sum(c[0] * w for c, w in weighted_rgb) / total_w
        avg_g = sum(c[1] * w for c, w in weighted_rgb) / total_w
        avg_b = sum(c[2] * w for c, w in weighted_rgb) / total_w
        ambient_hex = _rgb_to_hex((int(round(avg_r)), int(round(avg_g)), int(round(avg_b))))

        lit_clauses: list[str] = []
        for tone, names in tone_groups.items():
            joined = " & ".join(names) if len(names) <= 2 else f"{', '.join(names[:-1])} & {names[-1]}"
            lit_clauses.append(f"{joined} in {tone}")
        if dark_rooms:
            dark_joined = " & ".join(dark_rooms) if len(dark_rooms) <= 2 else f"{', '.join(dark_rooms[:-1])} & {dark_rooms[-1]}"
            lit_clauses.append(f"{dark_joined} dark")
        summary = ", ".join(lit_clauses)
    else:
        ambient_hex = DEFAULT_AMBIENT_HEX
        summary = "All lamps dark — tarnished gold stillness"

    return {
        "summary": summary,
        "ambient_hex": ambient_hex,
        "rooms": rooms,
    }


def _parse_tub_and_plant(
    state_map: dict[str, dict[str, Any]],
    magtag_data: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    def _sensor_float(entities: tuple[str, ...]) -> float | None:
        for eid in entities:
            val = _to_float(state_map.get(eid, {}).get("state"))
            if val is not None:
                return val
        return None

    temp_c = _sensor_float(HA_TEMP_ENTITIES)
    rh_pct = _sensor_float(HA_RH_ENTITIES)
    co2_ppm = _sensor_float(HA_CO2_ENTITIES)
    if co2_ppm is not None:
        co2_ppm = round(co2_ppm, 1)
    if rh_pct is not None:
        rh_pct = round(rh_pct, 1)

    heat_auto = _clean_state_str(state_map.get(HA_HEAT_AUTO_ENTITY, {}).get("state"))
    plug_state = _clean_state_str(state_map.get(HA_PLUG_ENTITY, {}).get("state"))
    power_w = _to_float(state_map.get(HA_POWER_ENTITY, {}).get("state"))

    if temp_c is None and rh_pct is None and co2_ppm is None:
        tub_status = "offline"
    else:
        parts: list[str] = []
        if co2_ppm is not None and co2_ppm >= 1000:
            parts.append("dense CO2 — wants fresh air")
        elif rh_pct is not None and rh_pct >= 85:
            parts.append("humid fruiting breath")
        else:
            parts.append("steady mycelial climate")
        if plug_state == "on" or (power_w is not None and power_w > 1.0):
            parts.append("mat warming")
        elif plug_state == "off":
            parts.append("mat resting")
        tub_status = " · ".join(parts)

    # Soil sensors + optional MagTag line.json
    moisture: str | None = None
    hints_lower = tuple(h.lower() for h in SOIL_SENSOR_HINTS)
    for eid, ent in state_map.items():
        low = eid.lower()
        if eid.startswith("sensor.") and any(h in low for h in hints_lower):
            st_val = _clean_state_str(ent.get("state"))
            if st_val is not None:
                unit = (ent.get("attributes") or {}).get("unit_of_measurement", "")
                moisture = f"{st_val}{unit}".strip()
                break

    plant_line: str | None = None
    if isinstance(magtag_data, dict):
        raw_line = magtag_data.get("line")
        if isinstance(raw_line, str) and raw_line.strip():
            plant_line = raw_line.strip()
        if moisture is None:
            raw_m = magtag_data.get("moisture")
            if raw_m is not None and str(raw_m).strip() not in ("", "?", "None"):
                moisture = str(raw_m).strip()

    tub = {
        "temperature_c": temp_c,
        "humidity_pct": rh_pct,
        "co2_ppm": co2_ppm,
        "heat_mat_auto": heat_auto,
        "power_w": power_w,
        "status": tub_status,
    }
    plant = {
        "label": PLANT_LABEL,
        "line": plant_line,
        "moisture": moisture,
    }
    return tub, plant


def _read_magtag_line() -> dict[str, Any] | None:
    if MAGTAG_LINE_PATH is None or not MAGTAG_LINE_PATH.is_file():
        return None
    try:
        return json.loads(MAGTAG_LINE_PATH.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


async def gather_header_telemetry() -> dict[str, Any]:
    """Fast (`timeout=2.0s`) header telemetry read for chamber, botanical, lights & sky."""
    hass_url, hass_token = _load_hass_credentials()
    state_map: dict[str, dict[str, Any]] = {}

    async def _fetch_ha() -> dict[str, dict[str, Any]]:
        if not hass_url or not hass_token:
            return {}
        payload = await _async_get_json(
            f"{hass_url}/api/states",
            headers={"Authorization": f"Bearer {hass_token}"},
            timeout=2.0,
        )
        if isinstance(payload, list):
            return {
                str(item["entity_id"]): item
                for item in payload
                if isinstance(item, dict) and item.get("entity_id")
            }
        return {}

    ha_task = asyncio.create_task(_fetch_ha())
    magtag_task = asyncio.to_thread(_read_magtag_line)
    ha_res, magtag_data = await asyncio.gather(ha_task, magtag_task, return_exceptions=True)

    if isinstance(ha_res, dict):
        state_map = ha_res
    if isinstance(magtag_data, BaseException):
        magtag_data = None

    tub, plant = _parse_tub_and_plant(state_map, magtag_data)
    lights = _parse_lights(state_map)

    return {
        "tub": tub,
        "plant": plant,
        "lights": lights,
        "celestial": celestial_state(),
    }


# ===========================================================================
# SOMATIC WEATHER (QUALITATIVE PROSE ONLY — ZERO RAW SCORES)
# ===========================================================================


def translate_biometrics_to_qualitative(
    payload: dict[str, Any] | None,
    *,
    from_archive: bool = False,
) -> str:
    """Translate biometrics `/now` or archive JSON into pure qualitative somatic prose.

    Strictly forbids emitting raw integer sleep scores or numeric digits.
    Rested baseline is ~360–390 minutes (6–6.5h).
    """
    if not isinstance(payload, dict) or not payload:
        return "offline / unspoken — ring silent beyond the tailnet"

    duration_min: float | None = None
    session_count = 1
    awake_breaks = 0

    last_sleep = payload.get("lastSleep")
    if isinstance(last_sleep, dict):
        dur = last_sleep.get("durationMinutes")
        if isinstance(dur, (int, float)):
            duration_min = float(dur)
        sessions = last_sleep.get("sessions")
        if isinstance(sessions, list) and sessions:
            session_count = len(sessions)

    sleep_list = payload.get("sleep")
    if duration_min is None and isinstance(sleep_list, list) and sleep_list:
        latest = sleep_list[-1]
        if isinstance(latest, dict):
            dur = latest.get("durationMinutes")
            if isinstance(dur, (int, float)):
                duration_min = float(dur)
            sessions = latest.get("sessions")
            if isinstance(sessions, list) and sessions:
                session_count = len(sessions)
                stages = sessions[-1].get("stages") if isinstance(sessions[-1], dict) else None
                if isinstance(stages, list):
                    awake_breaks = sum(
                        1 for st in stages if isinstance(st, dict) and str(st.get("stage", "")).upper() == "AWAKE"
                    )

    bpm: float | None = None
    hr = payload.get("heartRate")
    if isinstance(hr, dict) and isinstance(hr.get("bpm"), (int, float)):
        bpm = float(hr["bpm"])
    elif isinstance(hr, list) and hr:
        last_hr = hr[-1]
        if isinstance(last_hr, dict) and isinstance(last_hr.get("bpm"), (int, float)):
            bpm = float(last_hr["bpm"])

    clauses: list[str] = []
    split_flag = session_count > 1 or awake_breaks >= 10

    if duration_min is not None:
        if duration_min >= 420:
            clauses.append(
                "deeply replenished rest across a split-sleep seam"
                if split_flag
                else "deeply rested, long-tide recovery well above baseline"
            )
        elif duration_min >= 355:
            clauses.append(
                "rested baseline across a split-sleep seam"
                if split_flag
                else "steady, well-rested baseline"
            )
        elif duration_min >= 295:
            clauses.append(
                "split-sleep edge just shy of baseline"
                if split_flag
                else "trimmed sleep edge just beneath baseline"
            )
        else:
            clauses.append("thin, short-slept nocturnal edge")

    if bpm is not None:
        if bpm < 62:
            clauses.append("unhurried parasympathetic calm in the resting pulse")
        elif bpm <= 76:
            clauses.append("even, settled autonomic hum")
        elif bpm <= 90:
            clauses.append("warm, lightly elevated sympathetic pulse")
        else:
            clauses.append("quickened high-voltage pulse")

    if not clauses:
        return "offline / unspoken — somatic trace quiet"

    prose = " with ".join(clauses)
    if from_archive:
        prose = f"live ring unreachable; last archived trace held {prose}"

    # Hard belt-and-suspenders guard: strip any accidental digits
    prose = re.sub(r"\d+", "", prose).replace("  ", " ").strip()
    return prose


def _read_latest_biometrics_archive() -> tuple[dict[str, Any] | None, str]:
    if BIOMETRICS_ARCHIVE_DIR is None or not BIOMETRICS_ARCHIVE_DIR.is_dir():
        return None, "offline"
    files = sorted(BIOMETRICS_ARCHIVE_DIR.glob("*.json"))
    if not files:
        return None, "offline"
    newest = files[-1]
    try:
        data = json.loads(newest.read_text(encoding="utf-8", errors="replace"))
        return (data if isinstance(data, dict) else None), f"archive:{newest.name}"
    except Exception:
        return None, "offline"


async def _gather_somatic_weather() -> dict[str, str]:
    if BIOMETRICS_URL:
        try:
            now_data = await _async_get_json(BIOMETRICS_URL, timeout=1.8)
            if isinstance(now_data, dict) and (
                now_data.get("lastSleep") or now_data.get("heartRate") or now_data.get("skinTemperature")
            ):
                return {
                    "summary": translate_biometrics_to_qualitative(now_data, from_archive=False),
                    "source": "biometrics:/now",
                }
        except Exception:
            pass

    archive_data, source_label = await asyncio.to_thread(_read_latest_biometrics_archive)
    if archive_data is not None:
        return {
            "summary": translate_biometrics_to_qualitative(archive_data, from_archive=True),
            "source": source_label,
        }
    return {
        "summary": "offline / unspoken — ring silent beyond the tailnet",
        "source": "offline",
    }


# ===========================================================================
# SCRIPTORIUM JOURNAL & SESSION DIGESTS (`[quiet]` / `(quiet)` SEPARATION)
# ===========================================================================


def strip_yaml_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text or "").strip()


def _read_recent_journals(
    max_entries: int = 3,
    journal_dir: Path = JOURNAL_DIR,
) -> list[dict[str, Any]]:
    if max_entries <= 0 or not journal_dir.is_dir():
        return []

    candidates: list[tuple[str, Path]] = []
    for entry in journal_dir.iterdir():
        name = entry.name
        if name.startswith("_") or name.startswith(".") or not entry.is_file():
            continue
        m = _JOURNAL_FILE_RE.match(name)
        if m:
            candidates.append((m.group(1), entry))

    candidates.sort(key=lambda item: item[0], reverse=True)
    results: list[dict[str, Any]] = []
    for date_str, path in candidates:
        if len(results) >= max_entries:
            break
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = strip_yaml_frontmatter(raw)
        cleaned = re.sub(r"\n{3,}", "\n\n", body).strip()
        if not cleaned:
            continue
        excerpt = cleaned[:1200].rstrip() + ("…" if len(cleaned) > 1200 else "")
        first_line = next((ln.lstrip("# ").strip() for ln in cleaned.splitlines() if ln.strip()), "")
        results.append(
            {
                "date": date_str,
                "file": path.name,
                "excerpt": excerpt,
                "preview": first_line[:160],
                "word_count": len(cleaned.split()),
            }
        )
    return results


def parse_session_digest_bullets(markdown_text: str) -> tuple[list[str], list[str]]:
    """Strip YAML frontmatter and split bullets into `(public_bullets, whispered_quiet_bullets)`.

    Any bullet or standalone content line containing `(quiet)` or `[quiet]`
    (case-insensitive) is routed strictly into `whispered_quiet_bullets`.
    """
    body = strip_yaml_frontmatter(markdown_text)
    if not body:
        return [], []

    items: list[str] = []
    current_bullet: list[str] = []

    def _flush() -> None:
        if current_bullet:
            joined = " ".join(part.strip() for part in current_bullet if part.strip()).strip()
            if joined:
                items.append(joined)
            current_bullet.clear()

    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            _flush()
            continue
        if stripped.startswith("#"):
            _flush()
            if _QUIET_RE.search(stripped):
                items.append(stripped.lstrip("#").strip())
            continue
        if stripped.startswith(("- ", "* ", "• ")):
            _flush()
            current_bullet.append(stripped[2:].strip())
        elif current_bullet and raw_line[:1] in (" ", "\t"):
            current_bullet.append(stripped)
        else:
            _flush()
            items.append(stripped)
    _flush()

    public_bullets: list[str] = []
    whispered_quiet_bullets: list[str] = []
    for item in items:
        if _QUIET_RE.search(item):
            whispered_quiet_bullets.append(item)
        else:
            public_bullets.append(item)

    return public_bullets, whispered_quiet_bullets


def _read_session_digests(
    max_digest_days: int = 4,
    sessions_root: Path | None = DIGESTS_DIR,
    max_files: int = 10,
) -> list[dict[str, Any]]:
    """Read session digests from `<sessions_root>/<channel>/*.md`."""
    if sessions_root is None or not sessions_root.is_dir():
        return []

    today_local: date = datetime.now(_local_tz()).date()
    cutoff_date: date = today_local - timedelta(days=max(1, max_digest_days))

    channels = DIGEST_CHANNELS or tuple(
        sorted(d.name for d in sessions_root.iterdir() if d.is_dir() and not d.name.startswith(("_", ".")))
    )

    discovered: list[tuple[str, float, str, Path]] = []
    for persona in channels:
        p_dir = sessions_root / persona
        if not p_dir.is_dir():
            continue
        for md_path in p_dir.glob("*.md"):
            if not md_path.is_file() or md_path.name.startswith(("_", ".")):
                continue
            m = _DIGEST_DATE_RE.match(md_path.name)
            try:
                mtime = md_path.stat().st_mtime
            except OSError:
                continue
            if m:
                d_str = m.group(1)
            else:
                d_str = datetime.fromtimestamp(mtime, tz=_local_tz()).strftime("%Y-%m-%d")
            discovered.append((d_str, mtime, persona, md_path))

    discovered.sort(key=lambda item: (item[0], item[1]), reverse=True)

    in_window: list[tuple[str, float, str, Path]] = []
    for item in discovered:
        try:
            d_obj = date.fromisoformat(item[0])
            if d_obj >= cutoff_date:
                in_window.append(item)
        except ValueError:
            continue

    selected = in_window[:max_files] if in_window else discovered[: min(8, max_files)]

    sessions: list[dict[str, Any]] = []
    for d_str, _, persona, md_path in selected:
        try:
            raw_md = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        public_bullets, whispered_quiet_bullets = parse_session_digest_bullets(raw_md)
        if not public_bullets and not whispered_quiet_bullets:
            continue
        sessions.append(
            {
                "persona": persona,
                "date": d_str,
                "file": md_path.name,
                "public_bullets": public_bullets,
                "whispered_quiet_bullets": whispered_quiet_bullets,
            }
        )
    return sessions


async def gather_full_entrails(
    max_journal_entries: int = 3,
    max_digest_days: int = 4,
) -> dict[str, Any]:
    """Gather complete live & vault entrails for the High Haruspex ritual distillation."""
    telemetry_task = asyncio.create_task(gather_header_telemetry())
    somatic_task = asyncio.create_task(_gather_somatic_weather())
    journals_task = asyncio.to_thread(_read_recent_journals, max_journal_entries)
    digests_task = asyncio.to_thread(_read_session_digests, max_digest_days)

    telemetry, somatic_weather, recent_journals, session_digests = await asyncio.gather(
        telemetry_task,
        somatic_task,
        journals_task,
        digests_task,
    )

    all_quiet_whispers: list[str] = [
        f"[{sess['persona']} · {sess['date']}] {bullet}"
        for sess in session_digests
        for bullet in sess.get("whispered_quiet_bullets", [])
    ]
    quiet_count = sum(len(sess.get("whispered_quiet_bullets", [])) for sess in session_digests)

    return {
        "gathered_at": datetime.now(_local_tz()).isoformat(timespec="seconds"),
        "telemetry": telemetry,
        "somatic_weather": somatic_weather,
        "recent_journals": recent_journals,
        "session_digests": session_digests,
        "whispered_quiet_bullets": all_quiet_whispers,
        "quiet_count": quiet_count,
        "quiet_framing_note": QUIET_FRAMING_NOTE,
    }
