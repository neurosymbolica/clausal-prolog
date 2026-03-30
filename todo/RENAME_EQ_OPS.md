# Rename Equality Operators + Add True Structural Equality

## Status: ✅ Complete

## Problem

`==` in clausal mapped to an AST node called `StructuralEq`, but the compiler routed it
to `_fd_eq` (CLP(FD) arithmetic equality, i.e. Prolog's `=:=/2`).  The name was wrong
and caused repeated mis-renaming by Claude Code instances.

## ISO Prolog semantics (reference)

| Prolog | Meaning                          | Clausal syntax          | Clausal AST node      |
|--------|----------------------------------|-------------------------|-----------------------|
| `=/2`  | Unification (binds variables)    | `is`                    | `Unify` ✓             |
| `\=/2` | Not unifiable                    | `is not`                | `DoesNotUnify` ✓      |
| `=:=/2`| Arithmetic equality (evaluates)  | `==`                    | `ArithEq` ✓           |
| `=\=/2`| Arithmetic inequality (evaluates)| `!=`                    | `ArithNeq` ✓          |
| `==/2` | Structural equality (no binding) | `structural_eq(X, Y)`   | `StructuralEq` ✓      |
| `\==/2`| Structural inequality (no binding)| `not structural_eq(X,Y)`| `StructuralNeq` ✓    |

## Changes made

### 1. Rename existing nodes ✅

- `StructuralEq`  → `ArithEq` (with guard comment warning against re-renaming)
- `StructuralNeq` → `ArithNeq` (with guard comment)

### 2. Add true structural equality (`==/2`) ✅

- New AST nodes: `StructuralEq`, `StructuralNeq` in `pythonic_ast/nodes.py`
- Re-exported from `clausal/terms.py`
- Runtime: `structural_eq()` / `structural_neq()` in `clausal/logic/constraints.py`
  — deref both sides, walk recursively (Compound, SegList, SegString, DictTerm, SetTerm,
  user-defined term dataclasses), return bool.  No trail modifications.
- Compiler: simple + trampoline compilers emit `_structural_eq`/`_structural_neq` calls
- Determinism: both marked as deterministic
- Builtin predicate: `structural_eq/2` (replaced old `equivalent/2`)
  — callable from `.clausal` files as `structural_eq(X, Y)`
  — inequality via `not structural_eq(X, Y)`
- Tests: `TestStructuralEquality` and `TestStructuralInequality` in
  `tests/conformity/test_iso_unification.py`, plus `TestStructuralEq` in `tests/test_clpfd.py`

### 3. Verify `X % 2 == 0` works ✅

`==` still compiles to `_fd_eq` (arithmetic), so `X % 2 == 0` in `.clausal` files
works as arithmetic equality.
