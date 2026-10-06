"""clausal.modules.py.asyncio — awaiting from Clausal queries.

Predicates that wait on Python awaitables.  Under ``clausal.aio.asolve`` a
wait suspends the query and frees the event loop for other tasks; under plain
``solve`` (the CLI, the REPL, ``once``) it blocks.  The program is the same
either way.  Import via::

    -import_from(py.asyncio, [await_value, await_each, sleep])

or, from Clausal Prolog, ``:- use_module(library(asyncio)).``

- ``await_value(Awaitable, Value)`` — await a coroutine, task or future and
  unify its result with *Value*.
- ``await_each(AsyncIterable, Item)`` — nondeterministic: one solution per item
  of an async iterator, awaited lazily as backtracking asks for the next.
- ``sleep(Seconds)`` — ``asyncio.sleep``: other queries run meanwhile.

An awaitable that raises surfaces as an error term, catchable with
``catch/3``.  See ``clausal.aio`` for the driver and its semantics.
"""

from __future__ import annotations

from clausal.aio import _in_query_greenlet, await_only
from clausal.modules.py import (
    NUMBER_TYPES,
    ModulePredicate,
    _import_stdlib,
    expect_type,
    simple_to_trampoline,
)
from clausal.logic.variables import deref, unify

_asyncio = _import_stdlib("asyncio")
_inspect = _import_stdlib("inspect")


def _await_value_2(awaitable, value, trail, k):
    """await_value/2: await_value(Awaitable, Value)."""
    aw = deref(awaitable)
    if not _inspect.isawaitable(aw):
        expect_type(aw, (), "await_value/2", type_name="awaitable", arg=1)
    if unify(value, await_only(aw), trail):
        yield None


def _await_each_2(iterable, item, trail, k):
    """await_each/2: await_each(AsyncIterable, Item) — one solution per item."""
    source = deref(iterable)
    if not hasattr(source, "__aiter__"):
        expect_type(source, (), "await_each/2", type_name="async_iterable", arg=1)
    iterator = source.__aiter__()
    exhausted = False
    try:
        while True:
            try:
                value = await_only(iterator.__anext__())
            except StopAsyncIteration:
                exhausted = True
                return
            mark = trail.mark()
            if unify(item, value, trail):
                yield None
            trail.undo(mark)
    finally:
        if not exhausted:
            _close_iterator(iterator)


def _close_iterator(iterator):
    """Release an async iterator backtracking stopped pulling from early.

    In a query that can wait, wait for ``aclose()``, so a cursor or socket is
    released before the query moves on.  This can also run when an abandoned
    query's frames are finalised outside any query, on a running loop that
    must not block: leave the iterator to asyncio's own async-generator
    finaliser then, which closes it on that loop.
    """
    aclose = getattr(iterator, "aclose", None)
    if aclose is None:
        return
    try:
        if not _in_query_greenlet():
            try:
                _asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                return
        await_only(aclose())
    except Exception:  # noqa: BLE001 - best effort, as in a finaliser
        pass


def _sleep_1(seconds, trail, k):
    """sleep/1: sleep(Seconds) — asyncio.sleep."""
    secs = deref(seconds)
    expect_type(secs, NUMBER_TYPES, "sleep/1", arg=1)
    await_only(_asyncio.sleep(float(secs)))
    yield None


await_value = ModulePredicate("await_value")
await_value._register(2, simple_to_trampoline(_await_value_2))

await_each = ModulePredicate("await_each")
await_each._register(2, simple_to_trampoline(_await_each_2))

sleep = ModulePredicate("sleep")
sleep._register(1, simple_to_trampoline(_sleep_1))
