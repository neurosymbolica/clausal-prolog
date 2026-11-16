"""Probe F075: every char/atom predicate rejects SegString as
``type_error("atom", ...)``.

``_atom_to_str`` in ``chars.py:47-57`` accepts only:
  * a plain Python ``str``, or
  * a zero-arity ``PredicateMeta`` (whose ``__name__`` is the atom name).

A ``SegString`` is neither, so every char/atom predicate raises
``type_error("atom", SegString(...))`` when handed one.  Affected:
``upcase_atom/2``, ``downcase_atom/2``, ``atom_length/2``,
``atom_chars/2``, ``atom_codes/2``, ``atom_concat/3``, ``sub_atom/5``,
``number_chars/2``, ``number_codes/2``.  ``char_type/2`` and
``char_code/2`` use ``isinstance(vc, str)`` and silently fail.

Same blind-spot pattern as [[F069]] (``phrase/2,3`` on SegString),
[[F068]] (``phrase/3`` state-thread), and the broader C3 SegList /
SegString gap.  Once head-pattern reconstruction (cf. [[F033]]) starts
producing SegString-shaped bindings, every char predicate above
breaks.

Severity: design-gap (C3).  Fix shape: call ``__walk__`` once at the
top of each predicate when the input is a ``SegString``/``SegList`` and
re-enter on the result, OR add a SegString branch to ``_atom_to_str``
that concatenates the segments when fully ground.
"""
from __future__ import annotations

from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.exceptions import LogicException
from clausal.terms import SegString, ConcreteSeg


def _try(name, arity, *args):
    disp = get_builtin_dispatch(name, arity, None)
    try:
        return ("ok",
                solutions(StepGenerator(disp, None, None, None, *args, Trail())))
    except LogicException as e:
        return ("err", str(e))


def main() -> None:
    print("Probe F075: char/atom predicates on SegString")

    seg = SegString([ConcreteSeg(["h", "i"])])
    # SegString is fully ground — it walks to "hi" — but the predicates
    # never call __walk__.

    for name, arity, args in [
        ("upcase_atom",   2, (seg, Var())),
        ("downcase_atom", 2, (seg, Var())),
        ("atom_length",   2, (seg, Var())),
        ("atom_chars",    2, (seg, Var())),
        ("atom_codes",    2, (seg, Var())),
        ("sub_atom",      5, (seg, Var(), Var(), Var(), Var())),
        ("atom_concat",   3, (seg, "X", Var())),
        ("number_chars",  2, (seg, Var())),
        ("number_codes",  2, (seg, Var())),
    ]:
        kind, res = _try(name, arity, *args)
        snippet = res if kind == "ok" else res[:80]
        print(f"  {name}/{arity}({args!r:.50}...):")
        print(f"      kind={kind}  result={snippet}")

    # char_type uses isinstance check → silent fail, not type_error
    disp = get_builtin_dispatch("char_type", 2, None)
    n = len(solutions(StepGenerator(disp, None, None, None, seg, "alpha", Trail())))
    print(f"  char_type(SegString, alpha)    silent count={n}  (no error, just fail)")
    assert n == 0

    # char_code on SegString — len(seg) is not 1, so type_error
    disp = get_builtin_dispatch("char_code", 2, None)
    try:
        solutions(StepGenerator(disp, None, None, None, seg, Var(), Trail()))
        print("  char_code(SegString, V)        unexpectedly succeeded")
    except (LogicException, TypeError) as e:
        print(f"  char_code(SegString, V)        err: {str(e)[:80]}")

    print()
    print("  Verdict: every char/atom predicate is SegString-blind.  Fixing")
    print("  this is on the same checklist as [[F069]] / [[F068]] — promote")
    print("  Seg* through ``__walk__`` (or extend ``_atom_to_str``).")


if __name__ == "__main__":
    main()
