# Ported from clp(q,r) version 1.3.3, file project.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Answer constraint projection: project.pl.

Every predicate of project.pl is a function here, in file order, named by
NAMES.md.  project_attributes/2 "may be destructive (either acts on a copy
or in a failure loop)": its caller (residual_constraints.dump) runs it
between a trail mark and the undo to it.

Lists: a variable list is a Python list or a components.ListCell chain
(an open member list), walked up to its tail.  A pivot `T:Nt` is the pair
(T, Nt); the pivot list is a Python list, newest first.
"""
from clausal.logic.clpq import limits
from clausal.logic.clpq.attributes import BOUNDS_NONE, bounds_none, state_of
from clausal.logic.clpq.bounded_simplex import _put_attributes, pivot
from clausal.logic.clpq.components import (
    ListCell, closed_list, component_all_variables)
from clausal.logic.clpq.delayed_goals import project_nonlinear
from clausal.logic.clpq.fourier_motzkin import fourier_motzkin_eliminate
from clausal.logic.clpq.linear_forms import independent, renormalize
from clausal.logic.clpq.redundancy import redundancy_variables, systems
from clausal.logic.clpq.variable_ordering import (
    arrangement, compare_variable_order)
from clausal.logic.variables import deref, is_var, unify


#
# interface predicate
#
# May be destructive (either acts on a copy or in a failure loop)
#
def project_attributes(target_variables, constrained_variables, trail):
    """project.pl, project_attributes/2: project the store of
    *constrained_variables* onto *target_variables*.  False where it
    fails.

    The rows it writes are counted (limits.start_projection): past the
    clpq_projection cap it raises `resource_error(clpq_projection)`
    (DEVIATIONS.md D24).  Its caller undoes the store either way."""
    previous = limits.start_projection()
    try:
        return _project_attributes(target_variables, constrained_variables,
                                   trail)
    finally:
        limits.stop_projection(previous)


def _project_attributes(target_variables, constrained_variables, trail):
    targets = sort_variables(target_variables)             # duplicates ?
    constrained = sort_variables(constrained_variables)    # duplicates ?
    mark_target(targets, trail)
    reachable = project_nonlinear(targets, constrained, trail)
    if not targets:
        drop_linear_attributes(constrained, trail)
        return True
    if not redundancy_variables(constrained, trail):       # redundancy.pl
        return False
    pivots = make_target_independent(targets, trail)
    if pivots is None:
        return False
    mark_target(reachable, trail)       # after make_indep to express priority
    drop_dependent(constrained, trail)
    if not fourier_motzkin_eliminate(constrained, targets, pivots, trail):
        return False
    return impose_ordering(constrained, trail)


def sort_variables(variables):
    """sort/2 on a list of variables: unbound ones in the standard order,
    each once.  The standard order of two variables is creation order
    (DEVIATIONS.md D4).  A bound element (no caller passes one) is kept
    after them, dereferenced, in the given order (test_sort_variables)."""
    unbound = []
    bound = []
    seen = set()
    for variable in variables:
        variable = deref(variable)
        if is_var(variable):
            if variable._id not in seen:
                seen.add(variable._id)
                unbound.append(variable)
        else:
            bound.append(variable)
    unbound.sort(key=_creation)
    return unbound + bound


def _creation(variable):
    return variable._id


def mark_target(variables, trail):
    """project.pl, mark_target/1."""
    for variable in variables:
        _put_attributes(deref(variable), trail, target=True)


def mark_keep(variables, trail):
    """project.pl, mark_keep/1."""
    for variable in variables:
        _put_attributes(deref(variable), trail, keep=True)


#
# Collect the pivots in reverse order
# We have to protect the target variables pivot partners
# from redundancy eliminations triggered by fm_elim,
# in order to allow for reverse pivoting.
#
def make_target_independent(targets, trail):
    """project.pl, make_target_independent/2,3: pivot each dependent target
    with the first non-target of its row, marking that one `keep`.
    Returns the pivots (T, Nt), newest first, or None where a pivot
    fails."""
    pivots = []
    for target in targets:
        target = deref(target)
        state = state_of(target) if is_var(target) else None
        if state is None or state.linear_form is None or state.bounds is None:
            continue
        nontarget_variable = nontarget(state.linear_form.terms)
        if nontarget_variable is None:
            continue
        pivots = [(target, nontarget_variable)] + pivots
        _put_attributes(nontarget_variable, trail, keep=True)
        if not pivot(target, nontarget_variable, state.bounds, trail):
            return None
    return pivots


def nontarget(terms):
    """project.pl, nontarget/2: the first variable of *terms* with neither
    `target` nor `keep_independent`, or None."""
    for variable, _ in terms:
        state = state_of(variable)
        if state is None or (not state.target and not state.keep_independent):
            return deref(variable)
    return None


def drop_dependent(variables, trail):
    """project.pl, drop_dependent/1 (drop_dep/1)."""
    node = closed_list(variables) if type(variables) is list else deref(variables)
    while type(node) is ListCell:
        drop_dependent_one(node.head, trail)
        node = deref(node.rest)


def drop_dependent_one(variable, trail):
    """project.pl, drop_dependent_one/1 (drop_dep_one/1): a dependent
    variable of type t_none that is not a target, not kept and not nonzero
    loses its linear attributes."""
    variable = deref(variable)
    state = state_of(variable) if is_var(variable) else None
    if state is None or state.linear_form is None or state.bounds is None:
        return
    if state.bounds.kind != BOUNDS_NONE or state.target or state.keep \
            or state.nonzero:
        return
    if independent(state.linear_form, variable):
        return
    _drop_linear(variable, trail)


def _drop_linear(variable, trail):
    """put_atts(V, [-linear_form(_), -type(_), -component(_),
    -variable_order(_), -strictness(_)])."""
    _put_attributes(variable, trail, linear_form=None, bounds=None,
                    component=None, variable_order=None, lower_strict=False,
                    upper_strict=False)


def drop_linear_attributes(variables, trail):
    """project.pl, drop_linear_attributes/1 (drop_lin_atts/1)."""
    for variable in variables:
        variable = deref(variable)
        if is_var(variable) and state_of(variable) is not None:
            _drop_linear(variable, trail)


def impose_ordering(constrained_variables, trail):
    """project.pl, impose_ordering/1."""
    return impose_ordering_systems(systems(constrained_variables, []), trail)


def impose_ordering_systems(component_list, trail):
    """project.pl, impose_ordering_systems/1 (impose_ordering_sys/1).
    arrangement/2 raises where the ordering is unsatisfiable (D6)."""
    for component in component_list:
        if not arrange(arrangement(component), component, trail):  # ordering.pl
            return False
    return True


def arrange(arranged, component, trail):
    """project.pl, arrange/2: number the variables of *arranged* 1, 2, ...,
    then the other unnumbered members after them; re-sort every row and
    pivot each t_none row whose first variable now comes before it."""
    if not arranged:
        return True
    members = component_all_variables(component)
    if members is None:
        return False
    count = variable_order(arranged, 1, trail)
    if count is None:
        return False
    if variable_order(members, count, trail) is None:
        return False
    if not renormalize_all(members, trail):
        return False
    return arrange_pivot(members, trail)


def variable_order(items, number, trail):
    """project.pl, variable_order/3 (order/3): bind each unbound order value
    in turn to *number*, *number* + 1, ...; returns the next number, or
    None where a binding fails."""
    node = closed_list(items) if type(items) is list else deref(items)
    while type(node) is ListCell:
        variable = deref(node.head)
        node = deref(node.rest)
        state = state_of(variable) if is_var(variable) else None
        if state is None or state.variable_order is None:
            continue
        order = deref(state.variable_order)
        if is_var(order):
            if not unify(order, number, trail):
                return None
            number += 1
    return number


def renormalize_all(items, trail):
    """project.pl, renormalize_all/1 (renorm_all/1) on an open member list.
    1.3.3 has no clause for `[]`, so a closed list fails (False)."""
    node = deref(items)
    while type(node) is ListCell:
        variable = deref(node.head)
        node = deref(node.rest)
        state = state_of(variable) if is_var(variable) else None
        if state is None or state.linear_form is None:
            continue
        form = renormalize(state.linear_form)
        if form is None:
            return False
        _put_attributes(variable, trail, linear_form=form)
    return node is not None


def arrange_pivot(items, trail):
    """project.pl, arrange_pivot/1 on an open member list: pivot a t_none
    row X with its first variable Y where Y now comes before X.  1.3.3 has
    no clause for `[]`, so a closed list fails (False)."""
    node = deref(items)
    while type(node) is ListCell:
        variable = deref(node.head)
        node = deref(node.rest)
        state = state_of(variable) if is_var(variable) else None
        if state is None or state.linear_form is None or state.bounds is None \
                or state.bounds.kind != BOUNDS_NONE:
            continue
        terms = state.linear_form.terms
        if not terms:
            continue
        first = terms[0][0]
        if compare_variable_order(first, variable) == -1:
            if not pivot(variable, first, bounds_none(), trail):
                return False
    return node is not None
