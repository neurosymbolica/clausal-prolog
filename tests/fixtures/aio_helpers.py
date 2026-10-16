"""Async adapters for tests/fixtures/aio_demo.seam (tests/test_aio.py)."""
from __future__ import annotations

import asyncio

from clausal.aio import async_predicate
from clausal.modules.py import to_text


async def _fetch(name, delay):
    await asyncio.sleep(delay)
    return f"{to_text(name)}-done"


fetch = async_predicate("fetch", _fetch, 3)


async def _ticks(n, delay):
    for i in range(n):
        await asyncio.sleep(delay)
        yield i


def ticks(n, delay):
    return _ticks(n, delay)


async def _boom(message):
    await asyncio.sleep(0)
    raise ValueError(to_text(message))


boom = async_predicate("boom", _boom, 2)


def _episode_depth():
    # Read in the query (synchronously), returned after an await.
    from clausal.logic import tabling
    depth = len(tabling._drive_ctx.episodes)

    async def later():
        await asyncio.sleep(0)
        return depth
    return later()


episode_depth = async_predicate("episode_depth", _episode_depth, 1)


async def _hang():
    # Wait on a future nothing holds but this coroutine: a query parked here,
    # INSIDE a tabled evaluation, is held only by a Task <-> Future cycle, so
    # dropping its task leaves it to the cyclic GC (tests/test_aio.py's
    # dropped-query tests: since D68 a query holding an ANSWER holds a
    # complete table, so an evaluating one has to be parked mid-evaluation).
    await asyncio.get_running_loop().create_future()


hang = async_predicate("hang", _hang, 1)


CLOSED = []


async def _closing_ticks():
    try:
        for i in range(10):
            await asyncio.sleep(0)
            yield i
    finally:
        CLOSED.append("closed")


def closing_ticks():
    return _closing_ticks()
