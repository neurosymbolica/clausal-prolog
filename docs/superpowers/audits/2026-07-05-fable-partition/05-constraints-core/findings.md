# Findings — A05 constraints core (dif, attributed vars, reif)

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.
Test file: `tests/audit_2026_07_05/test_05_constraints_core.py` (57 passed,
17 xfailed on 2026-07-05 — every suspected-bug xfail actually fails, i.e.
every finding below reproduces).

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A05-F001 | correctness | **dif/2 constraint silently dropped when its free vars live only inside `DictTerm` / `SegList` / `SegString` / `Quantity`.** `_collect_free_vars` (Python AND C — identical blind spot, parity-confirmed) walks only Var/tuple/list/Compound/term-instances, but the sandbox `_structural_unify_oc` falls through to full `unify()` which binds *through* any `__unify__`-hooked container. Result: `dif` returns True on the "pending" path, attaches the pair to **zero** variables, and the disequality is never re-checked — the terms may silently become equal. Reachable from pure Clausal: `D is not {"k": 1}, D is {"k": V}, V is 1` succeeds. (`SetTerm` is exempt: the unifier itself refuses var-element set unification, so no-attach is consistent.) | `clausal/logic/constraints.py:152-182` (`_collect_free_vars`); `clausal/logic/_constraints_dif.c:68-153` (`collect_walk`) | `A=Var(); dif(DictTerm({"k":A}), DictTerm({"k":1}), t)` → True, then `unify(A,1,t)` | `unify(A,1)` → `False` vs `True` (constraint lost) | `TestF001DifContainerBlindSpots` (5 xfail + 4 controls + language-level xfail) | `todo/audit-2026-07-05/fix-A05-dif-collect-free-vars-container-blindness.md` |
| A05-F002 | correctness (C, crash) | **Interpreter SIGSEGV: C `_dif_hook` does unchecked `PyTuple_GET_ITEM(pair, 0/1)` on user-controllable attr-list items.** The hook validates `attr_value` is a list but not that its items are 2-tuples. `put_attr(X, "dif", [42], t)` (or `[(1,)]`, `["ab"]`) followed by `unify(X, 1, t)` kills the process (exit 139). Reachable from pure Clausal via the `put_attr/3` builtin with key `"dif"`. The Python fallback raises a clean `TypeError` for the same inputs (differential-confirmed); the attach path (`attach_dif_pair` with a malformed *existing* attr) also fails cleanly in both impls — only the C hook path crashes. | `clausal/logic/_constraints_dif.c:474-477` (`py_dif_hook`) | `put_attr(X,"dif",[42],t); unify(X,1,t)` in a subprocess → rc −11 | clean Python-level `TypeError` (as Python impl does) vs SIGSEGV | `TestF002DifHookMalformedAttr` (3 xfail params + 2 clean-path controls) | `todo/audit-2026-07-05/fix-A05-dif-hook-malformed-attr-segfault.md` |
| A05-F003 | correctness | **`structural_eq` is asymmetric and inconsistent with `reify_eq`/`dif`/`unify` on values that unify with no bindings.** (a) `structural_eq("ab", SegString(["ab"]))` → True but `structural_eq(SegString(["ab"]), "ab")` → False (SegString arm demands both sides SegString; the str arm delegates to `str.__eq__`/`==` which answers True) — an equality relation that is not symmetric. (b) `structural_eq("ab", ["a","b"])` → False although the standing contract says a string IS a list of single-char strings and `reify_eq("ab", ["a","b"])` → True (identical, zero bindings). (c) ground `SegList([ConcreteSeg([1,2])])` vs `[1,2]` → False both ways despite `reify_eq` → True. Violated invariant: `structural_eq(x,y) ⟺ reify_eq(x,y) is True`. | `clausal/logic/constraints.py:36-138` (str arm `:54`, list arm `:58-61`, SegList/SegString arms `:77-103`) | `structural_eq(SegString(["ab"]), "ab")` vs flipped | symmetric + consistent with reify_eq vs asymmetric/False | `TestF003StructuralEqInconsistencies` (3 xfail + 4 controls) | `todo/audit-2026-07-05/fix-A05-structural-eq-asymmetry-consistency.md` |
| A05-F004 | correctness (low) | **`term_attvars/2` is blind to tuples, plain dicts, sets, and Seg\* terms** — `_collect_attvars` walks only list/Compound/term-instance/DictTerm. A tuple is a core Clausal structure; an attributed var sitting in `(V,)` is not reported. | `clausal/logic/builtins/attributes.py:125-146` | `put_attr(V,"k",1,t); term_attvars((V,), Out)` | `Out = [V]` vs `Out = []` | `TestF004TermAttvarsBlindSpots` (3 xfail + 3 controls) | `todo/audit-2026-07-05/fix-A05-term-attvars-container-blindness.md` |
| A05-F005 | correctness (error-path) | **`has_units/2` raises `AttributeError` instead of failing when the 2nd arg is not a units predicate** — `unit_pred._dims` is accessed unguarded; `has_units(D, "meters")` crashes the query instead of failing per its own docstring ("anything else → fail"). | `clausal/logic/units_constraint.py:111` | `list(_has_units(Var(), "meters", t, []))` | `[]` (fail) vs `AttributeError` | `TestF005HasUnitsErrorPath` (1 xfail + 5 unit-hook controls) | `todo/audit-2026-07-05/fix-A05-has-units-error-path.md` |
| A05-F006 | doc-drift (consequence of A01-F001) | **`docs/constraints.md` promises "Occurs check: `dif(X, f(X))` → succeed (can never be equal)"** — but `unify_with_occurs_check` is Compound-blind (A01-F001), so the sandbox unify *succeeds with growth* and a pending constraint is attached to X instead of immediate satisfaction. Final semantics eventually agree (later bindings re-check structurally), but the documented immediate-discharge behaviour only holds for lists/tuples. Fix rides on the A01 occurs-check fix; no separate code change here. | `clausal/logic/constraints.py:227` fallthrough → `_variables.c:941-954` (A01-F001); doc at `docs/constraints.md:162` | `dif(X, Compound("f",(X,)), t)` → True but `get_attr(X,"dif")` non-None | no pending constraint vs pair attached | `TestF006DifOccursCheckCompound` (1 xfail + list control) | `todo/audit-2026-07-05/fix-A01-occurs-check-compound-blindness.md` (A01's; cited, not duplicated) |

Prior art cited, not re-reported:
- `todo/cross_cutting_issues.md` #1 (missing `Trail_Check`): **already fixed in
  `_constraints_dif.c`** — all four exported entry points guard the trail arg
  (`:298, :409, :462, :522`); verified by code read.
- A01-F001 (Compound-blind occurs check) — dif-level consequence logged as
  A05-F006 above.
- A01-D003 (hookless put_attr silently succeeds) — resolved-from-docs in A01.
- A04-D001 (boolean attr-hook protocol is semidet) — the dif hook shares this
  protocol; dif itself is deterministic so unaffected, but any hook-contract
  redesign must include `_dif_hook` (noted in that decision's Affects column).

Open design questions (parked by standing user instruction — see
`design-questions.md` and
`todo/audit-2026-07-05/investigate-A05-parked-design-decisions.md`):
A05-D001 cross-type truth values in the dif/reify layer (blocked on A01-D001),
A05-D002 user-writable engine-reserved attribute keys.

## Coverage map

Files: `clausal/logic/constraints.py`, `clausal/logic/reif.py`,
`clausal/logic/units_constraint.py`, `clausal/logic/builtins/attributes.py`,
`clausal/logic/_constraints_dif.c`.

Dimensions per row: **IN** = input/ground mode, **OUT** = output/var mode,
**PART** = partially instantiated, **EMPTY/SINGLE** = empty & singleton,
**CYC** = cyclic/occurs, **BT** = backtracking + trail restoration,
**ERR** = error paths. Legend: `✓` probed clean, `F###` finding, `D###`
design question, `pa` = prior art (cited), `n/a` = meaningless.

### dif/2 (`constraints.py` + `_constraints_dif.c`, C active; Python differential-checked)

| Surface | IN | OUT | PART | EMPTY/SINGLE | CYC | BT | ERR |
|---|---|---|---|---|---|---|---|
| `dif` ground scalars / strings | ✓ | n/a | n/a | ✓ | n/a | ✓ | D001 (1 vs 1.0/True follows unify; parked) |
| `dif` var-var / var-ground, bind equal & different | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| `dif` tuple / list / Compound / term-instance args | ✓ | ✓ | ✓ | ✓ (arity mismatch immediate) | F006 (Compound occurs) | ✓ | ✓ |
| `dif` DictTerm / SegList / SegString / Quantity args | F001 | F001 | F001 | — | — | — | — |
| `dif` SetTerm args | ✓ (consistent w/ unifier's refusal) | ✓ | n/a | ✓ | n/a | n/a | n/a |
| `dif(X, f(X))` / `dif(X, [X])` occurs | n/a | F006 / ✓ | — | — | F006 | — | — |
| multi-pair hook: violation mid-list rolls back earlier re-attaches | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| transitive violation via var-var aliasing | — | ✓ | ✓ | — | — | ✓ | — |
| constraint fully undone on `trail.undo(mark)`; re-post next clause | — | — | — | — | — | ✓ (pa: sequential-accumulation regression) | — |
| `_collect_free_vars` (dedup, nesting, bound-var chase) | ✓ | ✓ | ✓ | ✓ | ✓ (MAX_DEPTH clean) | n/a | F001 container blindness |
| `_structural_unify_oc` deep nesting | ✓ 49k clean | — | — | — | ✓ 51k clean RecursionError | ✓ | ✓ |
| hook input validation (attr not list / items not 2-tuples / attach onto malformed existing) | — | — | — | — | — | — | ✓ / **F002 segfault** / ✓ TypeError |
| `Trail_Check` guards on all 4 C entry points | pa cross_cutting #1 — fixed here, verified | | | | | | |
| Python↔C parity (dif, hook, reify_eq, collect) | ✓ transcript-identical except F002 (Python clean, C crash) | | | | | | |
| Memory: post/propagate/violate/backtrack loops, shared-value refcount | ✓ stable (obj Δ0; alloc within tol; getrefcount Δ0) | | | | | | |
| FT/free-threading | unconfirmed — needs 3.14t (3.13 GIL box); hook registry sync is A01 territory | | | | | | |

### structural_eq / structural_neq

| Surface | IN | OUT | PART | EMPTY/SINGLE | CYC | BT | ERR |
|---|---|---|---|---|---|---|---|
| scalars / lists / tuples / Compound / bound-var chase | ✓ | ✓ (two unbound distinct → False; same → True) | ✓ | ✓ | not probed (RecursionError expected; unify(oc-off) cyclic is A01-documented) | n/a | D001 (cross-type 1/1.0/True → True) |
| str ↔ char-list; ground Seg* ↔ str/list; SegString symmetry | F003 | — | — | — | — | n/a | — |
| DictTerm ↔ dict, SetTerm ↔ set equivalence | ✓ (documented intent) | — | ✓ | ✓ | — | n/a | — |

### reify_eq / eq/3 / dif_t/3 (`reif.py`)

| Surface | IN | OUT | PART | EMPTY/SINGLE | CYC | BT | ERR |
|---|---|---|---|---|---|---|---|
| `reify_eq` True/False/None; identical-var fast path; no binding leak | ✓ | ✓ | ✓ | ✓ | F006-adjacent | ✓ (trail len 0 after) | ✓ |
| `reify_eq` entailment via prior dif (hook rejection in sandbox → False) | ✓ | ✓ | ✓ | — | — | ✓ | — |
| `eq/3` T unbound / T=True / T=False / T non-truth junk | ✓ | ✓ | ✓ | ✓ | — | ✓ (suspended-generator dif live; exhaustion restores) | D001 (`eq(1,1,1)` succeeds via cross-type unify) |
| `dif_t/3` all modes + branch order (True first) | ✓ | ✓ | ✓ | ✓ | — | ✓ | D001 |
| `eq(X,Y,T)` var-var: aliases then difs | — | ✓ | — | — | — | ✓ | — |
| undetermined branches over F001 containers | inherits F001 (not separately counted) | | | | | | |

### Attributed-variable builtins (`builtins/attributes.py`)

| Surface | IN | OUT | PART | EMPTY/SINGLE | CYC | BT | ERR |
|---|---|---|---|---|---|---|---|
| put_attr/3, get_attr/3, del_attr/2 roundtrip + mode guards | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | ✓ (fail, not raise); D002 (reserved keys writable → feeds F002) |
| get_attrs/2, put_attrs/2 (DictTerm + plain dict; non-str key) | ✓ | ✓ | ✓ | ✓ (empty DictTerm) | n/a | ✓ (puts trailed) | ✓ fail-not-raise |
| attvar/1 (no attrs / attrs / deleted-last-attr) | ✓ | ✓ | n/a | ✓ | n/a | ✓ | ✓ |
| term_attvars/2 list/Compound/term-instance/DictTerm/bound-var chase | ✓ | ✓ | ✓ | ✓ | n/a | n/a | — |
| term_attvars/2 tuple / plain dict / set / Seg* | F004 | F004 | F004 | — | — | — | — |

### Units constraint (`units_constraint.py`)

| Surface | IN | OUT | PART | EMPTY/SINGLE | CYC | BT | ERR |
|---|---|---|---|---|---|---|---|
| hook: Quantity match/mismatch; zero-exponent normalisation | ✓ | ✓ | n/a | ✓ | n/a | ✓ | ✓ |
| hook: plain number vs dimensionless/dimensioned; bool rejected | ✓ | ✓ | n/a | ✓ | n/a | ✓ | ✓ |
| hook: var-var merge (same/diff dims) + transfer to unconstrained older var | ✓ | ✓ | ✓ | n/a | n/a | ✓ | ✓ |
| constrain_var_dims re-post (match/conflict); undo restores | ✓ | ✓ | n/a | ✓ | n/a | ✓ | ✓ |
| has_units/2: Quantity / attvar / non-units 2nd arg | ✓ | ✓ | n/a | n/a | n/a | ✓ | **F005** (AttributeError) |
| dif inside Quantity value | F001 | | | | | | |

### Language level (compiled `is not`, builtins from source)

| Surface | Result |
|---|---|
| `X is not Y` sugar → dif (enumerate distinct pairs; survive clause backtracking) | ✓ |
| `not (X is Y)` immediate semantics preserved | ✓ |
| `is not` vs partial pattern lint warning fires | ✓ (observed) |
| eq/3, dif_t/3 callable from Clausal source | ✓ |
| `D is not {...}` DictTerm literal | F001 (xfail) |
| dif + CLP(FD) `in_domain`/`label` seam | ✓ (singleton violating dif is rejected; label skips dif-excluded value) |

## Seam notes (for A12)

- **A01 unifier**: `_structural_unify_oc`'s fallthrough calls the *full*
  `unify_with_occurs_check` (`do_unify_and_wake`) — so **attribute hooks fire
  inside dif's sandbox**. Observed consequences are beneficial (constraint
  entailment: `reify_eq(X,1)` → False when `dif(X,1)` already posted;
  FD-domain rejection makes `dif` immediately satisfied), but it means dif's
  "structurally incompatible" branch actually encodes "incompatible under all
  currently-posted constraints", and sandbox unifies can trigger full FD/CLP(B)
  propagation cascades (perf, and any non-monotonic hook would be unsound
  here). Also: cross-type unification (A01-D001) flows straight into
  dif/reify_eq truth (A05-D001).
- **A01 occurs check**: Compound/KWTerm/PredicateMeta blindness (A01-F001)
  surfaces here as A05-F006.
- **A01 Var-Var wakeup policy**: only the *newer* var's hooks fire on
  aliasing; dif survives because pairs re-attach to the canonical (older) var
  on the next check, and units transfers explicitly — but any new constraint
  solver must copy that transfer idiom or attrs on a newer var are checked
  only via re-attachment.
- **A04 coroutining**: the boolean semidet hook protocol (A04-D001) is shared
  by `_dif_hook` and `_units_hook`; a redesign must migrate both.
- **A06 CLP(FD)**: dif+FD composition probed clean at the label/in_domain
  seam (independent attr keys, both hooks fire).
- **A03 compiler**: `DoesNotUnify` → `_dif` injection works in both compile
  paths (language-level tests); the `is not`-vs-fresh-var lint fires.
