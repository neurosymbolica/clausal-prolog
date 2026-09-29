# Written list-destructuring head patterns still let a str caller in (§1b symmetry gap)

Found by the Task 4 reviewer (Observation 2), P3-2, 2026-09-05. Deliberate
scope-out at the time — filed here so the next §1b reviewer doesn't have to
re-trace it.

## What §1b promises, and where it holds

Post-P3-1 (§1b, `implementation_plans/tagged-tuple-term-representation.md`):
"Double-quoted strings lower to char LISTS ... str unifies with str by
equality, lists with lists." P3-2 Task 4's first-arg-indexing fix (retiring the
`R8` str/char-list bucket-key coalesce, and skipping the lift of a ground
str-content list literal in `_lift_clause_at_pos`) made this symmetric for
**ground list literal facts**: a `str` caller and a `list` caller now get
exactly one solution each against a fact whose head is a ground list, matching
§1b. See `todo/done/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md`
for the full trace and fix.

## Where it does NOT hold: written patterns

That fix only covers a ground list **literal** used as a fact head. It does
nothing about a **written pattern** head — `Pat([H, *T])` or similar — compiled
from source. `docs/strings_as_lists.md` §"Pattern Matching" documents this as a
standing, intentional feature, not a bug:

> Because a string unifies with list patterns, `Listish([*XS])` succeeds for
> `Listish("met")` too — binding `XS` to the whole string — and `[H, *T]`
> destructures a string one character at a time.

The runtime helper behind a compiled `[H, *T]`-shaped head pattern
(`_head_list_unify_input_py` in `clausal/logic/runtime/list_unify.py`, and its
C twin) still implements the pre-P3-1 "a string is a list of its chars"
leniency for exactly this reason — it is load-bearing for a documented,
tested feature (the doc's own gate-around-it example cites
`clausal/rewrite/rules/head_fold.clausal`).

## The gap, stated precisely

§1b's symmetry claim ("lists unify with lists, str unifies with str") is true
for a GROUND list literal fact (Task 4 closed that case) but false, by design,
for a WRITTEN destructuring pattern: a `str` caller reaches a clause whose head
pattern is `[H, *T]` and gets destructured character-by-character, which is
list-shaped leniency applied to string data. This is not a regression and not
inconsistent with `docs/strings_as_lists.md` — the doc has always described
this leniency and continues to — but it means "§1b symmetry" is scoped
narrower than a first reading of the STATUS note might suggest: literal facts
are symmetric, arbitrary head patterns are not, on purpose.

## Disposition

Not a bug to fix — a documentation/scoping note to keep on record so a future
`§1b` audit (or a future user surprised by `[H, *T]` eating a string) traces
to this explanation rather than re-discovering it as "surely this should be
symmetric now that Task 4 fixed the literal case." If the leniency is ever
revisited, `docs/strings_as_lists.md` §"Pattern Matching" is the single place
that documents both the feature and its required gate
(`ISLIST is ++isinstance(X, list), ISLIST is True`).

## Where to look

- `docs/strings_as_lists.md` §"Pattern Matching" — the documented feature and
  its gate idiom.
- `clausal/logic/runtime/list_unify.py` — `_head_list_unify_input_py` (+ C
  twin) — the runtime helper implementing the leniency.
- `todo/done/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md`
  — the adjacent, ALREADY-FIXED literal-fact case, for contrast.

## Closed 2026-09-30 (superseded)

The atoms-as-str flip (2026-09-18) resolved the asymmetry this note recorded:
a `str` is now an ATOM and a string is the chars carrier. Re-measured on
9b6b58a1: `pat([H, *T], H, T)` and `all([*XS], XS)` give NO answer for the
atom `met` (an atom is not a list), and destructure the STRING `"met"` into
`m` and `"et"` -- a string is the list of its chars (ISO double_quotes=chars).
Nothing left to scope.
