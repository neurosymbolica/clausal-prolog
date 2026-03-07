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

from clausal.terms import And, Call, Compound, LoadName


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

        Raises NotImplementedError if the predicate has not been compiled yet.
        The compiler is wired in steps 4–5.
        """
        if self.dispatch_fn is None:
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
        """Return the PredicateTable for (functor, arity), or None."""
        return self._tables.get((functor, arity))

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
        """
        head = predicate_node.head
        body_goals = _flatten_body(predicate_node.body)
        self.db.assertz(Clause(head=head, body=body_goals))

    def solve(self, goal: Any):
        """Solve a goal against this module's database.

        Stub — implemented in step 7 (clausal.logic.solve).
        """
        raise NotImplementedError("Module.solve is implemented in step 7.")

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
    if dataclasses.is_dataclass(head) and not isinstance(head, type):
        return type(head).__name__, len(dataclasses.fields(head))
    raise TypeError(
        f"Cannot extract (functor, arity) from head term: {head!r}\n"
        "Expected Compound, Call(LoadName(...), ...), or a functor dataclass instance."
    )


def _flatten_body(body: Any) -> list:
    """Flatten a nested And-chain body term into a flat list of goal terms.

    And(And(a, b), c)  →  [a, b, c]
    A single non-And term  →  [term]
    None  →  []
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
