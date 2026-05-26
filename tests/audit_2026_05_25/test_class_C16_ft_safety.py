"""C16 — Free-threaded build safety.

1 bug finding. The str↔list unification path in _variables.c uses
PyList_GET_ITEM without a critical section, which is unsafe under
Py_GIL_DISABLED builds. The test is xfail-NON-strict because GIL
builds mask the race; on FT builds it triggers a segfault or wrong
result.

Findings tested here:
- F011 (bug, xfail-non-strict) FT critical section missing in str↔list unify
"""

import sys
import threading

import pytest

from clausal.logic.variables import Trail, Var, unify


@pytest.mark.xfail(
    strict=False,  # GIL builds mask the race; allow unexpected pass
    reason=(
        "ledger F011: FT critical section missing in str↔list unify; "
        "GIL-enabled builds can't reproduce the race so this test passes "
        "harmlessly when sys._is_gil_enabled() is True"
    ),
)
def test_F011_str_list_unify_ft_smoke():
    """Smoke-test concurrent str↔list unify under Python threads.

    On a GIL-enabled build this is uninformative; on a free-threaded
    build, a missing critical section around PyList_GET_ITEM in the
    str↔list path can produce a segfault or wrong result.

    Marked xfail-NON-strict so a GIL-build pass doesn't break the suite.
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
