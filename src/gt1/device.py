"""MIDI connection to the BOSS GT-1 (Roland SysEx RQ1/DT1)."""
import subprocess
import time

import mido

from .params import EDIT_BUFFER, PATCH_SIZE, to_addr, to_int

ROLAND = 0x41
DEVICE_ID = 0x00
MODEL = [0x00, 0x00, 0x00, 0x30]
RQ1, DT1 = 0x11, 0x12
CURRENT_PATCH = [0x00, 0x01, 0x00, 0x00]
EDITOR_MODE = [0x7F, 0x00, 0x00, 0x01]  # without it the GT-1 ignores setup/system requests


class NotConnected(RuntimeError):
    pass


def checksum(body):
    return (128 - sum(body) % 128) % 128


def tone_studio_running():
    try:
        out = subprocess.run(["pgrep", "-f", "BOSS TONE STUDIO"], capture_output=True, text=True)
        return bool(out.stdout.strip())
    except OSError:
        return False


class GT1:
    def __init__(self):
        self.inp = self.out = None

    # connection -------------------------------------------------------------
    def connect(self):
        if self.inp:
            return
        names = [n for n in mido.get_output_names() if "GT-1" in n]
        if not names:
            raise NotConnected(
                "GT-1 not found. Check that it is powered on, the USB cable is connected, "
                "and the GT-1 driver is installed.")
        last = None
        for _ in range(3):  # CoreMIDI sometimes fails the first open (-304)
            try:
                self.out = mido.open_output(names[0])
                self.inp = mido.open_input([n for n in mido.get_input_names() if "GT-1" in n][0])
                self._editor_mode()
                return
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(0.5)
        raise NotConnected(f"Could not open the GT-1 MIDI port ({last}). Unplug and replug the USB cable.")

    def close(self):
        for p in (self.inp, self.out):
            if p:
                p.close()
        self.inp = self.out = None

    def _editor_mode(self):
        """Same handshake BOSS TONE STUDIO does. Must be repeated if the GT-1 was power-cycled."""
        self.write(EDITOR_MODE, [1])
        time.sleep(0.2)

    # raw I/O ----------------------------------------------------------------
    def _drain(self):
        for _ in self.inp.iter_pending():
            pass

    def read(self, addr, size, timeout=2.0):
        """RQ1. Returns a list of `size` bytes (None where the GT-1 did not answer).
        If nothing comes back, re-sends the editor handshake once and retries."""
        result = self._read_once(addr, size, timeout)
        if all(b is None for b in result):
            self._editor_mode()
            result = self._read_once(addr, size, timeout)
        return result

    def _read_once(self, addr, size, timeout):
        self.connect()
        self._drain()
        body = list(addr) + to_addr(size)
        self.out.send(mido.Message("sysex", data=[ROLAND, DEVICE_ID] + MODEL + [RQ1] + body + [checksum(body)]))
        start, got = to_int(addr), {}
        head = [ROLAND, DEVICE_ID] + MODEL + [DT1]
        deadline, quiet = time.time() + timeout, None
        while time.time() < deadline:
            msgs = list(self.inp.iter_pending())
            for m in msgs:
                d = list(m.data) if m.type == "sysex" else []
                if d[:7] == head:
                    base = to_int(d[7:11])
                    for k, b in enumerate(d[11:-1]):
                        if start <= base + k < start + size:
                            got[base + k - start] = b
            if len(got) >= size:
                break
            if msgs:
                quiet = time.time()
            elif quiet and time.time() - quiet > 0.25:
                break
            time.sleep(0.005)
        return [got.get(i) for i in range(size)]

    def write(self, addr, data):
        """DT1, split so no message crosses a 128-byte address boundary."""
        self.connect()
        pos = to_int(addr)
        i = 0
        while i < len(data):
            room = 128 - (pos & 0x7F)
            chunk = data[i:i + min(room, 128)]
            body = to_addr(pos) + chunk
            self.out.send(mido.Message("sysex", data=[ROLAND, DEVICE_ID] + MODEL + [DT1] + body + [checksum(body)]))
            time.sleep(0.03 if len(chunk) > 8 else 0.015)
            pos += len(chunk)
            i += len(chunk)

    # patches ----------------------------------------------------------------
    @staticmethod
    def slot_addr(slot):
        """slot is 1..99 (U01..U99)."""
        return [0x10, slot - 1, 0x00, 0x00]

    def read_patch(self, slot=None):
        addr = EDIT_BUFFER if slot is None else self.slot_addr(slot)
        raw = self.read(addr, PATCH_SIZE, timeout=4.0)
        if None in raw:
            raise NotConnected("The GT-1 did not answer completely. Check the USB cable and try again.")
        return raw

    def write_patch(self, slot, raw):
        self.write(self.slot_addr(slot), raw)

    def write_buffer(self, raw):
        self.write(EDIT_BUFFER, raw)

    def patch_name(self, slot=None):
        addr = EDIT_BUFFER if slot is None else self.slot_addr(slot)
        raw = self.read(addr, 16)
        return bytes(b if b is not None else 63 for b in raw).decode("ascii", "replace").rstrip()

    def current_slot(self):
        raw = self.read(CURRENT_PATCH, 2)
        if None in raw:
            raise NotConnected("The GT-1 did not answer. Check the USB cable.")
        return (raw[0] << 7 | raw[1]) + 1

    def load_slot(self, slot):
        n = slot - 1
        self.write(CURRENT_PATCH, [n >> 7, n & 0x7F])
        time.sleep(1.2)
