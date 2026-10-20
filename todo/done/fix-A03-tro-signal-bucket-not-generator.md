# fix(A03-F003): signal-mode TRO-only index bucket compiles to a non-generator → TypeError

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F003
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF003TroSignalBucketNotGenerator` (2 xfail — flip to pass)

## Bug

`_build_predicate_trampoline_funcdef` (`predicate.py`) only forces
generator-ness (`return None; yield None`) when the body is EMPTY
(`predicate.py:490-495`). A signal-mode TRO clause's compiled arm contains
no `yield` at all (prefix goals + `_tro_state` stores + early-exit
`return`, `:456-469`; TRO leaf is empty). So an index bucket whose clauses
are ALL signal-mode TRO clauses — typically the default bucket holding the
lone var-headed recursive clause — compiles to a plain function returning
None. First dispatch:

    arg_index.py:900/939  yield from _dflt_fn(*_current)
    TypeError: 'NoneType' object is not iterable

Repro needs ≥4 clauses (index threshold) so it never fires on the in-tree
3-clause `cds` shape; `idx(3, R)` crashes on the FIRST call.

## Fix direction

Force every emitted funcdef to be a generator: after assembling
`all_stmts`, check for the presence of any `Yield` node (or simply always
append the unreachable `return None; yield None` tail used for the empty
case — cheap and uniform). Alternatively have the F3/F4 invariants module
grow an `assert_is_generator_funcdef` check so this class of emitter bug is
caught at compile time rather than dispatch time.

## Acceptance

- `idx(3,R)` → `[("z0",)]`; introspection test (all plan bucket fns are
  generator functions) passes.
- Controls stay green: keyed bucket, `jdx` (bucket with sibling var
  clause), interleaved signal-mode iterators, `wk5` check_indices probes.
