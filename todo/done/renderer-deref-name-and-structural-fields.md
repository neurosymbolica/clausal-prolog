# renderer — deref bound logic vars in name/structural field positions

STATUS: DONE (2026-07-20). A `_deref_field` (and sequence-aware `_deref_seq_field`)
helper now derefs every name/structural field that bypasses `_ClauseRenderer.term`
— `Goal.name`/`args`/`kwargs` (incl. each kwarg *entry* and name), `Clause.goals`,
`Variable.name`, `Escape.code`/`FormatString.code`, `_dict_literal_ast` keys/values,
`_dict_key_ast`'s intern-atom guard, `_lambda_ast` param chain, and `render_ast`'s
top-level split. Bound vars render their value; unbound vars (and non-sequence
garbage in a list position) raise `RenderError`, so render_ast/render_source now
raise **only** `RenderError`. Duplicate post-deref dict keys raise (collision key
is the unparsed *surface*, so AST-distinct-but-textually-equal keys are caught).
A Fable review drove a second pass that closed sibling leaks it found (kwarg-entry
var, `_dict_literal_ast`/`_dict_key_ast`/`_lambda_ast` positions) and the
dump→unparse collision-key fix. `tests/test_reflection_render.py::TestBoundLogicVarsInFields`
(19 tests, incl. parametrized unbound-var contract checks); full suite green
(9836 passed). Original notes follow.

(filed 2026-07-20, from the renderer-deref Fable review.)

## The gap
`todo/done/renderer-deref-bound-var-operands.md` made `_ClauseRenderer.term()`
deref at entry, fixing every *operand/element* position (operator operands, list
/tuple elements, dict values, `IfThenElse` parts). But `term()` is **not** the
only recursive entry: several **name and structural field** reads bypass it and,
when the field holds a bound logic `Var`, leak a non-`RenderError` exception —
violating `render_ast`'s documented contract (*"Raises `RenderError` for any node
kind the renderer does not handle"*, `clausal/reflection.py` ~948-954). All of
these reproduce today with a var bound *before* rendering (probe-confirmed in the
review); they pre-date the operand fix.

| Field position | Site (approx) | Current failure |
| --- | --- | --- |
| `Goal.name` (bound var) | `_name_ast` / `_goal_ast` | `RenderError: cannot render non-string name` — but this is the op_node late-binding case for `Goal(NAME, ARGS)` |
| `Goal.args` list is a var | `_goal_ast` | **`TypeError`** leak |
| `Goal.kwargs` pair name | `_goal_ast` | **`TypeError`** at unparse |
| `Clause.goals` is a var | `clause()` (~420) | **`TypeError: no len()`** |
| `Variable.name` (logic var) | `term()` Variable branch (~485) | **`AttributeError: 'AttVar' has no 'startswith'`** |
| `Escape.code` | `_parse_code` (~465) | **`TypeError` from `compile()`** |

## Deliverable
Deref (and `is_var`-guard → `RenderError`) at each field-read that bypasses
`term()`. Cleanest: a small `_deref_field(value)` helper that derefs and raises a
`RenderError` on an unbound var, used at:
- `_name_ast` entry (covers `Goal.name` and dotted-name segments);
- `clause()` before iterating `term.goals`;
- the `Variable` branch before `value.name.startswith(...)`;
- `_parse_code` before `compile(code)`;
- `_goal_ast` for the args list and each kwarg name/value.

## Also from the same review (minor, fold in here)
- **`render_ast` entry** (~955): add `term = deref(term)` before
  `isinstance(term, Clause)` — a top-level var bound to a `Clause` currently dies
  in `term()` with `cannot render term: Clause(...)`.
- **`_dict_key_ast`** (~633): `key = deref(key)` at entry — a bound var wrapping
  an `$intern_atom` key otherwise mis-renders.
- **Duplicate dict keys after deref** (dict branch ~510): two distinct key vars
  both bound to the same value render `{5: 'a', 5: 'b'}`, which re-reifies to
  `{5: 'b'}` — a silently lost key (round-trip fidelity is an invariant here).
  Raise `RenderError` if derefed keys collide.

## Acceptance
- Each row above renders the bound value (or raises `RenderError` if the var is
  unbound) — never `TypeError`/`AttributeError`.
- `render_ast`/`render_source` raise **only** `RenderError` for any unrenderable
  input, honoring the docstring contract.
- Duplicate post-deref dict keys raise `RenderError` rather than silently drop.
- Full suite green; focused tests per field position (mirror
  `tests/test_reflection_render.py::TestBoundLogicVars`).

## Scope note
Pure renderer robustness; mostly matters for renderer-constructed terms (op_node
/matcher-built `Goal`s with a `NAME`/`ARGS` var bound late). Normal reified
corpus terms carry reified `Variable`/`Atom` vocab, not logic vars, so the corpus
round-trip is unaffected — but the contract leak is real for the auditor's
build-then-render flows.
