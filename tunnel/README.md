# STARS Cloud Browser — isolated MCP tunnel templates

The browser runs in a Debian Slim container on localhost TCP/8811; a private Android viewer may use Tailscale Serve HTTPS/10000. This optional tunnel needs outbound HTTPS only. Never add a public listener, Funnel route, or Commander/VPS admin permission. The reference VPS has a separate, live-verified ChatGPT MCP connection; the following is a reproducible template, not its actual credential configuration.

## Reused, tested runtime
- Dedicated copy of existing STARS Commander tunnel-client v0.0.21: SHA256 4919b37dc9da3dc6e39a78e271a6b6984c11b6f16b481d603b976f538a9ed87d; LICENSE and NOTICE copied.
- MCP main channel: http://127.0.0.1:8811/mcp/mcp
- OAuth discovery intentionally disabled (the browser authenticates its own MCP token).
- Control-plane API key: new, browser-only, restricted Tunnels Read + Use; file reference only.
- Browser upstream authorization: separate protected file containing the exact single-line value "Bearer <existing browser MCP token>". Do not paste into chats, logs, YAML, or command arguments.
- Tunnel identity: NEW tunnel created in Platform settings, associated with the intended ChatGPT workspace. Do NOT reuse the Commander/NPFS tunnel IDs or their keys.
- Tunnel health binds only to 127.0.0.1:8812.

## Per-installation provisioning prerequisites (not committed to source)
1. Create the NEW Cloud Browser tunnel in OpenAI Platform tunnel settings (Tunnels Read + Manage role). Associate the personal ChatGPT workspace.
2. Provision its dedicated runtime key into /etc/stars-cloud-browser/openai-runtime-key, root-owned 0600, via an approved secure method.
3. Save the new tunnel ID (non-secret) as a single line in /etc/stars-cloud-browser/tunnel-id, root-owned 0600.
4. Provision /etc/stars-cloud-browser/upstream-authorization root-owned 0600, containing "Bearer " plus Cloud Browser's current MCP token; no copied Commander credentials.
5. Run python3 /opt/stars-cloud-browser/tunnel/preflight.py --prepare (checks and writes only the new config). The script keeps secrets in referenced files and never prints them.
6. Through an authorized service-management path, install only the staged browser tunnel unit, start it, and test /readyz on loopback 8812. Existing STARS Commander and NPFS tunnels remain running.
7. In ChatGPT Plugins, add a private custom MCP server with Connection: Tunnel and the NEW Cloud Browser tunnel. Verify real tool discovery and representative browser_status from ChatGPT on mobile.

Do not call this end-to-end connected until both tunnel readiness and ChatGPT tool invocation are independently demonstrated.

## Stop/rollback
Stop/disable only stars-cloud-browser-tunnel.service. Remove only its own service unit, config and browser-only runtime key; preserve the existing viewer/container, Commander and NPFS tunnels. No existing network/firewall/Serve state needs to change. If a later restart fails, the new service fails closed during preflight and must not substitute the Commander runtime identity.
