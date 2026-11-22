# STARS Cloud Browser — Complete Self-Hosting & Security Guide

**Release:** v0.4.1 (November 2026) · **License:** AGPL-3.0-only · **Intended host:** small Linux VPS with Docker and Tailscale.

This is a practical installation and operations guide for the [STARS Cloud Browser repository](https://github.com/NPFS42/STARS-Cloud-Browser). It distinguishes the **working reference deployment** from **procedures every new host must independently verify**. The goal is a private, lightweight Chromium browser reachable from a phone without exposing its web UI to the public Internet, plus an optional, separately authenticated ChatGPT MCP connection.

> **Important:** Running a browser on a VPS is not automatically secure. The benefit comes from strict network access, an isolated browser process, scoped credentials, timely security updates, and tested backups. Never run a browser that can access your VPS administration interface or household LAN unrestricted.

## 1. Quick links

### Example private installation (replace placeholders)

| Resource | Link or address | Purpose |
|---|---|---|
| **STARS browser** | `https://<YOUR-VPS-MAGICDNS-NAME>:10000/` | Replace with your own Tailnet-only HTTPS viewer address |
| Tailscale machines | [Tailscale Machines](https://login.tailscale.com/admin/machines) | Verify the phone and VPS belong to the same tailnet |
| Tailnet access rules | [Tailscale Access Controls](https://login.tailscale.com/admin/acls) | Restrict which devices/users can reach the browser |
| Browser source | [NPFS42/STARS-Cloud-Browser](https://github.com/NPFS42/STARS-Cloud-Browser) | Private code, tests, Docker and security templates |
| Tailscale setup | [Quickstart](https://tailscale.com/docs/how-to/quickstart) | Add a VPS and phone |
| Tailscale on Linux | [Install Tailscale on Linux](https://tailscale.com/docs/install/linux) | Ubuntu/Debian setup |
| Tailscale private HTTPS | [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) | Private reverse proxy |
| DNS names | [MagicDNS](https://tailscale.com/docs/features/magicdns) | Stable *.ts.net names |
| Docker setup | [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) | Engine and Compose |
| Docker firewall | [Docker packet filtering](https://docs.docker.com/engine/network/packet-filtering-firewalls/) | How published ports and host filtering interact |

Do not publish your real VPS hostname, public address, private network ranges, access tokens or browser-profile data in documentation, screenshots, issues or test logs. Use placeholders such as `<YOUR-VPS-MAGICDNS-NAME>` and `<YOUR-VPS-PUBLIC-IP>`; these are examples, not access credentials.

### What was actually verified on the reference VPS

- Ubuntu 24.04 VPS, 2 vCPUs, about 4 GiB RAM, Docker, Tailscale and one Debian Slim Chromium image.
- Browser Docker service bound to **127.0.0.1:8811**, healthy, non-root **UID 10001**, read-only root filesystem, dropped capabilities, Chromium sandbox enabled with an explicitly reviewed seccomp profile.
- Dedicated **172.30.251.0/28** Docker bridge: host firewall blocked tested LAN/private/Tailnet/metadata destinations and admitted tested public HTTPS and DNS.
- **Tailscale Serve HTTPS port 10000** routed to localhost port 8811 without changing existing Serve routes.
- ChatGPT MCP successfully called status, navigation, element discovery, text snapshot, responsive viewport changes, tabs and **screenshot**. The v0.4.1 screenshot schema correction was tested live.
- Browser UI JPEG/MJPEG and temporary file staging were tested. **Not yet independently proven:** a complete ChatGPT file upload/download roundtrip, physical Android touch acceptance, and a cold reboot recovery test.

## 2. Architecture: two separate, protected paths

~~~text
YOUR PHONE / LAPTOP                          CHATGPT (cloud)
  |                                               |
  | Tailscale identity, access policy             | separate private MCP connection
  | encrypted tailnet transport                   | via dedicated outbound tunnel
  v                                               v
Tailscale Serve HTTPS :10000             Outbound MCP tunnel client on VPS
  |                                               |
  | Proxy only to local service                   | independent token and grant policy
  +-------------------+---------------------------+
                      |
             127.0.0.1:8811 (VPS only)
                      |
            FastAPI / MCP / mobile UI
                      |
      Debian Slim Docker + Chromium + Playwright
       non-root | sandbox | no admin privileges
                      |
       scoped DOCKER-USER + host INPUT firewall
                      |
                 PUBLIC WEB
           (not LAN / host / Tailnet)
~~~

**These are different trust boundaries.** Your phone joins the tailnet; **ChatGPT does not automatically join it**. The optional MCP tunnel is an outbound connection from the VPS to the configured control plane and must use a **browser-only identity**, not Commander, Jarvis or VPS administrator credentials.

Tailscale **Serve** is private to the tailnet. **Funnel** is for public exposure; do not enable Funnel for this project. The VPS's Docker port must not bind to `0.0.0.0`.

## 3. Requirements and preflight

Recommended starting point: an Ubuntu 24.04 LTS or comparable up-to-date Linux VPS, roughly **2 vCPUs / 4 GiB RAM**, 10+ GiB available storage for an image, packages and profile, and an SSH or provider-console recovery path. A smaller host may work, but the browser can peak well above idle memory use.

Install or prepare:

1. A VPS you can administer; enable provider account MFA and keep a recovery console available.
2. Docker Engine and the **Docker Compose plugin** using the official [Ubuntu installation guide](https://docs.docker.com/engine/install/ubuntu/). Do not assume Docker's firewall is governed entirely by UFW.
3. Tailscale on the VPS and phone, both in the same tailnet.
4. Git access to this private repository.
5. A separate user or tightly scoped service account for deployments, where feasible. Avoid unnecessary tools inside the browser container.
6. A plan for encrypted backups **outside the same VPS**, and a tested restore path.

On the VPS, inspect your existing environment before making changes:

~~~bash
docker version
docker compose version
tailscale status
tailscale ip -4
tailscale serve status
sudo iptables -S DOCKER-USER
ss -ltn
df -h /
~~~

**Do not paste these as a script that blindly rewrites firewalls.** Inspect the output for conflicting ports, address space, Docker networks and existing Serve routes. Preserve existing SSH/Tailscale recovery access.

## 4. Create or join your tailnet

1. Open [Tailscale Quickstart](https://tailscale.com/docs/how-to/quickstart) and create an account/tailnet if needed. Turn on MFA for its identity provider.
2. Open [Tailscale Machines](https://login.tailscale.com/admin/machines). You should eventually see **both the VPS and your phone**.
3. Install Tailscale on Linux using the [official instructions](https://tailscale.com/docs/install/linux). For typical Linux setups, authenticate with `sudo tailscale up`, and complete the sign-in it supplies.
4. Install the Tailscale mobile app from your platform's official app store, sign into the **same tailnet**, and keep its VPN connected while using the private browser. You do **not** need a separate STARS Android companion application.
5. In the Tailscale admin console, enable/check [MagicDNS](https://tailscale.com/docs/features/magicdns) and HTTPS support. Confirm the VPS has a `machine-name.tailnet.ts.net` name.
6. Review [access controls and grants](https://tailscale.com/docs/features/access-control/grants). **Membership alone is not an adequate least-privilege policy**; a tailnet with an unrestricted default policy may allow more lateral access than you intended. Allow your approved devices/users to reach the VPS's Serve port only, and preserve a separately approved management route.

Testing: `tailscale status` on the VPS should include your approved devices. Private HTTPS access will not work reliably if the phone is signed into a different tailnet, its VPN is off, the MagicDNS name is wrong, or an access rule denies the port.

### Why the browser URL is HTTPS even though its backend is HTTP

Tailscale Serve terminates HTTPS and forwards traffic locally to `http://127.0.0.1:8811`. The backend HTTP service must stay on **loopback**. The HTTPS certificate may disclose the `*.ts.net` hostname through public certificate-transparency infrastructure; the hostname itself is **not an access-control mechanism**. Tailscale identity, network policy and the app login remain essential.

## 5. Download the source without copying private runtime data

Authenticate to the private repository using your normal GitHub authentication. For example:

~~~bash
git clone https://github.com/NPFS42/STARS-Cloud-Browser.git
sudo mkdir -p /opt/stars-cloud-browser
sudo cp -a STARS-Cloud-Browser/. /opt/stars-cloud-browser/
cd /opt/stars-cloud-browser
~~~

On a fresh server, verify the checkout includes `Dockerfile`, `compose.yaml`, `browser_control/`, `security/` and `tunnel/`.

**Do not copy** an existing browser's `.env`, `/data/profile`, browser cookies, downloaded files, runtime tunnel tokens or private credentials from another host. These are installation-specific secrets. The repository's `.env.example` is a template, not valid production authentication.

The base image is pinned to a particular digest, and the reference VPS's `startup_guard.py` also contains a pinned **locally built image ID**. The latter ID will **not necessarily match** an image you build on a different host; see the startup step below.

## 6. Set up browser-only authentication

Copy the example and edit the private copy:

~~~bash
sudo cp .env.example .env
sudo chmod 600 .env
sudoedit .env
~~~

Set these values:

| Setting | Required value |
|---|---|
| `STARS_BROWSER_UI_SECRET` | Fresh cryptographically random token of at least 40 characters |
| `STARS_BROWSER_MCP_TOKEN` | **Different** fresh cryptographically random token |
| `STARS_BROWSER_ALLOWED_HOST` | Exact MagicDNS hostname, **no** `https://` or port |
| `STARS_BROWSER_PROFILE` | `/data/profile` |
| `STARS_BROWSER_EXECUTABLE` | `/usr/bin/chromium` |
| `STARS_BROWSER_CHROMIUM_SANDBOX` | `1` |

To generate a random value without installing a password tool:

~~~bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
~~~

Generate **two separate** values and store them directly in the root-readable-only `.env`. Be mindful that printing passwords into a terminal can leave them in terminal scrollback; a password manager or secure provisioning is preferable. Do not place tokens in shell history, GitHub issues, CI logs or chat.

**Never** disable the Chromium sandbox to make deployment "work." A failure to launch under the selected seccomp/AppArmor/user-namespace policy is a reason to fix the platform or stop deployment.

## 7. Docker network and sandbox: order matters

Review these files **before deploying**:

- `compose.yaml` — non-root user, read-only root, limits, loopback-only published port, isolated `browser-egress` network.
- `security/seccomp_profile.json` — reviewed permissions needed for Chromium's user-namespace sandbox.
- `security/firewall.py` — scoped IPv4 network rules, Docker `DOCKER-USER` and host `INPUT`; it **discovers the public-facing interface subnet at runtime** rather than embedding a particular VPS public IP/network in the source.
- `security/startup_guard.py` — fail-closed checks and exact image / seccomp hashes.

The reference bridge is `172.30.251.0/28`, its gateway `172.30.251.1`, and the container `172.30.251.2`. **Do not blindly reuse these values** if they conflict with another Docker bridge, VPN subnet, or private LAN. If you change them, update **all** matching references in Compose, firewall, startup guard and tests.

**Host public IPv4 network discovery:** The source version of `security/firewall.py` obtains non-private IPv4 interface networks from `ip -j -4 address show` and blocks those networks in its dedicated Docker chain. This replaces hard-coded VPS public subnet identifiers while retaining the host-isolation intent. It **fails closed** on NAT-only hosts without a discoverable public IPv4 interface: provision and verify a suitable additional destination-deny policy rather than deleting the check or launching the browser unprotected. Verify all derived rules with `--check`, actual negative network probes, and a firewall-first startup plan. Existing live deployments should be migrated separately using backup and rollback, not implicitly changed by updating the repository.

### Safe initial sequence

The following commands assume the host-specific policy has been reviewed, the chosen address range is unused, and the Docker daemon has created its `DOCKER-USER` chain.

~~~bash
cd /opt/stars-cloud-browser
sudo docker compose build
sudo docker compose create --no-build
sudo python3 security/firewall.py --apply
sudo python3 security/firewall.py --check
~~~

**Stop here if either firewall command fails.** Do not start Chromium until the policy exists and the new bridge is isolated. Docker's firewall/port-publishing rules can bypass assumptions based only on UFW. For details, see [Docker packet filtering](https://docs.docker.com/engine/network/packet-filtering-firewalls/) and [port publishing](https://docs.docker.com/engine/network/port-publishing/).

Once the egress rules have been reviewed and tested, exercise Chromium sandboxing in a temporary container while the main service is stopped:

~~~bash
sudo docker compose run --rm --no-deps browser python -m browser_control.diag
~~~

Expected outcome: `STARS_BROWSER_CHROMIUM_SMOKE_OK`. If you encounter `No usable sandbox`, check the distro's user-namespace settings and the scoped seccomp profile; **do not** substitute `--no-sandbox`.

Then start the isolated service:

~~~bash
sudo docker compose up -d --no-build
sudo docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8811/healthz
~~~

Expected health response: `{"service":"stars-cloud-browser","ready":true}`. Check that `docker compose ps` publishes only `127.0.0.1:8811->8811/tcp`.

### Essential egress denial tests

From **inside** the browser container, verify connections cannot reach your actual private LAN, VPS administrative interfaces, Tailscale ranges or the cloud metadata service. An illustrative test:

~~~bash
sudo docker exec stars-cloud-browser-browser-1 python -c 'import socket; s=socket.socket();s.settimeout(2);print("metadata_connect_result",s.connect_ex(("169.254.169.254",80)));s.close()'
~~~

The result must **not** be zero. Test additional destinations meaningful for your infrastructure. In a separate test, confirm public HTTPS and DNS resolve. A policy that accidentally allows private networks or forbids all public sites is not accepted.

**IPv6 and DNS are separate security concerns.** The reference Compose bridge disables IPv6, but review host forwarding, Docker daemon settings, DNS and alternative network interfaces. Verify no route escapes the scoped policy. Do not rely on application URL validation alone: hostname resolution can change after an initial safety check.

### Make restart recovery fail-closed

**Do not set `restart: always` or `unless-stopped` in Docker** unless you can prove the host firewall is restored *before* the container is started after every boot. The reference deployment intentionally uses `restart: "no"` and a separately scheduled `security/startup_guard.py` to apply/check the firewall first.

Before using the reference guard on another host, update its locally built image pin based on:

~~~bash
sudo docker image inspect stars-cloud-browser:0.4.1-local --format '{{.Id}}'
sha256sum security/seccomp_profile.json
~~~

Compare the values to `IMAGE` and `SECCOMP` in `security/startup_guard.py`. Only pin values you have actually built/reviewed. **Do not remove these checks to make startup easier.** The example systemd unit in `security/stars-cloud-browser.service` is an alternative design, not evidence that systemd boot ordering has passed testing on your host. Install only one documented, independently tested firewall-first boot path.

## 8. Enable private HTTPS using Tailscale Serve

First ensure `http://127.0.0.1:8811/healthz` works **on the VPS** and your chosen Tailscale port is unused. The reference installation uses TCP **10000** to avoid disturbing other Tailscale Serve services.

~~~bash
sudo tailscale serve --bg --https=10000 --yes http://127.0.0.1:8811
tailscale serve status
~~~

The status output should describe **tailnet only** and a proxy to `http://127.0.0.1:8811`. It must **not** show a Funnel/public service for this browser. Do not use `tailscale serve reset`: that can remove unrelated existing Serve routes.

On an approved Tailscale-connected phone, open:

**https://<YOUR-VPS-MAGICDNS-NAME>:10000/**

For your installation, use `https://<YOUR-VPS-MAGICDNS-NAME>:10000/` while connected to the authorized tailnet.

Sign in with the browser **UI secret**, not the MCP token, Tailscale sign-in credentials, or any VPS admin password. The application then uses an HTTPS-only session cookie.

**Negative test:** disconnect the phone from Tailscale and confirm the private browser URL is **not** reachable. Also test with an account/device lacking the required tailnet grant. If the service is publicly accessible, stop and correct the Serve/network policy before browsing.

## 9. Use the phone interface

The viewer contains the live page and mobile controls. Under **Tools · Live view · Files · AI grants** you can:

- Start/stop the MJPEG live preview and select **1, 2 or 3 frames per second**.
- Switch between desktop and compact viewport sizes.
- Navigate, tap, type, press permitted keys, scroll, manage tabs and save a PNG screenshot.
- Stage a local file and attach it to an HTML file input on a website. File limits are **16 MiB per file** with bounded temporary storage and automatic expiry.
- Explicitly allow **AI control for 5, 15 or 30 minutes**, or revoke it immediately. Granting AI control is distinct from simply logging into the viewer.

Files obtained from sites are **untrusted and unscanned**. Do not automatically open or execute them on personal devices. The viewer is intended for ordinary browsing and approved interactions; use direct website APIs where possible.

## 10. Optional ChatGPT MCP connection (independent from Tailnet)

ChatGPT cannot use the tailnet-only viewer URL as though it were on the phone's VPN. The application exposes an authenticated **local** MCP endpoint at:

**`http://127.0.0.1:8811/mcp/mcp`**

The double `/mcp/mcp` is deliberate in this release because the FastMCP application is mounted under a FastAPI prefix. The route is **not intended for public ingress**.

For an account/workspace supporting private MCP tunnels:

1. Create/choose a **dedicated browser tunnel identity** in the provider's currently supported setup flow. Do not reuse credentials for STARS Commander, Jarvis, SSH, or VPS administration.
2. Use an appropriately scoped runtime key and separate MCP upstream authorization. Keep those protected values in root-owned files outside Git; never paste them into the repository.
3. Use `tunnel/tunnel.yaml.template` and `tunnel/preflight.py` as **staged examples**. Install an approved, licensed tunnel client separately; the runtime binary is not distributed in this repository.
4. Authenticate the tunnel to the browser's local MCP endpoint, keeping local tunnel health on a separate loopback port where supported.
5. Connect the browser MCP server in ChatGPT's available custom-plugin workflow. Confirm **tool discovery and real calls**, not just that a tunnel process is running.

In the reference installation ChatGPT successfully invoked **20 MCP tools**, including browser status, navigation, snapshot, element discovery and a **v0.4.1 screenshot**. A live MCP screenshot returns a **base64 PNG string** because the published tool schema expects a string. Avoid unnecessarily printing a large base64 image in conversations.

For consequential actions and transfers, unlock a short AI grant from the phone UI, perform the approved operation, then revoke the grant.

## 11. Acceptance checklist — do not skip

A new installation should pass all of the following before being described as fully operational:

- [ ] Docker container runs **non-root**, read-only root, with capabilities dropped and Chromium sandbox enabled.
- [ ] Only `127.0.0.1:8811` is published by Docker; no unexpected public or IPv6 listener.
- [ ] The browser's dedicated bridge cannot reach your VPS host/admin interface, metadata endpoints, Tailnet, or private LAN.
- [ ] Public HTTP/HTTPS and DNS from the browser work after filtering.
- [ ] Browser's private Tailnet HTTPS viewer works from an **authorized** device.
- [ ] Browser's viewer is unreachable from an **unauthorized** or off-Tailnet client.
- [ ] UI secret and MCP token are distinct; unauthenticated UI and MCP requests are rejected.
- [ ] Navigate to a harmless test page, inspect text, change viewport and capture a screenshot.
- [ ] Phone MJPEG stream responds, pauses/resumes properly, and respects one-viewer limits.
- [ ] Stage/upload/download/remove a small benign file; verify byte-for-byte roundtrip and expiry.
- [ ] ChatGPT can discover and invoke the MCP tools. Screenshot returns valid base64 PNG text.
- [ ] Temporarily grant AI control, verify an approved write action, revoke it and confirm the action is then denied.
- [ ] The browser is safely restored **after a full VPS reboot**, with firewall restored **before** Chromium launch.
- [ ] Backup and restore of the encrypted profile/config are tested without exposing cookies or tokens.
- [ ] Logs and monitoring show no unexpected public service, resource spike or growing filesystem.

The reference deployment has passed a **subset**, not the complete checklist. Its cold-reboot, physical phone and end-to-end ChatGPT file-transfer proofs still need specific acceptance runs.

## 12. Ongoing maintenance and backups

**Daily/weekly:** monitor container health, CPU/RAM, memory limits, free disk, Tailscale status, firewall policy and TLS verification. Review access to the browser profile and remove unnecessary temporary files. No browser should have access to the host's Docker socket or privileged administration credentials.

**Updates:** examine browser, Python dependency, base-image, Docker, Tailscale and Linux security notices. Rebuild a pinned candidate, test the sandbox and firewall, then replace only the browser service after an approved rollback checkpoint. A pinned image digest does **not** automatically deliver security fixes.

**Backups:** the browser profile volume contains potentially sensitive cookies, storage and history. Treat copies as secrets. Use encryption and an independent destination; maintain the selected retention limit (for example, **3 versions / 3 days**) and perform a real restore test. Do not put decrypted profiles or API keys into Git or a world-readable archive.

**Service boundaries:** keep Commander, Jarvis, Roundtable, GitHub automation and Cloud Browser permission scopes separate. Share **source code and tool contracts**, not privileged credentials or runtime control.

## 13. Why self-hosting *can* improve security

| Control | Personal computer browser | Generic managed cloud browser | Your hardened VPS browser |
|---|---|---|---|
| Exposure of your main workstation | Web pages execute on your daily-use machine | Browser is remote | Browser is remote and separated from Home/Shop PCs |
| Public inbound viewer | Depends on product | Provider-dependent | **None required**; Tailscale Serve is private |
| Browser profile custody | Local machine/user | Usually provider-controlled | Your VPS account and backup policy, subject to hosting provider |
| Restrict access to internal addresses | Depends on endpoint policies | Provider-dependent | Dedicated Docker egress deny policy with negative tests |
| AI interaction authority | Depends on tooling | Provider-dependent | Separate MCP token + short explicit grants |
| Updates and incident response | You/OS vendor | Typically browser service provider | **You must operate and patch the whole stack** |
| Visibility of data to others | Local services/sites | Service provider and sites | VPS host, integrated services and sites may still see relevant data |

### Reasons this setup can reduce certain risks

1. **Blast-radius reduction.** A malicious website or browser exploit runs on a dedicated VPS container rather than directly on your personal Windows computer. It does not eliminate container escape or kernel flaws, but creates additional boundaries.
2. **Small externally accessible surface.** The phone viewer is reachable only via an authenticated Tailnet Serve route and an app login. No public inbound browser port is necessary.
3. **Network deny rules are verifiable.** The browser's outbound connections are tested against the actual firewall, including metadata and private IP destinations. This helps limit server-side request forgery and browser pivot attacks.
4. **Separation of powers.** A browser token does not equal a VPS administrative token, and ChatGPT actions have their own time-limited grant mechanism.
5. **Owner-controlled retention and recoverability.** You can decide how much profile data, logs and backup history to keep, audit configuration changes and roll back the image.

### Reasons it may be *less* secure if poorly operated

A VPS provider can potentially access or snapshot its underlying storage. A compromised VPS, Tailscale identity, tunnel account, browser profile, or container escape remains serious. A third-party cloud browser with a mature security team may patch faster than an individually operated instance. ChatGPT receives text, screenshots or files that you allow through MCP; visited websites still see requests, the VPS's egress IP and any details you enter. An exposed public browser port, disabled sandbox, overly permissive Docker policy or stale Chromium could negate all the expected advantages.

**Conclusion:** Self-hosted is not synonymous with anonymous, invisible or immune to attack. The advantage is **auditable control of the trust boundaries**—only when those controls are actually maintained and tested.

## 14. Troubleshooting and recovery

| Symptom | Likely check | Safe response |
|---|---|---|
| Browser link won't load on phone | Phone's Tailscale VPN, MagicDNS, grant, port 10000, Serve status | Verify both devices and private HTTPS; do not open a public port as a workaround |
| Login rejected / 401 | UI vs MCP credential; browser session cookie; hostname | Use the UI secret at `/login`; don't reveal secrets in chat |
| Browser responds 421 / host rejected | `STARS_BROWSER_ALLOWED_HOST` | Use exact VPS MagicDNS hostname, not an IP or unrelated public domain |
| Chromium says "No usable sandbox" | Kernel user namespaces, seccomp/AppArmor, UID/caps | Use reviewed sandbox support; **never disable sandbox** for a quick fix |
| Firewall check fails | Docker chain, subnet conflict, policy ordering, host-input reply | Stop browser startup and restore known-good policy |
| Container fails after reboot | Docker startup ordering vs firewall; stale image pin | Validate firewall-first guard and image digest; do not enable blind Docker auto-restart |
| MCP returns 401 | Separate MCP token / tunnel header | Diagnose credentials locally without pasting or logging them |
| MCP screenshot schema error | Old release returned an Image where a string was required | Upgrade to v0.4.1 or later with matching schema and validate directly |
| Live stream stalls | Single-viewer lock, browser tab hidden, stream reconnection | Stop/restart live view; try manual screenshot fallback |
| Download missing | Website permission, staging limit, expiry, AI grant | Verify transfer status; do not expand unsafe file limits blindly |

### Non-destructive rollback

Only after preserving a recovery path, stop the browser component:

~~~bash
cd /opt/stars-cloud-browser
sudo docker compose down
~~~

`docker compose down` **without `--volumes`** preserves the named browser profile volume. If the optional private Serve mapping must be turned off, remove **only its own port**:

~~~bash
sudo tailscale serve --https=10000 off
~~~

Do **not** run `tailscale serve reset` or blindly flush iptables; both may disrupt unrelated services. Remove or roll back the dedicated firewall rules only after the browser is stopped, and only after verifying the remaining network dependencies. For a code regression, restore the previous pinned image and compatible config, then rerun firewall and MCP acceptance.

## 15. Official references

- [Tailscale quickstart](https://tailscale.com/docs/how-to/quickstart)
- [Tailscale Serve, private HTTPS](https://tailscale.com/docs/features/tailscale-serve)
- [Tailscale MagicDNS](https://tailscale.com/docs/features/magicdns)
- [Tailscale access control and grants](https://tailscale.com/docs/features/access-control/grants)
- [Tailscale private server with Docker](https://tailscale.com/docs/solutions/host-private-server-docker)
- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Docker packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
- [Docker published-port behavior](https://docs.docker.com/engine/network/port-publishing/)
- [Playwright Python browser documentation](https://playwright.dev/python/docs/browsers)
- [Project source](https://github.com/NPFS42/STARS-Cloud-Browser)

**Version and status disclaimer:** the reference-host deployment findings above are from November 22, 2026. Review upstream documentation, image/dependency changes and security advisories at the time of any new deployment. No guide can substitute for testing the actual host's network and security boundaries.
