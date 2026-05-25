"""Probe F050: C9 — split_with/3 join mode silently drops str parts.

The join branch at lists.py:630-642 interleaves *parts* with the
separator using ``if isinstance(p, list): joined.extend(p)``.  A part
that is a ``str`` (the natural inverse of the split direction, which
*produces* str parts when the input was a str) is silently skipped:
only the separators remain.

Reproduce: round-trip a str through split, then back through join — the
join produces only separators, not the original string.
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load_inline_clausal(name: str, source: str):
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def main() -> None:
    print("Probe F050: C9 — split_with/3 join mode drops str parts")
    mod = _load_inline_clausal(
        "probe_f050_split_with", "-module(t, [])\n"
    ).__dict__["$module"]

    # Round-trip: split then re-join.
    parts = Var()
    splits = []
    for _ in call("split_with", ",", "a,b,c", parts, module=mod):
        splits.append(deref(parts))
    print(f"  split_with(',', 'a,b,c', P)         → P = {splits!r}")

    # Now feed the split result back into join mode.
    joined = Var()
    joined_vals = []
    for _ in call("split_with", ",", joined, splits[0], module=mod):
        joined_vals.append(deref(joined))
    print(f"  split_with(',', J, ['a','b','c'])   → J = {joined_vals!r}")
    print(f"  Expected (round-trip): J = 'a,b,c' or ['a',',','b',',','c']")
    print(f"  Actual:                J = {joined_vals[0]!r}  ← str parts dropped")

    # Direct case: parts that are multi-char strs.
    j2 = Var()
    j2_vals = []
    for _ in call("split_with", ",", j2, ["abc", "def"], module=mod):
        j2_vals.append(deref(j2))
    print(f"  split_with(',', J, ['abc','def'])   → J = {j2_vals!r}")
    print(f"  Expected: J contains 'abc' and 'def' interleaved with ','")
    print(f"  Actual:   J = {j2_vals[0]!r}  ← 'abc' and 'def' dropped")

    if joined_vals == [[",", ","]] and j2_vals == [[","]]:
        print("  Verdict: F050 CONFIRMED — split_with join branch only extends "
              "isinstance(p, list); str parts are silently dropped.")


if __name__ == "__main__":
    main()
