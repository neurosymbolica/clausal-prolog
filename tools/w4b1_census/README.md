# W4b-1 completeness census

`field_names_for` (`clausal/logic/predicate.py`) has four arms. Arm 2
answers off the `PredicateMeta` CLASS and will keep answering, unchanged,
right up to the moment `PredicateMeta` is deleted at W4b-3. A green test
suite proves nothing about arm 3 (the NAME path) in the meantime — the
suite is equally green whether arm 3 is correct or completely broken,
because arm 2 answers every call first. This plugin is the actual gate: it
shadows every arm-2 call with what arm 3 *would* have answered for the same
name, and reports whether the two agree.

## Running it

Positive control (must be run and its output inspected before trusting any
other run):

```bash
./venv/bin/python -m pytest tests/test_w4b1_census_positive_control.py \
    -q -p no:cacheprovider -p tools.w4b1_census.plugin
```

Full census over the house suite:

```bash
./venv/bin/python -m pytest tests -q -rfE -p no:cacheprovider \
    --continue-on-collection-errors --ignore=tests/test_clportools.py \
    -p tools.w4b1_census.plugin > census.txt 2>&1
tail -60 census.txt
```

Both commands run from the repo root, with `./venv/bin/python`.

## Reading the report

* `N` — total `field_names_for` calls in the session. **`N == 0` is a
  REFUSAL, not a pass**: it means the plugin never loaded or nothing under
  test reached the accessor. Every other line is meaningless if this is 0.
* The four arm counts, each with `N` as its denominator.
* The shadow table — `agreed` / `DISAGREED` / `could not answer` — with the
  arm-2 count as ITS denominator (a different, smaller population than
  `N`). `agreed` means arm 3, asked for the class's own name, returned the
  exact same tuple arm 2 (`cls._fields`) did. `DISAGREED` lists the functor
  and both tuples — each one is a candidate defect, never a fallback to
  widen arm 3 around. `could not answer` (residue) lists every functor by
  name where arm 3 returned `None` while arm 2 answered something.

## Fail conditions

1. `N == 0`.
2. `DISAGREED` non-zero, for a functor NOT accounted for by the positive
   control test itself.
3. A residue name not explained. **The residue is not one story — it is at
   least three genuinely distinct mechanisms, confirmed by direct
   measurement, not by an assumption that unbound-row implies absence.**
   See "Reading the residue" below.

**There are zero production call sites of arm 3 (the NAME path) today.**
`compiler_v2.py`'s directive-target validation (`term_field_names_of_class(cls)`
at lines 1056/1095) is a real, executed call site — but it always passes a
CLASS, so it only ever exercises arm 2. It is not an arm-3 caller and does
not "already agree" with anything. All 41 arm-3 calls measured in this run
come from three test files: `tests/test_field_names_for.py`,
`tests/test_declaration_registration.py`, and
`tests/test_w4b1_census_positive_control.py`. Arm 3 has no production
readers to protect yet — which is a materially different claim from "arm 3
already has production callers that agree with arm 2," and is the claim
this document makes.

## The positive control

`tests/test_w4b1_census_positive_control.py` mints a class
(`PlantedDisagreement`, fields `x, y`) via `make_predicate`, then
DELIBERATELY registers the wrong signature (`WRONG, ALSO_WRONG`) for the
same name/arity in its own database. Arm 2 (the class) must answer the true
fields; arm 3 (the name) must answer the planted wrong ones. The census
must show exactly this pair in its `DISAGREEMENTS` section, or the
instrument itself is broken.

### F1 — the bug the brief's own draft code had

The brief's first draft of `_shadow_arm3` did
`from clausal.logic.predicate import field_names_for` INSIDE the shadow
function. But `pytest_configure` has already replaced
`predmod.field_names_for` with the counting wrapper for the whole session
by the time any test runs — so that import fetches the PATCHED name, and
the shadow's own call re-enters the counter. Every arm-2 call then silently
added a spurious arm-3 call to both `N` and `arm3_name`, corrupting the
exact numbers this census exists to report.

**Fix, in `plugin.py`:** `_shadow_arm3` takes the pre-patch `original`
function as an explicit parameter (closed over from `pytest_configure`'s
local variable) and calls that — it never imports `field_names_for` by
name. This is commented in the source directly above the function, because
it is a trap the next reader would otherwise reintroduce silently: the code
still type-checks, still looks correct, and the suite still passes.
Confirmed by running the positive control: `N` came back as exactly `2`
(the two calls the test itself makes), not `3` — proof the shadow read
does not recurse into the counter.

## Numbers actually measured, 2026-09-22

These are RE-DERIVED from a real run on this room's checkout (branch
`feat/w4b1-term-shape-2026-09-22`), not carried over from a prior task or
guessed. Re-run the command above if you need to check them again — do not
trust this file over a fresh run.

Positive control alone:

```
N (total field_names_for calls)          2
  arm 1  @dataclass class                      0  (0.0% of 2)
  arm 2  PredicateMeta class                   1  (50.0% of 2)
  arm 3  a NAME                                1  (50.0% of 2)
  arm 4  not term-shaped                       0  (0.0% of 2)

SHADOW READ, over the 1 arm-2 answers (the denominator):
  agreed                                       0  (0.0% of 1)
  DISAGREED                                    1  (100.0% of 1)
  could not answer                             0  (0.0% of 1)

DISAGREEMENTS (each is a defect, not a fallback):
  PlantedDisagreement: arm2=('x', 'y') arm3=('WRONG', 'ALSO_WRONG')
```

Full house suite (`tests -q -rfE -p no:cacheprovider
--continue-on-collection-errors --ignore=tests/test_clportools.py`, 16798
passed / 147 failed / 50 skipped / 38 xfailed — the 147 failures are
pre-existing, unrelated infra gaps: `test_clpsat.py`/`test_clportools_lp.py`
`ImportError`s, missing `ortools`/`pysat`/SCIP backends, etc.; none touch
`field_names_for` or `PredicateMeta`):

```
N (total field_names_for calls)          689
  arm 1  @dataclass class                      6  (0.9% of 689)
  arm 2  PredicateMeta class                 240  (34.8% of 689)
  arm 3  a NAME                               41  (6.0% of 689)
  arm 4  not term-shaped                     402  (58.3% of 689)

SHADOW READ, over the 240 arm-2 answers (the denominator):
  agreed                                     184  (76.7% of 240)
  DISAGREED                                    1  (0.4% of 240)
  could not answer                             55  (22.9% of 240)

DISAGREEMENTS (each is a defect, not a fallback):
  PlantedDisagreement: arm2=('x', 'y') arm3=('WRONG', 'ALSO_WRONG')

RESIDUE -- functors arm 3 could not answer (29), BY NAME:
  P0, Pt, PtAlias, animal, bar, cite, color, d, debug, dfact, empty_pred,
  f, fact, foo, ghost, gv_free, impclob_verdict, impord_fverdict, key, lp,
  marker, n, p, q, seen, solve_count_tabled, solve_tiny, verdict, zonkish
```

Reading it against the fail conditions:

1. `N == 0`? No — 689.
2. `DISAGREED` non-zero for a functor other than the positive control's own
   `PlantedDisagreement`? No. The ONE disagreement in the full run IS the
   positive-control test's own planted mismatch (that test file lives
   under `tests/` and is naturally swept into the full run). Excluding it,
   real engine/test code produced **zero** disagreements over 240 arm-2
   calls.
3. A residue name not explained? No — see "Reading the residue" below;
   every one of the 29 traces to one of three named mechanisms.

## Reading the residue (corrected 2026-09-22, fix round 1)

**The first version of this README explained all 29 residue names with one
story — "unbound row, so the shadow probe reads the wrong `db`" — and that
story is FALSE for at least one confirmed case, caught by a peer review
that loaded a real `-dynamic(dfact/3)` module and measured it directly.
The corrected account below distinguishes what was actually measured from
what is inferred by pattern, and says so at every step — because an
instrument whose own README states a false cause is exactly how a
fail-open gets built.**

Three genuinely distinct mechanisms produce a `None` shadow read. All are
consistent with the fail condition (residue is "explained," not silent) —
but they are different facts, and only one of them is a live todo.

**Mechanism 1 — a real declaredness gap, not a probe artifact.** A
`-dynamic(functor/arity)` directive, or a plain `name/arity` entry (no
field list) in a `-module(...)` export header, declares an ARITY, never
field names. Measured directly for two cases, using the REAL module `db`
(not derived from the residue class's own row):

```
-dynamic(dfact/3):  cls._row is bound (detached=False); db.signature_for
                     and db.declared_fields_by_name both None; arm2 answers
                     synthesized ('arg_0','arg_1','arg_2'); arm3 answers None.
-module(gate_vocab, [gv_free/1, ...]):  same result — checked against the
                     real module db via a SIBLING bound predicate, not
                     derived from gv_free's own (unbound) row.
```

No signature is EVER registered for these, on any `db`, at any time — this
is not about which `db` the shadow probe happens to derive. It is a
genuine bug in the declaredness contract, filed as
`todo/dynamic-declarations-are-invisible-to-arm-3-2026-09-22.md`, with the
measurement above, why it bites at W4b-3, and candidate fixes (not
decided here). Confirmed for `dfact` and `gv_free`; the same "arm 2
returned synthesized `arg_N` placeholder names" signature also appears for
9 more residue members (`cite`, `debug`, `fact`, `ghost`, `impclob_verdict`,
`impord_fverdict`, `lp`, `p`, `seen`) — consistent with the same mechanism,
**not individually re-verified against a fresh full-compile db** the way
`dfact`/`gv_free` were, and left as open follow-up rather than claimed as
measured.

**Mechanism 2 — a genuine shadow-probe artifact** (this is what the first
version of this README wrongly generalized to ALL 29 names). A
field-NAMED clause-free declaration — `-private([zonkish(X, Y)])`
(`tests/predmeta_p1/test_p1_sites_rerouted.py`) — DOES register its real
names on the compiling module's `db`:

```
real module db.declared_fields_by_name('zonkish') -> ('X', 'Y')   # found!
cls._row.detached                                 -> True          # but
                                                                     # zonkish's
                                                                     # OWN row
                                                                     # is a
                                                                     # different,
                                                                     # private
                                                                     # db that
                                                                     # never
                                                                     # saw it
```

Here the shadow probe's `db = cls._row._db` genuinely reads the wrong
database — a real arm-3 caller, handed the compiling module's own `db`
directly (never derived from the class), WOULD find `('X', 'Y')`. This is
the probe-derivation limitation, confirmed for `zonkish` only. Not claimed
for the other 17 real-field-named residue members without individual
verification (see below).

**Mechanism 3 — genuinely never declared anywhere.** Bare
`make_predicate(...)` calls or direct `class X(metaclass=PredicateMeta)`
test scaffolding, with no compiling module and no declaration on any `db`
at all: `P0`, `Pt`, `PtAlias` (`tests/test_field_names_for.py`), `bar`,
`foo` (`tests/test_funnel_accessors.py`), `animal`, `empty_pred`
(`tests/test_listing.py`, literal `class animal(metaclass=PredicateMeta)`)
— confirmed by source (the field names these carry are exactly the ones
passed at construction) plus row inspection. Here arm 3's `None` is
correct — there is nothing anywhere to find.

**What is NOT individually confirmed.** 10 of the 29 names carry real,
programmer-chosen field names (`color`, `d`, `f`, `key`, `marker`, `n`,
`q`, `solve_count_tabled`, `solve_tiny`, `verdict`) and have not each been
traced to a specific compiling module the way `zonkish` was — grep-based
guessing at their origin turned out to be unreliable during this
correction (the same bare name recurs across dozens of unrelated test
files at different arities with different declaration styles — `lp` and
`p`, for instance, each grep-matched a plausible source whose measured
fields did not match what the census actually captured). They are
Mechanism 2 or Mechanism 3 — not Mechanism 1, since they carry real names
— but which of the two, per name, is unresolved and not claimed here.

**Summary count:** 2 confirmed Mechanism 1 (+9 pattern-consistent,
unverified) = up to 11; 1 confirmed Mechanism 2; 7 confirmed Mechanism 3;
10 real-named names of unconfirmed mechanism (2 or 3). All 29 are
"explained" in the sense the fail condition asks (none is a silent,
untraceable gap) — but only Mechanism 1 is an actual defect, and it has
its own todo rather than being folded back into "the residue is fine."

No fail condition holds in the sense of blocking this task: `N` is
nonzero, the one `DISAGREED` is self-planted, and every residue name maps
to one of three named, evidenced mechanisms rather than an unexplained
gap. One genuine defect (Mechanism 1) was found and is filed as a todo for
W4b-2, per the instructions for this task — it does not block W4b-1.
