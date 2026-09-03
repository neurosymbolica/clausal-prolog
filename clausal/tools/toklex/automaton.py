"""toklex automaton core: RE -> Thompson NFA -> subset-construction DFA.

Builds a single DFA over a shared alphabet `Partition` from the RE IR
produced by ``spec.py`` (Task 3). Supports language subtraction
(``ButNot``) via completed-DFA product construction, and labeled union
of every token/trivia rule into one automaton (Task 3's ``Spec``).

No minimization (deliberate plan decision) -- DFA states are exactly
the frozensets discovered by subset construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from clausal.tools.toklex.charset import Partition
from clausal.tools.toklex.spec import Alt, ButNot, Lit, Opt, Plus, Seq, SpecError, Star


@dataclass(frozen=True)
class DFA:
    start: int
    delta: tuple  # tuple[dict[int, int], ...]  -- delta[q][sym] absent = no transition
    accepts: tuple  # tuple[tuple[str, ...], ...]  -- priority-ordered rule names


# ── alphabet collection ───────────────────────────────────────────────


def build_partition(spec) -> Partition:
    """Collect every Lit CharSet + every TokenRule.follow into one Partition."""
    charsets = []

    def walk(node):
        if isinstance(node, Lit):
            charsets.append(node.cs)
        elif isinstance(node, Seq) or isinstance(node, Alt):
            for part in node.parts:
                walk(part)
        elif isinstance(node, (Star, Plus, Opt)):
            walk(node.x)
        elif isinstance(node, ButNot):
            walk(node.a)
            walk(node.b)

    for rule in spec.tokens:
        walk(rule.expr)
        if rule.follow is not None:
            charsets.append(rule.follow)
    for rule in spec.trivia:
        walk(rule.expr)
        if rule.nest_close is not None:
            walk(rule.nest_close)

    return Partition.build(charsets)


# ── NFA builder (Thompson construction) ────────────────────────────────


class _NFABuilder:
    """Growable NFA state pool shared across fragments built into it."""

    def __init__(self):
        self.eps = []  # list[set[int]]
        self.trans = []  # list[dict[int, set[int]]]

    def new_state(self) -> int:
        self.eps.append(set())
        self.trans.append({})
        return len(self.eps) - 1

    def add_eps(self, a: int, b: int) -> None:
        self.eps[a].add(b)

    def add_trans(self, a: int, sym: int, b: int) -> None:
        self.trans[a].setdefault(sym, set()).add(b)


def _build_fragment(node, partition: Partition, nb: _NFABuilder) -> tuple:
    """Thompson-construct `node` into `nb`; returns (start, accept) states."""
    if isinstance(node, Lit):
        return _frag_lit(node, partition, nb)
    if isinstance(node, Seq):
        return _frag_seq(node, partition, nb)
    if isinstance(node, Alt):
        return _frag_alt(node, partition, nb)
    if isinstance(node, Star):
        return _frag_star(node, partition, nb)
    if isinstance(node, Plus):
        return _frag_plus(node, partition, nb)
    if isinstance(node, Opt):
        return _frag_opt(node, partition, nb)
    if isinstance(node, ButNot):
        return _compile_but_not(node, partition, nb)
    raise SpecError(f"unsupported RE node in automaton construction: {node!r}")


def _frag_lit(node: Lit, partition: Partition, nb: _NFABuilder) -> tuple:
    s, a = nb.new_state(), nb.new_state()
    for sym in partition.symbols_of(node.cs):
        nb.add_trans(s, sym, a)
    return s, a


def _frag_seq(node: Seq, partition: Partition, nb: _NFABuilder) -> tuple:
    cur_s, cur_a = _build_fragment(node.parts[0], partition, nb)
    start = cur_s
    for part in node.parts[1:]:
        s2, a2 = _build_fragment(part, partition, nb)
        nb.add_eps(cur_a, s2)
        cur_a = a2
    return start, cur_a


def _frag_alt(node: Alt, partition: Partition, nb: _NFABuilder) -> tuple:
    s, a = nb.new_state(), nb.new_state()
    for part in node.parts:
        ps, pa = _build_fragment(part, partition, nb)
        nb.add_eps(s, ps)
        nb.add_eps(pa, a)
    return s, a


def _frag_star(node: Star, partition: Partition, nb: _NFABuilder) -> tuple:
    s, a = nb.new_state(), nb.new_state()
    ps, pa = _build_fragment(node.x, partition, nb)
    nb.add_eps(s, ps)
    nb.add_eps(s, a)
    nb.add_eps(pa, ps)
    nb.add_eps(pa, a)
    return s, a


def _frag_plus(node: Plus, partition: Partition, nb: _NFABuilder) -> tuple:
    ps, pa = _build_fragment(node.x, partition, nb)
    a = nb.new_state()
    nb.add_eps(pa, ps)
    nb.add_eps(pa, a)
    return ps, a


def _frag_opt(node: Opt, partition: Partition, nb: _NFABuilder) -> tuple:
    s, a = nb.new_state(), nb.new_state()
    ps, pa = _build_fragment(node.x, partition, nb)
    nb.add_eps(s, ps)
    nb.add_eps(s, a)
    nb.add_eps(pa, a)
    return s, a


# ── subset construction (generic, over an _NFABuilder's state pool) ────


def _epsilon_closure(states, eps) -> frozenset:
    closure = set(states)
    stack = list(states)
    while stack:
        s = stack.pop()
        for t in eps[s]:
            if t not in closure:
                closure.add(t)
                stack.append(t)
    return frozenset(closure)


def _subset_construct(nb: _NFABuilder, start: int, n_syms: int):
    """Subset-construct the NFA rooted at `start`. Returns (dfa_states, delta)."""
    start_closure = _epsilon_closure({start}, nb.eps)
    dfa_states = [start_closure]
    index = {start_closure: 0}
    delta = []
    queue = [start_closure]
    while queue:
        cur = queue.pop(0)
        row = {}
        for sym in range(n_syms):
            nxt = set()
            for s in cur:
                nxt |= nb.trans[s].get(sym, set())
            if nxt:
                closure = _epsilon_closure(nxt, nb.eps)
                if closure not in index:
                    index[closure] = len(dfa_states)
                    dfa_states.append(closure)
                    queue.append(closure)
                row[sym] = index[closure]
        delta.append(row)
    return dfa_states, delta


# ── ButNot: product of two completed DFAs, pruned and re-embedded ─────


@dataclass
class _Det:
    delta: list
    accept: list


def _determinize_standalone(node, partition: Partition) -> _Det:
    nb = _NFABuilder()
    s, a = _build_fragment(node, partition, nb)
    states, delta = _subset_construct(nb, s, partition.n)
    accept = [a in st for st in states]
    return _Det(delta, accept)


def _complete(det: _Det, n_syms: int) -> None:
    """Add an explicit sink state and fill every missing transition."""
    sink = len(det.delta)
    for row in det.delta:
        for sym in range(n_syms):
            row.setdefault(sym, sink)
    det.delta.append({sym: sink for sym in range(n_syms)})
    det.accept.append(False)


def _product(det_a: _Det, det_b: _Det, n_syms: int):
    """BFS product of two total DFAs; accept iff a-accepts and not b-accepts."""
    states = [(0, 0)]
    index = {(0, 0): 0}
    delta, accept = [], []
    queue = [(0, 0)]
    while queue:
        qa, qb = queue.pop(0)
        accept.append(det_a.accept[qa] and not det_b.accept[qb])
        row = {}
        for sym in range(n_syms):
            nxt = (det_a.delta[qa][sym], det_b.delta[qb][sym])
            if nxt not in index:
                index[nxt] = len(states)
                states.append(nxt)
                queue.append(nxt)
            row[sym] = index[nxt]
        delta.append(row)
    return states, delta, accept


def _prune(states, delta, accept) -> set:
    """Keep states that can reach an accept, plus the start (index 0)."""
    n = len(states)
    rev = [[] for _ in range(n)]
    for i, row in enumerate(delta):
        for j in row.values():
            rev[j].append(i)
    keep = {i for i in range(n) if accept[i]}
    stack = list(keep)
    while stack:
        i = stack.pop()
        for p in rev[i]:
            if p not in keep:
                keep.add(p)
                stack.append(p)
    keep.add(0)
    return keep


def _embed(nb: _NFABuilder, delta, accept, keep: set) -> tuple:
    """Copy the kept pruned-product states into `nb`; returns (start, accept)."""
    mapping = {old: nb.new_state() for old in keep}
    fresh_accept = nb.new_state()
    for old in keep:
        new = mapping[old]
        for sym, tgt in delta[old].items():
            if tgt in keep:
                nb.add_trans(new, sym, mapping[tgt])
        if accept[old]:
            nb.add_eps(new, fresh_accept)
    return mapping[0], fresh_accept


def _compile_but_not(node: ButNot, partition: Partition, nb: _NFABuilder) -> tuple:
    det_a = _determinize_standalone(node.a, partition)
    det_b = _determinize_standalone(node.b, partition)
    _complete(det_a, partition.n)
    _complete(det_b, partition.n)
    states, delta, accept = _product(det_a, det_b, partition.n)
    keep = _prune(states, delta, accept)
    return _embed(nb, delta, accept, keep)


# ── public API ──────────────────────────────────────────────────────


def compile_expr(expr, partition: Partition, label: str = "x") -> DFA:
    nb = _NFABuilder()
    start, accept_state = _build_fragment(expr, partition, nb)
    states, delta = _subset_construct(nb, start, partition.n)
    accepts = tuple((label,) if accept_state in st else () for st in states)
    return DFA(start=0, delta=tuple(delta), accepts=accepts)


def compile_spec(spec, partition: Partition) -> DFA:
    rules = list(spec.tokens) + list(spec.trivia)
    global_index = {rule.name: i for i, rule in enumerate(rules)}

    nb = _NFABuilder()
    fresh_start = nb.new_state()
    accept_map = {}
    for rule in rules:
        s, a = _build_fragment(rule.expr, partition, nb)
        nb.add_eps(fresh_start, s)
        accept_map[a] = rule.name

    states, delta = _subset_construct(nb, fresh_start, partition.n)

    seen = set()
    accepts = []
    for st in states:
        names = sorted(
            (accept_map[s] for s in st if s in accept_map),
            key=lambda nm: global_index[nm],
        )
        accepts.append(tuple(names))
        seen.update(names)

    for rule in rules:
        if rule.name not in seen:
            raise SpecError(
                f"rule {rule.name!r} accepts no strings (subtracted to emptiness)"
            )

    return DFA(start=0, delta=tuple(delta), accepts=tuple(accepts))
