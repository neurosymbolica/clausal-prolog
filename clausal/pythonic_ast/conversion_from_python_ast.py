import ast
from typing import Any, Optional
from .nodes import *

# ── Modules ──────────────────────────────────────────────────────────────────

def convert_module(node: ast.Module) -> Module:
    return Module(body=visit_list(node.body))

def convert_interactive(node: ast.Interactive) -> Interactive:
    return Interactive(body=visit_list(node.body))

def convert_expression(node: ast.Expression) -> Expression:
    return Expression(body=visit(node.body))


# ── Literals ─────────────────────────────────────────────────────────────────

_CONSTANT_TYPE_MAP: dict[type, type] = {
    bool: BoolLiteral,   # must be before int in isinstance checks, but here we use exact type
    int: IntLiteral,
    float: FloatLiteral,
    complex: ComplexLiteral,
    str: StringLiteral,
    bytes: BytesLiteral,
}

def convert_constant(node: ast.Constant) -> Node:
    v = node.value
    if v is None:
        return locate(node, NoneLiteral())
    if v is ...:
        return locate(node, EllipsisLiteral())
    # bool must be checked before int (bool is a subclass of int)
    if isinstance(v, bool):
        return locate(node, BoolLiteral(value=v))
    cls = _CONSTANT_TYPE_MAP.get(type(v))
    if cls is not None:
        return locate(node, cls(value=v))
    raise NotImplementedError(f"Unknown constant type: {type(v)} ({v!r})")


def convert_joined_str(node: ast.JoinedStr) -> FString:
    return locate(node, FString(parts=visit_list(node.values)))


_CONVERSION_MAP = {-1: None, ord("s"): "s", ord("r"): "r", ord("a"): "a"}

def convert_formatted_value(node: ast.FormattedValue) -> FormattedExpr:
    return locate(node, FormattedExpr(
        value=visit(node.value),
        conversion=_CONVERSION_MAP.get(node.conversion),
        format_spec=visit(node.format_spec) if node.format_spec else None,
    ))


# ── Collections with context ────────────────────────────────────────────────

_LIST_CTX = {ast.Store: lambda elts: ListPattern(targets=elts)}
_TUPLE_CTX = {ast.Store: lambda elts: TuplePattern(targets=elts)}

def convert_list(node: ast.List) -> Node:
    elts = visit_list(node.elts)
    factory = _LIST_CTX.get(type(node.ctx))
    return locate(node, factory(elts) if factory else ListLiteral(elements=elts))

def convert_tuple(node: ast.Tuple) -> Node:
    elts = visit_list(node.elts)
    factory = _TUPLE_CTX.get(type(node.ctx))
    return locate(node, factory(elts) if factory else TupleLiteral(elements=elts))

def convert_set(node: ast.Set) -> SetLiteral:
    return locate(node, SetLiteral(elements=visit_list(node.elts)))

def convert_dict(node: ast.Dict) -> DictLiteral:
    return locate(node, DictLiteral(
        keys=[visit(k) if k else None for k in node.keys],
        values=visit_list(node.values),
    ))


# ── Names / Attributes / Subscripts ─────────────────────────────────────────

_NAME_CTX = {
    ast.Load: lambda id: LoadName(name=id),
    ast.Store: lambda id: StoreName(name=id),
    ast.Del: lambda id: DeleteName(name=id),
}

def convert_name(node: ast.Name) -> Node:
    return locate(node, _NAME_CTX[type(node.ctx)](node.id))


_ATTR_CTX = {
    ast.Load: lambda obj, attr: LoadAttr(object=obj, attr=attr),
    ast.Store: lambda obj, attr: StoreAttr(object=obj, attr=attr),
    ast.Del: lambda obj, attr: DeleteAttr(object=obj, attr=attr),
}

def convert_attribute(node: ast.Attribute) -> Node:
    return locate(node, _ATTR_CTX[type(node.ctx)](visit(node.value), node.attr))


_SUBSCRIPT_CTX = {
    ast.Load: lambda obj, idx: LoadSubscript(object=obj, index=idx),
    ast.Store: lambda obj, idx: StoreSubscript(object=obj, index=idx),
    ast.Del: lambda obj, idx: DeleteSubscript(object=obj, index=idx),
}

def convert_subscript(node: ast.Subscript) -> Node:
    return locate(node, _SUBSCRIPT_CTX[type(node.ctx)](visit(node.value), visit(node.slice)))


_STARRED_CTX = {
    ast.Store: lambda val: StarTarget(target=val),
}

def convert_starred(node: ast.Starred) -> Node:
    val = visit(node.value)
    factory = _STARRED_CTX.get(type(node.ctx))
    return locate(node, factory(val) if factory else StarUnpack(value=val))


def convert_slice(node: ast.Slice) -> Slice:
    return locate(node, Slice(
        lower=visit(node.lower) if node.lower else None,
        upper=visit(node.upper) if node.upper else None,
        step=visit(node.step) if node.step else None,
    ))


# ── Binary Operators ─────────────────────────────────────────────────────────

BINOP_CLASS: dict[type, type] = {
    ast.Add: Add, ast.Sub: Sub, ast.Mult: Mult, ast.Div: Div,
    ast.FloorDiv: FloorDiv, ast.Mod: Mod, ast.Pow: Pow, ast.MatMult: MatMult,
    ast.LShift: LShift, ast.RShift: RShift,
    ast.BitOr: BitOr, ast.BitXor: BitXor, ast.BitAnd: BitAnd,
}

def convert_binop(node: ast.BinOp) -> Node:
    return locate(node, BINOP_CLASS[type(node.op)](
        left=visit(node.left), right=visit(node.right),
    ))


# ── Unary Operators ──────────────────────────────────────────────────────────

UNARYOP_CLASS: dict[type, type] = {
    ast.UAdd: UnaryPlus, ast.USub: Negate, ast.Not: Not, ast.Invert: Invert,
}

def convert_unaryop(node: ast.UnaryOp) -> Node:
    return locate(node, UNARYOP_CLASS[type(node.op)](operand=visit(node.operand)))


# ── Boolean Operators ────────────────────────────────────────────────────────

BOOLOP_CLASS: dict[type, type] = {ast.And: And, ast.Or: Or}

def convert_boolop(node: ast.BoolOp) -> Node:
    cls = BOOLOP_CLASS[type(node.op)]
    values = [visit(v) for v in node.values]
    result = values[0]
    for v in values[1:]:
        result = locate(node, cls(left=result, right=v))
    return result


# ── Comparison Operators ─────────────────────────────────────────────────────

COMPARISON_CLASS: dict[type, type] = {
    ast.Eq: ArithEq, ast.NotEq: ArithNeq, ast.Lt: Lt, ast.LtE: LtE,
    ast.Gt: Gt, ast.GtE: GtE, ast.Is: Unify, ast.IsNot: DoesNotUnify,
    ast.In: In, ast.NotIn: NotIn,
}

def convert_compare(node: ast.Compare) -> Node:
    if len(node.ops) == 1:
        return locate(node, COMPARISON_CLASS[type(node.ops[0])](
            left=visit(node.left), right=visit(node.comparators[0]),
        ))
    all_operands = [visit(node.left)] + [visit(c) for c in node.comparators]
    comparisons = [
        COMPARISON_CLASS[type(op)](left=all_operands[i], right=all_operands[i + 1])
        for i, op in enumerate(node.ops)
    ]
    return locate(node, CompareChain(comparisons=comparisons))


# ── Augmented Assignment ─────────────────────────────────────────────────────

AUGASSIGN_CLASS: dict[type, type] = {
    ast.Add: AddAssign, ast.Sub: SubAssign, ast.Mult: MultAssign,
    ast.Div: DivAssign, ast.FloorDiv: FloorDivAssign, ast.Mod: ModAssign,
    ast.Pow: PowAssign, ast.MatMult: MatMultAssign,
    ast.LShift: LShiftAssign, ast.RShift: RShiftAssign,
    ast.BitOr: BitOrAssign, ast.BitXor: BitXorAssign, ast.BitAnd: BitAndAssign,
}

def convert_augassign(node: ast.AugAssign) -> Node:
    return locate(node, AUGASSIGN_CLASS[type(node.op)](
        target=visit(node.target), value=visit(node.value),
    ))


# ── Expressions ──────────────────────────────────────────────────────────────

def convert_call(node: ast.Call) -> Call:
    kwargs = [
        locate(kw, Keyword(name=kw.arg, value=visit(kw.value)))
        for kw in node.keywords
    ]
    return locate(node, Call(
        func=visit(node.func), args=visit_list(node.args), kwargs=kwargs,
    ))

def convert_ifexp(node: ast.IfExp) -> IfExpr:
    return locate(node, IfExpr(
        test=visit(node.test), body=visit(node.body), orelse=visit(node.orelse),
    ))

def convert_namedexpr(node: ast.NamedExpr) -> NamedExpr:
    return locate(node, NamedExpr(target=visit(node.target), value=visit(node.value)))

def convert_lambda(node: ast.Lambda) -> Lambda:
    return locate(node, Lambda(params=convert_arguments(node.args), body=visit(node.body)))

def convert_yield(node: ast.Yield) -> Yield:
    return locate(node, Yield(value=visit(node.value) if node.value else None))

def convert_yieldfrom(node: ast.YieldFrom) -> YieldFrom:
    return locate(node, YieldFrom(value=visit(node.value)))

def convert_await(node: ast.Await) -> Await:
    return locate(node, Await(value=visit(node.value)))


# ── Comprehensions ───────────────────────────────────────────────────────────

def convert_generators(generators: list[ast.comprehension]) -> list[ForClause]:
    return [
        ForClause(
            target=visit(gen.target), iterable=visit(gen.iter),
            filters=[visit(f) for f in gen.ifs], is_async=bool(gen.is_async),
        )
        for gen in generators
    ]

def convert_listcomp(node: ast.ListComp) -> ListComp:
    return locate(node, ListComp(
        element=visit(node.elt), clauses=convert_generators(node.generators),
    ))

def convert_setcomp(node: ast.SetComp) -> SetComp:
    return locate(node, SetComp(
        element=visit(node.elt), clauses=convert_generators(node.generators),
    ))

def convert_dictcomp(node: ast.DictComp) -> DictComp:
    return locate(node, DictComp(
        key=visit(node.key), value=visit(node.value),
        clauses=convert_generators(node.generators),
    ))

def convert_generatorexp(node: ast.GeneratorExp) -> GeneratorExpr:
    return locate(node, GeneratorExpr(
        element=visit(node.elt), clauses=convert_generators(node.generators),
    ))


# ── Parameters ───────────────────────────────────────────────────────────────

def convert_arguments(args: ast.arguments) -> Params:
    params: list[Param] = []

    for a in args.posonlyargs:
        params.append(PosOnlyParam(
            name=a.arg,
            annotation=visit(a.annotation) if a.annotation else None,
        ))

    for a in args.args:
        params.append(PosOrKwParam(
            name=a.arg,
            annotation=visit(a.annotation) if a.annotation else None,
        ))

    # defaults right-align to the combined posonlyargs + args
    all_positional = params[:]
    n_defaults = len(args.defaults)
    if n_defaults:
        defaults = [visit(d) for d in args.defaults]
        for i, d in enumerate(defaults):
            all_positional[len(all_positional) - n_defaults + i].default = d

    if args.vararg:
        params.append(VarPositional(
            name=args.vararg.arg,
            annotation=visit(args.vararg.annotation) if args.vararg.annotation else None,
        ))

    for i, a in enumerate(args.kwonlyargs):
        default = None
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default = visit(args.kw_defaults[i])
        params.append(KwOnlyParam(
            name=a.arg,
            annotation=visit(a.annotation) if a.annotation else None,
            default=default,
        ))

    if args.kwarg:
        params.append(VarKeyword(
            name=args.kwarg.arg,
            annotation=visit(args.kwarg.annotation) if args.kwarg.annotation else None,
        ))

    return Params(params=params)


# ── Statements ───────────────────────────────────────────────────────────────

def convert_expr_stmt(node: ast.Expr) -> Node:
    """No ExprStmt wrapper — return the expression directly."""
    return visit(node.value)

def convert_assign(node: ast.Assign) -> Assign:
    return locate(node, Assign(targets=visit_list(node.targets), value=visit(node.value)))

def convert_annassign(node: ast.AnnAssign) -> AnnAssign:
    return locate(node, AnnAssign(
        target=visit(node.target), annotation=visit(node.annotation),
        value=visit(node.value) if node.value else None, simple=bool(node.simple),
    ))

def convert_delete(node: ast.Delete) -> list[Node]:
    return [visit(t) for t in node.targets]

def convert_return(node: ast.Return) -> Return:
    return locate(node, Return(value=visit(node.value) if node.value else None))

def convert_pass(node: ast.Pass) -> Pass:
    return locate(node, Pass())

def convert_break(node: ast.Break) -> Break:
    return locate(node, Break())

def convert_continue(node: ast.Continue) -> Continue:
    return locate(node, Continue())

def convert_raise(node: ast.Raise) -> Raise:
    return locate(node, Raise(
        exc=visit(node.exc) if node.exc else None,
        cause=visit(node.cause) if node.cause else None,
    ))

def convert_assert(node: ast.Assert) -> Assert:
    return locate(node, Assert(
        test=visit(node.test), msg=visit(node.msg) if node.msg else None,
    ))

def convert_global(node: ast.Global) -> Global:
    return locate(node, Global(names=list(node.names)))

def convert_nonlocal(node: ast.Nonlocal) -> Nonlocal:
    return locate(node, Nonlocal(names=list(node.names)))


# --- Imports (flattened) ---

def convert_import(node: ast.Import) -> list[Import]:
    return [locate(node, Import(module=a.name, alias=a.asname)) for a in node.names]

def convert_importfrom(node: ast.ImportFrom) -> list[ImportFrom]:
    return [
        locate(node, ImportFrom(
            module=node.module, name=a.name, alias=a.asname, level=node.level,
        ))
        for a in node.names
    ]


# --- Compound statements ---

def convert_if(node: ast.If) -> If:
    return locate(node, If(
        test=visit(node.test), body=visit_list(node.body),
        orelse=visit_list(node.orelse),
    ))

def convert_while(node: ast.While) -> While:
    return locate(node, While(
        test=visit(node.test), body=visit_list(node.body),
        orelse=visit_list(node.orelse),
    ))

def convert_for(node: ast.For) -> For:
    return locate(node, For(
        target=visit(node.target), iterable=visit(node.iter),
        body=visit_list(node.body), orelse=visit_list(node.orelse), is_async=False,
    ))

def convert_asyncfor(node: ast.AsyncFor) -> For:
    return locate(node, For(
        target=visit(node.target), iterable=visit(node.iter),
        body=visit_list(node.body), orelse=visit_list(node.orelse), is_async=True,
    ))

def _convert_with_items(node) -> list[tuple[Node, Optional[Node]]]:
    return [
        (visit(item.context_expr), visit(item.optional_vars) if item.optional_vars else None)
        for item in node.items
    ]

def convert_with(node: ast.With) -> With:
    return locate(node, With(
        items=_convert_with_items(node), body=visit_list(node.body), is_async=False,
    ))

def convert_asyncwith(node: ast.AsyncWith) -> With:
    return locate(node, With(
        items=_convert_with_items(node), body=visit_list(node.body), is_async=True,
    ))

def _convert_handler(node: ast.ExceptHandler) -> ExceptHandler:
    return locate(node, ExceptHandler(
        type=visit(node.type) if node.type else None,
        name=node.name, body=visit_list(node.body),
    ))

def convert_try(node: ast.Try) -> Try:
    return locate(node, Try(
        body=visit_list(node.body),
        handlers=[_convert_handler(h) for h in node.handlers],
        orelse=visit_list(node.orelse), finalbody=visit_list(node.finalbody),
        is_star=False,
    ))

def convert_trystar(node: ast.TryStar) -> Try:
    return locate(node, Try(
        body=visit_list(node.body),
        handlers=[_convert_handler(h) for h in node.handlers],
        orelse=visit_list(node.orelse), finalbody=visit_list(node.finalbody),
        is_star=True,
    ))


# --- Definitions ---

def convert_functiondef(node: ast.FunctionDef) -> FunctionDef:
    type_params = visit_list(node.type_params) if hasattr(node, "type_params") else []
    return locate(node, FunctionDef(
        name=node.name, params=convert_arguments(node.args),
        body=visit_list(node.body), decorators=visit_list(node.decorator_list),
        returns=visit(node.returns) if node.returns else None,
        is_async=False, type_params=type_params,
    ))

def convert_asyncfunctiondef(node: ast.AsyncFunctionDef) -> FunctionDef:
    type_params = visit_list(node.type_params) if hasattr(node, "type_params") else []
    return locate(node, FunctionDef(
        name=node.name, params=convert_arguments(node.args),
        body=visit_list(node.body), decorators=visit_list(node.decorator_list),
        returns=visit(node.returns) if node.returns else None,
        is_async=True, type_params=type_params,
    ))

def convert_classdef(node: ast.ClassDef) -> ClassDef:
    kwargs = [locate(kw, Keyword(name=kw.arg, value=visit(kw.value))) for kw in node.keywords]
    type_params = visit_list(node.type_params) if hasattr(node, "type_params") else []
    return locate(node, ClassDef(
        name=node.name, bases=visit_list(node.bases), keywords=kwargs,
        body=visit_list(node.body), decorators=visit_list(node.decorator_list),
        type_params=type_params,
    ))

def convert_typealias(node: ast.TypeAlias) -> TypeAlias:
    return locate(node, TypeAlias(
        name=visit(node.name), type_params=visit_list(node.type_params),
        value=visit(node.value),
    ))


# --- Type params ---

def convert_typevar(node: ast.TypeVar) -> TypeVar:
    return locate(node, TypeVar(name=node.name, bound=visit(node.bound) if node.bound else None))

def convert_paramspec(node: ast.ParamSpec) -> ParamSpec:
    return locate(node, ParamSpec(name=node.name))

def convert_typevartuple(node: ast.TypeVarTuple) -> TypeVarTuple:
    return locate(node, TypeVarTuple(name=node.name))


# ── Pattern Matching ─────────────────────────────────────────────────────────

def convert_match(node: ast.Match) -> Match:
    return locate(node, Match(
        subject=visit(node.subject),
        cases=[_convert_match_case(c) for c in node.cases],
    ))

def _convert_match_case(node: ast.match_case) -> MatchCase:
    return MatchCase(
        pattern=visit(node.pattern),
        guard=visit(node.guard) if node.guard else None,
        body=visit_list(node.body),
    )

def convert_matchvalue(node: ast.MatchValue) -> MatchLiteral:
    return locate(node, MatchLiteral(value=visit(node.value), use_is=False))

def convert_matchsingleton(node: ast.MatchSingleton) -> MatchLiteral:
    v = node.value
    if v is None:
        val = NoneLiteral()
    elif isinstance(v, bool):
        val = BoolLiteral(value=v)
    else:
        val = convert_constant(ast.Constant(value=v))
    return locate(node, MatchLiteral(value=val, use_is=True))

def convert_matchsequence(node: ast.MatchSequence) -> MatchSequence:
    return locate(node, MatchSequence(patterns=visit_list(node.patterns)))

def convert_matchmapping(node: ast.MatchMapping) -> MatchMapping:
    return locate(node, MatchMapping(
        keys=visit_list(node.keys), patterns=visit_list(node.patterns), rest=node.rest,
    ))

def convert_matchclass(node: ast.MatchClass) -> MatchClass:
    return locate(node, MatchClass(
        cls=visit(node.cls), patterns=visit_list(node.patterns),
        kwd_attrs=list(node.kwd_attrs), kwd_patterns=visit_list(node.kwd_patterns),
    ))

def convert_matchstar(node: ast.MatchStar) -> MatchStar:
    return locate(node, MatchStar(name=node.name))

def convert_matchas(node: ast.MatchAs) -> MatchAs:
    return locate(node, MatchAs(
        pattern=visit(node.pattern) if node.pattern else None, name=node.name,
    ))

def convert_matchor(node: ast.MatchOr) -> MatchOr:
    return locate(node, MatchOr(patterns=visit_list(node.patterns)))


# ═══════════════════════════════════════════════════════════════════════════════
# VISITORS dispatch table: ast type → converter function
# ═══════════════════════════════════════════════════════════════════════════════

VISITORS: dict[type, Any] = {
    # Modules
    ast.Module: convert_module,
    ast.Interactive: convert_interactive,
    ast.Expression: convert_expression,
    # Literals
    ast.Constant: convert_constant,
    ast.JoinedStr: convert_joined_str,
    ast.FormattedValue: convert_formatted_value,
    # Collections
    ast.List: convert_list,
    ast.Tuple: convert_tuple,
    ast.Set: convert_set,
    ast.Dict: convert_dict,
    # Names / Attributes / Subscripts
    ast.Name: convert_name,
    ast.Attribute: convert_attribute,
    ast.Subscript: convert_subscript,
    ast.Starred: convert_starred,
    ast.Slice: convert_slice,
    # Operators
    ast.BinOp: convert_binop,
    ast.UnaryOp: convert_unaryop,
    ast.BoolOp: convert_boolop,
    ast.Compare: convert_compare,
    ast.AugAssign: convert_augassign,
    # Expressions
    ast.Call: convert_call,
    ast.IfExp: convert_ifexp,
    ast.NamedExpr: convert_namedexpr,
    ast.Lambda: convert_lambda,
    ast.Yield: convert_yield,
    ast.YieldFrom: convert_yieldfrom,
    ast.Await: convert_await,
    # Comprehensions
    ast.ListComp: convert_listcomp,
    ast.SetComp: convert_setcomp,
    ast.DictComp: convert_dictcomp,
    ast.GeneratorExp: convert_generatorexp,
    # Statements
    ast.Expr: convert_expr_stmt,
    ast.Assign: convert_assign,
    ast.AnnAssign: convert_annassign,
    ast.Delete: convert_delete,
    ast.Return: convert_return,
    ast.Pass: convert_pass,
    ast.Break: convert_break,
    ast.Continue: convert_continue,
    ast.Raise: convert_raise,
    ast.Assert: convert_assert,
    ast.Global: convert_global,
    ast.Nonlocal: convert_nonlocal,
    # Imports
    ast.Import: convert_import,
    ast.ImportFrom: convert_importfrom,
    # Compound statements
    ast.If: convert_if,
    ast.While: convert_while,
    ast.For: convert_for,
    ast.AsyncFor: convert_asyncfor,
    ast.With: convert_with,
    ast.AsyncWith: convert_asyncwith,
    ast.Try: convert_try,
    ast.TryStar: convert_trystar,
    # Definitions
    ast.FunctionDef: convert_functiondef,
    ast.AsyncFunctionDef: convert_asyncfunctiondef,
    ast.ClassDef: convert_classdef,
    ast.TypeAlias: convert_typealias,
    # Type params
    ast.TypeVar: convert_typevar,
    ast.ParamSpec: convert_paramspec,
    ast.TypeVarTuple: convert_typevartuple,
    # Match
    ast.Match: convert_match,
    ast.MatchValue: convert_matchvalue,
    ast.MatchSingleton: convert_matchsingleton,
    ast.MatchSequence: convert_matchsequence,
    ast.MatchMapping: convert_matchmapping,
    ast.MatchClass: convert_matchclass,
    ast.MatchStar: convert_matchstar,
    ast.MatchAs: convert_matchas,
    ast.MatchOr: convert_matchor,
}




# ═══════════════════════════════════════════════════════════════════════════════
# Transformer: ast → simple_ast
#
# Each CPython AST type maps to a bare converter function via VISITORS dict.
# visit(node) does a direct hash lookup by type(node).
# ═══════════════════════════════════════════════════════════════════════════════

def visit(node: ast.AST) -> Node:
    """Convert a single CPython AST node. Dispatches by type(node)."""
    converter = VISITORS.get(type(node))
    if converter is None:
        raise NotImplementedError(
            f"No handler for {node.__class__.__name__}: {ast.dump(node)}"
        )
    return converter(node)


def visit_list(nodes: list[ast.AST]) -> list[Node]:
    """Convert a list of CPython AST nodes, flattening any that return lists."""
    result = []
    for n in nodes:
        v = visit(n)
        if isinstance(v, list):
            result.extend(v)
        else:
            result.append(v)
    return result

