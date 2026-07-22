# A predicate call followed by another expression on the same line (statement context) is silently discarded

**Status:** RESOLVED 2026-07-22 — `EmbedTransformer.visit_Expr` now raises
`SyntaxError(_MULTI_GOAL_STMT_ERROR)` for an arrow-less, multi-element
statement-level `Tuple(ctx=Load)` whose first element is a `Call`. The
next-line-stray-goal form (§"Related form") was left out of scope (each line is
independently a valid fact — needs a separate lint). Tests:
`tests/test_statement_multi_goal_no_arrow.py`.

**Filed:** 2026-07-22 (root cause behind `todo/module-reexport-imported-functor-shadows.md` —
the "silent 0 solutions" there was actually an unparenthesised multi-goal body, not import
shadowing).

## Symptom
At module (statement) level, a predicate call followed by another expression on the **same
line**, comma-separated, with **no trailing comma** and **no `<-` arrow**, parses as a plain
Python tuple expression. It is evaluated and **discarded** — no clause is asserted, no goal is
run, and **no error or warning** is emitted:

```clausal
-module(d, [q(R), fact(R), other(R)])

fact(a),
other(a),
q(R),
fact(R), other(R)      # <-- intended as a rule body / goals; silently a no-op
```

Loading this succeeds. `q/1` has exactly one clause (the `q(R),` fact). The line
`fact(R), other(R)` adds **nothing** — `fact` and `other` keep only their `(a)` facts. The
author almost certainly meant `q(R) <- (fact(R), other(R))` (a conjunction) or a set of goals,
and got a silent no-op instead.

This is the real footgun that produced the "re-exported functor finds 0 solutions" report in
`todo/module-reexport-imported-functor-shadows.md`: a multi-goal body written without
parentheses, so goals silently dropped out of the clause.

## Related form (also silent) — for scope consideration
A comma-**terminated** single-goal rule followed by a stray goal on the next line turns that
goal into an accidental **fact**:

```clausal
q(R) <- fact(R),     # 1-tuple → rule with single goal fact(R)  (this line is fine)
other(R),            # <-- intended as the 2nd body goal; becomes a FACT other(R) for all R
```

Here `q/1` keeps only `fact(R)` as its body and `other/1` silently gains a spurious
all-quantified fact. Same class of bug (unparenthesised multi-goal body), different surface
shape. Deciding whether this one is in scope is part of the ask.

## What already IS caught (no change needed)
An unparenthesised multi-goal body **on a line that contains the `<-` arrow** already raises:

```clausal
q(R) <- fact(R), other(R)
# SyntaxError: clause body must be parenthesized or a single call:
#   write  head <- (body)  or  head <- goal(X)
```

(`_ARROW_BODY_ERROR`, raised from `visit_Expr` when a multi-element `Tuple` has an arrow
`Compare` as its first element — see `clausal/templating/term_rewriting.py`.) The gap is the
**arrow-less** statement-level tuple, which currently falls through with no case matching.

## Root cause / where to fix
`clausal/templating/term_rewriting.py`, `EmbedTransformer.visit_Expr` (~line 2672), scope
depth 0. The current classification of a module-level `Tuple(ctx=Load)`:

* 1 element that is a `Call` → trailing-comma **fact** (kept).
* 1 element that is an arrow `Compare` → **rule** (kept).
* >1 elements whose first is an arrow `Compare` → `_ARROW_BODY_ERROR` (already).
* **>1 elements whose first is a plain `Call`** (no arrow) → *falls through*, no case matches,
  so the tuple survives as a runtime expression and is silently evaluated + discarded. **This is
  the bug.**

## Ask
Raise a `SyntaxError` for the arrow-less multi-element statement-level tuple whose elements are
predicate-call-shaped, with a message that steers toward the right forms — e.g.:

> multiple goals on one statement need a rule head and parentheses: write
> `head <- (goal1, goal2)`; a single fact is `pred(args),` (note the trailing comma)

Decide whether to also flag the related next-line-stray-goal form above, or leave that to a
separate lint (it is harder to detect precisely because each line is independently a valid
fact).

## Repro
`fact(R), other(R)` as a bare module-level statement (predicates predeclared so it does not
merely `NameError`) → loads clean, asserts nothing. ~5 lines. See case D in the investigation.

## Tests to add with the fix
* Arrow-less multi-goal statement → `SyntaxError` (the new behaviour).
* Trailing-comma fact `pred(args),` still works (1-element tuple path unchanged).
* `head <- (g1, g2)` parenthesised body still works.
* `head <- g1, g2` still raises the existing `_ARROW_BODY_ERROR` (unchanged).
