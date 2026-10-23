# In a .pl file, a cut bound into an if_/3 branch runs as true

Filed: 2026-10-23, found while refusing a cut bound into a `.clausal`
meta-argument (commit 6231e39e). Severity: wrong answers vs Scryer, `.pl`
only, for a rare shape.

## What / Repro

```prolog
:- use_module(library(reif)).
p(1).
p(2).
r(L) :- G = !, findall(X, if_(1 = 1, (p(X), G), true), L).
```

Clausal (`.pl`): `L = [1, 2]`. Scryer: `L = [1]`. reif's `if_/3` CALLS its
branches, so the branch is converted when if_ calls it: `G` is `!` by
then, and the branch is `(p(X), !)`, whose cut prunes `p`. The native
front end compiles a `.pl` branch with a variable leaf in place, the
variable as `call(G)`, so the cut is that call's whole goal and runs as
`true`. (A cut WRITTEN in the branch is already lowered as `call(Branch)`,
2026-10-20.) `.clausal` refuses the bound cut (`iso_l3._if_arm`,
`_checked_in_place`).

Pinned as a strict xfail:
`tests/test_meta_call_cut_refused.py::test_a_pl_module_runs_the_bound_cut_as_scryer_does[if_branch]`.

## Options

- Fix with a run-time check that dispatches to `call(Branch)` only when
  the branch holds a cut, and otherwise runs the in-place code.
- Rejected: lowering every such branch as `call(Branch)` (tried in
  6231e39e's draft): about 3.6x slower (29 -> 104 us) for every `.pl`
  branch of that shape, cut or not.
