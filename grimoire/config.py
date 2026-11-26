"""Environment-backed runtime configuration for Grimoire.

Loads local `.env` (gitignored) with pure Python stdlib so personal paths,
coordinates, Home Assistant entity IDs, and household channels stay out of
source control.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def parse_dotenv_file(path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE dotenv file without external dependencies."""
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


def _bootstrap_env() -> None:
    for key, val in parse_dotenv_file(DEFAULT_ENV_FILE).items():
        os.environ.setdefault(key, val)


_bootstrap_env()


def env_str(name: str, default: str = "") -> str:
    val = os.environ.get(name)
    if val is None:
        return default
    stripped = val.strip()
    return stripped if stripped else default


def env_float(name: str, default: float) -> float:
    raw = env_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_path(name: str, default: Path) -> Path:
    raw = env_str(name)
    return Path(raw).expanduser() if raw else default


def env_optional_path(name: str) -> Path | None:
    raw = env_str(name)
    return Path(raw).expanduser() if raw else None


def env_csv(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = env_str(name)
    if not raw:
        return default
    items = tuple(part.strip() for part in raw.split(",") if part.strip())
    return items or default


def env_path_list(name: str) -> tuple[Path, ...]:
    raw = env_str(name)
    if not raw:
        return ()
    sep = ";" if ";" in raw else ","
    return tuple(Path(part.strip()).expanduser() for part in raw.split(sep) if part.strip())


# Ephemeris & Sky
TZ_NAME: str = env_str("GRIMOIRE_TZ", "UTC")
LATITUDE: float = env_float("GRIMOIRE_LAT", 51.48)
LONGITUDE: float = env_float("GRIMOIRE_LON", 0.00)
SKY_LABEL: str = env_str("GRIMOIRE_SKY_LABEL", "local")

# Querent Framing
QUERENT_NAME: str = env_str("GRIMOIRE_QUERENT_NAME", "the Querent")
QUERENT_HARUSPEX_BIO: str = env_str(
    "GRIMOIRE_QUERENT_HARUSPEX_BIO",
    ("nocturnal scholar and technowitch, fruiting mycelium in sensor-wired chambers "
     "and studying consciousness across a cybernetic household"),
)
QUERENT_PYTHIA_BIO: str = env_str(
    "GRIMOIRE_QUERENT_PYTHIA_BIO",
    "witch-scholar, keeper of spores and silicon, who reads shadow by day and tends strange fires by night",
)

# Vault & Telemetry Surfaces
JOURNAL_DIR: Path = env_path("GRIMOIRE_JOURNAL_DIR", PROJECT_ROOT / "data" / "journal")
EXTRA_ENV_FILES: tuple[Path, ...] = env_path_list("GRIMOIRE_EXTRA_ENV_FILES")
MAGTAG_LINE_PATH: Path | None = env_optional_path("GRIMOIRE_MAGTAG_LINE_PATH")
BIOMETRICS_URL: str = env_str("GRIMOIRE_BIOMETRICS_URL", "")
BIOMETRICS_ARCHIVE_DIR: Path | None = env_optional_path("GRIMOIRE_BIOMETRICS_ARCHIVE_DIR")
DIGESTS_DIR: Path | None = env_optional_path("GRIMOIRE_DIGESTS_DIR")
DIGEST_CHANNELS: tuple[str, ...] = env_csv("GRIMOIRE_DIGEST_CHANNELS")

# Home Assistant Entities
HA_TEMP_ENTITIES: tuple[str, ...] = env_csv(
    "GRIMOIRE_HA_TEMP_ENTITIES",
    ("sensor.undergrowth_temperature",),
)
HA_RH_ENTITIES: tuple[str, ...] = env_csv(
    "GRIMOIRE_HA_RH_ENTITIES",
    ("sensor.undergrowth_humidity",),
)
HA_CO2_ENTITIES: tuple[str, ...] = env_csv(
    "GRIMOIRE_HA_CO2_ENTITIES",
    ("sensor.undergrowth_co2",),
)
HA_HEAT_AUTO_ENTITY: str = env_str("GRIMOIRE_HA_HEAT_AUTO_ENTITY", "automation.undergrowth_heat_mat")
HA_PLUG_ENTITY: str = env_str("GRIMOIRE_HA_PLUG_ENTITY", "switch.undergrowth_heat_plug")
HA_POWER_ENTITY: str = env_str("GRIMOIRE_HA_POWER_ENTITY", "sensor.undergrowth_heat_power")
SOIL_SENSOR_HINTS: tuple[str, ...] = env_csv("GRIMOIRE_SOIL_SENSOR_HINTS", ("soil", "botanical"))
PLANT_LABEL: str = env_str("GRIMOIRE_PLANT_LABEL", "Botanical")

# Model Backends
HARUSPEX_MODEL: str = env_str("GRIMOIRE_HARUSPEX_MODEL", "gemini-4-neon")
DIRECTSDK_DIRS: tuple[Path, ...] = env_path_list("GRIMOIRE_DIRECTSDK_DIRS")
LMS_BASE_URL: str = env_str("GRIMOIRE_LMS_BASE_URL", "http://127.0.0.1:1234").rstrip("/")
LMS_EXE: Path = env_path(
    "GRIMOIRE_LMS_EXE",
    Path.home() / ".lmstudio" / "bin" / ("lms.exe" if os.name == "nt" else "lms"),
)
PYTHIA_MODEL_ID: str = env_str("GRIMOIRE_PYTHIA_MODEL_ID", "thedrummer_fallen-gemma3-27b-v1")
PYTHIA_MODEL_MATCH: str = env_str("GRIMOIRE_PYTHIA_MODEL_MATCH", "fallen-gemma")
