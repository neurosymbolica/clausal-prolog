"""
codegen.py — Compile Python AST nodes into callable functions.
"""

import ast
import builtins as _builtins

__all__ = [
    "GeneratedCodeError",
    "functiondef_to_function",
    "split_deep_nesting",
    "stmts_to_function",
]

_BUILTIN_NAMES = frozenset(vars(_builtins))


def _infer_args(stmts: list[ast.stmt], globals_: dict | None = None) -> ast.arguments:
    """Infer positional parameters by scanning name loads before assignments.

    A name becomes a parameter if it is loaded before it is assigned anywhere
    in ``stmts`` (at the top-level scope only — nested functions, classes,
    lambdas, and comprehensions introduce their own scopes and are not
    descended into, except that the outermost iterable of a comprehension IS
    evaluated in the enclosing scope).  Built-in names and names present in
    ``globals_`` are excluded (they are already available, not arguments).

    Order is the order of first qualifying load.
    """
    assigned: set[str] = set()
    params: list[str] = []
    seen: set[str] = set()
    excluded = _BUILTIN_NAMES if not globals_ else _BUILTIN_NAMES | globals_.keys()

    class _Scanner(ast.NodeVisitor):
        # ── nested scopes: record the name being bound, but do not descend ─────
        def visit_FunctionDef(self, node):
            assigned.add(node.name)
        visit_AsyncFunctionDef = visit_FunctionDef
        def visit_ClassDef(self, node):
            assigned.add(node.name)
        def visit_Lambda(self, node): pass

        # Only the outermost iterable of a comprehension is in the enclosing scope.
        def _comp(self, node):
            self.visit(node.generators[0].iter)
        visit_ListComp = _comp
        visit_SetComp = _comp
        visit_DictComp = _comp
        visit_GeneratorExp = _comp

        # ── name handling ─────────────────────────────────────────────────────
        def _record_load(self, name: str):
            if name not in assigned and name not in seen and name not in excluded:
                params.append(name)
                seen.add(name)

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                self._record_load(node.id)
            elif isinstance(node.ctx, (ast.Store, ast.Del)):
                assigned.add(node.id)

        # ── assignment ordering: value (RHS) must be visited before targets ──
        def visit_Assign(self, node):
            self.visit(node.value)
            for target in node.targets:
                self.visit(target)

        def visit_AnnAssign(self, node):
            if node.value:
                self.visit(node.value)
            self.visit(node.target)

        def visit_NamedExpr(self, node):
            # A10-F015: walrus `(x := expr)` evaluates value before binding the
            # target, like Assign — the generic (target, value) field order
            # would mark the target assigned before scanning the value.
            self.visit(node.value)
            self.visit(node.target)

        def visit_AugAssign(self, node):
            # Read-modify-write: target is implicitly loaded before being stored.
            if isinstance(node.target, ast.Name):
                self._record_load(node.target.id)
                assigned.add(node.target.id)
            else:
                self.visit(node.target)   # Attribute/Subscript: object is Load
            self.visit(node.value)

        # ── for loop: evaluate iterable before assigning loop target ─────────
        def visit_For(self, node):
            self.visit(node.iter)
            self.visit(node.target)
            for s in node.body:
                self.visit(s)
            for s in node.orelse:
                self.visit(s)

        # ── global/nonlocal: treat as already available, not parameters ──────
        def visit_Global(self, node):
            for name in node.names:
                assigned.add(name)

        def visit_Nonlocal(self, node):
            for name in node.names:
                assigned.add(name)

    scanner = _Scanner()
    for stmt in stmts:
        scanner.visit(stmt)

    return ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=name) for name in params],
        vararg=None,
        kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
    )


# ── Static block nesting ──────────────────────────────────────────────────────
#
# CPython refuses a function whose blocks nest more than CO_MAXBLOCKS deep
# (20 in a generator, whose body sits inside an implicit StopIteration block;
# 21 otherwise): ``SyntaxError: too many statically nested blocks``.  The
# clause compiler opens one loop per backtracking call around the REST of the
# body (``while _st is not DONE: <continuation>``), so a clause body with ~19
# user calls nested past the limit and the module failed to load.
#
# ``split_deep_nesting`` keeps every generated function under the limit by
# OUTLINING, bottom-up: a statement whose blocks nest ``_OUTLINE_HEIGHT``
# deep moves into a nested helper function -- a generator delegated to with
# ``yield from`` when it yields, a plain call otherwise -- and the helper
# starts a fresh block stack.  Each name then gets the innermost scope that
# can own it without changing what any mention reads (``_Outliner.localise``):
# helpers below the owner that bind it declare it ``nonlocal``.  A ``return``
# in moved code comes back as a 1-tuple and is re-returned; a ``break`` or
# ``continue`` is never separated from its loop.
#
# ``functiondef_to_function`` runs the pass only after CPython has refused
# the nesting, so functions under the limit -- everything but a very long
# clause body -- compile exactly as before, at no extra cost.

#: The deepest block nesting a generated function may reach, counted with the
#: generator's own implicit block -- CPython raises past 20.
_MAX_BLOCK_DEPTH = 20
#: The nesting height at which a statement is outlined.  Leaves the helper and
#: the statements around the call to it a margin under the limit.
_OUTLINE_HEIGHT = 12

_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_LOOP_NODES = (ast.For, ast.While, ast.AsyncFor)
_TRY_NODES = (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)


def _child_lists(stmt: ast.stmt) -> list[tuple[int, ast.AST, str]]:
    """``(added_depth, owner, field)`` for each statement list nested in
    *stmt*, by CPython 3.13's frame-block accounting (measured): a loop or
    ``with`` body +1 (``async with`` +2); a ``try`` body +1, or +2 when it
    has both ``except`` handlers and a ``finally`` (CPython nests a
    try/except inside a try/finally); an ``except`` handler +2 (handler and
    cleanup), +3 under a ``finally``; a ``finally`` body +1; a ``try``'s
    ``else`` +1 under a ``finally``, else +0; ``if``/``match`` bodies and a
    loop's ``else`` +0.  Nested function and class bodies are scopes of
    their own and are not listed."""
    if isinstance(stmt, _LOOP_NODES):
        return [(1, stmt, "body"), (0, stmt, "orelse")]
    if isinstance(stmt, ast.With):
        return [(1, stmt, "body")]
    if isinstance(stmt, ast.AsyncWith):
        return [(2, stmt, "body")]
    if isinstance(stmt, _TRY_NODES):
        fin = 1 if stmt.finalbody else 0
        both = 1 if (stmt.finalbody and stmt.handlers) else 0
        return ([(1 + both, stmt, "body"), (fin, stmt, "orelse"),
                 (1, stmt, "finalbody")]
                + [(2 + fin, h, "body") for h in stmt.handlers])
    if isinstance(stmt, ast.If):
        return [(0, stmt, "body"), (0, stmt, "orelse")]
    if isinstance(stmt, ast.Match):
        return [(0, c, "body") for c in stmt.cases]
    return []


def _postorder(stmts: list[ast.stmt]) -> list[ast.stmt]:
    """The statements of one scope (nested scopes excluded), children before
    parents.  Iterative: the trees this exists for nest hundreds deep."""
    out: list[ast.stmt] = []
    stack = [(s, False) for s in reversed(stmts)]
    while stack:
        s, done = stack.pop()
        if done:
            out.append(s)
            continue
        stack.append((s, True))
        for _, owner, field in reversed(_child_lists(s)):
            stack.extend((c, False) for c in reversed(getattr(owner, field)))
    return out


def _height(stmt: ast.stmt, heights: dict) -> int:
    return max((add + max((heights[id(c)] for c in getattr(owner, field)), default=0)
                for add, owner, field in _child_lists(stmt)), default=0)


def _function_depths(node) -> list[tuple[ast.AST, int]]:
    """``(function, deepest nesting)`` for *node* and every function defined
    in it, the nesting counting the generator block.  One statement-level
    walk: functions only nest at statement level (a lambda holds no blocks)."""
    out = []
    work = [node]
    while work:
        fn = work.pop()
        heights: dict = {}
        for s in _postorder(fn.body):
            heights[id(s)] = _height(s, heights)
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                work.append(s)
            elif isinstance(s, ast.ClassDef):
                work.extend(x for x in ast.walk(s)
                            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)))
        out.append((fn, 1 + max((heights[id(s)] for s in fn.body), default=0)))
    return out


def _walk_same_scope(node: ast.AST):
    """Every node under *node* (inclusive) evaluated in *node*'s scope: does
    not descend into nested function, lambda or class bodies."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for c in ast.iter_child_nodes(n):
            if isinstance(c, _SCOPE_NODES):
                # The def binds its name here, and its decorators, defaults
                # (and a class's bases) are evaluated here.
                yield c
                stack.extend(getattr(c, "decorator_list", ()))
                if isinstance(c, ast.ClassDef):
                    stack.extend(c.bases)
                    stack.extend(c.keywords)
                else:
                    stack.extend(d for d in c.args.defaults + c.args.kw_defaults if d)
            else:
                stack.append(c)


def _bound_names(node: ast.AST) -> set[str]:
    """Names *node* binds in its own scope.  A comprehension's loop target
    binds in the comprehension's own scope and is not counted (a walrus
    inside one still binds here, and is)."""
    out: set[str] = set()
    comp_targets: set[int] = set()
    for n in _walk_same_scope(node):
        if isinstance(n, ast.comprehension):
            comp_targets.update(id(t) for t in ast.walk(n.target))
        elif (isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))
                and id(n) not in comp_targets):
            out.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.MatchMapping) and n.rest:
            out.add(n.rest)
    return out


def _can_outline(stmt: ast.stmt) -> bool:
    """False when moving *stmt* into a helper would change what it means: a
    ``break``/``continue`` aimed at a loop outside it, or anything async."""
    stack = [(stmt, False)]
    while stack:
        n, in_loop = stack.pop()
        if isinstance(n, _SCOPE_NODES):
            continue
        if isinstance(n, (ast.Break, ast.Continue)) and not in_loop:
            return False
        if isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
            return False
        if isinstance(n, _LOOP_NODES):
            # A loop's ``else`` runs outside it: a break there leaves the
            # enclosing loop.
            stack.extend((x, True) for x in n.body)
            stack.extend((x, in_loop) for x in n.orelse)
            continue
        stack.extend((c, in_loop) for c in ast.iter_child_nodes(n))
    return True


class _Outliner:
    """Outlines one function (``function``); see the comment block above."""

    def __init__(self, globals_declared: set[str]):
        self.globs = globals_declared
        self.counter = 0
        #: The helpers made, in creation order: a helper is made after every
        #: helper it contains.
        self.helpers: list[ast.FunctionDef] = []

    def outline(self, s: ast.stmt) -> list[ast.stmt]:
        """The statements that replace *s*: a helper holding it and a call.
        The helper's ``nonlocal`` declaration is ``localise``'s to write."""
        self.counter += 1
        name = f"$nest{self.counter}"
        res = f"$nest{self.counter}_r"
        global_names = sorted(_bound_names(s) & self.globs)
        has_yield = has_return = False
        for n in _walk_same_scope(s):
            if isinstance(n, (ast.Yield, ast.YieldFrom)):
                has_yield = True
            elif isinstance(n, ast.Return):
                has_return = True
                n.value = ast.Tuple(
                    elts=[n.value if n.value is not None else ast.Constant(None)],
                    ctx=ast.Load())
        body: list[ast.stmt] = []
        if global_names:
            body.append(ast.Global(names=global_names))
        body.append(s)
        extra = {"type_params": []} if "type_params" in ast.FunctionDef._fields else {}
        helper = ast.FunctionDef(
            name=name,
            args=ast.arguments(posonlyargs=[], args=[], vararg=None, kwonlyargs=[],
                               kw_defaults=[], kwarg=None, defaults=[]),
            body=body, decorator_list=[], returns=None, type_comment=None, **extra)
        self.helpers.append(helper)
        call = ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=[], keywords=[])
        value = ast.YieldFrom(value=call) if has_yield else call
        out: list[ast.stmt] = [helper]
        if has_return:
            out.append(ast.Assign(targets=[ast.Name(id=res, ctx=ast.Store())], value=value))
            out.append(ast.If(
                test=ast.Compare(left=ast.Name(id=res, ctx=ast.Load()),
                                 ops=[ast.IsNot()], comparators=[ast.Constant(None)]),
                body=[ast.Return(value=ast.Subscript(
                    value=ast.Name(id=res, ctx=ast.Load()),
                    slice=ast.Constant(0), ctx=ast.Load()))],
                orelse=[]))
        else:
            out.append(ast.Expr(value=value))
        for top in out:
            stack = [top]
            while stack:
                c = stack.pop()
                if c is s:
                    continue
                if "lineno" in c._attributes and getattr(c, "lineno", None) is None:
                    ast.copy_location(c, s)
                stack.extend(ast.iter_child_nodes(c))
        return out

    def function(self, fn) -> None:
        """Outline, bottom-up, every statement of *fn*'s own scope whose
        blocks nest ``_OUTLINE_HEIGHT`` deep; then each outermost statement
        that came to contain a helper (a long clause's whole arm), so the
        clause's own variables belong to that helper rather than to *fn*;
        then declare every name's scope (``localise``)."""
        heights: dict = {}
        marked: set = set()
        holds_helper: set = set()

        def rebuilt(stmts):
            if not any(id(c) in marked for c in stmts):
                return stmts
            out = []
            for c in stmts:
                if id(c) in marked:
                    for x in self.outline(c):
                        heights[id(x)] = 0   # a def and a call
                        out.append(x)
                    holds_helper.add(id(out[-1]))
                    holds_helper.add(id(out[0]))
                else:
                    out.append(c)
            return out

        for s in _postorder(fn.body):
            for _, owner, field in _child_lists(s):
                setattr(owner, field, rebuilt(getattr(owner, field)))
            if any(id(c) in holds_helper for _, o, f in _child_lists(s)
                   for c in getattr(o, f)):
                holds_helper.add(id(s))
            h = _height(s, heights)
            if h >= _OUTLINE_HEIGHT and _can_outline(s):
                marked.add(id(s))
                h = 0
            heights[id(s)] = h
        fn.body = rebuilt(fn.body)

        def hoist(stmts):
            for s in stmts:
                if id(s) not in holds_helper or not _child_lists(s):
                    continue                  # a helper's own def or call
                if _can_outline(s):
                    marked.add(id(s))
                else:
                    for _, o, f in _child_lists(s):
                        hoist(getattr(o, f))
                        setattr(o, f, rebuilt(getattr(o, f)))
        hoist(fn.body)
        fn.body = rebuilt(fn.body)
        self.localise(fn)

    def localise(self, fn) -> None:
        """Give every name the moved code mentions the scope it had.

        Python resolves a name to the innermost function that binds it, so
        each name gets an OWNER -- the innermost scope (*fn* or a helper)
        enclosing every mention of it -- that binds it, and every helper
        below the owner that binds it declares it ``nonlocal``.  A helper
        runs afresh on each call, so a helper may own a name only when its
        value never has to outlive one call: some statement list of the
        helper holds a plain ``name = expr`` (``expr`` not mentioning it), or
        the helper ``def`` of that name, before every other mention (a list
        always runs from its first statement).  Otherwise the owner moves
        out, ending at *fn*, which owns everything it owned before the split
        (an owner that does not bind the name itself gets a never-run
        ``if False: name = None``).

        Owning by the innermost scope keeps closure cells to the names that
        really cross a helper boundary: every cell is allocated on EACH call
        of its function, so making a long clause's names cells of *fn*
        would tax every call of the predicate, whichever clause runs."""
        helpers = self.helpers
        hid = {id(h) for h in helpers}
        deep: dict[int, dict[str, int]] = {}     # id(stmt or helper) -> counts
        own_names: dict[int, set] = {}            # id(scope) -> names mentioned
        binds: dict[int, set] = {}                # id(scope) -> names bound
        parent: dict[int, ast.AST] = {}
        lists_of: dict[int, list] = {}

        def add(into, more):
            for k, v in more.items():
                into[k] = into.get(k, 0) + v

        def direct(stmt):
            """Name counts in *stmt* outside its nested statement lists."""
            c: dict[str, int] = {}
            nested = {id(x) for _, o, f in _child_lists(stmt) for x in getattr(o, f)}
            stack = list(ast.iter_child_nodes(stmt))
            while stack:
                n = stack.pop()
                if id(n) in nested:
                    continue
                if isinstance(n, ast.Name):
                    c[n.id] = c.get(n.id, 0) + 1
                stack.extend(ast.iter_child_nodes(n))
            return c

        for scope in helpers + [fn]:             # children before parents
            mentioned: set = set()
            bound: set = set()
            lists = [scope.body]
            for st in _postorder(scope.body):
                if id(st) in hid:
                    c = dict(deep[id(st)])
                    parent[id(st)] = scope
                    bound.add(st.name)
                else:
                    c = direct(st)
                    mentioned.update(c)
                    bound |= _bound_names_direct(st)
                    for _, o, f in _child_lists(st):
                        lists.append(getattr(o, f))
                        for x in getattr(o, f):
                            add(c, deep[id(x)])
                deep[id(st)] = c
            total: dict[str, int] = {}
            for st in scope.body:
                add(total, deep[id(st)])
            deep[id(scope)] = total
            own_names[id(scope)] = mentioned
            binds[id(scope)] = bound
            lists_of[id(scope)] = lists

        def chain(scope):
            out = [scope]
            while id(out[-1]) in parent:
                out.append(parent[id(out[-1])])
            return out                            # scope, ..., fn

        def can_own(scope, name):
            total = deep[id(scope)].get(name, 0)
            for lst in lists_of[id(scope)]:
                for i, st in enumerate(lst):
                    if deep[id(st)].get(name) or (
                            id(st) in hid and st.name == name):
                        break
                else:
                    continue
                if id(st) in hid and st.name == name:
                    pass                          # the helper ``def`` binds it
                elif not (isinstance(st, ast.Assign) and len(st.targets) == 1
                          and isinstance(st.targets[0], ast.Name)
                          and st.targets[0].id == name
                          and deep[id(st)][name] == 1):
                    continue
                if sum(deep[id(x)].get(name, 0) for x in lst[i:]) == total:
                    return True
            return False

        fixed = ({a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs}
                 | {a.arg for a in (fn.args.vararg, fn.args.kwarg) if a}
                 | {x for st in fn.body if isinstance(st, (ast.Nonlocal, ast.Global))
                    for x in st.names}
                 | self.globs)
        scopes = helpers + [fn]
        names: set = set()
        for sc in scopes:
            names |= own_names[id(sc)] | binds[id(sc)]
        decls: dict[int, list] = {id(h): [] for h in helpers}
        keeps: dict[int, list] = {id(sc): [] for sc in scopes}
        for name in sorted(names):
            users = [sc for sc in scopes
                     if name in own_names[id(sc)] or name in binds[id(sc)]]
            binders = [sc for sc in users if name in binds[id(sc)]]
            if name in self.globs:
                continue                          # ``global`` already declared
            if name in fixed:
                owner = fn
            else:
                # The innermost scope enclosing every user ...
                common = None
                for sc in users:
                    c = chain(sc)
                    common = c if common is None else [x for x in common if
                                                      any(x is y for y in c)]
                owner = common[0]
                # ... moved out until its value need not outlive one call.
                while owner is not fn and not can_own(owner, name):
                    owner = parent[id(owner)]
            for sc in binders:
                if sc is not owner:
                    decls[id(sc)].append(name)
            if owner is fn and name not in fixed and name not in binds[id(fn)] and any(
                    sc is not fn for sc in binders):
                keeps[id(fn)].append(name)
        for h in helpers:
            if decls[id(h)]:
                d = ast.Nonlocal(names=decls[id(h)])
                ast.copy_location(d, h)
                h.body.insert(0, d)
        if keeps[id(fn)]:
            keep = ast.If(
                test=ast.Constant(False),
                body=[ast.Assign(targets=[ast.Name(id=k, ctx=ast.Store())],
                                 value=ast.Constant(None)) for k in keeps[id(fn)]],
                orelse=[])
            for c in ast.walk(keep):
                ast.copy_location(c, fn.body[0])
            fn.body.insert(0, keep)


def _bound_names_direct(stmt: ast.stmt) -> set[str]:
    """Names *stmt* binds outside its nested statement lists (and outside
    the body of a function or class it defines)."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {stmt.name}
    nested = {id(x) for _, o, f in _child_lists(stmt) for x in getattr(o, f)}
    out: set[str] = set()
    if nested:
        for c in ast.iter_child_nodes(stmt):
            if id(c) in nested:
                continue
            if isinstance(c, (ast.ExceptHandler,)):
                if c.name:
                    out.add(c.name)
                out |= _bound_names(c.type) if c.type else set()
            elif isinstance(c, ast.match_case):
                out |= _bound_names(c.pattern)
                if c.guard is not None:
                    out |= _bound_names(c.guard)
            else:
                out |= _bound_names(c)
        return out
    return _bound_names(stmt)


def split_deep_nesting(node: ast.FunctionDef | ast.AsyncFunctionDef,
                       *, force: bool = False) -> bool:
    """Outline statements of *node* (and of the functions defined in it) that
    would nest blocks past CPython's static limit.  Mutates *node*; returns
    True when anything moved, False -- touching nothing -- for a function
    already under the limit."""
    moved = False
    # *force*: CPython has already refused *node*, so split every function
    # deep enough to hold an outlinable statement, even one this count puts
    # under the limit -- the count is a model of CPython's, not CPython.
    bound = _OUTLINE_HEIGHT if force else _MAX_BLOCK_DEPTH
    for fn, depth in _function_depths(node):
        if depth <= bound:
            continue
        globs = {x for n in _walk_same_scope(fn) if isinstance(n, ast.Global)
                 for x in n.names}
        o = _Outliner(globs)
        o.function(fn)
        moved = moved or o.counter > 0
    return moved


def _fix_missing_locations(node: ast.AST) -> None:
    """``ast.fix_missing_locations`` without its recursion: a long clause body
    lowers to an AST nested deeper than the interpreter's recursion limit."""
    stack = [(node, 1, 0, 1, 0)]
    while stack:
        n, lineno, col, end_lineno, end_col = stack.pop()
        attrs = n._attributes
        if "lineno" in attrs:
            if getattr(n, "lineno", None) is None:
                n.lineno = lineno
            else:
                lineno = n.lineno
        if "end_lineno" in attrs:
            if getattr(n, "end_lineno", None) is None:
                n.end_lineno = end_lineno
            else:
                end_lineno = n.end_lineno
        if "col_offset" in attrs:
            if getattr(n, "col_offset", None) is None:
                n.col_offset = col
            else:
                col = n.col_offset
        if "end_col_offset" in attrs:
            if getattr(n, "end_col_offset", None) is None:
                n.end_col_offset = end_col
            else:
                end_col = n.end_col_offset
        for c in ast.iter_child_nodes(n):
            stack.append((c, lineno, col, end_lineno, end_col))


class GeneratedCodeError(SyntaxError):
    """Generated code CPython refused to compile.  Names the generated
    function, and -- once :meth:`for_predicate` has enriched it -- the
    predicate (``name/arity``) and the source file and line of the clause it
    came from.  ``original`` is CPython's own exception."""

    def __init__(self, message, function_name, original,
                 filename=None, lineno=None, predicate=None):
        self.function_name = function_name
        self.original = original
        self.predicate = predicate
        self.reason = message
        where = (f"{filename}:{lineno}: " if filename and lineno
                 else f"{filename}: " if filename else "")
        what = (f"a clause of {predicate}" if predicate
                else f"generated function {function_name}")
        super().__init__(f"{where}{what} could not be compiled: {message}")
        self.filename = filename
        self.lineno = lineno

    def __str__(self):
        # The message already leads with ``file:line``; SyntaxError's own
        # ``(file, line N)`` suffix would say it twice.
        return self.msg

    def for_predicate(self, predicate: str, positions=()) -> "GeneratedCodeError":
        """The same error naming *predicate*.  *positions* are the clauses'
        source positions ``(line, col, end_line, end_col)`` (``None`` for a
        clause with no source); the line is the one of the clause CPython's
        error points into, else of the first clause that has one."""
        spans = [p for p in positions if p]
        line = self.lineno
        hit = [p for p in spans if line and p[0] <= line <= (p[2] or p[0])]
        if hit:
            line = hit[0][0]
        elif spans:
            line = spans[0][0]
        return GeneratedCodeError(self.reason, self.function_name, self.original,
                                  filename=self.filename, lineno=line,
                                  predicate=predicate)


def functiondef_to_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    globals_: dict | None = None,
    filename: str = "<template>",
):
    """Compile an ast.FunctionDef (or AsyncFunctionDef) into a Python callable.

    The function name is read from node.name.  globals_ provides names
    visible at definition time (closures, helper functions, etc.).

    If CPython refuses the code for nesting blocks too deep, the deep
    statements are outlined (``split_deep_nesting``) and the code compiled
    again.  If CPython still refuses it, the error is a
    :class:`GeneratedCodeError` naming the function and the source file and
    line of the code it came from, never a bare ``SyntaxError`` about
    ``<template>``.
    """
    module = ast.Module(body=[node], type_ignores=[])
    _fix_missing_locations(module)
    try:
        try:
            code = compile(module, filename, "exec")
        except (SyntaxError, RecursionError) as exc:
            # Outline only once CPython has refused the nesting, so a
            # function under the limit -- every one but a very long clause
            # body's -- pays nothing for the pass.  (A deep enough AST runs
            # out of compiler recursion before it reaches the block check.)
            if isinstance(exc, SyntaxError) and "nested blocks" not in str(exc.msg):
                raise
            if not split_deep_nesting(node, force=True):
                raise
            _fix_missing_locations(module)
            code = compile(module, filename, "exec")
    except (SyntaxError, RecursionError) as exc:
        src = (globals_ or {}).get("__file__") or (
            filename if filename != "<template>" else None)
        raise GeneratedCodeError(
            getattr(exc, "msg", None) or str(exc) or type(exc).__name__,
            node.name, exc, filename=src,
            lineno=getattr(exc, "lineno", None)) from exc
    # Every tuple/frozenset constant of generated code is Var-free and
    # immutable: certify it so a goal-position seam can hand it out by
    # identity (clausal.logic.cells, the compiled-constant certificate).
    from clausal.logic.cells import register_compiled_constants  # noqa: PLC0415
    register_compiled_constants(code)
    ns = dict(globals_ or {})
    exec(code, ns)
    return ns[node.name]


def stmts_to_function(
    body: list[ast.stmt],
    name: str,
    args: ast.arguments | None = None,
    *,
    decorators: list[ast.expr] | None = None,
    returns: ast.expr | None = None,
    globals_: dict | None = None,
    filename: str = "<template>",
):
    """Wrap a statement list in a function definition and return a callable.

    Parameters
    ----------
    body:       statements forming the function body
    name:       name to give the function
    args:       parameter signature; if omitted, inferred from the body via
                ``_infer_args`` (names that are loaded before being assigned
                become positional parameters, in order of first load)
    decorators: decorator list
    returns:    return-annotation expression
    globals_:   names made available in the function's defining scope
    filename:   filename used in tracebacks
    """
    if args is None:
        args = _infer_args(body, globals_)
    extra = {'type_params': []} if 'type_params' in ast.FunctionDef._fields else {}
    func_node = ast.FunctionDef(
        name=name,
        args=args,
        body=body,
        decorator_list=decorators or [],
        returns=returns,
        type_comment=None,
        **extra,
    )
    return functiondef_to_function(func_node, globals_=globals_, filename=filename)
