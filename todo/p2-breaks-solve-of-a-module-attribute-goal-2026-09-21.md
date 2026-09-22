# P2 breaks `solve(m.pred(X))` — every downstream caller, and the API contract

**Status:** **OPEN, BLOCKING the P2 line.** Found 2026-09-21 by
the downstream downstream lane running the downstream answer-set answer-set checks against tip `3d17fdf8`.
Reproduced engine-side here. **The branch is held.**

## What happens

every downstream domain tried score normally on `bd774c46` and produce NO SCORE on
`3d17fdf8` — four different families, so it is the calling convention, not a
domain quirk.

    bd774c46 (base)   domain A   341/341
    3d17fdf8 (P2)     domain A   (none)   — reproduced twice, alone
                      domain B             (none)
                      domain C             (none)
                      domain D             (none)
                      domain E             (none)

The engine's own diagnostic names it, from `_module_for_moduleless_solve`
(`clausal/logic/solve.py:862`):

> `solve/1: the unqualified cell goal decide_domain_a/2 has no
> calling module — pass module= (the module whose database answers), or
> qualify the goal as (':', M, Goal).  A cell names a predicate but carries no
> module of its own, so there is nothing here to infer one from`

## The mechanism, reproduced minimally on both arms

    mod = _load_module("…gate_dyn_owner", "tests/fixtures/gate_dyn_owner.clausal")
    solve(mod.gd_p(1))

    mainnow (bd774c46)   mod.gd_p(1) -> gd_p(arg_0=1)   solve -> 1 solution
    kwwt    (3d17fdf8)   mod.gd_p(1) -> ('gd_p', 1)     solve -> LogicException

`mod.gd_p` is still the `PredicateMeta` (P2 keeps the class as the predicate
handle until P4), but calling it now builds a CELL, and a cell carries no
module. Previously the INSTANCE's class knew its own module and `_infer_module`
walked back to it.

**This does not move an ANSWER. It removes the ability to ASK**, uniformly, at
the Python API. That is why the in-repo suite is NEW 0 / GONE 0 and all 12
packages are NEW 0 / GONE 0: nothing in-repo calls a rulebase through a module
attribute the way the downstream bodies do.

**`docs/terms-are-tuples.md` currently claims "`m.pred(X)` still works."**
That line is the defect in the announcement: `m.pred(X)` still BUILDS a term,
but it is no longer a self-describing GOAL.

## Measured, so the cost is not guessed

* **218** `solve(X.pred(…))` call sites in the downstream corpus:
  **181 in 73 `<downstream body>`** files, 25 in `<downstream body>`,
  7 + 3 in other downstream bodies, 1 in a `kernel.clausal`.
  (A `.py`-only census finds 5 of these. `.seam` is where they live.)
* The module variable is bound the SAME way everywhere:
  `module = loader.get()`, `_RULE = the loader(RULEBASE, …)` from
  **`auto/<the shared downstream checks downstream helper library>` — GATE_CORE** (editing it requires syncing the
  two downstream forks).
* 41 distinct attribute names are read off that variable in the downstream
  downstream checks, plus 2 `getattr(m, …)` sites, plus it is passed whole to
  `a strict getattr helper(m, …)` / `another helper(…)`.
* **The qualified form works on BOTH engines** — measured:
  `solve((':', mod, ('gd_p', 1)))` answers 1 solution on `bd774c46` AND on
  `3d17fdf8`. So a downstream checks-side fix can be dual-engine, which is the
  `_DATES_ARE_TERMS` policy `<the shared downstream checks downstream helper library>` already states in its own words:
  *"a downstream checks has to run on BOTH while the representation change is on an
  unpromoted branch — otherwise migrating the downstream checks takes the measurement
  axis dark exactly when it is needed to measure the landing."*

## THE QUESTION FOR THE OPERATOR

**Is `solve(m.pred(X))` — a bare module-attribute goal, with no `module=` —
part of the supported Python surface after P2?**

It is not an oversight either way: "a term carries no module" is P2's spine,
and "a goal that is just a tuple cannot name its module" is a CONSEQUENCE of
it, not a bug in the implementation.

### If YES — the engine carries it

* **(A) A carrier on the goal.** `PredicateMeta.__call__` returns something
  that keeps the owner. A `tuple` subclass would keep `isinstance`, indexing,
  unpacking, equality and hashing — but it contradicts "a cell IS the
  functor-first tuple", costs a slot on every term, and DIES AT P4 when the
  class goes. Qualifying every constructed term is wrong outright: data terms
  are not goals.
* **(B) Resolve at the moduleless `solve` boundary only.** Look the bare
  cell's `(functor, arity)` up across loaded modules; answer when exactly one
  defines it, keep today's error when none or several do. One place, no term
  change, and it REFUSES rather than guesses on ambiguity — but the P3-3
  Task 6 docstring calls precisely this "the module-locality bug this task
  exists to prevent", so adopting it is overriding a deliberate rule.

### If NO — the doc is amended and callers qualify

* **(C) One downstream checks file.** `the loader.get()` hands back a proxy whose
  attribute access builds `(':', module, cell)`. **Zero downstream-body edits**,
  dual-engine safe. Cost: a GATE_CORE edit, two fork syncs, and the proxy has
  to be faithful to the 41 attribute names, the 2 `getattr` sites and the
  whole-object uses.
* **(D) 218 sites across ~79 downstream bodies.** The expensive direction, and
  every one needs a §6 answer-preservation run afterwards.

**Note that (C) fixes THIS corpus and leaves the regression live for every
other Python caller** — packages/, the a downstream fork and tda forks,
out-of-tree consumers. If the answer is NO, `docs/terms-are-tuples.md` needs
the migration note in the same commit, because that file is what downstream
reads.

Engine-lane does not recommend one: (B) overrides a stated design rule and (C)
edits the instrument, and which of those is acceptable is the operator's call.

---

## 2026-09-21 — THE OPERATOR POINTED AT THE SEAM. Measured, both engines.

The operator's reading: these calls should be rewritten by the COMPILER to
insert the current module — the `--goal(…)` seam — and the question is which
Python positions it covers (`if`, `for`, `while`, statement, comprehension).

**He is right about the mechanism and right that the comprehension form is
missing. He is wrong about this fixing the downstream checks, for one reason nobody
had written down: the seam's module is the HOST module, resolved at COMPILE
time, and the downstream downstream checks address a rulebase loaded at RUNTIME.**

### Measured — the five positions, `mainnow bd774c46` vs `kwwt 3d17fdf8`

A `.seam` body importing a predicate statically (`-import_from`):

    position                        mainnow          kwwt
    statement   `--sp(1)`           ok               ok
    if          `if --sp(2):`       ok-true          ok-true
    for         `for X in --sp(X)`  ok [1, 2, 3]     ok [1, 2, 3]
    while       `while --sp(1)`     ok               ok
    for, 2 vars `for K, V in --pair(K, V)`
                                    ok [(a,1),(b,2)] ok [(a,1),(b,2)]

**IDENTICAL on both engines. The seam is P2-proof** — it is not affected by
the representation change at all, which is exactly why it is the right
surface.

### Measured — the comprehension form is NOT supported, on EITHER engine

    d2 = {K: V for K, V in --pair(K, V)}
    SyntaxError: assignment expression cannot be used in a comprehension
                 iterable expression (line 48)

Same failure on `bd774c46` and on `3d17fdf8`, so it is a PRE-EXISTING GAP and
not a P2 regression. `EmbedTransformer` has `visit_If`, `visit_For`,
`visit_While` and `visit_Expr` and no comprehension visitor
(`GeneratorExp`/`ListComp`/`DictComp`/`SetComp`). The operator asked for this
form; it needs building either way.

### Measured — THE REASON THE SEAM DOES NOT COVER THE DOWNSTREAM CHECKS

    m = _load_module("rb_under_test", path)     # the downstream lane's own shape
    for X in --m.sp(X): ...

    mainnow   NameError: name 'm.sp' is not defined
    kwwt      NameError: name 'm.sp' is not defined

    solve(m.sp(X))    mainnow: ok, 3 solutions    kwwt: LogicException

The seam resolves a goal's name at compile time against the host module's
rules. `m` is a Python variable holding a module object loaded at runtime, so
`m.sp` names nothing the compiler can see. **The downstream downstream checks are built
around exactly that** — `module = loader.get()`, with `fresh_per_case` reloading
the rulebase per case for the domains that need isolation. No static import can
express it.

## THE OPTION THE MEASUREMENTS ADD

* **(E) Teach the seam the DOTTED RUNTIME MODULE form.** `--m.pred(A, B)` in
  goal position lowers to the qualified goal against the runtime module `m` —
  i.e. `(':', m, ('pred', A, B))`, the form that ALREADY WORKS ON BOTH ENGINES
  (measured: `solve((':', mod, ('gd_p', 1)))` answers on `bd774c46` and on
  `3d17fdf8`). This is the operator's "the compiler inserts the module", with
  the module taken from the Python expression rather than from the host file.
  It puts NO module into a term: the qualified goal is a goal, not a data term.
  One place, in `EmbedTransformer`.

  **Sequencing matters and it is what makes this safe:** (E) is independent of
  P2 and works on main. Land the seam form on MAIN first, migrate the downstream
  bodies on MAIN, prove zero drift there with the instrument still live, and
  only then retest P2. That is the `_DATES_ARE_TERMS` policy followed exactly,
  and it never takes the measurement axis dark. The body migration is still
  ~218 sites, but onto the INTENDED surface, and each step is verifiable
  against a green baseline.

  It also retires the proxy idea (C) and its real risk, which
  the downstream downstream lane measured: the module object is passed WHOLE to
  `a strict getattr helper`, `another helper`, `_gold`, `_build_profile`, `_show`,
  `_answer`, `_atom`, `_profile_to_term`, `_profile`, plus 72 `getattr(m, …)`
  sites across 22 files and 168 distinct predicate attribute names — and
  `a strict getattr helper` does `getattr(module, value)` and RAISES on a miss BY DESIGN,
  which two domains depend on.

## Scope note on the call-site count

the downstream downstream lane re-derived it and the number depends on its definition:

    112  in 37 files   goal LEXICALLY inside solve/once/call(…)   — a FLOOR
    218  in ~79 files  calls that become goals (engine-lane)
    340  in 84 files   every `mod.attr(…)` on a the loader-bound name — a CEILING
                       (259 .seam, 81 .py)

The floor misses a goal built into a variable and passed to `solve` a line
later; the ceiling counts data-functor construction and helper predicates that
are never solved. Quote the definition with the number.

---

## 2026-09-21 (later) — THE COMPREHENSION GAP, and why it is SMALLER than it looks

the downstream downstream lane raised the comprehension restriction as a collision that
halves the value of the seam route. The restriction is real and I reproduced
it. **The conclusion does not follow, and the reason is in the lowering.**

### The Python restriction, verified

                                   ast.parse   compile()
    [x for x in (y := f())]        OK          SyntaxError: assignment
                                               expression cannot be used in a
                                               comprehension iterable expression
    [x for x in ys if (y := x)]    OK          OK
    [(y := x) for x in ys]         OK          OK
    {k: v for k, v in (p := g())}  OK          SyntaxError (same)

Iterable position only; condition and element are fine. **`ast.parse` cannot
see it** — it is enforced in the symbol-table pass, so only `compile()` raises.
(the downstream downstream lane measured this independently on 2026-09-09 as their defect
class 6; two of their tools validated generated bodies with `ast.parse` and
were blind to it. The gap is STABLE, not something P2 disturbed.)

### BUT THE SEAM'S `for` LOWERING USES NO WALRUS AT ALL

Dumped from `EmbedTransformer` on the branch:

    # for X in --sp(X):
    $v_X = $Var()                                   <-- HOISTED STATEMENT
    for X in $each($Call(...sp..., args=[$v_X]), ($v_X,), globals()):

    # statement  --sp(1)        ->  $seam($Call(...), globals())
    # if         if --sp(2):    ->  $once_bind($Call(...), globals())
    # while      while --sp(1): ->  $seam($Call(...), globals())

Every one of those is an ordinary CALL. The walrus appears ONLY when a seam
falls through to the GENERIC EXPRESSION lowering, which has nowhere to hoist to
and so introduces the logic vars inline:

    # {K: V for K, V in --pair(K, V)}   -- no comprehension visitor exists
    {K: V for K, V in $seam(((K := $Var()), (V := $Var()), $Call(...))[-1], globals())}
                                ^^^^^^^^^^^^^^^^^^^^^^^^^  the illegal part

**So the blocker is not "a seam is an assignment expression". It is "there is
no comprehension visitor, so the seam takes the generic path."** A comprehension
visitor does what `visit_For` already does — hoist the `$Var()` bindings to the
enclosing statement and emit `$each(...)` in the iterable — and the iterable
becomes a plain call, which Python allows.

### And the hard case DOES NOT OCCUR

A hoist is only sound for the OUTERMOST `for` clause: that iterable is
evaluated in the enclosing scope, while a later clause is re-evaluated per
outer iteration and would need fresh vars each time.

Censused over the downstream bodies — 161 files, **all 161 parsed**, no rubble:

    goal calls (solve/once/call) total        264   in 85 files
      in a COMPREHENSION ITERABLE             119   in 45 files   (45%)
         OUTERMOST for-clause                 119
         a LATER for-clause                     0

**All 119 are outermost. Zero inner-clause sites.** So a visitor that handles
only the outermost iterable — the case the existing hoist already fits —
covers 119 of 119 real sites, and the inner-clause complication can be
REFUSED with a diagnostic rather than built.

(the downstream downstream lane counted 110 of 230 = 47%; mine is 119 of 264 = 45%. The
gap is scope — which files count as a body — not disagreement. Quote the
definition with the number.)

### Net effect on the route

The comprehension visitor is not an obstacle that halves the seam route's
value; it is a prerequisite that reuses machinery already present, sized by a
census in which the hard case is empty. It also delivers the form the operator
asked for in its own right.

### Sequencing, unchanged and still the point

(E) and the comprehension visitor are both independent of P2 and work on main.
Land them on MAIN, migrate the downstream bodies on MAIN, prove zero drift there
with the instrument live, then retest P2. Per the downstream downstream lane: the census
guard and `<the migration tool>` must learn the dotted form in the same window,
or body 83 is written the old way — fix-then-arm, not arm-then-fix.
