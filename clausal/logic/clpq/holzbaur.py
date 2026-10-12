"""The legacy CLP(Q) API on the port of clp(q,r) 1.3.3 (CLAUSAL_CLPQ=holzbaur).

Every name and signature here is legacy.py's, so the package can export
either solver behind the same names (clausal/logic/clpq/__init__.py).  Each
entry point does what legacy's does at the boundary and hands the rest to
the port:

- an arithmetic cell becomes its operator node (``_cells_as_nodes``,
  ruling R9 A1), and the units side channel strips a Quantity or a united
  variable to its solver number or shadow (``_units_strip``,
  ``_units_strip_expr``); both are legacy.py's, which never touch its
  tableau;
- the constraint goes to nf.pl's ``{}/1`` (``normal_form.post_constraint``),
  the optimisers to bv.pl's ``inf``/``sup``/``minimize``/``maximize``,
  ``bb_inf`` to bb.pl's, ``entailed`` to nf.pl's, ``dump_q`` to dump.pl's
  ``dump/3`` (``residual_constraints.residual_strings``);
- an optimum comes back through ``_units_result``, as legacy presents it.

Where the port answers as 1.3.3 does and legacy did not, the port's answer
stands: a non-linear constraint waits (nf.pl) instead of raising
TypeError, ``maximize``/``minimize`` post ``{Expr =:= Optimum}`` and bind
only what that implies (bv.pl), and ``bb_inf`` binds Inf alone (bb.pl).

Decimal scale.  ``X == Decimal('2.50')`` with X a variable unifies X with
the number itself (``present_number``), as legacy's fast path does, so a
currency amount keeps its scale; through nf.pl it would come back as the
rational 5/2 (``arithmetic.to_number``).
(test_switch.py, test_a_decimal_keeps_its_scale_through_an_equation)

The rule for calls from another constraint library (ruling R28).  No
attribute hook body may call an entry point of the port (ruling R27,
DEVIATIONS.md D3): a hook runs while other variables of the same
unification are bound with their hooks still to come, and an entry point
reads rows and member lists that hold those bindings.  clpfd calls
``q_eq``, ``q_ne``, ``q_le``, ``q_lt`` (and ``q_gt``, ``q_ge`` through
them) and ``sync_fd_bounds`` from its propagation, which runs inside the
FD hook, from its reified comparisons and from the units hook.  So these
functions do not post in place while a component the post reads holds a
member that is bound with its CLPQ_KEY hook still to come: they queue the
post on the trail's pending queue (``trail.push_pending`` of a
``QueuedPost``) and return True, and the post runs after every hook of the
unification.  Otherwise they post in place.

Why not queue whenever ``trail.defer`` is True, as R28 is worded: under a
driver ``defer`` is True at every goal, not only inside a hook, and a
compiled comparison (``X =< 10`` in a seam clause, lowered to ``fd_le``)
is not followed by a goal boundary, so the queued post would run only
after the next goals had read the store without it: ``in_q(X, 0, 100), X
=< 10, X >= 3, inf(X, Lo)`` gave ``Lo = 0``
(tests/test_clpq.py::TestClausalIntegration::test_sup_inf, and
test_switch.py, test_a_comparison_from_clpfd_at_a_goal_is_posted_in_place).
Outside a hook's window no member is bound (each hook puts a stand-in in
place of its variable before it returns), so the check queues exactly
the posts R27 forbids.  ``{}`` (``clpq_constraint_block``) and the
optimisers are goals, never called from a hook, and post in place.

``{C1 ; C2}`` (ruling R18, DEVIATIONS.md D12).  A block that holds ``;``
is posted with ``post_constraint_with_choices``, and
``clpq_constraint_answers`` yields one answer per branch, resuming the
choice points with ``resume_constraint`` on backtracking.  The engine
does not undo a builtin's bindings before asking it for the next answer,
so the trail is still above the post when ``resume_constraint`` undoes to
the newest choice point, which is D12's precondition.
"""
from decimal import Decimal
from fractions import Fraction

from clausal.logic.clpq import bounded_simplex as _bounded_simplex
from clausal.logic.clpq import branch_and_bound as _branch_and_bound
from clausal.logic.clpq import normal_form as _normal_form
from clausal.logic.clpq import residual_constraints as _residual_constraints
from clausal.logic.clpq import variable_ordering as _variable_ordering
from clausal.logic.clpq.attribute_hooks import _own_state
from clausal.logic.clpq.attributes import CLPQ_KEY, state_of
from clausal.logic.clpq.components import (
    component_all_variables, list_elements)
from clausal.logic.clpq.legacy import (
    _cell_as_node, _cells_as_nodes, _units_result, _units_strip,
    _units_strip_expr)
from clausal.logic.variables import (
    AttVar, PlainVar, Var, deref, get_attr, is_var, present_number, unify)
from clausal.pythonic_ast.nodes import (
    ArithEq, ArithNeq, CompareChain, Gt, GtE, Lt, LtE)

#: The attribute key of a constrained variable, for clpfd's FD-to-Q
#: dispatch (``get_attr(X, Q_KEY)``) and sandbox.py's allowlist.
Q_KEY = CLPQ_KEY

#: entailed/4's constraint_type -> the node nf.pl's entailed/1 takes.
_ENTAILED_NODES = {"=<": LtE, "<=": LtE, ">=": GtE, "=>": GtE, "<": Lt,
                   ">": Gt, "=": ArithEq, "=:=": ArithEq, "\\=": ArithNeq,
                   "=\\=": ArithNeq}

#: The comparison nodes a block holds, and the context legacy names in a
#: units error for each.
_BLOCK_CONTEXTS = {ArithEq: "(==)/2", ArithNeq: "(!=)/2", LtE: "(=<)/2",
                   Lt: "(<)/2", GtE: "(>=)/2", Gt: "(>)/2"}

_label_targets = None


def _labels(variables, context):
    """units_clp.label_targets: each united variable as its shadow."""
    global _label_targets
    if _label_targets is None:
        from clausal.logic.units_clp import label_targets  # noqa: PLC0415
        _label_targets = label_targets
    return _label_targets(variables, context)


def _is_ground_number(x):
    return isinstance(x, (int, Fraction, Decimal)) and not isinstance(x, bool)


# ---------------------------------------------------------------- posting

def _variables_of(*terms):
    """The unbound variables in the expression trees *terms*."""
    found = []
    seen = set()
    stack = list(terms)
    while stack:
        term = deref(stack.pop())
        if is_var(term):
            if term._id not in seen:
                seen.add(term._id)
                found.append(term)
            continue
        if type(term) is list:
            stack.extend(term)
            continue
        functor, arguments = _normal_form._functor_and_arguments(term)
        if functor is not None:
            stack.extend(arguments)
    return found


def _promote_fd_variables(left, right, trail):
    """legacy's _ensure_q_for_expr for an FD variable: a variable with a
    finite-domain attribute and no CLP(Q) state gets its FD bounds as
    rational bounds before the post (ruling R4).  True, or False where a
    bound fails."""
    from clausal.logic.clpfd import FD_KEY  # noqa: PLC0415
    for variable in _variables_of(left, right):
        if type(variable) is PlainVar or state_of(variable) is not None:
            continue
        fd_state = get_attr(variable, FD_KEY)
        if fd_state is not None:
            if not promote_fd_to_q(variable, fd_state, trail):
                return False
    return True


def promote_fd_to_q(variable, fd_state, trail):
    """The FD variable *variable* as a CLP(Q) variable: its finite-domain
    bounds posted as `{Lo =< X, X =< Hi}` (an infinite end is left open).
    The FD attribute stays, so both solvers see the variable, as legacy's
    _promote_fd_to_q does."""
    from clausal.logic.clpfd import domain_max, domain_min  # noqa: PLC0415
    lower = domain_min(fd_state.domain)
    upper = domain_max(fd_state.domain)
    return _post_bounds(variable, lower, upper, trail)


def _post_bounds(variable, lower, upper, trail):
    constraints = []
    if type(lower) is int:
        constraints.append(GtE(left=variable, right=lower))
    if type(upper) is int:
        constraints.append(LtE(left=variable, right=upper))
    if not constraints:
        return _make_constrained(variable, trail)
    return _normal_form.post_constraint(constraints, trail)


def _make_constrained(variable, trail):
    """bv.pl var_intern/2: *variable* becomes a linear variable without
    bounds, so it carries CLPQ_KEY state (in_q/1, rational/1)."""
    return _bounded_simplex.variable_intern(variable, trail) is not None


def _post_now(node_class, left, right, trail):
    """One comparison through nf.pl's {}/1, after the FD promotion.  A
    variable against a number, for ``=``, is the unification itself
    (legacy's fast path: present_number keeps a Decimal's scale)."""
    if node_class is ArithEq:
        if is_var(left) and _is_ground_number(right):
            return unify(left, present_number(right), trail)
        if is_var(right) and _is_ground_number(left):
            return unify(right, present_number(left), trail)
    if _is_ground_number(left) and _is_ground_number(right):
        return _compare_numbers(node_class, Fraction(left), Fraction(right))
    if not _promote_fd_variables(left, right, trail):
        return False
    return _normal_form.post_constraint(node_class(left=left, right=right),
                                        trail)


def _compare_numbers(node_class, left, right):
    if node_class is ArithEq:
        return left == right
    if node_class is ArithNeq:
        return left != right
    if node_class is LtE:
        return left <= right
    if node_class is Lt:
        return left < right
    if node_class is GtE:
        return left >= right
    return left > right


class QueuedPost:
    """A post a constraint library made under ``trail.defer``, as a goal on
    the trail's pending queue (ruling R28): a zero-argument factory with
    one answer or none, as attribute_hooks.PendingLater is."""
    __slots__ = ("node_class", "left", "right", "trail")

    def __init__(self, node_class, left, right, trail):
        self.node_class = node_class
        self.left = left
        self.right = right
        self.trail = trail

    def __call__(self):
        if _post_now(self.node_class, deref(self.left), deref(self.right),
                     self.trail):
            return (None,)
        return ()


def _post_from_library(node_class, left, right, trail):
    """A comparison from clpfd (fd_eq and the others, its Python and its C
    form): queued while it may run inside a hook's window, posted in place
    otherwise (ruling R28 as the module docstring states it)."""
    if trail.defer and _reads_unhooked_bindings(left, right):
        trail.push_pending(QueuedPost(node_class, left, right, trail))
        return True
    return _post_now(node_class, left, right, trail)


def _reads_unhooked_bindings(*terms):
    """True when a component a post on *terms* reads holds a member that a
    unification has bound and whose CLPQ_KEY hook has not run yet: the
    window of DEVIATIONS.md D3 (ruling R27).  After a unification's hooks
    have run no member is bound (each hook puts a stand-in in place of its
    variable), so at a goal this is False and the post is made in place
    (test_switch.py, test_a_comparison_from_clpfd_inside_a_hook_is_queued
    and test_a_comparison_from_clpfd_at_a_goal_is_posted_in_place)."""
    seen = set()
    for variable in _variables_of(*terms):
        state = state_of(variable)
        if state is None or state.component is None:
            continue
        component = deref(state.component)
        if id(component) in seen:
            continue
        seen.add(id(component))
        for member in list_elements(component_all_variables(component)):
            if type(member) is AttVar and member.is_bound \
                    and _own_state(member) is not None:
                return True
    return False


def _prepare(left, right, context, trail):
    left, right = _cells_as_nodes(deref(left), deref(right), context)
    return _units_strip(left, right, context, trail)


def q_eq(l, r, trail):
    """Post l == r (nf.pl {L =:= R})."""
    l, r = _prepare(l, r, "(==)/2", trail)
    return _post_from_library(ArithEq, l, r, trail)


def q_ne(l, r, trail):
    """Post l != r (nf.pl {L =\\= R})."""
    l, r = _prepare(l, r, "(!=)/2", trail)
    return _post_from_library(ArithNeq, l, r, trail)


def q_le(l, r, trail):
    """Post l <= r (nf.pl {L =< R})."""
    l, r = _prepare(l, r, "(=<)/2", trail)
    return _post_from_library(LtE, l, r, trail)


def q_lt(l, r, trail):
    """Post l < r (nf.pl {L < R})."""
    l, r = _prepare(l, r, "(<)/2", trail)
    return _post_from_library(Lt, l, r, trail)


def q_gt(l, r, trail):
    """Post l > r (nf.pl {L > R})."""
    l, r = _prepare(l, r, "(>)/2", trail)
    return _post_from_library(Gt, l, r, trail)


def q_ge(l, r, trail):
    """Post l >= r (nf.pl {L >= R})."""
    l, r = _prepare(l, r, "(>=)/2", trail)
    return _post_from_library(GtE, l, r, trail)


def sync_fd_bounds(variable, lower, upper, trail):
    """clpfd narrowed the domain of *variable*, which has CLP(Q) state, to
    [lower, upper]: post those bounds (an infinite end is left open).
    clpfd's propagation calls this, so it may run inside a hook: queued
    as _post_from_library queues (ruling R28)."""
    variable = deref(variable)
    if not is_var(variable):
        return True
    if trail.defer and _reads_unhooked_bindings(variable):
        if type(lower) is int:
            trail.push_pending(QueuedPost(GtE, variable, lower, trail))
        if type(upper) is int:
            trail.push_pending(QueuedPost(LtE, variable, upper, trail))
        return True
    return _post_bounds(variable, lower, upper, trail)


# ---------------------------------------------------------------- in_q

def in_q(var_or_list, lo=None, hi=None, trail=None):
    """Declare variable(s) rational with optional bounds ``[lo, hi]``:
    ``{lo =< X, X =< hi}``, or bv.pl's var_intern/2 when there is no
    bound.  A Quantity bound declares the dimension too, as legacy's
    in_q does (units_clp's shadow carries the bounds)."""
    targets = deref(var_or_list)
    lo, hi = deref(lo), deref(hi)
    united = _in_q_units(targets, lo, hi, trail)
    if united is not None:
        return united
    if lo is not None:
        lo = Fraction(lo)
    if hi is not None:
        hi = Fraction(hi)
    for target in (targets if isinstance(targets, list) else [targets]):
        if not _declare(deref(target), lo, hi, trail):
            return False
    return True


def _declare(target, lower, upper, trail):
    if isinstance(target, bool):
        return False
    if _is_ground_number(target):
        value = Fraction(target)
        return ((lower is None or value >= lower)
                and (upper is None or value <= upper))
    if not is_var(target):
        return False
    if lower is not None and upper is not None and lower > upper:
        return False
    constraints = []
    if lower is not None:
        constraints.append(GtE(left=target, right=present_number(lower)))
    if upper is not None:
        constraints.append(LtE(left=target, right=present_number(upper)))
    if not constraints:
        if state_of(target) is not None:
            return True
        return _make_constrained(target, trail)
    return _normal_form.post_constraint(constraints, trail)


def _in_q_units(targets, lo, hi, trail):
    """legacy's _in_q_units with the port posting the bounds: None when
    neither bound is a Quantity."""
    from clausal.logic import _units_flag  # noqa: PLC0415
    if not _units_flag.active:
        return None
    from clausal.terms import Quantity  # noqa: PLC0415
    lo_q, hi_q = isinstance(lo, Quantity), isinstance(hi, Quantity)
    if not (lo_q or hi_q):
        return None
    from clausal.logic import units_clp  # noqa: PLC0415
    from clausal.logic.units_constraint import UNITS_KEY, to_solver_number  # noqa: PLC0415
    context = "in_q/3"
    if not (lo_q and hi_q):
        quantity, plain = (lo, hi) if lo_q else (hi, lo)
        if plain is not None:
            raise units_clp._mismatch_text(
                context, f"bound {plain!r} is a plain number beside {quantity!r}")
        dims = dict(quantity.dims)
    else:
        if dict(lo.dims) != dict(hi.dims):
            raise units_clp._mismatch(context, dict(lo.dims), dict(hi.dims))
        dims = dict(lo.dims)
    lower = Fraction(to_solver_number(lo.value)) if lo_q else None
    upper = Fraction(to_solver_number(hi.value)) if hi_q else None
    as_list = isinstance(targets, list)
    shadows = []
    for v in (targets if as_list else [targets]):
        v = deref(v)
        if isinstance(v, Quantity):
            if dict(v.dims) != dims:
                raise units_clp._mismatch(context, dict(v.dims), dims)
            shadows.append(to_solver_number(v.value))
            continue
        if not is_var(v):
            raise units_clp._mismatch(context, {}, dims, f"target {v!r}")
        state = get_attr(v, UNITS_KEY)
        if state is not None and state.dims != dims:
            raise units_clp._mismatch(context, state.dims, dims)
        if not dims:
            shadows.append(v)
            continue
        if state is None and (get_attr(v, Q_KEY) is not None
                              or get_attr(v, "fd") is not None
                              or get_attr(v, "real") is not None):
            raise units_clp._mismatch(
                context, {}, dims,
                f"target {v!r} is already a bare solver variable")
        units_clp._refuse_bypassed(v, context)
        shadows.append(units_clp.shadow_for(v, dims, trail))
    for shadow in shadows:
        if not _declare(deref(shadow), lower, upper, trail):
            return False
    return True


# ---------------------------------------------------------------- optima

def _without_a_queue(trail, call):
    """Run *call* with no goals queued from before it.  Outside a driver a
    queue left on the trail would be run by the port's own drain, and run
    again by its owner (Task 13c); so it is set aside and put back, in
    front of anything *call* queued.  Under a driver the port's drains
    never run it (the queue's owner does)."""
    if trail.defer or trail.pending is None:
        return call()
    earlier = trail.take_pending()
    try:
        return call()
    finally:
        later = trail.take_pending()
        for goal in earlier:
            trail.push_pending(goal)
        if later is not None:
            for goal in later:
                trail.push_pending(goal)


def _optimum(port_call, expr, result_var, dims, trail):
    """bv.pl's inf/2 or sup/2 into *result_var*.  With a dimension the
    optimum goes to a fresh variable first and comes back as a Quantity."""
    if not dims:
        return _without_a_queue(
            trail, lambda: port_call(expr, result_var, trail))
    value = Var()
    if not _without_a_queue(trail, lambda: port_call(expr, value, trail)):
        return False
    number = deref(value)
    if is_var(number):                  # the objective waits (not linear)
        return unify(result_var, value, trail)
    return unify(result_var, _units_result(Fraction(number), dims), trail)


def _objective(expr, context, trail):
    expr = _cell_as_node(deref(expr), context)
    return _units_strip_expr(expr, context, trail)


def sup(expr, result_var, trail):
    """bv.pl sup/2: the supremum of *expr*; fails where it is unbounded."""
    expr, dims = _objective(expr, "sup/2", trail)
    return _optimum(_bounded_simplex.sup, expr, deref(result_var), dims,
                    trail)


def inf(expr, result_var, trail):
    """bv.pl inf/2: the infimum of *expr*; fails where it is unbounded."""
    expr, dims = _objective(expr, "inf/2", trail)
    return _optimum(_bounded_simplex.inf, expr, deref(result_var), dims,
                    trail)


def maximize(expr, result_var, trail):
    """bv.pl maximize/1, then *result_var* is the maximum: sup/2 first, so
    an unbounded objective fails as legacy's does."""
    expr, dims = _objective(expr, "maximize/2", trail)
    value = Var()
    if not _without_a_queue(
            trail, lambda: _bounded_simplex.sup(expr, value, trail)):
        return False
    if not _without_a_queue(
            trail, lambda: _bounded_simplex.maximize(expr, trail)):
        return False
    return _bind_optimum(value, result_var, dims, trail)


def minimize(expr, result_var, trail):
    """bv.pl minimize/1, then *result_var* is the minimum."""
    expr, dims = _objective(expr, "minimize/2", trail)
    value = Var()
    if not _without_a_queue(
            trail, lambda: _bounded_simplex.inf(expr, value, trail)):
        return False
    if not _without_a_queue(
            trail, lambda: _bounded_simplex.minimize(expr, trail)):
        return False
    return _bind_optimum(value, result_var, dims, trail)


def _bind_optimum(value, result_var, dims, trail):
    number = deref(value)
    if is_var(number) or not dims:
        return unify(result_var, number, trail)
    return unify(result_var, _units_result(Fraction(number), dims), trail)


def bb_inf(int_vars, expr, result_var, trail):
    """bb.pl bb_inf/3: the infimum of *expr* with every variable of
    *int_vars* integral.  Binds *result_var* alone; the store is as it was
    (1.3.3's shape, Task 13).  A united variable's shadow is the integer."""
    expr, dims = _objective(expr, "bb_inf/3", trail)
    integers = _labels(deref(int_vars), "bb_inf/3")
    return _optimum(
        lambda objective, value, trail: _branch_and_bound.bb_inf(
            integers, objective, value, trail),
        expr, deref(result_var), dims, trail)


# ---------------------------------------------------------------- entailed

def entailed(constraint_type, l, r, trail):
    """nf.pl entailed/1 for ``l constraint_type r``.  The store is left as
    it was."""
    node_class = _ENTAILED_NODES.get(constraint_type)
    if node_class is None:
        raise ValueError(f"Unknown constraint type: {constraint_type!r}")
    l, r = _prepare(l, r, "entailed/1", trail)
    return _without_a_queue(
        trail, lambda: _normal_form.entailed(node_class(left=l, right=r),
                                             trail))


# ---------------------------------------------------------------- residuals

def _named_targets(target_vars, context, name_of):
    """The targets with each united variable as its shadow, and a namer
    that names a shadow as the variable the program wrote."""
    target_vars = list(target_vars)
    shadows = _labels(target_vars, context)
    names = {}
    for variable, shadow in zip(target_vars, shadows):
        variable, shadow = deref(variable), deref(shadow)
        if is_var(shadow):
            names.setdefault(shadow._id, variable)
    internal = {}

    def name(variable):
        # A variable dump/3 keeps that is not a target (a slack of a
        # disequation) is named _Q1, _Q2, ... as legacy names its internal
        # variables: name_of is asked about targets only.
        original = names.get(variable._id)
        if original is None:
            if variable._id not in internal:
                internal[variable._id] = f"_Q{len(internal) + 1}"
            return internal[variable._id]
        return str(original) if name_of is None else name_of(original)
    return shadows, name


def dump_q(target_vars, trail, name_of=None, *, toplevel=False):
    """dump.pl dump/3 on *target_vars*, as the strings the ``-g`` printer
    shows (``{X + Y = 3}``).  *toplevel* is accepted for legacy's
    signature: dump/3 already writes each constraint as 1.3.3 shows an
    answer."""
    shadows, name = _named_targets(target_vars, "dump_q/2", name_of)
    return _without_a_queue(
        trail, lambda: _residual_constraints.residual_strings(
            shadows, trail, name))


def residual_q(target_vars, trail, name_of):
    """The CLP(Q) constraints on *target_vars* as a toplevel prints them;
    ``[]`` when none of them carries CLP(Q) state."""
    return dump_q(target_vars, trail, name_of, toplevel=True)


# ---------------------------------------------------------------- ordering

def ordering(spec, trail):
    """ordering.pl ordering/1: *spec* is a list of variables or a ``<`` /
    ``>`` between two (an operator node or a cell)."""
    spec = deref(spec)
    kind = type(spec)
    if kind is Lt:
        spec = ("<", spec.left, spec.right)
    elif kind is Gt:
        spec = (">", spec.left, spec.right)
    return _variable_ordering.ordering(spec, trail)


# ---------------------------------------------------------------- {}
#
# A block is read into a tree first: a leaf is (node class, left, right,
# context) with the cells made nodes; a conjunction is a Python list of
# trees; `,` and `;` are [functor, tree, tree].  Explicit stacks: a long
# conjunction nests no frames.

def _block_tree(constraints):
    """(tree, holds a `;`) for the block *constraints*: a comparison node, a
    tuple or list of them, a CompareChain, or `,`/`;` cells."""
    disjunctive = False
    root = [deref(constraints)]
    work = [(root, 0)]
    while work:
        holder, index = work.pop()
        term = deref(holder[index])
        kind = type(term)
        if kind is list or (kind is tuple and term
                            and type(term[0]) is not str):
            elements = list(term)
        elif kind is CompareChain:
            elements = list(term.comparisons)
        elif kind is tuple and len(term) == 3 and term[0] in (",", ";"):
            disjunctive = disjunctive or term[0] == ";"
            branch = [term[0], term[1], term[2]]
            holder[index] = branch
            work.append((branch, 1))
            work.append((branch, 2))
            continue
        else:
            context = _BLOCK_CONTEXTS.get(kind)
            if context is None:
                raise TypeError(
                    f"clpq constraint block: unsupported node "
                    f"{kind.__name__}: {term}")
            left, right = _cells_as_nodes(deref(term.left),
                                          deref(term.right), context)
            holder[index] = (kind, left, right, context)
            continue
        holder[index] = elements
        for position in range(len(elements)):
            work.append((elements, position))
    return root[0], disjunctive


def _is_branch(tree):
    return type(tree) is list and len(tree) == 3 and type(tree[0]) is str


def _leaves(tree):
    """The comparisons of *tree*, in the order written."""
    leaves = []
    stack = [tree]
    while stack:
        item = stack.pop()
        if _is_branch(item):
            stack.append(item[2])
            stack.append(item[1])
        elif type(item) is list:
            for position in range(len(item) - 1, -1, -1):
                stack.append(item[position])
        else:
            leaves.append(item)
    return leaves


def _as_term(tree, trail):
    """*tree* as the term nf.pl's {}/1 reads: each comparison a node after
    the units side channel (in the order written), `,`/`;` cells, a
    conjunction a list.  Built bottom up from a post-order walk."""
    results = []
    stack = [(tree, False)]
    while stack:
        item, ready = stack.pop()
        if _is_branch(item):
            if ready:
                second = results.pop()
                first = results.pop()
                results.append((item[0], first, second))
            else:
                stack.append((item, True))
                stack.append((item[2], False))
                stack.append((item[1], False))
        elif type(item) is list:
            if ready:
                count = len(item)
                elements = results[len(results) - count:]
                del results[len(results) - count:]
                results.append(elements)
            else:
                stack.append((item, True))
                for position in range(len(item) - 1, -1, -1):
                    stack.append((item[position], False))
        else:
            kind, left, right, context = item
            left, right = _units_strip(left, right, context, trail)
            results.append(kind(left=left, right=right))
    return results[0]


def clpq_constraint_block(constraints, trail):
    """Post the constraints of a ``{...}`` block; True or False.  A block
    that holds ``;`` has several answers and goes through
    clpq_constraint_answers (ruling R18); here it raises TypeError, as
    legacy's does for a node it cannot post."""
    tree, disjunctive = _block_tree(constraints)
    if disjunctive:
        raise TypeError("clpq constraint block: a disjunction has several "
                        "answers; post it with clpq_constraint_answers")
    return _post_leaves(tree, trail)


def _post_leaves(tree, trail):
    """Each comparison in turn, as legacy's block posts them (so
    ``X == 2.50`` keeps its Decimal scale)."""
    for kind, left, right, context in _leaves(tree):
        left, right = _units_strip(left, right, context, trail)
        if not _post_now(kind, left, right, trail):
            return False
    return True


def clpq_constraint_answers(constraints, trail):
    """The answers of a ``{...}`` block, one per branch of each ``;``
    (ruling R18): a generator the engine backtracks into.  An answer keeps
    its bindings; the next request resumes the newest choice point
    (DEVIATIONS.md D12), and after the last the trail is undone to where
    the block started."""
    tree, disjunctive = _block_tree(constraints)
    if not disjunctive:
        if _post_leaves(tree, trail):
            yield None
        return
    mark = trail.mark()
    try:
        term = _as_term(tree, trail)
        if not _promote_fd_variables(term, None, trail):
            return
        state = _normal_form.post_constraint_with_choices(term, trail)
        if state is None:
            return
        yield None
        while _normal_form.resume_constraint(state, trail):
            yield None
    finally:
        trail.undo(mark)
