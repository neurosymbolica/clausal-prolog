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
- Tables: a query may wait anywhere, inside tabled evaluation included.
  While it is suspended -- at a wait, or between answers of a tabled goal it
  is still streaming -- its incomplete tables belong to it.  Another query
  that calls one raises ``permission_error(access, tabled_evaluation, P/N)``
  rather than see a partial answer set (SLG assumes one search per table).
  Per-query tabling state (leader stack, drive episodes) is kept apart.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import weakref

import greenlet as _greenlet

from clausal.logic.exceptions import LogicException, permission_error
from clausal.logic.solve import solve
from clausal.logic.variables import deref, unify

__all__ = ["asolve", "aonce", "acall", "adrive", "await_only", "async_predicate"]


class _QueryGreenlet(_greenlet.greenlet):
    """The greenlet a query runs in: ``await_only`` may switch out."""


def _in_query_greenlet():
    try:
        current = _greenlet.getcurrent()
    except RuntimeError:          # called while a greenlet is being finalised
        return False
    # A query greenlet being finalised (GC of an abandoned query) can no
    # longer switch to its parent: treat it as outside any query.
    return type(current) is _QueryGreenlet and not current.dead


# ── per-query engine state ───────────────────────────────────────────────
#
# Tabling keeps its leader stack, drive episodes and spawn depth in
# thread-locals.  Interleaved queries share a thread, so each query carries
# its own copy and installs it while it runs.  The drive context also names
# the query (``owner``), which tags the tables it creates (tabling._foreign).

def _engine_locals():
    from clausal.logic import tabling
    return (tabling._leader_ctx, tabling._drive_ctx, tabling._spawn_ctx)


def _fresh_state(owner):
    state = [dict(type(local)().__dict__) for local in _engine_locals()]
    state[1]["owner"] = owner
    return state


def _install(state):
    """Install *state* into the engine thread-locals; return what was there."""
    previous = []
    for local, d in zip(_engine_locals(), state):
        previous.append(dict(local.__dict__))
        local.__dict__.clear()
        local.__dict__.update(d)
    return previous


# ── await_only ───────────────────────────────────────────────────────────

_sync = threading.local()


def _close_loop(loop):
    if loop.is_closed() or loop.is_running():
        return
    try:
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        loop.close()


def _sync_loop():
    """The private loop a synchronous query awaits on (one per thread).

    Kept for the thread's life rather than one ``asyncio.run`` per await:
    ``asyncio.run`` finalises every async generator it touched, which would
    end an ``await_each`` iterator after its first item.  Closed when the
    thread object goes away, or at interpreter exit for the main thread.
    """
    loop = getattr(_sync, "loop", None)
    if loop is None or loop.is_closed():
        loop = _sync.loop = asyncio.new_event_loop()
        weakref.finalize(threading.current_thread(), _close_loop, loop)
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
        return _greenlet.getcurrent().parent.switch(("await", awaitable))
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _sync_loop().run_until_complete(_as_coroutine(awaitable))
    culprit = type(awaitable).__name__
    _discard(awaitable)
    raise LogicException(permission_error(
        "await", "synchronous_query", culprit,
        "await_only/1: a synchronous query (solve, once, ...) is waiting "
        "inside a running event loop, which it would block; drive it with "
        "clausal.aio.asolve or aonce instead (in Jupyter, "
        "`await Solutions(...)`; in seam, put the `--goal` in an async def)"))


# ── asolve / aonce ───────────────────────────────────────────────────────

class _Query:
    """One query: its answer generator, engine state and query greenlet.

    ``live`` says whether the query may still resume, which is what makes its
    unfinished tables its own (``tabling._foreign``).  It goes false when the
    query is closed, and also when the async generator driving it is gone
    without having been closed (dropped after its loop shut down): a query
    nobody can resume must not hold its tables forever.
    """

    __slots__ = ("gen", "state", "child", "_live", "agen", "loop", "created",
                 "__weakref__")

    def __init__(self, gen):
        self.gen, self.state = gen, _fresh_state(self)
        self.child, self._live, self.agen, self.loop = None, True, None, None
        self.created = []       # (entry, store, key) of tables it created

    def _died(self):
        """The async generator driving this query is gone, unclosed.

        Its own close may still run later (asyncio's finaliser) or never (the
        loop is gone).  Either way nobody can resume it, so the tables it
        left half-built leave the store now: another query then builds them
        afresh instead of meeting a dead query's partial evaluation (rounds
        5 and 6 of the review, 2026-10-06, each found a path that did).
        Identity-guarded, so a table someone has rebuilt since is left alone.
        """
        if not self._live:
            return                      # closed normally in the meantime
        self._live = False              # first: _died must not re-enter
        for entry, store, key in self.created:
            if (entry.status == "evaluating" and entry.owner is self
                    and store.get(key) is entry):
                del store[key]
        self.created = []
        # Finish the query's answer generator here, under its OWN engine
        # state.  Left to the cyclic GC, it was finalised at an arbitrary
        # moment inside whatever query was running, and its drive episode's
        # cleanup then repaired away THAT query's tables (eighth review,
        # 2026-10-06).  A generator still running inside a parked greenlet
        # cannot be closed; it is unreachable from any query's state.
        gen, self.gen = self.gen, None
        if gen is not None and not getattr(gen, "gi_running", False):
            saved = _install(self.state)
            try:
                gen.close()
            except BaseException:  # noqa: BLE001 - nobody to report it to
                pass
            finally:
                self.state = _install(saved)

    @property
    def live(self):
        """True while the query could still be resumed: not closed, its
        async generator still exists, and its event loop is not closed.  A
        query parked at a wait when its loop closes can never resume, even
        though nothing ever frees it (eighth review, 2026-10-06)."""
        return (self._live
                and (self.agen is None or self.agen() is not None)
                and (self.loop is None or not self.loop.is_closed()))

    def _switch(self, how, *args):
        from clausal.logic.tabling import _outer_ctx, _pending_dead, _reap_dead
        if _pending_dead:
            _reap_dead()
        saved = _install(self.state)
        # The context we just swapped out may be a synchronous query parked
        # mid-fixpoint (this async query runs inside its consumer): its
        # leaders are no longer on the installed stack, but their tables are
        # still being built.  Let tabling see them (tabling._foreign).
        _outer_ctx.leaders.append(saved[0])
        try:
            return how(*args)
        finally:
            _outer_ctx.leaders.pop()
            self.state = _install(saved)

    async def step(self, fn):
        """Run *fn* to completion in a query greenlet, awaiting what it asks.

        Whatever the awaited object raises -- an error, ``CancelledError``, or
        a ``BaseException`` such as ``GeneratorExit`` or ``SystemExit`` -- is
        thrown into the query at its ``await_only``, so the query unwinds (or
        a ``catch/3`` handles an ordinary error) before it reaches the caller.
        """
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        child = self.child = _QueryGreenlet(fn)
        child.gr_context = _greenlet.getcurrent().gr_context
        try:
            msg = self._switch(child.switch, None)
            while not child.dead:
                try:
                    result = await msg[1]
                except BaseException as exc:  # noqa: BLE001 - delivered
                    msg = self._switch(child.throw, exc)
                else:
                    msg = self._switch(child.switch, result)
            return msg
        finally:
            self.child = None

    def next_solution(self, _):
        try:
            return ("sol", next(self.gen))
        except StopIteration:
            return ("end", None)

    def close(self, _):
        close = getattr(self.gen, "close", None)
        if close is not None and not getattr(self.gen, "gi_running", False):
            close()
        return ("end", None)


def adrive(gen):
    """Drive any synchronous answer iterator on the event loop.

    *gen* yields once per answer (``solve``, or the seam's own answer
    generator); each answer is yielded on, and the generator runs in a query
    greenlet, so a wait inside it suspends only this query.

    Close the result (``aclose()``, or ``contextlib.aclosing``) when you stop
    early -- after a ``break`` out of ``async for``.  While something still
    references an unclosed result, the tables its query is building stay
    reserved (another query on them is refused).  Once nothing does, they are
    released at once, and the query's own close runs a loop tick or two later
    on asyncio's finaliser.
    """
    query = _Query(gen)
    answers = _adrive(query)
    alive = weakref.ref(query)

    def gone(_ref):
        # Only queue it: this can run inside the cyclic GC, in the middle of
        # another query's loop over a table store, or in another thread.
        # tabling._reap_dead removes the tables at a safe point.
        q = alive()
        if q is not None and q._live:
            from clausal.logic.tabling import _pending_dead
            _pending_dead.append(q)
    query.agen = weakref.ref(answers, gone)
    return answers


async def _adrive(query):
    try:
        while True:
            kind, value = await query.step(query.next_solution)
            if kind == "end":
                return
            yield value
    finally:
        # Close inside the query's greenlet and engine state, so the
        # generator's own cleanup (tabling episode repair, cleanup handlers)
        # runs where it would have run synchronously.
        try:
            await query.step(query.close)
        except RuntimeError as exc:
            # Finalised by the garbage collector from inside a dying query
            # greenlet: nothing can switch any more, so nothing to close in.
            if "greenlet is being finalized" not in str(exc):
                raise
        finally:
            query._live = False
            query.gen = None
            query.created = []


def asolve(goal, module=None, trail=None):
    """``async for trail in asolve(goal, module)``: solve on the event loop.

    Takes the same arguments as ``solve``.  The query yields to the event loop
    at every ``await_only``; between awaits it runs synchronously.
    """
    return adrive(solve(goal, module, trail))


def acall(functor, *args, module=None, trail=None):
    """The async twin of ``clausal.call``: ``async for trail in acall(...)``."""
    from clausal.logic.solve import call  # noqa: PLC0415
    return adrive(call(functor, *args, module=module, trail=trail))


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
