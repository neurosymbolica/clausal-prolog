from ast import *

from .parser import is_template_func
from .compiler import compile_template_func

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
    Eq: "Eq",
    NotEq: "NotEq",
    Lt: "Lt",
    LtE: "LtE",
    Gt: "Gt",
    GtE: "GtE",
    Is: "Is",
    IsNot: "IsNot",
    In: "In",
    NotIn: "NotIn",
}


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


# ─── Term Transformer ─────────────────────────────────────────────────────────


class TermTransformer(NodeTransformer):
    """Transform a Python expression AST into Python AST that constructs simple_ast nodes."""

    def __init__(transformer):
        transformer.seen_vars = set()

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
        # Python parses this as Compare(left=a, ops=[Lt], comparators=[UnaryOp(USub, b)]).
        # We recognise it when the '-' immediately follows '<' (no space between them).
        if (
            len(operators) == 1
            and isinstance(operators[0], Lt)
            and isinstance(comparators[0], UnaryOp)
            and isinstance(comparators[0].op, USub)
        ):
            right_hand_side = comparators[0]
            # Detect '<-': '<' and '-' must be adjacent (no space between them).
            # The gap from left's end to '-' is 1 for `a<-b` or 2 for `a <- b`;
            # a gap of 3+ means `a < -b` (space between '<' and '-').
            if (
                left.end_lineno == right_hand_side.lineno
                and 1 <= right_hand_side.col_offset - left.end_col_offset <= 2
            ):
                return node_ast(
                    "Predicate",
                    compare,
                    head=transformer.visit(left),
                    body=transformer.visit(right_hand_side.operand),
                )

        # Detect 'X == +Y': Eq with a UnaryPlus right-hand side → ArithConstraint stub.
        # Emits ArithConstraint(expr=Eq(X, Y)) so the compiler can raise NotImplementedError.
        if (
            len(operators) == 1
            and isinstance(operators[0], Eq)
            and isinstance(comparators[0], UnaryOp)
            and isinstance(comparators[0].op, UAdd)
        ):
            eq_node = node_ast(
                "Eq",
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
        return node_ast(
            "IfExpr",
            if_expression,
            test=transformer.visit(if_expression.test),
            body=transformer.visit(if_expression.body),
            orelse=transformer.visit(if_expression.orelse),
        )

    def visit_Lambda(transformer, lambda_expr):
        # Give the lambda body its own scope for seen_vars
        lambda_transformer = TermTransformer()
        return node_ast(
            "Lambda",
            lambda_expr,
            params=transformer._visit_arguments(lambda_expr.args, lambda_transformer),
            body=lambda_transformer.visit(lambda_expr.body),
        )

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
        return node_ast(
            "LoadName", name, name=replace(Constant(value=identifier), name)
        )

    def visit_NamedExpr(transformer, named_expr):
        return node_ast(
            "NamedExpr",
            named_expr,
            target=transformer.visit(named_expr.target),
            value=transformer.visit(named_expr.value),
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


# ─── Embed Transformer ────────────────────────────────────────────────────────


class EmbedTransformer(NodeTransformer):
    """Walk Python source and expand DSL escapes into simple_ast constructor calls.

    Recognised patterns:
      --expr      Nested adjacent USub: transforms expr via TermTransformer.
      ~~expr      Nested adjacent Invert: produces a standard Python ast.XXX node.
      head,       Trailing-comma tuple expression-statement: Prolog fact notation.
      head<-body  Module-level predicate definition (only at module scope).
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
                    return TermTransformer().visit(expression)
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
        match expr_stmt.value:
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

                term_transformer = TermTransformer()
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
            case Compare(
                left=left,
                ops=[Lt()],
                comparators=[UnaryOp(op=USub(), operand=body_expr) as rhs],
            ) if (
                left.end_lineno == rhs.lineno
                and 1 <= rhs.col_offset - left.end_col_offset <= 2
                and transformer._scope_depth == 0
            ):
                # Module-level predicate definition: functor_call<-body (no space)
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
                term_transformer = TermTransformer()
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
            term_transformer = TermTransformer()
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
