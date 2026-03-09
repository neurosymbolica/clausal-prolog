"""clausal.terms — logic term layer.

Functor types and value types for the clausal logic programming system.

Python built-in types (int, float, str, bool, None, list) are terms directly —
no wrapper needed.  Logic variables are Var objects.  Structured terms are
instances of user-defined dataclasses (one class per functor) or Compound for
runtime-constructed terms.

Goal types are term types: the same classes serve as goal nodes when they appear
in a predicate body.  The compiler dispatches on the class via Python's match
statement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .logic.variables import Var

# Re-export operator/expression classes already defined in pythonic_ast.
# They are plain dataclasses that work as both terms and goal nodes.
from .pythonic_ast.nodes import (
    # Arithmetic binary operators
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    # Bitwise / shift binary operators
    BitAnd, BitOr, BitXor, LShift, RShift,
    # Boolean binary operators (also conjunction / disjunction goals)
    And, Or,
    # Unary operators
    Not, Invert, Negate,
    # Comparison / unification operators
    Is, IsNot, Eq, NotEq, Lt, LtE, Gt, GtE, In, NotIn,
    # Expression nodes used in predicate bodies
    Call, LoadName, LoadAttr, LoadSubscript, Slice,
    # Predicate clause term
    Predicate,
)


# ── New term types ─────────────────────────────────────────────────────────────

@dataclass
class Compound:
    """Fallback for runtime-constructed or unknown-functor compound terms.

    Use when no compile-time dataclass exists for the functor, e.g.:
        Compound("cons", (head, tail))
        Compound(functor_var, args)
    """
    functor: str | Var
    args: tuple

    def __str__(self) -> str:
        args_str = ", ".join(term_str(a) for a in self.args)
        f = self.functor if isinstance(self.functor, str) else term_str(self.functor)
        return f"{f}({args_str})"


@dataclass
class ArithConstraint:
    """Stub node for the future CLP(FD) arithmetic constraint operator (==+).

    Constructed by the transformer when it sees ``X ==+ expr`` or ``X == +expr``.
    The compiler raises NotImplementedError when it encounters this node, marking
    the CLP(FD) integration point.
    """
    expr: Any
    position: tuple | None = field(default=None, repr=False, compare=False)

    def __str__(self) -> str:
        return f"==+({term_str(self.expr)})"


# ── Open-world keyword term ────────────────────────────────────────────────────


class KWTerm:
    """Open-world keyword term — any functor, any keywords, dict-backed.

    For runtime-constructed terms where the functor has no compile-time class.
    Attributes are read from the backing dict.  Iteration yields values in
    insertion order.  Equality and unification match by keyword name (not
    position): ``KWTerm('r', a=1, b=2) == KWTerm('r', b=2, a=1)``.
    """

    __slots__ = ("_functor", "_fields")

    def __init__(self, functor: str, **kwargs: Any) -> None:
        object.__setattr__(self, "_functor", functor)
        object.__setattr__(self, "_fields", dict(kwargs))

    @property
    def functor(self) -> str:
        return self._functor

    def __getattr__(self, name: str) -> Any:
        try:
            return self._fields[name]
        except KeyError:
            raise AttributeError(
                f"KWTerm {self._functor!r} has no field {name!r}"
            ) from None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, KWTerm):
            return (
                self._functor == other._functor
                and self._fields == other._fields
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._functor, tuple(sorted(self._fields.items()))))

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self._fields.items())
        return f"KWTerm({self._functor!r}, {args})"

    def keys(self):
        return self._fields.keys()

    def values(self):
        return self._fields.values()

    def items(self):
        return self._fields.items()

    def __len__(self) -> int:
        return len(self._fields)

    def with_overrides(self, **overrides: Any) -> "KWTerm":
        """Return a new KWTerm with specified fields replaced."""
        new_fields = dict(self._fields)
        for k in overrides:
            if k not in new_fields:
                raise KeyError(f"KWTerm {self._functor!r} has no field {k!r}")
        new_fields.update(overrides)
        return KWTerm(self._functor, **new_fields)

    def with_extensions(self, **extensions: Any) -> "KWTerm":
        """Return a new KWTerm with additional fields appended."""
        new_fields = dict(self._fields)
        for k in extensions:
            if k in new_fields:
                raise KeyError(
                    f"KWTerm {self._functor!r} already has field {k!r}"
                )
        new_fields.update(extensions)
        return KWTerm(self._functor, **new_fields)


# ── Cons / list helpers ────────────────────────────────────────────────────────

def list_to_cons(lst: list) -> object:
    """Convert a Python list to explicit Prolog-style cons structure.

    list_to_cons([1, 2, 3])  →  Compound("cons", (1, Compound("cons", (2, ...))))
    """
    result: object = Compound("nil", ())
    for elem in reversed(lst):
        result = Compound("cons", (elem, result))
    return result


def cons_to_list(term: object) -> list:
    """Convert a Prolog-style cons structure back to a Python list.

    Raises ValueError if term is not a proper nil-terminated cons chain.
    """
    result = []
    while isinstance(term, Compound) and term.functor == "cons" and len(term.args) == 2:
        result.append(term.args[0])
        term = term.args[1]
    if not (isinstance(term, Compound) and term.functor == "nil" and len(term.args) == 0):
        raise ValueError(f"Not a proper list: {term!r}")
    return result


# ── Readable term representation ───────────────────────────────────────────────

def term_str(t: Any) -> str:
    """Return a readable string representation of any term."""
    if t is None:
        return "None"
    if t is ...:
        return "..."
    if isinstance(t, bool):
        return str(t)
    if isinstance(t, (int, float, complex)):
        return repr(t)
    if isinstance(t, str):
        return repr(t)
    if isinstance(t, bytes):
        return repr(t)
    if isinstance(t, list):
        return "[" + ", ".join(term_str(e) for e in t) + "]"
    if isinstance(t, Var):
        return repr(t)
    if isinstance(t, (Compound, ArithConstraint)):
        return str(t)
    if isinstance(t, KWTerm):
        args = ", ".join(f"{k}={term_str(v)}" for k, v in t.items())
        return f"{t.functor}({args})"

    cls = type(t)
    op = getattr(cls, "op", None)

    # BinOp-style: left op right
    if op is not None and hasattr(t, "left") and hasattr(t, "right"):
        return f"({term_str(t.left)} {op} {term_str(t.right)})"

    # UnaryOp-style: op operand
    if op is not None and hasattr(t, "operand"):
        operand_str = term_str(t.operand)
        if op.isalpha():
            return f"{op} {operand_str}"
        return f"{op}{operand_str}"

    if isinstance(t, Call):
        args_str = ", ".join(term_str(a) for a in t.args)
        return f"{term_str(t.func)}({args_str})"
    if isinstance(t, LoadName):
        return t.name
    if isinstance(t, Predicate):
        return f"{term_str(t.head)} <- {term_str(t.body)}"

    return repr(t)


# ── Public API ─────────────────────────────────────────────────────────────────

__all__ = [
    # Logic variable
    "Var",
    # New term types
    "Compound",
    "KWTerm",
    "ArithConstraint",
    # Helpers
    "list_to_cons",
    "cons_to_list",
    "term_str",
    # Arithmetic binary operators
    "Add", "Sub", "Mult", "Div", "FloorDiv", "Mod", "Pow",
    # Bitwise / shift binary operators
    "BitAnd", "BitOr", "BitXor", "LShift", "RShift",
    # Boolean binary operators
    "And", "Or",
    # Unary operators
    "Not", "Invert", "Negate",
    # Comparison / unification operators
    "Is", "IsNot", "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE", "In", "NotIn",
    # Expression nodes
    "Call", "LoadName", "LoadAttr", "LoadSubscript", "Slice",
    # Predicate clause term
    "Predicate",
]
