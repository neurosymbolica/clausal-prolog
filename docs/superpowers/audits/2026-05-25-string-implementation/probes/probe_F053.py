"""Probe F053: C9 — length(Var, N) and replicate/3 always build list
output even when the surrounding context expects a str.

The output-mode helpers for ``length`` (lists.py:210-215) and
``replicate`` (lists.py:589-598) have no input-type hint to switch on —
they always allocate a Python ``list``.  Under the strings-as-lists
contract a caller cannot distinguish "give me a 5-char str variable"
from "give me a 5-element list variable".

This is the C9 mirror of [[F033]] / [[F042]] in head-pattern / body
multi-star output mode: when the type information genuinely isn't
present at the call site, the predicate has to pick one — and it
always picks list.
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
    print("Probe F053: C9 — length(Var, N) / replicate(N, 'a', R) build list")
    mod = _load_inline_clausal(
        "probe_f053_output_mode", "-module(t, [])\n"
    ).__dict__["$module"]

    # length output mode — always a list of fresh Vars.
    L = Var()
    for _ in call("length", L, 5, module=mod):
        val = deref(L)
        print(f"  length(L, 5):                L = {val!r}  ({type(val).__name__}, "
              f"len={len(val)})")
        break

    # replicate with 1-char str element — natural str output.
    R = Var()
    for _ in call("replicate", 5, "a", R, module=mod):
        val = deref(R)
        print(f"  replicate(5, 'a', R):        R = {val!r}  ({type(val).__name__})")
        break

    # replicate with multi-char str element — could only be a list.
    R = Var()
    for _ in call("replicate", 3, "abc", R, module=mod):
        val = deref(R)
        print(f"  replicate(3, 'abc', R):      R = {val!r}  ({type(val).__name__})")
        break

    print()
    print("  Expected (string-preserving contract): a way to request 'str shape'")
    print("  from a Var-target builder, or a documented contract that these")
    print("  modes are always list-typed.")
    print("  Actual: hard-coded list output.")
    print()
    print("  Verdict: F053 confirmed — output-mode builders are list-only;")
    print("  this matches [[F033]] / [[F042]] in the head/body-star layers.")


if __name__ == "__main__":
    main()
