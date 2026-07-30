# The pytest plugin still reports a bare "no solutions"

**Filed:** 2026-07-30, splitting the one unstarted item out of
`todo/done/test-failure-goal-level-diagnostics.md` before archiving it.

`diagnose_failure` (`clausal/testing.py:283`) is done and used by `run_test`
(`:232`) and `run_file` (`:266`): a `.clausal` test failure run through
`python -m clausal.testing` names the failing goal index, its source line, the
bindings at the point of failure and the nearest solution. 19 tests pin it
(`tests/test_testing_diagnostics.py`).

The pytest plugin does not use it. `conftest.py:107` calls
`run_test(self._mod, self.name)` with no `diagnose` argument, and `:113` raises
the bare:

```
test(...) failed (no solutions)
```

So the same failing test is informative from the CLI and opaque under pytest —
which is where CI and most day-to-day runs actually see it.

The fix is small: pass `diagnose=True` at `conftest.py:107` and put the returned
diagnosis in the assertion message. The one thing to decide is cost — the
diagnosis re-runs the goal, so it should stay on the failure path only, which is
already how `run_test` is structured.

The other three items on the archived file's "open" list are deliberate
non-goals, not work: minimal-generalisation refinement was explicitly not built,
variables first bound by the failing goal cannot be shown, and an infinite loop
in a test body is a pre-existing separate issue.
