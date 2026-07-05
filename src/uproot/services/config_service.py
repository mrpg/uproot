# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Configuration management service."""

from time import time
from typing import Any, cast

import httpx
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
    except Exception:
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


async def announcements() -> dict[str, Any]:
    """Fetch announcements from the upstream repository."""
    ANNOUNCEMENTS_URL = "https://raw.githubusercontent.com/mrpg/uproot/refs/heads/main/announcements.json"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(ANNOUNCEMENTS_URL)
            data = cast(dict[str, Any], response.json())
    except Exception:
        return {"error": True}

    with s.Admin() as admin:
        admin.announcements_queried = time()

    return data


async def praise() -> str:
    """Fetch praise message."""
    PRAISE_URL = "https://uproot.science/praise/"

    async with httpx.AsyncClient() as client:
        response = await client.get(PRAISE_URL)
        return response.text
