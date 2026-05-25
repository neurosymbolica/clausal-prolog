"""Probe F033: output mode always builds a list, never a str.

list_unify.py:156-200 / _list_unify.c:222-460 — the output-mode
helper unconditionally allocates ``result = [...]`` (a Python list)
even when the surrounding logical context would suggest a string
result. The deferred-output target's *original* logical type is not
recorded (there is no such state — it was an unbound Var when
deferred), so even if H='h' and T='ello' were derived from a str
context, the constructed result is ``['h', 'ello']``.

This is the C1 type-loss finding for the head-output path. A clause
``foo([H, *T])`` that matched against a string in another arg, then
constructs ``[H, *T]`` in a third arg, yields a list-shaped target
rather than a str even when both halves were strs.

Severity: design-gap (the type information is genuinely absent at
the output-mode call site; recovering it requires a structural fix
upstream — record the original target type at compile time or at
the input-mode boundary).

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F033.py
"""
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.logic.runtime.list_unify import (
    _head_list_unify_output,
    _head_list_unify_output_py,
)


def main() -> None:
    print("Probe F033: output mode constructs a list")

    target = Var()
    H, T = Var(), Var()
    unify(H, "h", Trail())
    unify(T, "ello", Trail())  # str-typed tail
    t = Trail()
    r = _head_list_unify_output(target, [H], T, [], t)
    print(f"  C  result: {r!r}")
    print(f"     target = {deref(target)!r}, type = {type(deref(target)).__name__}")

    target2 = Var()
    H2, T2 = Var(), Var()
    unify(H2, "h", Trail())
    unify(T2, "ello", Trail())
    t2 = Trail()
    r2 = _head_list_unify_output_py(target2, [H2], T2, [], t2)
    print(f"  Py result: {r2!r}")
    print(f"     target = {deref(target2)!r}, type = {type(deref(target2)).__name__}")

    print(f"  Expected (under strings-as-lists 'input type wins'): 'hello' (str).")
    print(f"  Actual: ['h', 'ello'] (list) — output mode has no type-restore.")


if __name__ == "__main__":
    main()
