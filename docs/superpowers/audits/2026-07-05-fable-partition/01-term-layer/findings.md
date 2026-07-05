# Findings — A01 term-layer & C unification

Severity order: correctness > memory > design > perf > doc-drift.
Confirmed correctness findings have a Test ref AND a Todo ref.
Test file: `tests/audit_2026_07_05/test_01_term_layer.py` (37 passed,
20 xfailed on 2026-07-05 — every suspected-bug xfail actually fails, i.e.
every finding below reproduces).

| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref | Todo ref |
|----|----------|-------|----------------------|-------|--------------------|----------|----------|
| A01-F001 | correctness | occurs-check blind to Compound / KWTerm / PredicateMeta instances — `unify_with_occurs_check` builds cyclic terms | `_variables.c:941-954` (hook fallthrough → 0); `terms.py:67` Compound, `terms.py:107` KWTerm, `predicate.py` PredicateMeta define no `__occurs_check__` | `occurs_check(X, Compound("f",(X,)))` | `True` vs `False`; `unify_with_occurs_check(X, f(X))` succeeds and creates the cycle it exists to prevent | `TestF001OccursCheckBlindness` | `todo/audit-2026-07-05/fix-A01-occurs-check-compound-blindness.md` |
| A01-F002 | correctness (latent, C) | `capi_put_attr` Var→AttVar promote path: `Py_BuildValue("(OOsO)")` passes a `PyObject*` where `s` expects `char*` (UB), the built tuple leaks, and `py_put_attr` would reject a plain Var anyway | `_variables.c:3145-3164` | code-read; no in-tree consumer of the capsule's `put_attr` exists (grep 2026-07-05), so **unconfirmed — not executable from Python** | promote or clean error vs undefined behaviour + guaranteed failure | — (unconfirmed; no reachable entry) | `todo/audit-2026-07-05/fix-A01-capi-put-attr-promote-path.md` |
| A01-F003 | correctness | Compound Var-functor support broken across the layer: unify compares functor with `!=` (no deref — even a functor Var *bound* to `"f"` fails; unbound never binds), `copy_term` doesn't freshen the functor var, `_is_ground` ignores the binding, `_collect_vars` misses the var, `term_str` renders a bound functor as anon `_` | `terms.py:92` (unify), `terms.py:1903-1907` (render); `_variables.c:2734` (copy), `:2120-2124` (ground), `:2985-3005` (collect) | `F=Var(); unify(F,"f",t); unify(Compound(F,(1,)), Compound("f",(1,)), t)` | `True` vs `False` (and 4 sibling behaviours) — docstring `terms.py:70-73` advertises `Compound(functor_var, args)` | `TestF003CompoundVarFunctor` (6 xfail + control) | `todo/audit-2026-07-05/fix-A01-compound-var-functor.md` (direction blocked on parked D004) |
| A01-F004 | correctness | KWTerm defines no `__unify__` — C falls back to rich-compare `__eq__`, so Var-valued fields never bind; docstring claims "Equality and **unification** match by keyword name" | `terms.py:107-189`; fallback `_variables.c:1379` | `unify(KWTerm("r",a=Y,b=2), KWTerm("r",a=1,b=2), t)` | `True` + `Y=1` vs `False`, no binding | `TestF004KWTermUnify` | `todo/audit-2026-07-05/fix-A01-kwterm-unify-hook.md` |
| A01-F005 | memory | Seg* `_unify_gens` cache: suspended (non-exhausted) generators are only popped on StopIteration, so each (target, trail) pair pins its Trail — and everything trailed — for the life of the Seg* term; 20/20 dead trails stayed alive in the probe | `terms.py:257-262,418-428` (SegList; SegString/SegBytes mirror) | drive first split of `[*A,*B] = [1,2,3]` on N fresh trails, undo, drop trail | trails collectable vs all N pinned via `sl._unify_gens` | `TestF005UnifyGensRetention` | `todo/audit-2026-07-05/fix-A01-seg-unify-gens-retention.md` |
| A01-F006 | correctness | SegList "ground" unify path: a walk that yields an all-ConcreteSeg **list containing unbound element Vars** is treated as ground and compared with `==` instead of element-wise unify — satisfiable goals fail; `is_ground()` also answers True for such terms | `terms.py:404-415` (unify), `:340-344` (is_ground) | `unify(SegList([VarSeg(A), ConcreteSeg([E])]), [1,2], t)` after `A=[1]` | `True, E=2` vs `False`; arises whenever a `[*A, X]` pattern's star gets bound before the list unify | `TestF006SegListElementVarGroundPath` | `todo/audit-2026-07-05/fix-A01-seglist-element-var-ground-path.md` |
| A01-F007 | correctness | `SegList.__unify__` accepts only `list`/`str` targets — no `bytes` arm, though the C layer unifies plain code-lists with bytes and `SegBytes` accepts lists (codes-model asymmetry) | `terms.py:404,429-431` | `unify(SegList([ConcreteSeg([71]), VarSeg(A)]), b"GET", t)` | `True, A=[69,84]` vs `False` (control: `unify([71,B], b"GE")` binds) | `TestF007SegListVsBytes` | `todo/audit-2026-07-05/fix-A01-seglist-bytes-target.md` |
| A01-F008 | design/correctness-low | C `walk()` rebuilds lists/tuples and `__walk__`-hooked types (Seg*, DictTerm) but is blind to Compound / KWTerm / PredicateMeta instances — a walked "snapshot" of a compound decays to unbound after `trail.undo`. Clausal thus has two deep-walkers with disjoint blind spots (see seam note on `_deref_walk`) | `_variables.c:1626-1635`; contrast `solve.py:49-68` | `walk(Compound("f",(X<-1,)))`, then `trail.reset()` | snapshot keeps `1` vs decays to unbound Var | `TestF008WalkFunctorTerms` | `todo/audit-2026-07-05/investigate-A01-walk-vs-deref-walk-split.md` (Opus) |
| A01-F009 | error-path | SegString VarSeg bound to a non-str scalar (contract violation reachable via plain `unify(V, 5)`) walks to a nonsense `VarSeg(5)` and fails silently forever — the F024 typed-error guard covers only char-*list* bindings | `terms.py:838-840` (else-branch keeps `VarSeg(v)`); guard at `:810-816` | `unify(Z,5,t); SegString(["a",VarSeg(Z)]).__walk__()` | `PartialTermError` (F024 precedent) vs silent non-ground limbo | `TestF009SegStringScalarBinding` | `todo/audit-2026-07-05/fix-A01-segstring-scalar-varseg-guard.md` |
| A01-F010 | design | Seg* `__getitem__` on a non-ground term raises `PartialTermError` for slices that lie entirely within the knowable concrete prefix (int indices there are served) | `terms.py:993-1009` (SegString; SegList `:515-546`, SegBytes `:1275-1291` mirror) | `SegString(["abc",VarSeg(B)])[0:2]` | `"ab"` vs `PartialTermError` | `TestF010SliceWithinPrefix` | `todo/audit-2026-07-05/fix-A01-seg-getitem-slice-in-prefix.md` |
| A01-F011 | doc-drift | `terms.__all__` omits public names its own docstrings/exceptions reference: `SegList`, `ConcreteSeg`, `VarSeg`, `Quantity`, `UnitsMismatch`, `PartialTermError` | `terms.py:2220-2260` | `from clausal.terms import *` | names importable vs absent | `TestF011AllExports` | `todo/audit-2026-07-05/fix-A01-terms-all-exports.md` |

Open design questions (parked by user 2026-07-05 — see
`design-questions.md` and `todo/audit-2026-07-05/investigate-A01-parked-design-decisions.md`):
A01-D001 cross-type numeric unification (`1`/`True`/`1.0`/`Decimal(1)` all
unify via Python `==`), A01-D002 Quantity dimensionless eq/unify vs
comparison asymmetry, A01-D004 intended support level for Compound Var
functors (fix direction for F003).

## Coverage map

Files: `clausal/terms.py`, `clausal/pythonic_terms.py` (re-export shim only — no
logic to probe), `clausal/logic/variables/_variables.c`,
`clausal/logic/variables/__init__.py`.

Dimensions per row: **IN** = input/ground mode, **OUT** = output/var mode
(unbound Var in the position), **PART** = partially instantiated,
**EMPTY/SINGLE** = empty & singleton inputs, **CYC** = cyclic/self-referential,
**BT** = backtracking + trail restoration, **ERR** = error paths.
Legend: `✓` probed clean, `F###` finding, `D###` design question, `pa` =
prior art (2026-05-25 ledger / cross_cutting_issues.md — cited, not
re-reported), `n/a` = dimension meaningless.

### C core (`_variables.c`)

| Surface | IN | OUT | PART | EMPTY/SINGLE | CYC | BT | ERR |
|---|---|---|---|---|---|---|---|
| `unify` atomic (int/float/bool/None/str/bytes) | ✓ | ✓ | n/a | ✓ | n/a | ✓ | D001 (cross-type ==) |
| `unify` Var-Var / Var-Term (age-ordered bind) | ✓ | ✓ | ✓ | n/a | ✓ (oc off → cyclic, documented) | ✓ | ✓ |
| `unify` tuple↔tuple / list↔list | ✓ | ✓ | ✓ | ✓ | ✓ (clean RecursionError) | ✓ | ✓ (MAX_DEPTH clean at 51k) |
| `unify` str↔list (Liskov chars) | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | ✓ |
| `unify` bytes↔list (codes) | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | ✓ |
| `__unify__` hook ordering (t1 non-seq → t2; raise propagates + rollback) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | F004 (KWTerm has no hook) |
| `unify_with_occurs_check` | ✓ | ✓ | ✓ | ✓ | F001 (Compound/KWTerm/PredicateMeta blind) | ✓ | ✓ |
| `occurs_check` list/tuple/Seg*/DictTerm/chains | ✓ | n/a | ✓ | ✓ | ✓ | n/a | ✓ (depth guard clean) |
| `walk` (deep substitution) | ✓ | ✓ | ✓ | ✓ | ✓ (terminates — via F008 blindness) | ✓ | F008 |
| `deref` / `is_var` / long chains (2k–10k) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Trail mark/undo/reset/record; undo past mark; negative mark | ✓ | n/a | ✓ | ✓ | n/a | ✓ | ✓ (cross-thread RuntimeError; `mark()` read allowed) |
| put_attr / get_attr / del_attr + wake hooks + reject-rollback + BT | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | ✓; D003 hookless silently succeeds (resolved-from-docs) |
| `capi_put_attr` promote path (PlainVar) | n/a | n/a | n/a | n/a | n/a | n/a | F002 (code-read; capi-only, no in-tree caller) |
| `_copy_term_impl` (Compound/KWTerm/dataclass/list; sharing) | ✓ | ✓ | ✓ | ✓ | n/a | n/a | F003 (functor var); pa F092 (Seg*) |
| `_collect_vars_impl` | ✓ | ✓ | ✓ | ✓ | n/a | n/a | pa F093 (Seg*); F003 (functor var) |
| `_is_ground` | ✓ | ✓ | ✓ | ✓ | n/a | n/a | pa F083 (Seg*); F003 (bound functor var) |
| `_functor_name`/`_arity`/`_nth_arg`/`_args_list` | pa F088–F091 cons-cell semantics (user decision 2026-06-13; not re-probed) | | | | | | |
| Var coercion int/float/bool; `UnboundVarCoercionError`; repr/str/format | ✓ | ✓ | n/a | n/a | ✓ (repr truncates via Python guard) | n/a | ✓ |
| FT/free-threading (statics, sub-interpreters) | pa cross_cutting #4/#5 — **unconfirmed, needs 3.14t** (this box is a 3.13 GIL build) | | | | | | |
| Leak checks (`refcount_stable`/`getrefcount_stable` on unify/backtrack, str↔list, Compound, put_attr+wake, bound value, trail) | ✓ all stable | | | | | F005 is the one structural retention found | |

### Python term layer (`terms.py`)

| Surface | IN | OUT | PART | EMPTY/SINGLE | CYC | BT | ERR |
|---|---|---|---|---|---|---|---|
| `Compound.__unify__` (str functor; arity/functor mismatch; empty args) | ✓ | ✓ | ✓ | ✓ | F001 | ✓ | ✓ |
| `Compound` (Var functor: unify/copy/ground/collect/render) | F003 | F003 | F003 | n/a | — | n/a | F003 |
| `KWTerm` eq/hash/keys/values/items/`_position`/with_overrides/with_extensions | ✓ | F004 | F004 | ✓ | F001 | n/a | ✓ |
| `SegList.__walk__` / `is_ground` / `to_list` (incl. nested partial inlining, VarSeg→str expansion, F018 promotion) | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | pa F018/F083; F006 (`is_ground` with element Vars) |
| `SegList.__unify__` vs list/str (drive pattern all splits; unhashable-elem cache keys) | ✓ | ✓ | ✓ | ✓ | n/a | pa F015 gen-cache | F006 (element-Var "ground" path); F007 (no bytes arm); F005 (retention) |
| Seg* vs Seg* non-ground | pa F030 (deferred) — still fails; SegString↔SegString and SegList↔SegString likewise (extension noted on F030 todo) | | | | | | |
| `SegList`/`SegString`/`SegBytes` seq protocol (len/iter/contains/getitem) | ✓ | ✓ | ✓ | ✓ | n/a | n/a | pa F021/F022/F038/F039; F010 (in-prefix slice) |
| `SegList`/`SegString` `__eq__`/`__hash__` | pa F017/F019/F025 (unconditional unhashable confirmed) | | | | | | |
| `SegString.__walk__`/`__unify__` (min-len fast fail, empty target, char-list guard) | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | pa F016/F023/F024; F009 (scalar VarSeg binding) |
| `SegBytes` walk/unify/eq/seq (vs bytes, vs code-list) | ✓ | ✓ | ✓ | ✓ | n/a | ✓ | ✓ (construction guard typed) |
| `DictTerm` (unify vs DictTerm/dict both orders, key mismatch, walk, occurs, hash-with-Var) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `SetTerm` (ground-only contract) | ✓ | n/a (documented) | n/a | ✓ | n/a | n/a | ✓ (silent False on Var elements — per docstring) |
| `Quantity` (arith incl. UnitsMismatch, cmp, unify, dims merge) | ✓ | ✓ | n/a | ✓ | n/a | ✓ | D002 |
| `list_to_cons` / `cons_to_list` | ✓ | n/a | n/a | ✓ | n/a | n/a | ✓ (ValueError on improper) |
| `term_str` / `term_pformat` / `term_html` | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | F003 (bound-Var functor renders `_`) |
| `terms.__all__` | F011 doc-drift | | | | | | |

### Dry-pass log

Five probe passes (`/tmp/a01_probe1..4.py` + inline pass 5). Pass 4 surfaced
only design items (D001 matrix, D003) and pass 5 surfaced F007; the follow-up
cyclic/depth checks surfaced nothing new → stopped per the 2-dry-pass rule
(passes were near-dry; the map above is fully exercised).

### Seam notes for A12

- **`_deref_walk` (solve.py:49 / `_tabling_core` C twin) is blind to `tuple`,
  `KWTerm`, `DictTerm`, and `SegList` templates** — probe-confirmed at helper
  level: snapshots taken per-solution decay to unbound after `trail.undo`,
  which is exactly the findall/bagof/setof snapshot path
  (`compiler/control_constructs.py:_compile_find_all_core` uses
  `$deref_walk`) and the tabling answer-key path (`tabling.py:186`). This is
  A04/A09 territory (files outside A01's list) — **needs its own finding
  there**; cross-ref A01-F008 (the C `walk` has the *complementary* blind
  spot: it handles Seg*/DictTerm via `__walk__` but not Compound).
- The compiler's head matcher relies on the F015 generator-cache drive
  pattern of `Seg*.__unify__` via C `do_unify`; F005's lifetime fix must
  preserve the mark/unify/undo enumeration contract.
- `c_is_term_instance` treats ANY dataclass instance as a term (attribute
  probe for `__dataclass_fields__`) — boundary with A02's head matcher for
  arbitrary Python objects.
- First-arg indexing / tabling keys may distinguish `1`/`True`/`1.0` where
  `unify` conflates them (D001) — check dispatch consistency in A02/A04.
