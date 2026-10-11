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

import weakref
from decimal import Decimal
from fractions import Fraction
from typing import Any

from clausal.logic.variables import (
    present_number,
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
        _Q_BLOCK_POSTERS[:] = [
            (ArithEq, q_eq, "(==)/2"), (ArithNeq, q_ne, "(!=)/2"),
            (LtE, q_le, "(=<)/2"), (Lt, q_lt, "(<)/2"),
            (GtE, q_ge, "(>=)/2"), (Gt, q_gt, "(>)/2"),
        ]


#: Constraint-block node class -> (poster, the operator the user wrote, for
#: the ISO ``units_mismatch`` context the side channel throws).  Filled by
#: :func:`_ensure_term_imports` with the node classes.
_Q_BLOCK_POSTERS: list = []


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

        # Remove pivot from rows if it was basic
        self.rows.pop(pivot, None)
        self.rhs.pop(pivot, None)

        # The pivot's value moved, so the basic vars that used it must be
        # recomputed; and its bounds now constrain the expression it was
        # replaced by.  Dropping them let {1 =< X, X =< 5, X = Y + 1} take
        # Y = -10 (X = -9).
        for bv in self.rows:
            v = self.rhs[bv]
            for rv, rc in self.rows[bv].items():
                v += rc * self.assign.get(rv, ZERO)
            self.assign[bv] = v
        plo, phi = self.lo.get(pivot), self.hi.get(pivot)
        if not self._restore_feasibility():
            return False
        if phi is not None and not self.add_inequality({pivot: ONE}, phi, '<='):
            return False
        if plo is not None and not self.add_inequality({pivot: ONE}, plo, '>='):
            return False

        # Check if any parametric variables are now fully determined
        # (all their dependencies are also parametric with no free vars,
        # i.e., they reduce to a constant)
        self._propagate_determined()

        return True

    def _propagate_determined(self) -> None:
        """Mark variables whose value is now forced as fixed (lo == hi).

        A parametric var is forced when every var in its equation is; so is
        a basic var whose row mentions only forced vars (an empty row is a
        constant).  ``check_implied_bindings`` then binds them.  Basic vars
        count since an eliminated var's bounds are kept as rows: a user var
        can be basic when the last equality fixes it (X + Y + Z = 6,
        X - Y = 2, Y - Z = 1 left Y basic with the row 5/3).
        """
        def fixed(dep_vid):
            dep_lo = self.lo.get(dep_vid)
            if dep_lo is not None and dep_lo == self.hi.get(dep_vid):
                return dep_lo
            return None

        changed = True
        while changed:
            changed = False
            defs = [(vid, pc, pk) for vid, (pc, pk) in self.parametric.items()]
            defs += [(bv, row, self.rhs[bv]) for bv, row in self.rows.items()]
            for vid, pc, pk in defs:
                val = pk
                for dep_vid, dep_coeff in pc.items():
                    dep_val = fixed(dep_vid)
                    if dep_val is None:
                        break
                    val += dep_coeff * dep_val
                else:
                    if fixed(vid) != val:
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
        max_iters = 50 * (len(self.rows) + len(self.lo)) + 1000
        for _ in range(max_iters):
            # Bland's rule: the lowest-numbered infeasible basic var leaves
            # (picking the most infeasible one can cycle).
            leaving = None
            for bv in sorted(self.rows):
                val = self.assign.get(bv, ZERO)
                blo = self.lo.get(bv)
                bhi = self.hi.get(bv)
                if (blo is not None and val < blo) or (bhi is not None and val > bhi):
                    leaving = bv
                    break

            if leaving is None:
                return True  # all feasible

            row = self.rows[leaving]
            val = self.assign[leaving]
            lo = self.lo.get(leaving)
            hi = self.hi.get(leaving)

            below = lo is not None and val < lo

            # Row convention: B = rhs + Σ row[v]*v, so moving non-basic v by
            # delta moves B by row[v]*delta.  B must rise when below its
            # lower bound and fall when above its upper bound; v can enter if
            # it has room to move the needed way.  A var need not sit at a
            # bound: a free one (no bounds) can move either way, which the
            # old test ("at its lower bound") missed, so {X + Y >= 2} over
            # free X, Y was rejected.
            entering = None
            for v in sorted(row.keys()):  # Bland's rule: sorted
                c = row[v]
                if c == ZERO:
                    continue
                v_val = self.assign.get(v, ZERO)
                rise = (c > ZERO) == below          # v must increase?
                if rise:
                    v_hi = self.hi.get(v)
                    if v_hi is None or v_val < v_hi:
                        entering = v
                        break
                else:
                    v_lo = self.lo.get(v)
                    if v_lo is None or v_val > v_lo:
                        entering = v
                        break

            if entering is None:
                return False  # infeasible — no valid pivot

            # Determine the bound the leaving variable goes to
            leaving_bound = lo if below else hi
            self._pivot(leaving, entering, leaving_bound=leaving_bound)

        raise RuntimeError("clpq: simplex did not terminate")

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
            # Find entering (Bland): the first non-basic var that improves
            # the objective by moving off its bound.  A positive coefficient
            # wants it to rise (room below its upper bound); a negative one
            # wants it to fall (room above its lower bound).  A var parked at
            # its upper bound must be able to come back down: dropping that
            # case left box-bounded maxima at a suboptimal vertex.
            entering = None
            step = 0
            for v in sorted(obj.keys()):
                if v in self.rows:
                    continue
                c = obj[v]
                a = self.assign.get(v, ZERO)
                if c > ZERO:
                    hi = self.hi.get(v)
                    if hi is None or a < hi:
                        entering, step = v, 1
                        break
                elif c < ZERO:
                    lo = self.lo.get(v)
                    if lo is None or a > lo:
                        entering, step = v, -1
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

            # Minimum ratio test: how far can entering move (by t >= 0 in
            # direction *step*) before a basic var hits a bound?
            # Row convention: B = rhs + Σ row[v]*v, so B changes by
            # row[entering]*step*t: falling → lower bound, rising → upper.
            leaving = None
            min_ratio: Fraction | None = None
            for bv, brow in self.rows.items():
                if entering not in brow:
                    continue
                coeff = brow[entering] * step
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
                if min_ratio is None or ratio < min_ratio or (
                        ratio == min_ratio and bv < leaving):
                    min_ratio = ratio
                    leaving = bv

            # The entering variable can also hit its OWN opposite bound
            # before any basic var does — a bound flip.  It stays non-basic
            # and keeps its objective coefficient (A08-F001: without this
            # check x rose past x <= 5 in a degenerate maximum).
            e_bound = self.hi.get(entering) if step > 0 else self.lo.get(entering)
            entering_ratio = abs(e_bound - self.assign.get(entering, ZERO)) \
                if e_bound is not None else None
            if entering_ratio is not None and (min_ratio is None
                                               or entering_ratio <= min_ratio):
                old_val = self.assign.get(entering, ZERO)
                self.assign[entering] = e_bound
                delta = e_bound - old_val
                for bv, brow in self.rows.items():
                    if entering in brow:
                        self.assign[bv] += brow[entering] * delta
                continue

            if leaving is None:
                return None  # truly unbounded (no basic limit, no own bound)

            # Determine which bound the leaving variable hit
            bv_coeff = self.rows[leaving][entering] * step
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

        raise RuntimeError("clpq: simplex did not terminate")

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

        # Bounds may live only in the tableau (posted by the single-variable
        # fast path of add_inequality via set_bound, which never refreshes the
        # QVar attr).  Overwriting them unconditionally silently destroyed
        # them, so in_q(X,0,100); q_le(X,5); X is 50 succeeded (A08-F001).
        cur_lo = self.lo.get(vid)
        cur_hi = self.hi.get(vid)
        if cur_lo is not None and value < cur_lo:
            return False
        if cur_hi is not None and value > cur_hi:
            return False

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
                    if not unify(var, present_number(lo), trail):
                        return False
        return True


# ── Tableau storage ──────────────────────────────────────────────────────────

_tableaux: dict[int, Tableau] = {}
_last_snapshot: dict[int, int] = {}  # trail_id → trail length at last snapshot


def _cleanup_tableau(tid: int) -> None:
    _tableaux.pop(tid, None)
    _last_snapshot.pop(tid, None)


def _get_tableau(trail: Trail) -> Tableau:
    """Get or create the global Tableau for this trail.

    On first creation, registers both an undo callback (for backtracking past
    the point where CLP(Q) was first used) and a weakref.finalize (for the
    normal case of a completed solve dropping the trail without a full undo).
    Without the finalize the entry leaked forever, and a new Trail() allocated
    at the same address inherited the stale tableau — cross-query constraint
    contamination, not just a leak (A08-F005).
    """
    tid = id(trail)
    tab = _tableaux.get(tid)
    if tab is None:
        tab = Tableau()
        _tableaux[tid] = tab
        trail.record(lambda: _cleanup_tableau(tid))
        weakref.finalize(trail, _cleanup_tableau, tid)
    return tab


def _snapshot_tableau(trail: Trail) -> None:
    """Save a snapshot so ``trail.undo()`` restores the tableau.

    Every change to the store takes one.  It used to be skipped when the
    trail had not grown since the last snapshot, but a choice point can be
    taken at that very length: the change after it then had nothing to
    undo it, and ``{X =< 3}, ({X >= 1}, fail ; true), X = 0`` failed.
    """
    tid = id(trail)
    old = _tableaux[tid].copy()
    _last_snapshot[tid] = len(trail) + 1  # +1 because record() adds an entry
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
    return isinstance(x, (int, Fraction, Decimal)) and not isinstance(x, bool)



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
    if isinstance(expr, Decimal):
        if not expr.is_finite():
            return None
        return {}, Fraction(expr)         # exact; scale is not carried
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
    if isinstance(target, (int, Fraction, Decimal)):
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
        if not unify(target, present_number(flo), trail):
            return False
    return True


# ── Attribute hook ───────────────────────────────────────────────────────────


def _q_hook(attr_value: Any, bound_to: Any, trail: Trail) -> bool:
    """Called when a Q-constrained variable is unified."""
    state: QVar = attr_value
    bound_to = deref(bound_to)

    if isinstance(bound_to, bool):
        return False

    if isinstance(bound_to, (int, Fraction, Decimal)):
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
    """Declare variable(s) as rational with optional bounds ``[lo, hi]``.

    Quantity bounds declare the targets' dimension too (``in_q(X, 0(euro),
    10(euro))``): both bounds must then be quantities of one dimension, every
    target becomes a united variable of it and the bounds are posted on its
    shadow -- CLP(FD)'s ``in_domain/3`` rule, without its whole-units clause
    (a rational domain holds any amount)."""
    targets = deref(var_or_list)
    united = _in_q_units(targets, deref(lo), deref(hi), trail)
    if united is not None:
        return united
    lo_val = Fraction(deref(lo)) if lo is not None else None
    hi_val = Fraction(deref(hi)) if hi is not None else None
    if isinstance(targets, list):
        for v in targets:
            if not _post_q_domain(deref(v), lo_val, hi_val, trail):
                return False
        return True
    return _post_q_domain(targets, lo_val, hi_val, trail)


def _in_q_units(targets, lo, hi, trail):
    """``in_q/3`` with a Quantity bound: None when neither bound is one."""
    from clausal.logic import _units_flag  # noqa: PLC0415
    if not _units_flag.active:
        return None
    from clausal.terms import Quantity  # noqa: PLC0415
    lo_q, hi_q = isinstance(lo, Quantity), isinstance(hi, Quantity)
    if not (lo_q or hi_q):
        return None
    from clausal.logic import units_clp  # noqa: PLC0415
    from clausal.logic.units_constraint import UNITS_KEY, to_solver_number  # noqa: PLC0415
    ctx = "in_q/3"
    if not (lo_q and hi_q):
        q, plain = (lo, hi) if lo_q else (hi, lo)
        if plain is None:
            # One-sided: the missing bound is unbounded, not a plain number.
            dims = dict(q.dims)
        else:
            raise units_clp._mismatch_text(
                ctx, f"bound {plain!r} is a plain number beside {q!r}")
    else:
        if dict(lo.dims) != dict(hi.dims):
            raise units_clp._mismatch(ctx, dict(lo.dims), dict(hi.dims))
        dims = dict(lo.dims)
    lo_val = Fraction(to_solver_number(lo.value)) if lo_q else None
    hi_val = Fraction(to_solver_number(hi.value)) if hi_q else None
    as_list = isinstance(targets, list)
    shadows = []
    for v in (targets if as_list else [targets]):
        v = deref(v)
        if isinstance(v, Quantity):
            if dict(v.dims) != dims:
                raise units_clp._mismatch(ctx, dict(v.dims), dims)
            shadows.append(to_solver_number(v.value))
            continue
        if not is_var(v):
            raise units_clp._mismatch(ctx, {}, dims, f"target {v!r}")
        state = get_attr(v, UNITS_KEY)
        if state is not None and state.dims != dims:
            raise units_clp._mismatch(ctx, state.dims, dims)
        if not dims:
            shadows.append(v)                     # dimensionless bounds: a plain domain
            continue
        if state is None and (get_attr(v, Q_KEY) is not None
                              or get_attr(v, "fd") is not None
                              or get_attr(v, "real") is not None):
            raise units_clp._mismatch(ctx, {}, dims,
                                      f"target {v!r} is already a bare solver variable")
        units_clp._refuse_bypassed(v, ctx)
        shadows.append(units_clp.shadow_for(v, dims, trail))
    for s in shadows:
        if not _post_q_domain(s, lo_val, hi_val, trail):
            return False
    return True


# ── Public API: constraint posting ───────────────────────────────────────────


def _cells_as_nodes(l, r, context):
    """clpfd's post-boundary rewrite, STRICT (ruling R9 A1, 2026-09-27): an
    arithmetic cell becomes its operator node, which is what the _linearize
    walk; an atom or a non-evaluable compound raises ``type_error(evaluable,
    F/N)`` -- the _linearize had no diagnosis of their own for it."""
    global _cells_as_nodes
    from clausal.logic.clpfd import _cells_as_nodes as impl  # noqa: PLC0415 -- clpfd imports this module lazily
    _cells_as_nodes = impl
    return impl(l, r, context)


def _cell_as_node(expr: Any, context: str) -> Any:
    """One operand's :func:`_cells_as_nodes` -- an objective or a bound."""
    return _cells_as_nodes(expr, 0, context)[0]


# ── Units ────────────────────────────────────────────────────────────────────
# The units side channel (clausal.logic.units_clp), the one CLP(FD) uses: a
# Quantity or a united variable anywhere in a post is analysed for its
# dimension first (a disagreement is ``system_error(units_mismatch)``), then
# every Quantity becomes its exact solver number and every united variable its
# bare shadow, so the tableau only ever sees rationals. When the tableau
# binds a shadow, the ``units_link`` hook rebinds the user's variable to a
# Quantity in the dimension's base unit -- ``5000 cent`` is 50 euro on the
# way in and comes back as euro, exactly as the ground path presents it.
# Cached on first use; the flag says whether any Quantity exists yet.

_strip_for_solver = None
_strip_expr_for_solver = None
_reattach = None
_label_targets = None


def _ensure_units_imports() -> None:
    global _strip_for_solver, _strip_expr_for_solver, _reattach, _label_targets
    if _strip_for_solver is None:
        from clausal.logic import units_clp  # noqa: PLC0415
        _strip_for_solver = units_clp.strip_for_solver
        _strip_expr_for_solver = units_clp.strip_expr_for_solver
        _reattach = units_clp.reattach
        _label_targets = units_clp.label_targets


def _units_strip(l, r, context, trail):
    """A comparison through the side channel: the ``(l, r)`` the tableau can
    take, or the pair untouched when no units material is involved. Runs
    AFTER the cell rewrite (a Quantity leaf may sit inside a cell built at
    run time) and before the ground fast paths, which read plain numbers."""
    if _strip_for_solver is None:
        _ensure_units_imports()
    stripped = _strip_for_solver(l, r, context, trail)
    return (l, r) if stripped is None else stripped


def _units_strip_expr(expr, context, trail):
    """An objective through the side channel: ``(expr', dims)`` -- the tree
    the tableau can take and the dimension its optimum carries (``{}`` when
    no units material is involved)."""
    if _strip_expr_for_solver is None:
        _ensure_units_imports()
    stripped = _strip_expr_for_solver(expr, context, trail)
    return (expr, {}) if stripped is None else stripped


def _units_result(value, dims):
    """An optimum as the term the caller gets: a Quantity of *dims*, else the
    number as the engine presents it (an integral rational is an int)."""
    if not dims:
        return present_number(value)
    return _reattach(value, dims)


def q_eq(l: Any, r: Any, trail: Trail) -> bool:
    """Post l == r as a rational equality constraint."""
    l, r = deref(l), deref(r)
    l, r = _cells_as_nodes(l, r, "(==)/2")   # ruling R9 A1
    l, r = _units_strip(l, r, "(==)/2", trail)
    if _is_ground_q(l) and _is_ground_q(r):
        return Fraction(l) == Fraction(r)
    # If one side is ground and other is a bare var, use unify for speed
    if _is_ground_q(r) and is_var(l):
        _ensure_q_for_expr(l, trail)
        return unify(l, present_number(r), trail)
    if _is_ground_q(l) and is_var(r):
        _ensure_q_for_expr(r, trail)
        return unify(r, present_number(l), trail)
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
    l, r = _cells_as_nodes(l, r, "(!=)/2")   # ruling R9 A1
    l, r = _units_strip(l, r, "(!=)/2", trail)
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
    l, r = _cells_as_nodes(l, r, "(=<)/2")   # ruling R9 A1
    l, r = _units_strip(l, r, "(=<)/2", trail)
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
    # The side channel once, under the operator the user wrote; the two
    # posts below then find bare numbers and shadows only and pass through.
    l, r = _cells_as_nodes(deref(l), deref(r), "(<)/2")
    l, r = _units_strip(l, r, "(<)/2", trail)
    if not q_le(l, r, trail):
        return False
    return q_ne(l, r, trail)


def q_gt(l: Any, r: Any, trail: Trail) -> bool:
    """Post l > r."""
    l, r = _cells_as_nodes(deref(l), deref(r), "(>)/2")
    l, r = _units_strip(l, r, "(>)/2", trail)
    return q_lt(r, l, trail)


def q_ge(l: Any, r: Any, trail: Trail) -> bool:
    """Post l >= r."""
    l, r = _cells_as_nodes(deref(l), deref(r), "(>=)/2")
    l, r = _units_strip(l, r, "(>=)/2", trail)
    return q_le(r, l, trail)


# ── Public API: optimization ─────────────────────────────────────────────────


def sup(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Compute the supremum (upper bound) of *expr* without committing.

    Unlike ``maximize``, this does not bind variables — it only computes
    the bound.  Useful for testing entailment and computing ranges.
    """
    expr = deref(expr)
    expr = _cell_as_node(expr, "sup/2")   # ruling R9 A1: a cell objective is its node
    expr, dims = _units_strip_expr(expr, "sup/2", trail)
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
    return unify(result_var, _units_result(opt + const, dims), trail)


def inf(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Compute the infimum (lower bound) of *expr* without committing.

    Unlike ``minimize``, this does not bind variables — it only computes
    the bound.
    """
    expr = deref(expr)
    expr = _cell_as_node(expr, "inf/2")   # ruling R9 A1: a cell objective is its node
    expr, dims = _units_strip_expr(expr, "inf/2", trail)
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
    return unify(result_var, _units_result(opt + const, dims), trail)


def entailed(constraint_type: str, l: Any, r: Any, trail: Trail) -> bool:
    """Test whether a constraint is logically implied by the current store.

    *constraint_type* is one of ``'='``, ``'\\\\='``, ``'<'``, ``'=<'``,
    ``'>'``, ``'>='``.

    Returns True if the constraint holds for ALL feasible points, False
    otherwise.  Does not modify the constraint store.
    """
    l, r = deref(l), deref(r)
    l, r = _cells_as_nodes(l, r, "entailed/1")   # ruling R9 A1
    # The side channel is read-only too when the shadows exist already; a
    # first-seen united var gets its shadow here (trailed), which is the
    # var's identity in the tableau, not a constraint on it.
    l, r = _units_strip(l, r, "entailed/1", trail)
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
            if not unify(var, present_number(val), trail):
                return False
    return True


def maximize(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Maximize *expr* subject to current constraints.

    Binds *result_var* to the optimal objective value and all
    constrained variables to their optimal assignments.
    """
    expr = deref(expr)
    expr = _cell_as_node(expr, "maximize/2")   # ruling R9 A1: a cell objective is its node
    expr, dims = _units_strip_expr(expr, "maximize/2", trail)
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
    return unify(result_var, _units_result(opt + const, dims), trail)


def minimize(expr: Any, result_var: Any, trail: Trail) -> bool:
    """Minimize *expr* subject to current constraints.

    Binds *result_var* to the optimal objective value and all
    constrained variables to their optimal assignments.
    """
    expr = deref(expr)
    expr = _cell_as_node(expr, "minimize/2")   # ruling R9 A1: a cell objective is its node
    expr, dims = _units_strip_expr(expr, "minimize/2", trail)
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
    return unify(result_var, _units_result(opt + const, dims), trail)


# ── Public API: projection ───────────────────────────────────────────────────


def dump_q(target_vars: list, trail: Trail, name_of=None, *,
           toplevel: bool = False) -> list[str]:
    """Project the constraint store onto *target_vars*.

    Returns a list of constraint strings over only the target variables,
    with all internal (slack, parametric) variables eliminated via
    Fourier-Motzkin elimination.

    Each returned string is of the form ``"{2*X + Y =< 16}"``, ``"{X = 5}"``,
    ``"{X < 3}"`` (a bound and a disequality on the same expression) or
    ``"{X =\\= 2}"``.  A disequality is shown only when every variable it
    mentions is a target: it cannot be projected through an eliminated one.

    *name_of* names a target variable (default: ``str``).  *toplevel*
    writes a constraint whose coefficients are all negative the other way
    round (``{X >= 2}``, not ``{-X =< -2}``), as an answer is printed.
    """
    tableau = _get_tableau(trail)
    target_ids = set()
    id_to_name: dict[int, str] = {}
    if _label_targets is None:
        _ensure_units_imports()
    # A united variable's constraints sit on its shadow: project onto the
    # shadow, named as the variable the program wrote (it answered [] before).
    for v, s in zip(target_vars, _label_targets(target_vars, "dump_q/2")):
        v, s = deref(v), deref(s)
        if is_var(s):
            target_ids.add(s._id)
            id_to_name[s._id] = str(v) if name_of is None else name_of(v)

    constraints = _connected(_collect_constraints(tableau, target_ids),
                             target_ids)
    projected = _project(constraints, target_ids)
    if projected is None:
        # Too large to project: show the constraints as they are, over
        # their internal variables.  Complete and true, just not simplified.
        projected = constraints
    constraints = projected

    # Disequalities (q_ne, and the strict half of q_lt) over targets only.
    # A bound on the same expression and value makes the pair one strict
    # constraint: X =< 3 and X =\= 3 are X < 3.
    for _tag, coeffs, constant in tableau.diseqs:
        if not coeffs or not set(coeffs) <= target_ids:
            continue
        neg = {v: -c for v, c in coeffs.items()}
        for i, (c2, rel2, rhs2) in enumerate(constraints):
            if rel2 == '=<' and ((c2 == coeffs and rhs2 == constant)
                                 or (c2 == neg and rhs2 == -constant)):
                constraints[i] = (c2, '<', rhs2)
                break
        else:
            constraints.append((dict(coeffs), '=\\=', constant))

    return _format_constraints(constraints, id_to_name, toplevel=toplevel)


def residual_q(target_vars: list, trail: Trail, name_of) -> list[str]:
    """The CLP(Q) constraints on *target_vars* as a toplevel prints them
    (:func:`dump_q` with ``toplevel=True``); ``[]`` without creating a
    store when this trail never posted one."""
    if id(trail) not in _tableaux:
        return []
    return dump_q(target_vars, trail, name_of, toplevel=True)


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

    # Rows: bv = rhs + Σ row[v]*v, written as the equation itself (a
    # user variable can be basic, and a parametric definition can name a
    # basic slack: bounds on the row alone lost both).
    for bv, row in tableau.rows.items():
        coeffs = {bv: ONE}
        for v, c in row.items():
            coeffs[v] = coeffs.get(v, ZERO) - c
        coeffs = {v: c for v, c in coeffs.items() if c != ZERO}
        constraints.append((coeffs, '=', tableau.rhs[bv]))

    # Bounds on every variable, basic or not.
    for vid in sorted(tableau.lo.keys() | tableau.hi.keys()):
        lo = tableau.lo.get(vid)
        hi = tableau.hi.get(vid)
        if lo is not None and lo == hi:
            constraints.append(({vid: ONE}, '=', lo))
            continue
        if lo is not None:
            constraints.append(({vid: -ONE}, '=<', -lo))
        if hi is not None:
            constraints.append(({vid: ONE}, '=<', hi))

    return constraints


def _connected(constraints, target_ids):
    """The constraints linked to *target_ids* through shared variables.

    The rest cannot narrow the targets (the store is feasible), and
    projecting them away is wasted work."""
    reach = set(target_ids)
    todo = list(constraints)
    keep = []
    changed = True
    while changed:
        changed = False
        rest = []
        for con in todo:
            if reach.intersection(con[0]):
                keep.append(con)
                reach.update(con[0])
                changed = True
            else:
                rest.append(con)
        todo = rest
    return keep


#: Fourier-Motzkin gives up past this many constraints, or this many pairs
#: to combine in one step (see :func:`_project`).
_FM_LIMIT = 2000
_FM_PAIRS = 20000


def _project(constraints, target_ids):
    """Eliminate every non-target variable; None when it grows past
    ``_FM_LIMIT``.

    Equalities are substituted first.  Inequalities are combined pairwise
    (Fourier-Motzkin), cheapest variable first, keeping each derived
    constraint's set of source inequalities: after eliminating *k*
    variables one built from more than *k* + 1 sources is redundant
    (Chernikov), and duplicates keep only their tightest bound.  Without
    this pruning the count grew exponentially, and an answer printed by
    ``clausal -g`` could hang.
    """
    cons = [(c, r, k, frozenset() if r == '=' else frozenset([i]))
            for i, (c, r, k) in enumerate(constraints)]
    elim = set()
    for c, _, _, _ in cons:
        elim.update(c)
    elim -= target_ids
    eliminated = 0
    while elim:
        eq = next(((v, i) for i, (c, r, _, _) in enumerate(cons) if r == '='
                   for v in sorted(c) if v in elim), None)
        if eq is not None:
            v, i = eq
            cons = _fm_substitute(cons, i, v)
            eliminated += 1
        else:
            def cost(v):
                pos = sum(1 for c, _, _, _ in cons if c.get(v, ZERO) > ZERO)
                neg = sum(1 for c, _, _, _ in cons if c.get(v, ZERO) < ZERO)
                return (pos * neg - pos - neg, v)
            v = min(elim, key=cost)
            eliminated += 1
            # Counting substituted variables too only keeps more (sound).
            cons = _fm_combine(cons, v, eliminated + 1)
            if cons is None:
                return None
        elim.discard(v)
    return [(c, r, k) for c, r, k, _ in cons]


def _fm_substitute(cons, i, v):
    """Use equality *i* to eliminate *v* from every other constraint."""
    coeffs, _, rhs, _ = cons[i]
    c = coeffs[v]
    out = []
    for j, (c2, rel2, rhs2, h2) in enumerate(cons):
        if j == i:
            # The equality defines v and is used up by the substitution:
            # X + Y = 3 projected onto X is no constraint, not X = 3.
            continue
        f = c2.get(v, ZERO)
        if f == ZERO:
            out.append((c2, rel2, rhs2, h2))
            continue
        new_c = {u: k for u, k in c2.items() if u != v}
        for u, k in coeffs.items():
            if u != v:
                new_c[u] = new_c.get(u, ZERO) - f * k / c
        new_c = {u: k for u, k in new_c.items() if k != ZERO}
        if new_c:
            out.append((new_c, rel2, rhs2 - f * rhs / c, h2))
    return out


def _fm_combine(cons, v, max_sources):
    """Fourier-Motzkin step on *v*; None past ``_FM_LIMIT``."""
    upper, lower, keep = [], [], []
    for coeffs, rel, rhs, h in cons:
        c = coeffs.get(v, ZERO)
        if c == ZERO:
            keep.append((coeffs, rel, rhs, h))
            continue
        rest = {u: -k / c for u, k in coeffs.items() if u != v}
        (upper if c > ZERO else lower).append((rest, rhs / c, h))
    if len(upper) * len(lower) > _FM_PAIRS:
        return None
    best: dict = {}
    for lo_c, lo_r, lo_h in lower:
        for hi_c, hi_r, hi_h in upper:
            h = lo_h | hi_h
            if len(h) > max_sources:
                continue                     # Chernikov: redundant
            combined = dict(lo_c)
            for u, k in hi_c.items():
                combined[u] = combined.get(u, ZERO) - k
            combined = {u: k for u, k in combined.items() if k != ZERO}
            if not combined:
                continue
            # Scale so the first coefficient is ±1, to spot duplicates.
            first = combined[min(combined)]
            scale = abs(first)
            key = tuple(sorted((u, k / scale) for u, k in combined.items()))
            rhs = (hi_r - lo_r) / scale
            if key not in best or rhs < best[key][0]:
                best[key] = (rhs, h)
    for key, (rhs, h) in best.items():
        keep.append((dict(key), '=<', rhs, h))
    if len(keep) > _FM_LIMIT:
        return None
    return keep


#: A relation written with every coefficient negated (``toplevel``).
_FLIPPED = {'=': '=', '=\\=': '=\\=', '=<': '>=', '<': '>'}


def _format_constraints(constraints: list[tuple[dict[int, Fraction], str, Fraction]],
                        id_to_name: dict[int, str], *,
                        toplevel: bool = False) -> list[str]:
    """Format constraint triples as human-readable strings."""
    result: list[str] = []
    id_to_name = dict(id_to_name)
    for coeffs, rel, rhs in constraints:
        if not coeffs:
            continue
        for vid in sorted(coeffs):
            if vid not in id_to_name:
                id_to_name[vid] = f'_Q{len(id_to_name) + 1}'
        if toplevel and all(c < ZERO for c in coeffs.values()):
            coeffs = {v: -c for v, c in coeffs.items()}
            rel, rhs = _FLIPPED[rel], -rhs
        terms = []
        for vid in sorted(coeffs.keys()):
            c = coeffs[vid]
            name = id_to_name[vid]
            if c == ONE:
                terms.append(name)
            elif c == -ONE:
                terms.append(f'-{name}')
            elif c.denominator == 1:
                terms.append(f'{c.numerator}*{name}')
            else:
                terms.append(f'{c}*{name}')
        lhs = ' + '.join(terms).replace('+ -', '- ')
        result.append(f'{{{lhs} {rel} {rhs}}}')
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
    expr = _cell_as_node(expr, "bb_inf/3")   # ruling R9 A1: a cell objective is its node
    expr, dims = _units_strip_expr(expr, "bb_inf/3", trail)
    result_var = deref(result_var)
    if _label_targets is None:
        _ensure_units_imports()
    int_ids = set()
    for v in _label_targets(int_vars, "bb_inf/3"):   # a united var: its shadow is the integer
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
    return unify(result_var, _units_result(best_val, dims), trail)


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

    for node_class, post, context in _Q_BLOCK_POSTERS:
        if isinstance(node, node_class):
            return _post_q_stripped(post, node.left, node.right, context, trail)

    raise TypeError(
        f"clpq constraint block: unsupported node {type(node).__name__}: {node}"
    )



def _post_q_stripped(post, l: Any, r: Any, context: str, trail: Trail) -> bool:
    """Run the units side channel (``units_clp``) on one comparison of a
    constraint block, then post it.  The bare comparators strip a Quantity
    or a united variable to its solver number / shadow variable before
    dispatching; a block posts straight to ``q_*``, so it strips here too,
    through the same cached channel (``_units_strip``) every CLP(Q) entry
    point uses."""
    l, r = _units_strip(l, r, context, trail)
    return post(l, r, trail)
