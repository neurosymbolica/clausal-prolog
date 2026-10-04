"""clausal.modules.py.sympy — SymPy integration for Clausal.

Provides symbolic math predicates that accept **native Clausal terms**
directly — no ``sym()`` bootstrapping or ``++()`` escaping required::

    -import_from(sympy, [simplify, solve, diff, sin, cos, inf])

    Test("basic")    <- simplify(X**2 + 2*X + 1 - (X + 1)**2, 0)
    Test("solve")    <- (solve(X**2 - 4, X, S), S == 2)
    Test("diff sin") <- (diff(sin(X), X, R), R == cos(X))
    Test("limit")    <- (limit(1/X, X, inf, R), R == 0)

Design
------
Clausal arithmetic terms (``Add``, ``Mult``, ``Pow``, etc.) are the input
language.  Logic variables (``Var``) inside these terms become SymPy
``Symbol`` objects.  Each predicate call creates a conversion context
that tracks Var-Symbol identity, so the same Var always maps to the
same Symbol within one operation.

Unbound Vars are auto-named alphabetically in discovery order:
first Var -> ``x``, second -> ``y``, etc.  This gives readable ``str()``
output without requiring explicit ``sym("x", X)`` calls.

Results are wrapped in ``SymExpr``, whose ``__eq__`` does symbolic
comparison for PYTHON callers.  Clausal's ``==`` goal is arithmetic and does
NOT use it: ``diff(X**3, X, R), R == 3*X**2`` raises
``domain_error(clpz_expression, ...)``.  Compare symbolically with
``sym_equal/2``::

    diff(X**3, X, R), sym_equal(R, 3*X**2)

Numeric results (Integer, Float) are collapsed to plain Python values.

Math functions (``sin``, ``cos``, ``exp``, ``log``, ``sqrt``, etc.) and
constants (``inf``, ``pi``, ``E``) are importable as term constructors.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.logic.exceptions import LogicException, instantiation_error, type_error
from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline

_sp = _import_stdlib("sympy")
from clausal.terms import (
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate, term_str, DictTerm,
)







# -- Var naming --------------------------------------------------------------

# Auto-assign readable names to anonymous Vars: x, y, z, a, b, c, ...
_ALPHA = list("xyzabcdefghijklmnopqrstuvw")


def _auto_name(index: int) -> str:
    """Generate a readable symbol name for the Nth variable."""
    if index < len(_ALPHA):
        return _ALPHA[index]
    return f"x{index}"


# -- Term <-> SymPy conversion -----------------------------------------------


class _VarSymbol(_sp.Dummy):
    """A SymPy symbol tagged with the Clausal :class:`Var` it came from.

    Used ONLY by ``sympy_term/2`` (see ``_tag_vars``/``_untag_vars``
    below), never by :class:`_ConversionContext`/``var_to_symbol`` itself
    -- those stay exactly as every OTHER predicate (``subs``, ``collect``,
    ``sym_equal``, ...) already relies on them, so this does not change
    how any other predicate maps variables.

    ``sympy_term/2`` round-trips a variable across two SEPARATE predicate
    calls, each with its OWN fresh :class:`_ConversionContext` -- so the
    Var <-> Symbol mapping cannot live only in one context's dict; it has
    to travel WITH the Symbol object that ends up embedded in the SymPy
    expression the first call hands back to the caller. ``sympy_term/2``
    does this as its OWN extra tagging pass, confined to itself.

    This is a :class:`sympy.Dummy`, not a plain :class:`sympy.Symbol`,
    because ``Symbol.__new__`` CACHES by ``(class, name, assumptions)``: two
    separate ``Symbol("x", ...)`` constructions with the same name return
    the literal SAME cached object, so a second variable's tag would
    silently overwrite the first's (confirmed empirically: ``a is b`` for
    two ``Symbol("x", clausal_var=...)`` constructions with different
    tags). ``Dummy`` is SymPy's own mechanism for "guaranteed-unique even
    with the same display name" (it folds a hidden counter into its
    identity), which is exactly "two distinct variables must never share
    a Symbol" and needs no override of equality/hashing. It prints as the
    plain name in ``latex``/``pretty`` output (only its ``str()``/``repr()``
    adds the leading-underscore convention) -- not that it matters here,
    since ``_untag_vars`` always removes it before the term reaches the
    caller.

    The reference to the Var is a plain (strong) attribute, not a
    ``weakref``: Clausal's ``Var`` (a C extension type) does not support
    weak references at all (``weakref.ref(Var())`` raises ``TypeError``),
    so neither a ``WeakKeyDictionary`` nor a ``WeakValueDictionary`` keyed
    or valued by a Var is possible. Tying the reference to the Symbol
    object instead of a separate module-level table means there is
    nothing to leak: the Var stays alive exactly as long as the tagged
    SymPy expression (built fresh by ``_tag_vars`` on every ``sympy_term``
    call, held only by the trail's binding of the Sympy argument) stays
    alive, and once that is unreachable, the Symbol and the Var it tags
    become unreachable too and are collected normally.
    """

    def __new__(cls, name: str, *, clausal_var: Var | None = None, **assumptions):
        obj = super().__new__(cls, name, **assumptions)
        # ``Dummy.__getnewargs_ex__`` (copy/deepcopy/pickle) reconstructs via
        # ``cls(name, dummy_index, **assumptions)`` -- its own positional
        # ``dummy_index``, never ours. Nothing in this module's normal
        # xreplace/free_symbols path copies or pickles a tagged Symbol, so
        # this is a tripwire, not a live path: with ``clausal_var``
        # keyword-only, that reconstruction call now raises ``TypeError``
        # (confirmed empirically) instead of what an EARLIER, positional-arg
        # version of this class did -- silently land the raw dummy_index
        # int in ``_clausal_var`` (RULED 2026-10-02, code review).
        # ``_detag_vars``/``_untag_vars`` both still guard on
        # ``_clausal_var is not None`` regardless, in case a future caller
        # ever constructs one of these without a tag.
        obj._clausal_var = clausal_var
        return obj


def _tag_vars(expr: Any, ctx: "_ConversionContext") -> Any:
    """Replace each plain Symbol *ctx* minted (via ``var_to_symbol``) with
    a :class:`_VarSymbol` carrying the Var it came from, so a LATER,
    independent ``sympy_term/2`` call (fresh context) can recover it.
    Confined to ``sympy_term/2``: *ctx* is a throwaway context created
    just for this one conversion, never shared with any other predicate.

    ``xreplace`` (not ``subs``): an exact structural leaf swap, with no
    re-evaluation/re-simplification pass over the result.
    """
    replace_map = {}
    for name, v in ctx._sym_to_var.items():
        sym = ctx._var_to_sym.get(v._id)
        if sym is not None:
            replace_map[sym] = _VarSymbol(name, clausal_var=v)
    return expr.xreplace(replace_map) if replace_map else expr


def _detag_vars(expr: Any, ctx: "_ConversionContext") -> Any:
    """The inverse half of :func:`_tag_vars`'s containment: an ALREADY-SymPy
    expression handed to ``_to_sympy`` (the "pass-through" case every OTHER
    predicate -- ``subs``, ``sym_equal``, ``sym_str``, ``free_vars``,
    ``collect``, ...) -- may be one ``sympy_term/2`` tagged and handed back
    to the caller. Those predicates have no idea what a ``_VarSymbol`` is;
    left alone, a tagged ``Dummy`` would silently fail to unify/match a
    plain ``Symbol`` for the SAME Var that one of THEM creates afresh (e.g.
    ``subs``'s binding-key conversion), and its ``str()`` leaks a leading
    underscore (RULED 2026-10-02, code review). So every ``_VarSymbol``
    found here is converted via ``_to_sympy_ctx`` -- exactly as if the
    caller had passed the Var directly instead of a pre-tagged sympy
    expression. That is ``_to_sympy_ctx``, NOT ``ctx.var_to_symbol``
    directly (RULED 2026-10-02, code review): the Var may have been
    BOUND since ``sympy_term/2`` tagged it (``sympy_term(S, X+1), X = 2,
    simplify(S, R)`` must give ``R = 3``, not the still-symbolic
    ``x + 1``), and only ``_to_sympy_ctx`` dereferences before deciding
    whether it is still free. A plain, untagged symbol is returned as
    itself (nothing to detag).

    Dereferencing opens a CYCLE the engine's own occurs check cannot see,
    since the Var is reachable only through this opaque Python attribute,
    not through Clausal's own term structure: ``sympy_term(S, X+1), X =
    S`` unifies X with the very sympy expression that has X's tag buried
    inside it, and detagging it recurses forever (RULED 2026-10-02, code
    review: confirmed empirically -- an uncaught ``RecursionError``,
    since every predicate here only catches ``TypeError``/``ValueError``
    around a conversion). Caught here and turned into the ``ValueError``
    those catches already expect, so a cyclic binding becomes an
    ordinary caught conversion failure (-> ``type_error(sympy_expression,
    ...)`` from ``sympy_term/2`` itself, a plain failed goal from
    everything else) instead of a process-level crash.
    """
    tagged = {s for s in expr.free_symbols if isinstance(s, _VarSymbol)}
    if not tagged:
        return expr
    try:
        replace_map = {s: _to_sympy_ctx(s._clausal_var, ctx) for s in tagged
                       if s._clausal_var is not None}
    except RecursionError:
        raise ValueError("sympy_term/2: cyclic variable binding")
    return expr.xreplace(replace_map) if replace_map else expr


def _untag_vars(term: Any) -> Any:
    """Undo :func:`_tag_vars`: replace any :class:`_VarSymbol` leaf left
    in a Clausal term (by ``_from_sympy``'s ordinary "unknown Symbol
    passes through as itself" behaviour) with the Var it carries.
    Confined to ``sympy_term/2`` -- the shared ``_from_sympy_ctx`` engine
    every other predicate runs through never produces or needs to
    understand this tag.
    """
    if isinstance(term, _VarSymbol) and term._clausal_var is not None:
        return term._clausal_var
    if type(term) is tuple:
        if term and type(term[0]) is str:
            return (term[0],) + tuple(_untag_vars(a) for a in term[1:])
        return tuple(_untag_vars(a) for a in term)
    for attr in ("left", "right", "operand"):
        if hasattr(term, attr):
            kwargs = {a: _untag_vars(getattr(term, a))
                      for a in ("left", "right", "operand") if hasattr(term, a)}
            return type(term)(**kwargs)
    return term


class _ConversionContext:
    """Bidirectional mapping between Clausal Vars and SymPy Symbols."""

    __slots__ = ("_var_to_sym", "_sym_to_var", "_counter")

    def __init__(self) -> None:
        self._var_to_sym: dict[int, _sp.Symbol] = {}   # Var._id -> Symbol
        self._sym_to_var: dict[str, Var] = {}           # Symbol.name -> Var
        self._counter: int = 0

    def var_to_symbol(self, v: Var) -> _sp.Symbol:
        """Get or create a SymPy Symbol for a Clausal Var."""
        vid = v._id
        sym = self._var_to_sym.get(vid)
        if sym is not None:
            return sym
        # Auto-assign a readable name
        name = _auto_name(self._counter)
        self._counter += 1
        sym = _sp.Symbol(name)
        self._var_to_sym[vid] = sym
        self._sym_to_var[sym.name] = v
        return sym

    def symbol_to_var(self, sym: _sp.Symbol) -> Var:
        """Get the Clausal Var for a SymPy Symbol, or create a fresh one."""
        v = self._sym_to_var.get(sym.name)
        if v is not None:
            return v
        v = Var()
        self._var_to_sym[v._id] = sym
        self._sym_to_var[sym.name] = v
        return v


def _to_sympy(term: Any, ctx: _ConversionContext | None = None) -> _sp.Expr:
    """Convert a Clausal term to a SymPy expression.

    - Bound Vars are dereferenced first.
    - Free Vars become SymPy Symbols (auto-named if no context).
    - Arithmetic nodes (Add, Sub, ...) map to SymPy operators.
    - Python int/float pass through as SymPy Integer/Float.
    - The cell ("sin", x) -> sympy.sin(x), etc. for known functions.
    """
    if ctx is None:
        ctx = _ConversionContext()
    return _to_sympy_ctx(term, ctx)


def _to_sympy_ctx(term: Any, ctx: _ConversionContext) -> _sp.Expr:
    term = deref(term)

    # Free variable -> Symbol
    if is_var(term):
        return ctx.var_to_symbol(term)

    # Python numeric -> SymPy numeric
    if isinstance(term, bool):
        return _sp.S.true if term else _sp.S.false
    if isinstance(term, int):
        return _sp.Integer(term)
    if isinstance(term, float):
        return _sp.Float(term)

    # SymExpr wrapper -> unwrap
    if isinstance(term, SymExpr):
        term = term._expr

    # Already a SymPy expression (pass-through) -- strip any sympy_term/2
    # _VarSymbol tag first (see _detag_vars): this call's own ctx has no
    # idea what that tag means, and every OTHER predicate that shares
    # this conversion path must keep seeing a plain, ctx-local Symbol.
    if isinstance(term, _sp.Basic):
        return _detag_vars(term, ctx)

    # Binary arithmetic nodes
    _BINOP_MAP = {
        Add: _sp.Add,
        Sub: lambda l, r: _sp.Add(l, _sp.Mul(_sp.Integer(-1), r)),
        Mult: _sp.Mul,
        Pow: _sp.Pow,
    }
    for cls, sp_fn in _BINOP_MAP.items():
        if isinstance(term, cls):
            l = _to_sympy_ctx(term.left, ctx)
            r = _to_sympy_ctx(term.right, ctx)
            return sp_fn(l, r)

    if isinstance(term, Div):
        l = _to_sympy_ctx(term.left, ctx)
        r = _to_sympy_ctx(term.right, ctx)
        return l / r

    if isinstance(term, FloorDiv):
        l = _to_sympy_ctx(term.left, ctx)
        r = _to_sympy_ctx(term.right, ctx)
        return _sp.floor(l / r)

    if isinstance(term, Mod):
        l = _to_sympy_ctx(term.left, ctx)
        r = _to_sympy_ctx(term.right, ctx)
        return _sp.Mod(l, r)

    if isinstance(term, Negate):
        return -_to_sympy_ctx(term.operand, ctx)

    # Compound terms (cells ``(name, *args)``) -> SymPy function calls
    if type(term) is tuple and len(term) >= 2 and type(term[0]) is str:
        fn_name = term[0]
        sp_args = [_to_sympy_ctx(a, ctx) for a in term[1:]]
        sp_fn = _SYMPY_FUNCTIONS.get(fn_name)
        if sp_fn is not None:
            return sp_fn(*sp_args)
        # Unknown functor -> SymPy Function
        return _sp.Function(fn_name)(*sp_args)

    # String symbol name -> SymPy Symbol
    if isinstance(term, str):
        return _sp.Symbol(term)

    # Fallback: try to use as-is (e.g. sympy.pi passed through)
    return _sp.sympify(term)


# Known function name -> SymPy function mapping
_SYMPY_FUNCTIONS: dict[str, Any] = {
    "sin": _sp.sin,
    "cos": _sp.cos,
    "tan": _sp.tan,
    "asin": _sp.asin,
    "acos": _sp.acos,
    "atan": _sp.atan,
    "exp": _sp.exp,
    "log": _sp.log,
    "ln": _sp.log,
    "sqrt": _sp.sqrt,
    "abs": _sp.Abs,
    "factorial": _sp.factorial,
    "gamma": _sp.gamma,
    "ceiling": _sp.ceiling,
    "floor": _sp.floor,
}


def _from_sympy(expr: _sp.Expr, ctx: _ConversionContext | None = None) -> Any:
    """Convert a SymPy expression back to a Clausal term.

    - SymPy Symbols -> Clausal Vars (preserving mapping if ctx provided).
    - SymPy Add/Mul/Pow -> Clausal Add/Mult/Pow nodes.
    - SymPy Integer/Rational -> Python int or Clausal Div.
    - SymPy functions -> the cell ("name", *args).
    """
    if ctx is None:
        ctx = _ConversionContext()
    return _from_sympy_ctx(expr, ctx)


def _from_sympy_ctx(expr: _sp.Expr, ctx: _ConversionContext) -> Any:
    # Symbol -> Var (if known) or pass through as SymPy Symbol (ground value)
    if isinstance(expr, _sp.Symbol):
        v = ctx._sym_to_var.get(expr.name)
        if v is not None:
            return v
        return expr

    # Integer -> int
    if isinstance(expr, _sp.Integer):
        return int(expr)

    # Rational -> keep as Python fraction or Div term
    if isinstance(expr, _sp.Rational):
        n, d = int(expr.p), int(expr.q)
        if d == 1:
            return n
        return Div(left=n, right=d)

    # Float -> float
    if isinstance(expr, _sp.Float):
        return float(expr)

    # Add -> nested Add terms
    if isinstance(expr, _sp.Add):
        args = [_from_sympy_ctx(a, ctx) for a in expr.args]
        result = args[0]
        for a in args[1:]:
            result = Add(left=result, right=a)
        return result

    # Mul -> nested Mult terms (handle negation: -1 * x -> Negate)
    if isinstance(expr, _sp.Mul):
        args = list(expr.args)
        if len(args) >= 2 and args[0] == _sp.Integer(-1):
            inner = args[1:]
            if len(inner) == 1:
                return Negate(operand=_from_sympy_ctx(inner[0], ctx))
            inner_expr = _sp.Mul(*inner)
            return Negate(operand=_from_sympy_ctx(inner_expr, ctx))
        converted = [_from_sympy_ctx(a, ctx) for a in args]
        result = converted[0]
        for a in converted[1:]:
            result = Mult(left=result, right=a)
        return result

    # Pow -> Pow term
    if isinstance(expr, _sp.Pow):
        base = _from_sympy_ctx(expr.args[0], ctx)
        exp = _from_sympy_ctx(expr.args[1], ctx)
        if exp == -1:
            return Div(left=1, right=base)
        return Pow(left=base, right=exp)

    # Mod
    if isinstance(expr, _sp.Mod):
        return Mod(
            left=_from_sympy_ctx(expr.args[0], ctx),
            right=_from_sympy_ctx(expr.args[1], ctx),
        )

    # Known functions -> cell
    for name, sp_fn in _SYMPY_FUNCTIONS.items():
        if isinstance(expr, sp_fn.__class__) or (
            hasattr(sp_fn, "__name__") and type(expr).__name__ == sp_fn.__name__
        ):
            c_args = tuple(_from_sympy_ctx(a, ctx) for a in expr.args)
            return (name, *c_args) if c_args else name   # arity 0: the atom

    # Applied function -> cell
    if isinstance(expr, _sp.Function):
        name = type(expr).__name__
        c_args = tuple(_from_sympy_ctx(a, ctx) for a in expr.args)
        return (name, *c_args) if c_args else name   # arity 0: the atom

    # Derivative, Integral -> cell representation
    if isinstance(expr, _sp.Derivative):
        c_args = tuple(_from_sympy_ctx(a, ctx) for a in expr.args)
        return ("derivative", *c_args)

    if isinstance(expr, _sp.Integral):
        c_args = tuple(_from_sympy_ctx(a, ctx) for a in expr.args)
        return ("integral", *c_args)

    # Infinity, pi, e, etc. -- arity 0, so the ATOM (``foo()`` is not a term)
    if expr is _sp.oo:
        return "inf"
    if expr is _sp.pi:
        return "pi"
    if expr is _sp.E:
        return "e"

    # Order term O(...)
    if isinstance(expr, _sp.Order):
        c_args = tuple(_from_sympy_ctx(a, ctx) for a in expr.args)
        return ("O", *c_args)

    # Fallback: string representation
    return str(expr)


# -- SymExpr wrapper -- symbolic __eq__ for Python callers --------------------


class SymExpr:
    """Thin wrapper around a SymPy expression.

    Overrides ``__eq__`` for PYTHON-side comparison: it converts the other
    operand (e.g. a Clausal ``3*X**2`` term) to SymPy and checks
    ``simplify(a - b) == 0``, with alpha-equivalence for variable names.

    Clausal's ``==`` goal does NOT reach this method: ``==`` is arithmetic
    and raises ``domain_error(clpz_expression, ...)`` on a SymPy result.
    Clausal code compares symbolically with ``sym_equal/2``.
    """

    __slots__ = ("_expr",)

    def __init__(self, expr: _sp.Basic) -> None:
        self._expr = expr

    # -- Symbolic equality ---------------------------------------------------

    def __eq__(self, other: Any) -> bool:
        try:
            if isinstance(other, SymExpr):
                other_expr = other._expr
            elif isinstance(other, _sp.Basic):
                other_expr = other
            else:
                other_expr = _to_sympy(other)

            # Fast path: direct symbolic equality
            if _sp.simplify(self._expr - other_expr) == 0:
                return True

            # Slow path: alpha-equivalence (different Symbol names)
            free_a = self._expr.free_symbols
            free_b = other_expr.free_symbols
            if len(free_a) != len(free_b) or len(free_a) == 0:
                return False
            if len(free_a) <= 5:
                from itertools import permutations
                sorted_a = sorted(free_a, key=str)
                sorted_b = sorted(free_b, key=str)
                for perm in permutations(sorted_b):
                    subs_list = list(zip(sorted_a, perm))
                    renamed = self._expr.subs(subs_list, simultaneous=True)
                    if _sp.simplify(renamed - other_expr) == 0:
                        return True
            return False
        except (TypeError, ValueError):
            return NotImplemented

    def __hash__(self) -> int:
        return hash(self._expr)

    # -- Display -------------------------------------------------------------

    def __str__(self) -> str:
        return str(self._expr)

    def __repr__(self) -> str:
        return str(self._expr)

    # -- Arithmetic -- delegates to SymPy, re-wraps result -------------------

    def _wrap(self, result):
        """Re-wrap a SymPy result so chained arithmetic stays symbolic."""
        if isinstance(result, _sp.Basic):
            return _to_pyval(result)
        return result

    def __add__(self, other):
        return self._wrap(self._expr + (other._expr if isinstance(other, SymExpr) else other))

    def __radd__(self, other):
        return self._wrap((other._expr if isinstance(other, SymExpr) else other) + self._expr)

    def __mul__(self, other):
        return self._wrap(self._expr * (other._expr if isinstance(other, SymExpr) else other))

    def __rmul__(self, other):
        return self._wrap((other._expr if isinstance(other, SymExpr) else other) * self._expr)

    def __sub__(self, other):
        return self._wrap(self._expr - (other._expr if isinstance(other, SymExpr) else other))

    def __rsub__(self, other):
        return self._wrap((other._expr if isinstance(other, SymExpr) else other) - self._expr)

    def __pow__(self, other):
        return self._wrap(self._expr ** (other._expr if isinstance(other, SymExpr) else other))

    def __rpow__(self, other):
        return self._wrap((other._expr if isinstance(other, SymExpr) else other) ** self._expr)

    def __truediv__(self, other):
        return self._wrap(self._expr / (other._expr if isinstance(other, SymExpr) else other))

    def __rtruediv__(self, other):
        return self._wrap((other._expr if isinstance(other, SymExpr) else other) / self._expr)

    def __neg__(self):
        return self._wrap(-self._expr)

    def __pos__(self):
        return self._wrap(self._expr)


# -- Result helpers ----------------------------------------------------------


def _to_pyval(expr: _sp.Basic) -> Any:
    """Collapse trivial SymPy results to Python values, wrap the rest."""
    if isinstance(expr, _sp.Integer):
        return int(expr)
    if isinstance(expr, _sp.Float):
        return float(expr)
    if isinstance(expr, _sp.Rational):
        n, d = int(expr.p), int(expr.q)
        if d == 1:
            return n
    if expr is _sp.S.true:
        return True
    if expr is _sp.S.false:
        return False
    return SymExpr(expr)


def _convert_multi(*terms):
    """Convert multiple Clausal terms to SymPy using a shared context.

    Returns (ctx, *sympy_exprs).
    """
    ctx = _ConversionContext()
    return (ctx,) + tuple(_to_sympy_ctx(t, ctx) for t in terms)


# -- Predicate: sym/2 -- named symbol (still available but rarely needed) ----


def _sym_2(name, result, trail, k):
    """sym/2: sym(name, Result) -- create a SymPy Symbol from a string name."""
    name = deref(name)
    if not isinstance(name, str):
        return
    sym = _sp.Symbol(name)
    if unify(result, sym, trail):
        yield None


# -- Predicate: sympy_term/2 -- explicit bidirectional conversion -----------


def _sympy_term_2(sympy_arg, term_arg, trail, k):
    """sympy_term(Sympy, Term): bidirectional conversion between a SymPy
    expression and a Clausal arithmetic term, in the style of ISO
    ``atom_codes/2``:

    - Sympy already a SymPy expression -> Term is the equivalent Clausal
      term (``_from_sympy``);
    - Sympy unbound, Term bound to anything other than a bare unbound
      variable (a number, an atom, a term that may itself contain
      variables, e.g. ``X+1``) -> Sympy is the equivalent SymPy expression
      (``_to_sympy``);
    - Sympy and Term both unbound -> ``instantiation_error``;
    - Sympy bound to something that is neither a SymPy expression nor
      unbound -> ``type_error(sympy_expression, Sympy)``.

    NOT a true bijection: SymPy canonicalises on construction (``X+X`` ->
    ``2*X``, ``X*1`` -> ``X``, term reordering), so Term -> Sympy -> Term
    returns an EQUIVALENT term, not necessarily the SAME one. Variables
    round-trip exactly (see ``_VarSymbol``): two separate ``sympy_term/2``
    calls sharing a SymPy expression recover the identical Clausal Var,
    and two distinct Vars never collide onto one Symbol even if they
    print with the same auto-assigned name.
    """
    sympy_val = deref(sympy_arg)
    # Every other predicate hands its result back through _to_pyval,
    # which collapses a trivial SymPy value straight to a Python
    # int/float/bool and wraps anything else in SymExpr -- never a bare
    # sympy.Basic. Both are "already a SymPy expression" here too (RULED
    # 2026-10-02, code review: simplify(E, S), sympy_term(S, T) must not
    # raise type_error(sympy_expression, S) just because S is a SymExpr).
    if isinstance(sympy_val, SymExpr):
        sympy_val = sympy_val._expr
    if isinstance(sympy_val, (int, float, bool)):
        # _to_pyval already collapsed a trivial result to exactly this
        # value; Term IS that value -- no need to round-trip it through
        # SymPy and back. (RULED 2026-10-02, code review: a round trip
        # via _sp.sympify(True) -> _from_sympy_ctx DOES lose this one --
        # _from_sympy_ctx has no case for a SymPy Boolean, so it falls to
        # the str(expr) fallback and Term would come back the STRING
        # "True", not the bool True.)
        if unify(term_arg, sympy_val, trail):
            yield None
        return
    if isinstance(sympy_val, _sp.Basic):
        try:
            term = _from_sympy(sympy_val)
        except (TypeError, ValueError):
            raise LogicException(
                type_error("clausal_term", sympy_val, "sympy_term/2: argument 1"))
        term = _untag_vars(term)
        if unify(term_arg, term, trail):
            yield None
        return

    if not is_var(sympy_val):
        # Sympy is bound, but to something that isn't a SymPy expression.
        raise LogicException(
            type_error("sympy_expression", sympy_val, "sympy_term/2: argument 1"))

    term_val = deref(term_arg)
    if is_var(term_val):
        raise LogicException(instantiation_error("sympy_term/2"))

    ctx = _ConversionContext()
    try:
        expr = _to_sympy(term_val, ctx)
    except (TypeError, ValueError):
        raise LogicException(
            type_error("sympy_expression", term_val, "sympy_term/2: argument 2"))
    expr = _tag_vars(expr, ctx)
    if unify(sympy_arg, expr, trail):
        yield None


# -- Predicate: simplify/2 --------------------------------------------------


def _simplify_2(term, result, trail, k):
    """simplify/2: simplify an expression."""
    term = deref(term)
    try:
        expr = _to_sympy(term)
        out = _to_pyval(_sp.simplify(expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: expand/2 ----------------------------------------------------


def _expand_2(term, result, trail, k):
    """expand/2: algebraically expand an expression."""
    term = deref(term)
    try:
        expr = _to_sympy(term)
        out = _to_pyval(_sp.expand(expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: factor/2 ----------------------------------------------------


def _factor_2(term, result, trail, k):
    """factor/2: factor an expression."""
    term = deref(term)
    try:
        expr = _to_sympy(term)
        out = _to_pyval(_sp.factor(expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: solve/3 -- nondeterministic ----------------------------------


def _solve_3(this_generator, _proceed, _fail, _catcher, equation, var, solution, trail):
    """solve/3: solve equation=0 for var, yielding one solution per answer."""
    equation = deref(equation)
    var = deref(var)
    try:
        ctx, eq_expr, var_expr = _convert_multi(equation, var)
        solutions = _sp.solve(eq_expr, var_expr)
    except (TypeError, ValueError):
        yield (_fail, DONE)
        return
    for sol in solutions:
        mark = trail.mark()
        out = _to_pyval(sol)
        if unify(solution, out, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# -- Predicate: solve_all/3 --------------------------------------------------


def _solve_all_3(equation, var, solutions, trail, k):
    """solve_all/3: solve equation, unify solutions with a Python list."""
    equation = deref(equation)
    var = deref(var)
    try:
        ctx, eq_expr, var_expr = _convert_multi(equation, var)
        sols = _sp.solve(eq_expr, var_expr)
        out = [_to_pyval(s) for s in sols]
    except (TypeError, ValueError):
        return
    if unify(solutions, out, trail):
        yield None


# -- Predicate: diff/2,3 ----------------------------------------------------


def _diff_2(term, result, trail, k):
    """diff/2: differentiate w.r.t. the single free variable."""
    term = deref(term)
    try:
        expr = _to_sympy(term)
        free = list(expr.free_symbols)
        if len(free) != 1:
            return
        out = _to_pyval(_sp.diff(expr, free[0]))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _diff_3(term, var, result, trail, k):
    """diff/3: differentiate term w.r.t. specified variable."""
    term = deref(term)
    var = deref(var)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        out = _to_pyval(_sp.diff(expr, var_expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: integrate/2,3 -----------------------------------------------


def _integrate_2(term, result, trail, k):
    """integrate/2: indefinite integral w.r.t. the single free variable."""
    term = deref(term)
    try:
        expr = _to_sympy(term)
        free = list(expr.free_symbols)
        if len(free) != 1:
            return
        out = _to_pyval(_sp.integrate(expr, free[0]))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _integrate_3(term, var, result, trail, k):
    """integrate/3: indefinite integral w.r.t. specified variable."""
    term = deref(term)
    var = deref(var)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        out = _to_pyval(_sp.integrate(expr, var_expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: limit/4 -----------------------------------------------------


def _limit_4(term, var, point, result, trail, k):
    """limit/4: limit of term as var -> point."""
    term = deref(term)
    var = deref(var)
    point = deref(point)
    try:
        ctx, expr, var_expr, pt_expr = _convert_multi(term, var, point)
        out = _to_pyval(_sp.limit(expr, var_expr, pt_expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: series/4,5 --------------------------------------------------


def _series_4(term, var, n, result, trail, k):
    """series/4: Taylor series of term around var=0 to n terms."""
    term = deref(term)
    var = deref(var)
    n = deref(n)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        s = _sp.series(expr, var_expr, 0, int(n))
        out = _to_pyval(s.removeO())
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _series_5(term, var, point, n, result, trail, k):
    """series/5: Taylor series of term around var=point to n terms."""
    term = deref(term)
    var = deref(var)
    point = deref(point)
    n = deref(n)
    try:
        ctx, expr, var_expr, pt_expr = _convert_multi(term, var, point)
        s = _sp.series(expr, var_expr, pt_expr, int(n))
        out = _to_pyval(s.removeO())
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: subs/3 ------------------------------------------------------


def _subs_3(term, bindings, result, trail, k):
    """subs/3: substitute values into an expression.

    bindings is a Python dict {symbol: value} or list of (symbol, value) pairs.
    """
    term = deref(term)
    bindings = deref(bindings)
    try:
        expr = _to_sympy(term)
        if isinstance(bindings, dict):
            sp_subs = {_to_sympy(k_): _to_sympy(v_) for k_, v_ in bindings.items()}
        elif isinstance(bindings, (list, tuple)):
            sp_subs = {}
            for pair in bindings:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    sp_subs[_to_sympy(pair[0])] = _to_sympy(pair[1])
        else:
            return
        out = _to_pyval(expr.subs(sp_subs))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: free_vars/2 --------------------------------------------------


def _free_vars_2(term, vars_list, trail, k):
    """free_vars/2: get list of free symbol names in an expression."""
    term = deref(term)
    try:
        expr = _to_sympy(term)
        names = sorted(str(s) for s in expr.free_symbols)
    except (TypeError, ValueError):
        return
    if unify(vars_list, names, trail):
        yield None


# -- Predicate: sym_equal/2 -- symbolic equality ------------------------------


def _sym_equal_2(a, b, trail, k):
    """sym_equal/2: succeeds if a and b are symbolically equal.

    Each side is converted to SymPy independently.  If they share the same
    Var objects, a shared context ensures matching Symbol names.  If one
    side is an opaque SymPy result (from diff, expand, etc.) and the other
    has fresh Vars, we check alpha-equivalence: whether some consistent
    variable renaming makes the two expressions identical.
    """
    a = deref(a)
    b = deref(b)
    try:
        # Convert with a shared context so same-Var -> same-Symbol
        ctx = _ConversionContext()
        sa = _to_sympy_ctx(a, ctx)
        sb = _to_sympy_ctx(b, ctx)

        # Fast path: direct symbolic equality
        if _sp.simplify(sa - sb) == 0:
            yield None
            return

        # Slow path: alpha-equivalence.
        # One side may be an opaque SymPy result with symbols x, y
        # and the other a Clausal term whose Vars got different names.
        free_a = sa.free_symbols
        free_b = sb.free_symbols
        if len(free_a) != len(free_b):
            return

        n = len(free_a)
        if n == 0:
            return  # Both ground but simplify said they differ

        # For small variable counts, try all permutations
        # (use simultaneous=True so swaps like x<->y happen atomically)
        if n <= 5:
            from itertools import permutations
            sorted_a = sorted(free_a, key=str)
            sorted_b = sorted(free_b, key=str)
            for perm in permutations(sorted_b):
                subs_list = list(zip(sorted_a, perm))
                renamed = sa.subs(subs_list, simultaneous=True)
                if _sp.simplify(renamed - sb) == 0:
                    yield None
                    return

    except (TypeError, ValueError):
        return


# -- Predicate: sym_str/2 -- readable string representation -------------------


def _sym_str_2(term, result, trail, k):
    """sym_str/2: convert an expression to a readable string via SymPy."""
    term = deref(term)
    try:
        expr = _to_sympy(term)
        s = str(expr)
    except (TypeError, ValueError):
        return
    if unify(result, s, trail):
        yield None


# -- Algebra extras ----------------------------------------------------------


def _collect_3(term, var, result, trail, k):
    """collect/3: collect terms by powers of var."""
    term = deref(term)
    var = deref(var)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        out = _to_pyval(_sp.collect(expr, var_expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _cancel_2(term, result, trail, k):
    """cancel/2: cancel common factors in a rational expression."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.cancel(_to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _apart_2(term, result, trail, k):
    """apart/2: partial fraction decomposition w.r.t. the single free variable."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.apart(_to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _apart_3(term, var, result, trail, k):
    """apart/3: partial fraction decomposition w.r.t. specified variable."""
    term = deref(term)
    var = deref(var)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        out = _to_pyval(_sp.apart(expr, var_expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _together_2(term, result, trail, k):
    """together/2: combine fractions over a common denominator."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.together(_to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _degree_2(term, result, trail, k):
    """degree/2: polynomial degree w.r.t. the single free variable."""
    term = deref(term)
    try:
        expr = _to_sympy(term)
        free = list(expr.free_symbols)
        if len(free) != 1:
            return
        out = int(_sp.degree(expr, free[0]))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _degree_3(term, var, result, trail, k):
    """degree/3: polynomial degree w.r.t. specified variable."""
    term = deref(term)
    var = deref(var)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        out = int(_sp.degree(expr, var_expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _coeffs_3(term, var, result, trail, k):
    """coeffs/3: list of polynomial coefficients [highest degree first]."""
    term = deref(term)
    var = deref(var)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        poly = _sp.Poly(expr, var_expr)
        out = [_to_pyval(c) for c in poly.all_coeffs()]
    except (TypeError, ValueError, _sp.GeneratorsNeeded):
        return
    if unify(result, out, trail):
        yield None


def _roots_3(this_generator, _proceed, _fail, _catcher, equation, var, root, trail):
    """roots/3: nondeterministic -- yields (root, multiplicity) pairs."""
    equation = deref(equation)
    var = deref(var)
    try:
        ctx, eq_expr, var_expr = _convert_multi(equation, var)
        root_dict = _sp.roots(eq_expr, var_expr)
    except (TypeError, ValueError):
        yield (_fail, DONE)
        return
    for r, mult in root_dict.items():
        mark = trail.mark()
        pair = (_to_pyval(r), int(mult))
        if unify(root, pair, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# -- Trig --------------------------------------------------------------------


def _trig_simp_2(term, result, trail, k):
    """trig_simp/2: simplify trigonometric expressions."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.trigsimp(_to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _expand_trig_2(term, result, trail, k):
    """expand_trig/2: expand trig functions (e.g. sin(a+b) -> sin(a)cos(b)+cos(a)sin(b))."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.expand_trig(_to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Printing ----------------------------------------------------------------


def _latex_2(term, result, trail, k):
    """latex/2: convert expression to LaTeX string."""
    term = deref(term)
    try:
        s = _sp.latex(_to_sympy(term))
    except (TypeError, ValueError):
        return
    if unify(result, s, trail):
        yield None


def _pretty_2(term, result, trail, k):
    """pretty/2: convert expression to Unicode pretty-print string."""
    term = deref(term)
    try:
        s = _sp.pretty(_to_sympy(term), use_unicode=True)
    except (TypeError, ValueError):
        return
    if unify(result, s, trail):
        yield None


def _mathml_2(term, result, trail, k):
    """math_ml/2: convert expression to math_ml string."""
    term = deref(term)
    try:
        mathml = _sp.printing.mathml.mathml
        s = mathml(_to_sympy(term))
    except (TypeError, ValueError, ImportError):
        return
    if unify(result, s, trail):
        yield None


# -- Number theory -----------------------------------------------------------


def _is_prime_1(n, trail, k):
    """is_prime/1: succeeds if n is prime."""
    n = deref(n)
    if isinstance(n, int) and _sp.isprime(n):
        yield None


def _next_prime_2(n, result, trail, k):
    """next_prime/2: smallest prime greater than n."""
    n = deref(n)
    if not isinstance(n, int):
        return
    if unify(result, int(_sp.nextprime(n)), trail):
        yield None


def _factor_int_2(n, result, trail, k):
    """factor_int/2: prime factorization as dict {prime: exponent}."""
    n = deref(n)
    if not isinstance(n, int):
        return
    try:
        d = DictTerm({int(p): int(e) for p, e in _sp.factorint(n).items()})
    except (TypeError, ValueError):
        return
    if unify(result, d, trail):
        yield None


def _divisors_2(n, result, trail, k):
    """divisors/2: sorted list of positive divisors."""
    n = deref(n)
    if not isinstance(n, int):
        return
    try:
        out = [int(d) for d in _sp.divisors(n)]
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _gcd_sym_3(a, b, result, trail, k):
    """gcd/3: symbolic GCD of two expressions."""
    a = deref(a)
    b = deref(b)
    try:
        ctx, sa, sb = _convert_multi(a, b)
        out = _to_pyval(_sp.gcd(sa, sb))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _lcm_sym_3(a, b, result, trail, k):
    """lcm/3: symbolic LCM of two expressions."""
    a = deref(a)
    b = deref(b)
    try:
        ctx, sa, sb = _convert_multi(a, b)
        out = _to_pyval(_sp.lcm(sa, sb))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Special functions -------------------------------------------------------


def _summation_4(term, var, low, high, result, trail, k):
    """sum_/5: symbolic summation of term for var from low to high."""
    term = deref(term)
    var = deref(var)
    low = deref(low)
    high = deref(high)
    try:
        ctx, expr, var_expr, lo, hi = _convert_multi(term, var, low, high)
        out = _to_pyval(_sp.summation(expr, (var_expr, lo, hi)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _product_sym_4(term, var, low, high, result, trail, k):
    """product/5: symbolic product of term for var from low to high."""
    term = deref(term)
    var = deref(var)
    low = deref(low)
    high = deref(high)
    try:
        ctx, expr, var_expr, lo, hi = _convert_multi(term, var, low, high)
        out = _to_pyval(_sp.product(expr, (var_expr, lo, hi)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _binomial_3(n, k_val, result, trail, k):
    """binomial/3: binomial coefficient C(n, k)."""
    n = deref(n)
    k_val = deref(k_val)
    try:
        out = _to_pyval(_sp.binomial(_to_sympy(n), _to_sympy(k_val)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Math function constructors ----------------------------------------------
#
# These are callable objects that build compound terms (cells).  In .clausal files:
#     -import_from(sympy, [sin, cos, exp, diff])
#     Test("diff sin") <- (diff(sin(X), X, R), R == cos(X))
#
# sin(X) -> the cell ("sin", X) which _to_sympy converts to sympy.sin(Symbol).


class _MathFunc:
    """Callable that produces the cell ``(name, *args)``."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __call__(self, *args):
        return (self._name, *args) if args else self._name   # arity 0: the atom

    def __repr__(self) -> str:
        return self._name


sin = _MathFunc("sin")
cos = _MathFunc("cos")
tan = _MathFunc("tan")
asin = _MathFunc("asin")
acos = _MathFunc("acos")
atan = _MathFunc("atan")
exp = _MathFunc("exp")
log = _MathFunc("log")
ln = _MathFunc("ln")
sqrt = _MathFunc("sqrt")
factorial = _MathFunc("factorial")
abs_ = _MathFunc("abs")

# Constants -- usable directly in term expressions:
#     -import_from(py.sympy, [limit, inf])
#     limit(1/X, X, inf, R)
inf = _sp.oo
pi = _sp.pi
e = _sp.E


# -- Build and export predicate objects --------------------------------------

sym = ModulePredicate("sym")
sym._register(2, simple_to_trampoline(_sym_2))

sympy_term = ModulePredicate("sympy_term")
sympy_term._register(2, simple_to_trampoline(_sympy_term_2))

simplify = ModulePredicate("simplify")
simplify._register(2, simple_to_trampoline(_simplify_2))

expand = ModulePredicate("expand")
expand._register(2, simple_to_trampoline(_expand_2))

factor = ModulePredicate("factor")
factor._register(2, simple_to_trampoline(_factor_2))

solve = ModulePredicate("solve")
solve._register(3, _solve_3)

solve_all = ModulePredicate("solve_all")
solve_all._register(3, simple_to_trampoline(_solve_all_3))

diff = ModulePredicate("diff")
diff._register(2, simple_to_trampoline(_diff_2))
diff._register(3, simple_to_trampoline(_diff_3))

integrate = ModulePredicate("integrate")
integrate._register(2, simple_to_trampoline(_integrate_2))
integrate._register(3, simple_to_trampoline(_integrate_3))

limit = ModulePredicate("limit")
limit._register(4, simple_to_trampoline(_limit_4))

series = ModulePredicate("series")
series._register(4, simple_to_trampoline(_series_4))
series._register(5, simple_to_trampoline(_series_5))

subs = ModulePredicate("subs")
subs._register(3, simple_to_trampoline(_subs_3))

free_vars = ModulePredicate("free_vars")
free_vars._register(2, simple_to_trampoline(_free_vars_2))

sym_equal = ModulePredicate("sym_equal")
sym_equal._register(2, simple_to_trampoline(_sym_equal_2))

sym_str = ModulePredicate("sym_str")
sym_str._register(2, simple_to_trampoline(_sym_str_2))

# Algebra extras
collect = ModulePredicate("collect")
collect._register(3, simple_to_trampoline(_collect_3))

cancel = ModulePredicate("cancel")
cancel._register(2, simple_to_trampoline(_cancel_2))

apart = ModulePredicate("apart")
apart._register(2, simple_to_trampoline(_apart_2))
apart._register(3, simple_to_trampoline(_apart_3))

together = ModulePredicate("together")
together._register(2, simple_to_trampoline(_together_2))

degree = ModulePredicate("degree")
degree._register(2, simple_to_trampoline(_degree_2))
degree._register(3, simple_to_trampoline(_degree_3))

coeffs = ModulePredicate("coeffs")
coeffs._register(3, simple_to_trampoline(_coeffs_3))

roots = ModulePredicate("roots")
roots._register(3, _roots_3)

# Trig
trig_simp = ModulePredicate("trig_simp")
trig_simp._register(2, simple_to_trampoline(_trig_simp_2))

expand_trig = ModulePredicate("expand_trig")
expand_trig._register(2, simple_to_trampoline(_expand_trig_2))

# Printing
latex = ModulePredicate("latex")
latex._register(2, simple_to_trampoline(_latex_2))

pretty = ModulePredicate("pretty")
pretty._register(2, simple_to_trampoline(_pretty_2))

math_ml = ModulePredicate("math_ml")
math_ml._register(2, simple_to_trampoline(_mathml_2))

# Number theory
is_prime = ModulePredicate("is_prime")
is_prime._register(1, simple_to_trampoline(_is_prime_1))

next_prime = ModulePredicate("next_prime")
next_prime._register(2, simple_to_trampoline(_next_prime_2))

factor_int = ModulePredicate("factor_int")
factor_int._register(2, simple_to_trampoline(_factor_int_2))

divisors = ModulePredicate("divisors")
divisors._register(2, simple_to_trampoline(_divisors_2))

gcd = ModulePredicate("gcd")
gcd._register(3, simple_to_trampoline(_gcd_sym_3))

lcm = ModulePredicate("lcm")
lcm._register(3, simple_to_trampoline(_lcm_sym_3))

# Special functions
sum_ = ModulePredicate("sum_")
sum_._register(5, simple_to_trampoline(_summation_4))

product = ModulePredicate("product")
product._register(5, simple_to_trampoline(_product_sym_4))

binomial = ModulePredicate("binomial")
binomial._register(3, simple_to_trampoline(_binomial_3))
