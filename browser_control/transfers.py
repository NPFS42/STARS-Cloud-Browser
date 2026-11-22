"""Bounded, temporary file staging; never exposes arbitrary VPS filesystem paths."""
from __future__ import annotations

import asyncio
import base64
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 12
MAX_MCP_BYTES = 256 * 1024
FILE_TTL = 30 * 60
CHUNK = 256 * 1024


def safe_name(name: str) -> str:
    """Filename is metadata, never a filesystem path."""
    name = name.replace('\\', '/').split('/')[-1]
    name = re.sub(r'[^A-Za-z0-9._ ()-]', '_', name).strip(' .')[:120]
    return name if name not in ('', '.', '..') else 'file'


@dataclass
class Record:
    id: str
    name: str
    size: int
    direction: str
    path: Path
    created: float
    state: str = 'ready'
    error: str = ''

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "size": self.size,
                "direction": self.direction, "state": self.state,
                "created": int(self.created), "error": self.error}


class TransferStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.environ.get('STARS_BROWSER_TRANSFER_DIR', '/tmp/stars-browser-transfers'))
        self.records: dict[str, Record] = {}
        self.lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def _purge(self) -> None:
        now = time.time()
        for key, record in list(self.records.items()):
            if now - record.created > FILE_TTL:
                # Browser downloads may still be active; the container's tmpfs
                # bounds their space. An abandoned MCP upload can be retired.
                if record.state == 'pending' and record.direction == 'download':
                    continue
                record.path.unlink(missing_ok=True)
                del self.records[key]

    def _new(self, name: str, direction: str, state: str = 'ready') -> Record:
        self._ensure_root()
        self._purge()
        if len(self.records) >= MAX_FILES:
            raise ValueError('Transfer limit reached; remove an old file first')
        ident = secrets.token_hex(16)
        return Record(ident, safe_name(name), 0, direction, self.root / ident, time.time(), state)

    def _reserve(self, size: int) -> None:
        if size > MAX_FILE_BYTES:
            raise ValueError('File exceeds 16 MiB limit')
        if sum(r.size for r in self.records.values()) + size > MAX_TOTAL_BYTES:
            raise ValueError('Transfer staging storage limit exceeded')

    async def upload(self, file: Any) -> dict[str, Any]:
        """Stream an UploadFile in bounded chunks; zero-byte files are valid."""
        async with self.lock:
            rec = self._new(file.filename or 'upload', 'upload')
            size = 0
            try:
                with rec.path.open('xb') as dest:
                    os.chmod(rec.path, 0o600)
                    while chunk := await file.read(CHUNK):
                        size += len(chunk)
                        self._reserve(size)
                        dest.write(chunk)
                rec.size = size
                self.records[rec.id] = rec
                return rec.summary()
            except Exception:
                rec.path.unlink(missing_ok=True)
                raise
            finally:
                await file.close()

    async def upload_bytes(self, filename: str, b64: str) -> dict[str, Any]:
        if len(b64) > (MAX_MCP_BYTES * 4 // 3) + 8:
            raise ValueError('MCP upload exceeds 256 KiB; use mobile file transfer')
        try:
            raw = base64.b64decode(b64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError('Invalid base64 file data') from exc
        if len(raw) > MAX_MCP_BYTES:
            raise ValueError('MCP upload exceeds 256 KiB')
        async with self.lock:
            rec = self._new(filename, 'upload')
            self._reserve(len(raw))
            try:
                with rec.path.open('xb') as dest:
                    os.chmod(rec.path, 0o600)
                    dest.write(raw)
                rec.size = len(raw)
                self.records[rec.id] = rec
                return rec.summary()
            except Exception:
                rec.path.unlink(missing_ok=True)
                raise

    async def begin_upload(self, filename: str) -> dict[str, Any]:
        """Start a bounded multi-call MCP upload. IDs only, never a host path."""
        async with self.lock:
            rec = self._new(filename, 'upload', state='pending')
            with rec.path.open('xb'):
                pass
            os.chmod(rec.path, 0o600)
            self.records[rec.id] = rec
            return rec.summary()

    async def append_upload(self, ident: str, offset: int, data_base64: str) -> dict[str, Any]:
        if len(data_base64) > (MAX_MCP_BYTES * 4 // 3) + 8:
            raise ValueError('Upload chunk exceeds 256 KiB')
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError('Invalid base64 file data') from exc
        if len(raw) > MAX_MCP_BYTES:
            raise ValueError('Upload chunk exceeds 256 KiB')
        async with self.lock:
            self._purge()
            rec = self.records.get(ident)
            if not rec or rec.direction != 'upload' or rec.state != 'pending':
                raise ValueError('Upload not in progress')
            if not isinstance(offset, int) or rec.size != offset:
                raise ValueError('Upload offset mismatch')
            if rec.size + len(raw) > MAX_FILE_BYTES:
                raise ValueError('File exceeds 16 MiB limit')
            # Existing rec.size is already counted in stored totals.
            self._reserve(len(raw))
            with rec.path.open('ab') as dest:
                dest.write(raw)
            rec.size += len(raw)
            return rec.summary()

    async def finish_upload(self, ident: str) -> dict[str, Any]:
        async with self.lock:
            self._purge()
            rec = self.records.get(ident)
            if not rec or rec.direction != 'upload' or rec.state != 'pending':
                raise ValueError('Upload not in progress')
            if rec.path.stat().st_size != rec.size:
                raise ValueError('Upload size verification failed')
            rec.state = 'ready'
            return rec.summary()

    async def add_download(self, download: Any) -> None:
        async with self.lock:
            try:
                rec = self._new(download.suggested_filename, 'download', state='pending')
                self.records[rec.id] = rec
            except ValueError:
                await download.cancel()
                return
        # Save to a path inside the bounded tmpfs; Chromium's download temp
        # storage is also there. Check size before advertising the file.
        try:
            await download.save_as(str(rec.path))
            size = rec.path.stat().st_size
            async with self.lock:
                self._reserve(size)
                rec.size = size
                rec.state = 'ready'
        except Exception:
            rec.path.unlink(missing_ok=True)
            async with self.lock:
                rec.state = 'failed'
                rec.error = 'Download failed or exceeds the transfer quota'

    def observe_download(self, download: Any) -> None:
        task = asyncio.create_task(self.add_download(download))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def list(self) -> list[dict[str, Any]]:
        async with self.lock:
            self._purge()
            return [r.summary() for r in sorted(self.records.values(), key=lambda x: x.created, reverse=True)]

    async def get(self, ident: str, direction: str | None = None) -> Record:
        if not re.fullmatch(r'[a-f0-9]{32}', ident):
            raise ValueError('Invalid transfer identifier')
        async with self.lock:
            self._purge()
            rec = self.records.get(ident)
            if not rec or (direction and rec.direction != direction) or rec.state != 'ready':
                raise ValueError('File not available')
            return rec

    async def read_chunk(self, ident: str, offset: int = 0) -> dict[str, Any]:
        rec = await self.get(ident, direction='download')
        if not isinstance(offset, int) or offset < 0 or offset > rec.size:
            raise ValueError('Invalid offset')
        with rec.path.open('rb') as f:
            f.seek(offset)
            data = f.read(MAX_MCP_BYTES)
        return {"id": ident, "name": rec.name, "size": rec.size,
                "offset": offset, "next_offset": offset+len(data),
                "data_base64": base64.b64encode(data).decode('ascii'),
                "eof": offset + len(data) >= rec.size}

    async def remove(self, ident: str) -> None:
        async with self.lock:
            self._purge()
            rec = self.records.get(ident)
            if not rec or (rec.state == 'pending' and rec.direction == 'download'):
                raise ValueError('File not found or still transferring')
            rec.path.unlink(missing_ok=True)
            del self.records[ident]

    async def close(self) -> None:
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        async with self.lock:
            for rec in self.records.values():
                rec.path.unlink(missing_ok=True)
            self.records.clear()
