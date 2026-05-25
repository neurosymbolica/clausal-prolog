"""Probe F008: SegString-vs-list reaches the __unify__ hook in C.

The C path (lines 1127, 1154) keys off PyUnicode_Check. SegString is NOT
a PyUnicode subclass (it is a Python class that proxies a str), so the
str<->list branch will not fire for SegString. The code then falls through
to the __unify__ protocol at line 1188 — confirm.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F008.py
"""
from clausal.logic.variables import Trail, unify

try:
    from clausal.terms import SegString
except Exception as e:
    print(f"Probe F008: SKIP — cannot import SegString: {e}")
    raise SystemExit(0)


def main() -> None:
    print("Probe F008: SegString-vs-list reaches __unify__ hook")
    print(f"  SegString MRO: {[t.__name__ for t in SegString.__mro__]}")
    print(f"  issubclass(SegString, str): {issubclass(SegString, str)}")

    # Ground SegString: should defer to SegString.__unify__
    seg = SegString("abc")
    t = Trail()
    try:
        ok = unify(seg, ["a", "b", "c"], t)
        print(f"  unify(SegString('abc'), ['a','b','c']): {ok}")
    except Exception as e:
        print(f"  unify(SegString('abc'), ['a','b','c']) raised: {type(e).__name__}: {e}")

    # Reverse direction
    t = Trail()
    try:
        ok = unify(["a", "b", "c"], seg, t)
        print(f"  unify(['a','b','c'], SegString('abc')): {ok}")
    except Exception as e:
        print(f"  unify(['a','b','c'], SegString('abc')) raised: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
