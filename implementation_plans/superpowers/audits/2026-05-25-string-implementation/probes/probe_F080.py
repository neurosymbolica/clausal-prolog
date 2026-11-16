"""Probe F080 — type-check predicate answer matrix over str / list / Seg* inputs.

Drives every type-check builtin defined in
``clausal/logic/builtins/type_checks.py`` against the audit row-set
(str, list, empty-str, empty-list, partial SegList, partial SegString,
unbound Var) and prints the answer matrix.

The probe is the source for findings F080 through F08x:
  - F080  is_list("abc") fails — strings-as-lists contract gap
  - F081  string([...]) is not even a predicate name (only ``is_str``)
  - F082  atomic/1 is not registered as a builtin
  - F083  ground/1 returns True for SegList / SegString that contain
           an unbound VarSeg
  - F084  callable_/1 returns True for "abc" (an arbitrary string)
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var
from clausal.terms import SegList, SegString, VarSeg, ConcreteSeg


# Predicates this probe attempts to exercise.  Includes the names the
# audit task asks about (``string`` and ``atomic``) even though they are
# not currently registered — the failure is itself a finding.
PREDICATES = (
    "is_list",
    "is_chars",      # the polymorphic char-sequence variant
    "is_str",        # the actually-registered "is this a Python str?"
    "string",        # asked-for name; expected to be UNDEFINED
    "atom",
    "atomic",        # asked-for name; expected to be UNDEFINED
    "var",
    "nonvar",
    "ground",
    "compound",
    "callable_",
)


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


def _build_inputs():
    """Build the row-set.  Each row is (label, value)."""
    X = Var()                                            # used twice below
    Y = Var()
    return [
        ('"abc"',                          "abc"),
        ('["a","b","c"]',                  ["a", "b", "c"]),
        ('""',                             ""),
        ('[]',                             []),
        ('SegList([VarSeg(X)]) unbound',
         SegList([VarSeg(X)])),
        ('SegString(["a",VarSeg(Y)]) unbound',
         SegString(["a", VarSeg(Y)])),
        ('Var() (unbound)',                Var()),
    ]


def _check(mod, pred: str, value) -> str:
    """Return "T" / "F" / "ERR(...)" / "UNDEF" for a single cell."""
    try:
        from clausal.logic.builtins import get_builtin_predicate
        if get_builtin_predicate(pred, 1, mod.db) is None:
            return "UNDEF"
    except Exception as exc:                         # pragma: no cover
        return f"ERR({type(exc).__name__})"
    try:
        for _ in call(pred, value, module=mod):
            return "T"
        return "F"
    except Exception as exc:
        # Trim long messages.
        return f"ERR({type(exc).__name__})"


def main() -> None:
    print("Probe F080 — type-check predicate answer matrix.")
    print()

    mod_obj = _load_inline_clausal("probe_f080", "")
    mod = mod_obj.__dict__["$module"]

    inputs = _build_inputs()

    # Header
    col_w = max(len(p) for p in PREDICATES) + 1
    row_w = max(len(label) for label, _ in inputs) + 2
    header = " " * row_w + "".join(p.ljust(col_w) for p in PREDICATES)
    print(header)
    print(" " * row_w + "-" * (col_w * len(PREDICATES)))

    # Body
    for label, value in inputs:
        cells = [_check(mod, p, value) for p in PREDICATES]
        print(label.ljust(row_w) + "".join(c.ljust(col_w) for c in cells))

    print()
    print("Key:  T = succeeds  |  F = fails  |  UNDEF = builtin not registered")
    print("      ERR(...) = exception raised during the call")
    print()

    # ── Asserts that pin down the findings ───────────────────────────────
    # F080: is_list("abc") fails (strings-as-lists asymmetry).
    assert _check(mod, "is_list", "abc") == "F"
    assert _check(mod, "is_chars", "abc") == "T"
    assert _check(mod, "is_chars", ["a", "b", "c"]) == "T"

    # F081: there is no `string/1` builtin — only `is_str/1`.
    assert _check(mod, "string", "abc") == "UNDEF"
    assert _check(mod, "is_str", "abc") == "T"

    # F082: there is no `atomic/1` builtin.
    assert _check(mod, "atomic", "abc") == "UNDEF"

    # F083: ground/1 returns True for a SegList / SegString that contains
    # an unbound VarSeg — the C and Python implementations of _is_ground
    # don't know about Seg* containers.
    Xv = Var()
    sl = SegList([VarSeg(Xv)])
    assert _check(mod, "ground", sl) == "T", (
        "expected ground(SegList([VarSeg(unbound)])) == False; "
        "got True (Seg* invisible to _is_ground)."
    )
    Yv = Var()
    ss = SegString(["a", VarSeg(Yv)])
    assert _check(mod, "ground", ss) == "T", (
        "expected ground(SegString([... VarSeg(unbound)])) == False"
    )

    # F084: callable_/1 says any str is callable.  Useful for `call(F, ...)`
    # dispatch by predicate-name, but it also means callable_("definitely
    # not a predicate name") succeeds.  Flag as a smell.
    assert _check(mod, "callable_", "abc") == "T"
    assert _check(mod, "callable_", "this is not a predicate") == "T"

    # Sanity: atom/1 does NOT say "abc" is an atom (only zero-arity
    # PredicateMeta classes are).  is_str/1 is the right test for str.
    assert _check(mod, "atom", "abc") == "F"
    assert _check(mod, "is_str", "abc") == "T"

    # Sanity: var/nonvar behave correctly for the unbound Var.
    v = Var()
    assert _check(mod, "var", v) == "T"
    assert _check(mod, "nonvar", v) == "F"
    assert _check(mod, "var", "abc") == "F"
    assert _check(mod, "nonvar", "abc") == "T"

    print("All matrix-row assertions passed (findings F080–F084 confirmed).")


if __name__ == "__main__":
    main()
