# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Set

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import uproot.deployment as d
from uproot.constraints import ensure


class ModuleManager:
    def __init__(self) -> None:
        self.modules: Dict[str, ModuleType] = {}
        self.watched_dirs: Dict[str, str] = {}
        self.watching_paths: Set[str] = set()
        self.observer = Observer()

    def __getitem__(self, module_name: str) -> Any:
        return self.modules[module_name]

    def __setitem__(self, module_name: str, module: Any) -> None:
        self.modules[module_name] = module

    def __delitem__(self, module_name: str) -> None:
        if module_name in sys.modules:
            del sys.modules[module_name]

        del self.modules[module_name]

    def __contains__(self, module_name: str) -> bool:
        return module_name in self.modules

    def start_watching(self) -> None:
        self.observer.start()

    def stop_watching(self) -> None:
        self.observer.stop()
        self.observer.join()

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

        spec = importlib.util.spec_from_file_location(module_name, module_file)

        ensure(
            spec is not None,
            ImportError,
            f"Could not create spec for module {module_name}",
        )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        sys.modules[module_name] = module
        self.modules[module_name] = module
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

            try:
                reloaded = importlib.reload(old_module)
                self.modules[module_name] = reloaded

                d.LOGGER.info(f"Reloaded {module_name}.")
            except Exception as e:
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
