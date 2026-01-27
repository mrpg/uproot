# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import atexit
import logging
import os
import secrets
from types import EllipsisType
from typing import TYPE_CHECKING, Any, Optional

import uproot.drivers
from uproot.i18n import ISO639

if TYPE_CHECKING:
    from uproot.rooms import RoomType

logging.basicConfig(level=logging.INFO)

ADMINS: dict[str, str | EllipsisType] = dict()
API_KEYS: set[str] = set()
DATABASE: uproot.drivers.DBDriver = uproot.drivers.Memory()

# Auto-detect PostgreSQL on Heroku (DATABASE_URL is set by Heroku Postgres addon)
DBENV: str
if not os.getenv("UPROOT_DATABASE"):
    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith(("postgres://", "postgresql://")):
        DBENV = "postgresql"
    else:
        DBENV = "sqlite3"
else:
    DBENV = os.getenv("UPROOT_DATABASE", "sqlite3")

DEFAULT_ROOMS: list["RoomType"] = list()
HERE_TOLERANCE: float = 5.0
HOST: str = "127.0.0.1"
LANGUAGE: ISO639 = "en"
LOGIN_TOKEN: Optional[str] = None
LOGGER: Any = logging.getLogger("uproot")
ORIGIN: Optional[str] = os.getenv("UPROOT_ORIGIN")

# Auto-detect Heroku app URL if not explicitly set
if ORIGIN is None:
    if heroku_domain := os.getenv("HEROKU_APP_DEFAULT_DOMAIN_NAME"):
        # Dyno metadata provides the exact domain (requires `heroku labs:enable runtime-dyno-metadata`)
        ORIGIN = f"https://{heroku_domain}"

PATH: str = os.getcwd()
PORT: int = 8000
PROJECT_METADATA: dict[str, Any] = dict()
TBLEXTRA: str = os.getenv("UPROOT_TBLEXTRA", "")
TIMEOUT_TOLERANCE: float = 1.0
UNAVAILABLE_EQUIVALENT: str = "null"
UNSAFE: bool = False
UVICORN_KWARGS: dict[str, Any] = dict(
    reload=False,
    log_level="info",
)

if DBENV == "sqlite3":
    DATABASE = uproot.drivers.Sqlite3(
        os.getenv("UPROOT_SQLITE3", "uproot.sqlite3"), TBLEXTRA
    )
elif DBENV == "memory":
    LOGGER.warning("Using 'memory' database driver. Data will not persist.")
elif DBENV == "postgresql":
    # Use DATABASE_URL (Heroku standard) if UPROOT_POSTGRESQL is not set
    pg_url = os.getenv("UPROOT_POSTGRESQL", "") or os.getenv("DATABASE_URL", "")
    DATABASE = uproot.drivers.PostgreSQL(pg_url, TBLEXTRA)
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


def ensure_login_token() -> None:
    # Callers must ensure any conditions are met
    global LOGIN_TOKEN

    if LOGIN_TOKEN is None:
        LOGIN_TOKEN = secrets.token_urlsafe()


async def lifespan_start(*args: Any, **kwargs: Any) -> None:
    pass


async def lifespan_stop(*args: Any, **kwargs: Any) -> None:
    DATABASE.close()


# Ensure database is properly closed on program exit to flush any pending writes
atexit.register(DATABASE.close)
