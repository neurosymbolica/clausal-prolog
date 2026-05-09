"""Stratification of `-bottom_up` predicates.

The engine evaluates predicates one SCC at a time, in topological order over
the rule-dependency graph. Each SCC is iterated to fixpoint with semi-naive
evaluation; lower SCCs see the upper SCCs as completed extensional relations.

Cyclic negation is rejected: if an SCC contains an edge through ``Not(...)``,
the program is not stratifiable and the engine refuses to run it.
"""

from __future__ import annotations

from typing import Iterable

from clausal.logic.database import Clause, head_key
from clausal.pythonic_ast.nodes import Call, LoadName, Not, And, TupleLiteral


# ── Body walker ─────────────────────────────────────────────────────────


def _walk_body_atoms(body, *, in_negation: bool = False):
    """Yield (functor, arity, in_negation) for each atom in `body`.

    Conjunctions (And, TupleLiteral) are flattened. Predicate calls are
    reported as (functor, arity, in_negation). Other goal forms — Is,
    comparisons, etc. — are skipped here; the dependency graph is over
    *predicate* atoms only.
    """
    if body is None:
        return
    stack = [(body, in_negation)]
    while stack:
        node, neg = stack.pop()
        if isinstance(node, list):
            for item in reversed(node):
                stack.append((item, neg))
            continue
        if isinstance(node, And):
            stack.append((node.right, neg))
            stack.append((node.left, neg))
            continue
        if isinstance(node, TupleLiteral):
            for el in reversed(node.elements):
                stack.append((el, neg))
            continue
        if isinstance(node, Not):
            stack.append((node.operand, True))
            continue
        if isinstance(node, Call) and isinstance(node.func, LoadName):
            yield (node.func.name, len(node.args), neg)
            continue
        # Ignore other node kinds (Is, comparisons, etc.) — they don't
        # contribute predicate-dependency edges.


# ── Tarjan SCC ──────────────────────────────────────────────────────────


def _tarjan(nodes: list, successors: dict) -> list[list]:
    """Return SCCs in reverse-topological order (leaves first).

    Uses Tarjan's iterative algorithm.
    """
    index_of: dict = {}
    lowlink: dict = {}
    on_stack: set = set()
    stack: list = []
    sccs: list[list] = []
    counter = [0]

    def strongconnect(start):
        # Iterative DFS using an explicit work stack.
        work = [(start, iter(successors.get(start, ())))]
        index_of[start] = counter[0]
        lowlink[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack.add(start)

        while work:
            v, it = work[-1]
            for w in it:
                if w not in index_of:
                    index_of[w] = counter[0]
                    lowlink[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(successors.get(w, ()))))
                    break
                if w in on_stack:
                    lowlink[v] = min(lowlink[v], index_of[w])
            else:
                # iterator exhausted — pop frame
                if lowlink[v] == index_of[v]:
                    component = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.append(w)
                        if w == v:
                            break
                    sccs.append(component)
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])

    for n in nodes:
        if n not in index_of:
            strongconnect(n)

    return sccs


# ── Public API ──────────────────────────────────────────────────────────


def stratify(predicates_with_clauses: dict) -> list[list]:
    """Compute SCCs of `-bottom_up` predicates in topological order.

    Parameters
    ----------
    predicates_with_clauses : dict
        Mapping ``(functor_name, arity) -> list[Clause]``.

    Returns
    -------
    list[list[(functor, arity)]]
        SCCs in *forward* topological order (dependencies first, dependents
        last). Each SCC is a group of mutually-recursive predicates that
        must be evaluated together.

    Raises
    ------
    StratificationError
        If any SCC contains a negation edge — the program is not
        stratifiable.
    """
    nodes = list(predicates_with_clauses.keys())
    node_set = set(nodes)

    # Build edge maps: positive (any call) and negative (call inside Not).
    successors: dict[tuple, set] = {n: set() for n in nodes}
    neg_edges: set[tuple[tuple, tuple]] = set()

    for key, clauses in predicates_with_clauses.items():
        for clause in clauses:
            for callee_name, callee_arity, in_neg in _walk_body_atoms(clause.body):
                callee = (callee_name, callee_arity)
                if callee not in node_set:
                    # Calls into non-bottom_up predicates (pure callees) do
                    # not contribute to the bottom_up dependency graph.
                    continue
                successors[key].add(callee)
                if in_neg:
                    neg_edges.add((key, callee))

    sccs_reverse = _tarjan(nodes, successors)
    sccs = list(sccs_reverse)  # Tarjan emits leaves-first; we want roots-first
    # _tarjan returns leaves-first (i.e. SCCs whose successors come earlier).
    # That matches "forward topological order" from the perspective of
    # evaluation: evaluate dependencies before dependents.
    # (Verify: a node v whose only outgoing edge is to w is yielded *after* w.)

    # Detect cyclic negation: an SCC containing a negation edge between
    # members is not stratifiable.
    for component in sccs:
        if len(component) == 1 and not (component[0],) in successors.get(component[0], set()):
            # singleton with no self-loop — no internal cycle to worry about
            self_loops = (component[0], component[0]) in neg_edges
            if not self_loops:
                continue
        members = set(component)
        bad = [
            (a, b) for (a, b) in neg_edges
            if a in members and b in members
        ]
        if bad:
            raise StratificationError(
                f"Cyclic negation in mutually-recursive SCC {sorted(component)}: "
                f"negation edges {bad}. The program is not stratifiable. "
                "See docs/purity.md and the stratified-negation requirement "
                "in implementation_plans/PROVENANCE_SEMIRINGS.md."
            )

    return sccs


class StratificationError(Exception):
    """Program contains cyclic negation; not stratifiable."""


def predicate_keys_from_clauses(clauses: Iterable[Clause]) -> set[tuple[str, int]]:
    """Helper: extract the set of (functor, arity) heads from a clause list."""
    out: set[tuple[str, int]] = set()
    for clause in clauses:
        out.add(head_key(clause.head))
    return out


__all__ = [
    "stratify",
    "StratificationError",
    "predicate_keys_from_clauses",
]
