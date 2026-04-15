# Internal-name audit — where compiler/runtime names can leak into user code

**Status:** ✅ complete (2026-04-14).

## Resolution

Audit (via Explore subagent) found only one real collision surface:
the Slice G `position` metadata attribute on user-reachable term
classes (`Compound`, `KWTerm`, `DictTerm`, `SetTerm`, `PyThunk`).
Users could write a `.clausal` keyword term with `position=...` or a
PredicateMeta clause head with a `position` field, silently clashing
with the metadata slot.

**Fix applied:** renamed the attribute `position` → `_position` across
all five term classes.  Clausal treats leading-underscore names as
logic variables, so `_position` is syntactically unreachable as a
user field name at the Clausal source level — complete isolation
with no Python-dunder-namespace collision risk.

Updated reader/emitter sites:
- `clausal/terms.py` — slots + constructor kwargs.
- `clausal/templating/term_rewriting.py` — templater-emitted kwargs
  for `PyThunk` and `DictTerm` constructor calls.
- `clausal/logic/compiler/terms_to_goalop.py` — reads `_position`
  from terms (falls back to `position` for pythonic_ast Nodes).
- `clausal/logic/compiler/terms_to_ast.py` — filter now excludes
  both `_position` (term) and `position` (pythonic_ast Node).

Out of scope (kept as-is):
- `pythonic_ast.Node.position` — internal AST nodes, never
  user-constructable.
- `GoalOp.position` — internal IR.
- `base_globals` bare names (`unify`, `deref`, `Compound`, `Var`, …)
  — intentional API surface.
- Compiler-emitted locals (`trail`, `this_generator`, `_disp_*`, …)
  — scope-local function parameters, hygienic.
- `$module`, `$ast` module-namespace keys — `$` prefix already blocks
  dot-access syntactically.

Tests green: 10439 passed / 0 failed / 90 skipped (delta: pre-fix
baseline had 24 pre-existing position-collision failures, now all
passing).
