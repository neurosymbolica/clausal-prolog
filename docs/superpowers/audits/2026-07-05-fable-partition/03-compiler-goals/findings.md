# Findings — A03 compiler: goals, control & specialization

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.
Test file: `tests/audit_2026_07_05/test_03_compiler_goals.py` (51 passed,
17 xfailed on 2026-07-05 — every suspected-bug xfail actually fails, i.e.
every finding below reproduces).

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A03-F001 | correctness | **TRO silently drops solutions when a prefix goal is nondeterministic.** The shared determinism table classifies `MemberIn` (`X in L` — generates members / succeeds per occurrence), `Branch` (reified `If` — explores BOTH arms when undetermined), and enumerable builtins (`atom_concat/3` split mode, `sub_atom/5`; both confirmed multi-solution) as deterministic. The TRO restart keeps only the LAST prefix solution: `trm(2,0,OUT)` yields `[4]` instead of `[2,3,3,4]`; `tri(1,0,OUT)` yields `[7]` instead of `[5,7]`; `tac(1,[],OUT)` yields `[["ab"]]` instead of 3 splits. Shallow twins (no TRO) and non-tail controls give the correct sets — the shallow-vs-trampoline differential oracle confirms | `tro.py:106-122` (`_is_deterministic_op_ir` — `MemberIn`, `Branch()` → True), `:293-339` (legacy `_is_deterministic_goal` — `in_()`, `IfExpr()` arms), `:343-370` (`_DETERMINISTIC_BUILTINS` — `atom_concat/3`, `sub_atom/5`); consumed by `optimisations/tro.py:analyse` via `predicate.py:_sweep_tro_eligible` | `trm(N,ACC,OUT) <- (N>0, X in [1,2], N1 := N-1, ACC1 := ACC+X, trm(N1,ACC1,OUT))`, query `trm(2,0,OUT)` | `[2,3,3,4]` vs `[4]` | `TestF001TroNondetPrefix` (4 xfail + 8 controls) | `todo/audit-2026-07-05/fix-A03-tro-nondet-prefix.md` |
| A03-F002 | correctness | **Destructive reuse corrupts containers under backtracking** — same broken determinism gate as F001 legitimises DR criterion 5 ("no choice points precede the mutation"): `append/3` with a dead source behind an `in`/undetermined-`If` prefix mutates the source list in place untrailed; on backtracking the SECOND solution is built from the corrupted list: `drm(OUT)` yields `[1,2,10]` then `[1,2,20,20]` (wrong VALUE, not just lost). `dict_put/4` and `set_union/3` are analysis-eligible in the same shape. `Or`/`Alternate` prefix correctly blocks. Invalidates `implementation_plans/compiler/todo/destructive_reuse_optimization_issue.md` §6's safety argument | `destructive_reuse.py:129` (`analyse_ir` prefix check delegating to `tro._is_deterministic_op_ir`); mutation in `builtins/lists.py:_append_dr__3` (A09-owned, correct given the contract) | `drm(OUT) <- (SRC is [1,2], X in [10,20], append(SRC, [X], OUT))` | `[[1,2,10]],[[1,2,20]]` vs `[[1,2,10]],[[1,2,20,20]]` | `TestF002DestructiveReuseNondetPrefix` (3 xfail + 2 controls) | `todo/audit-2026-07-05/fix-A03-dr-nondet-prefix.md` (same root fix as F001) |
| A03-F003 | correctness | **Hard crash: an index bucket containing ONLY signal-mode TRO clauses compiles to a non-generator function.** The TRO leaf emits no yield (`tro_set` + return), and `_build_predicate_trampoline_funcdef` only forces generator-ness when the body is EMPTY — so a default bucket whose sole clause is the var-headed TRO clause is a plain function returning None; first dispatch to it raises `TypeError: 'NoneType' object is not iterable` (`yield from _dflt_fn(...)`). Needs ≥4 clauses (index threshold) + a TRO-eligible var-headed clause alone in a bucket — `idx(3,R)` crashes on the FIRST call. Adding any non-TRO clause to the bucket masks it | `predicate.py:490-495` (generator-forcing gated on `not all_stmts`), `:456-469` (signal-mode arms yield-free); crash surfaces at `arg_index.py:900/939` (A02 file, behaves correctly given a generator) | `idx(0,"z0"), idx(90,·), idx(80,·), idx(N,R) <- (N>0, N<50, N1 := N-1, idx(N1,R))` then `idx(3,R)` | `[("z0",)]` vs `TypeError` | `TestF003TroSignalBucketNotGenerator` (2 xfail + 5 controls incl. interleaved-iterator and check_indices guards) | `todo/audit-2026-07-05/fix-A03-tro-signal-bucket-not-generator.md` |
| A03-F004 | correctness | **`catch/3` never matches exceptions thrown as declared-functor terms**: `_catcher_to_structural` lowers the catcher `kab(N)` to `Compound("kab",(N,))`, but the throw site constructs the module's `kab` PredicateMeta instance, and `unify(Compound("kab",(N,)), kab(7)) is False` → catch rethrows. Every `.clausal` module following the corpus idiom (declared exception functors in `-private`/`-module`) cannot catch its own exceptions. Var/str/int catchers work; passing a pre-built instance through a variable catcher arg works (`targ`) — the compile-time Compound conversion is the defect. In-tree tests never covered functor catchers (strings/ints/vars/Python-side `Compound` only) | `control_constructs.py:642-647` (`_catcher_to_structural`), used at `:678`; root asymmetry vs `terms_to_ast.py` term construction; `unify` Compound↔instance is A01 territory (parked A01-D004 family) | `cfun(N,R) <- catch(throw(kab(7)), kab(N), R is "caught")` with `-private([kab(KA)])` | `[(7,"caught")]` vs `LogicException` uncaught | `TestF004CatchFunctorCatcher` (3 xfail + 5 controls) | `todo/audit-2026-07-05/fix-A03-catch-functor-catcher.md` |
| A03-F005 | correctness | **`setof/3` does not sort** — `$set_of_dedup` is an order-preserving dedup (`dict.fromkeys`); `setof(X, member-of [3,1,3,2], L)` gives `[3,1,2]`, violating `docs/meta_predicates.md` ("sorted list with duplicates removed") and ISO | `control_constructs.py:621-624` (`_compile_find_all_core` dedup arm), `globals_env.py:42-50` (`_set_of_dedup`) | `so(L) <- setof(X, in_(X,[3,1,3,2]), L)` | `[1,2,3]` vs `[3,1,2]` | `TestF005F006FindallFamily::test_setof_is_sorted` (xfail + dedup guard) | `todo/audit-2026-07-05/fix-A03-setof-not-sorted.md` |
| A03-F006 | correctness | **findall/bagof/setof do not rename free template variables** — collected rows hold the ORIGINAL Var objects (`$deref_walk`, no copy_term-style renaming): `findall([X,Y], in_(X,[1,2]), L), Y is 9` retroactively rewrites L to `[[1,9],[2,9]]` (rows also share ONE var, not fresh-per-row). ISO findall copies the template per solution | `control_constructs.py:592-595` (`_compile_find_all_core` append of `$deref_walk(template)`) | `fat2(L,Y) <- (findall([X,Y], in_(X,[1,2]), L), Y is 9)` | rows carry fresh unbound vars vs both rows mutate to 9 | `TestF005F006FindallFamily::test_findall_free_vars_are_fresh_per_solution` (xfail) | `todo/audit-2026-07-05/fix-A03-findall-template-sharing.md` |
| A03-F007 | correctness | **Specialization silently DROPS MI body goals between `MatchClause` and the recursive call** — `analyze_mi` keeps only pre-match (before `MatchClause`) and post-match (after the last MI-related index) goals; anything in between vanishes from every specialized clause. A depth-guard MI (`MatchClause, LIM > 0, append, LIM1 := LIM-1, rec`) specializes to an UNGUARDED predicate: `SolveGuardNat(NAT3, 1)` succeeds where generic `SolveGuard(..., 1)` fails. Should at minimum raise `CannotSpecialize` | `specialization.py:187-198` (`pre_match_goals` / `post_match_goals` classification) | fixture `SolveGuard` + `-specialize(SolveGuard, NatProg, alias=SolveGuardNat)` | specialized respects guard (or load refuses) vs guard silently ignored | `TestF007SpecializationDropsMidBodyGoals` (1 xfail + 2 controls) | `todo/audit-2026-07-05/fix-A03-specialize-midbody-goals.md` |
| A03-F008 | correctness | **Deep unfolding (`depth=N`) inlines a single-clause functor without unifying constant head args** — `_try_inline_goal` checks only arity, builds a substitution ONLY for var head args, and inlines unconditionally: program `f(1). g :- f(2).` deep-specializes so that `g` SUCCEEDS (generic and shallow-spec correctly fail). Var-vs-const also drops the binding constraint | `specialization.py:1528-1546` (`_try_inline_goal` — "Check unifiability" is a length check; ` _ast_unify` exists (`:1999`) but is not used here, only in CPD) | `-specialize(Solve, ConstProg, alias=ConstDeep, depth=5)` then `ConstDeep([["g"]])` | fail vs succeed | `TestF008DeepUnfoldConstantCheck` (1 xfail + 1 control) | `todo/audit-2026-07-05/fix-A03-deep-unfold-const-args.md` |
| A03-F009 | correctness | **CPD + extension chaining emits duplicate `Evaluate` targets → deeper solutions silently lost.** With `cpd=True` on a counting MI, second-level deforested clauses contain the same var as `Evaluate` LHS twice (e.g. `_309 := _316+1; _313 := _309+1; _309 := _313+1; …`) — the second Evaluate fails, so those clauses can never succeed: `CountGraphCPD([["path","a",Y]], C)` returns only the 1-hop path `("b",2)`; generic/non-CPD return `("b",2),("c",4),("d",4)`. Plain-`Solve` CPD (no extension chaining) is correct | `specialization.py:1918-1975` (`_unfold_body_goal` `chain_subst` construction + recursive `_deforest_clause` reuse of already-chained vars) | `-specialize(SolveCount, GraphProg, alias=CountGraphCPD, cpd=True)` | counts match generic vs 2 of 3 solutions lost | `TestF009CpdExtensionChaining` (1 xfail + 2 controls) | `todo/audit-2026-07-05/fix-A03-cpd-extension-chaining.md` |
| A03-F010 | doc-drift | Compiler README §5 still states continuation-level TCO "does NOT happen today" / "the compiler doesn't do this yet", but `optimisations/continuation_tco.py` + `TrampolineStrategy.emit_sub_call(tail_position=…)` implement exactly that (E-slice landed); `todo/continuation_tco.md` is cited as if still open | `clausal/logic/compiler/README.md` §5 "What does NOT happen today"; vs `optimisations/continuation_tco.py`, `strategy.py:132-183` | read | README matches implementation vs says feature absent | — (doc-only) | `todo/audit-2026-07-05/fix-A03-readme-ctco-drift.md` |

Minor / code-read notes (no ledger row, tracked in todos where actionable):

- `tro.py:601-613` — `_compile_tro_tail` computes `fallback_stmts` via
  `_compile_predicate_call_impl(..., [None]*arity, ...)` then unconditionally
  overwrites it at `:633`; the first call is dead code (burns fresh names,
  emits nothing). Folded into `fix-A03-tro-nondet-prefix.md`.
- `tro.py:455-471` — `_head_has_unifying_list_pattern` only handles
  `is_term_instance` heads, not `Compound` heads (cr — no in-tree route to a
  TRO-compiled Compound-head clause found; noted in the fix todo).
- `goal_shallow.py:226-262` — `_head_has_deferred_pattern` does not walk
  `DictTerm`/`SetTerm` values. cr only: dict/set head guards are match-entry
  `unify` guards (`head_match.py:1129-1176`), not per-yield deferred guards,
  so no reachable output-guard-bypass shape was found; the emit-time
  `_k_stmts_is_bare_leaf_yield` check (`strategy.py:99-113`) does NOT protect
  here because `_wrap_yields_with_output_guards` runs after body emission.
- `throw(X)` with X unbound raises `LogicException` carrying the var instead
  of an instantiation error (ISO). Doc/design note only.
- `solve.py:83` emits a `DeprecationWarning` (3-arg `gen.throw()`) whenever an
  exception crosses the trampoline — A04 seam, noted below.

## Coverage map

Files: `predicate.py`, `goal_shallow.py`, `goal_trampoline.py`,
`control_constructs.py`, `ite_reified.py`, `tabled_naf.py`, `tro.py`,
`destructive_reuse.py`, `specialization.py`, `optimisations/{call_site,
continuation_tco,destructive_reuse,tro}.py`.

Dimensions: **IN** = input/ground mode, **OUT** = output/var mode,
**PART** = partially instantiated arg, **E/S** = empty & singleton,
**ORD/BT** = clause order + backtracking/trail, **ERR** = error paths.
Legend: `✓` probed clean, `F###` finding, `pa` = prior art, `cr` = code-read
only, `n/a`, `doc` = documented divergence (not a finding).

### TRO (`tro.py`, `optimisations/tro.py`, predicate.py wiring)

| Surface | IN | OUT | PART | E/S | ORD/BT | ERR |
|---|---|---|---|---|---|---|
| deterministic prefix (`:=`, `>`, once) loop mode | ✓ (`cnt`, `trob`) | ✓ | ✓ | ✓ (0-step) | ✓ deep 3000 stack-safe | ✓ |
| nondet prefix: `in`/Branch/atom_concat/sub_atom | F001 | F001 | — | — | F001 (restart keeps last) | — |
| non-tail control (Unify after call) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| shallow twin (no TRO) — differential oracle | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| signal mode (indexed ≥4 clauses): TRO-only bucket | F003 crash | F003 | — | — | — | F003 `TypeError` |
| signal mode: bucket with sibling var clause | ✓ (`jdx`) | ✓ | ✓ | ✓ | ✓ interleaved iterators | ✓ |
| check_indices runtime ground-check (list-decomposed tail arg) | ✓ (`wk5`, keyed-bucket overlap `[9]` 2 sols) | ✓ | ✓ parity w/ shallow (both raise TypeError on unbound `:=` — parity holds) | ✓ | ✓ | ✓ |
| tabled predicate → TRO disabled | cr (`predicate.py:731,995` gate) | | | | | |
| `_head_has_unifying_list_pattern` Compound heads | cr — gap noted (no reachable route found) | | | | | |
| catch/nondet-meta prefix blocks TRO | ✓ (`ctp` + analysis check) | ✓ | — | — | ✓ | — |

### Destructive reuse (`destructive_reuse.py`, `optimisations/destructive_reuse.py`)

| Surface | IN | OUT | PART | E/S | ORD/BT | ERR |
|---|---|---|---|---|---|---|
| det prefix, dead source (intended) | ✓ (`drok`) | ✓ | n/a | ✓ | ✓ | ✓ |
| nondet prefix (MemberIn / Branch) | F002 | F002 | — | — | F002 corrupted 2nd solution | — |
| live-after source → ineligible | ✓ (`drmc`) | ✓ | — | — | ✓ | — |
| head-aliased source → ineligible | ✓ (analysis) | — | — | — | — | — |
| Alternate prefix → ineligible | ✓ (analysis) | — | — | — | — | — |
| dict_put / set_union candidates | F002 (analysis-eligible; runtime not separately run) | | | | | |

### Continuation-TCO (`optimisations/continuation_tco.py`, `strategy.py` emit)

| Surface | IN | OUT | PART | E/S | ORD/BT | ERR |
|---|---|---|---|---|---|---|
| pass-through wrapper (1 + 2 levels) | ✓ 3 sols each | ✓ | ✓ | ✓ | ✓ | ✓ |
| Or-arm tails | ✓ 6 sols, order kept | ✓ | ✓ | ✓ | ✓ | — |
| general-ITE then-arm tail | ✓ (`altif` per-cond-solution) | ✓ | ✓ | ✓ | ✓ | — |
| deferred head pattern gate (`[H,*T]` head, output mode) | ✓ (`sp2` binds caller list) | ✓ | ✓ | ✓ | ✓ | — |
| tail into indexed bucket-ref (call_site + TCO) | ✓ (`wk` 2 sols) | ✓ | n/a | ✓ | ✓ | — |
| exception through TCO'd chain (catcher slot) | ✓ (`cvar` catches) | — | — | — | — | ✓ |
| once() over TCO'd wrapper (shallow↔tramp bridge) | ✓ | ✓ | — | — | ✓ | — |
| dict/set-nested star pattern vs gate | cr — no deferred-guard route found (see notes) | | | | | |

### Control constructs (`control_constructs.py`, `ite_reified.py`, `tabled_naf.py`)

| Surface | IN | OUT | PART | E/S | ORD/BT | ERR |
|---|---|---|---|---|---|---|
| once/1 | ✓ commits, continuation backtracks | ✓ bindings escape | ✓ | ✓ fail→fail | ✓ | ✓ |
| call_nth/2 | ✓ nth only | doc — N must be bound int (documented; unbound raises type_error) | n/a | ✓ | ✓ | ✓ (0/-1 raise, prior fixture) |
| count_all/2 | ✓ | ✓ unifies count | n/a | ✓ | ✓ wrong count fails | ✓ |
| setup_call_cleanup/3 | ✓ setup→call→cleanup order (side-effect log) | ✓ bindings escape | — | ✓ fail→or-arm clean trail | ✓ | ✓ cleanup runs then exception propagates |
| catch/throw | ✓ str/int/var catchers; rethrow on miss; nondet recovery; catch_error/catch_recover | F004 declared-functor catchers | — | — | ✓ trail undone before catcher unify (cr + fixtures) | F004 |
| findall/bagof/setof | ✓ order+dups; bagof fails empty | F006 free-var sharing | — | ✓ | ✓ | — |
| setof sortedness | F005 | F005 | — | — | — | — |
| forall/2 | ✓ true/false (via `call`; zero-arity `solve()` gap → seam) | — | — | ✓ | ✓ | — |
| freeze/when (compile side) | ✓ fires on bind; `when((nonvar,ground))` conj split; `when(ground)` | ✓ | — | — | ✓ | — |
| throw(unbound) | note — LogicException carrying Var (vs ISO instantiation_error) | | | | | |
| reified ITE unify/dif/FD | ✓ ground both ways; undetermined explores both; nested 4 paths | ✓ | ✓ | ✓ | ✓ constraints undone between branches | ✓ |
| general ITE (non-reifiable cond) | ✓ then per cond-solution; else on none | ✓ | ✓ | ✓ | ✓ | — |
| tabled ITE (`If(tabled,…)`) + tabled NAF | ✓ reachable/unreachable; `not Path` both ways | ✓ | — | — | ✓ | — |

### Specialization (`specialization.py`)

| Surface | Result |
|---|---|
| tail-style unfold (Solve/SolveCount), ground + count-output | ✓ equals generic |
| pre-match goals (SolveLimit depth guard) | ✓ preserved (`LimNat`) |
| post-match goals (SolveCount `COUNT := SUB+1`) | ✓ preserved |
| mid-body goals (between MatchClause and rec call) | F007 silently dropped |
| split style (SolveTree) proof trees | ✓ byte-equal trees |
| deep unfolding depth=N, var-only heads | ✓ (in-tree fixtures) |
| deep unfolding, single-clause functor w/ constant args | F008 wrong inline |
| CPD deforestation, vanilla Solve | ✓ equals generic |
| CPD + counting extension chaining | F009 solutions lost |
| residual builtin catch-all (`gt/sub/mul` etc.) | ✓ `FactSpec` fact(4)=24; doc — generic MI intentionally lacks builtin dispatch (documented) |
| MI with imported `MatchClause` | note — `CannotSpecialize` at module load (recognizer requires local `LoadName("MatchClause")`); loud, but surprising for users importing the stock helper |
| `_subst` on `Call.kwargs` | cr — kwargs not substituted (no kwarg-using MI shape reachable via `-specialize`) |

### Dry-pass log

Seven probe passes (`/tmp/a03_probe1..7*`). Pass 1: F001 (member/If prefixes)
+ F002 confirmed at runtime; pass 1b isolated root cause via direct
`tro/dr analyse` introspection + confirmed `atom_concat`/`sub_atom`
enumeration. Pass 2: F007, F008, F009(setup) + ctco/scc/once/findall-family
guards; F004 first seen (probe aborted early — later isolated). Pass 2c/2d:
F003 single-call crash isolated (non-generator bucket introspection),
F004 matrix (var/str/instance catchers fine; functor catchers never);
`unify(Compound, instance)=False` verified as mechanism. Pass 3: shallow
oracles, fee parity, tabled ITE/NAF, freeze/when, LimNat/TreeGraph/
CPD-count → F009 confirmed + clause dump showed duplicate-Evaluate root
cause; F005 (setof) + zero-arity `solve()` seam. Pass 4: scc ordering with
side-effect log, catch_error/catch_recover, TRO-once prefix — all clean.
Pass 5: findall shared-var (F006) confirmed with retroactive mutation; wk5
check_indices probe corrected (initial mismatch was a fixture authoring
error — base clause demanded ACC=0). Pass 6: FD/dif reified undetermined,
residual-builtin differential — clean (dry 1). Pass 7: `when` conjunction,
once-over-deep-recursion (no RecursionError — inner is a single bridged
trampoline call) — clean (dry 2) → stopped per the 2-dry-pass rule.

### Seam notes for A12

- **Zero-arity predicates cannot be queried from Python**: `solve(m.fal(), m)`
  raises `NotImplementedError: goal shape not yet supported (PredicateMeta)`
  (`terms_to_goalop.py:457`, A02 file) and direct iteration raises
  `TypeError: 'PredicateMeta' object is not iterable` (A01 predicate API);
  only `call("fal", module=m)` works. Query-API seam (A02/A01/A04).
- **`unify(Compound(f, args), f_instance)` is False** — the enabling half of
  A03-F004; whether Compound↔declared-functor-instance unification should
  succeed is an A01 design question (A01-D004 family, parked). The A03 fix
  (resolve catcher through base_globals term classes) does not depend on it.
- **`solve.py:83` DeprecationWarning** (3-arg `gen.throw()`) fires whenever an
  exception crosses the trampoline driver — A04.
- **`:=`/arith on unbound vars raises raw Python `TypeError`** (`ACC + H`
  with H unbound) instead of an instantiation error — shallow and trampoline
  agree (parity ✓); error-taxonomy question for A09/A05.
- **`_tro_state` is a per-predicate shared mutable list** in `base_globals`
  (`predicate.py:744-746`); set/consume is synchronous within one dispatch
  pull (single-thread safe, interleaved iterators probed ✓) but is a data
  race under free-threading — unconfirmed, needs 3.14t build (A04/FT).
- **`_lift_clause_at_pos` bucket lifting is trampoline-only** — shallow
  indexed buckets compile unlifted clauses (`predicate.py:1394` vs `:769`).
  No divergence found (fee/walk parity probes), noted for the A02↔A03 seam.
- **`visualize.predicate_to_source` cannot show TRO/TCO/dispatch closures**
  (A02 note confirmed; not used as oracle here).
