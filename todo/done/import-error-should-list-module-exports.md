# Bug: `cannot import name X from M` never says what M *does* export

**Reported:** 2026-07-29, from an external authoring harness
**Severity:** highest measured — this is the single dominant failure mode for
machine authors, by a factor of four over the next one.

---

## STATUS: FIXED at the raise site (2026-07-29)

Implemented in `clausal/import_diagnostics.py`, hooked in at the module-exec
seam in `clausal/import_hook.py` (both the V2 and the legacy V1 pipeline).
Tests: `tests/test_import_export_diagnostic.py` (21), fixtures
`tests/fixtures/impexp_*`.

### Before

```
FAILURES:
  test_load.clausal :: <load> — cannot import name 'within_limit' from 'schema' (/tmp/impdemo/schema.clausal)

1 tests: 0 passed, 1 failed [FAILED]
```

### After

```
FAILURES:
  test_load.clausal :: <load> — cannot import name 'within_limit' from 'schema' (/tmp/impdemo/schema.clausal)
  schema exports: verdict/2, beneficial_owner, not_beneficial_owner, holdings,
                  person, entity, overall, as_of_date, exceeds_limit
  did you mean: exceeds_limit ?
  -> either add `within_limit` to that -module(...) list and define it there,
     or stop importing it and remove every use.

1 tests: 0 passed, 1 failed [FAILED]
```

### The three cases, kept apart

* **Clausal module, name not exported** — the `-module(...)` list, predicates
  with arity (`verdict/2`) and bare atoms without, exactly as declared.
* **Module does not exist** — says so and says there is *no* export list.  An
  empty list is never printed; it would read as "exports nothing", which is a
  different and wrong diagnosis.  The offending directive and the importing
  file are named.  Covers `-import_module` too.
* **Not a Clausal module** — Python's message, byte-for-byte untouched.  A
  Clausal file importing `re`/`numpy` gets Python's diagnosis; inventing a
  Clausal-flavoured export list for it would be misdirection.  Tested both for
  a missing name in a Python library and for an `ImportError` raised inside a
  Python module body.

Two further honest-reporting rules:

* a module with **no** `-module(...)` list is told so, then shown the names it
  really binds (they *are* importable — `from M import f` is a `getattr`), and
  an explicitly **empty** list is distinguished from an absent one;
* if the target's source cannot be re-read, the message says that rather than
  reporting an absence it never established.

### Near-miss

Plain `difflib` scores `within_limit` vs `exceeds_limit` at 0.48 and would miss
the very rename this report is about, so similarity blends character ratio with
shared snake_case tokens (`…_limit`).  When more than three candidates tie at
the top score — a whole family like `wide_export_00 … _59` — no suggestion is
offered at all; three of sixty is a coin toss dressed up as advice.

### Cap

40 names (~5 wrapped lines at 78 columns), which covers real vocabulary
modules.  A longer list is truncated **and says so**, with the true total and
the file path.  Near-misses are always computed over the full list, never the
truncated one.

### Consequence for the harness mitigation

The external authoring harness's own `_missing_import_context` loader hook is now **redundant**, not
conflicting: its `_MISSING_IMPORT` regex still matches (the loader's first line
is still CPython's verbatim), so it will append a *second*, weaker copy of the
same information — no arities, only two candidate paths searched, and it prints
`(nothing)` when it finds no `-module(...)`, which is exactly the "reads as
exports nothing" failure this todo warns about.  Recommend deleting it there
once this lands.  Not touched from this side.

---

## Symptom

```
test_load.clausal::<load> — cannot import name 'within_limit' from
'eu.compliance.compliance_threshold_rule.schema' (/…/schema.clausal)
```

The message names the file, which is good. It never names **what that module
actually exports**, which is the information needed to act. Three resolutions are
possible and the author cannot tell which applies:

1. add `within_limit` to `schema.clausal`'s `-module(...)` list *and define it there*
2. import it from the module that really owns it
3. drop the reference entirely (it was a stale/placeholder name)

## Measured impact

A 25-run census of a local 27B model authoring five domains, ranked by repair
attempts burned and by whether the *next* attempt escaped the error:

| failure mode | attempts | runs hit | recovered | stuck | stuck% |
|---|---|---|---|---|---|
| **`cannot import name X from M`** | **85** | **22 / 22** | 12 | 62 | **84%** |
| functor field-name mismatch (`arg_1`) | 19 | 5 | 1 | 14 | 93% |
| assertion failure (test name only) | 17 | 10 | 2 | 5 | 71% |

It was hit by **every single run**, burned **85 repair attempts**, and the author
escaped it only 16% of the time. 16 of 22 runs ended in a repair fixed point
(byte-identical output attempt after attempt).

The specific names, which show it is a *reconciliation* problem:

```
40  within_limit             <- schema
18  eu_todo_primary_source   <- citations      (a scaffold placeholder key)
16  required                 <- schema
```

These are names one file imports that a sibling was supposed to export. The author
rewrote the exporting module with real vocabulary and left the importing side
stale — with the correct names sitting in the very file the error points at,
invisible.

## Requested fix

Append the target module's export list, and the near-miss if there is one:

```
cannot import name 'within_limit' from 'eu.compliance.compliance_threshold_rule.schema'
  (/…/schema.clausal)
  schema exports: verdict/2, beneficial_owner, not_beneficial_owner, holdings,
                  person, entity, overall, as_of_date, exceeds_limit
  did you mean: exceeds_limit ?
  -> either add `within_limit` to that -module(...) list and define it there,
     or stop importing it and remove every use.
```

The export list alone is most of the value; the did-you-mean is a bonus. This is
the same treatment already requested in
[`functor-field-name-mismatch-diagnostic.md`](functor-field-name-mismatch-diagnostic.md)
and [`test-failure-goal-level-diagnostics.md`](test-failure-goal-level-diagnostics.md),
and it is the same principle that made the `-module` arity error actionable:
**say what is available, not only what is missing.**

## Interim mitigation (harness side, already shipped)

The external authoring harness's own loader now parses this error, reads the target
module's `-module(...)` list off disk, and appends it to the repair prompt
(its own `_missing_import_context`, commit `d3fae4f`). A re-run of the
census measures whether that collapses the 84%.

That workaround only helps callers who drive clausal through *this* harness, and
it re-derives by regex what the loader already knows exactly — including the
distinction between a module that lacks the name and one that does not exist at
all. The fix belongs at the raise site.

## Note on interpreting the 84%

If the harness mitigation collapses the stuck rate, this is purely a diagnostic
gap. If it does **not**, the residue is a genuine cross-module coherence limit in
the author, and the process fix is different (generate importing/exporting sides
as one coupled unit rather than asking a model to keep two files in sync). Either
way the message should carry the export list — the ambiguity is only about how
much of the 84% it recovers.
