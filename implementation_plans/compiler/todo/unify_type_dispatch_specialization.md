# Specialize unify / structural_eq type dispatch

## Context

Unification is one of the hottest operations in the engine — called on
every head match, every `==`, every bidirectional wrapper. The
current implementation runs a chain of `isinstance` / `PyList_Check`
checks to pick the right branch for each operand type.

Counts as of 2026-04-23:

- `clausal/logic/variables/_variables.c`, `do_unify` — 24 C-level
  type checks (`PyList_Check`, `PyTuple_Check`, `PyUnicode_Check`,
  plus the `__unify__` protocol call)
- `clausal/logic/constraints.py`, `structural_eq` — 24 Python-level
  `isinstance` checks covering Var, scalar types, list, tuple,
  Compound, SegList, SegString, DictTerm, SetTerm, dict, set,
  frozenset, user-defined term dataclasses
- `clausal/terms.py` — 126 `isinstance` occurrences across term
  classes (most aren't in the unify hot path, but `__eq__` and
  `__unify__` hooks are)

The recent symmetric-equality fix for DictTerm↔dict and
SetTerm↔set/frozenset (commit `d13fcc4`) added one more isinstance
branch to each of those call sites. Not a problem in isolation, but
motivates cleaning up the pattern before more types follow.

## Why this costs

Each `isinstance` check is a `PyObject_TypeCheck` — cheap individually
(a C-level type-MRO walk, typically short) but the *chain* means every
unify call pays O(n) checks for n supported types, even for the
common-case types (Var, int, list).

The `__unify__` protocol hook in `do_unify` adds two `getattr` calls
on the fast path (`PyObject_GetAttrString(t1, "__unify__")` and again
symmetrically on t2) — one per unify, which dominates the isinstance
cost in microbenchmarks.

## Specialization options

### A — Type-table double dispatch at runtime

Build a dispatch table keyed on `(type(a), type(b)) → handler`. Looks
up in one step instead of walking an isinstance chain.

```python
_UNIFY_TABLE = {
    (int, int): _unify_scalars,
    (list, list): _unify_list_list,
    (DictTerm, DictTerm): _unify_dict_dict,
    (DictTerm, dict): _unify_dict_plain,
    ...
}
```

Uses concrete types, not MRO — so subclasses miss unless registered.
For Clausal's closed set of term types this is fine; the corner case
is user-defined dataclass terms, which already have their own
`is_term_instance` gate.

**Cost.** Dict lookup vs isinstance chain — wins when there are
enough types that the chain is long, loses for 2–3 types. Current
chain is ~12 types, so probably a small win.

**Where.** Could be a Python-level dispatch (replaces `structural_eq`
chain) or a C-level one (replaces `do_unify` chain — uses a
`PyTypeObject* → handler` table lookup).

### B — Compile-time specialization via AST transformer

When the compiler knows the static type of one or both unify operands
(via IR type inference or from the source literal), it can emit a
specialized call that skips dispatch entirely.

Example: `TREE is {"a": 1}` has the RHS as a known `DictTerm`
literal — the compiler could emit `unify_with_dictterm(lhs, lit,
trail)` directly, one type check instead of twelve.

Same for `X == [1, 2, 3]` — LHS is a Var, RHS is a list-typed literal
→ compiler emits the list-case directly.

**Benefit.** Entirely elides the dispatch for literal-heavy code
paths. Many fixtures and performance-sensitive user code fall in
this bucket.

**Cost.** Requires type info in the IR. Some of this already exists
(literal types are known at parse time); extending to bound-var
inference is more work.

**Overlap.** `destructive_reuse_optimization.md` and
`runtime_arg_key_fast_path.md` are adjacent — they also specialize
based on static type info at call sites.

### C — Rewrite `__unify__` protocol to avoid double getattr

The C hot path does two `PyObject_GetAttrString(t1, "__unify__")`
calls per unify even when both sides are plain types. A single
`PyType_Check` on each for "known protocol types" (DictTerm, SetTerm,
SegList, SegString) would cut both getattrs when neither is a custom
term.

```c
if (is_protocol_type(t1) || is_protocol_type(t2)) {
    /* existing __unify__ dispatch */
} else {
    /* skip straight to list/tuple/== fallback */
}
```

`is_protocol_type` can be a `PyTypeObject*` comparison against a
small set of cached types — single-digit-nanosecond check.

**This is the highest-ROI item** in the list. The `__unify__`
dispatch accounts for the lion's share of non-Var unify overhead on
plain types per profiles of the JAX/torch fixture suites.

## Suggested order

1. Option C — cheap, localised, big win on hot paths.
2. Option B — compiler changes, medium effort, affects code that
   already benefits from type inference.
3. Option A — least justified unless the isinstance chain grows (new
   term types) or Option C is insufficient.

## How to measure

- `benchmarks/` has a unify microbenchmark harness (grep for
  `bench_unify`). Use it before/after each option.
- Profile a representative fixture (e.g.
  `tests/fixtures/jax_tree_tests.clausal`) via `cProfile` or
  `scalene` and look at `do_unify` / `structural_eq` self-time.
- Real-world: run the full `test_jax_infra.py` suite and compare
  wall-clock. Unify is called millions of times across the 615
  tests.

## Related

- `C_predicate_helpers.md` — similar "move dispatch to C" theme.
- `C_type_checks_and_inspection.md` — moves isinstance-chain type
  predicates (`ground/1`, `var/1`, etc.) to C.
- `runtime_arg_key_fast_path.md` — compile-time arg specialization
  for call-site dispatch.
- `destructive_reuse_optimization.md` — another IR-level
  specialization that depends on type info.

## Cross-references

- `clausal/logic/variables/_variables.c:1100–1232` — `do_unify` type
  dispatch
- `clausal/logic/constraints.py:36–132` — `structural_eq` chain
- `clausal/terms.py` — `__unify__` / `__eq__` protocol
  implementations per term type
