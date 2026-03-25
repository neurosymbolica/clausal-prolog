# Rename Equality Operators + Add True Structural Equality

## Problem

`==` in clausal maps to an AST node called `StructuralEq`, but the compiler routes it
to `_fd_eq` (CLP(FD) arithmetic equality, i.e. Prolog's `=:=/2`).  The name is wrong
and risks future Claude Code instances "fixing" the behaviour to match the name.

## ISO Prolog semantics (reference)

| Prolog | Meaning                          | Clausal syntax | Clausal AST node      |
|--------|----------------------------------|----------------|-----------------------|
| `=/2`  | Unification (binds variables)    | `is`           | `Unify` ✓             |
| `\=/2` | Not unifiable                    | `is not`       | `DoesNotUnify` ✓      |
| `=:=/2`| Arithmetic equality (evaluates)  | `==`           | `StructuralEq` ✗ name |
| `=\=/2`| Arithmetic inequality (evaluates)| `!=`           | `StructuralNeq` ✗ name|
| `==/2` | Structural equality (no binding) | —              | missing               |
| `\==/2`| Structural inequality (no binding)| —             | missing               |

## Required changes

### 1. Rename existing nodes

- `StructuralEq`  → `ArithEq` (or `Eq`)
- `StructuralNeq` → `ArithNeq` (or `Neq`)

Files to update:
- `clausal/terms.py` — class definitions
- `clausal/templating/term_rewriting.py` — `CMPOP_CLS` mapping
- `clausal/logic/compiler.py` — all `case StructuralEq/StructuralNeq` branches (simple + trampoline)
- `clausal/logic/goal_expansion.py` — if referenced
- Tests that reference these node names

### 2. Add true structural equality (`==/2`)

Structural equality checks whether two terms are already identical after
dereferencing variables, **without** binding any variables and **without**
evaluating arithmetic.

- New AST nodes: `StructuralEq`, `StructuralNeq` (reclaim the names)
- New runtime function: `structural_eq(l, r)` — deref both sides, walk
  recursively, return bool.  No trail modifications.
- Syntax: TBD — Python has no spare comparison operators.  Options:
  - Builtin predicate `TermEq(X, Y)` / `TermNeq(X, Y)`
  - Or repurpose a different operator

### 3. Verify `X % 2 == 0` works

Once renamed, `==` still compiles to `_fd_eq` (arithmetic), so
`X % 2 == 0` in `.clausal` files should work as arithmetic equality.
Update TODOs in `higher_order.clausal` and `meta_predicates.clausal`.
