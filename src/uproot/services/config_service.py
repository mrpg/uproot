# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Configuration management service."""

from time import time
from typing import Any, cast

import httpx
from packaging.version import InvalidVersion, Version
from sortedcontainers import SortedDict

import uproot as u
import uproot.storage as s


def config_summary(cname: str) -> str:
    """Get a summary description for a configuration."""
    try:
        if cname.startswith("~"):
            return getattr(u.APPS[u.CONFIGS[cname][0]], "DESCRIPTION", "").strip()
        else:
            return " → ".join(u.CONFIGS[cname])
    except (KeyError, IndexError, TypeError):
        return ""


def displaystr(s: str) -> str:
    """Truncate a string for display."""
    s = s.strip()

    if len(s) > 128:
        s = s[:128] + "…"

    return s


def configs() -> dict[str, SortedDict[str, str]]:
    """Get all configurations organized by type."""
    return {
        "configs": SortedDict(
            {
                c: displaystr(config_summary(c))
                for c in u.CONFIGS
                if not c.startswith("~")
            }
        ),
        "apps": SortedDict(
            {c: displaystr(config_summary(c)) for c in u.CONFIGS if c.startswith("~")}
        ),
    }


def version_is_current(current: str, recommended: str) -> bool:
    """Return whether the running version meets the recommended version."""
    try:
        return Version(current) >= Version(recommended)
    except InvalidVersion:
        return False


async def announcements() -> dict[str, Any]:
    """Fetch announcements from the maintainers' server.

    The returned data is enriched with fields computed against the running
    version: "versionIsCurrent" and "versionAnnouncement" (or None).
    """
    ANNOUNCEMENTS_URL = "https://uproot.science/announcements.json"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(ANNOUNCEMENTS_URL)
            data = cast(dict[str, Any], response.json())
            recommended = str(data["recommendedVersion"])
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return {"error": True}

    with s.Admin() as admin:
        admin.announcements_queried = time()

    version_announcements = data.get("announcements")

    if not isinstance(version_announcements, dict):
        version_announcements = {}

    data["recommendedVersion"] = recommended
    data["versionIsCurrent"] = version_is_current(u.__version__, recommended)
    data["versionAnnouncement"] = version_announcements.get(u.__version__)

    return data


async def praise() -> str:
    """Fetch praise message."""
    PRAISE_URL = "https://uproot.science/praise/"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(PRAISE_URL)
            return response.text
    except Exception:  # noqa: BLE001
        return "We couldn't load praise right now."
