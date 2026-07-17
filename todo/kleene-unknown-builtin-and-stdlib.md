# Strong-Kleene stdlib module + `Unknown` builtin truth value

## STATUS: PROPOSED 2026-07-17 — investigation done, not yet built
**Child todo:** [kleene-nary-connectives-and4-or4.md](kleene-nary-connectives-and4-or4.md) —
n-ary `and4/or4 ... and9/or9` + list folds (Order 2, assigned to Opus; settles the naming
question as lowercase snake_case with numeral = arity).

## Motivation
Two corpus domains hand-write the same strong-Kleene machinery from scratch:
- `clausify-domains/eu/ai_act/prohibited_practices/__init__.clausal:122-145` — 9-row `and3/3` +
  9-row `or3/3` fact tables + `status_from_truth/2`, plus ~20 `tri_<key>/2` reader **pairs**
  (2 clauses each) mapping absent profile keys to the atom `unknown`.
- `clausify-domains/eu/market_integrity/mar_market_manipulation/__init__.clausal` — same tables again.
The "three-valued limb logic" pattern is a documented family standard (deontic domains), so
duplication will grow with the corpus.

Today's truth values are Python `True`/`False` (process-wide identity) plus the bare atom
`unknown`, which is **module-scoped** and must be exported for tests/oracle to unify on the same
object (see ai_act export list line 55 — a known module-scoped-atom pitfall).

## Proposal (two independent pieces)

### 1. `Unknown` builtin constant (Titlecase, sits beside True/False)
- Syntactically safe: logic variables are only ALL_CAPS or `_x`-prefixed
  (`clausal/logic/goal_expansion.py:203-211`); `"Unknown".isupper()` is False, so it resolves as a
  plain name, never a variable.
- Mechanism already exists: inject a singleton into `predicate_builtins`
  (`clausal/import_hook.py:212-246`, same as `Quantity`, `BoolEq`) → available in every module,
  no declaration, no export, `-strict_atoms`-proof, process-wide identity like True/False.
- Singleton class in `clausal/terms.py` with `__repr__` → `"Unknown"`; hashable (clause indexing ok).

### 2. `clausal/stdlib/kleene.clausal` (next to `reif.clausal`, which is the precedent)
- `And3/3`, `Or3/3`, `Not3/2` fact tables over `True/False/Unknown` — pure, first-arg-indexed,
  fully relational, so "inference in any direction" (e.g. `And3(X, False, R)`) falls out of ordinary
  unification. **Do NOT implement as a Python `@_builtin`**: a 9-row indexed table costs nothing and
  a Python builtin would have to hand-code the relational enumeration to preserve directionality.
- Chain folds: `And3List(LIST, R)` / `Or3List(LIST, R)` folding the tables over a list — this is the
  "A and B and C and ..." case. Forward evaluation is linear; backward queries enumerate (fine at
  limb scale, ~2-6 conjuncts).
- Profile reader: `TriGet(PROFILE, KEY, T)` — bound value if key present, `Unknown` if absent.
  This kills the biggest boilerplate (2 clauses × ~20 keys per domain), and is the piece most worth
  a Python builtin (mirrors existing `get/3`; `clausal/logic/builtins/` registry via `@_builtin`).
- **Do NOT touch the language's `and`/`or`**: those are control constructs (compiled to
  `Sequence`/`Alternate` CPS in `clausal/logic/compiler/terms_to_goalop.py:135-233`); Kleene truth
  values here are *data*. Conflating goal success with truth values is a deep semantic change with
  no payoff at current scale.

## Design questions (parked, not asked interactively)
1. **Naming**: stdlib uses TitleCase predicates (`MemberdT`, `If` in `reif.clausal`) but the domain
   corpus writes `and3/or3` snake_case. `And3/Or3` vs `and3/or3` for the stdlib module?
2. **`bool(Unknown)`**: should Python-level truthiness coercion raise (catches accidental use of
   Unknown in a Python `if`), or be defined? Recommend: raise `TypeError`.
3. **Goal position**: `True` compiles to empty `Sequence`, `False` to `Fail()`
   (`terms_to_goalop.py:200-208`). A bare `Unknown` goal should probably be a clear compile error,
   not a third goal outcome.
4. **Prolog round-trip**: map `Unknown` ↔ atom `unknown` in `tools/clausal_to_prolog.py` /
   `prolog_to_clausal.py`? Careful: existing domains use the module-scoped atom `unknown`; an
   automatic lowercase→builtin rewrite would silently change identity semantics. Migration story
   needed for ai_act + mar_market_manipulation (or leave old domains on their local atom).
5. **Relation to reified ITE**: `docs/reified_ite.md` uses Python `None` for "undetermined" at the
   engine level, and `None` is already a literal. Reuse `None` as the Kleene third value instead of
   a new `Unknown`? Rejected tentatively — `None` is overloaded ("no value" / absent), and
   distinguishing "key absent" from "truth value unknown" is exactly what these domains trade in.
   But confirm we're happy having *both* `None` and `Unknown` in the value vocabulary.
6. **Constraint-level upgrade** (future, only if backward queries over long chains get slow):
   3-valued propagation via attributed-variable hooks (watched operands), analogous to the existing
   two-valued CLP(B) (`clausal/logic/_clpb_core.c`, `BoolEq`/`BoolImpl`). Not warranted now.

## Acceptance sketch
- ai_act + MAR domains rewritten on the stdlib module lose their local tables/readers and their
  `unknown` atom export, byte-identical verdicts on the existing fixture suites.
- `And3(X, Y, False)` enumerates the 5 assignments; `And3List([True, Unknown, X], False)` gives `X=False`.
- `Unknown is Unknown` unifies across modules without any export.
