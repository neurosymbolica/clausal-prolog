# Bug: `cannot import name X from M` never says what M *does* export

**Reported:** 2026-07-29, from the clausify formalizer-training harness
**Severity:** highest measured — this is the single dominant failure mode for
machine authors, by a factor of four over the next one.

---

## Symptom

```
test_load.clausal::<load> — cannot import name 'within_limit' from
'eu.aml.amlr_bo_chain.schema' (/…/schema.clausal)
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
cannot import name 'within_limit' from 'eu.aml.amlr_bo_chain.schema'
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

`clausify`'s `gate_load` now parses this error, reads the target module's
`-module(...)` list off disk, and appends it to the repair prompt
(`auto/gates.py::_missing_import_context`, commit `d3fae4f`). A re-run of the
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
