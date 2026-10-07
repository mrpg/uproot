# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2026.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Reproducible .tar.gz archives of project code that respect .gitignore files."""

import gzip
import os
import tarfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from tempfile import SpooledTemporaryFile
from typing import IO

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pathspec import GitIgnoreSpec
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

Rules = tuple[tuple[PurePosixPath, GitIgnoreSpec], ...]


def available(root: Path) -> bool:
    return (root / ".gitignore").is_file()


def rules(file: Path, base: PurePosixPath) -> Rules:
    if file.is_file():
        return ((base, GitIgnoreSpec.from_lines(file.read_text().splitlines())),)
    else:
        return ()


def ignored(rel: PurePosixPath, isdir: bool, specs: Rules) -> bool:
    result = False

    # Deeper .gitignore files and later patterns take precedence
    for base, spec in specs:
        path = str(rel.relative_to(base)) + ("/" if isdir else "")
        check = spec.check_file(path)

        if check.include is not None:
            result = check.include

    return result


def walk(root: Path) -> Iterator[tuple[PurePosixPath, bool]]:
    """Yield the relative paths of root and all directories and files in it that are
    not ignored, each with whether it is a directory. Symlinks are followed, but
    symlink cycles are not."""

    def recurse(
        rel: PurePosixPath, specs: Rules, ancestors: frozenset[str]
    ) -> Iterator[tuple[PurePosixPath, bool]]:
        directory = root / rel
        real = os.path.realpath(directory)

        if real in ancestors:
            return

        yield rel, True

        ancestors |= {real}
        specs += rules(directory / ".gitignore", rel)

        for entry in sorted(os.scandir(directory), key=lambda entry: entry.name):
            child = rel / entry.name
            isdir = entry.is_dir()

            if entry.name == ".git" or ignored(child, isdir, specs):
                continue
            elif isdir:
                yield from recurse(child, specs, ancestors)
            elif entry.is_file():
                yield child, False

    top = PurePosixPath()

    yield from recurse(top, rules(root / ".git" / "info" / "exclude", top), frozenset())


def files(root: Path) -> Iterator[PurePosixPath]:
    return (rel for rel, isdir in walk(root) if not isdir)


def contains(root: Path, path: Path) -> bool:
    """Whether path lies within root or within any directory that the archive reaches
    through symlinks, i.e., whether writing to path could end up in the archive."""
    real = path.resolve()

    return any(
        real.is_relative_to(os.path.realpath(root / rel))
        for rel, isdir in walk(root)
        if isdir
    )


def write(root: Path, fileobj: IO[bytes]) -> None:
    """Write a reproducible .tar.gz archive of root to fileobj. Files keep their
    modification times (in whole seconds), while ownership is zeroed and modes are
    normalized, so unmodified project files always produce identical archives."""
    prefix = PurePosixPath(root.resolve().name)

    with (
        gzip.GzipFile(filename="", mode="wb", fileobj=fileobj, mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for rel in files(root):
            path = root / rel
            info = tarfile.TarInfo(str(prefix / rel))
            stat = path.stat()
            info.size = stat.st_size
            info.mtime = int(stat.st_mtime)
            info.mode = 0o755 if stat.st_mode & 0o111 else 0o644

            with path.open("rb") as f:
                tar.addfile(info, f)


def build(root: Path) -> IO[bytes]:
    body = SpooledTemporaryFile(max_size=16 * 1024**2)  # noqa: SIM115
    write(root, body)
    body.seek(0)

    return body


async def download(root: Path) -> StreamingResponse:
    if not available(root):
        raise HTTPException(
            status_code=409,
            detail="Project code can only be archived if the project has a .gitignore",
        )

    body = await run_in_threadpool(build, root)

    return StreamingResponse(
        iter(lambda: body.read(64 * 1024), b""),
        media_type="application/gzip",
        headers={
            "Content-Disposition": "attachment; filename=project.tar.gz",
            "Content-Encoding": "identity",
        },
        background=BackgroundTask(body.close),
    )
