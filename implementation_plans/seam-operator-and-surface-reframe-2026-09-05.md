# The `--` seam operator + the surface reframe (design note, 2026-09-05)

Author's chain of thought during P3-3 plan review; assessed same day. Two related
ideas, one ruling, no P3-3 impact beyond R10's revision (recorded in the plan).

## 1. The `--` seam operator (parked; post-P3-3 or surface phase)

As `++(py_expr)` escapes Clausal→Python, `--(clausal_expr)` escapes
Python→Clausal inside embedded Python in `.clausal` files. History: `--` was the
ORIGINAL "seam" operator (looks like sewing stitches); `++` came after. Example
target: `solve(goal, module=--m1.m2)` — and more generally passing TERMS from
embedded Python: `--foo(1, 2, X)`.

Feasibility (assessed):
- `--x` is already valid Python (`UnaryOp(USub, UnaryOp(USub, x))`) — the exact
  mirror of `++`'s interception; the CURRENT rewriter pipeline can claim it in
  `.clausal` files without waiting for the ISO reader.
- The term lowering it needs ALREADY EXISTS: P3-2's Site A (`term_to_ast_expr` +
  `_place_signature_slots`) is precisely the `foo(1,2,X)` → `('foo', 1, 2, X)`
  AST translation; `--` is a routing decision into it, not new compilation.
- Boundary: only `.clausal` files get the sugar (the rewriter never sees `.py`);
  plain Python uses the runtime API (`solve(goal, module='m1.m2')`, tuples as
  terms — the representation is public post-P3-2).

## 2. The surface reframe (PROPOSED direction, author 2026-09-05; endorsed on
assessment, not yet ratified as a ruling)

Flip the framing: **ISO Prolog syntax becomes the PRIMARY Clausal syntax for
logic programs** (the reader being built, user-owned, R3); the existing
Python-style syntax is re-positioned as what it structurally always was — a
**Python-familiar embedding/adaptor syntax** for expressing terms and programs
inside Python surface code. Under this reading:
- The runtime is already ISO-shaped (global atoms P3-1, cells P3-2, qualified
  goals + Database-authoritative P3-3) — the reframe makes the program MORE
  coherent, changes no mechanics.
- `==`-for-unify / `is`-binding stop being "the language's quirks" and become
  adaptor idioms; the primary surface has `'='(X, Y)`, proper operators, and
  ISO semantics natively.
- Phase 5's positioning (docs, seam naming) re-aims accordingly; the
  classes-as-functors seam design (python-seam-classes-as-functors.md) sits
  naturally as part of the ADAPTOR story.

## Ruling recorded (user, 2026-09-05)

- **Directives in the ISO surface use the standard `:- ` form** (not the
  adaptor's `-name(...)` spelling, which remains the adaptor's).

## Related R10 revision (recorded in implementation_plans/p33-state-relocation.md)

Module designators key `sys.modules` directly by dotted atom — ONE module
registry (user: two possibly-conflicting module dicts is the same disease as
two clause stores). Nested `(":", m1, (":", m2, G))` legal, peels innermost-wins
(qualification stacking à la SWI/SICStus; modules are flat — ISO 13211-2 is
effectively unadopted); the dotted atom is the idiomatic path form since the
hierarchy lives in Python's module system.
