"""clausal.logic.database — in-memory predicate clause store.

Components:
    Clause    — one clause (head term + list of body goal terms)
    Database  — maps (functor, arity) → clause list + signatures
    Module    — runtime $module object wrapping a Database
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from clausal.terms import And, Call, Compound, KWTerm, LoadName
from clausal.pythonic_ast.nodes import TupleLiteral, StarUnpack
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names


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
        self.module_dict: dict | None = module_dict

    def assertz(self, clause: Clause) -> None:
        """Add clause at end of its predicate's clause list."""
        functor, arity = head_key(clause.head)
        key = (functor, arity)
        self._clauses.setdefault(key, []).append(clause)
        # Invalidate compiled dispatch so lazy recompile triggers on next use.
        if key in self._dispatch:
            self._dispatch[key] = None
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
        """Mark a predicate as tabled (memoised via SLG resolution)."""
        self._tabled.add((functor, arity))

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
    to a value-rejecting MatchClass (Compound / Call(LoadName) / functor
    instance). Such head args must be hoisted into a Var + Unify body goal so an
    unbound caller binds in output mode. Atomics, Vars, StarUnpack and lists are
    handled by other compiler paths and must NOT be normalized here."""
    from clausal.logic.variables import is_var
    if is_var(val) or isinstance(val, (StarUnpack, list, KWTerm)):
        return False
    if isinstance(val, Compound):
        return True
    if isinstance(val, Call):
        return isinstance(val.func, LoadName)
    if is_term_instance(val):
        return True
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
        if _is_structural_head_value(val):
            v = Var()
            replacements[name] = v
            prepend.append(Unify(left=v, right=val))
    if not replacements:
        return head, body
    new_kwargs = {
        name: replacements.get(name, getattr(head, name)) for name in fields
    }
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
    "head_key",
]
