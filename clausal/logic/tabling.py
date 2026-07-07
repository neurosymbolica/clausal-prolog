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


def pop_leader(entry: TableEntry | None = None) -> TableEntry | None:
    """Remove *entry* from the leader stack and return it (A04-F001).

    An abandoned tabled generator's ``finally`` may run out of order (on GC),
    long after its entry stopped being the stack top — blindly popping the top
    would corrupt an unrelated leader's stack (breaking any dispatch that reads
    it, e.g. SCC completion). Remove the specific entry instead; fall back to a
    plain pop of the top only when no entry is given.
    """
    stack = _leader_ctx.stack
    if entry is not None:
        for i in range(len(stack) - 1, -1, -1):
            if stack[i] is entry:
                del stack[i]
                return entry
        return None
    return stack.pop() if stack else None


def current_leader() -> TableEntry | None:
    return _leader_ctx.stack[-1] if _leader_ctx.stack else None


def _on_leader_stack(entry: TableEntry) -> bool:
    """True if *entry* is an actively-leading ancestor (A04-F001 SCC)."""
    return any(e is entry for e in _leader_ctx.stack)


def _complete_scc(root: TableEntry, table_store) -> None:
    """Mark *root* complete, then sweep dormant SCC members (A04-F001).

    A member deferred completion while it consumed a still-evaluating
    ancestor; once every dependency is complete it may complete too. Iterate
    to a fixpoint so a chain of members resolves.
    """
    root.status = "complete"
    changed = True
    while changed:
        changed = False
        for e in table_store.values():
            if (e.status != "evaluating" or _on_leader_stack(e)
                    or not e.scc_deps):
                continue
            if all(dep is e or dep.status == "complete" for dep in e.scc_deps):
                e.status = "complete"
                changed = True


# ── Table entry ───────────────────────────────────────────────────────────


class TableEntry:
    """Stores status, answers, and suspended consumers for one subgoal."""
    __slots__ = ("status", "answers", "answer_set", "suspended",
                 "conditions", "_current_delays", "scc_deps")

    def __init__(self):
        self.status: str = "evaluating"       # "evaluating" | "complete"
        self.answers: list[tuple] = []
        self.answer_set: set = set()   # canonical answer keys (A04-F005/F006)
        self.suspended: list = []             # list of SuspendedConsumer
        self.conditions: list = []            # parallel to answers: frozenset[DelayedNegation] | _FAILED
        self._current_delays: set[DelayedNegation] = set()
        # A04-F001 SCC completion: entries this one consumed as an evaluating
        # ANCESTOR (mutual recursion). While any dep is still evaluating this
        # entry is an SCC member and must not complete on its own.
        self.scc_deps: set = set()            # set[TableEntry]

    def add_answer(self, answer: tuple, delay_set: frozenset | None = None) -> bool:
        """Add a frozen answer tuple.  Returns True if it was new.

        Dedup uses the canonical, hashable key (A04-F005) — a frozen answer may
        contain a list/dict/set/term instance, which are unhashable and cannot
        go directly in ``answer_set``. The key also type-distinguishes numeric
        leaves (A04-F006), so 1/True/1.0 answers are kept distinct exactly as
        the untabled dispatch would. The original frozen tuple is stored in
        ``answers`` for unification.
        """
        key = make_subgoal_key(answer, None)
        if key in self.answer_set:
            return False
        self.answer_set.add(key)
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
    __slots__ = ("generator", "_proceed", "args", "trail", "answers_seen")

    def __init__(self, generator, _proceed, args, trail, answers_seen):
        self.generator = generator    # the consumer's StepGenerator
        self._proceed = _proceed      # solution routing key for intercepting yields
        self.args = args              # call args (for unification with new answers)
        self.trail = trail
        self.answers_seen: int = answers_seen


# ── Key computation (variant checking) ────────────────────────────────────


def _normalize_for_key_py(term):
    """Deref term into a hashable, type-distinguishing canonical key.

    Exact ``int`` stays canonical (the fast path). Other numeric leaves
    (``bool``/``float``/``complex``) are type-tagged as ``(type, value)`` so
    ``1``/``True``/``1.0`` do not conflate in variant keys or answer dedup
    (A04-F006 — semantics-neutral; unification is untouched, see A01-D001).
    Containers (``list``/``tuple``/``dict``/``set``, ``Compound``, term
    instances) are rebuilt into hashable forms so answers/keys holding them
    can live in the dedup set (A04-F005).

    Keep this in exact lock-step with the C twin ``do_normalize``
    (``_tabling_core.c``) — the two must produce identical keys (P52).
    ``Decimal``/``Fraction`` are intentionally left raw in BOTH (they still
    conflate with ``int`` — a documented residual pending A01-D001).
    """
    term = deref(term)
    if type(term) is int:
        return term
    if is_var(term):
        return _VAR
    if term is None:
        return term
    if isinstance(term, (bool, float, complex)):
        return (type(term), term)          # A04-F006
    if isinstance(term, (str, bytes)):
        return term
    if isinstance(term, list):
        return ("__list__",) + tuple(_normalize_for_key_py(e) for e in term)
    if isinstance(term, tuple):
        return ("__tuple__",) + tuple(_normalize_for_key_py(e) for e in term)
    if isinstance(term, dict):
        return ("__dict__", frozenset(
            (_normalize_for_key_py(k), _normalize_for_key_py(v))
            for k, v in term.items()))
    if isinstance(term, (set, frozenset)):
        return ("__set__", frozenset(_normalize_for_key_py(e) for e in term))
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

    # No exact-variant entry. A COMPLETE same-functor entry whose variant key
    # SUBSUMES this call already knows the full answer set for the call's
    # instances (A04-F002): e.g. a complete ``tp(_,_)`` table answers
    # ``not tp(1,2)`` even though there is no exact ``tp(1,2)`` entry. Check the
    # call against such a table before any fallthrough.
    from clausal.logic.variables import Trail as _Trail
    for (f, a, k), e in table_store.items():
        if f != functor or a != arity or e.status != "complete":
            continue
        if not _key_subsumes(k, key):
            continue
        scratch = _Trail()
        for i, stored in enumerate(e.answers):
            if e.conditions[i] is _FAILED:
                continue
            mark = scratch.mark()
            if _unify_answer(list(args), list(stored), scratch):
                scratch.undo(mark)
                return False  # subsuming complete table has a matching answer
            scratch.undo(mark)
        # A subsuming complete table with no matching answer means the goal is
        # false for this call → negation succeeds.
        return True

    # Check if ANY variant of this predicate is evaluating — if so, we're in a
    # cycle through negation and must delay. This handles cases like: leader
    # evaluates win(_), body calls not win(2), a different variant but still
    # part of the same SLG cycle.
    for (f, a, _k), e in table_store.items():
        if f == functor and a == arity and e.status == "evaluating":
            frozen = freeze_args(args, trail)
            dn = DelayedNegation(functor, arity, key, frozen)
            leader = current_leader()
            if leader is not None:
                leader._current_delays.add(dn)
            return True  # conditionally succeed

    # No entry at all — predicate never called for a subsuming variant.
    # SOUND resolution requires spawning the positive subgoal (evaluate the
    # table, then re-check) — that needs dispatch access threaded from the
    # compiler and full WFS-cycle integration, tracked in
    # investigate-A04-wfs-variant-resolution.md (parked decision A04-D004).
    # Until then this conservatively succeeds (the historical behaviour).
    return True


def _key_subsumes(general: tuple, specific: tuple) -> bool:
    """True if variant key ``general`` is at least as general as ``specific``
    — each position is the unbound ``_VAR`` sentinel or structurally identical.
    A complete table under ``general`` then covers every instance of a call
    whose key is ``specific`` (A04-F002 subsuming-variant NAF)."""
    if len(general) != len(specific):
        return False
    return all(g is _VAR or g == s for g, s in zip(general, specific))


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
        except BaseException:
            # A04-F007: drop a poisoned "evaluating" entry on abnormal exit so
            # a later query recomputes (or re-raises) rather than silently
            # returning the partial set. Simple mode has no suspended consumers.
            table_store.pop(store_key, None)
            raise
        finally:
            pop_leader(entry)

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

    def tabled_dispatch(this_generator, _proceed, _fail, _catcher, *args_trail):
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
                    yield (_proceed, None)
                trail.undo(mark)
            yield (_fail, DONE)
            return

        # ── CONSUMER: an actively-leading ANCESTOR is evaluating this exact
        # table (a genuine cycle) — yield its known answers, then suspend. A
        # dormant "evaluating" entry (its leader finished without completing —
        # an SCC member from mutual recursion) instead falls through to the
        # LEADER path below and is RE-LED so it re-derives against grown answers
        # (A04-F001). ──
        if (entry is not None and entry.status == "evaluating"
                and _on_leader_stack(entry)):
            # Record the SCC dependency: the leader making this call depends on
            # `entry` (the ancestor) and must not complete before it does.
            cl = current_leader()
            if cl is not None:
                cl.scc_deps.add(entry)
            for i, stored in enumerate(entry.answers):
                if entry.conditions[i] is _FAILED:
                    continue
                mark = trail.mark()
                if _unify_answer(args, stored, trail):
                    yield (_proceed, None)
                trail.undo(mark)

            # Register as suspended consumer
            sc = SuspendedConsumer(
                this_generator, _proceed, args, trail, len(entry.answers)
            )
            entry.suspended.append(sc)

            # SUSPEND — trampoline intercepts this, sends DONE to _proceed
            signal = yield (_proceed, _TABLING_SUSPEND)

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
                        yield (_proceed, None)
                    trail.undo(mark)
                # If table still evaluating, re-suspend for more answers
                if entry.status == "evaluating":
                    signal = yield (_proceed, _TABLING_SUSPEND)
                else:
                    break

            yield (_fail, DONE)
            return

        # ── LEADER (fresh table) or RE-LEAD (a dormant "evaluating" SCC member
        # whose leader deferred completion — A04-F001): drive to fixpoint. ──
        if entry is None:
            entry = TableEntry()
            table_store[store_key] = entry
        push_leader(entry)

        try:
            # A04-F001: drive the dispatch to a FIXPOINT by re-running it until
            # no new answer appears, rather than a single pass followed by the
            # (broken) consumer-resume completion phase. On each re-run a
            # consumer (an inner call to this same still-evaluating table) sees
            # the grown answer set and routes it to its clause continuation,
            # which derives further answers. New answers stream to the leader's
            # caller exactly once (add_answer dedups). This makes tabled
            # solution sets clause-order-independent for single-table recursion;
            # mutual recursion additionally needs SCC-aware completion (below).
            changed = True
            while changed:
                old_count = len(entry.answers)
                _gen = StepGenerator(original_dispatch, this_generator,
                                     this_generator, this_generator, *args, trail)
                _st = yield (_gen, None)
                while _st is not DONE:
                    answer = freeze_args(args, trail)
                    delay_set = frozenset(entry._current_delays)
                    entry._current_delays.clear()
                    if entry.add_answer(answer, delay_set):
                        yield (_proceed, None)  # new answer to caller (incremental)
                    _st = yield (_gen, None)
                entry._current_delays.clear()
                # Consumers that suspended during this pass are re-derived by the
                # next pass; finish their parked generators cleanly.
                for sc in entry.suspended:
                    try:
                        sc.generator.close()
                    except BaseException:
                        pass
                entry.suspended.clear()
                changed = len(entry.answers) > old_count

            _resolve_conditions(entry, table_store)
        except BaseException:
            # A04-F007: an abnormal leader exit — GeneratorExit (once() takes
            # the first answer and abandons the solve loop) or a body exception
            # (e.g. ZeroDivisionError from `:=`) — must not leave a half-filled
            # "evaluating" entry behind. Later queries would take the consumer
            # path and silently return the partial answer set (and, orphaned at
            # the root, fabricate an unbound answer — A04-F008). Drop the entry
            # so the next query recomputes (or re-raises), and tear down any
            # suspended consumers registered on it so their callers don't hang.
            table_store.pop(store_key, None)
            for sc in entry.suspended:
                try:
                    sc.generator.close()
                except BaseException:
                    pass
            entry.suspended.clear()
            raise
        finally:
            pop_leader(entry)

        # A04-F001 SCC completion: a table that consumed an ANCESTOR still
        # evaluating (mutual recursion) is an SCC member — leave it dormant for
        # the SCC root to re-lead and complete. The root (no still-evaluating
        # dep) completes itself and sweeps its members to a fixpoint.
        deps_pending = any(
            dep is not entry and dep.status == "evaluating"
            for dep in entry.scc_deps
        )
        if not deps_pending:
            _complete_scc(entry, table_store)
        yield (_fail, DONE)

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
        root = StepGenerator(trampoline_dispatch, None, None, None, *args, trail)
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE or value is _TABLING_SUSPEND:
                    return   # A04-F008: suspend sentinel is not a solution
                yield None  # solution — bindings are live on trail
                gen, value = root.send(None)
            else:
                # Intercept _TABLING_SUSPEND → send DONE to parent
                if value is _TABLING_SUSPEND:
                    gen, value = gen.send(DONE)
                else:
                    gen, value = gen.send(value)

    return adapted
