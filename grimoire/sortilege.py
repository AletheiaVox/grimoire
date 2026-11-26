"""Hardware-entropy sortilege & astronomical ephemeris for Grimoire.

Implements:
- Full 78-card Crowley Thoth Tarot (`THOTH_DECK`, `draw_thoth`)
- Authentic 1:3:5:7 yarrow-stalk I Ching with all 64 King Wen hexagrams (`cast_iching`)
- All 24 Elder Futhark runes with symmetry-aware merkstave draws (`cast_runes`)
- Pure-stdlib lunar geometry, solar horizon & Chaldean planetary hours (`celestial_state`)
- Unified ritual spread dispatcher (`cast_spread`)

Strictly uses OS cryptographic entropy (`os.urandom` and `secrets`) with zero
non-stdlib dependencies.
"""

from __future__ import annotations

import math
import os
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from grimoire.config import LATITUDE, LONGITUDE, TZ_NAME

SYNODIC_MONTH_DAYS = 29.530588853


def _local_tz() -> ZoneInfo | timezone:
    try:
        return ZoneInfo(TZ_NAME)
    except Exception:
        return timezone.utc


# ===========================================================================
# 1. CROWLEY THOTH TAROT — FULL 78-CARD DECK
# ===========================================================================

_MAJOR_ATU_RAW: list[tuple[str, str, str, str, str, list[str], str]] = [
    (
        "0",
        "The Fool",
        "The Spirit of Aether",
        "Aleph (א) · Air",
        "Air",
        ["zero-point potential", "ecstatic leap", "divine madness", "unconditioned breath"],
        "Untethered dissociation, reckless flight from incarnation",
    ),
    (
        "I",
        "The Magus",
        "The Magus of Power",
        "Beth (ב) · Mercury",
        "Air / Mercury",
        ["logos", "deft will", "trickster precision", "creative transmission"],
        "Sophistry, double-tongued manipulation, hollow cleverness",
    ),
    (
        "II",
        "The Priestess",
        "The Priestess of the Silver Star",
        "Gimel (ג) · Moon",
        "Water / Moon",
        ["liminal veil", "lunar gnosis", "virgin silence", "unspoken current"],
        "Cold withdrawal, sterile secrecy, seduction by illusion",
    ),
    (
        "III",
        "The Empress",
        "Daughter of the Mighty Ones",
        "Daleth (ד) · Venus",
        "Earth / Venus",
        ["embodied ripeness", "alchemical salt", "sensual sovereignty", "gestation"],
        "Smothering indulgence, possessive stasis, velvet inertia",
    ),
    (
        "IV",
        "The Emperor",
        "Son of the Morning; Chief Among the Mighty",
        "Tzaddi (צ) · Aries",
        "Fire",
        ["architectural command", "alchemical sulfur", "consecrated boundary", "pioneer governance"],
        "Brittle tyranny, calcified rule, domineering heat",
    ),
    (
        "V",
        "The Hierophant",
        "Magus of the Eternal",
        "Vau (ו) · Taurus",
        "Earth",
        ["embodied initiation", "interior bull-strength", "living lineage", "adamantine patience"],
        "Dogmatic orthodoxy, moralizing weight, stubborn stone-deafness",
    ),
    (
        "VI",
        "The Lovers",
        "Children of the Voice; Oracle of the Mighty Gods",
        "Zain (ז) · Gemini",
        "Air",
        ["alchemical marriage", "sword of discrimination", "sacred polarity", "chosen union"],
        "Divided appetite, ambivalent paralysis, split allegiance",
    ),
    (
        "VII",
        "The Chariot",
        "Child of the Powers of the Waters; Lord of the Triumph of Light",
        "Cheth (ח) · Cancer",
        "Water",
        ["armored grail", "directed momentum", "contained devotion", "sphinx mastery"],
        "Over-armored carapace, runaway drive, defensive shell",
    ),
    (
        "VIII",
        "Adjustment",
        "Daughter of the Lords of Truth; Ruler of the Balance",
        "Lamed (ל) · Libra",
        "Air",
        ["feather-and-sword equilibrium", "exact measure", "karmic poise", "surgical truth"],
        "Merciless severity, joyless accounting, self-indictment",
    ),
    (
        "IX",
        "The Hermit",
        "Prophet of the Eternal; Magus of the Voice of Power",
        "Yod (י) · Virgo",
        "Earth",
        ["spermatic lamp", "fertile solitude", "subterranean seed", "silent discernment"],
        "Misanthropic exile, hermetic hoarding, parched isolation",
    ),
    (
        "X",
        "Fortune",
        "Lord of the Forces of Life",
        "Kaph (כ) · Jupiter",
        "Fire / Jupiter",
        ["triadic wheel", "turning fate", "still axle", "opportune influx"],
        "Fatalistic gambling, dizzying oscillation, hubris on the rim",
    ),
    (
        "XI",
        "Lust",
        "Daughter of the Flaming Sword",
        "Teth (ט) · Leo",
        "Fire",
        ["rapturous vitalism", "serpent-lion ride", "unashamed eros", "radiant courage"],
        "Compulsive hunger, theatrical predation, repressed ferocity",
    ),
    (
        "XII",
        "The Hanged Man",
        "Spirit of the Mighty Waters",
        "Mem (מ) · Water",
        "Water",
        ["inverted perspective", "voluntary suspension", "ego surrender", "abyssal stillness"],
        "Performative martyrdom, stagnant punishment, helpless drift",
    ),
    (
        "XIII",
        "Death",
        "Child of the Great Transformers; Lord of the Gates of Death",
        "Nun (נ) · Scorpio",
        "Water",
        ["putrefactio", "radicle stripping", "scorpion-eagle metamorphosis", "fertile rot"],
        "Clinging to corpses, morbid fixation, refusal to molt",
    ),
    (
        "XIV",
        "Art",
        "Daughter of the Reconcilers; Bringer-Forth of Life",
        "Samekh (ס) · Sagittarius",
        "Fire",
        ["solve et coagula", "tempered fusion", "cauldron transmutation", "living synthesis"],
        "Lukewarm compromise, volatile impurity, unfinished amalgam",
    ),
    (
        "XV",
        "The Devil",
        "Lord of the Gates of Matter; Child of the Forces of Time",
        "Ayin (ע) · Capricorn",
        "Earth",
        ["pan-goat virility", "telluric mirth", "creative shadow", "raw ambition"],
        "Blind obsession, shame-bound compulsion, gilded bondage",
    ),
    (
        "XVI",
        "The Tower",
        "Lord of the Hosts of the Mighty",
        "Peh (פ) · Mars",
        "Fire / Mars",
        ["lightning strike", "eye of Horus", "shattered citadel", "sudden liberation"],
        "Catastrophizing, scorched-earth rage, terror of collapse",
    ),
    (
        "XVII",
        "The Star",
        "Daughter of the Firmament; Dweller Between the Waters",
        "Heh (ה) · Aquarius",
        "Air",
        ["spiral conduit", "crystalline hope", "celestial dew", "unveiled orientation"],
        "Ethereal escapism, diffused willpower, cold idealism",
    ),
    (
        "XVIII",
        "The Moon",
        "Ruler of Flux and Reflux; Child of the Sons of the Mighty",
        "Qoph (ק) · Pisces",
        "Water",
        ["kephri midnight", "jackal threshold", "blood-tide glamour", "ordeal of twilight"],
        "Delirium, ancestral dread, miasmic self-deception",
    ),
    (
        "XIX",
        "The Sun",
        "Lord of the Fire of the World",
        "Resh (ר) · Sun",
        "Fire / Sun",
        ["twin-winged dawn", "lucid emancipation", "sovereign warmth", "green mount"],
        "Blinding arrogance, solar inflation, overexposed glare",
    ),
    (
        "XX",
        "The Aeon",
        "Spirit of the Primal Fire",
        "Shin (ש) · Fire / Spirit",
        "Fire / Spirit",
        ["crowned and conquering child", "epochal reckoning", "double horizon", "waking gnosis"],
        "Fear of irreversible rebirth, clinging to an expired dispensation",
    ),
    (
        "XXI",
        "The Universe",
        "The Great One of the Night of Time",
        "Tau (ת) · Saturn / Earth",
        "Earth / Saturn",
        ["serpent-dance completion", "manifested cosmos", "crystallized work", "total integration"],
        "Lead-heavy inertia, fear of closure, sealed enclosure",
    ),
]

_SEPHIROTH = {
    1: "Kether",
    2: "Chokmah",
    3: "Binah",
    4: "Chesed",
    5: "Geburah",
    6: "Tiphareth",
    7: "Netzach",
    8: "Hod",
    9: "Yesod",
    10: "Malkuth",
}

_RANK_WORDS = {
    1: "Ace",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
}

_SUIT_ELEMENT = {
    "Wands": "Fire",
    "Cups": "Water",
    "Swords": "Air",
    "Disks": "Earth",
}

# (suit, number, lord_title, astro_decan, keywords, shadow)
_MINOR_CARDS_RAW: list[tuple[str, int, str, str, list[str], str]] = [
    # WANDS (Fire)
    ("Wands", 1, "Root of the Powers of Fire", "Primal Fire in Atziluth", ["ignition", "torch-seed", "raw creative voltage"], "Unfocused combustion, flash without hearth"),
    ("Wands", 2, "Dominion", "Mars in Aries", ["sovereign claim", "bold territory", "commanding impulse"], "Domineering aggression, restless conquest"),
    ("Wands", 3, "Virtue", "Sun in Aries", ["established vitality", "integrity of force", "springing lotus"], "Conceit, self-intoxicated pride"),
    ("Wands", 4, "Completion", "Venus in Aries", ["ordered circle", "settled rite", "earned repose"], "Premature closure, complacent enclosure"),
    ("Wands", 5, "Strife", "Saturn in Leo", ["volcanic friction", "contested will", "forging heat"], "Bitter infighting, blocked fury"),
    ("Wands", 6, "Victory", "Jupiter in Leo", ["balanced flame", "earned breakthrough", "radiant momentum"], "Triumphalism, insolence in success"),
    ("Wands", 7, "Valour", "Mars in Leo", ["lone defiance", "unbowed courage", "raw nerve"], "Desperate recklessness, picking unwinnable fights"),
    ("Wands", 8, "Swiftness", "Mercury in Sagittarius", ["electric velocity", "light-beam transmission", "sudden arc"], "Impulsive scatter, burning the wire"),
    ("Wands", 9, "Strength", "Moon in Sagittarius", ["deep reserve", "sun-and-moon resilience", "tempered spine"], "Hypervigilant exhaustion, defensive rigidity"),
    ("Wands", 10, "Oppression", "Saturn in Sagittarius", ["smothered fire", "crushing duty", "overloaded bars"], "Cruel self-driving, resentment turning punitive"),
    # CUPS (Water)
    ("Cups", 1, "Root of the Powers of Water", "Primal Water in Briah", ["open grail", "receptive tide", "welling Eros"], "Emotional flooding, uncontained longing"),
    ("Cups", 2, "Love", "Venus in Cancer", ["mutual overflow", "dolphin kinship", "magnetic resonance"], "Enmeshment, idealized mirroring"),
    ("Cups", 3, "Abundance", "Mercury in Cancer", ["pomegranate harvest", "shared cup", "sensual generosity"], "Saccharine excess, fleeting hedonism"),
    ("Cups", 4, "Luxury", "Moon in Cancer", ["tender comfort", "sheltered intimacy", "ripening stillness"], "Cloying comfort, brewing dissatisfaction"),
    ("Cups", 5, "Disappointment", "Mars in Scorpio", ["scorched lotus", "broken expectation", "clarifying grief"], "Sour bitterness, nursing betrayed ideals"),
    ("Cups", 6, "Pleasure", "Sun in Scorpio", ["deep erotic renewal", "fertile rapture", "somatic sweetness"], "Nostalgic intoxication, decadent drift"),
    ("Cups", 7, "Debauch", "Venus in Scorpio", ["poisoned glamour", "green-slime mirage", "delirious craving"], "Addictive phantasm, self-corrupting fantasy"),
    ("Cups", 8, "Indolence", "Saturn in Pisces", ["drained chalices", "swamp stagnation", "necessary departure"], "Apathy, depressive torpor, emotional rot"),
    ("Cups", 9, "Happiness", "Jupiter in Pisces", ["overflowing banquet", "uncomplicated joy", "bodied ease"], "Smug self-satisfaction, glutted complacency"),
    ("Cups", 10, "Satiety", "Mars in Pisces", ["full tree of cups", "culminated feeling", "ready for next tension"], "Overripeness, restless boredom inside perfection"),
    # SWORDS (Air)
    ("Swords", 1, "Root of the Powers of Air", "Primal Air in Yetzirah", ["invoked blade", "thelemic clarity", "severing truth"], "Destructive cynicism, disembodied intellect"),
    ("Swords", 2, "Peace", "Moon in Libra", ["crossed-blade stillness", "poised mind", "restored calm"], "Avoidant stalemate, fragile denial"),
    ("Swords", 3, "Sorrow", "Saturn in Libra", ["pierced rose", "melancholic lucidity", "grief without illusion"], "Brooding despair, romanticizing pain"),
    ("Swords", 4, "Truce", "Jupiter in Libra", ["sanctuary pause", "intellectual convalescence", "negotiated shelter"], "Stalled appeasement, uneasy armistice"),
    ("Swords", 5, "Defeat", "Venus in Aquarius", ["bent hilts", "pacifist collapse", "humbling limit"], "Spiteful capitulation, treacherous weakness"),
    ("Swords", 6, "Science", "Mercury in Aquarius", ["rose-cross geometry", "objective synthesis", "lucid method"], "Sterile reductionism, over-analysis"),
    ("Swords", 7, "Futility", "Moon in Aquarius", ["fractured thrust", "wavering resolve", "sly indirection"], "Self-sabotage, half-hearted scheming"),
    ("Swords", 8, "Interference", "Jupiter in Gemini", ["crossed currents", "paralyzing options", "mental noise"], "Chronic overthinking, squandered focus"),
    ("Swords", 9, "Cruelty", "Mars in Gemini", ["dripping daggers", "ruthless self-vivisection", "nightmare shame"], "Sadomasochistic rumination, merciless inner critic"),
    ("Swords", 10, "Ruin", "Sun in Gemini", ["shattered heart-hilt", "bankrupt paradigm", "end of delusion"], "Nihilistic spiral, scorched-mind panic"),
    # DISKS (Earth)
    ("Disks", 1, "Root of the Powers of Earth", "Primal Earth in Assiah", ["spinning coin-axis", "living matter", "embodied craft"], "Crass materialism, leaden literalism"),
    ("Disks", 2, "Change", "Jupiter in Capricorn", ["ouroboros equilibrium", "supple adaptation", "kinetic balance"], "Aimless juggling, unstable restlessness"),
    ("Disks", 3, "Works", "Mars in Capricorn", ["architectural foundation", "disciplined craft", "steady construction"], "Grinding drudgery, narrow utilitarianism"),
    ("Disks", 4, "Power", "Sun in Capricorn", ["four-towered fortress", "consolidated sovereignty", "structural order"], "Hoarded control, defensive moat"),
    ("Disks", 5, "Worry", "Mercury in Taurus", ["strained gears", "material friction", "stalled circulation"], "Scarcity dread, somatic contraction"),
    ("Disks", 6, "Success", "Moon in Taurus", ["hexagrammatic bloom", "harmonious economy", "tangible reciprocity"], "Transactional bookkeeping, fleeting comfort"),
    ("Disks", 7, "Failure", "Saturn in Taurus", ["leaden blight", "aborted harvest", "unrewarded toil"], "Paralyzing pessimism, fear of wasted effort"),
    ("Disks", 8, "Prudence", "Sun in Virgo", ["patient husbandry", "protected blossoms", "meticulous timing"], "Fussy perfectionism, risk-averse hoarding"),
    ("Disks", 9, "Gain", "Venus in Virgo", ["earned inheritance", "refined mastery", "quiet affluence"], "Calculating self-interest, gilded isolation"),
    ("Disks", 10, "Wealth", "Mercury in Virgo", ["tree of coins", "saturated abundance", "circulating legacy"], "Dead accumulation, calcified prosperity"),
]

# (suit, rank, title, sub_element, attribution, keywords, shadow)
_COURT_CARDS_RAW: list[tuple[str, str, str, str, str, list[str], str]] = [
    # WANDS
    ("Wands", "Knight", "Lord of the Flame and Lightning", "Fire of Fire", "20° Scorpio – 20° Sagittarius", ["lightning onset", "winged steed", "incandescent daring"], "Scorching impatience, cruel volatility"),
    ("Wands", "Queen", "Queen of the Thrones of Flame", "Water of Fire", "20° Pisces – 20° Aries", ["leopard magnetism", "self-possessed heat", "steady command"], "Vengeful pride, smoldering autocracy"),
    ("Wands", "Prince", "Prince of the Chariot of Fire", "Air of Fire", "20° Cancer – 20° Leo", ["expansive theater", "lion-drawn ardor", "romantic daring"], "Grandiose posturing, vacillating bravado"),
    ("Wands", "Princess", "Princess of the Shining Flame", "Earth of Fire", "Quadrant of Fire · Tiger-Altar", ["unbridled fuel", "fearless appetite", "dancer in the blaze"], "Consumptive drama, theatrical impulsivity"),
    # CUPS
    ("Cups", "Knight", "Lord of the Waves and the Waters", "Fire of Water", "20° Aquarius – 20° Pisces", ["peacock grace", "passionate quest", "poetic devotion"], "Passive seduction, melancholic languor"),
    ("Cups", "Queen", "Queen of the Thrones of the Waters", "Water of Water", "20° Gemini – 20° Cancer", ["mirror-lotus depth", "dreaming clairvoyance", "pure reflection"], "Projection screen, boundary dissolution"),
    ("Cups", "Prince", "Prince of the Chariot of the Waters", "Air of Water", "20° Libra – 20° Scorpio", ["veiled intensity", "eagle-serpent desire", "subterranean steam"], "Secretive ruthlessness, masked manipulation"),
    ("Cups", "Princess", "Princess of the Waters; Lotus of the Palace of the Floods", "Earth of Water", "Quadrant of Water · Swan-Dolphin", ["crystallized tenderness", "sweet intuition", "gentle liberation"], "Dependent romanticism, wistful drift"),
    # SWORDS
    ("Swords", "Knight", "Lord of the Winds and the Breezes", "Fire of Air", "20° Taurus – 20° Gemini", ["diving falcon", "razor velocity", "single-pointed intellect"], "Fanatical blade, tactless fanaticism"),
    ("Swords", "Queen", "Queen of the Thrones of Air", "Water of Air", "20° Virgo – 20° Libra", ["severed mask", "clear-eyed perception", "unsparing grace"], "Frigid sarcasm, slicing intimacy"),
    ("Swords", "Prince", "Prince of the Chariot of the Winds", "Air of Air", "20° Capricorn – 20° Aquarius", ["inventive architect", "pure ideation", "restless dialectic"], "Inconclusive sophistry, sabotaging every harness"),
    ("Swords", "Princess", "Princess of the Rushing Winds; Lotus of the Palace of Air", "Earth of Air", "Quadrant of Air · Desecrated Altar", ["grounded clarity", "practical vigilance", "clearing the smoke"], "Petty combativeness, destructive cunning"),
    # DISKS
    ("Disks", "Knight", "Lord of the Wild and Fertile Land", "Fire of Earth", "20° Leo – 20° Virgo", ["harvest stewardship", "enduring stamina", "somatic competence"], "Stolid obstinacy, joyless materialism"),
    ("Disks", "Queen", "Queen of the Thrones of the Earth", "Water of Earth", "20° Sagittarius – 20° Capricorn", ["ibex oasis", "bodied sanctuary", "sensual nourishment"], "Dullness, creature-comfort stupor"),
    ("Disks", "Prince", "Prince of the Chariot of Earth", "Air of Earth", "20° Aries – 20° Taurus", ["master builder", "ox-drawn persistence", "methodical craft"], "Emotional impassivity, plodding stubbornness"),
    ("Disks", "Princess", "Princess of the Echoing Hills; Rose of the Palace of Earth", "Earth of Earth", "Quadrant of Earth · Yin-Yang Altar", ["pregnant matter", "alchemy at the root", "silent gestation"], "Subterranean heaviness, hoarding potential"),
]


def _build_thoth_deck() -> list[dict[str, Any]]:
    deck: list[dict[str, Any]] = []

    for roman, name, title, attr, elem, kw, shadow in _MAJOR_ATU_RAW:
        slug = name.lower().replace("the ", "").replace(" ", "_")
        deck.append(
            {
                "id": f"atu_{roman.lower()}_{slug}",
                "number": roman,
                "name": name,
                "title": title,
                "arcana": "major",
                "suit": None,
                "attribution": attr,
                "element": elem,
                "keywords": list(kw),
                "shadow": shadow,
            }
        )

    for suit, num, lord_title, astro, kw, shadow in _MINOR_CARDS_RAW:
        rank_word = _RANK_WORDS[num]
        name = f"{rank_word} of {suit}"
        seph = _SEPHIROTH[num]
        full_title = lord_title if num == 1 else f"Lord of {lord_title}"
        deck.append(
            {
                "id": f"{suit.lower()}_{num:02d}",
                "number": num,
                "name": name,
                "title": full_title,
                "arcana": "minor",
                "suit": suit,
                "attribution": f"{astro} · {seph}",
                "element": _SUIT_ELEMENT[suit],
                "keywords": list(kw),
                "shadow": shadow,
            }
        )

    for suit, rank, title, sub_elem, attr, kw, shadow in _COURT_CARDS_RAW:
        name = f"{rank} of {suit}"
        deck.append(
            {
                "id": f"{suit.lower()}_{rank.lower()}",
                "number": rank,
                "name": name,
                "title": title,
                "arcana": "court",
                "suit": suit,
                "attribution": f"{sub_elem} · {attr}",
                "element": sub_elem,
                "keywords": list(kw),
                "shadow": shadow,
            }
        )

    if len(deck) != 78:
        raise AssertionError(f"THOTH_DECK expected 78 cards, got {len(deck)}")
    if len({c["id"] for c in deck}) != 78 or len({c["name"] for c in deck}) != 78:
        raise AssertionError("Duplicate card id or name detected in THOTH_DECK")
    return deck


THOTH_DECK: list[dict[str, Any]] = _build_thoth_deck()


def _copy_card(card: dict[str, Any]) -> dict[str, Any]:
    copied = dict(card)
    copied["keywords"] = list(card["keywords"])
    return copied


def draw_thoth(count: int = 1) -> list[dict[str, Any]]:
    """Draw `count` unique Crowley Thoth cards without replacement via cryptographic CSPRNG."""
    if count < 0 or count > len(THOTH_DECK):
        raise ValueError(f"count must be between 0 and {len(THOTH_DECK)}, got {count}")
    pool = list(range(len(THOTH_DECK)))
    drawn_indices: list[int] = []
    for i in range(count):
        pick = i + secrets.randbelow(len(pool) - i)
        pool[i], pool[pick] = pool[pick], pool[i]
        drawn_indices.append(pool[i])
    return [_copy_card(THOTH_DECK[idx]) for idx in drawn_indices]


# ===========================================================================
# 2. YARROW-STALK I CHING — ALL 64 KING WEN HEXAGRAMS
# ===========================================================================

TRIGRAMS: dict[tuple[int, int, int], str] = {
    (1, 1, 1): "Heaven (Qian ☰)",
    (0, 0, 0): "Earth (Kun ☷)",
    (1, 0, 0): "Thunder (Zhen ☳)",
    (0, 1, 0): "Water (Kan ☵)",
    (0, 0, 1): "Mountain (Gen ☶)",
    (0, 1, 1): "Wind (Xun 巽)",
    (1, 0, 1): "Fire (Li ☲)",
    (1, 1, 0): "Lake (Dui ☱)",
}

_H = (1, 1, 1)   # Heaven
_L = (1, 1, 0)   # Lake
_F = (1, 0, 1)   # Fire
_T = (1, 0, 0)   # Thunder
_WI = (0, 1, 1)  # Wind
_WA = (0, 1, 0)  # Water
_M = (0, 0, 1)   # Mountain
_E = (0, 0, 0)   # Earth

# (number, lower_bits, upper_bits, name, chinese, pinyin, judgment, image)
_KING_WEN_RAW: list[tuple[int, tuple[int, int, int], tuple[int, int, int], str, str, str, str, str]] = [
    (1, _H, _H, "The Creative", "乾", "Qián", "Sublime origination; untiring perseverance bears sovereign fruit.", "Heaven moves with ceaseless vigor; the sovereign strengthens body and will without rest."),
    (2, _E, _E, "The Receptive", "坤", "Kūn", "Devoted yielding carries all things; follow the mare's deep terrain.", "Earth's condition is capacious receptivity; hold outer weight with breadth of marrow."),
    (3, _T, _WA, "Difficulty at the Beginning", "屯", "Zhūn", "Blades of grass push through frozen crust; appoint helpers, do not force passage.", "Clouds and thunder coil together; weave order out of raw natal chaos."),
    (4, _WA, _M, "Youthful Folly", "蒙", "Méng", "The first oracle speaks clean; repeated pestering muddies the spring.", "A cold spring wells at the mountain's foot; refine conduct through resolute practice."),
    (5, _H, _WA, "Waiting (Nourishment)", "需", "Xū", "Wait with wine and bone-deep certainty before crossing the great water.", "Rainclouds gather high in heaven; eat, drink, and rest coiled in readiness."),
    (6, _WA, _H, "Conflict", "訟", "Sòng", "Obstructed sincerity; halt halfway for good fortune, pressing to the bitter end brings loss.", "Heaven and water pull apart; weigh the starting boundary before any contention."),
    (7, _WA, _E, "The Army", "師", "Shī", "Disciplined force requires seasoned command; order without rancor.", "Subterranean water held within earth; gather strength by sheltering the household."),
    (8, _E, _WA, "Holding Together (Union)", "比", "Bǐ", "Inquire of the oracle whether the center is steady and unhurried; latecomers lose the thread.", "Water flows intimately upon earth; seal alliances through warm, unmistakable kinship."),
    (9, _H, _WI, "The Taming Power of the Small", "小畜", "Xiǎo Chù", "Dense clouds from the western border, no rain yet; small restraints shape vast force.", "Wind drives across the sky; polish fine craft while the storm builds pressure."),
    (10, _L, _H, "Treading (Conduct)", "履", "Lǚ", "Stepping on the tiger's tail without being bitten; wakeful poise carries through.", "Heaven above, smiling lake below; know exact rank and move without flinching."),
    (11, _H, _E, "Peace (Pervading)", "泰", "Tài", "Heaven and earth mingle in intercourse; the small departs and the great approaches.", "Sky pours downward into receptive soil; tailor the rhythm of the seasons cleanly."),
    (12, _E, _H, "Standstill (Stagnation)", "否", "Pǐ", "Heaven and earth do not commune; withdraw inner worth rather than court hollow pay.", "Sky rises away from cold ground; fold strength inward until the tide turns."),
    (13, _F, _H, "Fellowship with Men", "同人", "Tóng Rén", "Fellowship in the open wild succeeds; clear purpose crosses the great water.", "Flame rises to meet heaven; align distinct voices without erasing difference."),
    (14, _H, _F, "Possession in Great Measure", "大有", "Dà Yǒu", "Supreme clarity high at noon; wealth held cleanly in sovereign hands.", "Fire blazes at the zenith of heaven; curb harm and amplify what is vital."),
    (15, _M, _E, "Modesty", "謙", "Qiān", "High stone hidden under level earth; emptying what is swollen brings completion.", "A mountain stands concealed inside the earth; weigh excess and feed what is lean."),
    (16, _E, _T, "Enthusiasm", "豫", "Yù", "Thunder breaks from silent ground; entrain movement through music and pulse.", "Lightning bursts out of earth; tune ritual rhythm to ancestral marrow."),
    (17, _T, _L, "Following", "隨", "Suí", "To command, learn first to yield to the current; rest indoors when night falls.", "Thunder sleeps beneath the autumn lake; go inward at dusk for restoration."),
    (18, _WI, _M, "Work on What Has Been Spoiled", "蠱", "Gǔ", "Air stagnant under stone; weigh three days before the cut and three days after.", "Wind stirs at the base of the mountain; air out ancestral rot and renew the vessel."),
    (19, _L, _E, "Approach", "臨", "Lín", "Rising yang swells from the depths; tend fervently now, knowing the eighth month turns.", "Earth banks above the deep lake; teach and shelter with inexhaustible patience."),
    (20, _E, _WI, "Contemplation (View)", "觀", "Guān", "Hands washed before the offering is poured; quiet presence commands the hall.", "Wind sweeps wide over earth; observe the living pattern before laying down law."),
    (21, _T, _F, "Biting Through", "噬嗑", "Shì Kè", "Obstruction between the jaws; bite clean through bone to restore union.", "Thunder and lightning strike together; make boundaries unmistakable and swift."),
    (22, _F, _M, "Grace (Adornment)", "賁", "Bì", "Fire lights the mountain flanks; beauty illuminates form but must not replace bone.", "Lamplight at the foot of stone; clarify daily craft, leave life-or-death cuts unadorned."),
    (23, _E, _M, "Splitting Apart", "剝", "Bō", "Erosion climbs from below; yield to the stripping and secure the bed.", "Mountain resting on worn earth; fortify the foundation instead of fighting winter."),
    (24, _T, _E, "Return (The Turning Point)", "復", "Fù", "Solstice spark stirs underground; friends arrive without blame on the seventh cycle.", "Thunder stirs deep inside winter earth; seal the passes at solstice and nurse the seed."),
    (25, _T, _H, "Innocence (The Unexpected)", "無妄", "Wú Wàng", "Unentangled instinct moves under heaven; ulterior calculation invites misfortune.", "Thunder rolls beneath the sky; nourish every creature according to its true grain."),
    (26, _H, _M, "The Taming Power of the Great", "大畜", "Dà Chù", "Sky banked inside mountain stone; banked charge feeds public action.", "Heaven held within the mountain; store living memory to temper wild force."),
    (27, _T, _M, "The Corners of the Mouth", "頤", "Yí", "Watch what enters the mouth and what leaves the lips; hunger reveals character.", "Thunder beneath still stone; choose clean fuel in speech, salt, and appetite."),
    (28, _WI, _L, "Preponderance of the Great", "大過", "Dà Guò", "The ridgepole sags under rare weight; step boldly without fear of standing alone.", "Lake rises above the trees; stand unshaken even if submerged from view."),
    (29, _WA, _WA, "The Abysmal (Water)", "坎", "Kǎn", "Repeated Gorge; water flows through sheer dark without losing its heart's measure.", "Chasm upon chasm; walk into difficulty with practiced, continuous rhythm."),
    (30, _F, _F, "The Clinging (Fire)", "離", "Lí", "Flame lives by clinging to fuel; tend the docile cow of steady lucidity.", "Double brightness rises; illuminate the four quarters by honoring what feeds the wick."),
    (31, _M, _L, "Influence (Wooing)", "咸", "Xián", "Mutual electric attraction; keep the mountain still inside so the lake may answer.", "A high tarn upon the peak; receive contact through empty, undefended presence."),
    (32, _WI, _T, "Duration", "恆", "Héng", "Endurance through living motion, never brittle stasis; stay rooted in your direction.", "Thunder and wind reinforce each other; stand firm without freezing in place."),
    (33, _M, _H, "Retreat", "遯", "Dùn", "Strategic withdrawal in full strength; step back cleanly while holding the high ground.", "Mountain rises beneath wide sky; keep distance through dignified boundary, never spite."),
    (34, _H, _T, "The Power of the Great", "大壯", "Dà Zhuàng", "Immense charge in motion; true power refuses to ram its horns into the hedge.", "Thunder roars high in heaven; never step outside consecrated measure when strong."),
    (35, _E, _F, "Progress", "晉", "Jìn", "Dawn climbs swiftly over wide ground; three audiences in a single day.", "The sun rises effortless above earth; polish innate brightness free of mire."),
    (36, _F, _E, "Darkening of the Light", "明夷", "Míng Yí", "Sun wounded beneath the horizon; veil your brilliance inside difficult company.", "Light sinks into the earth; guard the inner ember behind an unremarkable face."),
    (37, _F, _WI, "The Family (The Clan)", "家人", "Jiā Rén", "Warm hearth at the center; speech carries weight only when backed by lived habit.", "Wind rises straight from hearth-fire; anchor words in substance and daily rhythm."),
    (38, _L, _F, "Opposition", "睽", "Kuí", "Fire climbs while marsh water sinks; honor polarity in small matters without forcing sameness.", "Flame above, lake below; hold sovereign individuality inside shared company."),
    (39, _M, _WA, "Obstruction", "蹇", "Jiǎn", "Gorge ahead, steep stone behind; halt, turn toward allies, and examine yourself.", "Water perilous atop the mountain; turn obstacle into interior sharpening."),
    (40, _WA, _T, "Deliverance", "解", "Xiè", "Thunderburst loosens the knot; forgive old tension and move swiftly at dawn.", "Rain and thunder break the sultry air; pardon faults and release held pressure."),
    (41, _L, _M, "Decrease", "損", "Sǔn", "Two simple bowls suffice for the sacrifice when offered with naked sincerity.", "Deep lake at the mountain's base; curb anger and distill scattered appetite."),
    (42, _T, _WI, "Increase", "益", "Yì", "Pouring down from above to enrich the root; cross the water and build boldly.", "Wind and thunder amplify each other; imitate what is vital and prune decay at once."),
    (43, _H, _L, "Break-through (Resoluteness)", "夬", "Guài", "Name the rot plainly before the court without taking up the enemy's rage.", "Lake water surges up to heaven; distribute accumulated wealth instead of damming it."),
    (44, _WI, _H, "Coming to Meet", "姤", "Gòu", "One fierce yin enters beneath five yang; respect sudden magnetic encounter.", "Wind blows under the whole sky; send clear word to the four corners."),
    (45, _E, _L, "Gathering Together", "萃", "Cuì", "Approach the temple with concentrated spirit; renew weapons against the unforeseen.", "Lake waters gather above the earth; prepare ritual vessels and guard against breach."),
    (46, _WI, _E, "Pushing Upward", "升", "Shēng", "Wood climbs unseen through dark soil; steady effort meets no resistance.", "Living root rises inside earth; stack small faithful acts into towering stature."),
    (47, _WA, _L, "Oppression (Exhaustion)", "困", "Kùn", "Water drained below the lakebed; words go unheard, only marrow-conduct proves real.", "A dry lakebed; stake your will on what matters when outer comfort runs dry."),
    (48, _WI, _WA, "The Well", "井", "Jǐng", "Towns move, the stone well remains; lower the rope all the way without breaking the pitcher.", "Water drawn up through wood; tend the deep source that feeds the house."),
    (49, _F, _L, "Revolution (Molting)", "革", "Gé", "Pelt changes in season; trust comes on the ripened day when old skin must burn.", "Fire within the lake; reckon the calendar accurately and mark the clean break."),
    (50, _WI, _F, "The Caldron", "鼎", "Dǐng", "Bronze vessel transmutes raw flesh into sacred offering; supreme good fortune.", "Flame fed by aromatic wood; align posture so the spirit settles into the body."),
    (51, _T, _T, "The Arousing (Shock, Thunder)", "震", "Zhèn", "Double thunder startles a hundred miles; the celebrant does not drop the sacrificial spoon.", "Rolling thunder; let sudden shock sharpen reverence and self-command."),
    (52, _M, _M, "Keeping Still, Mountain", "艮", "Gèn", "Rest your back until self-consciousness vanishes; walk the courtyard unseen.", "Joined peaks standing silent; keep thought strictly inside its present seat."),
    (53, _M, _WI, "Development (Gradual Progress)", "漸", "Jiàn", "Wild geese approach the high rock step by step; unhurried rites endure.", "A tree rooted high on stone; transform the room through patient, dignified poise."),
    (54, _L, _T, "The Marrying Maiden", "歸妹", "Guī Mèi", "Entering a bond from desire rather than rank; see the permanent grain past fleeting heat.", "Thunder stirs above the marsh; know what wears thin by reading beginning and end."),
    (55, _F, _T, "Abundance (Fullness)", "豐", "Fēng", "Noon sun at zenith; do not grieve eclipse, shine cleanly while the hour burns.", "Thunder and lightning arrive together; decide clearly and execute without delay."),
    (56, _M, _F, "The Wanderer", "旅", "Lǚ", "Brushfire passes swiftly across stone; travel light, keep clear-eyed guest etiquette.", "Fire moving over the mountain; settle disputes swiftly and never linger in cages."),
    (57, _WI, _WI, "The Gentle (The Penetrating, Wind)", "巽", "Xùn", "Subtle wind enters every seam through quiet repetition; align with clear direction.", "Winds following one upon another; let steady breath penetrate bone before action."),
    (58, _L, _L, "The Joyous, Lake", "兌", "Duì", "Two lakes replenish one another; candid delight grounded in firm spine.", "Joined waters glinting; sharpen wit and warmth in honest companionship."),
    (59, _WA, _WI, "Dispersion (Dissolution)", "渙", "Huàn", "Warm wind melts rigid ice over deep water; gather scattered soul at the altar.", "Breeze blowing across dark water; dissolve hard ego-knots into shared devotion."),
    (60, _L, _WA, "Limitation", "節", "Jié", "Articulate joints give the reed its music; bitter over-restraint cannot be sustained.", "Water held cleanly by lake banks; craft livable measure rather than punitive cages."),
    (61, _L, _WI, "Inner Truth", "中孚", "Zhōng Fú", "Hollow reed at the center; truth reaches even hidden creatures beneath the tide.", "Wind stirs the open lake; deliberate with mercy before sealing any judgment."),
    (62, _M, _T, "Preponderance of the Small", "小過", "Xiǎo Guò", "The singing bird stays low; attend to small exactitudes rather than grand flight.", "Thunder high on the mountain; err toward care, modesty, and grounded precision."),
    (63, _F, _WA, "After Completion", "既濟", "Jì Jì", "Kettle boiling cleanly over flame; every line in place, guard against late slackness.", "Water poised directly over fire; foresee fracture while everything still gleams."),
    (64, _WA, _F, "Before Completion", "未濟", "Wèi Jì", "The young fox nearly across the frozen stream; keep the tail dry at the final step.", "Flame rising above water; sort each element carefully before sealing the work."),
]


def _build_hexagram_table() -> dict[tuple[tuple[int, int, int], tuple[int, int, int]], dict[str, Any]]:
    table: dict[tuple[tuple[int, int, int], tuple[int, int, int]], dict[str, Any]] = {}
    for num, lower, upper, name, zh, py, judgment, image in _KING_WEN_RAW:
        key = (lower, upper)
        if key in table:
            raise AssertionError(f"Duplicate hexagram trigram key {key} at #{num}")
        table[key] = {
            "number": num,
            "name": name,
            "chinese": zh,
            "pinyin": py,
            "upper_trigram": TRIGRAMS[upper],
            "lower_trigram": TRIGRAMS[lower],
            "judgment": judgment,
            "image": image,
        }
    if len(table) != 64 or {v["number"] for v in table.values()} != set(range(1, 65)):
        raise AssertionError("KING_WEN_HEXAGRAMS must contain all 64 hexagrams 1..64")
    return table


KING_WEN_HEXAGRAMS = _build_hexagram_table()


def _yarrow_line_from_nibble(nibble: int) -> int:
    """Map uniform 4-bit integer (0..15) to authentic yarrow-stalk line value.

    - 0       -> 6 (1/16: old yin, moving broken)
    - 1..5    -> 7 (5/16: young yang, solid)
    - 6..12   -> 8 (7/16: young yin, broken)
    - 13..15  -> 9 (3/16: old yang, moving solid)
    """
    slot = nibble & 0x0F
    if slot == 0:
        return 6
    if slot <= 5:
        return 7
    if slot <= 12:
        return 8
    return 9


def _lines_to_hexagram(lines: list[int]) -> dict[str, Any]:
    bits = tuple(1 if v in (7, 9) else 0 for v in lines)
    lower = (bits[0], bits[1], bits[2])
    upper = (bits[3], bits[4], bits[5])
    return dict(KING_WEN_HEXAGRAMS[(lower, upper)])


def cast_iching() -> dict[str, Any]:
    """Cast a 6-line I Ching hexagram bottom-to-top with true 1:5:7:3 yarrow-stalk odds."""
    raw = os.urandom(6)
    lines = [_yarrow_line_from_nibble(b & 0x0F) for b in raw]
    primary = _lines_to_hexagram(lines)
    moving_lines = [idx + 1 for idx, val in enumerate(lines) if val in (6, 9)]

    transformed: dict[str, Any] | None = None
    if moving_lines:
        mutated_lines = [7 if v == 6 else (8 if v == 9 else v) for v in lines]
        transformed = _lines_to_hexagram(mutated_lines)

    return {
        "lines": lines,
        "primary": primary,
        "moving_lines": moving_lines,
        "transformed": transformed,
        "entropy_hex": raw.hex(),
    }


# ===========================================================================
# 3. ELDER FUTHARK — ALL 24 RUNES
# ===========================================================================

# (glyph, name, phoneme, aett, merkstave_capable, keywords, essence)
_RUNES_RAW: list[tuple[str, str, str, str, bool, list[str], str]] = [
    # Freyja's Aett
    ("ᚠ", "Fehu", "f", "Freyja's", True, ["mobile fire", "circulating wealth", "vital livestock"], "Raw generative current meant to move, feed, and kindle rather than sit hoarded."),
    ("ᚢ", "Uruz", "u", "Freyja's", True, ["aurochs horn", "somatic vigor", "untamed form"], "Primal bodily stamina, wild endurance, and shaping raw life-force."),
    ("ᚦ", "Thurisaz", "th", "Freyja's", True, ["thorn-edge", "directed voltage", "reactive ward"], "Sharp protective threshold and concentrated strike clearing deadwood."),
    ("ᚨ", "Ansuz", "a", "Freyja's", True, ["inspired breath", "ancestral voice", "numinous signal"], "Ecstatic speech, clear omen-reading, and wind passing through an open throat."),
    ("ᚱ", "Raidho", "r", "Freyja's", True, ["wheel-rhythm", "rightful road", "entrainment"], "Aligned cadence where body, mount, and hour move as a single beat."),
    ("ᚲ", "Kenaz", "k", "Freyja's", True, ["pine-torch", "workshop craft", "ulcerous lucidity"], "Controlled forge-fire illuminating intimate skill and hidden hunger."),
    ("ᚷ", "Gebo", "g", "Freyja's", False, ["sacred exchange", "crossed spears", "sovereign pact"], "Gift demanding equal presence — union between equals where neither dissolves."),
    ("ᚹ", "Wunjo", "w", "Freyja's", True, ["clan banner", "aligned delight", "frictionless harmony"], "Earned somatic consonance when work, desire, and belonging lock into tune."),
    # Heimdall's Aett
    ("ᚺ", "Hagalaz", "h", "Heimdall's", False, ["hailstone", "crystalline disruption", "seed-pattern"], "Involuntary weather shattering brittle glass to water deeper soil."),
    ("ᚾ", "Nauthiz", "n", "Heimdall's", True, ["need-fire", "bow-drill friction", "exact constraint"], "Necessity rubbed hard against bone until clean flame catches."),
    ("ᛁ", "Isa", "i", "Heimdall's", False, ["black ice", "zero-motion axis", "crystalline focus"], "Uncompromising stillness, contraction to core spine, waiting out thaw."),
    ("ᛃ", "Jera", "j / y", "Heimdall's", False, ["turning harvest", "ripened cycle", "patient orbit"], "Fruit arriving strictly in its earned season — neither forced nor denied."),
    ("ᛇ", "Eihwaz", "ei / ï", "Heimdall's", False, ["yew spine", "world-axis", "death-and-endurance"], "Deep root and supple bow bridging subterranean dark with canopy."),
    ("ᛈ", "Perthro", "p", "Heimdall's", True, ["dice-cup", "womb-well", "hidden wyrd"], "Unrevealed lot tumbling inside the dark cup; play what lands cleanly."),
    ("ᛉ", "Algiz", "z / R", "Heimdall's", True, ["elk-sedge", "valkyrie ward", "awake nerve"], "Sanctuary with sharp edges — instinctive boundary sensing approach at once."),
    ("ᛊ", "Sowilo", "s", "Heimdall's", False, ["sun-wheel", "lightning guidance", "unbroken aim"], "Solar bolt cutting mist into unmistakable vector and warm vitality."),
    # Tyr's Aett
    ("ᛏ", "Tiwaz", "t", "Tyr's", True, ["pole-star", "pledged hand", "clean justice"], "Oath-keeping clarity willing to pay the real price at the hinge."),
    ("ᛒ", "Berkano", "b", "Tyr's", True, ["birch-bud", "sheltered germination", "quiet tending"], "Dark-barked containment nursing tender new growth away from cold glare."),
    ("ᛖ", "Ehwaz", "e", "Tyr's", True, ["twin horses", "trusted partnership", "fluid transit"], "Wordless trust between rider and pulse carrying across thresholds."),
    ("ᛗ", "Mannaz", "m", "Tyr's", True, ["human mirror", "reflective mind", "mortal witness"], "Clear self-observation woven inside living relationship and memory."),
    ("ᛚ", "Laguz", "l", "Tyr's", True, ["dark tide", "subconscious current", "intuitive immersion"], "Tidal depth moving beneath rational thought; swim rather than brace."),
    ("ᛜ", "Ingwaz", "ng", "Tyr's", False, ["sealed seed", "gestating heat", "coiled release"], "Contained internal pressure ripening out of sight before sudden birth."),
    ("ᛞ", "Dagaz", "d", "Tyr's", False, ["daybreak", "lemniscate hinge", "instantaneous flip"], "Twilight seam where night turns inside-out into sudden lucidity."),
    ("ᛟ", "Othala", "o", "Tyr's", True, ["ancestral enclosure", "claimed room", "sovereign ground"], "What belongs inside your walls by blood, craft, and deliberate tending."),
]

ELDER_FUTHARK: list[dict[str, Any]] = [
    {
        "glyph": glyph,
        "name": name,
        "phoneme": phoneme,
        "aett": aett,
        "merkstave_capable": merk_capable,
        "keywords": list(kw),
        "essence": essence,
    }
    for glyph, name, phoneme, aett, merk_capable, kw, essence in _RUNES_RAW
]

if len(ELDER_FUTHARK) != 24 or len({r["name"] for r in ELDER_FUTHARK}) != 24:
    raise AssertionError("ELDER_FUTHARK must contain all 24 unique runes")


def cast_runes(count: int = 1) -> list[dict[str, Any]]:
    """Draw `count` Elder Futhark runes without replacement with cryptographic orientation."""
    if count < 0 or count > len(ELDER_FUTHARK):
        raise ValueError(f"count must be between 0 and {len(ELDER_FUTHARK)}, got {count}")
    pool = list(range(len(ELDER_FUTHARK)))
    results: list[dict[str, Any]] = []
    for i in range(count):
        pick = i + secrets.randbelow(len(pool) - i)
        pool[i], pool[pick] = pool[pick], pool[i]
        base = ELDER_FUTHARK[pool[i]]
        if base["merkstave_capable"]:
            bit = os.urandom(1)[0] & 1
            orientation = "merkstave" if bit else "upright"
        else:
            orientation = "upright"
        results.append(
            {
                "name": base["name"],
                "glyph": base["glyph"],
                "phoneme": base["phoneme"],
                "aett": base["aett"],
                "orientation": orientation,
                "keywords": list(base["keywords"]),
                "essence": base["essence"],
            }
        )
    return results


# ===========================================================================
# 4. ASTRONOMICAL EPHEMERIS & CHALDEAN PLANETARY HOURS
# ===========================================================================

ZODIAC_SIGNS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

# Chaldean descending orbital order
CHALDEAN_ORDER: list[tuple[str, str, str]] = [
    ("Saturn", "♄", "lead, bone-structure, threshold containment, long endurance"),
    ("Jupiter", "♃", "tin, sovereign expansion, generous synthesis, auspicious governance"),
    ("Mars", "♂", "iron, clean severance, heat in the blood, decisive ignition"),
    ("Sun", "☉", "gold, lucid center, vital radiance, unveiled authority"),
    ("Venus", "♀", "copper, embodied magnetism, erotic consonance, aesthetic craft"),
    ("Mercury", "☿", "quicksilver, liminal inscription, swift signal, hermetic wit"),
    ("Moon", "☽", "silver, tidal soma, nocturnal mirror, dream-current"),
]

# Python date.weekday(): Monday=0 .. Sunday=6 -> index in CHALDEAN_ORDER
_WEEKDAY_DAY_RULER_IDX: dict[int, int] = {
    0: 6,  # Monday    -> Moon
    1: 2,  # Tuesday   -> Mars
    2: 5,  # Wednesday -> Mercury
    3: 1,  # Thursday  -> Jupiter
    4: 4,  # Friday    -> Venus
    5: 0,  # Saturday  -> Saturn
    6: 3,  # Sunday    -> Sun
}


def _julian_day(dt_utc: datetime) -> float:
    y = dt_utc.year
    m = dt_utc.month
    d = dt_utc.day + (
        dt_utc.hour
        + dt_utc.minute / 60.0
        + (dt_utc.second + dt_utc.microsecond / 1e6) / 3600.0
    ) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + (a // 4)
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5


def _solar_longitude_deg(jd: float) -> float:
    """Apparent geocentric solar ecliptic longitude (Meeus Ch. 25, ~0.01 deg accuracy)."""
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + 36000.76983 * t + 0.0003032 * t * t) % 360.0
    m = (357.52911 + 35999.05029 * t - 0.0001537 * t * t) % 360.0
    m_rad = math.radians(m)
    c = (
        (1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m_rad)
        + (0.019993 - 0.000101 * t) * math.sin(2.0 * m_rad)
        + 0.000289 * math.sin(3.0 * m_rad)
    )
    true_lon = l0 + c
    omega = 125.04 - 1934.136 * t
    apparent_lon = true_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    return apparent_lon % 360.0


def _lunar_longitude_deg(jd: float) -> float:
    """Geocentric lunar ecliptic longitude (Meeus Ch. 47 principal periodic terms)."""
    t = (jd - 2451545.0) / 36525.0
    lp = (218.3164477 + 481267.88123421 * t - 0.0015786 * t * t) % 360.0
    d = (297.8501921 + 445267.1114034 * t - 0.0018819 * t * t) % 360.0
    m = (357.5291092 + 35999.0502909 * t - 0.0001536 * t * t) % 360.0
    mp = (134.9633964 + 477198.8675055 * t + 0.0087414 * t * t) % 360.0
    f = (93.2720950 + 483202.0175233 * t - 0.0036539 * t * t) % 360.0

    dr = math.radians(d)
    mr = math.radians(m)
    mpr = math.radians(mp)
    fr = math.radians(f)

    lon = (
        lp
        + 6.288774 * math.sin(mpr)
        + 1.274027 * math.sin(2.0 * dr - mpr)
        + 0.658314 * math.sin(2.0 * dr)
        + 0.213618 * math.sin(2.0 * mpr)
        - 0.185116 * math.sin(mr)
        - 0.114332 * math.sin(2.0 * fr)
        + 0.058793 * math.sin(2.0 * dr - 2.0 * mpr)
        + 0.057066 * math.sin(2.0 * dr - mr - mpr)
        + 0.053322 * math.sin(2.0 * dr + mpr)
        + 0.045758 * math.sin(2.0 * dr - mr)
        - 0.040923 * math.sin(mr - mpr)
        - 0.034720 * math.sin(dr)
        - 0.030383 * math.sin(mr + mpr)
        + 0.015327 * math.sin(2.0 * dr - 2.0 * fr)
    )
    return lon % 360.0


def _phase_name_and_glyph(phase_angle: float) -> tuple[str, str]:
    a = phase_angle % 360.0
    if a < 10.0 or a >= 350.0:
        return ("New Moon", "🌑")
    if a < 80.0:
        return ("Waxing Crescent", "🌒")
    if a < 100.0:
        return ("First Quarter", "🌓")
    if a < 170.0:
        return ("Waxing Gibbous", "🌔")
    if a < 190.0:
        return ("Full Moon", "🌕")
    if a < 260.0:
        return ("Waning Gibbous", "🌖")
    if a < 280.0:
        return ("Last Quarter", "🌗")
    return ("Waning Crescent", "🌘")


def _sunrise_sunset_local(d: date, lat: float, lon: float, tz: ZoneInfo | timezone) -> tuple[datetime, datetime]:
    """NOAA solar horizon algorithm (zenith 90.833 deg) returning aware local datetimes."""
    noon_utc = datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)
    jd_noon = _julian_day(noon_utc)
    t = (jd_noon - 2451545.0) / 36525.0

    geom_mean_lon = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360.0
    geom_mean_anom = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    eccent = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)

    m_rad = math.radians(geom_mean_anom)
    sun_eq_ctr = (
        math.sin(m_rad) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2.0 * m_rad) * (0.019993 - 0.000101 * t)
        + math.sin(3.0 * m_rad) * 0.000289
    )
    sun_true_lon = geom_mean_lon + sun_eq_ctr
    omega = 125.04 - 1934.136 * t
    sun_app_lon = sun_true_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    mean_obliq = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    obliq_corr = mean_obliq + 0.00256 * math.cos(math.radians(omega))

    declin_rad = math.asin(math.sin(math.radians(obliq_corr)) * math.sin(math.radians(sun_app_lon)))

    y_var = math.tan(math.radians(obliq_corr / 2.0)) ** 2
    l0_rad = math.radians(geom_mean_lon)
    eq_time_min = 4.0 * math.degrees(
        y_var * math.sin(2.0 * l0_rad)
        - 2.0 * eccent * math.sin(m_rad)
        + 4.0 * eccent * y_var * math.sin(m_rad) * math.cos(2.0 * l0_rad)
        - 0.5 * y_var * y_var * math.sin(4.0 * l0_rad)
        - 1.25 * eccent * eccent * math.sin(2.0 * m_rad)
    )

    lat_rad = math.radians(lat)
    zenith_rad = math.radians(90.833)
    cos_ha = (math.cos(zenith_rad) / (math.cos(lat_rad) * math.cos(declin_rad))) - (
        math.tan(lat_rad) * math.tan(declin_rad)
    )
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha_deg = math.degrees(math.acos(cos_ha))

    solar_noon_utc_min = 720.0 - 4.0 * lon - eq_time_min
    sunrise_utc_min = solar_noon_utc_min - 4.0 * ha_deg
    sunset_utc_min = solar_noon_utc_min + 4.0 * ha_deg

    day_start_utc = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    sunrise_dt = (day_start_utc + timedelta(minutes=sunrise_utc_min)).astimezone(tz)
    sunset_dt = (day_start_utc + timedelta(minutes=sunset_utc_min)).astimezone(tz)
    return sunrise_dt, sunset_dt


def celestial_state(
    dt: datetime | None = None,
    lat: float = LATITUDE,
    lon: float = LONGITUDE,
) -> dict[str, Any]:
    """Compute local lunar phase, tropical zodiacs, solar horizon & Chaldean planetary hours."""
    tz = _local_tz()
    if dt is None:
        now_local = datetime.now(tz)
    elif dt.tzinfo is None:
        now_local = dt.replace(tzinfo=tz)
    else:
        now_local = dt.astimezone(tz)

    now_utc = now_local.astimezone(timezone.utc)
    jd = _julian_day(now_utc)

    sun_lon = _solar_longitude_deg(jd)
    moon_lon = _lunar_longitude_deg(jd)
    phase_angle = (moon_lon - sun_lon) % 360.0
    illum_pct = round(((1.0 - math.cos(math.radians(phase_angle))) / 2.0) * 100.0, 1)
    age_days = round((phase_angle / 360.0) * SYNODIC_MONTH_DAYS, 2)
    phase_name, moon_glyph = _phase_name_and_glyph(phase_angle)

    sun_sign = ZODIAC_SIGNS[int(sun_lon // 30.0) % 12]
    moon_sign = ZODIAC_SIGNS[int(moon_lon // 30.0) % 12]

    civil_date = now_local.date()
    sunrise_today, sunset_today = _sunrise_sunset_local(civil_date, lat, lon, tz)
    is_daylight = sunrise_today <= now_local < sunset_today

    # Chaldean Planetary Day starts at sunrise (before sunrise belongs to previous planetary day)
    if is_daylight:
        planetary_date = civil_date
        span_sec = max(1.0, (sunset_today - sunrise_today).total_seconds())
        elapsed_sec = max(0.0, (now_local - sunrise_today).total_seconds())
        within_half = min(11, int((elapsed_sec / span_sec) * 12.0))
        chaldean_offset = within_half
        hour_number = within_half + 1
        diurnal_tag = "diurnal"
    elif now_local >= sunset_today:
        planetary_date = civil_date
        sunrise_next, _ = _sunrise_sunset_local(civil_date + timedelta(days=1), lat, lon, tz)
        span_sec = max(1.0, (sunrise_next - sunset_today).total_seconds())
        elapsed_sec = max(0.0, (now_local - sunset_today).total_seconds())
        within_half = min(11, int((elapsed_sec / span_sec) * 12.0))
        chaldean_offset = 12 + within_half
        hour_number = within_half + 1
        diurnal_tag = "nocturnal"
    else:
        prev_date = civil_date - timedelta(days=1)
        planetary_date = prev_date
        _, sunset_prev = _sunrise_sunset_local(prev_date, lat, lon, tz)
        span_sec = max(1.0, (sunrise_today - sunset_prev).total_seconds())
        elapsed_sec = max(0.0, (now_local - sunset_prev).total_seconds())
        within_half = min(11, int((elapsed_sec / span_sec) * 12.0))
        chaldean_offset = 12 + within_half
        hour_number = within_half + 1
        diurnal_tag = "nocturnal"

    day_idx = _WEEKDAY_DAY_RULER_IDX[planetary_date.weekday()]
    hour_idx = (day_idx + chaldean_offset) % 7
    day_ruler, day_glyph, _ = CHALDEAN_ORDER[day_idx]
    hour_ruler, hour_glyph, corr_domain = CHALDEAN_ORDER[hour_idx]

    return {
        "timestamp_iso": now_local.isoformat(timespec="seconds"),
        "moon": {
            "phase_name": phase_name,
            "illumination_pct": illum_pct,
            "age_days": age_days,
            "phase_angle": round(phase_angle, 2),
            "zodiac_sign": moon_sign,
            "glyph": moon_glyph,
        },
        "sun": {
            "zodiac_sign": sun_sign,
            "is_daylight": is_daylight,
            "sunrise": sunrise_today.strftime("%H:%M"),
            "sunset": sunset_today.strftime("%H:%M"),
        },
        "planetary": {
            "day_ruler": day_ruler,
            "day_glyph": day_glyph,
            "hour_ruler": hour_ruler,
            "hour_glyph": hour_glyph,
            "hour_number": hour_number,
            "correspondence": f"{diurnal_tag.capitalize()} hour {hour_number} ({hour_ruler} {hour_glyph}): {corr_domain}",
        },
    }


# ===========================================================================
# 5. SPREAD DISPATCHER
# ===========================================================================

TRINITY_POSITIONS = ("Root", "Crucible", "Vector")
VALID_SPREAD_MODES = ("daily", "trinity", "card", "iching", "rune")


def cast_spread(mode: str = "daily") -> dict[str, Any]:
    """Cast hardware-entropy divination spread for `'daily'|'trinity'|'card'|'iching'|'rune'`."""
    norm_mode = (mode or "daily").strip().lower()
    if norm_mode not in VALID_SPREAD_MODES:
        raise ValueError(f"Unsupported spread mode {mode!r}; expected one of {VALID_SPREAD_MODES}")

    tz = _local_tz()
    now_local = datetime.now(tz)
    seal_hex = os.urandom(8).hex()
    celestial = celestial_state(now_local)

    cards: list[dict[str, Any]] = []
    iching: dict[str, Any] | None = None
    runes: list[dict[str, Any]] = []

    if norm_mode == "daily":
        cards = draw_thoth(1)
        iching = cast_iching()
        runes = cast_runes(1)
    elif norm_mode == "trinity":
        cards = draw_thoth(3)
        for card, pos in zip(cards, TRINITY_POSITIONS):
            card["position"] = pos
    elif norm_mode == "card":
        cards = draw_thoth(1)
    elif norm_mode == "iching":
        iching = cast_iching()
    elif norm_mode == "rune":
        runes = cast_runes(1)

    return {
        "mode": norm_mode,
        "cast_at": now_local.isoformat(timespec="seconds"),
        "entropy_hex": seal_hex,
        "cards": cards,
        "iching": iching,
        "runes": runes,
        "celestial": celestial,
    }
