# investigate(A09-F007/D002): drive loop eats RuntimeError + subclasses (RecursionError) — for Opus

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F007 (+F006 root cause)
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F007_flatten_cyclic_not_silent (xfail), ::test_F007_regression_direct_generator_raises
**Boundary:** runtime/_trampoline.c is A03/A04 territory — flagged for A12 seams too.

## Problem

`_drive_until_yield` and its sibling loops (runtime/_trampoline.c:664-666,
719-721) do `PyErr_ExceptionMatches(PyExc_StopIteration) ||
PyErr_ExceptionMatches(PyExc_RuntimeError)` and CLEAR the error as "generator
exhausted". `ExceptionMatches` matches subclasses, so:

- RecursionError (subclass of RuntimeError!) from any builtin/user goal is
  converted to silent failure — `flatten(cyclic, F)` answers "no";
  copy_term on cyclic terms likewise (probes R05-R07).
- Any goal that raises RuntimeError for a REAL error (locked-predicate
  assertz, Trail cross-thread check in _variables.c) silently fails.

The RuntimeError arm presumably exists for PEP-479 ("generator raised
StopIteration") and "generator already executing".

## Investigation

1. Which RuntimeErrors does the loop actually need to absorb? Audit call
   sites; likely only the two generator-machinery messages.
2. Fix shape: exact-type match (`PyErr_GivenExceptionMatches` with
   `Py_TYPE`-equality, or check the message/context) so RecursionError and
   user RuntimeErrors propagate; decide propagate-as-Python vs wrap in
   LogicException(resource_error) per A09-D002.
3. Survey fallout: pure-Python trampoline fallback (trampoline.py) has the
   same catch? (grep shows only LogicException/StopIteration — verify parity).
4. Perf: this is the hot loop — keep the fast path unchanged.
