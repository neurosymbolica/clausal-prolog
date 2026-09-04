# pythonic_ast names leak into the strict-atom namespace

Found during P3-1 Task 7's re-review (the strictness-declaredness fix round),
while validating the fix against the reviewer's cross-module `-private`
scenario. Distinct mechanism, pre-existing (predates P3-1 entirely), NOT
fixed by that round's `_locally_declared_names` change.

## Observation

`clausal.pythonic_ast.nodes` (aliased `simple_ast` in `import_hook.py`)
exports a large set of AST-node class names via `__all__` -- `Add`, `Call`,
`Import`, `Global`, `Match`, and many more. `import_hook.py:217` seeds ALL
of them into the process-wide `predicate_builtins` pool **at module import
time** (`predicate_builtins = {name: getattr(simple_ast, name) for name in
simple_ast.__all__}`), i.e. at process bootstrap, before any `.clausal`
file has been loaded at all:

```python
predicate_builtins = {name: getattr(simple_ast, name) for name in simple_ast.__all__}
```

A bare reference to any of these names in a strict module with ZERO
declarations compiles clean instead of raising the expected
`strict_atoms: undeclared atom ...` diagnostic -- confirmed directly:

```
-module(pool_leak_probe, [Chk(X)])
Chk(X) <- (X == Add)
```

loads without error; `mod.Add is clausal.pythonic_ast.nodes.Add`. No other
file needs to run first -- this is **order-independent**, unlike the leak
Task 7 fixed (which needed an earlier module to declare the colliding
spelling at runtime). `Add` (and every other `simple_ast.__all__` name) is
in the pool from the first line of `import_hook.py` executing, full stop.

## Relationship to the Task 7 fix

The Task 7 fix (`compiler_v2._locally_declared_names` +
`_process_bare_atom_refs`'s narrowed "already resolved" check) only
distrusts `module_dict` for the specific **leaked-pool-atom shape**: a
plain `str` equal to its own name, still identical to the pool's live
entry for that name. It deliberately keeps trusting every OTHER
already-bound shape (a real `PredicateMeta` class, a genuine Python
import, or anything else) so that legitimate patterns -- an in-file
clause-head-only predicate referenced bare, or `import math` followed by
a bare `math` reference -- keep working (see
`clausal/logic/compiler_v2.py::_process_bare_atom_refs`'s docstring).
`simple_ast.__all__` class objects (`Add`, `Call`, ...) fall into exactly
that "anything else, trust it" bucket -- they are real class objects, not
the leaked-atom str shape -- so this fix's design cannot close this hole
without also breaking the raw-Python-import and in-file-predicate-class
cases it was written to preserve. This is a genuinely separate defect
needing its own, differently-shaped fix.

## Fix direction (sketch, not implemented)

Two candidate approaches, either closes it:

1. **Exclude the internal namespace from the strictness-visible pool.**
   `predicate_builtins` conflates two different jobs: (a) the runtime
   compilation-support namespace every generated module needs
   (`$ast`, `PredicateMeta`, `Var`, the `simple_ast` node classes used by
   generated code's own internals) and (b) the process-wide GLOBAL ATOM
   pool (§1b/R2). Only (b) should be visible to
   `_process_bare_atom_refs`'s "already resolved" check. Splitting these
   into two dicts (or tagging pool entries with their origin) would let
   the strictness check consult only the atom-pool half, closing this
   hole and the whole CLASS of "internal bootstrap name masquerading as a
   declared atom" bug at once, not just this instance.
2. **Require declaration even for names in `simple_ast.__all__`.** Add an
   explicit denylist (or: any name that is `getattr(simple_ast, name, None)
   is` the SAME object `simple_ast` exports) to `_process_bare_atom_refs`
   so these specific names are never treated as auto-resolved regardless
   of `module_dict` state. Cheaper to write, but doesn't generalize to
   whatever else might get seeded into `predicate_builtins` for
   non-atom reasons in the future (`INJECTED_RUNTIME_BUILTINS`, e.g.).

Option 1 is architecturally cleaner (fixes the conflation, not just the
symptom) and is the recommended direction; option 2 is a faster stopgap
if this needs fixing before the split is scoped.

## Disposition

Parked, not fixed. Distinct from, and not a regression introduced by, the
P3-1 Task 7 declaredness-bypass fix -- pre-existing since `predicate_builtins`
was first seeded with `simple_ast.__all__`, well before P3-1. Low real-world
impact (the colliding names are internal AST-node class names, unlikely to
be typed as an ordinary atom spelling by accident), but worth fixing before
relying on strict-atoms as a hard guarantee rather than a typo-catcher.
