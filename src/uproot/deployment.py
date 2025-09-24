# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import logging
import os
from typing import TYPE_CHECKING, Any

import uproot.drivers
from uproot.i18n import ISO639

if TYPE_CHECKING:
    from uproot.rooms import RoomType

logging.basicConfig(level=logging.INFO)

ADMINS: dict[str, str] = dict()
API_KEYS: set[str] = set()
DATABASE: uproot.drivers.DBDriver = uproot.drivers.Memory()
DBENV: str = os.getenv("UPROOT_DATABASE", "sqlite3")
DEFAULT_ROOMS: list["RoomType"] = list()
HOST: str = "127.0.0.1"
LANGUAGE: ISO639 = "en"
LOGGER: Any = logging.getLogger("uproot")
PATH: str = os.getcwd()
PORT: int = 8000
PROJECT_METADATA: dict[str, Any] = dict()
TBLEXTRA: str = os.getenv("UPROOT_TBLEXTRA", "")
TIMEOUT_TOLERANCE: float = 1.0
UNAVAILABLE_EQUIVALENT: str = "null"
UVICORN_KWARGS: dict[str, Any] = dict(
    reload=False,
    log_level="info",
)

if DBENV == "sqlite3":
    DATABASE = uproot.drivers.Sqlite3(
        os.getenv("UPROOT_SQLITE3", "uproot.sqlite3"), TBLEXTRA
    )
elif DBENV == "memory":
    pass
    LOGGER.warning("Using 'memory' database driver. Data will not persist.")
elif DBENV == "postgresql":
    DATABASE = uproot.drivers.PostgreSQL(os.getenv("UPROOT_POSTGRESQL", ""), TBLEXTRA)
else:
    raise NotImplementedError(f"Invalid UPROOT_DATABASE environment variable: {DBENV}")


if os.getenv("UPROOT_SUBDIRECTORY", None) is None:
    ROOT = ""
else:
    ROOT = "/" + os.getenv("UPROOT_SUBDIRECTORY", "").strip("/")


def project_metadata(uproot: str, *args: Any, **kwargs: Any) -> None:
    """This function intends to check for incompatibilities in the future."""
    global PROJECT_METADATA

    PROJECT_METADATA |= dict(uproot=uproot)
    PROJECT_METADATA |= kwargs


async def lifespan_start(*args: Any, **kwargs: Any) -> None:
    pass


async def lifespan_stop(*args: Any, **kwargs: Any) -> None:
    DATABASE.close()
