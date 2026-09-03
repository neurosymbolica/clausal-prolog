"""toklex annotation layer: turns a compiled DFA into a runnable ``Lexer``.

Consumes the ``Spec``/``DFA``/``Partition`` produced by earlier tasks
(``spec.py``, ``automaton.py``) and adds everything the runtime driver
(Task 6) needs to actually scan text: per-state *extend* sets (which
symbols can still lead somewhere live), a *follow* map for tokens with a
``followed_by`` constraint, a proof that the DFA's backup (the number of
already-consumed characters a maximal-munch scanner may need to "un-read"
past the last accepting state before it gets stuck) is bounded wherever
that is provable -- and, where it genuinely is not (design ISO tension:
quote-doubling and an escape's optional trailing terminator both create
real, unavoidable same-position multi-length ambiguity for a
maximal-munch DFA), a *commit region* the driver treats specially instead
of raising at compile time -- copies of the nested-comment open/close
DFAs, and a Prolog-readable term dump for cross-language interchange.

``annotate(spec)`` is the one-call compiler front door: it orchestrates
``build_partition`` -> ``compile_spec`` -> the annotation passes below.
"""

from __future__ import annotations

from dataclasses import dataclass

from clausal.tools.toklex.automaton import DFA, build_partition, compile_expr, compile_spec
from clausal.tools.toklex.charset import Partition
from clausal.tools.toklex.spec import Spec, SpecError


class UnboundedBackupError(SpecError):
    """Historically raised when the DFA's "pending" graph (non-accepting
    states reachable from some accepting state without crossing another
    accepting state) contained a cycle, meaning backup was not bounded by
    a constant. As of the Task 8 fix round, ``annotate()`` no longer
    raises this: such cycle states are instead identified precisely
    (``Lexer.commit``, see below) and handled at the driver level
    (``driver._resolve``'s commit-region branch) rather than rejected at
    compile time -- a cycle in the pending graph is now a *derived*,
    handled case, not a spec error. The class is kept defined and
    exported for API compatibility (some callers may still want to catch
    it); nothing in this module raises it any more.
    """


@dataclass(frozen=True)
class Lexer:
    """A compiled, annotated DFA ready for the runtime driver (Task 6/12).

    Fields:
        spec: the source ``Spec`` this was compiled from.
        partition: the shared alphabet ``Partition``.
        dfa: the unified token+trivia DFA (``compile_spec``'s output).
        extend: ``extend[q]`` (a ``frozenset[int]``) is the set of symbols
            sigma such that ``dfa.delta[q]`` has a transition on sigma into
            a *live* state (live = some accepting state is reachable from
            it, including itself). The driver uses this to decide whether
            it is still worth reading one more character after reaching an
            accepting state.
        follow: ``{rule_name: (frozenset[int], eof_ok: bool)}``. A token
            rule with **no** ``followed_by`` constraint is simply ABSENT
            from this dict -- this is the chosen representation for
            "unconstrained": Task 6's driver treats a missing key as
            unconstrained-pass (the follow check is skipped entirely).
            When a rule *is* present, the tuple's frozenset is never
            ``None``; ``eof_ok`` says whether end-of-input alone also
            satisfies the constraint.
        kind: ``{rule_name: 'token' | 'trivia'}``, covering every declared
            rule.
        nest: ``{trivia_rule_name: (open_dfa, close_dfa)}`` for trivia
            rules declared with ``nest self`` (nestable comments). The
            main ``dfa`` already contains the nest rule's open expression
            (``compile_spec`` folded it in like any other rule) -- that is
            intentional: the main DFA accepting the nest rule's label is
            what triggers nest mode in the driver. ``open_dfa`` here is a
            *separate* single-rule DFA (``compile_expr`` on the same
            ``TriviaRule.expr``) for re-matching further opens *inside*
            the comment body; ``close_dfa`` matches ``TriviaRule.nest_close``.
        builder: ``{rule_name: builder_str | None}`` for token rules only
            (trivia rules have no builder).
        commit: ``frozenset[int]`` -- the states in the "pending" graph
            (non-accepting states reachable from an accept without
            crossing another accept) that lie ON a cycle, or are
            REACHABLE FROM a cycle while staying inside the pending
            subgraph. These states cannot be given a constant backup
            bound: a maximal-munch scanner sitting in one of them could,
            in the worst case, need to consume unboundedly many
            characters before either finding a further accept or getting
            stuck. Rather than rejecting the spec, the driver
            (``driver._resolve``) *commits* once an attempt enters this
            region -- if it later dies with no further accept, it emits
            one zero-pushback ``'unterminated'`` error token spanning
            everything consumed, instead of backing up to an earlier
            (shorter) accept. This reproduces ``prolog_tokenizer.py``'s
            actual greedy, non-backtracking, single-pass behavior for the
            two ISO constructs that create this (quote-doubling; an
            escape's optional closing backslash) -- see
            task-8-report.md's fix-round section.
        max_backup: the proven upper bound (in characters) on how far a
            maximal-munch scanner must back up past the last accepting
            state before it is guaranteed to be stuck or matched again,
            computed over pending states OUTSIDE ``commit`` only (that
            restricted subgraph is acyclic by construction -- see
            ``_commit_region``).
    """

    spec: Spec
    partition: Partition
    dfa: DFA
    extend: tuple  # tuple[frozenset[int], ...], indexed by dfa state id
    follow: dict  # {rule_name: (frozenset[int], eof_ok: bool)}
    kind: dict  # {rule_name: 'token' | 'trivia'}
    nest: dict  # {rule_name: (DFA, DFA)}
    builder: dict  # {rule_name: str | None}
    commit: frozenset  # frozenset[int] -- see docstring above
    max_backup: int


# ── liveness + extend sets ───────────────────────────────────────────


def _liveness(dfa: DFA) -> list:
    """live[q] = True iff some accepting state is reachable from q (incl. q).

    Reverse BFS from every accepting state over the reversed transition
    graph. Computed independently of any pruning ``compile_spec`` may
    already have done -- correctness here must not depend on that.
    """
    n = len(dfa.delta)
    rev = [[] for _ in range(n)]
    for q, row in enumerate(dfa.delta):
        for dest in row.values():
            rev[dest].append(q)

    live = [bool(dfa.accepts[q]) for q in range(n)]
    stack = [q for q in range(n) if live[q]]
    while stack:
        q = stack.pop()
        for p in rev[q]:
            if not live[p]:
                live[p] = True
                stack.append(p)
    return live


def _extend_sets(dfa: DFA, live: list) -> tuple:
    """extend[q] = symbols sigma with delta[q][sigma] defined and live."""
    out = []
    for q, row in enumerate(dfa.delta):
        out.append(frozenset(sym for sym, dest in row.items() if live[dest]))
    return tuple(out)


# ── follow / kind / builder / nest maps ──────────────────────────────


def _follow_map(spec: Spec, partition: Partition) -> dict:
    follow = {}
    for rule in spec.tokens:
        if rule.follow is not None:
            follow[rule.name] = (partition.symbols_of(rule.follow), rule.follow_eof)
    return follow


def _kind_map(spec: Spec) -> dict:
    kind = {}
    for rule in spec.tokens:
        kind[rule.name] = "token"
    for rule in spec.trivia:
        kind[rule.name] = "trivia"
    return kind


def _builder_map(spec: Spec) -> dict:
    return {rule.name: rule.builder for rule in spec.tokens}


def _nest_map(spec: Spec, partition: Partition) -> dict:
    nest = {}
    for rule in spec.trivia:
        if rule.nest_close is not None:
            open_dfa = compile_expr(rule.expr, partition, label=rule.name)
            close_dfa = compile_expr(rule.nest_close, partition, label=rule.name)
            nest[rule.name] = (open_dfa, close_dfa)
    return nest


# ── bounded-backup proof + commit-region derivation (design §4.3, revised) ──


def _pending_states(dfa: DFA, accepting: list) -> set:
    """The set of non-accepting states reachable from some accepting state
    without passing through another accepting state (crossing exactly one
    edge out of the accepting state, then staying within non-accepting
    states)."""
    n = len(dfa.delta)
    pending = set()
    stack = []
    for q in range(n):
        if accepting[q]:
            for dest in dfa.delta[q].values():
                if not accepting[dest] and dest not in pending:
                    pending.add(dest)
                    stack.append(dest)
    while stack:
        q = stack.pop()
        for dest in dfa.delta[q].values():
            if not accepting[dest] and dest not in pending:
                pending.add(dest)
                stack.append(dest)
    return pending


def _pending_adjacency(dfa: DFA, pending: set) -> dict:
    """adj[q] = the distinct destinations of q that are also in `pending`
    (edges of the subgraph induced by `pending`, deduplicated across
    symbols)."""
    return {q: {d for d in dfa.delta[q].values() if d in pending} for q in pending}


def _cyclic_pending_states(adj: dict) -> set:
    """States in `adj` that lie on at least one cycle -- i.e. are
    reachable from one of their own successors by staying inside `adj`
    (equivalently: reachable from themselves via a path of length >= 1).
    """
    cyclic = set()
    for u in adj:
        stack = list(adj[u])
        seen = set()
        while stack:
            x = stack.pop()
            if x == u:
                cyclic.add(u)
                break
            if x in seen:
                continue
            seen.add(x)
            stack.extend(adj.get(x, ()))
    return cyclic


def _forward_reachable(adj: dict, sources: set) -> set:
    """All states reachable within `adj` from any state in `sources`
    (`sources` themselves included)."""
    seen = set(sources)
    stack = list(sources)
    while stack:
        u = stack.pop()
        for v in adj.get(u, ()):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def _commit_region(dfa: DFA, pending: set) -> frozenset:
    """States in `pending` that cannot be given a constant backup bound:
    states that lie ON a cycle of the induced pending-subgraph, or are
    REACHABLE FROM such a cycle while staying inside `pending`. See
    `Lexer.commit`'s docstring for what the driver does with this.

    Every OTHER pending state (`pending - commit`) is, by construction,
    free of cycles: any cycle running through such a state would put
    every state on that cycle "on a cycle" and hence in `commit` -- a
    contradiction. So `_longest_pending_chains`'s acyclicity assumption
    holds on exactly that restricted subgraph without a separate check.
    """
    if not pending:
        return frozenset()
    adj = _pending_adjacency(dfa, pending)
    cyclic = _cyclic_pending_states(adj)
    return frozenset(_forward_reachable(adj, cyclic))


def _longest_pending_chains(dfa: DFA, eligible: set) -> dict:
    """longest[q] = length in states (self-inclusive) of the longest chain
    of `eligible` states reachable from q by staying inside `eligible`.
    Assumes the induced subgraph is acyclic -- true by construction when
    `eligible` is `pending - commit` (see `_commit_region`)."""
    longest: dict = {}

    def compute(q):
        if q in longest:
            return longest[q]
        best = 0
        for dest in dfa.delta[q].values():
            if dest in eligible:
                best = max(best, compute(dest))
        longest[q] = 1 + best
        return longest[q]

    for q in eligible:
        compute(q)
    return longest


def _backup_bound(dfa: DFA, pending: set, commit: frozenset) -> int:
    """Longest-chain bound computed over `pending - commit` only -- the
    part of the pending graph proven acyclic by `_commit_region`. States
    in `commit` contribute no bound here; they're handled by the driver's
    commit-region branch instead (see `Lexer.commit`)."""
    eligible = pending - commit
    if not eligible:
        return 0
    longest = _longest_pending_chains(dfa, eligible)

    accepting = [bool(dfa.accepts[q]) for q in range(len(dfa.delta))]
    max_backup = 0
    for q in range(len(dfa.delta)):
        if accepting[q]:
            for dest in dfa.delta[q].values():
                if dest in eligible:
                    max_backup = max(max_backup, longest[dest])
    return max_backup


# ── front door ────────────────────────────────────────────────────────


def annotate(spec: Spec) -> Lexer:
    partition = build_partition(spec)
    dfa = compile_spec(spec, partition)
    live = _liveness(dfa)
    accepting = [bool(dfa.accepts[q]) for q in range(len(dfa.delta))]
    pending = _pending_states(dfa, accepting)
    commit = _commit_region(dfa, pending)
    return Lexer(
        spec=spec,
        partition=partition,
        dfa=dfa,
        extend=_extend_sets(dfa, live),
        follow=_follow_map(spec, partition),
        kind=_kind_map(spec),
        nest=_nest_map(spec, partition),
        builder=_builder_map(spec),
        commit=commit,
        max_backup=_backup_bound(dfa, pending, commit),
    )


# ── Prolog-term dump ───────────────────────────────────────────────────


def _quote_atom(name: str) -> str:
    if name and name[0].islower() and all(c.isalnum() or c == "_" for c in name):
        return name
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def dump_term(lexer: Lexer) -> str:
    """Render `lexer` as a single readable Prolog term, terminated by '.':

        toklex_dfa(start(S),
                    symbols([s(Sym, Lo, Hi), ...]),
                    states([q(Id, accepts([Name, ...]), extend([Sym, ...]),
                              trans([t(Sym, Dest), ...])), ...])).

    `symbols` is the partition's cell legend (codepoint bounds per symbol
    id); every other symbol id referenced in `states` is an index into it.
    """
    p = lexer.partition
    dfa = lexer.dfa

    symbols = ",".join(
        f"s({sym},{lo},{hi})" for sym, (lo, hi) in enumerate(p.cells())
    )

    state_terms = []
    for q, row in enumerate(dfa.delta):
        accepts = ",".join(_quote_atom(nm) for nm in dfa.accepts[q])
        extend_syms = ",".join(str(s) for s in sorted(lexer.extend[q]))
        trans = ",".join(f"t({sym},{dest})" for sym, dest in sorted(row.items()))
        state_terms.append(
            f"q({q},accepts([{accepts}]),extend([{extend_syms}]),"
            f"trans([{trans}]))"
        )

    return (
        f"toklex_dfa(start({dfa.start}),symbols([{symbols}]),"
        f"states([{','.join(state_terms)}]))."
    )
