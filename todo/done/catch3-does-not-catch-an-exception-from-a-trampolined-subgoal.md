**DONE — 2026-08-25**, branch `fix/catch3-trampolined-subgoal-2026-08-25`. The
drive loops now route every `Exception` through the `catcher` chain, not just
`LogicException`; `_tramp_call` (the `once`/`findall`/`\+`/lambda-body driver),
which routed nothing at all, was the same hole a fourth time and is fixed with
it. Tests: `tests/test_catch_trampolined.py` +
`tests/fixtures/catch_trampolined.clausal`. Full-suite failure SET unchanged
against `916cca0b`.

**The hypothesis below was wrong** in its second half — see "What it actually
was". The seam is the trampoline, as guessed; the *reason* is not compilation
strategy.

---

# `catch/3` does not catch an exception raised by a trampolined subgoal

Found 2026-07-30 while checking that the new undefined-name seam in
`_drive_trampoline` could not steal an exception a `catch/3` wanted. It cannot — but
only because `catch/3` never had it.

## Repro

Two files in one directory, `sib.clausal`:

```
# clausal: no-collect
-module(sib, [cite(KEY), art_9])

cite(art_9),
```

and `use.clausal`, which does NOT import `cite`:

```
-import_from(sib, [art_9])

-private([ground_a])

boom(X) <- (X == {ground_a: cite(art_9)}),

Test("catch anon") <- (
    catch(boom(Y), E, print(E))
),
```

Run it: the NameError escapes the `catch/3` entirely and the test reports it as
uncaught. The recovery goal never runs, and `E` never binds.

## Not a NameError special case

The identical shape with an exception the compiler *can* see coming is caught fine:

```
boom(X) <- (X == {ground_a: 1 // 0}),

Test("catch dict zerodiv") <- (
    catch(boom(Y), E, print(E))
),
```

passes. So the catcher, the structural `python_error_term` conversion and the recovery
goal all work; the difference is in how `boom` is *called*.

## Why it looks like the trampoline seam

The traceback for the uncaught case has no `Test__1` frame in it at all:

```
  File ".../clausal/logic/solve.py", line 531, in call
    yield from _drive_trampoline(dispatch_fn, trail, *args)
  File ".../clausal/logic/solve.py", line 102, in _drive_trampoline
    result = _drive_until_yield(sg)
  File "<template>", line 5, in boom__1
```

`boom` is being driven as a sub-generator by the trampoline, so it raises in the
trampoline's frame, not inside the `try` that `_compile_catch_impl` emitted in `Test__1`.
The working case presumably inlines `boom` into the caller, where the `try` does cover
it. The hypothesis — untested — is that an unresolvable call target in the callee forces
the deep/trampolined compilation route, and that route has no equivalent of the catch
frame.

## What it actually was

The first half of that reading is right: `boom` raises in the driver's frame, not
in the caller's `try`. The second half is not. Dumping the compiled ASTs for both
shapes shows they are **identical** — `boom` and the caller are trampoline-compiled
either way, and the caller's frame *does* carry a working
`try: … except Exception as _exc: … $python_error_term(_exc) …` around the
`yield (_gen1, None)`. Nothing was inlined; the compilation route never differed.

What differed was the exception *type*, and what the driver did with it:

- The drive loops (`_drive_until_yield`, `trampoline`, `solutions` — C in
  `runtime/_trampoline.c`, mirrored in `trampoline.py`) caught **`LogicException`
  only** and threw it into the failing generator's `catcher` chain, which is what
  delivers it to the caller's `except`.
- `1 // 0` inside a dict raises `LogicException(type_error(evaluable, …))`, so it
  was routed and caught. A raw Python exception — the `NameError` here, but equally
  a `ValueError` out of a `++` escape — was not routed, so it propagated out of
  `gen.send()` past every enclosing `catch/3`.

So it was never about NameError, and never about the compilation strategy: `catch/3`
was silently type-dependent. The generic repro is one line of `.clausal`:

```
raise_value_error(X) <- (X is ++(int("nope"))),
catch_from_callee(E) <- (catch(raise_value_error(_X), E, true)),   # escaped
catch_inline(E)      <- (catch((_X is ++(int("nope"))), E, true)), # caught
```

## The fix

`_is_routable` in `clausal/logic/trampoline.py` (twinned as
`is_routable_exception` in `runtime/_trampoline.c`) states the policy once:
route every `Exception`, except the two kinds that are protocol rather than
error — `BaseException`-only classes (`GeneratorExit`, `KeyboardInterrupt`,
`SystemExit`/`halt`) and `StopIteration` (plus the PEP-479 `RuntimeError`
wrapper `_drive_until_yield` already consumes as exhaustion, A04-F009). That
matches what the shallow route has always done, since `_compile_catch_impl`
emits `except Exception`; the driver stops being a second, narrower policy.

Two things the fix deliberately preserves:

- **Nothing is converted at the seam.** An exception no handler absorbs is
  re-raised unchanged and on its original traceback, so the undefined-name
  enrichment in `_drive_trampoline` — which sits above every `catch/3` and only
  ever sees what every handler declined — still fires, and Python callers'
  `except ValueError` still matches. Correspondingly, a *caught* `NameError`
  binds as the raw `NameError(...)` term, not the enriched `UndefinedNameError`:
  the enrichment is the message for the author when nothing catches, not a term
  a live handler is owed.
- **Traceback frames survive the route.** The C helper now throws with the
  one-argument `gen.throw(exc)` after putting the fetched traceback back on the
  instance; the legacy `(type, value)` form dropped the raising frames, which
  cost `test_source_locations.py::TestSourceLocationsG6` its callee line.

`runtime/tramp_call.py` — the mini-trampoline `once`/`findall`/`\+`/lambda
bodies use to reach a trampoline-mode predicate — had *no* routing at all, so a
`catch/3` written inside such a predicate was inert under any of them, for
`throw/1` as much as for a Python exception. Same root cause, same fix.

## Why it matters beyond this

`catch/3` silently not catching is worse than most bugs of this size: the author writes a
handler, reads a green-looking rulebase, and only discovers the handler is inert when
something in the goal actually raises. Whether a handler is live currently depends on a
compilation decision the author cannot see and did not make.

## Not folded into the undefined-name fix

That fix is a message change and touches no control flow: its seam sits at the outermost
driver, strictly above every `catch/3`, so it can only ever see exceptions `catch/3`
already declined. This is a control-flow defect in the compiler and wants its own change
and its own tests.

## Relation to the A09-D002 / A11-D001 error-protocol cluster

`todo/audit-2026-07-05/README.md` §1 wanted "one boundary-conversion fix at the
ModulePredicate/trampoline layer + a narrowed drive-loop catch". The narrowing
half landed as A04-F009; the per-builtin conversions landed as the A09/A11 fixes.
This change closes the structural remainder those point-fixes could not reach:
an exception raised in a *callee's own frame* has no builtin boundary to convert
at, and now needs none — the driver hands it to the handler and the handler
converts, exactly as the shallow route always did. Every listed member of that
cluster is already in `todo/audit-2026-07-05/done/`; nothing there re-opens.
