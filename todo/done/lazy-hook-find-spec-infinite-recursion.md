# `_LazyHookFinder.find_spec` recurses until RecursionError

**Severity:** high — crashes the host process's test runner outright (pytest
`INTERNALERROR`, not a test failure), so a whole suite reports nothing.

## Symptom

Running an external authoring harness's suite dies mid-execution:

```
INTERNALERROR> File "/workspace/clausal/clausal/_lazy_hook.py", line 25, in find_spec
INTERNALERROR>   if importlib.util.find_spec(qualified) is not None:
INTERNALERROR> File "<frozen importlib.util>", line 90, in find_spec
INTERNALERROR> File "<frozen importlib._bootstrap>", line 1371, in _find_and_load
INTERNALERROR> File "<frozen importlib._bootstrap>", line 1267, in _find_spec
INTERNALERROR> File "/workspace/clausal/clausal/_lazy_hook.py", line 25, in find_spec
...  (repeats)
INTERNALERROR> RecursionError: maximum recursion depth exceeded
```

The cycle is entirely within those frames: `find_spec` -> `importlib.util.find_spec`
-> meta_path -> the same `find_spec`.

## Suspected cause

Condition 2 in `find_spec`:

```python
        # Condition 2: bare top-level name that might be in clausal.modules
        if "." not in fullname:
            qualified = f"clausal.modules.{fullname}"
            try:
                if importlib.util.find_spec(qualified) is not None:
```

`importlib.util.find_spec(qualified)` imports the parent packages of `qualified`
to inspect their `__path__`. Those imports go back through `sys.meta_path`, reach
this same finder, and can re-enter Condition 2 for another bare name — with no
re-entrancy guard on this path. The `_installing` flag guards
`_activate_and_retry`, not the Condition-2 probe.

Suggested fix: hold a re-entrancy flag (or a per-thread "names currently being
probed" set) across the Condition-2 `find_spec` call, the same way `_installing`
guards activation. Bailing out with `return None` on re-entry is safe — it just
declines to claim the name.

## Reproduction

```
cd <external authoring harness checkout>
python3 -m pytest auto/tests -q -p no:randomly
# -> INTERNALERROR ... RecursionError, at
#    auto/tests/test_check_certificate.py::test_rederive_rejects_false_guard_from_bindings
```

## What is NOT the trigger

Isolation attempts that all pass cleanly, so the report should not be read as
"that test is broken":

- `pytest auto/tests/test_check_certificate.py` alone — 30 passed.
- Each individually-preceding module paired with it — no crash.
- `import clausal; importlib.util.find_spec("this_name_does_not_exist_anywhere")`
  — no recursion.

So it needs ACCUMULATED interpreter state (plausibly `sys.path` entries added by
earlier tests pointing at scratch domain trees, which also makes Condition 3 fire
for bare names, or a partially-imported `clausal.modules.*` parent). I did not
isolate the exact precondition. Deselecting the one test just moves the crash to
the next test, which is consistent with a state-dependent rather than
test-specific cause.

## Workaround in use

`pytest --ignore=auto/tests/test_check_certificate.py` (896 passed). This costs
the certificate-check coverage on every run, so it is a stopgap, not a fix.

---

## FIXED — 2026-07-29

**Trigger reproduced.** The exact reported one, and the precondition the report
could not isolate is in that suite itself:
`auto/tests/test_check_certificate.py::test_checker_does_not_import_clausal`
deletes every `clausal*` entry from `sys.modules` to assert the certificate
checker does not pull the interpreter in. It does not — but the stub finder is on
`sys.meta_path`, not in `sys.modules`, so it survives the sweep. From that point
the *next bare-name import anywhere in the process* recurses. That is why
deselecting one test only moved the crash: it moved the next bare import. In the
reported run the bare name was `_suggestions`, which CPython 3.14's
`traceback._compute_suggestion_error` imports while formatting an unrelated test
failure — hence a crash in the reporter rather than in a test.

Distilled to a five-line reproduction, no domain tree needed:

```python
import sys, importlib.util, clausal
for n in [m for m in sys.modules if m == "clausal" or m.startswith("clausal.")]:
    del sys.modules[n]
importlib.util.find_spec("totally_absent_module_xyz")   # -> RecursionError
```

**Mechanism.** Condition 2's probe `importlib.util.find_spec("clausal.modules.X")`
imports that dotted name's *parents* to read their `__path__`. With `clausal`
gone from `sys.modules` the parent import re-enters `sys.meta_path` as the bare
name `clausal`, which is a Condition-2 name, so it probes
`clausal.modules.clausal`, which imports `clausal` again. Same name, forever.
The pre-existing `_installing` flag guards `_activate_and_retry`, never the probe.

**Remedy.** A set of names whose probe is in flight, added before the probe and
discarded in a `finally`; a name already in the set is declined with `None`. This
is `ModulesFinder._resolving` in `clausal/import_hook.py`, the same seam solving
the same problem, rather than a new mechanism. One deliberate difference: the set
is `threading.local`, so a second thread legitimately importing the same name is
not declined a spec it is entitled to — `ModulesFinder`'s plain set has that
(latent, benign-in-practice) hazard and there was no reason to copy it.

Chosen over asking only the finders *after* this one on `sys.meta_path`: that
would mean reimplementing parent-`__path__` resolution here, in the stub whose
entire point is to stay small, and it would still not survive a second stub
instance appearing on `sys.meta_path` (which is exactly what the trigger causes —
see below). Not done by raising the recursion limit or catching `RecursionError`.

Declining is safe: `None` means "not mine", so the remaining finders still answer.
A genuinely absent module still raises the normal `ModuleNotFoundError`
(pinned), and nothing on the diagnostics path in `clausal/import_diagnostics.py`
changed — the real hook still activates through Condition 3, also pinned.

**Files.** `clausal/_lazy_hook.py`; `tests/test_lazy_hook_reentrancy.py`
(6 tests: three subprocess tests reproducing the cleared-`sys.modules` state, and
three unit tests for same-name re-entry, the nesting case, and the exception path).

**Verified.** `tests/` — 10519 passed, 1 pre-existing failure
(`test_doc_snippet_coverage.py::test_no_raw_untested_blocks`), 136 skipped,
44 xfailed. The reported suite now runs to completion with `CLAUSAL_ROOT` pointed
at the fix: `939 passed, 13 failed`, no `INTERNALERROR`, with
`test_check_certificate.py` no longer ignored — recovering the 30 certificate
tests the workaround was costing on every run. With the old `--ignore` still
applied, the failure list is byte-identical to the pre-fix run, so none of those
13 are new here.

**Left undone**, deliberately:

- The stub *reinstalls itself* when the trigger fires. Clearing `clausal` from
  `sys.modules` makes `clausal/__init__` re-execute during activation, which
  re-imports `clausal._lazy_hook` and inserts a second stub instance. Harmless
  now (each instance carries the guard, and a duplicate only costs one extra
  probe per bare import before it activates and removes itself), but it means
  `sys.meta_path` can accumulate stubs in a process that clears `clausal`
  repeatedly. Wants its own todo if it ever shows up as a cost.
- One external-harness test, `test_gate_query.py::
  test_query_headline_returns_count_and_decisions`, fails only when
  `test_check_certificate.py` runs before it — collateral of *that* test's
  `sys.modules` sweep leaving a second `clausal` module identity behind, not of
  this fix (it fails the same way with the guard removed and the crash avoided).
  It belongs to the external authoring harness, not here: the correct shape is for that
  test to restore `sys.modules` afterwards, or to make its assertion in a
  subprocess.
