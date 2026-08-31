"""clausal.logic.tabling — SLG tabling (memoisation with suspension).

Provides tabled evaluation for predicates marked with ``-table(pred/arity)``.
Tabled predicates cache their answers and terminate cyclic derivations via
SLG resolution.

Architecture
------------
A tabled predicate's dispatch function is wrapped so that:

- **Leader** (first call to a subgoal): drives the original dispatch to a
  FIXPOINT — re-running it until no new answer appears — collecting and
  caching answers (A04-F001).
- **Consumer** (recursive call while a leader for the same table is on the
  leader stack): yields currently cached answers, then suspends
  (``_TABLING_SUSPEND``); the leader's next fixpoint pass re-derives what the
  consumer would have produced and finishes the parked generator via close().
- **Complete** (cache hit after leader finished): yields all cached answers
  directly.

in_ trampoline mode, suspension is cooperative: the consumer yields
``(fail, _TABLING_SUSPEND)`` and the trampoline converts this to DONE so the
caller's while-loop exits normally — exactly like ordinary exhaustion.

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
from clausal.terms import Compound, Undefined

# ── Sentinels ──────────────────────────────────────────────────────────────

_VAR = object()              # unbound Var placeholder in subgoal keys
_TABLING_SUSPEND = object()  # consumer → trampoline: park me
_TABLING_RESUME = object()   # legacy: nothing sends this since the A04-F001
                             # fixpoint rework; kept only because external
                             # code (tests/test_tabling.py) still imports it
_FAILED = object()           # sentinel for invalidated conditional answers

# Canonical "unconditionally true" disjunction: one empty delay set
# (A04-F003 — conditions are a disjunction of per-derivation delay sets).
_UNCONDITIONAL = frozenset({frozenset()})

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


# ── Drive-episode tracking (A04-F007) ────────────────────────────────────
#
# The GeneratorExit route for abandonment cleanup (once() takes an answer and
# drops the solve loop) is NOT reliable: StepGenerator.close() closes only its
# OWN inner generator, and any SuspendedConsumer registered on a table entry
# keeps the parked tabled-wrapper frame permanently reachable
# (module → db.table_store → entry.suspended → consumer gen → parent chain →
# wrapper frame), so the wrapper's except-BaseException repair never runs —
# even after gc.collect() — and the module is poisoned for life (every later
# query silently returns the partial answer set). The root driver therefore
# tracks the table entries CREATED beneath it and repairs them itself.


class _DriveContext(threading.local):
    def __init__(self):
        self.episodes: list[list] = []

_drive_ctx = _DriveContext()


def begin_drive_episode() -> None:
    """Open a root-drive episode: entries created below are tracked."""
    _drive_ctx.episodes.append([])


def _record_created_entry(entry, table_store, store_key) -> None:
    episodes = _drive_ctx.episodes
    if episodes:
        episodes[-1].append((entry, table_store, store_key))


def end_drive_episode() -> None:
    """Close a root-drive episode; repair abandoned tables (A04-F007).

    If any entry created in this episode is still on the leader stack, the
    drive was abandoned mid-fixpoint (a normally-finished wrapper always pops
    its leader): drop every still-``evaluating`` entry the episode created —
    from the store (identity-guarded), the leader stack, and its suspended
    consumers — so later queries recompute instead of silently consuming the
    partial answer set. Entries that completed normally are untouched, as are
    entries belonging to enclosing episodes (nested drives from ``++``
    escapes). Idempotent with the wrapper's own except-BaseException repair,
    which still runs whenever GC eventually finalises the parked frame.
    """
    episodes = _drive_ctx.episodes
    if not episodes:
        return
    created = episodes.pop()
    if not created:
        return
    created_ids = {id(entry) for entry, _, _ in created}
    if any(id(e) in created_ids for e in _leader_ctx.stack):
        # Abandoned mid-fixpoint — repair.
        for entry, store, key in created:
            if entry.status != "evaluating":
                continue
            if store.get(key) is entry:
                del store[key]
            for sc in entry.suspended:
                try:
                    sc.generator.close()
                except BaseException:
                    pass
            entry.suspended.clear()
            pop_leader(entry)
    if episodes:
        # Nested episode (a NAF spawn, a ++-escape): hand every created
        # entry up to the enclosing episode, whether we completed or were
        # abandoned — the ROOT close is the one place that can cover repair
        # and cross-store resolution for everything the whole drive touched
        # (a spawn can complete tables in a FOREIGN module's store, which
        # the wrappers' own root-exit passes — each bound to its closed-over
        # store — would never revisit).
        episodes[-1].extend(created)
        return
    # A04-F003: the root episode is closing. An ABANDONED root never reached
    # the wrapper's root-exit resolution pass, and even a normal one only
    # resolved its own store — without a pass here, conditions in other
    # touched stores freeze at whatever was resolvable mid-drive (e.g.
    # win("b") forever Undefined although win("a") completed True moments
    # later). Run the global pass over every store this drive touched, once
    # no leader is active.
    if not _leader_ctx.stack:
        seen = set()
        for _entry, store, _key in created:
            if id(store) not in seen:
                seen.add(id(store))
                _resolve_all_conditions(store)


def _complete_scc(root: TableEntry, table_store) -> None:
    """Mark *root* complete, then sweep dormant SCC members (A04-F001).

    A member deferred completion while it (transitively) consumed a
    still-evaluating ancestor. Dormant members are re-led to an inner fixpoint
    on every pass of the enclosing leader's fixpoint loop, so when the root of
    the component stabilises, so have they — every dormant member whose
    dependencies cannot reach a STILL-ACTIVE leader (an entry on the leader
    stack, still growing) may complete now.

    Members can depend on EACH OTHER (deps recorded across different re-lead
    episodes form cycles among dormant members), so completion is decided per
    blocked-set rather than per entry: a member is blocked only if some dep is
    an active on-stack leader, unknown to this store's dormant set (e.g. an
    abandoned entry), or itself blocked. The unblocked residue reached a joint
    fixpoint under *root* and completes as a group.
    """
    root.status = "complete"
    members = [e for e in table_store.values()
               if e.status == "evaluating" and not _on_leader_stack(e)
               and e.scc_deps]
    if not members:
        return
    member_ids = {id(e) for e in members}
    blocked: set[int] = set()
    changed = True
    while changed:
        changed = False
        for e in members:
            if id(e) in blocked:
                continue
            for dep in e.scc_deps:
                if dep is e or dep.status != "evaluating":
                    continue
                if (_on_leader_stack(dep) or id(dep) in blocked
                        or id(dep) not in member_ids):
                    blocked.add(id(e))
                    changed = True
                    break
    for e in members:
        if id(e) not in blocked:
            e.status = "complete"


# ── Table entry ───────────────────────────────────────────────────────────


def _simplify_disjuncts(disjuncts: frozenset) -> frozenset:
    """Canonicalize a disjunction of delay sets (A04-F003).

    An empty delay set means one derivation is unconditional — the answer is
    True and every other disjunct is redundant. Otherwise drop any disjunct
    that is a strict superset of another (absorption: ``D ∨ (D ∧ E) = D``).
    """
    if frozenset() in disjuncts:
        return _UNCONDITIONAL
    return frozenset(
        d for d in disjuncts
        if not any(other < d for other in disjuncts)
    )


class TableEntry:
    """Stores status, answers, and suspended consumers for one subgoal."""
    __slots__ = ("status", "answers", "answer_set", "_answer_index",
                 "suspended", "conditions", "_current_delays", "scc_deps")

    def __init__(self):
        self.status: str = "evaluating"       # "evaluating" | "complete"
        self.answers: list[tuple] = []
        self.answer_set: set = set()   # canonical answer keys (A04-F005/F006)
        self._answer_index: dict = {}  # canonical key → index into answers
        self.suspended: list = []             # list of SuspendedConsumer
        # Parallel to answers. Each element is a DISJUNCTION of delay sets —
        # frozenset[frozenset[DelayedNegation]] — one inner set per derivation
        # of the answer (A04-F003: WFS truth is an OR over derivations, and
        # keeping only the first derivation's delays lost the one that
        # resolves to true). ``_FAILED`` when every disjunct was invalidated.
        self.conditions: list = []
        self._current_delays: set[DelayedNegation] = set()
        # A04-F001 SCC completion: entries this one consumed as an evaluating
        # ANCESTOR (mutual recursion). While any dep is still evaluating this
        # entry is an SCC member and must not complete on its own.
        self.scc_deps: set = set()            # set[TableEntry]

    def add_answer(self, answer: tuple, delay_set: frozenset | None = None) -> int | None:
        """Add a frozen answer tuple.  Returns its INDEX if the tuple was new.

        The index (never a bare bool: index 0 is falsy, so callers test
        ``is not None``) lets the root-lead deferral in the trampoline
        wrapper record which row it withheld without re-deriving the private
        canonical key.  ``None`` means the visible answer set did not change.

        Dedup uses the canonical, hashable key (A04-F005) — a frozen answer may
        contain a list/dict/set/term instance, which are unhashable and cannot
        go directly in ``answer_set``. The key also type-distinguishes numeric
        leaves (A04-F006), so 1/True/1.0 answers are kept distinct exactly as
        the untabled dispatch would. The original frozen tuple is stored in
        ``answers`` for unification.

        A re-derivation of a known answer under a DIFFERENT delay set unions
        that set into the answer's disjunction (A04-F003) and still returns
        None — the tuple was already streamed to the caller; only its truth
        got sharper. An unconditional re-derivation erases the delays.
        """
        ds = delay_set if delay_set is not None else frozenset()
        key = make_subgoal_key(answer, None)
        idx = self._answer_index.get(key)
        if idx is not None:
            conds = self.conditions[idx]
            if conds is _FAILED:
                # Every earlier disjunct was invalidated; this is a live one.
                # Report the tuple as NEW: consumers skip _FAILED rows during
                # replay, so anyone iterating this lead has not seen it —
                # returning None here would silently drop it from their
                # joins (a lost solution, not a duplicate).
                self.conditions[idx] = _simplify_disjuncts(frozenset({ds}))
                return idx
            self.conditions[idx] = _simplify_disjuncts(conds | {ds})
            return None
        self.answer_set.add(key)
        idx = len(self.answers)
        self._answer_index[key] = idx
        self.answers.append(answer)
        self.conditions.append(_simplify_disjuncts(frozenset({ds})))
        return idx

    def truth_value(self, i: int):
        """Return the i-th answer's WFS truth value: True, False, or ``Undefined``.

        The third value is the strong-Kleene ``Undefined`` singleton, not a
        string: WFS *is* a three-valued semantics over K3, so an unfounded
        (conditionally delayed) answer denotes the same lattice element that
        ``.clausal`` code writes as ``Undefined``.  Using the singleton also means
        ``bool(...)`` on the result raises rather than silently reporting the
        old truthy ``"undefined"`` string as true.

        True iff some derivation is delay-free; False iff every derivation
        was invalidated; Undefined otherwise (A04-F003 disjunction).
        """
        c = self.conditions[i]
        if c is _FAILED:
            return False
        if any(not d for d in c):
            return True
        return Undefined

    def delays_for(self, i: int) -> frozenset:
        """Flat view of the i-th answer's unresolved delayed negations —
        the union over its live disjuncts. Empty unless truth is Undefined."""
        c = self.conditions[i]
        if c is _FAILED or any(not d for d in c):
            return frozenset()
        return frozenset().union(*c) if c else frozenset()


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


def _scan_complete_answers(entry, args):
    """Scan a COMPLETE table's answers for matches against *args*.

    Returns ``(has_unconditional, has_conditional)``: whether some non-failed
    answer with an empty / non-empty delay set unifies with the call. Uses a
    scratch trail — the caller's bindings are untouched. Short-circuits on the
    first unconditional match (it alone decides the negation).
    """
    from clausal.logic.variables import Trail as _Trail
    scratch = _Trail()
    has_conditional = False
    for i, stored in enumerate(entry.answers):
        if entry.conditions[i] is _FAILED:
            continue
        mark = scratch.mark()
        matched = _unify_answer(list(args), list(stored), scratch)
        scratch.undo(mark)
        if matched:
            if entry.truth_value(i) is True:
                return True, has_conditional
            has_conditional = True
    return False, has_conditional


def _propagate_answer_delays(entry, i) -> None:
    """POSITIVE delay propagation (A04-F003 follow-up): a derivation that
    consumes a CONDITIONAL answer is itself conditional on the same delayed
    literals — WFS answer clauses carry delay lists through positive joins,
    not only through negation. Without this, a rule reading a conditional
    answer out of a completed table mints an unconditionally-true answer
    from an Undefined premise.

    Approximation, deliberately matching the existing negative-delay
    bookkeeping: the FLAT union of the answer's live disjuncts is added to
    the innermost active leader's in-progress delay set. Per-disjunct
    precision (and exact leader attribution when the consuming continuation
    is resumed under an unrelated mid-stream leader) is future work; the
    union direction errs toward Undefined, and the disjunction-of-
    derivations model keeps a genuinely unconditional derivation True
    regardless."""
    c = entry.conditions[i]
    if c is _FAILED or c is _UNCONDITIONAL:
        return  # the overwhelmingly common rows — one identity test each
    leader = current_leader()
    if leader is None:
        return
    delays = entry.delays_for(i)
    if delays:
        leader._current_delays |= delays


def _streaming_consumer_leader(entry):
    """Attribution target for a STREAMING leader's incremental yields:
    the leader immediately BELOW *entry*'s own position on the stack —
    not stack[-2] (a deeper leader may be parked mid-stream above us) and
    not current_leader() (that is *entry* itself).

    Returns None — no propagation — when *entry* is the bottom of a spawn
    segment: a spawn drive's root yields land in a discard loop, not in
    any derivation, and crediting its delays to the leader outside the
    boundary would contaminate an unrelated derivation with foreign
    conditions (which a False-resolving delay could then wrongly kill)."""
    stack = _leader_ctx.stack
    for idx in range(len(stack) - 1, -1, -1):
        if stack[idx] is entry:
            below = idx - 1
            boundaries = _spawn_ctx.boundaries
            if boundaries and below < boundaries[-1]:
                return None
            return stack[below] if below >= 0 else None
    return None


def _delay_negation(functor, arity, key, args, trail):
    """Record ``not functor(args)`` as a DelayedNegation on the current leader
    (conditional success). With no leader in scope there is nowhere to attach
    the condition — the negation still succeeds, matching how ``query()``/
    ``call()`` surface undefined answers alongside true ones."""
    frozen = freeze_args(args, trail)
    dn = DelayedNegation(functor, arity, key, frozen)
    leader = current_leader()
    if leader is not None:
        leader._current_delays.add(dn)


def _key_has_var(k) -> bool:
    """True if a normalized subgoal key contains the ``_VAR`` sentinel
    anywhere — i.e. the call it keys is nonground."""
    if k is _VAR:
        return True
    if isinstance(k, (tuple, frozenset)):
        return any(_key_has_var(x) for x in k)
    return False


# A04-F003 spawn-depth guard: spawns nest on the Python stack (each drive is
# synchronous inside _naf_tabled), and a negated call whose ground arguments
# GROW per level — ``Pn(X) <- (Y == X + 1, not Pn(Y))`` — would otherwise
# spawn unboundedly and die in a bare RecursionError. Beyond the cap the
# negation falls back to the conservative delay path (Undefined), the
# pre-spawn behaviour. Derived from the interpreter's recursion limit
# rather than a magic constant (measured ~4 frames per spawn level; 8 in
# the divisor leaves 2x headroom plus the query's own baseline depth), so
# raising sys.setrecursionlimit buys deeper definite chains. Deep POSITIVE
# call chains are unaffected (they trampoline).
def _spawn_depth_cap() -> int:
    import sys
    return max(32, (sys.getrecursionlimit() - 200) // 8)


class _SpawnContext(threading.local):
    def __init__(self):
        self.depth = 0
        # Leader-stack lengths at each active spawn's start: streaming
        # attribution must not cross the innermost boundary (see
        # _streaming_consumer_leader).
        self.boundaries: list[int] = []

_spawn_ctx = _SpawnContext()


def _drive_dispatch_to_completion(dispatch, args) -> None:
    """Drive a trampoline-mode dispatch to exhaustion, discarding solutions.

    A04-F003 negative-subgoal spawning: ``not p(args)`` with no table for the
    variant EVALUATES ``p(args)`` — the drive's side effect is a completed (or,
    inside an SCC, dormant) table entry the caller then decides against.
    Ground args + a scratch trail keep the caller's bindings untouched.

    The pull loop is the converged ``solutions()`` driver (suspension is
    exhaustion; FINAL retires the root; malformed steps raise; PEP-479
    StopIteration converts to exhaustion) — not another hand-rolled twin.

    A table this drive creates (or re-leads) can end still-``evaluating``:
    it consumed a still-evaluating ancestor and went dormant (A04-F001).
    The CALLER must then delay the negation — and the negation site
    re-spawns the dormant entry on every pass of the enclosing fixpoint
    (the exact-entry branch of ``_naf_tabled`` falls through for dormant
    entries instead of delaying), which re-leads it against the ancestor's
    grown answers. That is what makes ``_complete_scc``'s root-exit sweep
    of dormant members sound for spawn-created tables too: by the time the
    root stabilises, so have they.
    """
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.logic.variables import Trail as _Trail
    scratch = _Trail()
    root = StepGenerator(dispatch, None, None, None, *args, scratch)
    begin_drive_episode()
    try:
        solutions(root, snapshot=lambda: None)  # exhaust; answers land in the table
    finally:
        try:
            root.close()
        finally:
            end_drive_episode()


def _naf_tabled(functor, arity, args, trail, table_store, db=None):
    """Check negation-as-failure for a tabled predicate (WFS-aware).

    Returns True if negation succeeds (conditionally or unconditionally),
    False if negation fails (the positive goal has an unconditional answer).

    when the target table is still evaluating (cycle through negation),
    creates a DelayedNegation and attaches it to the current leader's
    delay set — the answer is conditional until resolution. A COMPLETE
    table whose only matching answers are themselves conditional
    (Undefined) delays the same way: ``not Undefined`` is Undefined, so
    failing the negation outright would turn "no determinate answer" into
    a definite "no" (todo/wfs-undefined-lost-at-query-surface.md — the
    root of the symmetric-win ground-query asymmetry).

    With ``db`` (the compiled seam passes it as ``$naf_db``), a ground
    negated call with NO table and no complete subsuming table SPAWNS the
    positive subgoal and decides against the completed result (A04-F003)
    instead of conservatively succeeding — the source of mode/order-dependent
    answer sets. ``db=None`` (legacy callers) keeps the conservative path.
    """
    key = make_subgoal_key(args, trail)
    store_key = (functor, arity, key)
    entry = table_store.get(store_key)

    if entry is not None and entry.status == "complete":
        # Standard NAF on complete table: an unconditional answer fails the
        # negation; a conditional-only match delays it (undefined).
        unconditional, conditional = _scan_complete_answers(entry, args)
        if unconditional:
            return False  # positive answer exists → negation fails
        if conditional:
            _delay_negation(functor, arity, key, args, trail)
        return True  # no determinate matching answer → negation succeeds

    if (entry is not None and entry.status == "evaluating"
            and _on_leader_stack(entry)):
        # Genuine cycle through negation (the target is an actively-leading
        # ancestor) — delay.
        _delay_negation(functor, arity, key, args, trail)
        return True  # conditionally succeed
    # A DORMANT evaluating entry (its leader finished without completing —
    # an SCC member) falls through: the spawn path below RE-LEADS it against
    # the ancestor's grown answers, exactly like the wrapper's own re-lead
    # path for positive calls (A04-F001/F003). Delaying on it instead would
    # freeze it with the partial answers spawn time happened to see.

    # No exact-variant entry. A COMPLETE same-functor entry whose variant key
    # SUBSUMES this call already knows the full answer set for the call's
    # instances (A04-F002): e.g. a complete ``tp(_,_)`` table answers
    # ``not tp(1,2)`` even though there is no exact ``tp(1,2)`` entry. Check the
    # call against such a table before any fallthrough.
    for (f, a, k), e in table_store.items():
        if f != functor or a != arity or e.status != "complete":
            continue
        if not _key_subsumes(k, key):
            continue
        unconditional, conditional = _scan_complete_answers(e, args)
        if unconditional:
            return False  # subsuming complete table has a definite answer
        if conditional:
            # The covering answer is itself Undefined — the negation is too.
            _delay_negation(functor, arity, key, args, trail)
        # A subsuming complete table with no determinate matching answer means
        # the goal is not definitely true for this call → negation succeeds.
        return True

    # A04-F003 (spawn-always): no exact table and no complete subsuming one —
    # EVALUATE the positive subgoal so the negation is decided by a real
    # answer set rather than conservatively succeeding. Only for ground calls
    # (a nonground spawn would bind the caller's vars) with a live dispatch.
    # An exact table exists from the drive's first step, so cyclic re-entries
    # hit the evaluating-entry delay above — this terminates exactly like any
    # SLG evaluation. If the spawned entry consumed a still-evaluating
    # ancestor it stays DORMANT (A04-F001 SCC) rather than completing on
    # partial answers; fall through to the delay path in that case.
    if (db is not None and not _key_has_var(key)
            and _spawn_ctx.depth < _spawn_depth_cap()):
        dispatch = db.get_dispatch(functor, arity)
        # Only ever drive the predicate's OWN tabled wrapper: get_dispatch
        # falls back to the builtin registry, and driving a same-name
        # builtin to exhaustion would run its side effects while creating
        # no table at all.
        if getattr(dispatch, "_tabled_for", None) == (functor, arity):
            _spawn_ctx.depth += 1
            _spawn_ctx.boundaries.append(len(_leader_ctx.stack))
            try:
                _drive_dispatch_to_completion(dispatch, args)
            finally:
                _spawn_ctx.boundaries.pop()
                _spawn_ctx.depth -= 1
            if not _leader_ctx.stack:
                _resolve_all_conditions(table_store)
            entry = table_store.get(store_key)
            if entry is not None and entry.status == "complete":
                unconditional, conditional = _scan_complete_answers(entry, args)
                if unconditional:
                    return False
                if conditional:
                    _delay_negation(functor, arity, key, args, trail)
                return True
            # The drive could not COMPLETE the table (it consumed a
            # still-evaluating ancestor and stays dormant, to be re-led by
            # a later pass) — the truth is undecided at this point in the
            # fixpoint: delay.
            _delay_negation(functor, arity, key, args, trail)
            return True

    # Check if ANY variant of this predicate is evaluating — if so, we're in a
    # cycle through negation and must delay. This handles cases like: leader
    # evaluates win(_), body calls not win(2), a different variant but still
    # part of the same SLG cycle.
    for (f, a, _k), e in table_store.items():
        if f == functor and a == arity and e.status == "evaluating":
            _delay_negation(functor, arity, key, args, trail)
            return True  # conditionally succeed

    # No entry at all and no way (or no need) to spawn — succeed
    # conservatively (the historical behaviour, kept for ``db=None`` legacy
    # callers and nonground negated calls).
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


def _delay_target_entry(dn, table_store):
    """Find the table that decides ``dn``: the exact-variant entry, else a
    COMPLETE same-functor entry whose key subsumes it (A04-F002/F003 — a delay
    recorded against a variant that was never led exactly, e.g. under a
    subsuming leader, is still decided by the subsuming completed table)."""
    target = table_store.get((dn.functor, dn.arity, dn.key))
    if target is not None:
        return target
    for (f, a, k), e in table_store.items():
        if (f == dn.functor and a == dn.arity and e.status == "complete"
                and _key_subsumes(k, dn.key)):
            return e
    return None


def _resolve_one_delay(dn, table_store):
    """Resolve a single delayed negation: True (negation holds — drop it),
    False (an unconditional positive answer exists — the disjunct fails),
    or None (still undecidable — keep the delay).

    Matching MUST mirror the NAF-time decision, which unifies the call
    against stored answers (``_scan_complete_answers``): equality would miss
    a nonground stored answer (a universal fact covering the delayed call)
    or a nonground delayed call, flipping the literal's truth depending on
    WHEN the target table happened to complete."""
    target_entry = _delay_target_entry(dn, table_store)
    if target_entry is None or target_entry.status != "complete":
        return None
    unconditional, conditional = _scan_complete_answers(
        target_entry, dn.frozen_args)
    if unconditional:
        return False
    if conditional:
        return None
    return True


def _resolve_conditions(entry, table_store) -> bool:
    """Resolve delayed negations after SLG completion. Returns whether any
    condition changed (so ``_resolve_all_conditions`` can run to a fixpoint).

    Per answer, per DISJUNCT (A04-F003 — one delay set per derivation):
    - a delay whose target holds a delay-free matching answer falsifies its
      disjunct (that derivation is gone);
    - a delay whose target has no matching answer is satisfied and dropped;
    - a delay whose target is undecided (evaluating, never evaluated, or
      matching only conditional answers) is kept.
    An answer is _FAILED only when EVERY disjunct falsified; it is True as
    soon as any disjunct empties.
    """
    any_change = False
    changed = True
    while changed:
        changed = False
        for i in range(len(entry.answers)):
            conds = entry.conditions[i]
            if conds is _FAILED or any(not d for d in conds):
                continue  # already resolved or unconditionally true

            new_disjuncts = set()
            for disjunct in conds:
                new_delays = set()
                disjunct_failed = False
                for dn in disjunct:
                    verdict = _resolve_one_delay(dn, table_store)
                    if verdict is False:
                        disjunct_failed = True
                        break
                    if verdict is None:
                        new_delays.add(dn)
                    # verdict is True → drop the delay
                if not disjunct_failed:
                    new_disjuncts.add(frozenset(new_delays))

            if not new_disjuncts:
                entry.conditions[i] = _FAILED
                changed = any_change = True
            else:
                new_conds = _simplify_disjuncts(frozenset(new_disjuncts))
                if new_conds != conds:
                    entry.conditions[i] = new_conds
                    changed = any_change = True
    return any_change


def _resolve_all_conditions(table_store) -> None:
    """Cross-table resolution at root exit (A04-F003 global pass).

    Per-leader resolution runs while sibling SCC members may still be
    evaluating, so a delay can stay undecided at that point and its owner's
    table completes with a stale condition. Once the ROOT leader finishes,
    every table it (transitively) drove is complete — iterate resolution over
    all of them to a joint fixpoint so late-completing targets propagate
    (e.g. ``win("a")`` turning True must fail ``win("b")``'s delayed
    ``not win("a")`` even though win("b") completed first)."""
    changed = True
    while changed:
        changed = False
        for e in list(table_store.values()):
            if e.status != "complete":
                continue
            # Skip entries with only trivial conditions — two identity
            # tests per row versus a full resolution fixpoint. This runs on
            # every root exit (including once()-style abandonments over
            # long-lived stores), so the negation-free common case must
            # stay near-free.
            if not any(c is not _FAILED and c is not _UNCONDITIONAL
                       for c in e.conditions):
                continue
            if _resolve_conditions(e, table_store):
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
                    _propagate_answer_delays(entry, i)
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
                        _propagate_answer_delays(entry, i)
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
                changed = False
                mark = trail.mark()
                for _ in original_dispatch(*args, trail, None):
                    answer = freeze_args(args, trail)
                    delay_set = frozenset(entry._current_delays)
                    entry._current_delays.clear()
                    if entry.add_answer(answer, delay_set) is not None:
                        # New tuple OR a revived _FAILED row — both change
                        # the visible answer set, so run another pass.
                        changed = True
                trail.undo(mark)
                entry._current_delays.clear()

            _resolve_conditions(entry, table_store)
        except BaseException:
            # A04-F007: drop a poisoned "evaluating" entry on abnormal exit so
            # a later query recomputes (or re-raises) rather than silently
            # returning the partial set. Simple mode has no suspended consumers.
            # Identity-guarded against out-of-order GC finalisation replacing
            # a fresh entry installed under the same key by a later query.
            if table_store.get(store_key) is entry:
                del table_store[store_key]
            raise
        finally:
            pop_leader(entry)

        entry.status = "complete"
        if not _leader_ctx.stack:
            _resolve_all_conditions(table_store)  # A04-F003 root-exit pass
        for i, stored in enumerate(entry.answers):
            if entry.conditions[i] is _FAILED:
                continue
            mark = trail.mark()
            if _unify_answer(args, stored, trail):
                _propagate_answer_delays(entry, i)
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
                    _propagate_answer_delays(entry, i)
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
                    _propagate_answer_delays(entry, i)
                    yield (_proceed, None)
                trail.undo(mark)

            # Register as suspended consumer
            sc = SuspendedConsumer(
                this_generator, _proceed, args, trail, len(entry.answers)
            )
            entry.suspended.append(sc)

            # SUSPEND — the trampoline intercepts the sentinel and sends DONE
            # to the yielded target. Suspension means "no more answers FOR
            # NOW" — an exhaustion signal — so it must route to _fail exactly
            # like the terminal ``yield (_fail, DONE)`` below. Routing it to
            # _proceed (the old behaviour) breaks under continuation TCO: for
            # a last-goal call site _proceed is the CALLER'S proceed (e.g. the
            # enclosing tabled wrapper), so the DONE faked that whole frame's
            # exhaustion — the enclosing leader ended its fixpoint pass early
            # and any mid-flight re-led member was abandoned on the leader
            # stack (A04-F001: lost joins / members frozen "evaluating").
            yield (_fail, _TABLING_SUSPEND)

            # Nothing sends _TABLING_RESUME any more: the leader re-derives a
            # suspended consumer's answers by re-running its dispatch to a
            # fixpoint (A04-F001) and finishes parked consumers via close().
            # If this frame is ever resumed anyway, report exhaustion.
            yield (_fail, DONE)
            return

        # ── LEADER (fresh table) or RE-LEAD (a dormant "evaluating" SCC member
        # whose leader deferred completion — A04-F001): drive to fixpoint. ──
        if entry is None:
            entry = TableEntry()
            table_store[store_key] = entry
            _record_created_entry(entry, table_store, store_key)  # A04-F007
            replay_count = 0
        else:
            # A04-F001 (re-lead replay): this caller has seen NONE of the
            # already-tabled answers, but the fixpoint loop below streams only
            # NEW answers (add_answer dedups the old ones away). Replay the
            # known answers first — exactly like the consumer and complete
            # paths — or joins against them are silently lost (e.g. a clause
            # calling this table twice never pairs an old first-call answer
            # with a new second-call answer). No double delivery: everything
            # replayed here dedups inside the drive.
            replay_count = len(entry.answers)
        # Root-lead deferral (todo/tabled-conditional-answers-stream-before-
        # invalidation.md): a ROOT leader's incremental yields land in the
        # surface caller (solve()/call()/query()), which cannot retract an
        # answer that root-exit resolution later invalidates (_FAILED) — the
        # same ground query then returns a different answer SET on the first
        # call vs the second. So the outermost leader (empty leader stack at
        # push — the one whose exit runs global resolution) DEFERS conditional
        # answers and delivers the survivors after resolution, while
        # unconditional answers keep streaming untouched. Inner (non-root)
        # leaders still stream conditionals: their consumers are other tabled
        # frames mid-fixpoint, which legitimately join against them and
        # re-derive per pass. A spawn-discard root (also pushed on an empty
        # stack) defers into _drive_dispatch_to_completion's discard loop —
        # harmless, the yields are discarded either way.
        root_lead = not _leader_ctx.stack
        deferred: set[int] = set()   # answer indices withheld from the root
        push_leader(entry)

        try:
            for i in range(replay_count):
                if entry.conditions[i] is _FAILED:
                    continue
                if root_lead and entry.conditions[i] is not _UNCONDITIONAL:
                    # Re-lead at the root: conditional rows join the same
                    # deferred delivery as newly-derived ones.
                    deferred.add(i)
                    continue
                mark = trail.mark()
                if _unify_answer(args, entry.answers[i], trail):
                    if entry.conditions[i] is not _UNCONDITIONAL:
                        replay_delays = entry.delays_for(i)
                        if replay_delays:
                            # Same streaming-site attribution as above.
                            consumer = _streaming_consumer_leader(entry)
                            if consumer is not None:
                                consumer._current_delays |= replay_delays
                    yield (_proceed, None)
                trail.undo(mark)
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
                changed = False
                _gen = StepGenerator(original_dispatch, this_generator,
                                     this_generator, this_generator, *args, trail)
                _st = yield (_gen, None)
                while _st is not DONE:
                    answer = freeze_args(args, trail)
                    delay_set = frozenset(entry._current_delays)
                    entry._current_delays.clear()
                    new_idx = entry.add_answer(answer, delay_set)
                    if new_idx is not None:
                        # New tuple OR a revived _FAILED row — both change the
                        # visible answer set: stream it and run another pass.
                        changed = True
                        if delay_set and root_lead:
                            # Root-lead deferral: the surface caller must not
                            # see a conditional answer that root-exit
                            # resolution may yet invalidate. Withhold it; the
                            # survivors are delivered after resolution below.
                            # (No positive propagation either — a root lead
                            # has no leader below it to credit.)
                            deferred.add(new_idx)
                        else:
                            if delay_set:
                                # Positive propagation for the STREAMING site:
                                # the consumer of this incremental yield is the
                                # leader below OUR OWN stack position (a deeper
                                # leader may be parked mid-stream above us), and
                                # a spawn-discard root propagates to nobody.
                                consumer = _streaming_consumer_leader(entry)
                                if consumer is not None:
                                    consumer._current_delays |= delay_set
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

            _resolve_conditions(entry, table_store)
        except BaseException:
            # A04-F007: an abnormal leader exit — GeneratorExit (once() takes
            # the first answer and abandons the solve loop) or a body exception
            # (e.g. ZeroDivisionError from `eval_/2`) — must not leave a half-filled
            # "evaluating" entry behind. Later queries would take the consumer
            # path and silently return the partial answer set (and, orphaned at
            # the root, fabricate an unbound answer — A04-F008). Drop the entry
            # so the next query recomputes (or re-raises), and tear down any
            # suspended consumers registered on it so their callers don't hang.
            # Identity-guarded: GC may deliver GeneratorExit to this parked
            # frame long after end_drive_episode() already repaired the store
            # and a LATER query installed a fresh entry under the same key —
            # a blind pop would destroy that innocent entry (A04-F007).
            if table_store.get(store_key) is entry:
                del table_store[store_key]
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
            # A04-F003: at ROOT exit every driven table is complete — run the
            # global resolution pass so late-completing targets finalize
            # conditions in tables that completed earlier.
            if not _leader_ctx.stack:
                _resolve_all_conditions(table_store)
        else:
            # A04-F001 (transitive): this entry stays dormant, and its
            # ENCLOSING leader transitively depends on the same still-active
            # ancestors (Tarjan lowlink propagation). Without this edge, a
            # middle member of a ≥3-node cycle — which only ever called FRESH
            # nested leaders, never an on-stack ancestor directly — ends with
            # no recorded deps of its own and completes mid-fixpoint, freezing
            # the whole component with a wrong/empty answer set. Propagate
            # only deps still ON the leader stack: an off-stack (dormant) dep
            # is resolved by its root's `_complete_scc` sweep, and propagating
            # it above its own root would deadlock completion.
            cl = current_leader()
            if cl is not None:
                for dep in entry.scc_deps:
                    if (dep is not cl and dep is not entry
                            and dep.status == "evaluating"
                            and _on_leader_stack(dep)):
                        cl.scc_deps.add(dep)
        # Root-lead deferred delivery: fixpoint done and (on the normal path)
        # global resolution has run — deliver the withheld conditional rows
        # that SURVIVED (skipping _FAILED), re-unifying against the call args
        # exactly like the COMPLETE path. Index order keeps delivery
        # deterministic. A caller that stopped pulling earlier (once()-style)
        # simply never resumes this generator — normal abandonment.
        for i in sorted(deferred):
            if entry.conditions[i] is _FAILED:
                continue
            mark = trail.mark()
            if _unify_answer(args, entry.answers[i], trail):
                yield (_proceed, None)
            trail.undo(mark)
        yield (_fail, DONE)

    tabled_dispatch._tabled_for = (functor, arity)
    return tabled_dispatch


def ensure_tabled_wrapper(db, functor, arity, fn):
    """Return *fn* wrapped for tabling, or *fn* itself if it needs no wrapper.

    The one place that decides whether a dispatch function has to be the SLG
    wrapper.  Idempotent: ``make_tabled_wrapper_trampoline`` stamps its result
    with ``_tabled_for``, so handing an already-wrapped function back through
    here does not stack a second table lookup on top of the first.

    Being idempotent is what lets *both* the load-time wrap (import_hook /
    compiler_v2 step 6) and the compile-time wrap in ``_install`` — which is
    what makes the wrapper survive an ``assertz``-driven recompile — call it
    without either having to know whether the other already ran.
    """
    if db is None or not db.is_tabled(functor, arity):
        return fn
    if getattr(fn, "_tabled_for", None) == (functor, arity):
        return fn
    return make_tabled_wrapper_trampoline(fn, functor, arity, db.table_store)


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
        begin_drive_episode()  # A04-F007: repair tables if abandoned mid-drive
        try:
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
        finally:
            try:
                root.close()
            finally:
                end_drive_episode()

    return adapted
