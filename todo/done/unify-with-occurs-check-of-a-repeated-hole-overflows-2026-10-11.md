# unify_with_occurs_check of a pattern with a repeated hole overflows

Found by the security review of the split pending goal (2026-10-10);
reproduces on 1b717269, before that change.

```seam
rep(R) <- (P is [*A, *A], findall(1, unify_with_occurs_check(P, [[A], A]), R))
```

raises `RecursionError: unify: term nesting too deep` from
`_apply_seglist_split` (clausal/terms.py). The expected answer is `R = []`:
every split binds `A` to a term containing `A`. A split binds holes with
plain `unify`; for the second occurrence of a repeated hole it unifies a
cyclic binding with more of itself and recurses. The occurs-checked
builtins check acyclicity only after a split is bound, so they never get
the chance. Fix direction: give the split's apply an occurs-checked mode
(or check `occurs_check(var, value)` before each hole's bind) when called
from `unify_with_occurs_check/2`.

## Resolved (2026-10-14)

The C unifier now records, on the trail, whether a term's `__unify__` hook
runs for an occurs-checked unification (`trail.unify_oc`, set and restored
around each hook call in `do_unify`). `SegList.__unify__` and the split
apply (`_drive_seg_unify`, `_apply_seg*_split`, `_unify_seglist_cons`,
`_unify_open_seglists`) bind with the unifier `_seg_unifier(trail)` picks:
`unify_with_occurs_check` while the flag is set. A queued split goal reads it
when it is queued. So `rep(R)` answers `R = []` (Scryer, append/3
formulation), and the bare Python case (item 6 of
trail-release-and-bare-unify-follow-ups) returns False instead of building
`A = [A]`. Plain `=`/2 is unchanged. Tests: tests/test_value_pattern_keeps_every_split.py.

Still open elsewhere: `=`/2 on the same pattern (`P is [*A, *A], P is [[A], A]`)
raises RecursionError where Scryer answers the rational tree `A = [A]`; that
is the cyclic-vs-cyclic unification gap tracked in
pl-translator-reads-an-improper-tail-as-an-element-2026-10-12.md.
