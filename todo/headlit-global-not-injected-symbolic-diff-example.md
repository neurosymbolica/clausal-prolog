# `$headlit_<id>` NameError breaks the shipped symbolic_diff example

**Filed:** 2026-07-30, found while auditing the stale `todo/done/test-failures.md`
(which listed a *different*, now-fixed failure in the same file — the old
`<load>`-time crash is gone, this is a new one).

`clausal/examples/symbolic_diff.clausal` is a shipped example and 6 of its 10
self-tests fail:

```
PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python \
  -m clausal.testing clausal/examples/symbolic_diff.clausal
# 10 tests: 4 passed, 6 failed
```

Every failure is the same shape — a compiler-generated head-literal global that
was never injected into the module's globals:

```
clausal/examples/symbolic_diff.clausal:54 :: d(x^3)/dx
  goal 1 of 1 raised:
    Diff(Vx ** 3, Vx, 3 * Vx ** 2 * 1)
    NameError: name '$headlit_246899737185712' is not defined
```

The name embeds `id()` of the literal, so it differs per run and per clause.
The four passing tests are the ones whose clauses need no head literal.

Two things make this worth more than an example fix:

- `$headlit_*` is compiler-generated, so the same gap is reachable from any
  rulebase with the head shape this example uses (a compound head arg that is a
  literal, e.g. `Diff(X ** N, X, ...)`). It is not example-specific.
- It fails at *runtime*, per-goal, not at load. A rulebase carrying this shape
  loads clean and then raises on the query.

Start at whoever mints `$headlit_` names and compare against the two
`base_globals` tables in `clausal/logic/compiler/predicate.py` (the same tables
that had to gain `$const_set` for the membership optimization) — the likely fault
is a name minted into the AST on one path and injected on another.

Not a regression from the 2026-07-29/30 merges: reproduced identically on
canonical `main` before the sync.
