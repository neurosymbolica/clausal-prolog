"""Pending goals: woken goals run at the next goal boundary, with every answer.

An attribute hook (``freeze/2``, ``when/2``) that wakes a goal while a driver
owns the trail (``trail.defer``) does not run the goal inside the
unification.  It queues it with ``trail.push_pending(goal)``, and the engine
runs the queue at the next goal boundary as a conjunction, backtracking into
every answer.  Scryer runs woken goals the same way: queued during the
unification, run before the next call.

The goal boundaries are:

* compiled code after a unification, ``for _ in pending_or_once(trail): <rest>``
  (``pending_or_once`` is a shared ``range(1)`` when nothing is queued), and after
  every other goal the compiler lowers inline that can bind: a CLP(FD)
  comparison (``X == 3``, ``X <= 3``; a domain squeezed to one value binds
  too) and each branch of a reified comparison it posts;
* a trampoline generator's solution step (``StepGenerator.send``), so every
  builtin's and every predicate's answers pass one;
* a shallow-mode sub-call, after each answer.

A goal is a zero-argument generator factory yielding once per answer and
undoing its own bindings between answers, as compiled goal bodies do.  The
queue and every change to it are on the trail, so backtracking past a push or
a take restores it.

Outside a driver (``trail.defer`` false: a bare ``unify`` from Python, a
compiled predicate called directly) hooks queue their goals all the same,
and the unification runs the queue itself before it returns, once every
hook has run, to the first answer (``run_first``); it fails when there is
none.  From its first binding until the queue has run it owns the trail as
a driver does (``trail.defer`` is set), so a unification nested in it -- a
term's ``__unify__`` unifying element by element, a hook, a woken goal --
only queues, and this drain runs what it queued.  A goal queued with no
unification to run it is not left on the queue: ``when/2`` whose condition
already holds runs its goal in place outside a driver
(``coroutining._run_now``).
"""

from __future__ import annotations

from clausal.logic.variables import _set_pending_drain


def drain(trail):
    """Run every goal queued on *trail*, as a conjunction; yield per answer.

    Goals a running goal queues in turn are run after the conjunction (each
    goal's own goal boundaries run the ones it wakes itself first), as the
    next conjunction.  Every conjunction, and every generation of goals
    woken by the one before, is driven on ONE explicit stack: a thousand
    goals woken by one unification, or a chain of a hundred thousand goals
    each waking the next, nest no Python frames and no generators.  (A
    nested ``yield from drain(trail)`` per generation was a chain of
    suspended generators; dropping it after a first answer recursed in C.)
    """
    goals = trail.take_pending()
    if goals is None:
        yield None
        return
    # One frame per running goal: (its answers, its conjunction, its index).
    stack = [(iter(goals[0]()), goals, 0)]
    while stack:
        it, conj, i = stack[-1]
        try:
            next(it)
        except StopIteration:
            stack.pop()
            continue
        if i + 1 < len(conj):
            stack.append((iter(conj[i + 1]()), conj, i + 1))
        elif trail.pending is None:
            yield None
        else:
            woken = trail.take_pending()
            stack.append((iter(woken[0]()), woken, 0))


def run_first(trail) -> bool:
    """Run the queued goals to their first answer and keep its bindings.

    For a test that only asks whether something succeeds (``\\=``, a probe):
    True when the goals have an answer.  On False the caller undoes."""
    if trail.pending is None:
        return True
    for _ in drain(trail):
        return True
    return False


_set_pending_drain(drain)
