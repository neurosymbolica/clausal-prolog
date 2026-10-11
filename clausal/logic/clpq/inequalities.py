# Ported from the clp(q,r) 1.3.3 distribution, file ineq.pl (banner: version 1.3.2)
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Posting inequalities: ineq.pl.

Every predicate of ineq.pl is a function here, in file order, named by
NAMES.md.  The commented-out predicates of ineq.pl (ineq_one/4's old body,
ineq_one_new/4, ineq_one_old/6, update_dep/4) are not ported.

Representations, as in bounded_simplex.py:

- The atoms `strict` and `nonstrict` are the bools True and False (bv.pl's
  'solve_<'/1 and 'solve_=<'/1 pass them).
- A linear form is linear_forms.LinearForm; `split_linear_form(Lin, H, R, I)`
  is reading `terms`, `rest` and `constant`.
- The `type/1` attribute is SolverState.bounds; the `strictness/1` value
  (Sold, Strict below) is the int attributes.strictness reads, bit 0b10 the
  lower bound and bit 0b01 the upper.
- `case_signum(Expression, Lt, Eq, Gt)` is an if/elif on
  arithmetic.sign(Expression): negative, zero, positive.
- A predicate that fails returns False.

Nothing here recurses: ineq.pl has no recursive predicate, and the loops
are bounded_simplex's (test_a_long_inequality_needs_no_recursion).
ineq.pl calls nothing of nf.pl, so this module imports bounded_simplex at
the top; bounded_simplex imports this module at its call sites.
"""
from clausal.logic.clpq.arithmetic import (
    ONE, ZERO, add, compare, divide, is_zero, negate, sign, subtract)
from clausal.logic.clpq.attributes import (
    BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE, BOUNDS_LOWER_ACTIVE_UPPER,
    BOUNDS_LOWER_UPPER, BOUNDS_LOWER_UPPER_ACTIVE, BOUNDS_NONE, BOUNDS_UPPER,
    BOUNDS_UPPER_ACTIVE, bounds_lower, bounds_lower_active,
    bounds_lower_active_upper, bounds_lower_upper, bounds_lower_upper_active,
    bounds_upper, bounds_upper_active, put_state, state_of, strictness,
    strictness_fields, with_changes)
from clausal.logic.clpq.bounded_simplex import (
    ABOVE_UPPER_BOUND, BELOW_LOWER_BOUND, back_substitute,
    back_substitute_delta, basis_add, decrease_step, dereference,
    determine_active_decrease, determine_active_increase, export_bindings,
    get_or_add_component, increase_step, lower_bound, pivot_exchange,
    reconsider, reconsider_basis_list_status, same_component, solve,
    unconstrained, upper_bound, variable_intern_with_bounds,
    variable_with_definition_intern)
from clausal.logic.clpq.linear_forms import (
    MINUS_ONE, LinearForm, add_linear_forms, add_linear_forms_scaled,
    normalize_scalar)
from clausal.logic.variables import Var, deref


def _put_type(variable, bounds, trail):
    """put_atts(X, type(Bounds))."""
    put_state(variable, with_changes(state_of(variable), bounds=bounds), trail)


def _put_strictness(variable, strict, trail):
    """put_atts(X, strictness(Strict))."""
    lower_strict, upper_strict = strictness_fields(strict)
    put_state(variable, with_changes(state_of(variable), lower_strict=lower_strict,
                                     upper_strict=upper_strict), trail)


def _put_type_and_strictness(variable, bounds, strict, trail):
    """put_atts(X, [type(Bounds), strictness(Strict)])."""
    lower_strict, upper_strict = strictness_fields(strict)
    put_state(variable, with_changes(state_of(variable), bounds=bounds,
                                     lower_strict=lower_strict,
                                     upper_strict=upper_strict), trail)


def _linear_type_strictness(variable):
    """get_atts(X, [linear_form(Lin), type(Type), strictness(Old)]):
    (Lin, Type, Old), or None where X lacks one of them."""
    state = state_of(deref(variable))
    if state is None or state.linear_form is None or state.bounds is None:
        return None
    return state.linear_form, state.bounds, strictness(state)


def _linear_form_of(variable):
    """get_atts(X, linear_form(LinX)): LinX, or None."""
    state = state_of(variable)
    if state is None:
        return None
    return state.linear_form


def _single_variable(variable):
    """[Z, Z, X*One]: the linear form of *variable* alone."""
    return LinearForm(ZERO, ZERO, [(variable, ONE)])


#
# Lin (=)< 0
#

def inequality(homogeneous, constant, normal_form, strict, trail):
    """ineq.pl, inequality/4 (ineq/4): `normal_form` (<|=<) 0, where
    *homogeneous* and *constant* are its split (nf.pl split/3), as bv.pl's
    'solve_<'/1 and 'solve_=<'/1 call it."""
    if not homogeneous:                                     # clause 1
        return inequality_ground(strict, constant)
    monomial = homogeneous[0]                               # clause 2
    powers = monomial.powers
    if len(powers) != 1 or powers[0][1] != 1:               # head needs [X^1]
        return False                       # (test_a_monomial_that_is_not_linear_fails)
    return inequality_cases(homogeneous, constant, normal_form, strict,
                            powers[0][0], monomial.coefficient, trail)


def inequality_cases(homogeneous, constant, normal_form, strict, variable,
                     coefficient, trail):
    """ineq.pl, inequality_cases/6 (ineq_cases/6).  1.3.3 passes the Tail of
    the homogeneous part; the port passes the whole part, and Tail is
    homogeneous[1:]."""
    if len(homogeneous) == 1:                               # clause 1: Tail = []
        return inequality_one_variable(strict, variable, coefficient, constant,
                                       trail)
    form = dereference(normal_form, trail)                  # clause 2: Id+Hd =< 0
    if form is None:
        return False
    return inequality_more_variables(form.terms, form.constant, form, strict,
                                     trail)


def inequality_ground(strict, constant):
    """ineq.pl, inequality_ground/2 (ineq_ground/2)."""
    if strict:
        return compare(constant, ZERO) < 0
    return compare(constant, ZERO) <= 0


#
# Special cases: k={+-}1,i=0
#

def inequality_one_variable(strict, variable, coefficient, constant, trail):
    """ineq.pl, inequality_one_variable/4 (ineq_one/4): K*X + I (<|=<) 0."""
    variable = deref(variable)
    if strict:                                              # clause 1
        if compare(coefficient, ZERO) > 0:
            if is_zero(constant):
                return inequality_one_variable_strict_positive_zero(variable, trail)
            return inequality_one_variable_strict_positive_constant(
                variable, divide(constant, coefficient), trail)
        if is_zero(constant):
            return inequality_one_variable_strict_negative_zero(variable, trail)
        return inequality_one_variable_strict_negative_constant(
            variable, divide(negate(constant), coefficient), trail)
    if compare(coefficient, ZERO) > 0:                      # clause 2
        if is_zero(constant):
            return inequality_one_variable_nonstrict_positive_zero(variable, trail)
        return inequality_one_variable_nonstrict_positive_constant(
            variable, divide(constant, coefficient), trail)
    if is_zero(constant):
        return inequality_one_variable_nonstrict_negative_zero(variable, trail)
    return inequality_one_variable_nonstrict_negative_constant(
        variable, divide(negate(constant), coefficient), trail)


# --------------------------- strict ----------------------------

def inequality_one_variable_strict_positive_zero(variable, trail):
    """ineq.pl, inequality_one_variable_strict_positive_zero/1
    (ineq_one_s_p_0/1): X < 0."""
    form = _linear_form_of(variable)
    if form is not None:                                    # old variable, this is deref
        return inequality_one_old_variable_strict_positive_zero(
            form.terms, variable, form.constant, trail)
    # new variable, nothing depends on it
    return variable_intern_with_bounds(bounds_upper(ZERO), variable, 0b01, trail)


def inequality_one_variable_strict_negative_zero(variable, trail):
    """ineq.pl, inequality_one_variable_strict_negative_zero/1
    (ineq_one_s_n_0/1): -X < 0."""
    form = _linear_form_of(variable)
    if form is not None:
        return inequality_one_old_variable_strict_negative_zero(
            form.terms, variable, form.constant, trail)
    return variable_intern_with_bounds(bounds_lower(ZERO), variable, 0b10, trail)


def inequality_one_variable_strict_positive_constant(variable, constant, trail):
    """ineq.pl, inequality_one_variable_strict_positive_constant/2
    (ineq_one_s_p_i/2): X + I < 0."""
    form = _linear_form_of(variable)
    if form is not None:
        return inequality_one_old_variable_strict_positive_constant(
            form.terms, constant, variable, form.constant, trail)
    return variable_intern_with_bounds(bounds_upper(negate(constant)), variable,
                                       0b01, trail)


def inequality_one_variable_strict_negative_constant(variable, constant, trail):
    """ineq.pl, inequality_one_variable_strict_negative_constant/2
    (ineq_one_s_n_i/2): -X + I < 0."""
    form = _linear_form_of(variable)
    if form is not None:
        return inequality_one_old_variable_strict_negative_constant(
            form.terms, constant, variable, form.constant, trail)
    return variable_intern_with_bounds(bounds_lower(constant), variable, 0b10, trail)


def inequality_one_old_variable_strict_positive_zero(terms, variable,
                                                     constant_x, trail):
    """ineq.pl, inequality_one_old_variable_strict_positive_zero/3
    (ineq_one_old_s_p_0/3): Lin(X) < 0 with Lin(X) = Ix + terms."""
    if not terms:                                           # clause 1
        return compare(constant_x, ZERO) < 0
    other, coefficient = terms[0]                           # clause 2
    if len(terms) == 1:
        bound = divide(negate(constant_x), coefficient)
        return update_independent(True, other, coefficient, bound, trail)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    return update_dependent_upper_strict(bounds, variable, form, ZERO, old, trail)


def inequality_one_old_variable_strict_negative_zero(terms, variable,
                                                     constant_x, trail):
    """ineq.pl, inequality_one_old_variable_strict_negative_zero/3
    (ineq_one_old_s_n_0/3)."""
    if not terms:
        return compare(constant_x, ZERO) > 0
    other, coefficient = terms[0]
    if len(terms) == 1:
        negated = negate(coefficient)
        bound = divide(constant_x, negated)
        return update_independent(True, other, negated, bound, trail)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    return update_dependent_lower_strict(bounds, variable, form, ZERO, old, trail)


def inequality_one_old_variable_strict_positive_constant(terms, constant,
                                                         variable, constant_x,
                                                         trail):
    """ineq.pl, inequality_one_old_variable_strict_positive_constant/4
    (ineq_one_old_s_p_i/4)."""
    if not terms:
        return compare(add(constant_x, constant), ZERO) < 0
    other, coefficient = terms[0]
    if len(terms) == 1:
        bound = divide(negate(add(constant_x, constant)), coefficient)
        return update_independent(True, other, coefficient, bound, trail)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    return update_dependent_upper_strict(bounds, variable, form, negate(constant),
                                         old, trail)


def inequality_one_old_variable_strict_negative_constant(terms, constant,
                                                         variable, constant_x,
                                                         trail):
    """ineq.pl, inequality_one_old_variable_strict_negative_constant/4
    (ineq_one_old_s_n_i/4)."""
    if not terms:
        return compare(add(negate(constant_x), constant), ZERO) < 0
    other, coefficient = terms[0]
    if len(terms) == 1:
        negated = negate(coefficient)
        bound = divide(subtract(constant_x, constant), negated)
        return update_independent(True, other, negated, bound, trail)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    return update_dependent_lower_strict(bounds, variable, form, constant, old,
                                         trail)


# -------------------------- nonstrict --------------------------

def inequality_one_variable_nonstrict_positive_zero(variable, trail):
    """ineq.pl, inequality_one_variable_nonstrict_positive_zero/1
    (ineq_one_n_p_0/1): X =< 0."""
    form = _linear_form_of(variable)
    if form is not None:                                    # old variable, this is deref
        return inequality_one_old_variable_nonstrict_positive_zero(
            form.terms, variable, form.constant, trail)
    # new variable, nothing depends on it
    return variable_intern_with_bounds(bounds_upper(ZERO), variable, 0b00, trail)


def inequality_one_variable_nonstrict_negative_zero(variable, trail):
    """ineq.pl, inequality_one_variable_nonstrict_negative_zero/1
    (ineq_one_n_n_0/1): -X =< 0."""
    form = _linear_form_of(variable)
    if form is not None:
        return inequality_one_old_variable_nonstrict_negative_zero(
            form.terms, variable, form.constant, trail)
    return variable_intern_with_bounds(bounds_lower(ZERO), variable, 0b00, trail)


def inequality_one_variable_nonstrict_positive_constant(variable, constant, trail):
    """ineq.pl, inequality_one_variable_nonstrict_positive_constant/2
    (ineq_one_n_p_i/2): X + I =< 0."""
    form = _linear_form_of(variable)
    if form is not None:
        return inequality_one_old_variable_nonstrict_positive_constant(
            form.terms, constant, variable, form.constant, trail)
    return variable_intern_with_bounds(bounds_upper(negate(constant)), variable,
                                       0b00, trail)


def inequality_one_variable_nonstrict_negative_constant(variable, constant, trail):
    """ineq.pl, inequality_one_variable_nonstrict_negative_constant/2
    (ineq_one_n_n_i/2): -X + I =< 0."""
    form = _linear_form_of(variable)
    if form is not None:
        return inequality_one_old_variable_nonstrict_negative_constant(
            form.terms, constant, variable, form.constant, trail)
    return variable_intern_with_bounds(bounds_lower(constant), variable, 0b00, trail)


def inequality_one_old_variable_nonstrict_positive_zero(terms, variable,
                                                        constant_x, trail):
    """ineq.pl, inequality_one_old_variable_nonstrict_positive_zero/3
    (ineq_one_old_n_p_0/3)."""
    if not terms:
        return compare(constant_x, ZERO) <= 0
    other, coefficient = terms[0]
    if len(terms) == 1:
        bound = divide(negate(constant_x), coefficient)
        return update_independent(False, other, coefficient, bound, trail)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    return update_dependent_upper(bounds, variable, form, ZERO, old, trail)


def inequality_one_old_variable_nonstrict_negative_zero(terms, variable,
                                                        constant_x, trail):
    """ineq.pl, inequality_one_old_variable_nonstrict_negative_zero/3
    (ineq_one_old_n_n_0/3)."""
    if not terms:
        return compare(constant_x, ZERO) >= 0
    other, coefficient = terms[0]
    if len(terms) == 1:
        negated = negate(coefficient)
        bound = divide(constant_x, negated)
        return update_independent(False, other, negated, bound, trail)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    return update_dependent_lower(bounds, variable, form, ZERO, old, trail)


def inequality_one_old_variable_nonstrict_positive_constant(terms, constant,
                                                            variable, constant_x,
                                                            trail):
    """ineq.pl, inequality_one_old_variable_nonstrict_positive_constant/4
    (ineq_one_old_n_p_i/4)."""
    if not terms:
        return compare(add(constant_x, constant), ZERO) <= 0
    other, coefficient = terms[0]
    if len(terms) == 1:
        bound = divide(negate(add(constant_x, constant)), coefficient)
        return update_independent(False, other, coefficient, bound, trail)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    return update_dependent_upper(bounds, variable, form, negate(constant), old,
                                  trail)


def inequality_one_old_variable_nonstrict_negative_constant(terms, constant,
                                                            variable, constant_x,
                                                            trail):
    """ineq.pl, inequality_one_old_variable_nonstrict_negative_constant/4
    (ineq_one_old_n_n_i/4)."""
    if not terms:
        return compare(add(negate(constant_x), constant), ZERO) <= 0
    other, coefficient = terms[0]
    if len(terms) == 1:
        negated = negate(coefficient)
        bound = divide(subtract(constant_x, constant), negated)
        return update_independent(False, other, negated, bound, trail)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    return update_dependent_lower(bounds, variable, form, constant, old, trail)


# ---------------------------------------------------------------

def inequality_more_variables(terms, constant, form, strict, trail):
    """ineq.pl, inequality_more_variables/4 (ineq_more/4): *form* is the
    dereferenced inequality, *terms* and *constant* its split."""
    if not terms:                                           # clause 1
        return inequality_ground(strict, constant)
    variable, coefficient = terms[0]                        # clause 2
    if len(terms) == 1:     # one var: update bound instead of slack introduction
        if get_or_add_component(variable, None, trail) is None:
            return False
        bound = divide(negate(constant), coefficient)
        return update_independent(strict, variable, coefficient, bound, trail)
    return inequality_more_variables_slack(strict, form, trail)


def inequality_more_variables_slack(strict, form, trail):
    """ineq.pl, inequality_more_variables/2 (ineq_more/2): introduce a slack
    variable S for *form* (<|=<) 0.  Where *form* has an unconstrained
    variable U, U absorbs the slack: S >= 0 (strict: S > 0) and U is
    defined over S.  Otherwise S, with S =< 0 (strict: S < 0), enters the
    basis.  The two clauses of 1.3.3 differ only in the strictness bits."""
    found = unconstrained(form)             # never fails, no implied value
    if found is not None:
        absorber, coefficient, rest = found
        slack = Var()
        if not variable_intern_with_bounds(bounds_lower(ZERO), slack,
                                           0b10 if strict else 0b00, trail):
            return False
        factor = divide(MINUS_ONE, coefficient)
        form_u = add_linear_forms_scaled(rest, factor,
                                         _single_variable(slack), factor)
        if form_u is None:
            return False
        component = get_or_add_component(absorber, None, trail)
        if component is None:
            return False
        if not same_component(form_u.terms, component, trail):
            return False
        return back_substitute(absorber, form_u, trail)
    slack = Var()
    if not variable_with_definition_intern(bounds_upper(ZERO), slack, form,
                                           0b01 if strict else 0b00, trail):
        return False
    if basis_add(slack, trail) is False:
        return False
    if not determine_active_decrease(form, trail):
        return False
    return reconsider(slack, trail)


def update_independent(strict, variable, coefficient, bound, trail):
    """ineq.pl, update_independent/4 (update_indep/4): K*X (<|=<) K*Bound for
    an independent X: an upper bound where K > 0, a lower where K < 0."""
    variable = deref(variable)
    found = _linear_type_strictness(variable)
    if found is None:
        return False
    form, bounds, old = found
    if strict:                                              # clause 1
        if compare(coefficient, ZERO) < 0:
            return update_independent_lower_strict(bounds, variable, form, bound,
                                                   old, trail)
        return update_independent_upper_strict(bounds, variable, form, bound, old,
                                               trail)
    if compare(coefficient, ZERO) < 0:                      # clause 2
        return update_independent_lower(bounds, variable, form, bound, old, trail)
    return update_independent_upper(bounds, variable, form, bound, old, trail)


# ---------------------------------------------------------------------------------------
#
# Update a bound on a var xi
#
#   a) independent variable
#
#	a1) update inactive bound: done
#
#	a2) update active bound:
#	    Determine [lu]b including most constraining row R
#	      If we are within: done
#	    else pivot(R,xi) and introduce bound via (b)
#
#	a3) introduce a bound on an unconstrained var:
#	    All vars that depend on xi are unconstrained (invariant) ->
#	      the bound cannot invalidate any Lhs
#
#   b) dependent variable
#
#	repair upper or lower (maybe just swap with an unconstrained var from Rhs)
#
# (ineq.pl's comments, kept.)  A dependent variable has no active bound, so
# update_dependent_* have clauses for t_none, t_l, t_u and t_lu only; any
# other type fails.

def _swap_with_unconstrained(variable, form, found, trail):
    """The `unconstrained(Lin, Uc, Kuc, Rest) -> ...` branch of the t_none
    clauses of update_dependent_*: Uc := (X - Rest)/Kuc, so X becomes
    independent."""
    absorber, coefficient, rest = found
    factor = divide(MINUS_ONE, coefficient)
    form_u = add_linear_forms_scaled(
        rest, factor, LinearForm(ZERO, ZERO, [(variable, MINUS_ONE)]), factor)
    if form_u is None:
        return False
    return back_substitute(absorber, form_u, trail)


def update_dependent_lower(bounds, variable, form, bound, old, trail):
    """ineq.pl, update_dependent_lower/5 (udl/5): X >= Bound, X dependent."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        _put_type_and_strictness(variable, bounds_lower(bound), 0b00, trail)
        found = unconstrained(form)
        if found is not None:
            return _swap_with_unconstrained(variable, form, found, trail)
        if basis_add(variable, trail) is False:
            return False
        if not determine_active_increase(form, trail):
            return False
        return reconsider(variable, trail)
    if kind == BOUNDS_LOWER:
        if sign(subtract(bound, bounds.lower)) <= 0:
            return True
        _put_type_and_strictness(variable, bounds_lower(bound), old & 0b01, trail)
        return reconsider_lower(variable, form, bound, trail)
    if kind == BOUNDS_UPPER:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return False
        if signum == 0:
            return solve_bound(form, bound, trail)
        _put_type(variable, bounds_lower_upper(bound, bounds.upper), trail)
        return reconsider_lower(variable, form, bound, trail)
    if kind == BOUNDS_LOWER_UPPER:
        if sign(subtract(bound, bounds.lower)) <= 0:
            return True
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return False
        if signum == 0:
            if old & 0b01 != 0:
                return False
            return solve_bound(form, bound, trail)
        _put_type_and_strictness(variable, bounds_lower_upper(bound, bounds.upper),
                                 old & 0b01, trail)
        return reconsider_lower(variable, form, bound, trail)
    return False


def update_dependent_lower_strict(bounds, variable, form, bound, old, trail):
    """ineq.pl, update_dependent_lower_strict/5 (udls/5): X > Bound."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        _put_type_and_strictness(variable, bounds_lower(bound), 0b10, trail)
        found = unconstrained(form)
        if found is not None:
            return _swap_with_unconstrained(variable, form, found, trail)
        if basis_add(variable, trail) is False:
            return False
        if not determine_active_increase(form, trail):
            return False
        return reconsider(variable, trail)
    if kind == BOUNDS_LOWER:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b10, trail)
            return True
        _put_type_and_strictness(variable, bounds_lower(bound), old | 0b10, trail)
        return reconsider_lower(variable, form, bound, trail)
    if kind == BOUNDS_UPPER:
        if compare(bounds.upper, bound) <= 0:
            return False
        _put_type_and_strictness(variable, bounds_lower_upper(bound, bounds.upper),
                                 old | 0b10, trail)
        return reconsider_lower(variable, form, bound, trail)
    if kind == BOUNDS_LOWER_UPPER:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b10, trail)
            return True
        if compare(bounds.upper, bound) <= 0:
            return False
        _put_type_and_strictness(variable, bounds_lower_upper(bound, bounds.upper),
                                 old | 0b10, trail)
        return reconsider_lower(variable, form, bound, trail)
    return False


def update_dependent_upper(bounds, variable, form, bound, old, trail):
    """ineq.pl, update_dependent_upper/5 (udu/5): X =< Bound, X dependent."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        _put_type_and_strictness(variable, bounds_upper(bound), 0b00, trail)
        found = unconstrained(form)
        if found is not None:
            return _swap_with_unconstrained(variable, form, found, trail)
        if basis_add(variable, trail) is False:
            return False
        if not determine_active_decrease(form, trail):
            return False
        return reconsider(variable, trail)
    if kind == BOUNDS_UPPER:
        if sign(subtract(bounds.upper, bound)) <= 0:
            return True
        _put_type_and_strictness(variable, bounds_upper(bound), old & 0b10, trail)
        return reconsider_upper(variable, form, bound, trail)
    if kind == BOUNDS_LOWER:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return False
        if signum == 0:
            return solve_bound(form, bound, trail)
        _put_type(variable, bounds_lower_upper(bounds.lower, bound), trail)
        return reconsider_upper(variable, form, bound, trail)
    if kind == BOUNDS_LOWER_UPPER:
        if sign(subtract(bounds.upper, bound)) <= 0:
            return True
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return False
        if signum == 0:
            if old & 0b10 != 0:
                return False
            return solve_bound(form, bound, trail)
        _put_type_and_strictness(variable, bounds_lower_upper(bounds.lower, bound),
                                 old & 0b10, trail)
        return reconsider_upper(variable, form, bound, trail)
    return False


def update_dependent_upper_strict(bounds, variable, form, bound, old, trail):
    """ineq.pl, update_dependent_upper_strict/5 (udus/5): X < Bound."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        _put_type_and_strictness(variable, bounds_upper(bound), 0b01, trail)
        found = unconstrained(form)
        if found is not None:
            return _swap_with_unconstrained(variable, form, found, trail)
        if basis_add(variable, trail) is False:
            return False
        if not determine_active_decrease(form, trail):
            return False
        return reconsider(variable, trail)
    if kind == BOUNDS_UPPER:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b01, trail)
            return True
        _put_type_and_strictness(variable, bounds_upper(bound), old | 0b01, trail)
        return reconsider_upper(variable, form, bound, trail)
    if kind == BOUNDS_LOWER:
        if compare(bound, bounds.lower) <= 0:
            return False
        _put_type_and_strictness(variable, bounds_lower_upper(bounds.lower, bound),
                                 old | 0b01, trail)
        return reconsider_upper(variable, form, bound, trail)
    if kind == BOUNDS_LOWER_UPPER:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b01, trail)
            return True
        if compare(bound, bounds.lower) <= 0:
            return False
        _put_type_and_strictness(variable, bounds_lower_upper(bounds.lower, bound),
                                 old | 0b01, trail)
        return reconsider_upper(variable, form, bound, trail)
    return False


def _tighten_active_upper(variable, upper, bound, new_bounds, pivot_bounds,
                          strict, trail):
    """The body shared by the `update active` clauses of
    update_independent_upper/5 and update_independent_upper_strict/5 once
    Bound < U: X's active upper bound U moves to Bound.  Where the tightest
    row Vlb reaches its bound first (Bound =< Lb + U), X is pivoted against
    it (and Vlb gets the type *pivot_bounds*); otherwise X's value moves by
    Bound - U
    (test_tightening_an_active_upper_bound_pivots)."""
    tightest = lower_bound(variable)
    if tightest is not None and compare(bound, add(tightest[2], upper)) <= 0:
        _put_type_and_strictness(variable, new_bounds, strict, trail)
        if not pivot_exchange(tightest[0], variable, tightest[1], pivot_bounds,
                              trail):
            return False
        return reconsider(variable, trail)
    _put_type_and_strictness(variable, new_bounds, strict, trail)
    return back_substitute_delta(variable, subtract(bound, upper), trail)


def _tighten_active_lower(variable, lower, bound, new_bounds, pivot_bounds,
                          strict, trail):
    """The mirror of _tighten_active_upper for the `update active bound`
    clauses of update_independent_lower/5 and
    update_independent_lower_strict/5: Bound > L, and X is pivoted where
    Bound >= Ub + L
    (test_tightening_an_active_bound_pivots_and_finds_the_implied_values)."""
    tightest = upper_bound(variable)
    if tightest is not None and compare(bound, add(tightest[2], lower)) >= 0:
        _put_type_and_strictness(variable, new_bounds, strict, trail)
        if not pivot_exchange(tightest[0], variable, tightest[1], pivot_bounds,
                              trail):
            return False
        return reconsider(variable, trail)
    # max(X) >= Ub, no implied value missed
    _put_type_and_strictness(variable, new_bounds, strict, trail)
    return back_substitute_delta(variable, subtract(bound, lower), trail)


def update_independent_upper(bounds, variable, form, bound, old, trail):
    """ineq.pl, update_independent_upper/5 (uiu/5): X =< Bound, X
    independent."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        _put_type_and_strictness(variable, bounds_upper(bound), 0b00, trail)
        return True
    if kind == BOUNDS_UPPER:
        if sign(subtract(bounds.upper, bound)) <= 0:
            return True
        _put_type_and_strictness(variable, bounds_upper(bound), old & 0b10, trail)
        return True
    if kind == BOUNDS_LOWER:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return False
        if signum == 0:
            return solve_bound(form, bound, trail)
        _put_type(variable, bounds_lower_upper(bounds.lower, bound), trail)
        return True
    if kind == BOUNDS_LOWER_ACTIVE:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return False
        if signum == 0:
            return solve_bound(form, bound, trail)
        _put_type(variable, bounds_lower_active_upper(bounds.lower, bound), trail)
        return True
    if kind == BOUNDS_LOWER_UPPER:
        if sign(subtract(bounds.upper, bound)) <= 0:
            return True
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return False
        if signum == 0:
            if old & 0b10 != 0:
                return False
            return solve_bound(form, bound, trail)
        _put_type_and_strictness(variable, bounds_lower_upper(bounds.lower, bound),
                                 old & 0b10, trail)
        return True
    if kind == BOUNDS_LOWER_ACTIVE_UPPER:
        if sign(subtract(bounds.upper, bound)) <= 0:
            return True
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return False
        if signum == 0:
            if old & 0b10 != 0:
                return False
            return solve_bound(form, bound, trail)
        _put_type_and_strictness(variable,
                                 bounds_lower_active_upper(bounds.lower, bound),
                                 old & 0b10, trail)
        return True
    # update active:
    if kind == BOUNDS_UPPER_ACTIVE:
        if sign(subtract(bounds.upper, bound)) <= 0:
            return True
        return _tighten_active_upper(variable, bounds.upper, bound,
                                     bounds_upper_active(bound),
                                     bounds_upper(bound), old & 0b10, trail)
    if kind == BOUNDS_LOWER_UPPER_ACTIVE:
        if sign(subtract(bounds.upper, bound)) <= 0:
            return True
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return False
        if signum == 0:
            if old & 0b10 != 0:
                return False
            return solve_bound(form, bound, trail)
        return _tighten_active_upper(
            variable, bounds.upper, bound,
            bounds_lower_upper_active(bounds.lower, bound),
            bounds_lower_upper(bounds.lower, bound), old & 0b10, trail)
    return False


def update_independent_upper_strict(bounds, variable, form, bound, old, trail):
    """ineq.pl, update_independent_upper_strict/5 (uius/5): X < Bound, X
    independent."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        _put_type_and_strictness(variable, bounds_upper(bound), 0b01, trail)
        return True
    if kind == BOUNDS_UPPER:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b01, trail)
            return True
        _put_type_and_strictness(variable, bounds_upper(bound), old | 0b01, trail)
        return True
    if kind == BOUNDS_LOWER:
        if compare(bound, bounds.lower) <= 0:
            return False
        _put_type_and_strictness(variable, bounds_lower_upper(bounds.lower, bound),
                                 old | 0b01, trail)
        return True
    if kind == BOUNDS_LOWER_ACTIVE:
        if compare(bound, bounds.lower) <= 0:
            return False
        _put_type_and_strictness(variable,
                                 bounds_lower_active_upper(bounds.lower, bound),
                                 old | 0b01, trail)
        return True
    if kind == BOUNDS_LOWER_UPPER:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b01, trail)
            return True
        if compare(bound, bounds.lower) <= 0:
            return False
        _put_type_and_strictness(variable, bounds_lower_upper(bounds.lower, bound),
                                 old | 0b01, trail)
        return True
    if kind == BOUNDS_LOWER_ACTIVE_UPPER:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b01, trail)
            return True
        if compare(bound, bounds.lower) <= 0:
            return False
        _put_type_and_strictness(variable,
                                 bounds_lower_active_upper(bounds.lower, bound),
                                 old | 0b01, trail)
        return True
    # update active:
    if kind == BOUNDS_UPPER_ACTIVE:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b01, trail)
            return True
        return _tighten_active_upper(variable, bounds.upper, bound,
                                     bounds_upper_active(bound),
                                     bounds_upper(bound), old | 0b01, trail)
    if kind == BOUNDS_LOWER_UPPER_ACTIVE:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b01, trail)
            return True
        if compare(bound, bounds.lower) <= 0:
            return False
        return _tighten_active_upper(
            variable, bounds.upper, bound,
            bounds_lower_upper_active(bounds.lower, bound),
            bounds_lower_upper(bounds.lower, bound), old | 0b01, trail)
    return False


def update_independent_lower(bounds, variable, form, bound, old, trail):
    """ineq.pl, update_independent_lower/5 (uil/5): X >= Bound, X
    independent."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        _put_type_and_strictness(variable, bounds_lower(bound), 0b00, trail)
        return True
    if kind == BOUNDS_LOWER:
        if sign(subtract(bound, bounds.lower)) <= 0:
            return True
        _put_type_and_strictness(variable, bounds_lower(bound), old & 0b01, trail)
        return True
    if kind == BOUNDS_UPPER:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return False
        if signum == 0:
            return solve_bound(form, bound, trail)
        _put_type(variable, bounds_lower_upper(bound, bounds.upper), trail)
        return True
    if kind == BOUNDS_UPPER_ACTIVE:
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return False
        if signum == 0:
            return solve_bound(form, bound, trail)
        _put_type(variable, bounds_lower_upper_active(bound, bounds.upper), trail)
        return True
    if kind == BOUNDS_LOWER_UPPER:
        if sign(subtract(bound, bounds.lower)) <= 0:
            return True
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return False
        if signum == 0:
            if old & 0b01 != 0:
                return False
            return solve_bound(form, bound, trail)
        _put_type_and_strictness(variable, bounds_lower_upper(bound, bounds.upper),
                                 old & 0b01, trail)
        return True
    if kind == BOUNDS_LOWER_UPPER_ACTIVE:
        if sign(subtract(bound, bounds.lower)) <= 0:
            return True
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return False
        if signum == 0:
            if old & 0b01 != 0:
                return False
            return solve_bound(form, bound, trail)
        _put_type_and_strictness(variable,
                                 bounds_lower_upper_active(bound, bounds.upper),
                                 old & 0b01, trail)
        return True
    # update active bound: % { a>=100,d=<5000,c>=10,-2*a+d-c=10,a>=2490 }.
    if kind == BOUNDS_LOWER_ACTIVE:
        if sign(subtract(bound, bounds.lower)) <= 0:
            return True
        return _tighten_active_lower(variable, bounds.lower, bound,
                                     bounds_lower_active(bound),
                                     bounds_lower(bound), old & 0b01, trail)
    if kind == BOUNDS_LOWER_ACTIVE_UPPER:
        if sign(subtract(bound, bounds.lower)) <= 0:
            return True
        signum = sign(subtract(bounds.upper, bound))
        if signum < 0:
            return False
        if signum == 0:
            if old & 0b01 != 0:
                return False
            return solve_bound(form, bound, trail)
        return _tighten_active_lower(
            variable, bounds.lower, bound,
            bounds_lower_active_upper(bound, bounds.upper),
            bounds_lower_upper(bound, bounds.upper), old & 0b01, trail)
    return False


def update_independent_lower_strict(bounds, variable, form, bound, old, trail):
    """ineq.pl, update_independent_lower_strict/5 (uils/5): X > Bound, X
    independent."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        _put_type_and_strictness(variable, bounds_lower(bound), 0b10, trail)
        return True
    if kind == BOUNDS_LOWER:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b10, trail)
            return True
        _put_type_and_strictness(variable, bounds_lower(bound), old | 0b10, trail)
        return True
    if kind == BOUNDS_UPPER:
        if compare(bounds.upper, bound) <= 0:
            return False
        _put_type_and_strictness(variable, bounds_lower_upper(bound, bounds.upper),
                                 old | 0b10, trail)
        return True
    if kind == BOUNDS_UPPER_ACTIVE:
        if compare(bounds.upper, bound) <= 0:
            return False
        _put_type_and_strictness(variable,
                                 bounds_lower_upper_active(bound, bounds.upper),
                                 old | 0b10, trail)
        return True
    if kind == BOUNDS_LOWER_UPPER:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b10, trail)
            return True
        if compare(bounds.upper, bound) <= 0:
            return False
        _put_type_and_strictness(variable, bounds_lower_upper(bound, bounds.upper),
                                 old | 0b10, trail)
        return True
    if kind == BOUNDS_LOWER_UPPER_ACTIVE:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b10, trail)
            return True
        if compare(bounds.upper, bound) <= 0:
            return False
        _put_type_and_strictness(variable,
                                 bounds_lower_upper_active(bound, bounds.upper),
                                 old | 0b10, trail)
        return True
    # update active bound:
    if kind == BOUNDS_LOWER_ACTIVE:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b10, trail)
            return True
        return _tighten_active_lower(variable, bounds.lower, bound,
                                     bounds_lower_active(bound),
                                     bounds_lower(bound), old | 0b10, trail)
    if kind == BOUNDS_LOWER_ACTIVE_UPPER:
        signum = sign(subtract(bound, bounds.lower))
        if signum < 0:
            return True
        if signum == 0:
            _put_strictness(variable, old | 0b10, trail)
            return True
        if compare(bounds.upper, bound) <= 0:
            return False
        return _tighten_active_lower(
            variable, bounds.lower, bound,
            bounds_lower_active_upper(bound, bounds.upper),
            bounds_lower_upper(bound, bounds.upper), old | 0b10, trail)
    return False


def reconsider_upper(variable, form, upper, trail):
    """ineq.pl, reconsider_upper/3: X has a new upper bound U; where its
    value R + I is at or above U, decrease it and export the implied
    bindings."""
    if compare(add(form.rest, form.constant), upper) >= 0:  # clause 1, then cut
        status = decrease_step(form.terms, trail)
        if status is None:
            return False
        bindings = []
        if not reconsider_basis_list_status(status, variable, None, bindings,
                                            (ABOVE_UPPER_BOUND, upper), trail):
            return False
        return export_bindings(bindings, trail)
    return True                                             # clause 2


def reconsider_lower(variable, form, lower, trail):
    """ineq.pl, reconsider_lower/3."""
    if compare(add(form.rest, form.constant), lower) <= 0:
        status = increase_step(form.terms, trail)
        if status is None:
            return False
        bindings = []
        if not reconsider_basis_list_status(status, variable, None, bindings,
                                            (BELOW_LOWER_BOUND, lower), trail):
            return False
        return export_bindings(bindings, trail)
    return True


#
# lin is dereferenced
#

def solve_bound(form, bound, trail):
    """ineq.pl, solve_bound/2: solve *form* = Bound."""
    if is_zero(bound):                                      # clause 1
        return solve(form, trail)
    equation = add_linear_forms(normalize_scalar(negate(bound)), form)  # clause 2
    if equation is None:
        return False
    return solve(equation, trail)
