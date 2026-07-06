# Findings — A02 compiler: heads & indexing

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.
Test file: `tests/audit_2026_07_05/test_02_compiler_heads.py` (51 passed,
20 xfailed on 2026-07-05 — every suspected-bug xfail actually fails, i.e.
every finding below reproduces).

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A02-F001 | correctness | Indexed dispatch silently loses solutions for **non-var args whose index key is uncomputable**: partial char/code-lists, `[]` vs `""` heads, SegLists, and numerics outside `_INDEXABLE_TYPES` (Decimal/Fraction/complex) route to the per-position **default** bucket (var-headed clauses only) — or to the **always-fail** joint/secondary default — instead of the all-clauses fallback. Controls (<4 clauses, linear scan) all find the solutions | `arg_index.py:145-179` (`_runtime_arg_key` → `_INDEX_VAR`), `:785-831` (single/multi groundness bodies route `_INDEX_VAR`-key to `dflt_fn`), `:448-477` (joint), `:650-684` (secondary); always-fail defaults wired at `compiler/predicate.py:917,958` (boundary) | `strs4([X,"b","c"], R)` with 4 str-headed clauses | `[("a","A")]` vs `[]`; same shape for `emp4([],R)`, `byt4([97,X],R)`, SegList caller, `kind4(Decimal(1),R)`, `jnt2([X,"a"],2,R)`, `sec2([X],1,R)` | `TestF001IndexedDispatchPartialTerms` (7 xfail + 5 controls) | `todo/audit-2026-07-05/fix-A02-dispatch-partial-term-fallback.md` |
| A02-F002 | correctness | List-structure dispatch (`_build_list_dispatch_guard`) has **no fallthrough arm**: a caller that is not `list`/`str`/unbound-Var gets zero solutions even when var-headed clauses must match — int/tuple callers lose the var clause; bytes callers additionally lose cons clauses (bytes-as-lists contract); SegList callers lose everything. Fires only for rule-clause sets with nil+cons(+var) heads at one position (fact normalization hoists ground `[]`, masking the fact case) | `list_dispatch.py:264-275` (isinstance tuple is `(list, str)`; `is_var` elif; no else), guard built at `:193-262` | `ld2([],R)<-…; ld2([H,*T],R)<-…; ld2(X,R)<-…` then `ld2(5, R)` | `[("any2",)]` vs `[]`; `ld2(b"ab",R)`: `[("cons2",),("any2",)]` vs `[]` | `TestF002ListDispatchFallthrough` (4 xfail + 4 controls) | `todo/audit-2026-07-05/fix-A02-list-dispatch-fallthrough.md` |
| A02-F003 | correctness | `head_to_match_pattern` final fallback is an **unguarded accept-all wildcard**: head literals of any unhandled type (datetime.date, Decimal, tuple, set, …) match ANY caller arg in input mode (wrong solutions) and bind nothing in output mode. Reachable today via runtime `assertz` of a dataclass fact (that path normalizes only `Compound` heads — `builtins/database_ops.py:44-47` comment asserts field patterns "work correctly", which is false for these types). Var-functor `Compound` heads take the same unguarded wildcard (`:539-541`) — unconfirmed-reachable, blocked on parked A01-D004 | `head_match.py:617-618` (fallback), `:539-541` (var functor); seam: `builtins/database_ops.py:20-47` | `assertz(dyn_date(date(2026,1,1),1))` then `dyn_date(date(1999,9,9), R)` | `[]` vs `[(1,)]`; output mode `dyn_date(X,R)` leaves X unbound; tuple/set/Decimal identical | `TestF003ExoticHeadWildcard` (5 xfail + control) | `todo/audit-2026-07-05/fix-A02-head-wildcard-accept-all.md` |
| A02-F004 | correctness | Multi-star list guard: **trailing fixed elements after the LAST star unify against indices 0..k instead of n-k..n** — the position accumulator is reset to 0 with a comment claiming the trailing elements "were already counted" (they were not; the emission loop still visits them). Every ground/input-mode call of a `[*A, x, *B, y]`-shaped head fails (or, if `d[0]==y` by coincidence, wrong splits); output mode (fresh-Var build path) is unaffected | `head_match.py:795-801` (reset), fixed-element emission `:733-748` | `ms3([*A,1,*B,2], A, B)` queried `ms3([1,2],A,B)` | `[([], [])]` vs `[]`; `mst([0,1,5,2,3],A,B)`: `[([0],[5])]` vs `[]`; str caller `mchr("xayb",A,B)`: `[("x","y")]` vs `[]` | `TestF004MultiStarTrailingFixed` (4 xfail + 6 controls) | `todo/audit-2026-07-05/fix-A02-multistar-trailing-fixed.md` |
| A02-F005 | doc-drift | Dispatch-impl docstrings say the trampoline `arg_offset` is **2** ("positions 0/1 are self_generator/parent") but every trampoline caller passes **4** (Phase-2 split-continuation layout `(this_generator, _proceed, _fail, _catcher, arg0, …)`); misleading for anyone re-deriving the arg layout | `arg_index.py:641-646` (`_make_secondary_dispatch_impl`), `:727-733` (`_make_indexed_dispatch_impl`), `:814-817` (`_groundness_dispatch_body_multi`) vs callers `:714-716`, `:775-779`, `:954-959` | read | docstrings match the Phase-2 layout vs say "2" | — (doc-only) | `todo/audit-2026-07-05/fix-A02-dispatch-docstring-arg-offsets.md` |

Open design question (parked per user preference — see `design-questions.md`
and `todo/audit-2026-07-05/investigate-A02-parked-design-decisions.md`):
A02-D002 — how exotic numeric types should participate in index keys once
A01-D001 (cross-type numeric unification) is decided.

## Coverage map

Files: `head_match.py`, `arg_index.py`, `terms_to_ast.py`,
`terms_to_goalop.py`, `ir.py`, `list_dispatch.py`.

Dimensions: **IN** = input/ground mode, **OUT** = output/var mode,
**PART** = partially instantiated arg, **E/S** = empty & singleton,
**ORD/BT** = clause order + backtracking/trail, **ERR** = error paths.
Legend: `✓` probed clean, `F###` finding, `pa` = prior art (cited, not
re-reported), `cr` = code-read only (no executable route found), `n/a`.

### head_match.py (patterns + guards)

| Surface | IN | OUT | PART | E/S | ORD/BT | ERR |
|---|---|---|---|---|---|---|
| scalar/singleton rule-head literals (int/float/bool/None; negative literals via `Negate` hoist) | ✓ | ✓ (pa 2026-06-23 fix) | n/a | ✓ | ✓ | ✓ |
| str head literal (F046 guard; charlist caller) | ✓ | ✓ | ✓ | F001 (`""` under index) | ✓ | ✓ |
| bytes head literal (codes contract) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| atom head literal (R1 guard; rule + fact) | ✓ | ✓ (binds atom) | n/a | n/a | ✓ | ✓ |
| single-star list heads (`$head_list_unify_*` compile side) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| multi-star: fixed between stars / adjacent stars / enumeration | ✓ | ✓ (builds SegList→walks ground) | ✓ | ✓ (min-len fail) | ✓ (all splits) | ✓ |
| multi-star: **trailing fixed after last star** | F004 | ✓ | F004 | F004 | — | — |
| multi-star: str / bytes / SegString / SegBytes callers | ✓ (`ms2` int-codes vs bytes; char-fixed vs str) | ✓ | seam (SegString align under-enumerates — A04) | ✓ | ✓ | ✓ |
| nested star-lists (incl. inner-vs-str element) | ✓ | ✓ | ✓ | ✓ (inner `[]` fails) | ✓ | ✓ |
| dup head vars (direct, in-list, across two list guards) | ✓ | ✓ | ✓ (shared fresh var) | ✓ | ✓ | ✓ |
| DictTerm/dict + SetTerm/set-literal heads | ✓ (both dict & DictTerm callers) | ✓ | ✓ | ✓ | ✓ | ✓ (mismatch fails) |
| tuple heads (TupleLiteral → structural hoist) | ✓ | ✓ | n/a | ✓ | ✓ | ✓ (mismatch fails) |
| Compound / Call(LoadName) / instance heads (structural hoist gate) | ✓ | ✓ (pa 2026-06-23/25) | ✓ | ✓ | ✓ | ✓ |
| imported-compound heads (`_resolve_loadname` / dotted) | pa (2026-06 fix); cross-module e2e deferred to A11 | | | | | |
| **fallback wildcard** (date/Decimal/tuple/set/… literals) | F003 wrong-match | F003 no-bind | F003 | — | — | F003 silent |
| var-functor Compound head | cr — unguarded wildcard, same class as F003; blocked on parked A01-D004 | | | | | |
| `_wrap_yields_with_output_guards` (output-mode construction, multi-solution) | ✓ | ✓ (`outl`: per-solution values correct, undone between) | ✓ | ✓ | ✓ | cr (no `ast.Match` arm in walker; no in-tree body emits one) |
| GeneratorExit / `_mark_cl` finally-guard | cr (prior fix, comment-documented; nondeterministic to force) | | | | | |

### arg_index.py (keys + dispatch)

| Surface | IN | OUT | PART | E/S | ORD/BT | ERR |
|---|---|---|---|---|---|---|
| key canonicalisation: charlist→str, bytelist→bytes (F095), compound `(f,n)`, atom `(name,0)`, LoadName/LoadAttr | ✓ (`coll` str+charlist same bucket, both clauses fire, both caller shapes) | ✓ | F001 | ✓ (`[]`→`_INDEX_VAR` vs `""` key) | ✓ | ✓ (TypeError→default guarded) |
| single-position groundness dispatch (hit / miss / var / partial) | ✓ | ✓ (var→all_fn) | F001 | F001 | ✓ (`ord6` interleave order) | ✓ |
| multi-position plans (first ground pos wins) | ✓ | ✓ | F001 | ✓ | ✓ | ✓ |
| joint dispatch (both/one/neither ground; unknown key) | ✓ | ✓ | F001 (partial→empty joint-default) | ✓ | ✓ | ✓ |
| secondary hierarchical (l0/l1 hit, l1 var, unknown, partial) | ✓ | ✓ | F001 (l0 partial→always-fail); l1 partial consistent | ✓ | ✓ | ✓ |
| cross-type numeric callers | ✓ True/1.0 (hash-equal, consistent with unify) | n/a | — | n/a | n/a | F001 Decimal/Fraction/complex (D002 parked) |
| `_static_call_key` / call-site bucket specialisation | ✓ (`usek`, `usekl` charlist static arg) | ✓ | n/a | ✓ | ✓ | ✓ |
| TRO × buckets (`tro_state` re-dispatch) | ✓ (`cds` recursion crosses buckets; order right) | ✓ | ✓ | ✓ | ✓ | seam (`"x" > 0` TypeError — body semantics, A03) |
| assertz → reindex (new key, old buckets, enumerate) | ✓ | ✓ | n/a | n/a | ✓ | pa (stale-dispatch note, cross_cutting) |
| single-clause bucket `skip_trail` | ✓ (no binding leak after failed body) | ✓ | n/a | n/a | ✓ | ✓ |
| docstring arg offsets | F005 (doc) | | | | | |

### terms_to_ast.py / terms_to_goalop.py / ir.py

| Surface | Result |
|---|---|
| lowering fidelity e2e (lists/stars, dicts, sets, tuples, compounds, atoms, arith `==`, `$Fraction` int/int) | ✓ via every fixture above (`term_to_ast_expr` exercised by hoisted-Unify bodies, guards, output builds) |
| `Or` chain (binary `Alternate` nesting) | ✓ order 1,2,3; membership check semidet |
| `If` reified (ground both ways; unbound → both branches) | ✓ |
| `If` with star-list unify test (DCG shape → general ITE) | ✓ |
| `False` truncates conjunction; `True` is unit | ✓ |
| bare Var in goal position → `BareGoalVariableError` naming `pred/arity` at load | ✓ |
| meta-name arms (`once`/`findall`/…) conversion | pa/A03 (lowering owned by A03; conversion shapes exercised indirectly) |
| `walk_goal_ops[_deep]` traversal | cr — pure traversal, matches op set; no divergence found reading |
| raw `Fraction`/exotic leaf reaching `term_to_ast_expr` | cr — would raise NotImplementedError; no .clausal route (Python-API route lands in F003's accept-all instead); noted in F003 todo |

### list_dispatch.py

| Surface | IN | OUT | PART | E/S | ORD/BT | ERR |
|---|---|---|---|---|---|---|
| nil/cons/var rule dispatch (list, str, var callers) | ✓ | ✓ (var caller enumerates all three) | ✓ | ✓ | ✓ | — |
| non-list/str/var callers (int, tuple, bytes, SegList) | F002 | — | F002 | — | — | F002 silent |
| `_lift_clause_at_pos` (scalar/compound lift; str/bytes/LoadName skip) | ✓ via bucket fixtures (kind4/strs4/cmq4/col4) | ✓ | ✓ | ✓ | ✓ | ✓ |

### Dry-pass log

Six probe passes (`/tmp/a02_probe1..6.py`). Pass 1 surfaced the F001 family +
regressions clean; pass 2 surfaced F002/F003 (+ two probe artifacts from
double-loading the fixture module — atoms/functors are module-scoped, worth
knowing when writing probes); pass 3 surfaced joint/secondary F001 variants;
pass 4 surfaced F004; pass 5 surfaced only F004/F003 variants (its two
"new" hits were probe errors — a multi-char fixed element is one list element,
not chars); pass 6 surfaced nothing new → stopped per the 2-dry-pass rule.

### Seam notes for A12

- **Guard clauses over mixed-type args raise instead of failing** (A03/A09):
  `cds("x", R)` with a sibling clause body `N > 0` raises `TypeError:
  '<' not supported between 'int' and 'str'` — indexed AND linear paths both
  hit the var-headed clause, so the cheat-sheet's disjoint-guard idiom crashes
  whenever one clause's numeric guard sees another clause's string key.
  FDCompare runtime semantics, not an A02 file.
- **Runtime `assertz` normalization gap** (A09): `builtins/database_ops.py`
  `_normalize_fact_clause` normalizes only `Compound` facts; dataclass facts
  pass through on the false assumption their "field patterns work correctly"
  — the reachable route into A02-F003. Fixing either side fixes the repro;
  fixing head_match (guarded fallback) also covers future asserters.
- **Non-ground SegString into a multi-star head under-enumerates** (A01/A04):
  `ms(SegString(["ax", VarSeg(X)]), A, B)` yields only `('a','')` — the
  runtime `_segstring_align` binds the tail VarSeg to `""` rather than
  enumerating/deferring alignments inside the unknown segment. Compile side
  (A02 `segstring_branch`) delegates correctly; alignment semantics are
  runtime-owned.
- **`compiler/predicate.py` wires empty joint/secondary defaults to
  always-fail functions** (`:917,958`) — correct only while dispatch never
  routes computable-key misses there; interacts with the A02-F001 fix (A03
  owns predicate.py).
- **`solve._query_cache` keys by arg types** (A04): back-to-back queries of
  one predicate with different arg types need a cache clear (probe footgun;
  the audit conftest ships `clear_query_cache` for this).
- **`visualize.predicate_to_source` renders the shallow strategy** and cannot
  show the production trampoline's dispatch closures (they are runtime
  closures, not AST) — limits its value as an oracle for exactly the dispatch
  layer this audit covered; A03 should not rely on it for dispatch questions.
- **Index-key ↔ unify parity for cross-type numerics** depends on parked
  A01-D001; see A02-D002.
