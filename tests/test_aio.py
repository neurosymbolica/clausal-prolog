"""clausal.aio: Clausal queries on an asyncio event loop.

Fixture: tests/fixtures/aio_demo.seam (library(asyncio) predicates and
async_predicate adapters from tests/fixtures/aio_helpers.py).
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from clausal.aio import aonce, asolve, await_only
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import once, solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "aio_demo.seam")


@pytest.fixture
def demo():
    return load_clausal_module(FIXTURE)


def run(coro):
    return asyncio.run(coro)


def _engine_state_clean():
    from clausal.logic import tabling
    return (not tabling._leader_ctx.stack and not tabling._leader_ctx.detached
            and not tabling._drive_ctx.episodes and tabling._spawn_ctx.depth == 0)


def _error_formal(exc):
    term = exc.term if hasattr(exc, "term") else exc.args[0]
    return term[1]


# ── concurrency ──────────────────────────────────────────────────────────

def test_concurrent_queries_overlap_their_waits(demo):
    async def main():
        rs = [Var() for _ in range(3)]
        t0 = time.perf_counter()
        await asyncio.gather(*(aonce(("job", f"q{i}", r), demo)
                               for i, r in enumerate(rs)))
        return [deref(r) for r in rs], time.perf_counter() - t0
    values, elapsed = run(main())
    assert values == ["q0-done", "q1-done", "q2-done"]
    assert elapsed < 0.45          # three 0.2 s waits, overlapped


def test_library_sleep_frees_the_loop(demo):
    async def main():
        beats = []

        async def heartbeat():
            for _ in range(4):
                beats.append(1)
                await asyncio.sleep(0.02)
        x = Var()
        await asyncio.gather(heartbeat(), aonce(("napped", x), demo))
        return deref(x), len(beats)
    assert run(main()) == ("done", 4)


# ── control constructs see awaits like any other call ────────────────────

def test_await_each_is_one_solution_per_item(demo):
    async def main():
        x, out = Var(), []
        async for _ in asolve(("ticked", x), demo):
            out.append(deref(x))
        return out
    assert run(main()) == [0, 1, 2]


def test_awaits_under_findall(demo):
    xs = Var()
    assert run(aonce(("all_ticks", xs), demo)) is not None
    assert deref(xs) == [0, 1, 2]


# once/1 and forall/2 (negation inside) run their goals in nested drive
# loops; built here, not in the fixture, so the transition-construct ratchet
# (tests/test_seam_transition_constructs.py) stays put.
@pytest.mark.parametrize("goal, expected", [
    (lambda x: ("once", ("ticked", x)), 0),
    (lambda x: ("forall", ("ticked", x), ("<", x, 3)), True),
    (lambda x: ("forall", ("ticked", x), ("<", x, 2)), False),
])
def test_awaits_under_once_and_forall(demo, goal, expected):
    x = Var()
    found = run(aonce(goal(x), demo))
    if expected is True or expected is False:
        assert (found is not None) is expected
    else:
        assert found is not None and deref(x) == expected


def test_an_awaited_exception_is_catchable(demo):
    r = Var()
    assert run(aonce(("safe", r), demo)) is not None
    assert deref(r) == ("ValueError", "bad")


def test_clausal_prolog_through_library_asyncio():
    naps = load_clausal_module(os.path.join(
        os.path.dirname(__file__), "fixtures", "aio_naps.clausal"))

    async def main():
        rs = [Var() for _ in range(4)]
        t0 = time.perf_counter()
        await asyncio.gather(*(aonce(("nap", f"n{i}", r), naps)
                               for i, r in enumerate(rs)))
        return [deref(r) for r in rs], time.perf_counter() - t0
    values, elapsed = run(main())
    assert values == [("done", f"n{i}") for i in range(4)]
    assert elapsed < 0.35          # four 0.1 s naps, overlapped


# ── synchronous drivers ──────────────────────────────────────────────────

def test_sync_query_blocks_on_a_private_loop(demo):
    r = Var()
    assert once(("job", "sync", r), demo) is not None
    assert deref(r) == "sync-done"
    x = Var()
    assert [deref(x) for _ in solve(("ticked", x), demo)] == [0, 1, 2]


def test_sync_query_on_a_running_loop_is_refused(demo):
    async def main():
        with pytest.raises(LogicException) as info:
            once(("napped", Var()), demo)
        return info.value
    formal = _error_formal(run(main()))
    assert formal[:3] == ("permission_error", "await", "synchronous_query")


def test_await_only_without_a_query():
    async def answer():
        return 42
    assert await_only(answer()) == 42


# ── tabling ──────────────────────────────────────────────────────────────

def test_concurrent_tabled_queries_keep_their_state_apart(demo):
    async def main():
        ys = [Var() for _ in range(3)]
        await asyncio.gather(*(aonce(("reach_after_nap", "a", y), demo)
                               for y in ys))
        return [sorted(deref(y)) for y in ys]
    assert run(main()) == [["a", "b", "c"]] * 3
    assert _engine_state_clean()


def test_each_query_sees_only_its_own_drive_episode(demo):
    # Three queries open their drive episodes, then all wait; on one shared
    # thread-local stack the last to resume would see three.
    async def main():
        ds = [Var() for _ in range(3)]
        await asyncio.gather(*(aonce(("depth_seen", d), demo) for d in ds))
        return [deref(d) for d in ds]
    assert run(main()) == [1, 1, 1]
    assert _engine_state_clean()


def test_waiting_inside_tabled_evaluation(demo):
    x = Var()
    assert run(aonce(("tabled_nap", x), demo)) is not None and deref(x) == 1
    assert _engine_state_clean()


def test_waiting_after_a_streaming_tabled_call(demo):
    async def main():
        y = Var()
        return sorted([deref(y) async for _ in asolve(("reach_then_nap", y), demo)])
    assert run(main()) == ["a", "b", "c"]


def _table_refusal(exc):
    formal = _error_formal(exc)
    return formal[:3] == ("permission_error", "access", "tabled_evaluation")


def test_a_table_another_query_is_building_is_refused_not_partial(demo):
    # Both queries reach tabled_nap/1's table; the second finds it still
    # being evaluated by the first (suspended in sleep/1) and must not see a
    # partial answer set (review 2026-10-06: it used to get no solution).
    async def main():
        xs = [Var(), Var()]
        return await asyncio.gather(
            *(aonce(("tabled_nap", x), demo) for x in xs), return_exceptions=True)
    first, second = run(main())
    assert first is not None and not isinstance(first, BaseException)
    assert isinstance(second, LogicException) and _table_refusal(second)
    x = Var()
    assert once(("tabled_nap", x), demo) is not None and deref(x) == 1
    assert _engine_state_clean()


def test_a_table_still_streaming_answers_is_exclusive(demo):
    # Query 1 has taken reach('a', Y)'s first answer; its table is still
    # evaluating.  Another query over the same table is refused, and query 1
    # still gets every answer (it used to lose two, silently).
    async def main():
        y = Var()
        agen = asolve(("reach", "a", y), demo)
        first = [deref(y) for _ in [await agen.__anext__()]]
        with pytest.raises(LogicException) as info:
            await aonce(("reach_count", Var()), demo)
        rest = [deref(y) async for _ in agen]
        return sorted(first + rest), info.value
    answers, refusal = run(main())
    assert answers == ["a", "b", "c"]
    assert _table_refusal(refusal)
    n = Var()
    assert once(("reach_count", n), demo) is not None and deref(n) == 3
    assert _engine_state_clean()


def test_sync_query_may_await_inside_tabled_evaluation(demo):
    x = Var()
    assert once(("tabled_nap", x), demo) is not None and deref(x) == 1


# ── cancellation and abandonment ─────────────────────────────────────────

def test_cancelling_unwinds_the_query_and_runs_cleanup(demo):
    async def main():
        task = asyncio.ensure_future(aonce(("guarded", Var()), demo))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    run(main())
    assert once("cleaned", demo) is not None
    assert _engine_state_clean()


def test_asyncio_timeout_bounds_a_query(demo):
    # docs/asyncio.md "Search control": a timeout is asyncio's, no predicate.
    async def main():
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.1):
                await aonce(("guarded", Var()), demo)
    run(main())
    assert once("cleaned", demo) is not None


def test_racing_queries_keeps_the_first_and_cancels_the_rest(demo):
    async def main():
        slow = asyncio.ensure_future(aonce(("job", "slow", Var()), demo))
        quick = asyncio.ensure_future(aonce(("napped", Var()), demo))
        done, pending = await asyncio.wait(
            {slow, quick}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return quick in done, slow.cancelled()
    assert run(main()) == (True, True)
    assert _engine_state_clean()


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_a_base_exception_at_a_wait_unwinds_the_query(demo, exc_type):
    # Review 2026-10-06: these used to surface as "generator already
    # executing" and leave the query's greenlet suspended.
    import gc
    import greenlet

    async def raiser():
        await asyncio.sleep(0)
        raise exc_type()

    async def main():
        await aonce(("await_value", raiser(), Var()), demo)
    with pytest.raises(exc_type):
        run(main())
    gc.collect()
    from clausal.aio import _QueryGreenlet
    assert not [g for g in gc.get_objects()
                if isinstance(g, _QueryGreenlet) and not g.dead]
    assert _engine_state_clean()


def test_await_each_closes_its_iterator_when_backtracking_stops(demo):
    from tests.fixtures import aio_helpers
    aio_helpers.CLOSED.clear()
    x = Var()
    assert run(aonce(("ticked_once", x), demo)) is not None and deref(x) == 0
    assert aio_helpers.CLOSED == ["closed"]


def test_the_private_loop_closes_with_its_thread(demo):
    import gc
    import threading
    import clausal.aio as aio
    seen = []

    def worker():
        once(("napped", Var()), demo)
        seen.append(aio._sync.loop)
    t = threading.Thread(target=worker)
    t.start()
    t.join()
    del t
    gc.collect()
    assert seen and seen[0].is_closed()


def test_abandoning_a_query_closes_it(demo):
    async def main():
        x = Var()
        gen = asolve(("ticked", x), demo)
        async for _ in gen:
            break
        await gen.aclose()
        return deref(x)
    assert run(main()) == 0
    assert _engine_state_clean()
