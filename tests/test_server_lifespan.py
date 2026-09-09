import asyncio

import pytest

from uproot import server


async def test_finish_cancelled_tasks_ignores_cancellation() -> None:
    async def wait_forever() -> None:
        await asyncio.Event().wait()

    task = asyncio.create_task(wait_forever())
    await asyncio.sleep(0)
    task.cancel()

    await server.finish_cancelled_tasks([task])


async def test_finish_cancelled_tasks_reraises_failures() -> None:
    error = RuntimeError("global job failed")

    async def fail() -> None:
        raise error

    task = asyncio.create_task(fail())

    with pytest.raises(RuntimeError, match="global job failed") as excinfo:
        await server.finish_cancelled_tasks([task])

    assert excinfo.value is error
