# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2026.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""A write-only file object for producing archives as a stream of chunks."""


class Sink:
    """Collects whatever an archive writer (ZipFile, GzipFile, …) writes, so that
    the bytes written so far can be taken out with drain() and sent onwards.

    It deliberately lacks tell() and seek(): ZipFile then writes data descriptors
    instead of seeking back to patch local headers."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def write(self, b: bytes, /) -> int:
        self.buffer += b

        return len(b)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def drain(self) -> bytes:
        chunk = bytes(self.buffer)
        self.buffer.clear()

        return chunk
