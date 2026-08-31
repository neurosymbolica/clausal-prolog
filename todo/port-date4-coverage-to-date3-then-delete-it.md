# `_date_4` is dead but still load-bearing for test coverage — port, then delete

**Raised:** 2026-09-01, from the `date/3` migration (`spike/date3`, `c1929462`).

`date/4` was retired: `date` is now the arity-3 TERM constructor and unification
does both modes of the old components↔object relation. The *registration* is
gone, so `date/4` is unreachable from Clausal.

`_date_4` — the Python function — was **left in place, unregistered**, and marked
in-source as dead. That is deliberate but temporary.

## Why it was not deleted with the registration

13 call sites across three test files still exercise `_date_4` **directly**, as a
Python function rather than through the language:

| file | sites |
|---|---|
| `tests/test_date_time.py` | 9 |
| `tests/audit_2026_07_05/test_11_modules_interop.py` | 2 |
| `tests/test_py_interop_type_notes.py` | 1 |

Several of them cover semantics `date/3` must honour too, and which its own
contract tests do not all reach yet:

- leap-year acceptance (`2024-02-29`) and rejection (`2025-02-29`)
- `datetime` offered where a plain `date` is required (a subclass, so
  `isinstance` passes — the case `note_mismatch` exists for)
- float components rejected rather than `int()`-truncated (`2020.9` → not 2020;
  audit finding F015)
- match vs. mismatch against an already-bound date

Deleting the function would have dropped that coverage silently, and doing the
port inside the migration commit would have made an already-large change
unreviewable. **The coverage should be PORTED to `date/3`, not dropped.**

## What to do

1. For each of the 13 sites, decide: is it testing something `date/3` still does
   (port it to `tests/test_date_term.py`), or is it testing the *relation* as a
   goal (delete — that behaviour is gone by design)?
2. Then delete `_date_4` and its `simple_to_trampoline` import if now unused.
3. Re-run with the failure set compared **by name** against baseline, not by
   count — the migration's guarantee was 0 new / 0 fixed and this must keep it.

## Notes

- Run in an isolated worktree with `PYTHONPATH` pinned to it. The venv carries
  `__editable__.clausal-0.4.0.pth` containing `/workspace/clausal`, which wins
  over a bare worktree, so the tree under test is otherwise **not** the tree that
  runs. Assert `clausal.__file__.startswith(<worktree>)` before believing any
  result. The `.so` files are gitignored (`*.so`, 0 tracked, 50 on disk) so a
  fresh worktree has none — copy them:
  `find clausal -name '*.so' -exec cp --parents {} <worktree>/ \;`
- Not urgent: nothing is reachable from Clausal, so this is tidiness plus
  honest coverage, not a defect.

**Done when:** `_date_4` is gone, no test imports it, and the suite's failure set
is byte-identical to baseline. Move this file to `todo/done/` on completion.
