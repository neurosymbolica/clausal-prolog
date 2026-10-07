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
import collections

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
    """The ``$`` names that are engine plumbing.  NOT the ``$``-only
    spellings of Python builtins (``$isinstance``, ``$globals``,
    ``$__import__``, ...): generated code reaches a builtin through one so
    a module cannot shadow it, but a builtin is not engine plumbing, and
    allowing ``$__import__``/``$globals`` here would let an attribute walk
    from one through the audit.  The plumbing that does call them is
    recognised by its exact shape (``plumbing``), never by name."""
    from clausal import import_hook  # noqa: PLC0415
    from clausal.logic.generated_names import (  # noqa: PLC0415
        GENERATED_CODE_BUILTINS, MODULE_CODE_BUILTINS)
    return (frozenset(
        n for n in import_hook.runtime_builtins if n.startswith("$")
    ) - frozenset(GENERATED_CODE_BUILTINS) - frozenset(MODULE_CODE_BUILTINS)
    ) | import_hook.PER_MODULE_RUNTIME_NAMES


#: Engine helper FUNCTIONS generated code may call (each takes terms or
#: constants and acts on the module's own database or atom pool).
_HELPER_CALLEES = frozenset({
    "$declare_head", "$define_predicate", "$assert_fact", "$head",
    "$intern_atom", "$keeps_predicate", "$mint", "$check_constant_ground",
    "$constant_functor_term", "$register_module_constant",
    "$register_constant_units", "$check_currency_unit", "$decimal_value",
    "$unterminated_fact_error", "$in_",
})

#: The DATA node classes (clause terms the logic compiler interprets),
#: by their place in the compiler's own node hierarchy.
_DATA_NODE_NAMES = frozenset({
    "Call", "Keyword", "IfExpr", "CompareChain", "DictLiteral", "FString",
    "FormattedExpr", "StarUnpack", "Slice", "ForClause", "Lambda", "Params",
    "LoadName", "LoadAttr", "LoadSubscript", "Predicate", "DictTerm",
    "SetTerm", "PyThunk", "FStringThunk", "Quantity", "Var", "FrozenList",
    "FrozenDict", "FrozenSet", "NoneLiteral", "EllipsisLiteral",
})


def _allowed_callees() -> frozenset:
    """The ``$`` callees generated code may call: the helper functions
    above, and the engine's DATA node classes -- the literal, operator,
    pattern, comprehension and parameter families of the compiler's node
    hierarchy plus the term nodes named above.  Never a node that stands
    for a Python effect (a store, delete, assignment, return, yield,
    await, a module or a loop), which the logic compiler would turn into
    one."""
    from clausal import import_hook  # noqa: PLC0415
    from clausal.pythonic_ast import nodes  # noqa: PLC0415
    families = tuple(getattr(nodes, n) for n in (
        "Literal", "ElementsLiteral", "BinOp", "UnaryOp", "PatternList",
        "ElemComp", "Param") if hasattr(nodes, n))
    out = set(_HELPER_CALLEES & _engine_names())
    for name, value in import_hook.runtime_builtins.items():
        if not name.startswith("$"):
            continue
        bare = name[1:]
        if bare in _DATA_NODE_NAMES or (
                isinstance(value, type) and families
                and issubclass(value, families)):
            out.add(name)
    return frozenset(out)


_ENGINE_MEANING: "frozenset | None" = None


def _engine_meaning_names() -> frozenset:
    """Names the engine itself gives a meaning, from its own tables: the
    registered builtin predicates and goal classes, the special forms and
    zero-arity control constructs, the arithmetic evaluables, and the ISO
    error formals."""
    global _ENGINE_MEANING
    if _ENGINE_MEANING is None:
        from clausal.logic.builtins import _BUILTIN_CLASSES  # noqa: PLC0415
        from clausal.logic.builtins._registry import _BUILTINS  # noqa: PLC0415
        from clausal.logic.builtins.clause_ops import (  # noqa: PLC0415
            SPECIAL_FORMS, _ZERO_ARITY_CONTROL)
        from clausal.templating.term_rewriting import (  # noqa: PLC0415
            _ERROR_FORMAL_DESCRIPTORS)
        from clausal.tools.iso_l3_directives import (  # noqa: PLC0415
            _evaluable_names)
        _ENGINE_MEANING = (
            frozenset(_BUILTIN_CLASSES)
            | frozenset(n for n, _a in _BUILTINS)
            | frozenset(n for n, _a in SPECIAL_FORMS)
            | frozenset(_ZERO_ARITY_CONTROL)
            | frozenset(_evaluable_names())
            | frozenset(_ERROR_FORMAL_DESCRIPTORS)
            | frozenset({"error", "system_error", "instantiation_error",
                         "uninstantiation_error"}))
    return _ENGINE_MEANING


def _runtime_bare_names() -> frozenset:
    """The bare (non-``$``) names the loader injects into every module: the
    module may not rebind them (a walrus or assignment target)."""
    from clausal import import_hook  # noqa: PLC0415
    return frozenset(n for n in import_hook.runtime_builtins
                     if not n.startswith("$"))


def generated_tree(source: str, filename: str) -> ast.Module:
    """The final Python tree the import hook compiles for this ``.seam``
    source (nothing executed)."""
    from clausal.import_hook import transform_seam_source  # noqa: PLC0415
    return transform_seam_source(source, filename)[0]


def audit_source(source: str, filename: str, check_module=None):
    """:func:`audit_tree` of the generated tree for *source*; a source that
    does not compile is ``[("uncompilable", 0)]``."""
    import warnings  # noqa: PLC0415
    from clausal.import_hook import transform_seam_source  # noqa: PLC0415
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree, transformer = transform_seam_source(source, filename)
    except Exception:  # noqa: BLE001 -- does not compile: fail closed
        return [("uncompilable", 0)], []
    return audit_tree(
        tree, check_module,
        translations=getattr(transformer, "_emitted_translations", ()) or (),
        module_items=getattr(transformer, "_module_items", ()) or ())


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
            if isinstance(n, ast.ImportFrom):
                return ast.ImportFrom(module="<M>", names=[], level=n.level)
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
    # _shape erases an ImportFrom's module and names, never its kind: only
    # the import guard's one ImportFrom position takes one.
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
    """The module-name constants of every ``$__import__(C, ...)`` in *node*
    (the plumbing's ``$``-only spelling of ``__import__``)."""
    out = []
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id == "$__import__" and sub.args
                and isinstance(sub.args[0], ast.Constant)):
            out.append(sub.args[0].value)
    return out


#: The engine plumbing modules a plumbing shape may import by name.
_PLUMBING_MODULES = {
    "import_guard": {"clausal.pl_data_imports"},
    "import_arities": {"clausal.logic.predicate"},
    "functor_signatures": set(),
}


# ── the audit ───────────────────────────────────────────────────────────────


def node_line(node) -> int:
    """The SOURCE line a generated node stands for: a clause-data node's
    ``position=(line, col, ...)`` when it carries one (the statement holding
    a clause has the line of its head, or of the module directive in the
    native lowering), else the node's own ``lineno``."""
    if isinstance(node, ast.Call):
        for k in node.keywords:
            if (k.arg == "position" and isinstance(k.value, ast.Tuple)
                    and k.value.elts
                    and isinstance(k.value.elts[0], ast.Constant)
                    and isinstance(k.value.elts[0].value, int)):
                return k.value.elts[0].value
    return getattr(node, "lineno", 0) or 0



class _Audit:
    def __init__(self, check_module):
        self.routes: list = []
        self.children: list = []
        self.engine = _engine_names()
        self.callees = _allowed_callees()
        self.reserved = _runtime_bare_names()
        self.imported_modules: dict = {}    # guarded import -> names
        self.implicit_functors = False      # set from the tree
        self.check_module = check_module
        self.own: set = set()           # names this module binds
        self.imported: dict = {}        # local -> "module.orig"
        self.module_names: dict = {}    # import binding -> module path

    def route(self, kind, node):
        self.routes.append((kind, node_line(node)))

    # -- imports --------------------------------------------------------
    def import_from(self, node):
        if node.level:
            self.route("python_import", node)
            return
        ok = self.check_module("module", node.module, None, node)
        for a in node.names:
            local = a.asname or a.name
            if local.startswith("_") or local in self.reserved:
                self.route("python_import", node)
            self.own.add(local)
            self.imported[local] = f"{node.module}.{a.name}"
            if ok:
                self.check_module("name", node.module, a.name, node)

    def import_(self, node):
        for a in node.names:
            self.check_module("module", a.name, None, node)
            bound = a.asname or a.name.split(".")[0]
            if bound.startswith("_") or bound in self.reserved:
                self.route("python_import", node)
            self.own.add(bound)
            self.module_names[bound] = a.name if a.asname else bound

    # -- statements -----------------------------------------------------
    def stmt(self, node, top=False):
        if isinstance(node, ast.Expr):
            self.expr(node.value, frozenset())
        elif isinstance(node, ast.Pass):
            pass
        elif isinstance(node, ast.ImportFrom):
            self.import_from(node)
            if not node.level:
                # The native (Prolog-syntax) lowering emits the import bare,
                # without the seam's guard: its signature plumbing names it.
                self.imported_modules.setdefault(node.module, set()).update(
                    a.name for a in node.names)
        elif isinstance(node, ast.Import):
            self.import_(node)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if not (isinstance(t, ast.Name)
                        and t.id not in self.reserved
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
        """A compiler plumbing statement: its SHAPE picks the builder, and
        the statement must then be EXACTLY what that builder emits for the
        constants it carries (rebuilt and compared), those constants
        checked against this file's own imports and declarations."""
        kind = _plumbing_shapes().get(_shape(node))
        if kind is None:
            return False
        from clausal.templating import term_rewriting as tr  # noqa: PLC0415
        anchor = node
        try:
            if kind == "import_guard":
                imp = node.body[0]
                if not isinstance(imp, ast.ImportFrom) or imp.level:
                    raise ValueError
                call = node.handlers[0].body[0].test.operand
                pairs = ast.literal_eval(call.args[2])
                eligible = ast.literal_eval(call.args[3])
                names = {a.asname or a.name: a.name for a in imp.names}
                if pairs != names or not set(eligible) <= set(names):
                    raise ValueError
                expected = tr._wrap_import_for_pl_data(
                    imp, imp.module, pairs, list(eligible), anchor)
                self.import_from(imp)
                self.imported_modules.setdefault(imp.module, set()).update(
                    a.name for a in imp.names)
            elif kind == "import_signatures":
                gen = node.value.args[0].generators[0]
                pairs = ast.literal_eval(gen.iter.func.value)
                module = _import_constants(node)[0]
                imported = self.imported_modules.get(module)
                if imported is None or not set(pairs.values()) <= imported:
                    raise ValueError
                expected = tr._make_import_signatures_update_ast(
                    module, list(pairs.items()), anchor)
            elif kind == "import_arities":
                selected = ast.literal_eval(node.value.args[1])
                if not set(selected) <= self.own:
                    raise ValueError
                expected = tr._make_import_arities_record_ast(
                    {k: (None if v is None else set(v))
                     for k, v in selected.items()}, anchor)
            else:   # functor_signatures
                entries = ast.literal_eval(node.value.args[0])
                if not all(isinstance(k, str) and k.isidentifier()
                           and not k.startswith("_") for k in entries):
                    raise ValueError
                expected = tr._make_functor_signatures_update_ast(
                    list(entries.items()), anchor)
        except Exception:  # noqa: BLE001 -- not the builder's own output
            self.route("python_statement", node)
            return True
        if (expected is None or ast.dump(expected) != ast.dump(node)):
            self.route("python_statement", node)
        return True

    # -- expressions ----------------------------------------------------
    def name_ok(self, name, scope) -> bool:
        if name in self.module_names and name not in scope:
            return False        # a module object as a value
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
            # The lowering's only walrus binds a fresh logic variable.
            if (node.target.id in self.reserved
                    or not (isinstance(node.value, ast.Call)
                            and isinstance(node.value.func, ast.Name)
                            and node.value.func.id == "$Var"
                            and not node.value.args
                            and not node.value.keywords)):
                self.route("python_statement", node)
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
            if f.id not in self.callees:
                self.route("python_call", node)
                return
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
                        and a.func.id == "$globals" and not a.args
                        and not a.keywords):
                    continue    # $helper(..., $globals()): the engine's own
                self.expr(a, scope)
            for k in node.keywords:
                self.expr(k.value, scope)
            return
        if (isinstance(f, ast.Attribute) and self.dollar_rooted(f)
                and ast.unparse(f).startswith("$module.db.mark_")
                and ast.unparse(f).count(".") == 2):
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
        elif name in self.module_names:
            # a bare -import_module binding: the MODULE OBJECT as a value
            self.route("non_export", node)
        elif not self.bare_name_ok(name):
            self.route("python_name", node)

    def bare_name_ok(self, name) -> bool:
        """The ALLOW-LIST for a bare clause-data name (what the logic
        compiler resolves): a name this module binds or imports, a name the
        engine gives a meaning of its own (a builtin predicate, a special
        form or control construct, an arithmetic evaluable, an ISO error
        formal, ``Undefined``), or a logic-variable spelling that is no
        injected runtime name.  Under ``-implicit_functors`` an undeclared
        functor is data, so any lowercase name the loader does not inject
        and Python's builtins do not bind is too."""
        if name in self.own or name in self.imported:
            return True
        if name in _engine_meaning_names():
            return True
        from clausal.templating.term_rewriting import (  # noqa: PLC0415
            _TITLECASE_EXEMPT_NAMES, _is_logic_var_name)
        if name in _TITLECASE_EXEMPT_NAMES:
            return True
        if name in self.reserved:
            return False
        if _is_logic_var_name(name):
            return True
        if self.implicit_functors:
            import builtins  # noqa: PLC0415
            return not hasattr(builtins, name)
        return False

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


def audit_tree(tree: ast.Module, check_module, *, translations=(),
               module_items=(), prolog_surface=False) -> "tuple[list, list]":
    """``(routes, [])`` of the generated module *tree*: every node that is
    not on the allow-list is a route.  *check_module(kind, a, b, node)*
    answers the module questions (``"module"``: may module *a* be imported;
    ``"name"``: is *b* an export of *a*; ``"chain"``: is the dotted *a*
    exactly ``module.export``), adding its own routes; it returns a bool.

    *prolog_surface*: the tree is a Prolog-syntax module's (``.pl``,
    ``.clausal``), where a bare name is always a functor (a predicate
    defined elsewhere, or asserted later): read as under
    ``-implicit_functors`` -- any name the loader does not inject and
    Python's builtins do not bind."""
    audit = _Audit(check_module)
    audit.implicit_functors = bool(prolog_surface)
    # *translations*: the dumps of the statements the -translations lowering
    # emitted (``EmbedTransformer._emitted_translations``); each matches one
    # top-level statement exactly, and nothing else is accepted for them.
    for item in module_items:
        if type(item).__name__ == "SpecializeDirective" and item.new_name:
            audit.own.add(item.new_name)
    # Pass 1: what the module binds (so a reference before its binding --
    # a predicate used above its clauses -- is still its own).
    for sub in ast.walk(tree):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id == "$declare_head" and sub.args
                and isinstance(sub.args[0], ast.Constant)):
            audit.own.add(sub.args[0].value)
        elif (isinstance(sub, ast.NamedExpr)
              and isinstance(sub.value, ast.Call)
              and isinstance(sub.value.func, ast.Name)
              and sub.value.func.id == "$Var"):
            audit.own.add(sub.target.id)
        elif isinstance(sub, ast.Assign):
            for t in sub.targets:
                if isinstance(t, ast.Name):
                    audit.own.add(t.id)
                    if (t.id == "__clausal_implicit_functors__"
                            and isinstance(sub.value, ast.Constant)
                            and sub.value.value is True):
                        audit.implicit_functors = True
    pending = collections.Counter(translations or ())
    for stmt in tree.body:
        key = ast.dump(stmt)
        if pending[key] > 0:
            # one of the statements the -translations lowering emitted
            pending[key] -= 1
            continue
        if isinstance(stmt, (ast.Try, ast.Expr)) and audit.plumbing(stmt):
            continue
        audit.stmt(stmt, top=True)
    return audit.routes, audit.children
