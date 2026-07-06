# Findings — A06 CLP(FD)

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.
Test file: `tests/audit_2026_07_05/test_06_clpfd.py` (56 passed, 23 xfailed).
All fd_* entry points run through the C accelerators (`_USE_C_DOMAINS` /
`_USE_C_PROPAGATE` both True on this box); Python twins were audited by
inspection and via the bignum-fallback helpers the C code tail-calls.

Prior art cited, not re-reported: `todo/cross_cutting_issues.md` issue 3
(Cumulative stale snapshots — weaker filtering, not unsound) and issue 8
(int64 ceilings >2^63; note F003/F004/F007 below are *distinct* bugs in the
claimed-safe paths); `implementation_plans/clpfd/todo/clpz_global_constraints_issues.md`
(cumulative per-value filtering perf, TuplesIn perf, missing automaton/lex_chain);
`C_clpfd_tiers234_issues*.md` (BFS→DFS queue order NO ACTION; linearise
overflow falls back to EqConstraint = weaker-but-sound).

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A06-F001 | correctness (unsound accept) | `!=` never evaluates arithmetic-expression operands — constraint silently unenforced | `clpfd.py:728-759` (`NeConstraint.propagate`), `:464-494` (`_ne_propagate_bignum`), `_clpfd_propagate.c:994-1227` (`ne_propagate`) | `Bad(X,Y) <- (X + 1 != Y, X is 1, Y is 2)` succeeds; `in 1..3, X+1 != Y` labels (1,2),(2,3) | ground compare must evaluate `Add(1,1)` → 2 ≠ 2 → fail; actual: structural `Add != int` → "different" → always satisfied | `TestNeExpressionBlindness` (3 xfail + 1 guard) | `todo/audit-2026-07-05/fix-A06-ne-expression-operands.md` |
| A06-F002 | correctness (completeness; contradicts cheat-sheet "works in all directions") | Output-mode linear `==` never grounds a default-domain (unbounded) var | `clpfd.py:892-910` (SumConstraint narrow), `:955-966` + `:580-590` (ScalarProduct/_bignum), `_clpfd_propagate.c:1681-1687,1849-1855` (nan guards) | `Double(X,Y) <- (Y == 2*X)`; `Double(X, 8)` → X unbound; `X == -Y, Y=3` → X unbound | X=4 / X=-3; actual: `other = total_sum − own_contribution` is inf−inf → nan-guard skips narrowing whenever the target var itself is unbounded — even when all *other* operands are ground | `TestOutputModeLinearEq` (3 xfail + 2 guards) | `todo/audit-2026-07-05/fix-A06-linear-eq-unbounded-narrowing.md` |
| A06-F003 | correctness (unsound reject) | C sum/scalar propagate in `double`; bounds ≥2^53 over-prune (guard checks only aggregate sums, not per-var contributions) | `_clpfd_propagate.c:1571-1714` (`sum_propagate`), `:1720-1894` (`scalar_propagate`), `DOUBLE_PRECISE_INT_LIMIT` guard `:1601-1606` | `Y in 2^53..2^53+2, -(2^53) + Y == 1` → fails; valid Y=2^53+1 | `1+2^53` rounds to `2^53` (ties-to-even) → Y over-pruned to {2^53} → wipeout; sums are tiny so the 2^53 guard never fires | `TestDoublePrecisionRounding::test_sum_near_2_53` (xfail) | `todo/audit-2026-07-05/fix-A06-sum-scalar-double-rounding.md` |
| A06-F004 | correctness (unsound reject) | The "bignum-safe" Python scalar helpers use float true division — large quotients round, over-pruning | `clpfd.py:592-596` (`_scalar_propagate_bignum`), `:696-700` + `:968-972` (`ScalarProductConstraint.propagate` — `(total − other)/c` via `/`) | `X in 0..2^62, 3*X == 3*(2^60+1)` → fails; valid X=2^60+1 | `float(3*2^60+3)/3` rounds → X pruned to {2^60} → recheck wipeout. Contradicts cross-cutting issue 8's "Python fallback handles correctly" | `TestDoublePrecisionRounding::test_scalar_bignum_exact_division` (xfail) | `todo/audit-2026-07-05/fix-A06-scalar-bignum-float-division.md` |
| A06-F005 | correctness (crash) | `element/3` with an unconstrained index raises ValueError instead of posting [1,n] | `clpfd.py:2152` (`fd_element` pre-`_ensure_fd(index)` → unbounded domain), `:1047-1065` (`ElementConstraint.propagate` enumerates it) | `fd_element(I, [10,20,30,20], V, t)` with fresh I | enumerate (1,10)…(4,20); actual `ValueError: Cannot enumerate unbounded domain` escapes to the caller | `TestElement::test_element_unconstrained_index` (xfail) + 4 guards | `todo/audit-2026-07-05/fix-A06-element-unbounded-index.md` |
| A06-F006 | correctness (crash) | Rational subexpression with unbound var: posting is accepted as CLP(Z), later binding raises TypeError from C domain ops on Fraction bounds | `clpfd.py:1460-1483` (`_is_rational_arg` doesn't evaluate `Div(int,int)` subtrees), `:1292-1300` (`_eval_ground` Div→Fraction), `_clpfd_domain_ops.h` `unpack_interval` (no Fraction) | `X == Y + 1/2` posts True; `unify(Y, 1)` → `TypeError: 'Fraction' object cannot be interpreted as an integer` | CLP(Q) dispatch (X=3/2) or clean failure; never an escaping TypeError | `TestRationalSubexpression::test_rational_subexpr_no_crash` (xfail) + guard | `todo/audit-2026-07-05/fix-A06-rational-subexpr-typeerror.md` |
| A06-F007 | correctness (unsound accept) | Exact INT64_MIN/MAX bounds conflated with ±inf sentinels — a legitimate finite domain becomes unbounded | `_clpfd_domain_ops.h:116-135` (`make_interval` sentinel mapping), `_clpfd_core.c:66-123` (`domain_from_range`) | `in_domain(X, 0, 2**63-1)` → domain `((0, inf),)`; `X == 2**100` then **succeeds** | values > declared max must be rejected, size finite; actual: accepts anything, `label` raises "unbounded". Related to cross-cutting issue 8 but wrong-not-error for in-range bounds | `TestInt64BoundarySentinel` (2 xfail + 1 guard) | `todo/audit-2026-07-05/fix-A06-int64-boundary-sentinel.md` |
| A06-F008 | correctness (completeness) | `in_domain` narrowing does not re-propagate the var's existing constraints | `clpfd.py:1834-1864` (`_post_domain` writes via `put_attr`, no queue/`_narrow`) | `X == Y` then `in_domain(X,1,5)`: Y stays (-inf,inf); `label([Y])` raises ValueError | Y narrowed to 1..5 (SWI: `X #= Y, X in 1..5` → Y in 1..5) | `TestInDomainPropagation` (xfail + guard) | `todo/audit-2026-07-05/fix-A06-indomain-no-propagation.md` |
| A06-F009 | correctness (C/Python divergence + doc drift) | Booleans: C `_fd_hook` accepts `True` via the `.denominator` sniff (bool *is* int in Python); Python hook rejects; ground fast paths treat True==1; docs say "explicitly rejected" | `_clpfd_propagate.c:2836-2857` (denominator probe), `clpfd.py:1731-1737` (Python hook rejects), `fd_eq`/`_both_ground` ground paths | `in_domain(X,1,5); unify(X, True)` → True (X bound to `True`); `fd_eq(1, True)` → True; `in_domain(X, True, True)` accepted | docs/constraints.md: "Booleans are explicitly rejected by CLP(ℝ) and CLP(ℤ) — distinct types"; cross-check A01-D001 (bool/int conflation) before fixing | `TestBooleanHandling` (2 xfail + 2 guards) | `todo/audit-2026-07-05/fix-A06-bool-hook-divergence.md` |
| A06-F010 | correctness (minor — delayed unsat) | `fd_ne(X, X)` succeeds at post; unsatisfiability only detected when X is bound | `clpfd.py:744-759` (both-var branch never checks identity), `_clpfd_propagate.c:1124-1219` | `fd_ne(x, x, t)` → True (SWI `X #\= X` fails); a query answering "true with pending X≠X" is a wrong maybe | fail at post (lhs is rhs after deref) | `TestNeReflexivity` (xfail + guard) | `todo/audit-2026-07-05/fix-A06-ne-reflexive.md` |
| A06-F011 | design/correctness (silent no-op) | `sum_`/`scalar_product` accept only Prolog-spelled ops; Python-style `"<="`, `"=="`, `"!="` (the language's own operator spelling) silently yield zero solutions | `clpfd.py:1983-1997` (`_FD_OPS`), `:2027-2029` (`op_fn is None` → bare `return`) | `sum_([X,Y], "<=", 6)` → 0 sols, no error | either accept Python spellings or raise ValueError on unknown op; silent failure in a cut-free language is indistinguishable from "no solution" | `TestSumOpStrings` (xfail + 3 guards) | `todo/audit-2026-07-05/fix-A06-sum-op-strings.md` (op set = design Q A06-D002) |
| A06-F012 | correctness (missed propagation, sound) | zcompare: (a) binding Order after posting propagates nothing until an X/Y event (constraint not attached to Order); (b) `zcompare(O, X, X)` never infers `=` | `clpfd.py:2719-2730` (attach skips order var), `:2561-2570` (var-order branch needs both singleton) | post `zcompare(O,X,Y)`, `O is '<'` → X stays 1..5; `zcompare(O,X,X)` → O unbound | SWI narrows X to 1..4 immediately; O='=' for aliased args. Labeling remains sound (guard) | `TestZcompare` (2 xfail + 3 guards) | `todo/audit-2026-07-05/fix-A06-zcompare-weak-propagation.md` |
| A06-F013 | correctness (missed propagation, sound) | `global_cardinality` never binds/narrows Var counts, even with all vars ground | `clpfd.py:2350-2353` (`propagate`: non-int count → `continue`) | vars=[1,1,1], pairs=[(1, CNT)] → CNT stays unbound | SWI binds CNT=3; at minimum narrow CNT to [definite, definite+possible] | `TestGlobalCardinality::test_var_count_bound_when_ground` (xfail) + 2 guards | `todo/audit-2026-07-05/fix-A06-gcc-var-count.md` |
| A06-F014 | correctness (type hole, minor) | `sum_`/`scalar_product` over non-integer elements silently succeed — strings get `_expr_domain` = (-inf,inf) and are treated as unconstrained integers | `clpfd.py:2040-2043` (no type check), `:1208-1215` (`_expr_domain` fallback returns full domain for any unknown object) | `sum_(["a","b"], "#=", 5)` → posts, yields | type failure (or clean fail) for non-FD-candidate elements (`_is_fd_candidate` exists at `:1455` but is never called) | `TestTypeHoles::test_sum_over_strings_rejected` (xfail) | `todo/audit-2026-07-05/fix-A06-sum-type-check.md` |
| A06-F015 | correctness (type hole + crash, minor) | `arith_plus` (plus/3) accepts strings: forward mode concatenates ("a"+"b"→"ab"), inverse mode raises TypeError instead of failing; `arith_max`/`arith_min` compare any type | `_arithmetic_core.c:207-255` (`py_arith_plus` — no `is_numeric` check), `:285-333` (max/min) | Clausal `plus("a","b",Z)` → Z="ab"; `arith_plus("a", Y, "ab")` → TypeError | plus/3 is an integer/numeric relation (docs/arithmetic.md); non-numeric args should fail cleanly in both modes | `TestTypeHoles` (2 xfail); `TestArithmeticCore` guards | `todo/audit-2026-07-05/fix-A06-plus-type-check.md` |
| A06-F016 | memory (latent UB — confirmed by inspection, no executed repro: would segfault the suite) | `c_add_constraint`/`c_ensure_fd`/`get_fdvar` duck-type non-FDVar attr values: after `FDVar_Check` fails they still cast to `FDVarObject *` and read struct fields directly | `_clpfd_propagate.c:504-518` (`get_fdvar` comment says "duck typing" then returns raw cast), `:645-648` (`c_ensure_fd`), `:826-841` (`c_add_constraint` reads `state->constraints` on the raw cast) | `put_attr(x, "fd", <any object with .domain/.constraints>)` then `fd_ne(x, 1)` → reads arbitrary memory at FDVarObject field offsets | either go through `PyObject_GetAttrString` (as `c_narrow`/`c_propagate` correctly do) or reject non-FDVar states | none (would crash pytest; verified by code inspection of all three sites) | `todo/audit-2026-07-05/fix-A06-capi-fdvar-duck-typing.md` |
| A06-F017 | doc-drift | `todo/cross_cutting_issues.md` issue 1 lists `_arithmetic_core.c` as casting the trail unchecked — every exported function now calls `Trail_Check()`; `_clpfd_propagate.c` never casts a trail at all (goes through the Python variables API) | `todo/cross_cutting_issues.md:8-17` vs `_arithmetic_core.c` (all 14 entry points) | n/a | update the cross-cutting ledger so future audits don't re-chase it | `TestArithmeticCore::test_trail_type_checked` (guard) | `todo/audit-2026-07-05/fix-A06-crosscutting-doc-drift.md` |
| A06-F018 | design (parked) | `label/1` inconsistency on unconstrained vars: no-fd-attr var → silent success with the var left **unbound**; fd-attr-but-unbounded var → ValueError | `clpfd.py:1884-1911` (`label`: attrless vars skipped; `best is None` → yield) | `label([X])` fresh X yields 1 "solution", X unbound | one consistent behaviour (SWI: instantiation error). Parked as A06-D001 | `TestLabeling::test_domainless_var_current_behaviour` (characterization guard) | `todo/audit-2026-07-05/investigate-A06-parked-design-decisions.md` |

## Confirmed-correct highlights (regression guards)

- Oracles: 6-queens = 4, 8-queens = 92, SEND+MORE=MONEY unique (9567+1085=10652).
- Differential vs brute force: 120 random binary networks over `==/!=/</<=/>/>=`
  and 80 random linear-expression `==/</<=` networks — zero divergence in
  normal integer ranges (labeling misses/dups: none).
- Backtracking: domains AND constraint tuples restored on `trail.undo`;
  labeling re-runnable after exhaustion.
- Var-var merge intersects domains, dedups + keeps constraints live.
- Hook rejects float/string/list bindings; accepts integer-valued Fraction.
- AC-3 cascade (X<Y<Z, Z=3 → X=1,Y=2 without labeling).
- C leak checks: post/label/undo cycle object+alloc stable (`refcount_stable`);
  per-object refcount of domain-bound ints stable (`getrefcount_stable`).
- Free-threading: not assessable on this 3.13 GIL box — module uses
  `m_size = -1` global state (cross-cutting issue 5, cited); no new FT claims.

## Coverage map

Dimensions: **I** input/ground mode, **O** output/var mode, **P** partial
(mixed), **E** empty/degenerate, **B** backtracking/trail, **X** error path,
**C** C-vs-Python parity. OK = exercised (probe and/or test), BUG = finding, — = n/a.

| Function / predicate | I | O | P | E | B | X | C | Notes |
|---|---|---|---|---|---|---|---|---|
| domain ops (from_range/contains/min/max/size/singleton/intersection/remove/remove_above/below/values) | OK | — | — | OK empty/singleton | — | OK ValueError paths | BUG F007 sentinel; bignum fallback OK | int64±1 boundary OK |
| `_ensure_fd` / auto-domain | OK | OK | OK | — | OK | — | BUG F016 duck-cast | |
| `_narrow` / `_narrow_if_changed` / queue | OK | OK | OK | wipeout OK | OK | — | OK | singleton→unify→hook reentry OK |
| `fd_eq` (var-var, var-int, ground, expr, linearise) | OK | BUG F002 | OK | `X==X` OK, `X==X+1` OK | OK | BUG F006 rational | BUG F003/F004 | bool BUG F009 |
| `fd_ne` | OK | OK | OK | `X!=X` BUG F010 | OK | — | OK | expr operands BUG F001 |
| `fd_lt` / `fd_le` / `fd_gt` / `fd_ge` | OK | OK | OK | chain cascade OK | OK | — | OK | exprs OK (differential) |
| `in_domain` | OK | OK | list OK | empty range OK, singleton OK | OK | bool bounds BUG F009 | OK | BUG F008 no re-propagation |
| `label` | OK | OK | BUG F018 domainless | ground list OK | OK restore+rerun | unbounded OK raises | — | first-fail order, holes, no dups OK |
| `all_different` | OK dup/ok | OK | OK | non-list OK (silent False) | OK | strings OK (silent False) | OK | value-consistency only (documented) |
| `_fd_hook` (int / var-var / Fraction / other) | OK | OK | OK | wipeout OK | OK | float/str/list OK | BUG F009 bool divergence | merge dedup OK |
| `sum_` (`fd_sum`) | OK | OK | OK | — | OK | op strings BUG F011; strings BUG F014 | BUG F003 | inequality→intermediate-var chain OK |
| `scalar_product` | OK | OK | OK neg coeffs | — | OK | — | BUG F003/F004 | backward narrowing OK |
| `element` | OK ground idx | BUG F005 unconstrained idx | OK var elems | out-of-range idx OK | OK | BUG F005 crash | — | value-fixed dual mode OK |
| `circuit` | OK n=3,4 | OK | — | n=0,1 characterized (D004) | OK | — | — | subtour elimination via counts OK |
| `cumulative` | OK | OK | — | overload OK | OK | — | — | issue 3 cited, not re-tested |
| `global_cardinality` | OK | BUG F013 var counts | OK | count=0 path (inspected) | OK | — | — | off-key values = D003 |
| `chain` | OK | OK | — | len≤1 (inspected) | OK | bad relation (inspected: silent False) | — | |
| `tuples_in` | OK | OK | OK | empty relation OK | OK | — | — | prior TuplesIn fix verified |
| `zcompare` | OK both ground | OK order var | BUG F012 order bound late; X≡Y | invalid order atom (inspected: False) | OK | — | — | |
| `reify_fd` | OK | OK None | OK | — | — | — | — | |
| `structural_eq` | delegate (A05 seam) | — | — | — | — | — | — | not re-audited here |
| `_arithmetic_core` between/succ/plus | OK | OK | OK | succ(X,0) OK | OK (mark protocol) | trail type OK; strings BUG F015 | OK | abs/sign/gcd/lcm/divmod/exp_mod/popcount/msb/lsb inspected (int-guarded; divmod y=0 OK by inspection) |
| C leak/refcount | — | — | — | — | OK | — | OK | post/label/undo loops stable |

## Seam notes (for A12)

- **A01/A04 unifier boundary:** FD hook fires inside `unify`; F006 shows a
  TypeError can escape *through* `unify` from C domain ops — callers of
  `unify` generally treat it as bool-returning and may not expect exceptions.
- **A05 dif:** `dif(X, X)` fails immediately while `X != X` (fd_ne) succeeds
  pending (F010) — the two disequality flavours disagree on reflexivity.
- **A03 compiler:** `!=` lowering passes expression trees to `_fd_ne`
  (`eval_arith=False`), which is exactly what F001 mis-handles; any fix must
  keep the compiler contract. `:=`-computed operands (queens fixture) dodge it.
- **A07 CLP(Q)/CLP(R):** rational dispatch hole (F006) sits in the shared
  `_is_rational_arg`/`_any_rational` predicates used by all fd_* operators;
  `_narrow` unconditionally imports `clausal.logic.clpq` (hard dependency).
- **A04 coroutining/hooks:** the boolean attr-hook protocol (A04-D001) is why
  FD propagation inside hooks is semidet; no new instance found here.
