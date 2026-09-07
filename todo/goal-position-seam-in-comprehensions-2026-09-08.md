# Goal-position `--` inside comprehensions (extension)

The goal-position seam (docs/superpowers/specs/2026-09-08-goal-position-seam-design.md)
recognises a closed list of positions: `if`/`elif`/`while` tests, the
iterable of `for`, and `not` inside those tests. Python has one more
goal-shaped position: the iterable of a comprehension or generator
expression, and the `if` filter inside it.

    [S for S, IDS in --decide(++p, verdict(S, IDS, _))]
    any(--(cited(++s, _)) for s in statuses)

Same rules would apply (targets must be variables of the goal; exports are
copies; strict on undefined answers and residual constraints). Deferred
2026-09-08 by the operator: not needed yet. When it is, the `for` branch's
emission (`$each` projected onto the targets) is the one to reuse; the
comprehension's own scoping (a nested function scope in Python 3) means the
exported names do not leak, which is Python's rule and fine.
