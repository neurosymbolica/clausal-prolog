"""clausal.aio — run Clausal queries on an asyncio event loop.

``asolve`` is the async twin of ``clausal.logic.solve.solve``: an async
generator that yields the trail once per solution and lets the event loop run
other tasks whenever the query is waiting on I/O::

    from clausal.aio import asolve, aonce

    async for _ in asolve(("fetch_all", urls, X), module):
        print(deref(X))

    await asyncio.gather(aonce(goal1, m), aonce(goal2, m))   # concurrent queries

A predicate waits by calling ``await_only(awaitable)`` from ordinary
synchronous code.  Under ``asolve`` that suspends the query and awaits on the
running loop; under plain ``solve`` (no loop running) it runs the awaitable to
completion on a private loop and blocks.  So whether a predicate is "async" is
decided by how the query is driven, never by the program: ``library(asyncio)``
(``await_value/2``, ``await_each/2``, ``sleep/1``) and any adapter built with
``async_predicate`` work under both.

How: the query runs in a greenlet (SQLAlchemy's ``greenlet_spawn`` /
``await_only`` pattern).  ``await_only`` switches to the greenlet running the
asyncio task, which awaits and switches back with the result.  Any depth of
synchronous engine code sits between the two unchanged — nested drive loops,
``findall``, negation, the C trampoline — which is why no engine path had to
learn about awaiting.  ``greenlet`` is a core dependency (operator ruling
2026-10-06: async is built in, not an optional extra).

Semantics:

- Each query has its own trail.  Queries interleave only at awaits
  (cooperative), so between two awaits a query runs alone.
- The database is shared: an ``assertz`` by one query is visible to another
  after its next await.
- Backtracking into a goal re-runs it, awaits included; ``await_each/2`` turns
  an async iterator into one solution per item.
- An awaitable that raises surfaces as an ordinary error term, catchable with
  ``catch/3``.  Cancelling the task raises ``CancelledError`` inside the
  query, which unwinds it (``setup_call_cleanup`` cleanups run).
- Tabled evaluation may not await under ``asolve`` (``permission_error(await,
  tabled_evaluation, _)``): SLG completion assumes one search at a time, and an
  incomplete table seen by an interleaved query would be wrong.  Per-query
  tabling state (leader stack, drive episodes) is kept apart regardless.
"""
from __future__ import annotations

import asyncio
import inspect
import threading

import greenlet as _greenlet

from clausal.logic.exceptions import LogicException, permission_error
from clausal.logic.solve import solve
from clausal.logic.variables import deref, unify

__all__ = ["asolve", "aonce", "await_only", "async_predicate"]


class _QueryGreenlet(_greenlet.greenlet):
    """The greenlet a query runs in: ``await_only`` may switch out."""


def _in_query_greenlet():
    return type(_greenlet.getcurrent()) is _QueryGreenlet


# ── per-query engine state ───────────────────────────────────────────────
#
# Tabling keeps its leader stack, drive episodes and spawn depth in
# thread-locals.  Interleaved queries share a thread, so each query carries
# its own copy and installs it while it runs.

def _engine_locals():
    from clausal.logic import tabling
    return (tabling._leader_ctx, tabling._drive_ctx, tabling._spawn_ctx)


def _fresh_state():
    return [dict(type(local)().__dict__) for local in _engine_locals()]


def _install(state):
    """Install *state* into the engine thread-locals; return what was there."""
    previous = []
    for local, d in zip(_engine_locals(), state):
        previous.append(dict(local.__dict__))
        local.__dict__.clear()
        local.__dict__.update(d)
    return previous


def _in_tabled_evaluation():
    from clausal.logic import tabling
    return bool(tabling._leader_ctx.stack or tabling._leader_ctx.detached
                or tabling._spawn_ctx.depth)


# ── await_only ───────────────────────────────────────────────────────────

_sync = threading.local()


def _sync_loop():
    """The private loop a synchronous query awaits on (one per thread).

    Kept for the thread's life rather than one ``asyncio.run`` per await:
    ``asyncio.run`` finalises every async generator it touched, which would
    end an ``await_each`` iterator after its first item.
    """
    loop = getattr(_sync, "loop", None)
    if loop is None or loop.is_closed():
        loop = _sync.loop = asyncio.new_event_loop()
    return loop


async def _as_coroutine(awaitable):
    return await awaitable


def _discard(awaitable):
    if inspect.iscoroutine(awaitable):
        awaitable.close()


def await_only(awaitable):
    """Wait for *awaitable* from synchronous code and return its result.

    Under ``asolve`` the query is suspended and the event loop awaits it; in a
    plain synchronous query it runs on a private loop and blocks.  Raises
    whatever the awaitable raises.
    """
    if _in_query_greenlet():
        if _in_tabled_evaluation():
            _discard(awaitable)
            raise LogicException(permission_error(
                "await", "tabled_evaluation", awaitable, "await_only/1"))
        current = _greenlet.getcurrent()
        kind, value = current.parent.switch(("await", awaitable))
        if kind == "err":
            raise value
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _sync_loop().run_until_complete(_as_coroutine(awaitable))
    _discard(awaitable)
    raise LogicException(permission_error(
        "await", "synchronous_query", awaitable, "await_only/1"))


# ── asolve / aonce ───────────────────────────────────────────────────────

class _Query:
    """One query: its solve generator, engine state and current greenlet."""

    __slots__ = ("gen", "state")

    def __init__(self, gen):
        self.gen, self.state = gen, _fresh_state()

    def _run(self, fn, first):
        """Run *fn* in a query greenlet until it finishes or awaits."""
        child = _QueryGreenlet(fn)
        child.gr_context = _greenlet.getcurrent().gr_context
        return child, self._switch(child.switch, first)

    def _switch(self, how, *args):
        saved = _install(self.state)
        try:
            return how(*args)
        finally:
            self.state = _install(saved)

    async def step(self, fn):
        """Run *fn* to completion in a greenlet, awaiting what it asks for."""
        child, msg = self._run(fn, None)
        while msg[0] == "await":
            try:
                result = await msg[1]
            except asyncio.CancelledError as exc:
                msg = self._switch(child.throw, exc)
                continue
            except Exception as exc:  # noqa: BLE001 - delivered to the query
                msg = self._switch(child.switch, ("err", exc))
            else:
                msg = self._switch(child.switch, ("ok", result))
        return msg

    def next_solution(self, _):
        try:
            return ("sol", next(self.gen))
        except StopIteration:
            return ("end", None)

    def close(self, _):
        self.gen.close()
        return ("end", None)


async def asolve(goal, module=None, trail=None):
    """``async for trail in asolve(goal, module)``: solve on the event loop.

    Takes the same arguments as ``solve``.  The query yields to the event loop
    at every ``await_only``; between awaits it runs synchronously.
    """
    query = _Query(solve(goal, module, trail))
    try:
        while True:
            kind, value = await query.step(query.next_solution)
            if kind == "end":
                return
            yield value
    finally:
        # Close inside the query's greenlet and engine state, so the solve
        # generator's own cleanup (tabling episode repair, cleanup handlers)
        # runs where it would have run synchronously.
        await query.step(query.close)


async def aonce(goal, module=None, trail=None):
    """The first solution's trail, or ``None`` — the async twin of ``once``."""
    gen = asolve(goal, module, trail)
    try:
        async for found in gen:
            return found
        return None
    finally:
        await gen.aclose()


# ── adapters ─────────────────────────────────────────────────────────────

def async_predicate(name, fn, arity):
    """A predicate over an ``async def``: ``fn(*inputs)`` -> awaitable.

    The predicate has *arity* arguments; the first ``arity - 1`` are passed
    to *fn* dereferenced, and the awaited result is unified with the last::

        async def _get(url): ...
        get = async_predicate("get", _get, 2)       # get(Url, Body)

    Convert text inside *fn* (``clausal.modules.py.to_text``): a string
    argument arrives as the chars carrier, not a ``str``.
    """
    from clausal.modules.py import ModulePredicate, simple_to_trampoline

    def simple(*args):
        *inputs, result, trail, _k = args
        value = await_only(fn(*(deref(a) for a in inputs)))
        if unify(result, value, trail):
            yield None

    pred = ModulePredicate(name)
    pred._register(arity, simple_to_trampoline(simple))
    return pred
