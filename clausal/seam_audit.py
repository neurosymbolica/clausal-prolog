"""The DECIDER of Python-freedom: an audit of a ``.seam`` module's FINAL
generated Python.

A ``.seam`` module is compiled by lowering its source (``EmbedTransformer``)
into a Python module tree, which the import hook compiles to bytecode and
executes; the clause bodies in it are DATA (``$Predicate(...)``,
``$LoadName(...)`` node constructors) that the logic compiler turns into
code at load time.  This module walks that final tree -- produced by the
same function the import hook uses (:func:`clausal.import_hook.
transform_seam_source`), executing nothing -- and ALLOWS only:

* literals and containers;
* the engine's own injected runtime names (the ``$`` names of
  ``import_hook.runtime_builtins`` and ``import_hook.
  PER_MODULE_RUNTIME_NAMES``) -- a ``$`` name cannot be written in source,
  so it is always compiler-emitted; its ARGUMENTS are audited like
  everything else (the compiler embeds author subtrees there);
* names the module itself binds (its predicates, constants, atoms, the
  local logic-variable plumbing: walrus targets and thunk parameters) and
  the names its allowed imports bind;
* imports (``from M import n``, ``import M``) of a Clausal module or an
  ENGINE-SHIPPED one, each imported name a declared export
  (:func:`clausal.python_bridges._exports`);
* clause-data references ``$LoadName('m.x')`` / ``$LoadAttr(...)`` that are
  exactly ``module.export``, never an attribute of an imported value;
* the compiler's fixed plumbing statements (the import guard, the registry
  copies), recognised by their exact SHAPE as the compiler's own builders
  emit it, with their module constants checked.

Everything else is a route (fail closed): any call of a non-``$`` callee,
any attribute not rooted at a ``$`` name, an underscore-led attribute, a
def/class/comprehension/subscript/statement outside the plumbing shapes,
a name the module does not bind (``exec``, ``open``, ``__import__``, ...).

The record (``term_rewriting._EXTERNAL_REFS``) and the static pre-scan stay
as diagnostics; they can only ADD routes.  This audit is what ALLOWS.
"""
from __future__ import annotations

import ast

__all__ = ["audit_tree", "audit_source", "generated_tree"]


_SAFE_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
                ast.Pow, ast.MatMult, ast.BitAnd, ast.BitOr, ast.BitXor,
                ast.LShift, ast.RShift)
_SAFE_UNARY = (ast.USub, ast.UAdd, ast.Not, ast.Invert)
_SAFE_CMP = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is,
             ast.IsNot, ast.In, ast.NotIn)

#: Module-level names the compiler itself assigns (not user Python).
_ENGINE_ASSIGNED = frozenset({"__clausal_implicit_functors__"})


def _engine_names() -> frozenset:
    from clausal import import_hook  # noqa: PLC0415
    return frozenset(
        n for n in import_hook.runtime_builtins if n.startswith("$")
    ) | import_hook.PER_MODULE_RUNTIME_NAMES


def generated_tree(source: str, filename: str) -> ast.Module:
    """The final Python tree the import hook compiles for this ``.seam``
    source (nothing executed)."""
    from clausal.import_hook import transform_seam_source  # noqa: PLC0415
    return transform_seam_source(source, filename)[0]


def audit_source(source: str, filename: str, check_module=None):
    """:func:`audit_tree` of the generated tree for *source*; a source that
    does not compile is ``[("uncompilable", 0)]``."""
    import warnings  # noqa: PLC0415
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = generated_tree(source, filename)
    except Exception:  # noqa: BLE001 -- does not compile: fail closed
        return [("uncompilable", 0)], []
    return audit_tree(tree, check_module)


# ── plumbing shapes (the compiler's own builders, canonicalised) ───────────


def _is_const_tree(node) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_const_tree(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and _is_const_tree(k) for k in node.keys) \
            and all(_is_const_tree(v) for v in node.values)
    return False


def _shape(node) -> str:
    """*node* with every constant subtree replaced by one placeholder and
    every import statement by another: the template a plumbing builder
    emits, whatever its constant parameters."""
    import copy  # noqa: PLC0415

    class _Canon(ast.NodeTransformer):
        def generic_visit(self, n):
            if isinstance(n, ast.expr) and _is_const_tree(n):
                return ast.Constant(value="<C>")
            if isinstance(n, (ast.ImportFrom, ast.Import)):
                return ast.Pass()
            return super().generic_visit(n)

    return ast.dump(_Canon().visit(copy.deepcopy(node)),
                    include_attributes=False)


_PLUMBING_SHAPES: "dict | None" = None


def _plumbing_shapes() -> dict:
    """shape -> plumbing kind, built by CALLING the compiler's builders."""
    global _PLUMBING_SHAPES
    if _PLUMBING_SHAPES is not None:
        return _PLUMBING_SHAPES
    from clausal.templating import term_rewriting as tr  # noqa: PLC0415
    anchor = ast.parse("x").body[0]
    imp = ast.parse("from m import a").body[0]
    shapes = {
        _shape(tr._wrap_import_for_pl_data(imp, "m", {"a": "a"}, ["a"],
                                           anchor)): "import_guard",
        _shape(tr._make_import_signatures_update_ast(
            "m", [("a", "a")], anchor)): "import_signatures",
        _shape(tr._make_import_arities_record_ast({"a": {1}}, anchor)):
            "import_arities",
        _shape(tr._make_functor_signatures_update_ast(
            [("f", ("x",))], anchor)): "functor_signatures",
    }
    _PLUMBING_SHAPES = shapes
    return shapes


def _import_constants(node) -> "list[str]":
    """The module-name constants of every ``__import__(C, ...)`` in *node*."""
    out = []
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id == "__import__" and sub.args
                and isinstance(sub.args[0], ast.Constant)):
            out.append(sub.args[0].value)
    return out


#: ``-translations``: the compiler imports these two registration functions
#: under these local names and calls them with constant arguments.
_TRANSLATIONS = ("clausal.logic.translations",
                 {"register_predicate": "_reg_pred",
                  "register_atom": "_reg_atom"})


def _is_translations_import(node) -> bool:
    return (isinstance(node, ast.ImportFrom) and node.level == 0
            and node.module == _TRANSLATIONS[0]
            and {a.name: a.asname for a in node.names} == _TRANSLATIONS[1])


#: The engine plumbing modules a plumbing shape may import by name.
_PLUMBING_MODULES = {
    "import_guard": {"clausal.pl_data_imports"},
    "import_arities": {"clausal.logic.predicate"},
    "functor_signatures": set(),
}


# ── the audit ───────────────────────────────────────────────────────────────


class _Audit:
    def __init__(self, check_module):
        self.routes: list = []
        self.children: list = []
        self.engine = _engine_names()
        self.check_module = check_module
        self.own: set = set()           # names this module binds
        self.imported: dict = {}        # local -> "module.orig"
        self.module_names: dict = {}    # import binding -> module path

    def route(self, kind, node):
        self.routes.append((kind, getattr(node, "lineno", 0) or 0))

    # -- imports --------------------------------------------------------
    def import_from(self, node):
        if node.level:
            self.route("python_import", node)
            return
        ok = self.check_module("module", node.module, None, node)
        for a in node.names:
            local = a.asname or a.name
            self.own.add(local)
            self.imported[local] = f"{node.module}.{a.name}"
            if ok:
                self.check_module("name", node.module, a.name, node)

    def import_(self, node):
        for a in node.names:
            self.check_module("module", a.name, None, node)
            bound = a.asname or a.name.split(".")[0]
            self.own.add(bound)
            self.module_names[bound] = a.name if a.asname else bound

    # -- statements -----------------------------------------------------
    def stmt(self, node, top=False):
        if isinstance(node, ast.Expr):
            self.expr(node.value, frozenset())
        elif isinstance(node, ast.Pass):
            pass
        elif isinstance(node, ast.ImportFrom) and _is_translations_import(
                node):
            self.translations = True
        elif isinstance(node, ast.ImportFrom):
            self.import_from(node)
        elif isinstance(node, ast.Import):
            self.import_(node)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if not (isinstance(t, ast.Name)
                        and (not t.id.startswith("_")
                             or t.id in _ENGINE_ASSIGNED)):
                    self.route("python_statement", node)
                    return
            self.expr(node.value, frozenset())
        elif isinstance(node, ast.If):
            self.expr(node.test, frozenset())
            for s in node.body + node.orelse:
                self.stmt(s)
        else:
            self.route("python_statement", node)

    def plumbing(self, node) -> bool:
        kind = _plumbing_shapes().get(_shape(node))
        if kind is None:
            return False
        if kind == "import_guard":
            imp = node.body[0]
            self.import_from(imp)
            for c in _import_constants(node):
                if c not in _PLUMBING_MODULES[kind]:
                    self.route("python_module", node)
            # bind_data_names / record_bound_data_names name the module the
            # guarded import imports: it must be that one.
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and len(sub.args) > 1
                        and isinstance(sub.args[1], ast.Constant)
                        and sub.args[1].value != imp.module):
                    self.route("python_module", node)
        elif kind == "import_signatures":
            for c in _import_constants(node):
                self.check_module("module", c, None, node)
        else:
            allowed = _PLUMBING_MODULES[kind]
            for c in _import_constants(node):
                if c not in allowed:
                    self.route("python_module", node)
        return True

    # -- expressions ----------------------------------------------------
    def name_ok(self, name, scope) -> bool:
        return (name in self.engine or name in scope or name in self.own)

    def expr(self, node, scope):
        if node is None or isinstance(node, ast.Constant):
            return
        if isinstance(node, ast.Name):
            if not isinstance(node.ctx, ast.Load):
                self.route("python_statement", node)
            elif not self.name_ok(node.id, scope):
                self.route("python_name", node)
            return
        if isinstance(node, ast.NamedExpr):
            self.own.add(node.target.id)
            self.expr(node.value, scope)
            return
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for e in node.elts:
                self.expr(e, scope)
            return
        if isinstance(node, ast.Starred):
            self.expr(node.value, scope)
            return
        if isinstance(node, ast.Dict):
            for k in node.keys:
                self.expr(k, scope)
            for v in node.values:
                self.expr(v, scope)
            return
        if isinstance(node, ast.BinOp) and isinstance(node.op, _SAFE_BINOPS):
            self.expr(node.left, scope)
            self.expr(node.right, scope)
            return
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, _SAFE_UNARY):
            self.expr(node.operand, scope)
            return
        if isinstance(node, ast.BoolOp):
            for v in node.values:
                self.expr(v, scope)
            return
        if isinstance(node, ast.Compare) and all(
                isinstance(o, _SAFE_CMP) for o in node.ops):
            self.expr(node.left, scope)
            for c in node.comparators:
                self.expr(c, scope)
            return
        if isinstance(node, ast.IfExp):
            self.expr(node.test, scope)
            self.expr(node.body, scope)
            self.expr(node.orelse, scope)
            return
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                self.expr(v, scope)
            return
        if isinstance(node, ast.FormattedValue):
            self.expr(node.value, scope)
            self.expr(node.format_spec, scope)
            return
        if isinstance(node, ast.Lambda):
            a = node.args
            if (a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs
                    or a.defaults or a.kw_defaults):
                self.route("python_def", node)
                return
            params = frozenset(p.arg for p in a.args)
            self.expr(node.body, scope | params)
            return
        if isinstance(node, ast.Attribute):
            if not self.dollar_rooted(node):
                self.route("non_export", node)
            return
        if isinstance(node, ast.Call):
            self.call(node, scope)
            return
        self.route("python_statement", node)

    def dollar_rooted(self, node) -> bool:
        """``$module.db.mark_tabled``: an attribute walk from a ``$`` name
        (compiler-emitted; the author cannot write one), every part public."""
        while isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                return False
            node = node.value
        return isinstance(node, ast.Name) and node.id in self.engine

    def call(self, node, scope):
        f = node.func
        if isinstance(f, ast.Name) and f.id in self.engine:
            if f.id == "$LoadName":
                self.load_name(node)
            elif f.id == "$LoadAttr":
                if not self.load_attr(node):
                    return
                # The chain (``object=``) was validated as a whole: its
                # inner $LoadAttr/$LoadName nodes are parts of ONE
                # reference, not references of their own.
                for k in node.keywords:
                    if k.arg != "object":
                        self.expr(k.value, scope)
                return
            for a in node.args:
                if (isinstance(a, ast.Call) and isinstance(a.func, ast.Name)
                        and a.func.id == "globals" and not a.args
                        and not a.keywords):
                    continue    # $helper(..., globals()): the engine's own
                self.expr(a, scope)
            for k in node.keywords:
                self.expr(k.value, scope)
            return
        if (isinstance(f, ast.Name) and getattr(self, "translations", False)
                and f.id in _TRANSLATIONS[1].values()
                and all(_is_const_tree(a) for a in node.args)
                and not node.keywords):
            return      # -translations registration, constant arguments
        if isinstance(f, ast.Attribute) and self.dollar_rooted(f):
            for a in node.args:
                self.expr(a, scope)
            for k in node.keywords:
                self.expr(k.value, scope)
            return
        self.route("python_call", node)

    # -- clause data: the names the logic compiler resolves -------------
    def _kw(self, node, name):
        for k in node.keywords:
            if k.arg == name:
                return k.value
        return None

    def load_name(self, node):
        n = self._kw(node, "name")
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
            self.route("python_name", node)
            return
        name = n.value
        parts = name.split(".")
        if not all(p.isidentifier() for p in parts):
            # A quoted name ('=..', '.'): one namespace key, no chain.
            if name.startswith("_"):
                self.route("non_export", node)
            return
        if any(p.startswith("_") for p in parts):
            self.route("non_export", node)
        elif len(parts) > 1:
            self.check_module("chain", name, None, node)

    def load_attr(self, node) -> bool:
        """Check a whole $LoadAttr chain; False when it was refused for its
        SHAPE (nothing below it is then worth auditing)."""
        parts = []
        cur = node
        while (isinstance(cur, ast.Call) and isinstance(cur.func, ast.Name)
               and cur.func.id == "$LoadAttr"):
            a = self._kw(cur, "attr")
            if not (isinstance(a, ast.Constant) and isinstance(a.value, str)):
                self.route("non_export", node)
                return False
            parts.append(a.value)
            cur = self._kw(cur, "object")
        if not (isinstance(cur, ast.Call) and isinstance(cur.func, ast.Name)
                and cur.func.id == "$LoadName"):
            self.route("non_export", node)
            return False
        base = self._kw(cur, "name")
        if not (isinstance(base, ast.Constant) and isinstance(base.value,
                                                              str)):
            self.route("non_export", node)
            return False
        if any(p.startswith("_") for p in parts):
            self.route("non_export", node)
            return False
        head = base.value
        if head in self.imported:
            # an attribute of an imported VALUE
            self.route("non_export", node)
            return False
        head = self.module_names.get(head, head)
        self.check_module("chain", ".".join([head, *reversed(parts)]),
                          None, node)
        return True


def audit_tree(tree: ast.Module, check_module) -> "tuple[list, list]":
    """``(routes, [])`` of the generated module *tree*: every node that is
    not on the allow-list is a route.  *check_module(kind, a, b, node)*
    answers the module questions (``"module"``: may module *a* be imported;
    ``"name"``: is *b* an export of *a*; ``"chain"``: is the dotted *a*
    exactly ``module.export``), adding its own routes; it returns a bool."""
    audit = _Audit(check_module)
    # Pass 1: what the module binds (so a reference before its binding --
    # a predicate used above its clauses -- is still its own).
    for sub in ast.walk(tree):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id == "$declare_head" and sub.args
                and isinstance(sub.args[0], ast.Constant)):
            audit.own.add(sub.args[0].value)
        elif isinstance(sub, ast.NamedExpr):
            audit.own.add(sub.target.id)
        elif isinstance(sub, ast.Assign):
            for t in sub.targets:
                if isinstance(t, ast.Name):
                    audit.own.add(t.id)
    for stmt in tree.body:
        if isinstance(stmt, (ast.Try, ast.Expr)) and audit.plumbing(stmt):
            continue
        audit.stmt(stmt, top=True)
    return audit.routes, audit.children
