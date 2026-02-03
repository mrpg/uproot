# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Configuration management service."""

from typing import Any, cast

import aiohttp
from sortedcontainers import SortedDict

import uproot as u


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
    return dict(
        configs=SortedDict(
            {
                c: displaystr(config_summary(c))
                for c in u.CONFIGS
                if not c.startswith("~")
            }
        ),
        apps=SortedDict(
            {c: displaystr(config_summary(c)) for c in u.CONFIGS if c.startswith("~")}
        ),
    )


async def announcements() -> dict[str, Any]:
    """Fetch announcements from the upstream repository."""
    ANNOUNCEMENTS_URL = "https://raw.githubusercontent.com/mrpg/uproot/refs/heads/main/announcements.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(ANNOUNCEMENTS_URL) as response:
            return cast(dict[str, Any], await response.json(content_type="text/plain"))


async def praise() -> str:
    """Fetch praise message."""
    PRAISE_URL = "https://max.pm/praise/uproot/"

    async with aiohttp.ClientSession() as session:
        async with session.get(PRAISE_URL) as response:
            return await response.text()
