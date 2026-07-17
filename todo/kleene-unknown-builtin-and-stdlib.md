# Strong-Kleene stdlib module + `Unknown` builtin truth value

## STATUS: DONE 2026-07-17 — piece 1 (Unknown builtin) + piece 2 (stdlib module) both landed
Piece 1 complete: `Unknown` is now a process-wide singleton (`clausal/terms.py`) injected
into every module (`import_hook.py`) beside True/False — resolves in `-strict_atoms` with no
declaration, `bool()` raises, copy/deepcopy/pickle keep identity. Bare `Unknown` in goal
position is a compile-time `BareGoalUnknownError` naming the predicate; `clausal_to_prolog`
emits atom `unknown` (inbound untouched). `kleene.clausal` migrated off the module-scoped atom
(dropped from exports); `tri_get/3` builtin added (absent key → `Unknown`, mirrors `get/3`).
Tests: `tests/test_unknown_builtin.py` (23) + `tests/test_kleene_stdlib.py` (19) pass; full
suite 9360 passed / 2 skipped / 44 xfailed (was 9337, delta = the 23 new tests).
CORPUS MIGRATION DONE 2026-07-17 (clausify-domains 257093c + 5569262): ai_act
prohibited_practices and MAR market_manipulation now import clausal.stdlib.kleene
(and4/and5 collapse the chains), read elements via tri_get/3 → Unknown, and keep the
public limb-status atom axis unchanged. Verified: 51/51 + 25/25 interface tests,
187/187 + 8939/8939 vs oracles, 10/10 + 6/6 mutants killed.
**Child todo:** [kleene-nary-connectives-and4-or4.md](kleene-nary-connectives-and4-or4.md) —
DONE 2026-07-17 (commit 093a18d2): `clausal/stdlib/kleene.clausal` with n-ary
`and4/or4 ... and9/or9` + list folds; settles the naming question as lowercase snake_case
with numeral = arity. Migrated onto the `Unknown` builtin by this todo's piece 1.

USER DECISION 2026-07-17: `Unknown` is wanted Clausal-wide, as a builtin. The design
questions below are now SETTLED — see "Implementation plan (piece 1)" for the Opus spec.

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

## Design questions — SETTLED 2026-07-17 (user decision: Unknown Clausal-wide, as a builtin)
1. **Naming**: lowercase snake_case, numeral = arity (`and3/or3/and4...`) — settled by the child
   todo; already shipped in `stdlib/kleene.clausal`.
2. **`bool(Unknown)`**: raises `TypeError` ("Unknown has no Python truth value") — catches
   accidental use in a Python `if`/`while`. `Unknown` must never be silently truthy or falsy.
3. **Goal position**: a bare `Unknown` in goal position is a **clear compile-time error** (like the
   `BareGoalVariableError` pattern), NOT a third goal outcome. `True` compiles to empty `Sequence`,
   `False` to `Fail()` at `terms_to_goalop.py:200-208`; add the `Unknown` check right there.
4. **Prolog round-trip**: **outbound only** — `clausal_to_prolog` emits the atom `unknown` for the
   `Unknown` constant. Inbound (`prolog_to_clausal`) is left UNCHANGED: auto-rewriting the atom
   `unknown` → builtin would silently change identity semantics of existing Prolog imports.
   Document the asymmetry where the outbound mapping is added.
5. **`None` vs `Unknown`**: both exist, deliberately distinct — `None` = "no value / absent",
   `Unknown` = "truth value unknown". Reified ITE keeps its internal `None`; no unification of
   the two concepts.
6. **Constraint-level upgrade**: still parked (future work, not in scope).

## Implementation plan (piece 1: the `Unknown` builtin) — assigned to Opus
1. **Singleton** in `clausal/terms.py` (precedent: `PyThunk`, `Quantity` live there): a
   `_UnknownType` class with a single instance `Unknown`; `__repr__`/`__str__` → `"Unknown"`;
   `__bool__` raises `TypeError`; hashable (default identity hash is fine — clause indexing needs
   it); make the singleton survive copy/deepcopy/pickle (`__reduce__` returning the module-level
   name) so trailing/copying never mints a second instance.
2. **Inject Clausal-wide**: `predicate_builtins["Unknown"] = Unknown` in
   `clausal/import_hook.py` (the "Builtins injected into every predicate module" block,
   lines ~212-246, next to `Quantity`). Verify it resolves in a `-strict_atoms` module with no
   declaration (it's a real binding, not a minted atom — should hold; test it).
3. **Unification**: verify `unify`/`deref` treat the singleton as an ordinary ground constant
   (identity equality). Test `Unknown is Unknown` across two separately loaded modules.
4. **Goal-position guard**: in `clausal/logic/compiler/terms_to_goalop.py` next to the
   `goal is False`/`goal is True` cases (~lines 205-208), raise a clear error naming the predicate
   if a bare `Unknown` reaches goal position.
5. **Outbound Prolog mapping**: `tools/clausal_to_prolog.py` `_convert_constant` (~line 689) emits
   `unknown` for the singleton; inbound untouched (decision 4 above).
6. **Migrate `stdlib/kleene.clausal`** (and `tests/test_kleene_stdlib.py`) from the module-scoped
   `unknown` atom to the `Unknown` builtin; drop `unknown` from the module's export list (the
   module shipped today, commit 093a18d2 — no external users yet, clean swap is fine).
7. **`tri_get/3` builtin**: `tri_get(PROFILE, KEY, T)` — key present → unify `T` with the stored
   value; key absent → `T = Unknown`; deterministic; mirror `get/3`'s behavior for unbound/non-dict
   `PROFILE` (find `get/3` in the interpreter builtins and match its edge-case semantics).
   Register via the `@_builtin` decorator pattern (`clausal/logic/builtins/_registry.py`).
   This replaces the 2-clauses-per-key `tri_<key>` reader boilerplate in the corpus domains.

**Out of scope for piece 1**: migrating the clausify-domains corpus (ai_act, MAR) — different
repo, canonical-venv suites; happens after this lands. The reified-ITE internal `None` stays.

## Acceptance (piece 1)
- `Unknown` resolves in any `.clausal` module (including `-strict_atoms`) with no declaration,
  import, or export; `repr` is `Unknown`; `bool(Unknown)` raises `TypeError`.
- `Unknown is Unknown` unifies across two separately loaded modules (process-wide identity).
- Bare `Unknown` in goal position → compile-time error naming the offending predicate.
- `kleene.clausal` tests pass rewritten on the builtin (backward enumeration counts unchanged:
  `and4(A, B, C, False)` → 19, all-True → 1).
- `tri_get({a: True}, a, T)` → `T = True`; `tri_get({a: True}, b, T)` → `T = Unknown`;
  `tri_get(P, K, Unknown)` with `b` absent succeeds checking-mode.
- `clausal_to_prolog` emits atom `unknown` for `Unknown`; `prolog_to_clausal` behavior unchanged.
- Full pytest suite at baseline (9337 passed, 2 skipped, 44 xfailed as of commit 093a18d2).
