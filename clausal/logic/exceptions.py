"""clausal.logic.exceptions — logic-level exception handling (V2-14).

LogicException wraps a logic term for throw/catch control flow.
It is a Python Exception subclass, so:
- .clausal code uses catch(Goal, E, Recovery) / throw(Error)
- Python code can try: ... except LogicException as e: e.term
- Builtins can raise it with structured error terms

Structured error term helpers follow ISO Prolog conventions:
    error(type_error(Type, Culprit), Context)
    error(instantiation_error, Context)
    error(existence_error(ObjType, Culprit), Context)
    error(permission_error(Operation, ObjType, Culprit), Context)
"""

from __future__ import annotations

from typing import Any

from clausal.logic.atoms import mint
from clausal.terms import Add, Compound, Div, FloorDiv, Mod, Mult, Negate, Pow, Sub

# ── The is/== hint ────────────────────────────────────────────────────────────
#
# `is/2` unifies, so ``R is 10000 // 4`` binds R to the *term* ``FloorDiv(10000,
# 4)``; ``==`` is the operator that evaluates.  That is deliberate, but `is` is
# spelled like Prolog's arithmetic-evaluation operator, so the term is written
# by accident and only surfaces later, where a number was required — as
# ``type_error(number, FloorDiv(...))``.  The culprit is in hand there, so say
# what it is.

#: The nodes ``==`` evaluates and ``is`` does not.  ``UnaryPlus`` is absent on
#: purpose: ``++X`` is this language's Python-interop marker, not arithmetic
#: (``DAYS is ++DELTA.days`` — reading a Python ``timedelta`` attribute — is
#: correct code).
ARITH_OPERATOR_TERMS = (Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)

#: Expected-types that mean "a number was required here".  ``evaluable`` is
#: excluded because its two raise sites in clpfd let arithmetic terms through
#: by construction, so it can never carry one as its culprit.
_NUMERIC_EXPECTATIONS = frozenset({"number", "integer"})

#: The half-sentence that turns the fact into an actionable one.  It states what
#: the two operators do — true whoever built the term, which matters because the
#: culprit need not have come from an `is` at all.
IS_VS_EQ_HINT = (
    "`is` unifies without evaluating: `X is <expr>` binds X to the term, "
    "`X == <expr>` binds X to its value"
)


def is_arith_operator_term(value: Any) -> bool:
    """True when *value* is an arithmetic operator term rather than a number."""
    return isinstance(value, ARITH_OPERATOR_TERMS)


def render_arith_operator_term(value: Any) -> str:
    """*value* in surface syntax (``10000 // 4``), or its repr if that fails.

    ``BinOp.__str__`` already spells the operator; the fallback exists because a
    diagnostic must not be able to raise on top of the error it is explaining.
    """
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - a hint may not out-fail its own error
        return repr(value)


def arith_in_numeric_position_hint(term: Any) -> str | None:
    """The is/== note for ``error(type_error(number, <arith term>), _)``, else None.

    Reads only the term already carried by the exception — there is no record of
    which goal built the culprit, and none is needed: that it is an unevaluated
    operator term where a number was required is a structural fact.
    """
    if not (isinstance(term, Compound) and term.functor == "error"
            and len(term.args) == 2):
        return None
    inner = term.args[0]
    if not (isinstance(inner, Compound) and inner.functor == "type_error"
            and len(inner.args) == 2):
        return None
    expected, culprit = inner.args
    # ``expected`` is a str at every raise site, but an unhashable one thrown
    # from .clausal would make the set membership itself raise.
    if not isinstance(expected, str) or expected not in _NUMERIC_EXPECTATIONS:
        return None
    if not is_arith_operator_term(culprit):
        return None
    return (f"`{render_arith_operator_term(culprit)}` is an unevaluated "
            f"arithmetic term, not a number. {IS_VS_EQ_HINT}")


class LogicException(Exception):
    """Exception carrying a logic term for throw/catch."""

    def __init__(self, term: Any) -> None:
        self.term = term
        super().__init__(f"Uncaught logic exception: {term!r}")

    def __str__(self) -> str:
        """The stored message, plus the is/== note when the term earns it.

        Computed here rather than in ``__init__`` so that a LogicException a
        ``catch/3`` swallows — the common case, since these terms are control
        flow — pays nothing for a note nobody reads.  ``args[0]`` is left alone
        so the note cannot leak into a caught term via ``python_error_term``
        (``catch/3`` reads ``.term`` for a LogicException and only falls back to
        ``python_error_term`` for a stray Python exception).

        A ``__str__`` that can raise loses every traceback that touches it, so
        the hint is contained: no note is strictly better than no message.
        """
        message = super().__str__()
        try:
            note = arith_in_numeric_position_hint(self.term)
        except Exception:  # noqa: BLE001 - see the docstring
            return message
        return f"{message}\nnote: {note}" if note else message


def python_error_term(exc: Exception) -> Compound:
    """Convert a Python exception to a catchable logic term.

    Produces ``ClassName(Message)`` — a Compound whose functor is the
    exception class name and whose single argument is the message string.
    This allows .clausal code to match Python exceptions the same way as
    logic ``throw/1`` terms::

        catch(Goal, UnitsMismatch(MSG), Recovery)
        catch(Goal, _, Recovery)   % any exception
        Catch(Goal, UnitsMismatch(MSG))

    This transliteration discards the exception OBJECT, so it cannot serve a
    ``++`` catcher — those are handled by :func:`catch_match`, which receives
    the live exception alongside this structural term.
    """
    return Compound(type(exc).__name__, (str(exc),))


def catch_match(catcher: Any, term: Any, exc: BaseException, trail: Any) -> bool:
    """Match a ``catch/3`` catcher against a raised exception.

    ``catcher`` is the evaluated catcher expression, ``term`` the structural
    ball (``LogicException.term``, or :func:`python_error_term` of a stray
    Python exception), ``exc`` the ORIGINAL exception object.

    A catcher that evaluated to a Python exception CLASS (``++ValueError``)
    matches by ``isinstance`` — subclasses in, Python semantics — and never a
    logic ``throw/1`` ball: its ``LogicException`` wrapper is excluded from
    both ++ arms unless the catcher names ``LogicException`` itself.  One that
    evaluated to an exception INSTANCE (``++ValueError(M)`` — the escape
    constructs the instance with ``M`` dereferenced) matches by isinstance on
    its type and unifies ``catcher.args`` against ``exc.args``, binding ``M``
    to the real message.  Anything else keeps the structural ``unify`` against
    ``term``, unchanged.

    Rationale: the transliterated ball defeats ``++`` (no object left to
    match) and a bare CamelCase functor catcher is an ISO translation hazard
    (initial-capital reads as a VARIABLE there, silently widening a specific
    catcher to a catch-all).  See
    todo/error-bridge-transliterates-python-exceptions-instead-of-using-plus-plus.md.
    """
    from clausal.logic.variables import deref, unify  # noqa: PLC0415

    catcher = deref(catcher)
    if isinstance(catcher, type) and issubclass(catcher, BaseException):
        # A ++ catcher is the PYTHON side of the boundary only: a logic
        # throw/1 ball travels as a LogicException, which subclasses
        # Exception, so a bare isinstance would let ``++Exception`` swallow
        # logic balls (roborev job 18). Those keep their own catch-all
        # spelling, ``catch(G, _, R)`` — a ++ class matches a logic ball
        # only when it names LogicException (or a subclass) explicitly.
        if isinstance(exc, LogicException) and not issubclass(
                catcher, LogicException):
            return False
        return isinstance(exc, catcher)
    if isinstance(catcher, BaseException):
        if isinstance(exc, LogicException) and not isinstance(
                catcher, LogicException):
            return False
        if not isinstance(exc, type(catcher)):
            return False
        catcher_args = list(catcher.args)
        exc_args = list(exc.args)
        return len(catcher_args) == len(exc_args) and unify(
            catcher_args, exc_args, trail
        )
    return unify(catcher, term, trail)


# ── Structured error term helpers ─────────────────────────────────────────────


def _name_atom(name: Any) -> Any:
    """*name* as an ATOM when it is a spelling, unchanged otherwise.

    Spec §6.4: the type/domain/operation name in a formal error term is an
    atom.  These constructors are also reachable with a name that is not a
    spelling at all — ``throw/1`` can put any term in the type slot, and
    ``must_be/2`` forwards whatever the caller wrote — and building an
    exception must never itself raise, so a non-``str`` passes through as the
    term it is rather than tripping ``mint``'s type check.
    """
    return mint(name) if type(name) is str else name


def type_error(expected_type: str, culprit: Any, context: str = "") -> Compound:
    """Build error(type_error(Type, Culprit), Context).

    Spec §6.4 (2026-09-06-atoms-as-cells-strings): the formal term's
    type/domain/operation NAMES are atoms, minted here so a ``catch/3``
    pattern written in source matches them.  *Culprit* is whatever term was
    at fault and *Context* is human text — a string, not an atom — so
    neither is touched.
    """
    inner = Compound("type_error", (_name_atom(expected_type), culprit))
    return Compound("error", (inner, context))


def instantiation_error(context: str = "") -> Compound:
    """Build error(instantiation_error, Context)."""
    return Compound("error", (mint("instantiation_error"), context))


def existence_error(obj_type: str, culprit: Any, context: str = "") -> Compound:
    """Build error(existence_error(ObjType, Culprit), Context)."""
    inner = Compound("existence_error", (_name_atom(obj_type), culprit))
    return Compound("error", (inner, context))


def permission_error(
    operation: str, obj_type: str, culprit: Any, context: str = ""
) -> Compound:
    """Build error(permission_error(Op, ObjType, Culprit), Context)."""
    inner = Compound("permission_error",
                     (_name_atom(operation), _name_atom(obj_type), culprit))
    return Compound("error", (inner, context))


def domain_error(domain: str, culprit: Any, context: str = "") -> Compound:
    """Build error(domain_error(Domain, Culprit), Context).

    ISO domain error: *culprit* is the right Python/logic type but its value is
    outside the set the operation admits (e.g. an unknown type name given to
    must_be/2, where the TYPE — not the term — is wrong)."""
    inner = Compound("domain_error", (_name_atom(domain), culprit))
    return Compound("error", (inner, context))


def evaluation_error(error_type: str, context: str = "") -> Compound:
    """Build error(evaluation_error(ErrorType), Context).

    ISO evaluation errors: ``zero_divisor``, ``undefined``, ``float_overflow``,
    ``int_overflow``, ``underflow`` — a numeric operation is mathematically
    undefined for its operands (e.g. a non-invertible modular inverse)."""
    inner = Compound("evaluation_error", (_name_atom(error_type),))
    return Compound("error", (inner, context))
