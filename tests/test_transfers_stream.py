"""New transfer and streaming behavior; no Chromium or real network required."""
import asyncio
import base64
import importlib
import io
import os
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from starlette.datastructures import UploadFile

from browser_control.browser import BrowserController
from browser_control.transfers import MAX_FILE_BYTES, TransferStore, safe_name


@pytest.mark.asyncio
async def test_upload_website_attach_and_explicit_remove(tmp_path):
    store = TransferStore(tmp_path / 'staging')
    file = UploadFile(io.BytesIO(b'hello-world'), filename='../../escape.txt')
    record = await store.upload(file)
    assert record['name'] == 'escape.txt'
    assert record['size'] == 11
    assert (tmp_path / 'staging' / record['id']).read_bytes() == b'hello-world'
    assert not (tmp_path / 'escape.txt').exists()
    assert (tmp_path / 'staging').stat().st_mode & 0o777 == 0o700

    class FileInput:
        async def set_input_files(self, path, **kwargs):
            assert Path(path).read_bytes() == b'hello-world'
            self.received = path

    class Locator:
        def __init__(self): self.first = FileInput()

    class Page:
        url = 'https://example.org/upload'
        def __init__(self): self.loc = Locator()
        def locator(self, selector):
            assert selector == 'input[type=file]'
            return self.loc

    browser = BrowserController()
    browser.transfers = store
    page = Page()
    browser.context = types.SimpleNamespace(pages=[page])
    assert await browser.attach_file(record['id']) == page.url
    assert page.loc.first.received
    await store.remove(record['id'])
    assert await store.list() == []
    assert not (tmp_path / 'staging' / record['id']).exists()


@pytest.mark.asyncio
async def test_upload_limits_and_empty_files(tmp_path):
    store = TransferStore(tmp_path)
    empty = await store.upload(UploadFile(io.BytesIO(b''), filename='empty.txt'))
    assert empty['size'] == 0
    with pytest.raises(ValueError, match='16 MiB'):
        await store.upload(UploadFile(io.BytesIO(b'x' * (MAX_FILE_BYTES + 1)), filename='big.bin'))
    assert [r['name'] for r in await store.list()] == ['empty.txt']
    assert not (tmp_path / 'big.bin').exists()


@pytest.mark.asyncio
async def test_download_sanitized_and_mcp_chunk(tmp_path):
    store = TransferStore(tmp_path)

    class Download:
        suggested_filename = '..\\reports/../../answer.csv'
        async def save_as(self, path): Path(path).write_bytes(b'a,b\n1,2\n')

    await store.add_download(Download())
    rows = await store.list()
    assert len(rows) == 1 and rows[0]['name'] == 'answer.csv'
    assert rows[0]['direction'] == 'download'
    chunk = await store.read_chunk(rows[0]['id'])
    assert base64.b64decode(chunk['data_base64']) == b'a,b\n1,2\n'
    assert chunk['eof'] and chunk['next_offset'] == 8
    with pytest.raises(ValueError): await store.get('../' + rows[0]['id'])
    await store.close()
    assert await store.list() == []


@pytest.mark.asyncio
async def test_oversized_download_is_not_advertised(tmp_path):
    store = TransferStore(tmp_path)
    class Download:
        suggested_filename = 'huge.bin'
        async def save_as(self, path): Path(path).write_bytes(b'x' * (MAX_FILE_BYTES + 1))
    await store.add_download(Download())
    rows = await store.list()
    assert rows[0]['state'] == 'failed'
    assert not rows[0]['path'] if 'path' in rows[0] else True
    with pytest.raises(ValueError): await store.get(rows[0]['id'])


@pytest.mark.asyncio
async def test_mcp_small_file_and_chunk_bounds(tmp_path):
    store = TransferStore(tmp_path)
    record = await store.upload_bytes('tiny.txt', base64.b64encode(b'hi').decode())
    assert record['size'] == 2
    with pytest.raises(ValueError, match='256 KiB'):
        await store.upload_bytes('huge.txt', base64.b64encode(b'a' * (256 * 1024 + 1)).decode())
    with pytest.raises(ValueError): await store.upload_bytes('bad.txt', '!!!!')
    with pytest.raises(ValueError): await store.read_chunk(record['id'])


def test_filename_never_becomes_path():
    assert safe_name('../etc/passwd') == 'passwd'
    assert safe_name('..\\my-private.txt') == 'my-private.txt'
    assert safe_name('') == 'file'
    assert '/' not in safe_name('x/y')


@pytest.fixture
def service_module(monkeypatch, tmp_path):
    # Source-only endpoint test: MCP isn't installed in this runner. Replace
    # only the MCP registration adapter with a simple collector, exercising
    # actual FastAPI endpoints / authorization checks unchanged.
    class FakeMCP:
        def __init__(self, *args, **kwargs):
            self.tools = {}
            @asynccontextmanager
            async def run():
                yield
            self.session_manager = types.SimpleNamespace(run=run)
        def tool(self):
            def register(fn):
                self.tools[fn.__name__] = fn
                return fn
            return register
        def streamable_http_app(self): return FastAPI()

    mcp = types.ModuleType('mcp')
    server = types.ModuleType('mcp.server')
    fastmcp = types.ModuleType('mcp.server.fastmcp')
    fastmcp.FastMCP = FakeMCP
    monkeypatch.setitem(sys.modules, 'mcp', mcp)
    monkeypatch.setitem(sys.modules, 'mcp.server', server)
    monkeypatch.setitem(sys.modules, 'mcp.server.fastmcp', fastmcp)
    sys.modules.pop('browser_control.service', None)
    module = importlib.import_module('browser_control.service')
    module.controller.transfers = TransferStore(tmp_path / 'api')
    monkeypatch.setenv('STARS_BROWSER_UI_SECRET', 's' * 48)
    monkeypatch.setenv('STARS_BROWSER_MCP_TOKEN', 'm' * 48)
    monkeypatch.setenv('STARS_BROWSER_ALLOWED_HOST', 'private.ts.net')
    yield module
    sys.modules.pop('browser_control.service', None)


@pytest.mark.asyncio
async def test_service_upload_download_auth_and_file_scope(service_module):
    from browser_control.security import issue_session
    app = service_module.app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='https://private.ts.net') as client:
        assert (await client.get('/api/files')).status_code == 401
        assert (await client.get('/api/live')).status_code == 401
        client.cookies.set('stars_browser_session', issue_session('s' * 48))
        assert (await client.post('/api/files/upload', files={'file': ('doc.txt', b'hello')})).status_code == 403
        res = await client.post('/api/files/upload', files={'file': ('doc.txt', b'hello')},
                                headers={'X-STARS-BROWSER-UI': '1', 'Origin': 'https://private.ts.net'})
        assert res.status_code == 200, res.text
        ident = res.json()['id']
        listing = await client.get('/api/files')
        assert listing.json()[0]['name'] == 'doc.txt'
        assert (await client.get(f'/api/files/{ident}')).status_code == 404  # No download of upload staging
        assert (await client.delete(f'/api/files/{ident}', headers={'X-STARS-BROWSER-UI':'1'})).status_code == 200
        assert (await client.get('/api/files')).json() == []
        assert (await client.get('/api/live?fps=99')).status_code == 400
        assert (await client.get('/api/files', headers={'Host': 'public.example'})).status_code == 421


@pytest.mark.asyncio
async def test_stream_emits_repeated_jpeg_frames_and_releases_gate(service_module):
    calls = 0
    class Request:
        async def is_disconnected(self):
            nonlocal calls
            calls += 1
            return calls > 2
    class Browser:
        async def screenshot(self, fmt):
            assert fmt == 'jpeg'
            return b'\xff\xd8frame\xff\xd9'

    original = service_module.controller.screenshot
    service_module.controller.screenshot = Browser().screenshot
    try:
        response = await service_module.live_view(Request(), fps=3)
        frames = [frame async for frame in response.body_iterator]
        assert len(frames) == 2
        assert all(b'Content-Type: image/jpeg' in chunk and b'--starsframe' in chunk for chunk in frames)
        assert not service_module.stream_gate.locked()
    finally:
        service_module.controller.screenshot = original


@pytest.mark.asyncio
async def test_mcp_transfer_requires_expiring_grant(service_module):
    import base64
    browser = service_module.controller
    tools = service_module.mcp.tools
    with pytest.raises(PermissionError):
        await tools['browser_upload_small']('x.txt', base64.b64encode(b'x').decode())
    browser.allow_mcp_write(300)
    rec = await tools['browser_upload_small']('x.txt', base64.b64encode(b'x').decode())
    assert rec['size'] == 1
    browser.allow_mcp_write(0)
    with pytest.raises(PermissionError):
        await tools['browser_attach_file'](rec['id'])
    with pytest.raises(PermissionError):
        await tools['browser_download_chunk'](rec['id'])


@pytest.mark.asyncio
async def test_mcp_upload_chunks_order_size_and_finalize(tmp_path):
    store = TransferStore(tmp_path)
    rec = await store.begin_upload('../quarterly.csv')
    assert rec['state'] == 'pending'
    await store.append_upload(rec['id'], 0, base64.b64encode(b'first').decode())
    with pytest.raises(ValueError, match='offset'):
        await store.append_upload(rec['id'], 0, base64.b64encode(b'again').decode())
    await store.append_upload(rec['id'], 5, base64.b64encode(b'last').decode())
    done = await store.finish_upload(rec['id'])
    assert done['state'] == 'ready' and done['size'] == 9
    assert (tmp_path / rec['id']).read_bytes() == b'firstlast'
    with pytest.raises(ValueError):
        await store.append_upload(rec['id'], 9, base64.b64encode(b'oops').decode())


@pytest.mark.asyncio
async def test_abandoned_mcp_upload_can_be_cancelled(tmp_path):
    store = TransferStore(tmp_path)
    rec = await store.begin_upload('unused.bin')
    await store.remove(rec['id'])
    assert await store.list() == []
    assert not (tmp_path / rec['id']).exists()


@pytest.mark.asyncio
async def test_new_mcp_chunk_tools_all_grant_gated(service_module):
    browser = service_module.controller
    tools = service_module.mcp.tools
    for name, args in [
        ('browser_upload_begin', ('a.txt',)),
        ('browser_upload_append', ('f' * 32, 0, '')),
        ('browser_upload_finish', ('f' * 32,)),
        ('browser_download_chunk', ('f' * 32,)),
        ('browser_remove_file', ('f' * 32,)),
    ]:
        with pytest.raises(PermissionError):
            await tools[name](*args)
    browser.allow_mcp_write(300)
    record = await tools['browser_upload_begin']('file.txt')
    await tools['browser_upload_append'](record['id'], 0, base64.b64encode(b'data').decode())
    record = await tools['browser_upload_finish'](record['id'])
    assert record['size'] == 4
