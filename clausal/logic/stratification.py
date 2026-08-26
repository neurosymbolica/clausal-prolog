"""clausal.logic.stratification — compile-time negation-cycle analysis.

A program whose predicate dependency graph has a cycle through ``not`` is
**non-stratified**: plain negation-as-failure has no defined answer for it —
untabled it loops (``RecursionError``), and only ``-table`` (well-founded
semantics) gives the cycle a meaning. Nothing used to say so at authoring
time; the author found out from a stack overflow naming no predicate
(todo/no-stratification-analysis.md).

This analysis REPORTS, never refuses:

- a negation cycle whose members are all ``-table``d is a legitimate WFS
  program (defeasible rules — "this applies unless that disapplies it" —
  are a wanted thing to express) and produces **no** diagnostic;
- a negation cycle with an untabled member gets a warning naming the cycle,
  which negated edges close it, and the ``-table`` remedy;
- stratified programs — negation with no cycle through it — are silent.

The graph is conservative in the lint direction: edges are recorded only for
syntactic goal-position calls (``Call``/bare-name goals, their negations, and
``if_`` tests — whose *else* branch is guarded by the test's failure, hence
both a positive and a negative edge). Goals reached through meta-calls
(``findall``, ``call/1``, …) are not traced, so a cycle hidden behind one is
missed rather than a stratified program flagged.
"""

from __future__ import annotations

import warnings

from clausal.pythonic_ast import nodes


class ClausalStratificationWarning(UserWarning):
    """A predicate dependency cycle passes through negation and at least one
    member is not tabled — NAF may loop or answer wrongly there."""


# ── Dependency graph construction ─────────────────────────────────────────


def _goal_call_key(goal):
    """(functor, arity) for a goal-position call, else None."""
    if isinstance(goal, nodes.Call) and isinstance(goal.func, nodes.LoadName):
        return (goal.func.name, len(goal.args) + len(goal.kwargs))
    if isinstance(goal, nodes.LoadName):
        return (goal.name, 0)  # bare zero-arity atom goal
    return None


def _walk_goal(goal, negative, add_edge):
    """Record dependency edges for one body goal.

    ``negative`` is sticky downward: every call under a ``not`` is a
    negative dependency. Call ARGUMENTS are terms, not goals — they are
    deliberately not walked (a data constructor sharing a predicate's name
    must not fabricate an edge).
    """
    key = _goal_call_key(goal)
    if key is not None:
        add_edge(key, negative)
        return
    if isinstance(goal, nodes.Not):
        _walk_goal(goal.operand, True, add_edge)
        return
    if isinstance(goal, nodes.BoolOp):  # And / Or — binary left/right
        _walk_goal(goal.left, negative, add_edge)
        _walk_goal(goal.right, negative, add_edge)
        return
    if isinstance(goal, nodes.IfExpr):
        # The else branch runs under the test's FAILURE — a negative
        # dependency on the test — while the then branch needs its success.
        _walk_goal(goal.test, negative, add_edge)
        _walk_goal(goal.test, True, add_edge)
        _walk_goal(goal.body, negative, add_edge)
        _walk_goal(goal.orelse, negative, add_edge)
        return
    # Comparisons, unifications, arithmetic, cuts, … carry no
    # predicate-to-predicate dependency.


def build_dependency_graph(db) -> dict:
    """``{(functor, arity): [((functor, arity), is_negative), ...]}`` over
    the predicates defined in *db*, from their clause bodies."""
    defined = set(db._clauses.keys())
    graph = {key: [] for key in defined}
    for key in defined:
        edges = graph[key]

        def add_edge(target, negative, edges=edges):
            if target in defined:
                edges.append((target, negative))

        for clause in db._clauses[key]:
            for goal in clause.body:
                _walk_goal(goal, False, add_edge)
    return graph


# ── SCC analysis ──────────────────────────────────────────────────────────


def _strongly_connected_components(graph):
    """Iterative Tarjan over ``{node: [(target, neg), ...]}``."""
    index_of, low, on_stack = {}, {}, set()
    stack, sccs = [], []
    counter = [0]
    for root in graph:
        if root in index_of:
            continue
        work = [(root, iter(graph[root]))]
        index_of[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for target, _neg in it:
                if target not in index_of:
                    index_of[target] = low[target] = counter[0]
                    counter[0] += 1
                    stack.append(target)
                    on_stack.add(target)
                    work.append((target, iter(graph[target])))
                    advanced = True
                    break
                if target in on_stack:
                    low[node] = min(low[node], index_of[target])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                scc = set()
                while True:
                    n = stack.pop()
                    on_stack.discard(n)
                    scc.add(n)
                    if n == node:
                        break
                sccs.append(scc)
    return sccs


def _cycle_path(graph, members, neg_edge):
    """A concrete cycle through ``neg_edge = (u, v)`` inside ``members``:
    ``[(node, edge_to_next_is_negative), ...]`` starting at u, implicitly
    closing back to u after the last element."""
    u, v = neg_edge
    if u == v:
        return [(u, True)]
    # BFS v → u inside the SCC.
    prev = {v: None}
    queue = [v]
    while queue:
        node = queue.pop(0)
        if node == u:
            break
        for target, _neg in graph[node]:
            if target in members and target not in prev:
                prev[target] = node
                queue.append(target)
    # Reconstruct v .. u, then prefix u -not-> v.
    chain = [u]
    while chain[-1] != v:
        chain.append(prev[chain[-1]])
    chain.reverse()  # v, ..., u
    path = [(u, True)]
    for i, node in enumerate(chain[:-1]):
        nxt = chain[i + 1]
        neg = any(t == nxt and n for t, n in graph[node])
        path.append((node, neg))
    return path


def find_negation_cycles(graph):
    """SCCs containing a negative internal edge.

    Returns ``[(member_set, path), ...]`` where ``path`` is a concrete cycle
    as produced by :func:`_cycle_path`.
    """
    out = []
    for scc in _strongly_connected_components(graph):
        neg_edge = None
        for node in scc:
            for target, neg in graph[node]:
                if neg and target in scc and (len(scc) > 1 or target == node):
                    neg_edge = (node, target)
                    break
            if neg_edge:
                break
        if neg_edge is None:
            continue
        # A single node is an SCC even without a self-edge; only report it
        # when the negative edge is a genuine self-loop (checked above).
        out.append((scc, _cycle_path(graph, scc, neg_edge)))
    return out


# ── Reporting ─────────────────────────────────────────────────────────────


def _fmt_pred(key):
    return f"{key[0]}/{key[1]}"


def _fmt_cycle(path):
    parts = []
    first = _fmt_pred(path[0][0])
    for i, (node, neg) in enumerate(path):
        if i == 0:
            parts.append(_fmt_pred(node))
        nxt = _fmt_pred(path[i + 1][0]) if i + 1 < len(path) else first
        parts.append(f"not {nxt}" if neg else nxt)
    return " -> ".join(parts)


def check_stratification(db, module_name="<module>") -> None:
    """Warn (never refuse) about negation cycles with untabled members.

    A fully ``-table``d cycle is well-founded — a legitimate program — and
    stays silent; every warning would otherwise be noise on exactly the
    programs WFS exists for.
    """
    graph = build_dependency_graph(db)
    for members, path in find_negation_cycles(graph):
        untabled = sorted(k for k in members if not db.is_tabled(*k))
        if not untabled:
            continue
        cycle = _fmt_cycle(path)
        remedy = " ".join(f"-table({_fmt_pred(k)})" for k in sorted(members))
        warnings.warn(
            f"{module_name}: non-stratified: {cycle} — a cycle through "
            f"negation with untabled member(s) "
            f"{', '.join(_fmt_pred(k) for k in untabled)}; plain NAF may "
            f"loop (RecursionError) or answer wrongly here. Add {remedy} "
            f"to give the cycle well-founded semantics, or break it.",
            ClausalStratificationWarning,
            stacklevel=2,
        )


__all__ = [
    "ClausalStratificationWarning",
    "build_dependency_graph",
    "find_negation_cycles",
    "check_stratification",
]
