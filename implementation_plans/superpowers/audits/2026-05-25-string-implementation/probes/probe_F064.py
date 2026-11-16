"""Probe F064 — confirmed-no-finding: ``maplist/2,3`` and ``foldl/4``
on str inputs pass 1-char ``str`` elements to the goal (per the
strings-as-lists contract), and foldl's accumulator is whatever the
user's goal binds — no implicit type-coercion bug.

Spec contract requirement (Phase 0 Task 8 prompt):
> When the input is a str, what type are the elements passed to the
> goal predicate? 1-char strs? Ints (char codes)? (Must be 1-char
> strs per the contract.)

This probe instruments a Python-callable goal via the ``++expr`` escape
to record the type of each element the higher_order trampoline hands
to the goal.  It also verifies foldl/4 transparently threads accumulator
types: a str-typed acc stays str when the goal builds str, and an
int-typed acc stays int when the goal does int arithmetic.

Confirms the contract — no bug here.  Logged as F064 confirmed.
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


SOURCE = """
-module(t, [observe(_c), observe2(_c, _y), concat(_c, _a, _o),
            add_code(_c, _acc, _out)])
observe(_c) <- ++record(_c)
observe2(_c, _y) <- (++record(_c), _y == _c)
concat(_c, _a, _o) <- atom_concat(_a, _c, _o)
add_code(_c, _acc, _out) <- (char_code(_c, _x), _out == _acc + _x)
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


def main() -> None:
    print("Probe F064 — confirmed-no-finding: higher_order goal-element "
          "typing on str inputs.")

    seen: list[tuple[str, object]] = []

    def record(c):
        seen.append((type(c).__name__, c))
        return True

    mod = _load_inline_clausal("probe_f064_typing", SOURCE).__dict__["$module"]
    mod.module_dict["record"] = record

    # maplist/2 on 'abc' — each elem must be a 1-char str.
    seen.clear()
    for _ in call("maplist", mod.module_dict["observe"], "abc", module=mod):
        break
    print(f"  maplist/2 over 'abc' saw elements: {seen}")
    assert seen == [("str", "a"), ("str", "b"), ("str", "c")], \
        f"contract violated: expected 1-char strs, saw {seen}"

    # maplist/3 — same goal-side typing as /2.
    seen.clear()
    R = Var()
    for _ in call("maplist", mod.module_dict["observe2"], "xy", R, module=mod):
        break
    print(f"  maplist/3 over 'xy'  saw elements: {seen}")
    assert seen == [("str", "x"), ("str", "y")], \
        f"contract violated: {seen}"

    # foldl/4 — accumulator stays str through char-concat.
    R = Var()
    for _ in call("foldl", mod.module_dict["concat"], "abc", "", R,
                  module=mod):
        val = deref(R)
        print(f"  foldl/4 concat over 'abc' with acc='': R = {val!r}  "
              f"({type(val).__name__})")
        assert val == "abc" and type(val) is str
        break

    # foldl/4 — accumulator stays int when goal does int arithmetic
    # over char codes derived from a str input.
    R = Var()
    for _ in call("foldl", mod.module_dict["add_code"], "abc", 0, R,
                  module=mod):
        val = deref(R)
        print(f"  foldl/4 add_code over 'abc' with acc=0:  R = {val!r}  "
              f"({type(val).__name__})  (97+98+99={97+98+99})")
        assert val == 97 + 98 + 99 and type(val) is int
        break

    print()
    print("  Verdict: F064 CONFIRMED-no-finding — goal-side element typing ")
    print("  obeys the strings-as-lists contract for maplist/2,3 and foldl/4,")
    print("  and foldl's accumulator is transparently typed by the user's goal.")


if __name__ == "__main__":
    main()
