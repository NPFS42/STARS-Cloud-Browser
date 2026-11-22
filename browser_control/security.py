"""Validation and authentication, deliberately independent of the browser runtime."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


class UnsafeURL(ValueError):
    pass


def _public_address(ip: str) -> bool:
    # is_global excludes loopback, metadata/link-local, CGNAT/Tailscale, LAN,
    # multicast, documentation addresses, unique-local IPv6, etc.
    return ipaddress.ip_address(ip).is_global


def validate_target(url: str, resolve: bool = True) -> str:
    if len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise UnsafeURL("Invalid URL")
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower().rstrip(".")
        port = p.port
    except ValueError as exc:
        raise UnsafeURL("Invalid host or port") from exc
    if p.scheme not in ("http", "https") or not host:
        raise UnsafeURL("Only public HTTP(S) destinations are allowed")
    if p.username or p.password or "@" in p.netloc:
        raise UnsafeURL("Embedded credentials are prohibited")
    if port not in (None, 80, 443):
        raise UnsafeURL("Only web ports 80 and 443 are allowed")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".ts.net")):
        raise UnsafeURL("Private hostname is prohibited")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise UnsafeURL("Non-public address is prohibited")
    if resolve:
        try:
            infos = socket.getaddrinfo(host, port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except OSError as exc:
            raise UnsafeURL("Hostname did not resolve") from exc
        if not infos or any(not _public_address(info[4][0]) for info in infos):
            raise UnsafeURL("Hostname resolves to a non-public address")
    return url


def _sign(payload: str, key: str) -> str:
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_session(key: str, ttl: int = 28800) -> str:
    payload = f"{int(time.time()) + ttl}:{secrets.token_hex(16)}"
    return f"{payload}:{_sign(payload,key)}"


def verify_session(value: str | None, key: str) -> bool:
    if not value or len(value) > 256 or not key:
        return False
    try:
        stamp, nonce, signature = value.split(":", 2)
        if int(stamp) <= time.time() or int(stamp) > time.time() + 28810:
            return False
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(_sign(f"{stamp}:{nonce}",key),signature)


def require_ui(request: Request) -> None:
    if not verify_session(request.cookies.get("stars_browser_session"), os.environ.get("STARS_BROWSER_UI_SECRET", "")):
        raise HTTPException(status_code=401, detail="Authentication required")
    # Cross-site reads cannot use SameSite=Strict cookies, and state-changing
    # requests must originate from this same browser origin.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlsplit as parse
            if parse(origin).netloc != request.headers.get("host") or parse(origin).scheme != "https":
                raise HTTPException(status_code=403, detail="Origin rejected")
        if request.headers.get("x-stars-browser-ui") != "1":
            raise HTTPException(status_code=403, detail="CSRF header required")


def require_mcp(request: Request) -> None:
    token = os.environ.get("STARS_BROWSER_MCP_TOKEN", "")
    expected = "Bearer " + token
    if len(token) < 32 or not hmac.compare_digest(request.headers.get("authorization", ""), expected):
        raise HTTPException(status_code=401, detail="Invalid MCP token")


def check_configuration() -> None:
    ui = os.environ.get("STARS_BROWSER_UI_SECRET", "")
    mcp = os.environ.get("STARS_BROWSER_MCP_TOKEN", "")
    if len(ui) < 40 or len(mcp) < 40 or hmac.compare_digest(ui,mcp):
        raise RuntimeError("Two distinct secrets of at least 40 characters are required")
    if os.environ.get("STARS_BROWSER_ALLOWED_HOST", "") == "":
        raise RuntimeError("Set STARS_BROWSER_ALLOWED_HOST to the exact Tailnet Serve hostname")
