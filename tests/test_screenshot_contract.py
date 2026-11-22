"""Prevent MCP schema regression: screenshot MUST return base64 str, not Image."""
import asyncio
import base64
from browser_control import service


def test_browser_screenshot_returns_base64_string(monkeypatch):
    fixture = bytes([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10]) + b"fakepng"
    async def fake_capture():
        return fixture

    monkeypatch.setattr(service.controller, "screenshot", fake_capture)
    async def invoke():
        return await service.mcp._tool_manager.get_tool("browser_screenshot").fn()

    result = asyncio.run(invoke())
    assert isinstance(result, str)
    assert base64.b64decode(result, validate=True) == fixture
