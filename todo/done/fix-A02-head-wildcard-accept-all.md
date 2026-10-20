# fix(A02-F003): unguarded accept-all wildcard for unhandled head-literal types

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/findings.md` A02-F003
**Tests:** `tests/audit_2026_07_05/test_02_compiler_heads.py::TestF003ExoticHeadWildcard` (5 xfail — flip to pass)

## Bug

`head_to_match_pattern`'s final fallback (`head_match.py:617-618`) is

    return ast.MatchAs(pattern=None, name=None)   # wildcard, NO guard

Any head-literal type without an explicit branch — `datetime.date`,
`Decimal`, `tuple`, `set`, `frozenset`, `Path`, any "native Python objects
are first-class ground terms" value (cheat-sheet §6) — therefore matches
EVERY caller argument (wrong solutions in input mode) and never binds an
unbound caller (silent no-bind in output mode). This is precisely the
"value-rejecting wildcard fallback ... masked this whole class of bug"
called out in the Call-branch comment at `:565-575`, still live one branch
below it.

**Reachable route:** runtime `assertz` of a dataclass/PredicateMeta fact.
`builtins/database_ops.py:20-47` normalizes only `Compound` facts to
Var+Unify; dataclass facts pass through on the false claim their "field
patterns work correctly". Repro: `assertz(dyn_date(date(2026,1,1),1))` then
`dyn_date(date(1999,9,9), R)` → succeeds with `R=1`.

Same unguarded wildcard for **var-functor Compound heads**
(`head_match.py:539-541`) — no executable route found from .clausal;
direction blocked on parked A01-D004 (Compound var-functor support level).

## Fix direction

Two complementary layers (do both):

1. **head_match (root fix, covers all asserters):** replace the bare
   wildcard fallback with capture + unify guard, exactly like the atom
   branch (`:593-597`): capture `_xcapN`, append a `("scalar-ish", cap,
   term)` guard, and in `compile_head_to_match_case` emit
   `unify(_xcapN, <ref>, trail)`. The literal cannot go through
   `ast.Constant` (CPython rejects non-primitive constants) nor reliably
   through `term_to_ast_expr` (raises NotImplementedError for e.g.
   `Fraction`); inject the VALUE itself into the compiled function's
   globals under a fresh `$headlit_N` key (base_globals already carries
   non-identifier keys, cf. `_bucket_key`) and reference it by name.
   When there is no `list_guards` sink, keep the current wildcard as the
   degraded path (matches the scalar branches' structure).
2. **database_ops (defence in depth, A09 boundary):** extend
   `_normalize_fact_clause` to hoist ground non-Var fields of dataclass
   facts the same way `_normalize_dataclass_fact` does at define time —
   deletes the reachable repro independently of (1).

Var-functor Compound: leave the wildcard but note it in the A01-D004
resolution; a functor-var head should probably also become capture+unify
once its semantics are decided.

## Acceptance

- 5 xfails flip (date/tuple/set/Decimal mismatches now FAIL; date output
  mode BINDS); `test_control_date_true_positive` stays green.
- `tests/test_structural_head_output_mode.py` and
  `tests/test_numeric_head_literal.py` stay green.
- Add a guard that `head_to_match_pattern` can no longer emit an unguarded
  accept-all for a non-Var term — extend
  `compiler/invariants.assert_head_pattern_unify_safe` if practical.
