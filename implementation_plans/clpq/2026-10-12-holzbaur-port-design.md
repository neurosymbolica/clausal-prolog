# CLP(Q): a faithful port of Holzbaur's clp(q,r) 1.3.3 — design

Date: 2026-10-12. Status: design, for review. Replaces `clausal/logic/clpq.py`.

## Why

CLP(Q) is now the default arithmetic for exact rational constraints:
currency amounts go through it.  On 2026-10-11 six review rounds
of `clpq.py` kept finding wrong answers.  Most were in the previous round's
patch.  Four structural faults sit under almost all of them:

1. Strict `<` is `=<` plus a disequality, checked with extra LPs.
2. Undo copies the whole store on every change, through a global dict keyed
   by trail.
3. A variable has two identities (`tab_id` and `_id`).
4. Eliminated variables live in two structures (parametric definitions and
   basic rows).

The open todos dated 2026-10-11 under `todo/clpq-*` record what is still
wrong.  This design replaces the solver instead of patching it further.

## Decisions (operator, 2026-10-11/12)

- **Correctness first, speed a close second.**  It must be correct.
- **Port Holzbaur faithfully** rather than design a new solver.  His is the
  most correct CLP(Q) known.  A clean-room rewrite risks getting something
  slightly wrong.
- **Optimise only after the port, and only with a measured justification.**
  Holzbaur spent a year optimising it.
- **Python first, written so that it ports line by line to a CPython
  extension.**  A C or C++ version comes later only if Python gets in the
  way.  No marshal-to-C-and-back design.
- **Solver state lives in the variables' attributes.**  There is no global
  store, and the engine's trail undoes it.
- **Full words for every name**, in the port and in the reading copy of
  the reference.
- **Comment how something works only when a test or a profile shows it.**
  Say which one.
- Licensing: the operator has weighed the risk of porting 1.3.3 and accepts
  it.  The copyright holder cannot be reached.  See Provenance.

## Sources

| Role | Path | Notes |
|---|---|---|
| Port from | `/workspace/sicstus/lib/sicstus-4.10.1/library/clpq/*.pl` | the SICStus distribution's `.pl` files only, all dated 2018-11-08; clp(q,r) 1.3.3, (c) 1992-1995 OFAI, Christian Holzbaur |
| Same files, working copy | `/workspace/claude_sicstus_clpq/clpq/*.pl` | byte-identical to the above (checked 2026-10-12) |
| Oracle (runnable) | Scryer build `/workspace/scryer-prolog-clpq`, via `tests/_oracles.py` | a local mechanical port of 1.3.3 into one `clpq.pl`, not upstream Scryer; its history includes porting fixes |
| Tie-breaker | SICStus 4.10.1 itself | the install here is a macOS x86_64 build and cannot run on this host; disputes go to the operator's machine |
| Excluded | `library/clpq/clpq-algorithm.md`, `library/clpq/.claude/`, and the notes in `/workspace/claude_sicstus_clpq/` (`ANALYSIS.md`, `possible_improvements_from_python_clpq.md`, `scryer_3295_findings.md`) | Claude-written, April 2026, not part of SICStus.  They may mislead and are not port inputs; a claim taken from them counts only once checked against the `.pl` source or a test |
| Example tests | `/workspace/claude_sicstus_clpq/test_examples_clpq.pl` | the SICStus CLP(Q) examples, passing on the Scryer port |
| Acceptance problem | `/workspace/claude_sicstus_clpq/filled_rectangle.pl` | Colmerauer's filled rectangle (nine distinct squares) |

Nothing from SWI-Prolog's `clpqr` (De Koninck's 2006 GPL rework) is used.

## Provenance

- Every ported module keeps the OFAI copyright line and names the 1.3.3
  file it comes from.
- `clausal/logic/clpq/PROVENANCE.md` records the source, the version, the
  operator's decision and its reasons, and that the SWI rework is not used.

## Architecture

### The data model is Holzbaur's

Each constrained variable carries one immutable attribute record.  Every
change is a `put_attr`, so the engine trails it.  The fields are his
attributes, renamed:

| Holzbaur | Field | Meaning |
|---|---|---|
| `lin` | `linear_form` | a dependent variable's solved form over independent variables, plus a constant |
| `type` | `bounds` | the bound type, which includes which bound is active (a capital letter in `t_L`, `t_U`, `t_Lu`, `t_lU` marks the active bound, `bv.pl`), plus the bound values |
| `strictness` | `lower_strict`, `upper_strict` | the strictness bits (0b10 lower, 0b01 upper); separate from the bound type |
| `class` | `component` | the connected component: a hidden attributed variable holding its member and basis lists |
| `order` | `variable_order` | stable order, for deterministic answers |
| `nonzero` | `nonzero` | `=\=` against zero |
| `goals`, `all_nonlin` | `delayed_goals` | non-linear constraints waiting to become linear |
| `forward`, `target`, `keep_indep`, `keep` | full-word names as found | projection and solving bookkeeping |

- Equalities are solved by Gaussian elimination into one solved form.  The
  solved variable becomes dependent and keeps its bounds.  Dependent
  variables are the simplex basis.  There is one structure, not two.
- Inequalities run a simplex with bounded variables (his `bv.pl`, `ineq.pl`).
- `inf`/`sup` pivot to the optimum, read it, and undo back to the starting
  vertex.  `bv.pl` says so: this removes the "garbage … produced by the
  pivots".
- Projection is Fourier–Motzkin plus redundancy elimination (`fourmotz.pl`,
  `redund.pl`).
- Non-linear constraints are delayed until they become linear (`geler.pl`,
  `nf.pl`).  A complete non-linear CLP over Q is out of reach: the existential
  theory of Q is Hilbert's tenth problem over Q, which is open, and the full
  theory is undecidable (J. Robinson, 1949).

### The package

`clausal/logic/clpq/`, one module per 1.3.3 file, every name in full words:

| 1.3.3 file | Module |
|---|---|
| `arith.pl`, `arith_q.pl` | `arithmetic` |
| `store.pl` | `linear_forms` |
| `class.pl` | `components` |
| `nf.pl`, `nfq.pl` | `normal_form` |
| `bv.pl` | `bounded_simplex` |
| `ineq.pl` | `inequalities` |
| `project.pl` | `projection` |
| `fourmotz.pl` | `fourier_motzkin` |
| `redund.pl` | `redundancy` |
| `bb.pl` | `branch_and_bound` |
| `dump.pl` | `residual_constraints` |
| `itf3.pl` | `attribute_hooks` |
| `geler.pl` | `delayed_goals` |
| `ordering.pl` | `variable_ordering` |

- Each function is named after the predicate it ports, in full words (`solve_x`
  becomes `solve_for_variable`).  A comment cites the predicate and its arity.
- `NAMES.md` maps every 1.3.3 name to its new name, so a side-by-side reading
  stays possible.

### Translation rules

- **The C-portable subset.**  Use `__slots__` records, Python `int`, `dict`,
  `list`, and explicit loops.  No `Fraction`, no generators or closures in the
  core, no deep recursion, no dynamic dispatch on hot paths.
- **Rationals** are a small module of plain functions on (numerator,
  denominator) pairs of Python ints.  This is deviation D1.
- **Control.**  Cut and if-then-else become `if`/`else`.  Failure becomes
  `return False`.  An exception means only what a C error return would mean.
- **The solver's own backtracking** becomes an explicit trail mark, attempt
  and undo.  This covers the failure-driven loops in `inf`/`sup` and the
  search in `bb_inf`.
- **Global state.**  The value a loop carries across a backtrack (`bb_put`
  of `inf`, the `bb_inf` incumbent) becomes a local variable.  The printing
  context (`assert` of `presentation_context`) becomes a parameter.  The port
  has no module-level state.
- **Unification hook.**  His `verify_attributes(X, Y, Later)` maps onto the
  engine's post-binding hook, which runs `Later` immediately and in order.
  Every site where his code may assume X is still unbound is listed in
  `DEVIATIONS.md` and gets a targeted test.  This is the riskiest
  translation point.

### Search and stack depth

- **The program's own search** (for example `filled_rectangle` trying
  placements) is ordinary engine search, driven by the trampoline.  Each
  `{...}` post is a deterministic builtin call inside it.  Its attribute
  changes are undone by the trail like any binding.
- **The solver needs no trampoline and no generators.**  Holzbaur's
  predicates are deterministic apart from three patterns:
  - **`inf`/`sup`:** a one-level failure-driven loop.  It becomes mark,
    pivot, read the optimum, undo.
  - **`bb_inf`:** the only real search.  It becomes an explicit loop over a
    work stack of branches, with mark and undo per branch.
  - **Clause selection:** this becomes `if` and `for`.
- **Recursion over linear forms** becomes loops (the "no deep recursion"
  rule).
- **Hook cascades are queued, never nested.**  A binding can force another
  variable, whose binding forces another, and so on.  The hook queues the
  follow-up work (his `Later` goals) and one loop drains the queue: the
  engine's pending-goal channel, or a local worklist.  So stack depth does
  not grow with the store.  This is tested with a long chain of implied
  bindings, thousands of links, beyond Python's default recursion limit.

### Outside the port

- The `{}`/1 and seam set-goal lowering stays as it is.
- The units layer (strip, solve on pure rationals, reattach) stays outside
  the core, as today.  It is sound because division is by constants only, so
  dimensions are checked per constraint before solving.
- The `-g` answer printer calls the port's residual constraints instead of
  today's projection code.
- Public names stay: `{}`, `sup`, `inf`, `maximize`, `minimize`, `bb_inf`,
  `entailed`, `dump`.

## Comments and deviations

- A comment about how something works needs evidence: name the test or the
  profile that shows it.  Without evidence, leave it out.
- `clausal/logic/clpq/DEVIATIONS.md` lists every difference from 1.3.3 with
  its reason.  It starts with D1 (rationals) and the hook mapping.  Each
  later optimisation is a new entry and needs a measurement behind it.

## Testing

The oracle is Scryer's CLP(Q), through `tests/_oracles.py`.  Answers are
compared after normalising residual order and spelling.  A disagreement is a
porting bug unless `DEVIATIONS.md` explains it.  Disputes the Scryer port
might itself have wrong go to SICStus.

| Level | What | Pass condition |
|---|---|---|
| Reading copy | the renamed 1.3.3 copy (step 1 below) | same answers as the original on every test below |
| Module | each ported predicate on small inputs | same as the oracle |
| Examples | the cut-free example predicates of `test_examples_clpq.pl`, read from its path (`tests/clpq_port/test_examples.py`): mg and the Monash mortgage, simplex 1 to 9, eliminat (three examples and two convex hulls), laplace (symbolic 4 x 4, ground 11 x 11), fib, SEND+MORE=MONEY (first answer) and option; the file's driver and its cut-using examples (matmul, root) cannot load in cut-free Clausal | same answers as the oracle, and the values the file documents |
| Fuzz (from 2026-10-11) | LP optima against scipy; strictness and satisfiability against z3; undo with replay; projection (per-variable min and max equal what is projected) | zero mismatches, apart from documented reference errors such as HiGHS presolve |
| Acceptance | `filled_rectangle.pl` | every solution, in the same order as the oracle; run time recorded |
| Depth | a chain of implied bindings and a long linear form, each beyond Python's default recursion limit | no RecursionError; time linear in length |
| Regression | existing `tests/test_clpq*`, `test_dump_q_projection`, `test_units_clp`, CLI tests | pass; an expectation that only the old solver produced is fixed and noted |

The fuzzers live in `tests/` as permanent tests.  They are seeded and sized
to keep the suite fast, with a larger opt-in run.

## Switch-over

Each step is a normal candidate: suite, box gate, A/B, review, downstream GOs.

1. **Reading copy and comparison tool.**  This is test infrastructure,
   not an engine change.  The renamed 1.3.3 copy stays outside the public
   repository: it is a reading aid, and its committed form is the port.
2. **The port, behind a switch**, so both solvers run side by side on the
   same suites and downstream programs.
3. **Flip the default.**  This needs the downstream answer comparison,
   because currency arithmetic goes through it.
4. **Delete `clausal/logic/clpq.py`.**  The 2026-10-11 `todo/clpq-*` items
   are closed by the port, each checked by a test.

Until step 3, the old solver gets wrong-answer fixes only.

## Risks

- **The oracle is a port.**  Scryer's copy had porting bugs of its own.
  Mitigation: the example tests, plus SICStus for disputes.
- **Hook semantics.**  Clausal's hook runs after the binding; Scryer binds,
  undoes, hooks and rebinds; SICStus has its own order.  Mitigation: a site
  list and targeted tests.
- **Speed in Python.**  Holzbaur's code is tuned for a WAM.  Mitigation:
  measure on `filled_rectangle.pl` and real downstream stores before deciding on
  the CPython step.
- **Licensing.**  This is the operator's decision, recorded in
  `PROVENANCE.md`.

## Not in scope

- CLP(R) and floats.
- Non-linear completeness (see the data model above).
- The CPython extension, which waits until the Python port is done and
  profiled.
