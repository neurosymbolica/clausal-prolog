# `catch(fail, _, R)` in a `.pl` body does not compile: `ValueError: empty body on Try`

**Status: OPEN.** Found while probing the final review's I-1 (2026-10-16). It reproduces on the branch base a643125b, so it predates this round.

```prolog
k(X) :- catch(fail, _, true), X = 1.
```

Importing this `.pl` (native front end) raises `ValueError: empty body on Try` from `codegen.functiondef_to_function`. The Goal `fail` lowers to `[]` (`Fail()` drops its continuation), and the inline trampoline catch puts that empty list straight into an `ast.Try` body. Scryer: `k(X)` fails.

Fix: when the Goal lowers to no statements, emit `pass` in the try body. Or drop the try altogether: a goal that cannot run cannot throw.
