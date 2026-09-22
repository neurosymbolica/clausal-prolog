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
3. A residue name not explained by the out-of-tree/detached-row population
   (spec `docs/superpowers/specs/2026-09-22-w4b1-term-shape-rehome-design.md`
   §3): a `PredicateMeta` class whose `_row` was never bound into a real
   module `Database` — bare `make_predicate(...)` calls, direct
   `class X(metaclass=PredicateMeta)` test classes, or a predicate DECLARED
   (`-dynamic`, `-private`, `-module`/`-import_from`) but never given
   clauses in that compiled unit, so it has no row either. For all of
   these, `cls._state_row()` mints a throwaway single-predicate detached
   `Database` on first access; the shadow read derives its probe `db` from
   that class's own row, so it is reading the WRONG (private, empty)
   database rather than the real module's — it therefore cannot see a
   declaration that legitimately exists elsewhere. This is a known
   limitation of the shadow probe's `db` derivation, not evidence that a
   real arm-3 caller (which is handed the compiling module's own `db`
   directly, never derives it from a class) would fail the same way.

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
3. Every one of the 29 residue names traced back (verified by hand, this
   run, not assumed) to a `PredicateMeta` class with no row bound to a real
   module `Database`:
   * bare `make_predicate(...)` calls or direct
     `class X(metaclass=PredicateMeta)` test scaffolding with no db at all
     — `P0`, `Pt`, `PtAlias` (`tests/test_field_names_for.py`), `bar`,
     `foo` (`tests/test_funnel_accessors.py`), `p`
     (`tests/test_predrow.py`), `animal`, `empty_pred`
     (`tests/test_listing.py`, literal `class animal(metaclass=
     PredicateMeta)`);
   * predicates DECLARED but never given clauses in the compiled unit that
     reaches them — `-dynamic(...)`: `color`, `dfact`, `fact`, `f`, `d`,
     `n`, `q`, `lp`, `seen`; `-private([...])`: `marker`, `verdict`;
     `-module(...)`/`-import_from(...)` vocabulary exports with no local
     clauses: `debug`, `key`, `cite`, `gv_free`, `impclob_verdict`,
     `impord_fverdict`; `-table(...)` targets named directly in
     `clausal/logic/compiler_v2.py`'s own comment as "declared, none with a
     row": `ghost`, `solve_tiny`, `solve_count_tabled`; `zonkish` is a
     `-private([...])` fixture in `tests/predmeta_p1/test_p1_sites_
     rerouted.py`.

   In every one of these cases `cls._row` is unbound, so
   `cls._state_row()` mints a fresh, private, single-predicate `Database`
   that never saw the real module's `declare_functor`/`register_signature`
   call — the shadow probe's `db = cls._state_row()._db` reads that empty
   private database, not the module's real one. A genuine arm-3 caller at
   a production site (`compiler_v2.py`'s directive-target validation, the
   only place these 29 names are actually probed) is handed the compiling
   module's own `db` directly and never derives it from the class, so this
   residue does not describe a live behavioural gap today — it is a
   property of the shadow probe's `db` derivation, named here per spec §3
   so it is a recorded, explained residue rather than a silent one.

No fail condition holds. No new todo filed: nothing in this run needed
widening arm 3, and the one disagreement found is the positive control
working as designed.
