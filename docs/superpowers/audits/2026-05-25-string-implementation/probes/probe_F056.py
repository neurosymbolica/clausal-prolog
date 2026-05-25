"""Probe F056: C9 — flatten/2 treats str as atom, breaking equivalence
with the list-of-1-char-strs form.

``flatten`` at lists.py:277-301 has an explicit "Strings are treated as
atoms (not flattened into characters)" rule.  The docstring is honest
but the semantics are still surprising under the strings-as-lists
contract: ``flatten(['ab'], R)`` returns ``['ab']`` (1 atom), but
``flatten([['a','b']], R)`` returns ``['a','b']`` (2 chars).  Two
"equivalent" inputs produce different outputs.

This is a deliberate semantics choice — flatten could not otherwise
distinguish "a list of words to keep whole" from "a list of char lists
to flatten".  Logged as design-gap, not bug — the docstring explicitly
calls out the contract.  The find still belongs in the C9 ledger
because it is the most prominent place where the "str ≡ list-of-chars"
equivalence breaks in the lists.py surface.
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


def _first(functor, *args, module):
    var = args[-1]
    for _ in call(functor, *args, module=module):
        return deref(var)
    return None


def main() -> None:
    print("Probe F056: C9 — flatten str-as-atom vs list-of-chars asymmetry")
    mod = _load_inline_clausal(
        "probe_f056_flatten", "-module(t, [])\n"
    ).__dict__["$module"]

    cases = [
        ("flatten(['ab'], R)",            [["ab"]]),
        ("flatten([['a','b']], R)",       [[["a", "b"]]]),
        ("flatten(['ab', 'cd'], R)",      [["ab", "cd"]]),
        ("flatten([['a','b'], ['c']], R)",[[["a", "b"], ["c"]]]),
        ("flatten([['ab', 'cd']], R)",    [[["ab", "cd"]]]),
        ("flatten(['a','b','c'], R)",     [[["a", "b", "c"]]]),  # mix str + list args
    ]

    pairs = [
        ("['ab']",               ["ab"]),
        ("[['a','b']]",          [["a", "b"]]),
        ("['ab','cd']",          ["ab", "cd"]),
        ("[['a','b'],['c']]",    [["a", "b"], ["c"]]),
        ("[['ab','cd']]",        [["ab", "cd"]]),
        ("['a','b','c']",        ["a", "b", "c"]),
    ]

    for label, val in pairs:
        r = _first("flatten", val, Var(), module=mod)
        print(f"  flatten({label}, R) → R = {r!r}")

    print()
    print("  Note: ['ab'] and [['a','b']] are 'equivalent' under strings-as-lists,")
    print("  but flatten emits 1 element for the str-wrapped form vs 2 elements for the")
    print("  list-wrapped form.  Documented as intentional but worth logging as the")
    print("  most user-visible place where the equivalence breaks down.")


if __name__ == "__main__":
    main()
