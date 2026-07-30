# `$headlit_<id>` NameError breaks the shipped symbolic_diff example

STATUS: DONE (2026-07-30). One-line fix in `clausal/logic/compiler/head_match.py`:
`head_to_match_pattern`'s functor-instance branch now takes its field list from a
new `_matched_field_names()` helper, which drops dataclass fields declared
`compare=False`. `clausal/examples/symbolic_diff.clausal` goes 10/10. Regression
test on a minimal, non-differentiation shape:
`tests/test_operator_head_indexed_dispatch.py` (4 behaviour tests + 1 unit test
pinning the emitted pattern + 1 end-to-end example run).

**Filed:** 2026-07-30, found while auditing the stale `todo/done/test-failures.md`
(which listed a *different*, now-fixed failure in the same file — the old
`<load>`-time crash is gone, this is a new one).

## The filed hypothesis was wrong

The original guess was "a name minted into the AST on one path and injected on
another, start at the two `base_globals` tables in
`clausal/logic/compiler/predicate.py`". The *symptom* is indeed a missing
`base_globals` entry, but injecting it is the wrong fix: patched in
experimentally, the NameError becomes a **silently empty answer**, because the
name should never have been minted at all. The literal being captured is not a
user literal — it is the compiler's own cosmetic source-position tuple.

## Actual mechanism

1. An operator head arg (`Diff(A + B, X, DA + DB)`) is an `Add`, i.e. a
   `clausal.pythonic_ast.nodes.BinOp` **dataclass**. `database.py::_normalize_structural_head_args`
   hoists it at assert time into a body `Unify`, where runtime `unify` decides
   the match via `BinOp.__unify__` — which deliberately ignores the
   non-semantic `position` field (`compare=False`). That path is correct and is
   why the 4 non-operator self-tests passed, and why the same rulebase works
   below the indexing threshold.
2. At ≥ `_INDEX_THRESHOLD` (4) clauses, `Diff/3` gets argument-index buckets, and
   Phase 8's `list_dispatch.py::_lift_clause_at_pos` lifts that body `Unify`
   **back into the head** so `head_to_match_pattern` can emit a pattern instead
   of a runtime unify.
3. `head_to_match_pattern`'s `is_term_instance` branch built its `MatchClass`
   from **all** `term_field_names(term)` — for a pythonic_ast node that is
   `('position', 'left', 'right')`. So the head pattern tested the clause's
   source position, a field both `unify` and `==` ignore.
4. That position tuple is ground and non-primitive, so `_is_opaque_head_literal`
   accepted it and the A02-F003 machinery emitted a `$headlit_<id>` capture +
   unify guard for it.
5. `$headlit_*` keys are injected only by `globals_env::_collect_globals_info`'s
   `_walk_head`, which ran on the **pre-lift** clauses. There the term lived in
   the body, and `_walk_body` collects types/thunks but not head literals. Hence
   `NameError: name '$headlit_<id>' is not defined`, raised per goal at runtime
   (a rulebase with this shape loads clean). The `id()` in the name made it look
   nondeterministic; it is not.
6. And even with the entry injected, step 3 would compare the clause's source
   position against the caller's — zero solutions, silently. Verified by
   monkeypatching the injection in: `NameError` → `[]`.

So the fault is step 3, and the seam is head matching, not globals: a head
pattern must test exactly the fields unification tests. `terms_to_ast.py::term_to_ast_expr`
already drops `("_position", "position")` when *constructing* a term; the
matching half of the same rule was missing. Fixing it there makes steps 4–6
unreachable — no bogus literal is minted, so nothing needs injecting — and keeps
the Phase 8 optimisation.

Not a regression from the 2026-07-29/30 merges. It is a regression from
`ca49b125` "fix(A02-F003): guard the accept-all wildcard for opaque head
literals" (2026-07-07), which turned the wildcard that used to swallow the
position tuple into a real guard. Before that commit position was ignored by
accident; the 2026-07-01 write-up of this same example
(`todo/done/symbolic-diff-structural-operator-heads-no-match.md`) records the
`MatchClass(Add, ...)` head pattern working, which is consistent.

## Blast radius

**General, not example-specific.** Reachable from any rulebase with

- a predicate at or above 4 clauses (so argument indexing builds buckets), and
- a structural head argument that is a dataclass carrying a `compare=False`
  field — today that means any `clausal.pythonic_ast` operator node, i.e. any
  arithmetic/bitwise/boolean operator term in a clause head.

Minimal reproducer (nothing to do with differentiation), now the regression test:

```clausal
-module(opidx, [Kind(TERM, NAME), Chk(N)])
-private([p, q, plus_, minus_, times_, other_])

Kind(A + B, plus_) <- (number(1))
Kind(A - B, minus_) <- (number(1))
Kind(A * B, times_) <- (number(1))
Kind(9, other_) <- (number(1))

Chk(N) <- Kind(p + q, N)     # NameError '$headlit_<id>' before the fix
```

Drop any one of the four `Kind` clauses and it passes — that is the whole
difference between the broken and working shapes, and it is why user-facing
symptoms look erratic.

Not affected: `Compound` (dedicated branch, never field-walked), `KWTerm`,
lists/dicts/sets, and user predicate terms (`PredicateMeta._fields` has no
`compare=False` members, and `_head_arg_patterns` is deliberately left alone
there — its field list is the predicate's own argument list and must stay
aligned with the head arity).

## Adjacent defect found, filed separately

`todo/quantity-head-literal-compiles-to-a-pythunk-that-never-matches.md` — a
`value(unit)` amount (`Len(5(m), short_)`, `Price(7.89(euro), one_)`) in a clause
head is compiled to a `PyThunk`, which `_is_opaque_head_literal` also accepts as
a ground literal, so the clause matches nothing at any clause count. Same
A02-F003 guard, different input, different fix; not folded in here.

---

## Original report

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
