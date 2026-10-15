"""Where a cut lands (ISO 7.8.4 scope rules on the GoalOp IR)."""
from __future__ import annotations

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
#: Scryer; pinned in tests/iso_l3/test_l3_cut_tabling.py).  THE ONE SWITCH:
#: :func:`check_cut_over_tabled` is the only reader, and the only caller is
#: ``goal_shallow._compile_body_impl``.
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
_COMMITS = frozenset({("once", "inner")})


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


_META_TERMS = {
    # functor/arity -> (MetaKind, the goal-argument positions as arg keys)
    ("once", 1): ("once", {1: "inner"}),
    ("findall", 3): ("findall", {2: "inner"}),
    ("findall", 4): ("findall", {2: "inner"}),
    ("bagof", 3): ("bagof", {2: "inner"}),
    ("setof", 3): ("setof", {2: "inner"}),
    ("forall", 2): ("forall", {1: "cond", 2: "action"}),
    ("catch", 3): ("catch", {1: "inner", 3: "recovery"}),
}


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
    meta = _META_TERMS.get((f, n))
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

    Goals built at run time (``G = (tf(X), !), call(G)``) are not seen: no
    static rule can (XSB pairs its static rule with a run-time check)."""
    from .tabled_naf import _resolve_tabled_call
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
                if pi not in left and _resolve_tabled_call(op.fname, op.arity, db) is not None:
                    left.append(pi)
            case _:
                pass

    scan(ir, [])
    return found


def check_cut_over_tabled(ir: GoalOp, db, goals=()) -> None:
    """Raise :class:`~.ir.CutOverTableError` if a cut in *ir* would cut over
    a tabled call -- under :data:`CUT_OVER_TABLED_CALL` ``== "refuse"``.

    Only a ``.pl`` db can hold a ``Cut``/``IfThenElse`` node (the converter
    refuses them elsewhere), so every other body returns before the walk:
    cut-free code pays one attribute read."""
    if CUT_OVER_TABLED_CALL != "refuse":
        return
    from clausal.logic.builtins.call_body import cut_allowed
    if not cut_allowed(db):
        return
    over = tabled_calls_in_cut_scope(ir, db)
    if over:
        from .ir import CutOverTableError
        pos = next((p for p in (getattr(g, "position", None) for g in goals)
                    if p), None)
        raise CutOverTableError(over, line=pos[0] if pos else None)
