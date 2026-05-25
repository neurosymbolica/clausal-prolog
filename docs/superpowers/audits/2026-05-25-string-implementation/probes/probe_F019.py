"""Probe F019: SegList vs SegString __eq__ asymmetry against `str` / `list`.

- terms.py:366-374 `SegList.__eq__`: accepts `list`, rejects `str`
  (returns NotImplemented; Python then asks `str.__eq__` which also
  rejects -> False).
- terms.py:581-587 `SegString.__eq__`: accepts `str`, returns
  NotImplemented for `list`.

So `SegList(['a','b','c']) == 'abc'` is False but the equivalent
`SegString(['abc']) == 'abc'` is True — even though both Seg* values
represent the same string under the strings-as-lists contract.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F019.py
"""
from clausal.terms import SegList, SegString, ConcreteSeg


def main() -> None:
    print("Probe F019: SegList vs SegString __eq__ asymmetry")

    sl = SegList([ConcreteSeg(["a", "b", "c"])])
    ss = SegString(["abc"])

    print(f"  SegList(['a','b','c']) == 'abc'        -> {sl == 'abc'}")
    print(f"  SegString('abc')       == 'abc'        -> {ss == 'abc'}")
    print(f"  SegList(['a','b','c']) == ['a','b','c'] -> {sl == ['a','b','c']}")
    print(f"  SegString('abc')       == ['a','b','c'] -> {ss == ['a','b','c']}")


if __name__ == "__main__":
    main()
