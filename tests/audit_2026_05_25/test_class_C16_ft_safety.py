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


def test_F011_str_list_unify_ft_smoke():
    """Smoke-test concurrent str↔list unify under Python threads.

    On a GIL-enabled build this is uninformative; on a free-threaded
    build, a missing critical section around PyList_GET_ITEM in the
    str↔list path could produce a segfault or wrong result.

    Post-fix (Phase 2 Task 4): the C-level accessor is PyList_GetItemRef
    which takes the appropriate critical section on FT builds, so this
    test is expected to pass reliably on both GIL and FT builds.
    """
    errors = []
    n_iters = 10_000

    def worker():
        for _ in range(n_iters):
            chars = ["h", "e", "l", "l", "o"]
            try:
                t = Trail()
                if not unify("hello", chars, t):
                    errors.append(("unify returned False unexpectedly",))
            except Exception as e:
                errors.append((type(e).__name__, str(e)))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors during concurrent str↔list unify: {errors[:5]}"
