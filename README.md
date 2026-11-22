# STARS Cloud Browser

> **Start here:** [Complete self-hosting, Tailnet setup and VPS security guide](docs/SETUP_AND_SECURITY.md) — installation, private HTTPS, MCP, firewall acceptance, maintenance and rollback.

**Private, Tailnet-first Chromium browser with ChatGPT MCP controls**, a compact mobile viewer, bounded file transfers and low-resource live MJPEG streaming.

The app is an independently operated STARS component. **It is not STARS Commander or Jarvis PC Link**, and it does not inherit their admin permissions or credentials.

## Current build

- `v0.4.1` — Python 3.12 Debian Slim, system Chromium, Playwright, FastAPI + FastMCP.
- Live-tested VPS image: `stars-cloud-browser:0.4.1-local` (`sha256:6eeb1bec3cc6bb8fa78c9121468a5d781964969c916e1cccd1fe1f22c1010dc9`).
- One persistent browser profile, up to five tabs, desktop/compact viewports and 20 MCP tools.
- Website navigation, visible-page text and element discovery, click/type/scroll, history, screenshots, and user-authorized AI actions.
- **v0.4.1 fix:** `browser_screenshot` returns a base64 PNG **string**, matching the published MCP schema. Verified end-to-end from ChatGPT on November 22, 2026.
- Authenticated phone viewer with MJPEG at 1–3 FPS and temporary upload/download staging (up to 16 MiB per file and 64 MiB staged).
- Image memory ceiling 1.2 GB; measured idle browser memory approximately 313 MiB on the reference VPS. Image on reference VPS about 374 MB.

**Repository scope:** sanitized source, build files, deployment guard templates, tests and license only. No production profiles, secrets, private keys, token files or tunnel executable are checked in.

## Architecture

```
ChatGPT (mobile / desktop)
         |
         | Private OpenAI Secure MCP tunnel (outbound from VPS)
         v
  STARS browser MCP :8811 (loopback) -- grants + separate token
         |
         v
  Single Playwright Chromium in Debian Slim Docker
         |
         | Private-address denial + restricted public web egress
         v
       Public web

Phone on Tailnet --> Tailscale Serve HTTPS :10000 --> 127.0.0.1:8811
```

Only Tailscale Serve exposes the phone viewer. **Do not publish the container directly to the public internet or enable Tailscale Funnel.** ChatGPT reaches the MCP server through a distinct outbound tunnel; it is not placed on the Tailnet.

## Getting started

1. Install Docker Engine + Compose, Python 3, Tailscale, and host `iptables` with a `DOCKER-USER` chain. Inspect the security rules before deployment; this source contains **reference-VPS-specific networking parameters**.
2. Copy `.env.example` to `.env`. Generate **two different random secrets** (40+ characters); keep file mode `0600`. Configure your actual private Tailscale hostname. Never commit this file.
3. Inspect `security/firewall.py`, `security/seccomp_profile.json` and `compose.yaml` for your host. Chromium's sandbox remains **enabled**; the narrowly scoped seccomp profile supports its user namespaces and chroot.
4. Build with `docker compose build`. Create the container/network but **do not let Docker auto-start it before firewall policy is applied**. Install firewall rules using `python3 security/firewall.py --apply`, then `docker compose up -d --no-build`. On the reference VPS a firewall-first scheduler uses `security/startup_guard.py` after boot.
5. Confirm `http://127.0.0.1:8811/healthz` locally, verify denial of access to private, metadata, Tailnet, LAN and host addresses from **inside** the browser bridge, and confirm the ordinary public HTTPS and DNS path. Run `pytest -q` in a suitable Python test environment.
6. Configure *Tailscale Serve* to proxy a **new tailnet-only HTTPS port** to `http://127.0.0.1:8811`. Do not overwrite existing Serve routes.
7. For ChatGPT controls, use a **dedicated Secure MCP Tunnel** identity. See `tunnel/README.md` for a template and the protected credential-file boundary. Actual runtime credentials/tunnel ID must never be committed or reused from Commander.

This is a deployment guide, not a promise that arbitrary hosts share the same firewall routing, ports, CPU budget, or namespace support.

## Source layout

- `browser_control/` — browser controller, security, MCP server and phone UI
- `security/` — reference firewall, approved seccomp and fail-closed startup guard
- `tunnel/` — optional independent Secure MCP tunnel config template and preflight; no binaries or credentials
- `tests/` — regression tests (including security and compact deployment)
- `compose.yaml`, `Dockerfile` — Debian Slim deployment
- `LICENSE` — GNU Affero General Public License v3

## Verification and limitations

Verified on the reference VPS: Docker Chromium sandbox smoke, browser health, public navigation, mobile/desktop viewport switching, mobile viewer JPEG/MJPEG, staging upload/list/delete, outbound firewall negatives, 20 local MCP tools, and **direct ChatGPT MCP navigation + screenshot**. Source tests passed 46/46 for the v0.4.0 baseline; the v0.4.1 screenshot fix passed a separate live ChatGPT roundtrip.

Not yet proven in this release: cold-boot recovery; actual physical mobile-handset interaction; full website file-upload and browser-download roundtrips through the ChatGPT MCP connection; sustained performance; all browser sites and special login flows. The tunnel client is a separate upstream dependency, not redistributed here.

## Security and operation

The browser views untrusted websites. It is intentionally **not** an administrative shell. MCP read and navigation operations are separate from time-limited authorization to click, type, attach files or retrieve downloads. Never grant access to VPS administrative destinations via the browser network.

The source is provided under **AGPL-3.0-only**; see `LICENSE`. Preserve third-party dependency licensing and obtain separately required tunnel-client licenses from its upstream distributor.
