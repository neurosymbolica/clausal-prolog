# Ported from clp(q,r) version 1.3.3, file geler.pl
# (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
# Artificial Intelligence (OFAI).  Author: Christian Holzbaur.
# See clausal/logic/clpq/PROVENANCE.md.
"""Delayed goals: geler.pl, non-linear goals that wait for a binding.

The goal interface.  1.3.3 delays a Prolog goal (`resubmit_equal(Norm)` and
the like, nf.pl) and runs it with call/1.  The port delays a pair
(procedure, argument): running it is `procedure(argument, trail) -> bool`,
True for success and False for failure, deterministic.  nf.pl's goals
(Task 10) are module-level functions of that shape.  collect_nonlinear
hands each pair to nfq.pl's translate_goal (a parameter; see translate),
and dump.pl (Task 12) reads the translated goals.

geler.pl's `goals/1` attribute is SolverState's `delayed_goals` field: a
tuple of DelayedGoal, newest first (1.3.3's conjunction `(Goal, Gv)`), or
None for no attribute.  verify_delayed is the part of the CLPQ_KEY hook
(attribute_hooks.verify_attributes calls it) that geler.pl's
verify_attributes/3 does; its Later goals go on a LaterWork queue and run
after the hook returns
(test_verify_delayed_against_a_value_queues_the_goals).
"""
from clausal.logic.clpq.attributes import (
    SolverState, put_state, state_of, with_changes)
from clausal.logic.variables import PlainVar, Var, deref, is_var, unify

DONE = "done"


class DelayedGoal:
    """geler.pl's `run(Mutex, Goal)`: *mutex* is a variable bound to `done`
    once the goal has run."""
    __slots__ = ("mutex", "procedure", "argument")

    def __init__(self, mutex, procedure, argument):
        self.mutex = mutex
        self.procedure = procedure
        self.argument = argument


class RunGoals:
    """A Later entry: the goals of one `goals/1` attribute, run in order.
    LaterWork calls it with no arguments."""
    __slots__ = ("goals", "trail")

    def __init__(self, goals, trail):
        self.goals = goals
        self.trail = trail

    def __call__(self):
        for goal in self.goals:
            if not run(goal, self.trail):
                return False
        return True


# ---------------------------------------------------------------- geler.pl

def attribute_goal(variable):
    """geler.pl, attribute_goal/2, first clause: the goals not yet run, as
    (procedure, argument) pairs, or None where it fails (none left).  The
    second clause reads `all_nonlinear/1`, which the port does not keep
    (DEVIATIONS.md D7)."""
    state = state_of(variable)
    if state is None or state.delayed_goals is None:
        return None
    goals = []
    for goal in nonexhausted(state.delayed_goals):
        goals.append((goal.procedure, goal.argument))
    if not goals:
        return None
    return goals


def nonexhausted(goals):
    """geler.pl, nonexhausted//1: the goals whose Mutex is unbound."""
    result = []
    for goal in goals:
        if is_var(deref(goal.mutex)):
            result.append(goal)
    return result


def verify_delayed(state, other, trail, later):
    """geler.pl, verify_attributes/3, for a variable X with *state* bound to
    *other* (Y).  Pushes Later onto *later*.  geler.pl's hook does not fail;
    the port returns False only for a Y that cannot carry attributes (a
    PlainVar): X's goals cannot move onto it, and dropping them would lose
    the constraint (test_verify_delayed_onto_a_plain_var_fails_closed)."""
    if state is None or state.delayed_goals is None:            # clause 2
        return True
    goals = state.delayed_goals
    other = deref(other)
    if is_var(other):
        if type(other) is PlainVar:
            return False
        state_other = state_of(other)
        if state_other is not None and state_other.delayed_goals is not None:
            later.push(RunGoals(goals, trail))                  # Later = [Gx, Gy]
            later.push(RunGoals(state_other.delayed_goals, trail))
            put_state(other, with_changes(state_other, delayed_goals=None),
                      trail)                                    # -goals(_)
        else:
            _put_goals(other, state_other, goals, trail)        # Later = []
    else:
        later.push(RunGoals(goals, trail))                      # Later = [Gx]
    return True


def project_nonlinear(target_variables, constrained_variables, trail,
                      translate_goal=None):
    """geler.pl, project_nonlinear/3: collect the goals not yet run on
    *constrained_variables* (marking them run), translated by
    *translate_goal* (see translate), and return the variables the
    translated goals reach (term_variables_set/2).  1.3.3 also sorts the
    goals and puts them on a fresh variable as `all_nonlinear/1`; nothing
    reads that variable, and the port leaves both out (DEVIATIONS.md D7).
    The variables come in creation order; project.pl only marks each one."""
    goals = collect_nonlinear(constrained_variables, trail, translate_goal)
    return _term_variables(goals)


def collect_nonlinear(variables, trail, translate_goal=None):
    """geler.pl, collect_nonlinear//1: the translated goals not yet run on
    *variables*; each goal is marked run (translate//1)."""
    result = []
    for variable in variables:
        state = state_of(variable)
        if state is not None and state.delayed_goals is not None:
            result.extend(translate(state.delayed_goals, trail,
                                    translate_goal))
    return result


def translate(goals, trail, translate_goal=None):
    """geler.pl, translate//1 and translate_goal//1.

    The hook point for nfq.pl.  geler/2 is a meta-predicate, so 1.3.3's
    stored goal is `nfq:G`, and translate_goal//1's `M:G` clause hands G to
    nfq.pl's exported translate_goal//1 (nfq.pl, the `transg` of the
    original), which turns `resubmit_*(Nf)` into `[clpq:{Term Rel 0}]` and
    `wait_linear_retry(Nf, Res, Goal)` into `[clpq:{Term = Res}, Goal]`.
    The port's goal is a (procedure, argument) pair whose module is always
    nfq, so *translate_goal* is that nfq.pl predicate:
    `translate_goal(procedure, argument) -> list of goal terms`, in order.
    Task 10 writes it with nfq.pl; dump.pl's nonlinear_strip/3 (Task 12)
    reads its output.  A port goal is never a conjunction, so the
    conjunction clause has nothing to do (DEVIATIONS.md D7).

    Without a *translate_goal*, the one nfq.pl exports is used
    (normal_form.translate_goal; test_translate_is_plugged_into_delayed_goals).
    """
    if translate_goal is None:
        from clausal.logic.clpq.normal_form import (  # cyclic: nfq.pl
            translate_goal)
    result = []
    for goal in goals:
        if is_var(deref(goal.mutex)):
            unify(goal.mutex, DONE, trail)
            result.extend(translate_goal(goal.procedure, goal.argument))
    return result


def run(goal, trail):
    """geler.pl, run/2."""
    if not is_var(deref(goal.mutex)):                           # clause 1
        return True
    unify(goal.mutex, DONE, trail)                              # clause 2
    return goal.procedure(goal.argument, trail)


def delay_goal(variables, procedure, argument, trail):
    """geler.pl, geler/2: delay `procedure(argument, trail)` until one of
    *variables* is bound.  False where attach fails."""
    return attach(variables, DelayedGoal(Var(), procedure, argument), trail)


def attach(variables, goal, trail):
    """geler.pl, attach/2.  Returns False for a PlainVar, which cannot carry
    the goal (test_delay_goal_on_a_plain_var_fails_closed); 1.3.3 has no
    such variable.  The check comes first, so a False attaches nothing."""
    for variable in variables:
        if type(deref(variable)) is PlainVar:
            return False
    for variable in variables:
        state = state_of(variable) if is_var(deref(variable)) else None
        if state is not None and state.delayed_goals is not None:
            put_state(variable, with_changes(
                state, delayed_goals=(goal,) + state.delayed_goals), trail)
        else:
            _put_goals(variable, state, (goal,), trail)
    return True


def _put_goals(variable, state, goals, trail):
    """put_atts(V, goals(G)) on a variable whose state is *state*."""
    if state is None:
        put_state(variable, SolverState(delayed_goals=goals), trail)
    else:
        put_state(variable, with_changes(state, delayed_goals=goals), trail)


def _term_variables(roots):
    """The unbound variables in *roots*, each once, in creation order.  An
    explicit stack (test_project_nonlinear_walks_records_and_deep_arguments);
    a record is walked through its __slots__."""
    seen = set()
    variables = []
    stack = list(roots)
    while stack:
        term = deref(stack.pop())
        if is_var(term):
            if term._id not in seen:
                seen.add(term._id)
                variables.append(term)
        elif type(term) is tuple or type(term) is list:
            stack.extend(term)
        else:
            slots = getattr(type(term), "__slots__", ())
            for name in slots:
                stack.append(getattr(term, name))
    variables.sort(key=_creation)
    return variables


def _creation(variable):
    return variable._id
