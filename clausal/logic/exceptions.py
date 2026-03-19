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

from clausal.terms import Compound


class LogicException(Exception):
    """Exception carrying a logic term for throw/catch."""

    def __init__(self, term: Any) -> None:
        self.term = term
        super().__init__(f"Uncaught logic exception: {term!r}")


def python_error_term(exc: Exception) -> Compound:
    """Convert a Python exception to a catchable logic term.

    Produces ``python_error(ClassName, Message)`` so that .clausal code can
    match on the exception type and/or message::

        catch(Goal, python_error("UnitsMismatch", MSG), Recovery)
        catch(Goal, python_error(_, _), Recovery)   % any Python error
    """
    return Compound("python_error", (type(exc).__name__, str(exc)))


# ── Structured error term helpers ─────────────────────────────────────────────


def type_error(expected_type: str, culprit: Any, context: str = "") -> Compound:
    """Build error(type_error(Type, Culprit), Context)."""
    inner = Compound("type_error", (expected_type, culprit))
    return Compound("error", (inner, context))


def instantiation_error(context: str = "") -> Compound:
    """Build error(instantiation_error, Context)."""
    return Compound("error", ("instantiation_error", context))


def existence_error(obj_type: str, culprit: Any, context: str = "") -> Compound:
    """Build error(existence_error(ObjType, Culprit), Context)."""
    inner = Compound("existence_error", (obj_type, culprit))
    return Compound("error", (inner, context))


def permission_error(
    operation: str, obj_type: str, culprit: Any, context: str = ""
) -> Compound:
    """Build error(permission_error(Op, ObjType, Culprit), Context)."""
    inner = Compound("permission_error", (operation, obj_type, culprit))
    return Compound("error", (inner, context))
