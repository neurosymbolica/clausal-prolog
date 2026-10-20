**DONE — commit 8027e88d.** Narrowed the C catch (and Py fallback) to clear only PEP-479 StopIteration wrappers; genuine RuntimeErrors propagate. Also resolves the A09-F006/F007 swallowing (now xpass, owned by the A09 instance).

---

# fix(A04-F009): C _drive_until_yield swallows every RuntimeError — user errors become silent failure

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F009
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF009RuntimeErrorSwallowed` (xfail — flip to pass) + `TestCToolkitGuards::test_solutions_propagates_runtime_error` (divergence control, stays green)

## Bug

`runtime/_trampoline.c` `drive_until_yield_func`, both at the first send
(`:663-671`) and in the loop (`:717-724`):

```c
if (PyErr_ExceptionMatches(PyExc_StopIteration) ||
    PyErr_ExceptionMatches(PyExc_RuntimeError)) {
    PyErr_Clear();
    Py_RETURN_NONE;          /* "search exhausted" */
}
```

ANY `RuntimeError` — including one raised by user Python code in a `++`
escape — is cleared and reported as zero solutions. Consequences:

- `list(call("rte", V))` → `[]`; `solve`/`once` likewise silent. The
  same predicate driven via `solutions()` (C `:609-628`) RAISES — the two
  entry points disagree, so `python -m clausal.testing` and Python
  embedding observe different behaviour for the same program.
- The pure-Python fallback (`trampoline.py:224-259`) catches only
  `StopIteration` — C≠Py divergence.
- StepGen protocol errors ("inner generator returned unexpectedly", a
  RuntimeError from `StepGen_send` `:213-223`) are masked the same way.

The broad catch presumably exists for PEP-479-converted StopIteration
("generator raised StopIteration" → RuntimeError). That case is
distinguishable: its `__cause__`/context is a StopIteration.

## Fix direction

Narrow the C catch: keep clearing `StopIteration`; for `RuntimeError`,
clear ONLY when it is the PEP-479 wrapper (check
`PyException_GetCause()` is a StopIteration instance) — otherwise
propagate. Align the Py fallback (add the same narrow case if it is
actually reachable there). Decide and TEST the intended contract for the
protocol-error RuntimeError (propagating it is almost certainly right —
it indicates a compiler bug, not exhaustion).

## Acceptance

- User RuntimeError from `++` propagates out of `call`/`solve`/`once`
  (xfail flips) and still propagates from `solutions()` (guard green).
- Full suite green — in particular anything that relied on
  generator-return-without-final-yield being treated as exhaustion.
