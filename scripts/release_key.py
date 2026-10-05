"""Release key: create it once, then sign latest.json for every release.

The private key lives only in the macOS Keychain of the release Mac (and in an offline backup).
It is never written to disk, printed, committed or uploaded.

  uv run scripts/release_key.py init
  uv run scripts/release_key.py sign --version 0.2.0 --notes "..." [--mcpb dist/x.mcpb] [--days 90]
"""
import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SERVICE, ACCOUNT = "dial-in-release-key", "release-2026-1"
DOWNLOAD_URL = "https://allankirsten.com/labs/dial-in/download"
OUT = Path(__file__).resolve().parents[1] / "dist" / "latest.json"


def _keychain_get():
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _public_b64(priv):
    raw = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def init(_):
    if _keychain_get():
        sys.exit(f"A key already exists in the Keychain ({SERVICE}/{ACCOUNT}). Not replacing it.")
    priv = Ed25519PrivateKey.generate()
    raw = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())
    r = subprocess.run(["security", "add-generic-password", "-s", SERVICE, "-a", ACCOUNT,
                        "-l", "Dial In release signing key", "-w", base64.b64encode(raw).decode()],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"Keychain refused the key: {r.stderr.strip()}")
    print(f"Stored in Keychain as {SERVICE}/{ACCOUNT}.")
    print(f"Public key for src/gt1/updates.py PUBLIC_KEYS['{ACCOUNT}']:")
    print(_public_b64(priv))


def sign(a):
    secret = _keychain_get()
    if not secret:
        sys.exit("No release key in the Keychain. Run: release_key.py init")
    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(secret))
    now = int(time.time())
    payload = {"seq": now, "issued_at": now, "expires_at": now + a.days * 86400,
               "version": a.version, "notes": a.notes, "download_url": DOWNLOAD_URL}
    if a.mcpb:
        payload["sha256"] = hashlib.sha256(Path(a.mcpb).read_bytes()).hexdigest()
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    env = {"key_id": ACCOUNT, "payload": base64.b64encode(body).decode(),
           "signature": base64.b64encode(priv.sign(body)).decode()}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(env, indent=1) + "\n")
    print(f"Signed {a.version} (expires in {a.days} days) -> {OUT}")


p = argparse.ArgumentParser()
sub = p.add_subparsers(required=True)
sub.add_parser("init").set_defaults(fn=init)
s = sub.add_parser("sign")
s.add_argument("--version", required=True)
s.add_argument("--notes", default="")
s.add_argument("--mcpb")
s.add_argument("--days", type=int, default=90)
s.set_defaults(fn=sign)
args = p.parse_args()
args.fn(args)
