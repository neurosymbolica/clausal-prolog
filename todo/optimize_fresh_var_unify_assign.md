# Optimize: compile `X is T` to plain assignment when X is a fresh variable

Parked from the 2026-07-15 walrus-operator redesign discussion
(`docs/superpowers/specs/2026-07-15-walrus-operator-redesign-design.md`).

With `is`-chains now the documented way to name terms inline
(`VALUE is compound(a, X) is C[key]`), the common case is a first-occurrence
variable on one side of a unification. General `$unify` + trail mark/undo is
wasted work there: the compiler can detect that the variable has no prior
occurrence in the clause (head or earlier body goals) and emit a plain Python
assignment (no occurs concerns, no trail entry needed if the binding cannot be
backtracked past within the clause — verify interaction with choicepoints
created *later* in the body: the binding must still be undone if a later goal
fails and retries an earlier alternative, so trail elision is only safe when
no earlier choicepoint exists or the existing trail-elision analysis says so;
see tests/test_trail_elision.py for the current machinery).

Scope:
- `Unify` (and the chain-expanded `CompareChain` members) in
  `terms_to_goalop.py` / `_lower_goalop_shared.py`.
- Possibly also `ArithEval` targets (`eval_(E, X)` with fresh `X`) — same shape.

Expected win: hot paths that use chains/`eval` for naming and accumulator
threading (TRO predicates) skip a `$unify` call + trail churn per step.
