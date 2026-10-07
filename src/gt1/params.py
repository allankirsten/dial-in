"""Parameter map for the BOSS GT-1.

The address map belongs to Roland and is never shipped with this project: it is read from the
BOSS TONE STUDIO for GT-1 app the user already has installed, then cached on this machine only.
"""
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

APP_CANDIDATES = [
    "/Applications/BOSS_TONE_STUDIO_for_GT1.app",
    "/Applications/BOSS/BOSS_TONE_STUDIO_for_GT1.app",
    os.path.expanduser("~/Applications/BOSS_TONE_STUDIO_for_GT1.app"),
]
MAP_IN_APP = "Contents/Resources/_assets/data/addressmap_gt.json"
CACHE_DIR = Path.home() / "Library" / "Application Support" / "Dial In"
_OLD_CACHE_DIR = Path.home() / "Library" / "Application Support" / "GT-1 Conversational"  # name before 0.2.0
if _OLD_CACHE_DIR.is_dir() and not CACHE_DIR.exists():
    try:
        _OLD_CACHE_DIR.rename(CACHE_DIR)  # carry patch backups and the cached map over to the new name
    except OSError:
        pass

EDIT_BUFFER = [0x60, 0x00, 0x00, 0x00]
PATCH_SIZE = 0x10 * 128 + 0x7F  # 2175 bytes, 60 00 00 00 .. 60 00 10 7E
USER_SLOTS = 99

# Type lists, in value order (GT-1 Parameter Guide).
TYPES = {
    "OD_DS": ["MID BOOST", "CLEAN BOOST", "TREBLE BOOST", "CRUNCH", "NATURAL OD", "WARM OD", "FAT DS",
              "LEAD DS", "METAL DS", "OCT FUZZ", "A-DIST", "BLUES OD", "OD-1", "T-SCREAM", "TURBO OD",
              "DISTORTION", "RAT", "GUV DS", "DST+", "METAL ZONE", "60S FUZZ", "MUFF FUZZ"],
    "PREAMP": ["NATURAL CLEAN", "FULL RANGE", "COMBO CRUNCH", "STACK CRUNCH", "HiGAIN STACK",
               "POWER DRIVE", "EXTREME LEAD", "CORE METAL", "JC-120", "CLEAN TWIN", "PRO CRUNCH", "TWEED",
               "DELUXE CRUNCH", "VO DRIVE", "VO LEAD", "MATCH DRIVE", "BG LEAD", "BG DRIVE", "MS1959 I",
               "MS1959 I+II", "R-FIER VINTAGE", "R-FIER MODERN", "T-AMP LEAD", "SLDN", "5150 DRIVE",
               "BGNR UB METAL", "ORNG ROCK"],
    "FX": ["COMPRESSOR", "LIMITER", "T.WAH", "GRAPHIC EQ", "PARAMETRIC EQ", "TONE MODIFY", "GUITAR SIM",
           "AC.GUITAR SIM", "SLOW GEAR", "OCTAVE", "PITCH SHIFTER", "HARMONIST", "OVERTONE", "FEEDBACKER",
           "AC.PROCESSOR", "PHASER", "FLANGER", "TREMOLO", "ROTARY", "UNI-V", "VIBRATO", "CHORUS", "SUB DELAY"],
    "COMP": ["BOSS COMP", "HI-BAND", "LIGHT", "D-COMP", "ORANGE", "FAT", "MILD", "STEREO COMP"],
    "DELAY": ["STANDARD", "PAN", "REVERSE", "ANALOG", "TAPE", "MODULATE", "TERA ECHO"],
    "REVERB": ["AMBIENCE", "ROOM", "HALL 1", "HALL 2", "PLATE", "SPRING", "MODULATE"],
}
TYPE_PARAMS = {
    "OD/DS: TYPE": "OD_DS", "PREAMP A: TYPE": "PREAMP", "PREAMP B: TYPE": "PREAMP",
    "COMP: TYPE": "COMP", "FX1: FX TYPE": "FX", "FX2: FX TYPE": "FX", "DELAY: TYPE": "DELAY", "REVERB: TYPE": "REVERB",
}

# Known value ranges (GT-1 Parameter Guide). Anything else is limited to 0-127.
RANGES = {
    "OD/DS: DRIVE": (0, 120), "PREAMP A: GAIN": (0, 120), "PREAMP B: GAIN": (0, 120),
    "DELAY: DELAY TIME": (1, 2000), "DELAY: EFFECT LEVEL": (0, 120),
}
for _p in ("PREAMP A", "PREAMP B"):
    for _k in ("BASS", "MIDDLE", "TREBLE", "PRESENCE", "LEVEL"):
        RANGES[f"{_p}: {_k}"] = (0, 100)
for _k in ("TONE", "BOTTOM", "EFFECT LEVEL", "DIRECT MIX"):
    RANGES[f"OD/DS: {_k}"] = (0, 100)
for _k in ("THRESHOLD", "RELEASE"):
    RANGES[f"NS1: {_k}"] = (0, 100)

# Parameters that make the patch louder. Raised at most VOLUME_STEP per call unless the user asks for more.
VOLUME_PARAMS = {"PREAMP A: LEVEL", "PREAMP B: LEVEL", "PATCH LEVEL", "OD/DS: EFFECT LEVEL", "COMP: LEVEL",
                 "FOOT VOLUME: LEVEL"}
VOLUME_STEP = 15
# Hard ceiling per call even when the player asks for much louder. Text Claude reads on the web
# (or anywhere else) could try to talk it into a big jump; this keeps that from reaching the ears.
VOLUME_BIG_STEP = 30

# Human-readable blocks for summaries: (label, on/off parameter, type parameter, key parameters)
BLOCKS = [
    ("Compressor", "COMP: ON/OFF", "COMP: TYPE", ["COMP: SUSTAIN", "COMP: LEVEL"]),
    ("Drive (OD/DS)", "OD/DS: ON/OFF", "OD/DS: TYPE", ["OD/DS: DRIVE", "OD/DS: TONE", "OD/DS: BOTTOM", "OD/DS: EFFECT LEVEL"]),
    ("Amp (Preamp A)", "PREAMP A: ON/OFF", "PREAMP A: TYPE",
     ["PREAMP A: GAIN", "PREAMP A: BASS", "PREAMP A: MIDDLE", "PREAMP A: TREBLE", "PREAMP A: PRESENCE", "PREAMP A: LEVEL"]),
    ("Noise suppressor", "NS1: ON/OFF", None, ["NS1: THRESHOLD", "NS1: RELEASE"]),
    ("FX1", "FX1: ON/OFF", "FX1: FX TYPE", []),
    ("FX2", "FX2: ON/OFF", "FX2: FX TYPE", []),
    ("Chorus", "CHORUS: ON/OFF", None, ["CHORUS: RATE", "CHORUS: DEPTH", "CHORUS: EFFECT LEVEL"]),
    ("Delay", "DELAY: ON/OFF", "DELAY: TYPE", ["DELAY: DELAY TIME", "DELAY: F.BACK", "DELAY: EFFECT LEVEL"]),
    ("Reverb", "REVERB: ON/OFF", "REVERB: TYPE", ["REVERB: TIME", "REVERB: EFFECT LEVEL"]),
]


class MapNotFound(RuntimeError):
    pass


def to_int(addr):
    n = 0
    for b in addr:
        n = (n << 7) | b
    return n


def to_addr(n):
    return [(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F]


def _parse(s):
    return [int(x, 16) for x in s.split(",")]


@dataclass(frozen=True)
class Param:
    name: str
    offset: int  # bytes from the start of the patch
    size: int
    address: tuple  # absolute address in the edit buffer


def find_map():
    cached = CACHE_DIR / "addressmap_gt.json"
    for app in APP_CANDIDATES:
        src = Path(app) / MAP_IN_APP
        if src.exists():
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if not cached.exists() or cached.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, cached)
            return cached
    if cached.exists():
        return cached
    raise MapNotFound(
        "BOSS TONE STUDIO for GT-1 is not installed. Install it once from boss.info (GT-1 > Downloads); "
        "it only needs to be installed, never open.")


class ParamMap:
    def __init__(self):
        raw = json.load(open(find_map()))
        base = to_int(EDIT_BUFFER)
        self.raw = raw
        self.patch = {}
        for p in raw["temporary"]:
            if "name" in p and "size" in p:
                a = _parse(p["address"])
                self.patch[p["name"]] = Param(p["name"], to_int(a) - base, to_int(_parse(p["size"])), tuple(a))
        self.system = {p["name"]: (tuple(_parse(p["address"])), to_int(_parse(p["size"])))
                       for p in raw["system"] if "name" in p and "size" in p}

    def decode(self, raw_patch, name):
        p = self.patch[name]
        chunk = raw_patch[p.offset:p.offset + p.size]
        return sum(b << (7 * (p.size - 1 - k)) for k, b in enumerate(chunk))

    def decode_all(self, raw_patch):
        return {n: self.decode(raw_patch, n) for n in self.patch}

    def encode(self, name, value):
        p = self.patch[name]
        return list(p.address), [(value >> (7 * (p.size - 1 - k))) & 0x7F for k in range(p.size)]

    def resolve(self, name):
        """Exact name, or a unique case-insensitive match. Raises with suggestions."""
        if name in self.patch:
            return name
        low = name.strip().lower()
        exact = [n for n in self.patch if n.lower() == low]
        if exact:
            return exact[0]
        words = low.replace(":", " ").split()
        hits = [n for n in self.patch if all(w in n.lower() for w in words)]
        if len(hits) == 1:
            return hits[0]
        hint = ", ".join(hits[:8]) if hits else "use describe_parameters to see valid names"
        raise KeyError(f"Unknown or ambiguous parameter '{name}'. Did you mean: {hint}")

    def value_for(self, name, value):
        """Accepts type names ('VO DRIVE'), 'on'/'off', or numbers. Validates range."""
        table = TYPE_PARAMS.get(name)
        if isinstance(value, str):
            v = value.strip()
            if table:
                options = TYPES[table]
                match = [i for i, t in enumerate(options) if t.lower() == v.lower()]
                if not match:
                    raise ValueError(f"'{value}' is not a valid type for {name}. Options: {', '.join(options)}")
                return match[0]
            if v.lower() in ("on", "off"):
                return 1 if v.lower() == "on" else 0
            value = float(v)
        value = int(round(value))
        lo, hi = RANGES.get(name, (0, 128 ** self.patch[name].size - 1))
        if table:
            lo, hi = 0, len(TYPES[table]) - 1
        if not lo <= value <= hi:
            raise ValueError(f"{name} must be between {lo} and {hi} (got {value})")
        return value

    def label(self, name, value):
        table = TYPE_PARAMS.get(name)
        if table and 0 <= value < len(TYPES[table]):
            return TYPES[table][value]
        if name.endswith("ON/OFF"):
            return "on" if value else "off"
        return value
