# Ported from clp(q,r) version 1.3.3, files nf.pl and nfq.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""The normal form and constraint posting: nf.pl and nfq.pl.

Every predicate of nf.pl, then nfq.pl's translate_goal//1, is a function
here in file order, named by NAMES.md.  A predicate defined at two arities
gets a second name for the second (NAMES.md, "Names the port adds").  The
commented-out `invertible/2` of nf.pl is not ported.

Representations:

- A normal form is a Python list of Monomial records, 1.3.3's list of
  `monomial(K, Powers)`, in the standard order of their power products
  (the constant, with no powers, first).  `coefficient` is a rational
  (arithmetic.py); `powers` is a list of (base, exponent) pairs, 1.3.3's
  `[X^P, ...]`, in the standard order of the bases; an exponent is an int.
- A base is an unbound variable or a NonlinearBase: 1.3.3's skeleton
  `abs(Nf)`, `sin(Nf)`, `cos(Nf)`, `tan(Nf)`, `min(Nf, Nf)`, `max(Nf, Nf)`,
  `exp(Nf, Nf)` or `Nf / Nf`, whose arguments are normal forms.  The record
  keeps 1.3.3's functor as `name`, because the standard order of two bases
  reads it.
- The standard order of terms that 1.3.3's compare/3 applies to power
  products is compare_power_products and the functions after it; two
  unbound variables are in creation order (DEVIATIONS.md D11).
- A constraint or an expression is an engine term: the operator nodes the
  `{}` lowering builds (ArithEq, Lt, LtE, Gt, GtE, ArithNeq, Add, Sub,
  Mult, Div, Negate, UnaryPlus, IsoIntPow for `^`), a tuple or list of
  constraints (a conjunction), or a compound cell `(functor, arg, ...)` as
  the reader and normal_form_to_term build it.
- A predicate that fails returns False (a bool result) or None (any other
  result).  illarg/3 raises a LogicException with the ISO error term.

Delayed goals are (procedure, argument) pairs (delayed_goals.py, D7).  The
goals nf.pl delays are resubmit_equal, resubmit_less_than,
resubmit_less_or_equal and resubmit_not_equal, whose argument is the normal
form, and wait_linear_retry, whose argument is a WaitLinearRetry record.
All of them are deterministic in 1.3.3 (DEVIATIONS.md D7 lists the clauses
that show it).

Imports: nf.pl calls bv.pl and ineq.pl, and bv.pl calls nf.pl back
(split, wait_linear, {}/1), so bounded_simplex imports this module at its
call sites ("cyclic") and this module imports bounded_simplex and
inequalities at the top.
"""
from math import log2 as _log2

from clausal.logic.clpq import limits
from clausal.logic.clpq.attributes import refuse_inside_attribute_hooks
from clausal.logic.cells import TUPLE_TAG, compound_cell_shape
from clausal.logic.clpq.arithmetic import (
    ONE, ZERO, absolute, add, arc_cosine, arc_sine, arc_tangent,
    arithmetic_normalize, compare, cosine, divide, exponential_power,
    is_number, is_zero, logarithm, maximum, minimum, multiply, rational_integer, sine,
    tangent, to_number)
from clausal.logic.clpq.arithmetic import negate as negate_rational
from clausal.logic.clpq.bounded_simplex import (
    dereference_balanced, export_binding, solve, solve_less,
    solve_less_or_equal, solve_not_equal)
from clausal.logic.clpq.delayed_goals import delay_goal
from clausal.logic.clpq.inequalities import (
    inequality_one_variable,
    inequality_one_variable_nonstrict_negative_zero,
    inequality_one_variable_nonstrict_positive_zero,
    inequality_one_variable_strict_negative_zero,
    inequality_one_variable_strict_positive_zero)
from clausal.logic.clpq.linear_forms import (
    MINUS_ONE, add_linear_forms, normalize_scalar)
from clausal.logic.exceptions import (
    LogicException, instantiation_error, type_error)
from clausal.logic.pending import run_first
from clausal.logic.variables import Var, deref, is_var
from clausal.pythonic_ast import nodes as _nodes

#: The solver's module, the `M` of the `M:{C}` goals translate_goal emits
#: and dump.pl's nonlinear_strip/3 tests with `M == Solver`.
SOLVER_MODULE = "clpq"


class Monomial:
    """nf.pl's `monomial(K, Powers)` (the `v/2` of the original)."""
    __slots__ = ("coefficient", "powers")

    def __init__(self, coefficient, powers):
        self.coefficient = coefficient
        self.powers = powers

    def __repr__(self):
        return f"Monomial({self.coefficient!r}, {self.powers!r})"


class NonlinearBase:
    """A non-linear base: 1.3.3's skeleton `name(Nf, ...)` with normal-form
    arguments, `abs`, `sin`, `cos`, `tan` (one argument), `min`, `max`,
    `exp` or `/` (two; `/` is numerator, divisor)."""
    __slots__ = ("name", "arguments")

    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments

    def __repr__(self):
        return f"NonlinearBase({self.name!r}, {self.arguments!r})"


class WaitLinearRetry:
    """nf.pl's goal `wait_linear_retry(Nf, Res, Goal)`: *result* is Res, a
    variable of its own, and the Goal is `procedure(Nf, argument, trail)`."""
    __slots__ = ("normal_form", "result", "procedure", "argument")

    def __init__(self, normal_form, result, procedure, argument):
        self.normal_form = normal_form
        self.result = result
        self.procedure = procedure
        self.argument = argument


# ---------------------------------------------------------------- terms
#
# How an engine term reads as a Prolog term: its functor and arguments.

_KIND_OTHER = 0
_KIND_VARIABLE = 1
_KIND_NUMBER = 2

_NODE_FUNCTORS = {
    _nodes.Add: "+", _nodes.Sub: "-", _nodes.Mult: "*", _nodes.Div: "/",
    _nodes.IsoTrueDiv: "/", _nodes.IsoIntPow: "^",
    _nodes.ArithEq: "=", _nodes.ArithNeq: "=\\=", _nodes.Lt: "<",
    _nodes.LtE: "=<", _nodes.Gt: ">", _nodes.GtE: ">=",
}
_UNARY_NODE_FUNCTORS = {_nodes.Negate: "-", _nodes.UnaryPlus: "+"}


def _functor_and_arguments(term):
    """(functor, arguments) of a dereferenced compound term, or (None, ())."""
    kind = type(term)
    functor = _NODE_FUNCTORS.get(kind)
    if functor is not None:
        return functor, (term.left, term.right)
    functor = _UNARY_NODE_FUNCTORS.get(kind)
    if functor is not None:
        return functor, (term.operand,)
    if kind is tuple and len(term) >= 2 and type(term[0]) is str:
        is_compound, functor = compound_cell_shape(term)
        if is_compound:
            return functor, term[1:]
    return None, ()


def _conjunction_elements(term):
    """The constraints of a conjunction written as a sequence, or None: a
    list, a tuple that is not a compound cell (what a `{C1, C2}` block
    passes), or a tuple-data cell ("()", C1, C2, ...)."""
    kind = type(term)
    if kind is list:
        return term
    if kind is tuple and term:
        if type(term[0]) is not str:
            return term
        if term[0] == TUPLE_TAG:
            return term[1:]
    return None


# ---------------------------------------------------------------- {}/1

class ConstraintChoices:
    """The choice points `{R ; Rs}` (nf.pl `{}/1` clause 3) leaves: a stack
    of (trail mark, the other branch, the goals after it), newest last.
    resume_constraint takes the newest one; it is how a caller backtracks
    into a posted `{}` (DEVIATIONS.md D12).  *post_comparison* is the
    function each comparison is posted with, kept so the branches a resume
    takes are posted as the first was."""
    __slots__ = ("choices", "post_comparison")

    def __init__(self, choices, post_comparison=None):
        self.choices = choices
        self.post_comparison = post_comparison


def post_constraint(term, trail):
    """nf.pl, {}/1: post the constraint *term*; True or False.

    The choice points of `{R ; Rs}` are kept while the constraint is being
    posted, so a later failure inside the same `{}` takes the other branch
    (test_a_disjunction_is_retried_when_a_later_constraint_fails); this
    function then drops them.  post_constraint_with_choices keeps them for
    the caller.  The conjunction and disjunction are a work list, not
    recursion."""
    refuse_inside_attribute_hooks(trail, ("{}", term), "{}", 1)
    return _run_constraint_goals((term, None), [], trail, _post_comparison)


def post_constraint_with_choices(term, trail, post_comparison=None):
    """nf.pl, {}/1 with its choice points handed back: a ConstraintChoices
    to pass to resume_constraint after a later failure, or None where the
    constraint fails (test_a_caller_resumes_a_posted_disjunction).

    *post_comparison*, when given, posts each comparison in place of nf.pl's
    clauses 4 to 12 (same arguments as _post_comparison): the adapter's
    Decimal-scale fast path (DEVIATIONS.md D20,
    test_a_decimal_keeps_its_scale_in_a_disjunction)."""
    refuse_inside_attribute_hooks(trail, ("{}", term), "{}", 1)
    if post_comparison is None:
        post_comparison = _post_comparison
    choices = []
    if not _run_constraint_goals((term, None), choices, trail,
                                 post_comparison):
        return None
    return ConstraintChoices(choices, post_comparison)


def resume_constraint(state, trail):
    """Backtrack into a constraint posted with post_constraint_with_choices:
    undo to its newest choice point and take the other branch, then the
    goals after it.  True when that succeeds (the state keeps any choice
    points that are left), False when no branch is left."""
    refuse_inside_attribute_hooks(
        trail, ("resume_constraint", state), "resume_constraint", 1)
    choices = state.choices
    post_comparison = state.post_comparison
    if post_comparison is None:
        post_comparison = _post_comparison
    while choices:
        mark, alternative, goals = choices.pop()
        trail.undo(mark)
        if _run_constraint_goals((alternative, goals), choices, trail,
                                 post_comparison):
            return True
    return False


def _run_constraint_goals(goals, choices, trail, post_comparison):
    """{}/1's clauses on the goal list *goals* (a cons list), pushing the
    choice points of `;` onto *choices* and backtracking into them on
    failure.  True when every goal has succeeded."""
    while True:
        if goals is None:
            return True
        goal, goals = goals
        goal = deref(goal)
        if is_var(goal):                                    # clause 1
            raise LogicException(instantiation_error("{}/1"))
        elements = _conjunction_elements(goal)
        if elements is not None:                            # a conjunction
            for element in reversed(elements):
                goals = (element, goals)
            continue
        if type(goal) is _nodes.CompareChain:
            for element in reversed(goal.comparisons):
                goals = (element, goals)
            continue
        functor, arguments = _functor_and_arguments(goal)
        if functor == "," and len(arguments) == 2:          # clause 2
            goals = (arguments[0], (arguments[1], goals))
            continue
        if functor == ";" and len(arguments) == 2:          # clause 3
            choices.append((trail.mark(), arguments[1], goals))
            goals = (arguments[0], goals)
            continue
        if post_comparison(functor, arguments, goal, trail):
            continue
        if not choices:
            return False
        mark, alternative, goals = choices.pop()
        trail.undo(mark)
        goals = (alternative, goals)


def _post_comparison(functor, arguments, goal, trail):
    """nf.pl, {}/1 clauses 4 to 12: one comparison."""
    if len(arguments) == 2:
        left, right = arguments
        if functor == "<":
            norm = _difference(left, right)
            return norm is not None and submit_less_than(norm, trail)
        if functor == ">":
            norm = _difference(right, left)
            return norm is not None and submit_less_than(norm, trail)
        if functor == "=<" or functor == "<=":
            norm = _difference(left, right)
            return norm is not None and submit_less_or_equal(norm, trail)
        if functor == ">=":
            norm = _difference(right, left)
            return norm is not None and submit_less_or_equal(norm, trail)
        if functor == "=\\=":
            norm = _difference(left, right)
            return norm is not None and submit_not_equal(norm, trail)
        if functor == "=:=" or functor == "=":
            norm = _difference(left, right)
            return norm is not None and submit_equal(norm, trail)
    raise LogicException(type_error("constraint", goal, "{}/1"))   # clause 13


def _difference(left, right):
    """normal_form(L-R, Nf); None where it fails."""
    return normal_form(("-", left, right))


#
# s -> c = ~s v c = ~(s /\ ~c)
# where s is the store and c is the constraint for which
# we want to know whether it is entailed.
#
def entailed(term, trail):
    """nf.pl, entailed/1: `negate(C, Cn), \\+ {Cn}`.  The store is left as
    it was (test_entailed_leaves_the_store_as_it_was).  The goals {Cn}
    wakes run inside the `\\+`, to their first answer; under a driver they
    are queued, so the queue entailed was entered with is taken first and
    the undo puts it back (ruling R24,
    test_entailed_runs_the_goals_its_probe_wakes)."""
    refuse_inside_attribute_hooks(trail, ("entailed", term), "entailed", 1)
    negation = negate(term)
    mark = trail.mark()
    try:
        trail.take_pending()
        return not (post_constraint(negation, trail) and run_first(trail))
    finally:
        trail.undo(mark)


_NEGATIONS = {"<": ">=", ">": "=<", "=<": ">", ">=": "<", "=:=": "=\\=",
              "=": "=\\=", "=\\=": "=:="}


def negate(term):
    """nf.pl, negate/2: the negation of a constraint, as compound cells.
    A conjunction (cell or tuple) becomes a disjunction and the other way
    round.  An explicit stack, not recursion (test_negate_of_a_long_
    conjunction_needs_no_recursion)."""
    # Post-order: (_EXPAND, term) pushes its parts; (_JOIN, functor, count)
    # joins the last *count* results right-nested.
    work = [(0, term)]
    results = []
    while work:
        item = work.pop()
        if item[0] == 1:
            _, functor, count = item
            parts = results[len(results) - count:]
            del results[len(results) - count:]
            joined = parts[-1]
            for part in reversed(parts[:-1]):
                joined = (functor, part, joined)
            results.append(joined)
            continue
        goal = deref(item[1])
        if is_var(goal):                                    # clause 1
            raise LogicException(instantiation_error("entailed/1"))
        elements = _conjunction_elements(goal)
        if elements is not None:
            elements = list(elements)
            if not elements:
                raise LogicException(type_error("constraint", goal, "entailed/1"))
            work.append((1, ";", len(elements)))
            for element in reversed(elements):
                work.append((0, element))
            continue
        if type(goal) is _nodes.CompareChain:
            elements = list(goal.comparisons)
            work.append((1, ";", len(elements)))
            for element in reversed(elements):
                work.append((0, element))
            continue
        functor, arguments = _functor_and_arguments(goal)
        if len(arguments) == 2 and functor == ",":           # clause 2
            work.append((1, ";", 2))
            work.append((0, arguments[1]))
            work.append((0, arguments[0]))
            continue
        if len(arguments) == 2 and functor == ";":           # clause 3
            work.append((1, ",", 2))
            work.append((0, arguments[1]))
            work.append((0, arguments[0]))
            continue
        negation = _NEGATIONS.get(functor) if len(arguments) == 2 else None
        if negation is None:                                # clause 11
            raise LogicException(type_error("constraint", goal, "entailed/1"))
        results.append((negation, arguments[0], arguments[1]))   # clauses 4-10
    return results[0]


# ---------------------------------------------------------------- submit
#
#   Cases:  a) Nf=[]
#           b) Nf=[A]
#              b1) A=k
#              b2) invertible(A)
#              b3) linear -> A=0
#              b4) nonlinear -> geler
#           c) Nf=[A,B|Rest]
#              c1) A=k
#                  c11) B=X^+-1, Rest=[] -> B=
#                  c12) invertible(A,B)
#                  c13) linear(B|Rest)
#                  c14) geler
#              c2) linear(Nf)
#              c3) nonlinear -> geler

def submit_equal(norm, trail):
    """nf.pl, submit_equal/1 (submit_eq/1).

    b2 and c12 end in the last call `submit_equal(New)`; those functions
    hand New back as a list and this loop takes it, so an invertible
    function nested any depth needs no recursion
    (test_a_deeply_nested_invertible_equation_needs_no_recursion)."""
    while True:
        if not norm:                                        # trivial success
            return True
        result = submit_equal_terms(norm[1:], norm[0], trail)
        if type(result) is not list:
            return result
        norm = result


def submit_equal_terms(rest, first, trail):
    """nf.pl, submit_equal/2 (submit_eq/2).  A bool, or the normal form to
    submit next (submit_equal's loop)."""
    if not rest:
        return submit_equal_single_term(first, trail)
    return submit_equal_several_terms(first, rest[0], rest[1:], trail)


def _single_power(monomial):
    """(base, exponent) of a monomial `K*X^P` with one power, else None."""
    powers = monomial.powers
    if len(powers) != 1:
        return None
    return deref(powers[0][0]), powers[0][1]


def submit_equal_single_term(monomial, trail):
    """nf.pl, submit_equal_single_term/1 (submit_eq_b/1): a bool, or the
    normal form to submit next."""
    if not monomial.powers:                                 # b1: trivial failure
        return False
    single = _single_power(monomial)
    if single is not None:
        base, exponent = single
        if is_var(base) and exponent > 0:                   # b2,b3: n*x^p=0 -> x=0
            return export_binding(base, ZERO, trail)
        if not is_var(base) and exponent == 1:              # b2
            found = nonlinear_invertible(base, ZERO)
            if found is not None:
                argument, inverse = found
                return normal_form_add(        # submit_equal(New): the loop
                    argument, normal_form_number(negate_rational(inverse)))
    return delay_goal(term_variables_set([monomial]), resubmit_equal,  # b4
                      [monomial], trail)


def _is_linear_variable_monomial(monomial):
    """`M = monomial(_, [X^1]), var(X)`."""
    single = _single_power(monomial)
    return single is not None and single[1] == 1 and is_var(single[0])


def submit_equal_several_terms(first, second, rest, trail):
    """nf.pl, submit_equal_several_terms/3 (submit_eq_c/3): a bool, or the
    normal form to submit next."""
    if not first.powers:
        return submit_equal_constant_first(rest, second, first.coefficient,
                                           trail)
    if _is_linear_variable_monomial(first) \
            and _is_linear_variable_monomial(second) and linear(rest):   # c2
        homogeneous = [first, second] + rest
        # 'solve_='( Hom).
        result = dereference_balanced(normal_form_length(homogeneous),
                                      homogeneous, 0, trail)
        if result is None:
            return False
        return solve(result[0], trail)
    norm = [first, second] + rest                           # c3
    return delay_goal(term_variables_set(norm), resubmit_equal, norm, trail)


def submit_equal_constant_first(rest, second, constant, trail):
    """nf.pl, submit_equal_constant_first/3 (submit_eq_c1/3): a bool, or
    the normal form to submit next."""
    single = _single_power(second)
    if not rest and single is not None:
        base, exponent = single
        coefficient = second.coefficient
        if is_var(base):                                    # c11
            if exponent == 1:
                return export_binding(
                    base, divide(negate_rational(constant), coefficient), trail)
            if exponent == -1:
                return export_binding(
                    base, divide(negate_rational(coefficient), constant), trail)
        else:                                               # c12
            value = None
            if exponent == 1:
                value = divide(negate_rational(constant), coefficient)
            elif exponent == -1:
                value = divide(negate_rational(coefficient), constant)
            if value is not None:
                found = nonlinear_invertible(base, value)
                if found is not None:
                    argument, inverse = found
                    return normal_form_add(    # submit_equal(New): the loop
                        argument, normal_form_number(negate_rational(inverse)))
    if _is_linear_variable_monomial(second) and linear(rest):   # c13
        # 'solve_='( [v(I,[]),B|Rest]).
        homogeneous = [second] + rest
        nonvariable = normalize_scalar(constant)
        result = dereference_balanced(normal_form_length(homogeneous),
                                      homogeneous, 0, trail)
        if result is None:
            return False
        form = add_linear_forms(nonvariable, result[0])
        if form is None:
            return False
        return solve(form, trail)
    norm = [Monomial(constant, []), second] + rest          # c14
    return delay_goal(term_variables_set(norm), resubmit_equal, norm, trail)


# -----------------------------------------------------------------------

def submit_less_than(norm, trail):
    """nf.pl, submit_less_than/1 (submit_lt/1)."""
    if not norm:                                            # trivial failure
        return False
    return submit_less_than_terms(norm[1:], norm[0], trail)


def submit_less_than_terms(rest, first, trail):
    """nf.pl, submit_less_than/2 (submit_lt/2)."""
    if not rest:
        return submit_less_than_single_term(first.powers, first.coefficient,
                                            trail)
    return submit_less_than_several_terms(rest[1:], first, rest[0], trail)


def submit_less_than_single_term(powers, coefficient, trail):
    """nf.pl, submit_less_than_single_term/2 (submit_lt_b/2)."""
    if not powers:
        return compare(coefficient, ZERO) < 0
    if len(powers) == 1 and powers[0][1] == 1 and is_var(deref(powers[0][0])):
        variable = deref(powers[0][0])
        if compare(coefficient, ZERO) > 0:
            return inequality_one_variable_strict_positive_zero(variable, trail)
        return inequality_one_variable_strict_negative_zero(variable, trail)
    return delay_goal(term_variables_set(powers), resubmit_less_than,
                      [Monomial(coefficient, powers)], trail)


def submit_less_than_several_terms(rest, first, second, trail):
    """nf.pl, submit_less_than_several_terms/3 (submit_lt_c/3)."""
    if not rest and not first.powers and _is_linear_variable_monomial(second):
        return inequality_one_variable(True, deref(second.powers[0][0]),
                                       second.coefficient, first.coefficient,
                                       trail)
    norm = [first, second] + rest
    if linear(norm):
        return solve_less(norm, trail)
    return delay_goal(term_variables_set(norm), resubmit_less_than, norm, trail)


def submit_less_or_equal(norm, trail):
    """nf.pl, submit_less_or_equal/1 (submit_le/1)."""
    if not norm:                                            # trivial success
        return True
    return submit_less_or_equal_terms(norm[1:], norm[0], trail)


def submit_less_or_equal_terms(rest, first, trail):
    """nf.pl, submit_less_or_equal/2 (submit_le/2)."""
    if not rest:
        return submit_less_or_equal_single_term(first.powers,
                                                first.coefficient, trail)
    return submit_less_or_equal_several_terms(rest[1:], first, rest[0], trail)


def submit_less_or_equal_single_term(powers, coefficient, trail):
    """nf.pl, submit_less_or_equal_single_term/2 (submit_le_b/2)."""
    if not powers:
        return compare(coefficient, ZERO) <= 0
    if len(powers) == 1 and powers[0][1] == 1 and is_var(deref(powers[0][0])):
        variable = deref(powers[0][0])
        if compare(coefficient, ZERO) > 0:
            return inequality_one_variable_nonstrict_positive_zero(variable,
                                                                   trail)
        return inequality_one_variable_nonstrict_negative_zero(variable, trail)
    return delay_goal(term_variables_set(powers), resubmit_less_or_equal,
                      [Monomial(coefficient, powers)], trail)


def submit_less_or_equal_several_terms(rest, first, second, trail):
    """nf.pl, submit_less_or_equal_several_terms/3 (submit_le_c/3)."""
    if not rest and not first.powers and _is_linear_variable_monomial(second):
        return inequality_one_variable(False, deref(second.powers[0][0]),
                                       second.coefficient, first.coefficient,
                                       trail)
    norm = [first, second] + rest
    if linear(norm):
        return solve_less_or_equal(norm, trail)
    return delay_goal(term_variables_set(norm), resubmit_less_or_equal, norm,
                      trail)


def submit_not_equal(norm, trail):
    """nf.pl, submit_not_equal/1 (submit_ne/1)."""
    constant = normal_form_constant(norm)
    if constant is not None:
        return not is_zero(constant)
    if linear(norm):
        return solve_not_equal(norm, trail)
    return delay_goal(term_variables_set(norm), resubmit_not_equal, norm,
                      trail)


def linear(norm):
    """nf.pl, linear/1 on a normal form (its clauses 1 and 3, with clause 2
    for each monomial)."""
    for monomial in norm:
        if not linear_power_products(monomial.powers):
            return False
    return True


def linear_power_products(powers):
    """nf.pl, linear_power_products/1 (linear_ps/1): [] or [V^1] with V a
    variable (excludes sin(_), ...)."""
    if not powers:
        return True
    return len(powers) == 1 and powers[0][1] == 1 and is_var(deref(powers[0][0]))


#
# Goal delays until Term gets linear.
# At this time, Var will be bound to the normalform of Term.
#
def wait_linear(term, procedure, argument, trail):
    """nf.pl, wait_linear/3: run `procedure(Nf, argument, trail)` once the
    normal form Nf of *term* is linear.  1.3.3's `Var` is the Nf the goal
    receives; the delayed goal keeps a variable of its own for it
    (WaitLinearRetry.result), which translate_goal shows."""
    norm = normal_form(term)
    if norm is None:
        return False
    if linear(norm):
        return procedure(norm, argument, trail)
    return delay_goal(term_variables_set(norm), wait_linear_retry,
                      WaitLinearRetry(norm, Var(), procedure, argument), trail)


#
# geler clients
#
def resubmit_equal(norm, trail):
    """nf.pl, resubmit_equal/1 (resubmit_eq/1)."""
    repaired = repair(norm)
    if repaired is None:
        return False
    return submit_equal(repaired, trail)


def resubmit_less_than(norm, trail):
    """nf.pl, resubmit_less_than/1 (resubmit_lt/1)."""
    repaired = repair(norm)
    if repaired is None:
        return False
    return submit_less_than(repaired, trail)


def resubmit_less_or_equal(norm, trail):
    """nf.pl, resubmit_less_or_equal/1 (resubmit_le/1)."""
    repaired = repair(norm)
    if repaired is None:
        return False
    return submit_less_or_equal(repaired, trail)


def resubmit_not_equal(norm, trail):
    """nf.pl, resubmit_not_equal/1 (resubmit_ne/1)."""
    repaired = repair(norm)
    if repaired is None:
        return False
    return submit_not_equal(repaired, trail)


def wait_linear_retry(record, trail):
    """nf.pl, wait_linear_retry/3."""
    norm = repair(record.normal_form)
    if norm is None:
        return False
    if linear(norm):
        return record.procedure(norm, record.argument, trail)
    return delay_goal(term_variables_set(norm), wait_linear_retry,
                      WaitLinearRetry(norm, record.result, record.procedure,
                                      record.argument), trail)


# -----------------------------------------------------------------------

def nonlinear_invertible(base, value):
    """nf.pl, nonlinear_invertible/4 (nl_invertible/4): for `base = value`,
    the argument X of *base* (a normal form) and the value Res it must take,
    as (X, Res); None where 1.3.3 fails."""
    name = base.name
    arguments = base.arguments
    if name == "sin":
        return arguments[0], arc_sine(value)
    if name == "cos":
        return arguments[0], arc_cosine(value)
    if name == "tan":
        return arguments[0], arc_tangent(value)
    if name == "exp":
        exponent_base, exponent = arguments
        constant_base = normal_form_constant(exponent_base)
        if constant_base is not None:
            if compare(value, ZERO) > 0 and compare(constant_base, ZERO) > 0 \
                    and compare(constant_base, ONE) != 0:
                return exponent, divide(logarithm(value),
                                        logarithm(constant_base))
            return None
        constant_exponent = normal_form_constant(exponent)
        if constant_exponent is None:
            return None
        if is_zero(value) and compare(constant_exponent, ZERO) <= 0:
            return None
        return exponent_base, exponential_power(
            value, divide(ONE, constant_exponent))
    return None


# -----------------------------------------------------------------------

def cyclic_term_error(functor, arity):
    """The error a cyclic expression raises: Scryer's is/2 on `X = 1+X`
    raises type_error(evaluable, (+)/2), naming the functor of the compound
    that closes the cycle, so the culprit is a finite term (DEVIATIONS.md
    D23)."""
    return type_error("evaluable", ("/", functor, arity), "normal_form/2")


def refuse_cyclic_term(term):
    """Raise cyclic_term_error when *term* is cyclic; otherwise return.
    A depth-first walk with an explicit stack: a compound is on the path
    from its entry to its exit, and one met again while on the path closes
    a cycle.  A compound already left is not walked again, so a term with
    shared subterms costs its number of distinct compounds.  The adapter
    calls it before clpfd's cell walk, which recurses
    (test_the_adapter_refuses_a_cyclic_term)."""
    on_path = set()
    done = set()
    stack = [(False, term)]
    while stack:
        leaving, item = stack.pop()
        if leaving:
            on_path.discard(id(item))
            done.add(id(item))
            continue
        item = deref(item)
        if is_var(item):
            continue
        kind = type(item)
        if kind is list:
            arguments = item
            functor = "."
            arity = 2
        elif kind is _nodes.CompareChain:
            arguments = item.comparisons
            functor = ","
            arity = 2
        else:
            functor, arguments = _functor_and_arguments(item)
            if functor is None:
                if kind is tuple and item and type(item[0]) is not str:
                    arguments = item                # a block's sequence
                    functor = ","
                    arity = 2
                else:
                    continue
            else:
                arity = len(arguments)
        key = id(item)
        if key in done:
            continue
        if key in on_path:
            raise LogicException(cyclic_term_error(functor, arity))
        on_path.add(key)
        stack.append((True, item))
        for argument in arguments:
            stack.append((False, argument))


# Work items of normal_form's explicit stack.
_EVALUATE = 0
_NEGATE = 1
_ADD = 2
_MULTIPLY = 3
_DIVIDE = 4
_NONLINEAR_UNARY = 5
_NONLINEAR_BINARY = 6
_LEAVE = 7


def normal_form(term):
    """nf.pl, normal_form/2 (nf/2): the normal form of the expression
    *term*, or None where it fails (a division by zero).

    1.3.3 recurses on the term; the port walks it with an explicit stack of
    work items and a stack of results, so a long sum needs no recursion
    (test_a_long_sum_needs_no_recursion).  Each clause pushes the
    operation to apply after its arguments.

    *path* holds the compounds between the root and the term being read
    (each one's `_LEAVE` item takes it off again), so a cyclic term raises
    type_error(evaluable, F/A) where 1.3.3 loops (DEVIATIONS.md D23,
    test_normal_form_of_a_cyclic_term_raises).

    Its powers and products of sums are charged, before each is made, to
    a count of this call's own (limits.Expansion, made at the first one):
    past a clpq_expansion cap it raises `resource_error(clpq_expansion)`
    (DEVIATIONS.md D24)."""
    work = [(_EVALUATE, term)]
    values = []
    path = set()
    expansion = None
    while work:
        item = work.pop()
        action = item[0]
        if action == _EVALUATE:
            if not _evaluate_step(item[1], work, values, path):
                return None
        elif action == _LEAVE:
            path.discard(item[1])
        elif action == _NEGATE:
            values.append(normal_form_multiply_factor(
                Monomial(MINUS_ONE, []), values.pop()))
        elif action == _ADD:
            right = values.pop()
            values.append(normal_form_add(values.pop(), right))
        elif action == _MULTIPLY:
            right = values.pop()
            left = values.pop()
            if len(left) > 1 and len(right) > 1:
                if expansion is None:
                    expansion = limits.Expansion()
                values.append(charged_multiply(left, right, expansion))
            else:
                values.append(normal_form_multiply(left, right))
        elif action == _DIVIDE:
            divisor = values.pop()
            result = normal_form_divide(divisor, values.pop())
            if result is None:
                return None
            values.append(result)
        elif action == _NONLINEAR_UNARY:
            values.append(normal_form_nonlinear_unary(item[1], values.pop()))
        else:
            right = values.pop()
            if expansion is None:
                expansion = limits.Expansion()
            result = normal_form_nonlinear_binary(item[1], values.pop(), right,
                                                  expansion)
            if result is None:
                return None
            values.append(result)
    return values[0]


def _evaluate_step(term, work, values, path):
    """One clause of normal_form/2 on *term*: push its value, or push the
    work for its arguments.  False where the clause fails.  *path* is
    normal_form's set of the compounds above *term*."""
    term = deref(term)
    if is_var(term):                                        # clause 1
        values.append([Monomial(ONE, [(term, 1)])])
        return True
    if is_normal_form_number(term):                         # clauses 2, 3
        values.append(normal_form_number(term))
        return True
    functor, arguments = _functor_and_arguments(term)
    arity = len(arguments)
    if functor is not None:
        key = id(term)
        if key in path:
            raise LogicException(cyclic_term_error(functor, arity))
        path.add(key)
        work.append((_LEAVE, key))
    if functor == "rat" and arity == 2:                     # clause 3
        numerator, denominator = deref(arguments[0]), deref(arguments[1])
        if type(numerator) is int and type(denominator) is int:
            values.append(normal_form_number((numerator, denominator)))
            return True
    if functor == "#" and arity == 1:                       # clause 4
        value = monash_constant(arguments[0])
        if value is not None:
            # In Q (evaluate_arithmetic(1, rat(1,1)) holds): swallows
            # #(zero) ... ok in Q.
            values.append(normal_form_number(value))
            return True
    if functor == "-" and arity == 1:                       # clause 5
        work.append((_NEGATE,))
        work.append((_EVALUATE, arguments[0]))
        return True
    if functor == "+" and arity == 1:                       # clause 6
        work.append((_EVALUATE, arguments[0]))
        return True
    if functor == "+" and arity == 2:                       # clause 7
        work.append((_ADD,))
        work.append((_EVALUATE, arguments[1]))
        work.append((_EVALUATE, arguments[0]))
        return True
    if functor == "-" and arity == 2:                       # clause 8: A + -B
        work.append((_ADD,))
        work.append((_NEGATE,))
        work.append((_EVALUATE, arguments[1]))
        work.append((_EVALUATE, arguments[0]))
        return True
    if functor == "*" and arity == 2:                       # clause 9
        work.append((_MULTIPLY,))
        work.append((_EVALUATE, arguments[1]))
        work.append((_EVALUATE, arguments[0]))
        return True
    if functor == "/" and arity == 2:                       # clause 10
        work.append((_DIVIDE,))
        work.append((_EVALUATE, arguments[1]))
        work.append((_EVALUATE, arguments[0]))
        return True
    name = nonlinear_unary(functor, arity)                  # clause 11
    if name is not None:
        work.append((_NONLINEAR_UNARY, name))
        work.append((_EVALUATE, arguments[0]))
        return True
    name = nonlinear_binary(functor, arity)                 # clause 12
    if name is not None:
        work.append((_NONLINEAR_BINARY, name))
        work.append((_EVALUATE, arguments[1]))
        work.append((_EVALUATE, arguments[0]))
        return True
    raise LogicException(type_error("expression", term, "normal_form/2"))  # clause 13


def normal_form_number(number):
    """nf.pl, normal_form_number/2 (nf_number/2): the normal form of a
    number (an engine number or a rational)."""
    normal = arithmetic_normalize(number)
    if is_zero(normal):
        return []
    return [Monomial(normal, [])]


def is_normal_form_number(term):
    """nf.pl, normal_form_number/1 (nf_number/1): an engine number (its
    first clause, number/1; a float as well, which arithmetic_normalize
    reads as 1.3.3's get_rational/3 does).  The second clause, rat(_,_),
    is normal_form's rat clause here."""
    return is_number(term)


def nonlinear_unary(functor, arity):
    """nf.pl, nonlinear_unary/4 (nonlin_1/4): the skeleton name of a
    one-argument non-linear function, or None."""
    if arity == 1 and functor in ("abs", "sin", "cos", "tan"):
        return functor
    return None


def nonlinear_binary(functor, arity):
    """nf.pl, nonlinear_binary/6 (nonlin_2/6): the skeleton name of a
    two-argument non-linear function, or None (pow and ^ are exp)."""
    if arity != 2:
        return None
    if functor == "min" or functor == "max" or functor == "exp":
        return functor
    if functor == "pow" or functor == "^":                  # pow->exp
        return "exp"
    return None


def normal_form_nonlinear_unary(name, argument):
    """nf.pl, normal_form_nonlinear_unary/4 (nf_nonlin_1/4)."""
    constant = normal_form_constant(argument)
    if constant is not None:
        return normal_form_number(evaluate_nonlinear(name, (constant,)))
    return [Monomial(ONE, [(NonlinearBase(name, (argument,)), 1)])]


def normal_form_nonlinear_binary(name, first, second, expansion=None):
    """nf.pl, normal_form_nonlinear_binary/6 (nf_nonlin_2/6).  None where
    a negative integer power of zero divides by zero."""
    constant_first = normal_form_constant(first)
    constant_second = normal_form_constant(second)
    if constant_first is not None and constant_second is not None:
        if name == "exp":
            exponent = rational_integer(constant_second)
            if exponent is not None and abs(exponent) > 1:
                # one exact power of a number (review R2)
                limits.check_coefficient(
                    _times_exponent(abs(exponent),
                                    rational_log2(constant_first)),
                    "a power of a number")
        value = evaluate_nonlinear(name, (constant_first, constant_second))
        if value is None:
            return None
        return normal_form_number(value)
    if name == "exp" and constant_second is not None:
        exponent = rational_integer(constant_second)
        if exponent is not None:
            return normal_form_power(exponent, first, expansion)
    return [Monomial(ONE, [(NonlinearBase(name, (first, second)), 1)])]


def evaluate_nonlinear(name, arguments):
    """nf.pl, evaluate_nonlinear/2 (nl_eval/2): the value of a skeleton
    with constant arguments, or None for a negative power of zero."""
    if name == "abs":
        return absolute(arguments[0])
    if name == "sin":
        return sine(arguments[0])
    if name == "cos":
        return cosine(arguments[0])
    if name == "tan":
        return tangent(arguments[0])
    if name == "min":
        return minimum(arguments[0], arguments[1])
    if name == "max":
        return maximum(arguments[0], arguments[1])
    if is_zero(arguments[0]) and arguments[1][1] == 1 and arguments[1][0] < 0:
        # 1.3.3's exponential_rational/6 builds rat(1, 0) here, which
        # arithmetic_normalize/2 then refuses, so normal_form/2 fails
        # (test_integer_powers_expand_binomially).
        return None
    return exponential_power(arguments[0], arguments[1])


def monash_constant(constant):
    """nf.pl, monash_constant/2: the value of `#(Constant)`, or None."""
    constant = deref(constant)
    if is_var(constant):
        return None
    if constant == "p" or constant == "pi":
        return 3.141592653589793
    if constant == "e":
        return 2.718281828459045
    if constant == "zero":
        return ZERO                                         # arithmetic_epsilon/1
    return None


#
# check if a Nf consists of just a constant
#
def normal_form_constant(norm):
    """nf.pl, normal_form_constant/2 (nf_constant/2): the constant, or None."""
    if not norm:
        return ZERO
    if len(norm) == 1 and not norm[0].powers:
        return norm[0].coefficient
    return None


#
# this depends on the polynf ordering, i.e. [] < [X^1] ...
#
def split(norm):
    """nf.pl, split/3: (H, I), the homogeneous part and the constant."""
    if not norm:
        return [], ZERO
    if not norm[0].powers:
        return norm[1:], norm[0].coefficient
    return norm, ZERO


#
# runtime predicate
#
def normal_form_add(first, second):
    """nf.pl, normal_form_add/3, normal_form_add/4 and normal_form_add_case/9
    (nf_add/3,4, nf_add_case/9): the sum of two normal forms.  The two-way
    merge is the recursion of normal_form_add/4, unrolled."""
    result = []
    i, j = 0, 0
    while i < len(first) and j < len(second):
        monomial_a = first[i]
        monomial_b = second[j]
        relation = compare_power_products(monomial_a.powers, monomial_b.powers)
        if relation < 0:
            result.append(monomial_a)
            i += 1
        elif relation > 0:
            result.append(monomial_b)
            j += 1
        else:
            coefficient = add(monomial_a.coefficient, monomial_b.coefficient)
            if not is_zero(coefficient):
                result.append(Monomial(coefficient, monomial_a.powers))
            i += 1
            j += 1
    result.extend(first[i:])
    result.extend(second[j:])
    return result


def normal_form_multiply(first, second):
    """nf.pl, normal_form_multiply/3 (nf_mul/3)."""
    return normal_form_multiply_balanced(
        normal_form_length(first), first, 0, normal_form_length(second),
        second)[0]


def normal_form_multiply_balanced(count, first, start, length_second, second):
    """nf.pl, normal_form_multiply_balanced/6 (nf_mul_log/6): the product of
    *count* monomials of *first* from *start* with *second*, as (product,
    start + count).  It halves *count*, so its depth is log2(count)
    (test_long_products_and_repairs_recurse_only_to_log_depth)."""
    if count == 0:
        return [], start
    if count == 1:
        return normal_form_multiply_factor_balanced(
            length_second, second, 0, first[start])[0], start + 1
    if count == 2:
        product_1 = normal_form_multiply_factor_balanced(
            length_second, second, 0, first[start])[0]
        product_2 = normal_form_multiply_factor_balanced(
            length_second, second, 0, first[start + 1])[0]
        return normal_form_add(product_1, product_2), start + 2
    half = count >> 1
    left, middle = normal_form_multiply_balanced(half, first, start,
                                                 length_second, second)
    right, end = normal_form_multiply_balanced(count - half, first, middle,
                                               length_second, second)
    return normal_form_add(left, right), end


def normal_form_add_two(first, second):
    """nf.pl, normal_form_add_two/3 and normal_form_add_two_case/7
    (nf_add_2/3, nf_add_2_case/7): `nf_add([Af], [Bf], Res)` unfolded."""
    relation = compare_power_products(first.powers, second.powers)
    if relation < 0:
        return [first, second]
    if relation > 0:
        return [second, first]
    coefficient = add(first.coefficient, second.coefficient)
    if is_zero(coefficient):
        return []
    return [Monomial(coefficient, first.powers)]


#
# multiply with a scalar =\= 0
#
def normal_form_multiply_scalar(norm, scalar):
    """nf.pl, normal_form_multiply_scalar/3 (nf_mul_k/3)."""
    result = []
    for monomial in norm:
        result.append(Monomial(multiply(scalar, monomial.coefficient),
                               monomial.powers))
    return result


def normal_form_multiply_factor(factor, norm):
    """nf.pl, normal_form_multiply_factor/3 (nf_mul_factor/3)."""
    if not factor.powers:
        return normal_form_multiply_scalar(norm, factor.coefficient)
    return normal_form_multiply_factor_balanced(normal_form_length(norm),
                                                norm, 0, factor)[0]


def normal_form_multiply_factor_balanced(count, norm, start, factor):
    """nf.pl, normal_form_multiply_factor_balanced/5 (nf_mul_factor_log/5):
    (product, start + count).  It halves *count*: depth log2(count)
    (test_long_products_and_repairs_recurse_only_to_log_depth)."""
    if count == 0:
        return [], start
    if count == 1:
        return [multiply_monomials(norm[start], factor)], start + 1
    if count == 2:
        return normal_form_add_two(multiply_monomials(norm[start], factor),
                                   multiply_monomials(norm[start + 1], factor)
                                   ), start + 2
    half = count >> 1
    left, middle = normal_form_multiply_factor_balanced(half, norm, start,
                                                        factor)
    right, end = normal_form_multiply_factor_balanced(count - half, norm,
                                                      middle, factor)
    return normal_form_add(left, right), end


def multiply_monomials(first, second):
    """nf.pl, multiply_monomials/3 (mult/3)."""
    return Monomial(multiply(first.coefficient, second.coefficient),
                    merge_power_products(first.powers, second.powers))


def merge_power_products(first, second):
    """nf.pl, merge_power_products/3,4 and merge_power_products_case/9
    (pmerge/3,4, pmerge_case/9): the product of two power products.  The
    merge is a loop."""
    result = []
    i, j = 0, 0
    while i < len(first) and j < len(second):
        base_a, exponent_a = first[i]
        base_b, exponent_b = second[j]
        relation = compare_bases(base_a, base_b)
        if relation < 0:
            result.append(first[i])
            i += 1
        elif relation > 0:
            result.append(second[j])
            j += 1
        else:
            exponent = exponent_a + exponent_b
            if exponent != 0:
                result.append((base_a, exponent))
            i += 1
            j += 1
    result.extend(first[i:])
    result.extend(second[j:])
    return result


def normal_form_divide(divisor, dividend):
    """nf.pl, normal_form_divide/3 (nf_div/3): dividend / divisor, or None
    where the divisor is zero."""
    if not divisor:
        return zero_division()
    if len(divisor) == 1:
        monomial = divisor[0]
        inverse = divide(ONE, monomial.coefficient)
        powers = multiply_exponents(monomial.powers, -1)
        return normal_form_multiply_factor(Monomial(inverse, powers), dividend)
    return [Monomial(ONE, [(NonlinearBase("/", (dividend, divisor)), 1)])]


def zero_division():
    """nf.pl, zero_division/0: fails (`raise_exception(_) ?`)."""
    return None


def multiply_exponents(powers, factor):
    """nf.pl, multiply_exponents/3 (mult_exp/3)."""
    result = []
    for base, exponent in powers:
        result.append((base, factor * exponent))
    return result


#
# raise to integer powers
#
# | ?- time({(1+X+Y+Z)^15=0}).
# Timing 00:00:02.610     2.610   iterative
# Timing 00:00:00.660     0.660   binomial
def normal_form_power(exponent, norm, expansion=None):
    """nf.pl, normal_form_power/3 (nf_power/3): *norm* to the int
    *exponent*; None where a negative power of zero divides by zero.

    The expansion is charged before it is made (power_size) to
    *expansion*, the count of the call making it: past the
    clpq_expansion caps it raises `resource_error(clpq_expansion)`
    (DEVIATIONS.md D24): `(Y + 1)^N` costs about N^3.  The largest
    coefficient it builds is checked too (largest_coefficient_bits),
    since one big integer costs more than its bits."""
    terms, bits = power_size(abs(exponent), norm)
    limits.charge_expansion(terms, bits, "the terms of an expansion",
                            expansion)
    limits.check_coefficient(largest_coefficient_bits(abs(exponent), norm),
                             "the largest coefficient of an expansion")
    if exponent < 0:
        inverse = binomial_power(norm, -exponent)
        return normal_form_divide(inverse, [Monomial(ONE, [])])
    if exponent > 0:
        return binomial_power(norm, exponent)
    return [Monomial(ONE, [])]          # 0^0 is indeterminate but we say 1


def coefficient_bits(norm):
    """About log2 of the largest coefficient of *norm*, numerator and
    denominator together: 0 for a coefficient of 1, so a power of a
    monomial with coefficient 1 makes no bits (`Y^N`)."""
    most = 0
    for monomial in norm:
        numerator, denominator = monomial.coefficient
        bits = numerator.bit_length() + denominator.bit_length() - 2
        if bits > most:
            most = bits
    return most


def rational_log2(value):
    """log2 of the rational *value*'s numerator and denominator together,
    |N| * D: 0 for 0, 1 and -1."""
    numerator, denominator = value
    bits = 0.0
    if numerator not in (0, 1, -1):
        bits += _log2(abs(numerator))
    if denominator != 1:
        bits += _log2(denominator)
    return bits


def largest_coefficient_bits(exponent, norm):
    """About the bits of the largest coefficient of *norm* (a sum of T
    terms) to the *exponent*, before it is built: under the base's largest
    coefficient times T, to the *exponent* (the multinomial coefficients
    are under T^exponent).  Exact log2, not power_size's floor: the cost
    of one integer is superlinear in its size (limits.check_coefficient),
    so `(3*Y)^N` counts log2(3) bits for each N.  0 for an exponent under
    2, and for a power of a monomial with coefficient 1 (`Y^(10^8)`)."""
    count = len(norm)
    if exponent < 2 or count == 0:
        return 0
    most = 0.0
    for monomial in norm:
        bits = rational_log2(monomial.coefficient)
        if bits > most:
            most = bits
    if count > 1:
        most += _log2(count)
    return _times_exponent(exponent, most)


def _times_exponent(exponent, bits):
    """*exponent* times the float *bits* (a log2: 0, or at least 1),
    without the float overflow of an exponent past 2^1024: such a power
    counts *exponent* bits, under its size and past any cap but a host's
    beyond reason."""
    if not bits:
        return 0
    if exponent >= 1 << 60:
        return exponent
    return exponent * bits


def power_size(exponent, norm):
    """(terms, bits) of *norm* (a sum of T terms) to the *exponent*,
    before it is expanded: binomial(exponent + T - 1, T - 1) power
    products before like ones merge, each coefficient a product of
    *exponent* of *norm*'s and a multinomial coefficient under
    T^exponent.  The binomial is built a factor at a time and stops past
    the clpq_expansion cap, so a huge exponent costs nothing.  (0, 0) for
    an exponent under 2.  The bits are log2 of each coefficient: the
    base's largest to the *exponent*, times the multinomial's, under
    (T - 1)^exponent (none for a monomial)."""
    count = len(norm)
    if exponent < 2 or count == 0:
        return 0, 0
    cap = limits.limit("clpq_expansion")
    terms = 1
    for index in range(1, count):
        terms = terms * (exponent + index) // index
        if terms > cap:
            return terms, 0                     # raises on the terms
    per_term = exponent * (coefficient_bits(norm) + (count - 1).bit_length())
    return terms, terms * per_term


def product_size(first, second):
    """(terms, bits) of the product of two normal forms, before it is
    made: every pair of terms, each coefficient the product of two."""
    terms = len(first) * len(second)
    return terms, terms * (coefficient_bits(first) + coefficient_bits(second))


def charged_multiply(first, second, expansion=None):
    """normal_form_multiply, charged first to *expansion*, the count of the
    call making it, against the clpq_expansion caps (a product of sums
    multiplies out: 2^k terms for k factors)."""
    if len(first) > 1 and len(second) > 1:
        terms, bits = product_size(first, second)
        limits.charge_expansion(terms, bits, "the terms of an expansion",
                                expansion)
    return normal_form_multiply(first, second)


def normal_form_power_positive(exponent, norm):
    """nf.pl, normal_form_power_positive/3 (nf_power_pos/3), N > 0.  1.3.3
    no longer calls it (normal_form_power uses binomial_power); the
    recursion is a loop."""
    result = norm
    for _ in range(exponent - 1):
        result = normal_form_multiply(norm, result)
    return result


def binomial_power(norm, exponent):
    """nf.pl, binomial_power/3 (binom/3), N > 0."""
    if exponent == 1:
        return norm
    if not norm:
        return []
    first, rest = norm[0], norm[1:]
    if not rest:
        return [normal_form_power_factor(first, exponent)]
    first_powers = factor_powers(exponent, first, Monomial(ONE, []))
    rest_powers = sum_powers(exponent, rest, [Monomial(ONE, [])])
    return combine_powers(first_powers, rest_powers, 0, exponent, 1, [])


def combine_powers(first_powers, rest_powers, left, right, binomial, so_far):
    """nf.pl, combine_powers/7: the sum of binomial(N, L) * A^L * B^(N-L);
    the recursion is a loop."""
    for index in range(len(first_powers)):
        product = normal_form_multiply(first_powers[index], rest_powers[index])
        scaled = normal_form_multiply_scalar(product,
                                             arithmetic_normalize(binomial))
        so_far = normal_form_add(scaled, so_far)
        binomial = binomial * right // (left + 1)       # C1 is C*R//L1
        left += 1
        right -= 1
    return so_far


def normal_form_power_factor(monomial, exponent):
    """nf.pl, normal_form_power_factor/3 (nf_power_factor/3)."""
    return Monomial(exponential_power(monomial.coefficient,
                                      arithmetic_normalize(exponent)),
                    multiply_exponents(monomial.powers, exponent))


def factor_powers(exponent, factor, previous):
    """nf.pl, factor_powers/4: [[F^0], [F^1], ..., [F^N]] (F^0 is
    *previous*); the recursion is a loop."""
    result = []
    for _ in range(exponent):
        result.append([previous])
        previous = multiply_monomials(previous, factor)
    result.append([previous])
    return result


def sum_powers(exponent, norm, previous):
    """nf.pl, sum_powers/5: [S^N, ..., S^1, S^0] (S^0 is *previous*); the
    recursion, which builds the list from its tail, is a loop and a
    reverse."""
    result = []
    for _ in range(exponent):
        result.append(previous)
        previous = normal_form_multiply(norm, previous)
    result.append(previous)
    result.reverse()
    return result


# ------------------------------------------------------------------------------

def repair(norm):
    """nf.pl, repair/2: the normal form of *norm* after its variables were
    bound, or None where it fails.

    1.3.3's repair_power_base/2 repairs a skeleton's arguments by calling
    repair/2 again, to the nesting depth of the skeletons.  The port
    repairs every skeleton first, innermost first (_nested_bases), into a
    table that repair_power_base reads, so the only recursion left halves
    its count (test_deeply_nested_bases_repair_without_recursion).

    Its expansions are charged to a count of its own (limits.Expansion,
    kept in the table under _EXPANSION), against the clpq_expansion caps.
    A delayed constraint's repair starts from what its earlier wake-ups
    spent (limits.CARRIED) and hands the new total on, so a product of
    sums multiplied out one binding at a time is counted whole
    (DEVIATIONS.md D24)."""
    carried = limits.CARRIED.get()
    expansion = limits.Expansion() if carried is None \
        else limits.Expansion(*carried)
    try:
        return _repair(norm, expansion)
    finally:
        if carried is not None:
            limits.CARRIED.set((expansion.terms, expansion.bits))


#: The key of the repair's limits.Expansion in its table.
_EXPANSION = "expansion"


def _repair(norm, expansion):
    table = {_EXPANSION: expansion}
    for base in _nested_bases(norm):
        try:
            table[id(base)] = (True, _repair_skeleton(base, table))
        except LogicException as error:
            # raised where 1.3.3 would raise it: when the skeleton is reached
            table[id(base)] = (False, error)
    return _repair_with(norm, table)


def _repair_with(norm, table):
    result = repair_balanced(normal_form_length(norm), norm, 0, table)
    if result is None:
        return None
    return result[0]


def _nested_bases(norm):
    """Every skeleton reachable from *norm*, each once, the ones inside a
    skeleton's arguments before it.  An explicit stack."""
    order = []
    expanded = set()
    stack = []
    _push_bases(norm, stack)
    while stack:
        base, arguments_done = stack.pop()
        if arguments_done:
            order.append(base)
            continue
        if id(base) in expanded:
            continue
        expanded.add(id(base))
        stack.append((base, True))
        for argument in base.arguments:
            _push_bases(argument, stack)
    return order


def _push_bases(norm, stack):
    for monomial in norm:
        for base, _ in monomial.powers:
            base = deref(base)
            if type(base) is NonlinearBase:
                stack.append((base, False))


def repair_balanced(count, norm, start, table):
    """nf.pl, repair_balanced/4 (repair_log/4): (repaired, start + count)
    or None.  It halves *count*: depth log2(count)
    (test_long_products_and_repairs_recurse_only_to_log_depth)."""
    if count == 0:
        return [], start
    if count == 1:
        monomial = norm[start]
        result = repair_term(monomial.coefficient, monomial.powers, table)
        if result is None:
            return None
        return result, start + 1
    if count == 2:
        first = repair_term(norm[start].coefficient, norm[start].powers, table)
        if first is None:
            return None
        second = repair_term(norm[start + 1].coefficient,
                             norm[start + 1].powers, table)
        if second is None:
            return None
        return normal_form_add(first, second), start + 2
    half = count >> 1
    left = repair_balanced(half, norm, start, table)
    if left is None:
        return None
    right = repair_balanced(count - half, norm, left[1], table)
    if right is None:
        return None
    return normal_form_add(left[0], right[0]), right[1]


def repair_term(coefficient, powers, table):
    """nf.pl, repair_term/3."""
    result = repair_power_balanced(len(powers), powers, 0,
                                   [Monomial(ONE, [])], table)
    if result is None:
        return None
    repaired_powers, _, factor = result
    if len(factor) > 1:
        # a monomial times a sum: as many terms as the sum (a product of
        # sums repaired a binding at a time grows so, review N1)
        limits.charge_expansion(
            len(factor),
            len(factor) * (coefficient_bits(factor)
                           + coefficient_bits([Monomial(coefficient, [])])),
            "the terms of an expansion", table[_EXPANSION])
    return normal_form_multiply_factor(Monomial(coefficient, repaired_powers),
                                       factor)


def repair_power_balanced(count, powers, start, so_far, table):
    """nf.pl, repair_power_balanced/6 (repair_p_log/6): (the powers whose
    bases are still variables, start + count, *so_far* times the normal
    forms of the others), or None.  It halves *count*, as 1.3.3 does."""
    if count == 0:
        return [], start, so_far
    if count == 1:
        base, exponent = powers[start]
        result = repair_power(base, exponent, so_far, table)
        if result is None:
            return None
        return result[0], start + 1, result[1]
    if count == 2:
        base_x, exponent_x = powers[start]
        base_y, exponent_y = powers[start + 1]
        result_x = repair_power(base_x, exponent_x, so_far, table)
        if result_x is None:
            return None
        result_y = repair_power(base_y, exponent_y, result_x[1], table)
        if result_y is None:
            return None
        return (merge_power_products(result_x[0], result_y[0]), start + 2,
                result_y[1])
    half = count >> 1
    left = repair_power_balanced(half, powers, start, so_far, table)
    if left is None:
        return None
    right = repair_power_balanced(count - half, powers, left[1], left[2],
                                  table)
    if right is None:
        return None
    return merge_power_products(left[0], right[0]), right[1], right[2]


def repair_power(term, exponent, so_far, table):
    """nf.pl, repair_power/5 (repair_p/5): ([Term^P], so_far) for a
    variable, else ([], so_far times Term's normal form to the P); None
    where that fails."""
    term = deref(term)
    if is_var(term):
        return [(term, exponent)], so_far
    base = repair_power_base(term, table)
    if base is None:
        return None
    powered = normal_form_power(exponent, base, table[_EXPANSION])
    if powered is None:
        return None
    return [], charged_multiply(powered, so_far, table[_EXPANSION])


#
# An undigested term a/b is distinguished from an
# digested one by the fact that its arguments are
# digested -> cuts after repair of args!
#
def repair_power_base(term, table):
    """nf.pl, repair_power_base/2 (repair_p_one/2).  A digested skeleton is
    a NonlinearBase record, already repaired in *table* (see repair);
    anything else a variable was bound to is an expression for
    normal_form."""
    if is_normal_form_number(term):                         # freq. shortcut
        return normal_form_number(term)
    if type(term) is NonlinearBase:
        succeeded, result = table[id(term)]
        if not succeeded:
            raise result
        return result
    return normal_form(term)


def _repair_skeleton(term, table):
    """repair_power_base/2's clauses 2 to 5 on a skeleton whose inner
    skeletons are in *table*."""
    name = term.name
    arguments = term.arguments
    if name == "/":
        numerator = _repair_with(arguments[0], table)
        divisor = (_repair_with(arguments[1], table)
                   if numerator is not None else None)
        if divisor is not None:
            return normal_form_divide(divisor, numerator)
    elif len(arguments) == 1:
        argument = _repair_with(arguments[0], table)
        if argument is not None:
            return normal_form_nonlinear_unary(name, argument)
    else:
        first = _repair_with(arguments[0], table)
        second = (_repair_with(arguments[1], table)
                  if first is not None else None)
        if second is not None:
            return normal_form_nonlinear_binary(name, first, second)
    # 1.3.3's last clause reads the skeleton as an expression and raises
    # type_error(expression, ...) on its list argument
    # (test_a_zero_divisor_inside_a_repaired_quotient_raises).
    raise LogicException(type_error("expression", term, "normal_form/2"))


def normal_form_length(norm):
    """nf.pl, normal_form_length/3 (nf_length/3): a list knows its length."""
    return len(norm)


# ------------------------------------------------------------------------------
#
# A normal form as a term: compound cells (functor, arguments...), with
# engine numbers (to_number) for the rationals.

def normal_form_to_term(norm):
    """nf.pl, normal_form_to_term/2 (nf2term/2).  1.3.3's
    power_base_to_term/2 calls normal_form_to_term/2 on a skeleton's
    arguments, to the nesting depth of the skeletons; the port builds the
    skeletons' terms first, innermost first, into a table
    (test_deeply_nested_bases_become_terms_without_recursion)."""
    table = {}
    for base in _nested_bases(norm):
        table[id(base)] = (base.name,) + power_base_arguments_to_terms(
            base.arguments, table)
    return _normal_form_to_term_with(norm, table)


def _normal_form_to_term_with(norm, table):
    if not norm:
        return to_number(ZERO)
    return build_left_associative(norm, 1,
                                  first_monomial_to_term(norm[0], table),
                                  table)


def build_left_associative(norm, start, term, table):
    """nf.pl, build_left_associative/3 (yfx/3); the recursion is a loop."""
    for index in range(start, len(norm)):
        monomial_term, operator = next_monomial_to_term(norm[index], table)
        term = (operator, term, monomial_term)
    return term


def first_monomial_to_term(monomial, table):
    """nf.pl, first_monomial_to_term/2 (f02t/2)."""
    coefficient = monomial.coefficient
    powers = monomial.powers
    if not powers:
        return to_number(coefficient)
    if compare(coefficient, ONE) == 0:
        return power_product_to_term(powers, table)
    if compare(coefficient, MINUS_ONE) == 0:
        return ("-", power_product_to_term(powers, table))
    return ("*", to_number(coefficient), power_product_to_term(powers, table))


def next_monomial_to_term(monomial, table):
    """nf.pl, next_monomial_to_term/3 (fn2t/3): (term, operator)."""
    coefficient = monomial.coefficient
    power_term = power_product_to_term(monomial.powers, table)
    if compare(coefficient, ONE) == 0:
        return power_term, "+"
    if compare(coefficient, MINUS_ONE) == 0:
        return power_term, "-"
    if compare(coefficient, ZERO) < 0:
        return ("*", to_number(negate_rational(coefficient)), power_term), "-"
    return ("*", to_number(coefficient), power_term), "+"


def power_product_to_term(powers, table):
    """nf.pl, power_product_to_term/2 (p2term/2): `[X^P|Xs]` is
    `p2term(Xs) * X^P`; the recursion is a loop from the end."""
    last_base, last_exponent = powers[-1]
    term = exponent_to_term(last_exponent,
                            power_base_to_term(last_base, table))
    for index in range(len(powers) - 2, -1, -1):
        base, exponent = powers[index]
        term = ("*", term,
                exponent_to_term(exponent, power_base_to_term(base, table)))
    return term


def exponent_to_term(exponent, term):
    """nf.pl, exponent_to_term/3 (exp2term/3)."""
    if exponent == 1:
        return term
    if exponent == -1:
        return ("/", to_number(ONE), term)
    # Term = exp(X,Pn).
    return ("^", term, to_number(arithmetic_normalize(exponent)))


def power_base_to_term(base, table):
    """nf.pl, power_base_to_term/2 (pe2term/2): a variable, or the term of
    a skeleton, built already in *table* (see normal_form_to_term).  A
    base bound to anything but a skeleton (a number, while its delayed goal
    has not run yet) is itself: clause 2's `=..` keeps an atomic term
    (test_a_delayed_goal_on_a_bound_base_translates_to_its_value)."""
    base = deref(base)
    if type(base) is not NonlinearBase:
        return base
    return table[id(base)]


def power_base_arguments_to_terms(arguments, table):
    """nf.pl, power_base_arguments_to_terms/2 (pe2term_args/2)."""
    result = []
    for argument in arguments:
        result.append(_normal_form_to_term_with(argument, table))
    return tuple(result)


# ------------------------------------------------------------------------------
#
# The standard order of terms on power products, which 1.3.3 gets from
# compare/3.  A power `X^P` is the compound ^/2, a power product a list, a
# monomial the compound v/2 and a coefficient rat/2.

_ORDER_VARIABLE = 0
_ORDER_NUMBER = 1
_ORDER_COMPOUND = 4

# The comparisons on compare/3's work stack.
_POWER_PRODUCTS = 0
_BASES = 1
_NORMAL_FORMS = 2
_INTEGERS = 3


def compare_power_products(first, second):
    """compare/3 on two power products: -1, 0 or 1."""
    return _standard_order(_POWER_PRODUCTS, first, second)


def compare_bases(first, second):
    """compare/3 on two bases.  Two unbound variables are in creation order
    (DEVIATIONS.md D11); a base bound to a number before repair compares as
    the number."""
    return _standard_order(_BASES, first, second)


def compare_normal_forms(first, second):
    """compare/3 on two normal forms (lists of v(rat(N, D), Powers))."""
    return _standard_order(_NORMAL_FORMS, first, second)


def _order_class(term):
    if is_var(term):
        return _ORDER_VARIABLE
    if is_number(term):
        return _ORDER_NUMBER
    if type(term) is NonlinearBase:
        return _ORDER_COMPOUND
    # A base bound to a term that is no number: nf.pl reads it as an
    # expression, and its last clause raises type_error(expression, Term)
    # (test_a_base_bound_to_a_non_number_raises_a_type_error).
    raise LogicException(type_error("expression", term, "normal_form/2"))


def _standard_order(kind, first, second):
    """compare/3 on two terms of the kind given, left to right: a work
    stack of the pairs still to compare, so bases nested any depth need no
    recursion (test_deeply_nested_bases_compare_without_recursion).  A list
    is compared element by element and then by length ([] before [_|_]); a
    power X^P by X, then P; a monomial v(rat(N, D), P) by N, D, then P; a
    skeleton by arity, name, then arguments."""
    work = [(kind, first, second)]
    while work:
        kind, first, second = work.pop()
        if kind == _INTEGERS:
            if first != second:
                return -1 if first < second else 1
        elif kind == _POWER_PRODUCTS:
            work.append((_INTEGERS, len(first), len(second)))
            for index in range(min(len(first), len(second)) - 1, -1, -1):
                work.append((_INTEGERS, first[index][1], second[index][1]))
                work.append((_BASES, first[index][0], second[index][0]))
        elif kind == _NORMAL_FORMS:
            work.append((_INTEGERS, len(first), len(second)))
            for index in range(min(len(first), len(second)) - 1, -1, -1):
                monomial_a = first[index]
                monomial_b = second[index]
                work.append((_POWER_PRODUCTS, monomial_a.powers,
                             monomial_b.powers))
                work.append((_INTEGERS, monomial_a.coefficient[1],
                             monomial_b.coefficient[1]))
                work.append((_INTEGERS, monomial_a.coefficient[0],
                             monomial_b.coefficient[0]))
        else:
            first = deref(first)
            second = deref(second)
            if first is second:
                continue
            class_a = _order_class(first)
            class_b = _order_class(second)
            if class_a != class_b:
                return -1 if class_a < class_b else 1
            if class_a == _ORDER_VARIABLE:
                if first._id != second._id:
                    return -1 if first._id < second._id else 1
            elif class_a == _ORDER_NUMBER:
                if first != second:
                    return -1 if first < second else 1
            else:
                arity_a = len(first.arguments)
                arity_b = len(second.arguments)
                if arity_a != arity_b:
                    return -1 if arity_a < arity_b else 1
                if first.name != second.name:
                    return -1 if first.name < second.name else 1
                for index in range(arity_a - 1, -1, -1):
                    work.append((_NORMAL_FORMS, first.arguments[index],
                                 second.arguments[index]))
    return 0


def term_variables_set(term):
    """library(terms) term_variables_set/2 on a normal form, a list of
    monomials or a power product: its unbound variables, each once, in
    creation order.  An explicit stack."""
    seen = set()
    variables = []
    stack = [term]
    while stack:
        item = stack.pop()
        kind = type(item)
        if kind is list:
            stack.extend(item)
        elif kind is Monomial:
            stack.append(item.powers)
        elif kind is tuple:                 # a power (base, exponent)
            base = deref(item[0])
            if is_var(base):
                if base._id not in seen:
                    seen.add(base._id)
                    variables.append(base)
            elif type(base) is NonlinearBase:
                stack.extend(base.arguments)
    variables.sort(key=_creation)
    return variables


def _creation(variable):
    return variable._id


# ============================================================== nfq.pl

def translate_goal(procedure, argument):
    """nfq.pl, translate_goal//1 (transg//1): a delayed goal as the goals
    dump.pl shows, each `M:Goal` as the cell (":", M, Goal) with M the
    solver module "clpq".  resubmit_*(Nf) is `clpq:{Term Rel 0}`;
    wait_linear_retry(Nf, Res, Goal) is `[clpq:{Term = Res}, Goal]`, where
    Goal is `clpq:Name(Res, Arguments...)` (1.3.3's goal is the bv.pl or
    bb.pl call, module-qualified by wait_linear/3's meta-argument; the port
    names it after the procedure).  bb.pl's goal has Res second, as
    bb.pl:22 writes `bb_inf_internal(Is, Nf, EpsN, Inf, Vertex)`
    (test_the_delayed_goal_shows_nf_second).  Raises ValueError for a goal
    nf.pl does not delay, where 1.3.3's translate_goal//1 fails."""
    if procedure is resubmit_equal:
        return [_solver_constraint("=", argument, normal_form_to_term([]))]
    if procedure is resubmit_less_than:
        return [_solver_constraint("<", argument, normal_form_to_term([]))]
    if procedure is resubmit_less_or_equal:
        return [_solver_constraint("=<", argument, normal_form_to_term([]))]
    if procedure is resubmit_not_equal:
        return [_solver_constraint("=\\=", argument, normal_form_to_term([]))]
    if procedure is wait_linear_retry:
        from clausal.logic.clpq.branch_and_bound import (  # cyclic: bb.pl
            branch_and_bound_infimum_internal)
        result = argument.result
        goal_argument = argument.argument
        if argument.procedure is branch_and_bound_infimum_internal:
            integer_variables, epsilon, infimum, vertex = goal_argument
            goal = (argument.procedure.__name__, integer_variables, result,
                    to_number(epsilon), infimum, vertex)
        elif goal_argument is None:
            goal = (argument.procedure.__name__, result)
        elif type(goal_argument) is tuple:
            goal = (argument.procedure.__name__, result) + goal_argument
        else:
            goal = (argument.procedure.__name__, result, goal_argument)
        return [_solver_constraint("=", argument.normal_form, result),
                (":", SOLVER_MODULE, goal)]
    raise ValueError(f"translate_goal: not a goal nf.pl delays: {procedure!r}")


def _solver_constraint(relation, norm, right):
    """`clpq:{Term Rel Right}` with Term = nf2term(Nf)."""
    return (":", SOLVER_MODULE,
            ("{}", (relation, normal_form_to_term(norm), right)))
