# The `-g` printer's CLP(Q) residuals ignore an `ordering/1` that disagrees with the query's variable order

Filed 2026-10-23, from item 5 of
todo/done/clpq-port-vs-sicstus-manual-23-gaps-2026-10-16.md. Severity: low (a
printing difference, raised only for a contradictory ordering).

**Operator ruling 2026-10-23 ("all as recommended"):** keep the printer as it
is now; porting itf3.pl's `project_attributes/2` toplevel hook is a later item.
This file is that item.

## What / Repro

On the port (`CLAUSAL_CLPQ=holzbaur`) the `-g` residual printer
(`holzbaur.residual_q` -> `dump_q(..., toplevel=True)`) projects through
dump.pl's `dump/3` over the goal's variables in the order the goal lists them,
which ordering.pl reads as the chain V1 < V2 < ...:

    ?- ordering(Y < X), {X + Y = 10}.     % the goal lists X before Y
    system_error(unsatisfiable_ordering)  % at print time

The SICStus 3.7.1 manual's toplevel lets `ordering([Mp])` win whatever order
the query names its variables in, because it prints through clp(Q,R) 1.3.3's
toplevel hook, itf3.pl `project_attributes/2`, which projects onto the query
variables without imposing the chain. That hook is not ported
(clausal/logic/clpq/DEVIATIONS.md D14 covers itf3.pl's presentation half;
`projection.project_attributes` is project.pl's, which dump/3 uses).

The manual's own `ordering/1` queries pass with the shown variables listed in
the answer's order (tests/clpq_port/test_manual_examples.py `_ORDERINGS`).

## To do

Port itf3.pl's `project_attributes/2` toplevel hook and have `residual_q`
print through it instead of `dump/3`; then the `_ORDERINGS` queries can list
the query's variables in any order. The default solver (legacy) has no
variable ordering and is unaffected.
