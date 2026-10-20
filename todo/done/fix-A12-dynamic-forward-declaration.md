# fix(A12-F005): `-dynamic(p/N)` with zero clauses doesn't mint the term class — declare-then-assertz broken

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md` A12-F005
**Tests:** `tests/audit_2026_07_05/test_12_seams.py::TestF005DynamicForwardDeclaration` (1 xfail — flip to pass; seeded control already passes)

## Bug

```clausal
-dynamic(ghost/1)

seed <- assertz(ghost("x"))
```

Calling `seed` raises
`NameError: Predicate 'ghost/1' is not in scope as a term class`
(clausal/logic/compiler/globals_env.py:92) — the directive records dynamic
metadata but never creates the predicate class, so the module's OWN clause
bodies cannot construct `ghost(...)` terms. With one seed fact the
identical workflow succeeds. Declaring a dynamic predicate and populating
it entirely at runtime is the standard ISO pattern (and the reason
`-dynamic` exists); requiring a dummy fact contradicts it.

## Fix direction

Make `-dynamic(p/N)` mint the empty predicate/term class at directive
processing (the machinery exists — assertz on an existing dynamic
predicate already extends it), register it in the compiler's globals env
and as a module attribute so both in-module bodies and the Python-side
`m.ghost(X)` / `call("ghost", ...)` APIs see it. Calling it with no
clauses just fails (0 solutions), per ISO dynamic semantics.

Coordinate with fix-A12-directive-target-validation.md: once `-dynamic`
mints the class, the end-of-load dangling-target check must treat
directive-minted predicates as defined.

## Acceptance

- The xfail flips: assertz into a clause-less dynamic predicate succeeds
  and the fact is queryable via `call` and `m.ghost(X)`.
- Querying a declared-but-empty dynamic predicate fails cleanly (0
  solutions), no NameError.
