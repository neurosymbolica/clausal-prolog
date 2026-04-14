"""Compiler optimisations as independent passes over the GoalOp IR.

Each submodule here is a single optimisation with a clear
before/after contract: ``analyse(ir, ...) -> Plan`` is pure
analysis, ``apply(ir, plan) -> ir`` rewrites the tree with the
plan's decisions baked in as hints (on :class:`SubCall` today —
:attr:`~clausal.logic.compiler.ir.SubCall.tail_recursive`,
:attr:`~clausal.logic.compiler.ir.SubCall.destructive_reuse`,
:attr:`~clausal.logic.compiler.ir.SubCall.direct_bucket_ref`).

Slice E migrates the D6 shadow analyses into this shape one pass
at a time.  Today the legacy analyses remain the source-of-truth
for code-generation; the optimisations module establishes the
architecture the D7c-post pipeline will use.

Passes:

- :mod:`.destructive_reuse` — dead-source container reuse
- :mod:`.tro` — tail recursion (pending E2)
- :mod:`.call_site` — bucket-ref specialisation (pending E3)

Indexing (V2-1 / V2-2 / joint / secondary) stays in
:mod:`~clausal.logic.compiler.arg_index` because it runs pre-IR
on the clause list, not over GoalOp trees — see the migration
plan §7.
"""
