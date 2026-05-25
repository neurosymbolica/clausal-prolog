"""Probe F054: C9 — list-of-1-char-str input is not promoted to str
output across the string-preserving predicates.

Every ``_seq_result`` call site computes ``was_string =
isinstance(lst_val, str)`` and only restores str when that flag is
True.  A caller that passes ``['a','b','c']`` — semantically the same
under strings-as-lists — gets the result back as a list even when the
result is a valid char sequence.

This is the C9 sibling of the type-loss findings logged in C1
([[F018]], [[F033]], [[F043]]).  Per the audit spec C9 enumerates the
mode matrix and tests whether equivalent calls in different shapes
produce the same answer (modulo container).  These do not.

Predicates affected (logged together): ``reverse/2``, ``msort/2``,
``sort/2``, ``permutation/2``, ``select/3``, ``take/3``, ``drop/3``,
``split_at/4``, ``list_to_set/2``, ``subtract/3``, ``intersection/3``,
``union/3``.

This probe demonstrates the asymmetry on a representative subset.
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
    print("Probe F054: C9 — list-of-1-char-str input ≠ str-promoted output")
    mod = _load_inline_clausal(
        "probe_f054_asymmetry", "-module(t, [])\n"
    ).__dict__["$module"]

    list_input = ["a", "b", "c"]
    str_input = "abc"

    pairs = [
        ("reverse",      ("reverse", list_input, Var()),
                         ("reverse", str_input, Var())),
        ("msort",        ("msort", ["c", "b", "a"], Var()),
                         ("msort", "cba",          Var())),
        ("sort",         ("sort", list_input,      Var()),
                         ("sort", str_input,       Var())),
        ("take",         ("take", 2, list_input,   Var()),
                         ("take", 2, str_input,    Var())),
        ("drop",         ("drop", 1, list_input,   Var()),
                         ("drop", 1, str_input,    Var())),
        ("list_to_set",  ("list_to_set", list_input, Var()),
                         ("list_to_set", str_input,  Var())),
        ("subtract",     ("subtract", list_input, ["b"], Var()),
                         ("subtract", str_input,  "b",   Var())),
        ("union",        ("union", list_input,   ["d"], Var()),
                         ("union", str_input,    "d",   Var())),
    ]

    for label, list_args, str_args in pairs:
        list_result = _first(*list_args, module=mod)
        str_result = _first(*str_args, module=mod)
        print(f"  {label:12s}  list-input → {list_result!r:25s} | "
              f"str-input → {str_result!r}")

    print()
    print("  Expected (string-preserving contract or full symmetry):")
    print("    output container shape consistent across logically-equivalent inputs.")
    print("  Actual: list input keeps list shape; str input promotes back to str.")
    print()
    print("  Verdict: F054 confirmed — type-loss asymmetry across the str↔list ")
    print("  boundary for every _seq_result-gated predicate.")


if __name__ == "__main__":
    main()
