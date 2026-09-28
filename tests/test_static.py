import hashlib
import os

import pytest

import uproot.deployment as d
from uproot import i18n, pages
from uproot.pages import static_context, static_exists, static_search

EMPTY = hashlib.sha256(b"").hexdigest()[:16]  # version of an empty file


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "_static" / "img").mkdir(parents=True)
    (tmp_path / "myapp" / "_static" / "img").mkdir(parents=True)
    (tmp_path / "_static" / "img" / "both.png").touch()
    (tmp_path / "_static" / "project.css").touch()
    (tmp_path / "myapp" / "_static" / "img" / "both.png").touch()
    (tmp_path / "myapp" / "_static" / "app.js").touch()

    return tmp_path


def test_prefers_app_over_project(project):
    static = static_search("myapp", "_project")

    assert static("img/both.png") == f"{d.ROOT}/static/myapp/img/both.png?v={EMPTY}"
    assert static("app.js") == f"{d.ROOT}/static/myapp/app.js?v={EMPTY}"


def test_falls_back_to_project(project):
    static = static_search("myapp", "_project")

    assert static("project.css") == f"{d.ROOT}/static/_project/project.css?v={EMPTY}"


@pytest.mark.parametrize("realm", ["myapp", "_project"])
def test_static_url_encodes_filename_with_special_characters(project, realm):
    directory = project if realm == "_project" else project / realm
    filename = "img/a file+%20#é.txt"
    (directory / "_static" / filename).write_text("correct asset", encoding="utf-8")
    url = static_search("myapp", "_project")(filename)

    assert url.startswith(
        f"{d.ROOT}/static/{realm}/img/a%20file%2B%2520%23%C3%A9.txt?v="
    )


def test_missing_file_links_to_first_realm(project):
    static = static_search("myapp", "_project")

    assert static("missing.txt") == f"{d.ROOT}/static/myapp/missing.txt"


def test_directories_are_not_files(project):
    static = static_search("myapp", "_project")

    (project / "myapp" / "_static" / "dir").mkdir()
    (project / "_static" / "dir").touch()

    assert static("dir") == f"{d.ROOT}/static/_project/dir?v={EMPTY}"


def test_follows_symlinks(project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "linked.js").touch()
    (outside / "dir").mkdir()
    (outside / "dir" / "nested.js").touch()
    (project / "myapp" / "_static" / "linked.js").symlink_to(outside / "linked.js")
    (project / "myapp" / "_static" / "linkdir").symlink_to(outside / "dir")
    static = static_search("myapp", "_project")

    assert static("linked.js") == f"{d.ROOT}/static/myapp/linked.js?v={EMPTY}"
    assert (
        static("linkdir/nested.js")
        == f"{d.ROOT}/static/myapp/linkdir/nested.js?v={EMPTY}"
    )


def test_broken_symlink_is_skipped(project):
    (project / "myapp" / "_static" / "project.css").symlink_to(project / "nowhere")
    static = static_search("myapp", "_project")

    assert static("project.css") == f"{d.ROOT}/static/_project/project.css?v={EMPTY}"


def test_paths_escaping_realm_are_skipped(project):
    (project / "myapp" / "secret.txt").touch()

    assert static_exists("myapp", "img/../app.js")
    assert not static_exists("myapp", "../secret.txt")
    assert not static_exists("myapp", str(project / "myapp" / "secret.txt"))
    assert not static_exists("_project", "../myapp/secret.txt")


def test_context_without_app(project):
    context = static_context(None)

    assert "appstatic" not in context
    assert context["static"]("img/both.png") == (
        f"{d.ROOT}/static/_project/img/both.png?v={EMPTY}"
    )


def test_context_with_app(project):
    context = static_context("myapp")

    assert context["appstatic"]("x") == f"{d.ROOT}/static/myapp/x"
    assert (
        context["static"]("img/both.png")
        == f"{d.ROOT}/static/myapp/img/both.png?v={EMPTY}"
    )


@pytest.fixture
def internal(tmp_path, monkeypatch):
    """A stand-in for uproot's own _static directory."""
    monkeypatch.setattr(
        pages, "static_dir", lambda realm: tmp_path if realm == "_uproot" else None
    )
    (tmp_path / "script.js").write_text("function f() { return 1; }\n")

    return tmp_path


def build_minified(directory, source_text):
    sha256 = hashlib.sha256(source_text.encode()).hexdigest()
    (directory / "script.min.js").write_text(
        pages.MINIFIED_HEADER.format(sha256) + "\nfunction f(){return 1}\n"
    )


def test_minified_build_of_current_source_is_linked(internal):
    build_minified(internal, (internal / "script.js").read_text())

    assert "/script.min.js?v=" in pages.static_factory()("script.js")


def test_outdated_minified_build_is_ignored(internal):
    build_minified(internal, "function f() { return 0; }\n")

    assert "/script.js?v=" in pages.static_factory()("script.js")


def test_minified_build_without_header_is_ignored(internal):
    (internal / "script.min.js").write_text("function f(){return 1}\n")

    assert "/script.js?v=" in pages.static_factory()("script.js")


def test_edited_source_falls_back_to_full_script(internal):
    build_minified(internal, (internal / "script.js").read_text())
    (internal / "script.js").write_text("function f() { return 2; }\n")

    assert "/script.js?v=" in pages.static_factory()("script.js")


def test_same_size_asset_with_preserved_mtime_gets_new_version(project):
    path = project / "_static" / "project.css"
    path.write_bytes(b"old!")
    stamp = path.stat()
    before = pages.static_factory("_project")("project.css")

    path.write_bytes(b"new!")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    assert pages.static_factory("_project")("project.css") != before


def test_terms_version_tracks_content(monkeypatch):
    monkeypatch.setattr(i18n, "JSON", {"en": '{"key":"old"}'})
    before = pages.terms_url("en")
    i18n.JSON["en"] = '{"key":"new"}'

    assert pages.terms_url("en") != before


def test_stable_file_is_hashed_once(tmp_path, monkeypatch):
    path = tmp_path / "stable.css"
    path.write_bytes(b"body {}")
    now = pages.time.time_ns()
    monkeypatch.setattr(pages.time, "time_ns", lambda: now + 10**10)
    hashed = []
    monkeypatch.setattr(pages, "sha256", lambda p: hashed.append(p) or "x")

    pages.file_sha256(str(path))
    pages.file_sha256(str(path))

    assert len(hashed) == 1
