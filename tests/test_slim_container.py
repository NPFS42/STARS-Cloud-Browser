"""Static contract checks; a real Docker build/start is still required."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_slim_glibc_debian_and_system_chromium_only():
    contents = (ROOT / "Dockerfile").read_text()
    assert "FROM python:3.12-slim-bookworm" in contents
    assert "chromium ca-certificates fonts-liberation" in contents
    assert "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1" in contents
    assert "STARS_BROWSER_EXECUTABLE=/usr/bin/chromium" in contents
    assert "playwright install" not in contents
    assert "chromium_sandbox=" in (ROOT / "browser_control/browser.py").read_text()


def test_compose_locks_down_private_port_and_process():
    c = (ROOT / "compose.yaml").read_text()
    assert '127.0.0.1:8811:8811' in c
    assert 'user: "10001:10001"' in c
    assert 'read_only: true' in c
    assert 'no-new-privileges:true' in c
    assert 'cap_drop:' in c and '- ALL' in c
    assert 'enable_ipv6: false' in c
    assert 'restart: unless-stopped' in c
    assert 'shm_size: 256m' in c
    assert 'privileged: true' not in c
    assert 'network_mode: host' not in c
    assert '/var/run/docker.sock' not in c


def test_docker_context_excludes_credentials_and_tests():
    d = (ROOT / '.dockerignore').read_text().splitlines()
    assert '.env' in d
    assert '.env.*' in d
    assert '!.env.example' in d
    assert 'tests' in d


def test_no_fixed_secret_in_image():
    docker = (ROOT / 'Dockerfile').read_text()
    assert 'STARS_BROWSER_UI_SECRET=' not in docker
    assert 'STARS_BROWSER_MCP_TOKEN=' not in docker
