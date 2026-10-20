# CLP(Q) port vs the SICStus 3.7.1 clp(Q,R) manual: 23 documented answers we do not give (2026-10-15)

Found by tests/clpq_port/test_manual_examples.py (strict xfails), on the .pl surface with CLAUSAL_CLPQ=holzbaur.
The oracle (our local clpq.pl port on Scryer) gives the manual's answer unless noted.

1. **FIXED 2026-10-20 (commit 273e4d58)** the builtin reads a relation cell (and legacy's
   disequality no longer needs both sides bounded); test_entailed and test_not_entailed in
   tests/clpq_port/test_manual_examples.py pass without their xfails.
   **WRONG ANSWER, silent:** `{A=<4}, entailed(A=\=5)` gives `false`, and `entailed(A=<5)` is also false.
   `_entailed__1` matches only the seam's comparison nodes, so a Prolog-term constraint never matches and fails.
   Highest priority. test_not_entailed currently passes only because entailed/1 always fails.
2. `maximize/1` and `minimize/1` are missing (existence_error); only the /2 form exists (DEVIATIONS D20).
3. `dump/3` raises `type_error(callable, <function dump ...>)`: a Python function leaks as a goal.
4. Nonlinear `sin/cos/pow/exp` inside `{}` are refused at load: the .pl front end (iso_l3 _clpq_constraint) lowers only + - * /.
   The port's nonlinear delay exists, so this is a front-end gap. 10 queries plus a dump of a nonlinear store.
5. `ordering/1` is missing (4 queries).
6. `bb_inf/5` (with Vertex and Eps) is missing; only bb_inf/3 is registered.
   flugpl: the oracle gives Inf=1201500 and Vertex=[75,70,70,60,60,0,12,7,16,6,6], exactly as the manual.
7. `call_residue/2` is missing. Scryer has none either; decide whether to add it.
8. `{A<10}, assertz(p(A)), p(X)` loses the constraint; the oracle loses it too. The manual's "Asserting with Constraints" section.
9. Monash go4: the manual's printed residual looks WRONG (z3: not equivalent; two signs flipped).
   The port's cubic matches the program by hand, so this is not a port bug. The as-documented test stays a strict xfail.

Also: pyproject sets `timeout = 10` but pytest-timeout is not installed; on a machine with the plugin the clpq example tests (about 5–25 s each, mostly CLI start-up) would time out.
