# Findings — A07 CLP(B) & SAT

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.

Files audited: `clausal/logic/clpb.py`, `clausal/logic/clpsat.py`,
`clausal/logic/_clpb_core.c`, `clausal/logic/builtins/sat_constraints.py`
(builtin surface for sat/taut/sat_count/bool_labeling lives in
`clausal/logic/builtins/constraints.py:100-134` — read, not modified).

Test file: `tests/audit_2026_07_05/test_07_clpb_sat.py` — **35 passed, 12 xfailed**
(per-file run, pyenv 3.13.3, C extension active).

Oracle: brute-force truth-table enumeration (independent evaluator in the test
file). 120-formula random single-post oracle and 60-trial multi-post network
oracle both pass — **standalone-formula semantics of sat/taut/sat_count/
bool_labeling are correct**; every divergence found is at a boundary
(constraint store, aliasing, C recursion, Python interop), not in the BDD
algebra itself. A 300-case C-vs-local-reference differential on
`apply`/`restrict`/`_count_paths` also found the C kernels correct.

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A07-F001 | correctness/perf (blocker at scale) | **`_collect_bdd_var_ids` traverses the shared BDD as a *tree* (no visited set) — `sat`/`sat_count`/`_propagate_forced`/`_bool_hook` go exponential in #vars on DAG-shaped BDDs.** Both the Python fallback (`clpb.py:540`) and C `c_collect_ids_rec` (`_clpb_core.c:709`) recurse on `high`/`low` without deduplication, so a 59-node XOR-chain BDD is walked 2^n times. | `clausal/logic/clpb.py:540-546`, `clausal/logic/_clpb_core.c:709-725` | `sat(X1^X2^...^X26)` takes 19 s (4x per +2 vars); a 63-var XOR `sat_count` hangs effectively forever. Measured: xor-16 0.02 s, xor-20 0.29 s, xor-24 4.6 s, xor-26 18.9 s | Linear in BDD size (the BDD is 2 nodes/level); ms | `test_A07_F001_xor_chain_sat_not_exponential` (subprocess, 5 s budget) | `todo/audit-2026-07-05/fix-A07-collect-bdd-var-ids-exponential.md` |
| A07-F002 | correctness | **Var-var aliasing does not rebuild the BDD from `sat_expr` — unsatisfiable stores survive posting, forced values are missed.** `_bool_hook` (clpb.py:730-752) just conjoins the two stale BDDs, in which the aliased variables still occupy *two distinct* BDD levels. `sat(X^Y), X is Y` succeeds (Prolog CLP(B): fails immediately; labeling then finds 0 solutions — a floundering "solution" with unbound vars escapes to the user). `sat(X|Y), X is Y` leaves X unbound (must force X=1). The module docstring and `BoolState.sat_expr` advertise "formula storage for aliasing rebuild" — the rebuild is not implemented, and `sat_expr` only keeps the *latest* formula of a merged network anyway (clpb.py:500), so a correct rebuild needs the conjunction of all posted formulas, not one. | `clausal/logic/clpb.py:730-752`, `399-412` | `sat(BitXor(X,Y)); unify(X,Y)` → True; `bool_labeling([X,Y])` → 0 sols | unify must fail / X forced to 1 | `test_A07_F002_alias_after_xor_must_fail`, `test_A07_F002_alias_or_propagates_forced` | `todo/audit-2026-07-05/fix-A07-clpb-aliasing-no-rebuild.md` |
| A07-F003 | correctness (vs claimed reference design) | **`taut/2` ignores posted constraints** — it builds the BDD of the bare expression only (clpb.py:549-561). After `sat(BoolImpl(X,Y))`, `taut(~X \| Y, T)` fails instead of unifying T=1. The module claims to follow "Markus Triska's reference design", where taut is entailment w.r.t. the current store. `docs/clpb.md` is silent on store interaction (only forced-value cases are exercised there, which work by accident of propagation). | `clausal/logic/clpb.py:549-561` | `sat(BoolImpl(X,Y)); taut(BitOr(Invert(X),Y), T)` → fails | T=1 (entailed) | `test_A07_F003_taut_entailed_by_store` | design-gated: `todo/audit-2026-07-05/investigate-A07-parked-design-decisions.md` (A07-D001) |
| A07-F004 | correctness (vs claimed reference design) | **`sat_count/2` ignores posted constraints** — counts the standalone formula (clpb.py:564-595). After `sat(BoolEq(X,Y))`, `sat_count(X \| Y, N)` gives N=3; Triska semantics (count assignments satisfying Expr AND store) gives 1. It also does not post Expr as a constraint (Triska's does). | `clausal/logic/clpb.py:564-595` | `sat(BoolEq(X,Y)); sat_count(BitOr(X,Y), N)` → N=3 | N=1 | `test_A07_F004_sat_count_respects_store` | design-gated: `todo/audit-2026-07-05/investigate-A07-parked-design-decisions.md` (A07-D001) |
| A07-F005 | correctness (unsound models) | **PySAT backend: Clausal bindings are invisible to the solver — `label_sat` enumerates models that violate the current bindings and `sat_check` reports SAT for unsatisfiable stores.** No attr hook is registered for `SAT_KEY` (`SATVarInfo` is stored but nothing reacts to binding), and `label_sat`/`sat_check` skip ground vars without assuming their values. | `clausal/logic/clpsat.py:183-210` (no `register_attr_hook`), `493-571` (ground vars skipped), `256-259` | post `X\|Y` via `sat_constraint_block`; `unify(X,0)`; `label_sat([X,Y])` yields **(0,0)**; then `unify(Y,0)`; `sat_check` → True | models within {(0,1)}; sat_check False | `test_A07_F005_label_sat_respects_clausal_bindings`, `test_A07_F005_sat_check_sees_bindings` | `todo/audit-2026-07-05/fix-A07-clpsat-bindings-invisible.md` |
| A07-F006 | memory | **Unbounded module-global growth: `_var_to_id`/`_id_to_var`/`_unique_tables` pin every CLP(B) variable and its BDD nodes forever.** `_id_to_var` holds strong refs; `_unique_tables` is keyed by `id(var)` and never pruned. 1000 throwaway two-var queries leave 2000 permanent entries in each table (measured). Long-running processes leak linearly per query. (The C kernel itself is refcount-clean: `refcount_stable`/`getrefcount_stable` over 2000-iteration apply/restrict/negate/collect loops show zero growth for *fixed* vars.) | `clausal/logic/clpb.py:79-116` | loop `sat(X\|Y)` with fresh Vars x1000 → `len(_id_to_var)` +2000 | bounded (weak refs / per-trail scoping) | `test_A07_F006_global_tables_bounded` | `todo/audit-2026-07-05/fix-A07-clpb-global-table-leak.md` |
| A07-F007 | crash (C) | **Unbounded C-stack recursion in `c_apply_rec`/`c_restrict_rec`/`c_collect_ids_rec` — deep BDDs segfault the interpreter.** A 100 000-level chain BDD (built iteratively via `make_node`) crashes with SIGSEGV inside `negate` (= `c_apply`); 10 000 levels survive. The Python fallback raises a catchable `RecursionError` instead. New C bug, not in `todo/cross_cutting_issues.md`. | `clausal/logic/_clpb_core.c:465-520, 524-559, 709-725` | subprocess: build 100k-deep chain, `negate(bdd)` → exit -11 | error raise (e.g. depth check / Py_EnterRecursiveCall) not process death | `test_A07_F007_deep_bdd_no_segfault` (subprocess) | `todo/audit-2026-07-05/fix-A07-clpb-c-recursion-overflow.md` |
| A07-F008 | correctness (latent) / maintenance | **The saved "Python reference implementations" are corrupted by C rebinding: `_count_paths_py` returns wrong counts whenever the C extension is loaded.** `_count_paths_py = _count_paths` saves the function object, but its *body* recurses through the module-global name `_count_paths`, which is rebound to the C wrapper — and the C wrapper drops `current_level`/`memo`, restarting every subtree at level 0. Differential vs a self-contained oracle: 162/300 wrong (values can exceed 2^n). `_apply_py`/`_restrict_py`/`_negate_py` have the same rebinding trap but happen to stay correct (their inner calls produce identical hash-consed nodes). The "works without C" claim only holds when C is absent; with C present the references are unusable as oracles or fallbacks. | `clausal/logic/clpb.py:598-628, 764-799` | `_count_paths_py(bdd_with_skipped_level, lm, 4, {})` → 2 (true count 4) | 4 | `test_A07_F008_count_paths_py_reference_correct` | `todo/audit-2026-07-05/fix-A07-clpb-python-fallback-rebinding.md` |
| A07-F009 | error-path | **`bool_labeling/1` silently succeeds over non-Boolean ground elements** — `bool_labeling([2, "a"])` yields one "solution" (no unbound var found → yield). SWI clpb raises a type error; at minimum it should fail. Same for a bare non-list scalar (wrapped as `[x]`). | `clausal/logic/clpb.py:631-672` | `list(bool_labeling([2, "a"], Trail()))` → 1 solution | type error or 0 solutions | `test_A07_F009_bool_labeling_validates_ground_elements` | `todo/audit-2026-07-05/fix-A07-bool-labeling-ground-validation.md` |
| A07-F010 | design/doc-drift | **CLP(B) variables accept Python `True`/`False` and stay bound to the bool** — `_bool_hook` checks `isinstance(bound_to, int)` + `in (0,1)`, both satisfied by bools. `docs/clpb.md` (Interaction with Other Constraints) pins the domain to "0/1 (integers), not Python booleans (True/False)" and stresses bool/number distinctness (CLP(Z)/CLP(R) reject bools). Downstream arithmetic/indexing then sees `True` where rules expect `1`. Overlaps A01-D001 (bool/int conflation in unify). Note `_expr_to_bdd` deliberately accepts bools as formula *constants* (clpb.py:299) — the doc's stance on that is also unstated. | `clausal/logic/clpb.py:687-688` | `sat(X\|Y); unify(X, True)` → succeeds, `deref(X) is True` | reject, or normalize to int 1 | `test_A07_F010_python_bool_binding` | design-gated: `todo/audit-2026-07-05/investigate-A07-parked-design-decisions.md` (A07-D002) |
| A07-F011 | doc-drift (minor) | Stale coverage/comment claims: `docs/clpb.md` says "tests/test_clpb.py (87 tests)" — file has 113; `_clpb_core.c:32-33` claims `is_bdd_true/false` "also accepts value comparison as fallback" — they are pointer-compare only; `HASH_KEY = "clpb_hash"` (clpb.py:44) is exported and `__all__`-listed but used nowhere in the codebase. | `docs/clpb.md:174`, `_clpb_core.c:31-39`, `clpb.py:44` | grep | docs match code | — (doc-only) | `todo/audit-2026-07-05/fix-A07-clpb-doc-drift.md` |

Cross-cutting items **cited, not re-reported** (see `todo/cross_cutting_issues.md`):
`_clpb_core.c` uses `m_size = -1` global module state (issue #5, no sub-interpreter
support) and module-static `BDD_TRUE_OBJ`/`BDD_FALSE_OBJ` init (benign on GIL
builds; free-threading claims **unconfirmed — needs 3.14t**, issue #4 pattern).
`_clpb_core.c` takes no Trail argument, so cross-cutting issue #1 (Trail cast)
does not apply to it.

## Coverage map

Dimensions: input mode / output mode (unbound result arg) / test mode (bound
result arg) / partial-ground exprs / constants / error paths / backtracking &
trail restoration / aliasing / network merging / C-vs-reference differential /
memory & refcounts / scale (deep + wide BDDs).

| Function / builtin | in-mode | out-mode | test-mode | constants | partial/bound-var exprs | error path | backtrack | aliasing | oracle diff | scale/mem |
|---|---|---|---|---|---|---|---|---|---|---|
| `sat/1` | ok (oracle x120) | ok forcing (`x&y`, `~x`) | n/a | ok 0/1/bool | ok deref'd bound vars | ok int!=0/1 ValueError, TypeError on junk | ok store restore | **F002** | ok multi-post x60 | **F001**, **F006** |
| `taut/2` | ok | ok T unbound | ok T=0/1 bound | ok taut/contra/ground | store interaction **F003** | ok | ok | — | ok | — |
| `sat_count/2` | ok | ok N unbound | ok N bound right/wrong | ok 1→1, 0→0 | reduced-away vars ok; store **F004** | — | ok | — | ok + big-int path 62/63/70 vars | **F001** |
| `bool_labeling/1` | ok constrained enum | ok | all-bound ok | ground junk **F009** | mixed ground/var ok | **F009** | ok clean undo | ok (post-alias enum consistent) | ok | ok no-growth loop |
| `_bool_hook` | int 0/1 ok | forced propagation ok | — | bool **F010**; 2/-1/"a"/1.0 rejected ok | chain alias transfer ok | ok | ok | conjoin-not-rebuild **F002** | — | — |
| `apply`/`negate`/`restrict`/`make_node` | ok all 6 ops | — | — | terminal table ok | — | unknown op ValueError (existing tests) | — | — | ok C=Py hash-consed identity x300 | segfault **F007**; refcount ok |
| `_count_paths` (C) | ok | — | — | ok | skipped levels ok | — | — | — | ok vs local reference | fast/big cutoff ok |
| `_count_paths_py` etc. | **F008** | — | — | — | — | — | — | — | 162/300 wrong | — |
| `_collect_bdd_var_ids` | ok | — | — | ok | — | — | — | — | ok | **F001** |
| `.clausal` surface (`sat`, `taut`, `sat_count`, `bool_labeling`, `BoolEq`, `^ & \| ~`) | ok | ok half-adder fwd + all rows | ok | ok | rev-mode (S,C ground) leaves constrained vars ok | — | ok via solve | — | ok | — |
| `sat_constraint_block` / Tseitin | ok and/or/xor/not/eq flatten | — | — | 0/1 literals ok | — | TypeError on junk (existing tests) | ok block retract | — | ok vs truth table | — |
| `label_sat` / `sat_check` / `pysat.solve/count/model` | ok | ok | — | ground mix ok | bound-var models **F005** | unregistered var ValueError (existing tests) | ok blocking clauses cleaned, re-label ok | — | ok | — |
| `sat_at_most/at_least/exactly` | ok | — | — | ground True consumption ok | ok | type errors (existing tests) | ok | — | ok 4-var cardinality table | — |
| solver registry (`get_sat_state`) | ok | — | — | — | — | mismatch ValueError ok; unknown name (existing tests) | weakref cleanup (existing tests) | — | — | — |

Dry-pass status: two consecutive passes over this map surfaced nothing new
after F001-F011 (final pass re-probed network merging, big-int boundary, trail
callbacks, and C refcounts — all clean).

## Seam notes (for A12)

- **Attr-hook protocol (A01/A04/A05 seam):** `_bool_hook` conforms to the
  boolean hook contract; A04-D001's semidet-hook limitation does not bite
  CLP(B) (propagation is deterministic), but any hook-contract redesign must
  include `B_KEY` (registered at `clpb.py:758`).
- **A01-D001 (bool/int conflation in `unify`)** directly gates A07-F010: the
  hook-level fix is trivial either way, but the *unify* layer is what delivers
  `True` to the hook as an int.
- **CLP(B) vs CLP(Z)/CLP(R)/dif independence** (`docs/clpb.md` claims all hooks
  fire independently): not probed here beyond attribute-key disjointness —
  flagged for A12 (a var carrying both `"fd"` and `"clpb"` attrs bound to 0/1).
- **PySAT trail integration:** `sat_push`/`label_sat` use `trail.record`
  callbacks (A04 runtime seam); callback double-remove is guarded in
  `label_sat` but `sat_push`'s callback would raise `ValueError` if its
  activation literal were ever removed by other means — currently unreachable,
  noted only.
- `builtins/constraints.py` (A09 surface) wraps clpb functions 1:1 — audited
  the wrappers by executing the `.clausal` surface only.
