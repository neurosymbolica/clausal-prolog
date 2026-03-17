from ast import *

from .parser import is_template_func
from .compiler import compile_template_func

# Module-level item types for the pipeline-split ModuleAST.
from clausal.pythonic_ast.nodes import (
    Directive as DirectiveItem,
    EdcgAccDecl,
    EdcgPassDecl,
    EdcgPredDecl,
    ImportFromDirective as ImportFromItem,
    ImportModuleDirective as ImportModuleItem,
    ModuleDeclaration as ModuleDeclItem,
    PrivateDeclaration as PrivateDeclItem,
    Predicate as PredicateItem,
)

load = Load()
store = Store()


# ─── Source-position helpers ──────────────────────────────────────────────────


def replace(new, start, end=None):
    if end is None:
        end = start
    new.lineno = start.lineno
    new.col_offset = start.col_offset
    new.end_lineno = end.end_lineno
    new.end_col_offset = end.end_col_offset
    return new


def load_name_ast(name, source):
    return replace(Name(id=name, ctx=load), source)


def make_keyword_node(arg, value, source):
    keyword_node = keyword(arg=arg, value=value)
    keyword_node.lineno = source.lineno
    keyword_node.col_offset = source.col_offset
    keyword_node.end_lineno = source.end_lineno
    keyword_node.end_col_offset = source.end_col_offset
    return keyword_node


def pos_ast(source, end=None):
    """Generate Python AST for SourcePosition(lineno=..., col_offset=..., ...)"""
    if end is None:
        end = source
    return replace(
        Tuple(
            elts=[
                replace(Constant(value=source.lineno), source),
                replace(Constant(value=source.col_offset), source),
                replace(Constant(value=end.end_lineno), source),
                replace(Constant(value=end.end_col_offset), source),
            ],
            ctx=Load()
        ),
        source,
    )


def node_ast(classname, source, end=None, **fields):
    """Generate Python AST for: classname(field=val, ..., position=SourcePosition(...))"""
    keywords = [
        make_keyword_node(field_name, field_value, source)
        for field_name, field_value in fields.items()
    ]
    keywords.append(make_keyword_node("position", pos_ast(source, end), source))
    return replace(
        Call(func=load_name_ast(classname, source), args=[], keywords=keywords), source
    )


def list_ast(elements, source):
    """Generate Python AST for a list literal [elem, ...]"""
    return replace(List(elts=list(elements), ctx=load), source)


# ─── Operator → simple_ast class name mappings ────────────────────────────────

BINOP_CLS = {
    Add: "Add",
    Sub: "Sub",
    Mult: "Mult",
    Div: "Div",
    FloorDiv: "FloorDiv",
    Mod: "Mod",
    Pow: "Pow",
    MatMult: "MatMult",
    LShift: "LShift",
    RShift: "RShift",
    BitOr: "BitOr",
    BitXor: "BitXor",
    BitAnd: "BitAnd",
}

UNARYOP_CLS = {
    USub: "Negate",
    UAdd: "UnaryPlus",
    Not: "Not",
    Invert: "Invert",
}

BOOLOP_CLS = {
    And: "And",
    Or: "Or",
}

CMPOP_CLS = {
    Eq: "StructuralEq",       # ==  structural equality (deref'd)
    NotEq: "StructuralNeq",   # !=  structural inequality (deref'd)
    Lt: "Lt",                 # <   arithmetic comparison (evaluates)
    LtE: "LtE",               # <=  arithmetic comparison (evaluates)
    Gt: "Gt",                 # >   arithmetic comparison (evaluates)
    GtE: "GtE",               # >=  arithmetic comparison (evaluates)
    Is: "Unify",              # is  unification (structural, no arithmetic eval)
    IsNot: "DoesNotUnify",    # is not  dif / negation of unification
    In: "In",                 # in  membership / enumeration
    NotIn: "NotIn",           # not in  non-membership
}


# ─── Arrow (<-) detection helpers ────────────────────────────────────────────

_ARROW_BODY_ERROR = (
    "clause body must be parenthesized or a single call: "
    "write  head <- (body)  or  head <- goal(X)"
)


def _leftmost_usub(node):
    """Walk the leftmost spine of *node* looking for a USub from ``<-``.

    Returns ``(usub_node, depth)`` where *depth* is how many nodes were
    traversed, or ``(None, 0)`` if no USub is reachable.  The walk follows
    the "leftmost child" of each node type — the child that occupies the
    leftmost source position and therefore absorbs the ``-`` from ``<-``
    due to operator precedence.
    """
    depth = 0
    while True:
        if isinstance(node, UnaryOp) and isinstance(node.op, USub):
            return node, depth
        elif isinstance(node, BinOp):
            node = node.left
        elif isinstance(node, Compare):
            node = node.left
        elif isinstance(node, BoolOp):
            node = node.values[0]
        elif isinstance(node, Subscript):
            node = node.value
        elif isinstance(node, Attribute):
            node = node.value
        elif isinstance(node, Call):
            node = node.func
        elif isinstance(node, Starred):
            node = node.value
        elif isinstance(node, IfExp):
            node = node.body
        else:
            return None, 0
        depth += 1


def _is_arrow_adjacent(left, usub_node):
    """True if ``<`` and ``-`` are adjacent (gap ≤ 2 columns, same line).

    Raises ``ValueError`` when position attributes are missing, which
    happens with programmatically constructed AST nodes that were never
    passed through ``ast.parse()`` or ``ast.fix_missing_locations()``.
    """
    try:
        end_line = left.end_lineno
        end_col = left.end_col_offset
        usub_line = usub_node.lineno
        usub_col = usub_node.col_offset
    except AttributeError:
        raise ValueError(
            "AST nodes passed to arrow detection are missing source "
            "positions (lineno/col_offset); use ast.fix_missing_locations() "
            "on programmatically constructed AST trees"
        ) from None
    if end_line is None or end_col is None or usub_line is None or usub_col is None:
        raise ValueError(
            "AST nodes passed to arrow detection have None source "
            "positions; use ast.fix_missing_locations() on programmatically "
            "constructed AST trees"
        )
    return end_line == usub_line and 1 <= usub_col - end_col <= 2


def _detect_arrow(left, operators, comparators):
    """Detect ``<-`` in a Compare node.

    Returns ``(head_ast, body_ast)`` if the Compare represents
    ``head <- body``, or ``None`` if this is not a ``<-`` expression.

    The body after ``<-`` must be one of:

    * a single call — ``head <- goal(X)``
    * a bare name  — ``head <- true``
    * a parenthesized expression — ``head <- (body)``

    When parenthesized, the USub from ``<-`` sits directly on top of the
    body expression (path depth 0).  Unparenthesized non-call/non-name
    bodies cause the USub to be absorbed deeper into the AST; these are
    detected and rejected with a clear error.
    """
    if not operators or not isinstance(operators[0], Lt):
        return None

    first_comp = comparators[0]
    usub_node, depth = _leftmost_usub(first_comp)
    if usub_node is None:
        return None

    if not _is_arrow_adjacent(left, usub_node):
        return None

    # The <- was found.  Now enforce the parenthesization rule.
    #
    # Simple case (depth 0, single operator): USub sits directly on the
    # comparator.  The body is either parenthesized, a call, or a bare name
    # — all safe.
    #
    # If depth > 0 the USub was buried inside a BinOp/Compare/etc chain,
    # meaning the body was not parenthesized and contains operators.
    # If len(operators) > 1 the body contains comparison operators that
    # Python absorbed into a chained comparison.  Both cases are rejected.
    if depth > 0 or len(operators) > 1:
        raise SyntaxError(_ARROW_BODY_ERROR)

    return left, usub_node.operand


def _extract_arrow_lambda_params(head_ast):
    """Extract lambda parameter names from an arrow head, or return None.

    Returns a list of parameter name strings if the head is a valid lambda
    parameter list (all logic-variable names, or an empty tuple).  Returns
    ``None`` if the head is not a lambda-style parameter list (e.g. a
    functor call like ``foo(X_)``).
    """
    # Single variable: X_ <- body
    if isinstance(head_ast, Name) and _is_logic_var_name(head_ast.id):
        return [head_ast.id]
    # Tuple of variables: (X_, Y_) <- body  or  () <- body
    if isinstance(head_ast, Tuple):
        params = []
        for elt in head_ast.elts:
            if isinstance(elt, Name) and _is_logic_var_name(elt.id):
                params.append(elt.id)
            else:
                return None  # non-variable element → not a lambda
        return params
    return None


def _check_hidden_arrow(node):
    """Raise if a top-level BoolOp hides a ``<-`` clause arrow.

    When the user writes ``head <- a or b`` without parenthesizing the
    body, Python parses it as ``(head < -a) or b`` — a BoolOp whose first
    value contains a Compare with an adjacent ``< -``.
    """
    if isinstance(node, BoolOp):
        inner = node.values[0]
    else:
        return
    if not isinstance(inner, Compare):
        return
    if not inner.ops or not isinstance(inner.ops[0], Lt):
        return
    first_comp = inner.comparators[0]
    usub_node, _ = _leftmost_usub(first_comp)
    if usub_node is not None and _is_arrow_adjacent(inner.left, usub_node):
        raise SyntaxError(_ARROW_BODY_ERROR)


# ─── Logic variable name helper ───────────────────────────────────────────────


def _is_logic_var_name(identifier: str) -> bool:
    """Return True if ``identifier`` should be treated as a logic variable.

    Two conventions are recognised:

    * **Trailing single underscore** — ``X_``, ``foo_``, ``HEAD_``.
      The underscore must be a single trailing one; dunders (``__``) and the
      bare ``_`` wildcard are excluded.
    * **ALL-CAPS** — ``X``, ``FOO``, ``HEAD``, ``TAIL``.
      Every *cased* character must be uppercase and there must be at least one
      cased character (so plain ``_`` and digit-only names are excluded).
      Underscores and digits are allowed inside (e.g. ``N1``, ``MAX_OF``).
    """
    if identifier == "_":
        return False
    if identifier.endswith("__"):
        return False
    if identifier.endswith("_"):
        return True
    # ALL-CAPS: str.isupper() is True iff all cased chars are uppercase AND
    # there is at least one cased character — exactly what we want.
    return identifier.isupper()


def _collect_logic_var_names(node) -> list[str]:
    """Collect logic variable names from an AST node in first-occurrence order."""
    ordered: list[str] = []
    seen: set[str] = set()

    class _Collector(NodeVisitor):
        def visit_Name(self, name):
            ident = name.id
            if ident != "_" and _is_logic_var_name(ident):
                if ident not in seen:
                    seen.add(ident)
                    ordered.append(ident)
            self.generic_visit(name)

    _Collector().visit(node)
    return ordered


def _build_py_thunk_ast(transformer, node, expression, var_names, thunk_cls="PyThunk"):
    """Build a ``PyThunk(lambda V1, ...: expr, [V1_var, ...])`` AST node.

    Shared by ``visit_JoinedStr`` (f-strings) and ``visit_UnaryOp`` (``++()``).
    *transformer* is the enclosing ``TermTransformer`` (for ``seen_vars``).
    *node* is used for source locations.  *expression* is the lambda body AST.
    *var_names* is the ordered list of logic variable names.
    """
    lambda_params = [
        arg(arg=name, annotation=None,
            lineno=node.lineno, col_offset=node.col_offset,
            end_lineno=node.end_lineno, end_col_offset=node.end_col_offset)
        for name in var_names
    ]
    lambda_node = replace(
        Lambda(
            args=arguments(
                posonlyargs=[], args=lambda_params, vararg=None,
                kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=expression,
        ),
        node,
    )

    var_ref_asts = []
    for name in var_names:
        if name not in transformer.seen_vars:
            transformer.seen_vars.add(name)
            var_ref_asts.append(replace(
                NamedExpr(
                    target=replace(Name(id=name, ctx=store), node),
                    value=replace(
                        Call(
                            func=replace(Name(id="Var", ctx=load), node),
                            args=[], keywords=[],
                        ),
                        node,
                    ),
                ),
                node,
            ))
        else:
            var_ref_asts.append(replace(Name(id=name, ctx=load), node))

    return replace(
        Call(
            func=replace(Name(id=thunk_cls, ctx=load), node),
            args=[
                lambda_node,
                replace(List(elts=var_ref_asts, ctx=load), node),
            ],
            keywords=[],
        ),
        node,
    )


# ─── Term Transformer ─────────────────────────────────────────────────────────


class TermTransformer(NodeTransformer):
    """Transform a Python expression AST into Python AST that constructs simple_ast nodes."""

    def __init__(transformer, atoms=frozenset(), import_remap=None):
        transformer.seen_vars = set()
        transformer.atoms = atoms
        transformer._import_remap = import_remap or {}

    def visit_Await(transformer, await_expr):
        return node_ast("Await", await_expr, value=transformer.visit(await_expr.value))

    def visit_BinOp(transformer, binary_operation):
        class_name = BINOP_CLS[type(binary_operation.op)]
        return node_ast(
            class_name,
            binary_operation,
            left=transformer.visit(binary_operation.left),
            right=transformer.visit(binary_operation.right),
        )

    def visit_BoolOp(transformer, bool_operation):
        _check_hidden_arrow(bool_operation)
        # Python's BoolOp has N values; simple_ast uses nested binary And/Or
        class_name = BOOLOP_CLS[type(bool_operation.op)]
        value_nodes = [
            transformer.visit(value_node) for value_node in bool_operation.values
        ]
        result = value_nodes[0]
        for value_node in value_nodes[1:]:
            result = node_ast(class_name, bool_operation, left=result, right=value_node)
        return result

    def visit_Call(transformer, call):
        visit = transformer.visit

        # q(expr) — quasi-quotation: produces the simple_ast node for expr.
        # The inner expression is transformed by the SAME TermTransformer
        # (sharing seen_vars), so variables are unified across the clause.
        if (
            isinstance(call.func, Name)
            and call.func.id == "q"
            and len(call.args) == 1
            and not call.keywords
        ):
            return visit(call.args[0])

        # If(cond, then) or If(cond, then, else) → IfExpr node
        if isinstance(call.func, Name) and call.func.id == "If":
            if call.keywords or len(call.args) != 3:
                raise SyntaxError(
                    "If() takes exactly 3 positional arguments: "
                    "If(condition, then, else)"
                )
            return node_ast(
                "IfExpr", call,
                test=visit(call.args[0]),
                body=visit(call.args[1]),
                orelse=visit(call.args[2]),
            )

        # A string literal used as the callable, e.g. '+'(a, b), is sugar for a
        # name reference whose identifier is that string.
        if isinstance(call.func, Constant) and isinstance(call.func.value, str):
            func_node = visit(replace(Name(id=call.func.value, ctx=load), call.func))
        else:
            func_node = visit(call.func)
        positional_args = [visit(argument) for argument in call.args]
        # Convert keyword arguments to Keyword simple_ast nodes
        keyword_argument_nodes = [
            node_ast(
                "Keyword",
                keyword_item,
                name=replace(Constant(value=keyword_item.arg), keyword_item),
                value=visit(keyword_item.value),
            )
            for keyword_item in call.keywords
        ]
        return node_ast(
            "Call",
            call,
            func=func_node,
            args=list_ast(positional_args, call),
            kwargs=list_ast(keyword_argument_nodes, call),
        )

    def visit_Compare(transformer, compare):
        operators = compare.ops
        comparators = compare.comparators
        left = compare.left

        # Detect '<-' pseudo-operator: written as  a <- b  in source.
        #
        # Python parses `a <- b` as Compare(a, [Lt], [UnaryOp(USub, b)]).
        # When the body contains operators with lower precedence than unary
        # minus, the USub ends up buried as the leftmost node of the body
        # expression.  When the body itself contains comparisons (e.g.
        # `a <- 1 < 2`), Python produces a chained comparison with multiple
        # operators.  _detect_arrow handles all of these cases.
        arrow = _detect_arrow(left, operators, comparators)
        if arrow is not None:
            head_ast, body_ast = arrow
            # If the head consists solely of logic-variable names (or is an
            # empty tuple), treat the expression-level ``<-`` as a lambda
            # (anonymous clause).  Otherwise fall through to Predicate node
            # (used by assertz for rule assertions).
            lambda_params = _extract_arrow_lambda_params(head_ast)
            if lambda_params is not None:
                return transformer._build_arrow_lambda(
                    lambda_params, body_ast, compare,
                )
            return node_ast(
                "Predicate",
                compare,
                head=transformer.visit(head_ast),
                body=transformer.visit(body_ast),
            )

        # Detect 'X == +Y': StructuralEq with a UnaryPlus right-hand side → ArithConstraint stub.
        # Emits ArithConstraint(expr=StructuralEq(X, Y)) so the compiler can raise NotImplementedError.
        if (
            len(operators) == 1
            and isinstance(operators[0], Eq)
            and isinstance(comparators[0], UnaryOp)
            and isinstance(comparators[0].op, UAdd)
        ):
            eq_node = node_ast(
                "StructuralEq",
                compare,
                left=transformer.visit(left),
                right=transformer.visit(comparators[0].operand),
            )
            return node_ast("ArithConstraint", compare, expr=eq_node)

        if len(operators) == 1:
            class_name = CMPOP_CLS[type(operators[0])]
            return node_ast(
                class_name,
                compare,
                left=transformer.visit(left),
                right=transformer.visit(comparators[0]),
            )

        # Multi-comparison chain → CompareChain
        all_operands = [left] + list(comparators)
        comparison_nodes = [
            node_ast(
                CMPOP_CLS[type(operator)],
                all_operands[index],
                left=transformer.visit(all_operands[index]),
                right=transformer.visit(all_operands[index + 1]),
            )
            for index, operator in enumerate(operators)
        ]
        return node_ast(
            "CompareChain", compare, comparisons=list_ast(comparison_nodes, compare)
        )

    def visit_Constant(transformer, constant):
        # Python built-in literals are terms directly — return the constant as-is.
        # The evaluator sees the native Python value (int, float, str, bool, None, …).
        return constant

    def visit_Dict(transformer, dict_expr):
        # If any key is None, this is a **splat dict — fall back to DictLiteral
        # (full splat/merge support is Phase 3).
        has_splat = any(k is None for k in dict_expr.keys)
        if has_splat:
            keys = list_ast(
                [
                    (
                        transformer.visit(key)
                        if key is not None
                        else replace(Constant(value=None), dict_expr)
                    )
                    for key in dict_expr.keys
                ],
                dict_expr,
            )
            values = list_ast(
                [transformer.visit(value_node) for value_node in dict_expr.values],
                dict_expr,
            )
            return node_ast("DictLiteral", dict_expr, keys=keys, values=values)

        # Emit DictTerm({k1: v1, k2: v2, ...}) constructor call.
        # Keys and values are transformed recursively.
        key_asts = [transformer.visit(k) for k in dict_expr.keys]
        val_asts = [transformer.visit(v) for v in dict_expr.values]
        dict_arg = replace(
            Dict(keys=key_asts, values=val_asts),
            dict_expr,
        )
        return replace(
            Call(
                func=replace(Name(id="DictTerm", ctx=load), dict_expr),
                args=[dict_arg],
                keywords=[],
            ),
            dict_expr,
        )

    def visit_DictComp(transformer, dict_comprehension):
        clauses = [
            transformer._visit_comprehension(clause)
            for clause in dict_comprehension.generators
        ]
        return node_ast(
            "DictComp",
            dict_comprehension,
            key=transformer.visit(dict_comprehension.key),
            value=transformer.visit(dict_comprehension.value),
            clauses=list_ast(clauses, dict_comprehension),
        )

    def visit_GeneratorExp(transformer, generator_expression):
        clauses = [
            transformer._visit_comprehension(clause)
            for clause in generator_expression.generators
        ]
        return node_ast(
            "GeneratorExpr",
            generator_expression,
            element=transformer.visit(generator_expression.elt),
            clauses=list_ast(clauses, generator_expression),
        )

    def visit_IfExp(transformer, if_expression):
        raise SyntaxError(
            "Ternary 'THEN if COND else ELSE' is not supported; "
            "use If(COND, THEN, ELSE) instead"
        )

    def visit_Lambda(transformer, lambda_expr):
        raise SyntaxError(
            "Python 'lambda' syntax is not supported in .clausal files; "
            "use arrow syntax instead: X_ <- (body) or (X_, Y_) <- (body)"
        )

    def _build_arrow_lambda(transformer, param_names, body_ast, source):
        """Build a Lambda node from ``(X_, Y_) <- (body)`` arrow syntax.

        Uses the same capture/LoadName mechanism as ``visit_Lambda``.
        """
        lambda_transformer = TermTransformer(import_remap=transformer._import_remap)
        lambda_transformer.seen_vars = transformer.seen_vars.copy()

        logic_var_params = [p for p in param_names if _is_logic_var_name(p)]
        lambda_transformer._load_names = (
            set(logic_var_params)
            | getattr(transformer, '_load_names', set())
        )
        lambda_transformer.seen_vars.update(logic_var_params)

        # Build Params AST — each param is a PosOrKwParam.
        if param_names:
            param_nodes = [
                replace(
                    Call(
                        func=load_name_ast("PosOrKwParam", source),
                        args=[],
                        keywords=[
                            make_keyword_node(
                                "name",
                                replace(Constant(value=name), source),
                                source,
                            ),
                        ],
                    ),
                    source,
                )
                for name in param_names
            ]
            params = replace(
                Call(
                    func=load_name_ast("Params", source),
                    args=[],
                    keywords=[
                        make_keyword_node(
                            "params",
                            list_ast(param_nodes, source),
                            source,
                        ),
                    ],
                ),
                source,
            )
        else:
            params = replace(
                Call(
                    func=load_name_ast("Params", source),
                    args=[],
                    keywords=[
                        make_keyword_node(
                            "params",
                            list_ast([], source),
                            source,
                        ),
                    ],
                ),
                source,
            )

        body = lambda_transformer.visit(body_ast)
        return node_ast("Lambda", source, params=params, body=body)

    def visit_List(transformer, list_expr):
        # Python lists are terms directly — emit a plain Python list.
        elements = [transformer.visit(element) for element in list_expr.elts]
        return list_ast(elements, list_expr)

    def visit_ListComp(transformer, list_comprehension):
        clauses = [
            transformer._visit_comprehension(clause)
            for clause in list_comprehension.generators
        ]
        return node_ast(
            "ListComp",
            list_comprehension,
            element=transformer.visit(list_comprehension.elt),
            clauses=list_ast(clauses, list_comprehension),
        )

    def visit_Name(transformer, name):
        identifier = name.id
        # Anonymous variable: each _ is a fresh Var, never reused.
        if identifier == "_":
            return replace(
                Call(
                    func=replace(Name(id="Var", ctx=load), name),
                    args=[],
                    keywords=[],
                ),
                name,
            )
        # Logic variable: trailing single underscore OR all-caps name.
        # Examples (underscore): X_, foo_, HEAD_ — all are logic variables.
        # Examples (all-caps):   X, FOO, HEAD, TAIL, N1, MAX_OF.
        # Excluded: __, x__, __init__ (dunder-style), MixedCase, lowercase.
        if _is_logic_var_name(identifier):
            # Lambda param or outer-lambda param: generate LoadName term node
            # so the compiler maps it to a function arg (no Var allocation).
            if identifier in getattr(transformer, '_load_names', ()):
                return node_ast(
                    "LoadName", name,
                    name=replace(Constant(value=identifier), name),
                )
            # First occurrence allocates a Var; subsequent ones reuse it.
            if identifier in transformer.seen_vars:
                return replace(Name(id=identifier, ctx=load), name)
            transformer.seen_vars.add(identifier)
            return replace(
                NamedExpr(
                    target=replace(Name(id=identifier, ctx=store), name),
                    value=replace(
                        Call(
                            func=replace(Name(id="Var", ctx=load), name),
                            args=[],
                            keywords=[],
                        ),
                        name,
                    ),
                ),
                name,
            )
        # Atom: declared in -module(...) export list — keep as plain Name reference.
        if identifier in transformer.atoms:
            return replace(Name(id=identifier, ctx=load), name)
        # Imported predicate: remap to full dotted path so Python code in the
        # .clausal file cannot accidentally clobber the predicate reference.
        dotted = transformer._import_remap.get(identifier)
        if dotted is not None:
            return node_ast(
                "LoadName", name, name=replace(Constant(value=dotted), name)
            )
        return node_ast(
            "LoadName", name, name=replace(Constant(value=identifier), name)
        )

    def visit_Attribute(transformer, attr_node):
        """Compile ``mod.Pred`` qualified calls to ``LoadAttr`` simple_ast nodes.

        Only supports dotted chains of non-variable names (e.g. ``utils.Helper``).
        Raises ``SyntaxError`` if any part of the chain is a logic variable or
        the expression isn't a simple dotted name.
        """
        # Collect the full dotted chain and validate each part.
        parts = []
        node = attr_node
        while isinstance(node, Attribute):
            if _is_logic_var_name(node.attr):
                raise SyntaxError(
                    f"Logic variable '{node.attr}' cannot appear in a "
                    f"qualified name (line {attr_node.lineno})"
                )
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, Name):
            raise SyntaxError(
                f"Unsupported attribute expression in predicate body "
                f"(line {attr_node.lineno}): only dotted names like "
                f"mod.Pred are supported"
            )
        if _is_logic_var_name(node.id):
            raise SyntaxError(
                f"Logic variable '{node.id}' cannot appear as the base "
                f"of a qualified name (line {attr_node.lineno})"
            )
        return node_ast(
            "LoadAttr",
            attr_node,
            object=transformer.visit(attr_node.value),
            attr=replace(Constant(value=attr_node.attr), attr_node),
        )

    def visit_NamedExpr(transformer, named_expr):
        # ':=' maps to Evaluate (arithmetic evaluate-and-bind) — Prolog-style 'is'.
        # Python's walrus operator requires a Name on the left, which is exactly
        # the common case: N := N1 + 1  →  Evaluate(N, Add(N1, 1)).
        return node_ast(
            "Evaluate",
            named_expr,
            left=transformer.visit(named_expr.target),
            right=transformer.visit(named_expr.value),
        )

    def visit_JoinedStr(transformer, node):
        """Defer f-string evaluation to search time via a lambda wrapper.

        Wraps the f-string in a lambda whose parameters are the logic variables
        referenced inside ``{...}`` slots.  The f-string stays as native Python
        code, so any Python expression (method calls, builtins, arithmetic)
        works inside interpolation slots.

        The result is ``FStringThunk(lambda V1, V2: f"...", [V1_var, V2_var])``
        where each ``Vi_var`` is the Var object from the enclosing clause scope.
        The compiler maps these Vars through ``var_context`` and emits
        ``thunk.fn(deref(_v0), deref(_v1), ...)``.
        """
        # Collect logic variable names from f-string interpolation values only.
        var_names = []
        seen: set[str] = set()
        for v in node.values:
            if isinstance(v, FormattedValue):
                for name in _collect_logic_var_names(v.value):
                    if name not in seen:
                        seen.add(name)
                        var_names.append(name)

        return _build_py_thunk_ast(
            transformer, node, node, var_names, thunk_cls="FStringThunk",
        )

    def visit_Set(transformer, set_expr):
        elements = [transformer.visit(element) for element in set_expr.elts]
        return node_ast(
            "SetLiteral",
            set_expr,
            elements=list_ast(elements, set_expr)
        )

    def visit_SetComp(transformer, set_comprehension):
        clauses = [
            transformer._visit_comprehension(clause)
            for clause in set_comprehension.generators
        ]
        return node_ast(
            "SetComp",
            set_comprehension,
            element=transformer.visit(set_comprehension.elt),
            clauses=list_ast(clauses, set_comprehension),
        )

    def visit_Starred(transformer, starred):
        return node_ast(
            "StarUnpack",
            starred,
            value=transformer.visit(starred.value)
        )

    def visit_Subscript(transformer, subscript):
        return node_ast(
            "LoadSubscript",
            subscript,
            object=transformer.visit(subscript.value),
            index=transformer.visit(subscript.slice),
        )

    def visit_Tuple(transformer, tuple_expr):
        assert type(tuple_expr.ctx) == Load
        elements = [transformer.visit(element) for element in tuple_expr.elts]
        return node_ast(
            "TupleLiteral",
            tuple_expr,
            elements=list_ast(elements, tuple_expr)
        )

    def visit_UnaryOp(transformer, unary_op):
        # ++expr — Python escape: evaluate expr as Python at search time.
        if (
            isinstance(unary_op.op, UAdd)
            and isinstance(unary_op.operand, UnaryOp)
            and isinstance(unary_op.operand.op, UAdd)
            # Adjacent columns — no space between the two '+' signs.
            and unary_op.col_offset == unary_op.operand.col_offset - 1
            and unary_op.lineno == unary_op.operand.lineno
        ):
            expression = unary_op.operand.operand
            var_names = _collect_logic_var_names(expression)
            return _build_py_thunk_ast(transformer, unary_op, expression, var_names)

        # Fold negative numeric literals: -3 → Constant(-3), not Negate(3).
        if (
            isinstance(unary_op.op, USub)
            and isinstance(unary_op.operand, Constant)
            and isinstance(unary_op.operand.value, (int, float))
        ):
            return replace(Constant(value=-unary_op.operand.value), unary_op)
        class_name = UNARYOP_CLS[type(unary_op.op)]
        return node_ast(
            class_name,
            unary_op,
            operand=transformer.visit(unary_op.operand)
        )

    def visit_Yield(transformer, yield_expr):
        if yield_expr.value is not None:
            return node_ast(
                "Yield",
                yield_expr,
                value=transformer.visit(yield_expr.value)
            )
        return node_ast("Yield", yield_expr)

    def visit_YieldFrom(transformer, yield_from_expr):
        return node_ast(
            "YieldFrom",
            yield_from_expr,
            value=transformer.visit(yield_from_expr.value)
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _visit_comprehension(transformer, generator_clause):
        """Convert an ast.comprehension into Python AST constructing a ForClause node."""
        # Use the iterable as the source-position anchor.
        source = generator_clause.iter
        filter_nodes = [
            transformer.visit(filter_node) for filter_node in generator_clause.ifs
        ]
        return node_ast(
            "ForClause",
            source,
            target=transformer.visit(generator_clause.target),
            iterable=transformer.visit(generator_clause.iter),
            filters=list_ast(filter_nodes, source),
            is_async=replace(
                Constant(value=bool(generator_clause.is_async)),
                source
            ),
        )

    def _visit_arguments(transformer, parameter_spec, body_transformer):
        """Convert ast.arguments into Python AST that constructs a Params node."""
        param_nodes = []

        for argument in parameter_spec.posonlyargs:
            name_node = replace(Constant(value=argument.arg), argument)
            keywords = [make_keyword_node("name", name_node, argument)]
            if argument.annotation:
                annotation = body_transformer.visit(argument.annotation)
                keywords.append(make_keyword_node("annotation", annotation, argument))
            param_nodes.append(
                replace(
                    Call(
                        func=load_name_ast("PosOnlyParam", argument),
                        args=[],
                        keywords=keywords,
                    ),
                    argument,
                )
            )

        for argument in parameter_spec.args:
            name_node = replace(Constant(value=argument.arg), argument)
            keywords = [make_keyword_node("name", name_node, argument)]
            if argument.annotation:
                annotation = body_transformer.visit(argument.annotation)
                keywords.append(make_keyword_node("annotation", annotation, argument))
            param_nodes.append(
                replace(
                    Call(
                        func=load_name_ast("PosOrKwParam", argument),
                        args=[],
                        keywords=keywords,
                    ),
                    argument,
                )
            )

        # defaults right-align over posonlyargs + args combined
        all_positional_args = parameter_spec.posonlyargs + parameter_spec.args
        default_count = len(parameter_spec.defaults)
        if default_count:
            offset = len(all_positional_args) - default_count
            for index, default_node in enumerate(parameter_spec.defaults):
                argument = all_positional_args[offset + index]
                param_class = (
                    "PosOrKwParam"
                    if argument in parameter_spec.args
                    else "PosOnlyParam"
                )
                default = body_transformer.visit(default_node)
                updated_keywords = param_nodes[offset + index].keywords + [
                    make_keyword_node("default", default, argument)
                ]
                param_nodes[offset + index] = replace(
                    Call(
                        func=load_name_ast(param_class, argument),
                        args=[],
                        keywords=updated_keywords,
                    ),
                    argument,
                )

        if parameter_spec.vararg:
            argument = parameter_spec.vararg
            name_node = replace(Constant(value=argument.arg), argument)
            keywords = [make_keyword_node("name", name_node, argument)]
            if argument.annotation:
                annotation = body_transformer.visit(argument.annotation)
                keywords.append(make_keyword_node("annotation", annotation, argument))
            param_nodes.append(
                replace(
                    Call(
                        func=load_name_ast("VarPositional", argument),
                        args=[],
                        keywords=keywords,
                    ),
                    argument,
                )
            )

        for index, argument in enumerate(parameter_spec.kwonlyargs):
            name_node = replace(Constant(value=argument.arg), argument)
            keywords = [make_keyword_node("name", name_node, argument)]
            if argument.annotation:
                annotation = body_transformer.visit(argument.annotation)
                keywords.append(make_keyword_node("annotation", annotation, argument))
            if (
                index < len(parameter_spec.kw_defaults)
                and parameter_spec.kw_defaults[index] is not None
            ):
                kw_default = parameter_spec.kw_defaults[index]
                default = body_transformer.visit(kw_default)
                keywords.append(make_keyword_node("default", default, argument))
            param_nodes.append(
                replace(
                    Call(
                        func=load_name_ast("KwOnlyParam", argument),
                        args=[],
                        keywords=keywords,
                    ),
                    argument,
                )
            )

        if parameter_spec.kwarg:
            argument = parameter_spec.kwarg
            name_node = replace(Constant(value=argument.arg), argument)
            keywords = [make_keyword_node("name", name_node, argument)]
            if argument.annotation:
                annotation = body_transformer.visit(argument.annotation)
                keywords.append(make_keyword_node("annotation", annotation, argument))
            param_nodes.append(
                replace(
                    Call(
                        func=load_name_ast("VarKeyword", argument),
                        args=[],
                        keywords=keywords,
                    ),
                    argument,
                )
            )

        # Pick a representative source position for the Params wrapper
        position_anchor = (
            parameter_spec.posonlyargs
            or parameter_spec.args
            or ([parameter_spec.vararg] if parameter_spec.vararg else [])
            or parameter_spec.kwonlyargs
            or ([parameter_spec.kwarg] if parameter_spec.kwarg else [])
        )
        if position_anchor:
            source = position_anchor[0]
            params_list = list_ast(param_nodes, source)
            return replace(
                Call(
                    func=load_name_ast("Params", source),
                    args=[],
                    keywords=[make_keyword_node("params", params_list, source)],
                ),
                source,
            )
        # No parameters at all
        return load_name_ast("Params", parameter_spec)


# ─── Functor class generator ──────────────────────────────────────────────────


def _dotted_name_from_ast(node):
    """Extract a dotted module path from nested ``ast.Attribute`` or ``ast.Name`` nodes.

    ``myapp.graphs.utils`` is parsed as::

        Attribute(value=Attribute(value=Name("myapp"), attr="graphs"), attr="utils")

    Returns a dotted string like ``"myapp.graphs.utils"``, or ``None`` if the
    node is not a valid dotted-name chain.
    """
    if isinstance(node, Name):
        return node.id
    if isinstance(node, Attribute) and isinstance(node.attr, str):
        prefix = _dotted_name_from_ast(node.value)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


# Map bare import names to ``clausal.modules.<file_basename>`` for the
# generated ``from … import …`` AST node.  Only names listed here are
# rewritten; other bare names are left for the import hook / meta-path
# finders to resolve.  An alias is needed when the Clausal module name
# would shadow a Python stdlib module (e.g. ``uuid`` ships as
# ``clausal/modules/uuid_mod.py`` shim re-exporting from ``py/uuid.py``).
_IMPORT_ALIASES: dict[str, str] = {
    "uuid": "uuid_mod",
}


def _resolve_import_path(module_path: str) -> str:
    """Rewrite aliased import paths to avoid stdlib collisions.

    Only names in ``_IMPORT_ALIASES`` are rewritten to their qualified
    ``clausal.modules.*`` form.  All other paths are returned unchanged.
    """
    mapped = _IMPORT_ALIASES.get(module_path)
    if mapped is not None:
        return f"clausal.modules.{mapped}"
    return module_path


def _parse_pred_arity_args(args, directive_name):
    """Parse ``pred/arity, ...`` arguments from a directive AST.

    Accepts two forms:
    - ``-dir(foo/2, bar/3)``        — positional pred/arity arguments
    - ``-dir([foo/2, bar/3])``      — a single list of pred/arity specs

    Each spec should be a ``BinOp(Name("pred"), Div(), Constant(arity))``
    node.  Returns a list of ``(functor_name, arity)`` tuples.
    Raises SyntaxError on malformed arguments.
    """
    # Unwrap single-list form: -dir([foo/2, bar/3]) → args = [foo/2, bar/3]
    if len(args) == 1 and isinstance(args[0], List):
        args = args[0].elts
    specs = []
    for arg in args:
        if (
            isinstance(arg, BinOp)
            and isinstance(arg.op, Div)
            and isinstance(arg.left, Name)
            and isinstance(arg.right, Constant)
            and isinstance(arg.right.value, int)
        ):
            specs.append((arg.left.id, arg.right.value))
        else:
            raise SyntaxError(
                f"Malformed argument in -{directive_name}(...): "
                f"expected pred/arity (e.g. foo/2), got {dump(arg)}"
            )
    if not specs:
        raise SyntaxError(
            f"-{directive_name}(...) requires at least one pred/arity argument"
        )
    return specs


def _make_functor_class_ast(functor_name, field_names, source):
    """Generate a try/except NameError block that defines a Predicate class.

    Generated code (example for ``fib`` with fields ``n``, ``f``):

        try:
            fib
        except NameError:
            class fib(metaclass=PredicateMeta):
                _fields = ('n', 'f')

    ``PredicateMeta`` handles ``__init__``, ``__eq__``, ``__repr__``,
    ``__match_args__``, ``__slots__``, and partial-term creation (missing
    fields → fresh ``Var()``).  No ``@dataclass`` and no singleton.
    ``fib`` stays as the class in module globals.
    """
    fields_tuple = repr(tuple(field_names))
    lines = [
        "try:",
        f"    {functor_name}",
        "except NameError:",
        f"    class {functor_name}(metaclass=PredicateMeta):",
        f"        _fields = {fields_tuple}",
    ]
    tree = parse("\n".join(lines))
    return copy_location(tree.body[0], source)


# ─── Python AST expression builder ───────────────────────────────────────────


def _py_ast_expr(node, anchor):
    """Build Python AST code that constructs `node` as an `ast.XXX` node at runtime.

    Returns an expression AST node (no statements, purely nested calls) that,
    when evaluated in a namespace where `ast` is the standard library module,
    produces the standard Python AST equivalent of `node`.
    """

    def build_value(value):
        if value is None:
            return replace(Constant(value=None), anchor)
        if isinstance(value, (bool, int, float, complex, str, bytes)):
            return replace(Constant(value=value), anchor)
        if isinstance(value, list):
            return replace(List(
                elts=[build_node(item) if isinstance(item, AST)
                      else replace(Constant(value=item), anchor)
                      for item in value],
                ctx=load,
            ), anchor)
        if isinstance(value, AST):
            return build_node(value)
        return replace(Constant(value=repr(value)), anchor)

    def build_node(n):
        kws = [
            replace(keyword(arg=field, value=build_value(val)), anchor)
            for field, val in iter_fields(n)
        ]
        # Propagate source positions from the parsed node into the constructor call,
        # so the runtime ast.XXX nodes carry the original file positions.
        for attr in n._attributes:
            if hasattr(n, attr):
                kws.append(replace(
                    keyword(arg=attr, value=replace(Constant(value=getattr(n, attr)), anchor)),
                    anchor,
                ))
        # '$ast' uses '$' so user code cannot accidentally shadow the stdlib ast module.
        return replace(Call(
            func=replace(Attribute(
                value=replace(Name(id='$ast', ctx=load), anchor),
                attr=type(n).__name__,
                ctx=load,
            ), anchor),
            args=[],
            keywords=kws,
        ), anchor)

    return build_node(node)



def _derive_field_names(pos_args: list) -> list[str]:
    """Derive unique field names from positional args in a clause head.

    Logic-variable Name nodes (trailing-underscore or ALL-CAPS) use their
    lowercased id as the field name.  Other args get ``arg_<i>``.  Duplicate
    names are disambiguated with a numeric suffix (e.g. ``b``, ``b_1``) so
    that repeated logic variables produce distinct dataclass fields.
    """
    names: list[str] = []
    counts: dict[str, int] = {}
    for i, arg in enumerate(pos_args):
        if isinstance(arg, Name) and _is_logic_var_name(arg.id):
            base = arg.id.rstrip("_").lower() or f"arg_{i}"
        else:
            base = f"arg_{i}"
        n = counts.get(base, 0)
        counts[base] = n + 1
        names.append(base if n == 0 else f"{base}_{n}")
    return names


# ─── DCG (Definite Clause Grammar) rewriting ─────────────────────────────────


def _collect_call_func_names(node):
    """Collect all function-call target names from a Python AST tree."""
    names = set()
    for child in walk(node):
        if isinstance(child, Call) and isinstance(child.func, Name):
            names.add(child.func.id)
    return names


def _is_dcg_passthrough(node):
    """Return True if this DCG body element does not consume input state.

    Passthrough elements: inline goals ``{goal}`` (Set nodes), empty terminals
    ``[]``, and negation-as-failure ``not X`` (tests but does not advance).
    """
    if isinstance(node, Set):
        return True
    if isinstance(node, List) and len(node.elts) == 0:
        return True
    if isinstance(node, UnaryOp) and isinstance(node.op, Not):
        return True
    return False


def _rewrite_dcg_body(node, s_in, s_out, counter, source):
    """Rewrite a single DCG body element into ordinary clause body AST.

    Returns ``(rewritten_ast, new_counter)`` where *counter* tracks the next
    available ``_dcg{N}_`` intermediate variable index.
    """
    match node:
        case List(elts=[]):
            # Empty terminal (epsilon): s_in = s_out.
            cmp = Compare(
                left=Name(id=s_in, ctx=load),
                ops=[Is()],
                comparators=[Name(id=s_out, ctx=load)],
            )
            return replace(cmp, source), counter

        case List(elts=elements):
            # Terminal [t1, ..., tn]: s_in is [t1, ..., tn, *s_out]
            starred = replace(
                Starred(value=Name(id=s_out, ctx=load), ctx=load), source
            )
            new_list = replace(
                List(elts=list(elements) + [starred], ctx=load), source
            )
            cmp = Compare(
                left=Name(id=s_in, ctx=load),
                ops=[Is()],
                comparators=[new_list],
            )
            return replace(cmp, source), counter

        case Set(elts=[goal]):
            # Inline goal {goal}: no state consumed.
            return goal, counter

        case Name(id=name):
            # Non-terminal, 0 extra args: name(s_in, s_out)
            call = Call(
                func=Name(id=name, ctx=load),
                args=[Name(id=s_in, ctx=load), Name(id=s_out, ctx=load)],
                keywords=[],
            )
            return replace(call, source), counter

        case Call(func=Name(id=name), args=args, keywords=kwargs) if (
            name == "If" and len(args) == 3
        ):
            # If-then-else: If(cond, then, else)
            cond, then_, else_ = args
            mid = f"_dcg{counter}_"
            counter += 1
            cond_r, counter = _rewrite_dcg_body(cond, s_in, mid, counter, source)
            then_r, counter = _rewrite_dcg_body(then_, mid, s_out, counter, source)
            else_r, counter = _rewrite_dcg_body(else_, s_in, s_out, counter, source)
            result = Call(
                func=Name(id="If", ctx=load),
                args=[cond_r, then_r, else_r],
                keywords=[],
            )
            return replace(result, source), counter

        case Call(func=func_node, args=args, keywords=kwargs):
            # Non-terminal with args: name(args..., s_in, s_out)
            new_args = list(args) + [
                Name(id=s_in, ctx=load), Name(id=s_out, ctx=load),
            ]
            call = Call(func=func_node, args=new_args, keywords=list(kwargs))
            return replace(call, source), counter

        case Tuple(elts=elements):
            return _rewrite_dcg_sequence(elements, s_in, s_out, counter, source)

        case BoolOp(op=And(), values=elements):
            return _rewrite_dcg_sequence(elements, s_in, s_out, counter, source)

        case BoolOp(op=Or(), values=elements):
            # Disjunction: each branch gets s_in → s_out.
            rewritten = []
            max_counter = counter
            for elem in elements:
                r, c = _rewrite_dcg_body(elem, s_in, s_out, counter, source)
                rewritten.append(r)
                if c > max_counter:
                    max_counter = c
            result = BoolOp(op=Or(), values=rewritten)
            return replace(result, source), max_counter

        case UnaryOp(op=Not(), operand=inner):
            # NAF: not rewrite(inner, s_in, _fresh). State passes through.
            fresh = f"_dcg{counter}_"
            counter += 1
            inner_r, counter = _rewrite_dcg_body(inner, s_in, fresh, counter, source)
            result = UnaryOp(op=Not(), operand=inner_r)
            return replace(result, source), counter

    raise SyntaxError(f"Unsupported DCG body element: {dump(node)}")


def _rewrite_dcg_sequence(elements, s_in, s_out, counter, source):
    """Rewrite a conjunction of DCG body elements, threading state variables.

    Implements inline-goal optimisation: elements that don't consume state
    (``{goal}``, empty ``[]``, ``not X``) don't generate intermediate state
    variables.  The last state-consuming element gets *s_out* directly.
    """
    # Find the last state-consuming element.
    last_consumer = -1
    for i in range(len(elements) - 1, -1, -1):
        if not _is_dcg_passthrough(elements[i]):
            last_consumer = i
            break

    if last_consumer == -1:
        # All passthrough — emit inline goals + s_in = s_out.
        parts = []
        for elem in elements:
            if isinstance(elem, Set):
                parts.append(elem.elts[0])
            elif isinstance(elem, UnaryOp) and isinstance(elem.op, Not):
                fresh = f"_dcg{counter}_"
                counter += 1
                inner_r, counter = _rewrite_dcg_body(
                    elem.operand, s_in, fresh, counter, source
                )
                parts.append(replace(UnaryOp(op=Not(), operand=inner_r), source))
        eq = Compare(
            left=Name(id=s_in, ctx=load),
            ops=[Is()],
            comparators=[Name(id=s_out, ctx=load)],
        )
        parts.append(replace(eq, source))
        if len(parts) == 1:
            return parts[0], counter
        result = BoolOp(op=And(), values=parts)
        return replace(result, source), counter

    # Thread state through elements.
    current_state = s_in
    rewritten_parts = []

    for i, elem in enumerate(elements):
        if isinstance(elem, Set):
            rewritten_parts.append(elem.elts[0])
        elif isinstance(elem, List) and len(elem.elts) == 0:
            pass  # empty terminal — nothing to emit
        elif isinstance(elem, UnaryOp) and isinstance(elem.op, Not):
            fresh = f"_dcg{counter}_"
            counter += 1
            inner_r, counter = _rewrite_dcg_body(
                elem.operand, current_state, fresh, counter, source
            )
            rewritten_parts.append(
                replace(UnaryOp(op=Not(), operand=inner_r), source)
            )
        else:
            # State-consuming element.
            if i == last_consumer:
                next_state = s_out
            else:
                next_state = f"_dcg{counter}_"
                counter += 1
            r, counter = _rewrite_dcg_body(
                elem, current_state, next_state, counter, source
            )
            rewritten_parts.append(r)
            current_state = next_state

    if len(rewritten_parts) == 1:
        return rewritten_parts[0], counter
    result = BoolOp(op=And(), values=rewritten_parts)
    return replace(result, source), counter


# ─── EDCG Rewriting ──────────────────────────────────────────────────────────


def _edcg_acc_vars(acc_name, suffix=""):
    """Return (in_var, out_var) names for an EDCG accumulator."""
    return f"_edcg_{acc_name}_in{suffix}_", f"_edcg_{acc_name}_out{suffix}_"


def _edcg_pass_var(pass_name):
    """Return the variable name for an EDCG passed argument."""
    return f"_edcg_{pass_name}_"


def _is_edcg_push(node):
    """Check if node is ``[value] // acc_name``.

    Returns ``(value_node, acc_name)`` or None.
    Python ``//`` is FloorDiv.
    """
    if not isinstance(node, BinOp) or not isinstance(node.op, FloorDiv):
        return None
    if not isinstance(node.right, Name):
        return None
    if not isinstance(node.left, List) or len(node.left.elts) != 1:
        return None
    return node.left.elts[0], node.right.id


def _is_edcg_read(node):
    """Check if node is ``acc_name / Var_``.

    Returns ``(acc_name, var_node)`` or None.
    Python ``/`` is Div.
    """
    if not isinstance(node, BinOp) or not isinstance(node.op, Div):
        return None
    if not isinstance(node.left, Name):
        return None
    return node.left.id, node.right


def _make_joiner_call(acc_info, val_ast, in_var, out_var, source):
    """Instantiate a joiner goal AST with concrete variable names.

    The joiner_ast from -edcg_acc uses placeholder variable names (Val_, In_, Out_).
    We substitute them with the actual variable names for this position in the chain.
    """
    import copy
    joiner = copy.deepcopy(acc_info["joiner_ast"])

    class _SubstVars(NodeTransformer):
        def visit_Name(self, node):
            if node.id == acc_info["val"]:
                return replace(val_ast, node)
            if node.id == acc_info["in_"]:
                return replace(Name(id=in_var, ctx=load), node)
            if node.id == acc_info["out"]:
                return replace(Name(id=out_var, ctx=load), node)
            return node

    result = _SubstVars().visit(joiner)
    return replace(result, source)


def _rewrite_edcg_body(node, acc_states, pass_states, edcg_accs, edcg_passes,
                        edcg_preds, counter, source):
    """Rewrite an EDCG body element into ordinary clause body AST.

    Parameters:
        node: the body AST node
        acc_states: dict mapping acc_name → (current_in_var, current_out_var)
        pass_states: dict mapping pass_name → var_name
        edcg_accs: the transformer's _edcg_accs dict
        edcg_passes: the transformer's _edcg_passes set
        edcg_preds: the transformer's _edcg_preds dict
        counter: int, next available intermediate variable index
        source: AST node for source position copying

    Returns (rewritten_ast, new_acc_states, new_counter).
    acc_states is updated: after a push, the "in" of the accumulator advances.
    """
    push = _is_edcg_push(node)
    if push is not None:
        val_node, acc_name = push
        if acc_name not in acc_states:
            raise SyntaxError(
                f"EDCG: accumulator '{acc_name}' not available in this rule "
                f"(available: {list(acc_states.keys())})"
            )
        in_var, out_var = acc_states[acc_name]
        # Create an intermediate variable for the new state.
        mid = f"_edcg_{acc_name}_{counter}_"
        counter += 1
        if acc_name == "dcg":
            # DCG accumulator: [V | Rest] pattern
            starred = replace(
                Starred(value=Name(id=mid, ctx=load), ctx=load), source
            )
            new_list = replace(
                List(elts=[val_node, starred], ctx=load), source
            )
            goal = Compare(
                left=Name(id=in_var, ctx=load),
                ops=[Is()],
                comparators=[new_list],
            )
        else:
            acc_info = edcg_accs[acc_name]
            goal = _make_joiner_call(acc_info, val_node, in_var, mid, source)
        new_acc_states = dict(acc_states)
        new_acc_states[acc_name] = (mid, out_var)
        return replace(goal, source), new_acc_states, counter

    read = _is_edcg_read(node)
    if read is not None:
        acc_or_pass_name, var_node = read
        if acc_or_pass_name in acc_states:
            # Read current accumulator value (the "in" variable).
            in_var, _ = acc_states[acc_or_pass_name]
            goal = Compare(
                left=var_node,
                ops=[Is()],
                comparators=[Name(id=in_var, ctx=load)],
            )
            return replace(goal, source), acc_states, counter
        elif acc_or_pass_name in pass_states:
            # Read passed argument value.
            pass_var = pass_states[acc_or_pass_name]
            goal = Compare(
                left=var_node,
                ops=[Is()],
                comparators=[Name(id=pass_var, ctx=load)],
            )
            return replace(goal, source), acc_states, counter
        else:
            raise SyntaxError(
                f"EDCG: '{acc_or_pass_name}' is not an available accumulator or pass "
                f"(accumulators: {list(acc_states.keys())}, passes: {list(pass_states.keys())})"
            )

    match node:
        case List(elts=[]):
            # Empty list [] in EDCG: no-op for all accumulators.
            # Each accumulator's in = out.
            parts = []
            for acc_name, (in_var, out_var) in acc_states.items():
                if in_var != out_var:
                    eq = Compare(
                        left=Name(id=in_var, ctx=load),
                        ops=[Is()],
                        comparators=[Name(id=out_var, ctx=load)],
                    )
                    parts.append(replace(eq, source))
            if not parts:
                # Degenerate: return True-like.
                parts.append(replace(Constant(value=True), source))
            new_acc_states = {k: (v[1], v[1]) for k, v in acc_states.items()}
            if len(parts) == 1:
                return parts[0], new_acc_states, counter
            return replace(BoolOp(op=And(), values=parts), source), new_acc_states, counter

        case List(elts=elements):
            # Terminal list [t1, t2, ...]: push to 'dcg' accumulator.
            if "dcg" not in acc_states:
                raise SyntaxError(
                    "EDCG: terminal list [..] requires 'dcg' accumulator but this "
                    "predicate doesn't use it"
                )
            in_var, out_var = acc_states["dcg"]
            mid = f"_edcg_dcg_{counter}_"
            counter += 1
            starred = replace(
                Starred(value=Name(id=mid, ctx=load), ctx=load), source
            )
            new_list = replace(
                List(elts=list(elements) + [starred], ctx=load), source
            )
            goal = Compare(
                left=Name(id=in_var, ctx=load),
                ops=[Is()],
                comparators=[new_list],
            )
            new_acc_states = dict(acc_states)
            new_acc_states["dcg"] = (mid, out_var)
            return replace(goal, source), new_acc_states, counter

        case Set(elts=[goal]):
            # Inline goal {goal}: no accumulator threading.
            return goal, acc_states, counter

        case Name(id=name) if name in edcg_preds:
            # EDCG non-terminal, 0 visible args.
            return _rewrite_edcg_subcall(
                name, [], [], acc_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )

        case Call(func=Name(id=name), args=args, keywords=kwargs) if name in edcg_preds:
            # EDCG non-terminal with args.
            return _rewrite_edcg_subcall(
                name, list(args), list(kwargs), acc_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )

        case Name(id=name):
            # Non-EDCG non-terminal with no args; treat like standard DCG
            # if 'dcg' is available.
            if "dcg" in acc_states:
                in_var, out_var = acc_states["dcg"]
                call_node = Call(
                    func=Name(id=name, ctx=load),
                    args=[Name(id=in_var, ctx=load), Name(id=out_var, ctx=load)],
                    keywords=[],
                )
                new_acc_states = dict(acc_states)
                new_acc_states["dcg"] = (out_var, out_var)
                return replace(call_node, source), new_acc_states, counter
            else:
                # 0-arity call.
                call_node = Call(
                    func=Name(id=name, ctx=load),
                    args=[],
                    keywords=[],
                )
                return replace(call_node, source), acc_states, counter

        case Call(func=Name(id=name), args=args, keywords=kwargs):
            # Non-EDCG call with args; if dcg available, add state args.
            if "dcg" in acc_states:
                in_var, out_var = acc_states["dcg"]
                new_args = list(args) + [
                    Name(id=in_var, ctx=load), Name(id=out_var, ctx=load),
                ]
                call_node = Call(func=Name(id=name, ctx=load),
                                args=new_args, keywords=list(kwargs))
                new_acc_states = dict(acc_states)
                new_acc_states["dcg"] = (out_var, out_var)
                return replace(call_node, source), new_acc_states, counter
            else:
                call_node = Call(func=Name(id=name, ctx=load),
                                args=list(args), keywords=list(kwargs))
                return replace(call_node, source), acc_states, counter

        case Tuple(elts=elements):
            return _rewrite_edcg_sequence(
                elements, acc_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )

        case BoolOp(op=And(), values=elements):
            return _rewrite_edcg_sequence(
                elements, acc_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )

        case BoolOp(op=Or(), values=elements):
            # Disjunction: each branch gets the same starting acc_states,
            # all branches must independently close to out_var.
            rewritten = []
            max_counter = counter
            for elem in elements:
                branch_states = dict(acc_states)
                r, branch_final, c = _rewrite_edcg_body(
                    elem, branch_states, dict(pass_states),
                    edcg_accs, edcg_passes, edcg_preds, counter, source
                )
                # Close any open accumulator chains in this branch.
                closers = []
                for acc_name, (orig_in, orig_out) in acc_states.items():
                    final_in, _ = branch_final.get(acc_name, (orig_in, orig_out))
                    if final_in != orig_out:
                        eq = Compare(
                            left=Name(id=final_in, ctx=load),
                            ops=[Is()],
                            comparators=[Name(id=orig_out, ctx=load)],
                        )
                        closers.append(replace(eq, source))
                if closers:
                    r = replace(BoolOp(op=And(), values=[r] + closers), source)
                rewritten.append(r)
                if c > max_counter:
                    max_counter = c
            result = BoolOp(op=Or(), values=rewritten)
            # After disjunction, all accumulators are at their out_var.
            closed_states = {k: (v[1], v[1]) for k, v in acc_states.items()}
            return replace(result, source), closed_states, max_counter

        case UnaryOp(op=Not(), operand=inner):
            # NAF: doesn't affect accumulator state.
            # Create fresh out vars for the inner goal.
            inner_acc_states = {}
            for acc_name, (in_var, out_var) in acc_states.items():
                fresh = f"_edcg_{acc_name}_{counter}_"
                counter += 1
                inner_acc_states[acc_name] = (in_var, fresh)
            inner_r, _, counter = _rewrite_edcg_body(
                inner, inner_acc_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
            result = UnaryOp(op=Not(), operand=inner_r)
            return replace(result, source), acc_states, counter

        case Call(func=Name(id="If"), args=[cond, then_, else_], keywords=_):
            # If-then-else.
            mid_states = {}
            for acc_name, (in_var, out_var) in acc_states.items():
                mid = f"_edcg_{acc_name}_{counter}_"
                counter += 1
                mid_states[acc_name] = (in_var, mid)
            cond_r, cond_out_states, counter = _rewrite_edcg_body(
                cond, mid_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
            # Then branch starts from where cond left off.
            then_states = {}
            for acc_name in acc_states:
                cin, _ = cond_out_states[acc_name]
                _, out_var = acc_states[acc_name]
                then_states[acc_name] = (cin, out_var)
            then_r, _, counter = _rewrite_edcg_body(
                then_, then_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
            # Else branch starts from original in.
            else_states = dict(acc_states)
            else_r, _, counter = _rewrite_edcg_body(
                else_, else_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
            result = Call(
                func=Name(id="If", ctx=load),
                args=[cond_r, then_r, else_r],
                keywords=[],
            )
            return replace(result, source), acc_states, counter

    raise SyntaxError(f"Unsupported EDCG body element: {dump(node)}")


def _rewrite_edcg_subcall(callee_name, args, kwargs, acc_states, pass_states,
                           edcg_accs, edcg_passes, edcg_preds, counter, source):
    """Rewrite a call to another EDCG predicate, threading shared accumulators."""
    callee_arity, callee_ap_names = edcg_preds[callee_name]

    # Build the full argument list: visible args + hidden acc/pass args.
    full_args = list(args)
    new_acc_states = dict(acc_states)

    for ap_name in callee_ap_names:
        if ap_name in edcg_accs or ap_name == "dcg":
            # Accumulator: thread in/out.
            if ap_name in acc_states:
                in_var, out_var = acc_states[ap_name]
                # Create intermediate variable for callee's output.
                mid = f"_edcg_{ap_name}_{counter}_"
                counter += 1
                full_args.append(Name(id=in_var, ctx=load))
                full_args.append(Name(id=mid, ctx=load))
                new_acc_states[ap_name] = (mid, out_var)
            else:
                # Caller doesn't use this accumulator — use fresh vars.
                fresh_in = f"_edcg_{ap_name}_{counter}_"
                counter += 1
                fresh_out = f"_edcg_{ap_name}_{counter}_"
                counter += 1
                full_args.append(Name(id=fresh_in, ctx=load))
                full_args.append(Name(id=fresh_out, ctx=load))
        elif ap_name in edcg_passes:
            # Pass: thread the value.
            if ap_name in pass_states:
                full_args.append(Name(id=pass_states[ap_name], ctx=load))
            else:
                # Caller doesn't have this pass — use fresh var.
                fresh = f"_edcg_{ap_name}_{counter}_"
                counter += 1
                full_args.append(Name(id=fresh, ctx=load))

    call_node = Call(
        func=Name(id=callee_name, ctx=load),
        args=full_args,
        keywords=list(kwargs),
    )
    return replace(call_node, source), new_acc_states, counter


def _is_edcg_passthrough(node, edcg_accs, edcg_passes):
    """Return True if this EDCG body element doesn't consume any accumulator state."""
    if isinstance(node, Set):
        return True
    if isinstance(node, UnaryOp) and isinstance(node.op, Not):
        return True
    return False


def _rewrite_edcg_sequence(elements, acc_states, pass_states,
                            edcg_accs, edcg_passes, edcg_preds, counter, source):
    """Rewrite a conjunction of EDCG body elements, threading accumulator state."""
    rewritten_parts = []

    # For the last element of each accumulator, we want it to reach the
    # final out_var. We process left-to-right, threading acc_states.
    # The final element for each accumulator should unify its output with
    # the accumulator's out_var.

    current_states = dict(acc_states)

    for i, elem in enumerate(elements):
        if isinstance(elem, Set):
            # Inline goal: no threading.
            rewritten_parts.append(elem.elts[0])
            continue

        is_last = (i == len(elements) - 1)

        if is_last:
            # Last element: its outputs should be the final out_vars.
            # Set up acc_states so each accumulator's out is the final out.
            final_states = {}
            for acc_name, (in_var, out_var) in current_states.items():
                final_out = acc_states[acc_name][1]  # original out_var
                final_states[acc_name] = (in_var, final_out)
            r, current_states, counter = _rewrite_edcg_body(
                elem, final_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
        else:
            r, current_states, counter = _rewrite_edcg_body(
                elem, current_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
        rewritten_parts.append(r)

    if not rewritten_parts:
        # Empty sequence: unify all in = out.
        parts = []
        for acc_name, (in_var, out_var) in acc_states.items():
            if in_var != out_var:
                eq = Compare(
                    left=Name(id=in_var, ctx=load),
                    ops=[Is()],
                    comparators=[Name(id=out_var, ctx=load)],
                )
                parts.append(replace(eq, source))
        if not parts:
            return replace(Constant(value=True), source), acc_states, counter
        if len(parts) == 1:
            return parts[0], acc_states, counter
        return replace(BoolOp(op=And(), values=parts), source), acc_states, counter

    if len(rewritten_parts) == 1:
        return rewritten_parts[0], current_states, counter
    result = BoolOp(op=And(), values=rewritten_parts)
    return replace(result, source), current_states, counter


# ─── Embed Transformer ────────────────────────────────────────────────────────


class EmbedTransformer(NodeTransformer):
    """Walk Python source and expand DSL escapes into simple_ast constructor calls.

    Recognised patterns:
      -dir(...)   Module-level directive (e.g. -module(name, [exports])).
      --expr      Nested adjacent USub: transforms expr via TermTransformer.
      ~~expr      Nested adjacent Invert: produces a standard Python ast.XXX node.
      head,       Trailing-comma tuple expression-statement: Prolog fact notation.
      head<-body  Module-level predicate definition (only at module scope).
      head>>(body) DCG rule: rewrites to head(_dcg0_,_dcg1_)<-(rewritten body).
      with --{} as target:
          <body>  Block form of --: transforms each expression-statement body
                  line via TermTransformer into a simple_ast node, assigns the
                  resulting list to target.
      with ~~{} as target:
          <body>  Block form of ~~: converts each body statement to a Python
                  ast.XXX node.  Expression statements yield the expression
                  node; other statements yield the statement node itself.
      _name       In outer Python code, rewrites to _name.value (unbox logic var).
    """

    def __init__(transformer):
        transformer._scope_depth = 0
        transformer._seen_functors: dict[str, list[str]] = {}
        transformer._atoms: set[str] = set()
        transformer._import_remap: dict[str, str] = {}
        transformer._module_items: list = []
        # EDCG declarations: populated by -edcg_acc, -edcg_pass, -edcg_pred directives.
        transformer._edcg_accs: dict[str, dict] = {}   # name → {val, in_, out, joiner_ast}
        transformer._edcg_passes: set[str] = set()      # set of pass names
        transformer._edcg_preds: dict[str, tuple[int, list[str]]] = {}  # pred → (visible_arity, [acc/pass names])

    def visit_FunctionDef(transformer, node):
        if is_template_func(node):
            return compile_template_func(node)
        transformer._scope_depth += 1
        result = transformer.generic_visit(node)
        transformer._scope_depth -= 1
        return result

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(transformer, node):
        transformer._scope_depth += 1
        result = transformer.generic_visit(node)
        transformer._scope_depth -= 1
        return result

    def visit_UnaryOp(transformer, unary_op):
        match unary_op:  # -- term_expression
            case UnaryOp(op=USub(), operand=UnaryOp(op=USub(), operand=expression)):
                # '--' must be written without a space (the two '-' are adjacent).
                if (
                    unary_op.col_offset == unary_op.operand.col_offset - 1
                    and unary_op.lineno == unary_op.operand.lineno
                ):
                    return TermTransformer(atoms=transformer._atoms, import_remap=transformer._import_remap).visit(expression)
            case UnaryOp(op=Invert(), operand=UnaryOp(op=Invert(), operand=expression)):
                # '~~' must be written without a space (the two '~' are adjacent).
                if (
                    unary_op.col_offset == unary_op.operand.col_offset - 1
                    and unary_op.lineno == unary_op.operand.lineno
                ):
                    inner = _py_ast_expr(expression, unary_op)
                    # Wrap with $ast.fix_missing_locations so runtime nodes have positions.
                    # '$ast' uses '$' so user code cannot accidentally shadow the stdlib ast module.
                    result = replace(Call(
                        func=replace(Attribute(
                            value=replace(Name(id='$ast', ctx=load), unary_op),
                            attr='fix_missing_locations',
                            ctx=load,
                        ), unary_op),
                        args=[inner],
                        keywords=[],
                    ), unary_op)
                    fix_missing_locations(result)
                    return result
        unary_op.operand = transformer.visit(unary_op.operand)
        return unary_op

    def visit_Expr(transformer, expr_stmt):
        """Detect trailing-comma tuple (Prolog fact) and module-level predicate definitions."""
        if transformer._scope_depth == 0:
            _check_hidden_arrow(expr_stmt.value)
        match expr_stmt.value:
            # -directive(...) at module level: unary minus applied to a call.
            # Currently only -module(name, [exports]) is recognised.
            case UnaryOp(
                op=USub(),
                operand=Call(func=Name(id=directive_name), args=directive_args),
            ) as neg if (
                transformer._scope_depth == 0
                # '-' must be adjacent to the call (no space).
                and neg.col_offset == neg.operand.col_offset - 1
                and neg.lineno == neg.operand.lineno
            ):
                return transformer._handle_directive(
                    directive_name, directive_args, expr_stmt
                )
            case Tuple(elts=[single_element], ctx=Load()) if (
                isinstance(single_element, Call)
                and isinstance(single_element.func, Name)
                and transformer._scope_depth == 0
            ):
                # Trailing-comma fact: ``edge(1, 2),`` — treated as a predicate
                # definition with body=True, generating a functor dataclass if
                # this is the first clause for this functor.
                functor_name = single_element.func.id
                orig_pos_args = single_element.args
                orig_kw_args = single_element.keywords

                arg_field_names = _derive_field_names(orig_pos_args)
                kwarg_field_names = [kw.arg for kw in orig_kw_args]
                all_field_names = arg_field_names + kwarg_field_names

                # If the functor was already seen, remap positional arg field
                # names to the established signature by position.
                prev_fields = transformer._seen_functors.get(functor_name)
                if prev_fields is not None:
                    for i in range(len(arg_field_names)):
                        if i < len(prev_fields):
                            arg_field_names[i] = prev_fields[i]
                    all_field_names = arg_field_names + kwarg_field_names

                term_transformer = TermTransformer(atoms=transformer._atoms, import_remap=transformer._import_remap)
                transformed_pos = [term_transformer.visit(a) for a in orig_pos_args]
                transformed_kw = [term_transformer.visit(kw.value) for kw in orig_kw_args]

                anchor = single_element.func
                head_keywords = [
                    make_keyword_node(fname, term, orig)
                    for fname, term, orig in zip(arg_field_names, transformed_pos, orig_pos_args)
                ] + [
                    make_keyword_node(fname, term, orig)
                    for fname, term, orig in zip(kwarg_field_names, transformed_kw, orig_kw_args)
                ]
                head_ast = replace(
                    Call(
                        func=replace(Name(id=functor_name, ctx=load), anchor),
                        args=[],
                        keywords=head_keywords,
                    ),
                    single_element,
                )

                predicate_ast = node_ast(
                    "Predicate", expr_stmt.value,
                    head=head_ast,
                    body=replace(Constant(value=True), expr_stmt.value),
                )
                define_stmt = replace(
                    Expr(
                        value=replace(
                            Call(
                                func=replace(
                                    Name(id="$define_predicate", ctx=load), expr_stmt.value
                                ),
                                args=[
                                    predicate_ast,
                                    replace(Name(id="$module", ctx=load), expr_stmt.value),
                                ],
                                keywords=[],
                            ),
                            expr_stmt.value,
                        )
                    ),
                    expr_stmt,
                )

                statements = []
                if functor_name not in transformer._seen_functors:
                    transformer._seen_functors[functor_name] = all_field_names
                    statements.append(
                        _make_functor_class_ast(functor_name, all_field_names, expr_stmt)
                    )
                statements.append(define_stmt)
                return statements if len(statements) > 1 else statements[0]
            case BinOp(left=lhs, op=RShift(), right=rhs) if (
                transformer._scope_depth == 0
            ):
                # DCG / EDCG rule: head >> (body)
                # Parse LHS for pushback: (head, [pushback]) >> (body)
                pushback = None
                if isinstance(lhs, Tuple) and len(lhs.elts) == 2:
                    head_part, pb_part = lhs.elts
                    if isinstance(pb_part, List):
                        pushback = pb_part.elts
                        lhs = head_part

                # Extract functor name and user args from the head.
                if isinstance(lhs, Call) and isinstance(lhs.func, Name):
                    functor_name = lhs.func.id
                    orig_pos_args = list(lhs.args)
                    orig_kw_args = list(lhs.keywords)
                elif isinstance(lhs, Name):
                    functor_name = lhs.id
                    orig_pos_args = []
                    orig_kw_args = []
                else:
                    return transformer.generic_visit(expr_stmt)

                src = expr_stmt.value

                # Check if this is an EDCG rule.
                if functor_name in transformer._edcg_preds:
                    return transformer._rewrite_edcg_rule(
                        functor_name, orig_pos_args, orig_kw_args,
                        rhs, pushback, lhs, src, expr_stmt
                    )

                # Standard DCG rule.
                # Add DCG state args (_dcg0_, _dcg1_) to the head.
                dcg_in = replace(Name(id="_dcg0_", ctx=load), src)
                dcg_out = replace(Name(id="_dcg1_", ctx=load), src)
                orig_pos_args.append(dcg_in)
                orig_pos_args.append(dcg_out)

                # Rewrite DCG body to ordinary clause body AST.
                if pushback is not None:
                    # (head, [pb...]) >> body → body s_out is _dcg_pb_,
                    # then _dcg1_ is [pb..., *_dcg_pb_]
                    body_raw, _ = _rewrite_dcg_body(
                        rhs, "_dcg0_", "_dcg_pb_", 2, src
                    )
                    pb_starred = replace(
                        Starred(value=Name(id="_dcg_pb_", ctx=load), ctx=load), src
                    )
                    pb_list = replace(
                        List(elts=list(pushback) + [pb_starred], ctx=load), src
                    )
                    pb_unify = replace(Compare(
                        left=Name(id="_dcg1_", ctx=load),
                        ops=[Is()],
                        comparators=[pb_list],
                    ), src)
                    body_expr_raw = replace(
                        BoolOp(op=And(), values=[body_raw, pb_unify]), src
                    )
                else:
                    body_expr_raw, _ = _rewrite_dcg_body(
                        rhs, "_dcg0_", "_dcg1_", 2, src
                    )

                # From here: same pipeline as <- rules.
                return transformer._finalize_dcg_rule(
                    functor_name, orig_pos_args, orig_kw_args,
                    body_expr_raw, lhs, src, expr_stmt
                )
            case Compare(
                left=left, ops=ops, comparators=comparators,
            ) if (
                transformer._scope_depth == 0
                and (arrow := _detect_arrow(left, ops, comparators)) is not None
            ):
                # Module-level predicate definition: functor_call<-body
                _, body_expr = arrow
                # Extract functor name and positional/keyword field names from the
                # original (pre-transformation) head Python AST.
                if isinstance(left, Call) and isinstance(left.func, Name):
                    functor_name = left.func.id
                    orig_pos_args = left.args
                    orig_kw_args = left.keywords
                elif isinstance(left, Name):
                    functor_name = left.id
                    orig_pos_args = []
                    orig_kw_args = []
                else:
                    return transformer.generic_visit(expr_stmt)

                arg_field_names = _derive_field_names(orig_pos_args)
                kwarg_field_names = [kw.arg for kw in orig_kw_args]
                all_field_names = arg_field_names + kwarg_field_names

                # If the functor was already seen, remap positional arg field
                # names to the established signature by position.
                prev_fields = transformer._seen_functors.get(functor_name)
                if prev_fields is not None:
                    for i in range(len(arg_field_names)):
                        if i < len(prev_fields):
                            arg_field_names[i] = prev_fields[i]
                    all_field_names = arg_field_names + kwarg_field_names

                # Transform terms. One shared transformer keeps variable bindings
                # (walrus operator) consistent across head and body.
                term_transformer = TermTransformer(atoms=transformer._atoms, import_remap=transformer._import_remap)
                transformed_pos = [term_transformer.visit(a) for a in orig_pos_args]
                transformed_kw = [term_transformer.visit(kw.value) for kw in orig_kw_args]
                body_ast = term_transformer.visit(body_expr)

                # Build head call: functor(field=term, ...) as a plain Python Call,
                # not a simple_ast.Call constructor.
                anchor = left.func if isinstance(left, Call) else left
                head_keywords = [
                    make_keyword_node(fname, term, orig)
                    for fname, term, orig in zip(arg_field_names, transformed_pos, orig_pos_args)
                ] + [
                    make_keyword_node(fname, term, orig)
                    for fname, term, orig in zip(kwarg_field_names, transformed_kw, orig_kw_args)
                ]
                head_ast = replace(
                    Call(
                        func=replace(Name(id=functor_name, ctx=load), anchor),
                        args=[],
                        keywords=head_keywords,
                    ),
                    left,
                )

                predicate_ast = node_ast(
                    "Predicate", expr_stmt.value, head=head_ast, body=body_ast
                )
                define_stmt = replace(
                    Expr(
                        value=replace(
                            Call(
                                func=replace(
                                    Name(id="$define_predicate", ctx=load), expr_stmt.value
                                ),
                                args=[
                                    predicate_ast,
                                    replace(Name(id="$module", ctx=load), expr_stmt.value),
                                ],
                                keywords=[],
                            ),
                            expr_stmt.value,
                        )
                    ),
                    expr_stmt,
                )

                statements = []
                if functor_name not in transformer._seen_functors:
                    transformer._seen_functors[functor_name] = all_field_names
                    statements.append(
                        _make_functor_class_ast(functor_name, all_field_names, expr_stmt)
                    )
                statements.append(define_stmt)
                return statements if len(statements) > 1 else statements[0]
        return transformer.generic_visit(expr_stmt)

    def _handle_directive(transformer, name, args, expr_stmt):
        """Dispatch a -directive(...) at module level."""
        if name == "module":
            return transformer._handle_module_directive(args, expr_stmt)
        if name == "private":
            return transformer._handle_private_directive(args, expr_stmt)
        if name == "dynamic":
            specs = _parse_pred_arity_args(args, "dynamic")
            transformer._module_items.append(DirectiveItem(name="dynamic", specs=specs))
            return transformer._handle_predspec_directive("mark_dynamic", args, expr_stmt)
        if name == "discontiguous":
            specs = _parse_pred_arity_args(args, "discontiguous")
            transformer._module_items.append(DirectiveItem(name="discontiguous", specs=specs))
            return transformer._handle_predspec_directive("mark_discontiguous", args, expr_stmt)
        if name == "table":
            specs = _parse_pred_arity_args(args, "table")
            transformer._module_items.append(DirectiveItem(name="table", specs=specs))
            return transformer._handle_predspec_directive("mark_tabled", args, expr_stmt)
        if name == "shallow":
            specs = _parse_pred_arity_args(args, "shallow")
            transformer._module_items.append(DirectiveItem(name="shallow", specs=specs))
            return transformer._handle_predspec_directive("mark_shallow", args, expr_stmt)
        if name == "import_from":
            return transformer._handle_import_from_directive(args, expr_stmt)
        if name == "import_module":
            return transformer._handle_import_module_directive(args, expr_stmt)
        if name == "edcg_acc":
            return transformer._handle_edcg_acc_directive(args, expr_stmt)
        if name == "edcg_pass":
            return transformer._handle_edcg_pass_directive(args, expr_stmt)
        if name == "edcg_pred":
            return transformer._handle_edcg_pred_directive(args, expr_stmt)
        raise SyntaxError(
            f"Unknown directive: -{name}(...)  "
            f"(known directives: -module, -private, -dynamic, -discontiguous, "
            f"-table, -shallow, -import_from, -import_module, "
            f"-edcg_acc, -edcg_pass, -edcg_pred)"
        )

    def _handle_module_directive(transformer, args, expr_stmt):
        """Process ``-module(Name, [export1(A,B), export2(X,Y)])`` directive.

        Extracts predicate signatures from the export list and emits
        ``_make_functor_class_ast`` definitions for each, pre-registering
        them in ``_seen_functors`` so that subsequent clauses use the
        declared field names rather than inferring them from the first clause.
        """
        statements = []
        module_name = ""
        exports_info = []  # for ModuleAST accumulation
        if len(args) >= 1 and isinstance(args[0], Name):
            module_name = args[0].id
        # args[1] should be the export list: ast.List of Call nodes.
        if len(args) >= 2 and isinstance(args[1], List):
            for export in args[1].elts:
                if isinstance(export, Name):
                    # Bare atom: generate ``name = "name"``
                    transformer._atoms.add(export.id)
                    exports_info.append(export.id)
                    statements.append(
                        replace(
                            Assign(
                                targets=[replace(Name(id=export.id, ctx=Store()), export)],
                                value=replace(Constant(value=export.id), export),
                            ),
                            expr_stmt,
                        )
                    )
                elif isinstance(export, Call) and isinstance(export.func, Name):
                    functor_name = export.func.id
                    # Use raw Name ids as field names (not lowercased) so they
                    # match keyword arg names in clauses like fib(N=0, F=0).
                    field_names = [
                        arg.id if isinstance(arg, Name) else f"arg_{i}"
                        for i, arg in enumerate(export.args)
                    ]
                    field_names += [kw.arg for kw in export.keywords]
                    exports_info.append((functor_name, field_names))
                    if functor_name not in transformer._seen_functors:
                        transformer._seen_functors[functor_name] = field_names
                        statements.append(
                            _make_functor_class_ast(
                                functor_name, field_names, expr_stmt
                            )
                        )
        transformer._module_items.append(
            ModuleDeclItem(module_name=module_name, exports=exports_info)
        )
        if not statements:
            return replace(Pass(), expr_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _handle_private_directive(transformer, args, expr_stmt):
        """Process ``-private([atom1, pred(A, B), ...])`` directive.

        Declares atoms and predicate signatures that are internal to the
        module.  Has the same compilation effect as ``-module`` exports
        (atom assignments, functor class generation, pre-registration in
        ``_seen_functors``) but communicates that these names are not part
        of the module's public API.
        """
        statements = []
        private_info = []  # for ModuleAST accumulation
        export_list = args[0] if len(args) >= 1 and isinstance(args[0], List) else None
        if export_list is None:
            transformer._module_items.append(PrivateDeclItem(items=[]))
            return replace(Pass(), expr_stmt)
        for item in export_list.elts:
            if isinstance(item, Name):
                # Bare atom: generate ``name = "name"``
                transformer._atoms.add(item.id)
                private_info.append(item.id)
                statements.append(
                    replace(
                        Assign(
                            targets=[replace(Name(id=item.id, ctx=Store()), item)],
                            value=replace(Constant(value=item.id), item),
                        ),
                        expr_stmt,
                    )
                )
            elif isinstance(item, Call) and isinstance(item.func, Name):
                functor_name = item.func.id
                field_names = [
                    arg.id if isinstance(arg, Name) else f"arg_{i}"
                    for i, arg in enumerate(item.args)
                ]
                field_names += [kw.arg for kw in item.keywords]
                private_info.append((functor_name, field_names))
                if functor_name not in transformer._seen_functors:
                    transformer._seen_functors[functor_name] = field_names
                    statements.append(
                        _make_functor_class_ast(
                            functor_name, field_names, expr_stmt
                        )
                    )
        transformer._module_items.append(PrivateDeclItem(items=private_info))
        if not statements:
            return replace(Pass(), expr_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _handle_predspec_directive(transformer, method_name, args, expr_stmt):
        """Process a directive that takes ``pred/arity, ...`` arguments.

        Emits ``$module.db.<method_name>("pred", arity)`` calls for each
        pred/arity spec.  Used by ``-dynamic``, ``-discontiguous``,
        ``-table``, and ``-shallow`` directives.
        """
        load = Load()
        specs = _parse_pred_arity_args(args, method_name)
        if not specs:
            return replace(Pass(), expr_stmt)
        statements = []
        for functor, arity in specs:
            # $module.db.<method_name>("functor", arity)
            call_node = replace(
                Expr(value=Call(
                    func=Attribute(
                        value=Attribute(
                            value=Name(id="$module", ctx=load),
                            attr="db",
                            ctx=load,
                        ),
                        attr=method_name,
                        ctx=load,
                    ),
                    args=[
                        Constant(value=functor),
                        Constant(value=arity),
                    ],
                    keywords=[],
                )),
                expr_stmt,
            )
            fix_missing_locations(call_node)
            statements.append(call_node)
        return statements if len(statements) > 1 else statements[0]

    def _handle_import_from_directive(transformer, args, expr_stmt):
        """Process ``-import_from(dotted.module, [Pred1, alias(Pred2, Local)])`` directive.

        Emits a Python ``from dotted.module import Pred1, Pred2 as Local``
        statement.  The imported names land in module globals where the
        compiler's ``_inject_call_targets`` picks them up.
        """
        if len(args) < 2:
            raise SyntaxError(
                "-import_from requires two arguments: "
                "-import_from(module.path, [Name, ...])"
            )
        module_path = _dotted_name_from_ast(args[0])
        if module_path is None:
            raise SyntaxError(
                f"-import_from: first argument must be a dotted module path, "
                f"got {dump(args[0])}"
            )
        if not isinstance(args[1], List):
            raise SyntaxError(
                f"-import_from: second argument must be a list of names, "
                f"got {dump(args[1])}"
            )
        aliases = []
        for item in args[1].elts:
            if isinstance(item, Name):
                # Map local name → "module.path.Name" for dotted globals key
                local_name = item.id
                dotted_key = f"{module_path}.{local_name}"
                transformer._import_remap[local_name] = dotted_key
                aliases.append(alias(name=item.id))
            elif (
                isinstance(item, Call)
                and isinstance(item.func, Name)
                and item.func.id == "alias"
                and len(item.args) == 2
                and isinstance(item.args[0], Name)
                and isinstance(item.args[1], Name)
            ):
                orig_name = item.args[0].id
                local_name = item.args[1].id
                dotted_key = f"{module_path}.{orig_name}"
                transformer._import_remap[local_name] = dotted_key
                aliases.append(alias(name=orig_name, asname=local_name))
            else:
                raise SyntaxError(
                    f"-import_from: import list items must be names or "
                    f"alias(OrigName, LocalName), got {dump(item)}"
                )
        # Accumulate import info for pipeline-split ModuleAST.
        import_names = []
        for a in aliases:
            if a.asname:
                import_names.append((a.name, a.asname))
            else:
                import_names.append(a.name)
        transformer._module_items.append(
            ImportFromItem(module=module_path, names=import_names)
        )
        # Resolve the module path for the generated ImportFrom AST node.
        # Bare names are mapped to ``clausal.modules.<name>`` so the
        # generated ``from ... import ...`` reaches our stdlib modules.
        # Aliases handle name collisions with Python's stdlib (e.g.
        # ``uuid`` → ``clausal.modules.uuid_mod``).
        resolved = _resolve_import_path(module_path)
        stmt = replace(
            ImportFrom(module=resolved, names=aliases, level=0),
            expr_stmt,
        )
        fix_missing_locations(stmt)
        return stmt

    def _handle_import_module_directive(transformer, args, expr_stmt):
        """Process ``-import_module(dotted.module)`` directive.

        Emits a Python ``import dotted.module`` statement.  The module object
        lands in globals; qualified calls like ``mod.Pred(X_)`` are resolved
        at compile time via ``_inject_call_targets``.
        """
        if len(args) < 1:
            raise SyntaxError(
                "-import_module requires one argument: "
                "-import_module(module.path)"
            )
        module_path = _dotted_name_from_ast(args[0])
        if module_path is None:
            raise SyntaxError(
                f"-import_module: argument must be a dotted module path, "
                f"got {dump(args[0])}"
            )
        transformer._module_items.append(
            ImportModuleItem(module=module_path)
        )
        resolved = _resolve_import_path(module_path)
        if resolved != module_path:
            # Aliased module: ``import clausal.modules.uuid_mod as uuid``
            stmt = replace(
                Import(names=[alias(name=resolved, asname=module_path)]),
                expr_stmt,
            )
        else:
            stmt = replace(
                Import(names=[alias(name=module_path)]),
                expr_stmt,
            )
        fix_missing_locations(stmt)
        return stmt

    # ── EDCG directive handlers ─────────────────────────────────────────────

    def _handle_edcg_acc_directive(transformer, args, expr_stmt):
        """Process ``-edcg_acc(name, Val_, In_, Out_, {Joiner})`` directive.

        Declares a named accumulator with a joiner goal that relates
        (Value, InputState, OutputState).
        """
        if len(args) != 5:
            raise SyntaxError(
                "-edcg_acc requires 5 arguments: "
                "-edcg_acc(name, Val_, In_, Out_, {JoinerGoal})"
            )
        name_node, val_node, in_node, out_node, joiner_node = args
        if not isinstance(name_node, Name):
            raise SyntaxError(
                f"-edcg_acc: first argument must be a name, got {dump(name_node)}"
            )
        acc_name = name_node.id
        # Extract variable names from Name nodes.
        if not isinstance(val_node, Name):
            raise SyntaxError(
                f"-edcg_acc: second argument (Val) must be a variable name, got {dump(val_node)}"
            )
        if not isinstance(in_node, Name):
            raise SyntaxError(
                f"-edcg_acc: third argument (In) must be a variable name, got {dump(in_node)}"
            )
        if not isinstance(out_node, Name):
            raise SyntaxError(
                f"-edcg_acc: fourth argument (Out) must be a variable name, got {dump(out_node)}"
            )
        # Joiner is wrapped in {braces} — a Set node in our AST.
        if isinstance(joiner_node, Set) and len(joiner_node.elts) == 1:
            joiner_ast = joiner_node.elts[0]
        else:
            joiner_ast = joiner_node

        info = {
            "val": val_node.id,
            "in_": in_node.id,
            "out": out_node.id,
            "joiner_ast": joiner_ast,
        }
        transformer._edcg_accs[acc_name] = info
        transformer._module_items.append(
            EdcgAccDecl(
                acc_name=acc_name,
                val_var=val_node.id,
                in_var=in_node.id,
                out_var=out_node.id,
                joiner_ast=joiner_ast,
            )
        )
        return replace(Pass(), expr_stmt)

    def _handle_edcg_pass_directive(transformer, args, expr_stmt):
        """Process ``-edcg_pass(name)`` directive.

        Declares a read-only passed argument that is threaded unchanged
        through EDCG rules.
        """
        if len(args) != 1:
            raise SyntaxError(
                "-edcg_pass requires 1 argument: -edcg_pass(name)"
            )
        if not isinstance(args[0], Name):
            raise SyntaxError(
                f"-edcg_pass: argument must be a name, got {dump(args[0])}"
            )
        pass_name = args[0].id
        transformer._edcg_passes.add(pass_name)
        transformer._module_items.append(EdcgPassDecl(pass_name=pass_name))
        return replace(Pass(), expr_stmt)

    def _handle_edcg_pred_directive(transformer, args, expr_stmt):
        """Process ``-edcg_pred(name, visible_arity, [acc1, pass1, ...])`` directive.

        Declares which accumulators and passed arguments a predicate uses.
        The hidden parameters are added automatically during DCG rewriting.
        """
        if len(args) != 3:
            raise SyntaxError(
                "-edcg_pred requires 3 arguments: "
                "-edcg_pred(name, visible_arity, [acc_or_pass, ...])"
            )
        name_node, arity_node, list_node = args
        if not isinstance(name_node, Name):
            raise SyntaxError(
                f"-edcg_pred: first argument must be a name, got {dump(name_node)}"
            )
        if not isinstance(arity_node, Constant) or not isinstance(arity_node.value, int):
            raise SyntaxError(
                f"-edcg_pred: second argument must be an integer, got {dump(arity_node)}"
            )
        if not isinstance(list_node, List):
            raise SyntaxError(
                f"-edcg_pred: third argument must be a list, got {dump(list_node)}"
            )
        pred_name = name_node.id
        visible_arity = arity_node.value
        acc_pass_names = []
        for item in list_node.elts:
            if isinstance(item, Name):
                item_name = item.id
                if item_name not in transformer._edcg_accs and item_name not in transformer._edcg_passes and item_name != "dcg":
                    raise SyntaxError(
                        f"-edcg_pred: '{item_name}' is not a declared accumulator or pass "
                        f"(declare with -edcg_acc or -edcg_pass before -edcg_pred)"
                    )
                acc_pass_names.append(item_name)
            else:
                raise SyntaxError(
                    f"-edcg_pred: list items must be names, got {dump(item)}"
                )
        transformer._edcg_preds[pred_name] = (visible_arity, acc_pass_names)

        # Compute full arity: visible + 2 per accumulator + 1 per pass.
        hidden_count = 0
        for ap_name in acc_pass_names:
            if ap_name in transformer._edcg_accs or ap_name == "dcg":
                hidden_count += 2  # In, Out
            elif ap_name in transformer._edcg_passes:
                hidden_count += 1  # read-only, single arg
        full_arity = visible_arity + hidden_count

        # Pre-register the functor with its full field set so the class
        # gets the right number of fields.  Field names: visible args use
        # arg_0..arg_N pattern (will be overridden by first clause), hidden
        # args use _edcg_{name}_in_, _edcg_{name}_out_, _edcg_{name}_.
        field_names = [f"arg_{i}" for i in range(visible_arity)]
        for ap_name in acc_pass_names:
            if ap_name in transformer._edcg_accs or ap_name == "dcg":
                field_names.append(f"_edcg_{ap_name}_in_")
                field_names.append(f"_edcg_{ap_name}_out_")
            elif ap_name in transformer._edcg_passes:
                field_names.append(f"_edcg_{ap_name}_")

        transformer._module_items.append(
            EdcgPredDecl(
                pred_name=pred_name,
                visible_arity=visible_arity,
                acc_pass_names=acc_pass_names,
            )
        )

        # Emit the functor class definition if not already seen.
        if pred_name not in transformer._seen_functors:
            transformer._seen_functors[pred_name] = field_names
            return _make_functor_class_ast(pred_name, field_names, expr_stmt)
        return replace(Pass(), expr_stmt)

    # ── EDCG rule rewriting ─────────────────────────────────────────────────

    def _rewrite_edcg_rule(transformer, functor_name, orig_pos_args, orig_kw_args,
                            rhs, pushback, lhs, src, expr_stmt):
        """Rewrite an EDCG ``>>`` rule into an ordinary ``<-`` clause.

        Adds hidden accumulator/pass arguments to the head and rewrites
        the body to thread multiple named accumulators.
        """
        visible_arity, ap_names = transformer._edcg_preds[functor_name]

        # Build initial accumulator/pass state for the body rewriter.
        acc_states = {}   # acc_name → (in_var, out_var)
        pass_states = {}  # pass_name → var_name

        for ap_name in ap_names:
            if ap_name in transformer._edcg_accs or ap_name == "dcg":
                in_var, out_var = _edcg_acc_vars(ap_name)
                acc_states[ap_name] = (in_var, out_var)
                orig_pos_args.append(replace(Name(id=in_var, ctx=load), src))
                orig_pos_args.append(replace(Name(id=out_var, ctx=load), src))
            elif ap_name in transformer._edcg_passes:
                pvar = _edcg_pass_var(ap_name)
                pass_states[ap_name] = pvar
                orig_pos_args.append(replace(Name(id=pvar, ctx=load), src))

        # Rewrite the EDCG body.
        counter = 0
        body_expr_raw, final_states, counter = _rewrite_edcg_body(
            rhs, acc_states, pass_states,
            transformer._edcg_accs, transformer._edcg_passes,
            transformer._edcg_preds, counter, source=src
        )

        # Close accumulator chains: if the body didn't fully thread an
        # accumulator to its out_var, add unification goals.
        closers = []
        for acc_name, (orig_in, orig_out) in acc_states.items():
            final_in, final_out = final_states.get(acc_name, (orig_in, orig_out))
            # final_in is where the chain currently points; orig_out is
            # the head's out variable.  If they differ, unify them.
            if final_in != orig_out:
                eq = Compare(
                    left=Name(id=final_in, ctx=load),
                    ops=[Is()],
                    comparators=[Name(id=orig_out, ctx=load)],
                )
                closers.append(replace(eq, src))
        if closers:
            if isinstance(body_expr_raw, BoolOp) and isinstance(body_expr_raw.op, And):
                body_expr_raw = replace(
                    BoolOp(op=And(), values=body_expr_raw.values + closers), src
                )
            else:
                body_expr_raw = replace(
                    BoolOp(op=And(), values=[body_expr_raw] + closers), src
                )

        if pushback is not None:
            raise SyntaxError("EDCG rules do not support pushback syntax")

        return transformer._finalize_dcg_rule(
            functor_name, orig_pos_args, orig_kw_args,
            body_expr_raw, lhs, src, expr_stmt
        )

    def _finalize_dcg_rule(transformer, functor_name, orig_pos_args, orig_kw_args,
                            body_expr_raw, lhs, src, expr_stmt):
        """Common tail for both DCG and EDCG rule processing.

        Takes the rewritten body AST and emits the functor class definition
        and $define_predicate call.
        """
        arg_field_names = _derive_field_names(orig_pos_args)
        kwarg_field_names = [kw.arg for kw in orig_kw_args]
        all_field_names = arg_field_names + kwarg_field_names

        prev_fields = transformer._seen_functors.get(functor_name)
        if prev_fields is not None:
            for i in range(len(arg_field_names)):
                if i < len(prev_fields):
                    arg_field_names[i] = prev_fields[i]
            all_field_names = arg_field_names + kwarg_field_names

        # Ensure all synthetic AST nodes have source positions.
        copy_location(body_expr_raw, src)
        fix_missing_locations(body_expr_raw)

        # Non-terminal call targets in the rewritten body must be
        # treated as predicate references (LoadName), not as atom
        # string constants.  Exclude them from the atom set.
        dcg_call_names = _collect_call_func_names(body_expr_raw)
        dcg_atoms = transformer._atoms - dcg_call_names
        term_transformer = TermTransformer(atoms=dcg_atoms, import_remap=transformer._import_remap)
        transformed_pos = [
            term_transformer.visit(a) for a in orig_pos_args
        ]
        transformed_kw = [
            term_transformer.visit(kw.value) for kw in orig_kw_args
        ]
        body_ast = term_transformer.visit(body_expr_raw)

        anchor = lhs.func if isinstance(lhs, Call) else lhs
        head_keywords = [
            make_keyword_node(fname, term, orig)
            for fname, term, orig in zip(
                arg_field_names, transformed_pos, orig_pos_args
            )
        ] + [
            make_keyword_node(fname, term, orig)
            for fname, term, orig in zip(
                kwarg_field_names, transformed_kw, orig_kw_args
            )
        ]
        head_ast = replace(
            Call(
                func=replace(Name(id=functor_name, ctx=load), anchor),
                args=[],
                keywords=head_keywords,
            ),
            lhs,
        )

        predicate_ast = node_ast(
            "Predicate", src, head=head_ast, body=body_ast
        )
        define_stmt = replace(
            Expr(
                value=replace(
                    Call(
                        func=replace(
                            Name(id="$define_predicate", ctx=load), src
                        ),
                        args=[
                            predicate_ast,
                            replace(Name(id="$module", ctx=load), src),
                        ],
                        keywords=[],
                    ),
                    src,
                )
            ),
            expr_stmt,
        )

        statements = []
        if functor_name not in transformer._seen_functors:
            transformer._seen_functors[functor_name] = all_field_names
            statements.append(
                _make_functor_class_ast(
                    functor_name, all_field_names, expr_stmt
                )
            )
        statements.append(define_stmt)
        return statements if len(statements) > 1 else statements[0]

    def visit_With(transformer, with_statement):
        first = with_statement.items[0]
        ctx = first.context_expr

        def _is_double(op_type):
            """True if ctx is op_type(op_type(Dict(…))) with adjacent operators."""
            return (
                isinstance(ctx, UnaryOp) and isinstance(ctx.op, op_type)
                and isinstance(ctx.operand, UnaryOp) and isinstance(ctx.operand.op, op_type)
                and isinstance(ctx.operand.operand, Dict)
                and ctx.lineno == ctx.operand.lineno
                and ctx.col_offset == ctx.operand.col_offset - 1
            )

        if _is_double(USub):
            # with --{} as target: — block form of --; produces simple_ast terms.
            term_transformer = TermTransformer(atoms=transformer._atoms, import_remap=transformer._import_remap)
            elements = [
                term_transformer.visit(stmt.value)
                for stmt in with_statement.body
                if isinstance(stmt, Expr)
            ]
            return replace(
                Assign(
                    targets=[first.optional_vars],
                    value=replace(List(elts=elements, ctx=load), with_statement),
                ),
                with_statement,
            )

        if _is_double(Invert):
            # with ~~{} as target: — block form of ~~; produces Python ast nodes.
            elements = [
                _py_ast_expr(
                    stmt.value if isinstance(stmt, Expr) else stmt,
                    stmt,
                )
                for stmt in with_statement.body
            ]
            return replace(
                Assign(
                    targets=[first.optional_vars],
                    value=replace(List(elts=elements, ctx=load), with_statement),
                ),
                with_statement,
            )

        return transformer.generic_visit(with_statement)

    def visit_Name(transformer, name):
        # In outer Python code, rewrite var_ / ALL_CAPS → .value to unbox a logic variable.
        if _is_logic_var_name(name.id):
            return replace(
                Attribute(value=name, attr="value", ctx=load),
                name,
            )
        return name
