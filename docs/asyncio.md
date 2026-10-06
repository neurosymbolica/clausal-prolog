# Asyncio

Clausal queries can run on an `asyncio` event loop. A query that waits on
I/O (an HTTP request, a database round trip, a timer) gives the loop to other
tasks until the result is ready, so many queries can wait at once in a single
thread.

!!! note "Experimental"
    `clausal.aio` and `library(asyncio)` are new and not yet part of the 1.0
    [public API](public-api.md). `asolve` needs the `greenlet` package:
    `pip install 'clausal[async]'`.

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
  query. The query unwinds, and `setup_call_cleanup/3` cleanups run.
- **Tabling.** A tabled predicate may not wait while it is being evaluated
  under `asolve`. It raises `permission_error(await, tabled_evaluation, _)`.
  SLG resolution completes a table assuming one search at a time; another
  query that saw a half-built table would get wrong answers. Waiting
  *before* calling a tabled predicate is fine, and so is waiting inside one
  under plain `solve`.
- **A synchronous query inside a coroutine.** Calling plain `solve` on a
  predicate that waits, from code already running on an event loop, raises
  `permission_error(await, synchronous_query, _)`. Blocking there would stop
  the loop, so use `asolve`.

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
nothing; a wait costs a few microseconds.

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
