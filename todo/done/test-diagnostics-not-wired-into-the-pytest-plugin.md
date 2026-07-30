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

## Done — 2026-07-30

`ClausalItem.runtest` now calls `run_test(..., path=self.path, diagnose=True)`
and appends `GoalDiagnostic.lines()` to the failure message via
`_with_diagnosis` (`conftest.py`). `path` matters as much as `diagnose`: it is
what lets the diagnosis quote the conjunct in its own source syntax and name its
variables, so without it the report degrades to a runtime `term_str` and
`bindings at failure: (unavailable …)`.

Before:

```
test('later goal fails after a binding') failed (no solutions)
```

After:

```
test('later goal fails after a binding') failed (no solutions)
    goal 2 of 2 failed:
      prc('gamma', NUM)
    bindings at failure: NUM = 10
    the predicate DID have a solution, which did not unify (argument 1 differs):
      prc('alpha', 10)
```

The headline is kept and the diagnosis appended, so `-q` summary lines and any
existing grep of a CI log still match. The raised branch is wired the same way,
matching how the CLI's `_failure_lines` treats both. Cost stays on the failure
path — `run_test` decides `passed` before diagnostics start.

Six tests in `tests/test_pytest_plugin_diagnostics.py` drive a real `pytest`
subprocess over the root `conftest.py`, because asserting on a message-building
helper would stay green with the call-site wiring missing — the exact defect.

Not done: the docs code-block path (`DocItem.runtest`) still reports a bare
`Test(...) has no solutions`. It is a different case — the block's module is
loaded from a temp file that is unlinked before the item runs, so there is no
`path` to reify against. Filed as
[[doc-block-failures-report-a-bare-no-solutions]].
