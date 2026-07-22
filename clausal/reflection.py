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
from clausal.logic.variables import deref, is_var
from clausal.pythonic_ast import nodes as simple_ast


# Sentinel wrapping a rendered lambda body so nested clause arrows can be
# re-tightened (``< -`` → ``<-``) without touching a genuine ``X < -1``.
_LAMBDA_ARROW_MARKER = "__clausal_lambda_arrow__"


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
    "RenderError",
    "Variable",
    "reify_ast",
    "reify_file",
    "reify_source",
    "render_ast",
    "render_source",
]


class ReifyError(SyntaxError):
    """Raised when ``.clausal`` source cannot be reified."""


class RenderError(Exception):
    """Raised when a reified term cannot be rendered back to ``.clausal`` source."""


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


def _is_const_key(key):
    """True for a dict key that reifies to a hashable constant (string/int/float,
    or a tuple of those) and so may key a raw Python dict.  Anything else reifies
    unhashable — a bare-atom ``$intern_atom(...)`` call (the compiler's rewrite of
    ``{foo: V}``, see ``EmbedTransformer._visit_dict_key``) becomes a ``Goal``, a
    variable or walrus-bound name becomes a ``Variable``/``Atom``/term — so the
    literal must be represented as a ``DictLiteral`` instead."""
    if isinstance(key, ast.Constant):
        return True
    if isinstance(key, ast.Tuple):
        return all(_is_const_key(elt) for elt in key.elts)
    return (
        isinstance(key, ast.UnaryOp)
        and isinstance(key.op, ast.USub)
        and isinstance(key.operand, ast.Constant)
    )


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
            # A non-constant key reifies unhashable — a bare-atom key (`{foo: V}`,
            # rewritten to `$intern_atom('foo')`) becomes a Goal, a variable key
            # (`{K: V}`) becomes a Variable — and so cannot key a raw Python
            # dict.  When any key is non-constant, represent the whole literal as
            # the same DictLiteral node the splat path yields (keys stay in a
            # list, never used as a Python dict key) — one representation for
            # both dict-literal paths, round-tripped by _dict_literal_ast.  A
            # dict with only hashable (string/int) keys still reifies to a raw
            # dict: "dicts appear as themselves" (F013).
            if any(key is not None and not _is_const_key(key) for key in node.keys):
                return simple_ast.DictLiteral(
                    keys=[self.term(key) for key in node.keys],
                    values=[self.term(value) for value in node.values],
                )
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


# simple_ast operator class name → Python ast operator, for rendering.
_RENDER_BINOP_OPS = {
    "Add": ast.Add, "Sub": ast.Sub, "Mult": ast.Mult, "Div": ast.Div,
    "FloorDiv": ast.FloorDiv, "Mod": ast.Mod, "Pow": ast.Pow,
    "MatMult": ast.MatMult, "LShift": ast.LShift, "RShift": ast.RShift,
    "BitOr": ast.BitOr, "BitXor": ast.BitXor, "BitAnd": ast.BitAnd,
}
_RENDER_CMP_OPS = {
    "Lt": ast.Lt, "LtE": ast.LtE, "Gt": ast.Gt, "GtE": ast.GtE,
    "ArithEq": ast.Eq, "ArithNeq": ast.NotEq,
    "Unify": ast.Is, "DoesNotUnify": ast.IsNot,
    "in_": ast.In, "NotIn": ast.NotIn,
}
_RENDER_BOOL_OPS = {"And": ast.And, "Or": ast.Or}
_RENDER_UNARY_OPS = {
    "Not": ast.Not, "Negate": ast.USub, "UnaryPlus": ast.UAdd,
    "Invert": ast.Invert,
}

#: Names of the ``simple_ast`` operator classes the renderer can round-trip —
#: the union of the four ``_RENDER_*_OPS`` dispatch tables above.  Public so
#: :mod:`clausal.modules.reflection` (``op_node/3``) can name/build exactly this
#: set and stay bijective with :func:`render_source` without importing the
#: private tables.  Keep this derived from the tables, not hand-listed.
RENDER_OP_CLASS_NAMES = frozenset(
    (*_RENDER_BINOP_OPS, *_RENDER_CMP_OPS, *_RENDER_BOOL_OPS, *_RENDER_UNARY_OPS)
)


def _deref_field(value):
    """Deref a *name/structural field* that bypasses
    :meth:`_ClauseRenderer.term` — ``Goal.name``/``args``/``kwargs``,
    ``Clause.goals``, ``Escape.code``, dict keys, …

    A bound logic ``Var`` yields its value; an unbound one raises
    :class:`RenderError`, so the renderer never leaks a
    ``TypeError``/``AttributeError`` past its documented contract when such a
    field holds a var (e.g. an ``op_node``/matcher-built ``Goal`` whose name or
    args are bound late)."""
    value = deref(value)
    if is_var(value):
        raise RenderError(f"cannot render unbound variable: {value!r}")
    return value


def _deref_seq_field(value, what):
    """:func:`_deref_field` for a field that must be a concrete sequence — a
    goal/arg/param list, dict keys/values.  A var *or* a non-list/tuple raises
    :class:`RenderError` rather than leaking a ``TypeError`` from ``len``/
    iteration, so the renderer honours its contract on malformed terms too."""
    value = _deref_field(value)
    if not isinstance(value, (list, tuple)):
        raise RenderError(f"cannot render {what}: expected a sequence, got {value!r}")
    return value


class _ClauseRenderer:
    """Render a reified term back to a Python surface ``ast`` node — the
    inverse of :class:`_ClauseReifier`.  Building fresh nodes; positions are
    filled by :func:`ast.fix_missing_locations` before unparse."""

    # -- clause entry ---------------------------------------------------------

    def clause(self, term):
        """``Clause(head, goals, position)`` → an ``ast.Expr`` statement.

        A fact renders as an ``Expr`` wrapping a single-element ``ast.Tuple``
        ``(HEAD,)`` so re-reification sees a clause, not embedded Python;
        :func:`_unparse_clause` unparses it to the canonical fact *surface*
        ``HEAD,`` (bare head + trailing comma, no wrapping parens).  A rule
        renders as the ``Compare(head, [Lt], [USub(body)])`` shape that surface
        ``HEAD <- BODY`` parses to and that ``_unparse_clause`` repairs."""
        head = self.term(term.head)
        goals = _deref_seq_field(term.goals, "clause goals")
        if not goals:
            return ast.Expr(value=ast.Tuple(elts=[head], ctx=ast.Load()))
        if len(goals) == 1:
            body = self.goal(goals[0])
        else:
            body = ast.Tuple(
                elts=[self.goal(goal) for goal in goals], ctx=ast.Load()
            )
        arrow = ast.Compare(
            left=head, ops=[ast.Lt()],
            comparators=[ast.UnaryOp(op=ast.USub(), operand=body)],
        )
        return ast.Expr(value=arrow)

    def goal(self, node):
        """Goals render identically to terms (both are ``ast`` expressions)."""
        return self.term(node)

    # -- names ----------------------------------------------------------------

    def _name_ast(self, dotted):
        """``"a"`` → ``Name(a)``; ``"a.b.c"`` → nested ``Attribute`` chain.

        Every dotted segment must be a valid Python identifier — ``ast.unparse``
        does not validate ``Name.id``, so a mutated term carrying a name like
        ``"has space"`` or the reserved lambda sentinel would otherwise emit
        malformed text that re-reifies wrongly.  Refuse instead."""
        dotted = _deref_field(dotted)
        if not isinstance(dotted, str):
            raise RenderError(f"cannot render non-string name: {dotted!r}")
        parts = dotted.split(".")
        for part in parts:
            if not part.isidentifier() or part == _LAMBDA_ARROW_MARKER:
                raise RenderError(f"cannot render non-identifier name: {dotted!r}")
        node = ast.Name(id=parts[0], ctx=ast.Load())
        for part in parts[1:]:
            node = ast.Attribute(value=node, attr=part, ctx=ast.Load())
        return node

    def _parse_code(self, code, kind):
        """Re-parse an ``Escape``/``FormatString`` code string to an expression.

        From reification the code is always ``ast.unparse`` output (valid), but a
        mutated term may carry invalid source — raise :class:`RenderError` rather
        than leak a raw ``SyntaxError`` past the documented contract."""
        code = _deref_field(code)
        if not isinstance(code, str):
            raise RenderError(f"{kind} code must be a string: {code!r}")
        try:
            return ast.parse(code, mode="eval").body
        except SyntaxError as exc:
            raise RenderError(
                f"{kind} code is not a valid expression: {code!r}"
            ) from exc

    # -- terms ----------------------------------------------------------------

    def term(self, value):
        # A term may hold a bound *logic* Var (e.g. an operator node built by
        # op_node/3 over an operand bound after construction); follow the
        # binding so its value renders.  Deref is a no-op on everything else,
        # including reified `Variable` vocab terms (not logic vars).
        value = deref(value)
        if is_var(value):
            raise RenderError(f"cannot render unbound variable: {value!r}")
        if isinstance(value, Variable):
            # Anonymous vars reify to non-identifier names (#anon1, …); render
            # each as `_`.  Per-clause anon numbering is deterministic by
            # encounter order, so `_` re-reifies to the same #anonN.
            name = _deref_field(value.name)
            if not isinstance(name, str):
                raise RenderError(f"cannot render non-string variable name: {name!r}")
            display = "_" if name.startswith("#") else name
            return ast.Name(id=display, ctx=ast.Load())
        if isinstance(value, Atom):
            return self._name_ast(value.name)
        if isinstance(value, Goal):
            return self._goal_ast(value)
        if isinstance(value, bool):
            return ast.Constant(value)
        if isinstance(value, (int, float, complex)):
            return ast.Constant(value)
        if isinstance(value, str):
            return ast.Constant(value)
        if isinstance(value, (ModuleDirective, PythonCode)):
            raise RenderError(
                f"cannot render {type(value).__name__} — only clause bodies "
                "are in scope for the renderer"
            )
        if isinstance(value, list):
            return ast.List(
                elts=[self.term(item) for item in value], ctx=ast.Load()
            )
        if isinstance(value, tuple):
            return ast.Tuple(
                elts=[self.term(item) for item in value], ctx=ast.Load()
            )
        if isinstance(value, dict):
            key_nodes, seen = [], set()
            for key in value:
                key_node = self.term(key)
                # re-reification is textual, so keys that *unparse* the same
                # collide and would silently drop a key — refuse instead.
                surface = ast.unparse(key_node)
                if surface in seen:
                    raise RenderError(f"duplicate dict key after deref: {surface!r}")
                seen.add(surface)
                key_nodes.append(key_node)
            return ast.Dict(
                keys=key_nodes,
                values=[self.term(val) for val in value.values()],
            )
        if isinstance(value, IfThenElse):
            return ast.Call(
                func=ast.Name(id="If", ctx=ast.Load()),
                args=[
                    self.term(value.condition),
                    self.term(value.then),
                    self.term(value.otherwise),
                ],
                keywords=[],
            )
        if isinstance(value, Escape):
            # `++(<code>)`: the escaped expression text re-parsed and wrapped in
            # two adjacent unary `+` — ast.unparse emits `++(code)`, which the
            # reifier re-detects as an escape and re-collects the captured vars.
            inner = self._parse_code(value.code, "Escape")
            return ast.UnaryOp(
                op=ast.UAdd(),
                operand=ast.UnaryOp(op=ast.UAdd(), operand=inner),
            )
        if isinstance(value, FormatString):
            return self._parse_code(value.code, "FormatString")
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return self._operator_ast(value)
        raise RenderError(f"cannot render term: {value!r}")

    def _operator_ast(self, node):
        """Raw ``simple_ast`` operator node → Python ``ast`` operator expr."""
        name = type(node).__name__
        if name in _RENDER_BINOP_OPS:
            return ast.BinOp(
                left=self.term(node.left),
                op=_RENDER_BINOP_OPS[name](),
                right=self.term(node.right),
            )
        if name in _RENDER_CMP_OPS:
            return ast.Compare(
                left=self.term(node.left),
                ops=[_RENDER_CMP_OPS[name]()],
                comparators=[self.term(node.right)],
            )
        if name in _RENDER_BOOL_OPS:
            return ast.BoolOp(
                op=_RENDER_BOOL_OPS[name](),
                values=[self.term(node.left), self.term(node.right)],
            )
        if name in _RENDER_UNARY_OPS:
            operand = self.term(node.operand)
            if (name == "UnaryPlus"
                    and isinstance(operand, ast.UnaryOp)
                    and isinstance(operand.op, ast.UAdd)):
                # `+(+X)` / `+(++X)`: ast.unparse drops the column gap the
                # reifier uses to tell nested unary-plus from the `++` escape,
                # so the text would silently re-reify as an Escape.  Refuse.
                raise RenderError(
                    "cannot render UnaryPlus over a '+'-prefixed operand: "
                    "ast.unparse would emit adjacent '++', which re-reifies "
                    "as a Python escape"
                )
            return ast.UnaryOp(op=_RENDER_UNARY_OPS[name](), operand=operand)
        if name == "StarUnpack":
            return ast.Starred(value=self.term(node.value), ctx=ast.Load())
        if name == "LoadSubscript":
            # ``object[index]`` — index is a term (often a dotted atom).
            return ast.Subscript(
                value=self.term(node.object),
                slice=self.term(node.index),
                ctx=ast.Load(),
            )
        if name == "Lambda":
            return self._lambda_ast(node)
        if name == "DictLiteral":
            return self._dict_literal_ast(node)
        raise RenderError(f"cannot render operator node: {name}")

    def _lambda_ast(self, node):
        """``Lambda(params, body)`` → the ``(P1, …, Pn) <- BODY`` term surface.

        In term position the reifier parses a parenthesised clause arrow into a
        ``Lambda`` node whose params are plain names and whose body is a goal.
        Rebuild the ``Compare(Tuple(params), [Lt], [USub(body)])`` shape that
        surface re-parses to.  Params reify to ``Atom`` when referenced in the
        body, so render each param name straight from ``node.params``.

        ``ast.unparse`` renders the arrow's ``<`` and ``-`` with a space
        (``(P) < -BODY``), which defeats the reifier's source-adjacency arrow
        detection — and a spaced ``X < -1`` is a *genuine* comparison, so the
        gap cannot be blindly collapsed.  Wrap the body in the sentinel call
        ``_LAMBDA_ARROW_MARKER(BODY)`` so :func:`_tighten_nested_arrows` can
        locate exactly the rendered lambda arrows (never a real ``<``), tighten
        the gap, and strip the wrapper."""
        params_container = _deref_field(node.params)
        param_items = _deref_seq_field(params_container.params, "lambda params")
        param_names = []
        for param in param_items:
            name = _deref_field(_deref_field(param).name)
            if not isinstance(name, str) or not name.isidentifier():
                raise RenderError(f"cannot render non-identifier lambda param: {name!r}")
            param_names.append(name)
        params_tuple = ast.Tuple(
            elts=[ast.Name(id=n, ctx=ast.Load()) for n in param_names],
            ctx=ast.Load(),
        )
        marked_body = ast.Call(
            func=ast.Name(id=_LAMBDA_ARROW_MARKER, ctx=ast.Load()),
            args=[self.term(node.body)],
            keywords=[],
        )
        return ast.Compare(
            left=params_tuple,
            ops=[ast.Lt()],
            comparators=[ast.UnaryOp(op=ast.USub(), operand=marked_body)],
        )

    def _dict_literal_ast(self, node):
        """``DictLiteral(keys, values)`` → an ``ast.Dict`` term surface.

        A key of ``None`` is a ``**splat`` (``{**value}``); an atom key
        reifies wrapped in ``$intern_atom(<name>)`` and renders back to a bare
        ``Name`` so the surface ``{name: value}`` re-interns it identically."""
        node_keys = _deref_seq_field(node.keys, "dict-literal keys")
        node_values = _deref_seq_field(node.values, "dict-literal values")
        keys, values = [], []
        for key, value in zip(node_keys, node_values):
            key = None if key is None else deref(key)
            keys.append(None if key is None else self._dict_key_ast(key))
            values.append(self.term(value))
        return ast.Dict(keys=keys, values=values)

    def _dict_key_ast(self, key):
        """A DictLiteral key: ``$intern_atom(<name>)`` → the bare name node."""
        key = _deref_field(key)
        if isinstance(key, Goal) and _deref_field(key.name) == "$intern_atom":
            args = _deref_seq_field(key.args, "$intern_atom key args")
            if len(args) == 1 and isinstance(_deref_field(args[0]), str):
                return self._name_ast(args[0])
        return self.term(key)

    def _goal_ast(self, goal):
        """``Goal(name, args, kwargs)`` → ``ast.Call``.

        ``name``/``args``/``kwargs``, each kwarg *entry* and its name may be
        bound logic vars (or garbage) on a matcher-built goal — deref/guard them
        so the call renders or raises ``RenderError``, never leaking a
        ``TypeError`` on the raw var."""
        args = _deref_seq_field(goal.args, "goal args")
        kwargs = _deref_seq_field(goal.kwargs, "goal kwargs")
        keywords = []
        for entry in kwargs:
            try:
                name, value = _deref_field(entry)
            except (TypeError, ValueError):
                raise RenderError(f"cannot render keyword entry: {entry!r}")
            name = _deref_field(name)
            if not isinstance(name, str):
                raise RenderError(f"cannot render non-string keyword name: {name!r}")
            keywords.append(ast.keyword(arg=name, value=self.term(value)))
        return ast.Call(
            func=self._name_ast(goal.name),
            args=[self.term(arg) for arg in args],
            keywords=keywords,
        )


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
        head = _tighten_nested_arrows(ast.unparse(inner.left))
        body = _tighten_nested_arrows(ast.unparse(inner.comparators[0].operand))
        return f"{head} <- ({body})"
    if isinstance(inner, ast.Tuple) and len(inner.elts) == 1:
        # Fact: ``_ClauseRenderer.clause`` wraps the head in a 1-tuple so this
        # ``Expr`` re-reifies as a Clause (a bare head reifies as embedded
        # Python).  ``ast.unparse`` would emit the Python tuple literal
        # ``(head,)``; the canonical clausal fact surface is ``head,`` (bare head
        # + trailing comma, no wrapping parens).  Emit that so a rendered fact
        # matches the corpus surface the mutation auditor splices back into a file.
        head = _tighten_nested_arrows(ast.unparse(inner.elts[0]))
        return f"{head},"
    return _tighten_nested_arrows(ast.unparse(node))


def _tighten_nested_arrows(text):
    """Re-tighten ``ast.unparse``'s ``head < -body`` back to ``head <- body``
    for nested lambda arrows, and strip the lambda-body sentinel.

    ``ast.unparse`` always separates a clause arrow's ``<`` and ``-`` with a
    space, which defeats the reifier's source-adjacency arrow detection; the
    same spaced ``X < -1`` is a *genuine* comparison, so the gap cannot be
    blindly collapsed.  :meth:`_ClauseRenderer._lambda_ast` therefore wraps
    each rendered lambda body in a ``_LAMBDA_ARROW_MARKER(BODY)`` sentinel call.
    Locate exactly those ``Compare(Lt, [USub(Call(marker, [body]))])`` nodes via
    a re-parse (never a real ``<``), tighten the ``< -`` to ``<-``, and remove
    the wrapper — leaving ``(P) <- BODY``.  A genuine ``X < -1`` carries no
    marker and is left untouched (F012)."""
    if _LAMBDA_ARROW_MARKER not in text:
        return text
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        # Cannot locate the markers to strip; fall through to the post-condition
        # below, which raises rather than emit sentinel-bearing text.
        tree = None
    edits = []
    lines = text.splitlines(keepends=True)
    line_starts, running = [], 0
    for line in lines:
        line_starts.append(running)
        running += len(line)

    def abs_offset(lineno, col):
        return line_starts[lineno - 1] + col

    # Each edit: (start, end, replacement) over the ORIGINAL text; applied R→L.
    for sub in ast.walk(tree) if tree is not None else ():
        if not (isinstance(sub, ast.Compare)
                and len(sub.ops) == 1 and isinstance(sub.ops[0], ast.Lt)
                and isinstance(sub.comparators[0], ast.UnaryOp)
                and isinstance(sub.comparators[0].op, ast.USub)):
            continue
        usub = sub.comparators[0]
        call = usub.operand
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == _LAMBDA_ARROW_MARKER
                and len(call.args) == 1):
            continue
        # Collapse the '< -' gap: the '-' is at the USub's column.
        minus_off = abs_offset(usub.lineno, usub.col_offset)
        lt_off = text.rfind("<", 0, minus_off)
        if lt_off != -1:
            edits.append((lt_off, minus_off + 1, "<-"))
        # Strip the sentinel wrapper but KEEP parentheses around the body:
        # the reifier requires a non-call/non-name arrow body to be
        # parenthesized, and unparse's ``marker(BODY)`` parens are the only
        # ones present.  Rewrite ``marker(`` → ``(`` and leave the closing
        # ``)`` so ``(P) <- (BODY)`` survives.
        call_start = abs_offset(call.lineno, call.col_offset)
        arg = call.args[0]
        arg_start = abs_offset(arg.lineno, arg.col_offset)
        edits.append((call_start, arg_start, "("))
    for start, end, repl in sorted(edits, reverse=True):
        text = text[:start] + repl + text[end:]
    if _LAMBDA_ARROW_MARKER in text:
        # Post-condition: every rendered lambda arrow must have been located and
        # its sentinel stripped.  A surviving marker means the lambda sat in a
        # position this pass could not reach (or the text did not re-parse) —
        # emitting it would silently corrupt, so fail loudly instead.
        raise RenderError(
            f"lambda-arrow sentinel survived rendering: {text!r}"
        )
    return text


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


def render_ast(term):
    """Render a reified term back to a Python surface ``ast`` node — the
    inverse of :func:`reify_ast`.

    A ``Clause`` renders to an ``ast.Expr`` statement; any other reified term
    renders to an expression node.  Raises :class:`RenderError` for any node
    kind the renderer does not handle (never emits malformed source)."""
    term = deref(term)  # a top-level var bound to a Clause must take the clause path
    renderer = _ClauseRenderer()
    if isinstance(term, Clause):
        node = renderer.clause(term)
    else:
        node = renderer.term(term)
    return ast.fix_missing_locations(node)


def render_source(term):
    """Render a reified term to ``.clausal`` source text — :func:`render_ast`
    followed by ``ast.unparse`` with the ``<-`` arrow repair."""
    node = render_ast(term)
    if isinstance(node, ast.Expr):
        return _unparse_clause(node)
    return _tighten_nested_arrows(ast.unparse(node))
