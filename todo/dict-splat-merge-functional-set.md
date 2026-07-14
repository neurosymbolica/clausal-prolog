# Dict splat/merge `{**P, k: V}` — functional set (the "Phase 3" gap)

**Part of:** [dict-native-profile-api.md](dict-native-profile-api.md) · **Order:** 4 (enables functional set)

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
