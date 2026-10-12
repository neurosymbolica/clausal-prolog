# Ported from clp(q,r) version 1.3.3, file itf3.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""The unification hook and the attribute interface: itf3.pl.

`holzbaur_hook` is the CLPQ_KEY hook, registered at import whatever
CLAUSAL_CLPQ says (ruling R1).  It is itf3.pl's verify_attributes/3 with
geler.pl's (delayed_goals.verify_delayed) for the same variable; class.pl's
is the COMPONENT_KEY hook in components.py.

1.3.3's verify_attributes/3 runs before X is bound.  The engine calls the
hook after the binding, with X's state and what X is bound to, never X
itself (DEVIATIONS.md D3).  So the hook:

- takes X out of the store before anything reads it: X, and every other
  constrained variable the same unification bound, is replaced in the
  member lists, the basis and the rows by a fresh unbound stand-in that
  carries its state.  The stand-in is X as verify_attributes/3 sees it, so
  the rest is itf3.pl's code on an unbound variable
  (test_one_unification_binding_two_constrained_variables);
- never writes to X: put_attr on a variable bound to another would write
  that one's attributes (test_the_state_on_the_bound_variable_is_left_alone);
- binds what solve/5 implies one binding at a time from a work list, each
  checked before it is made, so a cascade does not nest
  (test_implied_bindings_are_queued_not_nested);
- puts the Later goals on the trail's pending queue.  Every unification
  owns that queue while it binds and runs the hooks (`trail.defer`), so
  they run after every hook of the unification, at the next goal boundary
  under a driver and before a bare unify returns otherwise
  (test_later_work_goes_on_the_pending_queue_under_a_driver,
  test_a_cascade_of_delayed_goals_needs_no_recursion,
  test_one_unification_bare_one_at_a_time_and_under_a_driver_agree).

bv.pl's export_binding/1 (bounded_simplex.export_bindings) binds through
the same work list.

itf3.pl's goal expansions (nf_ordering/3, decompose/4) are
variable_ordering.compare_variable_order and the LinearForm fields.
"""
from clausal.logic.clpq.arithmetic import (
    compare, from_number, is_zero, to_number)
from clausal.logic.clpq.attributes import (
    BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE, BOUNDS_NONE, BOUNDS_UPPER,
    BOUNDS_UPPER_ACTIVE, CLPQ_KEY, LaterWork, SolverState, bounds_none,
    put_state, state_of, strictness, with_changes)
from clausal.logic.clpq.bounded_simplex import (
    dereference, detach_bounds, dump_disequation, dump_variable,
    solve_for_variable_homogeneous, solve_homogeneous)
from clausal.logic.clpq.components import (
    COMPONENT_KEY, ComponentRecord, ListCell, component_all_variables,
    component_drop, list_elements)
from clausal.logic.clpq.delayed_goals import verify_delayed
from clausal.logic.clpq.linear_forms import (
    LinearForm, independent, normal_form_coefficient_of)
from clausal.logic.exceptions import LogicException, system_error, type_error
from clausal.logic.pending import run_first
from clausal.logic.variables import (
    AttVar, PlainVar, deref, get_attr, is_var, put_attr, register_attr_hook,
    unify)

#: The value of solver_type/2 for this solver.
SOLVER_TYPE = "rational"


# ---------------------------------------------------------------- the hook

def holzbaur_hook(state, other, trail):
    """The CLPQ_KEY hook: itf3.pl's and geler.pl's verify_attributes/3 for a
    variable whose *state* is handed in, now bound to *other*; then the
    Later goals."""
    later = LaterWork()
    if not verify_attributes(state, other, trail, later):
        return False
    return run_later(later, trail)


register_attr_hook(CLPQ_KEY, holzbaur_hook)


class PendingLater:
    """A LaterWork queue as a goal on the trail's pending queue: a
    zero-argument factory with one answer or none.  It keeps the work as a
    tuple and runs a fresh queue of it on every call, because the engine's
    drain calls the factory again when an earlier queued goal gives another
    answer (test_later_work_survives_a_retry_under_a_driver)."""
    __slots__ = ("work",)

    def __init__(self, later):
        self.work = tuple(later.queue)

    def __call__(self):
        later = LaterWork()
        later.queue.extend(self.work)
        if later.drain():
            return (None,)
        return ()


def run_later(later, trail):
    """Run the Later goals after every hook of the unification: they go on
    the trail's pending queue.  Inside a unification or under a driver
    (`trail.defer`) the engine runs that queue after the last hook.  Called
    with no unification and no driver (bind_all from a bare post), it owns
    the queue as a bare unify does and runs it to its first answer, so a
    cascade of delayed goals runs in the engine's one drain loop
    (test_a_cascade_of_delayed_goals_needs_no_recursion)."""
    if not later.queue:
        return True
    trail.push_pending(PendingLater(later))
    if trail.defer:
        return True
    trail.defer = True
    try:
        return run_first(trail)
    finally:
        trail.defer = False


def verify_attributes(state, other, trail, later):
    """itf3.pl, verify_attributes/3, with geler.pl's verify_attributes/3.
    X is bound already; *state* is its state and *other* is Y."""
    other = deref(other)
    if type(other) is PlainVar and not _carries_nothing(state):
        # Y cannot carry X's attributes (put_atts would fail on it): a
        # limit of the engine's variable kind, not a fault of the program's
        # term, so system_error, before any trailed change
        # (test_a_plain_var_cannot_take_the_constraint).
        raise LogicException(system_error(
            "plain_variable", "=/2: a constrained variable met a variable "
            "that cannot carry attributes (PlainVar)"))
    if state.forward is not None:                               # clause 2
        # Only bind_queued sets forward on a variable it then binds, after
        # verify_bound has run geler.pl's part for it.
        return forward_dereference(state.forward, other, trail)
    if _without_solver_attributes(state):                       # clause 1
        return verify_delayed(state, other, trail, later)
    numbers_only(other, None)                                   # clause 3
    bindings = []
    if state.component is None or state.linear_form is None:
        # X has no linear form in a component: nothing to stand in for.
        if not verify_bound(None, state, other, trail, later, bindings):
            return False
        return bind_queued(bindings, trail, later)
    components = [deref(state.component)]
    other_component = _component_of(other)
    if other_component is not None:
        components.append(other_component)
    stand_ins = _stand_in_for_bound_members(components, state, trail)
    if stand_ins is None:
        return True             # an earlier hook of this unification did it
    if not _verify_stand_ins(stand_ins, trail, later, bindings):
        return False
    return bind_queued(bindings, trail, later)


def _carries_nothing(state):
    """*state* holds no attribute a binding would move: clause 1 with no
    delayed goals."""
    return _without_solver_attributes(state) and not state.delayed_goals


def _verify_stand_ins(stand_ins, trail, later, bindings):
    """Clause 3 for each bound member, on its stand-in."""
    for stand_in, member_state, member in stand_ins:
        value = deref(member)
        put_state(stand_in, with_changes(state_of(stand_in), forward=value),
                  trail)                                        # put_atts(X, forward(Y))
        if not verify_bound(stand_in, member_state, value, trail, later,
                            bindings):
            return False
    return True


def _component_of(value):
    """The component of *value*, dereferenced, or None."""
    if type(value) is not AttVar or not is_var(value):
        return None
    value_state = state_of(value)
    if value_state is None or value_state.component is None:
        return None
    return deref(value_state.component)


def _without_solver_attributes(state):
    """get_atts(X, [-component(_), -variable_order(_), -linear_form(_),
    -forward(_), -type(_), -strictness(_), -nonzero]).  Strictness 0 counts
    as absent: the port cannot tell the two apart."""
    return (state.component is None and state.variable_order is None
            and state.linear_form is None and state.forward is None
            and state.bounds is None and not state.lower_strict
            and not state.upper_strict and not state.nonzero)


def verify_bound(variable, state, value, trail, later, bindings):
    """itf3.pl, verify_attributes/3 clause 3 after put_atts(X, forward(Y)),
    and geler.pl's verify_attributes/3.  *variable* is the unbound variable
    that stands for X in the store (None where X has no linear form in a
    component), *state* X's own state, *value* Y.  Bindings solve/5 implies
    are appended to *bindings*."""
    numbers_only(value, variable)
    if not verify_nonzero(state, value, trail):
        return False
    if not verify_type(state, value, later, trail):
        return False
    if variable is not None and not verify_linear(variable, value, trail,
                                                  bindings):
        return False
    return verify_delayed(state, value, trail, later)


def bind_queued(bindings, trail, later):
    """bv.pl, export_binding/1, for bindings solve/5 implied: each one is
    checked by verify_attributes/3's clause 3 before it is made, so its hook
    finds `forward` and takes clause 2.  Bindings the checks imply join the
    end of the list (test_implied_bindings_are_queued_not_nested)."""
    i = 0
    while i < len(bindings):
        variable, value = bindings[i]
        i += 1
        number = to_number(value)
        variable = deref(variable)
        if not is_var(variable):
            if not unify(variable, number, trail):
                return False
            continue
        state = state_of(variable) if type(variable) is AttVar else None
        if state is None:
            if not unify(variable, number, trail):
                return False
            continue
        if state.forward is not None:                           # clause 2
            if not forward_dereference(state.forward, number, trail):
                return False
            continue
        put_state(variable, with_changes(state, forward=number), trail)
        if not verify_bound(variable, state, number, trail, later, bindings):
            return False
        if not unify(variable, number, trail):
            return False
    return True


def bind_all(bindings, trail):
    """bv.pl, export_binding/1 outside the hook: bind_queued, then the Later
    goals."""
    later = LaterWork()
    if not bind_queued(list(bindings), trail, later):
        return False
    return run_later(later, trail)


# ---------------------------------------------------------------- stand-ins

def _own_state(variable):
    """The CLPQ_KEY attribute *variable* itself carries, bound or not; None
    for none.  get_attr would read the variable it is bound to."""
    attributes = variable.attrs
    if not attributes:
        return None
    return attributes.get(CLPQ_KEY)


def _stand_in_for_bound_members(components, state, trail):
    """Replace every bound member of *components*, and of the components
    their values are in (transitively), by a fresh unbound stand-in, in the
    member lists, the bases and the rows.

    Returns [(stand_in, its state, the bound variable)], the member whose
    own state is *state* (X) first.  None where no bound member
    carries *state*: X is not a member any more, because the hook
    of another variable bound in the same unification has done X's work
    already."""
    unique = []
    seen = set()
    for component in components:
        if id(component) not in seen:
            seen.add(id(component))
            unique.append(component)
    components = unique
    bound = []
    found = False
    i = 0
    while i < len(components):
        component = components[i]
        i += 1
        for member in list_elements(component_all_variables(component)):
            if type(member) is not AttVar or not member.is_bound:
                continue
            member_state = _own_state(member)
            if member_state is None:
                continue
            if member_state is state:
                found = True
                bound.insert(0, (member, member_state))
            else:
                bound.append((member, member_state))
            reached = _component_of(deref(member))
            if reached is not None and id(reached) not in seen:
                seen.add(id(reached))
                components.append(reached)
    if not found:
        return None
    if not bound:
        return []
    for member, _ in bound:
        # numbers_only/2 before the first trailed change: the engine's undo
        # after a hook raises clears the exception (DEVIATIONS.md D3,
        # test_a_non_number_raises_a_type_error).
        numbers_only(deref(member), member)
    stand_ins = {}
    result = []
    for member, member_state in bound:
        stand_in = AttVar()
        stand_ins[id(member)] = stand_in
        result.append((stand_in, member_state, member))
    for stand_in, member_state, member in result:
        put_state(stand_in, with_changes(
            member_state, delayed_goals=None,
            linear_form=_rename_in_form(member_state.linear_form, stand_ins)),
            trail)
    for component in components:
        _rename_in_component(component, stand_ins, trail)
    return result


def _rename_in_form(form, stand_ins):
    """*form* with each variable that has a stand-in replaced by it, in
    place: the stand-in has the same variable_order, so the terms stay
    sorted."""
    if form is None:
        return None
    terms = form.terms
    renamed = None
    for i in range(len(terms)):
        stand_in = stand_ins.get(id(terms[i][0]))
        if stand_in is not None:
            if renamed is None:
                renamed = list(terms)
            renamed[i] = (stand_in, terms[i][1])
    if renamed is None:
        return form
    return LinearForm(form.constant, form.rest, renamed)


def _rename_in_list(items, stand_ins):
    """A member list or basis with each variable that has a stand-in
    replaced by it, in place; the tail is kept.  *items* itself where
    nothing changes."""
    elements = []
    node = deref(items)
    changed = False
    while type(node) is ListCell:
        element = node.head
        stand_in = stand_ins.get(id(element))
        if stand_in is not None:
            element = stand_in
            changed = True
        elements.append(element)
        node = deref(node.rest)
    if not changed:
        return items
    result = node
    i = len(elements) - 1
    while i >= 0:
        result = ListCell(elements[i], result)
        i -= 1
    return result


def _rename_in_component(component, stand_ins, trail):
    """The stand-ins in *component*'s member list, basis and rows."""
    record = get_attr(component, COMPONENT_KEY)
    members = _rename_in_list(record.members, stand_ins)
    basis = _rename_in_list(record.basis, stand_ins)
    if members is not record.members or basis is not record.basis:
        put_attr(component, COMPONENT_KEY,
                 ComponentRecord(members, record.tail, basis, record.priority),
                 trail)
    for member in list_elements(members):
        member = deref(member)
        if not is_var(member):
            continue
        member_state = state_of(member)
        if member_state is None or member_state.linear_form is None:
            continue
        form = _rename_in_form(member_state.linear_form, stand_ins)
        if form is not member_state.linear_form:
            put_state(member, with_changes(member_state, linear_form=form),
                      trail)


# ---------------------------------------------------------------- itf3.pl

def forward_dereference(forward, other, trail):
    """itf3.pl, forward_dereference/2 (fwd_deref/2): follow forward/1
    attributes from *forward*, then unify with *other*."""
    while True:
        forward = deref(forward)
        if not is_var(forward):                                 # clause 1
            return unify(forward, other, trail)
        state = state_of(forward) if type(forward) is AttVar else None
        if state is None or state.forward is None:              # clause 2
            return unify(forward, other, trail)
        forward = state.forward


def numbers_only(value, variable):
    """itf3.pl, numbers_only/2: Y is a variable or an exact number (an int,
    a Fraction or a finite Decimal, which arithmetic_normalize/2 gives
    back unchanged).  Anything else raises type_error(rational, Y), as
    illarg(type(rational), X=Y, 2) does (test_numbers_only)."""
    if is_var(value):
        return True
    try:
        from_number(value)
    except TypeError:
        raise LogicException(type_error(solver_type(), value, "=/2")) from None
    return True


def solver_type():
    """itf3.pl, solver_type/2 for clpq."""
    return SOLVER_TYPE


def verify_nonzero(state, value, trail):
    """itf3.pl, verify_nonzero/2.  A PlainVar Y cannot take `nonzero`; the
    port fails there rather than drop it."""
    if not state.nonzero:                                       # clause 2
        return True
    if is_var(value):                                           # clause 1
        if type(value) is PlainVar:
            return False
        value_state = state_of(value)
        if value_state is None:
            put_state(value, SolverState(nonzero=True), trail)
        else:
            put_state(value, with_changes(value_state, nonzero=True), trail)
        return True
    return not is_zero(from_number(value))                      # Y =\= 0


def verify_type(state, value, later, trail):
    """itf3.pl, verify_type//2 and verify_type//3: Later goals go on
    *later*.  False where a number is outside X's bounds."""
    bounds = state.bounds
    if bounds is None:                                          # clause 2
        return True
    strict = strictness(state)
    if is_var(value):
        verify_type_variable(bounds, value, strict, later, trail)
        return True
    return verify_type_nonvariable(bounds, from_number(value), strict)


def verify_type_nonvariable(bounds, value, strict):
    """itf3.pl, verify_type_nonvariable/3 (verify_type_nonvar/3) on a
    rational *value*."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        return True
    if kind == BOUNDS_LOWER or kind == BOUNDS_LOWER_ACTIVE:
        return lower_bound(strict, bounds.lower, value)
    if kind == BOUNDS_UPPER or kind == BOUNDS_UPPER_ACTIVE:
        return upper_bound(strict, bounds.upper, value)
    return (lower_bound(strict, bounds.lower, value)
            and upper_bound(strict, bounds.upper, value))


def lower_bound(strict, lower, value):
    """itf3.pl, lower_bound/3 (lb/3)."""
    if strict & 0b10 == 0:
        return compare(lower, value) <= 0
    return compare(lower, value) < 0


def upper_bound(strict, upper, value):
    """itf3.pl, upper_bound/3 (ub/3)."""
    if strict & 0b01 == 0:
        return compare(value, upper) <= 0
    return compare(value, upper) < 0


class PostBound:
    """A Later goal `{Left Relation Right}`."""
    __slots__ = ("relation", "left", "right", "trail")

    def __init__(self, relation, left, right, trail):
        self.relation = relation
        self.left = left
        self.right = right
        self.trail = trail

    def __call__(self):
        from clausal.logic.clpq.normal_form import (   # cyclic: nf.pl
            post_constraint)
        return post_constraint((self.relation, self.left, self.right),
                               self.trail)


def verify_type_variable(bounds, value, strict, later, trail):
    """itf3.pl, verify_type_variable//3 (verify_type_var//3): X's bounds as
    Later goals on Y (test_verify_type_variable_queues_the_bounds_as_later_goals)."""
    kind = bounds.kind
    if kind == BOUNDS_NONE:
        return
    if kind != BOUNDS_UPPER and kind != BOUNDS_UPPER_ACTIVE:
        later_lower_bound(strict, bounds.lower, value, later, trail)
    if kind != BOUNDS_LOWER and kind != BOUNDS_LOWER_ACTIVE:
        later_upper_bound(strict, bounds.upper, value, later, trail)


def later_lower_bound(strict, lower, value, later, trail):
    """itf3.pl, later_lower_bound//3 (llb//3)."""
    relation = "=<" if strict & 0b10 == 0 else "<"
    later.push(PostBound(relation, to_number(lower), value, trail))


def later_upper_bound(strict, upper, value, later, trail):
    """itf3.pl, later_upper_bound//3 (lub//3)."""
    relation = "=<" if strict & 0b01 == 0 else "<"
    later.push(PostBound(relation, value, to_number(upper), trail))


def verify_linear(variable, value, trail, bindings):
    """itf3.pl, verify_linear/2 (verify_lin/2) on the unbound *variable*
    that stands for X.  solve/5's bindings go on *bindings*."""
    state = state_of(variable)
    if state is None or state.component is None \
            or state.linear_form is None:                       # clause 2
        return True
    component = state.component
    if independent(state.linear_form, variable):
        if not detach_bounds(variable, trail):
            return False
        form = _difference_form(variable, value, trail)
        if form is None:
            return False
        if normal_form_coefficient_of(form, variable) is not None:
            if not component_drop(component, variable, trail):
                return False
            return solve_for_variable_homogeneous(
                form.terms, form, form.constant, variable, bindings, trail)
        # itf3.pl drops X here too, but X stays in a row and is then bound
        # to Y, a member.  The stand-in left in the row stays a member in
        # X's place, so dump/3 finds its bound (DEVIATIONS.md D3, "A
        # stand-in left in a row"; test_a_stand_in_left_in_a_row_is_a_member).
        return solve_homogeneous(form.terms, form, form.constant, bindings,
                                 trail)
    if not component_drop(component, variable, trail):
        return False
    form = _difference_form(variable, value, trail)
    if form is None:
        return False
    return solve_homogeneous(form.terms, form, form.constant, bindings, trail)


def _difference_form(variable, value, trail):
    """`nf(X-Y, Lin), dereference(Lin, Lind)`.  A PlainVar Y cannot become
    a linear variable; None there."""
    from clausal.logic.clpq.normal_form import normal_form    # cyclic: nf.pl
    if type(value) is PlainVar:
        return None
    norm = normal_form(("-", variable, value))
    if norm is None:
        return None
    return dereference(norm, trail)


# ---------------------------------------------------------------- answers

def attribute_goal(variable, context="toplevel"):
    """itf3.pl, attribute_goal/2: the residual goal of *variable*, `true`
    for none, or None where it fails.  presentation_context/2 is the
    parameter *context* (DEVIATIONS.md D14)."""
    linear = dump_linear(variable, context)
    if linear is None:
        return None
    nonzero = dump_nonzero(variable, context)
    if nonzero is None:
        return None
    return list_to_wrapped_conjunction(linear + nonzero)


def list_to_wrapped_conjunction(goals):
    """itf3.pl, list_to_wrapped_conjunction/2 (l2wrapped/2)."""
    if not goals:
        return "true"
    result = wrap(goals[-1])
    i = len(goals) - 2
    while i >= 0:
        result = (",", wrap(goals[i]), result)
        i -= 1
    return result


def wrap(constraint):
    """itf3.pl, wrap/2: `{C}`.  The port has no typein module, so never
    `clpq:{C}` (DEVIATIONS.md D14)."""
    return ("{}", constraint)


def dump_linear(variable, context):
    """itf3.pl, dump_linear//2: a list of goals, or None where it fails."""
    variable = deref(variable)
    state = state_of(variable) if is_var(variable) else None
    if state is None or state.linear_form is None \
            or state.bounds is None:                            # clause 2
        return []
    form = state.linear_form
    homogeneous = form.terms
    constant = form.constant
    none = state.bounds.kind == BOUNDS_NONE
    goals = []
    if not (none or not state.target):
        found = dump_variable_in_context(context, bounds_none(), variable,
                                         constant, homogeneous)
        if found is None:
            return None
        goals.extend(found)
    if not (none and not state.target):
        found = dump_variable_in_context(context, state.bounds, variable,
                                         constant, homogeneous)
        if found is None:
            return None
        goals.extend(found)
    return goals


def dump_variable_in_context(context, bounds, variable, constant, homogeneous):
    """itf3.pl, dump_variable_in_context//5 (dump_v//5)."""
    if context == "toplevel":
        return dump_variable(bounds, variable, constant, homogeneous)
    raise ValueError(f"no dump for the presentation context {context!r}"
                     " (DEVIATIONS.md D14)")


def dump_nonzero(variable, context):
    """itf3.pl, dump_nonzero//2: a list of goals, or None where it fails."""
    variable = deref(variable)
    state = state_of(variable) if is_var(variable) else None
    if state is None or not state.nonzero \
            or state.linear_form is None:                       # clause 2
        return []
    form = state.linear_form
    return dump_disequation_in_context(context, variable, form.terms,
                                       form.constant)


def dump_disequation_in_context(context, variable, homogeneous, constant):
    """itf3.pl, dump_disequation//4."""
    if context == "toplevel":
        return dump_disequation(variable, homogeneous, constant)
    raise ValueError(f"no dump for the presentation context {context!r}"
                     " (DEVIATIONS.md D14)")
