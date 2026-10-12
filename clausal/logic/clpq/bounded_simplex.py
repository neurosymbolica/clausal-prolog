# Ported from clp(q,r) version 1.3.3, file bv.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""The simplex with bounded variables: bv.pl.

Every predicate of bv.pl is a function here, in file order, named by
NAMES.md.  Where bv.pl defines one name at two arities, the second gets its
own name (NAMES.md, "Names the port adds").

Representations:

- A linear form is linear_forms.LinearForm; `split_linear_form(Lin, H, R, I)`
  is reading `terms`, `rest` and `constant`.
- The `type/1` attribute is SolverState.bounds, an attributes.Bounds record;
  `strictness/1` is the two fields lower_strict and upper_strict.
- A step status (`optimum`, `applied`, `unlimited(Indep, DepT)`) is a tuple
  (kind, independent, bounds) with kind one of the STATUS_* ints.
- A violated bound (`below_lower_bound(L)`, `above_upper_bound(U)`) is a
  pair (kind, bound).
- The tightest row `Dep-W-Limit` is a tuple (dependent, bounds, limit).
- A Prolog list of variables (a basis, a member list) is a components.ListCell
  chain; a binding list `[X-Value, ...]` is a Python list of pairs, which
  bv.pl threads as a difference list.
- A predicate that fails returns False or None, as its docstring says.

A normal form (nf.pl, Task 10) is read as a list of monomials, each with
`coefficient` (a rational) and `powers` (a list of (base, exponent) pairs).

Imports at the call site.  bv.pl and nf.pl, ineq.pl, bb.pl call each other.
bounded_simplex imports normal_form, inequalities and branch_and_bound at
the call site, inside the function that needs them, because each of those
modules imports this one.  Each such import is marked "cyclic".
"""
from clausal.logic.clpq.attributes import (
    culprit_argument, refuse_inside_attribute_hooks)
from clausal.logic.clpq.arithmetic import (
    ONE, ZERO, add, compare, divide, is_zero, multiply, negate,
    rational_to_float, sign, subtract, to_number)
from clausal.logic.clpq.attributes import (
    BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE, BOUNDS_LOWER_ACTIVE_UPPER,
    BOUNDS_LOWER_UPPER, BOUNDS_LOWER_UPPER_ACTIVE, BOUNDS_NONE, BOUNDS_UPPER,
    BOUNDS_UPPER_ACTIVE, SolverState, bounds_lower, bounds_lower_active,
    bounds_lower_active_upper, bounds_lower_upper, bounds_lower_upper_active,
    bounds_none, bounds_upper, bounds_upper_active, put_state, state_of,
    strictness_fields, with_changes)
from clausal.logic.clpq.components import (
    COMPONENT_KEY, ListCell, component_all_variables, component_basis_add,
    component_basis_drop, component_basis_pivot, component_new,
    list_elements, open_list)
from clausal.logic.clpq.linear_forms import (
    MINUS_ONE, LinearForm, add_linear_forms, add_linear_forms_scaled,
    delete_factor, independent, isolate, multiply_homogeneous_part,
    multiply_linear_factor, normal_form_right_hand_side,
    normal_form_substitute, normal_form_to_sum, normalize_scalar)
from clausal.logic.variables import Var, deref, get_attr, is_var, unify

STATUS_OPTIMUM = 0
STATUS_APPLIED = 1
STATUS_UNLIMITED = 2

OPTIMUM = (STATUS_OPTIMUM, None, None)
APPLIED = (STATUS_APPLIED, None, None)

BELOW_LOWER_BOUND = 0
ABOVE_UPPER_BOUND = 1

PIVOT_EXCHANGE = 0
PIVOT_OR_BOUND_SWAP = 1

# The tail call a reconsider step hands back to reconsider_basis_list_status.
_FAIL = 0
_WALK = 1           # reconsider_basis_list/3 on a continuation
_STATUS = 2         # reconsider_basis_list_status/6 on a new status

# What solve_step hands back to solve_homogeneous.
_SOLVE_FAILED = 0
_SOLVE_FINISHED = 1
_SOLVE_RECONSIDER = 2


def _put_attributes(variable, trail, **fields):
    """put_atts/2: set the named attributes, keeping the others."""
    state = state_of(variable)
    if state is None:
        state = SolverState(**fields)
    else:
        state = with_changes(state, **fields)
    put_state(variable, state, trail)


def _linear_variable(variable, bounds, strict, form, trail):
    """put_atts(Var, [variable_order(_), linear_form(Lin), type(Type),
    strictness(Strict)])."""
    lower_strict, upper_strict = strictness_fields(strict)
    _put_attributes(variable, trail, variable_order=Var(), linear_form=form,
                    bounds=bounds, lower_strict=lower_strict,
                    upper_strict=upper_strict)


def _has_type_none(state):
    """get_atts(X, type(bounds_none))."""
    return (state is not None and state.bounds is not None
            and state.bounds.kind == BOUNDS_NONE)


# ----------------------------------- deref ------------------------------------

def dereference(normal_form, trail):
    """bv.pl, dereference/2 (1.3.3 deref/2): a linear normal form as a linear
    form over the solver's independent variables.  None where it fails."""
    from clausal.logic.clpq.normal_form import split    # cyclic: nf.pl
    homogeneous, constant = split(normal_form)
    nonvariable = normalize_scalar(constant)
    result = dereference_balanced(len(homogeneous), homogeneous, 0, trail)
    if result is None:
        return None
    return add_linear_forms(nonvariable, result[0])


def dereference_balanced(count, monomials, start, trail):
    """bv.pl, dereference_balanced/4 (log_deref/4): the sum of the *count*
    monomials from monomials[start], each `K*X^1`, dereferenced.  Returns
    (form, start + count), or None.  The recursion halves *count*, so its
    depth is log2(count) (test_long_rows_and_long_bases_need_no_recursion)."""
    if count == 0:
        return LinearForm(ZERO, ZERO, []), start
    if count == 1:
        monomial = monomials[start]
        form = dereference_variable(_linear_base(monomial), trail)
        return multiply_linear_factor(form, monomial.coefficient), start + 1
    if count == 2:
        monomial_x = monomials[start]
        monomial_y = monomials[start + 1]
        form_x = dereference_variable(_linear_base(monomial_x), trail)
        form_y = dereference_variable(_linear_base(monomial_y), trail)
        form = add_linear_forms_scaled(form_x, monomial_x.coefficient,
                                       form_y, monomial_y.coefficient)
        if form is None:
            return None
        return form, start + 2
    first = count >> 1
    second = count - first
    left = dereference_balanced(first, monomials, start, trail)
    if left is None:
        return None
    right = dereference_balanced(second, monomials, left[1], trail)
    if right is None:
        return None
    form = add_linear_forms(left[0], right[0])
    if form is None:
        return None
    return form, right[1]


def _linear_base(monomial):
    """X of a monomial `K*X^1`.  For any other monomial 1.3.3's clause heads
    fail and the last clause splits 1 into 0 and 1 without end; the port
    raises instead (DEVIATIONS.md D9,
    test_dereference_of_a_non_linear_monomial_raises)."""
    powers = monomial.powers
    if len(powers) != 1 or powers[0][1] != 1:
        raise ValueError("dereference_balanced: monomial is not K*X^1")
    return powers[0][0]


def dereference_variable(variable, trail):
    """bv.pl, dereference_variable/2 (deref_var/2): the linear form of
    *variable*, making it a linear variable of type t_none if it has none.
    It gets no component here
    (test_dereference_variable_makes_a_linear_variable_without_a_component)."""
    variable = deref(variable)
    state = state_of(variable)
    if state is not None and state.linear_form is not None:
        return state.linear_form
    form = LinearForm(ZERO, ZERO, [(variable, ONE)])
    _linear_variable(variable, bounds_none(), 0b00, form, trail)
    return form


def variable_with_definition_assign(variable, form, trail):
    """bv.pl, variable_with_definition_assign/2 (var_with_def_assign/2)."""
    homogeneous = form.terms
    constant = form.constant
    if not homogeneous:                                     # X = k
        return unify(variable, to_number(constant), trail)
    if len(homogeneous) == 1 and compare(homogeneous[0][1], ONE) == 0 \
            and is_zero(constant):                          # X = Y
        return unify(variable, homogeneous[0][0], trail)
    return variable_with_definition_intern(bounds_none(), variable, form,
                                           0b00, trail)


def variable_with_definition_intern(bounds, variable, form, strict, trail):
    """bv.pl, variable_with_definition_intern/4 (var_with_def_intern/4):
    *variable* becomes the dependent variable defined by *form*, joining the
    component of every variable in it."""
    variable = deref(variable)
    _linear_variable(variable, bounds, strict, form, trail)
    component = get_or_add_component(variable, None, trail)
    if component is None:
        return False
    return same_component(form.terms, component, trail)


def variable_intern_with_bounds(bounds, variable, strict, trail):
    """bv.pl, variable_intern/3 (var_intern/3): a new independent variable
    with bound type *bounds* and strictness bits *strict*."""
    variable = deref(variable)
    form = LinearForm(ZERO, ZERO, [(variable, ONE)])
    _linear_variable(variable, bounds, strict, form, trail)
    return get_or_add_component(variable, None, trail) is not None


def variable_intern(variable, trail):
    """bv.pl, variable_intern/2 (var_intern/2), for ordering/1: the component
    of *variable*, making it a linear variable of type t_none first if it is
    not one.  None where it fails."""
    variable = deref(variable)
    state = state_of(variable)
    if state is not None and state.linear_form is not None \
            and state.bounds is not None:                   # clause 1
        return get_or_add_component(variable, None, trail)
    form = LinearForm(ZERO, ZERO, [(variable, ONE)])        # clause 2
    _linear_variable(variable, bounds_none(), 0b00, form, trail)
    return get_or_add_component(variable, None, trail)


# ------------------------------------------------------------------------------

def export_bindings(bindings, trail):
    """bv.pl, export_binding/1: bind each X to its value; bindings are
    (X, Value) pairs, Value a rational.  Each binding is checked by itf3.pl's
    verify_attributes/3 as it is made, through attribute_hooks.bind_all's
    work list, so a cascade of implied bindings does not nest
    (test_implied_bindings_are_queued_not_nested)."""
    from clausal.logic.clpq.attribute_hooks import bind_all   # cyclic: itf3.pl
    return bind_all(bindings, trail)


def export_binding(first, second, trail):
    """bv.pl, export_binding/2: `first = second`.  In clause 1 *second* is
    whatever the caller passes: a variable, or a rational (nf.pl passes
    one), which becomes an engine number
    (test_export_binding, test_export_binding_of_two_variables_unifies_them)."""
    if is_var(first):                                       # clause 1: Y = X
        if type(second) is tuple:               # a rational
            second = to_number(second)
        return unify(first, second, trail)
    if is_zero(first):                                      # clause 2
        return unify(second, to_number(ZERO), trail)
    return unify(to_number(first), second, trail)


def solve_equal(normal_form, trail):
    """bv.pl, 'solve_='/1."""
    form = dereference(normal_form, trail)
    if form is None:
        return False
    return solve(form, trail)


def solve_not_equal(normal_form, trail):
    """bv.pl, 'solve_=\\='/1."""
    form = dereference(normal_form, trail)
    if form is None:
        return False
    if not form.terms:
        return not is_zero(form.constant)
    nonzero = Var()
    if not variable_with_definition_intern(bounds_none(), nonzero, form,
                                           0b00, trail):
        return False
    _put_attributes(nonzero, trail, nonzero=True)
    return True


def solve_less(normal_form, trail):
    """bv.pl, 'solve_<'/1."""
    from clausal.logic.clpq.normal_form import split    # cyclic: nf.pl
    from clausal.logic.clpq.inequalities import inequality  # cyclic: ineq.pl
    homogeneous, constant = split(normal_form)
    return inequality(homogeneous, constant, normal_form, True, trail)


def solve_less_or_equal(normal_form, trail):
    """bv.pl, 'solve_=<'/1."""
    from clausal.logic.clpq.normal_form import split    # cyclic: nf.pl
    from clausal.logic.clpq.inequalities import inequality  # cyclic: ineq.pl
    homogeneous, constant = split(normal_form)
    return inequality(homogeneous, constant, normal_form, False, trail)


def maximize(term, trail):
    """bv.pl, maximize/1."""
    refuse_inside_attribute_hooks(trail, ("maximize", term), "maximize", 1)
    from clausal.terms import Negate
    return minimize(Negate(operand=term), trail)


def minimize(term, trail):
    """bv.pl, minimize/1: wait until *term* is linear, then minimize_linear."""
    refuse_inside_attribute_hooks(trail, ("minimize", term), "minimize", 1)
    from clausal.logic.clpq.normal_form import wait_linear  # cyclic: nf.pl
    return wait_linear(term, minimize_linear, None, trail)


def minimize_linear(normal_form, argument, trail):
    """bv.pl, minimize_linear/1 (minimize_lin/1), as the goal wait_linear
    calls: *argument* is unused.  Pivots to the optimum and stays there."""
    form = dereference(normal_form, trail)
    if form is None:
        return False
    dependent = Var()
    if not variable_with_definition_intern(bounds_none(), dependent, form,
                                           0b00, trail):
        return False
    if not determine_active_decrease(form, trail):
        return False
    infimum = iterate_decrease(dependent, trail)
    if infimum is None:
        return False
    return _post_equal(dependent, infimum, trail)           # { Dep =:= Inf }


def _post_equal(left, right, trail):
    """`{Left =:= Right}` through nf.pl's {}/1."""
    from clausal.logic.clpq.normal_form import post_constraint  # cyclic: nf.pl
    from clausal.pythonic_ast.nodes import ArithEq
    if type(right) is tuple:                    # a rational
        right = to_number(right)
    return post_constraint(ArithEq(left=left, right=right), trail)


def sup(expression, supremum, trail, vector=None, vertex=None):
    """bv.pl, sup/2 and sup/4: inf(-Expression, -Sup, Vector, Vertex)."""
    if vector is None and vertex is None:
        refuse_inside_attribute_hooks(
            trail, ("sup", expression, supremum), "sup", 2)
    else:
        refuse_inside_attribute_hooks(
            trail, ("sup", expression, supremum, culprit_argument(vector),
                    culprit_argument(vertex)), "sup", 4)
    from clausal.terms import Negate
    return inf(Negate(operand=expression), Negate(operand=supremum), trail,
               vector, vertex)


def inf(expression, infimum, trail, vector=None, vertex=None):
    """bv.pl, inf/2 and inf/4: wait until *expression* is linear, then
    infimum_linear.  inf/2 is inf(Expression, Inf, [], []): Vector and
    Vertex are lists, as a delayed goal shows them
    (test_translate_goal_of_wait_linear_retry_reaches_res_and_the_goal)."""
    if vector is None and vertex is None:
        refuse_inside_attribute_hooks(
            trail, ("inf", expression, infimum), "inf", 2)
    else:
        refuse_inside_attribute_hooks(
            trail, ("inf", expression, infimum, culprit_argument(vector),
                    culprit_argument(vertex)), "inf", 4)
    from clausal.logic.clpq.normal_form import wait_linear  # cyclic: nf.pl
    if vector is None:
        vector = []
    if vertex is None:
        vertex = []
    return wait_linear(expression, infimum_linear,
                       (infimum, vector, vertex), trail)


def infimum_linear(normal_form, argument, trail):
    """bv.pl, infimum_linear/4 (inf_lin/4), as the goal wait_linear calls:
    *argument* is (Infimum, Vector, Vertex).

    1.3.3 pivots to the optimum, records it with bb_put and fails back to
    the start vertex; the second clause takes the record and assigns it.
    Here the mark and undo do the failing back, and the record is a local
    (test_infimum_linear_leaves_the_store_as_it_was).  The assignment comes
    after the undo, as 1.3.3's comes after bb_delete."""
    infimum, vector, vertex = argument
    mark = trail.mark()
    found = None
    form = dereference(normal_form, trail)                  # clause 1
    if form is not None:
        dependent = Var()
        if variable_with_definition_intern(bounds_none(), dependent, form,
                                           0b00, trail) \
                and determine_active_decrease(form, trail):
            optimum = iterate_decrease(dependent, trail)
            if optimum is not None:
                values = []
                if vector:
                    from clausal.logic.clpq.branch_and_bound import (  # cyclic: bb.pl
                        vertex_value)
                    values = vertex_value(vector, trail)
                if values is not None:
                    found = [optimum] + list(values)
    trail.undo(mark)                                        # fail
    if found is None:                                       # bb_delete fails
        return False
    # clause 2, assign([Infimum|Vertex], L): Vertex is a list term, unbound,
    # partial or proper.  Against the proper list L, assign/2's clause
    # choice binds it to a list as long as L's tail, so it is unified with
    # that many fresh variables, which assign then posts
    # (test_inf_4_and_sup_4_bind_the_vertex_as_the_oracle).
    elements = [Var() for _ in range(len(found) - 1)]
    if not unify(vertex, elements, trail):
        return False
    return assign([infimum] + elements, found, trail)


def assign(variables, values, trail):
    """bv.pl, assign/2: {X =:= Y} for each pair."""
    if len(variables) != len(values):
        return False
    for i in range(len(variables)):
        if not _post_equal(variables[i], values[i], trail):
            return False
    return True


# --------------------------------- optimization -------------------------------

def iterate_decrease(optimum_variable, trail):
    """bv.pl, iterate_decrease/2 (iterate_dec/2): pivot until *optimum_
    variable* is at its minimum; returns that minimum (R + I), or None where
    it fails (unlimited).  The recursion on `applied` is a loop."""
    while True:
        state = state_of(optimum_variable)
        if state is None or state.linear_form is None:
            return None
        form = state.linear_form
        status = decrease_step(form.terms, trail)
        if status is None:
            return None
        if status[0] == STATUS_APPLIED:
            continue
        if status[0] == STATUS_OPTIMUM:
            return add(form.rest, form.constant)
        return None


def iterate_increase(optimum_variable, trail):
    """bv.pl, iterate_increase/2 (iterate_inc/2)."""
    while True:
        state = state_of(optimum_variable)
        if state is None or state.linear_form is None:
            return None
        form = state.linear_form
        status = increase_step(form.terms, trail)
        if status is None:
            return None
        if status[0] == STATUS_APPLIED:
            continue
        if status[0] == STATUS_OPTIMUM:
            return add(form.rest, form.constant)
        return None


def decrease_step(terms, trail):
    """bv.pl, decrease_step/2 (dec_step/2): one pivot or bound swap that
    decreases the row *terms* belongs to.  Returns OPTIMUM (nothing
    changed), APPLIED, or (STATUS_UNLIMITED, Indep, DepT); None where it
    fails.  Searches left to right; the recursion on the next term is a
    loop."""
    for variable, coefficient in terms:
        state = state_of(variable)
        if state is None or state.bounds is None:
            return None
        bounds = state.bounds
        kind = bounds.kind
        if kind == BOUNDS_UPPER_ACTIVE:
            if sign(coefficient) > 0:
                tightest = lower_bound(variable)
                if tightest is not None:
                    if not pivot_exchange(tightest[0], variable, tightest[1],
                                          bounds_upper(bounds.upper), trail):
                        return None
                    return APPLIED
                return (STATUS_UNLIMITED, variable, bounds_upper(bounds.upper))
        elif kind == BOUNDS_LOWER_UPPER_ACTIVE:
            if sign(coefficient) > 0:
                initial = subtract(bounds.lower, bounds.upper)
                dependents = basis(variable)
                if dependents is False:
                    return None
                tightest = lower_bound_tightest(
                    dependents, variable,
                    (variable, bounds_lower_active_upper(bounds.lower, bounds.upper),
                     initial))
                if not pivot_or_bound_swap(tightest[0], variable, tightest[1],
                                           bounds_lower_upper(bounds.lower, bounds.upper),
                                           trail):
                    return None
                return APPLIED
        elif kind == BOUNDS_LOWER_ACTIVE:
            if sign(coefficient) < 0:
                tightest = upper_bound(variable)
                if tightest is not None:
                    if not pivot_exchange(tightest[0], variable, tightest[1],
                                          bounds_lower(bounds.lower), trail):
                        return None
                    return APPLIED
                return (STATUS_UNLIMITED, variable, bounds_lower(bounds.lower))
        elif kind == BOUNDS_LOWER_ACTIVE_UPPER:
            if sign(coefficient) < 0:
                initial = subtract(bounds.upper, bounds.lower)
                dependents = basis(variable)
                if dependents is False:
                    return None
                tightest = upper_bound_tightest(
                    dependents, variable,
                    (variable, bounds_lower_upper_active(bounds.lower, bounds.upper),
                     initial))
                if not pivot_or_bound_swap(tightest[0], variable, tightest[1],
                                           bounds_lower_upper(bounds.lower, bounds.upper),
                                           trail):
                    return None
                return APPLIED
        elif kind == BOUNDS_NONE:
            return (STATUS_UNLIMITED, variable, bounds_none())
        else:                                   # no disjunct matches
            return None
    return OPTIMUM


def increase_step(terms, trail):
    """bv.pl, increase_step/2 (inc_step/2): decrease_step with the
    comparisons of K turned round."""
    for variable, coefficient in terms:
        state = state_of(variable)
        if state is None or state.bounds is None:
            return None
        bounds = state.bounds
        kind = bounds.kind
        if kind == BOUNDS_UPPER_ACTIVE:
            if sign(coefficient) < 0:
                tightest = lower_bound(variable)
                if tightest is not None:
                    if not pivot_exchange(tightest[0], variable, tightest[1],
                                          bounds_upper(bounds.upper), trail):
                        return None
                    return APPLIED
                return (STATUS_UNLIMITED, variable, bounds_upper(bounds.upper))
        elif kind == BOUNDS_LOWER_UPPER_ACTIVE:
            if sign(coefficient) < 0:
                initial = subtract(bounds.lower, bounds.upper)
                dependents = basis(variable)
                if dependents is False:
                    return None
                tightest = lower_bound_tightest(
                    dependents, variable,
                    (variable, bounds_lower_active_upper(bounds.lower, bounds.upper),
                     initial))
                if not pivot_or_bound_swap(tightest[0], variable, tightest[1],
                                           bounds_lower_upper(bounds.lower, bounds.upper),
                                           trail):
                    return None
                return APPLIED
        elif kind == BOUNDS_LOWER_ACTIVE:
            if sign(coefficient) > 0:
                tightest = upper_bound(variable)
                if tightest is not None:
                    if not pivot_exchange(tightest[0], variable, tightest[1],
                                          bounds_lower(bounds.lower), trail):
                        return None
                    return APPLIED
                return (STATUS_UNLIMITED, variable, bounds_lower(bounds.lower))
        elif kind == BOUNDS_LOWER_ACTIVE_UPPER:
            if sign(coefficient) > 0:
                initial = subtract(bounds.upper, bounds.lower)
                dependents = basis(variable)
                if dependents is False:
                    return None
                tightest = upper_bound_tightest(
                    dependents, variable,
                    (variable, bounds_lower_upper_active(bounds.lower, bounds.upper),
                     initial))
                if not pivot_or_bound_swap(tightest[0], variable, tightest[1],
                                           bounds_lower_upper(bounds.lower, bounds.upper),
                                           trail):
                    return None
                return APPLIED
        elif kind == BOUNDS_NONE:
            return (STATUS_UNLIMITED, variable, bounds_none())
        else:
            return None
    return OPTIMUM


# ------------------------------ best first heuristic --------------------------

def decrease_step_best(terms, trail):
    """bv.pl, decrease_step_best/2 (dec_step_best/2): decrease_step with a
    local best-first choice.  1.3.3 does not call it (its call in
    iterate_decrease/2 is commented out)."""
    evaluated = decrease_evaluate(terms)
    if evaluated is None:
        return None
    if type(evaluated) is tuple:                # unlimited(_, _)
        return evaluated
    if not evaluated:
        return OPTIMUM
    evaluated.sort(key=_delta_key)              # keysort/2 is stable
    action = evaluated[0][1]
    if action[0] == PIVOT_EXCHANGE:
        done = pivot_exchange(action[1], action[2], action[3], action[4], trail)
    else:
        done = pivot_or_bound_swap(action[1], action[2], action[3], action[4],
                                   trail)
    if not done:
        return None
    return APPLIED


def _delta_key(entry):
    return entry[0]


def _float_of(rational):
    """evaluate_arithmetic(float(X)) in Q: arithmetic.rational_to_float,
    arith.pl's rational_to_float/3 with its limit_encoding_length/5
    (test_float_of_is_rational_to_float)."""
    return rational_to_float(rational)


def decrease_evaluate(terms):
    """bv.pl, decrease_evaluate/2 (dec_eval/2).  Returns a list of
    (Delta, Action) pairs, an unlimited status, or None where it fails.  An
    Action is (PIVOT_EXCHANGE or PIVOT_OR_BOUND_SWAP, Vub, V, Vb, Wd).  An
    unlimited term after a listed one returns the status outright; 1.3.3
    leaves it as the tail of a partial list (DEVIATIONS.md D10,
    test_decrease_evaluate_returns_unlimited_after_a_listed_term)."""
    result = []
    for variable, coefficient in terms:
        state = state_of(variable)
        if state is None or state.bounds is None:
            return None
        bounds = state.bounds
        kind = bounds.kind
        if kind == BOUNDS_UPPER_ACTIVE:
            if sign(coefficient) > 0:
                tightest = lower_bound(variable)
                if tightest is None:
                    return (STATUS_UNLIMITED, variable, bounds_upper(bounds.upper))
                delta = _float_of(multiply(tightest[2], coefficient))
                result.append((delta, (PIVOT_EXCHANGE, tightest[0], variable,
                                       tightest[1], bounds_upper(bounds.upper))))
        elif kind == BOUNDS_LOWER_UPPER_ACTIVE:
            if sign(coefficient) > 0:
                initial = subtract(bounds.lower, bounds.upper)
                dependents = basis(variable)
                if dependents is False:
                    return None
                tightest = lower_bound_tightest(
                    dependents, variable,
                    (variable, bounds_lower_active_upper(bounds.lower, bounds.upper),
                     initial))
                delta = _float_of(multiply(tightest[2], coefficient))
                result.append((delta, (PIVOT_OR_BOUND_SWAP, tightest[0], variable,
                                       tightest[1],
                                       bounds_lower_upper(bounds.lower, bounds.upper))))
        elif kind == BOUNDS_LOWER_ACTIVE:
            if sign(coefficient) < 0:
                tightest = upper_bound(variable)
                if tightest is None:
                    return (STATUS_UNLIMITED, variable, bounds_lower(bounds.lower))
                delta = _float_of(multiply(tightest[2], coefficient))
                result.append((delta, (PIVOT_EXCHANGE, tightest[0], variable,
                                       tightest[1], bounds_lower(bounds.lower))))
        elif kind == BOUNDS_LOWER_ACTIVE_UPPER:
            if sign(coefficient) < 0:
                initial = subtract(bounds.upper, bounds.lower)
                dependents = basis(variable)
                if dependents is False:
                    return None
                tightest = upper_bound_tightest(
                    dependents, variable,
                    (variable, bounds_lower_upper_active(bounds.lower, bounds.upper),
                     initial))
                delta = _float_of(multiply(tightest[2], coefficient))
                result.append((delta, (PIVOT_OR_BOUND_SWAP, tightest[0], variable,
                                       tightest[1],
                                       bounds_lower_upper(bounds.lower, bounds.upper))))
        elif kind == BOUNDS_NONE:
            return (STATUS_UNLIMITED, variable, bounds_none())
        else:
            return None
    return result


# ------------------------- find the most constraining row ---------------------

def upper_bound(variable):
    """bv.pl, upper_bound/2 (ub/2): the basis row that limits *variable*'s
    increase the most, as (Dep, W, Ub); None where it fails (no such row)."""
    dependents = basis(variable)
    if dependents is False:
        return None
    return upper_bound_first(dependents, variable)


def upper_bound_first(dependents, variable):
    """bv.pl, upper_bound_first/3 (ub_first/3): the first feasible limiting
    row, then upper_bound_tightest over the rest."""
    node = deref(dependents)
    while type(node) is ListCell:
        dependent = node.head
        node = deref(node.rest)
        state = state_of(dependent)
        if state is None or state.linear_form is None or state.bounds is None:
            continue
        inner = upper_bound_inner(state.bounds, variable, state.linear_form)
        if inner is not None and compare(inner[1], ZERO) >= 0:
            return upper_bound_tightest(node, variable,
                                        (deref(dependent), inner[0], inner[1]))
    return None                                 # no clause for []


def upper_bound_tightest(dependents, variable, tightest):
    """bv.pl, upper_bound/4 (ub/4): keep the row with the smallest Ub >= 0."""
    node = deref(dependents)
    while type(node) is ListCell:
        dependent = node.head
        node = deref(node.rest)
        state = state_of(dependent)
        if state is None or state.linear_form is None or state.bounds is None:
            continue
        inner = upper_bound_inner(state.bounds, variable, state.linear_form)
        if inner is not None and compare(inner[1], tightest[2]) < 0 \
                and compare(inner[1], ZERO) >= 0:
            tightest = (deref(dependent), inner[0], inner[1])
    return tightest


def lower_bound(variable):
    """bv.pl, lower_bound/2 (lb/2)."""
    dependents = basis(variable)
    if dependents is False:
        return None
    return lower_bound_first(dependents, variable)


def lower_bound_first(dependents, variable):
    """bv.pl, lower_bound_first/3 (lb_first/3)."""
    node = deref(dependents)
    while type(node) is ListCell:
        dependent = node.head
        node = deref(node.rest)
        state = state_of(dependent)
        if state is None or state.linear_form is None or state.bounds is None:
            continue
        inner = lower_bound_inner(state.bounds, variable, state.linear_form)
        if inner is not None and compare(inner[1], ZERO) <= 0:
            return lower_bound_tightest(node, variable,
                                        (deref(dependent), inner[0], inner[1]))
    return None


def lower_bound_tightest(dependents, variable, tightest):
    """bv.pl, lower_bound/4 (lb/4): keep the row with the largest Lb =< 0."""
    node = deref(dependents)
    while type(node) is ListCell:
        dependent = node.head
        node = deref(node.rest)
        state = state_of(dependent)
        if state is None or state.linear_form is None or state.bounds is None:
            continue
        inner = lower_bound_inner(state.bounds, variable, state.linear_form)
        if inner is not None and compare(inner[1], tightest[2]) > 0 \
                and compare(inner[1], ZERO) <= 0:
            tightest = (deref(dependent), inner[0], inner[1])
    return tightest


def lower_bound_inner(bounds, variable, form):
    """bv.pl, lower_bound_inner/5 (lb_inner/5): for a row with bound type
    *bounds*, the bound it would become active at and the limit Lb it puts
    on *variable*; None where it fails."""
    kind = bounds.kind
    if kind != BOUNDS_LOWER and kind != BOUNDS_UPPER and kind != BOUNDS_LOWER_UPPER:
        return None
    found = normal_form_right_hand_side(form, variable)
    if found is None:
        return None
    right_hand_side, coefficient = found
    if kind == BOUNDS_LOWER:
        if sign(coefficient) > 0:
            return (bounds_lower_active(bounds.lower),
                    divide(subtract(bounds.lower, right_hand_side), coefficient))
        return None
    if kind == BOUNDS_UPPER:
        if sign(coefficient) < 0:
            return (bounds_upper_active(bounds.upper),
                    divide(subtract(bounds.upper, right_hand_side), coefficient))
        return None
    signum = sign(coefficient)                  # case_signum(K, <, =, >)
    if signum < 0:
        return (bounds_lower_upper_active(bounds.lower, bounds.upper),
                divide(subtract(bounds.upper, right_hand_side), coefficient))
    if signum == 0:
        return None
    return (bounds_lower_active_upper(bounds.lower, bounds.upper),
            divide(subtract(bounds.lower, right_hand_side), coefficient))


def upper_bound_inner(bounds, variable, form):
    """bv.pl, upper_bound_inner/5 (ub_inner/5)."""
    kind = bounds.kind
    if kind != BOUNDS_LOWER and kind != BOUNDS_UPPER and kind != BOUNDS_LOWER_UPPER:
        return None
    found = normal_form_right_hand_side(form, variable)
    if found is None:
        return None
    right_hand_side, coefficient = found
    if kind == BOUNDS_LOWER:
        if sign(coefficient) < 0:
            return (bounds_lower_active(bounds.lower),
                    divide(subtract(bounds.lower, right_hand_side), coefficient))
        return None
    if kind == BOUNDS_UPPER:
        if sign(coefficient) > 0:
            return (bounds_upper_active(bounds.upper),
                    divide(subtract(bounds.upper, right_hand_side), coefficient))
        return None
    signum = sign(coefficient)
    if signum < 0:
        return (bounds_lower_active_upper(bounds.lower, bounds.upper),
                divide(subtract(bounds.lower, right_hand_side), coefficient))
    if signum == 0:
        return None
    return (bounds_lower_upper_active(bounds.lower, bounds.upper),
            divide(subtract(bounds.upper, right_hand_side), coefficient))


# ---------------------------------- equations ---------------------------------

def solve(form, trail):
    """bv.pl, solve/1: add the equation 0 = *form* and export the bindings
    it implies."""
    bindings = []
    if not solve_homogeneous(form.terms, form, form.constant, bindings, trail):
        return False
    return export_bindings(bindings, trail)


def solve_homogeneous(terms, form, constant, bindings, trail):
    """bv.pl, solve/5: *terms* is the homogeneous part of *form*, *constant*
    its inhomogeneous part; implied bindings are appended to *bindings*.
    Its last goal for categories 3 and 4, reconsider_basis_list/3, runs
    after solve_step returns, so the tail calls between the two do not nest
    (test_a_cascade_of_implied_values_needs_no_recursion).  Where that pass
    changes the store, strictly_satisfiable checks it (D19)."""
    code, new_basis = solve_step(terms, form, constant, bindings, trail)
    if code == _SOLVE_FAILED:
        return False
    if code == _SOLVE_FINISHED:
        return True
    component = state_of(new_basis.head).component
    mark = trail.mark()
    if not reconsider_basis_list(new_basis, bindings, trail):
        return False
    if trail.mark() == mark:                    # the pass changed nothing
        return True
    return strictly_satisfiable(component, trail)


def strictly_satisfiable(component, trail):
    """Not in 1.3.3 (DEVIATIONS.md D19): False when a strict bound of a
    member of *component* cannot hold.  1.3.3's reconsider pass can leave
    a variable at a strict bound that it cannot leave, so a binding is
    accepted on an unsatisfiable store
    (test_a_binding_that_leaves_strict_constraints_unsatisfiable_fails,
    test_a_binding_is_accepted_exactly_when_z3_finds_it_satisfiable).

    The store without strictness is satisfiable here.  The pass leaves
    the row of every bounded basis variable holding only nonbasic
    variables at an active bound, and every basis value within its
    bounds, so a nonbasic variable without an active bound (an implicit
    0, which can be outside its bounds) is only in unbounded rows
    (test_the_check_runs_where_its_invariant_holds).  A strict bound
    holds somewhere in that store when its variable is inside it now, or
    when a small step takes it inside: a nonbasic variable at a strict active bound can step
    inside unless the row of a basis variable at one of its bounds would
    step out with it.  Otherwise its sup (or inf) over the store must be
    beyond the bound.  If each strict bound holds somewhere, all hold at
    once, at the average of those points: the store is convex."""
    members = component_all_variables(deref(component))
    if members is None:
        return True
    variables = []
    for member in list_elements(members):
        variable = deref(member)
        if is_var(variable):
            variables.append(variable)
    candidates = []             # (variable, factor): minimise factor*variable
    cannot_increase = {}        # nonbasic variables, by _id
    cannot_decrease = {}
    for variable in variables:                  # basis variables at a bound
        state = state_of(variable)
        if state is None or state.bounds is None or state.linear_form is None:
            continue
        form = state.linear_form
        if independent(form, variable):
            continue
        bounds = state.bounds
        kind = bounds.kind
        value = add(form.rest, form.constant)
        at_lower = (kind == BOUNDS_LOWER or kind == BOUNDS_LOWER_UPPER) \
            and compare(value, bounds.lower) <= 0
        at_upper = (kind == BOUNDS_UPPER or kind == BOUNDS_LOWER_UPPER) \
            and compare(value, bounds.upper) >= 0
        if not (at_lower or at_upper):
            continue
        if at_lower and state.lower_strict:
            candidates.append((variable, MINUS_ONE))
        if at_upper and state.upper_strict:
            candidates.append((variable, ONE))
        for term_variable, coefficient in form.terms:
            signum = sign(coefficient)
            if (at_lower and signum < 0) or (at_upper and signum > 0):
                cannot_increase[term_variable._id] = True
            if (at_lower and signum > 0) or (at_upper and signum < 0):
                cannot_decrease[term_variable._id] = True
    if not cannot_increase and not cannot_decrease and not candidates:
        return True
    for variable in variables:          # blocked at a strict active bound
        state = state_of(variable)
        if state is None or state.bounds is None:
            continue
        kind = state.bounds.kind
        if state.lower_strict and variable._id in cannot_increase and \
                (kind == BOUNDS_LOWER_ACTIVE
                 or kind == BOUNDS_LOWER_ACTIVE_UPPER):
            candidates.append((variable, MINUS_ONE))
        if state.upper_strict and variable._id in cannot_decrease and \
                (kind == BOUNDS_UPPER_ACTIVE
                 or kind == BOUNDS_LOWER_UPPER_ACTIVE):
            candidates.append((variable, ONE))
    for variable, factor in candidates:
        state = state_of(variable)
        if factor is MINUS_ONE:
            beyond = negate(state.bounds.lower)
        else:
            beyond = state.bounds.upper
        if not _decreases_below(state.linear_form, factor, beyond, trail):
            return False
    return True


def _decreases_below(form, factor, limit, trail):
    """Whether *factor* times *form* takes a value below *limit* in the
    store, strictness ignored: iterate_decrease on it, as infimum_linear
    sets it up, stopped as soon as the value is below *limit* or the
    decrease is unlimited.  The store is left as it was.

    A failed determine_active_decrease (a free variable in the row) or
    decrease_step (a term without an active bound) counts as "not below",
    and the binding is refused.  Neither can happen: *form* is a bounded
    basis variable's row, which holds only nonbasic variables at an
    active bound, or a nonbasic variable at an active bound itself
    (test_the_check_runs_where_its_invariant_holds).  If the invariant
    ever broke, a refused binding is a visible missing answer, where
    an accepted one could hide an unsatisfiable store."""
    mark = trail.mark()
    objective = multiply_linear_factor(form, factor)
    dependent = Var()
    below = False
    if variable_with_definition_intern(bounds_none(), dependent, objective,
                                       0b00, trail) \
            and determine_active_decrease(objective, trail):
        while True:                                 # iterate_decrease/2
            state = state_of(dependent)
            current = state.linear_form
            if compare(add(current.rest, current.constant), limit) < 0:
                below = True
                break
            status = decrease_step(current.terms, trail)
            if status is None or status[0] == STATUS_OPTIMUM:
                break
            if status[0] == STATUS_UNLIMITED:
                below = True
                break
    trail.undo(mark)
    return below


def solve_step(terms, form, constant, bindings, trail):
    """bv.pl, solve/5 up to its last goal.  Returns (_SOLVE_FAILED, None),
    (_SOLVE_FINISHED, None), or (_SOLVE_RECONSIDER, Basis) where the clause
    ends in reconsider_basis_list(Basis, ...)."""
    if not terms:                                           # clause 1
        if is_zero(constant):
            return _SOLVE_FINISHED, None
        return _SOLVE_FAILED, None
    components, preference, new_variables = select_dependent(terms)  # clause 2
    category = preference[0]
    selected = preference[1]
    form_1 = isolate(selected, form)
    if form_1 is None:
        return _SOLVE_FAILED, None
    if category == 1:
        _put_attributes(selected, trail, linear_form=form_1)
        back_substitute_collect_binding(form_1.terms, selected,
                                        form_1.constant, bindings)
        if not equate_components(new_variables, components, trail):
            return _SOLVE_FAILED, None
        return _SOLVE_FINISHED, None
    if category == 2:
        component = state_of(selected).component
        dependents = component_all_variables(component)
        if dependents is None:
            return _SOLVE_FAILED, None
        if len(components) == 1:                # rank increasing
            back_substitute_collect_bindings(dependents, selected, form_1,
                                             bindings, trail)
        else:
            back_substitute_variables(dependents, selected, form_1, trail)
        if not equate_components(new_variables, components, trail):
            return _SOLVE_FAILED, None
        return _SOLVE_FINISHED, None
    if category == 3:
        _put_attributes(selected, trail, linear_form=form_1)
        bounds = state_of(selected).bounds
        if bounds is None:
            return _SOLVE_FAILED, None
        if not deactivate_bound(bounds, selected, trail):
            return _SOLVE_FAILED, None
        if not equate_components(new_variables, components, trail):
            return _SOLVE_FAILED, None
        new_basis = basis_add(selected, trail)
        if new_basis is False:
            return _SOLVE_FAILED, None
        if not undetermined_active(form_1, trail):
            return _SOLVE_FAILED, None
        back_substitute_collect_binding(form_1.terms, selected,
                                        form_1.constant, bindings)
        return _SOLVE_RECONSIDER, new_basis
    # category 4
    state = state_of(selected)
    if state.bounds is None or state.component is None:
        return _SOLVE_FAILED, None
    bounds = state.bounds
    dependents = component_all_variables(state.component)
    if dependents is None:
        return _SOLVE_FAILED, None
    if len(components) == 1:                    # rank increasing
        back_substitute_collect_bindings(dependents, selected, form_1,
                                         bindings, trail)
    else:
        back_substitute_variables(dependents, selected, form_1, trail)
    if not deactivate_bound(bounds, selected, trail):
        return _SOLVE_FAILED, None
    new_basis = basis_add(selected, trail)
    if new_basis is False:
        return _SOLVE_FAILED, None
    if not equate(components, None, trail):
        return _SOLVE_FAILED, None
    if not undetermined_active(form_1, trail):
        return _SOLVE_FAILED, None
    return _SOLVE_RECONSIDER, new_basis


def solve_for_variable(form, variable, trail):
    """bv.pl, solve_for_variable/2 (solve_x/2): solve 0 = *form* for
    *variable*, a variable of type t_none."""
    bindings = []
    if not solve_for_variable_homogeneous(form.terms, form, form.constant,
                                          variable, bindings, trail):
        return False
    return export_bindings(bindings, trail)


def solve_for_variable_homogeneous(terms, form, constant, selected, bindings,
                                   trail):
    """bv.pl, solve_for_variable/6 (solve_x/6)."""
    if not terms:                                           # clause 1
        return is_zero(constant)
    components, _, new_variables = select_dependent(terms)  # clause 2
    selected = deref(selected)
    form_1 = isolate(selected, form)
    if form_1 is None:
        return False
    state = state_of(selected)
    if state is not None and state.component is not None:
        dependents = component_all_variables(state.component)
        if dependents is None:
            return False
        if len(components) == 1:                # rank increasing
            back_substitute_collect_bindings(dependents, selected, form_1,
                                             bindings, trail)
        else:
            back_substitute_variables(dependents, selected, form_1, trail)
        return equate_components(new_variables, components, trail)
    _put_attributes(selected, trail, linear_form=form_1)
    back_substitute_collect_binding(form_1.terms, selected, form_1.constant,
                                    bindings)
    return equate_components(new_variables, components, trail)


def select_dependent(terms):
    """bv.pl, select_dependent/7 (sd/7).  Returns (ClassesUniq, Preference,
    NV): the components of the old variables as an ordered set, the
    preferred (Category, Variable, Coefficient), and the new variables in
    order.  The preference starts at 9-9-0, which every category beats."""
    components = []
    chosen = (9, 9, ZERO)
    new_variables = []
    for variable, coefficient in terms:
        state = state_of(variable)
        if state is not None and state.component is not None:     # old
            components = ord_add_element(components, deref(state.component))
            if _has_type_none(state):
                chosen = preference(chosen, (2, variable, coefficient))
            else:
                chosen = preference(chosen, (4, variable, coefficient))
        else:                                                       # new
            new_variables.append(variable)
            if _has_type_none(state):
                chosen = preference(chosen, (1, variable, coefficient))
            else:
                chosen = preference(chosen, (3, variable, coefficient))
    return components, chosen, new_variables


def ord_add_element(elements, element):
    """library(ordsets), ord_add_element/3 on component variables, in the
    standard order of variables: creation order (DEVIATIONS.md D4)."""
    key = element._id
    result = []
    i = 0
    while i < len(elements) and elements[i]._id < key:
        result.append(elements[i])
        i += 1
    if i < len(elements) and elements[i] is element:
        return elements
    result.append(element)
    while i < len(elements):
        result.append(elements[i])
        i += 1
    return result


def preference(best, current):
    """bv.pl, preference/3: the lower category wins; on a tie, *current*
    (test_preference_takes_the_lower_category_and_the_later_on_ties)."""
    relation = (best[0] > current[0]) - (best[0] < current[0])
    if relation == 0:
        return current
    if relation < 0:
        return best
    return current



def equate_components(new_variables, components, trail):
    """bv.pl, equate_components/3 (eq_classes/3): the new variables get one
    new component, which every component in *components* joins."""
    if not new_variables:                                   # var(NV)
        return equate(components, None, trail)
    component = Var()
    head, tail = open_list(new_variables)
    if not component_new(component, head, tail, None, trail):
        return False
    attach_component(new_variables, component, trail)
    return equate(components, component, trail)


def equate(elements, first, trail):
    """bv.pl, equate/2: unify every element with *first* (with the first
    element when *first* is None, an unbound variable)."""
    for element in elements:
        if first is None:
            first = element
        elif not unify(element, first, trail):
            return False
    return True


def attach_component(variables, component, trail):
    """bv.pl, attach_component/2 (attach_class/2)."""
    for variable in variables:
        _put_attributes(deref(variable), trail, component=component)
    return True


def unconstrained(form):
    """bv.pl, unconstrained/4: a variable of *form* of category 1 or 2 (type
    t_none), with its coefficient and the form without it.  Returns
    (Uc, Kuc, Rest), or None."""
    _, chosen, _ = select_dependent(form.terms)
    if chosen[0] > 2:
        return None
    deleted = delete_factor(chosen[1], form)
    if deleted is None:
        return None
    return chosen[1], deleted[1], deleted[0]


def same_component(terms, component, trail):
    """bv.pl, same_component/2 (same_class/2)."""
    for variable, _ in terms:
        if get_or_add_component(variable, component, trail) is None:
            return False
    return True


def get_or_add_component(variable, component, trail):
    """bv.pl, get_or_add_component/2 (get_or_add_class/2): *variable*'s
    component, unified with *component* (None for a fresh variable).
    Returns the component, or None where the unification fails."""
    variable = deref(variable)
    state = state_of(variable)
    if state is not None and state.component is not None:  # clause 1
        if component is None or unify(state.component, component, trail):
            return state.component
        return None
    if component is None:                                   # clause 2
        component = Var()
    _put_attributes(variable, trail, component=component)
    head, tail = open_list([variable])
    if not component_new(component, head, tail, None, trail):
        return None
    return component


def all_variables(variable):
    """bv.pl, all_variables/2 (allvars/2): the member list of *variable*'s
    component, or None."""
    state = state_of(variable)
    if state is None or state.component is None:
        return None
    return component_all_variables(state.component)


def deactivate_bound(bounds, variable, trail):
    """bv.pl, deactivate_bound/2.  False for t_none, which has no clause."""
    kind = bounds.kind
    if kind == BOUNDS_LOWER or kind == BOUNDS_UPPER or kind == BOUNDS_LOWER_UPPER:
        return True
    if kind == BOUNDS_LOWER_ACTIVE:
        _put_attributes(variable, trail, bounds=bounds_lower(bounds.lower))
        return True
    if kind == BOUNDS_LOWER_ACTIVE_UPPER or kind == BOUNDS_LOWER_UPPER_ACTIVE:
        _put_attributes(variable, trail,
                        bounds=bounds_lower_upper(bounds.lower, bounds.upper))
        return True
    if kind == BOUNDS_UPPER_ACTIVE:
        _put_attributes(variable, trail, bounds=bounds_upper(bounds.upper))
        return True
    return False


def introduce_at(variable, value, bounds, trail):
    """bv.pl, introduce_at/3 (intro_at/3): give *variable* type *bounds* and
    move it to *value*."""
    _put_attributes(variable, trail, bounds=bounds)
    if is_zero(value):
        return True
    return back_substitute_delta(variable, value, trail)


def undetermined_active(form, trail):
    """bv.pl, undetermined_active/1: activate a bound of every variable of
    *form* that has bounds but no active one.  The choice t_lu -> t_Lu is
    arbitrary (bv.pl's comment)."""
    return undetermined_active_homogeneous(form.terms, trail)


def undetermined_active_homogeneous(terms, trail):
    """bv.pl, undetermined_active_homogeneous/1."""
    for variable, _ in terms:
        state = state_of(variable)
        if state is None or state.bounds is None:
            return False
        if not undetermined_active_type(state.bounds, variable, trail):
            return False
    return True


def undetermined_active_type(bounds, variable, trail):
    """bv.pl, undetermined_active/2."""
    kind = bounds.kind
    if kind == BOUNDS_LOWER:
        return introduce_at(variable, bounds.lower,
                            bounds_lower_active(bounds.lower), trail)
    if kind == BOUNDS_UPPER:
        return introduce_at(variable, bounds.upper,
                            bounds_upper_active(bounds.upper), trail)
    if kind == BOUNDS_LOWER_UPPER:
        return introduce_at(variable, bounds.lower,
                            bounds_lower_active_upper(bounds.lower, bounds.upper),
                            trail)
    return True                 # t_none and the active types


def determine_active_decrease(form, trail):
    """bv.pl, determine_active_decrease/1 (determine_active_dec/1)."""
    return determine_active(form.terms, MINUS_ONE, trail)


def determine_active_increase(form, trail):
    """bv.pl, determine_active_increase/1 (determine_active_inc/1)."""
    return determine_active(form.terms, ONE, trail)


def determine_active(terms, direction, trail):
    """bv.pl, determine_active/2."""
    for variable, coefficient in terms:
        state = state_of(variable)
        if state is None or state.bounds is None:
            return False
        if not determine_active_type(state.bounds, variable, coefficient,
                                     direction, trail):
            return False
    return True


def determine_active_type(bounds, variable, coefficient, direction, trail):
    """bv.pl, determine_active/4.  t_none has no clause, so an objective with
    a free variable fails
    (test_determine_active_picks_the_bound_by_the_sign_of_k_times_s)."""
    kind = bounds.kind
    if kind == BOUNDS_LOWER_ACTIVE or kind == BOUNDS_LOWER_ACTIVE_UPPER \
            or kind == BOUNDS_UPPER_ACTIVE or kind == BOUNDS_LOWER_UPPER_ACTIVE:
        return True
    if kind == BOUNDS_LOWER:
        return introduce_at(variable, bounds.lower,
                            bounds_lower_active(bounds.lower), trail)
    if kind == BOUNDS_UPPER:
        return introduce_at(variable, bounds.upper,
                            bounds_upper_active(bounds.upper), trail)
    if kind == BOUNDS_LOWER_UPPER:
        signum = sign(multiply(coefficient, direction))     # case_signum
        if signum < 0:
            return introduce_at(variable, bounds.lower,
                                bounds_lower_active_upper(bounds.lower, bounds.upper),
                                trail)
        if signum == 0:
            return False
        return introduce_at(variable, bounds.upper,
                            bounds_lower_upper_active(bounds.lower, bounds.upper),
                            trail)
    return False


def detach_bounds(variable, trail):
    """bv.pl, detach_bounds/1: drop *variable*'s bounds.  An independent
    variable is first exchanged against its tightest row; a dependent one
    leaves the basis (test_detach_bounds_drops_a_dependent_from_the_basis)."""
    variable = deref(variable)
    state = state_of(variable)
    if state is None or state.linear_form is None:
        return False
    form = state.linear_form
    _put_attributes(variable, trail, bounds=bounds_none(), lower_strict=False,
                    upper_strict=False)
    if independent(form, variable):
        tightest = upper_bound(variable)                    # exchange against tightest
        if tightest is None:
            tightest = lower_bound(variable)
        if tightest is None:
            return True
        if not basis_drop(tightest[0], trail):
            return False
        return pivot(tightest[0], variable, tightest[1], trail)
    return basis_drop(variable, trail)


# ----------------------------- manipulate the basis ---------------------------

def basis_drop(variable, trail):
    """bv.pl, basis_drop/1."""
    state = state_of(variable)
    if state is None or state.component is None:
        return False
    return component_basis_drop(state.component, variable, trail)


def basis(variable):
    """bv.pl, basis/2: the basis of *variable*'s component (a ListCell chain,
    None for []), or False where get_atts fails.  It reads the component
    record itself, because components.component_basis returns None for both
    (test_basis_add_drop_and_pivot_are_undone)."""
    state = state_of(variable)
    if state is None or state.component is None:
        return False
    record = get_attr(state.component, COMPONENT_KEY)
    if record is None:
        return False
    return record.basis


def basis_add(variable, trail):
    """bv.pl, basis_add/2: returns NewBasis, or False."""
    state = state_of(variable)
    if state is None or state.component is None:
        return False
    return component_basis_add(state.component, variable, trail)


def basis_pivot(leave, enter, trail):
    """bv.pl, basis_pivot/2."""
    state = state_of(leave)
    if state is None or state.component is None:
        return False
    return component_basis_pivot(state.component, enter, leave, trail)


# ----------------------------------- pivot ------------------------------------

def pivot_ignoring_bounds(dependent, independent_variable, trail):
    """bv.pl, pivot/2: pivot ignoring rhs and active states
    (test_pivot_without_the_bounds_ignores_them)."""
    state = state_of(dependent)
    if state is None or state.linear_form is None:
        return False
    deleted = delete_factor(independent_variable, state.linear_form)
    if deleted is None:
        return False
    form_0, coefficient = deleted
    factor = divide(MINUS_ONE, coefficient)
    form = add_linear_forms_scaled(
        form_0, factor, LinearForm(ZERO, ZERO, [(deref(dependent), MINUS_ONE)]),
        factor)
    if form is None:
        return False
    return back_substitute(independent_variable, form, trail)


def pivot_exchange(dependent, independent_variable, dependent_bounds,
                   independent_bounds, trail):
    """bv.pl, pivot_exchange/4 (pivot_a/4)."""
    if not basis_pivot(dependent, independent_variable, trail):
        return False
    if not pivot(dependent, independent_variable, dependent_bounds, trail):
        return False
    _put_attributes(independent_variable, trail, bounds=independent_bounds)
    return True


def pivot_or_bound_swap(limiting, variable, limiting_bounds, variable_bounds,
                        trail):
    """bv.pl, pivot_or_bound_swap/4 (pivot_b/4): where *variable* limits
    itself (`Vub == V`), swap its active bound; otherwise pivot."""
    if deref(limiting) is deref(variable):
        _put_attributes(variable, trail, bounds=limiting_bounds)
        delta = bound_swap_delta(limiting_bounds)
        if delta is None:
            return False
        return back_substitute_delta(variable, delta, trail)
    return pivot_exchange(limiting, variable, limiting_bounds, variable_bounds,
                          trail)


def bound_swap_delta(bounds):
    """bv.pl, bound_swap_delta/2 (pivot_b_delta/2), or None."""
    if bounds.kind == BOUNDS_LOWER_ACTIVE_UPPER:
        return subtract(bounds.lower, bounds.upper)
    if bounds.kind == BOUNDS_LOWER_UPPER_ACTIVE:
        return subtract(bounds.upper, bounds.lower)
    return None


def select_active_bound(bounds):
    """bv.pl, select_active_bound/2: the value of the active bound, 0 where
    none is active."""
    kind = bounds.kind
    if kind == BOUNDS_LOWER_ACTIVE or kind == BOUNDS_LOWER_ACTIVE_UPPER:
        return bounds.lower
    if kind == BOUNDS_UPPER_ACTIVE or kind == BOUNDS_LOWER_UPPER_ACTIVE:
        return bounds.upper
    return ZERO


def pivot(dependent, independent_variable, independent_bounds, trail):
    """bv.pl, pivot/3: exchange *dependent* and *independent_variable*,
    taking care of the rhs and active states.  *dependent* gets the type
    *independent_bounds*; every row of the component is rewritten through
    back_substitute, one trailed replace per row
    (test_a_pivot_agrees_with_fraction_substitution,
    test_pivot_moves_the_active_bound_into_the_rest)."""
    dependent = deref(dependent)
    state = state_of(dependent)
    if state is None or state.linear_form is None:
        return False
    homogeneous = state.linear_form
    _put_attributes(dependent, trail, bounds=independent_bounds)
    active_bound = select_active_bound(independent_bounds)
    deleted = delete_factor(independent_variable, homogeneous)
    if deleted is None:
        return False
    form_0, coefficient = deleted
    factor = divide(MINUS_ONE, coefficient)
    form = add_linear_forms_scaled(
        form_0, factor,
        LinearForm(ZERO, negate(active_bound), [(dependent, MINUS_ONE)]), factor)
    if form is None:
        return False
    return back_substitute(independent_variable, form, trail)


def back_substitute_delta(variable, delta, trail):
    """bv.pl, back_substitute_delta/2 (backsubst_delta/2): X := X + Delta in
    every row, the delta going into the rest."""
    return back_substitute(variable,
                           LinearForm(ZERO, delta, [(deref(variable), ONE)]),
                           trail)


def back_substitute(variable, form, trail):
    """bv.pl, back_substitute/2 (backsubst/2): replace *variable* by *form*
    in every row of its component."""
    members = all_variables(variable)
    if members is None:
        return False
    return back_substitute_variables(members, variable, form, trail)


def back_substitute_variables(members, variable, form, trail):
    """bv.pl, back_substitute_variables/3 (bs/3): walk the open member list
    up to its tail; a member whose row holds *variable* gets the new row."""
    node = deref(members)
    while type(node) is ListCell:
        member = deref(node.head)
        node = deref(node.rest)
        state = state_of(member)
        if state is None or state.linear_form is None:
            continue
        new_form = normal_form_substitute(variable, form, state.linear_form)
        if new_form is not None:
            put_state(member, with_changes(state, linear_form=new_form), trail)
    return True


def back_substitute_collect_bindings(members, variable, form, bindings, trail):
    """bv.pl, back_substitute_collect_bindings/5 (bs_collect_bindings/5):
    back_substitute_variables, also collecting each row that became
    constant."""
    node = deref(members)
    while type(node) is ListCell:
        member = deref(node.head)
        node = deref(node.rest)
        state = state_of(member)
        if state is None or state.linear_form is None:
            continue
        new_form = normal_form_substitute(variable, form, state.linear_form)
        if new_form is not None:
            put_state(member, with_changes(state, linear_form=new_form), trail)
            back_substitute_collect_binding(new_form.terms, member,
                                            new_form.constant, bindings)
    return True


def back_substitute_collect_binding(homogeneous, variable, constant, bindings):
    """bv.pl, back_substitute_collect_binding//3 (bs_collect_binding//3): a
    row with no variables left binds its variable."""
    if not homogeneous:
        bindings.append((variable, constant))


# ------------------------------ reconsider the basis --------------------------

def reconsider_basis_list(continuation, bindings, trail):
    """bv.pl, reconsider_basis_list/3 (rcbl/3): find the first basis
    variable outside or at its bound and move it back."""
    found = _next_culprit(continuation, trail)
    if found is None:
        return True
    status, variable, violated, rest = found
    return reconsider_basis_list_status(status, variable, rest, bindings,
                                        violated, trail)


def _next_culprit(continuation, trail):
    """The walk of reconsider_basis_list/3: (Status, X, Violated,
    Continuation) for the first X that reconsider_basis_variable/3 accepts,
    or None at the end of the list."""
    node = deref(continuation)
    while type(node) is ListCell:
        variable = node.head
        rest = node.rest
        found = reconsider_basis_variable(variable, trail)
        if found is not None:
            return found[0], deref(variable), found[1], rest
        node = deref(rest)
    return None


def reconsider(variable, trail):
    """bv.pl, reconsider/1: reconsider one basis variable and export the
    bindings that implies."""
    found = reconsider_basis_variable(variable, trail)
    if found is None:
        return True                                         # clause 2
    bindings = []
    if not reconsider_basis_list_status(found[0], deref(variable), None,
                                        bindings, found[1], trail):
        return False
    return export_bindings(bindings, trail)


def reconsider_basis_variable(variable, trail):
    """bv.pl, reconsider_basis_variable/3 (rcb/3): if *variable* is at or
    outside a bound of its (inactive) type, take one step towards inside.
    Returns (Status, Violated), or None, in which case anything the step
    changed is undone, as the failed condition would undo it in 1.3.3."""
    state = state_of(variable)
    if state is None or state.linear_form is None or state.bounds is None:
        return None
    form = state.linear_form
    bounds = state.bounds
    value = add(form.rest, form.constant)
    mark = trail.mark()
    if bounds.kind == BOUNDS_LOWER:
        if compare(value, bounds.lower) <= 0:
            status = increase_step(form.terms, trail)
            if status is not None:
                return status, (BELOW_LOWER_BOUND, bounds.lower)
            trail.undo(mark)
        return None
    if bounds.kind == BOUNDS_UPPER:
        if compare(value, bounds.upper) >= 0:
            status = decrease_step(form.terms, trail)
            if status is not None:
                return status, (ABOVE_UPPER_BOUND, bounds.upper)
            trail.undo(mark)
        return None
    if bounds.kind == BOUNDS_LOWER_UPPER:
        if compare(value, bounds.lower) <= 0:
            status = increase_step(form.terms, trail)
            if status is not None:
                return status, (BELOW_LOWER_BOUND, bounds.lower)
            trail.undo(mark)
        if compare(value, bounds.upper) >= 0:
            status = decrease_step(form.terms, trail)
            if status is not None:
                return status, (ABOVE_UPPER_BOUND, bounds.upper)
            trail.undo(mark)
        return None
    return None                                 # don't care for other types


def reconsider_basis_list_status(status, variable, continuation, bindings,
                                 violated, trail):
    """bv.pl, reconsider_basis_list_status/6 (rcbl_status/6).

    In 1.3.3 rcbl_status, rcbl_opt, rcbl_app, rcbl_unl, rcbl and solve/5
    call each other in tail position, so the chain of calls grows with the
    number of pivots and basis rows.  Here each of those steps returns the
    call it ends in, and this loop makes it
    (test_a_cascade_of_implied_values_needs_no_recursion,
    test_long_rows_and_long_bases_need_no_recursion)."""
    while True:
        kind = status[0]
        if kind == STATUS_OPTIMUM:
            action, value = reconsider_basis_list_optimum(
                violated, variable, continuation, bindings, trail)
        elif kind == STATUS_APPLIED:
            action, value = reconsider_basis_list_applied(
                violated, variable, continuation, trail)
        else:
            action, value = reconsider_basis_list_unlimited(
                violated, variable, continuation, status[1], status[2], trail)
        if action == _FAIL:
            return False
        if action == _STATUS:
            status = value
            continue
        found = _next_culprit(value, trail)                 # _WALK
        if found is None:
            return True
        status, variable, violated, continuation = found


def reconsider_basis_list_optimum(violated, variable, continuation, bindings,
                                  trail):
    """bv.pl, reconsider_basis_list_optimum/5 (rcbl_opt/5): the optimum in
    the direction of the violated bound is reached.  Where it meets the
    bound, the implied value is solved for (and solve/5 reconsiders the
    rank-increased system); a strict bound there fails
    (test_reconsider_respects_strictness_at_the_optimum).  Returns the tail
    call as (_WALK, Continuation) or (_FAIL, None)."""
    state = state_of(variable)
    if state is None or state.linear_form is None or state.bounds is None:
        return _FAIL, None
    form = state.linear_form
    bounds = state.bounds
    optimum = add(form.rest, form.constant)
    if violated[0] == BELOW_LOWER_BOUND:                    # clause 1
        signum = sign(subtract(violated[1], optimum))
        if signum < 0:
            if not narrow_upper(bounds, variable, optimum, trail):  # { X =< Opt }
                return _FAIL, None
            return _WALK, continuation
        if signum > 0:
            return _FAIL, None
        if state.lower_strict:                              # meets lower
            return _FAIL, None
        return _solve_implied_value(optimum, form, continuation, bindings, trail)
    signum = sign(subtract(violated[1], optimum))           # clause 2
    if signum < 0:
        return _FAIL, None
    if signum == 0:
        if state.upper_strict:                              # meets upper
            return _FAIL, None
        return _solve_implied_value(optimum, form, continuation, bindings, trail)
    if not narrow_lower(bounds, variable, optimum, trail):  # { X >= Opt }
        return _FAIL, None
    return _WALK, continuation


def _solve_implied_value(optimum, form, continuation, bindings, trail):
    """The `meets` branch of reconsider_basis_list_optimum/5: solve
    X = Opt, or go on with the continuation where no variable is left."""
    form_1 = add_linear_forms(normalize_scalar(negate(optimum)), form)
    if form_1 is None:
        return _FAIL, None
    if not form_1.terms:                                    # would not callback
        return _WALK, continuation
    code, new_basis = solve_step(form_1.terms, form_1, form_1.constant,
                                 bindings, trail)
    if code == _SOLVE_FAILED:
        return _FAIL, None
    if code == _SOLVE_FINISHED:
        return _WALK, None
    return _WALK, new_basis


def reconsider_basis_list_applied(violated, variable, continuation, trail):
    """bv.pl, reconsider_basis_list_applied/5 (rcbl_app/5): the basis has
    changed; go on with the continuation if *variable* is within its bound
    now, otherwise take another step.  Returns (_WALK, Continuation),
    (_STATUS, Status) or (_FAIL, None)."""
    state = state_of(variable)
    if state is None or state.linear_form is None:
        return _FAIL, None
    form = state.linear_form
    value = add(form.rest, form.constant)
    if violated[0] == BELOW_LOWER_BOUND:
        if compare(value, violated[1]) > 0:                 # within bound now
            return _WALK, continuation
        status = increase_step(form.terms, trail)
    else:
        if compare(value, violated[1]) < 0:
            return _WALK, continuation
        status = decrease_step(form.terms, trail)
    if status is None:
        return _FAIL, None
    return _STATUS, status


def reconsider_basis_list_unlimited(violated, variable, continuation,
                                    independent_variable, dependent_bounds,
                                    trail):
    """bv.pl, reconsider_basis_list_unlimited/7 (rcbl_unl/7): exchange
    *variable* against the unlimited independent variable, at the violated
    bound."""
    if violated[0] == BELOW_LOWER_BOUND:
        bounds = bounds_lower_active(violated[1])
    else:
        bounds = bounds_upper_active(violated[1])
    if not pivot_exchange(variable, independent_variable, bounds,
                          dependent_bounds, trail):
        return _FAIL, None
    return _WALK, continuation


def narrow_upper(bounds, variable, upper, trail):
    """bv.pl, narrow_upper/3 (narrow_u/3).  False for other types."""
    if bounds.kind == BOUNDS_UPPER:
        _put_attributes(variable, trail, bounds=bounds_upper(upper))
        return True
    if bounds.kind == BOUNDS_LOWER_UPPER:
        _put_attributes(variable, trail,
                        bounds=bounds_lower_upper(bounds.lower, upper))
        return True
    return False


def narrow_lower(bounds, variable, lower, trail):
    """bv.pl, narrow_lower/3 (narrow_l/3).  False for other types."""
    if bounds.kind == BOUNDS_LOWER:
        _put_attributes(variable, trail, bounds=bounds_lower(lower))
        return True
    if bounds.kind == BOUNDS_LOWER_UPPER:
        _put_attributes(variable, trail,
                        bounds=bounds_lower_upper(lower, bounds.upper))
        return True
    return False


# ----------------------------------- dump -------------------------------------
#
# The DCG rules return the list of constraint terms they produce, or None
# where they fail.  A term is a tuple (operator, left, right) as
# linear_forms.normal_form_to_sum writes its cells; bounds and values are
# engine numbers (to_number), never rational pairs
# (test_dump_variable_and_dump_disequation_write_engine_numbers).

def dump_variable(bounds, variable, constant, homogeneous):
    """bv.pl, dump_variable//4 (dump_var//4)."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        if len(homogeneous) == 1 and deref(homogeneous[0][0]) is deref(variable) \
                and is_zero(constant) and compare(homogeneous[0][1], ONE) == 0:
            return []                                       # indep var
        return [("=", variable, normal_form_to_sum(homogeneous, constant))]
    if kind == BOUNDS_LOWER_ACTIVE or kind == BOUNDS_LOWER:
        return _dump_lower(bounds.lower, variable, constant, homogeneous)
    if kind == BOUNDS_UPPER_ACTIVE or kind == BOUNDS_UPPER:
        return _dump_upper(bounds.upper, variable, constant, homogeneous)
    if kind == BOUNDS_LOWER_ACTIVE_UPPER or kind == BOUNDS_LOWER_UPPER_ACTIVE \
            or kind == BOUNDS_LOWER_UPPER:
        lower = _dump_lower(bounds.lower, variable, constant, homogeneous)
        if lower is None:
            return None
        upper = _dump_upper(bounds.upper, variable, constant, homogeneous)
        if upper is None:
            return None
        return lower + upper
    return [("+", (":", variable, (":", bounds, constant)), homogeneous)]


def _dump_lower(lower, variable, constant, homogeneous):
    """dump_variable//4's clause for t_l(L)."""
    if not homogeneous:                                     # avoid 1 >= 0
        return None
    coefficient = homogeneous[0][1]
    state = state_of(variable)
    if state is None:
        return None
    strict = 0b10 if state.lower_strict else 0              # Strict /\ 0b10
    reciprocal = divide(ONE, coefficient)
    bound = to_number(multiply(reciprocal, subtract(lower, constant)))
    total = normal_form_to_sum(multiply_homogeneous_part(homogeneous, reciprocal),
                               ZERO)
    if sign(coefficient) > 0:
        result = dump_strict(strict, (">=", total, bound), (">", total, bound))
    else:
        result = dump_strict(strict, ("=<", total, bound), ("<", total, bound))
    if result is None:
        return None
    return [result]


def _dump_upper(upper, variable, constant, homogeneous):
    """dump_variable//4's clause for t_u(U)."""
    if not homogeneous:                                     # avoid 0 =< 1
        return None
    coefficient = homogeneous[0][1]
    state = state_of(variable)
    if state is None:
        return None
    strict = 0b01 if state.upper_strict else 0              # Strict /\ 0b01
    reciprocal = divide(ONE, coefficient)
    bound = to_number(multiply(reciprocal, subtract(upper, constant)))
    total = normal_form_to_sum(multiply_homogeneous_part(homogeneous, reciprocal),
                               ZERO)
    if sign(coefficient) > 0:
        result = dump_strict(strict, ("=<", total, bound), ("<", total, bound))
    else:
        result = dump_strict(strict, (">=", total, bound), (">", total, bound))
    if result is None:
        return None
    return [result]


def dump_strict(strict, nonstrict_result, strict_result):
    """bv.pl, dump_strict/4: 0 gives the non-strict form, 1 or 2 the strict
    one; anything else fails (None)."""
    if strict == 0:
        return nonstrict_result
    if strict == 1 or strict == 2:
        return strict_result
    return None


def dump_disequation(variable, homogeneous, constant):
    """bv.pl, dump_disequation//3 (dump_nz//3)."""
    if not homogeneous:
        return None
    reciprocal = divide(ONE, homogeneous[0][1])
    value = to_number(multiply(negate(reciprocal), constant))
    total = normal_form_to_sum(multiply_homogeneous_part(homogeneous, reciprocal),
                               ZERO)
    return [("=\\=", total, value)]


# itf3.pl's hook for CLPQ_KEY, registered at import (ruling R1).  Every
# module of the port imports this one, so the hook is in place before any
# variable gets a state.
from clausal.logic.clpq import attribute_hooks  # noqa: E402,F401  cyclic: itf3.pl
