# Ported from clp(q,r) version 1.3.3, file bb.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Branch and bound for integer optimisation: bb.pl.

Every predicate of bb.pl is a function here, in file order, named by
NAMES.md.  `branch_and_bound_intern/4` is `branch_and_bound_intern_one`
(NAMES.md, "Names the port adds").

1.3.3 searches by backtracking: `branch_and_bound_infimum_internal/5`'s
first clause runs `branch_and_bound_loop/3`, whose `branch_and_bound_branch/3`
leaves a choice point at each node, records each better leaf with
`bb_put(incumbent, ...)` and ends in `fail`; the second clause takes the
record.  Here `branch_and_bound_loop` is one loop over an explicit stack of
the second alternatives, each with its trail mark, and the incumbent is a
local it returns (test_a_search_deeper_than_1000_branches_needs_no_recursion).
A predicate that fails returns False or None, as its docstring says.

Goals a post of the search wakes run after that post, to their first
answer, and their failure fails the post (ruling R24): in 1.3.3 they run
inside `{}/1`.  The hooks queue them on the trail whenever a driver or
a unification owns it (`trail.defer`), and bb_inf can run there: under a
driver, or as a goal a bare unify woke, in its drain.  So clause 1 of
branch_and_bound_infimum_internal takes the queue it was entered with:
the queue then holds only the search's goals, and its undo puts the outer
queue back (test_a_goal_woken_by_a_branch_runs_in_it,
test_a_goal_woken_by_narrowing_runs_in_it,
test_a_woken_bb_inf_runs_the_goals_its_search_wakes,
test_work_queued_before_bb_inf_stays_queued).
"""
from clausal.logic.clpq import limits
from clausal.logic.clpq.attributes import (
    culprit_argument, refuse_inside_attribute_hooks)
from clausal.logic.clpq.arithmetic import (
    ONE, add, arithmetic_normalize, ceiling_rational, compare, floor_rational,
    is_number, minimum, round_rational, subtract, to_number)
from clausal.logic.clpq.bounded_simplex import (
    _post_equal, dereference, dereference_variable, determine_active_decrease,
    inf, iterate_decrease, sup, variable_with_definition_assign)
from clausal.logic.clpq.normal_form import (
    entailed, normal_form, normal_form_constant, post_constraint, repair,
    wait_linear)
from clausal.logic.exceptions import LogicException, instantiation_error
from clausal.logic.pending import run_first
from clausal.logic.variables import Var, deref, is_var, unify

#: bb_inf/3's Eps, the float 0.001, which normal_form/2 reads as 1/1000.
DEFAULT_EPSILON = 0.001


def bb_inf(integer_variables, term, infimum, trail, vertex=None, epsilon=None):
    """bb.pl, bb_inf/3 and bb_inf/5: the infimum of *term* when every term
    of *integer_variables* is integral, posted as `{Infimum =:= value}`,
    and the rounded values of *integer_variables* there unified with
    *vertex*.  True or False.  bb_inf/3 is bb_inf/5 with a fresh Vertex
    and Eps 0.001.  Like inf, it waits until *term* is linear."""
    if vertex is None and epsilon is None:
        refuse_inside_attribute_hooks(
            trail, ("bb_inf", integer_variables, term, infimum), "bb_inf", 3)
    else:
        refuse_inside_attribute_hooks(
            trail, ("bb_inf", integer_variables, term, infimum,
                    culprit_argument(vertex), culprit_argument(epsilon)),
            "bb_inf", 5)
    if vertex is None:
        vertex = Var()
    if epsilon is None:
        epsilon = DEFAULT_EPSILON
    epsilon_form = normal_form(epsilon)
    if epsilon_form is None:
        return False
    epsilon_constant = normal_form_constant(epsilon_form)
    if epsilon_constant is None:
        return False
    return wait_linear(term, branch_and_bound_infimum_internal,
                       (integer_variables, epsilon_constant, infimum, vertex),
                       trail)


# ---------------------------------------------------------------------

def branch_and_bound_infimum_internal(normal_form, argument, trail):
    """bb.pl, branch_and_bound_infimum_internal/5 (bb_inf_internal/5), as
    the goal wait_linear calls: *normal_form* is Lin, *argument* is
    (Is, Eps, Inf, Vertex).  1.3.3's argument order is (Is, Lin, Eps, Inf,
    Vertex); translate_goal shows it that way
    (test_the_delayed_goal_shows_nf_second).

    Clause 1 is undone by the mark and undo, as its `fail` undoes it; the
    incumbent comes back as a local.  Clause 2 unifies Vertex, then posts
    `{Inf =:= InfVal}`.  One answer or none
    (test_the_delayed_goal_is_deterministic)."""
    integer_variables, epsilon, infimum, vertex = argument
    mark = trail.mark()
    incumbent = None                    # ( bb_delete(incumbent, _) -> true ; true )
    try:
        trail.take_pending()            # the outer queue, back at the undo
        integer_forms = branch_and_bound_intern(integer_variables, epsilon,
                                                trail)          # clause 1
        if integer_forms is not None:
            repaired = repair(normal_form)                      # bb_narrow ...
            if repaired is not None:
                form = dereference(repaired, trail)
                if form is not None:
                    dependent = Var()
                    if variable_with_definition_assign(dependent, form, trail) \
                            and determine_active_decrease(form, trail):
                        incumbent = branch_and_bound_loop(
                            dependent, integer_forms, epsilon, trail)
    finally:
        trail.undo(mark)                                        # fail
    if incumbent is None:                                       # bb_delete fails
        return False
    value, round_vertex = incumbent                             # clause 2
    if not unify(vertex, [to_number(element) for element in round_vertex],
                 trail):
        return False
    return _post_equal(infimum, value, trail)                   # { Inf =:= InfVal }


def branch_and_bound_loop(objective, integer_forms, epsilon, trail):
    """bb.pl, branch_and_bound_loop/3 (bb_loop/3), with the backtracking
    into it that clause 1 of branch_and_bound_infimum_internal/5 drives:
    the incumbent at the end of the search, (Inf, RoundVertex), or None.

    Each pass is one call of branch_and_bound_loop/3.  A pass that branches
    posts the first clause of branch_and_bound_branch/3 and pushes the
    second, with a trail mark; a pass that fails (no better bound, an
    unbounded objective, a branch that cannot be posted) or that records a
    leaf backtracks into the newest pushed alternative.  The incumbent is a
    local, not 1.3.3's global bb_put/bb_get
    (test_a_search_deeper_than_1000_branches_needs_no_recursion,
    test_the_incumbent_prunes_worse_branches).

    Each pass is one node.  Past the clpq_nodes cap it raises
    `resource_error(clpq_nodes)` (DEVIATIONS.md D24): 1.3.3 searches a
    store with no integer point for ever."""
    incumbent = None
    alternatives = []
    nodes = 0
    while True:
        nodes += 1
        limits.check("clpq_nodes", nodes,
                     "the branch and bound nodes of bb_inf")
        infimum = branch_and_bound_reoptimize(objective, trail)
        if infimum is not None \
                and branch_and_bound_better_bound(infimum, incumbent):
            values = vertex_value(integer_forms, trail)
            violation = branch_and_bound_first_non_integer(
                integer_forms, values, epsilon)
            if violation is not None:
                variable, floor, ceiling = violation
                alternatives.append((trail.mark(), variable, floor, ceiling))
                if branch_and_bound_branch(variable, floor, ceiling, 0, trail):
                    continue
            else:
                incumbent = (infimum, round_values(values))     # bb_put
        while alternatives:                                     # backtrack
            mark, variable, floor, ceiling = alternatives.pop()
            trail.undo(mark)
            if branch_and_bound_branch(variable, floor, ceiling, 1, trail):
                break
        else:
            return incumbent


#
# added ineqs may have led to binding
#
def branch_and_bound_reoptimize(objective, trail):
    """bb.pl, branch_and_bound_reoptimize/2 (bb_reoptimize/2): the
    infimum of the objective, pivoting to it while it is a variable, or
    None where that fails (unbounded)."""
    objective = deref(objective)
    if is_var(objective):
        return iterate_decrease(objective, trail)
    return arithmetic_normalize(objective)


def branch_and_bound_better_bound(infimum, incumbent):
    """bb.pl, branch_and_bound_better_bound/1 (bb_better_bound/1): with an
    incumbent, *infimum* must be below its value; *incumbent* is the local
    that stands for bb_get(incumbent, Inc-_)."""
    if incumbent is not None:
        return compare(infimum, incumbent[0]) < 0
    return True


def branch_and_bound_branch(variable, upper, lower, alternative, trail):
    """bb.pl, branch_and_bound_branch/3 (bb_branch/3): its clause
    *alternative*, 0 for `{V =< U}` and 1 for `{V >= L}`."""
    if alternative == 0:
        return branch_and_bound_post(("=<", variable, to_number(upper)), trail)
    return branch_and_bound_post((">=", variable, to_number(lower)), trail)


def branch_and_bound_post(constraint, trail):
    """bb.pl's `{}/1` inside the search: post_constraint, then the goals it
    queued, to their first answer (ruling R24)."""
    return post_constraint(constraint, trail) and run_first(trail)


def vertex_value(vector, trail):
    """bb.pl, vertex_value/2: right_hand_side_value of each element, as a
    list.  bv.pl's inf/4 calls it too (test_vertex_value_reads_the_right_
    hand_side)."""
    values = []
    for element in vector:
        values.append(right_hand_side_value(element, trail))
    return values


def right_hand_side_value(term, trail):
    """bb.pl, right_hand_side_value/2 (rhs_value/2): R + I of a variable's
    linear form; a non-variable is its own value (a number as a rational)."""
    term = deref(term)
    if not is_var(term):
        if is_number(term):
            return arithmetic_normalize(term)
        return term
    form = dereference_variable(term, trail)
    return add(form.rest, form.constant)


#
# Need only one as we branch on the first anyway ...
#
def branch_and_bound_first_non_integer(integer_forms, values, epsilon):
    """bb.pl, branch_and_bound_first_non_integer/6 (bb_first_nonint/6): the
    first element whose value is further than *epsilon* from both its floor
    and its ceiling, as (element, Floor, Ceiling); None where there is none.
    The recursion is a loop."""
    for index in range(len(integer_forms)):
        value = values[index]
        floor = floor_rational(value)
        ceiling = ceiling_rational(value)
        if compare(minimum(subtract(value, floor), subtract(ceiling, value)),
                   epsilon) > 0:
            return integer_forms[index], floor, ceiling
    return None


def round_values(values):
    """bb.pl, round_values/2: round_rational of each value."""
    result = []
    for value in values:
        result.append(round_rational(value))
    return result


def branch_and_bound_intern(integer_variables, epsilon, trail):
    """bb.pl, branch_and_bound_intern/3 (bb_intern/3): the list IsNf, each
    element a variable or a number, or None where it fails.  Raises
    instantiation_error for a term that is not a variable, a number or 0
    (branch_and_bound_intern/4's last clause)."""
    result = []
    for term in integer_variables:
        form = normal_form(term)
        if form is None:
            return None
        element = branch_and_bound_intern_one(form, term, epsilon, trail)
        if element is None:
            return None
        result.append(element)
    return result


def branch_and_bound_intern_one(form, term, epsilon, trail):
    """bb.pl, branch_and_bound_intern/4 (bb_intern/4): the element of IsNf
    for *term*, whose normal form is *form*; None where it fails."""
    if not form:                                            # clause 1
        return 0
    if len(form) == 1 and not form[0].powers:               # clause 2
        constant = form[0].coefficient
        if compare(minimum(subtract(constant, floor_rational(constant)),
                           subtract(ceiling_rational(constant), constant)),
                   epsilon) <= 0:
            return to_number(constant)
        return None
    if len(form) == 1 and len(form[0].powers) == 1 \
            and form[0].powers[0][1] == 1 \
            and compare(form[0].coefficient, ONE) == 0:     # clause 3
        variable = form[0].powers[0][0]
        if not branch_and_bound_narrow_lower(variable, trail):
            return None
        if not branch_and_bound_narrow_upper(variable, trail):
            return None
        return variable
    raise LogicException(instantiation_error(               # clause 4
        ("bb_inf", term, Var(), Var())))


def branch_and_bound_narrow_lower(variable, trail):
    """bb.pl, branch_and_bound_narrow_lower/1 (bb_narrow_lower/1)."""
    mark = trail.mark()
    infimum = Var()
    if not inf(variable, infimum, trail):
        trail.undo(mark)
        return True
    bound = to_number(ceiling_rational(arithmetic_normalize(deref(infimum))))
    if entailed((">", variable, bound), trail):
        return branch_and_bound_post((">=", variable, ("+", bound, 1)), trail)
    return branch_and_bound_post((">=", variable, bound), trail)


def branch_and_bound_narrow_upper(variable, trail):
    """bb.pl, branch_and_bound_narrow_upper/1 (bb_narrow_upper/1)."""
    mark = trail.mark()
    supremum = Var()
    if not sup(variable, supremum, trail):
        trail.undo(mark)
        return True
    bound = to_number(floor_rational(arithmetic_normalize(deref(supremum))))
    if entailed(("<", variable, bound), trail):
        return branch_and_bound_post(("=<", variable, ("-", bound, 1)), trail)
    return branch_and_bound_post(("=<", variable, bound), trail)
