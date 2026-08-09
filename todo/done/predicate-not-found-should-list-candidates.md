# Bug: `Predicate name/N not found` never says which predicates *are* defined

**Reported:** 2026-07-29, from an external authoring harness
**Severity:** medium-high for machine authors — 8 repair attempts, **0% recovered**.

---

## STATUS: FIXED at the raise site (2026-07-29)

Implemented in `clausal/predicate_diagnostics.py`, raised from the single
lookup-failure seam in `clausal/logic/compiler/globals_env.py`
(`_DbDispatchAdapter._get_dispatch`).  Near-miss scoring is imported from
`clausal/import_diagnostics.py`, not reimplemented, so the two messages agree
on what counts as a suggestion.

The message now distinguishes, in this order: the name defined **here at
another arity**; the name as a **builtin** at another arity (`atom_length/3`
used to be told to define `atom_length/3` — a worse diagnosis than the bare
line); the name in a module this file **imports** or in an un-imported
**sibling file**; and finally a plain statement of absence plus a near-miss on
the name.  It always names what this module *does* define, and says "defines no
predicates of its own" rather than printing an empty list.

The exception is now `PredicateNotFoundError`, a `KeyError` subclass whose
`__str__` returns its message verbatim — `str(KeyError(m))` is `repr(m)`, which
would have escaped every newline in the candidate list.  Existing
`except KeyError` handlers are unaffected.

Two limits are deliberate and are stated in the message rather than hidden:
an un-imported sibling is read only for its `-module(...)` export list (nothing
is executed to improve an error message), and the sibling scan is capped at 60
files with the message reporting the cap when it bites.

**Still open:** the *other* arity-mismatch path.  When the name IS bound in the
caller's namespace at a different arity, dispatch fails earlier with
`TypeError: citation__3() missing 1 required positional argument: 'trail'` and
never reaches this diagnostic.  That is the more common in-module shape and its
message is worse than the one fixed here — see
`todo/arity-mismatch-reports-a-missing-trail-argument.md`.

---

## Symptom

With goal-level test diagnostics now in place, a failing assertion reports:

```
test_load.clausal:38 :: citation record resolves — 'Predicate citation/2 not found'
  goal 1 of 3 raised: citation(eu.merger.turnover_threshold_rule.citations.example_art_1_2, METADATA)
  KeyError: 'Predicate citation/2 not found'
```

The goal-level part is a clear improvement — the goal index and the full goal term
are exactly what was missing before. What remains absent is the same gap that
[`import-error-should-list-module-exports.md`](import-error-should-list-module-exports.md)
closed for imports: **it says the predicate is not there, never what is.**

The author cannot distinguish:

- `citation` exists at a **different arity** (`citation/3`) — fix the call
- `citation` is defined in a **sibling module** and was never imported — fix the import
- `citation` was never written at all — define it

Three different fixes, no way to choose. This is the sole remaining 100%-stuck
class in the census that has an otherwise-good message.

## Measured impact

25-run census, local 27B authoring five domains:

| failure mode | attempts | runs | recovered | stuck | stuck% |
|---|---|---|---|---|---|
| `Predicate name/N not found` (goal-level) | 8 | 2 | 0 | 5 | **100%** |

Small n, but the 0% recovery is notable precisely *because* the surrounding
diagnostic is good: the goal index and term are present and the author still cannot
act, which isolates the missing piece to the candidate list.

## Requested fix

```
'Predicate citation/2 not found'
  goal 1 of 3 raised: citation(…citations.example_art_1_2, METADATA)
  module eu.merger.turnover_threshold_rule.citations defines: citation/3, cite/1
  did you mean: citation/3 ?   (same name, different arity)
```

Arity near-misses matter most — a same-name/different-arity match is both the most
common cause and the most mechanical fix. If the name is absent entirely, saying so
explicitly ("no predicate named `citation` in this module") is still strictly better
than silence, and points at import-vs-define.

Follows the pattern already established for imports and for the `-module` arity
error: **say what is available, not only what is missing.**

## Evidence that this pattern is what moves the needle

From the same census, before/after the import-export fix landed:

| failure mode | before | after |
|---|---|---|
| functor field-name/arity mismatch | 19 attempts, 93% stuck | 4 attempts, **33% stuck** |
| bodyless fact missing trailing comma (already names the construct) | — | 1 attempt, **0% stuck** |

Every message that names its subject gets fixed on the following attempt. Every
message that states a bare fact burns the author's whole repair budget.
