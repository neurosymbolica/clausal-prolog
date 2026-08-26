# clpz3 optimize can yield a model that violates its own constraints

**Written:** 2026-08-27, found while validating the WFS surface/core fix
(`todo/done/wfs-undefined-lost-at-query-surface.md`).
**Severity:** medium — a soundness bug in clpz3 labeling, currently visible
only under whole-suite conditions, but "optimizer hands back bindings that
violate an asserted constraint" is not a flake to shrug at.

## The observation

`tests/test_clpz3_opt.py::TestIntegrationScheduling::test_minimize_makespan`
asserts `t1+5<=t2`, `t2+3<=t3`, minimizes `t3`, and expects `(0, 5, 8)`.
Under the full suite on the WFS branch it deterministically (5/5 runs) gets

```
t1=0, t2=6, t3=8, cost=8
```

`t2=6, t3=8` **violates the asserted `t2+3<=t3`**. A genuine z3 model cannot
do that, so the bindings the test derefs are not (all) from the model z3
reported — stale or partially-applied labeling in `z3_optimize_label`, or
global z3 context state perturbed between solve and deref.

## What it is NOT

- Not a WFS/tabling regression: the failure-set diff vs a pristine-main
  worktree run (same venv, same command) is otherwise identical, and the
  test passes on the WFS branch:
  - in isolation, and repeatedly;
  - running the whole `tests/test_clpz3*.py` + `test_clpsat.py` group;
  - running the ENTIRE suite prefix in collection order up to and including
    `test_clpz3_opt.py` (`tests/audit_* … tests/test_c*.py`).
- Not the 4 GiB `ulimit -v`: reproduces identically without the cap.
- Not one of the new test modules' collection imports: still reproduces
  with `--ignore=tests/test_stratification.py` and with
  `--ignore=tests/test_wfs.py`.

It stops reproducing when `tests/audit_2026_07_05` is also ignored — the
branch's changes there (the un-xfailed F002/F003 spawning tests, which now
run further and allocate/GC more) shift timing/heap state enough to expose
it. Baseline main, whose audit phase does less work, never hits it.

## Where to look

`clausal/clpz3.py` / `z3_optimize_label`: how model values are read back and
bound on the trail, and whether anything (GC finalizers of abandoned
generators, a shared z3 context, a cached solver) can run between
`optimize()` and the deref the caller does per yielded solution. The
returned tuple mixing one stale value (`t2`) with consistent others points
at per-variable read-back rather than a wholesale wrong model.

## Repro

On branch with the WFS fix (or any tree where audit_2026_07_05 does the
extra spawning work):

```
/workspace/clausal/venv/bin/python -m pytest tests/ \
  --ignore=tests/test_clportools.py -q -p no:cacheprovider
# → FAILED ...test_minimize_makespan  (assert 6 == 5), every run
```

## Update (same day, after the review-fix round)

After the WFS review follow-ups (commit after 82267432) the full-suite
failure set is byte-identical to pristine main — the makespan failure no
longer reproduces here. Consistent with the diagnosis: it is heap/GC-timing
sensitive, and the perturbation moved again. The underlying soundness
question (an optimize "model" that violates its own asserted constraint)
stands and is worth chasing independently of what currently tickles it.
