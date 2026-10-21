# faulthandler's timed stack dump segfaults the process on CPython 3.13 (not the engine)

Filed/found: 2026-10-21, while diagnosing a module retried after a failed
import (the Python-bridge audit of its `.seam` dependency was re-run on
every retry; fixed the same day by memoising `python_bridges.audit_routes`).
A `faulthandler.dump_traceback_later(...)` put in to see where the retries
spent their time killed the process with SIGSEGV instead. Severity: a
diagnostic tool, not engine behaviour; recorded so nobody chases it as an
engine crash.

## What / Repro

`faulthandler.dump_traceback_later(0.3, repeat=True)` firing while the main
thread is busy in pure Python (walking a large `ast`, `copy.deepcopy`)
segfaults the process on CPython 3.13.5 (`[GCC 14.2.0]`, Linux). The dump
file ends mid-line, inside the watchdog thread's walk of the main thread's
frames, and the `faulthandler.enable()` SIGSEGV handler prints nothing
(it re-walks the same frames). Exit status 139.

Without the engine -- `clausal` never imported, no C extension loaded:

```python
import ast, copy, faulthandler, time
faulthandler.enable()
faulthandler.dump_traceback_later(0.3, repeat=True, file=open("dumps.txt", "w"))
src = "\n".join(f"def f{i}(x):\n    return (x + {i}) * [x, {i}][0]\n"
                for i in range(3000))
t0 = time.time()
while time.time() - t0 < 25:
    tree = ast.parse(src)
    for s in tree.body:
        ast.dump(copy.deepcopy(s))
print("finished")       # never printed: exit 139 after a few dumps
```

With the engine the same thing happens during a `.clausal` load whose
`use_module` audits a 3000-clause `.seam` module (the dumped frames are
`ast.py`, `copy.py`, `templating/term_rewriting.py` -- Python frames only).
The engine's C sources install no trace, profile or signal hook and never
release or take the GIL (`grep PyEval_SetTrace|PyGILState|Py_BEGIN_ALLOW_THREADS
clausal/**/*.c` is empty), so there is nothing of ours in the path: the
watchdog thread reads another thread's live frame chain without holding
the GIL, which CPython 3.13's frame layout no longer makes safe.

## What to do

- Nothing in the engine. Do not use `dump_traceback_later` as a profiler
  here; `signal.alarm` + `traceback.format_stack(frame)` in a Python-level
  handler (what the repro runner of the import retry used) is safe, and so
  is `faulthandler.dump_traceback()` called from the thread itself.
- Re-test on a later CPython 3.13.x / 3.14 and close this when the pure
  repro above runs to "finished".
