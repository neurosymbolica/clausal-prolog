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
| 8 | `Compound(f, args)` | `MatchClass(Compound, …)` | **FIXED — structural head normalization (this plan)** |
| 9 | imported `Call(LoadName, …)` | `MatchClass(cls, …)` | **FIXED — structural head normalization (this plan)** |
| 10 | functor term instance | `MatchClass(cls, …)` | **FIXED — structural head normalization (this plan)** |

### Fixed (this audit)
- **#1 numbers**, **#2 booleans/None**. Both now capture the arg and run the
  `scalar` guard (`== or unify`). `bool` is an `int` subclass so it shares the
  numeric branch; `None` is handled in the (former) singleton branch.
  Regression tests: `tests/test_numeric_head_literal.py`
  (fixture `tests/clausal_modules/numeric_head_literal.clausal`), red-green
  verified for every case.

### Fixed — structural head literals (#8/#9/#10)
`_normalize_structural_head_args` in `clausal/logic/database.py` now hoists
every structural (Compound / imported-Call / functor-instance) top-level head
arg into a fresh `Var` + prepended `Unify(Var, value)` goal at assert time,
mirroring what `_normalize_dataclass_fact` does for facts. The `MatchClass`
branches in `head_match.py` therefore only ever see ground (input-mode) callers;
output-mode binding is handled by `Unify` in the body, exactly as for facts.

Implemented: `docs/superpowers/plans/2026-06-23-structural-head-literal-binding.md`
(commits b37ea1c0..); WARNING comments removed from `head_match.py`.

**Caveat:** undeclared bare-functor construction (`point(1,2)` with no
declared/imported `point`) still raises the existing "not in scope as a term
class" error in output mode — the auto-mint data-constructor design is a
separate, deferred item.

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
- **Structural head literals (#8–#10):** resolved — see above and
  `todo/compound-head-literal-output-mode.md` (marked RESOLVED).
- **Mode coverage:** audit the whole suite for input vs output (var-query) mode
  coverage so this blind spot can't recur — see
  `todo/audit-tests-input-output-mode-coverage.md`.
- **Compiler self-check — DONE 2026-06-26.** `assert_head_pattern_unify_safe`
  in `clausal/logic/compiler/invariants.py` now runs on every compile (via
  `compile_head_to_match_case`) and raises `InvariantError` if any **top-level
  head argument** compiles to a bare `MatchValue` / `MatchSingleton` (the
  `==`/identity-only shape that never binds a Var caller). Scoped to direct arg
  slots, so it does not flag the legitimate, input-mode-only `MatchValue`
  discriminant nested inside a `MatchClass` (compound-key indexing) or the
  ground-position indexing lift. Negative + positive tests:
  `tests/test_invariant_errors.py::test_head_pattern_unify_safe_*`. The whole
  suite (8137 passing) is the standing affirmative gate that no real head trips
  it.

**This audit is now fully resolved** — all findings fixed and the bug class is
locked against regression by the always-on compiler invariant.
