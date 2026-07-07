"""clausal.reflection — reify ``.clausal`` source into Clausal compound terms.

Phase 1 of ``implementation_plans/clausal-ast-reflection-and-structural-matching.md``.

``.clausal`` source is Python surface syntax: ``ast.parse`` +
``EmbedTransformer`` turn each clause into *constructor code* — a Python AST
expression that would, at import time, build a ``simple_ast.Predicate`` node
and pass it to ``$define_predicate``.  This module evaluates those
constructor expressions **statically** (no ``exec``, no directive execution,
no predicate compilation), producing a homoiconic term tree Clausal itself
can pattern-match:

- ``Clause(head, goals, position)`` — one clause; ``goals`` is a Python list
  (``[]`` for facts).
- ``Goal(name, args, kwargs)`` — a predicate call *and* any compound term
  (heads, body goals, and structured arguments share this shape).  ``name``
  is a string (dotted for qualified calls); ``kwargs`` is a list of
  ``[name, value]`` pairs.
- ``Variable(name)`` / ``Atom(name)`` — leaves, ground and matchable.
- ``Escape(code, vars, position)`` — a ``++`` Python escape; ``code`` is the
  escaped expression's source text.  Never evaluated.
- ``FormatString(code, vars, position)`` — a deferred f-string.
- ``IfThenElse(condition, then, otherwise)`` — reified ``If/3``.
- ``ModuleDirective(name, args, position)`` — ``-name(...)`` module items.
- ``PythonCode(kind, name, position)`` — embedded plain-Python top-level
  statements (functions, classes, imports, …), reported but never run.

Operator and unary nodes (``Add``, ``Gt``, ``Unify``, ``Not``, ``Or``,
``StarUnpack``, …) are **not** re-wrapped: since ``BinOp``/``UnaryOp`` carry
structural ``__unify__`` they are already first-class unifiable terms, so
they pass through raw with reified operands.  Conjunctions normalize to
Python lists wherever they appear in goal position.

Variables reify as *ground* ``Variable(name)`` terms (anonymous variables
are numbered ``_1``, ``_2``, … per clause), so matchers can inspect clause
structure without accidentally binding anything.  This differs from the
runtime clause store, where heads hold real unbound ``Var`` objects.

``Goal`` deliberately has no ``position`` field: goals are compared whole
(``==``/unification) far more often than clauses, and an always-present
position would make structurally identical goals compare unequal.  Item
positions live on ``Clause``/``ModuleDirective``/``PythonCode``; operator
nodes keep their own (compare-neutral) ``position`` attribute.
"""

from __future__ import annotations

import ast
import dataclasses
import warnings

from clausal.logic.predicate import make_predicate
from clausal.pythonic_ast import nodes as simple_ast


__all__ = [
    "Atom",
    "Clause",
    "Escape",
    "FormatString",
    "Goal",
    "IfThenElse",
    "ModuleDirective",
    "PythonCode",
    "ReifyError",
    "Variable",
    "reify_ast",
    "reify_file",
    "reify_source",
]


class ReifyError(SyntaxError):
    """Raised when ``.clausal`` source cannot be reified."""


# ── Reified vocabulary ───────────────────────────────────────────────────────
# PredicateMeta classes: instances unify structurally, and construction with
# fewer arguments auto-fills the missing trailing fields with fresh variables,
# so ``Clause(HEAD, GOALS)`` written in a matcher head wildcards ``position``.

Clause = make_predicate("Clause", ["head", "goals", "position"])
Goal = make_predicate("Goal", ["name", "args", "kwargs"])
Variable = make_predicate("Variable", ["name"])
Atom = make_predicate("Atom", ["name"])
Escape = make_predicate("Escape", ["code", "vars", "position"])
FormatString = make_predicate("FormatString", ["code", "vars", "position"])
IfThenElse = make_predicate("IfThenElse", ["condition", "then", "otherwise"])
ModuleDirective = make_predicate("ModuleDirective", ["name", "args", "position"])
PythonCode = make_predicate("PythonCode", ["kind", "name", "position"])


# ── Static evaluation of constructor code ────────────────────────────────────
# EmbedTransformer rewrites each clause into
#   $define_predicate(Predicate(head=<runtime term ctor>, body=<simple_ast ctor>, position=(...)), $module)
# where heads construct terms by calling functor classes with keyword
# arguments and walrus-bound ``Var()``s, and bodies are nested calls to
# simple_ast node constructors.  _ClauseReifier interprets that closed
# vocabulary of expressions without executing anything.

# simple_ast names whose constructor calls map onto raw (unifiable) nodes.
_NODE_NAMES = {
    name for name in simple_ast.__all__
    if isinstance(getattr(simple_ast, name, None), type)
    and issubclass(getattr(simple_ast, name), simple_ast.Node)
}


def _const_value(node):
    """Statically evaluate a literal-only expression (positions, numbers)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_const_value(elt) for elt in node.elts)
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float, complex))
    ):
        return -node.operand.value
    raise ReifyError(f"not a literal: {ast.unparse(node)}")


def _dotted_name(node):
    """Extract a (possibly dotted) name from LoadName/LoadAttr constructor code."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        kwargs = {kw.arg: kw.value for kw in node.keywords}
        if node.func.id == "LoadName":
            return _const_value(kwargs["name"])
        if node.func.id == "LoadAttr":
            return f"{_dotted_name(kwargs['object'])}.{_const_value(kwargs['attr'])}"
    raise ReifyError(f"cannot extract functor name from {ast.unparse(node)}")


class _ClauseReifier:
    """Reify one clause's constructor expression.  Fresh per clause so that
    walrus-bound variable names and anonymous-variable numbering are scoped
    to the clause, mirroring logic-variable scope."""

    def __init__(self, field_order=None):
        self._vars = {}
        self._anon_count = 0
        # (functor, arity) → canonical field-name order (first definition wins),
        # shared across the clauses of one source so keyword heads canonicalize
        # to the runtime's field order (F010).
        self._field_order = {} if field_order is None else field_order

    # -- variables ----------------------------------------------------------

    def _named_var(self, name):
        term = self._vars.get(name)
        if term is None:
            term = self._vars[name] = Variable(name)
        return term

    def _anonymous_var(self):
        # Use a non-identifier prefix so an anonymous `_` never aliases a real
        # user variable with a leading-underscore name like `_1` (F011).
        self._anon_count += 1
        return Variable(f"#anon{self._anon_count}")

    # -- contexts -----------------------------------------------------------

    def goals(self, node):
        """Reify a clause body (or any conjunction) to a list of goals."""
        if isinstance(node, ast.Constant) and node.value is True:
            return []
        goal = self.goal(node)
        return goal if isinstance(goal, list) else [goal]

    def goal(self, node):
        """Reify in goal context: conjunctions become lists."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            if name == "TupleLiteral":
                flat = []
                for elt in kwargs["elements"].elts:
                    flat.extend(self.goals(elt))
                return flat
            if name == "And":
                return self.goals(kwargs["left"]) + self.goals(kwargs["right"])
            if name == "Or":
                return simple_ast.Or(
                    left=self.goal(kwargs["left"]),
                    right=self.goal(kwargs["right"]),
                    position=self._position_of(kwargs),
                )
            if name == "Not":
                return simple_ast.Not(
                    operand=self.goal(kwargs["operand"]),
                    position=self._position_of(kwargs),
                )
            if name == "IfExpr":
                return IfThenElse(
                    self.goal(kwargs["test"]),
                    self.goal(kwargs["body"]),
                    self.goal(kwargs["orelse"]),
                )
        return self.term(node)

    def term(self, node):
        """Reify in term context: tuples stay tuples."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.List):
            return [self.term(elt) for elt in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self.term(elt) for elt in node.elts)
        if isinstance(node, ast.Dict):
            return {
                self.term(key): self.term(value)
                for key, value in zip(node.keys, node.values)
                if key is not None
            }
        if isinstance(node, ast.NamedExpr):
            # (X := Var()) — a named logic variable's first occurrence.
            name = node.target.id
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "Var"
            ):
                return self._named_var(name)
            term = self.term(node.value)
            self._vars[name] = term
            return term
        if isinstance(node, ast.Name):
            # Subsequent occurrence of a walrus-bound variable, or a bare
            # runtime reference (defensively treated as an atom).
            if node.id in self._vars:
                return self._vars[node.id]
            return Atom(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return _const_value(node)
        if isinstance(node, ast.Call):
            return self._call(node)
        raise ReifyError(f"cannot reify: {ast.unparse(node)}")

    # -- constructor calls ----------------------------------------------------

    def _position_of(self, kwargs):
        pos = kwargs.get("position") or kwargs.get("_position")
        return _const_value(pos) if pos is not None else None

    def _call(self, node):
        if not isinstance(node.func, ast.Name):
            raise ReifyError(f"cannot reify call: {ast.unparse(node)}")
        name = node.func.id
        kwargs = {kw.arg: kw.value for kw in node.keywords}

        if name == "Var":
            return self._anonymous_var()
        if name in ("PyThunk", "FStringThunk"):
            return self._thunk(node, kwargs, name)
        if name == "Call":
            return self._goal_call(kwargs)
        if name == "LoadName":
            return Atom(_const_value(kwargs["name"]))
        if name == "LoadAttr":
            return Atom(_dotted_name(node))
        if name == "IfExpr":
            return IfThenElse(
                self.term(kwargs["test"]),
                self.term(kwargs["body"]),
                self.term(kwargs["orelse"]),
            )
        if name == "DictTerm":
            # A dict literal is rewritten to DictTerm({...}) before reaching
            # the reifier; docs promise "dicts appear as themselves", and the
            # arrow-pattern side builds a runtime dict too, so reify to the raw
            # dict rather than Goal('DictTerm', …) (F013).
            if node.args and isinstance(node.args[0], ast.Dict):
                return self.term(node.args[0])
        if name == "TupleLiteral":
            return tuple(self.term(elt) for elt in kwargs["elements"].elts)
        if name == "ListLiteral":
            return [self.term(elt) for elt in kwargs["elements"].elts]
        if name in _NODE_NAMES:
            return self._raw_node(name, kwargs)
        # Anything else is a runtime term construction — a functor class
        # called with its fields as keyword arguments (heads, compound args)
        # or a runtime helper (DictTerm, Quantity, …).  Reify uniformly as a
        # Goal: positional arguments first, then keyword values in field
        # order (head keyword form IS the field order).
        args = [self.term(arg) for arg in node.args]
        kw_items = [
            (key, value)
            for key, value in kwargs.items()
            if key not in ("position", "_position")
        ]
        # Positional heads are rewritten to keyword ctors whose field names are
        # in positional order; genuine keyword heads carry the user's names in
        # written order, which may differ from the functor's canonical field
        # order. The runtime canonicalizes by the field order of a functor's
        # FIRST definition, so `kp(y=20, x=10)` enumerates (10, 20) even though
        # it is written (y, x). Reorder keyword args to the first-seen order
        # for this functor so the reified positional args match the runtime
        # instead of the written order (F010).
        names = [k for k, _ in kw_items]
        canonical = self._field_order.setdefault((name, len(kw_items)), names)
        ordered = sorted(
            kw_items,
            key=lambda kv: canonical.index(kv[0]) if kv[0] in canonical
            else len(canonical),
        )
        args += [self.term(value) for _, value in ordered]
        return Goal(name, args, [])

    def _goal_call(self, kwargs):
        """simple_ast Call constructor → Goal(name, args, kwargs)."""
        name = _dotted_name(kwargs["func"])
        args = [self.term(arg) for arg in kwargs["args"].elts]
        kw_pairs = []
        keyword_ctors = kwargs["kwargs"].elts if "kwargs" in kwargs else []
        for keyword_ctor in keyword_ctors:
            kw_ctor_kwargs = {kw.arg: kw.value for kw in keyword_ctor.keywords}
            kw_pairs.append([
                _const_value(kw_ctor_kwargs["name"]),
                self.term(kw_ctor_kwargs["value"]),
            ])
        return Goal(name, args, kw_pairs)

    def _thunk(self, node, kwargs, kind):
        """PyThunk / FStringThunk constructor → Escape / FormatString.

        The first positional argument is a lambda whose body is the escaped
        Python expression; it is unparsed, never called."""
        lambda_node, var_list = node.args[0], node.args[1]
        code = ast.unparse(lambda_node.body)
        variables = [self.term(elt) for elt in var_list.elts]
        position = self._position_of(kwargs)
        cls = Escape if kind == "PyThunk" else FormatString
        return cls(code, variables, position)

    def _raw_node(self, name, kwargs):
        """Any other simple_ast constructor → the real node, operands reified.

        BinOp/UnaryOp subclasses carry structural ``__unify__``, so the raw
        node is directly matchable from Clausal."""
        cls = getattr(simple_ast, name)
        fields = {}
        for key, value in kwargs.items():
            if key in ("position", "_position"):
                fields["position"] = _const_value(value)
            else:
                fields[key] = self.term(value)
        return cls(**fields)

    # -- clause entry ---------------------------------------------------------

    def clause(self, predicate_ctor):
        """``Predicate(head=..., body=..., position=...)`` → Clause term."""
        kwargs = {kw.arg: kw.value for kw in predicate_ctor.keywords}
        head = self.term(kwargs["head"])
        goals = self.goals(kwargs["body"])
        return Clause(head, goals, self._position_of(kwargs))


# ── Module directives ────────────────────────────────────────────────────────

# Module-item class name → directive name.  Items not listed reify with a
# snake_cased class name; BareAtomRefs is compiler bookkeeping, not source.
_DIRECTIVE_NAMES = {
    "Directive": None,  # carries its own .name (dynamic/table/…)
    "ImportFromDirective": "import_from",
    "ImportModuleDirective": "import_module",
    "ModuleDeclaration": "module",
    "PrivateDeclaration": "private",
    "StrictAtomsDeclaration": "strict_atoms",
    "OverwritesDeclaration": "overwrites",
    "TranslationsDirective": "translations",
    "SpecializeDirective": "specialize",
    "EdcgAccDecl": "edcg_acc",
    "EdcgPassDecl": "edcg_pass",
    "EdcgPredDecl": "edcg_pred",
}

_SKIPPED_ITEMS = {"BareAtomRefs"}


def _plain_data(value):
    """Convert module-item field values to unification-friendly data
    (tuples/frozensets → lists)."""
    if isinstance(value, (list, tuple)):
        return [_plain_data(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(value)
    return value


def _reify_module_item(item):
    cls_name = type(item).__name__
    if cls_name in _SKIPPED_ITEMS:
        return None
    name = _DIRECTIVE_NAMES.get(cls_name, cls_name)
    args = []
    for field in dataclasses.fields(item):
        if field.name == "position":
            continue
        value = getattr(item, field.name)
        if cls_name == "Directive" and field.name == "name":
            name = value
            continue
        args.append(_plain_data(value))
    if cls_name == "Directive":
        # Directive holds specs in a single list field — splice it so
        # ``-dynamic(Color/2)`` reifies as args=[['Color', 2]].
        args = args[0]
    return ModuleDirective(name, args, getattr(item, "position", None))


# ── Embedded Python classification ───────────────────────────────────────────

_PY_KINDS = {
    ast.FunctionDef: "function",
    ast.AsyncFunctionDef: "function",
    ast.ClassDef: "class",
    ast.Import: "import",
    ast.ImportFrom: "import",
    ast.Assign: "assignment",
    ast.AnnAssign: "assignment",
    ast.AugAssign: "assignment",
    ast.Expr: "expression",
}


def _python_code_item(stmt):
    kind = _PY_KINDS.get(type(stmt), type(stmt).__name__.lower())
    name = getattr(stmt, "name", None)
    if name is None and isinstance(stmt, ast.Assign):
        target = stmt.targets[0]
        name = target.id if isinstance(target, ast.Name) else ""
    position = (stmt.lineno, stmt.col_offset, stmt.end_lineno, stmt.end_col_offset)
    return PythonCode(kind, name or "", position)


def _is_directive_stmt(stmt):
    """``-name(...)`` / ``-name`` expression statement (adjacent minus)."""
    if not isinstance(stmt, ast.Expr):
        return False
    value = stmt.value
    return (
        isinstance(value, ast.UnaryOp)
        and isinstance(value.op, ast.USub)
        and isinstance(value.operand, (ast.Call, ast.Name))
        and value.lineno == value.operand.lineno
        and value.col_offset == value.operand.col_offset - 1
    )


# ── Public API ───────────────────────────────────────────────────────────────


def reify_source(text, filename="<reflected>"):
    """Parse ``.clausal`` source text and reify every top-level item.

    Pure: no directive execution, no imports of the target's dependencies,
    no predicate compilation, and no evaluation of embedded Python or ``++``
    escapes.  Returns a list of ``ModuleDirective`` / ``Clause`` /
    ``PythonCode`` terms ordered by source position (directives, whose
    positions are not tracked, sort first)."""
    from clausal.templating.term_rewriting import EmbedTransformer

    source_lines = text.splitlines(keepends=True)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="'str' object is not callable",
                category=SyntaxWarning,
            )
            tree = ast.parse(text, filename=filename)
            transformer = EmbedTransformer(source_lines=source_lines)
            transformed = transformer.visit(tree)
    except SyntaxError as exc:
        raise ReifyError(str(exc)) from exc

    items = []
    for module_item in transformer._module_items:
        directive = _reify_module_item(module_item)
        if directive is not None:
            items.append(directive)

    clause_lines = set()
    # Shared across the source's clauses so a functor's canonical field order
    # is fixed by its first definition (F010).
    field_order: dict = {}
    for stmt in transformed.body:
        call = stmt.value if isinstance(stmt, ast.Expr) else None
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "$define_predicate"
        ):
            clause = _ClauseReifier(field_order=field_order).clause(call.args[0])
            items.append(clause)
            if clause.position is not None:
                clause_lines.update(range(clause.position[0], clause.position[2] + 1))

    # Original-AST pass: anything that is neither a directive nor covered by
    # a reified clause's line span is embedded Python.
    original = ast.parse(text, filename=filename)
    for stmt in original.body:
        if _is_directive_stmt(stmt):
            continue
        if any(
            line in clause_lines
            for line in range(stmt.lineno, stmt.end_lineno + 1)
        ):
            continue
        items.append(_python_code_item(stmt))

    def sort_key(indexed_item):
        index, item = indexed_item
        position = item.position
        line = position[0] if isinstance(position, tuple) else 0
        return (line, index)

    return [item for _, item in sorted(enumerate(items), key=sort_key)]


def reify_file(path):
    """``reify_source`` over a file's contents."""
    with open(path, encoding="utf-8") as source_file:
        return reify_source(source_file.read(), filename=path)


def _unparse_clause(node):
    """Unparse a ``.clausal`` statement, restoring the ``<-`` arrow.

    ``ast.unparse`` renders the clause arrow ``HEAD <- BODY`` as ``HEAD < -BODY``
    (a ``Compare`` with a single ``Lt`` and a ``USub`` comparator at the
    statement root). A blanket ``" < -" → " <- "`` replace also corrupts a
    genuine inner ``X < -1`` comparison (F012), so repair *only* the top-level
    arrow: unparse head and body separately and rejoin with a real ``<-``.
    """
    inner = node.value if isinstance(node, ast.Expr) else None
    if (isinstance(inner, ast.Compare)
            and len(inner.ops) == 1 and isinstance(inner.ops[0], ast.Lt)
            and isinstance(inner.comparators[0], ast.UnaryOp)
            and isinstance(inner.comparators[0].op, ast.USub)):
        head = ast.unparse(inner.left)
        body = ast.unparse(inner.comparators[0].operand)
        return f"{head} <- ({body})"
    return ast.unparse(node)


def reify_ast(node, source=None):
    """Reify a single parsed Python AST node of ``.clausal`` surface syntax.

    Statements round-trip through ``ast.unparse`` + :func:`reify_source`
    (``unparse`` renders the ``<-`` arrow as ``< -``, which is repaired);
    expressions reify directly in term context."""
    if isinstance(node, ast.Module):
        node = node.body[0]
    if isinstance(node, ast.Expression):
        node = node.body
    if isinstance(node, ast.stmt):
        text = source if source is not None else _unparse_clause(node)
        items = reify_source(text)
        if not items:
            raise ReifyError(f"no reifiable item in: {text}")
        return items[0]

    from clausal.templating.term_rewriting import TermTransformer

    ctor = TermTransformer().visit(node)
    return _ClauseReifier().term(ctor)
