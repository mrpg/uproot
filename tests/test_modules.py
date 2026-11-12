import sys
from pathlib import Path

import pytest
from watchdog.events import FileMovedEvent

from uproot.modules import ModuleFileHandler, ModuleManager


def write_app(app_dir: Path, source: str) -> None:
    app_dir.mkdir(exist_ok=True)
    (app_dir / "__init__.py").write_text(source, encoding="utf-8")


def test_reload_module_removes_deleted_names(tmp_path: Path) -> None:
    app_dir = tmp_path / "reload_app"
    write_app(app_dir, "kept = 1\nremoved = 2\n")

    manager = ModuleManager()
    try:
        old_module = manager.import_module(str(app_dir))

        write_app(app_dir, "kept = 3\n")
        manager.reload_module("reload_app")

        new_module = manager["reload_app"]

        assert new_module is not old_module
        assert new_module.kept == 3
        assert not hasattr(new_module, "removed")

        with pytest.raises(RuntimeError, match="has been reloaded"):
            assert old_module.kept

        with pytest.raises(RuntimeError, match="has been reloaded"):
            assert old_module.removed
    finally:
        sys.modules.pop("reload_app", None)


def test_reload_module_keeps_old_module_when_reload_fails(tmp_path: Path) -> None:
    app_dir = tmp_path / "reload_failure_app"
    write_app(app_dir, "kept = 1\nremoved = 2\n")

    manager = ModuleManager()
    try:
        old_module = manager.import_module(str(app_dir))

        write_app(app_dir, "kept =\n")
        manager.reload_module("reload_failure_app")

        assert manager["reload_failure_app"] is old_module
        assert sys.modules["reload_failure_app"] is old_module
        assert old_module.kept == 1
        assert old_module.removed == 2
    finally:
        sys.modules.pop("reload_failure_app", None)


def test_atomic_save_reloads_module(tmp_path: Path) -> None:
    app_dir = tmp_path / "atomic_save_app"
    write_app(app_dir, "value = 1\n")

    manager = ModuleManager()
    try:
        manager.import_module(str(app_dir))

        # Editors that save atomically move a temporary file over the original.
        # The new source has the same size and likely the same mtime (in seconds).
        temporary = app_dir / "__init__.py.tmp"
        temporary.write_text("value = 2\n", encoding="utf-8")
        temporary.replace(app_dir / "__init__.py")
        ModuleFileHandler(manager).on_moved(
            FileMovedEvent(str(temporary), str(app_dir / "__init__.py"))
        )

        assert manager["atomic_save_app"].value == 2
    finally:
        sys.modules.pop("atomic_save_app", None)
