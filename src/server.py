"""GT-1 Conversational: an MCP server that lets Claude shape BOSS GT-1 tones by conversation."""
import functools
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from gt1 import audio  # noqa: E402
from gt1.device import GT1, NotConnected, tone_studio_running  # noqa: E402
from gt1.params import (BLOCKS, CACHE_DIR, TYPE_PARAMS, TYPES, USER_SLOTS, VOLUME_PARAMS,  # noqa: E402
                        VOLUME_STEP, MapNotFound, ParamMap)

INSTRUCTIONS = """You control a BOSS GT-1 guitar multi-effects pedal connected over USB.
How to work with the player:
- Start with gt1_status. If Tone Studio is open, tell the player to close it (it reloads the patch and shows stale data).
- To build a tone for a song: research the gear used on the original recording, translate it to GT-1 models, apply with adjust_tone, then ask the player to play. Name the patch (rename_patch) so the change is visible on the pedal display.
- Make changes the player can clearly hear. If they say "nothing changed", first try one obvious change (for example gain to 100) to rule out a connection problem, and ask them to check the cables: a loose cable caused false alarms before.
- Vague feedback ("sounds weird", "needs more drive", "muddy") is normal: translate it into a small, explained change. Keep changes the player already approved; change only what they asked about.
- Volume matters (neighbors, ears). Level parameters rise at most 15 per call. When in doubt, use listen or match_volume instead of guessing.
- Nothing is saved until save_patch. Always tell the player when work is unsaved. Never overwrite a slot without showing what is in it and getting a yes.
- Keep replies short: what changed, from what to what, and what to try next.
"""

mcp = FastMCP("gt1-conversational", instructions=INSTRUCTIONS)
dev = GT1()
metronome = audio.Metronome()
_map = None
_history = []          # [(description, raw buffer before the change)]
_names = {}            # slot -> name cache
_last_listen = None


def pmap():
    global _map
    if _map is None:
        _map = ParamMap()
    return _map


def friendly(fn):
    """Turn known failures into plain-language messages instead of stack traces."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (NotConnected, MapNotFound, audio.NoAudio) as e:
            dev.close()
            return {"ok": False, "problem": str(e)}
        except (KeyError, ValueError) as e:
            return {"ok": False, "problem": e.args[0] if e.args else str(e)}
    return wrapper


def _warnings():
    w = []
    if tone_studio_running():
        w.append("BOSS TONE STUDIO is open. Close it: it reloads the patch when it connects and its patch "
                 "list does not update when we save from here.")
    return w


def _unsaved(slot=None):
    slot = slot or dev.current_slot()
    return dev.read_patch() != dev.read_patch(slot), slot


def _summary(values):
    m = pmap()
    out = {}
    for label, sw, typ, keys in BLOCKS:
        on = values.get(sw)
        entry = {"on": bool(on)}
        if typ:
            entry["type"] = m.label(typ, values[typ])
        for k in keys:
            entry[k.split(": ", 1)[1].lower()] = values[k]
        if typ and typ.startswith("FX") and on:
            fx = entry["type"]
            prefix = f"{typ.split(':')[0]}: {fx}:"
            entry.update({k.split(": ")[-1].lower(): v for k, v in values.items() if k.startswith(prefix)})
        out[label] = entry
    return out


# ---------------------------------------------------------------------------- status & reading
@mcp.tool()
@friendly
def gt1_status() -> dict:
    """Check the connection and what is loaded right now: current slot, patch name, unsaved changes,
    and anything that could get in the way (like Tone Studio being open). Call this first."""
    dev.connect()
    unsaved, slot = _unsaved()
    return {"ok": True, "connected": True, "slot": f"U{slot:02d}", "patch_name": dev.patch_name(),
            "unsaved_changes": unsaved, "undo_steps_available": len(_history),
            "metronome": f"{metronome.bpm} BPM" if metronome.bpm else "off", "warnings": _warnings()}


@mcp.tool()
@friendly
def get_current_tone() -> dict:
    """Readable summary of the patch currently loaded: every block, on/off, model and main knobs."""
    raw = dev.read_patch()
    values = pmap().decode_all(raw)
    return {"ok": True, "patch_name": dev.patch_name(), "blocks": _summary(values),
            "patch_level": values.get("PATCH LEVEL")}


@mcp.tool()
@friendly
def describe_parameters(block: str) -> dict:
    """List exact parameter names and current values for a block, for example 'PREAMP A', 'OD/DS',
    'DELAY', 'FX1: UNI-V', 'CHORUS', 'NS1'. Also lists the models available for type parameters."""
    raw = dev.read_patch()
    m = pmap()
    key = block.strip().lower()
    names = [n for n in m.patch if n.lower().startswith(key)]
    if not names:
        raise KeyError(f"No parameters start with '{block}'. Examples: PREAMP A, OD/DS, DELAY, REVERB, FX1, CHORUS, NS1")
    params = {n: m.label(n, m.decode(raw, n)) for n in names[:80]}
    models = {n: TYPES[t] for n, t in TYPE_PARAMS.items() if n in names}
    return {"ok": True, "parameters": params, "available_models": models,
            "truncated": len(names) > 80}


# ---------------------------------------------------------------------------- changing the tone
@mcp.tool()
@friendly
def adjust_tone(changes: dict, allow_big_volume_jump: bool = False) -> dict:
    """Change parameters of the loaded patch live. `changes` maps parameter name to value, e.g.
    {"PREAMP A: TYPE": "VO DRIVE", "PREAMP A: GAIN": 60, "CHORUS: ON/OFF": "off"}.
    Type parameters accept model names. Level parameters rise at most 15 per call unless
    allow_big_volume_jump is true (only when the player explicitly asks for much louder).
    Changes are heard immediately but are not saved. Returns before/after for each parameter."""
    m = pmap()
    before_raw = dev.read_patch()
    before = m.decode_all(before_raw)
    plan, notes = {}, []
    for name, value in changes.items():
        n = m.resolve(name)
        v = m.value_for(n, value)
        if n in VOLUME_PARAMS and not allow_big_volume_jump and v - before[n] > VOLUME_STEP:
            notes.append(f"{n}: asked {v}, raised to {before[n] + VOLUME_STEP} (max +{VOLUME_STEP} per step to protect ears)")
            v = before[n] + VOLUME_STEP
        plan[n] = v
    # type changes first, they take the pedal longer to process
    for n in sorted(plan, key=lambda k: 0 if k in TYPE_PARAMS else 1):
        addr, data = m.encode(n, plan[n])
        dev.write(addr, data)
        time.sleep(0.25 if n.endswith("TYPE") else 0.03)
    after = m.decode_all(dev.read_patch())
    _history.append((", ".join(plan), before_raw))
    result = {n: {"before": m.label(n, before[n]), "after": m.label(n, after[n])} for n in plan}
    failed = [n for n in plan if after[n] != plan[n]]
    return {"ok": not failed, "changed": result, "not_applied": failed, "notes": notes,
            "saved": False, "reminder": "Heard live, not saved yet."}


@mcp.tool()
@friendly
def rename_patch(name: str) -> dict:
    """Rename the loaded patch (max 16 characters). The name shows on the pedal display, which confirms
    the change reached the GT-1."""
    m = pmap()
    before_raw = dev.read_patch()
    text = name[:16].ljust(16)
    dev.write(list(m.patch["PATCH NAME1"].address), list(text.encode("ascii", "replace")))
    _history.append((f"rename to {name[:16]}", before_raw))
    return {"ok": True, "patch_name": dev.patch_name(), "saved": False}


@mcp.tool()
@friendly
def undo_last_change() -> dict:
    """Undo the last change made in this conversation (tone, name, or loaded patch contents)."""
    if not _history:
        return {"ok": False, "problem": "Nothing to undo in this conversation."}
    desc, raw = _history.pop()
    dev.write_buffer(raw)
    return {"ok": True, "undone": desc, "patch_name": dev.patch_name(), "undo_steps_left": len(_history)}


# ---------------------------------------------------------------------------- patches
@mcp.tool()
@friendly
def list_patches(refresh: bool = False) -> dict:
    """Names of the 99 user patches (U01..U99). Cached after the first read; refresh=true reads again."""
    if refresh or len(_names) < USER_SLOTS:
        for s in range(1, USER_SLOTS + 1):
            _names[s] = dev.patch_name(s)
    return {"ok": True, "patches": {f"U{s:02d}": n for s, n in sorted(_names.items())},
            "loaded": f"U{dev.current_slot():02d}"}


@mcp.tool()
@friendly
def load_patch(slot: int, discard_unsaved_changes: bool = False) -> dict:
    """Switch the GT-1 to user patch `slot` (1-99). If the loaded patch has unsaved changes this stops and
    asks first; pass discard_unsaved_changes=true only after the player agrees to lose them."""
    if not 1 <= slot <= USER_SLOTS:
        raise ValueError("Slot must be between 1 and 99.")
    unsaved, current = _unsaved()
    if unsaved and not discard_unsaved_changes:
        return {"ok": False, "needs_confirmation": True,
                "problem": f"'{dev.patch_name()}' (U{current:02d}) has unsaved changes. Save them first "
                           f"(save_patch) or confirm discarding them."}
    dev.load_slot(slot)
    _history.clear()
    return {"ok": True, "loaded": f"U{slot:02d}", "patch_name": dev.patch_name()}


@mcp.tool()
@friendly
def save_patch(slot: int, overwrite_confirmed: bool = False) -> dict:
    """Save the loaded patch into user slot `slot` (1-99). First call without overwrite_confirmed to see what
    is in the slot; only call again with overwrite_confirmed=true after the player says yes.
    A backup of the old slot is always kept, and the save is verified byte by byte."""
    if not 1 <= slot <= USER_SLOTS:
        raise ValueError("Slot must be between 1 and 99.")
    target_raw = dev.read_patch(slot)
    target_name = bytes(target_raw[:16]).decode("ascii", "replace").rstrip()
    buf = dev.read_patch()
    buf_name = bytes(buf[:16]).decode("ascii", "replace").rstrip()
    if target_raw == buf:
        return {"ok": True, "slot": f"U{slot:02d}", "message": f"U{slot:02d} already holds exactly this patch."}
    if not overwrite_confirmed:
        return {"ok": False, "needs_confirmation": True,
                "problem": f"U{slot:02d} currently holds '{target_name}'. Saving '{buf_name}' there replaces it "
                           f"(a backup is kept). Ask the player to confirm."}
    backups = CACHE_DIR / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"U{slot:02d}_{time.strftime('%Y%m%d-%H%M%S')}_{target_name.replace('/', '-')}.json"
    json.dump({"slot": slot, "name": target_name, "raw": target_raw}, open(backup, "w"))
    dev.write_patch(slot, buf)
    time.sleep(0.3)
    ok = dev.read_patch(slot) == buf
    _names[slot] = buf_name
    res = {"ok": ok, "slot": f"U{slot:02d}", "saved": buf_name, "replaced": target_name, "backup": str(backup)}
    if tone_studio_running():
        res["warning"] = "Tone Studio is open and will still show the old name until it reconnects."
    if not ok:
        res["problem"] = "Verification failed. The old patch is in the backup file; try again or check the cable."
    return res


@mcp.tool()
@friendly
def backup_all_patches() -> dict:
    """Save a full backup of all 99 user patches to a file on this Mac (takes about a minute)."""
    data = {f"U{s:02d}": dev.read_patch(s) for s in range(1, USER_SLOTS + 1)}
    folder = CACHE_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"all_user_patches_{time.strftime('%Y%m%d-%H%M%S')}.json"
    json.dump(data, open(path, "w"))
    return {"ok": True, "file": str(path)}


# ---------------------------------------------------------------------------- listening
@mcp.tool()
@friendly
def listen(seconds: float = 10) -> dict:
    """Record the GT-1's processed sound over USB while the player plays, and measure it: loudness, peak,
    brightness, balance across bands, noise in pauses, clipping. Tell the player to start playing right away
    (with pauses between phrases if you want to judge noise). Compares with the previous listen."""
    global _last_listen
    seconds = max(3.0, min(30.0, seconds))
    result = audio.analyze(audio.record(seconds))
    result["patch_name"] = dev.patch_name()
    if result["is_silent"]:
        result["hint"] = "Almost no sound was captured. Was the player playing? Check guitar volume and cables."
    if _last_listen:
        result["change_vs_previous"] = {
            "previous_patch": _last_listen["patch_name"],
            "level_db": round(result["playing_level_dbfs"] - _last_listen["playing_level_dbfs"], 1),
            "brightness_hz": result["brightness_hz"] - _last_listen["brightness_hz"],
        }
    _last_listen = result
    return {"ok": True, **result}


@mcp.tool()
@friendly
def match_volume(target_dbfs: float = -31.0, max_seconds: float = 40) -> dict:
    """Level the loaded patch while the player plays continuously: measures every 4 seconds and adjusts
    PREAMP A: LEVEL until the sound sits at target_dbfs (default -31, a comfortable reference).
    Measured energy is not the same as perceived loudness: ask the player afterwards and fine-tune."""
    m = pmap()
    level = m.decode(dev.read_patch(), "PREAMP A: LEVEL")
    start_level, db_per_step, last, hits, log = level, 0.5, None, 0, []
    end = time.time() + max(8.0, min(60.0, max_seconds))
    while time.time() < end:
        a = audio.analyze(audio.record(4))
        playing = a["playing_level_dbfs"]
        if playing < target_dbfs - 25:
            log.append(f"level {level}: no steady playing detected")
            continue
        err = target_dbfs - playing
        log.append(f"level {level}: {playing} dBFS ({err:+.1f} dB)")
        if abs(err) <= 1.0:
            hits += 1
            if hits >= 2:
                break
            continue
        hits = 0
        if last and last[0] != level and abs(playing - last[1]) > 0.3:
            db_per_step = max(0.1, min(2.0, abs((playing - last[1]) / (level - last[0]))))
        last = (level, playing)
        level = int(max(0, min(100, level + round(err / db_per_step))))
        addr, data = m.encode("PREAMP A: LEVEL", level)
        dev.write(addr, data)
    return {"ok": hits >= 2, "preamp_level": {"before": start_level, "after": level}, "log": log,
            "saved": False}


@mcp.tool()
@friendly
def calibrate_noise_gate(max_seconds: float = 45) -> dict:
    """Clean up string noise between phrases: while the player plays phrases with short silences, raises the
    noise suppressor threshold step by step until the pauses are quiet. Leaves drive and amp untouched."""
    m = pmap()
    threshold = m.decode(dev.read_patch(), "NS1: THRESHOLD")
    start, log, clean = threshold, [], False
    dev.write(*m.encode("NS1: ON/OFF", 1))
    end = time.time() + max(10.0, min(60.0, max_seconds))
    while time.time() < end:
        a = audio.analyze(audio.record(6))
        noise = a["noise_in_pauses_dbfs"]
        if noise is None:
            log.append(f"threshold {threshold}: no pauses heard (ask for silences between phrases)")
            continue
        log.append(f"threshold {threshold}: noise in pauses {noise} dBFS")
        if noise <= -65:
            clean = True
            break
        if threshold >= 85:
            log.append("limit reached: the noise likely comes from too much gain, not from pauses")
            break
        threshold += 5
        dev.write(*m.encode("NS1: THRESHOLD", threshold))
    return {"ok": clean, "threshold": {"before": start, "after": threshold}, "log": log, "saved": False}


@mcp.tool()
@friendly
def metronome_control(action: str, bpm: float = 100, volume: float = 0.15) -> dict:
    """Start or stop a click through the GT-1 output. action: 'start' or 'stop'. volume 0.05-0.5
    (default is quiet on purpose). The first beat of each bar is higher."""
    if action == "stop":
        metronome.stop()
        return {"ok": True, "metronome": "off"}
    metronome.start(max(30, min(260, bpm)), volume=max(0.02, min(0.5, volume)))
    return {"ok": True, "metronome": f"{metronome.bpm} BPM", "tip": "Ask if the click volume is comfortable."}


if __name__ == "__main__":
    mcp.run()
