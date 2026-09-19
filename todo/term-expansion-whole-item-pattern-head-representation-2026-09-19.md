# A term_expansion WHOLE-ITEM pattern still matches the head instance, not its cell

Found while clearing the P2 Task 3 checkpoint's worklist (2026-09-19).

## What is fixed, and what is not

Since P2 Task 3 every TERM a `term_expansion` pattern compiles to is a CELL,
while the clause-HEAD channel still carries INSTANCES until P4.  So a pattern
naming a functor that HAS clauses matched nothing:

```clausal
term_expansion(q(key(KEY)), [q(marker(KEY))], STATE, STATE) <- True
key(stays),          # arrives as the instance key(X='stays')
                     # the pattern builds the cell ('key', KEY)
```

`_try_te_match` now lowers the target with `_head_as_cell` on the HEAD-pattern
retry (`wrap_head=True`), which is the path a bare-term pattern like
`q(key(K))` takes.  `tests/fixtures/expansion_nested_var.clausal` is the gate.

The WHOLE-ITEM path (`wrap_head=False`, the pattern binds the `Predicate` node
itself) is NOT lowered.  Rebuilding the node with a lowered head hands the
rules a COPY, and the identity/pass-through/one-to-many expansions -- which
return the very term they matched -- went red on it (measured: 3 tests).

## When it bites

A pattern that quotes a RULE and names the head functor, e.g.

```clausal
term_expansion(q(key(K) <- Body), ..., S, S) <- True
```

The head sub-term inside the quoted pattern compiles to a cell; the item's head
is an instance; no match, silently.  No fixture and no corpus file writes one
today (surveyed 2026-09-19: every whole-item pattern in `tests/fixtures/` binds
a bare variable), which is why this is parked rather than fixed.

## The fix, when it is in scope

Either lower IN PLACE (mutate the node's head for the duration of the match and
restore it), or -- better -- let P4 delete the head-instance channel outright,
at which point the question disappears: there is one representation and nothing
to lower.  Prefer waiting for P4 unless a real program hits it first.
