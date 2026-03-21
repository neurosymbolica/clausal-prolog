"""clausal.logic.clpfd — CLP(FD) finite-domain constraint solver (V2-6).

Provides finite-domain constraint logic programming as a first-class
language feature.  Comparison operators (``==``, ``!=``, ``<``, ``>``,
``<=``, ``>=``) become CLP(FD) constraint operators.  Domains are stored
as AttVar attributes under the ``"fd"`` key.

Domain representation
---------------------
A ``Domain`` is a sorted tuple of ``(lo, hi)`` inclusive integer intervals::

    Domain = tuple[tuple[int, int], ...]

Single-interval fast path: most domains are contiguous ``((lo, hi),)``
which is optimized throughout.

Trail safety
------------
Every domain narrowing or constraint addition creates a **new** ``FDVar``
and calls ``put_attr(var, FD_KEY, new_state, trail)``.  The old ``FDVar``
is restored on backtrack.  Never mutate in place.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from clausal.logic.variables import (
    Var,
    Trail,
    deref,
    is_var,
    unify,
    put_attr,
    get_attr,
    register_attr_hook,
)

# ── Constants ────────────────────────────────────────────────────────────────

FD_KEY = "fd"
DEFAULT_MIN = -(2**63)
DEFAULT_MAX = 2**63

# Type alias for domains: sorted tuple of (lo, hi) inclusive intervals
Domain = tuple[tuple[int, int], ...]


# ── FDVar: per-variable finite-domain state ──────────────────────────────────


class FDVar:
    """Finite-domain state for one variable.

    Immutable for trail safety — narrowing creates a new instance.
    """
    __slots__ = ('domain', 'constraints')

    def __init__(self, domain: Domain, constraints: tuple = ()):
        self.domain = domain
        self.constraints = constraints  # tuple[Constraint, ...]


# ── Domain operations ────────────────────────────────────────────────────────


def domain_from_range(lo: int, hi: int) -> Domain:
    """Create a single-interval domain [lo, hi]."""
    if lo > hi:
        return ()
    return ((lo, hi),)


def domain_contains(domain: Domain, value: int) -> bool:
    """Check if *value* is in the domain."""
    for lo, hi in domain:
        if lo <= value <= hi:
            return True
        if value < lo:
            return False
    return False


def domain_min(domain: Domain) -> int:
    """Minimum value in domain. Raises ValueError on empty."""
    if not domain:
        raise ValueError("empty domain")
    return domain[0][0]


def domain_max(domain: Domain) -> int:
    """Maximum value in domain. Raises ValueError on empty."""
    if not domain:
        raise ValueError("empty domain")
    return domain[-1][1]


def domain_size(domain: Domain) -> int:
    """Number of values in domain."""
    return sum(hi - lo + 1 for lo, hi in domain)


def domain_singleton(domain: Domain) -> int | None:
    """If domain is a single value, return it; otherwise None."""
    if len(domain) == 1:
        lo, hi = domain[0]
        if lo == hi:
            return lo
    return None


def domain_intersection(d1: Domain, d2: Domain) -> Domain:
    """Intersection of two domains."""
    result: list[tuple[int, int]] = []
    i = j = 0
    while i < len(d1) and j < len(d2):
        lo = max(d1[i][0], d2[j][0])
        hi = min(d1[i][1], d2[j][1])
        if lo <= hi:
            result.append((lo, hi))
        if d1[i][1] < d2[j][1]:
            i += 1
        else:
            j += 1
    return tuple(result)


def domain_remove(domain: Domain, value: int) -> Domain:
    """Remove a single value from domain."""
    result: list[tuple[int, int]] = []
    for lo, hi in domain:
        if value < lo or value > hi:
            result.append((lo, hi))
        else:
            if lo < value:
                result.append((lo, value - 1))
            if value < hi:
                result.append((value + 1, hi))
    return tuple(result)


def domain_remove_above(domain: Domain, limit: int) -> Domain:
    """Remove all values > limit from domain."""
    result: list[tuple[int, int]] = []
    for lo, hi in domain:
        if lo > limit:
            break
        result.append((lo, min(hi, limit)))
    return tuple(result)


def domain_remove_below(domain: Domain, limit: int) -> Domain:
    """Remove all values < limit from domain."""
    result: list[tuple[int, int]] = []
    for lo, hi in domain:
        if hi < limit:
            continue
        result.append((max(lo, limit), hi))
    return tuple(result)


def domain_values(domain: Domain):
    """Iterate over all values in domain."""
    for lo, hi in domain:
        yield from range(lo, hi + 1)


# ── Ensure FD state ─────────────────────────────────────────────────────────


def _ensure_fd(var: Var, trail: Trail) -> FDVar:
    """Get or auto-create FDVar for a variable."""
    state = get_attr(var, FD_KEY)
    if state is not None:
        return state
    state = FDVar(domain_from_range(DEFAULT_MIN, DEFAULT_MAX))
    put_attr(var, FD_KEY, state, trail)
    return state


# ── Narrow + propagation queue ───────────────────────────────────────────────


def _narrow(var: Var, new_domain: Domain, trail: Trail, queue: deque) -> bool:
    """Narrow var's domain to new_domain. Returns False on wipeout."""
    if not new_domain:
        return False  # wipeout

    old_state = get_attr(var, FD_KEY)
    old_constraints = old_state.constraints if old_state else ()

    new_state = FDVar(new_domain, old_constraints)
    put_attr(var, FD_KEY, new_state, trail)

    # Keep real interval in sync if present
    from clausal.logic.clpr import REAL_KEY, RealVar
    real_state = get_attr(var, REAL_KEY)
    if real_state is not None:
        fd_lo = float(domain_min(new_domain))
        fd_hi = float(domain_max(new_domain))
        new_lo = max(real_state.lo, fd_lo)
        new_hi = min(real_state.hi, fd_hi)
        if new_lo > new_hi:
            return False
        if new_lo != real_state.lo or new_hi != real_state.hi:
            updated = RealVar(new_lo, new_hi, real_state.constraints)
            put_attr(var, REAL_KEY, updated, trail)

    # Singleton → bind variable
    val = domain_singleton(new_domain)
    if val is not None:
        if not unify(var, val, trail):
            return False

    # Schedule for propagation
    queue.append(var)
    return True


def _narrow_if_changed(var: Var, new_domain: Domain, trail: Trail, queue: deque) -> bool:
    """Narrow only if domain actually changed. Returns False on wipeout."""
    old_state = get_attr(var, FD_KEY)
    if old_state is not None and old_state.domain == new_domain:
        return True  # no change
    return _narrow(var, new_domain, trail, queue)


# ── Constraint base class ───────────────────────────────────────────────────


class Constraint:
    """Base class for FD constraints."""
    __slots__ = ('vars',)

    def __init__(self, vars_: tuple):
        self.vars = vars_

    def propagate(self, trail: Trail, queue: deque) -> bool:
        """Narrow domains. Return False on wipeout."""
        raise NotImplementedError


# ── Concrete constraint types ────────────────────────────────────────────────


class EqConstraint(Constraint):
    """X == Y (or X == expr)."""
    __slots__ = ('lhs', 'rhs')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        super().__init__(_collect_constraint_vars(lhs, rhs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        ld = _expr_domain(lhs, trail)
        rd = _expr_domain(rhs, trail)
        inter = domain_intersection(ld, rd)
        if not inter:
            return False
        if is_var(lhs):
            if not _narrow_if_changed(lhs, inter, trail, queue):
                return False
        if is_var(rhs):
            if not _narrow_if_changed(rhs, inter, trail, queue):
                return False
        return True


class NeConstraint(Constraint):
    """X != Y."""
    __slots__ = ('lhs', 'rhs')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        super().__init__(_collect_constraint_vars(lhs, rhs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        # Only propagate when one side is ground
        if not is_var(lhs) and not is_var(rhs):
            return lhs != rhs
        if not is_var(lhs) and isinstance(lhs, int) and is_var(rhs):
            state = get_attr(rhs, FD_KEY)
            if state is not None:
                new_d = domain_remove(state.domain, lhs)
                return _narrow_if_changed(rhs, new_d, trail, queue)
        if not is_var(rhs) and isinstance(rhs, int) and is_var(lhs):
            state = get_attr(lhs, FD_KEY)
            if state is not None:
                new_d = domain_remove(state.domain, rhs)
                return _narrow_if_changed(lhs, new_d, trail, queue)
        # Both vars — check for singleton
        if is_var(lhs) and is_var(rhs):
            ls = get_attr(lhs, FD_KEY)
            rs = get_attr(rhs, FD_KEY)
            if ls and rs:
                lv = domain_singleton(ls.domain)
                rv = domain_singleton(rs.domain)
                if lv is not None and rv is not None:
                    return lv != rv
                if lv is not None:
                    new_d = domain_remove(rs.domain, lv)
                    return _narrow_if_changed(rhs, new_d, trail, queue)
                if rv is not None:
                    new_d = domain_remove(ls.domain, rv)
                    return _narrow_if_changed(lhs, new_d, trail, queue)
        return True


class LtConstraint(Constraint):
    """X < Y."""
    __slots__ = ('lhs', 'rhs')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        super().__init__(_collect_constraint_vars(lhs, rhs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        ld = _expr_domain(lhs, trail)
        rd = _expr_domain(rhs, trail)
        if not ld or not rd:
            return False
        # X < Y → X's max < max(Y), Y's min > min(X)
        new_ld = domain_remove_above(ld, domain_max(rd) - 1)
        new_rd = domain_remove_below(rd, domain_min(ld) + 1)
        if not new_ld or not new_rd:
            return False
        if is_var(lhs):
            if not _narrow_if_changed(lhs, new_ld, trail, queue):
                return False
        elif domain_min(ld) >= domain_max(rd):
            return False
        if is_var(rhs):
            if not _narrow_if_changed(rhs, new_rd, trail, queue):
                return False
        return True


class LeConstraint(Constraint):
    """X <= Y."""
    __slots__ = ('lhs', 'rhs')

    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs
        super().__init__(_collect_constraint_vars(lhs, rhs))

    def propagate(self, trail: Trail, queue: deque) -> bool:
        lhs = deref(self.lhs)
        rhs = deref(self.rhs)
        ld = _expr_domain(lhs, trail)
        rd = _expr_domain(rhs, trail)
        if not ld or not rd:
            return False
        new_ld = domain_remove_above(ld, domain_max(rd))
        new_rd = domain_remove_below(rd, domain_min(ld))
        if not new_ld or not new_rd:
            return False
        if is_var(lhs):
            if not _narrow_if_changed(lhs, new_ld, trail, queue):
                return False
        elif domain_min(ld) > domain_max(rd):
            return False
        if is_var(rhs):
            if not _narrow_if_changed(rhs, new_rd, trail, queue):
                return False
        return True


class AllDiffConstraint(Constraint):
    """all_different(Vars) — when one var is ground, remove its value from all others."""
    __slots__ = ('all_vars',)

    def __init__(self, vars_: tuple):
        self.all_vars = vars_
        super().__init__(vars_)

    def propagate(self, trail: Trail, queue: deque) -> bool:
        ground_vals: set[int] = set()
        free_vars: list = []
        for v in self.all_vars:
            v = deref(v)
            if is_var(v):
                free_vars.append(v)
            elif isinstance(v, int):
                if v in ground_vals:
                    return False  # duplicate ground value
                ground_vals.add(v)
            else:
                return False  # non-integer
        for v in free_vars:
            state = get_attr(v, FD_KEY)
            if state is None:
                continue
            new_d = state.domain
            for gv in ground_vals:
                new_d = domain_remove(new_d, gv)
            if not _narrow_if_changed(v, new_d, trail, queue):
                return False
        return True


# ── Expression domain computation ────────────────────────────────────────────

# Import term node types lazily to avoid circular imports
_Add = _Sub = _Mult = _Div = _FloorDiv = _Mod = _Pow = _Negate = None


def _ensure_term_imports():
    global _Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate
    if _Add is None:
        from clausal.terms import Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate
        _Add = Add
        _Sub = Sub
        _Mult = Mult
        _Div = Div
        _FloorDiv = FloorDiv
        _Mod = Mod
        _Pow = Pow
        _Negate = Negate


def _expr_domain(expr, trail: Trail) -> Domain:
    """Compute the domain of an expression (Var, int, or arithmetic node)."""
    expr = deref(expr)
    if isinstance(expr, int):
        return ((expr, expr),)
    if is_var(expr):
        state = get_attr(expr, FD_KEY)
        if state is not None:
            return state.domain
        return domain_from_range(DEFAULT_MIN, DEFAULT_MAX)
    _ensure_term_imports()
    if isinstance(expr, _Add):
        ld = _expr_domain(expr.left, trail)
        rd = _expr_domain(expr.right, trail)
        return _domain_add(ld, rd)
    if isinstance(expr, _Sub):
        ld = _expr_domain(expr.left, trail)
        rd = _expr_domain(expr.right, trail)
        return _domain_sub(ld, rd)
    if isinstance(expr, _Mult):
        ld = _expr_domain(expr.left, trail)
        rd = _expr_domain(expr.right, trail)
        return _domain_mult(ld, rd)
    if isinstance(expr, _Negate):
        od = _expr_domain(expr.operand, trail)
        return _domain_negate(od)
    # Fallback: if ground, evaluate
    try:
        val = _eval_ground(expr)
        if val is not None:
            return ((val, val),)
    except Exception:
        pass
    return domain_from_range(DEFAULT_MIN, DEFAULT_MAX)


def _domain_add(d1: Domain, d2: Domain) -> Domain:
    """Bounds-based addition: [a,b] + [c,d] = [a+c, b+d]."""
    if not d1 or not d2:
        return ()
    lo = domain_min(d1) + domain_min(d2)
    hi = domain_max(d1) + domain_max(d2)
    return ((lo, hi),)


def _domain_sub(d1: Domain, d2: Domain) -> Domain:
    """Bounds-based subtraction: [a,b] - [c,d] = [a-d, b-c]."""
    if not d1 or not d2:
        return ()
    lo = domain_min(d1) - domain_max(d2)
    hi = domain_max(d1) - domain_min(d2)
    return ((lo, hi),)


def _domain_mult(d1: Domain, d2: Domain) -> Domain:
    """Bounds-based multiplication."""
    if not d1 or not d2:
        return ()
    corners = [
        domain_min(d1) * domain_min(d2),
        domain_min(d1) * domain_max(d2),
        domain_max(d1) * domain_min(d2),
        domain_max(d1) * domain_max(d2),
    ]
    return ((min(corners), max(corners)),)


def _domain_negate(d: Domain) -> Domain:
    """Negate a domain: -[a,b] = [-b, -a]."""
    if not d:
        return ()
    result = []
    for lo, hi in reversed(d):
        result.append((-hi, -lo))
    return tuple(result)


def _eval_ground(expr):
    """Evaluate an expression if all vars are bound to numbers.

    Returns int or float on success, None if expression contains unbound Vars.
    """
    expr = deref(expr)
    if isinstance(expr, (int, float)) and not isinstance(expr, bool):
        return expr
    if is_var(expr):
        return None
    _ensure_term_imports()
    if isinstance(expr, _Add):
        l = _eval_ground(expr.left)
        r = _eval_ground(expr.right)
        if l is not None and r is not None:
            return l + r
    elif isinstance(expr, _Sub):
        l = _eval_ground(expr.left)
        r = _eval_ground(expr.right)
        if l is not None and r is not None:
            return l - r
    elif isinstance(expr, _Mult):
        l = _eval_ground(expr.left)
        r = _eval_ground(expr.right)
        if l is not None and r is not None:
            return l * r
    elif isinstance(expr, _Div):
        l = _eval_ground(expr.left)
        r = _eval_ground(expr.right)
        if l is not None and r is not None and r != 0:
            return l / r
    elif isinstance(expr, _FloorDiv):
        l = _eval_ground(expr.left)
        r = _eval_ground(expr.right)
        if l is not None and r is not None and r != 0:
            return l // r
    elif isinstance(expr, _Mod):
        l = _eval_ground(expr.left)
        r = _eval_ground(expr.right)
        if l is not None and r is not None and r != 0:
            return l % r
    elif isinstance(expr, _Pow):
        l = _eval_ground(expr.left)
        r = _eval_ground(expr.right)
        if l is not None and r is not None:
            return l ** r
    elif isinstance(expr, _Negate):
        o = _eval_ground(expr.operand)
        if o is not None:
            return -o
    return None


# ── Variable collection ──────────────────────────────────────────────────────


def _collect_constraint_vars(lhs, rhs) -> tuple:
    """Collect all Vars from both sides of a constraint."""
    result: list = []
    _collect_vars_from(lhs, result)
    _collect_vars_from(rhs, result)
    return tuple(result)


def _collect_vars_from(expr, result: list) -> None:
    expr = deref(expr)
    if is_var(expr):
        result.append(expr)
        return
    _ensure_term_imports()
    if isinstance(expr, (_Add, _Sub, _Mult)):
        _collect_vars_from(expr.left, result)
        _collect_vars_from(expr.right, result)
    elif _Div is not None and isinstance(expr, (_Div, _FloorDiv, _Mod)):
        _collect_vars_from(expr.left, result)
        _collect_vars_from(expr.right, result)
    elif _Pow is not None and isinstance(expr, _Pow):
        _collect_vars_from(expr.left, result)
        _collect_vars_from(expr.right, result)
    elif _Negate is not None and isinstance(expr, _Negate):
        _collect_vars_from(expr.operand, result)


# ── Propagation engine (AC-3) ───────────────────────────────────────────────


def propagate(queue: deque, trail: Trail) -> bool:
    """AC-3 fixpoint loop: propagate constraints until stable or wipeout."""
    seen: set[int] = set()
    while queue:
        var = queue.popleft()
        var = deref(var)
        if not is_var(var):
            continue
        vid = id(var)
        if vid in seen:
            continue
        seen.add(vid)
        state = get_attr(var, FD_KEY)
        if state is None:
            continue
        for constraint in state.constraints:
            if not constraint.propagate(trail, queue):
                return False
        # Reset seen for next round since propagation may have changed things
    return True


def _add_constraint(var: Var, constraint: Constraint, trail: Trail) -> None:
    """Attach a constraint to a variable, creating new FDVar (trail-safe)."""
    state = _ensure_fd(var, trail)
    new_state = FDVar(state.domain, state.constraints + (constraint,))
    put_attr(var, FD_KEY, new_state, trail)


def _post_constraint(constraint: Constraint, trail: Trail) -> bool:
    """Attach constraint to all its variables and run initial propagation."""
    for v in constraint.vars:
        v = deref(v)
        if is_var(v):
            _add_constraint(v, constraint, trail)
    queue: deque = deque()
    if not constraint.propagate(trail, queue):
        return False
    return propagate(queue, trail)


# ── Top-level constraint posting functions ───────────────────────────────────


def _is_fd_candidate(x) -> bool:
    """True if x is a Var or an integer (types that participate in CLP(FD))."""
    return is_var(x) or (isinstance(x, int) and not isinstance(x, bool))


def _is_real_arg(x) -> bool:
    """True if x is a float literal or a Var with a real-domain attribute."""
    x = deref(x)
    if isinstance(x, float):
        return True
    if is_var(x):
        from clausal.logic.clpr import REAL_KEY
        return get_attr(x, REAL_KEY) is not None
    return False


def _any_real(l, r) -> bool:
    """True if either argument should use CLP(R) dispatch."""
    return _is_real_arg(l) or _is_real_arg(r)


def _resolve(x):
    """Resolve x: if it's an arithmetic expression tree, try to evaluate it.

    Returns the evaluated integer if fully ground, otherwise the original value.
    """
    _ensure_term_imports()
    if _Add is not None and isinstance(x, (_Add, _Sub, _Mult, _Negate)):
        val = _eval_ground(x)
        if val is not None:
            return val
    if _Div is not None and isinstance(x, (_Div, _FloorDiv, _Mod)):
        val = _eval_ground(x)
        if val is not None:
            return val
    return x


def _both_ground(l, r) -> bool:
    """True if neither side is a Var (both fully resolved)."""
    return not is_var(l) and not is_var(r)


def fd_eq(l, r, trail: Trail) -> bool:
    """Post X == Y.

    Dispatches to CLP(R) if either argument is a float or real variable;
    otherwise posts a CLP(FD) constraint.  For ground non-Var values,
    falls back to Python ``==``.
    """
    l = deref(l)
    r = deref(r)
    l = _resolve(l)
    r = _resolve(r)
    if _any_real(l, r):
        from clausal.logic.clpr import real_eq
        return real_eq(l, r, trail)
    if _both_ground(l, r):
        return l == r
    # At least one Var — use CLP(FD)
    if is_var(l):
        _ensure_fd(l, trail)
    if is_var(r):
        _ensure_fd(r, trail)
    constraint = EqConstraint(l, r)
    return _post_constraint(constraint, trail)


def fd_ne(l, r, trail: Trail) -> bool:
    """Post X != Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    l = _resolve(l)
    r = _resolve(r)
    if _any_real(l, r):
        from clausal.logic.clpr import real_ne
        return real_ne(l, r, trail)
    if _both_ground(l, r):
        return l != r
    if is_var(l):
        _ensure_fd(l, trail)
    if is_var(r):
        _ensure_fd(r, trail)
    constraint = NeConstraint(l, r)
    return _post_constraint(constraint, trail)


def fd_lt(l, r, trail: Trail) -> bool:
    """Post X < Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    l = _resolve(l)
    r = _resolve(r)
    if _any_real(l, r):
        from clausal.logic.clpr import real_lt
        return real_lt(l, r, trail)
    if _both_ground(l, r):
        return l < r
    if is_var(l):
        _ensure_fd(l, trail)
    if is_var(r):
        _ensure_fd(r, trail)
    constraint = LtConstraint(l, r)
    return _post_constraint(constraint, trail)


def fd_le(l, r, trail: Trail) -> bool:
    """Post X <= Y.  Dispatches to CLP(R) when appropriate."""
    l = deref(l)
    r = deref(r)
    l = _resolve(l)
    r = _resolve(r)
    if _any_real(l, r):
        from clausal.logic.clpr import real_le
        return real_le(l, r, trail)
    if _both_ground(l, r):
        return l <= r
    if is_var(l):
        _ensure_fd(l, trail)
    if is_var(r):
        _ensure_fd(r, trail)
    constraint = LeConstraint(l, r)
    return _post_constraint(constraint, trail)


def fd_gt(l, r, trail: Trail) -> bool:
    """Post X > Y.  Dispatches to CLP(R) when appropriate."""
    return fd_lt(r, l, trail)


def fd_ge(l, r, trail: Trail) -> bool:
    """Post X >= Y.  Dispatches to CLP(R) when appropriate."""
    return fd_le(r, l, trail)


# ── FD attribute hook ────────────────────────────────────────────────────────


def _fd_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when an FD-constrained var is unified.

    *attr_value* is the FDVar instance.
    *bound_to* is the value the variable was bound to.
    """
    state = attr_value
    bound_to = deref(bound_to)

    if isinstance(bound_to, int):
        # Check domain membership
        if not domain_contains(state.domain, bound_to):
            return False
        # Propagate constraints
        queue: deque = deque()
        for constraint in state.constraints:
            if not constraint.propagate(trail, queue):
                return False
        return propagate(queue, trail)

    if is_var(bound_to):
        # Unified with another var — merge FD state
        other_state = get_attr(bound_to, FD_KEY)
        if other_state is None:
            # Narrow FD domain against real interval if bound_to has one
            from clausal.logic.clpr import REAL_KEY
            real_state = get_attr(bound_to, REAL_KEY)
            if real_state is not None:
                import math
                r_lo = math.ceil(real_state.lo) if real_state.lo != -math.inf else DEFAULT_MIN
                r_hi = math.floor(real_state.hi) if real_state.hi != math.inf else DEFAULT_MAX
                narrowed = domain_intersection(
                    state.domain, domain_from_range(r_lo, r_hi)
                )
                if not narrowed:
                    return False
                state = FDVar(narrowed, state.constraints)
            put_attr(bound_to, FD_KEY, state, trail)
            # Propagate constraints from transferred state
            val = domain_singleton(state.domain)
            if val is not None:
                if not unify(bound_to, val, trail):
                    return False
            queue = deque()
            for constraint in state.constraints:
                if not constraint.propagate(trail, queue):
                    return False
            return propagate(queue, trail)
        else:
            # Both have FD — intersect domains, merge constraints
            new_domain = domain_intersection(state.domain, other_state.domain)
            if not new_domain:
                return False
            # Deduplicate constraints by identity
            seen_ids: set[int] = set()
            merged: list = []
            for c in state.constraints + other_state.constraints:
                cid = id(c)
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    merged.append(c)
            new_state = FDVar(new_domain, tuple(merged))
            put_attr(bound_to, FD_KEY, new_state, trail)
            # Check singleton
            val = domain_singleton(new_domain)
            if val is not None:
                if not unify(bound_to, val, trail):
                    return False
            # Propagate
            queue = deque()
            for constraint in merged:
                if not constraint.propagate(trail, queue):
                    return False
            return propagate(queue, trail)
        return True

    # Non-integer, non-var → fail
    return False


register_attr_hook(FD_KEY, _fd_hook)


# ── Builtins: in_domain, label, all_different, equivalent ────────────────────


def in_domain(var_or_list, lo, hi, trail: Trail) -> bool:
    """Post domain [lo, hi] on a variable or list of variables."""
    lo = deref(lo)
    hi = deref(hi)
    if not isinstance(lo, int) or not isinstance(hi, int):
        raise TypeError(f"in_domain bounds must be integers, got {lo!r}, {hi!r}")
    new_domain = domain_from_range(lo, hi)
    if not new_domain:
        return False

    targets = deref(var_or_list)
    if isinstance(targets, list):
        for v in targets:
            if not _post_domain(deref(v), new_domain, trail):
                return False
        return True
    return _post_domain(targets, new_domain, trail)


def _post_domain(target, new_domain: Domain, trail: Trail) -> bool:
    """Post domain on a single target."""
    if isinstance(target, int):
        return domain_contains(new_domain, target)
    if not is_var(target):
        return False
    state = get_attr(target, FD_KEY)
    if state is None:
        final_domain = new_domain
    else:
        final_domain = domain_intersection(state.domain, new_domain)
        if not final_domain:
            return False
    # Narrow against real interval if present
    from clausal.logic.clpr import REAL_KEY
    real_state = get_attr(target, REAL_KEY)
    if real_state is not None:
        import math
        r_lo = math.ceil(real_state.lo) if real_state.lo != -math.inf else DEFAULT_MIN
        r_hi = math.floor(real_state.hi) if real_state.hi != math.inf else DEFAULT_MAX
        final_domain = domain_intersection(final_domain, domain_from_range(r_lo, r_hi))
        if not final_domain:
            return False
    old_constraints = state.constraints if state is not None else ()
    new_state = FDVar(final_domain, old_constraints)
    put_attr(target, FD_KEY, new_state, trail)
    val = domain_singleton(final_domain)
    if val is not None:
        if not unify(target, val, trail):
            return False
    return True


def label(vars_list, trail: Trail):
    """Label variables: enumerate all values in domains.

    Uses first-fail strategy: picks the variable with the smallest domain first.
    Generator: yields None for each assignment.
    """
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        vars_list = [vars_list]

    # Collect unbound vars with FD domains
    unbound: list = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            unbound.append(v)

    if not unbound:
        yield None
        return

    # First-fail: pick var with smallest domain
    best = None
    best_size = None
    for v in unbound:
        v = deref(v)
        if not is_var(v):
            continue
        state = get_attr(v, FD_KEY)
        if state is None:
            continue
        sz = domain_size(state.domain)
        if best_size is None or sz < best_size:
            best = v
            best_size = sz

    if best is None:
        # All vars already ground
        yield None
        return

    state = get_attr(best, FD_KEY)
    if state is None:
        yield None
        return

    for val in domain_values(state.domain):
        mark = trail.mark()
        if unify(best, val, trail):
            # Recurse for remaining vars
            yield from label(vars_list, trail)
        trail.undo(mark)


def all_different(vars_list, trail: Trail) -> bool:
    """Post all_different constraint on a list of variables."""
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        return False
    vars_tuple = tuple(deref(v) for v in vars_list)
    constraint = AllDiffConstraint(vars_tuple)
    return _post_constraint(constraint, trail)


import operator as _operator_module

_REIFY_OPS = {
    "eq": _operator_module.eq,
    "ne": _operator_module.ne,
    "lt": _operator_module.lt,
    "le": _operator_module.le,
    "gt": _operator_module.gt,
    "ge": _operator_module.ge,
}


def reify_fd(op: str, x, y, trail: Trail) -> bool | None:
    """Reified FD comparison: three-valued decision.

    op is one of "eq", "ne", "lt", "le", "gt", "ge".
    Returns True (ground-satisfies), False (ground-violates), None (undetermined).
    """
    x = deref(x)
    y = deref(y)
    x = _resolve(x)
    y = _resolve(y)
    if _both_ground(x, y):
        return _REIFY_OPS[op](x, y)
    return None


def equivalent(t1, t2, trail: Trail) -> bool:
    """Structural equality (old == behavior): succeed iff deref'd values are equal."""
    t1 = deref(t1)
    t2 = deref(t2)
    return t1 == t2
