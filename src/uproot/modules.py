# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import uproot.deployment as d
from uproot.constraints import ensure


def noop(module: Any) -> None:
    pass


def poison_module(module: ModuleType) -> None:
    module_name = module.__name__

    def fail_access(name: str) -> Any:
        raise RuntimeError(
            f"Module {module_name!r} has been reloaded; use the current module instead"
        )

    module.__dict__.clear()
    module.__dict__.update(
        {
            "__doc__": f"Stale module object for {module_name!r}.",
            "__getattr__": fail_access,
            "__name__": module_name,
            "__package__": module_name.rpartition(".")[0],
        }
    )


class ModuleManager:
    def __init__(self, hook: Callable[[Any], None] | None = None) -> None:
        self.modules: dict[str, ModuleType] = {}
        self.watched_dirs: dict[str, str] = {}
        self.watching_paths: set[str] = set()
        self.observer = Observer()

        if hook is not None:
            self.hook = hook
        else:
            self.hook = noop

    def __getitem__(self, module_name: str) -> Any:
        return self.modules[module_name]

    def __setitem__(self, module_name: str, module: Any) -> None:
        self.modules[module_name] = module
        self.hook(self.modules[module_name])

    def __delitem__(self, module_name: str) -> None:
        if module_name in sys.modules:
            del sys.modules[module_name]

        del self.modules[module_name]

    def __contains__(self, module_name: str) -> bool:
        return module_name in self.modules

    def start_watching(self) -> None:
        try:
            self.observer.start()
        except OSError:
            d.LOGGER.warning(
                "Cannot watch for changes in apps; do you have a lot of apps?"
            )

    def stop_watching(self) -> None:
        self.observer.stop()
        self.observer.join()

    def load_module(self, module_name: str, module_file: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(module_name, module_file)

        ensure(
            spec is not None,
            ImportError,
            f"Could not create spec for module {module_name}",
        )

        if spec is not None:
            module = importlib.util.module_from_spec(spec)
        else:
            raise ImportError(f"Spec is None for module {module_name}")

        previous_module = sys.modules.get(module_name)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception:
            if previous_module is None:
                del sys.modules[module_name]
            else:
                sys.modules[module_name] = previous_module
            raise

        return module

    def import_module(self, module_dir: str) -> Any:
        path = Path(module_dir)
        module_name = path.name

        if not path.exists():
            raise FileNotFoundError(f"Module directory {module_dir} not found")

        init_file = path / "__init__.py"
        main_file = path / f"{module_name}.py"

        module_file = init_file if init_file.exists() else main_file

        if not module_file.exists():
            raise FileNotFoundError(f"No module file found in {module_dir}")

        module = self.load_module(module_name, module_file)
        self[module_name] = module
        self.watched_dirs[str(path)] = module_name
        self.watched_dirs[str(path.resolve())] = module_name

        if str(path) not in self.watching_paths:
            handler = ModuleFileHandler(self)
            real_path = str(path.resolve())
            self.observer.schedule(handler, real_path, recursive=True)
            self.watching_paths.add(str(path))

        return module

    def reload_module(self, module_name: str) -> None:
        if module_name in self.modules:
            old_module = self.modules[module_name]
            module_file = getattr(old_module, "__file__", None)

            try:
                if not isinstance(module_file, str):
                    raise TypeError(
                        f"Could not find source file for module {module_name}"
                    )

                reloaded = self.load_module(module_name, Path(module_file))
                self[module_name] = reloaded
                poison_module(old_module)

                d.LOGGER.info(f"Reloaded {module_name}.")
            except Exception as e:  # noqa: BLE001
                d.LOGGER.info(f"Failed to reload {module_name}: {e}")


class ModuleFileHandler(FileSystemEventHandler):
    def __init__(self, manager: ModuleManager):
        self.manager = manager

    def on_modified(self, event: Any) -> None:
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        if file_path.suffix == ".py":
            module_dir = str(file_path.parent)

            if module_dir in self.manager.watched_dirs:
                module_name = self.manager.watched_dirs[module_dir]
                self.manager.reload_module(module_name)
