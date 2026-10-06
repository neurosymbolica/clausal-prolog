# Asyncio

Clausal queries can run on an `asyncio` event loop. A query that waits on
I/O (an HTTP request, a database round trip, a timer) gives the loop to other
tasks until the result is ready, so many queries can wait at once in a single
thread.

Clausal has no scheduler of its own. Queries run on Python's standard
`asyncio` loop, the same one aiohttp, httpx, asyncpg and the LLM SDKs run on.
So a proof can await any of those libraries directly. Timeouts, cancellation,
racing and task groups are `asyncio`'s own, mature and already familiar,
rather than a second concurrency system to learn.

!!! note "Experimental"
    `clausal.aio` and `library(asyncio)` are new and not yet part of the 1.0
    [public API](public-api.md). It is built in: `pip install clausal` brings
    `greenlet`, the one runtime dependency, which `asolve` uses.

## The idea in one paragraph

Whether a predicate waits *asynchronously* is decided by how the query is
driven, not by the program. The same predicate, in the same program:

- under `clausal.aio.asolve` suspends the query and lets the event loop run
  other tasks;
- under plain `solve` (the CLI, the REPL, `once`) blocks until the result is
  ready.

So a Clausal Prolog program needs no async syntax. It calls `sleep/1`, or a
predicate a Python adapter built with `async_predicate`, like any other
predicate.

## What it is for

Prolog is a solver more than an I/O language, so it's fair to ask why it
should wait on anything. The answer: async here is not about making I/O
fast. It lets a solver **wait on the world in the middle of a search**,
without that costing a thread. Real-world, neurosymbolic problems are full of
such waits: a model to consult, a database to query, a person to ask, an
event that hasn't happened yet. Without async, every one of them is a
temporal problem the program has to manage. With it, waiting is just
another call in a proof.

Eagerly running independent subgoals in parallel is one use. The more
interesting ones are *lazy*, where the search decides what to fetch and
when, and *suspended*, where a proof sits waiting for the world.

### Expensive oracles inside the search

An LLM call, a theorem prover, an SMT check, a neural model on a GPU, or a
simulation can each be a predicate. The solver calls one only when the proof
needs it, and many branches or queries can have calls in flight at once.

The sharper version: `await_each/2` over a model's sampled answers turns
sampling into choice points. Backtracking draws the next candidate only when
logic rejects the current one. That's lazy generate-and-test: a model
generates, logic tests, and the model is asked for no more candidates than
the proof needs.

### Fact bases that live elsewhere

A predicate can stand for a remote relation: a SQL table, a REST or SPARQL
endpoint, a knowledge graph. Top-down search is already demand-driven query
planning. It fetches only the rows the proof touches, in the order the proof
needs them. With async, hundreds of such queries can share one process while
each waits on its own round trips.

### Askable predicates and long-running proofs

Classic expert systems had `ask/2`: in the middle of a proof, ask the user.
With async, a query can suspend while it waits for a form submission, a
chat reply or an approval, without a thread per user, so thousands of
half-finished proofs can wait at once. Configuration wizards, diagnosis,
eligibility and compliance rules are all proofs that need answers from a
person.

A suspended query lives in memory: it can't be saved to disk and resumed
in another process. So this works for waits of seconds to hours, not for
workflows that run for days.

### Event streams as relations

`await_each/2` over a websocket, a message queue or a sensor feed makes the
stream a nondeterministic predicate. A rule can then join live events with
the database and with constraints. That's complex event processing and
reactive rules: Clausal as the rules engine on a live feed.

### Agents that act, then sense

Planners and agents (Golog-style, BDI-style) alternate between choosing an
action, carrying it out, and waiting to observe the result. Many such agents
can run as concurrent queries in one process. Queries interleave only where
they wait, so they share the database without locks.

### Search control

These come from asyncio itself, with no new predicates:

- **Timeouts:** wrap a query in `asyncio.timeout(...)`.
- **Racing:** run several formulations or orderings of the same problem, take
  the first answer, and cancel the rest. Cancellation unwinds a query
  cleanly, cleanups included.
- **Bounded fan-out:** an `asyncio.Semaphore` inside an adapter limits how
  many oracle calls are in flight.

All of these take effect only at a wait. A purely CPU-bound search never
yields to the loop; for CPU parallelism see
[Free-Threaded Python](free_threading.md).

### Simulation

Drive queries with an event loop that has a virtual clock, and `sleep/1`
becomes simulated time. Each query is then a process in a discrete-event
simulation: protocols, queues, schedules, tested in milliseconds.

### Why Clausal in particular

- The Python async ecosystem (LLM SDKs, database drivers, HTTP clients) is
  async-first, and Clausal shares its objects and its event loop.
- A suspended query costs memory and a few microseconds per switch, not a
  thread.
- Backtracking still works across waits. Among the systems compared
  [below](#other-prologs), only trealla-js also lets backtracking pull the next
  item from an asynchronous source.

## From Clausal Prolog

`library(asyncio)` provides:

| Predicate | Meaning |
|---|---|
| `await_value(Awaitable, Value)` | Await a coroutine, task or future; unify its result with `Value`. |
| `await_each(AsyncIterable, Item)` | One solution per item of an async iterator, fetched as backtracking asks for the next. |
| `sleep(Seconds)` | `asyncio.sleep`: other queries run meanwhile. |

```prolog
:- module(naps, [nap/2]).
:- use_module(library(asyncio), [sleep/1]).

nap(Name, done(Name)) :- sleep(0.1).

:- end_module(naps).
```

Awaitables come from Python, so `await_value/2` and `await_each/2` are mostly
useful in seam code, where `++expr` calls Python:

```seam
-module(ticker, [ticks/1])
-import_from(py.asyncio, [await_each])

tick(X) <- await_each(++ticks_source(3), X)
ticks(XS) <- findall(X, tick(X), XS)
```

Here `ticks_source` stands for any Python function returning an async
iterator. `findall/3`, `once/1`, negation, `forall/2` and `catch/3` work
around waiting goals like any other: the waiting happens inside the call and
is invisible to the control construct.

## From Python

`asolve` is the async twin of `solve`: an async generator yielding the trail
once per solution. `aonce` returns the first solution's trail, or `None`.

```python
import asyncio
from clausal.aio import aonce
from clausal.logic.variables import Var, deref
import naps

async def main():
    results = [Var() for _ in range(3)]
    await asyncio.gather(*(aonce(("nap", name, r), naps)
                           for name, r in zip(["a", "b", "c"], results)))
    print([deref(r) for r in results])

asyncio.run(main())
```

The three naps overlap: the whole run takes about 0.1 s, not 0.3 s.

The other entry points have async forms too:

- `acall(functor, *args, module=...)` is the async twin of `clausal.call`.
- `async for bindings in Solutions(goal, ...)` streams binding dicts.
- `await Solutions(goal, ...)` fetches the answers to show, then displays
  them as usual. **In Jupyter, use this form.** The kernel always has an event
  loop running, so a plain `Solutions(...)` can't wait there and a waiting
  predicate raises `permission_error(await, synchronous_query, _)`.
- `adrive(generator)` runs any synchronous answer generator on the loop; the
  others are built on it.

### Writing an async adapter

`async_predicate(name, fn, arity)` turns an `async def` into a predicate. The
first `arity - 1` arguments are passed to `fn`, dereferenced. The awaited
result is unified with the last argument.

```python
import asyncio
from clausal.aio import async_predicate
from clausal.modules.py import to_text

async def _lookup(host):
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(to_text(host), None)
    return sorted({info[4][0] for info in infos})

lookup = async_predicate("lookup", _lookup, 2)     # lookup(Host, Addresses)
```

A string argument arrives as the chars carrier, not a Python `str`:
convert it with `to_text`. Lower-level code can call
`clausal.aio.await_only(awaitable)` from any synchronous predicate body; that
is what `async_predicate` and `library(asyncio)` do.

## From seam

In a `.seam` file, a goal-position `--goal` inside an `async def` runs on the
event loop. The enclosing function decides, as Python decides where `await`
is legal:

```seam
-module(waits, [])
-import_from(py.asyncio, [sleep])
import asyncio

nap(X) <- (sleep(0.05), X == 1)
nap(X) <- (sleep(0.05), X == 2)

async def first():
    if --nap(X):                     # awaited: the first answer
        return X

async def every():
    return [X for X in --nap(X)]     # an async comprehension

async def stream():
    async for X in --nap(X):         # an async generator of answers
        yield X

async def fetch(n):
    await asyncio.sleep(0.05)
    return n * 10

fetched(X) <- (X is ++await fetch(4))
```

- In an `async def`:
  - `if`, `elif` and `while --goal`, and `not --goal`, are awaited.
  - `for X in --goal` and `async for X in --goal` iterate asynchronously. A
    plain `for` is made async, because a waiting predicate inside it couldn't
    block the running loop.
  - List, set and dict comprehensions over `--goal` become async
    comprehensions.
  - A plain generator expression over `--goal` is refused at load. It would
    silently become an async generator; write `async for` to say so.
- A plain `def`, or a class, stays synchronous, even when it is nested inside
  an `async def`.
- Exported variables behave exactly as in a plain `def`. See
  [goal position](python_integration.md#goal-position-if-goal-for-in-goal).
- In a clause body, `++await f()`, or `await` inside an f-string slot, waits on
  the awaitable from within the query. It's the same as
  `await_value(++f(), X)`, and works under `asolve` and plain `solve` alike.
  Without `await`, `++f()` for an `async def f` gives you the coroutine
  object, not its result.

## Semantics

- **Interleaving.** Each query has its own trail. Queries interleave only
  where one waits, so between two waits a query runs alone. This is
  cooperative concurrency, not threads.
- **Shared database.** Queries share the database: a fact one query asserts is
  visible to another after the first query's next wait.
- **Backtracking.** Backtracking into a goal runs it again, waits included.
  `await_each/2` fetches the next item only when backtracking asks for it.
- **Errors.** An awaitable that raises surfaces as an error term, catchable
  with `catch/3` (a `ValueError("bad")` arrives as `'ValueError'(bad)`).
- **Cancellation.** Cancelling the task raises `CancelledError` inside the
  query. The query unwinds, and `setup_call_cleanup/3` cleanups run, even
  ones that wait. `catch/3` doesn't catch `CancelledError`, by design, so a
  catch-all handler can't swallow a cancellation. A second `cancel()` while a
  cleanup is waiting aborts that cleanup, as it would in plain asyncio. An
  `ExceptionGroup` from a `TaskGroup` arrives as one error term,
  `'ExceptionGroup'(Message)`; its sub-exceptions aren't turned into terms.
- **Tabling.** A query may wait anywhere, including inside a tabled
  predicate or between the answers of a tabled goal it is still
  enumerating. While a query is suspended, the tables it hasn't finished
  belong to it. Another query that calls one of them raises
  `permission_error(access, tabled_evaluation, Name/Arity)` rather than see
  a partial answer set, because SLG resolution builds each table in one
  search. To share a table between concurrent queries, complete it first
  (for example with `findall/3`), or run the queries one after another.
- **Stopping early from Python.** After a `break` out of `async for` over
  `asolve`, `acall` or `Solutions`, close the iterator with `await
  answers.aclose()` or `contextlib.aclosing(...)`. Python doesn't close an
  async generator on `break`; asyncio does it a loop tick or two later.
  Until then the query still owns any table it was building, and another
  query on that table is refused. In seam you don't need to: a `for` over
  `--goal` in an `async def` closes its iterator itself. A query abandoned
  without closing, after its loop has gone, releases its tables once it is
  garbage-collected.
- **Closing a query early.** When you stop asking for answers, cleanups of
  `setup_call_cleanup/3` still pending run when Python's garbage collector
  frees the query's frames, which happens with plain `solve` too. A cleanup
  that waits can't wait at that point. See
  `todo/closing-a-query-leaves-cleanup-to-the-garbage-collector-2026-10-06.md`.
- **A synchronous query inside a coroutine.** Calling plain `solve` on a
  predicate that waits, from code already running on an event loop, raises
  `permission_error(await, synchronous_query, _)`. Blocking there would stop
  the loop, so use `asolve`. This includes a coroutine that a query is
  itself awaiting, and a Jupyter cell (use `await Solutions(...)`).
- **Other event loops.** In a synchronous query, a wait runs on a private
  loop, one per thread, closed with its thread. A future or task that belongs
  to another loop and is still pending can't be awaited there.

## How it works

The engine itself is synchronous. Its generator trampoline is driven by plain
loops, some of them nested (`findall`, negation, `once`) and some written in
C. `asolve` runs the ordinary `solve` inside a
[greenlet](https://greenlet.readthedocs.io/), the technique SQLAlchemy's
asyncio support uses. `await_only` switches from the query's greenlet to the
one running the asyncio task. That greenlet awaits, then switches back with
the result.

Every engine frame in between stays suspended, unchanged. That is why no part
of the engine had to learn about waiting. A query that never waits pays
nothing; a wait costs on the order of 10 µs more than the same wait in a
synchronous query.

Use `clausal.aio.await_only` rather than SQLAlchemy's function of the same
name. SQLAlchemy's version checks for its own greenlet type and refuses to
run inside a Clausal query. SQLAlchemy's async API works fine through
`await_value/2` or `async_predicate`.

## Other Prologs

Few Prologs have async I/O, and nearly all of them run in a JavaScript host,
where the browser leaves no choice. The table helps translate a program
between them. It was checked against each system's own sources and manuals
in October 2026.

| Clausal | SWI-Prolog (WebAssembly) | Tau Prolog | Trealla (trealla-js) |
|---|---|---|---|
| Async query from the host: `asolve`, `aonce` (Python) | `Prolog.forEach(goal, ...)` (JS) | `session.query`, then `session.answer(callback)`; `promiseAnswers()` (JS) | `pl.query(goal)` is an async generator; `pl.queryOnce` (JS) |
| `await_value(Awaitable, Value)` | `await(Promise, Result)` | `await(Future, Result)` (on a future, not a JS promise) | `js_eval_json/2` returning a Promise |
| `await_each(AsyncIterable, Item)` | none | none | a JS predicate written as an `async function*` (each `yield` is a choice point) |
| `sleep(Seconds)` (`library(asyncio)`) | `sleep(Seconds)` (yields under `forEach`) | `sleep(Milliseconds)`, an integer (`library(os)`) | none |
| `async_predicate(name, fn, arity)` | none (call JS from Prolog, then `await/2`) | none | `new Predicate(...)` with an async function, then `pl.register` |
| HTTP: an adapter over aiohttp/httpx | `fetch(URL, Type, Data)` | `ajax(Method, URL, Response)` (`library(js)`) | `http_fetch(URL, Options, Content)` |
| Run goals concurrently: `asyncio.gather` of `aonce` calls | several `forEach` calls with `{engine: true}` (cooperative threads) | `future(Template, Goal, F)`, `future_all/2`, `future_any/2` (`library(concurrent)`) | several queries on one interpreter |
| Refused outside an async query: `permission_error(await, synchronous_query, _)` | `is_async/0` tells you whether `await/2` may be called | always async | always async |

Differences worth knowing when porting:

- **The same program, sync or async.** In Clausal, whether a predicate waits
  asynchronously depends on how the query is driven, so one program runs
  under the CLI (blocking) and under `asolve`. SWI's `await/2` likewise works
  only in a query started by `Prolog.forEach`. Tau and Trealla are async
  throughout.
- **Futures.** Tau's `future/3` runs a goal concurrently and returns a
  handle; its `await/2` waits on that handle. Clausal has no handle
  predicate yet. Start concurrent queries from Python with
  `asyncio.gather`.
- **Nondeterministic waits.** Only Clausal (`await_each/2`) and trealla-js
  (async-generator predicates) let backtracking pull the next item from an
  asynchronous source.
- **Native Prologs.** SWI-Prolog (native), XSB, Logtalk's `threaded_call/1`
  and `threaded_exit/1` give concurrency through OS threads
  rather than an event loop, with blocking I/O inside each thread. A program
  that uses threads only to overlap waiting translates to concurrent
  `aonce` calls. CPU parallelism is a different matter: see
  [Free-Threaded Python](free_threading.md).
