# Engine lane handoff — 2026-09-20 (c): P2 Task 4 sweep reaches **NEW 0**

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**.
Still nothing on main. Main was `bd774c46` at both ends of both gates.

Continues `…-task4.md` (7699f5bb) and `…-task4-b.md` (c2a3769b). Method,
rooms and the `-rfE` trap are in the first of those and are not repeated.

## THE GATE

    base (main bd774c46)   147 failed / 16709 passed / 50 skipped / 37 xfailed
    cand (5ab476f6)        146 failed / 16715 passed / 50 skipped / 40 xfailed

    NEW 0     GONE 1     extracted counts == the summary lines, both arms

Session went **142 → 46 → 0 NEW**, twelve batches, `e0bb5eaf`..`5ab476f6`.
xfail 37→40 is exactly the 3 parked below. **GONE 1 is the same
load-sensitive C17 perf test as the previous handoff** — passes 3/3 in
isolation in BOTH rooms; the base arm ran 268s against the candidate's 159s.

**The head-cells line is gated clean against main for the first time.**
It is NOT therefore finished — see "what this does not mean".

## THE ONE THING THAT NEEDS A RULING BEFORE THIS LANDS

**An aliased/imported `assertz` no longer reaches the owner's row.**
`todo/aliased-assertz-loses-the-owner-under-cells-2026-09-20.md`.

This is the only finding of the whole sweep that changes what a PROGRAM
DOES. `assertz(AliasS(X))` used to hand `assertz` a term INSTANCE, whose
CLASS pointed at the exporter's row. A cell carries the canonical NAME and
no module, so the functor resolves in the CALLING module and the clause
lands on the importer's own row. Measured: owner keeps 1 clause, importer
gains one. The same cause makes mutation-gate channel 4 answer the STATIC
refusal where the OWNERSHIP refusal belongs.

It sits across P1's shared row (`Database._adopted`), the P4-prerequisite
rule that every fielded declaration mints a row, and P2's module locality —
measured, `-import_from` gives the importer a DISTINCT row in both fixtures.
Three options are costed in the todo; engine-lane recommends **(a) adoption
wins**. Two tests are `xfail(strict=True)` against it.

Also parked: `todo/two-copy-diagnostic-after-the-cell-flip-2026-09-20.md` —
P2 removes the route the two-package-copy diagnostic pins (a head is a cell,
and a plain tuple crosses copies fine), so the failure now surfaces in the
pythonic_ast NODE layer with an uninformative message. Recommend (c),
promote the `dollar_ref` warning, which already names the duplicate class.

## THE DEFECTS THIS HALF FOUND (all in commits, all measured first)

* **Two load-time regressions the branch itself introduced**, each
  reproducible in three lines and each loading fine on main:
  a PREDICATE CLASS was narrowing a seam term's arity (`p(-3), p(2)` +
  `--(p(X, 1))`), because Task 3 let `cell_signature_for_name` hand back a
  class's field tuple and a class holds exactly ONE arity; and TERM
  EXPANSION pre-minted NOTHING, because `_collect_functor_arities` had no
  cell arm, so the pre-mint that exists to prevent "not in scope as a term
  class" produced that very error by a new route.
* **`_collect_head_types` had drifted from the walker it is the REFERENCE
  for.** The separate collectors are called nowhere in production; they
  exist so `_collect_globals_info` can be differentially tested. The cell arm
  went into the combined walker in P3-2 and not into this one, and stayed
  invisible until the head flip gave the comparison something to disagree
  about.
* **`vary/3` and `unbound_keys/2` had no cell arm at all** — the two builtins
  the keyword refusal deliberately KEPT. They read field names from the
  DECLARATION now (`-private([point(x, y, z)])`), the same registry
  `signature/3` has always read.
* **`@_db_builtin` could not declare itself db-optional.** The flag is read
  off the object in `_DB_BUILTINS`, which is the wrapper, so a decorated
  factory could never carry it. Now a decorator parameter.
* **`BuiltinPredicate` was not callable in ARGUMENT position — ON MAIN.**
  Still true on `bd774c46` today for every db-dependent builtin. Read this
  before Tasks 5/6 move more builtins into `_DB_BUILTINS`.
* **The benchmarks were measuring the cell's arity, not the workload.**
  Any perf number from this branch before `ad05bc62` is void.

**FOUR TEST INSTRUMENTS HAD STOPPED TESTING WHAT THEY NAME.**
`_python_minted` says it mints "a live term INSTANCE, the way PYTHON
producers mint one" and called `make_predicate` WITHOUT `instances=True`, so
since the constructor flip it returned a cell — every "live instance" test
under it was exercising the cell path twice. Three more of the same shape in
the audit files and the copy-identity file. When a test says *instance*,
check that it still mints one: a plain class constructs a CELL now.

## WHAT THIS DOES NOT MEAN

NEW 0 is "no regressions against main". Task 4's own exit criterion is
UNMET and is the next thing:

    is_term_instance(   79      (in clausal/, outside predicate.py)
    term_field_names(   76

**Unmoved this half, and that is the honest reading, not a stall.** Every
cell arm this session added sits BESIDE an instance arm rather than
replacing it -- phrase, time_goal, vary, unbound_keys, listing,
_collect_head_types, _collect_functor_arities all grew a cell branch while
the instance branch stayed, because instances still arrive from the bridge.
The count falls only when the arms can be DELETED.

Those fall to 0 only once nothing PRODUCES an instance, and the last
producers are the **Task 6** bridge — 16 `instances=True` declarations:
`reflection.py` 9, `clpb.py` 2, `term_expansion.py` 5. `clpb`'s
`BoolEq`/`BoolImpl` are user-facing vocabulary (`-import_from` in corpus and
test `.clausal` source), so that one is not a private refactor. Then Task 5
(17 C `PredicateMeta_type` arms), and those two together are what block step
C of the head flip.

Sequencing note: **R-P2-4 put P2 before L3's rules phases**, so this line is
what unblocks the ISO L3 work, whose later phases get written once against
the tuple AST.
