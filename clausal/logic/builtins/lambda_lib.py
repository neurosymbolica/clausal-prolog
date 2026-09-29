"""library(lambda): Ulrich Neumerkel's lambda expressions, as builtins.

A lambda is an ordinary term, applied through call/N:

    \\X1^...^Xn^Goal        parameters X1..Xn; every other variable is LOCAL
    Free+\\X1^...^Xn^Goal   the variables of Free are shared with the context

* ``\\(FC, A1, ..., Ak)`` copies FC (fresh variables, no attributes) and calls
  the copy with A1..Ak -- so a lambda called twice never carries a binding
  from the first call into the second.
* ``+\\(Free, FC, A1, ..., Ak)`` copies ``Free+FC`` and unifies the copy's
  Free with the original, so exactly Free's variables are shared.
* ``^(V, Goal, A1, A2, ..., Ak)`` binds the parameter V to A1 and calls Goal
  with A2..Ak.  With no argument left, Goal is called as it is -- unless it
  is itself ``_^_``: a parameter nothing was passed for, which raises
  ``existence_error(lambda_parameter, Goal)``.

The arities are the library's own: ``(\\)/1..8``, ``(^)/3..10`` and
``(+\\)/2..9``.  Semantics measured against Scryer's library(lambda)
(``tests/iso_l3/test_l3_lambda.py`` records its answers).  The ``+\\``
operator (``op(201, xfx, +\\)``) is added to a ``.pl`` file's reader table
when the file imports library(lambda).

Each builtin is DB-receiving (like call/N) so the goal it finally calls is
resolved in the CALLING module.
"""
from __future__ import annotations

from clausal.logic.builtins._registry import _BUILTIN_FIELDS, _DB_BUILTINS
from clausal.logic.exceptions import LogicException, existence_error
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.variables import deref, unify

#: Extra arguments a lambda can be applied to: the library's 0..7.
_MAX_EXTRA = 7


def _copy(term):
    # The engine's copy_term/2 copy: fresh plain variables, attributes not
    # carried -- library(lambda)'s copy_term_nat/2.
    from clausal.logic.builtins.inspection import _copy_term  # noqa: PLC0415
    return _copy_term(term, {})


def _is_hat(goal) -> bool:
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
    from clausal.pythonic_ast.nodes import BitXor  # noqa: PLC0415
    if type(goal) is BitXor:
        return True
    is_cell, functor = compound_cell_shape(goal)
    return is_cell and functor == "^" and len(goal) == 3


def _lambda_parameter_error(goal, who: str) -> LogicException:
    return LogicException(existence_error(
        "lambda_parameter", goal,
        f"{who}: the lambda has a parameter no argument was passed for"))


def _run(this_generator, _proceed, dispatch, call_args, trail):
    """Drive *dispatch* over *call_args*, yielding each solution."""
    sg = StepGenerator(dispatch, this_generator, this_generator,
                       this_generator, *call_args, trail)
    st = yield (sg, None)
    while st is not DONE:
        yield (_proceed, None)
        st = yield (sg, None)


def _caller(db, extra: int):
    """call/(extra + 1) resolved against *db* (the calling module)."""
    return _DB_BUILTINS[("call", extra + 1)](db)


def _apply(db, who, this_generator, _proceed, goal, extras, trail):
    """``call(Goal, *extras)``; with no extras, library(lambda)'s
    no_hat_call/1: a ``_^_`` goal is a missing lambda parameter."""
    goal = deref(goal)
    if not extras and _is_hat(goal):
        raise _lambda_parameter_error(goal, who)
    yield from _run(this_generator, _proceed, _caller(db, len(extras)),
                    (goal, *extras), trail)


def _make_backslash(extra: int):
    who = f"(\\)/{extra + 1}"

    def factory(db):
        def _backslash(this_generator, _proceed, _fail, _catcher, *args):
            # args = (FC, A1..Ak, trail)
            trail = args[extra + 1]
            copied = _copy(deref(args[0]))
            yield from _apply(db, who, this_generator, _proceed, copied,
                              args[1:extra + 1], trail)
            yield (_fail, DONE)
        return _backslash
    factory._db_optional = True
    return factory


def _make_plus_backslash(extra: int):
    who = f"(+\\)/{extra + 2}"

    def factory(db):
        def _plus_backslash(this_generator, _proceed, _fail, _catcher, *args):
            # args = (Free, FC, A1..Ak, trail)
            trail = args[extra + 2]
            free = args[0]
            copied = _copy(("+", deref(free), deref(args[1])))
            mark = trail.mark()
            if unify(free, copied[1], trail):
                yield from _apply(db, who, this_generator, _proceed,
                                  copied[2], args[2:extra + 2], trail)
            trail.undo(mark)
            yield (_fail, DONE)
        return _plus_backslash
    factory._db_optional = True
    return factory


def _make_hat(extra: int):
    who = f"(^)/{extra + 3}"

    def factory(db):
        def _hat(this_generator, _proceed, _fail, _catcher, *args):
            # args = (V, Goal, A1, A2..Ak, trail): V = A1, call(Goal, A2..Ak)
            trail = args[extra + 3]
            mark = trail.mark()
            if unify(args[0], args[2], trail):
                yield from _apply(db, who, this_generator, _proceed,
                                  args[1], args[3:extra + 3], trail)
            trail.undo(mark)
            yield (_fail, DONE)
        return _hat
    factory._db_optional = True
    return factory


def _extras(k: int) -> tuple[str, ...]:
    return tuple(f"a{i}" for i in range(1, k + 1))


for _k in range(_MAX_EXTRA + 1):
    _DB_BUILTINS[("\\", _k + 1)] = _make_backslash(_k)
    _BUILTIN_FIELDS[("\\", _k + 1)] = ("lambda",) + _extras(_k)
    _DB_BUILTINS[("+\\", _k + 2)] = _make_plus_backslash(_k)
    _BUILTIN_FIELDS[("+\\", _k + 2)] = ("free", "lambda") + _extras(_k)
    _DB_BUILTINS[("^", _k + 3)] = _make_hat(_k)
    _BUILTIN_FIELDS[("^", _k + 3)] = ("parameter", "goal", "a0") + _extras(_k)

del _k
