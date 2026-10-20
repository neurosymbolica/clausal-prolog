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

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.predicate import is_term_instance, tabled_home_of, term_field_names
from clausal.terms import ConcreteSeg, SegBytes, SegList, SegString, Undefined, VarSeg
from clausal.logic.cells import is_cell, intern_cell, is_intern_enabled, is_chars, chars_text

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
    """Represents a conditional dependency: 'not functor(frozen_args)' must hold.

    ``store`` (optional, excluded from equality/hash) is the table store the
    negated call's entry lives in.  A cross-module ``not Imported(...)``
    delays against the callee's HOME store, which is not the store of the
    entry carrying the delay — resolution (``_delay_target_entry``) follows
    ``store`` when set so the delay can still be decided.  ``None`` keeps the
    historical same-store lookup.
    """
    __slots__ = ("functor", "arity", "key", "frozen_args", "store")

    def __init__(self, functor: str, arity: int, key: tuple, frozen_args: tuple,
                 store: dict | None = None):
        self.functor = functor
        self.arity = arity
        self.key = key
        self.frozen_args = frozen_args
        self.store = store

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
        # Monotonic count of pushes.  A throwaway leader (seam.judged_answers)
        # compares it before and after its solve to learn whether any REAL
        # table was driven beneath it -- if none was, there is nothing to
        # resolve at its exit and the goal pays nothing.
        self.pushes: int = 0
        # One list per JUDGING leader currently on the stack, collecting the
        # table stores actually driven beneath it.  A real ROOT leader runs
        # the global resolution pass over its own store when it exits on an
        # empty stack; under a judging leader no inner leader is ever the
        # root, so the judging leader runs the pass itself -- and it must run
        # it over every store the drive TOUCHED, not only the ones its own
        # delays happen to name (a cross-module tabled call whose conditions
        # nobody carried up would otherwise never be resolved).
        self.driven_stores: list[list] = []
        # Leader segments lifted off `stack` by a judging generator that is
        # SUSPENDED at a yield (seam.judged_answers' detach/reattach).  They
        # are still actively leading -- the generator is alive and will resume
        # into them -- so cycle detection has to keep seeing them, even though
        # they must not be the attribution target while another goal runs.
        self.detached: list[list] = []
        # XSB's run-time cut check (D61 Q1, ``cut_over_incomplete``): every
        # tabled call frame that delivers answers from an INCOMPLETE table (a
        # consumer of a table under evaluation, or an SCC member handing back
        # what it has while an ancestor is still evaluating -- D68: every
        # other leader completes its table first) has a record ``[id, token,
        # entry, functor, arity, trail, within]`` while it can still deliver
        # answers; *within* is the ``(functor, arity)`` of the tabled
        # predicate whose evaluation keeps the table incomplete.
        # ``cut_seq`` is the id of the newest one ever opened; a cut scope
        # reads it at entry and its cut compares -- one int compare when no
        # tabled frame opened inside the scope since.
        self.cut_seq: int = 0
        self.open_tabled: list[list] = []
        # Bumped whenever a tabled frame hands out answers of an INCOMPLETE
        # table (a consumer of a table under evaluation; a leader streaming
        # an SCC member's or a constrained answer) -- except an SCC member's
        # delivery after its fixpoint, which its consumer read already
        # counted (see make_tabled_wrapper_trampoline).  A leader compares it
        # across a fixpoint pass: unchanged means the pass read only
        # complete tables, so it needs no confirming pass (D68 review F3).
        self.incomplete_reads: int = 0

_leader_ctx = _LeaderContext()


# ── XSB's run-time cut check (D61 Q1) ─────────────────────────────────────
#
# The static rule (``compiler.cut_scope``) refuses at load every cut whose
# scope holds a call to a tabled predicate the compiler can SEE.  A tabled
# call reached through an untabled predicate, or through a goal built at run
# time, is checked here instead: a cut (an if-then-else commit, once/1,
# setup_call_cleanup's Setup) raises when a tabled call frame opened INSIDE
# its scope can still deliver answers from an incomplete table -- the cut
# would prune it, and the answer would depend on the fixpoint's pass order.
#
# A frame stops counting when it closes (exhausted, suspended, completed) or
# when backtracking passes the point it opened at: the record's ``token`` is
# a fresh variable bound on the caller's trail at open, so \+, findall,
# catch/3's recovery -- every construct that abandons a sub-search undoes
# its trail -- leave it unbound, and an abandoned frame that the GC has not
# finalised yet is not taken for a live one.


def _open_tabled(entry, functor, arity, trail, within=None) -> list:
    ctx = _leader_ctx
    recs = ctx.open_tabled
    while recs and is_var(deref(recs[-1][1])):
        recs.pop()                     # abandoned by backtracking
    tok = Var()
    unify(tok, True, trail)
    ctx.cut_seq += 1
    rec = [ctx.cut_seq, tok, entry, functor, arity, trail, within]
    recs.append(rec)
    return rec


def _close_tabled(rec) -> None:
    recs = _leader_ctx.open_tabled
    for i in range(len(recs) - 1, -1, -1):
        if recs[i] is rec:
            del recs[i]
            return


def cut_over_incomplete(mark: int, owner: "str | None" = None,
                        trail=None) -> None:
    """The slow half of a cut's check, reached only when a tabled frame over
    an incomplete table opened since the cut's scope began (``cut_seq >
    mark``): raise ``permission_error(cut, incomplete_table, F/N)`` if one of
    them is still live ON THE CUT'S TRAIL.  A record of another query --
    Python holding one solve() iterator open while it runs another on the
    same thread -- is not this cut's to prune (final re-review N-1)."""
    recs = _leader_ctx.open_tabled
    live = None
    i = len(recs) - 1
    while i >= 0 and recs[i][0] > mark:
        rec = recs[i]
        if is_var(deref(rec[1])) or rec[2].status == "complete":
            del recs[i]                # abandoned, or finished meanwhile
        elif trail is None or rec[5] is trail:
            live = rec
        i -= 1
    if live is None:
        return
    from clausal.logic.compiler import cut_scope
    if cut_scope.CUT_OVER_TABLED_CALL != "refuse":
        return                         # the one switch governs both halves
    from clausal.logic.compiler.ir import cut_over_incomplete_table_message
    from clausal.logic.exceptions import LogicException, permission_error
    functor, arity = live[3], live[4]
    raise LogicException(permission_error(
        "cut", "incomplete_table", ("/", functor, arity),
        cut_over_incomplete_table_message((functor, arity), owner, live[6])))


def _evaluating_ancestor(entry) -> "tuple[str, int] | None":
    """The predicate indicator of the OUTERMOST still-evaluating tabled
    call on the leader stack that *entry* (an SCC member about to hand back
    an incomplete table) depends on -- the evaluation that keeps its table
    open.  None when no such entry carries a name."""
    pending = {id(d) for d in entry.scc_deps
               if d is not entry and d.status == "evaluating"}
    for e in _leader_ctx.stack:
        if id(e) in pending and e.pi is not None:
            return e.pi
    for d in entry.scc_deps:
        if d is not entry and d.status == "evaluating" and d.pi is not None:
            return d.pi
    return None


def _has_pending_dep(entry) -> bool:
    """Whether *entry* consumed a still-evaluating ancestor: an SCC member,
    whose table cannot complete before that ancestor's (A04-F001)."""
    for dep in entry.scc_deps:
        if dep is not entry and dep.status == "evaluating":
            return True
    return False


#: The *within* of a cut-check record for a leader that streams an answer
#: carrying constraints (``_has_attributed_var``) before its table completes.
STREAMED_CONSTRAINED = "$constrained"


def _has_attributed_var(answer) -> bool:
    """Whether a frozen answer holds an unbound variable with attributes (a
    ``dif/2``, CLP or ``freeze/2`` constraint).  The table cannot store the
    constraint (todo/audit-2026-07-05/investigate-A12-tabling-answer-
    constraints.md: a replayed answer loses it), so such an answer is the
    one a leader still hands over live, mid-fixpoint, instead of from the
    completed table (D68)."""
    global _collect_vars
    if _collect_vars is None:
        from clausal.logic.builtins.inspection import _collect_vars_impl  # noqa: PLC0415
        _collect_vars = _collect_vars_impl
    vs: list = []
    _collect_vars(answer, vs)
    for v in vs:
        if getattr(v, "attrs", None):
            return True
    return False


_collect_vars = None   # inspection._collect_vars_impl, bound on first use


def push_leader(entry: TableEntry) -> None:
    _leader_ctx.stack.append(entry)
    _leader_ctx.pushes += 1


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


def _note_driven_store(table_store) -> None:
    """Tell every judging leader on the stack that *table_store* was driven."""
    for driven in _leader_ctx.driven_stores:
        if all(table_store is not st for st in driven):
            driven.append(table_store)


def current_leader() -> TableEntry | None:
    return _leader_ctx.stack[-1] if _leader_ctx.stack else None


def _on_leader_stack(entry: TableEntry) -> bool:
    """True if *entry* is an actively-leading ancestor (A04-F001 SCC).

    Includes segments DETACHED by a suspended judging generator.  Those frames
    are still leading: the generator holds a live `solve()` parked inside them
    and will resume into it.  Missing them makes a nested call on the same
    table take the LEADER path and re-drive a table someone else is mid-way
    through -- and the original leader's own answers are then deduped away as
    already-known when it resumes, losing solutions silently."""
    if any(e is entry for e in _leader_ctx.stack):
        return True
    return any(e is entry for seg in _leader_ctx.detached for e in seg)


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
        # The clausal.aio query this drive belongs to, or None for an
        # ordinary synchronous query.  clausal.aio installs a per-query copy
        # of this context while each query runs (queries interleave on one
        # thread), so the owner says whose table a new entry is.
        self.owner = None

_drive_ctx = _DriveContext()


# ── Ownership: tables shared by interleaved clausal.aio queries ──────────
#
# Synchronous queries run one at a time, so SLG can assume one search per
# table.  clausal.aio queries interleave on one thread: a query suspended at
# a wait (or between answers it streamed to the event loop) leaves the tables
# it is building visible to every other query, and it may be abandoned or die
# without ever finishing them.  These rules keep each table to one search.
# In the synchronous world every owner is None, so none of them changes
# anything there.
#
# 1. Owner.  An entry records the query leading it (``owner``; None when
#    synchronous).  ``_mine(entry)``: led by the drive now running.
# 2. Foreign.  Owned by another query that can still resume, or on a
#    synchronous leader stack the running async query has swapped out
#    (``_outer_ctx``).  A foreign entry is never consumed, re-led or
#    completed: reaching one raises permission_error(access,
#    tabled_evaluation, P/N) (``_refuse_if_foreign``).
# 3. Abandoned.  Evaluating, not mine and not foreign: its query is dead.  It
#    is never resumed -- a new lead starts over -- and the store-wide passes
#    (SCC completion, the negation scan) leave it alone.
# 4. Lead tokens.  Every lead and re-lead sets a fresh ``entry.lead``; a
#    leader frame's abnormal-exit repair and leader pop act only while the
#    entry is still its lead, because a re-lead reuses the entry OBJECT and a
#    dead query's frames may be finalised long after (``_new_lead``,
#    ``_repair_lead``).
# 5. Death and reaping.  When an unclosed query's async generator is freed, a
#    weakref callback queues it (``_pending_dead``); at the next safe point
#    -- the start of a tabled call or tabled negation, or an async query
#    switching in -- ``_reap_dead`` removes its abandoned tables and finishes
#    its generator.  The callback itself may run inside the cyclic GC, in the
#    middle of a loop over a table store or in another thread, so it never
#    touches a store.
#
# Each rule closes a bug an adversarial review round found (2026-10-06/07);
# tests/test_aio.py pins every one.


class _OuterContext(threading.local):
    def __init__(self):
        # Leader contexts (``_leader_ctx.__dict__`` copies) swapped OUT while
        # a clausal.aio query runs on this thread, innermost last.  A
        # synchronous query parked between answers keeps its leaders there.
        self.leaders: list[dict] = []

_outer_ctx = _OuterContext()


def _mine(entry: "TableEntry") -> bool:
    """Led by the drive now running (rule 1)."""
    return entry.owner is _drive_ctx.owner


def _on_outer_stack(entry: "TableEntry") -> bool:
    for ctx in _outer_ctx.leaders:
        if any(e is entry for e in ctx.get("stack", ())):
            return True
        if any(e is entry for seg in ctx.get("detached", ()) for e in seg):
            return True
    return False


def _foreign(entry: "TableEntry") -> bool:
    """Being built by a search other than this one that can still resume
    (rule 2): another live clausal.aio query, or a synchronous leader parked
    outside the running async query."""
    owner = entry.owner
    if owner is not None and not _mine(entry) and getattr(owner, "live", False):
        return True
    return bool(_outer_ctx.leaders) and _on_outer_stack(entry)


def _refuse_if_foreign(entry, functor, arity) -> None:
    """Raise if *entry* (or None) is a foreign table still being built."""
    if entry is None or entry.status != "evaluating" or not _foreign(entry):
        return
    from clausal.logic.exceptions import LogicException, permission_error
    raise LogicException(permission_error(
        "access", "tabled_evaluation", ("/", functor, arity),
        f"{functor}/{arity}: another asyncio query is still evaluating this "
        "table (it is suspended at a wait or between answers); complete it "
        "first, e.g. with findall/3, or run the queries one after another"))


def _new_lead(entry: "TableEntry") -> object:
    """Start a lead of *entry* (rule 4); the leader frame keeps the token."""
    entry.lead = token = object()
    return token


def _close_suspended(entry: "TableEntry") -> None:
    """Finish the parked generators of *entry*'s suspended consumers."""
    for sc in entry.suspended:
        try:
            sc.generator.close()
        except BaseException:
            pass
    entry.suspended.clear()


def _repair_lead(entry: "TableEntry", lead, table_store, store_key) -> None:
    """A04-F007 repair on a leader frame's abnormal exit: drop the half-built
    entry so a later query recomputes it, and release its consumers -- only
    while the entry is still this frame's lead (rule 4), and identity-guarded
    against a fresh entry installed since under the same key."""
    if entry.lead is not lead:
        return
    if table_store.get(store_key) is entry:
        del table_store[store_key]
    _close_suspended(entry)


# Rule 5: queries that died unclosed, waiting to be reaped.  list.append and
# list.pop are atomic, so the GC (or another thread) may queue at any time.
_pending_dead: list = []


def _reap_dead() -> None:
    while _pending_dead:
        try:
            query = _pending_dead.pop()
        except IndexError:
            return
        try:
            query._died()
        except Exception:  # noqa: BLE001 - never into an unrelated query
            pass


def begin_drive_episode() -> None:
    """Open a root-drive episode: entries created below are tracked."""
    _drive_ctx.episodes.append([])


def _record_created_entry(entry, table_store, store_key) -> None:
    episodes = _drive_ctx.episodes
    if episodes:
        # The lead token too: the repair below may only touch the entry while
        # it is still OUR lead (see TableEntry.lead).
        episodes[-1].append((entry, table_store, store_key, entry.lead))
    # A clausal.aio query also keeps its own list, so that when it dies
    # without being closed its abandoned tables leave the store at once
    # (clausal.aio._Query._died) instead of waiting for asyncio's finaliser.
    created = getattr(_drive_ctx.owner, "created", None)
    if created is not None:
        created.append((entry, table_store, store_key))


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
    created_ids = {id(entry) for entry, _, _, _ in created}
    if any(id(e) in created_ids for e in _leader_ctx.stack):
        # Abandoned mid-fixpoint — repair.
        for entry, store, key, lead in created:
            if entry.status != "evaluating":
                continue
            if entry.lead is not lead and not _mine(entry):
                # Re-led since by ANOTHER query (rule 4) after ours was
                # dropped and its close deferred: theirs now.  (A re-lead of a
                # dormant SCC member within this same drive changes the token
                # but keeps the owner, and is still ours to repair.)
                continue
            if store.get(key) is entry:
                del store[key]
            _close_suspended(entry)
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
        for _entry, store, _key, _lead in created:
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
    # Only entries this drive owns: completing another query's abandoned
    # entry would freeze its partial answers for good (rule 3).
    # The cheap tests first: ``_on_leader_stack`` walks the leader stack, so
    # asking it of every evaluating entry (each ancestor of a deep recursion)
    # made a completion cost O(store x depth).  Since D68 every leader
    # completes before its first answer, so that was paid on every call.
    members = [e for e in table_store.values()
               if e.status == "evaluating" and e.scc_deps
               and not _on_leader_stack(e) and _mine(e)]
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
                 "nonground", "suspended", "conditions", "_current_delays",
                 "scc_deps", "_sources", "owner", "lead", "pi")

    def __init__(self, pi: "tuple[str, int] | None" = None):
        self.status: str = "evaluating"       # "evaluating" | "complete"
        # ``(functor, arity)`` of the tabled call, for the run-time cut
        # error's wording (``cut_over_incomplete``); None for a judging
        # leader (seam.judged_answers), which is no predicate.
        self.pi = pi
        # The clausal.aio query leading this table (None when synchronous)
        # and the token of its current lead: see "Ownership" above.
        self.owner = _drive_ctx.owner
        self.lead = None
        self.answers: list[tuple] = []
        self.answer_set: set = set()   # canonical answer keys (A04-F005/F006)
        self._answer_index: dict = {}  # canonical key → index into answers
        # Indices of the rows that leave a variable unbound: each is stored
        # renamed apart and replayed as a fresh copy (``row``).  Empty for
        # the common all-ground table, so the replay check is one truth test.
        self.nonground: set[int] = set()
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
        # Opt-in LATE binding of positive conditions (``_credit_consumer``):
        # ``None`` for every real table, a ``{(entry, index): store}`` dict
        # for a judging leader that wants the consumed ROW rather than the
        # delay set that row happened to hold at the moment of consumption.
        self._sources: dict | None = None

    def add_answer(self, answer: tuple, delay_set: frozenset | None = None) -> int | None:
        """Add a frozen answer tuple.  Returns its INDEX if the tuple was new.

        The index is never a bare bool (index 0 is falsy, so callers test
        ``is not None``).  ``None`` means the visible answer set did not
        change.

        Dedup uses the canonical, hashable key (A04-F005) — a frozen answer may
        contain a list/dict/set/term instance, which are unhashable and cannot
        go directly in ``answer_set``. The key also type-distinguishes numeric
        leaves (A04-F006), so 1/True/1.0 answers are kept distinct exactly as
        the untabled dispatch would. The original frozen tuple is stored in
        ``answers`` for unification.

        A re-derivation of a known answer under a DIFFERENT delay set unions
        that set into the answer's disjunction (A04-F003) and still returns
        None — the tuple is already in the table; only its truth got
        sharper. An unconditional re-derivation erases the delays.

        Phase 2 bridge Task 4 -- selective ground-cell interning: this is
        the SINGLE Python funnel every frozen answer passes through
        regardless of which ``freeze_args`` built it (the pure-Python
        ``_freeze_args_py`` above, or the C twin ``_tabling_core.freeze_args``
        that normally shadows it -- both freeze cells as plain tuples
        either way, since a cell IS a plain tuple; see cells.py's module
        docstring). When ``is_intern_enabled()`` (default OFF -- flipped
        only by Task 4's own tests/benchmark), each cell-shaped arg of
        *answer* is passed through ``intern_cell`` before storage, so two
        structurally-equal ground cell answers land as the SAME object.
        Non-cell args (class terms, atoms, scalars) are left exactly as
        received -- they never reach ``intern_cell`` at all.

        A row that leaves a variable unbound is stored RENAMED APART (an
        attribute-free ``copy_term``), never as the frozen tuple itself:
        ``freeze_args`` is a deref-walk, so the frozen answer holds the
        derivation's own ``Var`` objects, which the caller's continuation
        can still bind (``v(X), X = b``) -- and which, replayed as they
        are, made every replay of the row one shared variable
        (todo/done/tabled-answer-rows-share-their-unbound-variables-
        2026-10-16.md).  ``row`` hands each replay its own copy.  A ground
        row (the common case) is stored as received, so interning keeps
        its identity and a replay costs nothing extra.
        """
        if is_intern_enabled():
            answer = tuple(
                intern_cell(a) if is_cell(a) else a for a in answer
            )
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
        if not _is_ground(answer):
            answer = _rename_row(answer)
            self.nonground.add(idx)
        self.answers.append(answer)
        self.conditions.append(_simplify_disjuncts(frozenset({ds})))
        return idx

    def row(self, i: int) -> tuple:
        """The i-th answer as a replay unifies it: the stored tuple itself
        for a ground row, a fresh attribute-free copy (its variables renamed
        apart, their sharing within the row kept) for one that leaves a
        variable unbound -- so no two replays, and no replay and the table,
        share a variable."""
        if self.nonground and i in self.nonground:
            return _rename_row(self.answers[i])
        return self.answers[i]

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
    Containers (``list``/``tuple``/``dict``/``set``, term
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
    if isinstance(term, bool):
        # A truth ATOM (D35): keyed as its spelling, the key the str
        # spelling of the same atom already has -- one atom, one variant.
        return "true" if term else "false"
    if isinstance(term, (float, complex)):
        return (type(term), term)          # A04-F006
    if isinstance(term, str):
        return term
    if isinstance(term, bytes):
        # A code list: b"ab" and [97, 98] are one term, so one key.
        return term if term else _NIL_KEY
    if isinstance(term, list):
        elems = tuple(_normalize_for_key_py(e) for e in term)
        return _seq_key(elems) or ("__list__",) + elems
    if type(term) is tuple and not term:
        return _NIL_KEY                 # () is nil: the key [] has
    if is_chars(term):
        # A char list: the carrier and [a, b] are one term, so one key.
        text = chars_text(term)
        return ("__chars__", text) if text else _NIL_KEY
    if isinstance(term, tuple):
        return ("__tuple__",) + tuple(_normalize_for_key_py(e) for e in term)
    if isinstance(term, dict):
        return ("__dict__", frozenset(
            (_normalize_for_key_py(k), _normalize_for_key_py(v))
            for k, v in term.items()))
    if isinstance(term, (set, frozenset)):
        return ("__set__", frozenset(_normalize_for_key_py(e) for e in term))
    if isinstance(term, _SEG_TYPES):
        return _seg_key(term)
    if is_term_instance(term):
        return (type(term).__name__,) + tuple(
            _normalize_for_key_py(getattr(term, f)) for f in term_field_names(term)
        )
    return term

_NIL_KEY = ("__list__",)


def _seq_key(elems):
    """The key of a NON-EMPTY list whose normalized elements are all one-char
    atoms (a char list: ``("__chars__", text)``, the carrier's key) or all
    exact ints in 0..255 (a code list: the ``bytes``, the ``b"..."`` key);
    else ``None``.  A bool never reaches here as an int (it keys as its atom
    spelling), and a float keys as ``(float, v)``."""
    if not elems:
        return None
    e0 = type(elems[0])
    if e0 is str:
        if all(type(e) is str and len(e) == 1 for e in elems):
            return ("__chars__", "".join(elems))
    elif e0 is int:
        if all(type(e) is int and 0 <= e < 256 for e in elems):
            return bytes(elems)
    return None


_normalize_for_key = _normalize_for_key_py

_SEG_TYPES = (SegList, SegString, SegBytes)
_HOLE = ("__hole__",)


def _seg_key(term):
    """The key of a ``SegList``/``SegString``/``SegBytes``.  A ground one
    walks to its list, carrier or bytes and keys as that.  A partial one keys
    as ``("__partial__", e0, e1, ..., _HOLE, ...)``: its known elements in
    order (a string segment as its chars, a bytes segment as its codes, so
    ``"a"||T`` and ``[a|T]`` key alike) with a ``_HOLE`` per open tail.  The
    C twin calls this function (registered below), so both produce it."""
    w = term.__walk__()
    if not isinstance(w, _SEG_TYPES):
        return _normalize_for_key(w)
    elems = []
    for seg in w._segments:
        if isinstance(seg, VarSeg):
            elems.append(_HOLE)
        elif isinstance(seg, ConcreteSeg):
            elems.extend(_normalize_for_key(e) for e in seg.elements)
        elif isinstance(seg, (str, bytes)):
            elems.extend(seg)            # chars, or codes
        else:
            elems.append(_normalize_for_key(seg))
    return ("__partial__",) + tuple(elems)


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


def _is_ground(answer) -> bool:
    """Whether a frozen answer leaves no variable unbound (the C walker
    behind ``ground/1``; bound on first use, as ``_collect_vars`` is)."""
    global _is_ground_impl
    if _is_ground_impl is None:
        from clausal.logic.builtins._helpers import _is_ground as impl  # noqa: PLC0415
        _is_ground_impl = impl
    return _is_ground_impl(answer)


def _rename_row(answer: tuple) -> tuple:
    """A copy of a frozen answer with its unbound variables renamed apart:
    fresh, attribute-free variables, one per distinct variable of the row,
    so the sharing within the row (``f(X, X)``) is kept.  The ground parts
    are the same objects (``copy_term`` returns a ground cell as it is)."""
    global _copy_term
    if _copy_term is None:
        from clausal.logic.builtins.inspection import _copy_term_impl  # noqa: PLC0415
        _copy_term = _copy_term_impl
    return _copy_term(answer, {})


_is_ground_impl = None   # builtins._helpers._is_ground, bound on first use
_copy_term = None        # inspection._copy_term_impl, bound on first use


# ── Answer unification ───────────────────────────────────────────────────


def _unify_answer_py(args, stored, trail):
    """Unify each arg with the corresponding stored value.

    With no driver this is ONE unification, as a clause head's arguments
    are, so a goal one argument's hook wakes runs after every argument is
    bound (twin of ``_tabling_core._unify_answer``)."""
    if not trail.defer:
        pairs = list(zip(args, stored))
        return unify(("$answer", *(a for a, _ in pairs)),
                     ("$answer", *(s for _, s in pairs)), trail)
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
    from clausal.logic._tabling_core import _register_seg_key  # noqa: PLC0415
    _register_seg_key(_SEG_TYPES, _seg_key)
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
    for i in range(len(entry.answers)):
        if entry.conditions[i] is _FAILED:
            continue
        mark = scratch.mark()
        matched = _unify_answer(list(args), list(entry.row(i)), scratch)
        scratch.undo(mark)
        if matched:
            if entry.truth_value(i) is True:
                return True, has_conditional
            has_conditional = True
    return False, has_conditional


def _charge_delays(leader, delays, trail) -> None:
    """Add *delays* to *leader*'s in-progress set, UNDOABLY.

    The in-progress set is one mutable bucket that is read (and snapshotted)
    when an answer arrives, so a delay incurred by a branch that then FAILED
    used to be charged to whatever answer came next — turning a WFS-true
    answer Undefined, the direction a caller cannot work around.  Every
    addition is therefore recorded on the trail: the same backtracking that
    undoes the branch's bindings retracts the conditions it incurred.

    Only the delays this call actually ADDS are recorded, and only once: a
    later re-addition of a delay already present records nothing, so undoing
    to a mark between the two leaves it in place (the earlier, still-live
    addition owns it) and undoing past both removes it."""
    new = frozenset(delays) - leader._current_delays
    if not new:
        return
    leader._current_delays |= new
    if trail is not None:
        trail.record(
            lambda l=leader, n=new: l._current_delays.difference_update(n))


def _credit_consumer(consumer, entry, i, store, trail, delays=None) -> None:
    """Charge *consumer*'s in-progress derivation with the condition of
    *entry*'s i-th answer (positive delay propagation, below).

    A leader that opted in to LATE binding (``_sources`` is a dict — the
    seam's throwaway judging leader) records the ROW rather than the delay
    set that row holds right now.  A re-derivation can still make the row
    unconditional AFTER we consumed it — ``add_answer`` returns ``None`` for
    it, so nothing re-streams and the row is the only place the improvement
    is written down — and reading the row at the end gets the answer the
    table finally settled on.  Every other leader takes the flat union it
    always took.  Both channels are trailed (see :func:`_charge_delays`)."""
    if consumer._sources is not None:
        key = (entry, i)
        if key not in consumer._sources:
            consumer._sources[key] = store
            if trail is not None:
                trail.record(
                    lambda d=consumer._sources, k=key: d.pop(k, None))
        return
    if delays is None:
        delays = entry.delays_for(i)
    if delays:
        _charge_delays(consumer, delays, trail)


def harvest_conditions(leader, bag: list) -> None:
    """Accumulate into *bag* the conditions *leader* is standing on right now.

    Called by a COLLECTING construct (``findall``/``bagof``/``setof``,
    ``count_all``) once per solution it keeps.  The construct backtracks
    between solutions and unwinds its own mark at the end, and condition
    charges are trailed (:func:`_charge_delays`), so by the time the bag is
    handed on, every condition its rows were derived under has been retracted.
    The bag survives the undo; its conditions must too.

    *leader* is bound ONCE, at the construct's entry, and passed in -- it is
    NOT ``current_leader()`` at the moment of the harvest.  While a tabled
    goal beneath us is streaming its answers, the top of the leader stack is
    that table's own entry (which is why ``_streaming_consumer_leader``
    exists): the credit for a conditional row lands on the leader BELOW it --
    ours -- and a harvest that resolved the stack top would look at the
    table's empty bucket and collect nothing.

    Accumulating (rather than snapshotting a copy per solution) keeps this
    linear in the conditions actually incurred: the live sets shrink again on
    the backtracking between solutions, so the per-solution cost is the
    solution's own conditions, not the running total.

    BAG LAYOUT, shared with :func:`charge_conditions` and minted empty by the
    codegen: ``[]`` while nothing has been harvested, and
    ``[delays_set, sources_dict]`` once anything has -- two slots, positional,
    never appended to beyond them.  Emptiness doubles as "nothing to charge"."""
    if leader is None:
        return
    delays = leader._current_delays
    sources = leader._sources
    if not delays and not sources:
        return
    if not bag:
        bag.append(set())
        bag.append({})
    if delays:
        bag[0] |= delays
    if sources:
        bag[1].update(sources)


def charge_conditions(trail, leader, bag: list) -> None:
    """Charge everything :func:`harvest_conditions` accumulated onto *leader*,
    after the collecting construct has unwound its own mark.

    The charge lands AT that mark, so backtracking over the whole construct
    -- discarding the bag itself -- retracts the conditions again, while
    backtracking WITHIN the collection no longer does.

    *bag* is ``[]`` or ``[delays_set, sources_dict]`` -- see
    :func:`harvest_conditions` for the layout both halves maintain."""
    if not bag:
        return
    if leader is None:
        bag.clear()
        return
    delays, sources = bag[0], bag[1]
    if delays:
        _charge_delays(leader, delays, trail)
    for (entry, i), store in sources.items():
        _credit_consumer(leader, entry, i, store, trail)
    bag.clear()


def _propagate_answer_delays(entry, i, store=None, trail=None) -> None:
    """POSITIVE delay propagation (A04-F003 follow-up): a derivation that
    consumes a CONDITIONAL answer is itself conditional on the same delayed
    literals — WFS answer clauses carry delay lists through positive joins,
    not only through negation. Without this, a rule reading a conditional
    answer out of a completed table mints an unconditionally-true answer
    from an Undefined premise.

    Approximation, deliberately matching the existing negative-delay
    bookkeeping: the FLAT union of the answer's live disjuncts is added to
    the innermost active leader's in-progress delay set (per-disjunct
    precision is future work; the union direction errs toward Undefined, and
    the disjunction-of-derivations model keeps a genuinely unconditional
    derivation True regardless).  A leader that asked for late binding gets
    the row instead — :func:`_credit_consumer`."""
    c = entry.conditions[i]
    if c is _FAILED or c is _UNCONDITIONAL:
        return  # the overwhelmingly common rows — one identity test each
    leader = current_leader()
    if leader is None:
        return
    _credit_consumer(leader, entry, i, store, trail)


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


def _delay_negation(functor, arity, key, args, trail, store=None):
    """Record ``not functor(args)`` as a DelayedNegation on the current leader
    (conditional success). With no leader in scope there is nowhere to attach
    the condition — the negation still succeeds, matching how ``query()``/
    ``call()`` surface undefined answers alongside true ones.

    *store* is the table store the negated call's entry lives in; passing it
    lets resolution find the target even when the delay is carried by an
    entry in a DIFFERENT module's store (cross-module tabled NAF)."""
    frozen = freeze_args(args, trail)
    dn = DelayedNegation(functor, arity, key, frozen, store=store)
    leader = current_leader()
    if leader is not None:
        _charge_delays(leader, (dn,), trail)


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

    Cross-module: the compiled seam always passes the CALLER's store and db,
    but an ``-import_from``-ed callee is tabled — and tabled INTO — its own
    module's db.  When the caller's db does not table the call, follow the
    binding's ROW to its home (``predicate.tabled_home_of``, the same answer
    the compile-time half uses) and operate on the home
    store/db instead (todo/cross-module-tabled-naf-loses-wfs-delay.md); the
    same-module hot path never takes the extra lookup.
    """
    # ``db`` is duck-typed (test doubles implement only ``get_dispatch``) —
    # a db that cannot answer ``is_tabled`` keeps the historical behaviour.
    _is_tabled = getattr(db, "is_tabled", None) if db is not None else None
    if _is_tabled is not None and not _is_tabled(functor, arity):
        md = getattr(db, "module_dict", None)
        cand = md.get(functor) if md is not None else None
        found = tabled_home_of(cand, arity=arity, db=db)
        if found is not None:
            # The home db keys tables/dispatch by the predicate's OWN name;
            # the compiled seam may pass the import rewrite's dotted
            # spelling ("lib.Win") — canonicalize alongside the redirect.
            db, functor = found
            table_store = db.table_store
    key = make_subgoal_key(args, trail)
    store_key = (functor, arity, key)
    entry = table_store.get(store_key)
    _refuse_if_foreign(entry, functor, arity)

    if entry is not None and entry.status == "complete":
        # Standard NAF on complete table: an unconditional answer fails the
        # negation; a conditional-only match delays it (undefined).
        unconditional, conditional = _scan_complete_answers(entry, args)
        if unconditional:
            return False  # positive answer exists → negation fails
        if conditional:
            _delay_negation(functor, arity, key, args, trail, store=table_store)
        return True  # no determinate matching answer → negation succeeds

    if (entry is not None and entry.status == "evaluating"
            and _on_leader_stack(entry)):
        # Genuine cycle through negation (the target is an actively-leading
        # ancestor) — delay.
        _delay_negation(functor, arity, key, args, trail, store=table_store)
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
            _delay_negation(functor, arity, key, args, trail, store=table_store)
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
                    _delay_negation(functor, arity, key, args, trail, store=table_store)
                return True
            # The drive could not COMPLETE the table (it consumed a
            # still-evaluating ancestor and stays dormant, to be re-led by
            # a later pass) — the truth is undecided at this point in the
            # fixpoint: delay.
            _delay_negation(functor, arity, key, args, trail, store=table_store)
            return True

    # Check if ANY variant of this predicate is evaluating — if so, we're in a
    # cycle through negation and must delay. This handles cases like: leader
    # evaluates win(_), body calls not win(2), a different variant but still
    # part of the same SLG cycle.
    for (f, a, _k), e in table_store.items():
        if f == functor and a == arity and e.status == "evaluating":
            if not _mine(e):
                # Another query's table (live or abandoned) is not in a cycle
                # of ours; a positive call that needs it is refused or rebuilds.
                continue
            _delay_negation(functor, arity, key, args, trail, store=table_store)
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
    subsuming leader, is still decided by the subsuming completed table).

    A delay recorded by cross-module tabled NAF carries the negated call's
    HOME store on ``dn.store`` — the entry that decides it does not live in
    the store of the entry carrying the delay, so prefer the recorded one."""
    if dn.store is not None:
        table_store = dn.store
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
        if _pending_dead:            # a safe point (Ownership, rule 5)
            _reap_dead()
        args = args_trail_k[:arity]
        trail = args_trail_k[arity]

        key = make_subgoal_key(args, trail)
        store_key = (functor, arity, key)
        entry = table_store.get(store_key)
        _refuse_if_foreign(entry, functor, arity)

        # ── COMPLETE: cache hit ──
        if entry is not None and entry.status == "complete":
            for i in range(len(entry.answers)):
                if entry.conditions[i] is _FAILED:
                    continue
                mark = trail.mark()
                if _unify_answer(args, entry.row(i), trail):
                    _propagate_answer_delays(entry, i, table_store, trail)
                    yield None
                trail.undo(mark)
            return

        # ── CONSUMER: yield known answers only (no suspension in simple mode) ──
        if entry is not None and entry.status == "evaluating":
            i = 0
            while i < len(entry.answers):
                if entry.conditions[i] is not _FAILED:
                    mark = trail.mark()
                    if _unify_answer(args, entry.row(i), trail):
                        _propagate_answer_delays(entry, i, table_store, trail)
                        yield None
                    trail.undo(mark)
                i += 1
            return

        # ── LEADER: fixpoint loop ──
        entry = TableEntry()
        lead = _new_lead(entry)
        table_store[store_key] = entry
        _note_driven_store(table_store)
        push_leader(entry)

        try:
            changed = True
            while changed:
                changed = False
                mark = trail.mark()
                for _ in original_dispatch(*args, trail, None):
                    answer = freeze_args(args, trail)
                    # KNOWINGLY divergent from the trampoline wrapper, which
                    # dropped this per-answer clear (see its note): there a
                    # clause-prefix delay covers every answer, here it is still
                    # charged to the first one only.  `ensure_tabled_wrapper`
                    # never builds this factory, so nothing in the engine takes
                    # this path -- but it IS live API, constructed directly by
                    # tests/test_tabling.py, so the divergence is recorded
                    # rather than silently left.  Anyone re-wiring simple mode
                    # should drop this clear too.
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
            _repair_lead(entry, lead, table_store, store_key)
            raise
        finally:
            if entry.lead is lead:
                pop_leader(entry)

        entry.status = "complete"
        if not _leader_ctx.stack:
            _resolve_all_conditions(table_store)  # A04-F003 root-exit pass
        for i in range(len(entry.answers)):
            if entry.conditions[i] is _FAILED:
                continue
            mark = trail.mark()
            if _unify_answer(args, entry.row(i), trail):
                _propagate_answer_delays(entry, i, table_store, trail)
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
        if _pending_dead:            # a safe point (Ownership, rule 5)
            _reap_dead()
        args = args_trail[:arity]
        trail = args_trail[arity]

        key = make_subgoal_key(args, trail)
        store_key = (functor, arity, key)
        entry = table_store.get(store_key)
        _refuse_if_foreign(entry, functor, arity)

        # ── COMPLETE: yield cached answers ──
        if entry is not None and entry.status == "complete":
            for i in range(len(entry.answers)):
                if entry.conditions[i] is _FAILED:
                    continue
                mark = trail.mark()
                if _unify_answer(args, entry.row(i), trail):
                    _propagate_answer_delays(entry, i, table_store, trail)
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
            # Answers from an incomplete table: a cut over this frame is
            # XSB's run-time error (``cut_over_incomplete``).  The table is
            # incomplete because this very call is inside its evaluation.
            _rec = _open_tabled(entry, functor, arity, trail, entry.pi)
            # Belt-and-braces, no pinning test: removing this bump fails no
            # test, and none could be built.  The no-confirming-pass check
            # (below, "No confirming pass") already sees every consumer
            # read another way: ``cl.scc_deps.add(entry)`` just above runs
            # before any answer is handed out, and ``cl`` is never None here
            # (the ancestor is on the leader stack), so the leader making
            # this call keeps ``scc_deps`` non-empty, and its own leaders get
            # the edge by the transitive propagation at its exit, or, when
            # the ancestor is that leader itself, see the SuspendedConsumer
            # registered below in ``entry.suspended``.  Kept so the counter
            # stays a complete record of incomplete reads (the final-delivery
            # exception aside, see there), not one that leans on that
            # propagation staying exact.
            _leader_ctx.incomplete_reads += 1
            try:
                # LIVE iteration: the ancestor's pass appends rows while
                # this consumer is handing them over (its continuation
                # derives them), and SLG hands over every answer found so
                # far.  A snapshot of the length (``range(len(...))``) read
                # one level per fixpoint pass: O(N) passes for an N-chain
                # left-recursive closure, 40x slower.  Pinned in
                # tests/iso_l3/test_l3_tabled_rows_fresh_variables.py::
                # test_a_left_recursive_closure_reads_rows_appended_mid_pass.
                i = 0
                while i < len(entry.answers):
                    if entry.conditions[i] is not _FAILED:
                        mark = trail.mark()
                        if _unify_answer(args, entry.row(i), trail):
                            _propagate_answer_delays(entry, i, table_store,
                                                     trail)
                            yield (_proceed, None)
                        trail.undo(mark)
                    i += 1
            finally:
                _close_tabled(_rec)

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
        if entry is not None and not _mine(entry):
            # Abandoned by another query (rule 3; a live one was refused
            # above): its partial answers, conditions and scc_deps describe
            # that query's search, not ours.  Start over.
            _close_suspended(entry)
            entry = None
        if entry is None:
            entry = TableEntry((functor, arity))
            lead = _new_lead(entry)
            table_store[store_key] = entry
            _record_created_entry(entry, table_store, store_key)  # A04-F007
        else:
            # A dormant member of our own drive.  A04-F001 (re-lead): this
            # caller has seen NONE of the already-tabled answers; the
            # delivery below hands back every row, old and new, once.
            lead = _new_lead(entry)
        # Complete first (operator ruling 2026-10-16, D68; XSB's local
        # scheduling): a leader hands its caller NO answer until its fixpoint
        # has ended -- every answer is delivered from the table afterwards,
        # in table order.  Streaming answers mid-fixpoint ran the caller's
        # continuation while this entry was still on the leader stack, so a
        # second call of the same variant there (``findall(X-Y, (t(X),
        # t(Y)), L)``) took the CONSUMER path and joined against a partial
        # table: lost answers, and, inside another table, a non-monotone
        # aggregate (a 6-pair and a 9-pair list both tabled).  And a cut
        # over the first answer pruned an incomplete table.  Now:
        #   * a leader whose table COMPLETES here (any leader that is not a
        #     member of an ancestor's SCC: a top-level call, or a fresh call
        #     inside another table's evaluation that does not depend on that
        #     evaluation) delivers from a complete table -- a cut over it is
        #     fine, and it opens no cut-check record;
        #   * an SCC member (it consumed a still-evaluating ancestor, so its
        #     table cannot complete before that ancestor's) streams its
        #     answers as before D68, from the moment it knows it is one
        #     (``_has_pending_dep``: on a re-lead, from the start, replaying
        #     its known rows first), under a cut-check record naming the
        #     ancestor: that table really is incomplete.  Withholding them
        #     too would let the enclosing fixpoint gain one step per pass
        #     (even/odd mutual recursion to depth n: O(n) passes); answers it
        #     derived before it knew are delivered after its fixpoint.
        # The root lead's conditional answers were already deferred until
        # after global resolution (todo/tabled-conditional-answers-stream-
        # before-invalidation.md); now every answer is.  Positive delay
        # propagation for a conditional row is credited at delivery, to the
        # leader BELOW this one (``_streaming_consumer_leader``: none for a
        # root or spawn-discard lead), as the streaming site used to.
        #   * one exception: an unconditional answer that carries a
        #     constraint (an attributed variable) is still handed over live,
        #     when derived, as before D68 -- the table cannot store the
        #     constraint, and delivering it from the table would drop it
        #     (``_has_attributed_var``).  Such an answer comes from an
        #     incomplete table, under a cut-check record.
        _note_driven_store(table_store)
        push_leader(entry)
        consumer = _streaming_consumer_leader(entry)
        streamed: set[int] = set()   # rows already handed over (above)
        _srec = None                 # their cut-check record

        try:
            if _has_pending_dep(entry):
                # A re-led SCC member: replay its known rows first, as
                # before D68 (A04-F001 re-lead replay); new ones stream.
                _srec = _open_tabled(entry, functor, arity, trail,
                                     _evaluating_ancestor(entry))
                _leader_ctx.incomplete_reads += 1
                # LIVE iteration (see the consumer loop above): a row the
                # caller's continuation appends while a known row is being
                # handed over is streamed here too, not left for a later
                # pass; ``streamed`` keeps the delivery below from repeating
                # it.
                i = 0
                while i < len(entry.answers):
                    c = entry.conditions[i]
                    if c is not _FAILED:
                        streamed.add(i)
                        mark = trail.mark()
                        if _unify_answer(args, entry.row(i), trail):
                            if consumer is not None and c is not _UNCONDITIONAL:
                                delays = entry.delays_for(i)
                                if delays:
                                    _credit_consumer(consumer, entry, i,
                                                     table_store, trail,
                                                     delays)
                            yield (_proceed, None)
                        trail.undo(mark)
                    i += 1
            # A04-F001: drive the dispatch to a FIXPOINT by re-running it until
            # no new answer appears, rather than a single pass followed by the
            # (broken) consumer-resume completion phase. On each re-run a
            # consumer (an inner call to this same still-evaluating table) sees
            # the grown answer set and routes it to its clause continuation,
            # which derives further answers. Each answer reaches the leader's
            # caller once, after the fixpoint (complete first, D68; add_answer
            # dedups). This makes tabled
            # solution sets clause-order-independent for single-table recursion;
            # mutual recursion additionally needs SCC-aware completion (below).
            changed = True
            while changed:
                changed = False
                pass_delays = False
                reads_at_start = _leader_ctx.incomplete_reads
                _gen = StepGenerator(original_dispatch, this_generator,
                                     this_generator, this_generator, *args, trail)
                _st = yield (_gen, None)
                while _st is not DONE:
                    answer = freeze_args(args, trail)
                    # NOT cleared per answer.  Charges are trailed now
                    # (``_charge_delays``), so a branch that delayed and then
                    # failed has already had them retracted -- while a delay
                    # incurred in the clause-body PREFIX still stands for every
                    # answer the suffix produces, because the prefix does not
                    # re-run.  Clearing here charged it to the FIRST answer
                    # only and reported the rest unconditionally true off an
                    # undefined premise.  The end-of-pass clear below stays: it
                    # covers callers that reach ``_charge_delays`` with no
                    # trail to record on.
                    delay_set = frozenset(entry._current_delays)
                    if delay_set:
                        pass_delays = True
                    new_idx = entry.add_answer(answer, delay_set)
                    if new_idx is not None:
                        # New tuple OR a revived _FAILED row — both change the
                        # visible answer set: run another pass.  Nothing is
                        # handed to the caller yet (complete first, above) --
                        # unless it carries a constraint the table would drop.
                        changed = True
                        member = _has_pending_dep(entry)
                        if member or (not delay_set
                                      and _has_attributed_var(answer)):
                            if _srec is None:
                                _srec = _open_tabled(
                                    entry, functor, arity, trail,
                                    _evaluating_ancestor(entry) if member
                                    else STREAMED_CONSTRAINED)
                            streamed.add(new_idx)
                            _leader_ctx.incomplete_reads += 1
                            if delay_set and consumer is not None:
                                _credit_consumer(consumer, entry, new_idx,
                                                 table_store, trail,
                                                 delay_set)
                            yield (_proceed, None)
                    _st = yield (_gen, None)
                # ``not pass_delays`` is belt-and-braces, with no pinning test:
                # removing it fails no test, and none could be built.  A
                # delay arises from a negation over a table on the leader
                # stack (``_delay_negation``: it succeeds conditionally
                # however far that table has grown) or from a conditional
                # row of a COMPLETE table; any read of an incomplete table
                # on the way is caught by the other three tests.  So a
                # re-run should derive the same answers with the same
                # delays.  Kept because a conditional answer's delay
                # bookkeeping (``_charge_delays``, ``_credit_consumer``,
                # ``_resolve_conditions``) was written for a leader that
                # runs its fixpoint to a confirming pass, and that pass is
                # paid only by tables with conditional answers.
                if (changed and not entry.suspended and not entry.scc_deps
                        and not pass_delays
                        and _leader_ctx.incomplete_reads == reads_at_start):
                    # No confirming pass (D68 review F3): nothing in this pass
                    # read an incomplete table -- no consumer suspended on
                    # this one, no SCC dependency, no answer handed out from
                    # an incomplete table anywhere beneath it (the
                    # ``incomplete_reads`` counter: a constrained answer
                    # streamed into the pass, say) -- and no answer is
                    # conditional.  The counter sees every such hand-out
                    # but one: the DELIVERY after an SCC member's fixpoint
                    # (below, "Delivery") hands back rows of its incomplete
                    # table without a bump.  That is safe: a table becomes
                    # an SCC member only by consuming a still-evaluating
                    # ancestor, and that consumer read, made inside the
                    # same pass, already bumped the counter, registered a
                    # suspended consumer on the ancestor and recorded an
                    # ``scc_deps`` edge on the leader that made it.  Every tabled call it made is complete,
                    # so a re-run derives the same answers.  Only a
                    # body that reads its OWN side effects (an assertz in the
                    # pass, read by a clause that ran before it) could differ,
                    # and then the single pass gives what the untabled
                    # program gives, with the side effects run once
                    # (tests/iso_l3/test_l3_tabled_complete_first.py::
                    # test_a_side_effect_runs_once_and_is_not_reread).
                    # That is Q4, provisional under operator ruling D74,
                    # 2026-10-19: accepted and documented, not yet final.
                    changed = False
                entry._current_delays.clear()
                # Consumers that suspended during this pass are re-derived by the
                # next pass; finish their parked generators cleanly.
                _close_suspended(entry)

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
            # Lead-guarded too: a re-lead reuses the entry OBJECT (rule 4).
            _repair_lead(entry, lead, table_store, store_key)
            raise
        finally:
            if _srec is not None:
                _close_tabled(_srec)
            if entry.lead is lead:
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
        # Delivery (complete first, above): the fixpoint is done and, at the
        # root, global resolution has run.  Every live row in table order,
        # re-unified against the call args like the COMPLETE path.  A row
        # appended meanwhile (the caller's continuation re-led this dormant
        # entry) is delivered too.  A caller that stops pulling (once/1)
        # simply never resumes this generator -- normal abandonment.
        _rec = None
        if entry.status != "complete":
            # An SCC member: its table is incomplete until the ancestor it
            # depends on completes, so a cut over this call is XSB's
            # run-time error, naming that ancestor.  These rows are NOT
            # counted in ``incomplete_reads`` (the one exception; see the
            # "No confirming pass" comment above for why that is safe).
            _rec = _open_tabled(entry, functor, arity, trail,
                                _evaluating_ancestor(entry))
        try:
            i = 0
            while i < len(entry.answers):
                c = entry.conditions[i]
                if c is not _FAILED and i not in streamed:
                    mark = trail.mark()
                    if _unify_answer(args, entry.row(i), trail):
                        if consumer is not None and c is not _UNCONDITIONAL:
                            delays = entry.delays_for(i)
                            if delays:
                                _credit_consumer(consumer, entry, i,
                                                 table_store, trail, delays)
                        yield (_proceed, None)
                    trail.undo(mark)
                i += 1
        finally:
            if _rec is not None:
                _close_tabled(_rec)
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
