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

## Resolution (2026-09-05, P3-2 Task 8)

Fixed via fix direction 1, the architectural split. `import_hook.py`'s one
process-wide dict is now two:

- `runtime_builtins` -- the compilation-support namespace (every
  `simple_ast.__all__` node class plus `INJECTED_RUNTIME_BUILTINS`).  Still
  seeded into every module's `module_dict` at exec start (generated code's
  bare `Predicate(head=..., body=...)` construction, among others, needs
  it), but NEVER consulted by the strictness check.
- `predicate_builtins` -- the §1b/R2 global ATOM pool, and *only* that.
  Starts empty at process bootstrap; grows solely via a legitimate
  declaration (`-module`/`-private`), auto-accept (`-implicit_atoms`), or
  `global_atom/2`'s mint-on-demand.

Module-exec seeding applies both, `predicate_builtins` (the atom pool)
FIRST and `runtime_builtins` layered on top, WINNING any collision --
fix round 1 tried the opposite order (by analogy with
`clausal/logic/compiler/predicate.py`'s `base_globals`, where a module's
own already-resolved globals safely win over the static runtime defaults)
and broke `tests/fixtures/tagged_shapes.clausal`: seeding runs BEFORE
`_process_declarations`/`_process_bare_atom_refs`, against the RAW,
unfiltered pool, so an atom legitimately declared as `Sub` in one module
clobbered every OTHER module's `module_dict["Sub"]` with a plain str --
breaking that module's own generated code, which unconditionally needs
the real `simple_ast.Sub` class to construct arithmetic in its clause
bodies (`N1 == N - 1` compiles to a bare `Sub(...)` constructor
reference). A module that DOES want to declare that spelling still gets
it correctly: `_process_declarations` runs after seeding and
unconditionally rebinds its own declared names regardless of what
seeding left there.

`compiler_v2._process_bare_atom_refs` and `import_hook._make_intern_atom`
(the dict-key path had the identical leak shape, e.g. `{Add: 1}[Add]`, and
was fixed too) both gained a second "leaked" shape alongside Task 7's
leaked-pool-atom check: an already-bound value that is identical to
`runtime_builtins`'s own entry for that name is now distrusted the same
way, unless the module's own declared/imported vocabulary
(`_locally_declared_names`) vouches for it, OR the name is one of the
explicit, reviewed exemptions in `import_hook.STRICTNESS_EXEMPT_RUNTIME_
NAMES` (currently just `Undefined` -- the Kleene K3 truth value, a
pre-existing, deliberate design decision that it resolves bare in every
module, strict or not, unrelated to this todo).

**Delivered contract**: the distrust check covers the WHOLE of
`runtime_builtins` by default -- not just the `simple_ast.__all__` subset
-- so a bare reference to ANY compilation-support name (a current
`simple_ast` node class, or a FUTURE `INJECTED_RUNTIME_BUILTINS` addition)
fails LOUD with the strict-atoms diagnostic unless it is either declared
by the referencing module or explicitly exempted. This closes the todo's
stated goal ("the whole CLASS of ... bug at once, not just this
instance") precisely: fix round 1 scoped the check to `_SIMPLE_AST_NODE_
NAMES` (`frozenset(simple_ast.__all__)`) instead, reasoning that was the
todo's entire repro surface and that `INJECTED_RUNTIME_BUILTINS` entries
were a separate exemption -- reviewer round 1 proved this left a gap by
injecting a SYNTHETIC name into `runtime_builtins` and reproducing the
identical `Add` leak on an instance the narrow allowlist could not have
anticipated (a future runtime binding, by construction, is never in
`simple_ast.__all__`). `_SIMPLE_AST_NODE_NAMES` is deleted -- fully
redundant now that the default is distrust-everything-except-the-
allowlist rather than distrust-only-this-allowlist.

Fix round 1 (implementing the general rule the FIRST time, before the
reviewer's ruling) checked the whole dict with NO exemption at all and
broke `clausal/stdlib/kleene.clausal` (a bare `Undefined` reference),
cascading into ~163 unrelated test failures across every file that
transitively loads it -- caught by the Task 8 full-suite gate. That is
exactly what `STRICTNESS_EXEMPT_RUNTIME_NAMES` now exists to prevent: one
explicit, reviewed, documented allowlist entry per genuinely-deliberate
resolve-everywhere name, rather than an ad hoc scope exclusion.

The todo's own repro now raises `strict_atoms: undeclared atom 'Add' ...`;
a module that *declares* the colliding spelling (`-private([Sub])`, e.g.)
still compiles and unifies globally, unchanged. §7.2's open question (a
declared *data functor* colliding with a `simple_ast.__all__` name, e.g.
`-module(m, [Call(x, y)])`) resolves the same way a bare-atom declaration
does: the local declaration always wins, in that module's own namespace
only -- `_process_declarations`'s tuple-entry branch was already binding
data functors through `module_dict` directly rather than the shared pool
(P3-2 Task 2, deliberate), so this shadowing is inherently local and
cannot leak into, or be affected by, any other module.

Tests: `tests/test_strict_atoms_default.py::TestPredicateBuiltinsPoolSplit`
(8 tests -- todo repro, declare-and-unify control, both load orders,
dict-key path, the §7.2 functor-collision answer, an existing
f-string/arith fixture regression check, the reviewer's synthetic-
runtime-name probe (Finding 1), and a self-contained seeding-order pin
(Finding 3: declaring `Mult` as an atom in one module must not break an
unrelated module's own multiplication)). Plus
`tests/test_term_inspection.py::TestGlobalAtom::
test_existing_pre_seeded_returned`, rewritten (Finding 2) to seed the pool
with a value distinct from a fresh mint's output, so "return the existing
entry, don't overwrite it" is actually exercised (verified by temporarily
reintroducing a blind-overwrite bug and confirming the test catches it).
Full suite: failed-name diff against
`.superpowers/sdd/p32-cell-default-flip/baseline-failed-names.txt` is
empty modulo the pre-existing solver-dependency/doc-snippet/C17-perf
ledger and the newly-added test names, on two consecutive runs with
identical failure sets. See
`.superpowers/sdd/p32-cell-default-flip/task-8-report.md` for full
evidence.
