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
_ArithEq = _ArithNeq = _Lt = _LtE = _Gt = _GtE = _CompareChain = None


def _ensure_term_imports():
    global _Add, _Sub, _Mult, _Div, _Negate
    global _ArithEq, _ArithNeq, _Lt, _LtE, _Gt, _GtE, _CompareChain
    if _Add is None:
        from clausal.terms import Add, Sub, Mult, Div, Negate
        _Add, _Sub, _Mult, _Div, _Negate = Add, Sub, Mult, Div, Negate
    if _ArithEq is None:
        from clausal.pythonic_ast.nodes import (
            ArithEq, ArithNeq, Lt, LtE, Gt, GtE, CompareChain,
        )
        _ArithEq, _ArithNeq = ArithEq, ArithNeq
        _Lt, _LtE, _Gt, _GtE = Lt, LtE, Gt, GtE
        _CompareChain = CompareChain


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

        Row convention: B = rhs[B] + Σ row[B][j]*Xj.
        Substituting into Σ coeffs*Xi = constant:
            coeff * B = coeff * (rhs[B] + Σ row[j]*Xj)
                      = coeff*rhs[B] + coeff*Σ row[j]*Xj
        The rhs part is on the LHS, so subtract from RHS.
        The variable part keeps its sign.
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
        # Σ coeffs·Xi <= constant → slack + Σ coeffs·Xi = constant
        # Rearrange: slack = constant - Σ coeffs·Xi
        # Row convention: basic = rhs + Σ row[v]*v (where row stores the coeffs
        # as-is, and assignment = rhs + Σ row[v]*assign[v])
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

    def _pivot(self, leaving: int, entering: int,
               leaving_bound: Fraction | None = None) -> None:
        """Swap leaving (basic) and entering (non-basic).

        *leaving_bound*: the value the leaving variable should take as a
        non-basic variable after the pivot.  If None, defaults to its
        lower bound (correct for primal simplex).
        """
        row = self.rows[leaving]
        pcoeff = row[entering]

        # Build new row for entering.
        # Original row: leaving = Σ row[v]*v + rhs  (entering is one of v)
        # Rearrange: entering = leaving/pcoeff - Σ (other_c/pcoeff)*v - rhs/pcoeff
        new_row: dict[int, Fraction] = {}
        for v, c in row.items():
            if v != entering:
                new_row[v] = -c / pcoeff
        new_row[leaving] = ONE / pcoeff
        new_rhs = -self.rhs[leaving] / pcoeff

        # Substitute into all other rows
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

        # Set leaving variable to its target bound
        if leaving_bound is not None:
            self.assign[leaving] = leaving_bound
        else:
            lo = self.lo.get(leaving)
            self.assign[leaving] = lo if lo is not None else ZERO

        # Recompute all basic variable assignments from their rows
        # Convention: B = rhs + Σ row[v]*v
        for bv in self.rows:
            val = self.rhs[bv]
            for v, c in self.rows[bv].items():
                val += c * self.assign.get(v, ZERO)
            self.assign[bv] = val

    # ── Restore feasibility (dual simplex) ───────────────────────────────

    def _restore_feasibility(self) -> bool:
        """Dual simplex with Bland's rule.  Returns False if infeasible.

        Algorithm:
        1. Find the most infeasible basic variable (leaving).
        2. Determine direction: below lower bound → need to increase;
           above upper bound → need to decrease.
        3. For each non-basic variable in the leaving row, check if
           pivoting it in would move the leaving variable toward
           feasibility.  A non-basic var can help if:
           - It's at its lower bound and has room to increase
             (coeff sign matches direction), OR
           - It's at its upper bound and has room to decrease
             (coeff sign matches direction).
        4. Among eligible entering vars, pick the first by Bland's rule
           (lowest index).
        5. Pivot, setting the leaving var to its violated bound.
        """
        max_iters = 2 * (len(self.rows) + len(self.lo)) + 100
        for _ in range(max_iters):
            # Find most infeasible basic variable
            leaving = None
            worst = ZERO
            for bv in self.rows:
                val = self.assign.get(bv, ZERO)
                blo = self.lo.get(bv)
                bhi = self.hi.get(bv)
                if blo is not None and val < blo:
                    viol = blo - val
                    if viol > worst:
                        worst, leaving = viol, bv
                elif bhi is not None and val > bhi:
                    viol = val - bhi
                    if viol > worst:
                        worst, leaving = viol, bv

            if leaving is None:
                return True  # all feasible

            row = self.rows[leaving]
            val = self.assign[leaving]
            lo = self.lo.get(leaving)
            hi = self.hi.get(leaving)

            below = lo is not None and val < lo
            # above = hi is not None and val > hi

            # Row convention: B = rhs + Σ row[v]*v.
            # Change in B when non-basic v changes by delta: row[v]*delta.
            #
            # To INCREASE leaving (below lower bound):
            #   Need row[v]*delta > 0.
            #   If v at lower bound (can increase, delta > 0): need row[v] > 0.
            #   If v at upper bound (can decrease, delta < 0): need row[v] < 0.
            #
            # To DECREASE leaving (above upper bound):
            #   Need row[v]*delta < 0.
            #   If v at lower bound (delta > 0): need row[v] < 0.
            #   If v at upper bound (delta < 0): need row[v] > 0.

            entering = None
            for v in sorted(row.keys()):  # Bland's rule: sorted
                c = row[v]
                if c == ZERO:
                    continue
                v_lo = self.lo.get(v)
                v_hi = self.hi.get(v)
                v_val = self.assign.get(v, ZERO)

                if below:
                    # Need to increase leaving
                    if c > ZERO and v_lo is not None and v_val <= v_lo:
                        # v at lower bound, positive coeff → increase v → increase leaving
                        if v_hi is None or v_val < v_hi:
                            entering = v
                            break
                    elif c < ZERO and v_hi is not None and v_val >= v_hi:
                        # v at upper bound, negative coeff → decrease v → increase leaving
                        if v_lo is None or v_val > v_lo:
                            entering = v
                            break
                else:
                    # Need to decrease leaving
                    if c < ZERO and v_lo is not None and v_val <= v_lo:
                        # v at lower bound, negative coeff → increase v → decrease leaving
                        if v_hi is None or v_val < v_hi:
                            entering = v
                            break
                    elif c > ZERO and v_hi is not None and v_val >= v_hi:
                        # v at upper bound, positive coeff → decrease v → decrease leaving
                        if v_lo is None or v_val > v_lo:
                            entering = v
                            break

            if entering is None:
                return False  # infeasible — no valid pivot

            # Determine the bound the leaving variable goes to
            leaving_bound = lo if below else hi
            self._pivot(leaving, entering, leaving_bound=leaving_bound)

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

            # Minimum ratio test: find which basic var first hits ANY bound
            # as we increase the entering variable.
            # Row convention: B = rhs + Σ row[v]*v.
            # Increasing entering by delta changes B by row[entering]*delta.
            # If row[entering] < 0, B decreases → may hit lower bound.
            #   ratio = (bval - blo) / (-coeff)
            # If row[entering] > 0, B increases → may hit upper bound.
            #   ratio = (bhi - bval) / coeff
            leaving = None
            min_ratio: Fraction | None = None
            for bv, brow in self.rows.items():
                if entering not in brow:
                    continue
                coeff = brow[entering]
                if coeff == ZERO:
                    continue
                bval = self.assign.get(bv, ZERO)
                ratio = None
                if coeff < ZERO:
                    blo = self.lo.get(bv)
                    if blo is not None:
                        ratio = (bval - blo) / (-coeff)
                else:  # coeff > 0
                    bhi = self.hi.get(bv)
                    if bhi is not None:
                        ratio = (bhi - bval) / coeff
                if ratio is None:
                    continue
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

            # Determine which bound the leaving variable hit
            bv_coeff = self.rows[leaving][entering]
            bv_val = self.assign[leaving]
            if bv_coeff < ZERO:
                # B decreased → hit lower bound
                lv_bound = self.lo.get(leaving, ZERO)
            else:
                # B increased → hit upper bound
                lv_bound = self.hi.get(leaving)

            # Update objective coefficients after pivot.
            # Row convention: entering = new_rhs + Σ new_row[v]*v (after pivot).
            enter_coeff = obj.pop(entering, ZERO)
            row = self.rows[leaving]
            pcoeff = row[entering]
            factor = enter_coeff / pcoeff
            for v, c in row.items():
                if v != entering:
                    obj[v] = obj.get(v, ZERO) - factor * c
            obj[leaving] = obj.get(leaving, ZERO) + factor
            obj_k -= factor * self.rhs[leaving]
            obj = {v: c for v, c in obj.items() if c != ZERO}

            self._pivot(leaving, entering, leaving_bound=lv_bound)

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
        self._propagate_determined()
        return self._check_diseqs()

    # ── Disequality check ────────────────────────────────────────────────

    def _check_diseqs(self) -> bool:
        """Fail if any disequality is violated.

        Disequalities are stored as ``('linear', coeffs, constant)``
        meaning ``Σ coeffs[v]*v != constant``.  We check this when all
        variables in the disequality are determined (fixed to a point).
        """
        for entry in self.diseqs:
            tag, coeffs, constant = entry
            # Check if all variables are determined
            all_fixed = True
            val = ZERO
            for vid, coeff in coeffs.items():
                vlo = self.lo.get(vid)
                vhi = self.hi.get(vid)
                if vlo is not None and vhi is not None and vlo == vhi:
                    val += coeff * vlo
                elif vid in self.parametric:
                    # Check if parametric var is fully determined
                    pc, pk = self.parametric[vid]
                    if not pc:
                        val += coeff * pk
                    else:
                        all_fixed = False
                        break
                else:
                    all_fixed = False
                    break
            if all_fixed and val == constant:
                return False  # disequality violated
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
_last_snapshot: dict[int, int] = {}  # trail_id → trail length at last snapshot


def _get_tableau(trail: Trail) -> Tableau:
    """Get or create the global Tableau for this trail.

    On first creation, registers an undo callback that removes the entry
    when the trail is unwound past this point, preventing leaks.
    """
    tid = id(trail)
    tab = _tableaux.get(tid)
    if tab is None:
        tab = Tableau()
        _tableaux[tid] = tab
        # Clean up when trail unwinds past the point where CLP(Q) was first used
        trail.record(lambda: (_tableaux.pop(tid, None),
                              _last_snapshot.pop(tid, None)))
    return tab


def _snapshot_tableau(trail: Trail) -> None:
    """Save a snapshot so ``trail.undo()`` restores the tableau.

    Deduplicates: if a snapshot was already taken at this trail position
    (i.e., no trail entries have been added since the last snapshot),
    skip the copy.  This avoids redundant deep copies when a single
    logical step triggers multiple internal operations (e.g., ``q_eq``
    → ``add_equality`` → ``check_implied_bindings`` → ``_q_hook``).
    """
    tid = id(trail)
    trail_len = len(trail)
    if _last_snapshot.get(tid) == trail_len:
        return  # already snapshotted at this point
    old = _tableaux[tid].copy()
    _last_snapshot[tid] = trail_len + 1  # +1 because record() adds an entry
    trail.record(lambda: (_tableaux.__setitem__(tid, old),
                          _last_snapshot.__setitem__(tid, 0)))


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


def _promote_fd_to_q(var: Var, trail: Trail) -> None:
    """Add Q bounds [fd_min, fd_max] alongside the existing FD attribute.

    Mirrors ``_promote_fd_to_real`` in CLP(R).  The FD attribute is kept
    so that both hooks fire independently — FD enforces integrality and
    domain holes, Q handles rational constraint propagation.

    Unlike float conversion, ``Fraction(int)`` is always exact.
    """
    from clausal.logic.clpfd import FD_KEY, domain_min, domain_max  # noqa: PLC0415
    fd_state = get_attr(var, FD_KEY)
    if fd_state is None:
        return
    lo = Fraction(domain_min(fd_state.domain))
    hi = Fraction(domain_max(fd_state.domain))
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    tab_id = tableau.register_var(var, lo, hi)
    put_attr(var, Q_KEY, QVar(lo, hi, tab_id), trail)


def _ensure_q_for_expr(expr: Any, trail: Trail) -> None:
    """Ensure all Vars in *expr* have Q-domain attributes.

    If a variable has an FD attribute but no Q attribute, promotes it
    (mirrors ``_ensure_real`` promoting FD to real in CLP(R)).
    """
    expr = deref(expr)
    if is_var(expr):
        if get_attr(expr, Q_KEY) is None:
            from clausal.logic.clpfd import FD_KEY  # noqa: PLC0415
            if get_attr(expr, FD_KEY) is not None:
                _promote_fd_to_q(expr, trail)
            else:
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

    # Empty interval (lo > hi) — reject up front.  The fresh-registration
    # branch below never compared the two bounds, so in_q(X, 10, 0) succeeded
    # and left a poisoned var that rejected every later binding (A08-F003).
    if lo is not None and hi is not None and lo > hi:
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

    if isinstance(bound_to, float):
        raise TypeError(
            f"Cannot unify CLP(Q) variable with float {bound_to!r}. "
            "Use Fraction for exact rationals, or declare the variable "
            "with in_real instead of in_q."
        )

    if is_var(bound_to):
        other = get_attr(bound_to, Q_KEY)
        if other is None:
            # Check for FD state and promote (mirrors _real_hook)
            from clausal.logic.clpfd import FD_KEY  # noqa: PLC0415
            if get_attr(bound_to, FD_KEY) is not None:
                _promote_fd_to_q(bound_to, trail)
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
    """Post l != r as a passive disequality.

    The disequality is stored in the Tableau and checked whenever a
    variable becomes ground.  If both sides are already ground at
    posting time, it's checked immediately.
    """
    l, r = deref(l), deref(r)
    if _is_ground_q(l) and _is_ground_q(r):
        return Fraction(l) != Fraction(r)
    _ensure_q_for_expr(l, trail)
    _ensure_q_for_expr(r, trail)
    lc = _linearize(l, trail)
    rc = _linearize(r, trail)
    if lc is None or rc is None:
        raise TypeError("CLP(Q) requires linear constraints")
    lk, lv = lc
    rk, rv = rc
    # Compute l - r: the disequality holds when this is != 0
    merged = dict(lk)
    for v, c in rk.items():
        merged[v] = merged.get(v, ZERO) - c
    coeffs = {v: c for v, c in merged.items() if c != ZERO}
    constant = rv - lv  # l - r = Σ coeffs[v]*v + (-constant) so l-r=0 ↔ Σ coeffs[v]*v = constant
    if not coeffs:
        # Pure constant: l - r = -constant, so ne iff constant != 0
        return constant != ZERO
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    # Store as (coefficients, constant) — the disequality is:
    # Σ coeffs[v]*v != constant
    tableau.diseqs.append(('linear', coeffs, constant))
    return tableau._check_diseqs()


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


def sup(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Compute the supremum (upper bound) of *expr* without committing.

    Unlike ``maximize``, this does not bind variables — it only computes
    the bound.  Useful for testing entailment and computing ranges.
    """
    expr = deref(expr)
    result_var = deref(result_var)
    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("sup requires a linear expression")
    coeffs, const = lc
    tableau = _get_tableau(trail)
    tab_copy = tableau.copy()
    opt = tab_copy.optimize(coeffs, 'max')
    if opt is None:
        return False  # unbounded
    return unify(result_var, opt + const, trail)


def inf(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Compute the infimum (lower bound) of *expr* without committing.

    Unlike ``minimize``, this does not bind variables — it only computes
    the bound.
    """
    expr = deref(expr)
    result_var = deref(result_var)
    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("inf requires a linear expression")
    coeffs, const = lc
    tableau = _get_tableau(trail)
    tab_copy = tableau.copy()
    opt = tab_copy.optimize(coeffs, 'min')
    if opt is None:
        return False  # unbounded
    return unify(result_var, opt + const, trail)


def entailed(constraint_type: str, l: Any, r: Any, trail: Trail) -> bool:
    """Test whether a constraint is logically implied by the current store.

    *constraint_type* is one of ``'='``, ``'\\\\='``, ``'<'``, ``'=<'``,
    ``'>'``, ``'>='``.

    Returns True if the constraint holds for ALL feasible points, False
    otherwise.  Does not modify the constraint store.
    """
    l, r = deref(l), deref(r)
    # Do NOT call _ensure_q_for_expr — entailed must be read-only.
    # If variables aren't in the Q domain, linearize will still work
    # (it just uses var._id as the key), but optimize won't know about
    # them unless they're registered. For unregistered vars, the result
    # is "not entailed" (the var could be anything).
    lc = _linearize(l, trail)
    rc = _linearize(r, trail)
    if lc is None or rc is None:
        raise TypeError("entailed requires linear constraints")
    lk, lv = lc
    rk, rv = rc
    # Compute l - r as a linear expression
    merged = dict(lk)
    for v, c in rk.items():
        merged[v] = merged.get(v, ZERO) - c
    coeffs = {v: c for v, c in merged.items() if c != ZERO}
    offset = lv - rv  # constant part of (l - r)

    tableau = _get_tableau(trail)

    def _sup_of_diff() -> Fraction | None:
        tab_copy = tableau.copy()
        return tab_copy.optimize(coeffs, 'max')

    def _inf_of_diff() -> Fraction | None:
        tab_copy = tableau.copy()
        return tab_copy.optimize(coeffs, 'min')

    if constraint_type in ('=<', '<='):
        # l <= r ⟺ l - r <= 0 ⟺ sup(l - r) <= 0
        s = _sup_of_diff()
        return s is not None and s + offset <= ZERO
    elif constraint_type in ('>=', '=>'):
        # l >= r ⟺ l - r >= 0 ⟺ inf(l - r) >= 0
        i = _inf_of_diff()
        return i is not None and i + offset >= ZERO
    elif constraint_type == '<':
        s = _sup_of_diff()
        return s is not None and s + offset < ZERO
    elif constraint_type == '>':
        i = _inf_of_diff()
        return i is not None and i + offset > ZERO
    elif constraint_type in ('=', '=:='):
        # l = r ⟺ sup(l-r) = inf(l-r) = 0
        s = _sup_of_diff()
        i = _inf_of_diff()
        return (s is not None and i is not None
                and s + offset == ZERO and i + offset == ZERO)
    elif constraint_type in ('\\=', '=\\='):
        # l != r ⟺ NOT(l = r) ⟺ inf(l-r) > 0 OR sup(l-r) < 0
        s = _sup_of_diff()
        i = _inf_of_diff()
        if s is None or i is None:
            return False
        return (s + offset < ZERO) or (i + offset > ZERO)
    else:
        raise ValueError(f"Unknown constraint type: {constraint_type!r}")


def _bind_optimal(tableau: Tableau, trail: Trail) -> bool:
    """Bind all user variables to their optimal assignments.

    Called after ``optimize`` to commit the optimal point.  Variables
    that are already bound are skipped.  Parametric variables are
    evaluated from their definitions.
    """
    for vid, var in list(tableau._var_map.items()):
        var = deref(var)
        if not is_var(var):
            continue
        # Compute the variable's value at the optimal point
        if vid in tableau.parametric:
            pc, pk = tableau.parametric[vid]
            val = pk
            for pv, pcoeff in pc.items():
                val += pcoeff * tableau.assign.get(pv, ZERO)
        else:
            val = tableau.assign.get(vid)
        if val is not None:
            if not unify(var, val, trail):
                return False
    return True


def maximize(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Maximize *expr* subject to current constraints.

    Binds *result_var* to the optimal objective value and all
    constrained variables to their optimal assignments.
    """
    expr = deref(expr)
    result_var = deref(result_var)
    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("maximize requires a linear expression")
    coeffs, const = lc
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    opt = tableau.optimize(coeffs, 'max')
    if opt is None:
        return False
    if not _bind_optimal(tableau, trail):
        return False
    return unify(result_var, opt + const, trail)


def minimize(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Minimize *expr* subject to current constraints.

    Binds *result_var* to the optimal objective value and all
    constrained variables to their optimal assignments.
    """
    expr = deref(expr)
    result_var = deref(result_var)
    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("minimize requires a linear expression")
    coeffs, const = lc
    tableau = _get_tableau(trail)
    _snapshot_tableau(trail)
    opt = tableau.optimize(coeffs, 'min')
    if opt is None:
        return False
    if not _bind_optimal(tableau, trail):
        return False
    return unify(result_var, opt + const, trail)


# ── Public API: projection ───────────────────────────────────────────────────


def dump_q(target_vars: list, trail: Trail) -> list[str]:
    """Project the constraint store onto *target_vars*.

    Returns a list of constraint strings over only the target variables,
    with all internal (slack, parametric) variables eliminated via
    Fourier-Motzkin elimination.

    Each returned string is of the form ``"{2*X + Y =< 16}"`` or ``"{X = 5}"``.
    """
    tableau = _get_tableau(trail)
    target_ids = set()
    id_to_name: dict[int, str] = {}
    for v in target_vars:
        v = deref(v)
        if is_var(v):
            target_ids.add(v._id)
            id_to_name[v._id] = str(v)

    constraints = _collect_constraints(tableau, target_ids)

    # Fourier-Motzkin elimination of non-target variables
    all_var_ids: set[int] = set()
    for coeffs, _, _ in constraints:
        all_var_ids.update(coeffs.keys())
    for elim_vid in sorted(all_var_ids - target_ids):
        constraints = _fm_eliminate(constraints, elim_vid)

    return _format_constraints(constraints, id_to_name)


def _collect_constraints(tableau: Tableau, target_ids: set[int],
                         ) -> list[tuple[dict[int, Fraction], str, Fraction]]:
    """Extract all constraints from the tableau as explicit triples."""
    constraints: list[tuple[dict[int, Fraction], str, Fraction]] = []

    # Parametric equalities
    for vid, (pc, pk) in tableau.parametric.items():
        coeffs: dict[int, Fraction] = {vid: ONE}
        for pv, pcoeff in pc.items():
            coeffs[pv] = coeffs.get(pv, ZERO) - pcoeff
        coeffs = {v: c for v, c in coeffs.items() if c != ZERO}
        if coeffs:
            constraints.append((coeffs, '=', pk))

    # Row inequalities: bv = rhs + Σ row[v]*v, bv in [lo, hi]
    for bv, row in tableau.rows.items():
        blo = tableau.lo.get(bv)
        bhi = tableau.hi.get(bv)
        rhs = tableau.rhs[bv]
        # bv >= blo → Σ (-row[v])*v =< rhs - blo
        if blo is not None:
            coeffs = {v: -c for v, c in row.items() if c != ZERO}
            if coeffs:
                constraints.append((coeffs, '=<', rhs - blo))
        # bv <= bhi → Σ row[v]*v =< bhi - rhs
        if bhi is not None:
            coeffs = {v: c for v, c in row.items() if c != ZERO}
            if coeffs:
                constraints.append((coeffs, '=<', bhi - rhs))

    # Explicit bounds on non-basic, non-parametric variables
    for vid in sorted(tableau.lo.keys()):
        if vid in tableau.rows or vid in tableau.parametric:
            continue
        lo = tableau.lo.get(vid)
        hi = tableau.hi.get(vid)
        if lo is not None:
            constraints.append(({vid: -ONE}, '=<', -lo))
        if hi is not None:
            constraints.append(({vid: ONE}, '=<', hi))

    return constraints


def _fm_eliminate(constraints: list[tuple[dict[int, Fraction], str, Fraction]],
                  elim_vid: int,
                  ) -> list[tuple[dict[int, Fraction], str, Fraction]]:
    """Eliminate *elim_vid* from all constraints via Fourier-Motzkin."""
    # Prefer equality substitution if available
    for i, (coeffs, rel, rhs) in enumerate(constraints):
        if rel == '=' and elim_vid in coeffs:
            c = coeffs[elim_vid]
            result: list[tuple[dict[int, Fraction], str, Fraction]] = []
            for j, (coeffs2, rel2, rhs2) in enumerate(constraints):
                if j == i:
                    other = {v: coeff for v, coeff in coeffs.items() if v != elim_vid}
                    if other:
                        result.append((other, '=', rhs))
                    continue
                c2 = coeffs2.get(elim_vid, ZERO)
                if c2 == ZERO:
                    result.append((coeffs2, rel2, rhs2))
                    continue
                new_c = {v: coeff for v, coeff in coeffs2.items() if v != elim_vid}
                for v, oc in coeffs.items():
                    if v != elim_vid:
                        new_c[v] = new_c.get(v, ZERO) - c2 * oc / c
                new_rhs = rhs2 - c2 * rhs / c
                new_c = {v: coeff for v, coeff in new_c.items() if coeff != ZERO}
                if new_c:
                    result.append((new_c, rel2, new_rhs))
            return result

    # No equality — Fourier-Motzkin on inequalities
    upper: list[tuple[dict[int, Fraction], Fraction]] = []
    lower: list[tuple[dict[int, Fraction], Fraction]] = []
    keep: list[tuple[dict[int, Fraction], str, Fraction]] = []

    for coeffs, rel, rhs in constraints:
        c = coeffs.get(elim_vid, ZERO)
        if c == ZERO:
            keep.append((coeffs, rel, rhs))
            continue
        rest = {v: coeff for v, coeff in coeffs.items() if v != elim_vid}
        if c > ZERO:
            upper.append(({v: -coeff / c for v, coeff in rest.items()}, rhs / c))
        else:
            lower.append(({v: -coeff / c for v, coeff in rest.items()}, rhs / c))

    for lo_c, lo_r in lower:
        for hi_c, hi_r in upper:
            combined = dict(lo_c)
            for v, c in hi_c.items():
                combined[v] = combined.get(v, ZERO) - c
            combined = {v: c for v, c in combined.items() if c != ZERO}
            if combined:
                keep.append((combined, '=<', hi_r - lo_r))

    return keep


def _format_constraints(constraints: list[tuple[dict[int, Fraction], str, Fraction]],
                        id_to_name: dict[int, str]) -> list[str]:
    """Format constraint triples as human-readable strings."""
    result: list[str] = []
    for coeffs, rel, rhs in constraints:
        if not coeffs:
            continue
        terms = []
        for vid in sorted(coeffs.keys()):
            c = coeffs[vid]
            name = id_to_name.get(vid, f'_{vid}')
            if c == ONE:
                terms.append(name)
            elif c == -ONE:
                terms.append(f'-{name}')
            elif c.denominator == 1:
                terms.append(f'{c.numerator}*{name}')
            else:
                terms.append(f'{c}*{name}')
        lhs = ' + '.join(terms).replace('+ -', '- ')
        if rel == '=':
            result.append(f'{{{lhs} = {rhs}}}')
        else:
            result.append(f'{{{lhs} =< {rhs}}}')
    return result


# ── Public API: mixed-integer optimization ───────────────────────────────────


def bb_inf(int_vars: list, expr: Any, result_var: Any,
           trail: Trail) -> bool:
    """Branch-and-bound mixed-integer optimization.

    Finds the infimum (minimum) of *expr* subject to the current
    constraints and the additional requirement that all variables in
    *int_vars* take integer values.

    Binds *result_var* to the optimal objective value and all
    constrained variables to their optimal assignments.

    Uses LP relaxation at each node and branches on the most fractional
    integer variable.
    """
    expr = deref(expr)
    result_var = deref(result_var)
    int_ids = set()
    for v in int_vars:
        v = deref(v)
        if is_var(v):
            int_ids.add(v._id)

    lc = _linearize(expr, trail)
    if lc is None:
        raise TypeError("bb_inf requires a linear expression")
    obj_coeffs, obj_const = lc

    tableau = _get_tableau(trail)
    best_val, best_tab = _bb_solve(tableau, obj_coeffs, obj_const, int_ids)
    if best_val is None:
        return False
    # Install the optimal tableau and bind variables
    _snapshot_tableau(trail)
    tid = id(trail)
    _tableaux[tid] = best_tab
    if not _bind_optimal(best_tab, trail):
        return False
    return unify(result_var, best_val, trail)


_BB_MAX_DEPTH = 50  # safety limit for branch-and-bound recursion


def _bb_solve(tableau: Tableau, obj_coeffs: dict[int, Fraction],
              obj_const: Fraction, int_ids: set[int],
              best_so_far: Fraction | None = None,
              best_tab: Tableau | None = None,
              depth: int = 0,
              ) -> tuple[Fraction | None, Tableau | None]:
    """Recursive branch-and-bound solver.

    Returns ``(optimal_value, optimal_tableau)`` or ``(None, None)``
    if infeasible.  The tableau holds the variable assignments at the
    optimal integer point.
    """
    import math

    if depth > _BB_MAX_DEPTH:
        return best_so_far, best_tab

    tab = tableau.copy()
    opt = tab.optimize(dict(obj_coeffs), 'min')
    if opt is None:
        return None, None  # unbounded
    obj_val = opt + obj_const

    # Pruning
    if best_so_far is not None and obj_val >= best_so_far:
        return best_so_far, best_tab

    # Check integrality
    most_frac_vid = None
    most_frac_dist = ZERO
    for vid in int_ids:
        val = tab.assign.get(vid, ZERO)
        if vid in tab.parametric:
            pc, pk = tab.parametric[vid]
            val = pk
            for pv, pcoeff in pc.items():
                val += pcoeff * tab.assign.get(pv, ZERO)
        if val.denominator != 1:
            frac_part = val - Fraction(math.floor(val))
            dist = min(frac_part, ONE - frac_part)
            if dist > most_frac_dist:
                most_frac_dist = dist
                most_frac_vid = vid

    if most_frac_vid is None:
        # All integer vars are integral — feasible integer solution
        return obj_val, tab

    # Branch on most fractional variable
    val = tab.assign.get(most_frac_vid, ZERO)
    if most_frac_vid in tab.parametric:
        pc, pk = tab.parametric[most_frac_vid]
        val = pk
        for pv, pcoeff in pc.items():
            val += pcoeff * tab.assign.get(pv, ZERO)
    floor_val = Fraction(math.floor(val))
    ceil_val = floor_val + ONE

    best = best_so_far
    b_tab = best_tab

    # Branch 1: vid <= floor_val
    tab1 = tab.copy()
    if tab1.set_bound(most_frac_vid, None, floor_val):
        v1, t1 = _bb_solve(tab1, obj_coeffs, obj_const, int_ids, best, b_tab, depth + 1)
        if v1 is not None and (best is None or v1 < best):
            best, b_tab = v1, t1

    # Branch 2: vid >= ceil_val
    tab2 = tab.copy()
    if tab2.set_bound(most_frac_vid, ceil_val, None):
        v2, t2 = _bb_solve(tab2, obj_coeffs, obj_const, int_ids, best, b_tab, depth + 1)
        if v2 is not None and (best is None or v2 < best):
            best, b_tab = v2, t2

    return best, b_tab


# ══════════════════════════════════════════════════════════════════════════════
# Module API — constraint block evaluator
# ══════════════════════════════════════════════════════════════════════════════

def clpq_constraint_block(constraints: Any, trail: Trail) -> bool:
    """Walk a tuple of Clausal AST constraint nodes and post each via CLP(Q).

    Handles comparisons (``LtE``, ``Lt``, ``GtE``, ``Gt``, ``ArithEq``,
    ``ArithNeq``) and ``CompareChain`` (chained comparisons like
    ``1 <= X <= 10``).  Variables are auto-registered as rational.
    """
    _ensure_term_imports()
    constraints = deref(constraints)
    if isinstance(constraints, (list, tuple)):
        elements = constraints
    else:
        elements = [constraints]

    for elem in elements:
        elem = deref(elem)
        if not _post_q_constraint_node(elem, trail):
            return False
    return True


def _post_q_constraint_node(node: Any, trail: Trail) -> bool:
    """Post a single AST constraint node to CLP(Q)."""
    _ensure_term_imports()

    if isinstance(node, _CompareChain):
        for cmp in node.comparisons:
            if not _post_q_constraint_node(cmp, trail):
                return False
        return True

    if isinstance(node, _ArithEq):
        return q_eq(node.left, node.right, trail)
    if isinstance(node, _ArithNeq):
        return q_ne(node.left, node.right, trail)
    if isinstance(node, _LtE):
        return q_le(node.left, node.right, trail)
    if isinstance(node, _Lt):
        return q_lt(node.left, node.right, trail)
    if isinstance(node, _GtE):
        return q_ge(node.left, node.right, trail)
    if isinstance(node, _Gt):
        return q_gt(node.left, node.right, trail)

    raise TypeError(
        f"clpq constraint block: unsupported node {type(node).__name__}: {node}"
    )
