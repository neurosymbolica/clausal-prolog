"""Probe F034: output mode never walks a SegString-bound star_val.

list_unify.py:166-200 / _list_unify.c:264-434 — the output-mode
helper has explicit branches for list, SegList, and Var when
handling the star_val deref. It has *no* SegString branch: a
star_val derefed to a SegString falls into the catch-all ``else``
that appends the value as a single element.

So ``foo([H, *T])`` in output mode where T is bound to
``SegString(['hello'])`` (which trivially walks to ``"hello"``)
produces a target ``['h', SegString(['hello'])]`` — both the type
loss (list, not str) and the failure to walk the SegString are
visible.

This is the C3 analogue of [[F031]]/[[F032]] for the output path:
both phases have a SegList branch with no SegString twin. C and
Python paths agree (both blind).

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F034.py
"""
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString, VarSeg
from clausal.logic.runtime.list_unify import (
    _head_list_unify_output,
    _head_list_unify_output_py,
)


def main() -> None:
    print("Probe F034: output mode does not walk SegString star_val")

    # Ground SegString tail
    target = Var()
    H = Var()
    T = Var()
    unify(H, "h", Trail())
    ss = SegString(["ello"])
    unify(T, ss, Trail())
    t = Trail()
    r = _head_list_unify_output(target, [H], T, [], t)
    print(f"  C  ground-SegString star: result={r!r}")
    print(f"     target = {deref(target)!r}")
    print(f"     type   = {type(deref(target)).__name__}")
    print(f"  Expected (analogous to SegList branch): ['h','e','l','l','o']"
          f" or 'hello'.")
    print(f"  Actual:   SegString appended as single elem.")

    # Non-ground SegString tail
    print()
    target = Var()
    H = Var()
    T = Var()
    X = Var()
    unify(H, "h", Trail())
    ss = SegString(["el", VarSeg(X), "o"])
    unify(T, ss, Trail())
    t = Trail()
    r = _head_list_unify_output(target, [H], T, [], t)
    print(f"  C  non-ground SegString star: result={r!r}")
    print(f"     target = {deref(target)!r}")
    print(f"  Expected (analogous to SegList branch): a new SegString or "
          f"SegList combining the prefix, the SegString's segments, and the suffix.")

    # Python parity check
    print()
    target = Var()
    H = Var()
    T = Var()
    unify(H, "h", Trail())
    unify(T, SegString(["ello"]), Trail())
    r = _head_list_unify_output_py(target, [H], T, [], Trail())
    print(f"  Py ground-SegString star: result={r!r}, target={deref(target)!r}")


if __name__ == "__main__":
    main()
