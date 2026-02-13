# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import atexit
import logging
import os
import secrets
from types import EllipsisType
from typing import TYPE_CHECKING, Any, Optional

import appendmuch

from uproot.i18n import ISO639

if TYPE_CHECKING:
    from uproot.rooms import RoomType

logging.basicConfig(level=logging.INFO)

ADMINS: dict[str, str | EllipsisType] = {}
API_KEYS: set[str] = set()

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

DEFAULT_ROOMS: list["RoomType"] = []
HERE_TOLERANCE: float = 5.0
HOST: str = "127.0.0.1"
LANGUAGE: ISO639 = "en"
LOGIN_TOKEN: Optional[str] = None
LOGGER: Any = logging.getLogger("uproot")
NO_ENTER: bool = False
ORIGIN: Optional[str] = os.getenv("UPROOT_ORIGIN")

# Auto-detect Heroku app URL if not explicitly set
if ORIGIN is None:
    if heroku_domain := os.getenv("HEROKU_APP_DEFAULT_DOMAIN_NAME"):
        ORIGIN = f"https://{heroku_domain}"

PATH: str = os.getcwd()
PORT: int = 8000
PROJECT_METADATA: dict[str, Any] = {}
PUBLIC_DEMO: bool = False
TBLEXTRA: str = os.getenv("UPROOT_TBLEXTRA", "")
TIMEOUT_TOLERANCE: float = 1.0
UNAVAILABLE_EQUIVALENT: str = "null"
UNSAFE: bool = False
UVICORN_KWARGS: dict[str, Any] = {
    "reload": False,
    "log_level": "info",
}

# Import uproot codec (registers uproot-specific types)
from uproot.stable import CODEC  # noqa: E402


def uproot_replace_predicate(namespace: str, field: str) -> bool:
    return field == "players" and namespace.startswith("session/")


def uproot_on_change(
    namespace: tuple[str, ...], field: str, value: appendmuch.Value
) -> None:
    if namespace[0] in ("session", "player", "group", "model"):
        from uproot.events import set_fieldchange

        set_fieldchange(namespace, field, value)


def uproot_namespace_validator(namespace: tuple[str, ...]) -> bool:
    return namespace[0] in ("admin", "session", "player", "group", "model")


# Create the driver
if DBENV == "sqlite3":
    driver: appendmuch.DBDriver = appendmuch.Sqlite3(
        os.getenv("UPROOT_SQLITE3", "uproot.sqlite3"),
        table_prefix="uproot",
        tblextra=TBLEXTRA,
        replace_index_specs=[("players", "session/%")],
    )
elif DBENV == "memory":
    LOGGER.warning("Using 'memory' database driver. Data will not persist.")
    driver = appendmuch.Memory()
elif DBENV == "postgresql":
    pg_url = os.getenv("UPROOT_POSTGRESQL", "") or os.getenv("DATABASE_URL", "")
    driver = appendmuch.PostgreSQL(
        pg_url,
        table_prefix="uproot",
        tblextra=TBLEXTRA,
        replace_index_specs=[("players", "session/%")],
    )
else:
    raise NotImplementedError(f"Invalid UPROOT_DATABASE environment variable: {DBENV}")

# Create the Store
STORE = appendmuch.Store(
    driver,
    codec=CODEC,
    replace_predicate=uproot_replace_predicate,
    on_change=uproot_on_change,
    namespace_validator=uproot_namespace_validator,
)

# Backward compatibility
DATABASE = STORE.driver

# Wire up the cache compatibility layer
import uproot.cache  # noqa: E402

uproot.cache.set_store(STORE)


if os.getenv("UPROOT_SUBDIRECTORY", None) is None:
    ROOT = ""
else:
    ROOT = "/" + os.getenv("UPROOT_SUBDIRECTORY", "").strip("/")


def project_metadata(uproot: str, *args: Any, **kwargs: Any) -> None:
    """This function intends to check for incompatibilities in the future."""
    global PROJECT_METADATA

    PROJECT_METADATA |= {"uproot": uproot}
    PROJECT_METADATA |= kwargs


def ensure_login_token() -> None:
    global LOGIN_TOKEN

    if LOGIN_TOKEN is None:
        LOGIN_TOKEN = secrets.token_urlsafe()


async def lifespan_start(*args: Any, **kwargs: Any) -> None:
    pass


async def lifespan_stop(*args: Any, **kwargs: Any) -> None:
    DATABASE.close()


# Ensure database is properly closed on program exit to flush any pending writes
atexit.register(DATABASE.close)
