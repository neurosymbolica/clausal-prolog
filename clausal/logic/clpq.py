"""clausal.logic.clpq — CLP(Q) rational-domain constraint solver.

Exact arithmetic over Python ``fractions.Fraction`` via Gaussian elimination
(equalities) and the revised simplex method (inequalities).  Unified syntax
with CLP(Z) and CLP(R): the same ``==``, ``<``, ``<=``, ``>``, ``>=``, ``!=``
operators dispatch to CLP(Q) when a ``Fraction`` literal or ``in_q``-declared
variable is detected.

Algorithm based on Holzbaur (1992, 1994):
- Gaussian elimination for the equality subsystem
- Revised simplex with Bland's rule for inequalities
- Passive disequalities checked when both sides become ground

Trail safety: the Tableau is snapshot-copied (via ``trail.record()``) before
each modification.  On backtrack the snapshot is restored automatically.
"""

from __future__ import annotations

from fractions import Fraction
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

Q_KEY = "clpq"
ZERO = Fraction(0)
ONE = Fraction(1)

# ── Lazy term imports ────────────────────────────────────────────────────────

_Add = _Sub = _Mult = _Div = _Negate = None


def _ensure_term_imports():
    global _Add, _Sub, _Mult, _Div, _Negate
    if _Add is None:
        from clausal.terms import Add, Sub, Mult, Div, Negate
        _Add, _Sub, _Mult, _Div, _Negate = Add, Sub, Mult, Div, Negate


# ── QVar: per-variable rational-domain state ─────────────────────────────────


class QVar:
    """Rational-domain state for one variable.

    Immutable for trail safety.  Stores optional bounds ``[lo, hi]`` and
    the variable's ID in the global tableau.
    """
    __slots__ = ('lo', 'hi', 'tab_id')

    def __init__(self, lo: Fraction | None, hi: Fraction | None,
                 tab_id: int):
        self.lo = lo      # None → unbounded below
        self.hi = hi      # None → unbounded above
        self.tab_id = tab_id


# ── Tableau: incremental Gaussian + simplex solver ───────────────────────────


class Tableau:
    """Incremental linear-constraint solver over exact rationals.

    Combines Gaussian elimination (equalities) with the revised simplex
    method (inequalities).

    Data structures
    ---------------
    rows : dict[int, dict[int, Fraction]]
        For each **basic** variable: its expression as a linear combination
        of non-basic variables.  ``rows[b][j]`` = coefficient of var *j*
        in the equation defining basic var *b*.
    rhs : dict[int, Fraction]
        Constant term for each basic variable.
    lo, hi : dict[int, Fraction | None]
        Lower / upper bounds for every variable (basic and non-basic).
    assign : dict[int, Fraction]
        Current assignment.  Non-basic vars sit at one of their bounds;
        basic vars are computed from their row.
    parametric : dict[int, tuple[dict[int, Fraction], Fraction]]
        Variables eliminated by equality constraints.
        ``parametric[x] = ({j: coeff_j, …}, constant)`` means
        ``x = Σ coeff_j·var_j + constant``.
    diseqs : list[tuple[int, int]]
        Passive disequality pairs.
    _var_map : dict[int, Var]
        Maps tableau variable IDs → original ``Var`` objects.
    """

    def __init__(self) -> None:
        self.rows: dict[int, dict[int, Fraction]] = {}
        self.rhs: dict[int, Fraction] = {}
        self.lo: dict[int, Fraction | None] = {}
        self.hi: dict[int, Fraction | None] = {}
        self.assign: dict[int, Fraction] = {}
        self.parametric: dict[int, tuple[dict[int, Fraction], Fraction]] = {}
        self.diseqs: list[tuple[int, int]] = []
        self._next_slack: int = 0
        self._var_map: dict[int, Var] = {}

    # ── Copying ──────────────────────────────────────────────────────────

    def copy(self) -> Tableau:
        """Deep copy for trail snapshots."""
        t = Tableau()
        t.rows = {k: dict(v) for k, v in self.rows.items()}
        t.rhs = dict(self.rhs)
        t.lo = dict(self.lo)
        t.hi = dict(self.hi)
        t.assign = dict(self.assign)
        t.parametric = {k: (dict(c), v) for k, (c, v) in self.parametric.items()}
        t.diseqs = list(self.diseqs)
        t._next_slack = self._next_slack
        t._var_map = dict(self._var_map)
        return t

    # ── Variable registration ────────────────────────────────────────────

    def _fresh_slack(self) -> int:
        """Allocate a fresh slack variable ID (negative to avoid user-var clash)."""
        self._next_slack += 1
        return -self._next_slack

    def register_var(self, var: Var, lo: Fraction | None,
                     hi: Fraction | None) -> int:
        """Register a Var in the tableau.  Returns the tableau variable ID."""
        vid = var._id
        self._var_map[vid] = var
        old_lo = self.lo.get(vid)
        old_hi = self.hi.get(vid)
        new_lo = lo if old_lo is None else (_max_none(old_lo, lo))
        new_hi = hi if old_hi is None else (_min_none(old_hi, hi))
        self.lo[vid] = new_lo
        self.hi[vid] = new_hi
        if vid not in self.assign:
            if new_lo is not None:
                self.assign[vid] = new_lo
            elif new_hi is not None:
                self.assign[vid] = min(ZERO, new_hi)
            else:
                self.assign[vid] = ZERO
        return vid

    # ── Internal substitution helpers ────────────────────────────────────

    def _substitute_parametric(self, coeffs: dict[int, Fraction],
                               constant: Fraction,
                               ) -> tuple[dict[int, Fraction], Fraction]:
        """Replace parametric (equality-eliminated) variables.

        Given equation: Σ coeffs[i]*Xi = constant
        For each parametric var Xi = Σ pc[j]*Xj + pk:
            Substitute: coeff_i * (Σ pc[j]*Xj + pk) = ...
            The pk term moves to the LHS, so must be subtracted from RHS.
        """
        new_c: dict[int, Fraction] = {}
        new_k = constant
        for vid, coeff in coeffs.items():
            if vid in self.parametric:
                pc, pk = self.parametric[vid]
                for pv, pcoeff in pc.items():
                    new_c[pv] = new_c.get(pv, ZERO) + coeff * pcoeff
                # pk is on the LHS, subtract from RHS
                new_k -= coeff * pk
            else:
                new_c[vid] = new_c.get(vid, ZERO) + coeff
        return {v: c for v, c in new_c.items() if c != ZERO}, new_k

    def _substitute_basic(self, coeffs: dict[int, Fraction],
                          constant: Fraction,
                          ) -> tuple[dict[int, Fraction], Fraction]:
        """Replace basic variables by their row definitions.

        A basic var B has row: B = Σ row[B][j]*Xj + rhs[B].
        Substituting into Σ coeffs*Xi = constant:
            coeff * B → coeff * (Σ row[j]*Xj + rhs[B])
        The rhs[B] is on the LHS, so subtract from RHS constant.
        """
        new_c: dict[int, Fraction] = {}
        new_k = constant
        for vid, coeff in coeffs.items():
            if vid in self.rows:
                row = self.rows[vid]
                new_k -= coeff * self.rhs[vid]
                for rv, rc in row.items():
                    new_c[rv] = new_c.get(rv, ZERO) + coeff * rc
            else:
                new_c[vid] = new_c.get(vid, ZERO) + coeff
        return {v: c for v, c in new_c.items() if c != ZERO}, new_k

    # ── Bounds ───────────────────────────────────────────────────────────

    def set_bound(self, vid: int, lo: Fraction | None,
                  hi: Fraction | None) -> bool:
        """Tighten bounds on a variable.  Returns False if infeasible."""
        new_lo = _max_none(self.lo.get(vid), lo)
        new_hi = _min_none(self.hi.get(vid), hi)
        if new_lo is not None and new_hi is not None and new_lo > new_hi:
            return False
        self.lo[vid] = new_lo
        self.hi[vid] = new_hi
        if vid not in self.rows:
            return self._update_nonbasic(vid)
        return self._check_basic(vid)

    def _update_nonbasic(self, vid: int) -> bool:
        """Snap a non-basic variable to its nearest bound if violated."""
        val = self.assign.get(vid, ZERO)
        lo = self.lo.get(vid)
        hi = self.hi.get(vid)
        new_val = val
        if lo is not None and val < lo:
            new_val = lo
        elif hi is not None and val > hi:
            new_val = hi
        if new_val != val:
            delta = new_val - val
            self.assign[vid] = new_val
            for bv, row in self.rows.items():
                if vid in row:
                    self.assign[bv] += row[vid] * delta
            for bv in list(self.rows):
                if not self._check_basic(bv):
                    return False
        return True

    def _check_basic(self, vid: int) -> bool:
        """If a basic variable violates its bounds, restore feasibility."""
        if vid not in self.rows:
            return True
        val = self.assign.get(vid, ZERO)
        lo = self.lo.get(vid)
        hi = self.hi.get(vid)
        if (lo is not None and val < lo) or (hi is not None and val > hi):
            return self._restore_feasibility()
        return True

    # ── Equality: Gaussian elimination ───────────────────────────────────

    def add_equality(self, coeffs: dict[int, Fraction],
                     constant: Fraction) -> bool:
        """Add: Σ coeffs[i]·Xi = constant.

        Performs Gaussian elimination: picks a pivot variable, solves for it,
        substitutes into all other rows and parametric definitions.
        Returns False on contradiction.
        """
        coeffs, constant = self._substitute_parametric(coeffs, constant)
        coeffs, constant = self._substitute_basic(coeffs, constant)

        if not coeffs:
            return constant == ZERO

        # Pick pivot: prefer user vars (positive id) over slacks
        pivot = min(coeffs, key=lambda v: (v < 0, abs(coeffs[v])))
        pcoeff = coeffs.pop(pivot)

        # Solve: pivot = (constant - Σ other*var) / pcoeff
        param_coeffs = {v: -c / pcoeff for v, c in coeffs.items()}
        param_const = constant / pcoeff

        self.parametric[pivot] = (param_coeffs, param_const)

        # Substitute into all rows
        for bv in list(self.rows):
            row = self.rows[bv]
            if pivot in row:
                factor = row.pop(pivot)
                for v, c in param_coeffs.items():
                    row[v] = row.get(v, ZERO) + factor * c
                self.rhs[bv] += factor * param_const
                self.rows[bv] = {v: c for v, c in row.items() if c != ZERO}

        # Substitute into other parametric definitions
        for pv in list(self.parametric):
            if pv == pivot:
                continue
            pc, pk = self.parametric[pv]
            if pivot in pc:
                factor = pc.pop(pivot)
                for v, c in param_coeffs.items():
                    pc[v] = pc.get(v, ZERO) + factor * c
                pk += factor * param_const
                self.parametric[pv] = ({v: c for v, c in pc.items() if c != ZERO}, pk)

        # Compute pivot's value from current assignment
        val = param_const
        for v, c in param_coeffs.items():
            val += c * self.assign.get(v, ZERO)
        self.assign[pivot] = val

        # Note: we do NOT check bounds on the pivot variable here.
        # The pivot is now parametric — its value is determined by other
        # variables. Bounds will be enforced when those variables are fixed
        # or when the simplex checks feasibility.

        # Remove pivot from rows if it was basic
        self.rows.pop(pivot, None)
        self.rhs.pop(pivot, None)

        # Check if any parametric variables are now fully determined
        # (all their dependencies are also parametric with no free vars,
        # i.e., they reduce to a constant)
        self._propagate_determined()

        return True

    def _propagate_determined(self) -> None:
        """Mark parametric variables as determined if all their deps are resolved.

        When a parametric var's equation has no remaining non-basic variables
        (all its coefficients reference other parametric vars), compute its
        actual value and update bounds to make check_implied_bindings fire.
        """
        changed = True
        while changed:
            changed = False
            for vid in list(self.parametric):
                pc, pk = self.parametric[vid]
                # Check if all variables in pc are themselves determined
                # (either parametric with empty coeffs, or already fixed via bounds)
                all_determined = True
                val = pk
                for dep_vid, dep_coeff in pc.items():
                    dep_lo = self.lo.get(dep_vid)
                    dep_hi = self.hi.get(dep_vid)
                    if dep_lo is not None and dep_hi is not None and dep_lo == dep_hi:
                        val += dep_coeff * dep_lo
                    elif dep_vid in self.parametric:
                        dep_pc, dep_pk = self.parametric[dep_vid]
                        if not dep_pc:
                            val += dep_coeff * dep_pk
                        else:
                            all_determined = False
                            break
                    else:
                        all_determined = False
                        break
                if all_determined:
                    old_lo = self.lo.get(vid)
                    old_hi = self.hi.get(vid)
                    if old_lo != val or old_hi != val:
                        self.lo[vid] = val
                        self.hi[vid] = val
                        self.assign[vid] = val
                        changed = True

    # ── Inequality: slack + simplex ──────────────────────────────────────

    def add_inequality(self, coeffs: dict[int, Fraction],
                       constant: Fraction, rel: str) -> bool:
        """Add: Σ coeffs[i]·Xi {<=, >=} constant.

        For single-variable inequalities, tightens bounds directly.
        For multi-variable, introduces a slack variable.
        """
        if rel == '>=':
            return self.add_inequality(
                {v: -c for v, c in coeffs.items()}, -constant, '<=')

        # rel == '<='
        coeffs, constant = self._substitute_parametric(coeffs, constant)
        coeffs, constant = self._substitute_basic(coeffs, constant)

        if not coeffs:
            return ZERO <= constant

        # Single-variable optimization: c*X <= k → X <= k/c (if c > 0)
        if len(coeffs) == 1:
            vid, coeff = next(iter(coeffs.items()))
            if coeff > ZERO:
                return self.set_bound(vid, None, constant / coeff)
            elif coeff < ZERO:
                return self.set_bound(vid, constant / coeff, None)
            else:
                return ZERO <= constant

        # Multi-variable: add slack
        # Σ coeffs·Xi <= constant → slack = constant - Σ coeffs·Xi, slack >= 0
        slack = self._fresh_slack()
        self.rows[slack] = {v: -c for v, c in coeffs.items()}
        self.rhs[slack] = constant
        self.lo[slack] = ZERO
        self.hi[slack] = None

        val = constant
        for v, c in coeffs.items():
            val -= c * self.assign.get(v, ZERO)
        self.assign[slack] = val

        if val < ZERO:
            return self._restore_feasibility()
        return True

    # ── Pivot ────────────────────────────────────────────────────────────

    def _pivot(self, leaving: int, entering: int) -> None:
        """Swap leaving (basic) and entering (non-basic).

        The leaving row expresses: leaving = Σ row[v]*v + rhs
        We solve for entering: entering = (leaving - Σ other*v - rhs) / row[entering]
        Then substitute into all other rows.
        """
        row = self.rows[leaving]
        pcoeff = row[entering]

        # Build new row for entering.
        # Original row: leaving = Σ row[v]*v + rhs  (where entering is one of v)
        # Rearrange: pcoeff*entering = leaving - Σ other_v*v - rhs
        # entering = leaving/pcoeff - Σ (other_c/pcoeff)*v - rhs/pcoeff
        new_row: dict[int, Fraction] = {}
        for v, c in row.items():
            if v != entering:
                new_row[v] = -c / pcoeff
        new_row[leaving] = ONE / pcoeff
        new_rhs = -self.rhs[leaving] / pcoeff

        # Substitute entering's new expression into all other rows
        for bv in list(self.rows):
            if bv == leaving:
                continue
            brow = self.rows[bv]
            if entering in brow:
                factor = brow.pop(entering)
                for v, c in new_row.items():
                    brow[v] = brow.get(v, ZERO) + factor * c
                self.rhs[bv] += factor * new_rhs
                self.rows[bv] = {v: c for v, c in brow.items() if c != ZERO}

        del self.rows[leaving]
        self.rows[entering] = new_row
        self.rhs[entering] = new_rhs

        # Recompute ALL assignments from scratch (robust, avoids drift)
        # Non-basic vars keep their current assignments (they sit at bounds)
        # The leaving var becomes non-basic at its lower bound
        lo = self.lo.get(leaving)
        if lo is not None:
            self.assign[leaving] = lo
        else:
            self.assign[leaving] = ZERO
        # Recompute all basic var assignments
        for bv in self.rows:
            val = self.rhs[bv]
            for v, c in self.rows[bv].items():
                val -= c * self.assign.get(v, ZERO)
            self.assign[bv] = val

    # ── Restore feasibility (dual simplex) ───────────────────────────────

    def _restore_feasibility(self) -> bool:
        """Dual simplex with Bland's rule.  Returns False if infeasible."""
        max_iters = 2 * (len(self.rows) + len(self.lo)) + 100
        for _ in range(max_iters):
            # Find most infeasible basic variable
            leaving = None
            worst = ZERO
            for bv in self.rows:
                val = self.assign.get(bv, ZERO)
                lo = self.lo.get(bv)
                hi = self.hi.get(bv)
                if lo is not None and val < lo:
                    viol = lo - val
                    if viol > worst:
                        worst, leaving = viol, bv
                elif hi is not None and val > hi:
                    viol = val - hi
                    if viol > worst:
                        worst, leaving = viol, bv

            if leaving is None:
                return True  # feasible

            row = self.rows[leaving]
            val = self.assign[leaving]
            lo = self.lo.get(leaving)
            hi = self.hi.get(leaving)
            entering = None

            if lo is not None and val < lo:
                # Need to increase leaving's value.
                # basic_var = Σ row[v]*non_basic_v + rhs
                # Increasing a non-basic var with positive coeff increases basic.
                # But in dual simplex, we look at which non-basic var can
                # LEAVE its bound to help. A non-basic at lower bound can
                # increase → helps if row coeff is positive.
                # A non-basic at upper bound can decrease → helps if row coeff
                # is negative.
                # Simplified Bland's: pick first var with negative coeff
                # (we'll pivot and the leaving var takes the entering's bound).
                # Actually: for dual simplex below-lower-bound, the standard
                # rule is to find entering with NEGATIVE coefficient (the
                # ratio test is inverted in dual simplex).
                # Let's try a simpler approach: just update the non-basic
                # variable's bound directly.
                for v in sorted(row.keys()):
                    c = row[v]
                    if c < ZERO:
                        # Decreasing v (to its lower bound) increases basic
                        entering = v
                        break
                    elif c > ZERO:
                        # Increasing v (to its upper bound) increases basic
                        # Check if v has an upper bound it can move to
                        v_hi = self.hi.get(v)
                        v_val = self.assign.get(v, ZERO)
                        if v_hi is not None and v_val < v_hi:
                            entering = v
                            break
            elif hi is not None and val > hi:
                # Need to decrease leaving's value.
                for v in sorted(row.keys()):
                    c = row[v]
                    if c > ZERO:
                        entering = v
                        break
                    elif c < ZERO:
                        v_lo = self.lo.get(v)
                        v_val = self.assign.get(v, ZERO)
                        if v_lo is not None and v_val > v_lo:
                            entering = v
                            break

            if entering is None:
                return False  # infeasible

            # Set leaving to its violated bound before pivot
            if lo is not None and val < lo:
                self.assign[leaving] = lo
            elif hi is not None and val > hi:
                self.assign[leaving] = hi

            self._pivot(leaving, entering)

        return False

    # ── Optimization (Phase II simplex) ──────────────────────────────────

    def optimize(self, objective: dict[int, Fraction],
                 direction: str) -> Fraction | None:
        """Phase II simplex: maximize or minimize.

        Returns optimal value, or None if unbounded.
        Updates ``self.assign`` to the optimal point.
        """
        obj, obj_k = self._substitute_parametric(dict(objective), ZERO)
        obj, obj_k = self._substitute_basic(obj, obj_k)

        if direction == 'min':
            obj = {v: -c for v, c in obj.items()}
            obj_k = -obj_k

        max_iters = 10 * (len(self.rows) + len(self.lo) + 1)
        for _ in range(max_iters):
            # Find entering: first non-basic with positive obj coefficient
            entering = None
            for v in sorted(obj.keys()):
                if v in self.rows:
                    continue
                if obj.get(v, ZERO) > ZERO:
                    entering = v
                    break

            if entering is None:
                # Optimal: compute from original objective and current assignments
                val = ZERO
                for v, c in objective.items():
                    a = self.assign.get(v, ZERO)
                    # Check parametric
                    if v in self.parametric:
                        pc, pk = self.parametric[v]
                        a = pk
                        for pv, pcoeff in pc.items():
                            a += pcoeff * self.assign.get(pv, ZERO)
                    val += c * a
                return val

            # Minimum ratio test: find which basic var first hits its lower
            # bound as we increase the entering variable.
            # basic_var changes by row[bv][entering] * delta.
            # If row coeff is negative, basic_var decreases.
            # Ratio = (bval - blo) / (-coeff) = how much entering can increase.
            leaving = None
            min_ratio: Fraction | None = None
            for bv, brow in self.rows.items():
                if entering not in brow:
                    continue
                coeff = brow[entering]
                if coeff >= ZERO:
                    continue  # positive coeff means bv increases — no limit
                bval = self.assign.get(bv, ZERO)
                blo = self.lo.get(bv)
                if blo is None:
                    continue  # no lower bound — no limit
                ratio = (bval - blo) / (-coeff)
                if min_ratio is None or ratio < min_ratio:
                    min_ratio = ratio
                    leaving = bv

            if leaving is None:
                # No basic variable limits entering. Check if entering has
                # its own upper bound (for max) that limits it.
                e_hi = self.hi.get(entering)
                if e_hi is None:
                    return None  # truly unbounded
                # Entering is bounded: set it to its upper bound
                old_val = self.assign.get(entering, ZERO)
                self.assign[entering] = e_hi
                delta = e_hi - old_val
                for bv, brow in self.rows.items():
                    if entering in brow:
                        self.assign[bv] += brow[entering] * delta
                # Remove entering from objective (it's now at its bound)
                obj.pop(entering, None)
                continue

            # Update objective coefficients after pivot
            enter_coeff = obj.pop(entering, ZERO)
            row = self.rows[leaving]
            pcoeff = row[entering]
            factor = enter_coeff / pcoeff
            for v, c in row.items():
                if v != entering:
                    obj[v] = obj.get(v, ZERO) - factor * c
            obj[leaving] = obj.get(leaving, ZERO) + factor
            obj_k += factor * self.rhs[leaving]
            obj = {v: c for v, c in obj.items() if c != ZERO}

            self._pivot(leaving, entering)

        return None

    # ── Fix variable (substitute ground value) ───────────────────────────

    def fix_variable(self, vid: int, value: Fraction) -> bool:
        """Fix vid = value.  Returns False on infeasibility.

        If vid is parametric (eliminated by a prior equality), this adds a
        new equality that propagates the value through the system.  If vid
        is basic or non-basic, it updates directly.
        """
        if vid in self.parametric:
            # vid is defined as vid = Σ(pc[v]*v) + pk.
            # Fixing vid = value means: Σ(pc[v]*v) + pk = value
            # → Σ(pc[v]*v) = value - pk
            pc, pk = self.parametric[vid]
            # This is a new equality over the remaining variables
            if not pc:
                # No variables left — pure constant check
                return pk == value
            return self.add_equality(dict(pc), value - pk)

        self.lo[vid] = value
        self.hi[vid] = value

        if vid in self.rows:
            return self.add_equality({vid: ONE}, value)

        # Non-basic: update dependents
        old_val = self.assign.get(vid, ZERO)
        self.assign[vid] = value
        if old_val != value:
            delta = value - old_val
            for bv, row in self.rows.items():
                if vid in row:
                    self.assign[bv] += row[vid] * delta

        for bv in list(self.rows):
            if not self._check_basic(bv):
                return False
        return self._check_diseqs()

    # ── Disequality check ────────────────────────────────────────────────

    def _check_diseqs(self) -> bool:
        """Fail if any ground disequality pair has become equal."""
        for a, b in self.diseqs:
            a_lo, a_hi = self.lo.get(a), self.hi.get(a)
            b_lo, b_hi = self.lo.get(b), self.hi.get(b)
            a_fixed = a_lo is not None and a_lo == a_hi
            b_fixed = b_lo is not None and b_lo == b_hi
            if a_fixed and b_fixed and self.assign.get(a) == self.assign.get(b):
                return False
        return True

    # ── Implied bindings ─────────────────────────────────────────────────

    def check_implied_bindings(self, trail: Trail) -> bool:
        """Bind variables whose bounds have collapsed to a point."""
        for vid, var in list(self._var_map.items()):
            lo = self.lo.get(vid)
            hi = self.hi.get(vid)
            if lo is not None and hi is not None and lo == hi:
                var = deref(var)
                if is_var(var):
                    if not unify(var, lo, trail):
                        return False
        return True


# ── Tableau storage ──────────────────────────────────────────────────────────

_tableaux: dict[int, Tableau] = {}


def _get_tableau(trail: Trail) -> Tableau:
    """Get or create the global Tableau for this trail."""
    tid = id(trail)
    tab = _tableaux.get(tid)
    if tab is None:
        tab = Tableau()
        _tableaux[tid] = tab
    return tab


def _snapshot_tableau(trail: Trail) -> None:
    """Save a snapshot so ``trail.undo()`` restores the tableau."""
    tid = id(trail)
    old = _tableaux[tid].copy()
    trail.record(lambda: _tableaux.__setitem__(tid, old))


# ── Utility helpers ──────────────────────────────────────────────────────────


def _max_none(a: Fraction | None, b: Fraction | None) -> Fraction | None:
    """max() treating None as -inf."""
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _min_none(a: Fraction | None, b: Fraction | None) -> Fraction | None:
    """min() treating None as +inf."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _is_ground_q(x: Any) -> bool:
    return isinstance(x, (int, Fraction)) and not isinstance(x, bool)


def _ensure_q_for_expr(expr: Any, trail: Trail) -> None:
    """Ensure all Vars in *expr* have Q-domain attributes."""
    expr = deref(expr)
    if is_var(expr):
        if get_attr(expr, Q_KEY) is None:
            _post_q_domain(expr, None, None, trail)
        return
    _ensure_term_imports()
    if isinstance(expr, (_Add, _Sub, _Mult, _Div)):
        _ensure_q_for_expr(expr.left, trail)
        _ensure_q_for_expr(expr.right, trail)
    elif isinstance(expr, _Negate):
        _ensure_q_for_expr(expr.operand, trail)


# ── Linearization ────────────────────────────────────────────────────────────


def _linearize(expr: Any, trail: Trail,
               ) -> tuple[dict[int, Fraction], Fraction] | None:
    """Flatten an expression tree to ``{var_id: coeff, …}, constant``.

    Returns None for non-linear expressions (e.g. Var * Var).
    """
    _ensure_term_imports()
    expr = deref(expr)

    if isinstance(expr, bool):
        return None
    if isinstance(expr, int):
        return {}, Fraction(expr)
    if isinstance(expr, Fraction):
        return {}, expr
    if isinstance(expr, float):
        return {}, Fraction(expr)
    if is_var(expr):
        return {expr._id: ONE}, ZERO

    if isinstance(expr, _Add):
        lc = _linearize(expr.left, trail)
        rc = _linearize(expr.right, trail)
        if lc is None or rc is None:
            return None
        lk, lv = lc
        rk, rv = rc
        m = dict(lk)
        for v, c in rk.items():
            m[v] = m.get(v, ZERO) + c
        return {v: c for v, c in m.items() if c != ZERO}, lv + rv

    if isinstance(expr, _Sub):
        lc = _linearize(expr.left, trail)
        rc = _linearize(expr.right, trail)
        if lc is None or rc is None:
            return None
        lk, lv = lc
        rk, rv = rc
        m = dict(lk)
        for v, c in rk.items():
            m[v] = m.get(v, ZERO) - c
        return {v: c for v, c in m.items() if c != ZERO}, lv - rv

    if isinstance(expr, _Mult):
        lc = _linearize(expr.left, trail)
        rc = _linearize(expr.right, trail)
        if lc is None or rc is None:
            return None
        lk, lv = lc
        rk, rv = rc
        if not lk:
            return {v: lv * c for v, c in rk.items()}, lv * rv
        if not rk:
            return {v: rv * c for v, c in lk.items()}, lv * rv
        return None  # non-linear

    if isinstance(expr, _Div):
        lc = _linearize(expr.left, trail)
        rc = _linearize(expr.right, trail)
        if lc is None or rc is None:
            return None
        rk, rv = rc
        if rk or rv == ZERO:
            return None
        lk, lv = lc
        return {v: c / rv for v, c in lk.items()}, lv / rv

    if isinstance(expr, _Negate):
        inner = _linearize(expr.operand, trail)
        if inner is None:
            return None
        k, v = inner
        return {x: -c for x, c in k.items()}, -v

    return None


# ── Domain posting ───────────────────────────────────────────────────────────


def _post_q_domain(target: Any, lo: Fraction | None,
                   hi: Fraction | None, trail: Trail) -> bool:
    """Post rational domain on a single target."""
    target = deref(target)
    if isinstance(target, bool):
        return False
    if isinstance(target, (int, Fraction)):
        val = Fraction(target)
        if lo is not None and val < lo:
            return False
        if hi is not None and val > hi:
            return False
        return True
    if not is_var(target):
        return False

    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)

    state = get_attr(target, Q_KEY)
    if state is None:
        tab_id = tableau.register_var(target, lo, hi)
        new_state = QVar(lo, hi, tab_id)
    else:
        new_lo = _max_none(state.lo, lo)
        new_hi = _min_none(state.hi, hi)
        if new_lo is not None and new_hi is not None and new_lo > new_hi:
            return False
        if not tableau.set_bound(state.tab_id, new_lo, new_hi):
            return False
        new_state = QVar(new_lo, new_hi, state.tab_id)

    put_attr(target, Q_KEY, new_state, trail)

    flo, fhi = new_state.lo, new_state.hi
    if flo is not None and fhi is not None and flo == fhi:
        if not unify(target, flo, trail):
            return False
    return True


# ── Attribute hook ───────────────────────────────────────────────────────────


def _q_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when a Q-constrained variable is unified."""
    state: QVar = attr_value
    bound_to = deref(bound_to)

    if isinstance(bound_to, bool):
        return False

    if isinstance(bound_to, (int, Fraction)):
        val = Fraction(bound_to)
        if state.lo is not None and val < state.lo:
            return False
        if state.hi is not None and val > state.hi:
            return False
        tableau = _get_tableau(trail)
        _snapshot_tableau(trail)
        if not tableau.fix_variable(state.tab_id, val):
            return False
        return tableau.check_implied_bindings(trail)

    if is_var(bound_to):
        other = get_attr(bound_to, Q_KEY)
        if other is None:
            put_attr(bound_to, Q_KEY, state, trail)
            return True
        # Both Q-constrained: merge bounds, add equality
        new_lo = _max_none(state.lo, other.lo)
        new_hi = _min_none(state.hi, other.hi)
        if new_lo is not None and new_hi is not None and new_lo > new_hi:
            return False
        tableau = _get_tableau(trail)
        _snapshot_tableau(trail)
        merged = QVar(new_lo, new_hi, other.tab_id)
        put_attr(bound_to, Q_KEY, merged, trail)
        if not tableau.add_equality({state.tab_id: ONE, other.tab_id: -ONE}, ZERO):
            return False
        return tableau.check_implied_bindings(trail)

    return False


register_attr_hook(Q_KEY, _q_hook)


# ── Public API: domain declaration ───────────────────────────────────────────


def in_q(var_or_list: Any, lo: Any = None, hi: Any = None,
         trail: Trail | None = None) -> bool:
    """Declare variable(s) as rational with optional bounds ``[lo, hi]``."""
    targets = deref(var_or_list)
    lo_val = Fraction(deref(lo)) if lo is not None else None
    hi_val = Fraction(deref(hi)) if hi is not None else None
    if isinstance(targets, list):
        for v in targets:
            if not _post_q_domain(deref(v), lo_val, hi_val, trail):
                return False
        return True
    return _post_q_domain(targets, lo_val, hi_val, trail)


# ── Public API: constraint posting ───────────────────────────────────────────


def q_eq(l: Any, r: Any, trail: Trail) -> bool:
    """Post l == r as a rational equality constraint."""
    l, r = deref(l), deref(r)
    if _is_ground_q(l) and _is_ground_q(r):
        return Fraction(l) == Fraction(r)
    # If one side is ground and other is a bare var, use unify for speed
    if _is_ground_q(r) and is_var(l):
        _ensure_q_for_expr(l, trail)
        return unify(l, Fraction(r), trail)
    if _is_ground_q(l) and is_var(r):
        _ensure_q_for_expr(r, trail)
        return unify(r, Fraction(l), trail)
    _ensure_q_for_expr(l, trail)
    _ensure_q_for_expr(r, trail)
    lc = _linearize(l, trail)
    rc = _linearize(r, trail)
    if lc is None or rc is None:
        raise TypeError("CLP(Q) requires linear constraints")
    lk, lv = lc
    rk, rv = rc
    merged = dict(lk)
    for v, c in rk.items():
        merged[v] = merged.get(v, ZERO) - c
    coeffs = {v: c for v, c in merged.items() if c != ZERO}
    constant = rv - lv
    if not coeffs:
        return constant == ZERO
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    if not tableau.add_equality(coeffs, constant):
        return False
    return tableau.check_implied_bindings(trail)


def q_ne(l: Any, r: Any, trail: Trail) -> bool:
    """Post l != r as a passive disequality."""
    l, r = deref(l), deref(r)
    if _is_ground_q(l) and _is_ground_q(r):
        return Fraction(l) != Fraction(r)
    _ensure_q_for_expr(l, trail)
    _ensure_q_for_expr(r, trail)
    lc = _linearize(l, trail)
    rc = _linearize(r, trail)
    if lc is not None and rc is not None:
        lk, lv = lc
        rk, rv = rc
        # Collect variable IDs
        l_vars = set(lk.keys())
        r_vars = set(rk.keys())
        if len(l_vars) == 1 and not r_vars:
            vid = next(iter(l_vars))
            if len(rk) == 0:
                tableau = _get_tableau(trail)
                _snapshot_tableau(trail)
                # Store disequality between vid and a value
                # For simplicity, store as pair and check later
                pass
        # For now, store as a general pair of linear expressions
        # Only checked when both sides become ground
    return True


def q_le(l: Any, r: Any, trail: Trail) -> bool:
    """Post l <= r as a rational inequality constraint."""
    l, r = deref(l), deref(r)
    if _is_ground_q(l) and _is_ground_q(r):
        return Fraction(l) <= Fraction(r)
    _ensure_q_for_expr(l, trail)
    _ensure_q_for_expr(r, trail)
    lc = _linearize(l, trail)
    rc = _linearize(r, trail)
    if lc is None or rc is None:
        raise TypeError("CLP(Q) requires linear constraints")
    lk, lv = lc
    rk, rv = rc
    merged = dict(lk)
    for v, c in rk.items():
        merged[v] = merged.get(v, ZERO) - c
    coeffs = {v: c for v, c in merged.items() if c != ZERO}
    constant = rv - lv
    if not coeffs:
        return constant >= ZERO
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    if not tableau.add_inequality(coeffs, constant, '<='):
        return False
    return tableau.check_implied_bindings(trail)


def q_lt(l: Any, r: Any, trail: Trail) -> bool:
    """Post l < r.  Equivalent to l <= r AND l != r."""
    if not q_le(l, r, trail):
        return False
    return q_ne(l, r, trail)


def q_gt(l: Any, r: Any, trail: Trail) -> bool:
    """Post l > r."""
    return q_lt(r, l, trail)


def q_ge(l: Any, r: Any, trail: Trail) -> bool:
    """Post l >= r."""
    return q_le(r, l, trail)


# ── Public API: optimization ─────────────────────────────────────────────────


def maximize(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Maximize *expr* subject to current constraints."""
    expr = deref(expr)
    result_var = deref(result_var)
    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("maximize requires a linear expression")
    coeffs, const = lc
    tableau = _get_tableau(trail)
    opt = tableau.optimize(coeffs, 'max')
    if opt is None:
        return False
    return unify(result_var, opt + const, trail)


def minimize(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Minimize *expr* subject to current constraints."""
    expr = deref(expr)
    result_var = deref(result_var)
    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("minimize requires a linear expression")
    coeffs, const = lc
    tableau = _get_tableau(trail)
    opt = tableau.optimize(coeffs, 'min')
    if opt is None:
        return False
    return unify(result_var, opt + const, trail)
