import asyncio
import logging

import uproot.jobs as j
from uproot.smithereens import spawn


def test_spawn_is_reexported_from_jobs():
    assert spawn is j.spawn


async def test_spawn_runs_to_completion():
    done = asyncio.Event()

    async def work() -> None:
        done.set()

    task = spawn(work())

    await asyncio.wait_for(done.wait(), timeout=1)
    await task
    await asyncio.sleep(0)  # let the done callback run

    assert task not in j.BACKGROUND_TASKS


async def test_spawn_keeps_reference_until_done():
    release = asyncio.Event()

    async def work() -> None:
        await release.wait()

    task = spawn(work())

    assert task in j.BACKGROUND_TASKS

    release.set()
    await task
    await asyncio.sleep(0)  # let the done callback run

    assert task not in j.BACKGROUND_TASKS


async def test_spawn_logs_exceptions(caplog):
    async def explode() -> None:
        raise ValueError("boom")

    with caplog.at_level(logging.ERROR, logger="uproot"):
        task = spawn(explode())
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)  # let the done callback run

    assert task not in j.BACKGROUND_TASKS
    assert any("explode" in record.message for record in caplog.records)
    assert any(
        isinstance(record.exc_info[1], ValueError)
        for record in caplog.records
        if record.exc_info
    )


async def test_spawn_cancellation_is_not_logged(caplog):
    async def forever() -> None:
        await asyncio.Event().wait()

    with caplog.at_level(logging.ERROR, logger="uproot"):
        task = spawn(forever())
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)  # let the done callback run

    assert task not in j.BACKGROUND_TASKS
    assert not caplog.records
