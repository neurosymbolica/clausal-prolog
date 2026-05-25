"""Probe F020: SegList __add__/__radd__ rejects str.

terms.py:353-364 — `SegList.__add__` handles `list` and `SegList` but
returns NotImplemented for `str`. `__radd__` only handles `list`. So
``SegList(['a','b']) + "cd"`` raises TypeError, and ``"cd" +
SegList(['a','b'])`` raises TypeError via str's own NotImplemented.

If the strings-as-lists contract means a `str` is interchangeable with
a char list as a SegList tail, this is a smell: SegList + list works,
SegList + str doesn't, even though list + str also fails in vanilla
Python — so the asymmetry is at least consistent with native Python.
Logged as a contract gap.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F020.py
"""
from clausal.terms import SegList, ConcreteSeg


def main() -> None:
    print("Probe F020: SegList + str / str + SegList")

    sl = SegList([ConcreteSeg(["a", "b"])])

    print("  SegList + list:", sl + ["c", "d"])
    print("  list + SegList:", ["c", "d"] + sl)

    try:
        print("  SegList + str:", sl + "cd")
    except TypeError as e:
        print(f"  SegList + str -> TypeError: {e}")

    try:
        print("  str + SegList:", "cd" + sl)
    except TypeError as e:
        print(f"  str + SegList -> TypeError: {e}")


if __name__ == "__main__":
    main()
