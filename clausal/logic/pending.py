"""Pending goals: woken goals run at the next goal boundary, with every answer.

An attribute hook (``freeze/2``, ``when/2``) that wakes a goal while a driver
owns the trail (``trail.defer``) does not run the goal inside the
unification.  It queues it with ``trail.push_pending(goal)``, and the engine
runs the queue at the next goal boundary as a conjunction, backtracking into
every answer.  Scryer runs woken goals the same way: queued during the
unification, run before the next call.

The goal boundaries are:

* compiled code after a unification, ``for _ in pending_or_once(trail): <rest>``
  (``pending_or_once`` is ``(None,)`` when nothing is queued);
* a trampoline generator's solution step (``StepGenerator.send``), so every
  builtin's and every predicate's answers pass one;
* a shallow-mode sub-call, after each answer.

A goal is a zero-argument generator factory yielding once per answer and
undoing its own bindings between answers, as compiled goal bodies do.  The
queue and every change to it are on the trail, so backtracking past a push or
a take restores it.

Outside a driver (``trail.defer`` false: a bare ``unify`` from Python, a
compiled predicate called directly) a hook runs its goals in place, to their
first answer, as before.
"""

from __future__ import annotations

from clausal.logic.variables import _set_pending_drain


def drain(trail):
    """Run every goal queued on *trail*, as a conjunction; yield per answer.

    Goals a running goal queues in turn are run after the conjunction (each
    goal's own goal boundaries run the ones it wakes itself first).  The
    conjunction is driven with an explicit stack, so a thousand goals woken
    by one unification nest no Python frames.
    """
    goals = trail.take_pending()
    if goals is None:
        yield None
        return
    n = len(goals)
    its = [iter(goals[0]())]
    while its:
        try:
            next(its[-1])
        except StopIteration:
            its.pop()
            continue
        if len(its) < n:
            its.append(iter(goals[len(its)]()))
        elif trail.pending is None:
            yield None
        else:
            yield from drain(trail)


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
