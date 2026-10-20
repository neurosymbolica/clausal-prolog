"""Where a cut lands (ISO 7.8.4 scope rules on the GoalOp IR)."""
from __future__ import annotations

import functools

from clausal.logic.special_forms import GOAL_POSITIONS

from .ir import Alternate, Branch, Cut, GoalOp, IfThenElse, Sequence


def cut_reaches_scope(ir: GoalOp) -> bool:
    """True iff a ``Cut`` in *ir* cuts the scope *ir* is lowered in: cut is
    transparent to conjunction, disjunction and the then/else of an
    if-then-else; everything else (an ITE condition, ``\\+``, a
    meta-call's goal) is a barrier of its own.

    ``Branch`` (the seam's ``if_/3``) lowers its then/else in the enclosing
    scope too, so they are descended as well: a false True only costs a
    sub-generator, a false False would reach a scope with no cut exit."""
    match ir:
        case Cut():
            return True
        case Sequence(ops=ops) | Alternate(ops=ops):
            return any(cut_reaches_scope(op) for op in ops)
        case IfThenElse(then=th, else_=el) | Branch(then=th, else_=el):
            return cut_reaches_scope(th) or cut_reaches_scope(el)
        case _:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# XSB's run-time half: the cut's check (D61 Q1)
# ─────────────────────────────────────────────────────────────────────────────
#
# Every barrier scope that sets ``ctx.cut_exit`` also sets ``ctx.cut_guard``
# to a fresh one-slot holder.  The first Cut lowered in the scope names a
# local there (``_cutm``); the scope's builder then prepends
# ``_cutm = $tab_ctx.cut_seq`` to the scope's body (``cut_guard_entry``), and
# the Cut emits ``if $tab_ctx.cut_seq > _cutm: $cut_over_incomplete(...)``
# before the continuation.  A scope with no cut emits nothing, so cut-free
# code is byte-identical; a cut pays one attribute read and one int compare
# unless a tabled call over an incomplete table opened inside its scope
# (``tabling.cut_over_incomplete`` then decides).

CUT_SEQ_GLOBAL = "$tab_ctx"
CUT_CHECK_GLOBAL = "$cut_over_incomplete"


def new_cut_guard(name: "str | None" = None) -> list:
    """A scope's guard holder: ``[local name or None]``.  Pass *name* for a
    scope whose builder assigns the mark itself (an if-then-else)."""
    return [name]


def cut_seq_expr() -> "ast.expr":
    from ._ast_helpers import _attr
    return _attr(CUT_SEQ_GLOBAL, "cut_seq")


def cut_mark_assign(name: str) -> "ast.stmt":
    """``name = $tab_ctx.cut_seq`` -- a scope's entry mark."""
    from ._ast_helpers import _assign
    return _assign(name, cut_seq_expr())


def cut_check_stmt(name: str, owner: "str | None", trail_name: str) -> "ast.stmt":
    """``if $tab_ctx.cut_seq > name: $cut_over_incomplete(name, owner,
    trail)`` -- the trail tells this query's tabled frames from those of
    another query interleaved on the same thread."""
    import ast
    from ._ast_helpers import _call, _if, _locate, _name
    return _if(
        ast.Compare(left=cut_seq_expr(), ops=[ast.Gt()],
                    comparators=[_name(name)]),
        [_locate(ast.Expr(value=_call(_name(CUT_CHECK_GLOBAL), _name(name),
                                      ast.Constant(owner),
                                      _name(trail_name))))])


def cut_check_stmts(ctx) -> list:
    """The Cut arm's check, naming the scope's mark on first use; ``[]``
    for a scope with no guard (none is built without one)."""
    guard = ctx.cut_guard
    if guard is None:
        return []
    if guard[0] is None:
        guard[0] = ctx.fresh("_cutm")
    return [cut_check_stmt(guard[0], ctx.cut_owner, ctx.trail_name)]


def cut_guard_entry(guard: "list | None", stmts: list) -> list:
    """*stmts* (a scope's body) with its entry mark prepended -- only when a
    cut in it named one."""
    if guard is None or guard[0] is None:
        return stmts
    return [cut_mark_assign(guard[0])] + list(stmts)


def head_pi_text(head) -> "str | None":
    """``F/N`` of a clause head (a tuple term or an atom), for the error."""
    if isinstance(head, tuple) and head and isinstance(head[0], str):
        return f"{head[0]}/{len(head) - 1}"
    if isinstance(head, str):
        return f"{head}/0"
    return None


def may_reach_a_table(db) -> bool:
    """Can a goal compiled against *db* reach a tabled predicate it can see
    when it is compiled: one *db* tables, or one tabled by a module *db*
    imports from, transitively (an untabled imported predicate may call a
    tabled one in its own imports)?"""
    from clausal.logic.atoms import is_mangled
    from clausal.logic.predicate import _resolve_mangled_owner
    seen: set = set()
    stack = [db]
    while stack:
        d = stack.pop()
        if d is None or id(d) in seen:
            continue
        seen.add(id(d))
        if getattr(d, "_tabled", None):
            return True
        md = getattr(d, "module_dict", None)
        if not isinstance(md, dict):
            continue
        for v in list(md.values()):
            if is_mangled(v):
                owner = _resolve_mangled_owner(v, d)
                if owner is not None and id(owner[0]) not in seen:
                    stack.append(owner[0])
    return False


#: Callees that run a goal argument at run time when they are reached as
#: an ordinary call rather than compiled inline.
#: Every special form with a goal argument (``clausal/logic/special_forms.py``)
#: plus call/N, the control constructs and the goal-taking builtins.
_RUN_TIME_META = frozenset({
    "call", ",", ";", "->", "*->", "\\+", "not", "ignore", ":",
    "aggregate_all", "phrase"}) | frozenset(name for name, _ in GOAL_POSITIONS)


def _goal_is_open(goal, db) -> bool:
    """Can *goal* (a once/1 or Setup argument, as written) run a goal that
    is only known at run time: a variable, or a call/N anywhere in its goal
    positions?  Conservative: a goal the converter cannot read counts."""
    from clausal.logic.variables import deref, is_var
    from .ir import META_GOAL_POSITIONS, MetaCall, Negate, SubCall
    from .terms_to_goalop import terms_to_goalop, _convert
    goal = deref(goal)
    if is_var(goal):
        return True
    try:
        stack = [terms_to_goalop([goal], db)]
    except Exception:  # noqa: BLE001 - unreadable: assume open
        return True
    while stack:
        op = stack.pop()
        match op:
            case SubCall(fname=f) if f in _RUN_TIME_META:
                return True            # call/N, or a control construct
                                       # reached as a predicate call
            case Sequence(ops=ops) | Alternate(ops=ops):
                stack.extend(ops)
            case IfThenElse(test=t, then=th, else_=el) | Branch(test=t, then=th, else_=el):
                stack.extend((t, th, el))
            case Negate(op=inner):
                stack.append(inner)
            case MetaCall(kind=kind, args=margs):
                for key in META_GOAL_POSITIONS.get(kind, ()):
                    inner = margs.get(key)
                    if inner is None:
                        continue
                    if not isinstance(inner, GoalOp):
                        if is_var(deref(inner)):
                            return True
                        try:
                            inner = _convert(inner, db)
                        except Exception:  # noqa: BLE001
                            return True
                    stack.append(inner)
            case _:
                pass
    return False


def commit_check(ctx, goal=None) -> "tuple[list, list]":
    """``(before, at_commit)`` statements for a committing construct of a
    ``.pl`` body (once/1, setup_call_cleanup's Setup, its *goal*): mark
    before the sub-search, check at its first solution.

    ``([], [])`` for any other db (``.clausal``, ``.seam``: cut-free code
    stays byte-identical), and in a ``.pl`` db for a goal that is closed
    (no variable goal, no call/N) when the db cannot see a tabled predicate
    (:func:`may_reach_a_table`): once/1 over a literal goal is common in
    cut-free ``.pl`` code, whose codegen stays byte-identical
    (tests/test_cut_codegen.py).  An open goal -- ``first(G) :- once(G).``
    in a library module -- may run any table at all, so it is always
    checked.  A ``!`` and an if-then-else always carry the check."""
    from clausal.logic.builtins.call_body import cut_allowed
    if not cut_allowed(ctx.db):
        return [], []
    if not may_reach_a_table(ctx.db) and not (
            goal is not None and _goal_is_open(goal, ctx.db)):
        return [], []
    m = ctx.fresh("_cutm")
    return ([cut_mark_assign(m)],
            [cut_check_stmt(m, ctx.cut_owner, ctx.trail_name)])


# ─────────────────────────────────────────────────────────────────────────────
# Cut over a tabled call (XSB's rule, ruling Q1 -- provisional)
# ─────────────────────────────────────────────────────────────────────────────

#: What a ``!`` or an if-then-else commit does when its scope holds a call to
#: a tabled predicate.  ``"refuse"`` is XSB's static rule: "cuts are allowed
#: within tabled predicates subject to the restriction that the scope of a cut
#: cannot include a call to a tabled predicate" -- the compiler checks it and
#: aborts the load (:class:`~.ir.CutOverTableError`).  Our ruling applies it
#: to every caller, tabled or not (XSB's run-time check fires only over an
#: INCOMPLETE table).  ``"run"`` only skips the refusal: the cut is compiled
#: as written.  It is NOT Scryer's behaviour -- over an incomplete
#: (recursive) table the committed answer depends on our re-lead fixpoint's
#: pass order and differs from Scryer's (S37's tg/1: [0,1] here, [0,1,2] in
#: Scryer; pinned in tests/iso_l3/test_l3_cut_tabling.py).  THE ONE SWITCH,
#: for both halves: :func:`check_cut_over_tabled` (load time; its only
#: caller is ``goal_shallow._compile_body_impl``) and
#: ``tabling.cut_over_incomplete`` (run time) are its only readers.
CUT_OVER_TABLED_CALL = "refuse"

# Meta-calls whose goal's choice points SURVIVE the meta-call (ISO: catch/3
# is call/1 for its Goal; call_cleanup's Goal, call_nth, freeze/when's
# delayed goal likewise): a later cut in the enclosing scope cuts over them.
_TRANSPARENT_TO_CHOICE_POINTS = frozenset({
    ("catch", "inner"), ("catch", "recovery"), ("catch_error", "inner"),
    ("catch_recover", "inner"), ("catch_recover", "recovery"),
    ("call_cleanup", "call"), ("setup_call_cleanup", "call"),
    ("call_nth", "inner"), ("freeze", "inner"), ("when", "inner"),
})
# Meta-calls that COMMIT to their goal's first solution by definition --
# ISO 8.15.2: once(G) is call((G, !)) -- so they cut over its tabled calls
# (coordinator ruling on Task 7 I-3; part of Mike's Q1).  \+ and findall
# are not defined through cut and stay allowed.
_COMMITS = frozenset({("once", "inner"),
                      # setup_call_cleanup runs Setup as once/1 (Scryer;
                      # coordinator ruling, with once/1's)
                      ("setup_call_cleanup", "setup")})


def _literal_call_goal(op, db):
    """The GoalOp that ``call/N`` (*op*, a ``SubCall`` to ``call``) runs, when
    its goal argument is a LITERAL callable: call/1's term as a body, or
    call/N's atom/compound closure extended by the N-1 extra arguments.
    ``None`` for a variable (or otherwise unknowable) goal -- a goal built at
    run time is out of reach of a static rule, as in XSB."""
    from clausal.logic.variables import deref, is_var
    if not op.args:
        return None
    closure = deref(op.args[0])
    extra = list(op.args[1:])

    def extend(c):
        c = deref(c)
        if is_var(c):
            return None
        if not extra:
            return c
        if type(c) is str:
            return (c, *extra)
        if type(c) is tuple and c and type(c[0]) is str:
            if c[0] == ":" and len(c) == 3:
                inner = extend(c[2])
                return None if inner is None else (":", c[1], inner)
            return (*c, *extra)
        return None

    goal = extend(closure)
    return None if goal is None else _body_term_ir(goal)


@functools.cache
def _meta_terms() -> dict:
    """``(functor, arity)`` -> ``(MetaKind, {1-based position: arg key})`` of
    every special form with a goal argument (``clausal/logic/special_forms.
    py``), read off the compiler: the MetaCall ``terms_to_goalop`` makes of
    the same goal in a clause body, so a literal call/N term is scanned
    exactly as that body goal is."""
    from clausal.logic.variables import Var
    from clausal.pythonic_ast import nodes
    from .ir import META_GOAL_POSITIONS, MetaCall
    from .terms_to_goalop import _convert
    table = {}
    for (name, arity) in GOAL_POSITIONS:
        probes = [Var() for _ in range(arity)]
        op = _convert(nodes.Call(func=nodes.LoadName(name=name), args=probes,
                                 kwargs=[]), None)
        assert isinstance(op, MetaCall), (name, arity)
        table[(name, arity)] = (op.kind, {
            i + 1: key for key in META_GOAL_POSITIONS.get(op.kind, ())
            for i, p in enumerate(probes) if op.args.get(key) is p})
    return table


def _body_term_ir(t) -> GoalOp:
    """A literal body TERM (call/N's argument: ``(',', A, B)``, ``'!'``,
    ``('tf', X)`` ...) as the GoalOp shape the scan reads -- for the scan
    only, never lowered.  An unknowable goal (a variable, a non-callable) is
    the empty conjunction: a static rule cannot see into it."""
    from clausal.logic.variables import deref, is_var
    from .ir import Fail, MetaCall, Negate, SubCall
    t = deref(t)
    if is_var(t):
        return Sequence(ops=[])
    if type(t) is str:
        return Cut() if t == "!" else SubCall(fname=t, arity=0, args=[])
    if not (type(t) is tuple and t and type(t[0]) is str):
        return Sequence(ops=[])
    f, args = t[0], t[1:]
    n = len(args)
    if f == "," and n == 2:
        return Sequence(ops=[_body_term_ir(args[0]), _body_term_ir(args[1])])
    if f == ";" and n == 2:
        lhs = deref(args[0])
        if type(lhs) is tuple and len(lhs) == 3 and lhs[0] == "->":
            return IfThenElse(test=_body_term_ir(lhs[1]), then=_body_term_ir(lhs[2]),
                              else_=_body_term_ir(args[1]))
        return Alternate(ops=[_body_term_ir(args[0]), _body_term_ir(args[1])])
    if f == "->" and n == 2:
        return IfThenElse(test=_body_term_ir(args[0]), then=_body_term_ir(args[1]),
                          else_=Fail())
    if f == "\\+" and n == 1:
        return Negate(op=_body_term_ir(args[0]))
    if f == ":" and n == 2:
        m, g = deref(args[0]), deref(args[1])
        if type(m) is str:
            if type(g) is str:
                return SubCall(fname=f"{m}.{g}", arity=0, args=[])
            if type(g) is tuple and g and type(g[0]) is str and g[0] not in (",", ";", "->", "\\+", ":"):
                return SubCall(fname=f"{m}.{g[0]}", arity=len(g) - 1, args=list(g[1:]))
        return _body_term_ir(g)
    meta = _meta_terms().get((f, n))
    if meta is not None:
        kind, positions = meta
        margs = {}
        for i, key in positions.items():
            g = deref(args[i - 1])
            while kind in ("bagof", "setof") and type(g) is tuple and len(g) == 3 and g[0] == "^":
                g = deref(g[2])
            margs[key] = _body_term_ir(g)
        return MetaCall(kind=kind, args=margs)
    return SubCall(fname=f, arity=n, args=list(args))


def _is_tabled_call(fname: str, arity: int, db) -> bool:
    """Does the call ``fname/arity`` (as compiled against *db*) reach a
    table?  A qualified ``M.g`` whose M is ``user`` or *db*'s own module
    names the LOCAL predicate g: the qualifier is stripped before the lookup
    (the dotted spelling is not a key of the local table)."""
    from .tabled_naf import _resolve_tabled_call
    if _resolve_tabled_call(fname, arity, db) is not None:
        return True
    mod, dot, base = fname.rpartition(".")
    if dot and mod and base and db is not None:
        own = getattr(db, "module_name", None)
        own = own() if callable(own) else own
        if mod == "user" or mod == own:
            return _resolve_tabled_call(base, arity, db) is not None
    return False


def _pi_text(pi: "tuple[str, int]") -> str:
    """ISO spelling of a predicate indicator: ``lib_t:lt/1`` for the dotted
    ``lib_t.lt`` an imported call compiles to."""
    name, arity = pi
    if "." in name:
        mod, _, base = name.rpartition(".")
        if mod and base:
            return f"{mod}:{base}/{arity}"
    return f"{name}/{arity}"


def tabled_calls_in_cut_scope(ir: GoalOp, db) -> list[tuple[str, int]]:
    """Calls to tabled predicates that a ``Cut`` (or an ``IfThenElse``
    condition's commit, or ``once/1``) would cut over: every tabled call
    executed before the cut in the same barrier scope.  XSB's compile-time
    rule.

    A barrier (``\\+``, an ITE condition, a meta-call's goal, call/N's
    literal goal) is a scope of its own: it is scanned with an empty "before"
    list, so a cut inside it is checked against the tabled calls in IT.  The
    tabled calls of a barrier whose choice points survive it (call/N,
    catch/3's goal, ...) then join the enclosing scope's list.  ``once/1``
    commits like ``( G -> true )``.  ``\\+`` and findall/bagof/setof/
    forall/count_all are not cuts and leave no choice points behind.

    Goals built at run time (``G = (tf(X), !), call(G)``), and tabled
    predicates reached through an untabled one, are not seen: no static rule
    can.  As in XSB, the run-time half covers them: a cut that would prune a
    tabled call over an INCOMPLETE table raises (``tabling.
    cut_over_incomplete``, the Cut arm's ``cut_check_stmts``)."""
    from .ir import META_GOAL_POSITIONS, MetaCall, Negate, SubCall
    found: list[tuple[str, int]] = []

    def report(xs) -> None:
        found.extend(x for x in xs if x not in found)

    def join(left, xs) -> None:
        left.extend(x for x in xs if x not in left)

    def scan(op: GoalOp, left: list) -> None:
        match op:
            case Sequence(ops=ops):
                for o in ops:
                    scan(o, left)
            case Alternate(ops=ops):
                before = list(left)
                for o in ops:
                    branch = list(before)
                    scan(o, branch)
                    join(left, branch)
            case Cut():
                report(left)
            case IfThenElse(test=t, then=th, else_=el):
                inner: list = []
                scan(t, inner)                 # the commit cuts over the test's calls
                report(inner)
                before = list(left)
                scan(th, left)
                alt = before
                scan(el, alt)
                join(left, alt)
            case Branch(test=t, then=th, else_=el):
                scan(t, left)
                before = list(left)
                scan(th, left)
                alt = before
                scan(el, alt)
                join(left, alt)
            case Negate(op=inner_op):
                scan(inner_op, [])
            case MetaCall(kind=kind, args=margs):
                from .terms_to_goalop import _convert
                for key in META_GOAL_POSITIONS.get(kind, ()):
                    if key not in margs:
                        continue
                    inner = margs[key]
                    if not isinstance(inner, GoalOp):
                        try:
                            inner = _convert(inner, db)
                        except NotImplementedError:
                            continue
                    sub: list = []
                    scan(inner, sub)
                    if (kind, key) in _COMMITS:
                        report(sub)
                    elif (kind, key) in _TRANSPARENT_TO_CHOICE_POINTS:
                        join(left, sub)
            case SubCall(fname="call"):
                inner = _literal_call_goal(op, db)
                if inner is not None:
                    sub = []
                    scan(inner, sub)           # call/N is a barrier ...
                    join(left, sub)            # ... its choice points are not
            case SubCall():
                pi = (op.fname, op.arity)
                if pi not in left and _is_tabled_call(op.fname, op.arity, db):
                    left.append(pi)
            case _:
                pass

    scan(ir, [])
    return found


#: The names a construct that commits can be spelled with, in any shape
#: the scan converts: ``!`` and ``->`` cells, once/setup_call_cleanup
#: (as a ``LoadName``, a ``MetaCall`` kind, a cell functor or a call/N
#: closure atom).
_COMMIT_NAMES = frozenset({"!", "->", "once", "setup_call_cleanup"})


def _raw_may_commit(t) -> bool:
    """:func:`_may_commit` for a raw goal TERM (a meta-call's goal, call/N's
    arguments), which the scan converts: any commit node, or any string
    spelled like a commit, anywhere in it."""
    from clausal.logic.variables import Var, deref
    from clausal.pythonic_ast import nodes
    stack = [t]
    while stack:
        t = stack.pop()
        if isinstance(t, Var):
            t = deref(t)
            if isinstance(t, Var):
                continue
        if type(t) is str:
            if t in _COMMIT_NAMES:
                return True
        elif isinstance(t, (nodes.Cut, nodes.IfThenElse, Cut, IfThenElse)):
            return True
        elif isinstance(t, (tuple, list)):
            stack.extend(t)
        elif isinstance(t, dict):
            stack.extend(t.values())
        elif hasattr(t, "__dataclass_fields__"):
            stack.extend(getattr(t, f, None) for f in t.__dataclass_fields__)
    return False


def _may_commit(ir) -> bool:
    """Cheap pre-check for :func:`tabled_calls_in_cut_scope`: can anything
    in *ir* commit -- a ``Cut``, an ``IfThenElse``, once/1 or
    setup_call_cleanup/3?  The scan reports only at such a commit, so False
    proves it would report nothing.  It walks exactly the goal positions
    the scan walks, with no conversion and no table lookups; a raw goal
    term (a meta-call's goal, call/N's arguments) counts if it holds a
    commit in any spelling (:func:`_raw_may_commit`)."""
    from .ir import META_GOAL_POSITIONS, MetaCall, Negate, SubCall
    stack = [ir]
    while stack:
        op = stack.pop()
        match op:
            case Cut() | IfThenElse():
                return True
            case Sequence(ops=ops) | Alternate(ops=ops):
                stack.extend(ops)
            case Branch(test=t, then=th, else_=el):
                stack.extend((t, th, el))
            case Negate(op=inner):
                stack.append(inner)
            case MetaCall(kind=kind, args=margs):
                if kind in _COMMIT_NAMES:
                    return True
                for key in META_GOAL_POSITIONS.get(kind, ()):
                    inner = margs.get(key)
                    if isinstance(inner, GoalOp):
                        stack.append(inner)
                    elif inner is not None and _raw_may_commit(inner):
                        return True
            case SubCall(fname="call"):
                if _raw_may_commit(op.args):
                    return True
            case _:
                pass
    return False


def check_cut_over_tabled(ir: GoalOp, db, goals=()) -> None:
    """Raise :class:`~.ir.CutOverTableError` if a cut in *ir* would cut over
    a tabled call -- under :data:`CUT_OVER_TABLED_CALL` ``== "refuse"``.

    Only a ``.pl`` db can hold a ``Cut``/``IfThenElse`` node (the converter
    refuses them elsewhere), so every other body returns before the walk:
    cut-free code pays one attribute read.  A ``.pl`` body that cannot
    commit (:func:`_may_commit`) skips the scan."""
    if CUT_OVER_TABLED_CALL != "refuse":
        return
    from clausal.logic.builtins.call_body import cut_allowed
    if not cut_allowed(db) or not _may_commit(ir):
        return
    over = tabled_calls_in_cut_scope(ir, db)
    if over:
        from .ir import CutOverTableError
        pos = next((p for p in (getattr(g, "position", None) for g in goals)
                    if p), None)
        raise CutOverTableError(over, line=pos[0] if pos else None)
