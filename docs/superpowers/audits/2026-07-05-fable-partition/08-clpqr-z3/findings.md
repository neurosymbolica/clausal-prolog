# Findings — A08 CLP(Q/R), Z3 & ortools

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.

All Test refs are in `tests/audit_2026_07_05/test_08_clpqr_z3.py`.
Oracles used: hand-checkable `fractions.Fraction` arithmetic and unsatisfiable
linear systems (CLP(Q)); IEEE/`math` semantics (CLP(R)); the `z3` package and
Python arithmetic semantics (Z3/ortools adapters). No Prolog CLP(Q) oracle was
runnable on this box (scryer-prolog is on PATH but ships no `library(clpq)`;
gprolog is not installed) — see `todo/audit-2026-07-05/investigate-A08-clpq-prolog-oracle.md`.

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A08-F001 | correctness (critical) | `fix_variable` overwrites tableau bounds instead of intersecting — tableau-only bounds (posted by single-var `q_le`/`q_ge`, which never update the `QVar` attr) are silently destroyed on unification | `clausal/logic/clpq.py:717-718` (`self.lo[vid] = value; self.hi[vid] = value`), interacts with `q_le` single-var path `clpq.py:391-399` | `in_q(X,0,100); q_le(X,5); unify(X,50)` | expected fail; actually succeeds (X<=5 AND X=50 accepted) | `test_qle_bound_then_unify_outside_fails` | `fix-A08-clpq-fix-variable-bound-overwrite.md` |
| A08-F002 | correctness (critical) | Gaussian elimination never re-checks bounds of the pivot (parametric) variable — unsatisfiable equality systems are accepted; the comment at `clpq.py:315-318` explicitly skips the check but nothing downstream performs it. `_propagate_determined` also overwrites bounds (`:366-368`) | `clausal/logic/clpq.py:263-329` (`add_equality`), `:331-369` | `in_q(X,0,10); in_q(Y,0,10); q_eq(X+Y,100)` | expected fail; actually succeeds (and a later `maximize(X+Y)` fails as if unbounded) | `test_parametric_bounds_infeasible_eq_fails` | `investigate-A08-clpq-bound-enforcement.md` |
| A08-F003 | correctness (high) | `in_q(X, lo, hi)` with `lo > hi` succeeds — the fresh-registration path has no empty-interval check (only the already-registered path checks `new_lo > new_hi`) | `clausal/logic/clpq.py:1001-1004` (`_post_q_domain`, `state is None` branch) | `in_q(X, 10, 0)` | expected fail; actually succeeds (poisoned var that rejects every later binding) | `test_in_q_empty_interval_fails` | `fix-A08-clpq-empty-domain-check.md` |
| A08-F004 | correctness (high) | Strict inequalities are `<=` + passive linear diseq — unsound: `{X<Y, Y<X}` accepted; `{X<Y}, X is Y` accepted; `{X!=Y}, X is Y` accepted (the var-var hook path calls `add_equality` but never `_check_diseqs`, and `_check_diseqs` cannot see aliasing while coefficients reference two now-equal columns) | `clausal/logic/clpq.py:1199-1203` (`q_lt`), `:1137-1169` (`q_ne`), `:1053-1075` (`_q_hook` var-var path), `:740-770` (`_check_diseqs`) | `q_lt(X,Y); q_lt(Y,X)` or `q_lt(X,Y); unify(X,Y)` | expected fail (SICStus/Holzbaur fails; Holzbaur uses epsilon-augmented rationals for strict bounds); actually succeeds | `test_strict_cycle_fails`, `test_strict_then_alias_unify_fails`, `test_ne_then_alias_unify_fails` | `investigate-A08-clpq-strict-inequalities.md` |
| A08-F005 | memory + correctness (critical) | `_tableaux`/`_last_snapshot` keyed by `id(trail)` with cleanup only via a trail-undo callback — trails dropped without full undo leak their entry, and a *recycled* Trail address inherits the stale tableau: probe showed 200 independent queries accumulating 200 variables into one shared tableau (cross-query constraint contamination). `clpz3.py`/`clportools.py` use `weakref.finalize` for the same pattern; `clpq.py` does not | `clausal/logic/clpq.py:789-807` (`_get_tableau`) | loop `t=Trail(); in_q(x,0,5,t); del t` — new Trail at same address sees old tableau | expected fresh trail => fresh tableau; actual stale constraints visible + unbounded growth | `test_no_stale_tableau_on_recycled_trail_id` | `fix-A08-clpq-tableau-weakref-lifecycle.md` |
| A08-F006 | correctness (high) | `bb_inf`/`int_minimize` cannot branch on a Gaussian-eliminated (parametric) integer variable: `set_bound` on a parametric vid is invisible to `optimize` (only row/non-basic bounds are used), so branch-and-bound loops to `_BB_MAX_DEPTH` and reports failure on feasible problems | `clausal/logic/clpq.py:1604-1679` (`_bb_solve`), `:216-227` (`set_bound`) | `X,Y>=0; Y+X==3/2; bb_inf([Y], X, R)` | expected `R = 1/2` (Y=1); actually fails | `test_bb_inf_parametric_int_var` | `investigate-A08-clpq-bound-enforcement.md` |
| A08-F007 | correctness/doc-drift (medium) | Q/R mixing rules not enforced at CLP(Q) entry points, contradicting docs/clpq.md ("Mixing ... raises TypeError"; dispatch-table row `in_real` then `in_q` -> TypeError): (a) `q_eq(X, 0.1)` silently converts the float to its binary-exact `Fraction` (3602879701896397/36028797018963968, not 1/10) via `_linearize`'s float branch; (b) `in_q` on an `in_real` variable succeeds silently. Only `_q_hook` raises on direct unify-with-float | `clausal/logic/clpq.py:916-917` (`_linearize`), `:982-1020` (`_post_q_domain` — no REAL_KEY check) | `in_q(X); q_eq(X, 0.1)` / `in_real(X,0,10); in_q(X,0,10)` | expected TypeError per docs; actually silent success | `test_q_eq_float_raises_typeerror`, `test_in_q_after_in_real_raises` | `fix-A08-clpq-float-mixing-enforcement.md` |
| A08-F008 | design (low) | `entailed` ignores stored disequalities and the strictness lost by F004: `{A =\= 5}, entailed(A =\= 5)` -> False; `{X < 5}, entailed(X < 5)` -> False (SICStus: both true). Entailment is sup/inf-only over the polytope — incomplete, not unsound | `clausal/logic/clpq.py:1259-1325` | `q_ne(A,5); entailed('\\=',A,5)` | expected True; actually False | `test_entailed_diseq_after_ne`, `test_entailed_strict_after_strict` | `investigate-A08-clpq-strict-inequalities.md` |
| A08-F009 | correctness (high) | `_imod` interval formula assumes integer modulo (`[0, abs(b)-1]`): (a) excludes true values for real numerators — `1.5 % 2 = 1.5` not in `[0, 1]` -> true constraints fail (breaks the documented outward-rounding soundness guarantee); (b) for `abs(b) < 1` returns an inverted (empty) interval — every `X % 0.5` constraint is instantly unsatisfiable. Mirrored in C (`py_imod`) and Python (`_imod_py`) | `clausal/logic/clpr.py:177-185`, `clausal/logic/_clpr_core.c:419-433` | `_imod(1.5,1.5,2,2)` -> `(0.0, 1.0000000000000002)`; `_imod(0,10,0.5,0.5)` -> `(0.0, -0.4999...)`; end-to-end `real_eq(Mod(1.5,2.0), Y); unify(Y,1.5)` fails | Python float `%`: result in `[0, b)` (sign of divisor); true value must be inside interval | `test_imod_contains_true_value_real_numerator`, `test_imod_fractional_divisor_nonempty`, `test_mod_constraint_true_value_accepted`, `test_mod_constraint_fractional_divisor_posts` | `fix-A08-clpr-imod-interval.md` |
| A08-F010 | correctness (critical — non-termination) | Strict `<` propagation on aliased/cyclic constraints never terminates: `RealLtConstraint.propagate` narrows by one ULP per pass and re-queues itself; `{X<Y}, X is Y` and `{X<Y, Y<X}` walk the interval ULP-by-ULP (~1e17 steps over [0,10]) — a hang instead of a failure | `clausal/logic/clpr.py:556-568` (`RealLtConstraint`), `:588-594` (`_propagate`) | `in_real(X,0,10); in_real(Y,0,10); real_lt(X,Y); unify(X,Y)` — subprocess timeout | expected prompt failure (SICStus CLP(R) fails); actually hangs | `test_real_lt_alias_unify_fails_promptly`, `test_real_strict_cycle_fails_promptly` (subprocess + timeout) | `fix-A08-clpr-strict-and-ne-aliasing.md` |
| A08-F011 | correctness (high) | `RealNeConstraint` never detects aliasing: after `{X != Y}, X is Y` both sides deref to the same var; the constraint only fails when the (shared) interval is a point — the unsat store is accepted | `clausal/logic/clpr.py:571-583` | `real_ne(X,Y); unify(X,Y)` | expected fail; actually succeeds | `test_real_ne_alias_fails` | `fix-A08-clpr-strict-and-ne-aliasing.md` |
| A08-F012 | correctness (low — Python-fallback only) | `_imul_py` (and sibling `min()/max()`-over-corners fallbacks) propagate NaN from `0 * inf` corners: `_imul_py(0,1,-inf,2)` -> `(nan, nan)` -> `_narrow_real` treats NaN as wipeout -> spurious failure. The C versions use `fmin/fmax` which skip NaN (`_clpr_core.c:44-54`), so the installed build is unaffected; a build without the C ext silently changes semantics | `clausal/logic/clpr.py:85-87` (`_imul_py`), also `_idiv_py` corners | `_imul_py(0.0, 1.0, -math.inf, 2.0)` vs `_imul(...)` | expected `(-inf, 2.0...)` (C parity); actually `(nan, nan)` | `test_imul_py_nan_corner_matches_c` | `fix-A08-clpr-pyfallback-nan-corners.md` |
| A08-F013 | correctness (high) | No attribute hook is registered for `Z3_KEY` (nor `OR_KEY`/`LP_KEY`): Clausal-side unification of a solver-registered var is never reflected in the backend store. `in_z3(X,1,10); X is 99` succeeds and `z3_check` stays sat; after `A==B, A is 3`, `label_z3([B])` enumerates 1..10 — answers inconsistent with the current substitution | `clausal/logic/clpz3.py` (only `put_attr`, no `register_attr_hook` anywhere); same in `clportools.py`, `clportools_lp.py` | see Test refs | expected: binding posts `z3v == value` (or at least fails out-of-domain, matching CLP(FD) `in_domain` semantics); actual: silent desync | `test_binding_out_of_domain_fails`, `test_label_respects_bindings` | `investigate-A08-solver-store-sync-hooks.md` |
| A08-F014 | correctness (medium) | Z3 translation of `FloorDiv`/`Mod` diverges from Python (= Clausal arithmetic) semantics: Int sort maps to SMT-LIB Euclidean div/mod (`7 // -2` -> -3 vs Python -4; `7 % -2` -> 1 vs -1); Real sort maps `FloorDiv` to *true division* (`7 // 2` -> 7/2) | `clausal/logic/clpz3.py:234-239` (`clausal_to_z3`) | `z3_eq(FloorDiv(7,-2), X); label_z3` -> -3 | Python floor-division/modulo semantics expected | `test_floordiv_negative_divisor`, `test_mod_negative_divisor`, `test_floordiv_real_sort` | `fix-A08-z3-floordiv-mod-translation.md` |
| A08-F015 | correctness (medium) | CP-SAT translation of `FloorDiv`/`Mod` diverges from Python semantics: `AddDivisionEquality` truncates toward zero (`-7 // 2` -> -3 vs -4); `AddModuloEquality` follows the numerator's sign AND the helper `rem` var is created with domain `[0, 10^9]` — so `X == -7 % 3` has NO solution at all (Python: 2) | `clausal/logic/clportools.py:459-475` (`clausal_to_cpsat`) | see Test refs | Python floor-division/modulo semantics expected; actual -3 / infeasible | `test_floordiv_negative_numerator`, `test_mod_negative_numerator` | `fix-A08-ortools-floordiv-mod-translation.md` |
| A08-F016 | correctness (medium) | `or_minimize`/`or_maximize` (and `lp_minimize`/`lp_maximize`) bind every `rev_map` var to its model value but ignore `unify` failures — an "optimal" solution is yielded even when it contradicts existing bindings (probe: Y bound to 99, model assigned Y in 1..3, yield still happened) | `clausal/logic/clportools.py:995-998, 1016-1019`; `clausal/logic/clportools_lp.py:490-495, 514-519` | `or_in(X,1,3); or_in(Y,1,3); Y is 99; or_minimize(X,V)` yields | expected 0 yields (or upfront failure); actually yields with Y=99 | `test_or_minimize_unify_failure_not_ignored` | `fix-A08-ortools-optimize-unify-failures.md` |
| A08-F017 | design/doc-drift (low) | LP strict `<`/`>` compiled with a hard-coded `+-1e-6` epsilon fudge — undocumented approximation (`x < 5` => `x <= 5 - 1e-6`); also `ArithNeq` in an LP block raises a bare `TypeError` with no hint that LP cannot express `!=` | `clausal/logic/clportools_lp.py:346-354` | `lp block (X < 5); lp_maximize(X)` -> 4.999999 | documented behaviour needed (or reject strict on continuous vars) | (probe-confirmed; doc issue, no xfail test) | `fix-A08-ortools-lp-strict-epsilon-doc.md` |
| A08-F018 | design (low) | `or_minimize`/`or_maximize` permanently install the objective on the shared `CpModel` (never cleared/scoped) and accept `FEASIBLE` (time-limit, not proven optimal) as the "optimal" value; `_z3_optimize`'s `opt.upper()` can report a non-attained supremum for strict constraints; unlike `clpq.maximize`, `maximize_z3` binds only the objective value, never the variables (doc parity gap) | `clausal/logic/clportools.py:987, 1008`; `clausal/logic/clpz3.py:1010-1028` | code reading | scoped objective + OPTIMAL-only (or documented) | — | `investigate-A08-parked-design-decisions.md` (A08-D005) |

## Coverage map

Dimensions per public entry point: input mode (ground args), **output mode**
(unbound result/var), partial/aliased args, empty/degenerate inputs,
backtracking + trail restoration, error paths, differential oracle.

| API | ground | output/var | aliased/partial | degenerate/empty | backtrack | error path | oracle | notes |
|---|---|---|---|---|---|---|---|---|
| clpq `in_q/1,3` | probe (ground within/outside bounds) | test | — | lo>hi (**F003**), point lo==hi probe | guard | bool rejected (read) | Fraction | |
| clpq `q_eq` | test | test (binds var) | alias via hook (**F004**) | contradiction/redundant probe | guard | float operand (**F007**) | Fraction | 3-var exactness guard |
| clpq `q_le/q_ge` | test | test | multi-var slack path guard | zero-coeff (read) | guard | — | Fraction | single-var bound not attr-synced (**F001**) |
| clpq `q_lt/q_gt/q_ne` | probe | test | **F004** | cycle **F004** | probe | — | hand-unsat systems | strict = le+diseq |
| clpq `maximize/minimize` | guard (310) | binds all vars guard | on infeasible-but-accepted store (F002 => spurious unbounded) | strict supremum guard (fails, matches SICStus) | via snapshot probe | non-linear TypeError (read) | hand simplex | |
| clpq `sup/inf` | guard | non-binding guard | — | unbounded -> fail (read) | copy-based (read) | non-linear TypeError (read) | Fraction | |
| clpq `entailed` | guard | — | — | diseq/strict (**F008**) | read-only probe | unknown type ValueError (read) | SICStus semantics (docs) | |
| clpq `bb_inf/int_minimize` | probe | test | parametric int var (**F006**) | depth cap (read; flagged) | snapshot (read) | non-linear TypeError (read) | hand MIP | |
| clpq `dump_q` | guard | guard | — | empty store (read) | — | — | no-slack-leak guard | |
| clpq module block | guard (chain + eq + maximize) | guard | — | — | — | unsupported node TypeError (read) | Fraction | |
| clpq tableau lifecycle | — | — | — | dropped trails (**F005**) | undo-restore guard | — | — | id(trail) keying |
| clpr `in_real` | guard | guard | — | empty intersection guard | guard | bool rejected (read) | IEEE | |
| clpr `real_eq/le/lt/ne` | probe | guard | aliased (**F010/F011**) | strict cycle (**F010** hang) | guard | — | IEEE/math | |
| clpr interval prims (`_iadd`..`_imod`) | spot tests | — | — | 0-in-denominator, NaN corners (**F012**) | — | — | math oracle | `_imod` (**F009**) both C+py |
| clpr `label_real` | guard (sqrt2) | guard | — | already-resolved (read) | generator restore (read) | — | math.sqrt | |
| clpz3 `in_z3`/`z3_eq`.. | guard | label guard | binding desync (**F013**) | lo>hi fails (read) | push/pop guard | sort mismatch TypeError (read) | z3 direct | |
| clpz3 labeling (`label_z3`, bool/real/bv/polymorphic) | enumeration guard | guard | — | all-ground -> check (read) | blocking scope popped (read) | unregistered ValueError (read) | z3 | |
| clpz3 `FloorDiv/Mod` translation | **F014** | test | — | — | — | — | Python semantics | Real-sort FloorDiv also wrong |
| clpz3 `taut/sat_count/z3_try/entailed` | guard | guard | — | constant expr (read) | probe push/pop (read) | — | truth tables | |
| clpz3 optimize | probe | probe | — | +-oo handling (read) | — | — | z3 Optimize | vars not bound (F018/D005) |
| clportools cpsat (or_in, constraints, label_or, or_count) | guard | guard | — | scoped count guard, count-after-label guard | act-lit scopes guard | unregistered ValueError (read) | cp_model direct | |
| clportools `FloorDiv/Mod` | **F015** | test | — | negative numerator infeasible (**F015**) | — | — | Python semantics | |
| clportools optimize | probe | probe | stale bindings (**F016**) | FEASIBLE-as-optimal (F018, read) | undo-after-yield (read) | — | — | |
| clportools_lp (lp_var, blocks, solve, min/max) | guard (310) | guard | — | strict epsilon (**F017**) | scope rebuild (read) | unknown-solver ValueError (read) | glop | shares F016 |
| clportools_graph (max_flow, min_cost_flow, assignment, knapsack) | guard | guard | — | empty costs (read) | one-shot | type errors (read) | hand-checked optima | |
| clportools_routing (tsp/vrp/vrptw) | guard (tsp n=4, opt 80) | guard | — | adaptive-timeout failure on large inputs (read) | one-shot | — | hand-checked | GLS is anytime — optimality not guaranteed (doc note) |
| `_clpr_core.c` memory | refcount_stable over interval ops + post/solve loop | — | — | — | — | — | — | no leak observed |

Dry-pass record: pass 1 (coverage map -> probes P1-P15, R1-R6, Z-probes,
OR-probes) surfaced F001-F016; pass 2 (misc batch: mixing, module blocks,
taut/sat_count, TSP, dump_q, sup/inf) surfaced F007/F017 plus regression
guards only; pass 3 was dry apart from the code-reading design note F018.
Free-threading: module-level dicts `_tableaux`, `_z3_states`, `_cpsat_states`,
`_lp_states` keyed by `id(trail)` with no locking are data races under 3.14t —
`unconfirmed — needs 3.14t`.

## Seam notes (for A12)

- **Dispatch boundary (A06/A07):** the Q/R/Z domain dispatch and the mixing
  guard `_check_no_mixed_rational_real` live in `clpfd.py` /
  `_clpfd_propagate.c`, not in this subsystem. F007 shows the CLP(Q) entry
  points do not defend themselves when called directly (builtins `in_q/3`,
  `clpq.rational` bypass the dispatch guard).
- **Cross-type unification (A01-D001 / A02-D002):** `q_eq(X, 5)` binds X to
  `Fraction(5, 1)`, not `int 5`; downstream indexing/tabling keyed by type will
  see `Fraction`, not `int`. Same for Z3 model extraction (`z3_to_python`
  returns `Fraction` for rationals).
- **Attr-hook protocol (A04-D001, A05):** `check_implied_bindings` calls
  `unify` from inside `_q_hook` cascades — reentrancy with `dif`/`freeze`
  hooks on the same variable was not exercised here.
- **Free-threading:** all four backends key global dicts by `id(trail)` with
  no locking; under 3.14t concurrent queries on different trails race on the
  dicts and (for clpq) on `_last_snapshot`. `unconfirmed — needs 3.14t`.
- **`weakref.finalize(trail, ...)`** in clpz3/clportools assumes `Trail` is
  weakref-able — holds today (A01/A04 own Trail's layout).
