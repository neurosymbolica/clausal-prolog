# Ported from clp(q,r) version 1.3.3, file dump.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""dump/3 and the residual constraints of an answer: dump.pl.

Every predicate of dump.pl is a function here, in file order, named by
NAMES.md, then the toplevel's own projection (toplevel_goals: project.pl's
project_attributes/2 and the attribute_goal/2 hooks of itf3.pl and geler.pl,
called as the SICStus toplevel calls them), then toplevel_strings, the
`-g` printer's text (`{X + Y = 3}`), and residual_strings, a dump/3 in the
same text.

findall/3.  dump/3 runs vars_constraints/2 inside findall/3, so the
projection, which is destructive, is undone and the answer is a copy.  The
port takes a trail mark, projects, copies the goals, and undoes to the
mark (test_dump_leaves_the_store_as_it_was).  In the copy each target
variable is replaced by its name, and every other variable by a fresh one.

A constraint goal is a compound cell (`("=<", Sum, Bound)`), with engine
numbers (int or Fraction) for the rationals
(test_dump_emits_engine_numbers_never_rational_pairs).
"""
from clausal.logic.clpq.attributes import refuse_inside_attribute_hooks
from clausal.logic.clpq.attribute_hooks import dump_linear, dump_nonzero
from clausal.logic.clpq.attributes import state_of
from clausal.logic.clpq.components import ListCell, component_all_variables
from clausal.logic.clpq.delayed_goals import _term_variables, collect_nonlinear
from clausal.logic.clpq.normal_form import SOLVER_MODULE
from clausal.logic.clpq.projection import project_attributes
from clausal.logic.clpq.variable_ordering import ordering
from clausal.logic.exceptions import LogicException, _error, system_error
from clausal.logic.variables import PlainVar, Var, deref, is_var, unify
from decimal import Decimal
from fractions import Fraction
from functools import cmp_to_key


# dump( +Target, ?NewVars, ?CodedAnswer)
#
# where Target and NewVars are lists of variables of equal length and
# CodedAnswer is the term representation of the projection of constraints
# onto the target variables where the target variables are replaced by
# the corresponding variables from NewVars.

def dump(target_variables, names, trail):
    """dump.pl, dump/3: the constraints on *target_variables* projected
    onto them, each target replaced by the element of *names* at its
    position; None where dump/3 fails.  An element of *target_variables*
    that is not an unbound variable raises uninstantiation_error, as
    must_be(Target, proper_list(var), ...) does.

    The projection runs with `trail.defer` off and restores it after, as a
    bare call does, so its trial posts run what they wake inside the trial
    (DEVIATIONS.md D3; test_dump_under_a_driver_matches_a_bare_dump).  It
    takes the queue it was entered with first, so a trial runs only what
    it wakes itself; the undo puts the queue back
    (test_work_queued_before_dump_stays_queued)."""
    refuse_inside_attribute_hooks(
        trail, ("dump", target_variables, names, Var()), "dump", 3)
    targets = _unbound_targets(target_variables)
    if len(names) != len(targets):
        return None
    saved_defer = trail.defer
    trail.defer = False
    try:
        mark = trail.mark()
        try:
            trail.take_pending()        # the outer queue, back at the undo
            goals = variables_constraints(targets, trail)
            if goals is None:
                return None
            renaming = {}
            positions = []
            for index in range(len(targets)):
                identity = targets[index]._id
                if identity in renaming:
                    positions.append((renaming[identity], names[index]))
                else:
                    renaming[identity] = names[index]
            copied = _copy_terms(goals, renaming)
        finally:
            trail.undo(mark)
    finally:
        trail.defer = saved_defer
    for first, other in positions:          # findall's [NewVars-Constraints]
        if not unify(first, other, trail):
            return None
    return copied


def _unbound_targets(target_variables):
    """must_be(Target, proper_list(var), dump(...), 1): the dereferenced
    targets; a bound one raises uninstantiation_error."""
    targets = []
    for variable in target_variables:
        variable = deref(variable)
        if not is_var(variable):
            raise LogicException(_error(("uninstantiation_error", variable),
                                        "dump/3"))
        targets.append(variable)
    return targets


def projecting_assert(clause, trail):
    """dump.pl, projecting_assert/1: the clause to assert for *clause* (a
    cell, `(":-", H, B)` for a rule), with the projection of the
    constraints on its variables as a first goal `clpq:{Conj}`.  The port
    returns the clause and its caller asserts it (DEVIATIONS.md D15).
    Where the projection fails or is empty, the clause itself ("not our
    business")."""
    refuse_inside_attribute_hooks(
        trail, ("projecting_assert", clause), "projecting_assert", 1)
    target = _term_variables([clause])
    saved_defer = trail.defer
    trail.defer = False
    try:
        mark = trail.mark()
        try:
            trail.take_pending()        # the outer queue, back at the undo
            goals = variables_constraints(target, trail)
            if goals is None:
                return clause
            renaming = {}
            copy = _copy_terms([clause] + goals, renaming)
        finally:
            trail.undo(mark)
    finally:
        trail.defer = saved_defer
    conjunction = nonempty_list_to_conjunction(copy[1:])      # fails for []
    if conjunction is None:
        return clause
    constraint = (":", SOLVER_MODULE, ("{}", conjunction))  # proper module for {}/1
    copied_clause = copy[0]
    if type(copied_clause) is tuple and len(copied_clause) == 3 \
            and copied_clause[0] == ":-":                       # former rule
        return (":-", copied_clause[1], (",", constraint, copied_clause[2]))
    return (":-", copied_clause, constraint)                    # former fact


def variables_constraints(target, trail):
    """dump.pl, variables_constraints/2 (vars_constraints/2): the goals of
    the projection onto *target*: the linear ones of every related
    variable, then the non-linear ones.  Destructive; None where it
    fails."""
    if not ordering(list(target), trail):
        return None
    related = related_linear_variables(target)
    if related is None:
        return None
    nonlinear = nonlinear_crux(related, trail)
    if nonlinear is None:
        return None
    if not project_attributes(target, related, trail):
        return None
    again = related_linear_variables(target)    # project drops/adds vars
    if again is None:
        return None
    goals = all_attribute_goals(again)
    if goals is None:
        return None
    return goals + nonlinear


def nonempty_list_to_conjunction(items):
    """dump.pl, nonempty_list_to_conjunction/2 (l2c/2): `(X1, (X2, ...))`;
    None for `[]`.  The recursion is a loop from the end."""
    if not items:
        return None
    conjunction = items[-1]
    index = len(items) - 2
    while index >= 0:
        conjunction = (",", items[index], conjunction)
        index -= 1
    return conjunction


def related_linear_variables(variables):
    """dump.pl, related_linear_variables/2 (related_linear_vars/2): the
    unbound members of the components of *variables*, component by
    component in the standard order of the components; None where
    copy_variables//1 fails."""
    return related_linear_system_variables(related_linear_systems(variables))


def related_linear_systems(variables):
    """dump.pl, related_linear_systems/3 (related_linear_sys/3): the
    components of *variables*, each once, in the standard order (an
    assoc's keys); two component variables are in creation order
    (DEVIATIONS.md D4)."""
    found = {}
    for variable in variables:
        variable = deref(variable)
        state = state_of(variable) if is_var(variable) else None
        if state is None or state.component is None:
            continue
        component = deref(state.component)
        found[component._id] = component
    keys = sorted(found)
    result = []
    for key in keys:
        result.append(found[key])
    return result


def related_linear_system_variables(component_list):
    """dump.pl, related_linear_variables//1 (related_linear_vars//1)."""
    result = []
    for component in component_list:
        members = copy_variables(component_all_variables(component))
        if members is None:
            return None
        result.extend(members)
    return result


def copy_variables(items):
    """dump.pl, copy_variables//1 (cpvars//1): the unbound elements of an
    open list, up to its tail; None for a closed list, which has no
    clause."""
    result = []
    node = deref(items)
    while type(node) is ListCell:
        element = deref(node.head)
        if is_var(element):
            result.append(element)
        node = deref(node.rest)
    if not is_var(node):
        return None
    return result


def nonlinear_crux(variables, trail):
    """dump.pl, nonlinear_crux/2 (nonlin_crux/2): the delayed goals of
    *variables*, translated (geler.pl collect_nonlinear//1, which marks
    each one run: destructive) and stripped of the solver's module; None
    where nonlinear_strip/3 fails."""
    goals = collect_nonlinear(variables, trail)
    return nonlinear_strip(goals, SOLVER_MODULE)


def nonlinear_strip(goals, solver):
    """dump.pl, nonlinear_strip/3 (nonlin_strip/3): `M:{G}` becomes G and
    `M:What` What when M is *solver*; a goal of another module is dropped.
    None for a goal that is not `M:What`, which has no clause."""
    result = []
    for goal in goals:
        goal = deref(goal)
        if not (type(goal) is tuple and len(goal) == 3 and goal[0] == ":"):
            return None
        module = deref(goal[1])
        what = deref(goal[2])
        if type(module) is str and module == solver:
            if type(what) is tuple and len(what) == 2 and what[0] == "{}":
                result.append(what[1])
            else:
                result.append(what)
    return result


def all_attribute_goals(variables):
    """dump.pl, all_attribute_goals//1: itf3.pl's dump_linear//2 and
    dump_nonzero//2 for each variable, in the toplevel context; None where
    one fails."""
    result = []
    for variable in variables:
        linear = dump_linear(variable, "toplevel")
        if linear is None:
            return None
        result.extend(linear)
        nonzero = dump_nonzero(variable, "toplevel")
        if nonzero is None:
            return None
        result.extend(nonzero)
    return result


# ---------------------------------------------------------------- the toplevel
#
# The SICStus 3 toplevel answers a query that leaves attributed variables
# through two hooks of each module that has attributes (the atts protocol,
# not 1.3.3 text): Module:project_attributes(QueryVars, AttrVars), then
# Module:attribute_goal(V, Goal) for each attributed variable, in a failure
# loop that undoes the projection.  clp(Q,R) 1.3.3's project_attributes/2
# is project.pl's ("interface predicate"); its attribute_goal/2 is
# itf3.pl's (dump_linear//2, dump_nonzero//2 in the toplevel context) and
# geler.pl's (the delayed goals, and the `all_nonlinear/1` goals
# project_nonlinear/3 collected).  Unlike dump/3 the toplevel calls no
# ordering/1 on the query variables, so the order the query names them in
# imposes no variable ordering (DEVIATIONS.md D26).

def toplevel_goals(query_variables, trail, attributed=()):
    """The goals the toplevel shows for *query_variables*: the projection
    of the store onto them (project.pl project_attributes/2), then for each
    related variable itf3.pl's attribute_goal/2 (dump_linear//2,
    dump_nonzero//2, toplevel context), then geler.pl's attribute_goal/2
    on the sorted `all_nonlinear/1` goals.  Copied as dump/3 copies, each
    query variable standing for itself; the store is left as it was.  None
    where the projection fails.

    AttrVars, which the SICStus toplevel gathers itself, is the variables
    with CLP(Q) state reachable from the query variables and from
    *attributed* (the caller's attributed variables of the query that no
    query variable reaches: the `-g` printer's call_residue_vars/2), see
    attributed_variables.  The goals are shown for the members of their
    components after the projection, component by component as dump.pl's
    related_linear_vars/2 lists them (DEVIATIONS.md D26).  Runs with
    `trail.defer` off, each trial post running what it wakes, as dump/3
    does (D3)."""
    refuse_inside_attribute_hooks(
        trail, ("toplevel_goals", query_variables), "toplevel_goals", 1)
    targets = _unbound_targets(query_variables)
    saved_defer = trail.defer
    trail.defer = False
    try:
        mark = trail.mark()
        try:
            trail.take_pending()        # the outer queue, back at the undo
            roots = targets + list(attributed)
            all_nonlinear = []
            if not project_attributes(targets, attributed_variables(roots),
                                      trail, all_nonlinear):
                return None
            shown = related_linear_variables(attributed_variables(roots))
            if shown is None:
                return None
            goals = all_attribute_goals(shown)
            if goals is None:
                return None
            # geler.pl's attribute_goal/2, second clause: the goals of
            # all_nonlinear(Ls), Ls = sort(L).  Its first clause shows the
            # goals still not run on a variable: project_nonlinear/3 ran
            # every goal of AttrVars, so there are none.
            nonlinear = nonlinear_strip(sort_goals(all_nonlinear),
                                        SOLVER_MODULE)
            if nonlinear is None:
                return None
            renaming = {}
            for variable in targets:
                renaming.setdefault(variable._id, variable)
            copied = _copy_terms(goals + nonlinear, renaming)
        finally:
            trail.undo(mark)
    finally:
        trail.defer = saved_defer
    return copied


def attributed_variables(variables):
    """The variables with CLP(Q) state reachable from *variables* through
    their attributes: a component's members, the variables of a linear form
    and of the delayed goals, transitively; in creation order (the sort/2
    of project_attributes/2, DEVIATIONS.md D4).  An explicit stack."""
    seen = set()
    found = []
    stack = list(variables)
    while stack:
        variable = deref(stack.pop())
        if not is_var(variable) or variable._id in seen:
            continue
        seen.add(variable._id)
        state = state_of(variable)
        if state is None:
            continue
        found.append(variable)
        if state.component is not None:
            members = component_all_variables(deref(state.component))
            if members is not None:
                node = deref(members)
                while type(node) is ListCell:
                    stack.append(node.head)
                    node = deref(node.rest)
        if state.linear_form is not None:
            stack.extend(_term_variables([state.linear_form]))
        if state.delayed_goals is not None:
            stack.extend(_term_variables([state.delayed_goals]))
    found.sort(key=_creation)
    return found


def _creation(variable):
    return variable._id


def sort_goals(goals):
    """sort/2 on goal terms: the standard order of terms, two unbound
    variables in creation order (DEVIATIONS.md D4), identical goals once."""
    keyed = sorted(goals, key=cmp_to_key(compare_terms))
    result = []
    for goal in keyed:
        if not result or compare_terms(result[-1], goal) != 0:
            result.append(goal)
    return result


_ORDER_VARIABLE, _ORDER_NUMBER, _ORDER_ATOM, _ORDER_COMPOUND = 0, 1, 3, 4


def _order_class(term):
    if is_var(term):
        return _ORDER_VARIABLE
    kind = type(term)
    if kind is int or kind is Fraction or kind is float:
        return _ORDER_NUMBER
    if kind is str:
        return _ORDER_ATOM
    return _ORDER_COMPOUND


def _compound_parts(term):
    """(name, arguments) of a compound: a cell `(Name, Args...)`, or a
    non-empty list as '.'(Head, Tail)."""
    if type(term) is list:
        return ".", (term[0], term[1:] if len(term) > 1 else "[]")
    return term[0], term[1:]


def compare_terms(first, second):
    """compare/3 on two goal terms: -1, 0 or 1.  Variables (creation
    order) before numbers (by value) before atoms (by text) before
    compounds (arity, name, then arguments left to right).  A work stack,
    no recursion."""
    work = [(first, second)]
    while work:
        first, second = work.pop()
        first, second = deref(first), deref(second)
        if first is second:
            continue
        if type(first) is list and not first:
            first = "[]"
        if type(second) is list and not second:
            second = "[]"
        class_a, class_b = _order_class(first), _order_class(second)
        if class_a != class_b:
            return -1 if class_a < class_b else 1
        if class_a == _ORDER_VARIABLE:
            if first._id != second._id:
                return -1 if first._id < second._id else 1
        elif class_a == _ORDER_NUMBER or class_a == _ORDER_ATOM:
            if first != second:
                return -1 if first < second else 1
        else:
            name_a, arguments_a = _compound_parts(first)
            name_b, arguments_b = _compound_parts(second)
            if len(arguments_a) != len(arguments_b):
                return -1 if len(arguments_a) < len(arguments_b) else 1
            if name_a != name_b:
                return -1 if str(name_a) < str(name_b) else 1
            for index in range(len(arguments_a) - 1, -1, -1):
                work.append((arguments_a[index], arguments_b[index]))
    return 0


# ---------------------------------------------------------------- the copy

def _copy_terms(terms, renaming):
    """findall/3's copy of *terms*: a variable whose `_id` is in *renaming*
    becomes its entry; any other variable a fresh one, the same one for
    each occurrence (entered in *renaming*).  An explicit stack, not
    recursion (test_a_dump_of_a_long_sum_needs_no_recursion)."""
    result = []
    for term in terms:
        result.append(_copy_term(term, renaming))
    return result


def _copy_term(term, renaming):
    term = deref(term)
    if type(term) is not tuple and type(term) is not list:
        return _copy_leaf(term, renaming)
    stack = [(term, [])]
    while True:
        node, done = stack[-1]
        if len(done) < len(node):
            child = deref(node[len(done)])
            if type(child) is tuple or type(child) is list:
                stack.append((child, []))
            else:
                done.append(_copy_leaf(child, renaming))
            continue
        stack.pop()
        copied = tuple(done) if type(node) is tuple else done
        if not stack:
            return copied
        stack[-1][1].append(copied)


def _copy_leaf(term, renaming):
    if is_var(term):
        identity = term._id
        copy = renaming.get(identity)
        if copy is None:
            copy = Var()
            renaming[identity] = copy
        return copy
    return term


# ---------------------------------------------------------------- residual_strings

_RELATIONS = frozenset(("=", "<", "=<", ">", ">=", "=\\=", "=:="))

# Prolog's operator table for what a residual holds: (priority, type).
_INFIX = {"+": (500, "yfx"), "-": (500, "yfx"), "*": (400, "yfx"),
          "/": (400, "yfx"), "^": (200, "xfy"), ":": (200, "xfy"),
          ",": (1000, "xfy"), "=": (700, "xfx"), "<": (700, "xfx"),
          "=<": (700, "xfx"), ">": (700, "xfx"), ">=": (700, "xfx"),
          "=\\=": (700, "xfx"), "=:=": (700, "xfx")}
_SPACED = frozenset(("+", "-", ",", "=", "<", "=<", ">", ">=", "=\\=", "=:="))


def residual_strings(target_variables, trail, name_of):
    """The residual constraints on *target_variables* as the `-g` printer
    shows them: one string per goal of dump/3, a constraint in braces
    (`{X + Y = 3}`, `{X < 3}`), strictness kept; variables named by
    *name_of*.  A bound element, a duplicate and a PlainVar (which cannot
    carry constraints) are left out of the targets.  Without any CLP(Q)
    state on the targets the answer is [] at once, which is what dump/3
    gives there (test_residual_strings_without_a_store_is_empty).  Raises
    system_error(clpq_dump_failed) where dump/3 fails, so an answer's
    constraints are never dropped in silence
    (test_a_failing_dump_raises_a_system_error)."""
    targets = []
    seen = set()
    stateful = False
    for variable in target_variables:
        variable = deref(variable)
        if not is_var(variable) or type(variable) is PlainVar:
            continue
        if variable._id in seen:
            continue
        seen.add(variable._id)
        targets.append(variable)
        if state_of(variable) is not None:
            stateful = True
    if not stateful:
        return []
    goals = dump(targets, targets, trail)
    if goals is None:
        raise LogicException(system_error(
            "clpq_dump_failed", "dump/3: dump/3 failed on a store that holds"))
    return goal_strings(goals, name_of)


def toplevel_strings(query_variables, trail, name_of, attributed=()):
    """The `-g` printer's residual constraints on *query_variables* (and
    the constraints of *attributed* the projection keeps, see
    toplevel_goals): toplevel_goals's goals in residual_strings's text.
    The targets are chosen as residual_strings chooses them, and without
    any CLP(Q) state on them or on *attributed* the answer is [] at once.  Raises
    system_error(clpq_projection_failed) where the projection fails, so an
    answer's constraints are never dropped in silence
    (test_a_failing_projection_raises_a_system_error)."""
    targets = []
    seen = set()
    stateful = False
    for variable in query_variables:
        variable = deref(variable)
        if not is_var(variable) or type(variable) is PlainVar:
            continue
        if variable._id in seen:
            continue
        seen.add(variable._id)
        targets.append(variable)
        if state_of(variable) is not None:
            stateful = True
    others = []
    for variable in attributed:
        variable = deref(variable)
        if is_var(variable) and state_of(variable) is not None:
            others.append(variable)
            stateful = True
    if not stateful:
        return []
    goals = toplevel_goals(targets, trail, others)
    if goals is None:
        raise LogicException(system_error(
            "clpq_projection_failed",
            "project_attributes/2: the projection failed on a store that holds"))
    return goal_strings(goals, name_of)


def goal_strings(goals, name_of):
    """Each goal as format_term writes it, a constraint in braces."""
    result = []
    for goal in goals:
        text = format_term(goal, name_of)
        if type(goal) is tuple and len(goal) == 3 and goal[0] in _RELATIONS:
            text = "{" + text + "}"
        result.append(text)
    return result


def format_term(term, name_of):
    """*term* as Prolog text with spaces around `+`, `-`, `,` and the
    relations, rationals as `N/D`, and parentheses only where priorities
    need them.  An explicit stack (test_a_dump_of_a_long_sum_needs_no_recursion)."""
    pieces = []
    stack = [(term, 1200, False)]
    while stack:
        item = stack.pop()
        if type(item) is str:
            pieces.append(item)
            continue
        node, limit, tight = item
        node = deref(node)
        if is_var(node):
            pieces.append(name_of(node))
            continue
        kind = type(node)
        if kind is int or kind is Fraction:
            text = _number_text(node)
            priority = 400 if kind is Fraction and node.denominator != 1 else 0
            if priority > limit or (tight and node < 0):
                text = "(" + text + ")"
            pieces.append(text)
            continue
        if kind is list:        # bb.pl's goal holds Is (test_a_delayed_bb_inf_shows_in_the_residual)
            stack.append("]")
            index = len(node) - 1
            while index >= 0:
                stack.append((node[index], 999, False))
                if index > 0:
                    stack.append(", ")
                index -= 1
            stack.append("[")
            continue
        if kind is not tuple or not node or type(node[0]) is not str:
            pieces.append(str(node))
            continue
        functor = node[0]
        if len(node) == 3 and functor in _INFIX:
            priority, operator_type = _INFIX[functor]
            left_limit = priority if operator_type == "yfx" else priority - 1
            right_limit = priority if operator_type == "xfy" else priority - 1
            spaced = functor in _SPACED
            operator = " " + functor + " " if spaced else functor
            if functor == ",":
                operator = ", "
            if priority > limit:
                stack.append(")")
            stack.append((node[2], right_limit, not spaced))
            stack.append(operator)
            stack.append((node[1], left_limit, False))
            if priority > limit:
                stack.append("(")
            continue
        if len(node) == 2 and (functor == "-" or functor == "+"):
            operand = deref(node[1])
            wrap = 200 > limit
            if wrap:
                stack.append(")")
            if type(operand) is int or type(operand) is Fraction:
                stack.append(")")
                stack.append((operand, 1200, False))
                stack.append(functor + "(")
            else:
                stack.append((operand, 200, True))
                stack.append(functor)
            if wrap:
                stack.append("(")
            continue
        stack.append(")")
        index = len(node) - 1
        while index >= 1:
            stack.append((node[index], 999, False))
            if index > 1:
                stack.append(", ")
            index -= 1
        stack.append(functor + "(")
    return "".join(pieces)


def _number_text(number):
    if type(number) is Fraction:
        if number.denominator == 1:
            return _integer_text(number.numerator)
        return (f"{_integer_text(number.numerator)}/"
                f"{_integer_text(number.denominator)}")
    if type(number) is int:
        return _integer_text(number)
    return str(number)


_PLAIN_TEXT_LIMIT = 10 ** 4000


def _integer_text(integer):
    """*integer* in decimal.  CPython's str(int) refuses more than 4300
    digits; Decimal's does not, as chars.py's _number_text prints it
    (test_a_bound_past_4300_digits_prints)."""
    if -_PLAIN_TEXT_LIMIT < integer < _PLAIN_TEXT_LIMIT:
        return str(integer)
    return str(Decimal(integer))
