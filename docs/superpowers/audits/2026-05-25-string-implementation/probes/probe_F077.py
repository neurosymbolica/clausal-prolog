"""Probe F077: atom_concat/3 raises instantiation_error for
fully-instantiated non-string args.

``atom_concat`` infers boundness from the success of ``_atom_to_str``
(``chars.py:347-349``).  When all three args are fully bound but at
least one is not str/atom-shaped (e.g. an int, a list, a Compound),
all three ``_bound`` flags are False and the final ``else`` branch on
``chars.py:393`` raises ``instantiation_error("atom_concat/3")``.

Concretely:
  * ``atom_concat([h,e,l], 'lo', V)`` raises instantiation_error
    even though every arg is fully ground.
  * ``atom_concat(1, 2, V)`` raises instantiation_error rather than
    type_error.
  * ``atom_concat(foo(x), 'y', V)`` raises instantiation_error.

The ISO error should be ``type_error(atom, NonAtom)``.  Mixing the
two error classes is C9 (polymorphic mode matrix): a user
``catch(_, instantiation_error, _)`` handler will swallow a real
type error.

Severity: smell.  Same class as the existing predicate-shape mismatch
findings ([[F062]] / [[F063]]).
"""
from __future__ import annotations

from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.exceptions import LogicException


def _try(name, arity, *args):
    disp = get_builtin_dispatch(name, arity, None)
    try:
        solutions(StepGenerator(disp, None, None, None, *args, Trail()))
        return ("ok", None)
    except LogicException as e:
        return ("err", str(e))


def main() -> None:
    print("Probe F077: atom_concat type_error vs instantiation_error")

    cases = [
        ("list, str, V",   (["h", "e", "l"], "lo", Var())),
        ("int, int, V",    (1, 2, Var())),
        ("int, str, V",    (5, "x", Var())),
        ("float, str, V",  (3.14, "x", Var())),
    ]
    for label, args in cases:
        kind, msg = _try("atom_concat", 3, *args)
        print(f"  atom_concat({label})")
        print(f"      {kind}: {(msg or 'success')[:90]}")
        # All of these should be type_error, not instantiation_error.
        assert kind == "err"
        assert "instantiation" in (msg or "")  # current (wrong) behaviour
        assert "type_error" not in (msg or "")

    print()
    print("  Verdict: every fully-bound mis-typed call yields")
    print("  instantiation_error, masking the real type error.  Fix is")
    print("  local to chars.py:391-393 — distinguish 'no _bound flags True")
    print("  because all args are Var' from 'no flags True because the")
    print("  bound args are not atoms'.")


if __name__ == "__main__":
    main()
