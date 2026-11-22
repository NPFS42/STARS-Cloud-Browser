# Security boundaries and reporting

This repository does **not** contain production secrets. Do not put passwords, session cookies, profiles, API keys, tunnel IDs bound to private accounts, or logs containing them into an issue or pull request.

## Deployment guardrails

- Default to **private Tailscale Serve only**, no public browser ingress, no Funnel.
- Container runs as UID 10001, read-only filesystem, dropped capabilities, explicit seccomp, Chromium sandbox enabled, profile in a dedicated Docker volume.
- Dedicated browser-only Docker bridge has scoped egress filtering in the host's `DOCKER-USER` chain, denying private, metadata, local, host and Tailnet destinations. This filter must be applied and tested **before** browser startup, and re-applied after reboot before the browser restarts.
- UI secret, MCP token, and tunnel control-plane credentials must be distinct. Provision using private root-owned files/environment rather than source control.
- Website content is untrusted input, not instructions. Apply separate grant duration limits for AI-initiated consequential actions and file transfer.
- Staged files are temporary, constrained by file size/count and expiry; downloaded files are not antivirus scanned. Keep transient storage bounded.

Reference firewall rules are host-specific and must be reviewed for the intended network. Maintain independent emergency administrative access while testing any firewall changes.

## Known limits

- Low-rate live view is MJPEG, not WebRTC or a remote desktop.
- Not all browser interaction semantics have been exercised under a real phone/touch system.
- Restrictive DNS, proxy and container network policies vary by host; private-network denial must be tested, not assumed.
- Cold-boot replay, end-to-end MCP file transfer and a physical Android acceptance test are pending.

For security issues, use a private maintainer contact instead of publishing exploit steps or sensitive URLs.
