"""clausal.logic.database — in-memory predicate clause store.

Components:
    Clause    — one clause (head term + list of body goal terms)
    Database  — maps (functor, arity) → clause list + signatures
    Module    — runtime $module object wrapping a Database
"""

from __future__ import annotations

import contextlib
import dataclasses
from collections import namedtuple
from typing import Any, Callable

from clausal.terms import And, Call, Compound, KWTerm, LoadName, PyThunk
from clausal.pythonic_ast.nodes import TupleLiteral, StarUnpack
from clausal.logic.cells import (TUPLE_TAG, compound_cell_shape, is_chars,
                                 cell_args, make_cell)
from clausal.logic.exceptions import (
    LogicException,
    existence_error,
    permission_error,
    type_error,
)
from clausal.logic.predicate import (
    PredicateMeta,
    describe_term_identity_mismatch,
    is_term_instance,
    is_zero_field_class,
    module_source_path,
    term_field_names,
    term_field_dict,
)


# ── Clause ─────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Clause:
    """One predicate clause: a head term and a list of body goal terms.

    An empty body list means a fact.

    ``position`` (Slice G) is the source-position tuple of the
    originating ``.clausal`` clause statement — the whole
    ``head <- body`` span.  Set by
    :meth:`LogicModule.define_predicate` from the parsed
    :class:`~clausal.pythonic_ast.nodes.Predicate` node.  ``None`` for
    clauses added at runtime (``assertz`` / generated-from-nothing
    dataclass facts) that have no source origin.
    """

    head: Any
    body: list  # list[term]
    position: "tuple[int,int,int,int] | None" = dataclasses.field(
        default=None, compare=False, repr=False,
    )

    def is_fact(self) -> bool:
        return not self.body


# ── PredRow ────────────────────────────────────────────────────────────────────


WriteStamp = namedtuple("WriteStamp", "author kind detail")
"""One provenance record on ``PredRow.writes``: who wrote, what kind of write,
and a free-form detail. Diagnostics, not history — see ``PredRow.record_write``.
"""

_WRITES_CAP = 32

DEFAULT_BACKEND = "python"
"""The in-tree dispatch backend: the Python compiler in
``clausal/logic/compiler/``.  The only backend this repository ships — see
:meth:`Database.set_backend_chooser` for the seam an out-of-tree one plugs
into."""


@dataclasses.dataclass(slots=True)
class PredRow:
    """Per-``(functor, arity)`` predicate state, minted by ``Database.row()``.

    P3-3 Task 1 (additive; zero behavior change): this is a THIN READ-THROUGH
    facade over the Database's existing storage, not a second parallel store.
    ``clauses``, ``dispatch_fn``, ``lazy_recompile``, ``signature`` and
    ``dynamic`` are ALL properties that read/write straight through to the
    Database's existing ``_clauses``/``_dispatch``/``_lazy_recompile``/
    ``_signatures``/``_dynamic`` containers, so the legacy public methods
    (``assertz``, ``set_dispatch``, ``register_signature``, ``mark_dynamic``,
    ...) keep operating exactly as before — untouched by this task — while a
    row and the legacy dicts always agree, and a row SELF-HEALS across a
    wholesale backing-dict wipe (e.g. the existing ``db._clauses.clear()``
    pattern in tests/test_search.py:472-474): the next access re-aliases
    whatever the dict holds at that moment instead of a stale captured
    reference. The ``_rows`` cache on ``Database`` is never invalidated, but
    that's harmless precisely because every field is live — a cached row
    outliving a wipe just re-reads through it.

    ``locked``, ``source`` and ``writes`` are new state that nothing else
    reads or writes yet this task; they exist here only because later tasks
    (Task 2 onward) consume this exact field set.
    """

    _db: "Database" = dataclasses.field(repr=False, compare=False)
    _key: "tuple[str, int]" = dataclasses.field(repr=False, compare=False)
    # Which backend compiled the dispatch this row currently holds (P3-3
    # Task 4).  ``"python"`` — the in-tree compiler — unless a backend
    # chooser said otherwise at install time; see
    # ``Database.set_backend_chooser``.  Descriptive, not a request: it
    # records what happened, and changing it by hand installs nothing.
    backend: str = DEFAULT_BACKEND
    locked: bool = False
    source: "tuple[str, str] | None" = None
    writes: list = dataclasses.field(default_factory=list)
    # (REMOVED 2026-09-22, option D.)  ``dynamic_arities`` used to live here
    # as a per-NAME set, on the argument that it "cannot be reconstructed from
    # one key's boolean".  True of ONE key; false of the SET: scanning
    # ``self._dynamic`` for every entry with a given functor recovers both
    # distinctions that mattered — "nothing declared" (an empty result, which
    # ``_declared_arity`` treats exactly as the old ``None``) and size 1 vs
    # >1.  ``PredicateMeta._declared_arity`` derives it that way now, so the
    # Database is the single store for a declaration.  See ``PredicateMeta.
    # _declared_arity``, which declines on ``None``, declines on
    # ``len(...) != 1``, and reports the single element otherwise.
    # Index plans (arg_index): the call-site bucket functions the compiler
    # exposes per argument position. Row-LOCAL (P1, 2026-09-17): they were
    # class-only state, the one thing an index-hint pass could not find by
    # (functor, arity). ``repr=False``: they hold closures.
    # Nothing here clears a stale plan: the compiler REWRITES all three on
    # every recompile of this key, which is what keeps them in step with the
    # dispatch, and ``locked`` is what gates every reader (``hint_row``
    # refuses an unlocked row, because its bucket functions may still be
    # rebuilt), so a plan is never read across the window in which it could
    # be stale.
    index_plans: dict = dataclasses.field(default_factory=dict, repr=False, compare=False)
    index_plans_joint: dict = dataclasses.field(default_factory=dict, repr=False, compare=False)
    index_plans_hierarchical: dict = dataclasses.field(default_factory=dict, repr=False, compare=False)
    # The list handed out by ``clauses`` while this predicate has NO entry in
    # ``Database._clauses`` yet — an UNMINTED clause list.  ``None`` once the
    # entry exists (``ensure_clauses`` promotes this exact object into the
    # dict, so nothing appended to it before promotion is lost, and the
    # setter clears it for the same reason).  See ``clauses``.
    _unminted_clauses: "list | None" = dataclasses.field(
        default=None, repr=False, compare=False,
    )
    # Open-transaction depth (P3-3 Task 3).  Non-zero while a
    # ``Database.mutate`` transaction naming this row is in flight; the
    # ``dispatch_fn`` setter refuses an install while it is 0, and a nested
    # ``mutate`` on a row already in a transaction inherits that
    # transaction's authorization instead of asking the policy again.
    _txn: int = dataclasses.field(default=0, repr=False, compare=False)
    # True for the PRIVATE row a ``PredicateMeta`` mints for itself outside
    # any module load (``PredicateMeta._detached_row``).  A detached row is
    # nobody's predicate, so a class sitting on one may be bound onto a real
    # Database's row freely; a class on a REAL row may not be moved off it by
    # an unauthorized write (see ``PredicateMeta._bind_row``).
    detached: bool = False

    @property
    def db(self) -> "Database":
        """The Database this row belongs to."""
        return self._db

    @property
    def key(self) -> "tuple[str, int]":
        """This row's ``(functor, arity)``."""
        return self._key

    @property
    def clauses(self) -> list:
        """Clause list for this predicate — the SAME object as the legacy
        ``Database._clauses[key]`` entry whenever that entry exists, always
        re-read live (never a captured reference) so it self-heals across a
        wholesale dict wipe.

        READING THIS DOES NOT MINT (P3-3 Task 2 fix round 1). When the
        Database has no entry for this key, the getter hands back a per-row
        empty list and leaves ``Database._clauses`` untouched, so
        ``is_defined(functor, arity)`` stays False. That matters because
        Task 2 routed every clause read off a ``PredicateMeta`` through here: a
        setdefault in the getter would have turned each of those reads —
        ``__repr__``, ``_clause_arity``, ``_declared_arity``, the compiler's
        own inspections — into a minting site, and a clause-less
        ``-dynamic`` predicate would report itself defined merely for having
        been looked at.

        Minting stays where Task 1's contract put it: the explicit,
        sanctioned mutation sites, all of which call ``ensure_clauses``
        first — ``Database.assertz``/``asserta`` (and therefore
        ``LogicModule.define_predicate``, which goes through them),
        ``PredicateMeta._assertz``/``_asserta``, and ``compiler_v2`` step
        4's clause install.

        The unminted list is IDENTITY-PRESERVING: ``ensure_clauses`` promotes
        that same object into the dict rather than a fresh one, so a caller
        that read the list, appended to it, and only then triggered a mint
        does not lose the append.
        """
        existing = self._db._clauses.get(self._key)
        if existing is not None:
            return existing
        pending = self._unminted_clauses
        if pending is None:
            pending = self._unminted_clauses = []
        return pending

    @clauses.setter
    def clauses(self, value: list) -> None:
        """Replace the clause list wholesale with *value* — the caller's list
        object itself, not a copy, so an alias the caller keeps stays live.

        This one DOES mint: an explicit assignment is an explicit statement
        that this predicate has a clause list. Exists for the legacy spelling
        that rebinds rather than mutates (``row.clauses = []``, used by
        several tests to reset a class between cases). Every in-tree
        production write is an in-place mutation of the list the getter hands
        back.
        """
        self._db._clauses[self._key] = value
        self._unminted_clauses = None

    def ensure_clauses(self) -> list:
        """Mint this predicate's clause list in the Database and return it.

        The ONE sanctioned promotion point (P3-3 Task 2 fix round 1): callers
        that are about to MUTATE the clause list call this first, so the
        mutation lands somewhere ``db.clauses_for``/``is_defined`` can see,
        while a plain ``clauses`` READ mints nothing. Idempotent, and
        identity-preserving — the list already handed out by ``clauses`` is
        the object promoted, never a fresh one.
        """
        clauses = self._db._clauses.get(self._key)
        if clauses is None:
            clauses = self._unminted_clauses
            if clauses is None:
                clauses = []
            self._db._clauses[self._key] = clauses
        self._unminted_clauses = None
        return clauses

    @property
    def dispatch_fn(self) -> "Callable | None":
        return self._db._dispatch.get(self._key)

    @dispatch_fn.setter
    def dispatch_fn(self, value: "Callable | None") -> None:
        """INSTALLING a dispatch requires an open ``Database.mutate``
        transaction (P3-3 Task 3); CLEARING one never does.

        The aliased-import clobber (``adf95a31``) went through this channel
        while the clause list was guarded: a second module replaced the shared
        predicate's dispatch and the damage was invisible to a clause count.
        Requiring the txn is what makes that shape impossible rather than
        merely refused where somebody remembered to check — the gate has
        already asked "may this author write this row" by the time control
        gets here.

        Writing ``None`` is not a clobber: it is invalidation, and a cleared
        dispatch recompiles from the OWNER's clause list, so it can lose no
        answers.  It routes to ``invalidate()`` — the one invalidation point —
        which keeps every ``row.dispatch_fn = None`` spelling in the tree
        working without a transaction.
        """
        if value is None:
            self.invalidate()
            return
        if self._txn == 0:
            functor, arity = self._key
            raise RuntimeError(
                f"dispatch install for {functor}/{arity} outside a mutation "
                f"transaction (channel: PredRow.dispatch_fn) — write it "
                f"inside Database.mutate({functor!r}, {arity}, author=..., "
                f"kind=...)"
            )
        self._db._dispatch[self._key] = value

    @property
    def lazy_recompile(self) -> "Callable | None":
        return self._db._lazy_recompile.get(self._key)

    @lazy_recompile.setter
    def lazy_recompile(self, value: "Callable | None") -> None:
        self._db._lazy_recompile[self._key] = value

    @property
    def signature(self) -> "tuple[str, ...] | None":
        return self._db._signatures.get(self._key)

    @signature.setter
    def signature(self, value: "tuple[str, ...] | None") -> None:
        self._db._signatures[self._key] = value

    @property
    def dynamic(self) -> bool:
        return self._key in self._db._dynamic

    @dynamic.setter
    def dynamic(self, value: bool) -> None:
        if value:
            self._db._dynamic.add(self._key)
        else:
            self._db._dynamic.discard(self._key)

    def invalidate(self) -> None:
        """Clear the compiled dispatch function only; ``lazy_recompile`` is left
        intact so the next call can recompile through it.

        THE one invalidation point (P3-3 Task 3): the ``dispatch_fn`` setter
        routes ``= None`` here, ``Database.mutate`` calls it on exit from a
        transaction that changed the clause list, and the channels that used
        to invalidate for themselves no longer do.  It writes the backing dict
        directly — going back through the setter would recurse.
        """
        self._db._dispatch[self._key] = None

    def record_write(self, author: str, kind: str, detail: Any = None) -> None:
        """Append a ``WriteStamp`` to ``writes``, keeping only the last 32.

        Diagnostics, not history.  ``Database.mutate`` calls this once per
        authorized transaction, so provenance is per WRITE rather than per
        load — the defect the mutation-gate todo names for ``assertz``, whose
        clauses used to be attributed to whichever module last compiled the
        predicate.
        """
        self.writes.append(WriteStamp(author, kind, detail))
        if len(self.writes) > _WRITES_CAP:
            del self.writes[: len(self.writes) - _WRITES_CAP]

    def mutate(self, author: str, kind: str, detail: Any = None,
               through: Any = None):
        """Row-side spelling of :meth:`Database.mutate`, for callers that hold
        a row (or a class bound to one) rather than a ``(functor, arity)``
        pair.  Same gate, same policy — this only spares them reaching into
        ``_db``/``_key`` to say what they already have."""
        functor, arity = self._key
        return self._db.mutate(
            functor, arity, author=author, kind=kind, detail=detail,
            through=through,
        )


# ── The mutation policy ────────────────────────────────────────────────────────
#
# ONE question — "may this author write this row" — asked in ONE place, by
# every channel, through ``Database.mutate``.  Before P3-3 Task 3 there were
# four channels onto a shared predicate and a guard in front of whichever one
# a bug had last been found behind
# (``todo/done/a-shared-predicate-has-no-single-mutation-gate.md``).
#
# An AUTHOR is a string identifying who is writing:
#
#   * a load writes as its module's canonical SOURCE PATH.  The path, never
#     the module name: one file legitimately compiles under two names in one
#     process (a dotted ``-import_from`` and ``clausal.testing.
#     load_clausal_module``'s ``_clausal_test_*``), and keying ownership on
#     the name made a file refuse to load beside itself
#     (``todo/done/predicate-identity-is-keyed-on-spelling-not-on-the-class
#     .md``, instance 1).  ``Database.load_author`` builds it.
#   * a runtime assert/retract writes as ``runtime-assert:<module>``.
#     ``Database.runtime_author`` builds it.
#
# A KIND says what sort of write it is; the policy branches on it, and it is
# the only branch in here:

WRITE_LOAD_CLAUSES = "load-clauses"
WRITE_LOAD_DISPATCH = "load-dispatch"
WRITE_ASSERT = "assert"
WRITE_RETRACT = "retract"
WRITE_RECOMPILE = "recompile"

_LOAD_KINDS = frozenset((WRITE_LOAD_CLAUSES, WRITE_LOAD_DISPATCH))
_RUNTIME_KINDS = frozenset((WRITE_ASSERT, WRITE_RETRACT))
# Kinds whose transaction can leave the compiled dispatch out of step with the
# clause list, and which therefore invalidate on the way out.
_CLAUSE_KINDS = frozenset((WRITE_LOAD_CLAUSES, WRITE_ASSERT, WRITE_RETRACT))

RUNTIME_AUTHOR_PREFIX = "runtime-assert:"


def write_refusal(row: "PredRow", author: str, kind: str) -> "str | None":
    """THE ownership policy.  Return why *author* may not write *row* with a
    write of *kind*, or ``None`` when the write is permitted.

    Three rules, in order:

    1. **The owner may always write.**  ``row.source`` records the load that
       supplied the clauses; a re-compile of that same file — under any module
       name, from any channel — is that load writing its own predicate again.
    2. **A runtime write is refused by the lock.**  ``assertz``/``retract``
       against a LOCKED (static) procedure is the ISO refusal, unchanged in
       meaning from the per-channel ``_locked`` checks this replaces; it now
       covers the low-level ``Database.assertz`` door too, which the dual
       store used to guard by accident (P3-3 Task 2, F3).
    3. **A load may not overwrite somebody else's predicate.**  This is the
       clause-clobber refusal: an ``-import_from`` SHARES the exporter's
       class, so a clause written here would replace, not extend, for every
       module that can reach it.  Narrowed exactly as the guard it replaces
       was: a row nobody owns (``source is None`` — the clause-free vocabulary
       export, whose implementer lives downstream) and an owned row with
       nothing on it are both free to write.

    ``WRITE_RECOMPILE`` is deliberately never refused: recompiling a dispatch
    from the clause list the row already holds changes no answers and takes no
    authorship.  What the dispatch channel has to refuse is a LOAD installing
    its own dispatch onto another module's predicate — ``WRITE_LOAD_DISPATCH``,
    rule 3, which is the aliased-import clobber (``adf95a31``).
    """
    owner = row.source[1] if row.source else None
    if owner is not None and author == owner:
        return None
    if kind in _RUNTIME_KINDS:
        if row.locked:
            # "locked" is the word this refusal has always used for the
            # static-procedure state, and callers match on it; the rest of
            # the line is what the gate adds.
            return ("it is a locked static procedure"
                    + (f" owned by {owner}" if owner else "")
                    + " — declare it -dynamic to assert against it")
        return None
    if kind in _LOAD_KINDS:
        if owner is None:
            return None
        n = len(row.clauses)
        if n:
            return (f"its {n} clause{'' if n == 1 else 's'} "
                    f"{'is' if n == 1 else 'are'} owned by {owner}")
        if row.locked:
            return f"it is a locked predicate owned by {owner}"
    return None


def refusal_error(functor: str, arity: int, author: str, kind: str,
                  reason: str, channel: "str | None" = None,
                  attempted: "tuple[str, int] | None" = None) -> LogicException:
    """The ONE refusal.  Every channel raises this exception or wraps it; no
    channel keeps a diagnostic of its own.

    The term is the ISO ``permission_error(modify, static_procedure, F/A)``
    the ``assertz/1`` family already raised — unchanged, so ``catch/3``
    programs still catch it — with the context extended to carry the author
    and the row key, which is what makes one text usable from four channels.
    It still LEADS with the channel (``assertz/1``, ``retract/1``, ...) where
    the caller named one, because that is the part of the old context a
    reader of the error was using to find the call.

    *attempted* is the key the CALLER asked to write, when the refusing row is
    not it (final review M-e).  A write's blast radius includes the row a
    shared ``-import_from``'d class is reading, and that row can have a
    different ARITY from the one the caller named: the importer writing
    ``k(a, 2)`` against an owner that exports the atom ``k`` was refused with
    "may not write k/0", naming a key that appears nowhere in the importer's
    source.  The refusal is right and the row it names is the right row; the
    line just has to say both, or the reader hunts for a ``k/0`` they never
    wrote.  Omitted (or equal to the row's own key) leaves the text exactly as
    it was.
    """
    where = f"{functor}/{arity}"
    if attempted is not None and tuple(attempted) != (functor, arity):
        where = f"{where} (reached by writing {attempted[0]}/{attempted[1]})"
    return LogicException(permission_error(
        "modify", "static_procedure", Compound("/", (functor, arity)),
        f"{channel or kind}: {author} may not write {where}: "
        f"{reason}",
    ))


# ── The backend seam ───────────────────────────────────────────────────────────
#
# Process-wide, because the decision is per ROW and a row names its own
# ``db``.  Both are empty/``None`` in this repository: ``"python"`` is the only
# backend in tree.  See ``Database.set_backend_chooser`` for the contract.

_BACKEND_CHOOSER: "Callable[[PredRow], str] | None" = None
_BACKEND_INSTALLERS: dict[str, Callable] = {}


# ── Database ───────────────────────────────────────────────────────────────────


class Database:
    """in_-memory store mapping (functor, arity) → clause list."""

    def __init__(self, module_dict: dict | None = None) -> None:
        self._clauses: dict[tuple[str, int], list[Clause]] = {}
        self._signatures: dict[tuple[str, int], tuple | None] = {}
        # P2 Task 2 (R-P2-1): the DECLARATION registry -- (functor, arity) ->
        # declared field names, from fielded -private/-module entries and
        # -import_from'd ones.  A declared functor is DATA until a row exists
        # for it (clauses, -dynamic, a directive naming it); see declared_kind.
        self._declared: dict[tuple[str, int], tuple[str, ...]] = {}
        self._dispatch: dict[tuple[str, int], Callable | None] = {}
        self._lazy_recompile: dict[tuple[str, int], Callable] = {}
        self._dynamic: set[tuple[str, int]] = set()
        self._discontiguous: set[tuple[str, int]] = set()
        self._tabled: set[tuple[str, int]] = set()
        self._shallow: set[tuple[str, int]] = set()
        self._table_store: dict = {}
        self._rows: dict[tuple[str, int], PredRow] = {}
        # Rows another database OWNS, resolvable here under this module's own
        # spelling because an ``-import_from`` named them (spec §4 q1).  Held
        # apart from ``_rows`` deliberately: adoption must never shadow a
        # predicate this module goes on to DEFINE, and imports are processed
        # before any local clause is compiled, so an entry in ``_rows`` would
        # be found by the local definition's own ``row(..., create=True)``.
        # See ``row()``: adopted rows answer READS only.
        self._adopted: dict[tuple[str, int], PredRow] = {}
        self.module_dict: dict | None = module_dict

    def arities_for(self, functor: str) -> "set[int]":
        """Every arity this database knows *functor* at.

        The functor-only question ``row(functor, arity)`` cannot answer, and
        the one the import plant needs: an ``-import_from`` names a predicate
        but carries no arity, so the arities have to come from the EXPORTER's
        database.  Scans the same containers ``row()``'s own ``known`` test
        consults, so the two agree about what "this database knows it" means.
        """
        found = {a for (f, a) in self._rows if f == functor}
        for keyed in (self._clauses, self._dispatch, self._lazy_recompile,
                      self._signatures, self._dynamic):
            found |= {a for (f, a) in keyed if f == functor}
        return found

    def functors(self) -> "list[str]":
        """Every predicate NAME this database knows, sorted.

        The functor-only twin of ``arities_for``, and the population a
        diagnostic means by "the predicates available here": the same
        containers ``row()``'s own ``known`` test consults, plus ``_adopted``
        -- a row this module adopted at ``-import_from`` answers reads here
        under this module's own spelling, so the name IS available.

        Exists so a caller outside this module does not have to reach into
        ``_rows`` to enumerate (final review minor 5, 2026-09-17): ``_rows``
        is LAZILY materialised, so it is the one container that can be
        missing a name the database plainly knows -- which made a
        ``-specialize`` diagnostic list a population that was not quite the
        one it was refusing against.
        """
        found = {f for (f, _a) in self._rows}
        found |= {f for (f, _a) in self._adopted}
        for keyed in (self._clauses, self._dispatch, self._lazy_recompile,
                      self._signatures, self._dynamic):
            found |= {f for (f, _a) in keyed}
        return sorted(found)

    def adopt_row(self, local_functor: str, arity: int, row: "PredRow") -> bool:
        """Make ``(local_functor, arity)`` resolve to an existing *row* that
        another database owns.  True if it was adopted, False if this database
        already had something under that key.

        Spec §4 q1.  ``-import_from`` is ``getattr`` today, so the importing
        database holds no row and no dispatch for an imported predicate and
        the whole relationship lives as one Python object reference in
        ``module_dict``.  This is the relationship, in the store that is
        supposed to hold it -- keyed by the IMPORTER's spelling, which is what
        makes an aliased import an ordinary key rather than a class whose
        ``__name__`` disagrees with the name the file uses.

        Never displaces an existing entry: a module that imports a name AND
        defines its own predicate under it keeps its own, and the clash is
        left for the mutation gate to police rather than silently resolved
        here in load order.
        """
        key = (local_functor, arity)
        if key in self._rows or key in self._adopted:
            return False
        self._adopted[key] = row
        return True

    def owns(self, functor: str, arity: int) -> bool:
        """True if this database is the HOME of ``(functor, arity)`` — as
        opposed to merely resolving it through a row it adopted at import.

        The replacement for asking a predicate class whether it "belongs
        elsewhere" (``compiler_v2._belongs_elsewhere``): a row knows its own
        database, so ownership is a property of the row rather than of a class
        object's identity across module copies.
        """
        row = self.row(functor, arity)
        return row is not None and row.db is self

    def row(self, functor: str, arity: int, create: bool = False) -> "PredRow | None":
        """Return the ``PredRow`` for ``(functor, arity)``, or ``None``.

        Rows are cached: repeated calls for the same key return the SAME
        object. A predicate reached only through legacy paths (``assertz``,
        ``set_dispatch``, ``register_signature``, ``mark_dynamic``) is still
        "known" and discoverable with ``create=False`` — the Database is the
        authoritative store regardless of which door state came in through.
        With ``create=False`` an unknown predicate returns ``None``; with
        ``create=True`` a row is minted (and cached) even for a brand-new key.
        """
        key = (functor, arity)
        existing = self._rows.get(key)
        if existing is not None:
            return existing
        known = (
            key in self._clauses
            or key in self._dispatch
            or key in self._lazy_recompile
            or key in self._signatures
            or key in self._dynamic
        )
        if not known:
            # A row this module ADOPTED at import answers a read -- that is
            # what makes ``db.row(functor, arity)`` a correct answer to "what
            # does this name mean here".  It must NOT answer a write: a
            # ``create=True`` caller is defining a predicate, and handing it
            # somebody else's row is how a local clause stops producing
            # solutions (tests/fixtures/fnmismatch_use.clausal).
            if not create:
                return self._adopted.get(key)
        # NOTE: deliberately does NOT touch ``_clauses`` here (Finding 2) —
        # minting a row from a dispatch/signature/dynamic-only predicate must
        # not flip ``is_defined()`` False→True. Clause-list vivification is
        # deferred to first access of the ``clauses`` property.
        new_row = PredRow(self, key)
        self._rows[key] = new_row
        return new_row

    # ── The backend seam ────────────────────────────────────────────────────

    @classmethod
    def set_backend_chooser(cls, fn: "Callable[[PredRow], str] | None"):
        """Install the per-predicate backend chooser; returns the previous one.

        THE SEAM.  This is the single point at which something other than the
        in-tree Python compiler can own a predicate's compiled dispatch, and
        it exists so that the copy-and-patch JIT revival
        (``implementation_plans/stencil-v2-scoping-memo.md``, "What rewrites"
        → "The integration seam") has one hook to target instead of the ~1,196
        LOC of ad-hoc backend selection the parked branch grew inside
        ``compiler/predicate.py``.  That memo calls the parked seam a complete
        rewrite rather than an adaptation; this is what it rewrites TO.

        The contract, in three sentences:

        1. **One invalidation point.**  A dispatch is dropped by
           :meth:`PredRow.invalidate` and by nothing else, whatever compiled
           it.  A backend that caches anything derived from a predicate's
           clauses hangs that cache off the row and lets ``invalidate()``
           drive it; it must not install its own invalidation channel, because
           a second channel is exactly the shape the P3-3 mutation gate exists
           to make impossible.
        2. **Per-predicate choice, at install time.**  ``fn(row) -> str`` is
           called once per dispatch install, with the ``PredRow`` about to
           receive it — so the decision can read the predicate's clauses,
           signature, tabled-ness, source module (``row.db``) or anything else
           the row knows.  Its answer is recorded on ``row.backend``.
        3. **Installation stays in one place.**  A backend does not install;
           it PRODUCES.  ``fn`` returning ``"python"`` (the default) leaves the
           install byte-for-byte as it was.  Any other name is looked up in
           the registry (:meth:`register_backend`) and its installer is called
           as ``installer(row, python_fn) -> Callable | None``: the callable it
           returns is what gets installed, through the same transaction, the
           same tabling wrapper and the same provenance stamp the Python
           dispatch would have gone through.  Returning ``None`` means "not
           mine" — a real backend cannot compile every predicate shape — and
           falls back to the Python dispatch with ``row.backend`` left at
           ``"python"``.

        Process-wide rather than per-``Database``: the decision is made per
        ROW, and a row names its own ``db``, so a chooser that wants
        per-module policy reads ``row.db`` instead of needing an installation
        per module.  Passing ``None`` restores the default (always
        ``"python"``), which is also the state this repository ships in — no
        backend is registered in-tree.
        """
        global _BACKEND_CHOOSER
        previous = _BACKEND_CHOOSER
        _BACKEND_CHOOSER = fn
        return previous

    @classmethod
    def backend_chooser(cls) -> "Callable[[PredRow], str] | None":
        """The installed backend chooser, or ``None`` when the default
        (always ``"python"``) is in force."""
        return _BACKEND_CHOOSER

    @classmethod
    def register_backend(cls, name: str, installer: Callable) -> None:
        """Register ``installer`` under ``name`` for :meth:`set_backend_chooser`.

        ``installer(row, python_fn)`` returns the dispatch callable to install
        in place of ``python_fn``, or ``None`` to decline this predicate.
        ``"python"`` is the in-tree backend and cannot be re-registered.
        """
        if name == DEFAULT_BACKEND:
            raise ValueError(
                f"{DEFAULT_BACKEND!r} is the in-tree backend and cannot be "
                f"re-registered"
            )
        _BACKEND_INSTALLERS[name] = installer

    def backend_dispatch(self, functor: str, arity: int,
                         fn: Callable) -> Callable:
        """Resolve ``functor/arity``'s backend and return the dispatch to install.

        Called by the compiler's single install choke point
        (``compiler/predicate.py::_install``) with the freshly compiled Python
        dispatch.  With no chooser installed this returns ``fn`` untouched
        without so much as looking a row up — the default path costs one
        global read.
        """
        chooser = _BACKEND_CHOOSER
        if chooser is None:
            return fn
        row = self.row(functor, arity, create=True)
        backend = chooser(row) or DEFAULT_BACKEND
        if backend != DEFAULT_BACKEND:
            installer = _BACKEND_INSTALLERS.get(backend)
            if installer is None:
                # Through the engine's error family, like every other refusal
                # in this file (P3-3 Task 4 fix round 1): an ISO
                # ``existence_error(backend, Name)`` a ``catch/3`` can see,
                # not a stray Python builtin.
                raise LogicException(existence_error(
                    "backend", backend,
                    f"backend_dispatch: backend {backend!r} chosen for "
                    f"{functor}/{arity} is not registered — call "
                    f"Database.register_backend({backend!r}, installer) first",
                ))
            replacement = installer(row, fn)
            if replacement is not None:
                row.backend = backend
                return replacement
            backend = DEFAULT_BACKEND  # the backend declined this predicate
        row.backend = backend
        return fn

    # ── The mutation gate ───────────────────────────────────────────────────

    def module_name(self) -> str:
        """This Database's module name, for authorship strings only.

        ``module_dict`` is not always a module dict: a handful of callers
        construct ``Database("some-name")``, so this reads defensively — an
        author string is diagnostics, and must never be the thing that raises.
        """
        md = self.module_dict
        if isinstance(md, dict):
            return md.get("__name__") or "<anonymous>"
        if isinstance(md, str):
            return md
        return "<detached>"

    def load_author(self) -> str:
        """Author string for a write this Database's own LOAD makes: the
        canonical source path of its module, which is the identity ownership
        is keyed on (never the module name — see the policy above)."""
        md = self.module_dict
        path = module_source_path(md) if isinstance(md, dict) else None
        return path or f"load:{self.module_name()}"

    def runtime_author(self) -> str:
        """Author string for a runtime ``assertz``/``asserta``/``retract``
        against this Database.  Distinct from :meth:`load_author` on purpose:
        that distinction IS the per-write provenance the mutation-gate todo
        asks for."""
        return f"{RUNTIME_AUTHOR_PREFIX}{self.module_name()}"

    def _write_rows(self, functor: str, arity: int, through: Any = None,
                    create: bool = True) -> "list[PredRow]":
        """Every row in the blast radius of a write to ``(functor, arity)``
        made *through* an optional ``PredicateMeta``.

        One definition, used by both :meth:`mutate` and :meth:`refusal_for`,
        so a dry run cannot ask about a different set of rows than the write
        would touch.
        """
        rows = []
        target = self.row(functor, arity, create=create)
        if target is not None:
            rows.append(target)
        if through is not None:
            other = getattr(through, "_row", None)
            if isinstance(other, PredRow) and all(r is not other for r in rows):
                rows.append(other)
        return rows

    def refusal_for(self, functor: str, arity: int, *, author: str, kind: str,
                    detail: Any = None,
                    through: Any = None) -> "LogicException | None":
        """Ask the policy WITHOUT opening a transaction: the exception
        :meth:`mutate` would raise, or ``None`` if the write is permitted.

        The policy is pure, which is what makes a dry run meaningful — and
        what lets a LOAD ask about every predicate it is going to write
        BEFORE it writes any of them.  Without that, a refusal fired partway
        through the write loop leaves the module it was protecting holding
        the earlier, legal writes of a load that never finished (the ordering
        property the deleted step-3c pre-pass carried).

        Mints nothing: rows are looked up with ``create=False``.
        """
        for row in self._write_rows(functor, arity, through, create=False):
            if row._txn:
                continue
            reason = write_refusal(row, author, kind)
            if reason is not None:
                return refusal_error(
                    *row.key, author, kind, reason,
                    channel=detail if isinstance(detail, str) else None,
                    attempted=(functor, arity),
                )
        return None

    @contextlib.contextmanager
    def mutate(self, functor: str, arity: int, *, author: str, kind: str,
               detail: Any = None, through: Any = None):
        """THE mutation gate: open a write transaction on ``(functor, arity)``
        and yield its row.  Every channel that mutates predicate state goes
        through here.

        On entry the ownership policy (:func:`write_refusal`) is asked once,
        and a refusal raises :func:`refusal_error` — the one refusal, in the
        one text, for all four channels.  On exit — CLEAN OR NOT — the write is
        stamped on the row (``author``, ``kind``, ``detail``, the detail
        marked ``(failed)`` when the body raised), and a transaction of a
        clause-writing kind invalidates the row and abolishes its table
        unless it installed a dispatch of its own on the way out.  Both
        belong in the unwind rather than on the happy path: a body that
        appends a clause and then raises leaves the clause behind, and a
        dispatch compiled from the clause list before it is stale however
        the transaction ended.  No channel keeps invalidation code of its
        own.

        *through* is a ``PredicateMeta`` this write will go through when that
        class is not (yet) reading this row: an ``-import_from`` SHARES the
        exporter's class, so writing "our" row through it lands on the
        exporter's predicate for every module that can reach it.  Its current
        row is therefore part of this write's blast radius and is asked the
        same question.  This is also how the ALIASED import is caught, where
        ``module_dict.get(functor)`` finds nothing (identity todo instance 3):
        the resolver hands the class over, and the row answers.

        Transactions nest.  A ``mutate`` naming a row that is already inside
        one inherits that transaction's authorization and stamp — the gate
        authorizes an operation, not a call — which is what lets the low-level
        ``assertz`` keep its own default author for direct callers while a
        load that goes through it is still recorded as the load.
        """
        target = self.row(functor, arity, create=True)
        opened = [row for row in self._write_rows(functor, arity, through)
                  if row._txn == 0]
        for row in opened:
            reason = write_refusal(row, author, kind)
            if reason is not None:
                raise refusal_error(
                    *row.key, author, kind, reason,
                    channel=detail if isinstance(detail, str) else None,
                    attempted=(functor, arity),
                )
        before = [(row, row.dispatch_fn) for row in opened]
        for row in opened:
            row._txn += 1
        failed = False
        try:
            yield target
        except BaseException:
            failed = True
            raise
        finally:
            for row in opened:
                row._txn -= 1
            stamp = f"{detail} (failed)" if failed else detail
            for row, dispatch in before:
                row.record_write(author, kind, stamp)
                if kind not in _CLAUSE_KINDS or row.dispatch_fn is not dispatch:
                    # Not a clause write, or this transaction installed a
                    # dispatch of its own on the way out (the assert channels
                    # recompile inside their transaction) — nothing is stale.
                    continue
                # Unconditional for a clause-writing kind, rather than
                # conditional on a clause-COUNT change: one transaction that
                # removes a clause and adds another leaves the count alone and
                # the compiled dispatch just as stale, and detecting the
                # difference honestly would mean copying the clause list on
                # every assertz.  Recompilation is lazy, so invalidating a
                # transaction that turned out to write nothing costs one
                # recompile.
                db, key = row.db, row.key
                if key in db._dispatch:
                    # Guarded on an EXISTING entry: writing ``_dispatch[key] =
                    # None`` for a never-compiled predicate would announce a
                    # dispatch slot nothing ever filled (pinned by
                    # ``test_retract_builtin_does_not_create_a_dispatch_entry_
                    # it_did_not_find``).
                    row.invalidate()
                if key in db._tabled:
                    db.abolish_table(*key)

    def assertz(self, clause: Clause, author: str | None = None) -> None:
        """Add clause at end of its predicate's clause list.

        P3-3 Task 2: there is no longer a second clause store to mirror onto.
        A ``PredicateMeta`` class bound to this predicate reads its ``_clauses``
        THROUGH ``self.row(functor, arity)`` — the very list appended to here —
        so the class sees the new clause by construction, at the right arity.
        (The deleted mirror was arity-BLIND: it looked the functor up in
        ``module_dict`` and appended a ``p/1`` clause onto whatever class named
        ``p`` happened to be bound, ``p/3`` included.)

        P3-3 Task 3: this door is gated like the others.  *author* defaults to
        :meth:`runtime_author`, so a legacy caller still produces a STAMPED
        write rather than an anonymous one, and the static lock now holds here
        too — before the gate, this was the one channel a locked predicate's
        clauses could be changed through (P3-3 Task 2, F3).  Invalidation and
        table abolition moved into the gate's exit; they are not repeated here.
        """
        functor, arity = _stored_head_key(clause.head, "assertz")
        with self.mutate(functor, arity, author=author or self.runtime_author(),
                         kind=WRITE_ASSERT, detail="assertz") as row:
            row.ensure_clauses().append(clause)

    def asserta(self, clause: Clause, author: str | None = None) -> None:
        """Add clause at front of its predicate's clause list.

        See ``assertz`` for why no class mirror is needed any more, and for
        what the gate does with *author*.
        """
        functor, arity = _stored_head_key(clause.head, "asserta")
        with self.mutate(functor, arity, author=author or self.runtime_author(),
                         kind=WRITE_ASSERT, detail="asserta") as row:
            row.ensure_clauses().insert(0, clause)

    def retract(self, head: Any, author: str | None = None) -> bool:
        """Remove first clause whose head structurally equals head.

        Returns True if a clause was removed.

        See ``assertz`` for why no class mirror is needed any more, and for
        what the gate does with *author*.

        ``_stored_head_key``, symmetrically with ``assertz``/``asserta`` (final
        review M-c): a CELL head read by plain ``head_key`` produced a key,
        matched no stored clause (stored heads are class terms or
        ``Compound``s, never cells) and returned a bare ``False`` — "nothing
        matched", indistinguishable from a genuine miss, for a head this door
        cannot store in the first place.  The same refusal the assert side
        gives points at the same remedy: go through the ``retract/1`` builtin,
        which normalizes the cell.
        """
        functor, arity = _stored_head_key(head, "retract")
        clause_list = self._clauses.get((functor, arity))
        if clause_list is None:
            return False
        if not any(clause.head == head for clause in clause_list):
            # Nothing to remove: no write, so no transaction and no stamp.
            return False
        with self.mutate(functor, arity, author=author or self.runtime_author(),
                         kind=WRITE_RETRACT, detail="retract") as row:
            clauses = row.clauses
            for i, clause in enumerate(clauses):
                if clause.head == head:
                    del clauses[i]
                    return True
        return False

    def clauses_for(self, functor: str, arity: int) -> list[Clause]:
        """Return a snapshot of clauses for (functor, arity), or [] if undefined."""
        return list(self._clauses.get((functor, arity), []))

    def is_defined(self, functor: str, arity: int) -> bool:
        """True if any clause has been asserted for (functor, arity)."""
        return (functor, arity) in self._clauses

    def register_signature(
        self, functor: str, arity: int, param_names: tuple[str, ...]
    ) -> None:
        """Register the keyword parameter names for a predicate.

        If a signature is already registered and matches, this is a no-op.
        If it conflicts, emit a warning.
        """
        import warnings

        key = (functor, arity)
        existing = self._signatures.get(key)
        if existing is None:
            self._signatures[key] = param_names
        elif existing != param_names:
            warnings.warn(
                f"signature conflict for {functor}/{arity}: "
                f"registered {existing}, got {param_names}"
            )

    def signature_for(self, functor: str, arity: int) -> tuple[str, ...] | None:
        """Return the registered keyword param names, or None."""
        sig = self._signatures.get((functor, arity))
        if sig is None:
            sig = self._declared.get((functor, arity))   # P2: a declared functor's fields
        return sig

    # -- the declaration registry (P2 Task 2, R-P2-1) ------------------------

    def declare_functor(self, functor: str, fields: tuple[str, ...]) -> None:
        """Record that this module declares ``functor/len(fields)`` with these
        field names.  Declaring is not defining: ``row()`` stays None until a
        row is minted (clauses, ``mark_dynamic``, a directive naming it)."""
        self._declared[(functor, len(fields))] = tuple(fields)

    def declared_fields(self, functor: str, arity: int) -> tuple[str, ...] | None:
        return self._declared.get((functor, arity))

    def declared_fields_by_name(self, functor: str) -> tuple[str, ...] | None:
        """The by-NAME read the exec-time registry map offered (one entry per
        name; the last declaration wins), for ``functor_signature_for``."""
        found = None
        for (f, _a), fields in self._declared.items():
            if f == functor:
                found = fields
        return found

    def declared_kind(self, functor: str, arity: int) -> str | None:
        """``"predicate"`` when the Database knows a row for the key (clauses,
        dispatch, ``-dynamic``, an adopted import, or a directive-minted row);
        ``"data"`` when it is declared and rowless; ``None`` otherwise."""
        if self.row(functor, arity) is not None:
            return "predicate"
        if (functor, arity) in self._declared:
            return "data"
        return None

    def set_dispatch(
        self,
        functor: str,
        arity: int,
        fn: Callable,
        lazy_recompile: Callable | None = None,
    ) -> None:
        """Store the compiled dispatch function for (functor, arity).

        P3-3 Task 3: the db-side dispatch door, routed through the gate for
        the same reason ``assertz`` is — so the write is stamped and lands
        inside a transaction.  It opens one of its own only when it is not
        already inside somebody's (``compiler._install`` and ``compiler_v2``
        step 6 both call it from within theirs), and a ``WRITE_RECOMPILE`` is
        never refused: installing a dispatch compiled from the row's own
        clauses takes no authorship.
        """
        key = (functor, arity)
        with self.mutate(functor, arity, author=self.load_author(),
                         kind=WRITE_RECOMPILE, detail="set_dispatch") as row:
            row.dispatch_fn = fn
            if lazy_recompile is not None:
                self._lazy_recompile[key] = lazy_recompile

    def get_dispatch(self, functor: str, arity: int) -> Callable | None:
        """Return the compiled dispatch function for (functor, arity), or None.

        If the dispatch was invalidated by assertz/retract and a lazy recompile
        callback is registered, recompiles on demand before returning.
        Falls back to the builtin/stdlib registry if not found locally.
        """
        key = (functor, arity)
        fn = self._dispatch.get(key)
        if fn is None and key in self._dispatch:
            # Invalidated — try lazy recompile.
            lazy = self._lazy_recompile.get(key)
            if lazy is not None:
                fn = lazy()
                # The recompile installs through ``compiler._install``, which is
                # where a ``-table``d predicate is re-wrapped in its SLG
                # wrapper.  Prefer what it stored over the function it returned
                # — see ``PredicateMeta._get_dispatch`` for the same reason.
                installed = self._dispatch.get(key)
                if installed is not None:
                    fn = installed
                else:
                    self._dispatch[key] = fn
        if fn is not None:
            return fn
        from clausal.logic.builtins import get_builtin_dispatch  # noqa: PLC0415
        return get_builtin_dispatch(functor, arity, self)

    # ── Directive metadata ──────────────────────────────────────────────────

    def mark_dynamic(self, functor: str, arity: int) -> None:
        """Mark a predicate as dynamic (runtime assertz/retract allowed)."""
        self._dynamic.add((functor, arity))

    def is_dynamic(self, functor: str, arity: int) -> bool:
        """True if the predicate was declared -dynamic."""
        return (functor, arity) in self._dynamic

    def mark_discontiguous(self, functor: str, arity: int) -> None:
        """Mark a predicate as discontiguous (clauses may be non-adjacent)."""
        self._discontiguous.add((functor, arity))

    def is_discontiguous(self, functor: str, arity: int) -> bool:
        """True if the predicate was declared -discontiguous."""
        return (functor, arity) in self._discontiguous

    def mark_tabled(self, functor: str, arity: int) -> None:
        """Mark a predicate as tabled (memoised via SLG resolution).

        Also stamps the minted PredicateMeta class (when it exists in this
        db's ``module_dict``) with ``_tabled_home_db = self``, so tabledness
        travels with the class across ``-import_from`` — the caller-side NAF
        seam reads the stamp to find the home db and table store
        (todo/cross-module-tabled-naf-loses-wfs-delay.md).  Last marker wins:
        one load pipeline marks the same predicate on more than one db (the
        exec-time db, then the compile pipeline's) and the most recent is the
        live one; only the owning module can mark at all (``-table`` in an
        importing module is refused at load).
        """
        self._tabled.add((functor, arity))
        md = self.module_dict
        if md is not None:
            from clausal.logic.predicate import PredicateMeta  # noqa: PLC0415
            cand = md.get(functor)
            if isinstance(cand, PredicateMeta):
                cand._tabled_home_db = self

    def is_tabled(self, functor: str, arity: int) -> bool:
        """True if the predicate was declared -table."""
        return (functor, arity) in self._tabled

    def mark_shallow(self, functor: str, arity: int) -> None:
        """Mark a predicate as shallow (compile with short-stack mode)."""
        self._shallow.add((functor, arity))

    def is_shallow(self, functor: str, arity: int) -> bool:
        """True if the predicate was declared -shallow."""
        return (functor, arity) in self._shallow

    @property
    def table_store(self) -> dict:
        """The shared table store for all tabled predicates in this database."""
        return self._table_store

    def abolish_table(self, functor: str, arity: int) -> None:
        """Remove all cached answers for (functor, arity).

        Entries are keyed as (functor, arity, variant_key) in _table_store.
        This removes all variant entries for the given predicate.
        """
        to_remove = [k for k in self._table_store
                     if k[0] == functor and k[1] == arity]
        for k in to_remove:
            del self._table_store[k]

    def abolish_all_tables(self) -> None:
        """Remove all cached tabling answers."""
        self._table_store.clear()

    def __repr__(self) -> str:
        parts = ", ".join(f"{f}/{a}" for f, a in sorted(self._clauses))
        return f"Database({{{parts}}})"


# ── Module ─────────────────────────────────────────────────────────────────────


class Module:
    """Runtime module object that serves as the $module value injected by the
    import hook.

    The two call-sites the transformed source uses are:

        $assert_fact(term)               → module.assert_fact(term)
        $define_predicate(pred, module)  → module.define_predicate(pred)
    """

    def __init__(self, name: str, db: Database | None = None,
                 module_dict: dict | None = None) -> None:
        self.name = name
        self.db: Database = db if db is not None else Database(module_dict=module_dict)
        self.module_dict: dict | None = module_dict
        # -constants declared BY this module (not imported ones — see
        # register_module_constant in clausal/logic/constants.py). Backs the
        # module_constant/3 reflection builtin (docs/builtins.md). Keyed by
        # the full `_NAME_`-shaped declaration spelling.
        self.constants: dict[str, Any] = {}
        #: name -> (declared_number, declared_units_term) for constants
        #: declared with ``-constant_number_units``. Kept beside .constants
        #: rather than inside it because it records what the DECLARATION
        #: said, which is not recoverable from the value: a unit that is not
        #: the base of its dimension rescales, so `30 day` is stored as
        #: Quantity(2592000, second) and the 30 is gone. See
        #: constant_number_units/3.
        self.constant_units: dict[str, tuple] = {}

    def assert_fact(self, term: Any) -> None:
        """assertz a fact (clause with no body goals)."""
        self.db.assertz(Clause(head=term, body=[]))

    def define_predicate(self, predicate_node: Any) -> None:
        """assertz one clause from a Predicate node produced by the transformer.

        Flattens the body And-chain into a flat list of goal terms and stores
        the resulting Clause.  The dispatch_fn slot is left None until the
        compiler (steps 4–5) recompiles the predicate.

        Also registers the keyword signature from the head's field names.

        For facts (body is just [True]), ground values in dataclass head fields
        are normalized to Var+Is form so output-mode queries work correctly.
        """
        head = predicate_node.head
        body_goals = _flatten_body(predicate_node.body)
        # Normalize dataclass facts: ground field values → Var + Is body goals.
        if body_goals == [True] and _is_normalizable_fact(head):
            head, body_goals = _normalize_dataclass_fact(head)
        else:
            # Ruled clause: hoist structural head args (Compound / Call(LoadName)
            # / functor-instance) into prepended Unify goals so an unbound caller
            # binds in output mode — the same Var+Unify shape facts use. Atomic
            # head literals keep the match-guard path.
            head, body_goals = _normalize_structural_head_args(head, body_goals)
        self.db.assertz(Clause(
            head=head,
            body=body_goals,
            position=getattr(predicate_node, "position", None),
        ))
        functor, arity = head_key(head)
        param_names = _extract_param_names(head)
        if param_names is not None:
            self.db.register_signature(functor, arity, param_names)

    def solve(self, goal: Any, trail=None):
        """Solve a goal against this module's database.

        Delegates to clausal.logic.solve.solve.  Returns an iterator that
        yields the Trail after each solution (bindings live on the trail).
        """
        from clausal.logic.solve import solve as _solve
        return _solve(goal, self, trail=trail)

    def __repr__(self) -> str:
        return f"Module({self.name!r}, {self.db!r})"


# ── Fact normalization ────────────────────────────────────────────────────────


def _is_ground_value(val: Any) -> bool:
    """Return True if val contains no Vars and no structural patterns (StarUnpack).

    Ground values (scalars, empty lists, ground nested lists) are eligible for
    Var+Is normalization in fact heads.  Lists containing Vars or StarUnpack
    elements, and standalone Vars, are structural and must NOT be normalized.
    """
    from clausal.logic.variables import is_var
    if is_var(val):
        return False
    if isinstance(val, StarUnpack):
        return False
    if isinstance(val, list):
        return all(_is_ground_value(e) for e in val)
    return True


def _is_normalizable_fact(head: Any) -> bool:
    """True if head is a user term -- a CELL since the P2 head flip, or a
    term instance before it -- with at least one ground argument that needs
    normalization.

    The cell arm is here so the flip does not change WHEN a fact is
    normalized: a ground fact argument becomes a fresh Var plus a body
    ``Unify`` under both representations.  Without it a cell fact fell
    through to the structural hoist, which leaves atomics on the match-guard
    path -- a different lowering for the same program.
    """
    if compound_cell_shape(head)[0]:
        return any(_is_ground_value(a) for a in cell_args(head))
    if not is_term_instance(head):
        return False
    if isinstance(head, (Compound, Call, KWTerm)):
        return False
    return any(
        _is_ground_value(getattr(head, name))
        for name in term_field_names(head)
    )


def _normalize_dataclass_fact(head: Any) -> tuple[Any, list]:
    """Replace ground field values in a dataclass fact head with Vars + Unify goals.

    Returns (new_head, body_goals) where each ground field has been replaced by
    a fresh Var and a corresponding Unify(var, value) goal in the body.

    Lists containing Vars or StarUnpack elements are structural patterns and are
    left in place (handled by the compiler's list-guard machinery).
    """
    from clausal.logic.variables import Var
    from clausal.terms import Unify

    body: list = []

    # P2 (2026-09-19): a head is the functor-first CELL; the instance arm below
    # is the pre-flip shape and goes with the class in P4.  Both do the same
    # thing positionally -- a ground argument becomes a fresh Var plus a body
    # Unify -- so the only difference is how the head is taken apart and put
    # back together.
    is_cell, functor = compound_cell_shape(head)
    if is_cell:
        args = list(cell_args(head))
        changed = False
        for i, val in enumerate(args):
            if _is_ground_value(val):
                v = Var()
                args[i] = v
                body.append(Unify(left=v, right=val))
                changed = True
        if not changed:
            return head, [True]
        return make_cell(functor, *args), body

    replacements: dict[str, Any] = {}
    fields = term_field_names(head)
    for name in fields:
        val = getattr(head, name)
        if _is_ground_value(val):
            v = Var()
            replacements[name] = v
            body.append(Unify(left=v, right=val))
    if not replacements:
        return head, [True]
    # Build a new head with Vars replacing ground values.
    new_kwargs = {
        name: replacements.get(name, getattr(head, name))
        for name in fields
    }
    # W4a: the tail of this function is the DATACLASS path (its gate,
    # ``_is_normalizable_fact``, excludes cells and the Compound/Call/KWTerm
    # shapes), so the rebuild is the class's own
    # constructor.  It used to be ``_clausal_head``, for the predicate
    # INSTANCE that path also carried until W4a retired it.
    new_head = type(head)(**new_kwargs)
    return new_head, body


def _is_structural_head_value(val: Any) -> bool:
    """True if val is a structural term that head_to_match_pattern would compile
    to a value-rejecting MatchClass or sequence pattern (Compound /
    Call(LoadName) / functor instance / CELL). Such head args must be hoisted
    into a Var + Unify body goal so an unbound caller binds in output mode.
    Atomics, Vars, StarUnpack and lists are handled by other compiler paths and
    must NOT be normalized here."""
    from clausal.logic.variables import is_var
    if is_var(val) or isinstance(val, (StarUnpack, list, KWTerm)):
        return False
    if isinstance(val, Compound):
        return True
    if isinstance(val, Call):
        return isinstance(val.func, LoadName)
    if is_term_instance(val):
        return True
    # A live CELL — ``("point", 1, X)``.  P3-2 Task 3: post-flip this is the
    # compiled representation of the very same term ``Compound`` is on this
    # list for, and it needs hoisting for the identical reason.  A cell
    # containing a Var is the sharp case: its inner Var has to couple to the
    # clause's body, and a head pattern captures into per-call locals while
    # the hoisted ``Unify`` also freshens it (``_preallocate_body_vars``) —
    # whereas leaving it in the head unhoisted costs output-mode binding, so
    # an unbound caller gets no answer where the pre-flip class program bound
    # one.  Slot 0 is read RAW (no deref), matching the head-pattern branch
    # this decision feeds; ``type(...) is tuple`` matches ``cells.is_cell``'s
    # own domain, so a tuple SUBCLASS stays opaque data (Task 2C's exact-type
    # ruling), and a plain data tuple ``(1, 2)`` is not structural either.
    # ``type(val[0]) is str`` (not ``isinstance``) matches ``cells.
    # _valid_functor_slot``'s own exact-type convention (a ``str`` subclass
    # is deliberately excluded there too — see that function's docstring).
    # THE FLIP (2026-09-06-atoms-as-cells-strings): an ARITY-0 cell is an
    # ATOM — an atomic term — and is deliberately excluded.  It has no
    # arguments, so there is no inner Var to couple to the body and nothing
    # to destructure; ``head_to_match_pattern`` compiles it to the same
    # capture + ``unify`` guard it gives a ``str``/``bytes``/atom-class head
    # argument, which already binds an unbound caller in output mode.
    # Hoisting it would be worse than pointless: the head argument would
    # become a fresh Var, so every reader of a stored clause head — clause
    # inspection (``clauses_for``), ``listing/1``, the test harness's
    # description, first-argument indexing — would see a variable where the
    # program wrote an atom.
    if is_chars(val):
        # STAGE 1 (spec 2026-09-18): the chars CARRIER is a string literal --
        # atomic here for the same reasons the arity-0 cell is: nothing to
        # destructure, no inner Var, and ``head_to_match_pattern`` gives it
        # the str literal's capture + ``unify`` guard.  Hoisting it left a
        # Var in every stored ``test("...")`` head, and the test runner then
        # dispatched every test to the first clause.
        return False
    if type(val) is tuple and len(val) > 1 and (
            type(val[0]) is str or val[0] is TUPLE_TAG):
        return True
    # A deferred Python expression (quantity/currency literal `5(m)`,
    # f-string, `++()` escape) in a head arg: nothing on the head-match path
    # evaluates it, so unhoisted it is captured as an opaque literal and the
    # clause guards against the thunk OBJECT — matching nothing. The hoisted
    # body Unify compiles through term_to_ast_expr, which calls the thunk at
    # runtime and unifies its value.
    if isinstance(val, PyThunk):
        return True
    return False


def _contains_structural_head_value(val: Any) -> bool:
    """Recursively True if *val* is, or contains, a structural term that needs
    hoisting (a Compound / Call(LoadName) / functor instance). Used to detect
    structural literals nested inside a head *list* (or compound), e.g. the
    ``item2(S)`` in a head arg ``[item2(S)]`` — whose inner var would otherwise
    stay decoupled from a body goal that binds it."""
    if _is_structural_head_value(val):
        return True
    if isinstance(val, list):
        return any(_contains_structural_head_value(e) for e in val)
    if isinstance(val, Compound):
        return any(_contains_structural_head_value(a) for a in val.args)
    return False


def _normalize_structural_head_args(head: Any, body: list) -> tuple[Any, list]:
    """Hoist structural top-level head args into prepended Unify body goals.

    Mirrors _normalize_dataclass_fact but for structural args only (atomics keep
    the match-guard path). Each structural field is replaced by a fresh Var and a
    Unify(var, value) goal is prepended to body (prepended so destructured inner
    vars are bound before the original body runs). No-op for non-functor-instance
    heads (bare Compound/Call/KWTerm) or heads with no structural fields."""
    from clausal.logic.variables import Var
    from clausal.terms import Unify

    # P2 (2026-09-19): a head is the functor-first CELL.  Same hoist,
    # positionally; the instance arm below goes with the class in P4.
    is_cell, functor = compound_cell_shape(head)
    if is_cell:
        args = list(cell_args(head))
        prepend: list = []
        for i, val in enumerate(args):
            if _is_structural_head_value(val) or (
                    isinstance(val, list) and _contains_structural_head_value(val)):
                v = Var()
                args[i] = v
                prepend.append(Unify(left=v, right=val))
        if not prepend:
            return head, body
        return make_cell(functor, *args), prepend + list(body)

    if not is_term_instance(head) or isinstance(head, (Compound, Call, KWTerm)):
        return head, body
    fields = term_field_names(head)
    replacements: dict[str, Any] = {}
    prepend: list = []
    for name in fields:
        val = getattr(head, name)
        # Hoist a top-level structural arg, OR a list arg that *contains* a
        # structural literal at any depth (its inner var must unify with the
        # clause's shared body var — cons-pattern head matching doesn't couple
        # them in output mode).
        if _is_structural_head_value(val) or (
                isinstance(val, list) and _contains_structural_head_value(val)):
            v = Var()
            replacements[name] = v
            prepend.append(Unify(left=v, right=val))
    if not replacements:
        return head, body
    new_kwargs = term_field_dict(head)
    new_kwargs.update(replacements)
    new_head = type(head)(**new_kwargs)   # W4a: the dataclass constructor
    return new_head, prepend + list(body)


# ── Helpers ────────────────────────────────────────────────────────────────────


def head_key(head: Any) -> tuple[str, int]:
    """Extract (functor_name, arity) from a head term.

    Handles:
    - Compound(functor, args)              → (functor, len(args))
    - Call(func=LoadName(name), args)      → (name, len(args))
    - functor dataclass instance           → (type.__name__, len(fields))
    - cell ``("f", a, b)``                 → ("f", len(cell) - 1)
    """
    if isinstance(head, Compound):
        f = head.functor
        if not isinstance(f, str):
            raise TypeError(
                f"Compound functor must be a str at database level, got {f!r}"
            )
        return f, len(head.args)
    if isinstance(head, Call):
        if isinstance(head.func, LoadName):
            return head.func.name, len(head.args)
        raise TypeError(f"Call head with non-LoadName func: {head.func!r}")
    if isinstance(head, KWTerm):
        return head.functor, len(head)
    if is_term_instance(head):
        return type(head).__name__, len(term_field_names(head))
    # Zero-arity PredicateMeta class in the HEAD channel -- kept deliberately
    # (STAGE 2, spec §4 made the class no TERM: the functor/arity twins answer
    # None for it).  A head names a PREDICATE, and a clause-less DECLARED
    # 0-arity predicate is still its class with no row (P1: declared
    # clause-less = class), so its first assertz'd clause arrives here as
    # that class and must key name/0.
    if is_zero_field_class(head):
        return head.__name__, 0
    # A CELL names its predicate in slot 0 (P3-3 Task 5, R11).  Last, because
    # every branch above is a cheaper and far commoner shape and this one only
    # fires for a tuple.  A ``TUPLE_TAG`` cell and a slot-0-Var tuple are DATA,
    # not a predicate head, and keep the TypeError below -- which is exactly
    # what ``compound_cell_shape`` excludes.
    if type(head) is str:
        return head, 0                 # STAGE 2: an atom head is name/0
    is_cell_head, cell_functor_name = compound_cell_shape(head)
    if is_cell_head:
        return cell_functor_name, len(head) - 1
    raise TypeError(
        f"Cannot extract (functor, arity) from head term: {head!r}\n"
        "Expected Compound, Call(LoadName(...), ...), a functor dataclass "
        "instance, or a cell ('f', a, b)."
        + describe_term_identity_mismatch(head)
    )


def _stored_head_key(head: Any, channel: str) -> tuple[str, int]:
    """``head_key`` for a head on its way INTO the clause store.

    This used to REFUSE a cell head, and the refusal was load-bearing for two
    releases: no lowering path read a cell as a head (``head_match`` and
    ``list_dispatch._get_head_arg`` both wanted a ``Compound`` or a class
    term), so a cell-headed clause compiled to a predicate that answered with
    its arguments UNBOUND -- a silent wrong answer, which is why the door
    raised instead.  The head flip (2026-09-19) made every one of those
    readers take a cell, so there is nothing left to refuse and a head IS a
    cell.

    Kept as a distinct name from ``head_key`` because the QUESTION differs:
    ``head_key`` reads the (functor, arity) of a raw term a caller handed in,
    this reads a head the store is about to keep.  If storing ever needs a
    check again, this is where it goes.
    """
    return head_key(head)


def _extract_param_names(head: Any) -> tuple[str, ...] | None:
    """Extract keyword parameter names from a head term.

    Returns a tuple of field name strings if the head is a user-defined functor
    dataclass instance; None for built-in term types (Compound, Call) and
    non-dataclass values.
    """
    if compound_cell_shape(head)[0]:
        # P2: a cell head carries no field NAMES -- they come from the
        # declaration (``-private([point(x, y)])`` / the -module export list),
        # which the class already records.  The KWTerm arm below was the only
        # other producer and its surface spelling is refused since 2026-09-19.
        return None
    if isinstance(head, KWTerm):
        return tuple(head.keys())
    if not is_term_instance(head):
        return None
    # exclude built-in term types that happen to be dataclasses.
    if isinstance(head, (Compound, Call)):
        return None
    return term_field_names(head)


def _flatten_body(body: Any) -> list:
    """flatten a nested And-chain or TupleLiteral body into a flat goal list.

    And(And(a, b), c)                →  [a, b, c]
    TupleLiteral([a, b, c])          →  [a, b, c]
    A single non-And/non-Tuple term  →  [term]
    None                             →  []
    """
    if body is None:
        return []
    goals: list = []
    stack = [body]
    while stack:
        term = stack.pop()
        if isinstance(term, And):
            # Push right first so left is processed first (preserving order).
            stack.append(term.right)
            stack.append(term.left)
        elif isinstance(term, TupleLiteral):
            # Comma-as-conjunction: (goal1, goal2, ...) in <- bodies.
            # Push in reverse so elements are processed left-to-right.
            for element in reversed(term.elements):
                stack.append(element)
        else:
            goals.append(term)
    return goals


__all__ = [
    "Clause",
    "Database",
    "Module",
    "PredRow",
    "WriteStamp",
    "head_key",
]
