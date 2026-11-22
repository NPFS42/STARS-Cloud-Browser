"""Compact controls must preserve full browser capabilities without extra browser workers."""
import pytest
from browser_control.browser import BrowserController

class Page:
    url = 'https://example.org/'
    viewport_size = {'width':1280,'height':800}
    async def go_back(self, **kwargs): self.called = 'back'
    async def go_forward(self, **kwargs): self.called = 'forward'
    async def reload(self, **kwargs): self.called = 'reload'
    async def set_viewport_size(self, dims): self.viewport_size = dims
    async def screenshot(self, **kwargs):
        self.screenshot_args = kwargs
        return b'img'
    async def evaluate(self, expr):
        assert 'input' in expr and 'value' not in expr
        return []

class Context:
    def __init__(self, page): self.pages = [page]

@pytest.mark.asyncio
async def test_jpeg_preview_and_png_export():
    b=BrowserController(); page=Page(); b.context=Context(page)
    assert await b.screenshot('jpeg') == b'img'
    assert page.screenshot_args['type'] == 'jpeg' and page.screenshot_args['quality'] == 65
    assert await b.screenshot('png') == b'img'
    assert page.screenshot_args['type'] == 'png' and 'quality' not in page.screenshot_args
    with pytest.raises(ValueError): await b.screenshot('webp')

@pytest.mark.asyncio
async def test_compact_viewport_is_reversible_without_new_context():
    b=BrowserController(); page=Page(); b.context=Context(page)
    assert await b.viewport('compact') == {'width':390,'height':844}
    assert b.context.pages[0] is page
    assert b.view_mode == 'compact'
    assert await b.viewport('desktop') == {'width':1280,'height':800}
    with pytest.raises(ValueError): await b.viewport('unbounded')

@pytest.mark.asyncio
async def test_history_and_element_inspection():
    b=BrowserController(); page=Page(); b.context=Context(page)
    for op in ('back','forward','reload'):
        assert await b.history(op) == page.url
        assert page.called == op
    assert await b.elements() == []
    with pytest.raises(ValueError): await b.history('javascript')


def test_mobile_ui_uses_adaptive_viewport_and_reduced_polling():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    js=(root/'browser_control/static/ui.js').read_text()
    assert 'viewport.width / r.width' in js
    assert 'viewport.height / r.height' in js
    assert 'document.hidden' in js
    assert '7000' in js
    assert '/api/screenshot?format=jpeg' in js
