# Structural Head-Literal Binding (output mode) — Design Spec

**Date:** 2026-06-23
**Author:** Michael Amy (with Claude)
**Status:** Designed — pending implementation
**Closes:** Findings #8–#10 of `todo/equality-vs-unification-audit.md`
(Compound / imported-`Call` / functor-instance head literals)
**Related:** numeric/bool/None head-literal fix (commits `71d7062f`, `c8807d36`);
F046 (string head literals); the deferred "auto-mint compound data constructors"
design (explicitly **out of scope** here)

---

## Goal

A **structural** literal in the head of a **ruled** clause must bind into an
unbound caller `Var` (output / var-query mode), exactly as a bare fact already
does. Given

```
Check(Wrap(SUB), RESULT) <- (RESULT is "matched")
```

the query `Check(X, "matched")` with `X` unbound must yield `X = Wrap(_)` (one
solution), identical to the fact form `CheckFact(Wrap(SUB), "matched")` which
already yields `Wrap(SUB=AttVar)` today. Input mode (`Check(Wrap(a), R)`) and
first-argument indexing must be unaffected.

This is the structural tail of the `==`/identity-vs-unification bug class; the
atomic cases (numbers, bool, None, str, bytes, atoms) are already fixed.

---

## Background

### The bug

A structural head arg compiles, in
`clausal/logic/compiler/head_match.py`, to a Python `MatchClass`
(`Compound(functor=…, args=…)`, or `cls(field=…)` for an imported-`Call` /
functor-instance). A `MatchClass` matches only when the deref'd caller arg
**already is** a term of that shape (input mode). An unbound `Var` caller fails
the match and yields **no solution** — it is never bound to a freshly
constructed `functor(args…)` term the way unification would. The atomic
`== or unify` guard trick does not transfer: a `match` pattern cannot
*construct-and-bind*.

### Proof (current behaviour)

Same head shape, opposite results — the only difference is rule vs fact:

| Clause | Query `(_, "matched")` with first arg unbound | Result |
|---|---|---|
| `Check(Wrap(SUB), RESULT) <- (RESULT is "matched")` (rule) | `Check(X, "matched")` | `[]` (bug) |
| `CheckFact(Wrap(SUB), "matched")` (fact) | `CheckFact(X, "matched")` | `[Wrap(SUB=AttVar)]` |

### Why the fact works

Facts are normalized at assert time by `_normalize_dataclass_fact`
(`clausal/logic/database.py`): each ground head field is replaced by a fresh
`Var` and a `Unify(Var, value)` goal is added to the body. `Unify` is
bidirectional — it destructures a ground caller (input) and constructs/binds an
unbound caller (output). Ruled clauses are simply **not** put through this
normalization, so their structural head args stay as `Call`/`Compound` nodes and
compile to the value-rejecting `MatchClass`.

Stored forms (observed):

```
# rule  pt(N, point(1,2)) <- (N >= 0)
head: pt(n=Var, arg_1=Call(LoadName('point'), [1,2]))   # → MatchClass, bug
body: [GtE(Var, 0)]

# fact  pf(50, point(1,2)),
head: pf(arg_0=Var, arg_1=Var)                            # normalized
body: [Unify(Var, 50), Unify(Var, Call(LoadName('point'), [1,2]))]
```

### Why this is safe for indexing

`arg_index._extract_arg_key` (`clausal/logic/compiler/arg_index.py:253-266`)
already recognises the `Var + Unify` pattern: when a head arg is a `Var`, it
scans the body for a `Unify(arg, term)` goal and recovers the index key from the
other side (compounds included — "Phase 9a"). So normalizing a rule head the
same way facts are normalized keeps first-argument indexing and
groundness-keyed dispatch working. The existing `CheckIndexed` rule clauses in
`tests/fixtures/head_compound_importer.clausal` exercise exactly this.

---

## Approach

Apply fact-style normalization to **ruled** clauses, restricted to **structural**
top-level head args. Atomic args keep the match-guard path (already fixed,
efficient, directly indexable). Normalization happens at assert time so the
stored clause, the compiler, and the indexer all see one canonical form.

### Components — all in `clausal/logic/database.py`

1. **`_is_structural_head_value(val) -> bool`**
   True for the term kinds that compile to a value-rejecting `MatchClass`:
   - `Compound`
   - `Call` with `func=LoadName(...)`
   - functor-instance (`is_term_instance(val)` and not `Compound`/`Call`/`KWTerm`)

   False for atomics (int/float/complex/bool/None/str/bytes), `Var`,
   `StarUnpack`, and `list` (those are handled by the match-guard / list-guard
   paths and must not be disturbed). This is the key difference from
   `_is_ground_value`, which returns True for atomics too; here we deliberately
   normalize *only* the structural kinds and leave atomics on the match path. A
   structural term that *contains* `Var`s (e.g. `Item(REQ_ID, Met(SUB), _)`)
   still counts as structural — `Unify` binds the inner vars in both directions
   (matching `_is_ground_value`, which also treats a var-containing `Call` as a
   normalizable value since it does not recurse into `Call`/`Compound` args).

2. **`_normalize_structural_head_args(head, body) -> (new_head, new_body)`**
   For each top-level head field whose value is structural, replace it with a
   fresh `Var` and **prepend** a `Unify(Var, value)` goal to `body` (prepended so
   the inner vars are bound before the original body runs). Returns the head
   unchanged with no extra goals when nothing qualifies. Only applies to
   term-instance heads (the head itself is never a bare `Compound`/`Call`/
   `KWTerm` for a user predicate; its *fields* may be).

3. **`LogicModule.define_predicate`** (and any sibling assert path)
   - Fact (`body == [True]`) + normalizable → existing `_normalize_dataclass_fact`
     (already covers structural args; unchanged).
   - Otherwise (ruled clause) → `_normalize_structural_head_args(head, body)`.
   Verify the other clause-entry paths share this normalization:
   `LogicModule.assert_fact`, the `assertz`/`asserta` builtins, and the import
   hook's `_define_predicate` / `_assert_fact`. Route them through one shared
   helper so behaviour can't drift between load paths.

### Data flow

```
.clausal source → transformer → Predicate node (head, body)
   → define_predicate:
        ruled & structural head arg?  → hoist to Var + prepended Unify
   → Database.assertz(Clause)
   → compiler: head arg is now a Var → MatchAs capture; Unify in body
   → arg_index: recovers key from the Unify goal (indexing intact)
   → runtime: Unify destructures (input) / constructs+binds (output)
```

### Error behaviour (intended change)

For an **undeclared** bare functor (`point(1,2)` with no declared/imported
`point`), the prepended `Unify(Var, Call(LoadName('point'), …))` will, in output
mode, attempt to construct `point(...)` and raise the existing helpful error
("`point/2` is not in scope as a term class — import it first"). This replaces
today's silent no-solution and is consistent with how facts already behave.
Declared/imported constructors and functor-instances construct and bind cleanly.
We will assert this consistency (fact and rule raise the same way) in a test.

---

## Testing

- **Extend `tests/test_head_match_imported_compound.py`** with output-mode cases:
  an unbound `Var` caller in the structural-head position of a *rule* must bind
  to the constructor (`Check(X, "matched") → X = Wrap(_)`), including the nested
  `Item(REQ_ID, Met(SUB), _)` case.
- **Rule/fact parity:** assert the rule form now matches the fact form
  (`Check` vs `CheckFact`) in output mode.
- **Input-mode regression:** all existing input-mode and `CheckIndexed`
  indexing tests must still pass unchanged.
- **Undeclared-functor consistency:** a rule and a fact with an undeclared
  functor raise the same "not in scope as a term class" error in output mode.
- **Red-green:** new output-mode tests fail before the change, pass after.
- **Regression sweep:** `test_compiler`, `test_first_arg_index`,
  `test_groundness_dispatch`, `test_head_match_imported_compound`,
  `test_compiled_programs`, `test_numeric_head_literal`, plus the string/bytes
  head-pattern suites. Run file-by-file (full `pytest tests/` OOMs this box).

---

## Out of scope

- **Auto-minting undeclared compound data constructors** (the `point(1,2)`
  construction itself). Tracked separately; this spec only routes structural
  head args through `Unify` so *constructible* terms bind in both modes.
- Atomic head literals (already fixed).

---

## Done when

- A `Compound` / imported-`Call` / functor-instance head literal in a ruled
  clause binds an unbound `Var` caller (output mode) and still matches a ground
  caller (input mode), with first-arg indexing intact.
- Output-mode and parity regression tests added, red-green verified.
- The `WARNING (== / structural-match-vs-unification bug class)` comments at the
  three `head_match.py` sites are removed, and findings #8–#10 in
  `todo/equality-vs-unification-audit.md` marked FIXED.
