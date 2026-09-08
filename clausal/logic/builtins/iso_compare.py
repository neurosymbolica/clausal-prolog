"""ISO comparison, unification and arithmetic builtins under their ISO names.

Reachable from `.clausal` ONLY through the quoted canonical form —
`'=:='(A, B)` — because Python has no infix syntax for these; natively in
`.pl`. Spec: docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md
"""
from clausal.logic.builtins._registry import _builtin
from clausal.logic.exceptions import LogicException, instantiation_error, type_error
from clausal.logic.variables import deref, is_var


def _iso_eval(term, context: str):
    """Evaluate an arithmetic term to a number, with ISO's errors.

    `clpfd._eval_ground` returns None for an unbound operand and raises its own
    leaf error for a non-number; ISO wants instantiation_error and
    type_error(evaluable, F/N). Scryer attributes BOTH to (is)/2 regardless of
    which comparison raised them — pin what it does, not what reads tidily.
    """
    from clausal.logic.clpfd import _eval_ground
    t = deref(term)
    if is_var(t):
        raise LogicException(instantiation_error(context))
    try:
        value = _eval_ground(t)
    except LogicException:
        raise
    except Exception:
        raise LogicException(type_error("evaluable", t, context)) from None
    if value is None:
        raise LogicException(instantiation_error(context))
    return value


def _arith_cmp(name, op):
    @_builtin(name, 2)
    def _cmp(a, b, trail, k, _op=op, _name=name):
        if _op(_iso_eval(a, "is/2"), _iso_eval(b, "is/2")):
            yield None
    return _cmp


import operator as _o
_arith_cmp("=:=", _o.eq)
_arith_cmp("=\\=", _o.ne)
_arith_cmp("<", _o.lt)
_arith_cmp(">", _o.gt)
_arith_cmp("=<", _o.le)     # ISO spells it =<, never <=
_arith_cmp(">=", _o.ge)
