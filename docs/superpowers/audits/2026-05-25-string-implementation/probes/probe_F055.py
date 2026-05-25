"""Probe F055: C9 — transpose/2 silently fails on str matrix and on str
rows-of-list-matrix mixtures.

``transpose`` at lists.py:700-722 requires the outer matrix to be a
``list`` (not ``_as_items``-derived): ``if is_var(mat) or not
isinstance(mat, list): return``.  A str matrix is therefore silently
rejected, even though under the strings-as-lists contract a str is a
list of 1-char strs (so a 2-char str ``"ab"`` could be interpreted as a
2x0 matrix or refused with an error — but not silently fail).

Inside the loop, rows go through ``_as_items``, so str rows of a list
matrix work — confirming the asymmetric contract: matrix shape must be
list, rows can be either.
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
    print("Probe F055: C9 — transpose/2 silently fails on str outer matrix")
    mod = _load_inline_clausal(
        "probe_f055_transpose", "-module(t, [])\n"
    ).__dict__["$module"]

    # Control: list-of-list matrix.
    T = Var()
    n_list = 0
    for _ in call("transpose", [[1, 2], [3, 4]], T, module=mod):
        n_list += 1
        print(f"  transpose([[1,2],[3,4]], T):    T = {deref(T)!r}")

    # Control: list-of-str matrix — works via _as_items per row.
    T = Var()
    n_los = 0
    for _ in call("transpose", ["ab", "cd"], T, module=mod):
        n_los += 1
        print(f"  transpose(['ab','cd'], T):      T = {deref(T)!r}")

    # Probe: str matrix — silently fails.
    T = Var()
    n_str = sum(1 for _ in call("transpose", "ab", T, module=mod))
    print(f"  transpose('ab', T):              {n_str} solutions  ← silent failure")

    # Probe: list-of-list-of-int — works (control).
    T = Var()
    n_int = 0
    for _ in call("transpose", [[1], [2], [3]], T, module=mod):
        n_int += 1
        print(f"  transpose([[1],[2],[3]], T):    T = {deref(T)!r}")

    if n_str == 0 and n_list > 0 and n_los > 0:
        print()
        print("  Verdict: F055 confirmed — transpose accepts list outer matrix")
        print("  (with str or list rows) but silently fails on str outer matrix.")


if __name__ == "__main__":
    main()
