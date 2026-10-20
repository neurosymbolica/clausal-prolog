# fix-A07: _clpb_core.c recursion has no depth guard — deep BDDs segfault

**Finding:** A07-F007.
**Severity:** crash (C) — process death on extreme but constructible inputs.

`c_apply_rec` (_clpb_core.c:465), `c_restrict_rec` (:524), and
`c_collect_ids_rec` (:709) recurse on the C stack per BDD level. A
100 000-level chain BDD segfaults inside `negate` (SIGSEGV, exit -11);
10 000 levels survive. The Python fallback raises RecursionError (catchable)
for the same input, so C acceleration *downgrades* failure behaviour from an
exception to a crash.

**Fix:** either `Py_EnterRecursiveCall("...")`/`Py_LeaveRecursiveCall()` in
each recursive C function (matches CPython conventions, raises RecursionError
like the fallback), or convert to an explicit work-stack (heap) — preferred
for `c_collect_ids_rec`, trivial there. Not covered by
`todo/cross_cutting_issues.md`; sibling extensions (`_clpfd_propagate.c`,
`_lists_core.c`) should be checked for the same pattern when fixing.

**Test:** `test_A07_F007_deep_bdd_no_segfault` (subprocess; xfail strict=False).
