# `msort`/`sort` order a compound's INTEGER arguments lexicographically — silently

**Found:** 2026-09-01. **SCOPE CORRECTED the same day — read this first.**

This is about DOMAIN-LOCAL COMPOUNDS ONLY. It is NOT about dates, and the engine's date term
is NOT affected. `date_time`'s `date/3` (clausal 60fb1313) constructs a REAL `datetime.date`
and sorts correctly:

    -import_from(date_time, [date])
    msort([date(2026,1,15), date(2026,1,2), date(2026,1,9)], S)
      -> [datetime.date(2026,1,2), datetime.date(2026,1,9), datetime.date(2026,1,15)]   CORRECT

The original version of this todo drew a date-migration conclusion from a probe that DECLARED
`date(Y, M, D)` in its own `-module` export list. That creates a domain-local compound which
merely happens to be spelled `date`; it is not the engine's date term. THE TRAP WORTH
REMEMBERING: both forms report `type(V).__name__ == "date"`, so a naive type check cannot tell
them apart — only behaviour separates them.

## The defect

Standard order compares a compound's integer arguments as STRINGS. Bare integers are fine;
put the same integers inside a compound and the order becomes lexicographic.

    msort([15, 2, 9], S)                                 -> [2, 9, 15]        CORRECT
    msort([score(15), score(2), score(9)], S)            -> [15, 2, 9]        WRONG
    msort([pt(1,15), pt(1,2), pt(1,9)], S)               -> [15, 2, 9]        WRONG
    msort([[2026,1,15], [2026,1,2], [2026,1,9]], S)      -> [2, 9, 15]        CORRECT (lists)

"15" < "2" < "9" is exactly lexicographic order on the decimal rendering.

## It is a real order, not a no-op — which is why it is dangerous

Two DIFFERENT input orders produce the SAME output:

    msort([date(2026,1,15), date(2026,1,2), date(2026,1,9)], S) -> [15, 2, 9]
    msort([date(2026,1,9),  date(2026,1,15), date(2026,1,2)], S) -> [15, 2, 9]

So this is not stable-sort-preserving-input and it is not "the terms compare equal". It is a
deterministic total order that disagrees with arithmetic. Confirmed separately that the terms
do NOT compare equal: `sort/2`, which deduplicates, returns all three distinct terms rather
than collapsing them. Nothing is lost — the ORDER is wrong.

## Why it matters, and why nothing catches it

`msort` does not raise. It returns a well-formed, plausibly-ordered list. A rulebase that sorts
compound terms carrying numbers — money amounts, thresholds, day counts, scores, tenders by
value, dates — gets a confidently wrong answer, and a test asserting "the result is a sorted
list" passes.

For comparison, `<` on these terms DOES raise (`type_error(orderable, ...)`), which is the right
behaviour. The inconsistency is the trap: the loud path is loud and the quiet path is quiet.

This is the project's recurring shape — the instrument answers, the answer is wrong, and nothing
says so.

## Scope

Any compound with integer arguments, at any arity (reproduced at 1-arg and 2-arg). Lists are
NOT affected: they compare element-wise numerically, which is why the legacy `[Y, M, D]` date
representation sorts correctly and the migration target does not.

## What correct looks like

Standard order of terms should compare compound arguments by term type and, for numbers,
NUMERICALLY — the same comparison bare integers already get. The bare-integer path is already
right; the compound-argument path should reuse it rather than falling back to a string render.

## NO impact on the date migration

Retracted. The migration target is `-import_from(date_time, [date])`, which is a real
`datetime.date` and orders correctly. Do NOT route date ordering through `ymd_date/4`: that
alias is transitional and marked for deletion, and the operator's design is that
`date(Y, M, D)` IS usable as a Python `datetime.date` directly.

What remains is the generic question below, which stands on its own evidence.

## Repro

Probes are in the session scratchpad; the shortest form is a module declaring
`-module(m, [pt(A, B), two_arg(S)])` with `two_arg(SORTED) <- msort([pt(1,15), pt(1,2), pt(1,9)], SORTED)`,
queried via `clausal.query`. No engine edits were made; the live tree was read-only throughout.

## This is an instance of an already-filed defect

The "both forms report `type(V).__name__ == 'date'`" trap recorded above is not new. It is
[[a-generic-compound-renders-identically-to-a-declared-term]] (filed 2026-07-30, still OPEN),
one layer up:

> A goal that fails on a Compound-vs-declared-term mismatch reports a binding that is
> character-for-character what the author asked for. ... The renderer is telling the truth
> about the *shape* and hiding the only thing that matters.

    str(cite(1))                            # 'cite(k=1)'      declared term
    str(Compound('cite', [1]))              # 'cite(1)'        generic compound
    unify(cite(1), Compound('cite', [1]))   # False

The date case is the same defect with a more expensive consequence: a domain-local
`date(Y, M, D)` and the engine's imported `date` term render alike, report the same Python
type name, and behave differently — and the difference only shows up in ORDERING, which is
the one place nothing raises. Two instances now, and the second cost a full evening's wrong
conclusion plus a nearly-issued wrong migration instruction.

That raises the priority of the renderer/identity fix: it is not a cosmetic diagnostics
problem, it is a defect that makes correct-looking evidence wrong.

---

## FIXED — 2026-09-01

**Root cause.** `msort/2` and `sort/2` (`clausal/logic/builtins/lists.py`) sorted with
`sorted(items)` and, on `TypeError`, fell back to `key=lambda x: (type(x).__name__, repr(x))`.
Every compound takes that fallback — `Compound`, `KWTerm` and declared term instances define no
`__lt__` — so a compound's arguments were ordered by their decimal *rendering*. Not a no-op and
not a tie: a deterministic total order on strings, which is exactly why it was quiet.

Five further sites carried the identical fallback and the identical defect:
`sort_by/3`, `max_by/3`, `min_by/3` (`builtins/higher_order.py`) and `setof/3`
(`compiler/globals_env.py` `_set_of_sort_dedup`).

**Fix.** One `_standard_order_key` in `clausal/logic/builtins/_helpers.py`, used by all six, plus
a `_standard_order_sorted` wrapper for the three whole-list sites. It is a rank-tagged tuple key
following the ISO standard order (Var < Number < Atom < String < Compound) that recurses into
compound arguments, lists, dicts and sets, dereferencing as it goes — so a compound's arguments
get exactly the comparison the same values get when bare. Every key starts with a rank int, so
keys of different ranks decide on that int alone and same-rank payloads are always shape-uniform:
the key is **total by construction**, which is what lets it stand in for a comparison the terms do
not implement. The fallback still cannot raise.

Two details worth keeping:

- **`_OpaqueOrder`** carries values with no term shape (`date`, `Quantity`, `Path`, ...). Same
  Python type compares with `<`, so those keep their *natural* order on this path too — `repr`
  would have ordered `date(2020, 1, 15)` before `date(2020, 1, 2)`, the same defect one type
  over. Different types fall back to the type-name grouping this path always used.
- **Compound flavours.** A generic `Compound` and a declared term that render alike do not unify
  (this file's own "already-filed defect" section), so they get adjacent but distinct places
  rather than interleaving. That also keeps argument payloads shape-uniform, since `KWTerm` must
  key by field *name* — its equality is name-based, so a position-based key could sort two equal
  terms to different places.

**Tests.** `tests/test_standard_order.py`, 26 tests: the reported repro at 1/2/3-arity, the
input-order-independence property, `KWTerm` and dataclass terms, `sort/2` dedup, `setof/3`,
nested compounds, a totality sweep over mixed junk, the paths that were already right (bare ints,
lists, strings, dates), and the todo's own end-to-end repro through a loaded `.clausal` module.
Verified meaningful by restoring the old key and watching `msort` return
`[pt(1,15), pt(1,2), pt(1,9)]` again.

**Regression check.** Full suite: 140 failed / 12350 passed. All 140 accounted for against a
clean-HEAD worktree — 82 `.clausal` solver fixtures (identical failure set at HEAD; `ortools` and
`pysat` are not installed in this venv), 55 `tests/test_clpsat.py` (55 at HEAD), and 3 others:
`tests/rewrite/test_corpus.py` and `test_doc_snippet_coverage.py` both fail at HEAD too, and
`test_F026_multi_star_splits_bounded_for_moderate_input` is a hard 3.0s wall-clock assertion that
tripped under load during the full run and passes 3/3 standalone (it exercises
`_multi_star_splits`, which this change does not touch). No regressions.

**Cost.** The fallback key is ~2.5x slower than the `repr` key on 20k compounds (31 ms -> 76 ms).
It is the already-slow path, and it is the path that was returning wrong answers.

**Still open:** the renderer/identity defect this file names as the layer above —
`todo/a-generic-compound-renders-identically-to-a-declared-term.md`. This fix makes the *ordering*
right; it does not make a generic `Compound` distinguishable from a declared term at a glance.
