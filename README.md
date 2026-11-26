# Grimoire // Technowitch

A fin-de-siècle Symbolist **Scriptorium** and **Three-Tier Delphic Oracle** styled as a tarnished brass laboratory instrument.

Pairs a pure-Markdown daily journal (`YYYY-MM-DD.md`) with a hardware-entropy divination engine and a two-model mantic pipeline that metabolizes room atmosphere, fruiting-chamber telemetry, lunar geometry, and veiled session digests into live prophetic prose.

---

## Architecture

1. **Stage I — Hardware-Entropy Sortilege & Astronomical Ephemeris (`grimoire/sortilege.py`)**
   - Zero external dependencies (`os.urandom` + `secrets` rejection sampling).
   - Full **78-card Crowley Thoth Tarot** with Qabalistic, astrological, and shadow attributions.
   - Authentic **1:3:5:7 yarrow-stalk I Ching** across all 64 King Wen hexagrams, tracking moving lines (`6` / `9`) and transformed hexagrams.
   - **24 Elder Futhark runes** with symmetry-aware *Brightstave* / *Merkstave* orientation.
   - Pure-stdlib solar horizon, lunar phase/illumination/zodiac, and unequal **Chaldean planetary hours**.

2. **Stage II — The High Haruspex (`grimoire/haruspex.py` + `grimoire/entrails.py`)**
   - Gathers optional live entrails asynchronously: Home Assistant fruiting-chamber sensors (`CO2`, `RH`, temperature) & room lamp color, qualitative somatic weather (strictly stripped of raw numeric scores), recent Markdown journal entries, and session digests.
   - Routes `(quiet)` / `[quiet]` behind-the-curtain whispers through a strict veil: distilled into oblique symbolic voltage inside a 160–240 word **Ritual Smoke Packet**, never quoted or itemized aloud.
   - Falls back cleanly to a deterministic local alchemical compiler if cloud Haruspex auth is absent.

3. **Stage III — The Feral Pythia (`grimoire/pythia.py`)**
   - Manages local **LM Studio** vessel lifecycle (`Awaken` / `Banish` VRAM controls) and streams syncretic **Daily Omens** and multi-turn tripod dialogues over Server-Sent Events (`SSE`) from `Fallen Gemma 3 27B`.
   - Any passage from the Chasm can be inscribed directly into today's Markdown journal.

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
python run.py --host 127.0.0.1 --port 7940
```

Open `http://127.0.0.1:7940` in your browser.

- **Scriptorium** writes clean `YYYY-MM-DD.md` files in `GRIMOIRE_JOURNAL_DIR` (`./data/journal` by default).
- **Oracle consultations & multi-turn threads** persist separately in `./data/oracle.db` (SQLite WAL).
