# The error bridge transliterates Python exceptions instead of using `++`

**Raised:** 2026-09-01, from the ISO-compatibility question on the `date/3`
migration. The full written analysis lives in the downstream (closed) notes; the
measured evidence it rests on is reproduced in full below, so this file stands
on its own.

**Routed here 2026-09-01 (operator):** engine bug-fix work happens in this tree.
The copy in `/workspace/clausal/todo/` is the original; this is the one to work.

**A SECOND CALLER NOW WANTS IT, which raises the priority.** Retiring
`ymd_date/4` stalled on exactly this. `ymd_date/4` FAILS on a calendrically
invalid triple; the `date/3` TERM RAISES. A downstream library module needs the
FAILURE: its malformed-input tests require a calendrically invalid triple such as
`[2024, 2, 30]` to yield no solution and the surrounding predicate to skip it
silently, matching an existing implementation byte-for-byte. A working `catch/3`
would let a caller convert the raise back into a failure at the call site and the
retirement could finish.
Today it cannot: the only catcher that matches is a bare CamelCase functor,
which ISO reads as a VARIABLE — so a specific catcher silently widens to a
catch-all. See `clausal/todo/port-date4-coverage-to-date3-then-delete-it.md`.

## Measured

`++` is Clausal's compiler-understood escape into Python and it works for
expressions — `X is ++ValueError` binds `X` to `<class 'ValueError'>`, the real
class. **The error path does not participate in it.**

| probe | result |
|---|---|
| `X is ++ValueError` | `<class 'ValueError'>` |
| `catch(G, ++ValueError, true)` | **no match**, error propagates |
| `catch(G, ++ValueError(M), true)` | **no match**, error propagates |
| `catch(G, ValueError(M), true)` | matches, binds `M` |
| the ball | `Compound(functor='ValueError', args=('...',))` |
| `isinstance(Ball, ValueError)` | **False** |

`clausal/logic/exceptions.py:121` `python_error_term(exc)` builds
`Compound(type(exc).__name__, (str(exc),))`. So a Python exception is
**transliterated** into a stringly-named compound and the object is discarded.
This is a designed, documented helper — its docstring gives
`Catch(Goal, UnitsMismatch(MSG))` as the idiom — not an accident. But it has two
costs that were not visible when it was written.

## Why it matters

**1. It defeats `++`.** There is no Python object left to match, so the escape
hatch the language already has cannot be used for the one thing most obviously
on the Python side of the boundary.

**2. It creates an ISO translation hazard, and a silent one.** Clausal's variable
rule is ALL_CAPS; ISO's is initial-capital. So `ValueError` is a **functor** in
Clausal and a **variable** in ISO. Translating `catch(G, ValueError(M), R)`
outward, a translator that resolves it as a variable produces
`catch(G, Catcher, R)` with `Catcher` free — **a catcher for one specific error
silently becomes a catch-everything**, swallowing errors meant to propagate. It
fails in the unsafe direction with no syntax error to warn anyone. For a rulebase
whose answers are relied on, this is the difference between "this rule did not
apply" and "something went wrong and we hid it".

Marked `++` syntax has neither problem: a translator must handle it deliberately,
and it makes the genuinely non-portable region *visible and enumerable* — which
is a better ISO story than transliteration, not a worse one.

## What to do

Preserve the exception object in the ball so `catch(G, ++ValueError(M), R)`
works. Then the split is by whether an error has a portable meaning:

- **Tier 1 — has an ISO meaning → ISO shape.** Already done for `date/3`
  (`error(domain_error("date", Culprit), "date/3")`, commit `c1929462`). The
  `Context` argument is implementation-defined under ISO, so it can carry full
  Python detail losslessly.
- **Tier 2 — genuine Python leakage → the object, reachable via `++`.** A
  `KeyError` out of a user callout has no ISO meaning and should not be given a
  fake one.

## Scope and risk

- A survey of the downstream rulebases found **zero** uses of `catch`/`throw`, so
  no existing rulebase depends on the current shape and the bridge can change
  freely. One downstream library module throws **bare strings** — a third shape,
  and the least translatable of them; those should become error terms too. That
  module lives outside this repository, so it is a separate change made there.
- This touches every `++` callout's failure path, which is why it was kept out
  of the `date/3` change deliberately.
- The operator has deferred the Python-exception→ISO-formal-term **mapping
  table**: it is "probably sensible" and the answer "would turn up obviously when
  translation is actually done". Do not invent it in advance.

## Notes

- Related and larger, found while writing the analysis: **`is/2` means
  unification in Clausal and arithmetic evaluation in ISO**, while `==` is
  arithmetic here and term identity there. All three operators are crossed. Not
  an error-handling issue, but it belongs in the same translator conformance
  suite — assert that catchers keep their SELECTIVITY across a round trip, which
  is the failure a syntax check cannot see.
- Unprobed: how `prolog_backends/` (trealla, gprolog, scryer) surface *their*
  errors. That is a second translation boundary and the place the ISO story gets
  tested for real rather than reasoned about.

**Done when:** `catch(G, ++SomeError(M), R)` matches a real Python exception, the
downstream bare-string throws are error terms, and a conformance test pins catcher
selectivity across translation. Move this file to `todo/done/` on completion.
