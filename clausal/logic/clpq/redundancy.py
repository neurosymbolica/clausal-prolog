# Ported from the clp(q,r) 1.3.3 distribution, file redund.pl (banner: version 1.3.2)
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Redundancy elimination: redund.pl.

Every predicate of redund.pl is a function here, in file order, named by
NAMES.md.  A bound is redundant when the rest of the store implies it:
redundant/3 drops it, then posts its negation; where that post fails, the
bound stays dropped.

Backtracking.  1.3.3 runs redundant/3 as the condition of an if-then-else,
so a bound that turns out not to be redundant comes back when the
condition fails, and the negation is posted inside `\\+` (negate_lower/3,
negate_upper/3 unfold it), so it never stays.  The port takes a trail mark
before each and undoes to it (test_a_bound_that_is_not_redundant_comes_back,
test_negate_lower_leaves_the_store_as_it_was).

Lists: a variable list is a Python list or a components.ListCell chain
(an open member list), walked up to its tail.
"""
from clausal.logic.clpq.arithmetic import negate, to_number
from clausal.logic.clpq.attributes import (
    BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE, BOUNDS_LOWER_ACTIVE_UPPER,
    BOUNDS_LOWER_UPPER, BOUNDS_LOWER_UPPER_ACTIVE, BOUNDS_UPPER,
    BOUNDS_UPPER_ACTIVE, bounds_lower, bounds_lower_active, bounds_none,
    bounds_upper, bounds_upper_active, state_of, strictness,
    strictness_fields)
from clausal.logic.clpq.bounded_simplex import (
    _put_attributes, detach_bounds, introduce_at)
from clausal.logic.clpq.components import (
    ListCell, closed_list, component_all_variables)
from clausal.logic.variables import deref, is_var


#
# O(n^2), use sort later
#
def systems(variables, so_far):
    """redund.pl, systems/3: the components of *variables* not in *so_far*,
    each once, prepended as found (so the last one found comes first)."""
    for variable in variables:
        variable = deref(variable)
        if not is_var(variable):
            continue
        state = state_of(variable)
        if state is None or state.component is None:
            continue
        component = deref(state.component)
        if not_member_identical(so_far, component):
            so_far = [component] + so_far
    return so_far


def not_member_identical(items, x):
    """redund.pl, not_member_identical/2: no element of *items* is `==` x."""
    for item in items:
        if deref(item) is x:
            return False
    return True


def redundancy_systems(component_list, trail):
    """redund.pl, redundancy_systems/1."""
    for component in component_list:
        members = component_all_variables(component)
        if members is None:
            return False
        if not redundancy_variable_list(members, trail):
            return False
    return True


def redundancy_variables(variables, trail):
    """redund.pl, redundancy_variables/1.  Its second clause, which times
    the same call, is unreachable after the first clause's cut and is not
    ported."""
    return redundancy_variable_list(variables, trail)


#
# remove redundant bounds from variables
#
def redundancy_variable_list(variables, trail):
    """redund.pl, redundancy_variable_list/1: try each variable's bounds;
    where redundant/3 fails, its changes are undone."""
    node = closed_list(variables) if type(variables) is list else deref(variables)
    while type(node) is ListCell:
        variable = deref(node.head)
        node = deref(node.rest)
        state = state_of(variable) if is_var(variable) else None
        if state is None or state.bounds is None:
            continue
        mark = trail.mark()
        if not redundant(state.bounds, variable, strictness(state), trail):
            trail.undo(mark)
    return True


def redundant(bounds, variable, strict, trail):
    """redund.pl, redundant/3: drop the redundant bounds of *variable*,
    whose type is *bounds* and strictness bits *strict*.  False where the
    bound is not redundant (the caller undoes); its changes then stand
    only in the two-bound types, whose inner if-then-else undoes its own
    conditions here."""
    kind = bounds.kind
    if kind == BOUNDS_LOWER:
        if not detach_bounds(variable, trail):              # drop temporarily
            return False
        if not negate_lower(strict, bounds.lower, variable, trail):
            return False
        return redundant_bounds_lower()
    if kind == BOUNDS_UPPER:
        if not detach_bounds(variable, trail):
            return False
        if not negate_upper(strict, bounds.upper, variable, trail):
            return False
        return redundant_bounds_upper()
    if kind == BOUNDS_LOWER_UPPER:
        lower_bits, upper_bits = strictness_parts(strict)
        lower_value = bounds.lower
        upper_value = bounds.upper
        mark = trail.mark()
        _put_type_and_strictness(variable, bounds_upper(upper_value),
                                 upper_bits, trail)
        if negate_lower(strict, lower_value, variable, trail):
            redundant_bounds_lower()
            _try_redundant(bounds_upper(upper_value), variable, strict, trail)
            return True
        trail.undo(mark)
        _put_type_and_strictness(variable, bounds_lower(lower_value),
                                 lower_bits, trail)
        if negate_upper(strict, upper_value, variable, trail):
            return redundant_bounds_upper()
        trail.undo(mark)
        return True
    if kind == BOUNDS_LOWER_ACTIVE:
        if not introduce_at(variable, negate(bounds.lower), bounds_none(),
                            trail):                         # drop temporarily
            return False
        if not detach_bounds(variable, trail):
            return False
        if not negate_lower(strict, bounds.lower, variable, trail):
            return False
        return redundant_bounds_lower_active()
    if kind == BOUNDS_UPPER_ACTIVE:
        if not introduce_at(variable, negate(bounds.upper), bounds_none(),
                            trail):                         # drop temporarily
            return False
        if not detach_bounds(variable, trail):
            return False
        if not negate_upper(strict, bounds.upper, variable, trail):
            return False
        return redundant_bounds_upper_active()
    if kind == BOUNDS_LOWER_ACTIVE_UPPER:
        lower_bits, upper_bits = strictness_parts(strict)
        lower_value = bounds.lower
        upper_value = bounds.upper
        mark = trail.mark()
        if introduce_at(variable, negate(lower_value), bounds_upper(upper_value),
                        trail):
            _put_strictness(variable, upper_bits, trail)
            if negate_lower(strict, lower_value, variable, trail):
                redundant_bounds_lower()
                _try_redundant(bounds_upper(upper_value), variable, strict,
                               trail)
                return True
        trail.undo(mark)
        _put_type_and_strictness(variable, bounds_lower_active(lower_value),
                                 lower_bits, trail)
        if negate_upper(strict, upper_value, variable, trail):
            return redundant_bounds_upper()
        trail.undo(mark)
        return True
    if kind == BOUNDS_LOWER_UPPER_ACTIVE:
        lower_bits, upper_bits = strictness_parts(strict)
        lower_value = bounds.lower
        upper_value = bounds.upper
        mark = trail.mark()
        _put_type_and_strictness(variable, bounds_upper_active(upper_value),
                                 upper_bits, trail)
        if negate_lower(strict, lower_value, variable, trail):
            redundant_bounds_lower()
            _try_redundant(bounds_upper_active(upper_value), variable, strict,
                           trail)
            return True
        trail.undo(mark)
        if introduce_at(variable, negate(upper_value), bounds_lower(lower_value),
                        trail):
            _put_strictness(variable, lower_bits, trail)
            if negate_upper(strict, upper_value, variable, trail):
                return redundant_bounds_upper()
        trail.undo(mark)
        return True
    return False                                            # t_none: no clause


def _try_redundant(bounds, variable, strict, trail):
    """`( redundant(Bounds, X, Strict) -> true ; true )`."""
    mark = trail.mark()
    if not redundant(bounds, variable, strict, trail):
        trail.undo(mark)


def _put_type_and_strictness(variable, bounds, bits, trail):
    """put_atts(X, [type(Bounds), strictness(Bits)])."""
    lower_strict, upper_strict = strictness_fields(bits)
    _put_attributes(variable, trail, bounds=bounds, lower_strict=lower_strict,
                    upper_strict=upper_strict)


def _put_strictness(variable, bits, trail):
    """put_atts(X, strictness(Bits))."""
    lower_strict, upper_strict = strictness_fields(bits)
    _put_attributes(variable, trail, lower_strict=lower_strict,
                    upper_strict=upper_strict)


def strictness_parts(strict):
    """redund.pl, strictness_parts/3: (lower bit 0b10, upper bit 0b01)."""
    return strict & 0b10, strict & 0b01


#
# encapsulation via \+ (unfolded to avoid metacall)
#
def negate_lower(strict, lower_value, variable, trail):
    """redund.pl, negate_lower/3: True where the store implies the lower
    bound (X >= L, or X > L for a strict one), that is where posting
    `{L > X}` (`{L >= X}`) fails.  The post is undone either way."""
    if strict == 0b00 or strict == 0b01:
        constraint = (">", to_number(lower_value), variable)
    else:
        constraint = (">=", to_number(lower_value), variable)
    return not _consistent(constraint, trail)


def negate_upper(strict, upper_value, variable, trail):
    """redund.pl, negate_upper/3: True where the store implies the upper
    bound, that is where posting `{U < X}` (`{U =< X}` for a strict one)
    fails.  The post is undone either way."""
    if strict == 0b00 or strict == 0b10:
        constraint = ("<", to_number(upper_value), variable)
    else:
        constraint = ("=<", to_number(upper_value), variable)
    return not _consistent(constraint, trail)


def _consistent(constraint, trail):
    """`{C}` succeeds; the store is left as it was."""
    from clausal.logic.clpq.normal_form import (    # cyclic: nf.pl
        post_constraint)
    mark = trail.mark()
    try:
        return post_constraint(constraint, trail)
    finally:
        trail.undo(mark)


#
# profiling
#
def redundant_bounds_lower():
    """redund.pl, redundant_bounds_lower/0 (red_t_l/0): a profiling marker."""
    return True


def redundant_bounds_upper():
    """redund.pl, redundant_bounds_upper/0 (red_t_u/0)."""
    return True


def redundant_bounds_lower_active():
    """redund.pl, redundant_bounds_lower_active/0 (red_t_L/0)."""
    return True


def redundant_bounds_upper_active():
    """redund.pl, redundant_bounds_upper_active/0 (red_t_U/0)."""
    return True
