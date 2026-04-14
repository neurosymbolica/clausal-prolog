# Remove surface support for `(block if condition else orelse)`

Python-style conditional expressions as goals lower to
`clausal.pythonic_ast.nodes.IfExpr`, which the compiler handles as a
general / reified if-then-else (see `clausal/logic/compiler/ite_reified.py`
and, post-Slice D5d, the IR `Branch` op in `clausal/logic/compiler/ir.py`).

User intent: drop the surface-level support so goal-position
`if`/`else` is no longer accepted.  Clausal already has Prolog-style
`(Cond -> Then ; Else)` via the control-construct pathway; the
Python-ternary syntax is redundant and has been a source of
confusion.

## Scope

- Surface parser: reject `block if cond else orelse` in goal position
  (likely a diagnostic in the pythonic_ast → terms lowering, or a
  grammar change depending on where `IfExpr` is emitted).
- Decide whether `IfExpr` stays in the AST as an *expression-position*
  node or is removed wholesale.  If it stays, goal-position usage
  must raise a clear diagnostic.
- Remove `IfExpr` handling from:
  - `clausal/logic/compiler/goal_shallow.py::_dispatch_goal`
  - `clausal/logic/compiler/goal_trampoline.py::_dispatch_goal_trampoline`
  - `clausal/logic/compiler/ite_reified.py` (entire module, if
    fully unreachable)
  - `clausal/logic/compiler/terms_to_goalop.py::_convert` (IfExpr arm)
  - `clausal/logic/compiler/_lower_goalop_shared.py::_lower_reified_branch`
    and the `Branch` arm in `_lower_goalop_shared`
  - `clausal/logic/compiler/lower_python_shallow.py` (general-ITE arm)
  - `clausal/logic/compiler/lower_python_trampoline.py` (general-ITE arm)
  - `clausal/logic/compiler/ir.py` — `Branch` class and `ReifiedKind`
    literal (if no other IR consumer uses them)

## Dependencies

- Sequence with the Slice D migration: easier to remove after D7
  retires the legacy path.  Removing before D7 means touching twin
  legacy + IR handlers.
- Audit `.clausal` fixtures / docs / tutorials for existing usage;
  each will need to migrate to `(Cond -> Then ; Else)` or be
  removed.

## Validation

- Full test suite passes (10463+ ex-trealla baseline).
- No `IfExpr` nodes remain in any compiled `.clausal` or `.pl`
  fixture (grep the AST dumps).
- A negative test asserts a friendly diagnostic when
  `block if cond else orelse` appears in goal position.
