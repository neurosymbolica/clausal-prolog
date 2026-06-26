# TODO: smarter way to bind a compound head literal in output mode

RESOLVED 2026-06-23 (binding fix): declared/imported constructors (Compound /
imported-Call / functor-instance) now bind in output mode via
`_normalize_structural_head_args` in `clausal/logic/database.py`, which hoists
each structural top-level head arg to a fresh Var + prepended Unify goal at
assert time (mirroring fact normalization). The undeclared-bare-functor
construction case (`point(1,2)` with no declared `point`) remains a separate
data-constructor design item — it raises the existing "not in scope" error in
output mode rather than silently failing.

**Opened 2026-06-23** as follow-up to `equality-vs-unification-audit.md`
(findings #8–#10: `Compound` / imported-`Call` / functor-instance head literals).

## Problem

A structural head literal compiles to a Python `MatchClass`
(`clausal/logic/compiler/head_match.py`):

```python
pt(N, point(1, 2)) <- (N >= 0)
# →  case [_v0, Compound(functor='point', args=[1, 2])]:
```

`MatchClass` matches only when the caller arg **already is** that term (input
mode). An unbound `Var` caller (`pt(5, X)`) fails the match and yields no
solution — it is never bound to `point(1, 2)`. Same bug class as the numeric /
bool / None literals (which are now fixed), but a `match` pattern cannot
*construct-and-bind*, so the atomic `== or unify` guard trick doesn't transfer.

## Lead: the fact-lowering path already does this correctly

Bare facts do NOT use structural match patterns — they capture every arg and
`unify()`:

```
fact_int(50, 20000),   # → case [_v2, _v3]: if unify(_v2, 50, trail) and unify(_v3, 20000, trail): ...
```

`unify()` already handles both directions: it destructures a ground caller and
constructs/binds an unbound one. So the "smarter way" probably already exists in
the fact lowering — the task is to **reuse it for ruled-clause heads that
contain a structural literal**, instead of emitting a `MatchClass`.

## Options to evaluate

- **A. Construct-and-unify lowering.** When a head arg is a `Compound` /
  term-instance, capture it as a wildcard and emit
  `unify(cap, <build_term_expr>, trail)`, where `build_term_expr` constructs the
  term with fresh `Var`s for any head vars (exactly the bare-fact path). Handles
  both modes; likely the cleanest.
- **B. Hybrid match + fallback.** Keep `MatchClass` for the common ground/input
  case and add a Var-caller fallback that constructs+unifies. Harder to express
  in a single match arm; probably not worth it over (A).
- **C. Route whole clause through fact-style lowering** when any head arg is
  structural, skipping match patterns for that clause. Simplest correctness
  story; measure the dispatch-speed cost vs (A).

## Entanglement / blocker

This is tied to **data-constructor support**: `point(1, 2)` in a head isn't even
constructible today unless `point` is a registered/imported constructor (see the
deferred "auto-mint compound data constructors" design). Resolve the constructor
story and #8–#10 together rather than piecemeal.

## Done when

- A compound / functor-instance head literal binds an unbound `Var` caller
  (output mode) AND still matches a ground caller (input mode).
- Regression tests in both modes (extend `tests/test_numeric_head_literal.py`
  or a sibling), red-green verified.
- WARNING comments in `head_match.py` (#8–#10) removed once fixed.
