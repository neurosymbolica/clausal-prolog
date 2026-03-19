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
    Unify, DoesNotUnify, Evaluate, StructuralEq, StructuralNeq, Lt, LtE, Gt, GtE, In, NotIn,
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


# ── DictTerm — unification-aware dictionary ───────────────────────────────────


class DictTerm:
    """Unification-aware dictionary term.

    Keys must be ground (str, int, or other hashable atoms).
    Values may be Vars, participating in unification.

    Two DictTerms unify iff they have the same key set and values unify pairwise.
    """
    __slots__ = ("_data",)

    def __init__(self, data: dict):
        self._data = dict(data)  # defensive copy

    @property
    def data(self) -> dict:
        return self._data

    def keys(self):   return self._data.keys()
    def values(self): return self._data.values()
    def items(self):  return self._data.items()
    def __len__(self): return len(self._data)
    def __getitem__(self, key): return self._data[key]
    def __contains__(self, key): return key in self._data

    def __eq__(self, other):
        return isinstance(other, DictTerm) and self._data == other._data

    def __hash__(self):
        return hash(frozenset(self._data.items()))

    def __repr__(self):
        inner = ", ".join(f"{k!r}: {v!r}" for k, v in self._data.items())
        return f"DictTerm({{{inner}}})"

    # ── Protocol hooks for C extension ──

    def __walk__(self):
        """Called by C do_walk: return new DictTerm with walked values."""
        from .logic.variables import walk
        new_data = {k: walk(v) for k, v in self._data.items()}
        return DictTerm(new_data)

    def __occurs_check__(self, var):
        """Called by C do_occurs_check: check if var appears in any value."""
        from .logic.variables import occurs_check
        return any(occurs_check(var, v) for v in self._data.values())

    def __unify__(self, other, trail):
        """Called by C do_unify: pairwise value unification."""
        if not isinstance(other, DictTerm):
            return NotImplemented
        if self._data.keys() != other._data.keys():
            return False
        from .logic.variables import unify
        mark = trail.mark()
        for key in self._data:
            if not unify(self._data[key], other._data[key], trail):
                trail.undo(mark)
                return False
        return True


# ── SetTerm — unification-aware set ──────────────────────────────────────────


class SetTerm:
    """Unification-aware set term.

    Elements must be ground (hashable). Backed by frozenset for immutability.
    Two SetTerms unify iff they contain the same elements.
    """
    __slots__ = ("_elements",)

    def __init__(self, elements):
        self._elements = frozenset(elements)

    @property
    def elements(self) -> frozenset:
        return self._elements

    def __len__(self): return len(self._elements)
    def __contains__(self, item): return item in self._elements
    def __iter__(self): return iter(self._elements)

    def __eq__(self, other):
        return isinstance(other, SetTerm) and self._elements == other._elements

    def __hash__(self):
        return hash(self._elements)

    def __repr__(self):
        inner = ", ".join(repr(e) for e in sorted(self._elements, key=repr))
        return f"SetTerm({{{inner}}})"

    def __unify__(self, other, trail):
        """Called by C do_unify: element-wise equality (elements are ground)."""
        if not isinstance(other, SetTerm):
            return NotImplemented
        return self._elements == other._elements


# ── Dimensioned — number with physical dimensions ─────────────────────────────


class UnitsMismatch(Exception):
    """Raised when dimensioned quantities with incompatible units are combined."""


def _dim_name(k) -> str:
    """Return a short display name for a dimension key (predicate or string)."""
    return k._name if hasattr(k, "_name") else str(k)


def _dims_str(dims: dict) -> str:
    """Human-readable dimension string, e.g. 'm·s^-2'."""
    if not dims:
        return "1"
    parts = []
    for k in sorted(dims, key=_dim_name):
        v = dims[k]
        name = _dim_name(k)
        parts.append(name if v == 1 else f"{name}^{v}")
    return "·".join(parts)


class Dimensioned:
    """A number with physical dimensions for dimensional analysis.

    ``dims`` maps dimension keys (arbitrary atoms/strings) to integer exponents.
    Zero-valued exponents are removed automatically.  The empty dict means
    dimensionless.  Internally all values are stored in SI base units; named-unit
    predicates (``Meter``, ``Newton``, ``Watt``, …) in ``clausal.modules.units``
    handle scaling on the way in/out.

    Arithmetic:
        - ``+`` / ``-`` require identical dimension dicts; raises ``UnitsMismatch``
          otherwise.
        - ``*`` / ``/`` merge dimension dicts by addition / subtraction.
        - ``**`` scales every exponent by an integer constant; raises
          ``UnitsMismatch`` if the exponent is non-integer or has dimensions.
        - Plain numeric scalars (int/float) can be multiplied/divided freely.

    Clausal protocol:
        - ``__unify__`` — checks dims equality then unifies values.

    Uninstantiated dimensioned slots are plain ``AttVar`` objects carrying a
    ``"units"`` attribute (see ``clausal.logic.units_constraint``).  A
    ``Dimensioned`` always holds a ground numeric value — never a logic var.
    """

    __slots__ = ("_value", "_dims")

    def __init__(self, value, dims: dict) -> None:
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_dims", {k: v for k, v in dims.items() if v != 0})

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def value(self):
        return self._value

    @property
    def dims(self) -> dict:
        return dict(self._dims)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _require_same_dims(self, other: "Dimensioned", op: str) -> None:
        if not isinstance(other, Dimensioned):
            raise UnitsMismatch(
                f"Cannot {op} dimensioned ({_dims_str(self._dims)}) "
                f"with plain value {other!r}"
            )
        if self._dims != other._dims:
            raise UnitsMismatch(
                f"Unit mismatch for {op}: "
                f"{_dims_str(self._dims)} vs {_dims_str(other._dims)}"
            )

    @staticmethod
    def _merge_dims(a: dict, b: dict, sign: int) -> dict:
        """Return a merged dims dict: a + sign*b, zeros removed."""
        result = dict(a)
        for k, v in b.items():
            new_v = result.get(k, 0) + sign * v
            if new_v:
                result[k] = new_v
            else:
                result.pop(k, None)
        return result

    # ── Arithmetic ──────────────────────────────────────────────────────────

    def __add__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            return Dimensioned(self._value + other, {})
        self._require_same_dims(other, "add")
        return Dimensioned(self._value + other._value, self._dims)

    def __radd__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            return Dimensioned(other + self._value, {})
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            return Dimensioned(self._value - other, {})
        self._require_same_dims(other, "subtract")
        return Dimensioned(self._value - other._value, self._dims)

    def __rsub__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            return Dimensioned(other - self._value, {})
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, Dimensioned):
            new_dims = self._merge_dims(self._dims, other._dims, +1)
            return Dimensioned(self._value * other._value, new_dims)
        return Dimensioned(self._value * other, self._dims)

    def __rmul__(self, other):
        return Dimensioned(other * self._value, self._dims)

    def __truediv__(self, other):
        if isinstance(other, Dimensioned):
            new_dims = self._merge_dims(self._dims, other._dims, -1)
            return Dimensioned(self._value / other._value, new_dims)
        return Dimensioned(self._value / other, self._dims)

    def __rtruediv__(self, other):
        new_dims = {k: -v for k, v in self._dims.items()}
        return Dimensioned(other / self._value, new_dims)

    def __pow__(self, exp):
        if isinstance(exp, Dimensioned):
            if exp._dims:
                raise UnitsMismatch("Exponent cannot have dimensions")
            exp = exp._value
        if not isinstance(exp, int):
            if self._dims:
                raise UnitsMismatch(
                    f"Exponent must be an integer constant for dimensional "
                    f"quantities, got {exp!r}"
                )
            # Dimensionless: allow any numeric exponent (e.g. sqrt via ** 0.5)
            return Dimensioned(self._value ** exp, {})
        new_dims = {k: v * exp for k, v in self._dims.items() if v * exp != 0}
        return Dimensioned(self._value ** exp, new_dims)

    def __neg__(self):
        return Dimensioned(-self._value, self._dims)

    def __abs__(self):
        return Dimensioned(abs(self._value), self._dims)

    def __pos__(self):
        return self

    # ── Comparisons (same dims required) ────────────────────────────────────

    def _cmp_value(self, other):
        """Return (self_val, other_val) after verifying same dims, or raise."""
        if isinstance(other, Dimensioned):
            if self._dims != other._dims:
                raise UnitsMismatch(
                    f"Cannot compare {_dims_str(self._dims)} "
                    f"with {_dims_str(other._dims)}"
                )
            return self._value, other._value
        if not self._dims:
            return self._value, other
        raise UnitsMismatch(
            f"Cannot compare dimensioned ({_dims_str(self._dims)}) "
            f"with plain value {other!r}"
        )

    def __lt__(self, other):
        a, b = self._cmp_value(other)
        return a < b

    def __le__(self, other):
        a, b = self._cmp_value(other)
        return a <= b

    def __gt__(self, other):
        a, b = self._cmp_value(other)
        return a > b

    def __ge__(self, other):
        a, b = self._cmp_value(other)
        return a >= b

    def __eq__(self, other):
        if isinstance(other, Dimensioned):
            return self._dims == other._dims and self._value == other._value
        return NotImplemented

    def __hash__(self):
        return hash((self._value, frozenset(self._dims.items())))

    # ── Representation ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"Dimensioned({self._value!r}, {self._dims!r})"

    def __str__(self) -> str:
        return f"{self._value} {_dims_str(self._dims)}"

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)

    # ── Clausal unification protocol ─────────────────────────────────────────

    def __unify__(self, other, trail) -> bool:
        """Called by C do_unify: dims must match exactly; values are unified."""
        if not isinstance(other, Dimensioned):
            return NotImplemented
        if self._dims != other._dims:
            return False
        from .logic.variables import unify
        return unify(self._value, other._value, trail)


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


# ── Deferred Python expression thunk ──────────────────────────────────────────

class PyThunk:
    """Deferred Python expression: a lambda evaluated at search time.

    The lambda takes the dereferenced values of logic variables as positional
    arguments and returns the result.  ``var_objects`` is a list of ``Var``
    instances (in parameter order) so the compiler can map each to its local
    variable name via ``var_context`` and emit ``fn(deref(v0), ...)``.

    Used for:
    - **f-strings in .clausal files**: ``f"Hello, {NAME}!"`` — the lambda
      contains the native f-string, returns a formatted string.
    - **``++()`` Python escape in logic terms**: ``++len(X_)`` — the lambda
      wraps the Python expression, returns any Python value.

    The lambda keeps the Python code native — no term transformation — so any
    Python expression (method calls, builtins, arithmetic, etc.) works.
    """
    __slots__ = ('fn', 'var_objects')

    def __init__(self, fn, var_objects):
        self.fn = fn
        self.var_objects = tuple(var_objects)

    def __repr__(self):
        return f"PyThunk({self.fn!r}, {self.var_objects!r})"


# Backward-compat alias — f-string thunks use the same mechanism.
FStringThunk = PyThunk


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
    if isinstance(t, Compound):
        return str(t)
    if isinstance(t, KWTerm):
        args = ", ".join(f"{k}={term_str(v)}" for k, v in t.items())
        return f"{t.functor}({args})"
    if isinstance(t, DictTerm):
        inner = ", ".join(f"{term_str(k)}: {term_str(v)}" for k, v in t.items())
        return "{" + inner + "}"
    if isinstance(t, SetTerm):
        inner = ", ".join(term_str(e) for e in sorted(t.elements, key=repr))
        return "{" + inner + "}"
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
    "DictTerm",
    "SetTerm",

    "KWTerm",
    "PyThunk",
    "FStringThunk",
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
    "Unify", "DoesNotUnify", "Evaluate", "StructuralEq", "StructuralNeq", "Lt", "LtE", "Gt", "GtE", "In", "NotIn",
    # Expression nodes
    "Call", "LoadName", "LoadAttr", "LoadSubscript", "Slice",
    # Predicate clause term
    "Predicate",
]
