from ast import *


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


def load_name_ast(name, src):
    return replace(Name(id=name, ctx=load), src)


def _kw(arg, value, src):
    kw = keyword(arg=arg, value=value)
    kw.lineno = src.lineno
    kw.col_offset = src.col_offset
    kw.end_lineno = src.end_lineno
    kw.end_col_offset = src.end_col_offset
    return kw


def pos_ast(src, end=None):
    """Generate Python AST for SourcePosition(lineno=..., col_offset=..., ...)"""
    if end is None:
        end = src
    return replace(
        Call(
            func=load_name_ast('SourcePosition', src),
            args=[],
            keywords=[
                _kw('lineno',          replace(Constant(value=src.lineno),          src), src),
                _kw('col_offset',      replace(Constant(value=src.col_offset),      src), src),
                _kw('end_lineno',      replace(Constant(value=end.end_lineno),      src), src),
                _kw('end_col_offset',  replace(Constant(value=end.end_col_offset),  src), src),
            ]
        ),
        src
    )


def node_ast(classname, src, end=None, **fields):
    """Generate Python AST for: classname(field=val, ..., position=SourcePosition(...))"""
    kws = [_kw(k, v, src) for k, v in fields.items()]
    kws.append(_kw('position', pos_ast(src, end), src))
    return replace(
        Call(func=load_name_ast(classname, src), args=[], keywords=kws),
        src
    )


def list_ast(elts, src):
    """Generate Python AST for a list literal [elem, ...]"""
    return replace(List(elts=list(elts), ctx=load), src)


# ─── Operator → simple_ast class name mappings ────────────────────────────────

BINOP_CLS = {
    Add:      'Add',      Sub:      'Sub',      Mult:  'Mult',   Div:    'Div',
    FloorDiv: 'FloorDiv', Mod:      'Mod',      Pow:   'Pow',    MatMult:'MatMult',
    LShift:   'LShift',   RShift:   'RShift',
    BitOr:    'BitOr',    BitXor:   'BitXor',   BitAnd:'BitAnd',
}

UNARYOP_CLS = {
    USub: 'Negate', UAdd: 'UnaryPlus', Not: 'Not', Invert: 'Invert',
}

BOOLOP_CLS = {
    And: 'And', Or: 'Or',
}

CMPOP_CLS = {
    Eq: 'Eq', NotEq: 'NotEq', Lt: 'Lt', LtE: 'LtE',
    Gt: 'Gt', GtE: 'GtE', Is: 'Is', IsNot: 'IsNot',
    In: 'In', NotIn: 'NotIn',
}


# ─── Term Transformer ─────────────────────────────────────────────────────────

class TermTransformer(NodeTransformer):
    """Transform a Python expression AST into Python AST that constructs simple_ast nodes."""

    def __init__(transformer):
        transformer.seen_vars = set()

    def visit_Await(transformer, await_expr):
        return node_ast('Await', await_expr,
            value=transformer.visit(await_expr.value))

    def visit_BinOp(transformer, binop):
        cls = BINOP_CLS[type(binop.op)]
        return node_ast(cls, binop,
            left=transformer.visit(binop.left),
            right=transformer.visit(binop.right))

    def visit_BoolOp(transformer, boolop):
        # Python's BoolOp has N values; simple_ast uses nested binary And/Or
        cls = BOOLOP_CLS[type(boolop.op)]
        values = [transformer.visit(v) for v in boolop.values]
        result = values[0]
        for v in values[1:]:
            result = node_ast(cls, boolop, left=result, right=v)
        return result

    def visit_Call(transformer, call):
        visit = transformer.visit
        args = [visit(a) for a in call.args]
        # Convert keyword arguments to Keyword simple_ast nodes
        kwargs_nodes = [
            node_ast('Keyword', kw,
                name=replace(Constant(value=kw.arg), kw),
                value=visit(kw.value))
            for kw in call.keywords
        ]
        return node_ast('Call', call,
            func=visit(call.func),
            args=list_ast(args, call),
            kwargs=list_ast(kwargs_nodes, call))

    def visit_Compare(transformer, compare):
        ops = compare.ops
        comparators = compare.comparators
        left = compare.left

        # Detect '<-' pseudo-operator: written as  a <- b  in source.
        # Python parses this as Compare(left=a, ops=[Lt], comparators=[UnaryOp(USub, b)]).
        # We recognise it when the '-' immediately follows '<' (no space between them).
        if (len(ops) == 1
                and isinstance(ops[0], Lt)
                and isinstance(comparators[0], UnaryOp)
                and isinstance(comparators[0].op, USub)):
            rhs_node = comparators[0]
            # col_offset of the UnaryOp is where '-' sits; '<' is one before it.
            if left.end_col_offset + 1 == rhs_node.col_offset:
                return node_ast('Assign', compare,
                    targets=list_ast([transformer.visit(left)], compare),
                    value=transformer.visit(rhs_node.operand))

        if len(ops) == 1:
            cls = CMPOP_CLS[type(ops[0])]
            return node_ast(cls, compare,
                left=transformer.visit(left),
                right=transformer.visit(comparators[0]))

        # Multi-comparison chain → CompareChain
        all_operands = [left] + list(comparators)
        cmp_nodes = [
            node_ast(CMPOP_CLS[type(op)], all_operands[i],
                left=transformer.visit(all_operands[i]),
                right=transformer.visit(all_operands[i + 1]))
            for i, op in enumerate(ops)
        ]
        return node_ast('CompareChain', compare,
            comparisons=list_ast(cmp_nodes, compare))

    def visit_Constant(transformer, constant):
        v = constant.value
        if v is None:
            return node_ast('NoneLiteral', constant)
        if v is ...:
            return node_ast('EllipsisLiteral', constant)
        # bool must precede int (bool is a subclass of int)
        if isinstance(v, bool):
            return node_ast('BoolLiteral', constant, value=constant)
        if isinstance(v, int):
            return node_ast('IntLiteral', constant, value=constant)
        if isinstance(v, float):
            return node_ast('FloatLiteral', constant, value=constant)
        if isinstance(v, complex):
            return node_ast('ComplexLiteral', constant, value=constant)
        if isinstance(v, str):
            return node_ast('StringLiteral', constant, value=constant)
        if isinstance(v, bytes):
            return node_ast('BytesLiteral', constant, value=constant)
        raise NotImplementedError(f"Unknown constant type: {type(v)!r}")

    def visit_Dict(transformer, dict_expr):
        keys = list_ast(
            [transformer.visit(k) if k is not None
             else replace(Constant(value=None), dict_expr)
             for k in dict_expr.keys],
            dict_expr
        )
        values = list_ast([transformer.visit(v) for v in dict_expr.values], dict_expr)
        return node_ast('DictLiteral', dict_expr, keys=keys, values=values)

    def visit_DictComp(transformer, dictcomp):
        return node_ast('DictComp', dictcomp,
            key=transformer.visit(dictcomp.key),
            value=transformer.visit(dictcomp.value),
            clauses=list_ast(
                [transformer._visit_comprehension(g) for g in dictcomp.generators],
                dictcomp))

    def visit_GeneratorExp(transformer, gen_exp):
        return node_ast('GeneratorExpr', gen_exp,
            element=transformer.visit(gen_exp.elt),
            clauses=list_ast(
                [transformer._visit_comprehension(g) for g in gen_exp.generators],
                gen_exp))

    def visit_IfExp(transformer, if_exp):
        return node_ast('IfExpr', if_exp,
            test=transformer.visit(if_exp.test),
            body=transformer.visit(if_exp.body),
            orelse=transformer.visit(if_exp.orelse))

    def visit_Lambda(transformer, lambda_expr):
        # Give the lambda body its own scope for seen_vars
        lambda_transformer = TermTransformer()
        return node_ast('Lambda', lambda_expr,
            params=transformer._visit_arguments(lambda_expr.args, lambda_transformer),
            body=lambda_transformer.visit(lambda_expr.body))

    def visit_List(transformer, list_expr):
        return node_ast('ListLiteral', list_expr,
            elements=list_ast(
                [transformer.visit(e) for e in list_expr.elts], list_expr))

    def visit_ListComp(transformer, listcomp):
        return node_ast('ListComp', listcomp,
            element=transformer.visit(listcomp.elt),
            clauses=list_ast(
                [transformer._visit_comprehension(g) for g in listcomp.generators],
                listcomp))

    def visit_Name(transformer, name):
        id = name.id
        if id[0] == '_' and id != '_':
            # Logic variable: first occurrence allocates a Var; subsequent ones reuse it.
            if id in transformer.seen_vars:
                return replace(Name(id=id, ctx=load), name)
            transformer.seen_vars.add(id)
            return replace(
                NamedExpr(
                    target=replace(Name(id=id, ctx=store), name),
                    value=replace(
                        Call(
                            func=replace(Name(id='Var', ctx=load), name),
                            args=[replace(Constant(value=id), name)],
                            keywords=[]
                        ),
                        name
                    ),
                ),
                name
            )
        return node_ast('LoadName', name,
            name=replace(Constant(value=id), name))

    def visit_NamedExpr(transformer, named_expr):
        return node_ast('NamedExpr', named_expr,
            target=transformer.visit(named_expr.target),
            value=transformer.visit(named_expr.value))

    def visit_Set(transformer, set_expr):
        return node_ast('SetLiteral', set_expr,
            elements=list_ast(
                [transformer.visit(e) for e in set_expr.elts], set_expr))

    def visit_SetComp(transformer, setcomp):
        return node_ast('SetComp', setcomp,
            element=transformer.visit(setcomp.elt),
            clauses=list_ast(
                [transformer._visit_comprehension(g) for g in setcomp.generators],
                setcomp))

    def visit_Starred(transformer, starred):
        return node_ast('StarUnpack', starred,
            value=transformer.visit(starred.value))

    def visit_Subscript(transformer, subscript):
        return node_ast('LoadSubscript', subscript,
            object=transformer.visit(subscript.value),
            index=transformer.visit(subscript.slice))

    def visit_Tuple(transformer, tuple_expr):
        assert type(tuple_expr.ctx) == Load
        return node_ast('TupleLiteral', tuple_expr,
            elements=list_ast(
                [transformer.visit(e) for e in tuple_expr.elts], tuple_expr))

    def visit_UnaryOp(transformer, unary_op):
        cls = UNARYOP_CLS[type(unary_op.op)]
        return node_ast(cls, unary_op,
            operand=transformer.visit(unary_op.operand))

    def visit_Yield(transformer, yield_expr):
        if yield_expr.value is not None:
            return node_ast('Yield', yield_expr,
                value=transformer.visit(yield_expr.value))
        return node_ast('Yield', yield_expr)

    def visit_YieldFrom(transformer, yield_from_expr):
        return node_ast('YieldFrom', yield_from_expr,
            value=transformer.visit(yield_from_expr.value))

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _visit_comprehension(transformer, comp):
        """Convert an ast.comprehension into Python AST constructing a ForClause node."""
        src = comp.iter  # use the iterable as the source-position anchor
        filters = list_ast([transformer.visit(f) for f in comp.ifs], src)
        return node_ast('ForClause', src,
            target=transformer.visit(comp.target),
            iterable=transformer.visit(comp.iter),
            filters=filters,
            is_async=replace(Constant(value=bool(comp.is_async)), src))

    def _visit_arguments(transformer, args, body_transformer):
        """Convert ast.arguments into Python AST that constructs a Params node."""
        param_nodes = []

        for a in args.posonlyargs:
            kws = [_kw('name', replace(Constant(value=a.arg), a), a)]
            if a.annotation:
                kws.append(_kw('annotation', body_transformer.visit(a.annotation), a))
            param_nodes.append(replace(
                Call(func=load_name_ast('PosOnlyParam', a), args=[], keywords=kws), a))

        for a in args.args:
            kws = [_kw('name', replace(Constant(value=a.arg), a), a)]
            if a.annotation:
                kws.append(_kw('annotation', body_transformer.visit(a.annotation), a))
            param_nodes.append(replace(
                Call(func=load_name_ast('PosOrKwParam', a), args=[], keywords=kws), a))

        # defaults right-align over posonlyargs + args combined
        all_pos = args.posonlyargs + args.args
        n_defaults = len(args.defaults)
        if n_defaults:
            offset = len(all_pos) - n_defaults
            for i, default_node in enumerate(args.defaults):
                a = all_pos[offset + i]
                param_nodes[offset + i] = replace(
                    Call(
                        func=load_name_ast('PosOrKwParam' if a in args.args else 'PosOnlyParam', a),
                        args=[],
                        keywords=param_nodes[offset + i].keywords + [
                            _kw('default', body_transformer.visit(default_node), a)
                        ]
                    ),
                    a
                )

        if args.vararg:
            a = args.vararg
            kws = [_kw('name', replace(Constant(value=a.arg), a), a)]
            if a.annotation:
                kws.append(_kw('annotation', body_transformer.visit(a.annotation), a))
            param_nodes.append(replace(
                Call(func=load_name_ast('VarPositional', a), args=[], keywords=kws), a))

        for i, a in enumerate(args.kwonlyargs):
            kws = [_kw('name', replace(Constant(value=a.arg), a), a)]
            if a.annotation:
                kws.append(_kw('annotation', body_transformer.visit(a.annotation), a))
            if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
                kws.append(_kw('default', body_transformer.visit(args.kw_defaults[i]), a))
            param_nodes.append(replace(
                Call(func=load_name_ast('KwOnlyParam', a), args=[], keywords=kws), a))

        if args.kwarg:
            a = args.kwarg
            kws = [_kw('name', replace(Constant(value=a.arg), a), a)]
            if a.annotation:
                kws.append(_kw('annotation', body_transformer.visit(a.annotation), a))
            param_nodes.append(replace(
                Call(func=load_name_ast('VarKeyword', a), args=[], keywords=kws), a))

        # Pick a representative source position for the Params wrapper
        anchor = (
            args.posonlyargs or args.args or
            ([args.vararg] if args.vararg else []) or
            args.kwonlyargs or
            ([args.kwarg] if args.kwarg else [])
        )
        if anchor:
            src = anchor[0]
            return replace(
                Call(
                    func=load_name_ast('Params', src),
                    args=[],
                    keywords=[_kw('params', list_ast(param_nodes, src), src)]
                ),
                src
            )
        # No parameters at all
        return load_name_ast('Params', args)


# ─── Embed Transformer ────────────────────────────────────────────────────────

class EmbedTransformer(NodeTransformer):
    """Walk Python source and expand DSL escapes into simple_ast constructor calls.

    Recognised patterns:
      --expr            Nested adjacent USub: transforms expr via TermTransformer.
      (head,)           Trailing-comma tuple expression-statement: Prolog fact notation.
      with the_following as target:
          <body>        Converts body statements via TermTransformer, assigns list to target.
      _name             In outer Python code, rewrites to _name.value (unbox logic var).
    """

    def visit_UnaryOp(transformer, unary_op):
        match unary_op:  # -- term_expression
            case UnaryOp(
                op=USub(),
                operand=UnaryOp(
                    op=USub(),
                    operand=expression
                )
            ):
                # '--' must be written without a space (the two '-' are adjacent).
                if (unary_op.col_offset == unary_op.operand.col_offset - 1
                        and unary_op.lineno == unary_op.operand.lineno):
                    return TermTransformer().visit(expression)
        unary_op.operand = transformer.visit(unary_op.operand)
        return unary_op

    def visit_Expr(transformer, expr_stmt):
        """Detect trailing-comma tuple: (head,) — Prolog fact notation."""
        match expr_stmt.value:
            case Tuple(elts=[single_elt], ctx=Load()):
                # Transform the single element as a term and pass to assert_fact
                term = TermTransformer().visit(single_elt)
                return replace(
                    Expr(value=replace(
                        Call(
                            func=replace(Name(id='assert_fact', ctx=load), expr_stmt.value),
                            args=[term],
                            keywords=[]
                        ),
                        expr_stmt.value
                    )),
                    expr_stmt
                )
        return transformer.generic_visit(expr_stmt)

    def visit_With(transformer, with_statement):
        first = with_statement.items[0]
        if isinstance(first.context_expr, Name) and first.context_expr.id == 'the_following':
            tt = TermTransformer()
            elts = [
                tt.visit(stmt.value) if isinstance(stmt, Expr) else tt.visit(stmt)
                for stmt in with_statement.body
            ]
            return replace(
                Assign(
                    targets=[first.optional_vars],
                    value=replace(List(elts=elts, ctx=load), with_statement)
                ),
                with_statement
            )
        return transformer.generic_visit(with_statement)

    def visit_Name(transformer, name):
        # In outer Python code, rewrite _Var → _Var.value to unbox a logic variable.
        # Ignore dunders and bare '_'.
        if name.id[0] == '_' and name.id[-1] != '_' and name.id != '_':
            return replace(
                Attribute(
                    value=name,
                    attr='value',
                    ctx=load
                ),
                name,
            )
        return name
