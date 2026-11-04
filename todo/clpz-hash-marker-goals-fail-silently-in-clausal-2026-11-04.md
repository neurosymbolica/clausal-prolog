# CLP(Z): a `#X` marker in a `.clausal` goal fails silently

**Status: OPEN.** Found 2026-11-04 while adding the `#(Name)` constant fold. Not caused by that
change: the lowered output for these goals is byte-identical to the commit before it.

In a `.clausal` clause body under `library(clpz)`:

- `#X #= 3` and `#(X) #= 3` fail with no answer. Expected: `X = 3`, as Scryer's clpz gives;
- `X #= #(3)` raises `domain_error`.

A plain `X #= 3` works. The marker shapes as data terms (`#X`, `#3`) are correct.
`clausal/logic/clpz_surface.py` (477, 684, 711) and `clpfd._CLPZ_MARKERS` handle the markers; find
out which path a written goal takes and why the marker is lost there. Pin the fix with a test
against Scryer's answers.
