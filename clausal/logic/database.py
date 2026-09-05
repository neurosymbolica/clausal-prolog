"""clausal.logic.database — in-memory predicate clause store.

Components:
    Clause    — one clause (head term + list of body goal terms)
    Database  — maps (functor, arity) → clause list + signatures
    Module    — runtime $module object wrapping a Database
"""

from __future__ import annotations

import dataclasses
from collections import namedtuple
from typing import Any, Callable

from clausal.terms import And, Call, Compound, KWTerm, LoadName, PyThunk
from clausal.pythonic_ast.nodes import TupleLiteral, StarUnpack
from clausal.logic.cells import TUPLE_TAG
from clausal.logic.predicate import (
    PredicateMeta,
    describe_term_identity_mismatch,
    is_term_instance,
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


@dataclasses.dataclass
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

    ``backend``, ``locked``, ``source`` and ``writes`` are new state that
    nothing else reads or writes yet this task; they exist here only because
    later tasks (Task 2 onward) consume this exact field set.
    """

    _db: "Database" = dataclasses.field(repr=False, compare=False)
    _key: "tuple[str, int]" = dataclasses.field(repr=False, compare=False)
    backend: str = "python"
    locked: bool = False
    source: "tuple[str, str] | None" = None
    writes: list = dataclasses.field(default_factory=list)

    @property
    def clauses(self) -> list:
        """Clause list for this predicate — the SAME object as the legacy
        ``Database._clauses[key]`` entry, always re-read live (never a
        captured reference) so it self-heals across a wholesale dict wipe.

        NOTE: merely READING this property lazily vivifies an empty
        ``_clauses[key]`` entry if none exists yet (via ``setdefault``),
        which flips ``Database.is_defined(functor, arity)`` False→True for a
        predicate that otherwise only ever had dispatch/signature/dynamic
        state. This is an intentional, narrow side effect of read access,
        not of ``Database.row()`` itself (which does not touch ``_clauses``
        at all) — Task 2's compile-install path is the real, deliberate
        minting site for clause lists going forward.
        """
        return self._db._clauses.setdefault(self._key, [])

    @property
    def dispatch_fn(self) -> "Callable | None":
        return self._db._dispatch.get(self._key)

    @dispatch_fn.setter
    def dispatch_fn(self, value: "Callable | None") -> None:
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

        This is the ONE invalidation point going forward (enforced by
        convention this task; the Task 3 mutation gate makes it structural).
        """
        self.dispatch_fn = None

    def record_write(self, author: str, kind: str, detail: Any = None) -> None:
        """Append a ``WriteStamp`` to ``writes``, keeping only the last 32.

        Diagnostics, not history — nothing in this task calls this yet
        (Task 3 wires ``Database.mutate`` provenance through it).
        """
        self.writes.append(WriteStamp(author, kind, detail))
        if len(self.writes) > _WRITES_CAP:
            del self.writes[: len(self.writes) - _WRITES_CAP]


# ── Database ───────────────────────────────────────────────────────────────────


class Database:
    """in_-memory store mapping (functor, arity) → clause list."""

    def __init__(self, module_dict: dict | None = None) -> None:
        self._clauses: dict[tuple[str, int], list[Clause]] = {}
        self._signatures: dict[tuple[str, int], tuple | None] = {}
        self._dispatch: dict[tuple[str, int], Callable | None] = {}
        self._lazy_recompile: dict[tuple[str, int], Callable] = {}
        self._dynamic: set[tuple[str, int]] = set()
        self._discontiguous: set[tuple[str, int]] = set()
        self._tabled: set[tuple[str, int]] = set()
        self._shallow: set[tuple[str, int]] = set()
        self._table_store: dict = {}
        self._rows: dict[tuple[str, int], PredRow] = {}
        self.module_dict: dict | None = module_dict

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
        if not known and not create:
            return None
        # NOTE: deliberately does NOT touch ``_clauses`` here (Finding 2) —
        # minting a row from a dispatch/signature/dynamic-only predicate must
        # not flip ``is_defined()`` False→True. Clause-list vivification is
        # deferred to first access of the ``clauses`` property.
        new_row = PredRow(self, key)
        self._rows[key] = new_row
        return new_row

    def _pred_cls_for(self, functor: str) -> Any:
        """Return the unlocked PredicateMeta class for *functor*, or None.

        ``solve()`` (and compiled inter-predicate calls) resolve a predicate
        through its PredicateMeta class — a clause store that runs in parallel
        with ``self._clauses``.  Mutating only the DB store leaves the class
        stale, so the low-level assertz/asserta/retract below must mirror the
        change onto the class.  Locked (static) predicates are skipped so the
        low-level API does not silently bypass the runtime-mutation lock; only
        dynamic predicates — the ones that may legitimately change at runtime —
        are synced.
        """
        md = self.module_dict
        if md is None:
            return None
        from clausal.logic.predicate import PredicateMeta  # noqa: PLC0415
        cand = md.get(functor)
        if isinstance(cand, PredicateMeta) and not cand._locked:
            return cand
        return None

    def assertz(self, clause: Clause) -> None:
        """Add clause at end of its predicate's clause list."""
        functor, arity = head_key(clause.head)
        key = (functor, arity)
        self._clauses.setdefault(key, []).append(clause)
        # Invalidate compiled dispatch so lazy recompile triggers on next use.
        if key in self._dispatch:
            self._dispatch[key] = None
        # Keep the predicate class (which solve() dispatches through) in sync.
        pred_cls = self._pred_cls_for(functor)
        if pred_cls is not None:
            pred_cls._clauses.append(clause)
            pred_cls._dispatch_fn = None
        # Auto-invalidate tabled answers when a tabled predicate changes.
        if key in self._tabled:
            self.abolish_table(functor, arity)

    def asserta(self, clause: Clause) -> None:
        """Add clause at front of its predicate's clause list."""
        functor, arity = head_key(clause.head)
        key = (functor, arity)
        if key not in self._clauses:
            self._clauses[key] = []
        self._clauses[key].insert(0, clause)
        # Invalidate compiled dispatch so lazy recompile triggers on next use.
        if key in self._dispatch:
            self._dispatch[key] = None
        # Keep the predicate class (which solve() dispatches through) in sync.
        pred_cls = self._pred_cls_for(functor)
        if pred_cls is not None:
            pred_cls._clauses.insert(0, clause)
            pred_cls._dispatch_fn = None
        # Auto-invalidate tabled answers when a tabled predicate changes.
        if key in self._tabled:
            self.abolish_table(functor, arity)

    def retract(self, head: Any) -> bool:
        """Remove first clause whose head structurally equals head.

        Returns True if a clause was removed.
        """
        functor, arity = head_key(head)
        key = (functor, arity)
        if key not in self._clauses:
            return False
        for i, clause in enumerate(self._clauses[key]):
            if clause.head == head:
                del self._clauses[key][i]
                # Invalidate compiled dispatch.
                if key in self._dispatch:
                    self._dispatch[key] = None
                # Keep the predicate class (which solve() dispatches through) in
                # sync: remove the same clause object by identity.
                pred_cls = self._pred_cls_for(functor)
                if pred_cls is not None:
                    for j, pcls_clause in enumerate(pred_cls._clauses):
                        if pcls_clause is clause:
                            del pred_cls._clauses[j]
                            pred_cls._dispatch_fn = None
                            break
                # Auto-invalidate tabled answers when a tabled predicate changes.
                if key in self._tabled:
                    self.abolish_table(functor, arity)
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
        return self._signatures.get((functor, arity))

    def set_dispatch(
        self,
        functor: str,
        arity: int,
        fn: Callable,
        lazy_recompile: Callable | None = None,
    ) -> None:
        """Store the compiled dispatch function for (functor, arity)."""
        key = (functor, arity)
        self._dispatch[key] = fn
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
    """True if head is a term instance (not a built-in term type) with
    at least one ground field value that needs normalization."""
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

    replacements: dict[str, Any] = {}
    body: list = []
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
    if type(val) is tuple and val and (
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
    new_head = type(head)(**new_kwargs)
    return new_head, prepend + list(body)


# ── Helpers ────────────────────────────────────────────────────────────────────


def head_key(head: Any) -> tuple[str, int]:
    """Extract (functor_name, arity) from a head term.

    Handles:
    - Compound(functor, args)              → (functor, len(args))
    - Call(func=LoadName(name), args)      → (name, len(args))
    - functor dataclass instance           → (type.__name__, len(fields))
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
    # Zero-arity PredicateMeta class: the class IS the atom
    if isinstance(head, PredicateMeta) and not head._fields:
        return head.__name__, 0
    raise TypeError(
        f"Cannot extract (functor, arity) from head term: {head!r}\n"
        "Expected Compound, Call(LoadName(...), ...), or a functor dataclass instance."
        + describe_term_identity_mismatch(head)
    )


def _extract_param_names(head: Any) -> tuple[str, ...] | None:
    """Extract keyword parameter names from a head term.

    Returns a tuple of field name strings if the head is a user-defined functor
    dataclass instance; None for built-in term types (Compound, Call) and
    non-dataclass values.
    """
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
