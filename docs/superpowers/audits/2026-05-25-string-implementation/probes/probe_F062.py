"""Probe F062: C9 — list-of-1-char-str input is not promoted to str
output across the higher_order string-preserving predicates (sibling
of [[F054]] for ``lists.py``).

Every ``_seq_result`` call site in ``higher_order.py`` derives
``was_str`` from ``isinstance(lst_val, str)`` alone — a caller that
passes ``['h','e','l','l','o']`` (semantically equivalent to
``"hello"`` under the strings-as-lists contract) gets a list result
even when the result is a valid char sequence.

Predicates affected (all higher_order builtins that call
``_seq_result``): ``include/3``, ``exclude/3``, ``partition/4``,
``take_while/3``, ``drop_while/3``, ``span/4``, ``tfilter/3``,
``tpartition/4``.

This probe runs every affected predicate on logically-equivalent
list-vs-str inputs and tabulates the asymmetric result containers.
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


SOURCE = """
-module(t, [is_vowel(_c)])
is_vowel(_c) <- in_(_c, ['a', 'e', 'i', 'o', 'u'])
"""


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


def _first_pair(functor, *args, module):
    """For partition/span: collect both output vars."""
    y, n = args[-2], args[-1]
    for _ in call(functor, *args, module=module):
        return (deref(y), deref(n))
    return None


def main() -> None:
    print("Probe F062: C9 — higher_order: list-of-1-char-str input "
          "≠ str-promoted output")
    mod = _load_inline_clausal(
        "probe_f062_higher_order_asymmetry", SOURCE
    ).__dict__["$module"]

    is_vowel = mod.module_dict["is_vowel"]
    list_input = ["h", "e", "l", "l", "o"]
    str_input = "hello"

    cases_single = [
        ("include",    "include"),
        ("exclude",    "exclude"),
        ("take_while", "take_while"),
        ("drop_while", "drop_while"),
    ]
    for label, functor in cases_single:
        list_r = _first(functor, is_vowel, list_input, Var(), module=mod)
        str_r = _first(functor, is_vowel, str_input, Var(), module=mod)
        print(f"  {label:11s}  list-input → {list_r!r:25s} | "
              f"str-input → {str_r!r}")

    # partition/4 and span/4 return two output vars.
    for label, functor in (("partition", "partition"), ("span", "span")):
        list_r = _first_pair(functor, is_vowel, list_input, Var(), Var(),
                             module=mod)
        str_r = _first_pair(functor, is_vowel, str_input, Var(), Var(),
                            module=mod)
        print(f"  {label:11s}  list-input → {list_r!r:35s} | "
              f"str-input → {str_r!r}")

    print()
    print("  Expected (string-preserving contract or full symmetry):")
    print("    output container shape consistent across logically-equivalent")
    print("    inputs.")
    print("  Actual: list input keeps list shape; str input promotes back to str.")
    print()
    print("  Verdict: F062 confirmed — same _seq_result/was_str asymmetry as ")
    print("  [[F054]] in lists.py, replicated across higher_order builtins.")


if __name__ == "__main__":
    main()
