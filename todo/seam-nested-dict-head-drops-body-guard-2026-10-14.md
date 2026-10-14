# A head with a variable inside a nested dict or list drops its body guard

Found 2026-10-14 in review of 0681a752 (reproduces independent of `++`).

```seam
-module(pq, [a(X), c(X), e(X), b(X)])
-private([k, j])
a({'k': {'j': X}}) <- (X == 1)
b([[X]]) <- (X == 1)
c({'k': [X]}) <- (X == 1)
e([{'k': X}]) <- (X == 1)
```

Calling `a({'k': {'j': 2}})` (goal-position `--a(++v)` with `v = {'k': {'j': 2}}`)
is true although `X == 1` fails; `c({'k': [2]})` and `e([{'k': 2}])` behave the
same. A flat `r({'k': X}) <- (X == 1)` is correct, so the guard is lost when the
variable sits one container deeper than a dict value (dict in dict, list in dict,
dict in list). `f(...) <- (X > 5)` and `g(...) <- (X != 1)` with the same head
shape are also affected, so the body is not run (or its result is ignored).

Repro script: `scratchpad/dictrev/p7.py` (review of 0681a752). Expected:
`[True, False]` for values `1, 2` in each of a, c, e.

Likely area: head matching for DictTerm (wildcard capture + unify guard,
`clausal/logic/compiler/head_match.py` around the DictTerm branch) with a nested
variable. A separate fix is being dispatched.
