# head_fold's "structured" guard never excluded a Variable/Goal cell

Found 2026-09-22 while converting the reified vocabulary from
`make_predicate` classes to constructors. **Behaviour was PRESERVED, not
changed** — this note is the question that preserving it leaves open.

## The guard

`clausal/rewrite/rules/head_fold.clausal`, `subst_term/4`'s last clause:

    subst_term(X, _, _, X) <- (
        STRUCTURED is ++isinstance(X, (Variable, Goal, list)),
        STRUCTURED is False
    )

Read as intent: "X is a leaf — not a Variable, not a Goal, not a list — so
substitution leaves it alone."

## What it actually did

Post-P2 the vocabulary builds CELLS (`('Variable', N)`, `('Goal', N, A, K)`),
and a cell is a **tuple**. `isinstance(a_tuple, <PredicateMeta class>)` is
False. So the two class arms matched NOTHING and the test reduced to
`isinstance(X, list)`. `reflection.is_v`'s own docstring is about exactly this
trap: *"a cell is a tuple, so `isinstance` against the vocabulary class answers
False for every term the vocabulary builds — and answers it QUIETLY, which is
how a dispatch chain of these turns into a wrong branch rather than an error."*

The conversion made the arms a hard `TypeError` (`isinstance() arg 2 must be a
type`) instead of a silent False, which is how it surfaced: 6 red in
`tests/rewrite/`. Spelled `isinstance(X, list)` to match the behaviour that
shipped.

## The open question

Because the guard never excluded them, **this clause ALSO fires for a
`Variable` or `Goal` cell** — the engine has no cut, so it is tried alongside
the earlier clauses that match those heads. That may be producing a spurious
extra answer (X substituted-away as a leaf) on top of the correct one.

Not changed here, because:
* it is a semantic change to the rewriter, not part of a representation
  conversion whose bar is NEW 0;
* the correct spelling is `is_v(X, (Variable, Goal))`, and adopting it would
  SUPPRESS an answer the rule produces today — which wants its own gate run.

To settle it: count answers from `subst_term/4` on a clause whose body holds a
`Variable` cell, before and after switching the guard to `is_v`. If the count
drops, the spurious answer was real and the fix is the `is_v` spelling.

## Note for whoever takes it

`clausal/rewrite/rules/_broken_head_fold_control.clausal` is a deliberately
broken COPY of head_fold with ONE deletion (the `not reified_subterm(REST,
Variable(N))` legality goal) and is otherwise "head_fold as shipped" — so any
edit to head_fold must be mirrored there or the negative control stops
isolating the condition it exists to isolate.

## Closed 2026-09-30

Measured as the note proposed: `subst_term(Variable(1), 1, T, R)` answered
`R = T` and then `R = Variable(1)` (2 answers), a Goal holding the variable 3 --
the spurious answer was real. Fixed on fix/todo-batch-5-2026-09-30: the leaf
guard also excludes a Variable/Goal cell (read by functor, as `is_v` does),
mirrored in `_broken_head_fold_control.clausal`. tests/rewrite (578) green;
pinned by tests/rewrite/test_head_fold_subst_term_no_spurious_leaf.py.
