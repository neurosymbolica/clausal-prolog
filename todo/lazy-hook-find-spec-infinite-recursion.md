# `_LazyHookFinder.find_spec` recurses until RecursionError

**Severity:** high — crashes the host process's test runner outright (pytest
`INTERNALERROR`, not a test failure), so a whole suite reports nothing.

## Symptom

Running the clausify-executor-train suite dies mid-execution:

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
cd /workspace/clausify-executor-train
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
