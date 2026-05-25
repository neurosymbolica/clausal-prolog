"""Probe F067 — ``phrase/3`` loses str type in Rest.

When ``phrase(g, "abcd", Rest)`` is called with a str input, the
remainder ``Rest`` is bound to a Python ``list`` of 1-char strs
(e.g. ``['c', 'd']``), never to a str like ``"cd"``.  This contradicts
the strings-as-lists "input-type wins" principle established in
[[F018]], [[F033]], [[F042]], [[F043]], [[F053]], [[F062]], [[F063]]
across the rest of the codebase.

The behaviour is documented in ``docs/dcg.md:148`` ("Rest == ['a', 'b']"
in the partial-parse example) — so this is the *documented* contract.
That said, the contract is inconsistent with the broader audit:
str input degrades to list output unconditionally because
``dcg.py:49-50`` converts the input via ``list_val = list(list_val)``
before threading it through the rule body, and no shape-preservation
record is kept.

Logged as design-gap (under C10) because the contract is itself
under-specified: the user is given no way to opt in to str-preserving
output even when every threaded value would be a 1-char str.
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
    print("Probe F067 — phrase/3 Rest type when input is str.")

    src = 'tok(_t) >> ([_t])\n'
    mod_obj = _load_inline_clausal("probe_f067", src)
    mod = mod_obj.__dict__["$module"]
    cls = mod_obj.__dict__["tok"]

    # Case 1: str input, Var Rest — Rest binds to list, not str.
    v, rest = Var(), Var()
    for _ in call("phrase", cls(v), "abcd", rest, module=mod):
        rv = deref(rest)
        print(f"  phrase(tok(V), 'abcd', Rest):  V={deref(v)!r}, "
              f"Rest={rv!r} (type {type(rv).__name__})")
        assert type(rv) is list, (
            f"expected list-typed Rest under current contract, got {type(rv)}"
        )
        assert rv == ["b", "c", "d"]
        break

    # Case 2: list input — Rest is a list (consistent).
    v, rest = Var(), Var()
    for _ in call("phrase", cls(v), ["a", "b", "c", "d"], rest, module=mod):
        rv = deref(rest)
        print(f"  phrase(tok(V), ['a','b','c','d'], Rest):  "
              f"V={deref(v)!r}, Rest={rv!r} (type {type(rv).__name__})")
        assert type(rv) is list
        break

    print()
    print("  Verdict: str input -> list Rest (documented in docs/dcg.md:148,")
    print("  but inconsistent with the broader str-preserving 'input-type")
    print("  wins' contract enforced/wanted by F018/F033/F042/F043/F053/")
    print("  F062/F063).  Design-gap.")


if __name__ == "__main__":
    main()
