# Each CLP(Q) post copies the whole store

`_snapshot_tableau` deep-copies the tableau on every public CLP(Q) call
(`q_le`, `q_eq`, `q_ne`, the `_q_hook` on a binding, `maximize`, ...), so
that backtracking can restore it.  A conjunction of n posts therefore costs
O(n^2) time and memory.  The 2026-10-11 measurement used 2,000 posts:

    chain  X_i = X_{i+1} + 1, then 0 =< X_i      21 s, 3.9 GB peak RSS
    bounds 0 =< X_i =< i + 5                      2.4 s, 950 MB

The copy used to be skipped when the trail had not grown since the last
one.  That was unsound: a choice point can be taken at that very length,
and the change after it was then never undone.  Sharing one copy per
public call is unsound too: `dif/2`'s hook marks the trail, tries a
unification that wakes the CLP(Q) hook, and undoes it, all inside one
post.  So every snapshot request copies: about 3x the old memory
(1.2 GB on `chain`).

The fix is incremental undo: record each change to rows, bounds,
assignments and parametric definitions on the trail, and undo it entry by
entry, instead of copying the whole store.  The C port design for CLP(Q)
(Holzbaur's solver is the reference) has the same aim.
