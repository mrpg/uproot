# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2026.
# SPDX-License-Identifier: LGPL-3.0-or-later

import io
import os
import tarfile
from pathlib import Path

from uproot import archive


def touch(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def project(tmp_path: Path) -> Path:
    root = tmp_path / "study"
    outside = tmp_path / "outside"

    touch(root / ".gitignore", ".env\n*.sqlite3*\nbuild/\n*.log\n!keep.log\n")
    touch(root / ".env", "UPROOT_ADMIN_PASSWORD=secret")
    touch(root / "uproot.sqlite3")
    touch(root / "main.py")
    touch(root / "build" / "keep.log")
    touch(root / "app" / "debug.log")
    touch(root / "app" / "keep.log")
    touch(root / "app" / "__init__.py")
    touch(root / "app" / ".gitignore", "*.tmp\n!main.py\n")
    touch(root / "app" / "scratch.tmp")
    touch(root / ".git" / "HEAD")
    touch(root / ".git" / "info" / "exclude", "private.txt\n")
    touch(root / "private.txt")
    touch(outside / "logo.svg")
    touch(outside / "notes.tmp")

    (root / "app" / "static").symlink_to(outside)
    (root / "app" / "loop").symlink_to(root / "app")
    (root / "dangling").symlink_to(tmp_path / "missing")

    return root


def test_files_respect_gitignore_and_follow_symlinks(tmp_path: Path) -> None:
    assert [str(path) for path in archive.files(project(tmp_path))] == [
        ".gitignore",
        "app/.gitignore",
        "app/__init__.py",
        "app/keep.log",
        "app/static/logo.svg",
        "main.py",
    ]


def test_archive_is_reproducible(tmp_path: Path) -> None:
    root = project(tmp_path)
    os.utime(root / "main.py", (0, 1700000000))
    first, second, third = io.BytesIO(), io.BytesIO(), io.BytesIO()

    archive.write(root, first)
    archive.write(root, second)
    os.utime(root / "main.py", (0, 1800000000))
    archive.write(root, third)

    assert first.getvalue() == second.getvalue() != third.getvalue()

    with tarfile.open(fileobj=io.BytesIO(first.getvalue())) as tar:
        assert "study/app/static/logo.svg" in tar.getnames()
        assert tar.getmember("study/main.py").mtime == 1700000000
        assert all(info.uid == 0 for info in tar.getmembers())


def test_archive_streams_file_by_file(tmp_path: Path) -> None:
    root = project(tmp_path)
    written = io.BytesIO()
    archive.write(root, written)

    chunks = list(archive.chunks(root))

    assert len(chunks) > 1
    assert b"".join(chunks) == written.getvalue()


def test_archive_requires_gitignore(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert archive.available(root)

    (root / ".gitignore").unlink()
    assert not archive.available(root)


def test_archive_must_be_stored_outside_project(tmp_path: Path) -> None:
    root = project(tmp_path)

    assert archive.contains(root, root / "project.tar.gz")
    assert archive.contains(root, root / "build" / "project.tar.gz")
    assert archive.contains(root, tmp_path / "outside" / "project.tar.gz")
    assert archive.contains(root, root / ".." / "study" / "project.tar.gz")
    assert not archive.contains(root, tmp_path / "project.tar.gz")
