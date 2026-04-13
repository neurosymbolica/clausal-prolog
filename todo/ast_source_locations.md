# Source-location fidelity in generated AST

The compiler calls `ast.fix_missing_locations(func_def)` at the end of
every funcdef it builds (see `clausal/logic/compiler/predicate.py`
in `_build_predicate_trampoline_funcdef` and `_build_predicate_funcdef`,
and a few places that build standalone helper funcdefs).

`fix_missing_locations` sets `lineno` / `col_offset` to the parent
node's values for any child node that doesn't have them. In practice
this means **every** node inside the generated function ends up
labelled with the same line/column as the outer `FunctionDef` — which
is usually line 0, column 0, because the compiler builds AST nodes
directly rather than via `ast.parse` on source text.

**Consequence:** when a compiled predicate raises a Python exception,
the traceback points into the generated function but the line number
is meaningless. It does not correspond to any line in the `.clausal`
source file. Debugging is harder than it should be.

**What we'd like:** every compiled node should carry the
`lineno` / `col_offset` of the original `.clausal` source term it
was compiled from. Then Python's traceback machinery would point at
the actual source location when things go wrong.

Pieces involved:

1. `.clausal` terms carry `position` (see the `term_field_names`
   exclusion in `terms_to_ast.py`). The source-level line/column
   *is* available at parse time but is not currently threaded
   through to the compiled AST nodes.
2. The compiler's AST-building helpers (`_name`, `_call`, `_if`,
   `_assign`, etc. in `_ast_helpers.py`) take no location info.
3. Many nodes are built directly with `ast.FunctionDef(..., lineno=0,
   col_offset=0)` etc.

Proposal:

- Extend the AST-building helpers (or `CompilationContext`) to carry
  a "current source location" that tracks the term being compiled.
- As the compiler recurses into a sub-term, push its position onto
  the stack; pop on return.
- Every AST node built during that sub-term's compilation gets the
  pushed position.
- Replace `fix_missing_locations` with an assertion that all nodes
  have locations set.

Tests needed:

- Compile a predicate that raises a Python exception from a known
  source line. Verify the traceback's topmost frame inside the
  compiled function points at that line.
- Cover Unify, Evaluate, Call, list patterns, ITE, catch — each term
  shape should produce correctly-located nodes.

**Assumed broken, not tested.** Write a test that confirms the
bug before attempting the fix so we have a regression target.

## References

- `clausal/logic/compiler/predicate.py` — `_build_predicate_*_funcdef`
  functions use `fix_missing_locations`.
- `clausal/logic/compiler/_ast_helpers.py` — leaf AST builders,
  currently location-unaware.
