# The `-table` × `-specialize` refusal is probably over-broad after P3-3 Task 7

**Filed:** 2026-09-06 at P3-3 Task 7 (specialization stops minting), report §7.1.

**Before Task 7** a `-specialize`d predicate lived in a private, free-floating
`Database` of its own, so a `-table` directive naming the same alias could not
reach the dispatch the specializer installed; `compiler_v2` refused the
combination with a "private database" reason.

**After Task 7** `_install_specialized` writes the specialized clauses and
dispatch into a ROW of the defining module's own `Database` (through
`Database.mutate`, author `specialize:<load author>`), and the dispatch goes
through `_install` → `ensure_tabled_wrapper` on that db like any other
predicate. So a tabled alias would very likely just work. Task 7 kept the
refusal (reworded the reason; comment names this follow-up) rather than lift
it on an unmeasured guess.

**To close.**
1. Fixture: a module that `-specialize`s an MI pattern to `alias/N` AND
   `-table`s `alias/N`, with a query whose answer set differs between tabled
   and untabled evaluation (a left-recursive or cyclic object program).
2. Verify the ORDER: step 6a (tabling wrap) vs step 6b (specialization install
   + recompile). If 6b recompiles the dispatch after 6a wrapped it, the wrapper
   is lost — either reorder, or have `_install_specialized` call
   `ensure_tabled_wrapper` itself.
3. Assert via table introspection (`db.table_store`, as
   `tests/test_qualified_goals.py::TestQualifiedTabling` does) that the table
   lands in the module's own db.
4. Lift the refusal only when 1–3 pass; otherwise keep it and fix the reason
   text to the real obstacle.

Cost of leaving it: a program that wants a tabled specialized alias must table
the object predicate instead (works today).
