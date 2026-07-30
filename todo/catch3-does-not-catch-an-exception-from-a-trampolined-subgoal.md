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
