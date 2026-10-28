"""Mark the answers a compiled predicate KNOWS are its last (``FINAL``).

CONTINUATION_TCO_PLAN Phase 4 (the ``commit`` variant,
``implementation_plans/compiler/todo/commit_yield_determinism.md``): a
trampoline generator may answer ``yield (_proceed, FINAL)`` instead of
``yield (_proceed, None)`` when it has no alternative left after that answer,
and a frame making a tail call (continuation-TCO) sets
``this_generator.tail_final`` when it has none left after the call, so the
callee's own FINAL holds for it too (the drive core's ``final_holds``).

This is a post-pass over the finished ``FunctionDef``, not part of lowering:
the generated code is regular, and reading it back is the one place every
emitter's shape is visible at once.  Soundness over coverage -- a shape the
pass does not recognise keeps its plain ``None``:

- an answer is a candidate only on a path through ``If``/``Match`` arms,
  ``try`` blocks whose only handler is the ``GeneratorExit`` bookkeeping,
  the loop of a sub-call (``while _st is not $DONE``, whose answer must
  itself be FINAL: the condition ``_st is $FINAL`` is added), a goal
  boundary ``for _ in $unify_iter(...)`` / ``$pending(trail)`` (FINAL only
  when no woken goal is draining: the iterable is the shared ``range(1)``,
  ``$ONCE``), and a ``for`` loop that ends in ``break`` (``once/1``);
- every statement that would run after the answer, on the way out of the
  generator, must be inert -- a trail undo, a flag, the terminal
  ``yield (_fail, $DONE)`` -- so a later clause arm, a second disjunct, a
  catch/3 handler or any loop the pass does not know keeps the answer
  non-final;
- a TRO function (its body restarts in place) is never touched.

A frame still pulls a child again after the child's FINAL answer (and
hears DONE).  Breaking out instead saved that pull but left the child
suspended: its generator frame and its ``StepGenerator`` refer to each
other, so it lived on as cyclic garbage until a collection (q_bench ran
~8% slower over a few repetitions from the extra collections), and its
bindings had to be undone by someone else.  The drivers report a FINAL
(``solve_with_last``) and still pull the search to its end.
"""

from __future__ import annotations

import ast
import copy

from ._ast_helpers import _name

_FINAL = "$FINAL"
_DONE = "$DONE"
_ONCE = "$ONCE"
_GOAL_BOUNDARY_ITERS = frozenset({"$unify_iter", "$pending"})


class _Names:
    __slots__ = ("self_name", "proceed", "fail", "fresh", "later_excluded",
                 "later_excluded_arms")

    def __init__(self, self_name, proceed, fail, later_excluded=None):
        self.self_name, self.proceed, self.fail = self_name, proceed, fail
        self.fresh = 0
        # ({id(clause arm Match): test that no later arm can match the
        # call}, {id(every clause arm Match)})
        self.later_excluded, self.later_excluded_arms = (
            later_excluded or ({}, frozenset()))


def _is_name(node, ident) -> bool:
    return type(node) is ast.Name and node.id == ident


def _yield_pair(stmt):
    """``(target, value)`` of a statement ``yield (target, value)``, else None."""
    if type(stmt) is ast.Expr and type(stmt.value) is ast.Yield:
        v = stmt.value.value
        if type(v) is ast.Tuple and len(v.elts) == 2:
            return v.elts
    return None


def _is_leaf_yield(stmt, n: _Names) -> bool:
    pair = _yield_pair(stmt)
    return (pair is not None and _is_name(pair[0], n.proceed)
            and type(pair[1]) is ast.Constant and pair[1].value is None)


def _is_exhaustion(stmt, n: _Names) -> bool:
    pair = _yield_pair(stmt)
    return pair is not None and _is_name(pair[0], n.fail) and _is_name(pair[1], _DONE)


def _pull(stmt):
    """``(status, gen)`` for ``_st = (yield (_gen, None))``, else None."""
    if (type(stmt) is ast.Assign and len(stmt.targets) == 1
            and type(stmt.targets[0]) is ast.Name
            and type(stmt.value) is ast.Yield):
        v = stmt.value.value
        if (type(v) is ast.Tuple and len(v.elts) == 2
                and type(v.elts[0]) is ast.Name
                and type(v.elts[1]) is ast.Constant and v.elts[1].value is None):
            return stmt.targets[0].id, v.elts[0].id
    return None


def _gen_assign(stmt):
    """``(gen, proceed_arg)`` for ``_gen = $StepGenerator(fn, proceed, ...)``."""
    if (type(stmt) is ast.Assign and len(stmt.targets) == 1
            and type(stmt.targets[0]) is ast.Name
            and type(stmt.value) is ast.Call
            and _is_name(stmt.value.func, "$StepGenerator")
            and len(stmt.value.args) >= 4):
        return stmt.targets[0].id, stmt.value.args
    return None


def _status_loop(stmt, status, gen):
    """True for ``while status is not $DONE: ...; status = yield (gen, None)``."""
    if type(stmt) is not ast.While or stmt.orelse:
        return False
    t = stmt.test
    if not (type(t) is ast.Compare and _is_name(t.left, status)
            and len(t.ops) == 1 and type(t.ops[0]) is ast.IsNot
            and len(t.comparators) == 1 and _is_name(t.comparators[0], _DONE)):
        return False
    return bool(stmt.body) and _pull(stmt.body[-1]) == (status, gen)


def _sub_call(stmts, i):
    """The sub-call starting at ``stmts[i]``: ``(gen, args, status, loop)``.

    The emitted shape (strategy.TrampolineStrategy.emit_sub_call)::

        _gen = $StepGenerator(dispatch, proceed, self, self, *args, trail)
        _st = (yield (_gen, None))
        while _st is not $DONE:
            <continuation>
            _st = (yield (_gen, None))
    """
    ga = _gen_assign(stmts[i])
    if ga is None or i + 2 >= len(stmts):
        return None
    gen, args = ga
    p = _pull(stmts[i + 1])
    if p is None or p[1] != gen:
        return None
    status = p[0]
    loop = stmts[i + 2]
    if not _status_loop(loop, status, gen):
        return None
    return gen, args, status, loop


# ── inertness ────────────────────────────────────────────────────────────────


def _inert_expr(node) -> bool:
    return type(node) in (ast.Name, ast.Constant) or (
        type(node) is ast.UnaryOp and type(node.op) is ast.Not
        and type(node.operand) is ast.Name)


def _inert(stmt, n: _Names) -> bool:
    """A statement that runs no goal, binds nothing a caller sees and
    produces no answer."""
    t = type(stmt)
    if t is ast.Pass:
        return True
    if t is ast.Expr and type(stmt.value) is ast.Call:
        c = stmt.value
        # trail.undo(mark)
        return (type(c.func) is ast.Attribute and c.func.attr == "undo"
                and type(c.func.value) is ast.Name and not c.keywords
                and all(type(a) is ast.Name for a in c.args))
    if t is ast.Assign:
        return (len(stmt.targets) == 1 and type(stmt.targets[0]) is ast.Name
                and _inert_expr(stmt.value))
    if t is ast.If:
        return (_inert_expr(stmt.test) and _inert_block(stmt.body, n)
                and _inert_block(stmt.orelse, n))
    return False


def _inert_block(stmts, n: _Names) -> bool:
    for s in stmts:
        if _is_exhaustion(s, n) or type(s) in (ast.Return, ast.Break):
            return True         # nothing after it runs in this block
        if not _inert(s, n):
            return False
    return True


def _generator_exit_only(handlers) -> bool:
    """The ``except $GeneratorExit: _mark_cl = True; raise`` bookkeeping
    every clause arm carries, and nothing else."""
    return all(_is_name(h.type, "$GeneratorExit") for h in handlers)


# ── the walk ─────────────────────────────────────────────────────────────────


class _Site:
    """A candidate: a leaf answer (``kind == "leaf"``) or a tail call
    (``"tail"``), with the conditions under which it is final."""
    __slots__ = ("kind", "block", "stmt", "conds")

    def __init__(self, kind, block, stmt, conds):
        self.kind, self.block, self.stmt, self.conds = kind, block, stmt, conds


def _walk_block(stmts, conds, ok, n: _Names, out: list, end=None) -> None:
    """Walk ``stmts[:end]`` (the list itself, so a site can be inserted
    into it); what follows *end* in *stmts* is accounted for by the caller."""
    if end is None:
        end = len(stmts)
    i = 0
    while i < end:
        st = stmts[i]
        here = ok and _inert_block(stmts[i + 1:end], n)
        if ok and not here and id(st) in n.later_excluded:
            # A clause arm followed by later arms: final when the call's
            # first argument rules every one of them out.
            rest = stmts[i + 1:end]
            j = 0
            while j < len(rest) and id(rest[j]) in n.later_excluded_arms:
                j += 1
            if j and _inert_block(rest[j:], n):
                _walk_stmt(st, stmts, conds + [n.later_excluded[id(st)]],
                           True, n, out)
                i += 1
                continue
        sc = _sub_call(stmts, i) if i + 2 < end else None
        if sc is not None:
            gen, args, status, loop = sc
            here = ok and _inert_block(stmts[i + 3:end], n)
            if _is_name(args[1], n.proceed) and len(loop.body) == 1:
                # A tail call: the child answers our caller directly.
                if here:
                    out.append(_Site("tail", stmts, st, conds))
            elif _is_name(args[1], n.self_name):
                # The continuation runs once per child answer; it is final
                # only after the child's own last answer.
                cond = ast.Compare(left=_name(status), ops=[ast.Is()],
                                   comparators=[_name(_FINAL)])
                _walk_block(loop.body, conds + [cond], here, n, out,
                            end=len(loop.body) - 1)
            i += 3
            continue
        _walk_stmt(st, stmts, conds, here, n, out)
        i += 1


def _walk_stmt(st, block, conds, ok, n: _Names, out: list) -> None:
    t = type(st)
    if _is_leaf_yield(st, n):
        if ok:
            out.append(_Site("leaf", block, st, conds))
        return
    if t is ast.If:
        _walk_block(st.body, conds, ok, n, out)
        _walk_block(st.orelse, conds, ok, n, out)
    elif t is ast.Match:
        for case in st.cases:
            _walk_block(case.body, conds, ok, n, out)
    elif t is ast.Try:
        plain = _generator_exit_only(st.handlers) and not st.orelse
        body_ok = ok and plain and _inert_block(st.finalbody, n)
        _walk_block(st.body, conds, body_ok, n, out)
    elif t is ast.For and not st.orelse:
        it = st.iter
        if (type(it) is ast.Call and type(it.func) is ast.Name
                and it.func.id in _GOAL_BOUNDARY_ITERS):
            # Runs its body once -- unless the unification woke goals,
            # whose drain answers once per answer of theirs.
            _walk_goal_boundary(st, conds, ok, n, out)
        elif st.body and type(st.body[-1]) is ast.Break:
            # ``for _ in G(): ...; break`` -- at most one pass (once/1).
            _walk_block(st.body, conds, ok, n, out, end=len(st.body) - 1)
    # Anything else (other loops, with, nested defs) is left alone: an
    # answer under it keeps its plain None.


def _walk_goal_boundary(st, conds, ok, n: _Names, out: list) -> None:
    if not ok:
        return
    # Name the iterable, so the answer can ask whether it is the shared
    # ``range(1)`` (no woken goal) rather than a drain.  Only a loop that
    # holds a site is rewritten: the others keep their unnamed iterable.
    n.fresh += 1
    it_name = f"_fin_it{n.fresh}"
    cond = ast.Compare(left=_name(it_name), ops=[ast.Is()],
                       comparators=[_name(_ONCE)])
    before = len(out)
    _walk_block(st.body, conds + [cond], ok, n, out)
    if len(out) > before:
        st._final_iter = it_name                  # see _NameIters


# ── rewriting ────────────────────────────────────────────────────────────────


def _cond_expr(conds):
    if len(conds) == 1:
        return conds[0]
    return ast.BoolOp(op=ast.And(), values=list(conds))


def _final_value(conds):
    if not conds:
        return _name(_FINAL)
    return ast.IfExp(test=_cond_expr(conds), body=_name(_FINAL),
                     orelse=ast.Constant(None))


def _set_tail_final(self_name):
    return ast.Assign(
        targets=[ast.Attribute(value=_name(self_name), attr="tail_final",
                               ctx=ast.Store())],
        value=ast.Constant(True))


class _NameIters(ast.NodeTransformer):
    """``for _ in $unify_iter(...)`` -> ``_fin_itN = $unify_iter(...)`` then
    ``for _ in _fin_itN`` for the loops a site depends on."""

    def generic_visit(self, node):
        for field, old in ast.iter_fields(node):
            if isinstance(old, list):
                new = []
                for s in old:
                    if isinstance(s, ast.AST):
                        s = self.visit(s)
                    name = getattr(s, "_final_iter", None)
                    if name is not None:
                        assign = ast.Assign(
                            targets=[ast.Name(id=name, ctx=ast.Store())],
                            value=s.iter)
                        ast.copy_location(assign, s)
                        s.iter = _name(name)
                        del s._final_iter
                        new.append(assign)
                    new.append(s)
                old[:] = new
            elif isinstance(old, ast.AST):
                self.visit(old)
        return node


def _unshare(node, seen: set) -> None:  # noqa: C901
    """Make every statement object occur once in the tree.  Lowering threads
    one continuation into several places (both arms of a disjunction get
    the same ``k_stmts``), and a site is final in one place and not in the
    other: each occurrence must be its own node before any is rewritten."""
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            if id(value) in seen:           # the statement LIST is shared too
                value = list(value)
                setattr(node, field, value)
            seen.add(id(value))
            for i, item in enumerate(value):
                if not isinstance(item, ast.AST):
                    continue
                if isinstance(item, ast.stmt):
                    if id(item) in seen:
                        item = value[i] = copy.deepcopy(item)
                    seen.add(id(item))
                _unshare(item, seen)
        elif isinstance(value, ast.AST):
            _unshare(value, seen)


def mark_final_yields(func_def: ast.FunctionDef, *, self_name: str,
                      proceed_name: str, fail_name: str,
                      later_excluded=None) -> int:
    """Rewrite *func_def* in place; return how many sites it marked.

    *later_excluded* is ``(conds, arms)``: the clause arms (top-level
    ``match`` statements, by id) and, per arm, the runtime test under which
    no later arm can match the call (first-argument keys)."""
    n = _Names(self_name, proceed_name, fail_name, later_excluded)
    _unshare(func_def, set())
    sites: list[_Site] = []
    _walk_block(func_def.body, [], True, n, sites)
    for site in sites:
        idx = next(j for j, s in enumerate(site.block) if s is site.stmt)
        if site.kind == "leaf":
            new = ast.Expr(value=ast.Yield(value=ast.Tuple(
                elts=[_name(proceed_name), _final_value(site.conds)],
                ctx=ast.Load())))
            site.block[idx] = ast.copy_location(new, site.stmt)
        else:
            mark = _set_tail_final(self_name)
            if site.conds:
                mark = ast.If(test=_cond_expr(site.conds), body=[mark], orelse=[])
            ast.copy_location(mark, site.stmt)
            site.block.insert(idx, mark)
    _NameIters().visit(func_def)
    ast.fix_missing_locations(func_def)
    return len(sites)


__all__ = ["mark_final_yields"]
