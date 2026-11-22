#!/usr/bin/env python3
"""Fail-closed staging/activation checks for STARS Cloud Browser's independent MCP tunnel.

This only reads metadata for secret files; it never prints, copies, exports or
rewrites credential material. A new Platform tunnel and restricted key are required.
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys
import urllib.request

BASE = pathlib.Path("/opt/stars-cloud-browser")
CONFIG = pathlib.Path("/etc/stars-cloud-browser")
ID_FILE = CONFIG / "tunnel-id"
RUNTIME_KEY = CONFIG / "openai-runtime-key"
BROWSER_AUTH = CONFIG / "upstream-authorization"
OUTPUT = CONFIG / "tunnel.yaml"
TEMPLATE = BASE / "tunnel/tunnel.yaml.template"
FIREWALL = BASE / "security/firewall.py"
BROWSER_HEALTH = "http://127.0.0.1:8811/healthz"
EXPECTED_BINARY_SHA256 = "4919b37dc9da3dc6e39a78e271a6b6984c11b6f16b481d603b976f538a9ed87d"

def private_file(path, lo, hi):
    try:
        s = path.stat()
        return s.st_uid == 0 and s.st_mode & 0o077 == 0 and lo <= s.st_size <= hi and path.is_file()
    except FileNotFoundError:
        return False

def config_text():
    if not private_file(ID_FILE, 20, 110):
        raise RuntimeError("Cloud Browser's separate tunnel ID is not provisioned as a root-private file")
    identity = ID_FILE.read_text(encoding="utf8").strip()
    if not re.fullmatch(r"tunnel_[A-Za-z0-9]{12,96}", identity):
        raise RuntimeError("Malformed Cloud Browser tunnel ID")
    if identity == "tunnel_REPLACE_WITH_NEW_CLOUD_BROWSER_ID":
        raise RuntimeError("Template tunnel ID is not valid provisioning")
    if not private_file(RUNTIME_KEY, 30, 1200):
        raise RuntimeError("Separate Cloud Browser runtime API key is not provisioned root-private")
    if not private_file(BROWSER_AUTH, 40, 1000):
        raise RuntimeError("Separate browser upstream Authorization file is not provisioned root-private")
    template = TEMPLATE.read_text(encoding="utf8")
    assert template.count("tunnel_REPLACE_WITH_NEW_CLOUD_BROWSER_ID") == 1
    return template.replace("tunnel_REPLACE_WITH_NEW_CLOUD_BROWSER_ID", identity)

def app_ready():
    try:
        with urllib.request.urlopen(BROWSER_HEALTH, timeout=5) as r:
            return r.status == 200 and b'"ready":true' in r.read(1024).replace(b" ", b"")
    except Exception:
        return False

def firewall_ready():
    r = subprocess.run([sys.executable, str(FIREWALL), "--check"], capture_output=True, timeout=15)
    return r.returncode == 0

def binary_ready():
    import hashlib
    binary = BASE / "tunnel/tunnel-client"
    if not binary.is_file():
        return False
    h = hashlib.sha256()
    with binary.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest() == EXPECTED_BINARY_SHA256

def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true")
    g.add_argument("--prepare", action="store_true")
    g.add_argument("--strict", action="store_true")
    opts = p.parse_args()
    status = {"binary_verified": binary_ready(), "browser_healthy": app_ready(),
              "firewall_healthy": firewall_ready(),
              "tunnel_id_present": private_file(ID_FILE,20,110),
              "runtime_key_present": private_file(RUNTIME_KEY,30,1200),
              "upstream_header_present": private_file(BROWSER_AUTH,40,1000),
              "configured": private_file(OUTPUT,200,3000)}
    if opts.status:
        import json
        print(json.dumps(status, sort_keys=True))
        return 0
    if not all(status[k] for k in ("binary_verified","browser_healthy","firewall_healthy")):
        raise RuntimeError("Browser, source binary or firewall is not verified; refusing tunnel startup")
    expected = config_text()
    if opts.prepare:
        CONFIG.mkdir(parents=True, exist_ok=True)
        os.chmod(CONFIG, 0o700)
        tmp = CONFIG / ".tunnel.yaml.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf8") as f:
                f.write(expected)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, OUTPUT)
        finally:
            try:tmp.unlink(missing_ok=True)
            except OSError:pass
        os.chmod(OUTPUT,0o600)
        print("BROWSER_TUNNEL_CONFIG_PREPARED; no credentials were displayed")
    else:
        if not private_file(OUTPUT,200,3000):
            raise RuntimeError("Dedicated browser tunnel config not ready")
        if OUTPUT.read_text(encoding="utf8") != expected:
            raise RuntimeError("Browser tunnel config has drifted; check manually")
        print("BROWSER_TUNNEL_PREFLIGHT_PASS")

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("BROWSER_TUNNEL_FAIL_CLOSED:", str(e), file=sys.stderr)
        sys.exit(3)
