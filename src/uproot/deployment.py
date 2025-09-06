# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import logging
import os
from typing import TYPE_CHECKING, Any

import uproot.drivers
from uproot.i18n import ISO639

if TYPE_CHECKING:
    from uproot.rooms import RoomType

HOST: str
PORT: int
ADMINS: dict[str, str] = dict()
DEFAULT_ROOMS: list["RoomType"] = list()
FIRST_RUN: bool = False
PATH: str = os.getcwd()
TIMEOUT_TOLERANCE: float = 1.0
LANGUAGE: ISO639 = "en"
PROJECT_METADATA: dict[str, Any] = dict()
SKIP_INTERNAL: bool = True
UVICORN_KWARGS: dict[str, Any] = dict(
    reload=False,  # auto-reloading is handled by uproot itself
    # ~ log_level="critical",
    log_level="info",
)

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("uproot")

TBLEXTRA = os.getenv("UPROOT_TBLEXTRA", "")
DBENV = os.getenv("UPROOT_DATABASE", "sqlite3")
UNAVAILABLE_EQUIVALENT: str = "null"
DATABASE: uproot.drivers.DBDriver

if DBENV == "sqlite3":
    DATABASE = uproot.drivers.Sqlite3(
        os.getenv("UPROOT_SQLITE3", "uproot.sqlite3"), TBLEXTRA
    )
elif DBENV == "memory":
    DATABASE = uproot.drivers.Memory()
    # LOGGER.warning("Using Memory() database driver. Data will not persist.")
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


async def lifespan_start(*args, **kwargs) -> None:
    pass


async def lifespan_stop(*args, **kwargs) -> None:
    pass
