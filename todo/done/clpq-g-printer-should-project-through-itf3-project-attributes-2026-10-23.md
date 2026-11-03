# The `-g` printer's CLP(Q) residuals ignore an `ordering/1` that disagrees with the query's variable order

**Status: FIXED 2026-11-03 (112f0cc1).** `holzbaur.residual_q` projects as
the SICStus toplevel does (`residual_constraints.toplevel_goals`:
project.pl's `project_attributes/2`, then itf3.pl's and geler.pl's
`attribute_goal/2` halves), not through dump/3; DEVIATIONS.md D26.
Pinned by tests/clpq_port/test_toplevel_projection.py
(`test_an_ordering_against_the_target_order_prints`,
`test_the_g_printer_on_an_ordering_against_the_query_order`,
`test_every_variable_order_prints_the_oracle_s_solution_set`) and
tests/clpq_port/test_manual_examples.py
`test_ordering_in_any_variable_order`.  Note on the title: the toplevel
hook `project_attributes/2` is project.pl's, not itf3.pl's; itf3.pl
supplies `attribute_goal/2`.  Left as it is: the manual's
`ordering(B < Mp), mg(...), ordering(P < Mp)` leaves B and P unordered,
and which one is defined follows the standard order of the two variables
(creation order on the port, D4), so it is the manual's P only where P is
created first (D26).

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
