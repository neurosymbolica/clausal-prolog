# Dict splat/merge `{**P, k: V}` — functional set (the "Phase 3" gap)

**Part of:** [dict-native-profile-api.md](dict-native-profile-api.md) · **Order:** 4 (enables functional set)

## STATUS: DONE 2026-07-14 — already worked at runtime; the "Phase 3" comment was stale
`visit_Dict` emits a `DictLiteral` for splat dicts, and `term_to_ast_expr`'s `DictLiteral` case
(`clausal/logic/compiler/terms_to_ast.py`) already folds it into `DictTerm({**deref(P).data, k: v, ...})`,
which gives Python **last-wins** for free (later explicit pairs and later `**splat`s override). Verified all
acceptance cases + multi-splat + value-var preserved; locked with tests (`merge override/default order/addkey/
value var/multi splat` in the fixture + `test_dict_set_compiler.py`).

**Hardened 2026-07-14:** the merge lowering now routes each splat source through the `$splat_data` runtime
helper (`clausal/logic/runtime/dict_ops.py`) instead of a bare `deref(P).data`, so an **unbound splat
source** (`{**P}` with `P` a Var) raises a catchable `instantiation_error` and a **non-dict source**
(`{**5}`) raises `type_error(dict, …)` — previously both leaked a raw `AttributeError`. Covered by
`splat unbound/nondict source errors` tests.

## Goal
Evaluate splat/merge dict literals at runtime so functional profile update works:
- `P2 is {**P, filing_status: V}` → new `DictTerm` = P with `filing_status` **set/overridden** to `V`.
- `P2 is {filing_status: Default, **P}` → P **wins** if present (this is the *default* idiom).
Semantics: **Python last-wins** — later entries (explicit pair or a later `**splat`) override earlier ones.
Always succeeds (setting never throws). Multiple splats allowed. Keys ground.

## Where
- `clausal/templating/term_rewriting.py:726-746` (`visit_Dict`) already detects `**` and emits a
  `DictLiteral` node — with the comment **"full splat/merge support is Phase 3."** That runtime evaluation
  is the missing piece: fold the `DictLiteral` (keys list w/ `None` marking splat positions + values list)
  into a single merged `DictTerm`, honoring last-wins.
- Must interoperate with `is/2` evaluation (RHS is computed) and with unbound `Var` values (carry them into
  the result; they stay unifiable).
- Interaction with unification: a fully-ground merge yields a ground `DictTerm`; document behaviour if a
  splat source is an unbound var (should error or defer — pick and test).

## Acceptance
- `P2 is {**{a:1, b:2}, b: 9}` ⇒ `P2 == {a:1, b:9}` (override).
- `P2 is {b: 9, **{a:1, b:2}}` ⇒ `P2 == {a:1, b:2}` (default: source wins).
- add-new-key: `P2 is {**{a:1}, c: 3}` ⇒ `{a:1, c:3}`.
- value-var preserved: `P2 is {**{a:1}, b: V}`, later `V=2` ⇒ `P2 == {a:1, b:2}`.
- `set`/`delete` are NOT on the SMT proof surface (mutation is planner-only) — no prover change needed here.
