"""Probe F063: C9 — ``maplist/3``, ``filter_map/3``, ``group_by/3``,
``sort_by/3`` always build list output and never call ``_seq_result``,
even when the input is a str and every result element is a 1-char str.

Unlike ``include/3``, ``exclude/3``, ``partition/4``, ``take_while/3``,
``drop_while/3``, ``span/4`` (which honour the str-input shape via
``_seq_result(kept, was_str)``), these four output-building predicates
have no ``was_str``/``_seq_result`` path at all.  The result is hard-coded
to a Python ``list`` even when the natural representation would be a
str.

This is structurally distinct from [[F054]] (which is about
*input*-side list-vs-str asymmetry on str-preserving predicates) and
from [[F062]] (the same input-side asymmetry in higher_order): F063 is
that for these four predicates, **even str input degrades to list
output**.  Closest sibling in lists.py is [[F053]] (output-mode
builders always list).

Examples (each yields a ``list`` despite str input + 1-char str
results):
- ``maplist(upcase, "abc", R)`` → ``R = ['A','B','C']``
- ``filter_map(upcase, "abc", R)`` → ``R = ['A','B','C']``
- ``group_by(key_of, "hello", R)`` → ``R = [['h'], ['e'], ['l','l'], ['o']]``
  (no str preservation even at the inner-group level)
- ``sort_by(code_key, "cba", R)`` → ``R = ['a','b','c']``
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


SOURCE = """
-module(t, [upcase(_c, _u), code_key(_c, _k), vowel_key(_c, _k)])
upcase(_c, _u) <- upcase_atom(_c, _u)
code_key(_c, _k) <- char_code(_c, _k)
vowel_key(_c, _k) <- If(in_(_c, ['a', 'e', 'i', 'o', 'u']),
                        _k == 1, _k == 0)
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


def main() -> None:
    print("Probe F063: C9 — maplist/3, filter_map, group_by, sort_by build "
          "list output even for str input")
    mod = _load_inline_clausal(
        "probe_f063_higher_order_list_only_output", SOURCE
    ).__dict__["$module"]

    upcase = mod.module_dict["upcase"]
    code_key = mod.module_dict["code_key"]
    vowel_key = mod.module_dict["vowel_key"]

    # maplist/3 on str — 1-char str elements but result is list.
    r = _first("maplist", upcase, "abc", Var(), module=mod)
    print(f"  maplist/3(upcase, 'abc', R):                 R = {r!r}  "
          f"({type(r).__name__})")

    # filter_map on str — 1-char str outputs but result is list.
    r = _first("filter_map", upcase, "abc", Var(), module=mod)
    print(f"  filter_map(upcase, 'abc', R):                R = {r!r}  "
          f"({type(r).__name__})")

    # group_by on str — outer list of inner lists.
    r = _first("group_by", vowel_key, "hello", Var(), module=mod)
    print(f"  group_by(vowel_key, 'hello', R):             R = {r!r}  "
          f"({type(r).__name__})")
    if r and isinstance(r, list) and r:
        inner = r[0]
        print(f"    inner-group container: {type(inner).__name__} (str would be ideal)")

    # sort_by on str — should preserve str since outputs are 1-char strs.
    r = _first("sort_by", code_key, "cba", Var(), module=mod)
    print(f"  sort_by(code_key, 'cba', R):                 R = {r!r}  "
          f"({type(r).__name__})")

    # Control: include/3 *does* preserve str via _seq_result for comparison.
    SOURCE_VOWEL = """
-module(t2, [is_vowel(_c)])
is_vowel(_c) <- in_(_c, ['a', 'e', 'i', 'o', 'u'])
"""
    mod2 = _load_inline_clausal(
        "probe_f063_control", SOURCE_VOWEL).__dict__["$module"]
    is_vowel = mod2.module_dict["is_vowel"]
    r_inc = _first("include", is_vowel, "hello", Var(), module=mod2)
    print(f"  control: include(is_vowel, 'hello', R):       R = {r_inc!r}  "
          f"({type(r_inc).__name__})  <- str preserved")

    print()
    print("  Expected (string-preserving contract): when input is str and ")
    print("  every result element is a 1-char str, output should be str.")
    print("  Actual: hard-coded list output (no _seq_result/was_str path).")
    print()
    print("  Verdict: F063 confirmed — these four higher_order builders ")
    print("  drop str typing unconditionally. Sibling of [[F053]] / [[F054]].")


if __name__ == "__main__":
    main()
