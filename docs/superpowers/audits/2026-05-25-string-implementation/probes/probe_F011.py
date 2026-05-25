"""Probe F011: str<->list path acquires no critical section on the list.

Static-review check: lines 1127-1179 of _variables.c iterate the list with
PyList_GET_ITEM in a loop, with no FT_CS_BEGIN on the list. On a
free-threaded build, another thread mutating the list mid-iteration is
undefined behaviour at the C level.

This probe documents the concern via a stress test on the GIL build
(where mutation-from-another-thread is impossible during a C call).
On a free-threaded build (Py_GIL_DISABLED), the same test could race.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F011.py
"""
import sys
import threading
from clausal.logic.variables import Trail, unify


def main() -> None:
    print("Probe F011: list mutation during str<->list unification")
    gil_disabled = getattr(sys, "_is_gil_enabled", lambda: True)
    try:
        gil_on = gil_disabled()
    except Exception:
        gil_on = True
    print(f"  sys._is_gil_enabled(): {gil_on}")
    print(f"  This probe is a stress test; on a GIL build mutation cannot")
    print(f"  interleave inside the C call, so the race is masked.")

    N = 10_000
    s = "a" * N
    lst = ["a"] * N

    errors = []

    def mutator():
        # Try to mutate the list while unify is iterating it.
        for _ in range(100):
            try:
                lst[N // 2] = "a"  # no-op semantically but writes the slot
            except Exception as e:
                errors.append(e)

    def unifier():
        for _ in range(20):
            t = Trail()
            ok = unify(s, lst, t)
            if not ok:
                errors.append(RuntimeError("unify returned False"))

    threads = [threading.Thread(target=unifier) for _ in range(4)]
    threads += [threading.Thread(target=mutator) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    print(f"  errors observed: {len(errors)}")
    if errors:
        print(f"  first 3: {errors[:3]}")
    print("  (Absence of errors on a GIL build does NOT prove FT safety.)")


if __name__ == "__main__":
    main()
