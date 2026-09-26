import pytest

import uproot.deployment as d
from uproot.pages import static_context, static_exists, static_search


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

    assert static("img/both.png") == f"{d.ROOT}/static/myapp/img/both.png"
    assert static("app.js") == f"{d.ROOT}/static/myapp/app.js"


def test_falls_back_to_project(project):
    static = static_search("myapp", "_project")

    assert static("project.css") == f"{d.ROOT}/static/_project/project.css"


def test_missing_file_links_to_first_realm(project):
    static = static_search("myapp", "_project")

    assert static("missing.txt") == f"{d.ROOT}/static/myapp/missing.txt"


def test_directories_are_not_files(project):
    static = static_search("myapp", "_project")

    (project / "myapp" / "_static" / "dir").mkdir()
    (project / "_static" / "dir").touch()

    assert static("dir") == f"{d.ROOT}/static/_project/dir"


def test_follows_symlinks(project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "linked.js").touch()
    (outside / "dir").mkdir()
    (outside / "dir" / "nested.js").touch()
    (project / "myapp" / "_static" / "linked.js").symlink_to(outside / "linked.js")
    (project / "myapp" / "_static" / "linkdir").symlink_to(outside / "dir")
    static = static_search("myapp", "_project")

    assert static("linked.js") == f"{d.ROOT}/static/myapp/linked.js"
    assert static("linkdir/nested.js") == f"{d.ROOT}/static/myapp/linkdir/nested.js"


def test_broken_symlink_is_skipped(project):
    (project / "myapp" / "_static" / "project.css").symlink_to(project / "nowhere")
    static = static_search("myapp", "_project")

    assert static("project.css") == f"{d.ROOT}/static/_project/project.css"


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
        f"{d.ROOT}/static/_project/img/both.png"
    )


def test_context_with_app(project):
    context = static_context("myapp")

    assert context["appstatic"]("x") == f"{d.ROOT}/static/myapp/x"
    assert context["static"]("img/both.png") == f"{d.ROOT}/static/myapp/img/both.png"
