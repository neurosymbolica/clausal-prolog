# Ported from the clp(q,r) 1.3.3 distribution, file fourmotz.pl (banner: version 1.3.2)
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Fourier-Motzkin elimination: fourmotz.pl.

Every predicate of fourmotz.pl is a function here, in file order, named by
NAMES.md.  Where fourmotz.pl defines one name at two arities, the second
gets its own name (NAMES.md, "Names the port adds").

Representations:

- An occurrence `D:K` (row D holds the variable with coefficient K) is the
  pair (D, K); a list of them is a Python list.
- A cross product entry `less_or_equal_zero(Strict, Lin)` is the pair
  (strict, form): form (<|=<) 0, strict 1 or 0.
- A pivot `T:Nt` (projection.make_target_independent) is the pair (T, Nt).
- A member list is a components.ListCell chain, walked up to its tail.
- `findall/3` over the nondeterministic `fourier_motzkin_cross_product_filter`
  is that function returning the list of its answers.

A predicate that fails returns False or None, as its docstring says.

Imports at the call site.  fourmotz.pl and project.pl call each other;
projection imports this module at the top, so this module imports
projection at its call sites ("cyclic").
"""
from clausal.logic.clpq import limits
from clausal.logic.clpq.arithmetic import (
    ZERO, divide, multiply, negate, sign, add)
from clausal.logic.clpq.attributes import (
    BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE, BOUNDS_LOWER_ACTIVE_UPPER,
    BOUNDS_LOWER_UPPER, BOUNDS_LOWER_UPPER_ACTIVE, BOUNDS_UPPER,
    BOUNDS_UPPER_ACTIVE, bounds_lower, bounds_lower_upper, bounds_upper,
    state_of, strictness)
from clausal.logic.clpq.bounded_simplex import (
    _put_attributes, all_variables, basis_add, detach_bounds, pivot,
    variable_with_definition_intern)
from clausal.logic.clpq.components import ListCell
from clausal.logic.clpq.linear_forms import (
    MINUS_ONE, add_linear_forms, add_linear_forms_first_scaled, independent,
    normal_form_coefficient_of, normalize_scalar)
from clausal.logic.clpq.redundancy import redundancy_variables
from clausal.logic.variables import Var, deref, is_var


def fourier_motzkin_eliminate(variables, target, pivots, trail):
    """fourmotz.pl, fourier_motzkin_eliminate/3 (fm_elim/3): eliminate the
    non-target variables of *variables* that occur in a bounded row."""
    return fourier_motzkin_eliminate_internal(prefilter(variables, trail),
                                              target, pivots, trail)


def prefilter(variables, trail):
    """fourmotz.pl, prefilter/2: the variables without `target` that occur,
    each marked `keep_independent`."""
    result = []
    for variable in variables:
        variable = deref(variable)
        if not is_var(variable):
            continue
        state = state_of(variable)
        if state is not None and state.target:
            continue
        if occurs(variable):
            result.append(variable)
            _put_attributes(variable, trail, keep_independent=True)
    return result


def fourier_motzkin_eliminate_internal(variables, target, pivots, trail):
    """fourmotz.pl, fourier_motzkin_eliminate_internal/3 (fm_elim_int/3).
    The target variables are marked; *target* lists them too.  The
    recursion is a loop; where best/3 finds no candidate, it gives up.

    Each elimination derives the cross product of its occurrences, a row
    each.  They are charged to the projection before they are made: past
    the clpq_projection cap it raises `resource_error(clpq_projection)`
    (limits.charge_projection, DEVIATIONS.md D24); their number can grow
    exponentially."""
    while variables:
        found = best(variables)
        if found is not None:
            chosen, rest = found
            occurrences = occurences(chosen)
            if occurrences is None:
                return False
            limits.charge_projection(
                cross_product_cardinality(occurrences, 0))
            pivots = eliminate_minimum(chosen, occurrences, target, pivots,
                                       trail)
            if pivots is None:
                return False
        else:                                               # give up
            rest = []
        variables = rest
    return unkeep(pivots, trail)                            # done


def best(variables):
    """fourmotz.pl, best/3: the variable with the smallest net growth of the
    inequality system on its elimination (the first one, on a tie, as
    keysort/2 is stable), and the others in order; None where there is no
    candidate."""
    deltas = fourier_motzkin_cross_product_filter(variables)
    if not deltas:
        return None
    least_delta, least_index = deltas[0]
    for delta, index in deltas:
        if delta < least_delta:
            least_delta = delta
            least_index = index
    return select_nth(variables, least_index)


def fourier_motzkin_cross_product_filter(variables):
    """fourmotz.pl, fourier_motzkin_cross_product_filter/3 (fm_cp_filter/3),
    every answer in order, as best/3's findall/3 collects them: a list of
    (Delta, N) with N the 1-based position of an independent non-target
    variable that occurs."""
    answers = []
    length = len(variables)
    for variable, rest in member_with_rest(variables):
        variable = deref(variable)
        if not is_var(variable):
            continue
        state = state_of(variable)
        if state is None or state.target or state.linear_form is None:
            continue
        if not independent(state.linear_form, variable):
            continue
        occurrences = occurences(variable)
        if not occurrences:
            continue
        new_count = cross_product_cardinality(occurrences, 0)
        answers.append((new_count - len(occurrences), length - len(rest)))
    return answers


def member_with_rest(items):
    """fourmotz.pl, member_with_rest/3, every answer: (X, the elements after
    X) for each X in order."""
    answers = []
    for index in range(len(items)):
        answers.append((items[index], items[index + 1:]))
    return answers


def select_nth(items, n):
    """fourmotz.pl, select_nth/4,5: the n-th element (1-based) and the
    others in order."""
    return items[n - 1], items[:n - 1] + items[n:]


#
# fm_detach + reverse_pivot introduce indep t_none, which
# invalidates the invariants
#
def eliminate_minimum(variable, occurrences, target, pivots, trail):
    """fourmotz.pl, eliminate_minimum/5 (elim_min/5): eliminate *variable*,
    replacing its bounded rows *occurrences* by their cross product.
    Returns the new pivots, or None."""
    from clausal.logic.clpq.projection import (    # cyclic: project.pl
        drop_dependent, make_target_independent)
    new = crossproduct(occurrences)
    if not activate_crossproduct(new, trail):
        return None
    if not reverse_pivot(pivots, trail):
        return None
    if not fourier_motzkin_detach(occurrences, trail):
        return None
    members = all_variables(variable)
    if members is None:
        return None
    if not redundancy_variables(members, trail):    # only for New \== []
        return None
    new_pivots = make_target_independent(target, trail)
    if new_pivots is None:
        return None
    drop_dependent(members, trail)
    return new_pivots


#
# restore NF by reverse pivoting
#
def reverse_pivot(pivots, trail):
    """fourmotz.pl, reverse_pivot/1: undo each pivot `I:D` in list order,
    head first, as reverse_pivot/1's recursion walks the list."""
    for independent_variable, dependent in pivots:
        state = state_of(dependent)
        if state is None or state.bounds is None:
            return False
        _put_attributes(dependent, trail, keep=False)       # no longer
        if not pivot(dependent, independent_variable, state.bounds, trail):
            return False
    return True


def unkeep(pivots, trail):
    """fourmotz.pl, unkeep/1."""
    from clausal.logic.clpq.projection import (    # cyclic: project.pl
        drop_dependent_one)
    for _, dependent in pivots:
        _put_attributes(dependent, trail, keep=False)
        drop_dependent_one(dependent, trail)
    return True


#
# All we drop are bounds
#
def fourier_motzkin_detach(occurrences, trail):
    """fourmotz.pl, fourier_motzkin_detach/1 (fm_detach/1)."""
    for dependent, _ in occurrences:
        if not detach_bounds(dependent, trail):
            return False
    return True


#
# Todo: maybe bulk_basis_add
#
def activate_crossproduct(new, trail):
    """fourmotz.pl, activate_crossproduct/1: each `Lin (<|=<) 0` becomes a
    new variable defined by Lin with the upper bound 0, in the basis."""
    for strict, form in new:
        variable = Var()
        if not variable_with_definition_intern(bounds_upper(ZERO), variable,
                                               form, strict, trail):
            return False
        if basis_add(variable, trail) is False:
            return False
    return True


# ------------------------------------------------------------------------------

def crossproduct(occurrences):
    """fourmotz.pl, crossproduct//1: the entries for every pair of
    occurrences, in the order of the DCG (each A with every later B)."""
    result = []
    for index in range(len(occurrences)):
        crossproduct_with(occurrences[index + 1:], occurrences[index], result)
    return result


def crossproduct_with(rest, first, result):
    """fourmotz.pl, crossproduct//2: the entries for *first* (`A:Ka`) with
    each `B:Kb` of *rest*, appended to *result*."""
    a, coefficient_a = first
    state_a = state_of(a)
    for b, coefficient_b in rest:
        state_b = state_of(b)
        k = divide(negate(coefficient_b), coefficient_a)
        form = add_linear_forms_first_scaled(state_a.linear_form, k,
                                             state_b.linear_form)
        strict_a = strictness(state_a)
        strict_b = strictness(state_b)
        if sign(k) > 0:                                 # signs were opposite
            strict = strict_a | strict_b
            cross_lower(state_a.bounds, state_b.bounds, k, form, strict, result)
            cross_upper(state_a.bounds, state_b.bounds, k, form, strict, result)
        else:                   # La =< A =< Ua -> -Ua =< -A =< -La
            flipped = flip(state_a.bounds)
            strict = flip_strict(strict_a) | strict_b
            cross_lower(flipped, state_b.bounds, k, form, strict, result)
            cross_upper(flipped, state_b.bounds, k, form, strict, result)


def cross_lower(bounds_a, bounds_b, k, form, strict, result):
    """fourmotz.pl, cross_lower//5: where both have a lower bound,
    `Ln - Lin =< 0` with Ln = K*La + Lb, strictness normalized to an upper
    bound."""
    lower_a = lower(bounds_a)
    lower_b = lower(bounds_b)
    if lower_a is None or lower_b is None:
        return
    scalar = normalize_scalar(add(multiply(k, lower_a), lower_b))
    left = add_linear_forms_first_scaled(form, MINUS_ONE, scalar)
    result.append((strict >> 1, left))


def cross_upper(bounds_a, bounds_b, k, form, strict, result):
    """fourmotz.pl, cross_upper//5: where both have an upper bound,
    `Lin + Un =< 0` with Un = -(K*Ua + Ub)."""
    upper_a = upper(bounds_a)
    upper_b = upper(bounds_b)
    if upper_a is None or upper_b is None:
        return
    scalar = normalize_scalar(negate(add(multiply(k, upper_a), upper_b)))
    left = add_linear_forms(scalar, form)
    result.append((strict & 0b01, left))


def lower(bounds):
    """fourmotz.pl, lower/2: the lower bound of a bound type, or None."""
    kind = bounds.kind
    if kind == BOUNDS_LOWER or kind == BOUNDS_LOWER_UPPER \
            or kind == BOUNDS_LOWER_ACTIVE or kind == BOUNDS_LOWER_ACTIVE_UPPER \
            or kind == BOUNDS_LOWER_UPPER_ACTIVE:
        return bounds.lower
    return None


def upper(bounds):
    """fourmotz.pl, upper/2: the upper bound of a bound type, or None."""
    kind = bounds.kind
    if kind == BOUNDS_UPPER or kind == BOUNDS_LOWER_UPPER \
            or kind == BOUNDS_UPPER_ACTIVE or kind == BOUNDS_LOWER_ACTIVE_UPPER \
            or kind == BOUNDS_LOWER_UPPER_ACTIVE:
        return bounds.upper
    return None


def flip(bounds):
    """fourmotz.pl, flip/2: the bound type of -A.  An active bound comes
    back inactive.  None for t_none, which has no clause."""
    kind = bounds.kind
    if kind == BOUNDS_LOWER or kind == BOUNDS_LOWER_ACTIVE:
        return bounds_upper(bounds.lower)
    if kind == BOUNDS_UPPER or kind == BOUNDS_UPPER_ACTIVE:
        return bounds_lower(bounds.upper)
    if kind == BOUNDS_LOWER_UPPER or kind == BOUNDS_LOWER_UPPER_ACTIVE \
            or kind == BOUNDS_LOWER_ACTIVE_UPPER:
        return bounds_lower_upper(bounds.upper, bounds.lower)
    return None


def flip_strict(strict):
    """fourmotz.pl, flip_strict/2: swap the lower (0b10) and upper (0b01)
    bits."""
    return ((strict & 0b01) << 1) | ((strict & 0b10) >> 1)


def cross_product_cardinality(occurrences, count):
    """fourmotz.pl, cross_product_cardinality/3 (cp_card/3): *count* plus
    the number of entries crossproduct//1 makes, without making them."""
    for index in range(len(occurrences)):
        count = cross_product_cardinality_with(occurrences[index + 1:],
                                               occurrences[index], count)
    return count


def cross_product_cardinality_with(rest, first, count):
    """fourmotz.pl, cross_product_cardinality/4 (cp_card/4)."""
    a, coefficient_a = first
    bounds_a = state_of(a).bounds
    for b, coefficient_b in rest:
        bounds_b = state_of(b).bounds
        k = divide(negate(coefficient_b), coefficient_a)
        if sign(k) > 0:                                 # signs were opposite
            count = cross_product_cardinality_lower(bounds_a, bounds_b, count)
            count = cross_product_cardinality_upper(bounds_a, bounds_b, count)
        else:
            flipped = flip(bounds_a)
            count = cross_product_cardinality_lower(flipped, bounds_b, count)
            count = cross_product_cardinality_upper(flipped, bounds_b, count)
    return count


def cross_product_cardinality_lower(bounds_a, bounds_b, count):
    """fourmotz.pl, cross_product_cardinality_lower/4 (cp_card_lower/4)."""
    if lower(bounds_a) is not None and lower(bounds_b) is not None:
        return count + 1
    return count


def cross_product_cardinality_upper(bounds_a, bounds_b, count):
    """fourmotz.pl, cross_product_cardinality_upper/4 (cp_card_upper/4)."""
    if upper(bounds_a) is not None and upper(bounds_b) is not None:
        return count + 1
    return count


# ------------------------------------------------------------------------------

def occurences(variable):
    """fourmotz.pl, occurences/2: the rows of *variable*'s component with a
    bound that hold *variable*, as (row variable, coefficient) pairs; None
    where all_variables/2 fails."""
    members = all_variables(variable)
    if members is None:
        return None
    return occurences_in(members, variable)


def occurences_in(members, variable):
    """fourmotz.pl, occurences/3, on the open member list up to its tail."""
    result = []
    node = deref(members)
    while type(node) is ListCell:
        member = deref(node.head)
        node = deref(node.rest)
        state = state_of(member) if is_var(member) else None
        if state is None or state.linear_form is None or state.bounds is None:
            continue
        if not occurrence_type_filter(state.bounds):
            continue
        coefficient = normal_form_coefficient_of(state.linear_form, variable)
        if coefficient is not None:
            result.append((member, coefficient))
    return result


def occurrence_type_filter(bounds):
    """fourmotz.pl, occurrence_type_filter/1: any type but t_none."""
    kind = bounds.kind
    return kind == BOUNDS_LOWER or kind == BOUNDS_UPPER \
        or kind == BOUNDS_LOWER_UPPER or kind == BOUNDS_LOWER_ACTIVE \
        or kind == BOUNDS_UPPER_ACTIVE or kind == BOUNDS_LOWER_UPPER_ACTIVE \
        or kind == BOUNDS_LOWER_ACTIVE_UPPER


#
# occurs( V) :-  occurences( V, Occ),  Occ = [_|_].
#
def occurs(variable):
    """fourmotz.pl, occurs/1."""
    members = all_variables(variable)
    if members is None:
        return False
    return occurs_in(members, variable)


def occurs_in(members, variable):
    """fourmotz.pl, occurs/2: the first bounded row holding *variable*
    ends the walk."""
    node = deref(members)
    while type(node) is ListCell:
        member = deref(node.head)
        node = deref(node.rest)
        state = state_of(member) if is_var(member) else None
        if state is None or state.linear_form is None or state.bounds is None:
            continue
        if occurrence_type_filter(state.bounds) and \
                normal_form_coefficient_of(state.linear_form, variable) is not None:
            return True
    return False
