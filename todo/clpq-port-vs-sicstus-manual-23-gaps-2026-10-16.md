# CLP(Q) port vs the SICStus 3.7.1 clp(Q,R) manual: 23 documented answers we do not give (2026-10-15)

Found by tests/clpq_port/test_manual_examples.py (strict xfails), on the .pl surface with CLAUSAL_CLPQ=holzbaur.
The oracle (our local clpq.pl port on Scryer) gives the manual's answer unless noted.

1. **FIXED 2026-10-20 (commit 55a37b9c)** the builtin reads a relation cell (and legacy's
   disequality no longer needs both sides bounded); test_entailed and test_not_entailed in
   tests/clpq_port/test_manual_examples.py pass without their xfails.
   **WRONG ANSWER, silent:** `{A=<4}, entailed(A=\=5)` gives `false`, and `entailed(A=<5)` is also false.
   `_entailed__1` matches only the seam's comparison nodes, so a Prolog-term constraint never matches and fails.
   Highest priority. test_not_entailed currently passes only because entailed/1 always fails.
2. **FIXED 2026-10-22 (commit 57834f49)** builtins `maximize/1` and `minimize/1` (`maximize(Z, _)`
   with a fresh result), both solvers; test_maximize_1_as_documented passes without its xfail, and
   tests/test_clpq_prolog_surface_builtins.py pins both solvers. D20 did not rule the /1 form out;
   it records the test adaptation only.
   `maximize/1` and `minimize/1` are missing (existence_error); only the /2 form exists (DEVIATIONS D20).
3. **FIXED 2026-10-22 (commit 57834f49)** the builtin `dump/3` (the port's dump.pl dump/3 as terms;
   under the default solver dump_q/2's projection as terms, `legacy.dump`); test_dump_3,
   test_dump_3_with_atoms_for_names and test_dump_3_of_a_nonlinear_store pass without their xfails.
   The leak was `pythonic_ast.nodes.dump` in every module's globals, found before any builtin.
   `dump/3` raises `type_error(callable, <function dump ...>)`: a Python function leaks as a goal.
4. **FIXED 2026-10-22 (commit 05dedc0a)** the front end passes nf.pl's functions through as cells
   (`pow/2` and `exp/2` spelt `^`, which the R9 A1 post boundary admits), and that boundary keeps a
   non-ground evaluable with no node (`cos(X)` under `sin`) instead of refusing it; all ten
   test_nonlinear queries pass without their xfail.
   Nonlinear `sin/cos/pow/exp` inside `{}` are refused at load: the .pl front end (iso_l3 _clpq_constraint) lowers only + - * /.
   The port's nonlinear delay exists, so this is a front-end gap. 10 queries plus a dump of a nonlinear store.
5. **FIXED 2026-10-22 (commit 57834f49)** the builtin `ordering/1` (the port's ordering.pl; the
   default solver accepts the hint without effect, it has no variable ordering); the four
   test_ordering queries pass without their xfail.
   NEEDS RULING (printing): the `-g` residual printer runs dump/3 over the goal's variables in the
   order the goal lists them, which ordering.pl reads as the chain V1 < V2 < ..., so
   `?- ordering(Y < X), {X + Y = 10}.` with the goal listing X before Y raises
   `system_error(unsatisfiable_ordering)` at print time on the port, where the manual's toplevel
   lets `ordering([Mp])` win whatever order the query names its variables in. Options: (a) keep it
   (the chain is dump/3's documented behaviour, and the manual's own queries pass with the
   variables listed in the answer's order); (b) print through 1.3.3's toplevel hook instead, which
   projects onto the query variables without the chain (itf3.pl project_attributes/2, not ported,
   D14). Recommendation: (b), once the hook is ported; until then (a).
   `ordering/1` is missing (4 queries).
6. **FIXED 2026-10-22 (commit 57834f49)** the builtin `bb_inf/5`: the port's bb.pl bb_inf/5 (Vertex
   and Eps); the default solver's bb_inf binds the variables and reads Vertex off them, and reads
   Eps without using it (its integrality test is exact). test_flugpl_bb_inf_5 passes without its
   xfail: Inf=1201500 and the manual's Vertex.
   Found on the way: the default solver's bb_inf/3 fails on the manual's `{X >= Y+Z, Y > 1, Z > 1},
   bb_inf([Y,Z], X, Inf)` (strict bounds; Inf = 4 on the port and in the manual). Not fixed here:
   the legacy solver is unchanged by ruling.
   `bb_inf/5` (with Vertex and Eps) is missing; only bb_inf/3 is registered.
   flugpl: the oracle gives Inf=1201500 and Vertex=[75,70,70,60,60,0,12,7,16,6,6], exactly as the manual.
7. NEEDS RULING. `call_residue/2` is a SICStus 3 builtin of the engine, not of clp(Q,R)
   (`call_residue(Goal, Residue)` runs Goal and collects the residual goals on its variables as
   `[Vars-Goal, ...]`); SICStus 4 replaced it with `call_residue_vars/2`, ISO has neither, and
   Scryer has neither. Options: (a) leave it out (the test stays a strict xfail documenting the
   manual's example); (b) add `call_residue/2` in SICStus 3's shape over every attributed-variable
   residual (CLP(Q), dif, clpz, clpb), an engine builtin; (c) add SICStus 4's `call_residue_vars/2`
   (the variables alone) instead. Recommendation: (a) for the manual's sake, (c) if a residual
   collector is wanted, since it is the form SICStus still ships and SWI has it too.
   `call_residue/2` is missing. Scryer has none either; decide whether to add it.
8. NEEDS RULING (engine-wide, not CLP(Q)'s). ISO's assertz/1 copies the clause; what a copy of an
   attributed variable carries is implementation-defined. SICStus 3.7.1 keeps the constraints
   (the manual's section), Scryer drops them (the oracle), and Clausal drops them for every
   attribute (dif/2, clpz, clpb, CLP(Q)). Options: (a) keep dropping (Scryer, and ISO's letter);
   (b) copy attributes on assert, as copy_term/2 of an attributed variable does in SICStus, for
   every solver; (c) CLP(Q) only, through dump.pl's projecting_assert/1 (ported, D15, unused) as a
   `clpq:assert` hook. Recommendation: (a) unless the behaviour is wanted for all solvers; a CLP(Q)
   special case would be a surprise beside dif/2. The test stays a strict xfail.
   `{A<10}, assertz(p(A)), p(X)` loses the constraint; the oracle loses it too. The manual's "Asserting with Constraints" section.
9. RULED not a bug (2026-10-16, this file): the manual's printed go4 residual is wrong.
   Monash go4: the manual's printed residual looks WRONG (z3: not equivalent; two signs flipped).
   The port's cubic matches the program by hand, so this is not a port bug. The as-documented test stays a strict xfail.

Also: pyproject sets `timeout = 10` but pytest-timeout is not installed; on a machine with the plugin the clpq example tests (about 5–25 s each, mostly CLI start-up) would time out.
