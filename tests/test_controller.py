import pytest
from browser_control.browser import BrowserController

@pytest.mark.asyncio
async def test_reject_oversized_text_before_page_access():
    browser=BrowserController()
    with pytest.raises(ValueError):await browser.type_text('x'*5001)

@pytest.mark.asyncio
async def test_reject_unsupported_key_before_page_access():
    browser=BrowserController()
    with pytest.raises(ValueError):await browser.press('ControlOrMeta+Shift+J')

@pytest.mark.asyncio
async def test_reject_bad_scroll_before_page_access():
    browser=BrowserController()
    with pytest.raises(ValueError):await browser.scroll(1601)


def test_mcp_write_requires_bounded_grant():
    b=BrowserController()
    with pytest.raises(PermissionError): b.require_mcp_write()
    with pytest.raises(ValueError): b.allow_mcp_write(3600)
    b.allow_mcp_write(300)
    b.require_mcp_write()
    assert 0 < b.mcp_grant_remaining() <= 300
    b.allow_mcp_write(0)
    with pytest.raises(PermissionError): b.require_mcp_write()
