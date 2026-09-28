# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Response compression with Brotli (preferred) and gzip.

Static files are compressed once at the highest level and kept in memory.
Dynamic responses are compressed by CompressionMiddleware. Brotli releases the
GIL, so compressing in worker threads does not block the event loop.
"""

import asyncio
import gzip
from typing import Literal, cast

import anyio.to_thread
import brotli
from starlette.datastructures import Headers
from starlette.middleware.gzip import (
    GZipMiddleware,
    GZipResponder,
    IdentityResponder,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from uproot.constraints import ensure

Encoding = Literal["br", "gzip"]

BROTLI_QUALITY = 11
BROTLI_QUALITY_LARGE = 5
BROTLI_MAX_SIZE = 256 * 1024
GZIP_LEVEL = 9
MINIMUM_SIZE = 512
COMPRESSIBLE = (
    "application/javascript",
    "application/json",
    "application/xml",
    "image/svg+xml",
    "text/",
)


def negotiate(accept_encoding: str) -> Encoding | None:
    """Pick the best encoding the client accepts, honoring q=0."""
    accepted = set()

    for item in accept_encoding.lower().split(","):
        coding, *params = (part.strip() for part in item.split(";"))
        q = 1.0

        for param in params:
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0

        if q > 0:
            accepted.add(coding)

    if "br" in accepted:
        return "br"
    elif "gzip" in accepted or "x-gzip" in accepted:
        return "gzip"
    else:
        return None


def compressible(media_type: str | None) -> bool:
    return media_type is not None and media_type.lower().startswith(COMPRESSIBLE)


def compress(data: bytes, encoding: Encoding) -> bytes:
    if encoding == "br":
        return bytes(brotli.compress(data, quality=BROTLI_QUALITY))
    else:
        return gzip.compress(data, compresslevel=GZIP_LEVEL, mtime=0)


# (path, encoding) -> (SHA-256, compressed bytes). One entry per file and
# encoding, so a changed file replaces its stale entry. Pending compressions
# are shared, so that simultaneous first requests compress only once.
STATIC_CACHE: dict[tuple[str, Encoding], tuple[str, asyncio.Task[bytes]]] = {}


async def compressed_file(path: str, sha256: str, encoding: Encoding) -> bytes:
    """Compressed contents of a static file, keyed by its SHA-256."""
    key = (path, encoding)
    cached = STATIC_CACHE.get(key)

    if cached is None or cached[0] != sha256 or cached[1].cancelled():
        task = asyncio.create_task(
            anyio.to_thread.run_sync(compress_path, path, encoding)
        )
        STATIC_CACHE[key] = (sha256, task)
    else:
        task = cached[1]

    try:
        return await asyncio.shield(task)
    except OSError:
        STATIC_CACHE.pop(key, None)
        raise


def compress_path(path: str, encoding: Encoding) -> bytes:
    with open(path, "rb") as f:
        return compress(f.read(), encoding)


class BrotliResponder(IdentityResponder):
    content_encoding = "br"

    def __init__(self, app: ASGIApp, minimum_size: int) -> None:
        super().__init__(app, minimum_size)

        self.compressor: brotli.Compressor | None = None

    async def apply_compression(self, body: bytes, *, more_body: bool) -> bytes:
        if self.compressor is None:
            # The highest quality is slow (~1 MB/s), so it is reserved for
            # complete responses of moderate size, such as pages
            small = not more_body and len(body) <= BROTLI_MAX_SIZE
            quality = BROTLI_QUALITY if small else BROTLI_QUALITY_LARGE
            self.compressor = brotli.Compressor(quality=quality)

        return await anyio.to_thread.run_sync(self.compress_body, body, more_body)

    def compress_body(self, body: bytes, more_body: bool) -> bytes:
        ensure(self.compressor is not None)
        compressor = cast(brotli.Compressor, self.compressor)

        data = compressor.process(body)

        if more_body:
            return bytes(data + compressor.flush())
        else:
            return bytes(data + compressor.finish())


class CompressionMiddleware(GZipMiddleware):
    """Like Starlette's GZipMiddleware, but prefers Brotli and honors q=0.
    Responses that already have a Content-Encoding pass through unchanged."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app, minimum_size=MINIMUM_SIZE, compresslevel=GZIP_LEVEL)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        encoding = negotiate(",".join(Headers(scope=scope).getlist("accept-encoding")))
        responder: IdentityResponder

        if encoding == "br":
            responder = BrotliResponder(self.app, self.minimum_size)
        elif encoding == "gzip":
            responder = GZipResponder(
                self.app, self.minimum_size, compresslevel=self.compresslevel
            )
        else:
            responder = IdentityResponder(self.app, self.minimum_size)

        await responder(scope, receive, send)
