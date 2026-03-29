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

in_ trampoline mode, suspension is cooperative: the consumer yields
``(parent, _TABLING_SUSPEND)`` and the trampoline converts this to DONE so the
caller's while-loop exits normally.  The leader's completion phase resumes
consumers via a mini-trampoline that uses the consumer's ``parent`` reference
as a routing key.

Well-Founded Semantics (WFS)
----------------------------
when NAF targets a tabled predicate whose table is still evaluating (cycle
through negation), the negation is *delayed* rather than checked immediately.
After SLG completion, a simplification pass resolves delayed negations:

- Negation of a completed table with no matching answer → **true** (remove delay)
- Negation of a completed table with unconditional matching answer → **false** (invalidate)
- Remaining delays form unfounded sets → truth value **undefined**
"""

from __future__ import annotations
import threading
from typing import Any, Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import Compound

# ── Sentinels ──────────────────────────────────────────────────────────────

_VAR = object()              # unbound Var placeholder in subgoal keys
_TABLING_SUSPEND = object()  # consumer → trampoline: park me
_TABLING_RESUME = object()   # leader → consumer: wake up, check for answers
_FAILED = object()           # sentinel for invalidated conditional answers

# ── Delayed negation ─────────────────────────────────────────────────────


class DelayedNegation:
    """Represents a conditional dependency: 'not functor(frozen_args)' must hold."""
    __slots__ = ("functor", "arity", "key", "frozen_args")

    def __init__(self, functor: str, arity: int, key: tuple, frozen_args: tuple):
        self.functor = functor
        self.arity = arity
        self.key = key
        self.frozen_args = frozen_args

    def __eq__(self, other):
        if not isinstance(other, DelayedNegation):
            return NotImplemented
        return (self.functor == other.functor and self.arity == other.arity
                and self.key == other.key and self.frozen_args == other.frozen_args)

    def __hash__(self):
        return hash((self.functor, self.arity, self.key, self.frozen_args))

    def __repr__(self):
        return f"DelayedNegation({self.functor!r}/{self.arity}, key={self.key!r})"


# ── Leader context stack (thread-local) ──────────────────────────────────


class _LeaderContext(threading.local):
    def __init__(self):
        self.stack: list[TableEntry] = []

_leader_ctx = _LeaderContext()


def push_leader(entry: TableEntry) -> None:
    _leader_ctx.stack.append(entry)


def pop_leader() -> TableEntry:
    return _leader_ctx.stack.pop()


def current_leader() -> TableEntry | None:
    return _leader_ctx.stack[-1] if _leader_ctx.stack else None


# ── Table entry ───────────────────────────────────────────────────────────


class TableEntry:
    """Stores status, answers, and suspended consumers for one subgoal."""
    __slots__ = ("status", "answers", "answer_set", "suspended",
                 "conditions", "_current_delays")

    def __init__(self):
        self.status: str = "evaluating"       # "evaluating" | "complete"
        self.answers: list[tuple] = []
        self.answer_set: set[tuple] = set()
        self.suspended: list = []             # list of SuspendedConsumer
        self.conditions: list = []            # parallel to answers: frozenset[DelayedNegation] | _FAILED
        self._current_delays: set[DelayedNegation] = set()

    def add_answer(self, answer: tuple, delay_set: frozenset | None = None) -> bool:
        """Add a frozen answer tuple.  Returns True if it was new."""
        if answer in self.answer_set:
            return False
        self.answer_set.add(answer)
        self.answers.append(answer)
        self.conditions.append(delay_set if delay_set is not None else frozenset())
        return True

    def truth_value(self, i: int):
        """Return True, False, or 'undefined' for the i-th answer."""
        c = self.conditions[i]
        if c is _FAILED:
            return False
        if not c:
            return True
        return "undefined"


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


_SCALAR_TYPES = (bool, int, float, str, bytes)


def _normalize_for_key_py(term):
    """Deref term; replace unbound Vars with _VAR sentinel."""
    term = deref(term)
    if type(term) is int:
        return term
    if is_var(term):
        return _VAR
    if term is None or isinstance(term, _SCALAR_TYPES):
        return term
    if isinstance(term, list):
        return ("__list__",) + tuple(_normalize_for_key_py(e) for e in term)
    if isinstance(term, Compound):
        return (term.functor,) + tuple(_normalize_for_key_py(a) for a in term.args)
    if is_term_instance(term):
        return (type(term).__name__,) + tuple(
            _normalize_for_key_py(getattr(term, f)) for f in term_field_names(term)
        )
    return term

_normalize_for_key = _normalize_for_key_py


def _make_subgoal_key_py(args, trail):
    """Compute variant key for a tabled call's arguments."""
    return tuple([_normalize_for_key(a) for a in args])

make_subgoal_key = _make_subgoal_key_py


# ── Answer freezing ──────────────────────────────────────────────────────


def _freeze_args_py(args, trail):
    """Capture a ground snapshot of current arg bindings."""
    from clausal.logic.solve import _deref_walk
    return tuple([_deref_walk(a) for a in args])

freeze_args = _freeze_args_py


# ── Answer unification ───────────────────────────────────────────────────


def _unify_answer_py(args, stored, trail):
    """Unify each arg with the corresponding stored value."""
    for a, s in zip(args, stored):
        if not unify(a, s, trail):
            return False
    return True

_unify_answer = _unify_answer_py

# ── C acceleration (optional) ────────────────────────────────────────────

try:
    from clausal.logic._tabling_core import (
        _normalize_for_key as _normalize_for_key_c,
        make_subgoal_key as _make_subgoal_key_c,
        freeze_args as _freeze_args_c,
        _unify_answer as _unify_answer_c,
        _register_var_sentinel,
    )
    _register_var_sentinel(_VAR)
    _normalize_for_key = _normalize_for_key_c
    make_subgoal_key = _make_subgoal_key_c
    freeze_args = _freeze_args_c
    _unify_answer = _unify_answer_c
except ImportError:
    pass  # Python fallbacks above


# ── Delayed negation runtime (WFS) ──────────────────────────────────────


def _naf_tabled(functor, arity, args, trail, table_store):
    """Check negation-as-failure for a tabled predicate (WFS-aware).

    Returns True if negation succeeds (conditionally or unconditionally),
    False if negation fails (the positive goal has an answer).

    when the target table is still evaluating (cycle through negation),
    creates a DelayedNegation and attaches it to the current leader's
    delay set — the answer is conditional until resolution.
    """
    key = make_subgoal_key(args, trail)
    store_key = (functor, arity, key)
    entry = table_store.get(store_key)

    if entry is not None and entry.status == "complete":
        # Standard NAF on complete table: check if any non-failed answer unifies.
        from clausal.logic.variables import Trail as _Trail
        scratch = _Trail()
        for i, stored in enumerate(entry.answers):
            if entry.conditions[i] is _FAILED:
                continue
            mark = scratch.mark()
            if _unify_answer(list(args), list(stored), scratch):
                scratch.undo(mark)
                return False  # positive answer exists → negation fails
            scratch.undo(mark)
        return True  # no matching answer → negation succeeds

    if entry is not None and entry.status == "evaluating":
        # Cycle through negation — delay.
        frozen = freeze_args(args, trail)
        dn = DelayedNegation(functor, arity, key, frozen)
        leader = current_leader()
        if leader is not None:
            leader._current_delays.add(dn)
        return True  # conditionally succeed

    # No exact variant entry. Check if ANY variant of this predicate is
    # evaluating — if so, we're in a cycle through negation and must delay.
    # This handles cases like: leader evaluates win(_), body calls not win(2),
    # which is a different variant but still part of the same SLG cycle.
    for (f, a, _k), e in table_store.items():
        if f == functor and a == arity and e.status == "evaluating":
            frozen = freeze_args(args, trail)
            dn = DelayedNegation(functor, arity, key, frozen)
            leader = current_leader()
            if leader is not None:
                leader._current_delays.add(dn)
            return True  # conditionally succeed

    # No entry at all — predicate not yet called. Treat as no answers.
    return True


# ── Conditional answer resolution (WFS) ─────────────────────────────────


def _resolve_conditions(entry, table_store):
    """Resolve delayed negations after SLG completion.

    Iterates until no changes:
    - DelayedNegation targeting complete table with no matching answer → remove (true)
    - DelayedNegation targeting complete table with unconditional match → invalidate (false)
    - Remaining delays → unfounded (undefined)
    """
    changed = True
    while changed:
        changed = False
        for i in range(len(entry.answers)):
            conds = entry.conditions[i]
            if conds is _FAILED or not conds:
                continue  # already resolved or unconditional

            new_delays = set()
            failed = False
            for dn in conds:
                target_key = (dn.functor, dn.arity, dn.key)
                target_entry = table_store.get(target_key)

                if target_entry is None or target_entry.status != "complete":
                    new_delays.add(dn)  # can't resolve yet
                    continue

                # Check if target has ANY matching answer
                has_match = False
                has_unconditional_match = False
                for j, stored in enumerate(target_entry.answers):
                    if target_entry.conditions[j] is _FAILED:
                        continue
                    if stored == dn.frozen_args:
                        has_match = True
                        if not target_entry.conditions[j]:  # unconditional
                            has_unconditional_match = True
                            break

                if has_unconditional_match:
                    # Negation is false → this answer is invalidated
                    failed = True
                    break
                elif not has_match:
                    # No matching answer → negation is true → delay resolved
                    continue
                else:
                    # Matching answer exists but is conditional → keep delay
                    new_delays.add(dn)

            if failed:
                entry.conditions[i] = _FAILED
                changed = True
            else:
                new_conds = frozenset(new_delays)
                if new_conds != conds:
                    entry.conditions[i] = new_conds
                    changed = True


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
            for i, stored in enumerate(entry.answers):
                if entry.conditions[i] is _FAILED:
                    continue
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield None
                trail.undo(mark)
            return

        # ── CONSUMER: yield known answers only (no suspension in simple mode) ──
        if entry is not None and entry.status == "evaluating":
            i = 0
            while i < len(entry.answers):
                if entry.conditions[i] is not _FAILED:
                    mark = trail.mark()
                    if _unify_answer(args, entry.answers[i], trail):
                        yield None
                    trail.undo(mark)
                i += 1
            return

        # ── LEADER: fixpoint loop ──
        entry = TableEntry()
        table_store[store_key] = entry
        push_leader(entry)

        try:
            changed = True
            while changed:
                old_count = len(entry.answers)
                mark = trail.mark()
                for _ in original_dispatch(*args, trail, None):
                    answer = freeze_args(args, trail)
                    delay_set = frozenset(entry._current_delays)
                    entry._current_delays.clear()
                    entry.add_answer(answer, delay_set)
                trail.undo(mark)
                entry._current_delays.clear()
                changed = len(entry.answers) > old_count

            _resolve_conditions(entry, table_store)
        finally:
            pop_leader()

        entry.status = "complete"
        for i, stored in enumerate(entry.answers):
            if entry.conditions[i] is _FAILED:
                continue
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
            for i, stored in enumerate(entry.answers):
                if entry.conditions[i] is _FAILED:
                    continue
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield (parent, None)
                trail.undo(mark)
            yield (parent, DONE)
            return

        # ── CONSUMER: yield known answers, then SUSPEND ──
        if entry is not None and entry.status == "evaluating":
            for i, stored in enumerate(entry.answers):
                if entry.conditions[i] is _FAILED:
                    continue
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
                    cond = entry.conditions[sc.answers_seen]
                    sc.answers_seen += 1
                    if cond is _FAILED:
                        continue
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
        push_leader(entry)

        try:
            # Drive original dispatch through trampoline protocol
            _gen = StepGenerator(original_dispatch, this_generator, *args, trail)
            _st = yield (_gen, None)
            while _st is not DONE:
                answer = freeze_args(args, trail)
                delay_set = frozenset(entry._current_delays)
                entry._current_delays.clear()
                if entry.add_answer(answer, delay_set):
                    yield (parent, None)  # new answer to leader's caller (incremental)
                _st = yield (_gen, None)
            entry._current_delays.clear()

            # ── Completion phase ──
            changed = True
            while changed and entry.suspended:
                changed = False
                pending = list(entry.suspended)
                entry.suspended.clear()

                for sc in pending:
                    if sc.answers_seen >= len(entry.answers):
                        continue

                    old_count = len(entry.answers)

                    gen, value = sc.generator.send(_TABLING_RESUME)

                    while True:
                        if gen is sc.parent:
                            if value is None:
                                answer = freeze_args(sc.args, sc.trail)
                                delay_set = frozenset(entry._current_delays)
                                entry._current_delays.clear()
                                if entry.add_answer(answer, delay_set):
                                    yield (parent, None)
                                gen, value = sc.generator.send(None)
                            elif value is DONE:
                                break
                            elif value is _TABLING_SUSPEND:
                                entry.suspended.append(sc)
                                break
                            else:
                                break
                        else:
                            gen, value = gen.send(value)

                    entry._current_delays.clear()
                    if len(entry.answers) > old_count:
                        changed = True

            # Send DONE to any remaining suspended consumers (cleanup)
            for sc in entry.suspended:
                try:
                    sc.generator.send(DONE)
                except StopIteration:
                    pass
            entry.suspended.clear()

            _resolve_conditions(entry, table_store)
        finally:
            pop_leader()

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
