"""Probe F043: _build_*_list lose str type when star is a list-of-1-char-strs
or a non-ground SegString.

body_star_unify.py:50-126 (`_build_star_list`) and :129-205
(`_build_multi_star_list`) preserve ``str`` *only* when the deref'd
star is itself a ``str`` (or a ground SegString that walks to a str).
When the star is bound to a ``list`` of 1-char strs — semantically
equivalent under the strings-as-lists contract — the helpers fall
into the ``list`` branch and never re-promote the result to ``str``.

For ``_build_multi_star_list``: the non-ground-SegString fork at
:167-184 sets ``all_str = False`` and emits ``ConcreteSeg`` /
``VarSeg`` (SegList shape) rather than rebuilding a ``SegString``,
losing the str-typing even for the segments that *are* concrete
strings.

The probe demonstrates the type loss for both helpers across the
list-of-chars and non-ground-SegString cases.

Severity: design-gap — sibling of F033 (output-mode list-only) and
F018 (SegList walk drops str). The "input type wins" contract is
underdetermined when the input is a list-of-chars: ambiguous whether
it was originally str or list, so collapsing to list is defensible
but inconsistent.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F043.py
"""
from clausal.logic.variables import Var, unify, Trail
from clausal.logic.runtime.body_star_unify import (
    _build_star_list,
    _build_multi_star_list,
)
from clausal.terms import SegString, VarSeg


def main() -> None:
    print("Probe F043: type loss in body-position _build_* helpers")

    # _build_star_list: star bound to list-of-chars
    X = Var()
    unify(X, ["e", "l", "l", "o"], Trail())
    r = _build_star_list(["h"], X, [])
    print(f"  _build_star_list, star=list-of-1-char-strs: {r!r}, "
          f"type={type(r).__name__}")
    print(f"    (Expected under str-typing: 'hello'.)")

    # _build_star_list: star bound to str (control — preserves str)
    Y = Var()
    unify(Y, "ello", Trail())
    r2 = _build_star_list(["h"], Y, [])
    print(f"  _build_star_list, star='ello' str:           {r2!r}, "
          f"type={type(r2).__name__}")

    # _build_multi_star_list: star bound to list-of-chars
    print()
    Z = Var()
    unify(Z, ["e", "l", "l", "o"], Trail())
    r3 = _build_multi_star_list([("fixed", ["h"]), ("star", Z)])
    print(f"  _build_multi_star_list, star=list-of-1-char-strs: {r3!r}, "
          f"type={type(r3).__name__}")
    print(f"    (Expected under str-typing: 'hello'.)")

    # _build_multi_star_list: star bound to non-ground SegString
    W = Var()
    Inner = Var()
    unify(W, SegString(["el", VarSeg(Inner), "o"]), Trail())
    r4 = _build_multi_star_list([("fixed", ["h"]), ("star", W)])
    print(f"  _build_multi_star_list, star=non-ground SegString: {r4!r}, "
          f"type={type(r4).__name__}")
    print(f"    (Expected: a SegString with prefix 'hel', the var hole, suffix 'o'.)")


if __name__ == "__main__":
    main()
