"""clausal.modules.py.sympy — SymPy integration for Clausal.

Provides symbolic math predicates that accept **native Clausal terms**
directly — no ``Sym()`` bootstrapping or ``++()`` escaping required::

    -import_from(sympy, [Simplify, Solve, Diff, sin, cos, inf])

    Test("basic")    <- Simplify(X**2 + 2*X + 1 - (X + 1)**2, 0)
    Test("solve")    <- (Solve(X**2 - 4, X, S), S == 2)
    Test("diff sin") <- (Diff(sin(X), X, R), R == cos(X))
    Test("limit")    <- (Limit(1/X, X, inf, R), R == 0)

Design
------
Clausal arithmetic terms (``Add``, ``Mult``, ``Pow``, etc.) are the input
language.  Logic variables (``Var``) inside these terms become SymPy
``Symbol`` objects.  Each predicate call creates a conversion context
that tracks Var-Symbol identity, so the same Var always maps to the
same Symbol within one operation.

Unbound Vars are auto-named alphabetically in discovery order:
first Var -> ``x``, second -> ``y``, etc.  This gives readable ``str()``
output without requiring explicit ``Sym("x", X)`` calls.

Results are wrapped in ``SymExpr``, which overrides ``__eq__`` to do
symbolic comparison.  This means Clausal's native ``==`` works::

    Diff(X**3, X, R), R == 3*X**2

Numeric results (Integer, Float) are collapsed to plain Python values.

Math functions (``sin``, ``cos``, ``exp``, ``log``, ``sqrt``, etc.) and
constants (``inf``, ``pi``, ``E``) are importable as term constructors.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline

_sp = _import_stdlib("sympy")
from clausal.terms import (
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate, Compound, term_str, DictTerm,
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


def to_sympy(term: Any, ctx: _ConversionContext | None = None) -> _sp.Expr:
    """Convert a Clausal term to a SymPy expression.

    - Bound Vars are dereferenced first.
    - Free Vars become SymPy Symbols (auto-named if no context).
    - Arithmetic nodes (Add, Sub, ...) map to SymPy operators.
    - Python int/float pass through as SymPy Integer/Float.
    - Compound("sin", (x,)) -> sympy.sin(x), etc. for known functions.
    """
    if ctx is None:
        ctx = _ConversionContext()
    return _to_sympy(term, ctx)


def _to_sympy(term: Any, ctx: _ConversionContext) -> _sp.Expr:
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
        return term._expr

    # Already a SymPy expression (pass-through)
    if isinstance(term, _sp.Basic):
        return term

    # Binary arithmetic nodes
    _BINOP_MAP = {
        Add: _sp.Add,
        Sub: lambda l, r: _sp.Add(l, _sp.Mul(_sp.Integer(-1), r)),
        Mult: _sp.Mul,
        Pow: _sp.Pow,
    }
    for cls, sp_fn in _BINOP_MAP.items():
        if isinstance(term, cls):
            l = _to_sympy(term.left, ctx)
            r = _to_sympy(term.right, ctx)
            return sp_fn(l, r)

    if isinstance(term, Div):
        l = _to_sympy(term.left, ctx)
        r = _to_sympy(term.right, ctx)
        return l / r

    if isinstance(term, FloorDiv):
        l = _to_sympy(term.left, ctx)
        r = _to_sympy(term.right, ctx)
        return _sp.floor(l / r)

    if isinstance(term, Mod):
        l = _to_sympy(term.left, ctx)
        r = _to_sympy(term.right, ctx)
        return _sp.Mod(l, r)

    if isinstance(term, Negate):
        return -_to_sympy(term.operand, ctx)

    # Compound terms -> SymPy function calls
    if isinstance(term, Compound):
        fn_name = term.functor
        sp_args = [_to_sympy(a, ctx) for a in term.args]
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


def from_sympy(expr: _sp.Expr, ctx: _ConversionContext | None = None) -> Any:
    """Convert a SymPy expression back to a Clausal term.

    - SymPy Symbols -> Clausal Vars (preserving mapping if ctx provided).
    - SymPy Add/Mul/Pow -> Clausal Add/Mult/Pow nodes.
    - SymPy Integer/Rational -> Python int or Clausal Div.
    - SymPy functions -> Compound("name", args).
    """
    if ctx is None:
        ctx = _ConversionContext()
    return _from_sympy(expr, ctx)


def _from_sympy(expr: _sp.Expr, ctx: _ConversionContext) -> Any:
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
        args = [_from_sympy(a, ctx) for a in expr.args]
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
                return Negate(operand=_from_sympy(inner[0], ctx))
            inner_expr = _sp.Mul(*inner)
            return Negate(operand=_from_sympy(inner_expr, ctx))
        converted = [_from_sympy(a, ctx) for a in args]
        result = converted[0]
        for a in converted[1:]:
            result = Mult(left=result, right=a)
        return result

    # Pow -> Pow term
    if isinstance(expr, _sp.Pow):
        base = _from_sympy(expr.args[0], ctx)
        exp = _from_sympy(expr.args[1], ctx)
        if exp == -1:
            return Div(left=1, right=base)
        return Pow(left=base, right=exp)

    # Mod
    if isinstance(expr, _sp.Mod):
        return Mod(
            left=_from_sympy(expr.args[0], ctx),
            right=_from_sympy(expr.args[1], ctx),
        )

    # Known functions -> Compound
    for name, sp_fn in _SYMPY_FUNCTIONS.items():
        if isinstance(expr, sp_fn.__class__) or (
            hasattr(sp_fn, "__name__") and type(expr).__name__ == sp_fn.__name__
        ):
            c_args = tuple(_from_sympy(a, ctx) for a in expr.args)
            return Compound(name, c_args)

    # Applied function -> Compound
    if isinstance(expr, _sp.Function):
        name = type(expr).__name__
        c_args = tuple(_from_sympy(a, ctx) for a in expr.args)
        return Compound(name, c_args)

    # Derivative, Integral -> Compound representation
    if isinstance(expr, _sp.Derivative):
        c_args = tuple(_from_sympy(a, ctx) for a in expr.args)
        return Compound("derivative", c_args)

    if isinstance(expr, _sp.Integral):
        c_args = tuple(_from_sympy(a, ctx) for a in expr.args)
        return Compound("integral", c_args)

    # Infinity, pi, e, etc.
    if expr is _sp.oo:
        return Compound("inf", ())
    if expr is _sp.pi:
        return Compound("pi", ())
    if expr is _sp.E:
        return Compound("e", ())

    # Order term O(...)
    if isinstance(expr, _sp.Order):
        c_args = tuple(_from_sympy(a, ctx) for a in expr.args)
        return Compound("O", c_args)

    # Fallback: string representation
    return str(expr)


# -- SymExpr wrapper -- makes == do symbolic comparison -----------------------


class SymExpr:
    """Thin wrapper around a SymPy expression.

    Overrides ``__eq__`` so that Clausal's native ``==`` operator does
    symbolic comparison instead of structural comparison.  This means::

        Diff(X**3, X, R) and R == 3*X**2

    just works -- the ``==`` triggers ``SymExpr.__eq__`` which converts
    ``3*X**2`` (a Clausal ``Mult`` term) to SymPy and checks
    ``simplify(a - b) == 0``, with alpha-equivalence for variable names.
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
                other_expr = to_sympy(other)

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
        """Re-wrap SymPy result so == keeps working through chains."""
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
    return (ctx,) + tuple(_to_sympy(t, ctx) for t in terms)


# -- Predicate: Sym/2 -- named symbol (still available but rarely needed) ----


def _sym_2(name, result, trail, k):
    """Sym/2: Sym(name, Result) -- create a SymPy Symbol from a string name."""
    name = deref(name)
    if not isinstance(name, str):
        return
    sym = _sp.Symbol(name)
    if unify(result, sym, trail):
        yield None


# -- Predicate: ToSympy/2 -- explicit conversion -----------------------------


def _to_sympy_2(term, result, trail, k):
    """ToSympy/2: convert Clausal arithmetic term to SymPy expression."""
    term = deref(term)
    try:
        expr = to_sympy(term)
    except (TypeError, ValueError):
        return
    if unify(result, expr, trail):
        yield None


# -- Predicate: FromSympy/2 -- explicit conversion ---------------------------


def _from_sympy_2(expr, result, trail, k):
    """FromSympy/2: convert SymPy expression to Clausal term."""
    expr = deref(expr)
    if not isinstance(expr, _sp.Basic):
        return
    try:
        term = from_sympy(expr)
    except (TypeError, ValueError):
        return
    if unify(result, term, trail):
        yield None


# -- Predicate: Simplify/2 --------------------------------------------------


def _simplify_2(term, result, trail, k):
    """Simplify/2: simplify an expression."""
    term = deref(term)
    try:
        expr = to_sympy(term)
        out = _to_pyval(_sp.simplify(expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: Expand/2 ----------------------------------------------------


def _expand_2(term, result, trail, k):
    """Expand/2: algebraically expand an expression."""
    term = deref(term)
    try:
        expr = to_sympy(term)
        out = _to_pyval(_sp.expand(expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: Factor/2 ----------------------------------------------------


def _factor_2(term, result, trail, k):
    """Factor/2: factor an expression."""
    term = deref(term)
    try:
        expr = to_sympy(term)
        out = _to_pyval(_sp.factor(expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: Solve/3 -- nondeterministic ----------------------------------


def _solve_3(this_generator, _proceed, _fail, _catcher, equation, var, solution, trail):
    """Solve/3: solve equation=0 for var, yielding one solution per answer."""
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


# -- Predicate: SolveAll/3 --------------------------------------------------


def _solve_all_3(equation, var, solutions, trail, k):
    """SolveAll/3: solve equation, unify solutions with a Python list."""
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


# -- Predicate: Diff/2,3 ----------------------------------------------------


def _diff_2(term, result, trail, k):
    """Diff/2: differentiate w.r.t. the single free variable."""
    term = deref(term)
    try:
        expr = to_sympy(term)
        free = list(expr.free_symbols)
        if len(free) != 1:
            return
        out = _to_pyval(_sp.diff(expr, free[0]))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _diff_3(term, var, result, trail, k):
    """Diff/3: differentiate term w.r.t. specified variable."""
    term = deref(term)
    var = deref(var)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        out = _to_pyval(_sp.diff(expr, var_expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: Integrate/2,3 -----------------------------------------------


def _integrate_2(term, result, trail, k):
    """Integrate/2: indefinite integral w.r.t. the single free variable."""
    term = deref(term)
    try:
        expr = to_sympy(term)
        free = list(expr.free_symbols)
        if len(free) != 1:
            return
        out = _to_pyval(_sp.integrate(expr, free[0]))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _integrate_3(term, var, result, trail, k):
    """Integrate/3: indefinite integral w.r.t. specified variable."""
    term = deref(term)
    var = deref(var)
    try:
        ctx, expr, var_expr = _convert_multi(term, var)
        out = _to_pyval(_sp.integrate(expr, var_expr))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: Limit/4 -----------------------------------------------------


def _limit_4(term, var, point, result, trail, k):
    """Limit/4: limit of term as var -> point."""
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


# -- Predicate: Series/4,5 --------------------------------------------------


def _series_4(term, var, n, result, trail, k):
    """Series/4: Taylor series of term around var=0 to n terms."""
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
    """Series/5: Taylor series of term around var=point to n terms."""
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


# -- Predicate: Subs/3 ------------------------------------------------------


def _subs_3(term, bindings, result, trail, k):
    """Subs/3: substitute values into an expression.

    bindings is a Python dict {symbol: value} or list of (symbol, value) pairs.
    """
    term = deref(term)
    bindings = deref(bindings)
    try:
        expr = to_sympy(term)
        if isinstance(bindings, dict):
            sp_subs = {to_sympy(k_): to_sympy(v_) for k_, v_ in bindings.items()}
        elif isinstance(bindings, (list, tuple)):
            sp_subs = {}
            for pair in bindings:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    sp_subs[to_sympy(pair[0])] = to_sympy(pair[1])
        else:
            return
        out = _to_pyval(expr.subs(sp_subs))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Predicate: FreeVars/2 --------------------------------------------------


def _free_vars_2(term, vars_list, trail, k):
    """FreeVars/2: get list of free symbol names in an expression."""
    term = deref(term)
    try:
        expr = to_sympy(term)
        names = sorted(str(s) for s in expr.free_symbols)
    except (TypeError, ValueError):
        return
    if unify(vars_list, names, trail):
        yield None


# -- Predicate: SymEqual/2 -- symbolic equality ------------------------------


def _sym_equal_2(a, b, trail, k):
    """SymEqual/2: succeeds if a and b are symbolically equal.

    Each side is converted to SymPy independently.  If they share the same
    Var objects, a shared context ensures matching Symbol names.  If one
    side is an opaque SymPy result (from Diff, Expand, etc.) and the other
    has fresh Vars, we check alpha-equivalence: whether some consistent
    variable renaming makes the two expressions identical.
    """
    a = deref(a)
    b = deref(b)
    try:
        # Convert with a shared context so same-Var -> same-Symbol
        ctx = _ConversionContext()
        sa = _to_sympy(a, ctx)
        sb = _to_sympy(b, ctx)

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


# -- Predicate: SymStr/2 -- readable string representation -------------------


def _sym_str_2(term, result, trail, k):
    """SymStr/2: convert an expression to a readable string via SymPy."""
    term = deref(term)
    try:
        expr = to_sympy(term)
        s = str(expr)
    except (TypeError, ValueError):
        return
    if unify(result, s, trail):
        yield None


# -- Predicate: Inf/1 -- SymPy infinity (kept for backward compat) ----------


def _inf_1(result, trail, k):
    """Inf/1: unify with SymPy's oo (infinity)."""
    if unify(result, _sp.oo, trail):
        yield None


# -- Algebra extras ----------------------------------------------------------


def _collect_3(term, var, result, trail, k):
    """Collect/3: collect terms by powers of var."""
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
    """Cancel/2: cancel common factors in a rational expression."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.cancel(to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _apart_2(term, result, trail, k):
    """Apart/2: partial fraction decomposition w.r.t. the single free variable."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.apart(to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _apart_3(term, var, result, trail, k):
    """Apart/3: partial fraction decomposition w.r.t. specified variable."""
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
    """Together/2: combine fractions over a common denominator."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.together(to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _degree_2(term, result, trail, k):
    """Degree/2: polynomial degree w.r.t. the single free variable."""
    term = deref(term)
    try:
        expr = to_sympy(term)
        free = list(expr.free_symbols)
        if len(free) != 1:
            return
        out = int(_sp.degree(expr, free[0]))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _degree_3(term, var, result, trail, k):
    """Degree/3: polynomial degree w.r.t. specified variable."""
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
    """Coeffs/3: list of polynomial coefficients [highest degree first]."""
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
    """Roots/3: nondeterministic -- yields (root, multiplicity) pairs."""
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
    """TrigSimp/2: simplify trigonometric expressions."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.trigsimp(to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


def _expand_trig_2(term, result, trail, k):
    """ExpandTrig/2: expand trig functions (e.g. sin(a+b) -> sin(a)cos(b)+cos(a)sin(b))."""
    term = deref(term)
    try:
        out = _to_pyval(_sp.expand_trig(to_sympy(term)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Printing ----------------------------------------------------------------


def _latex_2(term, result, trail, k):
    """Latex/2: convert expression to LaTeX string."""
    term = deref(term)
    try:
        s = _sp.latex(to_sympy(term))
    except (TypeError, ValueError):
        return
    if unify(result, s, trail):
        yield None


def _pretty_2(term, result, trail, k):
    """Pretty/2: convert expression to Unicode pretty-print string."""
    term = deref(term)
    try:
        s = _sp.pretty(to_sympy(term), use_unicode=True)
    except (TypeError, ValueError):
        return
    if unify(result, s, trail):
        yield None


def _mathml_2(term, result, trail, k):
    """MathML/2: convert expression to MathML string."""
    term = deref(term)
    try:
        mathml = _sp.printing.mathml.mathml
        s = mathml(to_sympy(term))
    except (TypeError, ValueError, ImportError):
        return
    if unify(result, s, trail):
        yield None


# -- Number theory -----------------------------------------------------------


def _is_prime_1(n, trail, k):
    """IsPrime/1: succeeds if n is prime."""
    n = deref(n)
    if isinstance(n, int) and _sp.isprime(n):
        yield None


def _next_prime_2(n, result, trail, k):
    """NextPrime/2: smallest prime greater than n."""
    n = deref(n)
    if not isinstance(n, int):
        return
    if unify(result, int(_sp.nextprime(n)), trail):
        yield None


def _factor_int_2(n, result, trail, k):
    """FactorInt/2: prime factorization as dict {prime: exponent}."""
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
    """Divisors/2: sorted list of positive divisors."""
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
    """Product/5: symbolic product of term for var from low to high."""
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
    """Binomial/3: binomial coefficient C(n, k)."""
    n = deref(n)
    k_val = deref(k_val)
    try:
        out = _to_pyval(_sp.binomial(to_sympy(n), to_sympy(k_val)))
    except (TypeError, ValueError):
        return
    if unify(result, out, trail):
        yield None


# -- Math function constructors ----------------------------------------------
#
# These are callable objects that build Compound terms.  In .clausal files:
#     -import_from(sympy, [sin, cos, exp, Diff])
#     Test("diff sin") <- (Diff(sin(X), X, R), R == cos(X))
#
# sin(X) -> Compound("sin", (X,)) which to_sympy converts to sympy.sin(Symbol).


class _MathFunc:
    """Callable that produces Compound("name", args) terms."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __call__(self, *args):
        return Compound(self._name, args)

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
#     -import_from(py.sympy, [Limit, inf])
#     Limit(1/X, X, inf, R)
inf = _sp.oo
pi = _sp.pi
e = _sp.E


# -- Build and export predicate objects --------------------------------------

Sym = ModulePredicate("Sym")
Sym._register(2, simple_to_trampoline(_sym_2))

ToSympy = ModulePredicate("ToSympy")
ToSympy._register(2, simple_to_trampoline(_to_sympy_2))

FromSympy = ModulePredicate("FromSympy")
FromSympy._register(2, simple_to_trampoline(_from_sympy_2))

Simplify = ModulePredicate("Simplify")
Simplify._register(2, simple_to_trampoline(_simplify_2))

Expand = ModulePredicate("Expand")
Expand._register(2, simple_to_trampoline(_expand_2))

Factor = ModulePredicate("Factor")
Factor._register(2, simple_to_trampoline(_factor_2))

Solve = ModulePredicate("Solve")
Solve._register(3, _solve_3)

SolveAll = ModulePredicate("SolveAll")
SolveAll._register(3, simple_to_trampoline(_solve_all_3))

Diff = ModulePredicate("Diff")
Diff._register(2, simple_to_trampoline(_diff_2))
Diff._register(3, simple_to_trampoline(_diff_3))

Integrate = ModulePredicate("Integrate")
Integrate._register(2, simple_to_trampoline(_integrate_2))
Integrate._register(3, simple_to_trampoline(_integrate_3))

Limit = ModulePredicate("Limit")
Limit._register(4, simple_to_trampoline(_limit_4))

Series = ModulePredicate("Series")
Series._register(4, simple_to_trampoline(_series_4))
Series._register(5, simple_to_trampoline(_series_5))

Subs = ModulePredicate("Subs")
Subs._register(3, simple_to_trampoline(_subs_3))

FreeVars = ModulePredicate("FreeVars")
FreeVars._register(2, simple_to_trampoline(_free_vars_2))

SymEqual = ModulePredicate("SymEqual")
SymEqual._register(2, simple_to_trampoline(_sym_equal_2))

SymStr = ModulePredicate("SymStr")
SymStr._register(2, simple_to_trampoline(_sym_str_2))

Inf = ModulePredicate("Inf")
Inf._register(1, simple_to_trampoline(_inf_1))

# Algebra extras
Collect = ModulePredicate("Collect")
Collect._register(3, simple_to_trampoline(_collect_3))

Cancel = ModulePredicate("Cancel")
Cancel._register(2, simple_to_trampoline(_cancel_2))

Apart = ModulePredicate("Apart")
Apart._register(2, simple_to_trampoline(_apart_2))
Apart._register(3, simple_to_trampoline(_apart_3))

Together = ModulePredicate("Together")
Together._register(2, simple_to_trampoline(_together_2))

Degree = ModulePredicate("Degree")
Degree._register(2, simple_to_trampoline(_degree_2))
Degree._register(3, simple_to_trampoline(_degree_3))

Coeffs = ModulePredicate("Coeffs")
Coeffs._register(3, simple_to_trampoline(_coeffs_3))

Roots = ModulePredicate("Roots")
Roots._register(3, _roots_3)

# Trig
TrigSimp = ModulePredicate("TrigSimp")
TrigSimp._register(2, simple_to_trampoline(_trig_simp_2))

ExpandTrig = ModulePredicate("ExpandTrig")
ExpandTrig._register(2, simple_to_trampoline(_expand_trig_2))

# Printing
Latex = ModulePredicate("Latex")
Latex._register(2, simple_to_trampoline(_latex_2))

Pretty = ModulePredicate("Pretty")
Pretty._register(2, simple_to_trampoline(_pretty_2))

MathML = ModulePredicate("MathML")
MathML._register(2, simple_to_trampoline(_mathml_2))

# Number theory
IsPrime = ModulePredicate("IsPrime")
IsPrime._register(1, simple_to_trampoline(_is_prime_1))

NextPrime = ModulePredicate("NextPrime")
NextPrime._register(2, simple_to_trampoline(_next_prime_2))

FactorInt = ModulePredicate("FactorInt")
FactorInt._register(2, simple_to_trampoline(_factor_int_2))

Divisors = ModulePredicate("Divisors")
Divisors._register(2, simple_to_trampoline(_divisors_2))

gcd = ModulePredicate("gcd")
gcd._register(3, simple_to_trampoline(_gcd_sym_3))

lcm = ModulePredicate("lcm")
lcm._register(3, simple_to_trampoline(_lcm_sym_3))

# Special functions
sum_ = ModulePredicate("sum_")
sum_._register(5, simple_to_trampoline(_summation_4))

Product = ModulePredicate("Product")
Product._register(5, simple_to_trampoline(_product_sym_4))

Binomial = ModulePredicate("Binomial")
Binomial._register(3, simple_to_trampoline(_binomial_3))
