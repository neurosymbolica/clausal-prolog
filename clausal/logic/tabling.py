"""clausal.logic.tabling — SLG tabling (memoisation with suspension).

Provides tabled evaluation for predicates marked with ``-table(pred/arity)``.
Tabled predicates cache their answers and terminate cyclic derivations via
SLG resolution.

Architecture
------------
A tabled predicate's dispatch function is wrapped so that:

- **Leader** (first call to a subgoal): drives the original dispatch, collects
  and caches answers, then runs a completion phase that resumes any suspended
  consumers.
- **Consumer** (recursive call while leader is running): yields currently cached
  answers, then suspends (``_TABLING_SUSPEND``) until the leader resumes it.
- **Complete** (cache hit after leader finished): yields all cached answers
  directly.

In trampoline mode, suspension is cooperative: the consumer yields
``(parent, _TABLING_SUSPEND)`` and the trampoline converts this to DONE so the
caller's while-loop exits normally.  The leader's completion phase resumes
consumers via a mini-trampoline that uses the consumer's ``parent`` reference
as a routing key.
"""

from __future__ import annotations
from typing import Any, Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import Compound

# ── Sentinels ──────────────────────────────────────────────────────────────

_VAR = object()              # unbound Var placeholder in subgoal keys
_TABLING_SUSPEND = object()  # consumer → trampoline: park me
_TABLING_RESUME = object()   # leader → consumer: wake up, check for answers

# ── Table entry ───────────────────────────────────────────────────────────


class TableEntry:
    """Stores status, answers, and suspended consumers for one subgoal."""
    __slots__ = ("status", "answers", "answer_set", "suspended")

    def __init__(self):
        self.status: str = "evaluating"       # "evaluating" | "complete"
        self.answers: list[tuple] = []
        self.answer_set: set[tuple] = set()
        self.suspended: list = []             # list of SuspendedConsumer

    def add_answer(self, answer: tuple) -> bool:
        """Add a frozen answer tuple.  Returns True if it was new."""
        if answer in self.answer_set:
            return False
        self.answer_set.add(answer)
        self.answers.append(answer)
        return True


class SuspendedConsumer:
    """A consumer generator parked waiting for new answers."""
    __slots__ = ("generator", "parent", "args", "trail", "answers_seen")

    def __init__(self, generator, parent, args, trail, answers_seen):
        self.generator = generator    # the consumer's StepGenerator
        self.parent = parent          # routing key for intercepting yields
        self.args = args              # call args (for unification with new answers)
        self.trail = trail
        self.answers_seen: int = answers_seen


# ── Key computation (variant checking) ────────────────────────────────────


def _normalize_for_key(term):
    """Deref term; replace unbound Vars with _VAR sentinel."""
    term = deref(term)
    if is_var(term):
        return _VAR
    if term is None or isinstance(term, (bool, int, float, str, bytes)):
        return term
    if isinstance(term, list):
        return ("__list__",) + tuple(_normalize_for_key(e) for e in term)
    if isinstance(term, Compound):
        return (term.functor,) + tuple(_normalize_for_key(a) for a in term.args)
    if is_term_instance(term):
        return (type(term).__name__,) + tuple(
            _normalize_for_key(getattr(term, f)) for f in term_field_names(term)
        )
    return term


def make_subgoal_key(args, trail):
    """Compute variant key for a tabled call's arguments."""
    return tuple(_normalize_for_key(a) for a in args)


# ── Answer freezing ──────────────────────────────────────────────────────


def freeze_args(args, trail):
    """Capture a ground snapshot of current arg bindings."""
    from clausal.logic.solve import _deref_walk
    return tuple(_deref_walk(a) for a in args)


# ── Answer unification ───────────────────────────────────────────────────


def _unify_answer(args, stored, trail):
    """Unify each arg with the corresponding stored value."""
    for a, s in zip(args, stored):
        if not unify(a, s, trail):
            return False
    return True


# ── Simple-mode tabled wrapper (linear tabling) ─────────────────────────


def make_tabled_wrapper_simple(original_dispatch, functor, arity, table_store):
    """Linear tabling wrapper for simple-mode dispatch.

    Simple-mode signature: dispatch(arg0, ..., trail, k) → yields None per solution.
    Uses fixpoint iteration: re-runs original dispatch until no new answers appear.
    """

    def tabled_dispatch(*args_trail_k):
        args = args_trail_k[:arity]
        trail = args_trail_k[arity]

        key = make_subgoal_key(args, trail)
        store_key = (functor, arity, key)
        entry = table_store.get(store_key)

        # ── COMPLETE: cache hit ──
        if entry is not None and entry.status == "complete":
            for stored in entry.answers:
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield None
                trail.undo(mark)
            return

        # ── CONSUMER: yield known answers only (no suspension in simple mode) ──
        if entry is not None and entry.status == "evaluating":
            i = 0
            while i < len(entry.answers):
                mark = trail.mark()
                if _unify_answer(args, entry.answers[i], trail):
                    yield None
                trail.undo(mark)
                i += 1
            return

        # ── LEADER: fixpoint loop ──
        entry = TableEntry()
        table_store[store_key] = entry

        changed = True
        while changed:
            old_count = len(entry.answers)
            mark = trail.mark()
            for _ in original_dispatch(*args, trail, None):
                answer = freeze_args(args, trail)
                entry.add_answer(answer)
            trail.undo(mark)
            changed = len(entry.answers) > old_count

        entry.status = "complete"
        for stored in entry.answers:
            mark = trail.mark()
            if _unify_answer(args, stored, trail):
                yield None
            trail.undo(mark)

    return tabled_dispatch


# ── Trampoline-mode tabled wrapper (SLG) ────────────────────────────────


def make_tabled_wrapper_trampoline(original_dispatch, functor, arity, table_store):
    """SLG tabling wrapper for trampoline-mode dispatch.

    Trampoline-mode signature: dispatch(this_gen, parent, arg0, ..., trail)
    Yields (target, value) tuples per trampoline protocol.
    """
    from clausal.logic.trampoline import StepGenerator, DONE

    def tabled_dispatch(this_generator, parent, *args_trail):
        args = args_trail[:arity]
        trail = args_trail[arity]

        key = make_subgoal_key(args, trail)
        store_key = (functor, arity, key)
        entry = table_store.get(store_key)

        # ── COMPLETE: yield cached answers ──
        if entry is not None and entry.status == "complete":
            for stored in entry.answers:
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield (parent, None)
                trail.undo(mark)
            yield (parent, DONE)
            return

        # ── CONSUMER: yield known answers, then SUSPEND ──
        if entry is not None and entry.status == "evaluating":
            for stored in entry.answers:
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield (parent, None)
                trail.undo(mark)

            # Register as suspended consumer
            sc = SuspendedConsumer(
                this_generator, parent, args, trail, len(entry.answers)
            )
            entry.suspended.append(sc)

            # SUSPEND — trampoline intercepts this, sends DONE to parent
            signal = yield (parent, _TABLING_SUSPEND)

            # Resumed by leader's completion phase with _TABLING_RESUME
            while signal is _TABLING_RESUME:
                while sc.answers_seen < len(entry.answers):
                    stored = entry.answers[sc.answers_seen]
                    sc.answers_seen += 1
                    mark = trail.mark()
                    if _unify_answer(args, stored, trail):
                        yield (parent, None)
                    trail.undo(mark)
                # If table still evaluating, re-suspend for more answers
                if entry.status == "evaluating":
                    signal = yield (parent, _TABLING_SUSPEND)
                else:
                    break

            yield (parent, DONE)
            return

        # ── LEADER: drive original dispatch, then complete ──
        entry = TableEntry()
        table_store[store_key] = entry

        # Drive original dispatch through trampoline protocol
        _gen = StepGenerator(original_dispatch, this_generator, *args, trail)
        _st = yield (_gen, None)
        while _st is not DONE:
            answer = freeze_args(args, trail)
            if entry.add_answer(answer):
                yield (parent, None)  # new answer to leader's caller (incremental)
            _st = yield (_gen, None)

        # ── Completion phase ──
        # Original dispatch exhausted. Resume suspended consumers to process
        # answers they haven't seen yet. This may discover new answers,
        # requiring further rounds.
        changed = True
        while changed and entry.suspended:
            changed = False
            pending = list(entry.suspended)
            entry.suspended.clear()

            for sc in pending:
                if sc.answers_seen >= len(entry.answers):
                    # No new answers for this consumer — skip
                    continue

                old_count = len(entry.answers)

                # Resume consumer — send _TABLING_RESUME
                gen, value = sc.generator.send(_TABLING_RESUME)

                # Mini-trampoline: drive consumer, intercept parent-directed yields
                while True:
                    if gen is sc.parent:
                        # Yield directed at consumer's (dead) parent — intercept
                        if value is None:
                            # Consumer found a solution
                            answer = freeze_args(sc.args, sc.trail)
                            if entry.add_answer(answer):
                                yield (parent, None)  # propagate to leader's caller
                            # Ask consumer for next result
                            gen, value = sc.generator.send(None)
                        elif value is DONE:
                            break  # consumer finished
                        elif value is _TABLING_SUSPEND:
                            # Consumer re-suspends — save for next round
                            entry.suspended.append(sc)
                            break
                        else:
                            break  # unknown value — treat as done
                    else:
                        # Sub-call from consumer body — drive through trampoline
                        gen, value = gen.send(value)

                if len(entry.answers) > old_count:
                    changed = True

        # Send DONE to any remaining suspended consumers (cleanup)
        for sc in entry.suspended:
            try:
                sc.generator.send(DONE)
            except StopIteration:
                pass
        entry.suspended.clear()

        entry.status = "complete"
        yield (parent, DONE)

    return tabled_dispatch


# ── Simple-mode adapter for trampoline-mode tabled wrapper ──────────────


def _trampoline_to_simple_adapter(trampoline_dispatch, arity):
    """Adapt a trampoline-mode dispatch to simple-mode calling convention.

    Simple-mode callers use ``for _ in dispatch(*args, trail, k): ...``.
    This adapter creates a StepGenerator and drives it via a mini-trampoline
    that yields per solution while bindings are still live.
    """
    from clausal.logic.trampoline import StepGenerator, DONE

    def adapted(*args_trail_k):
        args = args_trail_k[:arity]
        trail = args_trail_k[arity]
        root = StepGenerator(trampoline_dispatch, None, *args, trail)
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    return
                yield None  # solution — bindings are live on trail
                gen, value = root.send(None)
            else:
                # Intercept _TABLING_SUSPEND → send DONE to parent
                if value is _TABLING_SUSPEND:
                    gen, value = gen.send(DONE)
                else:
                    gen, value = gen.send(value)

    return adapted
