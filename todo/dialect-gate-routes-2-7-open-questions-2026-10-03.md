# Dialect gate (routes 2-7): questions for an operator ruling — 2026-10-03

The run-time half of the one-way rule (`.pl` may call `.clausal`, never the
reverse) is built in `clausal/logic/dialect_edge.py` and pinned in
`tests/test_dialect_gate_routes.py`. These choices were made without a
ruling. Each one is a default that can be reversed with a small edit.

1. **A module with no source file is allowed.** A target `Module` built in
   memory (Python `Module("x")`, a test database, anything without a
   `__file__`) has no dialect. The gate lets a Clausal Prolog caller reach it.
   Rules cannot be asserted into one (`_build_clause` refuses rules), so no
   cut can get in. Should it be refused like a Python module instead?

2. **Python `solve()` is exempt, but `call/N` run under it is not.**
   `solve((":", "legacy", G), module=kit)` runs (route 5: Python is the
   programmer's responsibility). `solve(("call", (":", "legacy", G)),
   module=kit)` is refused, because call/1 is built for `kit`'s database and
   `kit` is Clausal Prolog. The gate sees the frame, not the code that
   started the query. Is that the intended reading?

3. **The chain through `.seam` stays open.** `.clausal` -> `.seam` ->
   `.pl` is allowed: `.seam` is the Python boundary and is not bound by the
   rule. So cut-freedom is transitive only up to the first `.seam` module.
   This follows the ruling as written. Confirm it.

4. **Python-only routes are not gated.** These are a Python callable bound
   in a Clausal Prolog namespace (`_goal_object_dispatch`), a predicate
   class/handle localized by `localize_goal`, and a goal object handed to
   `call/N` directly. Only Python can put a `.pl` predicate there. The one
   defensive check the spec asked for is in `_namespace_dispatch`. Should
   the other three be checked too? Each costs a home-module lookup on its
   path.

5. **The error context for a written `m:p(X)`.** It is the callee's
   indicator `p/1` (Scryer's shape for an unknown procedure). For call/N,
   assert, clause and phrase it is that builtin's indicator. Keep these, or
   always name the builtin?

6. **`abolish/1` takes no `M:` qualification at all.** So there is no
   abolish route to gate. If `abolish(M:N/A)` is ever added, it must go
   through `resolve_qualified_goal_cell` so that it inherits the gate.
