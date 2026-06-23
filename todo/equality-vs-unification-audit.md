# Audit: `==` / identity used where unification is required (head patterns)

**Started 2026-06-23**, triggered by the numeric-head-literal bug
(`todo/numeric-head-literal-unification-bug.md`). This audits the whole class:
**any place a compiled clause head tests an argument with Python `==`, `is`,
or a structural `match` pattern instead of `unify()`** — which only matches an
*input-mode* caller (arg already equals the literal) and **silently fails to
bind an unbound `Var` caller** (output / var-query mode), yielding no solution.

## The invariant

Every atomic head literal must **capture the arg and route through `unify()`**:

```python
case [_v0, _ncap0]:
    if _ncap0 == 20000 or unify(_ncap0, 20000, trail):   # == is a fast path only
        ...
```

The `==` (or `is`) disjunct is a C-speed short-circuit for an already-equal
caller; the **`unify()` fallback is what binds an unbound `Var`**. A bare
`MatchValue` / `MatchSingleton` has no `unify()` fallback — that is the bug.

All head-pattern emission lives in `clausal/logic/compiler/head_match.py`
(`head_to_match_pattern` + `compile_head_to_match_case`).

## Findings

| # | Head literal kind | Pattern emitted (before) | Status |
|---|---|---|---|
| 1 | int / float / complex | `MatchValue` (== only) | **FIXED** — scalar capture+unify guard (commit: numeric-head-literal fix) |
| 2 | bool / None | `MatchSingleton` (identity only) | **FIXED** — folded into the scalar guard |
| 3 | str | capture + `== or unify` guard | OK (pre-existing, F046) |
| 4 | bytes | capture + `== or unify` guard | OK (pre-existing, bytes-as-lists) |
| 5 | atom (PredicateMeta) | capture + `unify` guard | OK (pre-existing, R1) |
| 6 | list / SegString | capture + `_head_list_unify` guard | OK (pre-existing) |
| 7 | dict / set / set-literal | capture + unify guard | OK (pre-existing) |
| 8 | `Compound(f, args)` | `MatchClass(Compound, …)` | **KNOWN GAP** — see below (commented) |
| 9 | imported `Call(LoadName, …)` | `MatchClass(cls, …)` | **KNOWN GAP** — commented |
| 10 | functor term instance | `MatchClass(cls, …)` | **KNOWN GAP** — commented |

### Fixed (this audit)
- **#1 numbers**, **#2 booleans/None**. Both now capture the arg and run the
  `scalar` guard (`== or unify`). `bool` is an `int` subclass so it shares the
  numeric branch; `None` is handled in the (former) singleton branch.
  Regression tests: `tests/test_numeric_head_literal.py`
  (fixture `tests/clausal_modules/numeric_head_literal.clausal`), red-green
  verified for every case.

### Known gap — structural head literals (#8/#9/#10)
A `Compound` / imported-`Call` / functor-instance head literal compiles to a
Python `MatchClass`, which matches only when the caller arg **already is** a
term of that shape (input mode). An unbound `Var` caller is **not** bound to a
freshly constructed `functor(args…)` term the way unification would — the query
fails silently. Same bug class as #1/#2, but the fix is materially harder: a
`match` pattern cannot *construct-and-bind*; it would need to build the term
(allocating fresh `Var`s for any head vars) and `unify()` it into the caller
arg, i.e. a code path more like the bare-fact `unify(...)` lowering than a match
arm.

This is **entangled with data-constructor support**: a compound like
`point(1, 2)` in a head currently isn't even constructible unless `point` is a
registered/imported constructor (see the deferred "auto-mint compound data
constructors" design). So #8–#10 should be resolved *together with* that design
decision rather than patched piecemeal. Warning comments have been added at all
three sites in `head_match.py`. **Not yet fixed — needs a design call.**

## Not in scope (verified intentional)
- `control_constructs.py` `ast.Eq()` sites — runtime counter / index / type
  checks on ground Python ints (`call_nth/2` etc.), not head unification.
- `control_constructs.py` body `==` operator — clausal arithmetic equality
  (`=:=`), an intentional comparison, not a binding point.
- `ite_reified.py` `is True/False` — tests an already-bound reification flag.
- First-argument indexing (`predicate.py`) lifts a `MatchValue` head pattern,
  but the lifted bucket fn **only runs when the position is ground** (guaranteed
  by dispatch), so its `==` match is always input-mode and safe. The non-ground
  call mode takes a different plan. This is why indexing never tripped the bug.
- `list_dispatch.py` already documents and *avoids* the `MatchValue`-`==` hazard
  by lifting strings through unify.

## Follow-up
- Decide the structural-head-literal (#8–#10) fix alongside data constructors.
- Consider a compiler self-check / lint that flags any `MatchValue` /
  `MatchSingleton` head pattern lacking a `unify()` fallback.
