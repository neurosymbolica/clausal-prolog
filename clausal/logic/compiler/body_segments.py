"""Long conjunctions as a chain of segment functions (trampoline strategy).

A trampoline clause body nests: each goal's continuation runs inside the
loop over the previous goal's answers, so a body of N goals compiles to a
function whose blocks nest about N deep.  CPython refuses more than 20
statically nested blocks, and ``codegen.split_deep_nesting`` -- which
outlines the deep tail into helpers NESTED inside each other -- is
quadratic and still hits CPython's compiler recursion limit near 10k goals
(todo/done/pl-readers-recursion-limit-on-long-clause-bodies-2026-10-02.md).

Here a long ``Sequence`` is cut into segments of bounded nesting, and each
segment becomes a generator function of its own at MODULE level, run as a
trampoline frame like an auxiliary predicate:

- the goals of the sequence are lowered with a fresh proceed name ``P``
  and the leaf ``yield (P, None)``; every ``SEGMENT_HEIGHT`` levels of
  nesting the continuation so far becomes a segment ``S_{j+1}`` and is
  replaced by a TAIL call of it, ``StepGenerator(S_{j+1}, P, self, self,
  ..., trail)`` -- its answers go straight to ``P``;
- the whole chain is called from the enclosing frame with ``self`` as its
  proceed, and the sequence's own continuation (``k_stmts``: the rest of
  the clause, the leaf answer, a catch/3 flag...) runs in the ENCLOSING
  frame once per answer, exactly where it ran before.

Answers, their order and exceptions are the inline code's: a segment is a
frame like any callee (its exceptions go to its catcher, the enclosing
frame, at the ``yield`` that runs it, inside whatever ``try`` encloses it).
A cut in a segment runs the clause's own cut exit -- ``trail.undo(_mark);
yield (_fail, DONE)`` -- with the clause's ``_mark`` and ``_fail`` passed
in, so its exhaustion goes to the clause's caller and every frame between
(the clause frame and the segments before it) is abandoned, as the clause
frame alone was before.

Python locals cross a segment boundary as parameters (logic variables are
``Var`` objects, so passing them is sharing them).  The hoist pass
(``hoist_segments``) works out each segment's parameters with Python's own
scoping rules, and REFUSES -- the predicate is then rebuilt without
segments, and the old outliner handles it -- whenever passing by value
could change a result: a segment storing a name read outside it, a yield
or return it does not recognise, ``self`` used other than as a callee's
continuation slot, and so on.

Only a sequence that nests deeper than ``SPLIT_ABOVE`` is cut, so every
clause that compiled before keeps its exact code; set the environment
variable ``CLAUSAL_BODY_SEGMENT_HEIGHT=<n>`` to cut every sequence of two
goals or more at height ``n`` (the differential test mode).
"""

from __future__ import annotations

import ast
import os

#: The block nesting a segment may grow to before it is cut.
SEGMENT_HEIGHT = 12
#: A sequence whose lowering nests deeper than this is cut into segments.
#: A clause arm adds two blocks (the generator, the arm's ``try``), and
#: CPython allows 20.
SPLIT_ABOVE = 18
#: Shorter sequences are never cut (and pay no height tracking).
MIN_OPS = 8

ENV_VAR = "CLAUSAL_BODY_SEGMENT_HEIGHT"

_SEG_FAIL = "_seg_fail"
SEGMENT_FAIL = _SEG_FAIL
_SEG_CATCHER = "_seg_catcher"
_SEG_ENV = "_segenv"


def settings() -> tuple[int, int, int]:
    """``(segment height, split above, min ops)``; the env var forces
    every sequence of two goals or more to be cut."""
    raw = os.environ.get(ENV_VAR)
    if raw:
        try:
            h = max(1, int(raw))
        except ValueError:
            h = SEGMENT_HEIGHT
        return h, -1, 2
    return SEGMENT_HEIGHT, SPLIT_ABOVE, MIN_OPS


class SegmentRefused(Exception):
    """A segment cannot be hoisted without changing what the code does;
    the predicate is rebuilt without segments."""


class Segment:
    """One segment: its body (off the main tree), the names its frame
    uses, and the ``$StepGenerator`` call that runs it."""
    __slots__ = ("name", "body", "self_name", "proceed", "fail_name",
                 "trail_name", "call", "params", "unpack", "root", "env", "func")

    def __init__(self, name, body, self_name, proceed, fail_name, trail_name, call):
        self.name, self.body = name, body
        self.self_name, self.proceed = self_name, proceed
        self.fail_name, self.trail_name = fail_name, trail_name
        self.call = call
        self.params: list[str] = []
        self.func = None


# ── heights ──────────────────────────────────────────────────────────────────


def _list_height(stmts, memo: dict) -> int:
    """The block nesting of *stmts* (CPython's accounting, as
    ``codegen._child_lists``), memoised by statement: the fold re-measures
    a continuation it has already measured, so each step costs only the
    code it added.  The memo holds the statements so ids stay unique."""
    from clausal.codegen import _child_lists
    best = 0
    for top in stmts:
        got = memo.get(id(top))
        if got is not None:
            best = max(best, got[1])
            continue
        stack = [(top, False)]
        while stack:
            s, done = stack.pop()
            if id(s) in memo:
                continue
            kids = _child_lists(s)
            if not done:
                stack.append((s, True))
                for _, owner, field in kids:
                    for c in getattr(owner, field):
                        if id(c) not in memo:
                            stack.append((c, False))
                continue
            h = 0
            for add, owner, field in kids:
                for c in getattr(owner, field):
                    h = max(h, add + memo[id(c)][1])
            memo[id(s)] = (s, h)
        best = max(best, memo[id(top)][1])
    return best


# ── the fold ─────────────────────────────────────────────────────────────────


def fold_sequence(ops, ctx, k_stmts, recurse):
    """Lower the conjunction *ops* with continuation *k_stmts*; the
    ``Sequence`` arm of ``_lower_goalop_shared`` delegates here."""
    from .strategy import TrampolineStrategy

    segments = ctx.body_segments
    height, split_above, min_ops = settings()
    if (segments is None or len(ops) < min_ops
            or not isinstance(ctx.strategy, TrampolineStrategy)):
        return _fold_plain(ops, ctx, k_stmts, recurse)
    if split_above >= 0:
        # Fold as always; only a sequence that turns out deeper than the
        # limit is folded again, in segments.  Lowering records first-seen
        # body variables in ``var_context``: restore it for the refold.
        saved = dict(ctx.var_context)
        memo: dict = {}
        k = list(k_stmts)
        for op in reversed(ops):
            k = recurse(op, ctx, k)
            if _list_height(k, memo) > split_above:
                break
        else:
            return k
        ctx.var_context.clear()
        ctx.var_context.update(saved)
    return _fold_segmented(ops, ctx, k_stmts, recurse, height, segments)


def _fold_plain(ops, ctx, k_stmts, recurse):
    k = list(k_stmts)
    for op in reversed(ops):
        k = recurse(op, ctx, k)
    return k


def _fold_segmented(ops, ctx, k_stmts, recurse, height, segments):
    from ._ast_helpers import _name, _locate
    from .goal_trampoline import _yield_step_stmt

    proceed = ctx.fresh("_segp")
    sctx = ctx.replace(proceed_name=proceed)
    k = [_locate(_yield_step_stmt(_name(proceed), ast.Constant(None)))]
    memo: dict = {}
    for idx in range(len(ops) - 1, -1, -1):
        k = recurse(ops[idx], sctx, k)
        if idx > 0 and _list_height(k, memo) >= height:
            # The continuation so far becomes a segment, run by a tail call.
            k = _segment_call(sctx, k, proceed, segments, tail=True)
    # The whole chain, run by the enclosing frame; its answers come back
    # here and the sequence's own continuation runs on each.
    return _segment_call(ctx, k, proceed, segments, tail=False,
                         k_stmts=list(k_stmts))


def _segment_call(ctx, body, proceed, segments, *, tail, k_stmts=None):
    """``[g = $StepGenerator(seg, ...), s = yield (g, None), while s is not
    $DONE: <k>; s = yield (g, None)]`` -- the parameters are filled in by
    ``hoist_segments``."""
    from ._ast_helpers import _assign, _call, _name, _locate
    from .goal_trampoline import _assign_yield_step

    seg_name = ctx.fresh("$seg")
    self_ = ctx.self_name
    call = _call(_name("$StepGenerator"), _name(seg_name),
                 _name(proceed if tail else self_), _name(self_), _name(self_),
                 _name(ctx.trail_name))
    seg = Segment(seg_name, body, self_, proceed, ctx.fail_name,
                  ctx.trail_name, call)
    call._clausal_segment = seg
    segments.append(seg)
    gen = ctx.fresh("_segg")
    status = ctx.fresh("_segs")
    resume = [] if tail else (k_stmts or [ast.Pass()])
    loop = ast.While(
        test=ast.Compare(left=_name(status), ops=[ast.IsNot()],
                         comparators=[_name("$DONE")]),
        body=resume + [_assign_yield_step(status, _name(gen), ast.Constant(None))],
        orelse=[])
    out = [_assign(gen, call),
           _assign_yield_step(status, _name(gen), ast.Constant(None)),
           loop]
    for s in out:
        _locate(s)
    return out


# ── hoisting: scope analysis ─────────────────────────────────────────────────

_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef,
           ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


class _Scope:
    """A real function scope or a segment body."""
    __slots__ = ("node", "seg", "parent", "events", "loads", "stores", "args",
                 "children", "pre", "post", "free", "owner")

    def __init__(self, node, seg, parent):
        self.node, self.seg, self.parent = node, seg, parent
        self.events: list = []        # ("l", name) | ("s", name) | ("c", scope)
        self.loads: set = set()
        self.stores: set = set()
        self.args: set = set()
        self.children: list = []
        self.pre = self.post = 0
        self.free: list = []
        self.owner = None             # nearest real-function scope


def _ordered(node):
    """Children of *node* in evaluation order, near enough for "is this
    name read before it is written": a value before its targets, a loop's
    iterable before its target."""
    t = type(node)
    if t is ast.Assign:
        return [node.value, *node.targets]
    if t is ast.AnnAssign:
        return ([node.value] if node.value is not None else []) + [node.target]
    if t in (ast.For, ast.AsyncFor):
        return [node.iter, node.target, *node.body, *node.orelse]
    if t is ast.NamedExpr:
        return [node.value, node.target]
    return list(ast.iter_child_nodes(node))


def _check_refuse(cond, why):
    if cond:
        raise SegmentRefused(why)


def _scan(scope: _Scope, roots, new_scopes: list) -> None:
    """Fill *scope*'s events from its own statements (*roots*), recording
    nested real scopes and segment calls as children."""
    seg = scope.seg
    seen: set = set()
    allowed: set = set()      # ids of Name nodes allowed to load self/proceed
    stepgens: set = set()     # names assigned a $StepGenerator in this scope
    pulled: list = []
    stack = list(reversed(roots))
    while stack:
        n = stack.pop()
        t = type(n)
        if t is tuple:                 # a synthetic event: ("store"|"load"|"child", x)
            kind, val = n
            if kind == "store":
                scope.events.append(("s", val))
                scope.stores.add(val)
            elif kind == "load":
                scope.events.append(("l", val))
                scope.loads.add(val)
            else:
                scope.events.append(("c", val))
            continue
        if id(n) in seen:
            continue
        seen.add(id(n))
        if t is ast.Name:
            if type(n.ctx) is ast.Load:
                if seg is not None and n.id in (seg.self_name, seg.proceed) \
                        and id(n) not in allowed:
                    raise SegmentRefused(f"{n.id} used outside a continuation slot")
                scope.events.append(("l", n.id))
                scope.loads.add(n.id)
            else:
                scope.events.append(("s", n.id))
                scope.stores.add(n.id)
            continue
        if isinstance(n, _SCOPES):
            # Decorators, defaults (and a class's bases) run here.
            pre = list(getattr(n, "decorator_list", ()))
            if isinstance(n, ast.ClassDef):
                pre += n.bases + [k.value for k in n.keywords]
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                pre += [d for d in n.args.defaults + n.args.kw_defaults if d]
            child = _Scope(n, None, scope)
            scope.children.append(child)
            new_scopes.append(child)
            # Order: the defaults, then the scope's free names, then the def's name.
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                stack.append(("store", n.name))
            stack.append(("child", child))
            stack.extend(reversed(pre))
            continue
        if seg is not None:
            if t in (ast.Global, ast.Nonlocal, ast.YieldFrom, ast.Await,
                     ast.AsyncFor, ast.AsyncWith):
                raise SegmentRefused(f"{t.__name__} in a segment")
            if t is ast.Yield:
                pulled_name = _check_yield(n, seg, allowed)
                if pulled_name is not None:
                    pulled.append(pulled_name)
            elif (t is ast.Assign and _is_stepgen_call(n.value)
                  and len(n.value.args) >= 4
                  and all(type(a) is ast.Name and a.id == seg.self_name
                          for a in n.value.args[2:4])
                  and type(n.value.args[1]) is ast.Name
                  and n.value.args[1].id in (seg.self_name, seg.proceed)):
                # A callee whose exhaustion and errors come back to this
                # frame: the only kind a segment may pull.
                for tg in n.targets:
                    if type(tg) is ast.Name:
                        stepgens.add(tg.id)
        if t is ast.Call:
            if _is_stepgen_call(n):
                for a in n.args[1:4]:
                    if type(a) is ast.Name:
                        allowed.add(id(a))
            sub = getattr(n, "_clausal_segment", None)
            if sub is not None:
                child = _Scope(None, sub, scope)
                scope.children.append(child)
                new_scopes.append(child)
                scope.events.append(("c", child))
        if t in (ast.MatchAs, ast.MatchStar) and n.name:
            stack.append(("store", n.name))
        elif t is ast.MatchMapping and n.rest:
            stack.append(("store", n.rest))
        elif t is ast.ExceptHandler and n.name:
            # ``except E as name``: the type, then the binding, then the body.
            kids = ([n.type] if n.type is not None else []) + [("store", n.name)] + n.body
            stack.extend(reversed(kids))
            continue
        elif t in (ast.Import, ast.ImportFrom):
            _check_refuse(seg is not None, "import in a segment")
            for a in n.names:
                stack.append(("store", (a.asname or a.name).split(".")[0]))
        elif t is ast.AugAssign:
            # ``x += e``: reads x after e, then writes it.
            tg = n.target
            stack.append(tg)
            if type(tg) is ast.Name:
                stack.append(("load", tg.id))
            stack.append(n.value)
            continue
        stack.extend(reversed(_ordered(n)))
    if seg is not None:
        for g in pulled:
            _check_refuse(g not in stepgens, f"pulls {g}, not its own callee")
        for name in (seg.self_name, seg.proceed, seg.trail_name, _SEG_FAIL,
                     _SEG_CATCHER, _SEG_ENV):
            _check_refuse(name in scope.stores, f"a segment rebinds {name}")
        _check_statements(seg)


def _is_stepgen_call(node) -> bool:
    return (type(node) is ast.Call and type(node.func) is ast.Name
            and node.func.id == "$StepGenerator")


def _check_yield(y, seg: Segment, allowed: set):
    """The yields a segment may make: an answer to its proceed, a pull of
    a callee it made, the cut exit's exhaustion to the scope's fail.
    Returns the pulled generator's name for a pull."""
    v = y.value
    if not (type(v) is ast.Tuple and len(v.elts) == 2
            and type(v.elts[0]) is ast.Name):
        raise SegmentRefused("a yield of an unknown shape")
    target, value = v.elts
    if target.id == seg.proceed:
        allowed.add(id(target))
        return None
    if target.id == seg.fail_name:
        _check_refuse(not (type(value) is ast.Name and value.id == "$DONE"),
                      "a yield to the scope's fail that is not exhaustion")
        return None
    _check_refuse(not (type(value) is ast.Constant and value.value is None),
                  "a yield to an unknown target")
    return target.id


def _check_statements(seg: Segment) -> None:
    """A ``return`` only right after the cut exit's exhaustion yield (it
    never runs), and no ``break``/``continue`` leaving the segment."""
    from clausal.codegen import _can_outline, _child_lists
    for s in seg.body:
        _check_refuse(not _can_outline(s), "break/continue/await leaving a segment")
    stack = [seg.body]
    seen: set = set()
    while stack:
        lst = stack.pop()
        if id(lst) in seen:
            continue
        seen.add(id(lst))
        for i, s in enumerate(lst):
            if type(s) is ast.Return:
                prev = lst[i - 1] if i else None
                ok = (prev is not None and type(prev) is ast.Expr
                      and type(prev.value) is ast.Yield
                      and type(prev.value.value) is ast.Tuple
                      and type(prev.value.value.elts[0]) is ast.Name
                      and prev.value.value.elts[0].id == seg.fail_name)
                _check_refuse(not ok, "a return that is not the cut exit's")
            for _, owner, field in _child_lists(s):
                stack.append(getattr(owner, field))


def _args_of(node) -> set:
    a = node.args
    out = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    out |= {x.arg for x in (a.vararg, a.kwarg) if x}
    return out


def _comp_targets(node) -> set:
    out = set()
    for g in node.generators:
        for x in ast.walk(g.target):
            if type(x) is ast.Name:
                out.add(x.id)
    return out


def hoist_segments(func_def: ast.FunctionDef, segments: list) -> list:
    """Give every segment reached from *func_def* its parameters and its
    module-level ``FunctionDef``; returns them (innermost first).  Raises
    :class:`SegmentRefused` if any one cannot be hoisted."""
    from ._ast_helpers import _name
    from .goal_trampoline import _yield_step_stmt

    root = _Scope(func_def, None, None)
    root.args = _args_of(func_def)
    order = [root]
    work = [root]
    found: set = set()
    while work:
        sc = work.pop()
        new: list = []
        if sc.seg is not None:
            _check_refuse(id(sc.seg) in found, "a segment reached twice")
            found.add(id(sc.seg))
            sc.args = {sc.seg.self_name, sc.seg.proceed, _SEG_FAIL, _SEG_CATCHER,
                       _SEG_ENV, sc.seg.trail_name}
            _scan(sc, sc.seg.body, new)
        else:
            node = sc.node
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                sc.args = _args_of(node)
                body = node.body if isinstance(node.body, list) else [node.body]
            elif isinstance(node, ast.ClassDef):
                body = node.body
            else:                                       # a comprehension
                sc.args = _comp_targets(node)
                body = [x for x in ast.iter_child_nodes(node)]
            _scan(sc, body, new)
        order.extend(new)
        work.extend(new)
    _check_refuse(len(found) != len(segments), "a segment not reached")

    # Pre-order intervals and owners.
    counter = 0
    stack = [(root, False)]
    while stack:
        sc, done = stack.pop()
        if done:
            sc.post = counter
            continue
        sc.pre = counter
        counter += 1
        sc.owner = sc if sc.seg is None else sc.parent.owner
        stack.append((sc, True))
        stack.extend((c, False) for c in reversed(sc.children))

    # Who binds each name, for "is it bound in an enclosing scope".
    binders: dict = {}
    for sc in order:
        for nme in sc.stores | sc.args:
            binders.setdefault(nme, []).append(sc)

    def nearest_binder(sc, nme):
        best = None
        for b in binders.get(nme, ()):
            if b.pre <= sc.pre < b.post and (best is None or b.pre > best.pre):
                best = b
        return best

    # The names a chain of segments needs from the function that runs it
    # travel in ONE tuple (``_segenv``), built where the chain starts and
    # handed down, each segment unpacking the ones it reads itself: passed
    # one by one, every segment would forward every name a later one
    # needs -- O(N) per segment, O(N^2) for the body.  A name a segment
    # binds goes on to the segments below it as a parameter.
    for sc in sorted(order, key=lambda s: s.pre):      # parents first
        if sc.seg is not None:
            sc.seg.root = sc if sc.parent.seg is None else sc.parent.seg.root
            if sc.seg.root is sc:
                sc.seg.env = {}
    for sc in sorted(order, key=lambda s: -s.pre):     # children first
        if sc.seg is None:
            if sc is root:
                continue
            names: list = []
            have: set = set()
            for kind, val in sc.events:
                for nme in ([val] if kind == "l" else
                            val.free if kind == "c" else ()):
                    if nme not in have:
                        have.add(nme)
                        names.append(nme)
            bound = sc.stores | sc.args
            sc.free = [x for x in names if x not in bound]
            continue
        seg = sc.seg
        written: set = set()
        have: set = set()
        exposed: list = []
        for kind, val in sc.events:
            if kind == "s":
                written.add(val)
                continue
            for nme in ([val] if kind == "l" else val.free):
                if nme in written or nme in have or nme in sc.args:
                    continue
                have.add(nme)
                exposed.append(nme)
        params, unpack = [], []
        env = seg.root.seg.env
        for nme in exposed:
            b = nearest_binder(sc.parent, nme)
            if b is None:
                # A global (a predicate, a ``$`` runtime name).
                _check_refuse(nme in sc.stores,
                              f"{nme} read before it is written, bound nowhere")
            elif b.seg is not None:
                params.append(nme)
            else:
                env.setdefault(nme, len(env))
                unpack.append(nme)
        seg.params, seg.unpack = params, unpack
        # What the scope running this segment reads at the call: the
        # parameters -- and, for a chain's first segment, the whole tuple.
        sc.free = params + (list(env) if seg.root is sc else [])

    # Reads and writes of each name across each real function's family
    # (itself, its segments, and the free names of the functions inside).
    occ: dict = {}
    for sc in order:
        fam = id(sc.owner)
        for nme in sc.loads:
            occ.setdefault((fam, nme), [[], []])[0].append(sc.pre)
        for c in sc.children:
            for nme in c.free:
                occ.setdefault((fam, nme), [[], []])[0].append(sc.pre)
        for nme in sc.stores | (sc.args if sc.seg is None else set()):
            occ.setdefault((fam, nme), [[], []])[1].append(sc.pre)
    for sc in order:
        if sc.seg is None:
            continue
        fam = id(sc.owner)
        for nme in sc.stores:
            reads, writes = occ.get((fam, nme), ([], []))
            if not reads:
                continue                 # written, never read (``_``)
            outside = [p for p in reads + writes if not (sc.pre <= p < sc.post)]
            _check_refuse(bool(outside),
                          f"{nme} is written in a segment and used outside it")

    funcs = []
    for sc in sorted(order, key=lambda s: s.pre):
        seg = sc.seg
        if seg is None:
            continue
        params, unpack = seg.params, seg.unpack
        index = seg.root.seg.env
        call = seg.call
        if seg.root is sc:
            env_arg = ast.Tuple(elts=[_name(n) for n in index], ctx=ast.Load())
        else:
            env_arg = _name(_SEG_ENV)
        call.args = (call.args[:4] + [env_arg] + [_name(p) for p in params]
                     + [call.args[-1]])
        fargs = ([seg.self_name, seg.proceed, _SEG_FAIL, _SEG_CATCHER, _SEG_ENV]
                 + params + [seg.trail_name])
        prelude = [ast.Assign(
            targets=[ast.Name(id=n, ctx=ast.Store())],
            value=ast.Subscript(value=_name(_SEG_ENV), slice=ast.Constant(index[n]),
                                ctx=ast.Load()))
            for n in unpack]
        for st in prelude:
            ast.copy_location(st, call)
            for x in ast.walk(st):
                ast.copy_location(x, call)
        extra = {"type_params": []} if "type_params" in ast.FunctionDef._fields else {}
        fd = ast.FunctionDef(
            name=seg.name,
            args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=p) for p in fargs],
                               vararg=None, kwonlyargs=[], kw_defaults=[],
                               kwarg=None, defaults=[]),
            body=prelude + list(seg.body)
            + [_yield_step_stmt(_name(_SEG_FAIL), _name("$DONE"))],
            decorator_list=[], returns=None, type_comment=None, **extra)
        ast.copy_location(fd, call)
        seg.func = fd
        funcs.append(fd)
    for sc in order:
        if sc.seg is not None:
            # Hoisted: the call is an ordinary call now (and a copy of it,
            # made by a later pass, must not copy the segment).
            del sc.seg.call._clausal_segment
    return funcs


__all__ = ["ENV_VAR", "Segment", "SegmentRefused", "fold_sequence",
           "hoist_segments", "settings"]
