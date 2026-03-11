"""clausal.logic.database — in-memory predicate clause store.

Components:
    Clause          — one clause (head term + list of body goal terms)
    PredicateTable  — clause list + dispatch slot for one (functor, arity)
    Database        — maps (functor, arity) → PredicateTable
    Module          — runtime $module object wrapping a Database
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from clausal.terms import And, Call, Compound, KWTerm, LoadName
from clausal.pythonic_ast.nodes import TupleLiteral


# ── Clause ─────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Clause:
    """One predicate clause: a head term and a list of body goal terms.

    An empty body list means a fact.
    """

    head: Any
    body: list  # list[term]

    def is_fact(self) -> bool:
        return not self.body


# ── PredicateTable ─────────────────────────────────────────────────────────────


class PredicateTable:
    """Holds all clauses for one (functor, arity) pair plus a dispatch slot."""

    def __init__(self, functor: str, arity: int) -> None:
        self.functor = functor
        self.arity = arity
        self._clauses: list[Clause] = []
        self.dispatch_fn: Callable | None = None
        self.dispatch_index: dict = {}  # reserved for first-argument indexing
        self.signature: tuple[str, ...] | None = None
        # Lazy recompile: set by the compiler after first compilation.
        # When dispatch_fn is cleared by assertz/asserta/retract, the next
        # get_dispatch() call invokes this to recompile from the current clauses.
        self._lazy_recompile: Callable | None = None

    def assertz(self, clause: Clause) -> None:
        """Append clause at end; invalidate the compiled dispatch function."""
        self._clauses.append(clause)
        self.dispatch_fn = None

    def asserta(self, clause: Clause) -> None:
        """Prepend clause at front; invalidate the compiled dispatch function."""
        self._clauses.insert(0, clause)
        self.dispatch_fn = None

    def retract(self, head: Any) -> bool:
        """Remove the first clause whose head equals head (structural equality).

        Returns True if a clause was removed, False if none matched.
        Note: step-8 builtins add unification-based retract on top of this.
        """
        for i, clause in enumerate(self._clauses):
            if clause.head == head:
                del self._clauses[i]
                self.dispatch_fn = None
                return True
        return False

    @property
    def clauses(self) -> list[Clause]:
        """Snapshot of the current clause list."""
        return list(self._clauses)

    def get_dispatch(self) -> Callable:
        """Return the compiled dispatch function.

        If dispatch_fn was cleared by a dynamic clause addition and a lazy
        recompile callback is registered, recompiles on demand before returning.

        Raises NotImplementedError if neither dispatch_fn nor _lazy_recompile
        is available (predicate has never been compiled).
        """
        if self.dispatch_fn is None:
            if self._lazy_recompile is not None:
                self.dispatch_fn = self._lazy_recompile()
            else:
                raise NotImplementedError(
                    f"Predicate {self.functor}/{self.arity} has no compiled dispatch "
                    "function. The compiler (steps 4–5) must be run first."
                )
        return self.dispatch_fn

    def __repr__(self) -> str:
        compiled = "compiled" if self.dispatch_fn is not None else "uncompiled"
        return (
            f"PredicateTable({self.functor!r}/{self.arity}, "
            f"{len(self._clauses)} clause(s), {compiled})"
        )


# ── Database ───────────────────────────────────────────────────────────────────


class Database:
    """In-memory store mapping (functor, arity) → PredicateTable."""

    def __init__(self) -> None:
        self._tables: dict[tuple[str, int], PredicateTable] = {}

    def _table(self, functor: str, arity: int) -> PredicateTable:
        key = (functor, arity)
        if key not in self._tables:
            self._tables[key] = PredicateTable(functor, arity)
        return self._tables[key]

    def assertz(self, clause: Clause) -> None:
        """Add clause at end of its predicate's clause list."""
        functor, arity = head_key(clause.head)
        self._table(functor, arity).assertz(clause)

    def asserta(self, clause: Clause) -> None:
        """Add clause at front of its predicate's clause list."""
        functor, arity = head_key(clause.head)
        self._table(functor, arity).asserta(clause)

    def retract(self, head: Any) -> bool:
        """Remove first clause whose head structurally equals head.

        Returns True if a clause was removed.
        """
        functor, arity = head_key(head)
        key = (functor, arity)
        if key not in self._tables:
            return False
        return self._tables[key].retract(head)

    def clauses_for(self, functor: str, arity: int) -> list[Clause]:
        """Return a snapshot of clauses for (functor, arity), or [] if undefined."""
        key = (functor, arity)
        if key not in self._tables:
            return []
        return self._tables[key].clauses

    def is_defined(self, functor: str, arity: int) -> bool:
        """True if any clause has been asserted for (functor, arity)."""
        return (functor, arity) in self._tables

    def table_for(self, functor: str, arity: int) -> PredicateTable | None:
        """Return the PredicateTable for (functor, arity).

        Checks the local table first.  If not found, falls back to the
        builtin/stdlib registry (clausal.logic.builtins).  Builtin tables are
        cached on first access so subsequent lookups are O(1).
        """
        local = self._tables.get((functor, arity))
        if local is not None:
            return local
        # Lazy builtin/stdlib lookup — avoids circular imports at module level.
        from clausal.logic.builtins import get_builtin_dispatch  # noqa: PLC0415
        dispatch_fn = get_builtin_dispatch(functor, arity, self)
        if dispatch_fn is not None:
            table = PredicateTable(functor, arity)
            table.dispatch_fn = dispatch_fn
            self._tables[(functor, arity)] = table  # cache
            return table
        return None

    def register_signature(
        self, functor: str, arity: int, param_names: tuple[str, ...]
    ) -> None:
        """Register the keyword parameter names for a predicate.

        If a signature is already registered and matches, this is a no-op.
        If it conflicts, emit a warning.
        """
        import warnings

        table = self._table(functor, arity)
        if table.signature is None:
            table.signature = param_names
        elif table.signature != param_names:
            warnings.warn(
                f"Signature conflict for {functor}/{arity}: "
                f"registered {table.signature}, got {param_names}"
            )

    def signature_for(self, functor: str, arity: int) -> tuple[str, ...] | None:
        """Return the registered keyword param names, or None."""
        table = self._tables.get((functor, arity))
        return table.signature if table else None

    def __repr__(self) -> str:
        parts = ", ".join(f"{f}/{a}" for f, a in sorted(self._tables))
        return f"Database({{{parts}}})"


# ── Module ─────────────────────────────────────────────────────────────────────


class Module:
    """Runtime module object that serves as the $module value injected by the
    import hook.

    The two call-sites the transformed source uses are:

        $assert_fact(term)               → module.assert_fact(term)
        $define_predicate(pred, module)  → module.define_predicate(pred)
    """

    def __init__(self, name: str, db: Database | None = None) -> None:
        self.name = name
        self.db: Database = db if db is not None else Database()

    def assert_fact(self, term: Any) -> None:
        """Assert a fact (clause with no body goals)."""
        self.db.assertz(Clause(head=term, body=[]))

    def define_predicate(self, predicate_node: Any) -> None:
        """Assert one clause from a Predicate node produced by the transformer.

        Flattens the body And-chain into a flat list of goal terms and stores
        the resulting Clause.  The dispatch_fn slot is left None until the
        compiler (steps 4–5) recompiles the predicate.

        Also registers the keyword signature from the head's field names.
        """
        head = predicate_node.head
        body_goals = _flatten_body(predicate_node.body)
        self.db.assertz(Clause(head=head, body=body_goals))
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


# ── Helpers ────────────────────────────────────────────────────────────────────


def head_key(head: Any) -> tuple[str, int]:
    """Extract (functor_name, arity) from a head term.

    Handles:
    - Compound(functor, args)              → (functor, len(args))
    - Call(func=LoadName(name), args)      → (name, len(args))
    - Functor dataclass instance           → (type.__name__, len(fields))
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
    if dataclasses.is_dataclass(head) and not isinstance(head, type):
        return type(head).__name__, len(dataclasses.fields(head))
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
    if not dataclasses.is_dataclass(head) or isinstance(head, type):
        return None
    # Exclude built-in term types that happen to be dataclasses.
    if isinstance(head, (Compound, Call)):
        return None
    return tuple(f.name for f in dataclasses.fields(head))


def _flatten_body(body: Any) -> list:
    """Flatten a nested And-chain or TupleLiteral body into a flat goal list.

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
    "PredicateTable",
    "Database",
    "Module",
    "head_key",
]
