# CLP(Q) implementation issues

Known issues, remaining limitations, and potential improvements in the
CLP(Q) implementation (`clausal/logic/clpq.py` and supporting files).

All original issues (#1–#14) from Phases A–D have been resolved. The items
below are **remaining known limitations** discovered during implementation
and review.

---

## Resolved issues (for reference)

| # | Issue | Phase | Resolution |
|---|---|---|---|
| 1 | `q_ne` stub | A4 | Disequalities stored in Tableau, checked on ground |
| 2 | `_tableaux` memory leak | C2 | Cleanup callback on first CLP(Q) use per trail |
| 3 | Dual simplex confused entering-variable rule | A3 | Rewritten with correct direction logic |
| 4 | Redundant tableau snapshots | B4 | Deduplication via trail-length tracking |
| 5 | `optimize` doesn't bind variables | B1 | `_bind_optimal` binds all vars after optimize |
| 6 | No projection (Fourier-Motzkin) | D1 | `dump_q` implemented |
| 7 | `_is_rational_arg` tree walk overhead | C3 | int/float fast-reject |
| 8 | `Fraction` import per call | C1 | Moved to module level |
| 9 | `float` in Q hook silently fails | A5 | Raises `TypeError` |
| 10 | `maximize`/`minimize` missing snapshot | A1 | Snapshot added |
| 11 | No `entailed`/`sup`/`inf` | B2/B3 | All three implemented |
| 12 | No `bb_inf` | D2 | Branch-and-bound implemented |
| 13 | Pivot always targets lower bound | A2 | `leaving_bound` parameter added |
| 14 | C extension dispatch ordering | C4 | Audited — correct, no change needed |

---

## Remaining known limitations

### 15. `dump_q` produces redundant constraints

**Severity:** usability (cosmetic)

Fourier-Motzkin elimination produces O(n^2) constraints per eliminated variable
(every lower bound combined with every upper bound). No LP-based redundancy
removal is performed, so the output may contain constraints that are implied by
others.

Example: a system with 5 slack variables could produce dozens of constraints,
most redundant. The constraints are all *correct* but verbose.

**Potential fix:** after projection, check each constraint for redundancy by
testing `entailed` on the remaining constraints. Remove any that are implied.
This is O(n) LP solves per constraint — expensive but produces a minimal set.

### 16. `_fm_eliminate` silently drops trivially-true constraints

**Severity:** low (harmless)

When equality substitution in `_fm_eliminate` cancels all variables, the
resulting constraint `0 =< constant` or `0 = constant` is dropped regardless
of whether it's trivially true or indicates infeasibility. In practice this
is harmless because `dump_q` only operates on already-feasible tableaux, so
the infeasible case can't arise. But it's not fully rigorous.

**Potential fix:** check `constant >= 0` (for `=<`) or `constant == 0` (for `=`)
and raise an error or return an infeasibility marker if violated.

### 17. `dump_q` skips ground variables in `target_vars`

**Severity:** low (edge case)

If a target variable has already been bound to a value (ground), `dump_q` skips
it because `is_var(v)` returns False after deref. The user might expect to see
`{X = 5}` in the output, but instead gets nothing for that variable.

**Potential fix:** handle ground values in target_vars by emitting explicit
equality constraints: `{X = <value>}`.

### 18. `_format_constraints` orders terms by variable ID, not user order

**Severity:** cosmetic

Constraint terms are sorted by numeric variable ID (`sorted(coeffs.keys())`),
which may not match the order the user declared them. For example, if Y was
declared before X, terms still appear as `X + Y` (by ID order).

**Potential fix:** use the order from `target_vars` as the preferred term order.

### 19. `bb_inf` recursion depth limit is arbitrary

**Severity:** design decision

`_BB_MAX_DEPTH = 50` is a hard-coded safety limit. For problems with many
integer variables and wide bounds, this may be too low (returning a suboptimal
solution) or too high (slow). There's no way for the user to configure it.

**Potential fix:** accept an optional `max_depth` parameter in `bb_inf`, or
use an iteration count instead of depth. SICStus `bb_inf/5` accepts a tolerance
parameter but not a depth limit.

### 20. `bb_inf` does not return the optimal variable assignments

**Severity:** functional gap

Unlike `maximize`/`minimize`, `bb_inf` only returns the optimal objective value
— it does not bind the integer variables to their optimal values. The user knows
the minimum cost but not which assignment achieves it.

**Potential fix:** track the optimal assignment alongside the optimal value in
`_bb_solve`, then bind variables after returning (similar to `_bind_optimal`).

### 21. `entailed` on bare (non-Q) variables always returns False

**Severity:** correct but surprising

`entailed('=<', X, 5)` on a variable X that was never declared with `in_q`
returns False because the variable has no constraints. This is technically
correct (an unconstrained variable could be anything, so nothing is entailed),
but may surprise users who expect it to also work for CLP(Z) variables.

**Potential fix:** document this clearly. Or extend `entailed` to work with
CLP(Z) domains by checking FD bounds.

---

## IMPORTANT: Python fallback requirement

All C extensions MUST keep the Python reference implementation as a fallback.
Pattern:

```python
# Python reference implementation
def _foo_py(...):
    ...

# C-accelerated version with fallback
_foo = _foo_py
try:
    from clausal.logic._c_module import _foo
except ImportError:
    pass
```

Do NOT delete the Python originals when adding C versions. The codebase must
work correctly (just slower) if C extensions fail to build.
