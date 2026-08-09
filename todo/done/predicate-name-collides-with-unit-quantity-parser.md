# Predicate name that parses as a unit/quantity crashes at load when self-referenced

Found 2026-07-20 while building repros for
[[tro-signal-flag-clobbered-by-later-match-arms]] (a red herring for that fix,
but a real defect on its own).

## Symptom

A predicate whose name parses as an SI unit / quantity, when that name is
referenced inside a clause BODY (e.g. a self-recursive call), crashes at module
load with:

    TypeError: 'clausal.logic.variables.AttVar' object is not callable

Minimal repro (crashes):

    -module(m, [P(N, X)])
    P(N, X) <- (N > 0, M is N - 1, P(M, X))   # the body ref `P(M, X)` is the trigger
    P(N, X) <- (X is N)

Rename `P` -> `Foo` and it loads and runs fine. The crash is at the module-exec
of the clause whose HEAD is the offending name; the generated code evaluates the
name as a Quantity/AttVar and then tries to call it.

## Which names collide

It is NOT simply "single uppercase letter" and NOT the variable-naming rule
(`Xx`, `Bp`, `Pq`, `Foo` all work as predicates). It tracks the SI-prefix / unit
grammar in `clausal/terms.py` (the `Quantity` constructor — cf. the `Y`=yotta
"SI prefixes cannot be used as units" error seen elsewhere):

    CRASH:  P, PP, Pp, A1, P1        (P=Peta, A=atto/Ampere, digit suffixes, …)
    OK:     Foo, Ab, Xx, Bp, Pq

The exact collision set needs to be read off the unit/prefix tables. A name only
triggers the crash when it appears in a body position that the compiler lowers to
a term-evaluated expression (heads are fine; a name used ONLY as a head, never in
a body, does not crash — e.g. non-recursive `P/1` loads).

## Impact / priority

Low. Real predicate names (multi-letter, non-unit) are unaffected, and the
canonical convention already uses descriptive names. But the error is cryptic —
it gives no hint that the predicate NAME is the problem.

## Fix directions

1. Diagnostic: when compilation of a body call target resolves to a Quantity /
   non-callable, raise a clear error naming the predicate and suggesting a
   rename ("predicate name `P` collides with unit parsing").
2. Or: reserve predicate-name resolution ahead of unit/quantity parsing for
   names that are declared as predicates in the module header.

## FIXED — 2026-07-29

Fixed on `fix/var-shaped-predicate-name`, but **not as reported**. The triage
overturned the diagnosis; the title is now wrong and is kept only so the
original report is findable.

### The premise was false: it is the variable convention, not the unit grammar

The crash reproduces exactly as written. The mechanism does not. Dumping the
transform of the repro shows:

    Call(func=(P := Var()), args=[M, X], ...)

`P` in the body is read as a **logic variable** by `_is_logic_var_name` in
`clausal/templating/term_rewriting.py` — the documented ALL-CAPS / leading-
underscore convention (`X`, `FOO`, `MAX_OF`, `_head`). A clause head's *functor*
position is the one place that rule is not applied, so `P/2` mints a class named
`P` while every other occurrence of `P` is a fresh `Var`. The module-level walrus
`(P := Var())` then overwrites the class binding, and the guarded class block in
`_make_functor_class_ast` deliberately leaves a non-`PredicateMeta` binding
alone (its docstring says so), so the *second* clause head calls the `Var`:

    TypeError: 'clausal.logic.variables.AttVar' object is not callable

The collision set stated in the report is wrong. Probing 19 names:

    CRASH: P PP A1 P1 Y M KG FOO N1 MAX_OF     — exactly `_is_logic_var_name`
    OK:    Pp Foo Ab Xx Bp Pq Km p foo

`Pp` does **not** crash (the report says it does), and `FOO`, `KG`, `MAX_OF`,
`N1` all do — none of which is an SI prefix or unit. There is no unit/prefix
table involved in the load crash.

Where the unit grammar *does* appear is as a downstream symptom of the same
root cause, at arity 1. For

    FOO(X) <- (X is 1)
    q(X)   <- (FOO(X))

the module **loads clean** and the body goal is silently rewritten by the
`VAR(Unit)` quantity sugar into `PyThunk(lambda FOO: Quantity(FOO, X), …)`,
failing only at query time with `cannot build a Quantity from AttVar(_1): SI
prefixes cannot be used as units`. That is almost certainly the message that
led to the unit-parser diagnosis. It is a consequence, not the cause — and this
silent shape is worse than the reported crash, because nothing goes wrong until
a query runs.

### Both proposed remedies were wrong

* Fix direction **2** ("reserve predicate-name resolution ahead of unit/quantity
  parsing") would have broken working programs for no benefit. `VAR(Unit)` is a
  documented, tested feature — `tests/test_units.py::test_var_sugar_constructs_quantity`
  compiles `eval_(N(Metre), D)` and asserts it equals `5(Metre)`. Narrowing the
  quantity parse to favour declared predicate names is exactly the change that
  would kill it, and it would not have fixed the arity-2 crash at all (that path
  never touches the quantity parser).
* Fix direction **1** (a diagnostic) was right in spirit but sited at the crash,
  which is a `TypeError` in exec'd bytecode with no name to hand. The
  information — "this identifier is both a head functor and a logic variable" —
  is fully available statically, in the transformer.

### What was actually done

`EmbedTransformer.visit_Module` now calls a new
`_check_var_shaped_predicate_names`, which raises a `SyntaxError` when a name is
in **both** of

* `_seen_functors` — it is a clause-head functor in this file, and
* `_logic_var_refs` — this file also reads it as a logic variable.

`_logic_var_refs` is a new shared sink alongside the existing `_bare_atom_refs`,
written by `TermTransformer.visit_Name` and by `_build_py_thunk_ast` (the second
is required: the `VAR(Unit)` sugar mints its `Var()`s there and never passes
through `visit_Name`, which is why the arity-1 shape above escapes a
`visit_Name`-only sink).

    SyntaxError: predicate name 'P' is also read as a logic variable in this file
      predicate: m.clausal:1 — -module(m, [P(N, X)])
      read as a variable: m.clausal:2 — P(N, X) <- (N > 0, M is N - 1, P(M, X))
    In Clausal an ALL-CAPS name is a logic variable, so 'P' outside a clause head
    is a fresh Var, never a call to P. That makes P's own clauses unable to refer
    to it and overwrites the module binding, which surfaces later as "'AttVar'
    object is not callable". Rename the predicate to a non-variable name (e.g. Px).

### Why the INTERSECTION, and not "reject var-shaped predicate names"

Rejecting var-shaped head functors outright was the first candidate, and it has
precedent: `-import_from(m, [alias(twice, T)])` is already rejected at the
directive for the same underlying reason (A10-F017, same file). It was rejected
here on measured blast radius. A var-shaped head that is never read as a
variable in its own file **works today**, and the repo leans on it as test
shorthand — ~28 sites across ~10 files (`A(X) <- B(X)`, `K(B) <- …`,
`M(S, G) <- match(…)`, `T(V) <- strip_units(5(m), V)`), plus
`LP(X, Y, OBJ)` in `tests/fixtures/clpq_examples.clausal`, which backs a
`docs/clpq.md` code block and `test_lp_maximize`. Erroring on those is a rename
campaign that fixes no defect. The intersection leaves every one of them alone.

### Blast radius measured

The intersection rule was instrumented to *log* rather than raise, and run over:

* the full test suite (10520 passing tests, every inline `.clausal` snippet) — **0 clashes**
* every `.clausal` file in a downstream rulebase corpus — **0 clashes**
* all 346 `.clausal` files in the repo — **0 clashes**

Also checked directly: the downstream rulebase corpus has **no** ALL-CAPS clause
heads at all, and no ALL-CAPS atoms (the 4196 `PROFILE` / 782 `STATUS` / 144
`EUR` hits are all logic variables, comments or string contents), so a currency
vocabulary spelling `EUR` as an atom would not be affected either.

False-positive risk specifically for quantity expressions: none found. The sugar
requires its subject to be a logic variable; a logic variable that is also a
clause-head functor in the same file does not occur anywhere in the suite or the
corpus. `tests/test_var_shaped_predicate_name.py::TestNotNarrowed` pins
`N(Metre)`, head-only `LP/3`, a var-shaped head calling a lowercase predicate,
and a recursive TitleCase predicate.

### Verification

* `tests/test_var_shaped_predicate_name.py` — 12 tests; the 8 fault tests fail
  before the change and pass after, the 4 `TestNotNarrowed` guards pass both
  before and after (that is the point of them).
* Full suite: `1 failed, 10532 passed, 136 skipped, 44 xfailed` — the one
  failure being the expected `test_doc_snippet_coverage.py::test_no_raw_untested_blocks`.
* The investment-screening domain: load check clean, 46/27/32/18 tests `[PASSED]`, 4/4 negative
  controls load-bearing — run with this worktree on `PYTHONPATH` ahead of
  `/workspace/clausal`, verified via `clausal.logic.compiler_v2.__file__`.

### The cross-module hole, also closed

The intra-file intersection does not see an imported predicate, so the first
draft of this fix left a hole, found by probing it:

    xlib.clausal: -module(xlib, [FOO(X)])   FOO(X) <- (X == 1)
    xuse.clausal: -import_from(xlib, [FOO]) q(X) <- FOO(X)

Both files loaded clean and the query failed with the same
`cannot build a Quantity from AttVar(_1)`. `-import_from` was already rejecting
var-shaped names in the `alias(orig, local)` form (A10-F017, same file, same
reasoning: `visit_Name` consults `_is_logic_var_name` before `_import_remap`, so
the remap never fires) — but *not* in the direct `[FOO]` form. It now does:

    SyntaxError: -import_from name 'FOO' is a logic-variable name; a call to it
    is read as a variable, never as xlib.FOO. Import it under a non-variable
    alias: alias(FOO, Foo)

Unlike a local var-shaped clause head, an imported name exists only to be
called, so there is no head-only usage to preserve — the rejection is
unconditional, matching the existing `alias(…)` behaviour. The suggested repair
is tested end-to-end (`test_the_suggested_alias_repair_actually_works`), so the
message is not offering advice that does not work. Blast radius: **0** var-shaped
direct imports across the suite, the corpus and the repo (measured the same
log-instead-of-raise way).

### Left open (deliberately) — an open question, not a defect

`visit_Name` checks `_is_logic_var_name` *before* both `transformer.atoms` and
`_import_remap`, so a var-shaped name **declared** in a `-module`/`-private`
list is a dead declaration in its own right:

* `-module(m, [FOO(X)])` with `FOO/1` defined but never called in-file — loads,
  is now un-importable, and cannot be called from its own file. A live export
  that nothing can consume.
* `-module(m, [OK])` declaring `OK` as an *atom* — the atom is unreachable for
  the same reason; every `OK` in a body is a fresh variable.

Neither crashes and neither occurs in the suite or the corpus, so nothing was
changed. The open question, with options:

1. **Reject a var-shaped name in a `-module`/`-private` list outright.** Cleanest
   and consistent with what `-import_from` now does. Cost: it is the "reject
   var-shaped predicate names" rule wearing a smaller hat, and it would also
   reject var-shaped *atom* declarations, which is a separate argument (an
   ALL-CAPS atom such as a currency code is a plausible thing to want, even
   though nothing in the corpus spells one that way today).
2. **Leave it.** A dead declaration costs nothing until someone tries to use it,
   and when they do, the intersection check or the import check fires with a
   good message. This is the current state.
3. Reject only the *predicate* form (`FOO(X)`), leaving bare atom declarations
   alone.

Recommendation: **2** until someone actually trips over it. The failure modes
that had no diagnosis now have one, and 1 buys correctness for a shape that has
never been written, at the price of pre-judging the ALL-CAPS-atom question.

Also unchanged, and correct: `FOO(X)` in a body where `FOO` is not a head
functor and not an import is still the `VAR(Unit)` quantity sugar. That is the
sugar working as designed.
