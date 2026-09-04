"""C16 — Free-threaded build safety.

1 bug finding (now fixed). The str↔list unification path in
_variables.c previously used PyList_GET_ITEM without a critical
section, which was unsafe under Py_GIL_DISABLED builds. Fixed in
Phase 2 Task 4 by switching to PyList_GetItemRef (FT-safe accessor,
Py 3.13+) at all 4 sites in do_unify.

Findings tested here:
- F011 (fixed) FT critical section in str↔list unify
"""

import threading

from clausal.logic.variables import Trail, unify


def test_F011_str_list_unify_retired_ft_smoke_no_crash():
    """P3-1 Task 5 (§1b): the str↔list cons-rule unification block this
    test smoke-tested is now DELETED from ``_variables.c`` — there is no
    ``PyList_GET_ITEM``-in-the-str↔list-path code left to race on. The
    concurrency concern is retargeted: str-vs-list unify must still be
    thread-safe (no crash, no exception) under concurrent free-threaded
    access, even though it now deterministically returns False (it falls
    to the ``__unify__``-protocol probe, then the list/tuple-mismatch
    guard — never touching a list element at all).

    (Formerly ``test_F011_str_list_unify_ft_smoke``, which asserted
    ``unify("hello", chars, t)`` succeeded; that was the retired
    cross-type unification.)
    """
    errors = []
    n_iters = 10_000

    def worker():
        for _ in range(n_iters):
            chars = ["h", "e", "l", "l", "o"]
            try:
                t = Trail()
                if unify("hello", chars, t):
                    errors.append(("unify returned True unexpectedly (cons rule retired)",))
            except Exception as e:
                errors.append((type(e).__name__, str(e)))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors during concurrent str↔list unify: {errors[:5]}"
