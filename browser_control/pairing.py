"""Time-bounded, device-bound viewer pairing approved only through VPS host control.

A displayed challenge is NOT an authentication credential. The approval marker
must be written by the host administrator inside the running browser container.
No existing UI or MCP secret is revealed or changed.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import secrets
import stat
import time

PAIR_ROOT = Path("/tmp/stars-browser-pairing")
LIFETIME_SECONDS = 600
MAX_PENDING = 8


class PairingStore:
    def __init__(self) -> None:
        self.pending: dict[str, tuple[bytes, float, float]] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        for code, (_, until, _) in list(self.pending.items()):
            if now >= until:
                self.pending.pop(code, None)
                (PAIR_ROOT / ("approved-" + code)).unlink(missing_ok=True)

    def request(self) -> tuple[str, str]:
        self._prune()
        if len(self.pending) >= MAX_PENDING:
            raise ValueError("Too many outstanding pairing requests; retry later")
        PAIR_ROOT.mkdir(mode=0o700, parents=False, exist_ok=True)
        s = PAIR_ROOT.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
            raise RuntimeError("Pairing directory failed owner/mode preflight")
        code = secrets.token_hex(5).upper()
        while code in self.pending:
            code = secrets.token_hex(5).upper()
        cookie = secrets.token_urlsafe(32)
        self.pending[code] = (hashlib.sha256(cookie.encode()).digest(),
                              time.monotonic() + LIFETIME_SECONDS, time.time())
        return code, cookie

    def status(self, cookie: str | None) -> tuple[str | None, bool]:
        self._prune()
        if not cookie or len(cookie) > 128:
            return None, False
        digest = hashlib.sha256(cookie.encode()).digest()
        for code, (expected, expiry, issued_wall) in list(self.pending.items()):
            if not hmac.compare_digest(digest, expected) or time.monotonic() >= expiry:
                continue
            approval = PAIR_ROOT / ("approved-" + code)
            try:
                info = approval.lstat()
            except FileNotFoundError:
                return code, False
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != 0 or
                info.st_mtime < issued_wall - 2):
                return code, False
            approval.unlink(missing_ok=True)
            self.pending.pop(code, None)
            return code, True
        return None, False


pairing = PairingStore()
