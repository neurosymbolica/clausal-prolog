# A bare /0 predicate name as a clause-body goal does not compile

**Found:** 2026-09-06 during P3-3 Task 5b (import-edge (name, arity) resolution),
while trying to pin "bare `k` as a body goal from an importer runs the owner's
/0 predicate".

**Repro** (single file, no import involved):

```
-module(m, [k, go])
k,
go <- k,
```

Loading fails in `terms_to_goalop`: `goal shape not yet supported (str)`. The
same happens for a local /0 predicate called bare in its own file, so this is
a general compiler gap, not an import-edge bug. `call(k)` works (Task 5 resolves
a bare-str atom goal in call/N via the db row + namespace fallback), and `k()`
with explicit parens works.

**Why it matters.** ISO Prolog: `k` in a body is an ordinary /0 goal. The
Task 5b pin for the import edge had to fall back to `call(kfact)`; the
bare-goal form remains unpinnable until this lands.

**Suggested home.** P3-3 Task 6 (qualified goals) or the ISO phase — the
lowering site is the same `_term_to_goal` / `terms_to_goalop` seam that Task 6
touches for `(":", M, G)`. Fix: a bare `str` body goal whose name has a /0 row
(local or via the module's dispatch/namespace) lowers to `AstCall(LoadName(k), ())`,
exactly as the cell `("k",)` does since Task 5; a bare str with no /0 row keeps
the compile-time refusal.

## Closed 2026-09-30 (stale)

No longer reproduces on f01790d2: `-module(m, [k, go]) k, go <- k,` loads and
`go` succeeds once (the bare /0 body goal compiles).
