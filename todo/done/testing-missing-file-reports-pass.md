# TODO: `clausal.testing` reports PASS for a missing / empty input path

**Opened 2026-06-25** from real-world exercise. Low severity, but it masks mistakes
(a mistyped path or wrong cwd looks like a green run).

## Symptom

```
$ python -m clausal.testing /tmp/does_not_exist_xyz.clausal
0 tests: 0 passed, 0 failed [PASSED]
```

A non-existent path (and likewise a file that defines no `Test(...)`) yields
`[PASSED]` with exit status success. During downstream authoring work this repeatedly hid
"ran from the wrong directory" / "module not found" mistakes as green runs.

## Expected

- A path that does not exist → an error message and a **non-zero exit status**
  (not `[PASSED]`).
- A file that loads but contains **zero** `Test(...)` clauses → at minimum a
  distinct "no tests collected" notice; ideally non-zero exit under a
  `--strict`/`--fail-on-empty` flag (mirrors pytest's `--strict`).

## Likely site

The CLI entry in `clausal/testing/` (argument handling + the collect/run/report
path). Add an explicit existence check before load, and distinguish
"0 collected" from "all passed" in both the message and the exit code.

## Done when

- Missing path exits non-zero with a clear "no such file" message.
- Empty / test-less file is reported distinctly from a passing run.
- A small CLI test covers both.
