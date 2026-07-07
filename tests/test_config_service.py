from contextlib import asynccontextmanager

import httpx

from uproot.services import config_service


async def test_praise_returns_fallback_on_network_error(monkeypatch):
    @asynccontextmanager
    async def raising_client():
        raise httpx.ConnectError("offline")
        yield

    monkeypatch.setattr(config_service.httpx, "AsyncClient", raising_client)

    assert await config_service.praise() == "We couldn't load praise right now."
