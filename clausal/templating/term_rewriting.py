from ast import *
from copy import deepcopy

from .parser import is_template_func
from .compiler import compile_template_func
from .desugar import desugar_surface, dotted_attr_chain, is_dict_attr_access

# Module-level item types for the pipeline-split ModuleAST.
from clausal.pythonic_ast.nodes import (
    BareAtomRefs as BareAtomRefsItem,
    Directive as DirectiveItem,
    EdcgAccDecl,
    EdcgPassDecl,
    EdcgPredDecl,
    ImportFromDirective as ImportFromItem,
    ImportModuleDirective as ImportModuleItem,
    ModuleDeclaration as ModuleDeclItem,
    OverwritesDeclaration as OverwritesDeclItem,
    PrivateDeclaration as PrivateDeclItem,
    Predicate as PredicateItem,
    SpecializeDirective as SpecializeItem,
    ImplicitAtomsDeclaration as ImplicitAtomsItem,
    StrictAtomsDeclaration as StrictAtomsItem,
    TranslationsDirective as TranslationsItem,
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
    Eq: "ArithEq",             # ==  arithmetic equality (CLP(FD), Prolog =:=)
    NotEq: "ArithNeq",        # !=  arithmetic inequality (CLP(FD), Prolog =\=)
    Lt: "Lt",                 # <   arithmetic comparison (evaluates)
    LtE: "LtE",               # <=  arithmetic comparison (evaluates)
    Gt: "Gt",                 # >   arithmetic comparison (evaluates)
    GtE: "GtE",               # >=  arithmetic comparison (evaluates)
    Is: "Unify",              # is  unification (structural, no arithmetic eval)
    IsNot: "DoesNotUnify",    # is not  dif / negation of unification
    In: "in_",                 # in  membership / enumeration
    NotIn: "NotIn",           # not in  non-membership
}


# ─── Arrow (<-) detection helpers ────────────────────────────────────────────

_ARROW_BODY_ERROR = (
    "clause body must be parenthesized or a single call: "
    "write  head <- (body)  or  head <- goal(X)"
)

_MULTI_GOAL_STMT_ERROR = (
    "multiple comma-separated goals at statement level need a rule head and "
    "parentheses: write  head <- (goal1, goal2)  for a rule, or  pred(args),  "
    "(note the trailing comma) for a single fact"
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


def _is_arrow_adjacent(left, usub_node, source_lines=None):
    """True if ``<`` and ``-`` form a contiguous ``<-`` arrow in source.

    Python parses ``head <- body`` as ``head < (-body)``.  To distinguish
    a genuine arrow from ``a < -b`` (less-than with negation) we check
    that the ``<`` character immediately precedes the ``-`` in the source
    text — i.e. no whitespace between them.

    When *source_lines* is provided, the check is exact: the character at
    column ``usub_col - 1`` on the USub's line must be ``<``.

    When *source_lines* is ``None`` (programmatically constructed AST),
    we fall back to a column-gap heuristic (gap ≤ 2).

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
    if end_line != usub_line:
        return False

    if source_lines is not None and usub_col >= 1:
        # Exact check: the character before '-' must be '<'.
        # Python 3.14+ col_offset values are UTF-8 byte offsets, so we
        # must index into the byte representation of the source line.
        line_bytes = source_lines[usub_line - 1].encode("utf-8")  # 1-based lineno
        return usub_col - 1 < len(line_bytes) and line_bytes[usub_col - 1:usub_col] == b"<"

    # Fallback heuristic for programmatic AST (no source available).
    return 1 <= usub_col - end_col <= 2


def _detect_arrow(left, operators, comparators, source_lines=None):
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

    if not _is_arrow_adjacent(left, usub_node, source_lines):
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
    functor call like ``foo(_x)``).
    """
    # Single variable: _x <- body
    if isinstance(head_ast, Name) and _is_logic_var_name(head_ast.id):
        return [head_ast.id]
    # Tuple of variables: (_x, _y) <- body  or  () <- body
    if isinstance(head_ast, Tuple):
        params = []
        for elt in head_ast.elts:
            if isinstance(elt, Name) and _is_logic_var_name(elt.id):
                params.append(elt.id)
            else:
                return None  # non-variable element → not a lambda
        return params
    return None


def _check_hidden_arrow(node, source_lines=None):
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
    if usub_node is not None and _is_arrow_adjacent(inner.left, usub_node, source_lines):
        raise SyntaxError(_ARROW_BODY_ERROR)


# ─── Logic variable name helper ───────────────────────────────────────────────


def _is_logic_var_name(identifier: str) -> bool:
    """Return True if ``identifier`` should be treated as a logic variable.

    Two conventions are recognised:

    * **Leading single underscore** — ``_x``, ``_foo``, ``_head``.
      The underscore must be a single leading one; dunders (``__``) and the
      bare ``_`` wildcard are excluded.
    * **ALL-CAPS** — ``X``, ``FOO``, ``HEAD``, ``TAIL``.
      Every *cased* character must be uppercase and there must be at least one
      cased character (so plain ``_`` and digit-only names are excluded).
      Underscores and digits are allowed inside (e.g. ``N1``, ``MAX_OF``).
    """
    if identifier == "_":
        return False
    if identifier.startswith("__"):
        return False
    if identifier.startswith("_"):
        return True
    # ALL-CAPS: str.isupper() is True iff all cased chars are uppercase AND
    # there is at least one cased character — exactly what we want.
    return identifier.isupper()


# ``P.key`` sugar recognition and expansion live in ``.desugar`` — the single,
# syntax-only implementation the SMT prover shares.  Re-exported under the
# module-private names this file has always used.
_dotted_attr_chain = dotted_attr_chain
_is_dict_attr_access = is_dict_attr_access


# ─── Read-once lowering for dict reads (``P.key`` / ``P[key]``) ──────────────
#
# A dict read means: read ONCE into an implicit variable, then substitute.  For
# a clause body the compiler mints a fresh implicit variable, inserts the read
# as a *goal* at the position of the first occurrence, and substitutes that
# variable at every remaining occurrence in the same scope:
#
#     foo(P) <- ( bar(P.k), baz(P.k, 1) )
#     # means
#     foo(P) <- ( _read_0 is P[k], bar(_read_0), baz(_read_0, 1) )
#
# Inserting a *goal* — rather than caching the value in a compiled-in Python
# local — is what makes this sound under backtracking: in
# ``member(P, [D1, D2]), foo(P.k)`` the read sits after ``member/2``, so redo
# re-executes it against the new binding of ``P``.
#
# The read is scoped to the innermost enclosing control construct and is never
# lifted out of a disjunction arm, a negation, or an if-then-else branch —
# ``( a(P) or b(P.k) )`` must not throw on a missing key when ``a(P)``
# succeeds.  The deliberate consequence is that sharing does not cross an arm
# boundary: a later occurrence outside the construct reads again.
#
# See docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md.


def _flatten_conjunction(goal):
    """Flatten a goal-position tuple into its conjunct goals."""
    if isinstance(goal, Tuple) and isinstance(goal.ctx, Load):
        conjuncts = []
        for element in goal.elts:
            conjuncts.extend(_flatten_conjunction(element))
        return conjuncts
    return [goal]


def _is_plain_term(node) -> bool:
    """True when *node* is a term with no goal-position sub-expression.

    The rule that matters is **no nested ``Call``**.  Every construct that
    takes a goal as an argument — ``findall``, ``forall``, ``catch``, ``once``,
    ``call``, … — spells that goal as a call (or as a control construct, also
    excluded here), so refusing to reach inside a nested call is exactly what
    keeps a read from being hoisted out of a nested goal's scope.  It needs no
    table of meta-predicate names, which would rot.

    Everything else unrecognised is refused too (``++(...)`` Python escapes,
    f-strings, lambdas, comprehensions, ``:=``, slices, …).  A refusal only
    costs sharing: those reads stay inline, exactly as they compile today.
    """
    for child in walk(node):
        if isinstance(child, (Load, Name, Constant, Attribute, Subscript,
                              Tuple, List, Dict, Set, Starred, keyword)):
            continue
        if isinstance(child, BinOp) or isinstance(child, operator):
            continue
        return False
    return True


def _is_lowerable_goal(goal) -> bool:
    """True when reads may be extracted out of *goal* to just before it.

    False means "leave this goal alone" — it is not a shape we lower (a
    control construct, a meta-call, a Python escape) or one of its arguments
    is not a plain term.  Refusing only costs sharing: the reads inside stay
    inline, exactly as they compile today.
    """
    if isinstance(goal, Call):
        if isinstance(goal.func, Name):
            if _is_logic_var_name(goal.func.id):
                return False         # meta-call on a variable goal
        elif not isinstance(goal.func, Attribute) or _is_dict_attr_access(goal.func):
            return False
        parts = list(goal.args) + [kw.value for kw in goal.keywords]
    elif isinstance(goal, Compare):
        parts = [goal.left] + list(goal.comparators)
    else:
        return False
    return all(_is_plain_term(part) for part in parts)


def _dict_read_key_tag(key_node):
    """Sharing identity for a subscript key, or ``None`` if not shareable.

    A ``Name`` key (an atom, or a logic variable naming the key) and a literal
    ``Constant`` key are shareable; a computed key is left inline.
    """
    if isinstance(key_node, Name):
        return ("name", key_node.id)
    if isinstance(key_node, Constant):
        return ("const", type(key_node.value).__name__, key_node.value)
    return None


class _DictReadExtractor(NodeTransformer):
    """Replace dict reads in a term by implicit variables, collecting the reads.

    Children are rewritten first, so chains fold left to right: ``P.a.b``
    mints ``_read_0 is P[a]`` and then ``_read_1 is _read_0[b]``.  The minted
    names are logic variables (leading underscore), so a minted base is itself
    recognised as a readable base.
    """

    def __init__(self, mint, shared, reads):
        self._mint = mint
        self._shared = shared      # (base name, key tag) -> implicit var name
        self._reads = reads        # read goals to emit before the using goal

    def _read(self, base_name, key_node, source):
        tag = _dict_read_key_tag(key_node)
        if tag is None:
            return None
        cache_key = (base_name, tag)
        existing = self._shared.get(cache_key)
        if existing is not None:
            return existing
        var_name = self._mint()
        self._reads.append(
            replace(
                Compare(
                    left=replace(Name(id=var_name, ctx=load), source),
                    ops=[Is()],
                    comparators=[
                        replace(
                            Subscript(
                                value=replace(Name(id=base_name, ctx=load),
                                              source),
                                slice=key_node,
                                ctx=load,
                            ),
                            source,
                        )
                    ],
                ),
                source,
            )
        )
        self._shared[cache_key] = var_name
        return var_name

    # There is no ``visit_Attribute``: ``_lower_dict_reads`` runs the shared
    # ``desugar_surface`` pass first, so ``P.k`` has already become ``P[k]``
    # by the time this extractor sees the body.  One spelling, one rule.

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if not (isinstance(node.value, Name)
                and _is_logic_var_name(node.value.id)):
            return node
        var_name = self._read(node.value.id, node.slice, node)
        if var_name is None:
            return node
        return replace(Name(id=var_name, ctx=load), node)


def _explicit_read_binding(goal):
    """``(var name, sharing key)`` if *goal* is ``VAR is BASE[key]``, else None.

    The ``VAR is BASE.key`` spelling arrives here already expanded — the
    caller runs the shared ``desugar_surface`` pass first.
    """
    if not (isinstance(goal, Compare) and len(goal.ops) == 1
            and isinstance(goal.ops[0], Is)
            and isinstance(goal.left, Name)
            and _is_logic_var_name(goal.left.id)):
        return None
    rhs = goal.comparators[0]
    if isinstance(rhs, Subscript):
        base, key_node = rhs.value, rhs.slice
    else:
        return None
    if not (isinstance(base, Name) and _is_logic_var_name(base.id)):
        return None
    tag = _dict_read_key_tag(key_node)
    if tag is None:
        return None
    return goal.left.id, (base.id, tag)


def _lower_dict_reads_in_scope(goal, mint):
    """Lower every dict read in one control-construct scope.

    Returns a goal AST for the scope.  Reads minted here do not escape it.
    """
    lowered = []
    shared = {}
    for conjunct in _flatten_conjunction(goal):
        lowered.extend(_lower_dict_reads_in_goal(conjunct, mint, shared))
    if len(lowered) == 1:
        return lowered[0]
    return replace(Tuple(elts=lowered, ctx=load), goal)


def _lower_dict_reads_in_goal(goal, mint, shared):
    """Lower one goal; returns the read goals plus the rewritten goal."""
    # Control constructs: each arm is its own scope, so a read is never lifted
    # out of it.  `( a(P) or b(P.k) )` must still succeed via `a(P)` when the
    # key is missing.
    if isinstance(goal, BoolOp):
        return [replace(
            BoolOp(op=goal.op,
                   values=[_lower_dict_reads_in_scope(value, mint)
                           for value in goal.values]),
            goal,
        )]
    if isinstance(goal, UnaryOp) and isinstance(goal.op, Not):
        return [replace(
            UnaryOp(op=goal.op,
                    operand=_lower_dict_reads_in_scope(goal.operand, mint)),
            goal,
        )]
    if (isinstance(goal, Call) and isinstance(goal.func, Name)
            and goal.func.id == "If" and len(goal.args) == 3
            and not goal.keywords):
        return [replace(
            Call(func=goal.func,
                 args=[_lower_dict_reads_in_scope(arm, mint)
                       for arm in goal.args],
                 keywords=[]),
            goal,
        )]

    # ``X is P[k]`` / ``X is P.k`` already *is* a read into a named variable.
    # Leave it alone and register X as the implicit variable for that read, so
    # later occurrences in the scope reuse it.  This keeps the lowering
    # idempotent — the read goals it emits have exactly this shape, so
    # re-running the pass over a rendered clause (the reifier round-trip) is a
    # no-op — and leaves the common hand-written idiom untouched.
    binding = _explicit_read_binding(goal)
    if binding is not None:
        var_name, cache_key = binding
        if cache_key not in shared:
            shared[cache_key] = var_name
            return [goal]

    if not _is_lowerable_goal(goal):
        return [goal]
    reads = []
    extractor = _DictReadExtractor(mint, shared, reads)
    if isinstance(goal, Call):
        goal.args = [extractor.visit(arg) for arg in goal.args]
        for kw in goal.keywords:
            kw.value = extractor.visit(kw.value)
    else:                                   # Compare
        goal.left = extractor.visit(goal.left)
        goal.comparators = [extractor.visit(comparator)
                            for comparator in goal.comparators]
    return reads + [goal]


def _lower_dict_reads(head_ast, body_ast):
    """Read-once lowering over a whole clause body.  Returns the new body.

    The body is copied first: the pass rewrites in place, and the caller's AST
    is shared with the module tree.  The copy is then run through the shared
    surface-desugar pass, so this pass only ever sees the ``P[key]`` spelling
    — ``P.key`` is expanded once, in one place, by ``desugar_surface``.

    Note that hoisting itself is NOT shared with the SMT prover: minting
    implicit variables and reordering goals is an evaluation strategy, not a
    spelling.  See ``clausal/templating/desugar.py``.
    """
    body_ast = desugar_surface(deepcopy(body_ast))
    taken = {node.id for node in walk(body_ast) if isinstance(node, Name)}
    taken.update(node.id for node in walk(head_ast) if isinstance(node, Name))
    counter = [0]

    def mint():
        while True:
            name = f"_read_{counter[0]}"
            counter[0] += 1
            if name not in taken:
                taken.add(name)
                return name

    return _lower_dict_reads_in_scope(body_ast, mint)


def _is_unit_expr(node) -> bool:
    """True for AST nodes that form a valid unit-type expression.

    Accepts plain Names (e.g. ``Metre``) and compound expressions built from
    ``*``, ``/``, ``**`` with Names and numeric Constants as leaves — e.g.
    ``Metre**2``, ``Metre/Second``, ``Kilogram*Metre/Second**2``.
    """
    if isinstance(node, Name):
        return True
    if isinstance(node, Attribute):
        return _is_unit_expr(node.value)
    if isinstance(node, Constant) and isinstance(node.value, (int, float)):
        return True
    if isinstance(node, UnaryOp) and isinstance(node.op, USub):
        return isinstance(node.operand, Constant)
    if isinstance(node, BinOp) and isinstance(node.op, (Pow, Mult, Div)):
        return _is_unit_expr(node.left) and _is_unit_expr(node.right)
    return False


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


class ClausalLintWarning(UserWarning):
    """Load-time lint diagnostic for a likely-footgun Clausal construct."""


def _node_has_var_or_wildcard(node) -> bool:
    """True if *node* contains a logic variable or a bare ``_`` wildcard."""
    found = False

    class _V(NodeVisitor):
        def visit_Name(self, name):
            nonlocal found
            if name.id == "_" or _is_logic_var_name(name.id):
                found = True

    _V().visit(node)
    return found


def _isnot_rhs_is_partial_pattern(rhs) -> bool:
    """True when the RHS of ``X is not RHS`` is a *structural* term (compound,
    list, tuple, set, or dict) that contains an unbound variable or ``_``.

    ``is not`` is ``dif/2`` (disequality). Against a partial term it compares with
    a *fresh* variable, so the guard succeeds even for terms that match the shape
    — almost always a mistake (the author meant ``not (X is P)``). Scalars and
    fully-ground RHS (the correct, common uses — ``X is not 0``, ``K is not "k"``,
    ``KEYS is not []``) return False.
    """
    if isinstance(rhs, Call):
        # A functor application like tag(_); exclude a logic variable applied as
        # a goal closure (e.g. Goal(...)) — that is not a data pattern.
        if isinstance(rhs.func, Name) and _is_logic_var_name(rhs.func.id):
            return False
    elif not isinstance(rhs, (List, Tuple, Set, Dict)):
        return False
    return _node_has_var_or_wildcard(rhs)


def _warn_isnot_partial_pattern(rhs, node, source_lines) -> None:
    import warnings  # noqa: PLC0415
    lineno = getattr(node, "lineno", None)
    snippet = ""
    if source_lines and lineno and 1 <= lineno <= len(source_lines):
        snippet = " — " + source_lines[lineno - 1].strip()
    where = f" (line {lineno})" if lineno else ""
    warnings.warn(
        f"`is not` against a pattern containing an unbound variable{where}"
        f"{snippet}: this is dif/2 against a fresh variable, so it ALWAYS "
        "succeeds (even for terms matching the shape). Use `not (X is P)` to "
        "test non-matching, or `dif` against a fully-ground term for disequality.",
        ClausalLintWarning,
        stacklevel=2,
    )


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
            keywords=[make_keyword_node("_position", pos_ast(node), node)],
        ),
        node,
    )


# ─── Term Transformer ─────────────────────────────────────────────────────────


class TermTransformer(NodeTransformer):
    """Transform a Python expression AST into Python AST that constructs simple_ast nodes."""

    def __init__(transformer, atoms=frozenset(), import_remap=None,
                 source_lines=None, bare_atom_refs=None):
        transformer.seen_vars = set()
        transformer.atoms = atoms
        transformer._import_remap = import_remap or {}
        transformer._source_lines = source_lines
        # Shared sink for bare-atom collection.  EmbedTransformer passes the
        # same set into every per-clause TermTransformer so that the final
        # union is naturally available without a post-pass merge.  Phase 2 of
        # GLOBAL_ATOMS_DEFAULT.md (auto-mint hook) consumes this.
        transformer._bare_atom_refs = (
            bare_atom_refs if bare_atom_refs is not None else set()
        )
        # When True, ``visit_Name`` will not add the visited identifier to
        # ``_bare_atom_refs``.  ``visit_Call`` flips this on while visiting
        # ``call.func`` so that predicate functor names (which are calls, not
        # atoms) are excluded from the global-atom auto-mint set.
        transformer._suppress_bare_atom_collection = False

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
        _check_hidden_arrow(bool_operation, transformer._source_lines)
        # Python's BoolOp has N values; simple_ast uses nested binary And/Or
        class_name = BOOLOP_CLS[type(bool_operation.op)]
        value_nodes = [
            transformer.visit(value_node) for value_node in bool_operation.values
        ]
        result = value_nodes[0]
        for value_node in value_nodes[1:]:
            result = node_ast(class_name, bool_operation, left=result, right=value_node)
        return result

    def _visit_call_func(transformer, func_expr):
        """Visit a Call's func position with bare-atom collection suppressed.

        Predicate functor names (e.g. ``Edge`` in ``Edge(X, Y)``) emerge from
        ``visit_Name`` as ``LoadName`` nodes — the same shape as bare atom
        references — but they should NOT auto-mint as 0-arity global atoms.
        They resolve via the runtime predicate-resolution path instead, so
        ``visit_Name`` skips its bare-atom-set add when this guard is active.

        Also rejects the method-call form ``P.foo(A)``.  ``P.foo`` on a logic
        variable is dict attribute-access sugar — it *reads a value*, which is
        not callable — so the shape is reserved rather than silently compiled
        into a call on a dict entry.
        """
        if _is_dict_attr_access(func_expr):
            base_name, key_names = _dotted_attr_chain(func_expr)
            dotted = ".".join([base_name.id] + key_names)
            raise SyntaxError(
                f"Method-call form '{dotted}(...)' is not supported "
                f"(line {func_expr.lineno}): '.' on the logic variable "
                f"'{base_name.id}' is dict attribute access, which reads a "
                f"value and cannot be called.  Read the value into a variable "
                f"first, or use a qualified predicate name (mod.pred(...))."
            )
        prev = transformer._suppress_bare_atom_collection
        transformer._suppress_bare_atom_collection = True
        try:
            return transformer.visit(func_expr)
        finally:
            transformer._suppress_bare_atom_collection = prev

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
            func_node = transformer._visit_call_func(
                replace(Name(id=call.func.value, ctx=load), call.func)
            )
        # HasUnits(X, compound_unit) — auto-wrap compound unit expr in PyThunk
        # so it evaluates as Python rather than being compiled as a Clausal term.
        elif (
            isinstance(call.func, Name)
            and call.func.id in ("has_units", "HasUnits")
            and len(call.args) == 2
            and _is_unit_expr(call.args[1])
            and not isinstance(call.args[1], Name)
            and not call.keywords
        ):
            first_arg = visit(call.args[0])
            unit_thunk = _build_py_thunk_ast(transformer, call, call.args[1], [])
            func_node = transformer._visit_call_func(call.func)
            return node_ast(
                "Call", call,
                func=func_node,
                args=list_ast([first_arg, unit_thunk], call),
                kwargs=list_ast([], call),
            )
        elif (
            isinstance(call.func, Constant)
            and isinstance(call.func.value, (int, float))
            and len(call.args) == 0
            and not call.keywords
        ):
            # n() — dimensionless sugar: 42() → ++(Quantity(42, {}))
            inner = Call(
                func=replace(Name(id="Quantity", ctx=load), call),
                args=[call.func, replace(Dict(keys=[], values=[]), call)],
                keywords=[],
            )
            return _build_py_thunk_ast(transformer, call, inner, [])
        elif (
            not (isinstance(call.func, Name) and not _is_logic_var_name(call.func.id))
            and not isinstance(call.func, Attribute)
            and len(call.args) == 1
            and _is_unit_expr(call.args[0])
            and not call.keywords
        ):
            # <expr>(Unit) — unit annotation sugar.
            # Any expression that is not a predicate/functor name or attribute
            # access can be annotated with a unit: 5(Metre), X(Newton),
            # [1,2,3](Metre), (A + B)(Metre/Second), etc.
            # Transforms to: ++(Quantity(<expr>, Unit))
            raw_unit = call.args[0]
            var_names = _collect_logic_var_names(call.func)
            inner = Call(
                func=replace(Name(id="Quantity", ctx=load), call),
                args=[call.func, raw_unit],
                keywords=[],
            )
            return _build_py_thunk_ast(transformer, call, inner, var_names)
        else:
            func_node = transformer._visit_call_func(call.func)
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
        arrow = _detect_arrow(left, operators, comparators, transformer._source_lines)
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
            # Read-once lowering: dict reads (``P.key`` / ``P[key]``) become an
            # explicit read goal at their first-occurrence position, scoped to
            # the innermost control construct.  Head first — its variables are
            # in scope for the implicit-variable name choice.
            return node_ast(
                "Predicate",
                compare,
                head=transformer.visit(head_ast),
                body=transformer.visit(_lower_dict_reads(head_ast, body_ast)),
            )


        if len(operators) == 1:
            if isinstance(operators[0], IsNot) and \
                    _isnot_rhs_is_partial_pattern(comparators[0]):
                _warn_isnot_partial_pattern(
                    comparators[0], compare, transformer._source_lines)
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

    def _visit_dict_key(transformer, key):
        """Transform a dict-literal key.

        A bare atom in key position (unquoted lowercase identifier, e.g.
        ``{filing_status: V}``) must resolve to its **interned atom value**, not
        to the ``LoadName`` reflection node ``visit_Name`` emits for atoms in
        value position — a ``LoadName`` instance is unhashable and cannot key a
        ``DictTerm``.  Emit ``$intern_atom("filing_status")`` so the key is the
        process-wide interned atom at construction time (dict literals are built
        eagerly during exec, before the bare-atom mint pass); ``setdefault`` in
        that helper yields the same object a value-position use of the atom
        resolves to, so ``{foo: 1}[foo]`` matches.  Atom keys are distinct from
        string keys (atoms do not unify with strings), matching Python dict-key
        identity.  Also register the name so a value-position use mints
        consistently.

        Everything else — string/int ``Constant`` keys, logic-variable keys
        (left to their existing behaviour), and computed expressions — is
        transformed as before.
        """
        if (
            isinstance(key, Name)
            and key.id != "_"
            and not _is_logic_var_name(key.id)
        ):
            if not transformer._suppress_bare_atom_collection:
                transformer._bare_atom_refs.add(key.id)
            return replace(
                Call(
                    func=replace(Name(id="$intern_atom", ctx=load), key),
                    args=[replace(Constant(value=key.id), key)],
                    keywords=[],
                ),
                key,
            )
        return transformer.visit(key)

    def visit_Dict(transformer, dict_expr):
        # If any key is None, this is a **splat dict — fall back to DictLiteral
        # (full splat/merge support is Phase 3).
        has_splat = any(k is None for k in dict_expr.keys)
        if has_splat:
            keys = list_ast(
                [
                    (
                        transformer._visit_dict_key(key)
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
        key_asts = [transformer._visit_dict_key(k) for k in dict_expr.keys]
        val_asts = [transformer.visit(v) for v in dict_expr.values]
        dict_arg = replace(
            Dict(keys=key_asts, values=val_asts),
            dict_expr,
        )
        return replace(
            Call(
                func=replace(Name(id="DictTerm", ctx=load), dict_expr),
                args=[dict_arg],
                keywords=[make_keyword_node("_position", pos_ast(dict_expr), dict_expr)],
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
        # A10-F006: thread source_lines and atoms through (as
        # _make_term_transformer does). Without source_lines, arrow detection
        # inside the lambda body falls back to the column-gap heuristic and
        # misparses a legal Lt guard like ``X_ < -3`` as a nested arrow lambda.
        lambda_transformer = TermTransformer(
            atoms=transformer.atoms,
            import_remap=transformer._import_remap,
            source_lines=transformer._source_lines,
            bare_atom_refs=transformer._bare_atom_refs,
        )
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
        # Logic variable: leading single underscore OR all-caps name.
        # Examples (underscore): _x, _foo, _head — all are logic variables.
        # Examples (all-caps):   X, FOO, HEAD, TAIL, N1, MAX_OF.
        # Excluded: __, __init__ (dunder-style), MixedCase, lowercase.
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
        # Fallthrough — bare reference that may need auto-minting as a global
        # atom (Phase 2 of GLOBAL_ATOMS_DEFAULT.md).  Record the name; the
        # auto-mint pass in ``compiler_v2._process_bare_atom_refs`` decides at
        # compile time whether the name is already bound (skip) or needs to
        # be minted into the process-wide ``predicate_builtins`` dict.
        # The ``_suppress_bare_atom_collection`` flag is set by ``visit_Call``
        # when visiting ``call.func`` so that predicate functor names are not
        # auto-minted as 0-arity atoms — those resolve via the runtime
        # predicate-resolution path (builtins, module globals, dispatch
        # adapter) rather than the global atom dict.
        if not transformer._suppress_bare_atom_collection:
            transformer._bare_atom_refs.add(identifier)
        return node_ast(
            "LoadName", name, name=replace(Constant(value=identifier), name)
        )

    def visit_Attribute(transformer, attr_node):
        """Compile dotted expressions — two distinct constructs share the syntax.

        * **Logic-variable base** (``P.key``): dict attribute-access sugar.  It
          lowers to the subscript read ``P[key]`` (a ``LoadSubscript`` node), so
          ``.`` is *not* a term — there is no ``./2`` functor, nothing a program
          can inspect or unify against.  Key resolution goes through the same
          path a bare ``Name`` takes, so ``P.status`` loads iff ``P[status]``
          does (including the strict-atoms declaration requirement).  Chains
          nest: ``P.a.b`` → ``P[a][b]``.  A logic-variable attribute is a
          *variable key*: ``P.KEY`` → ``P[KEY]``.
          See docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md.
        * **Non-variable base** (``mod.Pred``, ``currency.euro``): a qualified
          name, compiled to a ``LoadAttr`` simple_ast node.  Only dotted chains
          of non-variable names are supported; a logic variable anywhere in such
          a chain is a ``SyntaxError``.

        The method-call form ``P.foo(A)`` is rejected in ``_visit_call_func``.
        """
        if _is_dict_attr_access(attr_node):
            # Expand the sugar with the SHARED, syntax-only pass (the SMT
            # prover runs the very same function on its own parse), then
            # compile the resulting ``P[key]`` through ``visit_Subscript`` —
            # so the key is routed through ``visit_Name`` exactly as a
            # hand-written subscript's index is: declared atom, imported
            # name, logic variable, or bare-atom reference registered for
            # the mint / strict-atoms passes.  Never intern the attribute
            # name directly.
            return transformer.visit(desugar_surface(deepcopy(attr_node)))
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
        # ':=' (arithmetic evaluate-and-bind) was removed.  Its eager meaning
        # lives in the reserved builtin ``eval_(EXPR, X)`` — same Evaluate →
        # ArithEval backend — while ``==`` posts relational constraints and
        # ``is`` unifies (chain ``A is B is C`` to name a term inline).  This
        # raises rather than warns because ':=' used to kind-of-work, which
        # taught authors (and LLMs) the wrong operator.
        lineno = getattr(named_expr, "lineno", None)
        snippet = ""
        if transformer._source_lines and lineno \
                and 1 <= lineno <= len(transformer._source_lines):
            snippet = " — " + transformer._source_lines[lineno - 1].strip()
        where = f" (line {lineno})" if lineno else ""
        raise SyntaxError(
            f"`:=` is not a Clausal operator{where}{snippet}. Use "
            "`eval_(EXPR, X)` for eager arithmetic (the old `:=` behaviour), "
            "`==` for relational arithmetic constraints, `is` for unification "
            "(chain `A is B is C` to name a term inline), or `is ++(...)` "
            "for an arbitrary Python expression."
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

        # -n(Unit) / -n(): fold the USub into the numeric callee so the
        # unit-sugar transform sees (-n)(Unit) and yields ++(Quantity(-n, Unit))
        # rather than Negate(++thunk), which term unification never evaluates —
        # so -3(Second) works in `is`/argument position, not only after `:=`
        # (F047).
        if (
            isinstance(unary_op.op, USub)
            and isinstance(unary_op.operand, Call)
            and isinstance(unary_op.operand.func, Constant)
            and isinstance(unary_op.operand.func.value, (int, float))
        ):
            call = unary_op.operand
            negated_func = replace(Constant(value=-call.func.value), call.func)
            folded = replace(
                Call(func=negated_func, args=call.args, keywords=call.keywords),
                call,
            )
            return transformer.visit(folded)

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
    "csv_mod": "py.csv",
    "date_time": "py.datetime",
    "files_mod": "py.files",
    "hash_mod": "py.hash",
    "hmac_mod": "py.hmac",
    "http_mod": "py.http",
    "json_mod": "py.json",
    "log": "py.logging",
    "os_mod": "py.os",
    "pbkdf2_mod": "py.pbkdf2",
    "process_mod": "py.process",
    "random_mod": "py.random",
    "regex": "py.re",
    "sqlite": "py.sqlite",
    "tcp_mod": "py.tcp",
    "url_mod": "py.url",
    "uuid": "py.uuid",
    "uuid_mod": "py.uuid",
    "yaml": "py.yaml",
    "spacy": "py.spacy",
    "sympy": "py.sympy",
    "scipy_cluster": "py.scipy_cluster",
    "scipy_constants": "py.scipy_constants",
    "scipy_differentiate": "py.scipy_differentiate",
    "scipy_fft": "py.scipy_fft",
    "scipy_integrate": "py.scipy_integrate",
    "scipy_interpolate": "py.scipy_interpolate",
    "scipy_linalg": "py.scipy_linalg",
    "scipy_ndimage": "py.scipy_ndimage",
    "scipy_optimize": "py.scipy_optimize",
    "scipy_signal": "py.scipy_signal",
    "scipy_sparse": "py.scipy_sparse",
    "scipy_spatial": "py.scipy_spatial",
    "scipy_special": "py.scipy_special",
    "scipy_stats": "py.scipy_stats",
    "torch": "py.torch",
    "torch_nn": "py.torch_nn",
    "torch_data": "py.torch_data",
    "torch_functional": "py.torch_functional",
    "torch_distributions": "py.torch_distributions",
    "jax": "py.jax",
    "jax_random": "py.jax_random",
    "jax_nn": "py.jax_nn",
    "jax_transforms": "py.jax_transforms",
    "jax_scipy": "py.jax_scipy",
    "jax_sharding": "py.jax_sharding",
    "jax_tree": "py.jax_tree",
    "jax_optax": "py.jax_optax",
    "jax_equinox": "py.jax_equinox",
    "jax_flax": "py.jax_flax",
    "opencv": "py.opencv",
    "opencv_calib3d": "py.opencv_calib3d",
    "opencv_color": "py.opencv_color",
    "opencv_contours": "py.opencv_contours",
    "opencv_draw": "py.opencv_draw",
    "opencv_features": "py.opencv_features",
    "opencv_imgproc": "py.opencv_imgproc",
    "opencv_objdetect": "py.opencv_objdetect",
    "opencv_video": "py.opencv_video",
    "sklearn": "py.sklearn",
    # Clausal-domain modules (not third-party wrappers — no py/ subdirectory)
    "currency": "currency",
    "graphs": "graphs",
    "imperial": "imperial",
    "prolog": "prolog",
    "provenance": "provenance",
    "reflection": "reflection",
    "units": "units",
}

_CURRENCY_JURISDICTIONS: frozenset | None = None


def _currency_jurisdictions() -> frozenset:
    """Lazily load the generated currency jurisdiction names (cached).

    Imported on first use (compile time), never at module load, so the core
    import resolver carries no startup dependency on the currency vocabulary.
    """
    global _CURRENCY_JURISDICTIONS
    if _CURRENCY_JURISDICTIONS is None:
        from clausal.modules.countries._data import JURISDICTIONS
        _CURRENCY_JURISDICTIONS = frozenset(JURISDICTIONS)
    return _CURRENCY_JURISDICTIONS


def _resolve_import_path(module_path: str) -> str:
    """Rewrite aliased import paths to avoid stdlib collisions.

    Names in ``_IMPORT_ALIASES`` (and any currency jurisdiction, e.g.
    ``thailand`` -> ``countries.thailand``) are rewritten to their qualified
    ``clausal.modules.*`` form.  All other paths are returned unchanged.
    """
    mapped = _IMPORT_ALIASES.get(module_path)
    if mapped is None and module_path in _currency_jurisdictions():
        mapped = f"countries.{module_path}"
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
    """Generate a guarded block that defines a Predicate class.

    Generated code (example for ``fib`` with fields ``n``, ``f``):

        try:
            fib
            if isinstance(fib, PredicateMeta) and getattr(
                fib, '_fields', None) != ('n', 'f'):
                raise NameError
        except NameError:
            class fib(metaclass=PredicateMeta):
                _fields = ('n', 'f')

    ``PredicateMeta`` handles ``__init__``, ``__eq__``, ``__repr__``,
    ``__match_args__``, ``__slots__``, and partial-term creation (missing
    fields → fresh ``Var()``).  No ``@dataclass`` and no singleton.
    ``fib`` stays as the class in module globals.

    The arity-aware re-raise of ``NameError`` is needed because, under the
    global-atoms-default rule (Phase 2 of GLOBAL_ATOMS_DEFAULT.md), any
    earlier file in the process may have auto-minted a 0-arity
    ``PredicateMeta`` for the same name into ``predicate_builtins``.
    Without the arity check, that 0-arity class would silently shadow this
    file's intended N-arity predicate.

    The guard is deliberately narrowed to ``isinstance(.., PredicateMeta)``:
    a non-``PredicateMeta`` binding of the same name (e.g. a user-defined
    ``def Foo(...)`` in the .clausal file) is left alone and the predicate
    block is skipped.  Clobbering a non-``PredicateMeta`` value would
    silently destroy user code; failing loudly later (when the clause body
    tries to use ``Foo`` as a predicate) preserves the pre-Phase-2 behavior
    for that edge case.
    """
    fields_tuple = repr(tuple(field_names))
    lines = [
        "try:",
        f"    {functor_name}",
        f"    if isinstance({functor_name}, PredicateMeta) and getattr(",
        f"            {functor_name}, '_fields', None) != {fields_tuple}:",
        "        raise NameError",
        "except NameError:",
        f"    class {functor_name}(metaclass=PredicateMeta):",
        f"        _fields = {fields_tuple}",
    ]
    tree = parse("\n".join(lines))
    block = tree.body[0]
    # Position the WHOLE block, not just the try: the nodes come from parsing a
    # fresh snippet, so without this the inner ``class`` statement keeps the
    # snippet's own line 7 and any traceback through it (notably the
    # field-name mismatch diagnostic's "registered by:") points at a line that
    # has nothing to do with the declaration.
    for node in walk(block):
        copy_location(node, source)
    return block


def _make_define_stmt(predicate_ast, expr_stmt):
    """Wrap a Predicate node in a ``$define_predicate(pred, $module)`` stmt."""
    return replace(
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

    Logic-variable Name nodes (leading-underscore or ALL-CAPS) use their
    lowercased id as the field name.  Other args get ``arg_<i>``.  Duplicate
    names are disambiguated with a numeric suffix (e.g. ``b``, ``b_1``) so
    that repeated logic variables produce distinct dataclass fields.
    """
    names: list[str] = []
    counts: dict[str, int] = {}
    for i, arg in enumerate(pos_args):
        if isinstance(arg, Name) and _is_logic_var_name(arg.id):
            base = arg.id.lstrip("_").lower() or f"arg_{i}"
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


def _dcg_set_goals(node, source):
    """Return the embedded goal(s) of a ``{...}`` DCG body element (a Set node).

    A single-element set ``{g}`` yields ``g``; a multi-element set ``{g1, g2}``
    yields a conjunction ``And(g1, g2, ...)`` (Prolog's ``{A, B}``). Python's AST
    preserves the source order of set-display elements, so ordering is
    deterministic (the set is never materialised). Empty ``{}`` is a Dict, never
    a Set, so it never reaches here.
    """
    if len(node.elts) == 1:
        return node.elts[0]
    return replace(BoolOp(op=And(), values=list(node.elts)), source)


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

        case Constant(value=value) if isinstance(value, (str, bytes)):
            # String / bytes terminal: ``>> ("hi")`` or ``>> (b"hi")``.
            # Standard Prolog treats a string constant as a terminal sequence;
            # under the strings-as-lists / bytes-as-lists contracts this is the
            # same as the list form. Route through the ``sequence//1`` builtin
            # (sequence(Str, s_in, s_out)), which already destructures str/bytes
            # input natively and builds a typed residue in generation mode —
            # so a str terminal matches both str and char-list callers.
            call = Call(
                func=Name(id="sequence", ctx=load),
                args=[
                    Constant(value=value),
                    Name(id=s_in, ctx=load),
                    Name(id=s_out, ctx=load),
                ],
                keywords=[],
            )
            return replace(call, source), counter

        case Set(elts=[goal]):
            # Inline goal {goal}: no state consumed.
            return goal, counter

        case Set(elts=goals) if len(goals) >= 2:
            # Multi-goal inline block {g1, g2, ...}: a conjunction of embedded
            # goals, matching Prolog's ``{A, B}``. Python's AST preserves the
            # source order of set-display elements, so the order is deterministic
            # here (the set is never materialised). No state is consumed.
            return replace(BoolOp(op=And(), values=list(goals)), source), counter

        case Dict(keys=[], values=[]):
            # Empty ``{}`` parses as an empty dict display, not a set.
            raise SyntaxError("empty {} block in DCG body")

        case Name(id=name) if _is_logic_var_name(name):
            # Variable non-terminal (call//1): a bare logic variable as a body
            # is the standard meta-nonterminal — the grammar to run is bound at
            # call time (e.g. ``run(_g) >> (_g)``). Lowering it as a direct call
            # ``_g(s_in, s_out)`` produces a Call on a Var, which the goal
            # compiler rejects. Route through phrase/3 instead, which dispatches
            # on the bound nonterminal (class or instance).
            call = Call(
                func=Name(id="phrase", ctx=load),
                args=[
                    Name(id=name, ctx=load),
                    Name(id=s_in, ctx=load),
                    Name(id=s_out, ctx=load),
                ],
                keywords=[],
            )
            return replace(call, source), counter

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

    raise SyntaxError(
        f"Unsupported DCG body element: {dump(node)}. To embed a goal in a DCG "
        "body, wrap it in braces: {...} (e.g. {_d > 0})."
    )


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
                parts.append(_dcg_set_goals(elem, source))
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
            rewritten_parts.append(_dcg_set_goals(elem, source))
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

        case Set(elts=goals) if len(goals) >= 2:
            # Multi-goal inline block {g1, g2, ...}: a conjunction of embedded
            # goals (Prolog's ``{A, B}``). Source order preserved by Python's
            # AST; no accumulator threading.
            result = replace(BoolOp(op=And(), values=list(goals)), source)
            return result, acc_states, counter

        case Dict(keys=[], values=[]):
            # Empty ``{}`` parses as an empty dict display, not a set.
            raise SyntaxError("empty {} block in EDCG body")

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
                # A10-F003: mint a fresh mid var (like _rewrite_edcg_subcall
                # and the terminal-list case) — consuming straight to out_var
                # and setting the state to (out_var, out_var) collapsed every
                # following sequence element to ``out = out``.
                mid = f"_edcg_dcg_{counter}_"
                counter += 1
                call_node = Call(
                    func=Name(id=name, ctx=load),
                    args=[Name(id=in_var, ctx=load), Name(id=mid, ctx=load)],
                    keywords=[],
                )
                new_acc_states = dict(acc_states)
                new_acc_states["dcg"] = (mid, out_var)
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
                # A10-F003: mint a fresh mid var (see the Name branch above).
                mid = f"_edcg_dcg_{counter}_"
                counter += 1
                new_args = list(args) + [
                    Name(id=in_var, ctx=load), Name(id=mid, ctx=load),
                ]
                call_node = Call(func=Name(id=name, ctx=load),
                                args=new_args, keywords=list(kwargs))
                new_acc_states = dict(acc_states)
                new_acc_states["dcg"] = (mid, out_var)
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

    raise SyntaxError(
        f"Unsupported EDCG body element: {dump(node)}. To embed a goal in an "
        "EDCG body, wrap it in braces: {...} (e.g. {_d > 0})."
    )


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
            # Inline goal(s): no threading. Single ``{g}`` or multi-goal
            # ``{g1, g2}`` conjunction.
            rewritten_parts.append(_dcg_set_goals(elem, source))
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

    def __init__(transformer, source_lines=None, implicit_atoms_default=False,
                 filename=None):
        transformer._scope_depth = 0
        # Source file being rewritten, used only to attribute compile-time
        # errors.  A load failure surfaces through the *importing* file, so a
        # message that does not name its own file reads as an error in every
        # test that imports the package — the same trap the -module directive
        # error hit.
        transformer._filename = filename
        transformer._seen_functors: dict[str, list[str]] = {}
        # Functors whose _seen_functors entry was minted by a -dynamic
        # directive with PLACEHOLDER arg_i field names (A12-F005). The first
        # real clause for such a functor unseats the placeholder so its
        # derived head-var names win — see _unseat_directive_minted.
        transformer._directive_minted_functors: set[str] = set()
        # functor name → (lineno, human description) of whatever first fixed
        # its signature in this file, so a later clause head that disagrees
        # can name the declaration it disagrees with.
        transformer._functor_decl_site: dict[str, tuple[int, str]] = {}
        transformer._atoms: set[str] = set()
        transformer._import_remap: dict[str, str] = {}
        # Local names bound by an -import_from seen SO FAR in this file. A
        # clause head for one of these binds by position rather than by field
        # name — see _emit_head_positionally.
        transformer._imported_functors: set[str] = set()
        transformer._module_items: list = []
        transformer._source_lines = source_lines
        # When True (set by the REPL/IPython transform site), the file
        # defaults to loose auto-mint: visit_Module seeds an
        # ImplicitAtomsDeclaration unless the cell states its own mode.
        transformer._implicit_atoms_default = implicit_atoms_default
        # Shared bare-atom collection sink — every per-clause TermTransformer
        # writes into this single set so the union is naturally accumulated.
        # ``visit_Module`` emits a final ``BareAtomRefs`` module item that
        # ``compiler_v2._process_bare_atom_refs`` consumes for auto-minting
        # (Phase 2 of GLOBAL_ATOMS_DEFAULT.md).
        transformer._bare_atom_refs: set[str] = set()
        # EDCG declarations: populated by -edcg_acc, -edcg_pass, -edcg_pred directives.
        transformer._edcg_accs: dict[str, dict] = {}   # name → {val, in_, out, joiner_ast}
        transformer._edcg_passes: set[str] = set()      # set of pass names
        transformer._edcg_preds: dict[str, tuple[int, list[str]]] = {}  # pred → (visible_arity, [acc/pass names])

    def _register_functor(transformer, functor_name, field_names, node, kind):
        """Record *functor_name*'s signature and where it was fixed.

        Every site that writes ``_seen_functors`` goes through here so the
        arity-conflict error can attribute the *first* declaration.
        """
        transformer._seen_functors[functor_name] = field_names
        transformer._functor_decl_site[functor_name] = (
            getattr(node, "lineno", 0), kind,
        )

    def _site(transformer, lineno):
        """``file.clausal:12`` when the filename is known, else ``line 12``."""
        if transformer._filename:
            return f"{transformer._filename}:{lineno}"
        return f"line {lineno}"

    def _source_snippet(transformer, lineno):
        """The source text of *lineno*, stripped — ``''`` when unavailable."""
        lines = transformer._source_lines
        if not lines or not lineno or lineno > len(lines):
            return ""
        return lines[lineno - 1].strip()

    def _check_head_signature(transformer, functor_name, all_field_names,
                              prev_fields, node):
        """Reject a clause head that cannot be built against the bound class.

        ``_seen_functors[functor_name]`` is exactly the tuple the guarded
        class block was minted with, so any head field name outside it would
        be emitted as a keyword the class does not have — the bare
        ``__init__() got an unexpected keyword argument 'arg_1'`` failure of
        ``todo/functor-field-name-mismatch-diagnostic.md``.

        The overwhelmingly common shape is an *arity* disagreement: a
        ``-module``/``-private`` declaration (or an earlier clause) fixes
        arity N and a later clause head supplies N+k arguments, whose surplus
        positions fall back to ``arg_N`` placeholder names.  A functor name
        has exactly one arity in Clausal, so that is a source error, not
        something to resolve.  Supplying *fewer* arguments than declared is
        left alone: it builds a partial head whose trailing fields become
        fresh ``Var()``s, which is a documented ``PredicateMeta.__call__``
        behaviour.
        """
        unknown = [n for n in all_field_names if n not in prev_fields]
        if not unknown:
            return
        lineno = getattr(node, "lineno", 0)
        decl_lineno, decl_kind = transformer._functor_decl_site.get(
            functor_name, (0, "an earlier declaration"),
        )
        decl_src = transformer._source_snippet(decl_lineno)
        head_src = transformer._source_snippet(lineno)
        where_decl = transformer._site(decl_lineno)
        where_head = transformer._site(lineno)
        where = (
            f"  declared: {where_decl} ({decl_kind})"
            + (f" — {decl_src}" if decl_src else "")
            + f"\n  clause:   {where_head}"
            + (f" — {head_src}" if head_src else "")
        )
        declared = f"({', '.join(prev_fields)})"
        if len(all_field_names) > len(prev_fields):
            raise SyntaxError(
                f"functor {functor_name}/{len(all_field_names)} conflicts "
                f"with the declaration of {functor_name}/{len(prev_fields)} "
                f"in the same file\n{where}\n"
                f"{functor_name}'s class is minted with "
                f"{len(prev_fields)} field(s) {declared}, so a "
                f"{len(all_field_names)}-argument head cannot be built "
                f"against it. A functor name has exactly one arity in "
                f"Clausal: give the declaration and every clause head of "
                f"{functor_name} the same number of arguments, or rename one "
                f"of them."
            )
        raise SyntaxError(
            f"clause head for {functor_name}/{len(all_field_names)} names "
            f"field(s) {', '.join(unknown)} that {functor_name} does not "
            f"have\n{where}\n"
            f"{functor_name}'s class is minted with fields {declared}. "
            f"Use those names, or change the declaration to match."
        )

    def _emit_head_positionally(transformer, functor_name, prev_fields):
        """True when this clause head must bind by POSITION, not by field name.

        Field names are a module-local *labelling of slots*; **arity** is the
        functor's cross-module contract.  When a file both fixes a local
        signature for *functor_name* and ``-import_from``s the same name, the
        guarded class block is emitted at the declaration's source position and
        the import then rebinds the module global to the FOREIGN class at
        *its* position — while ``_seen_functors`` still holds the LOCAL field
        names.  A keyword head then names local fields against the foreign
        class and raises ``__init__() got an unexpected keyword argument``
        (``todo/functor-field-name-mismatch-diagnostic.md``).

        A positional head binds against whatever class the import supplied, so
        a module-local labelling can no longer contradict a foreign class.  A
        genuine disagreement is an ARITY disagreement, which still raises —
        with full attribution — from ``PredicateMeta.__call__``.

        Deliberately narrow on two axes:

        * ``prev_fields is not None`` means no guarded class block is emitted
          at this head.  When one *is* emitted (the functor's first clause) it
          re-mints the class to exactly the derived fields unless they already
          match, so the bound class is known here and keyword emission is
          precise.  That is the shape ``au/firb/computation.clausal`` and
          ``us/sara_irc_tax/computation.clausal`` rely on: import a 0-arity
          vocabulary atom, then define a same-named predicate whose first
          clause re-mints over the import.
        * the import must have been seen *earlier in the file*.  Before it, the
          binding is provably local, so keyword emission is both correct and a
          better error message.
        """
        return (
            prev_fields is not None
            and functor_name in transformer._imported_functors
        )

    def _build_head_arguments(transformer, positional, arg_field_names,
                              transformed_pos, orig_pos_args,
                              kwarg_field_names, transformed_kw, orig_kw_args):
        """Return ``(args, keywords)`` for a clause head's ``Call``.

        Explicitly-written keyword arguments name a field on purpose, so they
        stay keywords either way; only the positional arguments — whose field
        names the rewriter *derived* — are affected by *positional*.
        """
        keywords = [
            make_keyword_node(fname, term, orig)
            for fname, term, orig in zip(
                kwarg_field_names, transformed_kw, orig_kw_args
            )
        ]
        if positional:
            return list(transformed_pos), keywords
        return [], [
            make_keyword_node(fname, term, orig)
            for fname, term, orig in zip(
                arg_field_names, transformed_pos, orig_pos_args
            )
        ] + keywords

    def _unseat_directive_minted(transformer, functor_name):
        """Drop a -dynamic-minted placeholder registration for *functor_name*.

        A12-F005: the -dynamic(p/N) handler mints the term class with default
        arg_0..arg_{N-1} field names so the declare-then-assertz pattern works
        with no clause in the file. But a REAL clause's derived head-var names
        must win (pre-regression behaviour): call this before consulting
        ``_seen_functors`` at a clause-head site, so the normal first-clause
        path re-derives the names and re-emits the guarded class block (which
        redefines the class iff the fields actually differ).
        """
        if functor_name in transformer._directive_minted_functors:
            transformer._directive_minted_functors.discard(functor_name)
            transformer._seen_functors.pop(functor_name, None)

    def _make_term_transformer(transformer, atoms=None):
        """Build a TermTransformer sharing this EmbedTransformer's
        bare-atom collection sink and import-remap table.

        Centralised so every per-clause TermTransformer participates in the
        same Phase 2 (auto-mint) collection without each call site having
        to remember the plumbing.
        """
        return TermTransformer(
            atoms=atoms if atoms is not None else transformer._atoms,
            import_remap=transformer._import_remap,
            source_lines=transformer._source_lines,
            bare_atom_refs=transformer._bare_atom_refs,
        )

    def _build_fact_statements(transformer, functor_name, orig_pos_args,
                               orig_kw_args, anchor, src_node, expr_stmt):
        """Build AST for a bodyless fact ``functor(args)`` (arity >= 0 via args).

        Shared by the trailing-comma fact case and the comma-optional
        declared-predicate case. Returns ``[functor_class_def?, define_stmt]``
        (a single statement when no class needs emitting).
        """
        arg_field_names = _derive_field_names(orig_pos_args)
        kwarg_field_names = [kw.arg for kw in orig_kw_args]
        all_field_names = arg_field_names + kwarg_field_names

        transformer._unseat_directive_minted(functor_name)
        prev_fields = transformer._seen_functors.get(functor_name)
        if prev_fields is not None:
            for i in range(len(arg_field_names)):
                if i < len(prev_fields):
                    arg_field_names[i] = prev_fields[i]
            all_field_names = arg_field_names + kwarg_field_names
            transformer._check_head_signature(
                functor_name, all_field_names, prev_fields, expr_stmt)

        term_transformer = transformer._make_term_transformer()
        transformed_pos = [term_transformer.visit(a) for a in orig_pos_args]
        transformed_kw = [term_transformer.visit(kw.value) for kw in orig_kw_args]

        head_args, head_keywords = transformer._build_head_arguments(
            transformer._emit_head_positionally(functor_name, prev_fields),
            arg_field_names, transformed_pos, orig_pos_args,
            kwarg_field_names, transformed_kw, orig_kw_args,
        )
        head_ast = replace(
            Call(
                func=replace(Name(id=functor_name, ctx=load), anchor),
                args=head_args,
                keywords=head_keywords,
            ),
            src_node,
        )
        predicate_ast = node_ast(
            "Predicate", expr_stmt.value,
            head=head_ast,
            body=replace(Constant(value=True), expr_stmt.value),
        )
        define_stmt = _make_define_stmt(predicate_ast, expr_stmt)

        statements = []
        if functor_name not in transformer._seen_functors:
            transformer._register_functor(
                functor_name, all_field_names, expr_stmt, "first clause")
            statements.append(
                _make_functor_class_ast(functor_name, all_field_names, expr_stmt)
            )
        statements.append(define_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _build_zero_arity_fact_statements(transformer, functor_name, name_node,
                                          expr_stmt):
        """Build AST for a zero-arity bodyless fact ``flag`` / ``flag,``."""
        head_ast = replace(
            Call(
                func=replace(Name(id=functor_name, ctx=load), name_node),
                args=[],
                keywords=[],
            ),
            name_node,
        )
        predicate_ast = node_ast(
            "Predicate", expr_stmt.value,
            head=head_ast,
            body=replace(Constant(value=True), expr_stmt.value),
        )
        define_stmt = _make_define_stmt(predicate_ast, expr_stmt)
        statements = []
        if functor_name not in transformer._seen_functors:
            transformer._register_functor(
                functor_name, [], expr_stmt, "first clause")
            statements.append(
                _make_functor_class_ast(functor_name, [], expr_stmt)
            )
        statements.append(define_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _is_module_compile(transformer):
        """True when compiling a .clausal MODULE (source_lines were supplied),
        False for REPL cells transformed by _FreshEmbedTransformer via a bare
        EmbedTransformer().  The comma-optional fact rewrite and the bare-call
        guard apply only to modules; a REPL cell's trailing bare Call/Name must
        stay an ast.Expr so the interactive display hook still echoes it."""
        return transformer._source_lines is not None

    def _guard_bare_call(transformer, functor_name, expr_stmt):
        """Wrap an UNDECLARED bare ``functor(...)`` / ``functor`` statement.

        Emits::

            try:
                functor              # resolve the functor NAME only
            except NameError:
                $unterminated_fact_error('functor', lineno, src)
            else:
                <original statement>  # the real call; arg errors surface here

        So an undefined functor becomes a 'missing comma' diagnostic, while a
        legitimate call (imported macro, builtin) runs normally and its own
        argument errors are reported honestly.
        """
        src_text = ""
        if transformer._source_lines is not None:
            idx = expr_stmt.lineno - 1
            if 0 <= idx < len(transformer._source_lines):
                src_text = transformer._source_lines[idx].strip()

        orig_stmt = transformer.generic_visit(expr_stmt)

        guard = Try(
            body=[Expr(value=Name(id=functor_name, ctx=load))],
            handlers=[
                ExceptHandler(
                    type=Name(id="NameError", ctx=load),
                    name=None,
                    body=[
                        Expr(value=Call(
                            func=Name(id="$unterminated_fact_error", ctx=load),
                            args=[
                                Constant(value=functor_name),
                                Constant(value=expr_stmt.lineno),
                                Constant(value=src_text),
                            ],
                            keywords=[],
                        ))
                    ],
                )
            ],
            orelse=[orig_stmt],
            finalbody=[],
        )
        return replace(guard, expr_stmt)

    def visit_Module(transformer, module):
        """Visit the module body, then emit a final ``BareAtomRefs`` item
        carrying every bare reference the per-clause transformers saw.

        The auto-mint pass in ``compiler_v2._process_bare_atom_refs`` reads
        this item and decides per-name whether to install the global atom.
        """
        result = transformer.generic_visit(module)
        if transformer._bare_atom_refs:
            transformer._module_items.append(
                BareAtomRefsItem(names=frozenset(transformer._bare_atom_refs))
            )
        if transformer._implicit_atoms_default and not any(
            isinstance(it, (StrictAtomsItem, ImplicitAtomsItem))
            for it in transformer._module_items
        ):
            transformer._module_items.append(ImplicitAtomsItem())
        return result

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
                    return transformer._make_term_transformer().visit(expression)
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
            _check_hidden_arrow(expr_stmt.value, transformer._source_lines)
            # A trailing comma after a ``<-`` rule parses the rule's
            # ``head < -body`` Compare as a tuple element.  Normalise the two
            # tuple shapes so a comma-terminated rule behaves identically to a
            # newline-separated one — including the same guard errors:
            #
            #   ``head <- (body),``   → Tuple([Compare])      (one element)
            #                           unwrap → compile as a clause below.
            #   ``head <- g1, g2,``   → Tuple([Compare, ...]) (many elements)
            #                           the body was left unparenthesised; raise
            #                           the same error the bare form raises.
            #
            # A single-element tuple whose element is a plain Call is a fact and
            # is handled below unchanged.
            value = expr_stmt.value
            if isinstance(value, Tuple) and isinstance(value.ctx, Load):
                if len(value.elts) == 1:
                    inner = value.elts[0]
                    # ``head <- a or b,`` hides the arrow inside a BoolOp; run the
                    # same disjunction-body check the bare form gets.
                    _check_hidden_arrow(inner, transformer._source_lines)
                    if isinstance(inner, Compare) and _detect_arrow(
                        inner.left, inner.ops, inner.comparators,
                        transformer._source_lines,
                    ) is not None:
                        expr_stmt = replace(Expr(value=inner), expr_stmt)
                elif len(value.elts) > 1 and isinstance(value.elts[0], Compare):
                    head = value.elts[0]
                    if _detect_arrow(
                        head.left, head.ops, head.comparators,
                        transformer._source_lines,
                    ) is not None:
                        # ``head <- g1, g2`` — the comma split an unparenthesised
                        # multi-goal body into tuple elements.
                        raise SyntaxError(_ARROW_BODY_ERROR)
                elif len(value.elts) > 1 and isinstance(value.elts[0], Call):
                    # ``g1, g2`` with no ``<-`` arrow and no head — a bare,
                    # comma-separated sequence of predicate-call-shaped goals at
                    # statement level.  This is never a valid clause: it parses as
                    # a plain tuple that would be evaluated and discarded (no clause
                    # asserted, no goal run).  The author almost certainly meant a
                    # rule body ``head <- (g1, g2)`` or a trailing-comma fact.
                    raise SyntaxError(_MULTI_GOAL_STMT_ERROR)
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
            # Bare -directive at module level (no parens, no args).
            # ``-strict_atoms`` and ``-implicit_atoms`` use this form; other
            # directives all take arguments and parse as the Call form above.
            case UnaryOp(
                op=USub(),
                operand=Name(id=directive_name),
            ) as neg if (
                transformer._scope_depth == 0
                and neg.col_offset == neg.operand.col_offset - 1
                and neg.lineno == neg.operand.lineno
            ):
                return transformer._handle_directive(
                    directive_name, [], expr_stmt
                )
            case Tuple(elts=[single_element], ctx=Load()) if (
                isinstance(single_element, Call)
                and isinstance(single_element.func, Name)
                and transformer._scope_depth == 0
            ):
                # Trailing-comma fact: ``edge(1, 2),`` — build via shared helper.
                return transformer._build_fact_statements(
                    single_element.func.id,
                    single_element.args,
                    single_element.keywords,
                    single_element.func,
                    single_element,
                    expr_stmt,
                )
            case Tuple(elts=[Name(id=functor_name) as name_node], ctx=Load()) if (
                transformer._scope_depth == 0
                and not _is_logic_var_name(functor_name)
            ):
                # A10-F011: zero-arity trailing-comma fact ``flag,`` — shared helper.
                return transformer._build_zero_arity_fact_statements(
                    functor_name, name_node, expr_stmt,
                )
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
                and (arrow := _detect_arrow(left, ops, comparators, transformer._source_lines)) is not None
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
                # names to the established signature by position — unless the
                # entry is a -dynamic placeholder (A12-F005): the first REAL
                # clause's derived head-var names win.
                transformer._unseat_directive_minted(functor_name)
                prev_fields = transformer._seen_functors.get(functor_name)
                if prev_fields is not None:
                    for i in range(len(arg_field_names)):
                        if i < len(prev_fields):
                            arg_field_names[i] = prev_fields[i]
                    all_field_names = arg_field_names + kwarg_field_names
                    transformer._check_head_signature(
                        functor_name, all_field_names, prev_fields, expr_stmt)

                # Transform terms. One shared transformer keeps variable bindings
                # (walrus operator) consistent across head and body.
                term_transformer = transformer._make_term_transformer()
                transformed_pos = [term_transformer.visit(a) for a in orig_pos_args]
                transformed_kw = [term_transformer.visit(kw.value) for kw in orig_kw_args]
                # Read-once lowering: dict reads (``P.key`` / ``P[key]``) become
                # explicit read goals at their first-occurrence position, scoped
                # to the innermost enclosing control construct.
                body_ast = term_transformer.visit(
                    _lower_dict_reads(left, body_expr)
                )

                # Build head call: functor(field=term, ...) as a plain Python Call,
                # not a simple_ast.Call constructor.
                anchor = left.func if isinstance(left, Call) else left
                head_args, head_keywords = transformer._build_head_arguments(
                    transformer._emit_head_positionally(
                        functor_name, prev_fields),
                    arg_field_names, transformed_pos, orig_pos_args,
                    kwarg_field_names, transformed_kw, orig_kw_args,
                )
                head_ast = replace(
                    Call(
                        func=replace(Name(id=functor_name, ctx=load), anchor),
                        args=head_args,
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
                    transformer._register_functor(
                        functor_name, all_field_names, expr_stmt,
                        "first clause")
                    statements.append(
                        _make_functor_class_ast(functor_name, all_field_names, expr_stmt)
                    )
                statements.append(define_stmt)
                return statements if len(statements) > 1 else statements[0]
            case Starred():
                # *(goal_expr) query syntax — leave untouched for
                # _StarQueryTransformer in IPython, which applies TermTransformer
                # to the inner expression.  Returning expr_stmt unchanged prevents
                # EmbedTransformer.visit_Name (X → X.value) from mangling the
                # names that TermTransformer needs to see as plain Name nodes.
                return expr_stmt
            case Call(func=Name(id="_clausal_star_query_")):
                # Sentinel form of *(…) after text-level input transformer
                # rewrites it for Python ≥ 3.14 compatibility.  Same treatment
                # as Starred(): leave untouched for _StarQueryTransformer.
                return expr_stmt
            case Call(func=Name(id=functor_name)) if (
                transformer._scope_depth == 0
                and transformer._is_module_compile()
            ):
                if functor_name in transformer._seen_functors:
                    # Comma-optional bodyless fact for a DECLARED predicate.
                    src = expr_stmt.value
                    return transformer._build_fact_statements(
                        functor_name, src.args, src.keywords, src.func, src,
                        expr_stmt,
                    )
                # Undeclared: guard so an undefined functor yields a comma hint.
                return transformer._guard_bare_call(functor_name, expr_stmt)
            case Name(id=functor_name) if (
                transformer._scope_depth == 0
                and not _is_logic_var_name(functor_name)
                and transformer._is_module_compile()
            ):
                if functor_name in transformer._seen_functors:
                    return transformer._build_zero_arity_fact_statements(
                        functor_name, expr_stmt.value, expr_stmt,
                    )
                return transformer._guard_bare_call(functor_name, expr_stmt)
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
            # A12-F005: mint an empty term class for each dynamic predicate so
            # the module's own clause bodies (and the m.ghost/call APIs) can
            # construct ghost(...) terms before any clause exists — the ISO
            # declare-then-assertz pattern. (-table/-discontiguous do NOT mint;
            # a dangling target there is a load error — A12-F003.)
            statements = []
            for functor, arity in specs:
                if functor not in transformer._seen_functors:
                    field_names = [f"arg_{i}" for i in range(arity)]
                    transformer._register_functor(
                        functor, field_names, expr_stmt,
                        "-dynamic directive")
                    # Placeholder names: a later real clause unseats this
                    # registration so its derived head-var names win
                    # (A12-F005 — see _unseat_directive_minted).
                    transformer._directive_minted_functors.add(functor)
                    statements.append(
                        _make_functor_class_ast(functor, field_names, expr_stmt))
            predspec = transformer._handle_predspec_directive(
                "mark_dynamic", args, expr_stmt)
            if isinstance(predspec, list):
                statements.extend(predspec)
            else:
                statements.append(predspec)
            return statements if len(statements) > 1 else statements[0]
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
        if name == "specialize":
            return transformer._handle_specialize_directive(args, expr_stmt)
        if name == "edcg_acc":
            return transformer._handle_edcg_acc_directive(args, expr_stmt)
        if name == "edcg_pass":
            return transformer._handle_edcg_pass_directive(args, expr_stmt)
        if name == "edcg_pred":
            return transformer._handle_edcg_pred_directive(args, expr_stmt)
        if name == "translations":
            return transformer._handle_translations_directive(args, expr_stmt)
        if name == "strict_atoms":
            return transformer._handle_strict_atoms_directive(args, expr_stmt)
        if name == "implicit_atoms":
            return transformer._handle_implicit_atoms_directive(args, expr_stmt)
        if name == "overwrites":
            return transformer._handle_overwrites_directive(args, expr_stmt)
        raise SyntaxError(
            f"Unknown directive: -{name}(...)  "
            f"(known directives: -module, -private, -dynamic, -discontiguous, "
            f"-table, -shallow, -import_from, -import_module, "
            f"-specialize, -edcg_acc, -edcg_pass, -edcg_pred, -translations, "
            f"-strict_atoms, -implicit_atoms, -overwrites)"
        )

    def _handle_module_directive(transformer, args, expr_stmt):
        """Process ``-module(Name, [export1(A,B), export2(X,Y)])`` directive.

        Extracts predicate signatures from the export list and emits
        ``_make_functor_class_ast`` definitions for each, pre-registering
        them in ``_seen_functors`` so that subsequent clauses use the
        declared field names rather than inferring them from the first clause.
        """
        statements = []
        exports_info = []  # for ModuleAST accumulation
        # A10-F012: validate shape instead of silently dropping malformed
        # parts (every other directive raises on bad args).
        if len(args) < 1 or len(args) > 2 or not isinstance(args[0], Name):
            raise SyntaxError(
                "-module requires a bare name and an export list: "
                "-module(name, [ ... ]); got -module("
                f"{', '.join(unparse(a) for a in args)}) — a dotted "
                "package path is not a valid module name")
        module_name = args[0].id
        if len(args) == 2 and not isinstance(args[1], List):
            raise SyntaxError(
                "-module requires a name and an export list: "
                f"-module(name, [ ... ]); got -module({module_name}, "
                f"{unparse(args[1])}) — second argument must be a list")
        # args[1] should be the export list: ast.List of Call / Name nodes.
        if len(args) == 2:
            for export in args[1].elts:
                if isinstance(export, Name):
                    # Bare atom: generate zero-arity PredicateMeta class
                    transformer._atoms.add(export.id)
                    exports_info.append(export.id)
                    if export.id not in transformer._seen_functors:
                        transformer._register_functor(
                            export.id, [], export, "-module export list")
                        statements.append(
                            _make_functor_class_ast(export.id, [], expr_stmt)
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
                        transformer._register_functor(
                            functor_name, field_names, export,
                            "-module export list")
                        statements.append(
                            _make_functor_class_ast(
                                functor_name, field_names, expr_stmt
                            )
                        )
                # Other item shapes (e.g. the ISO ``foo/2`` arity form, a
                # BinOp) are not pre-registered here — the signature is taken
                # from the first clause — but the list itself is well-formed.
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
        # A10-F012: a missing/malformed list (e.g. -private(helper(X))) used to
        # silently become a no-op, so the predicate signature was later
        # inferred from the first clause with no warning. Raise instead.
        if len(args) != 1 or not isinstance(args[0], List):
            raise SyntaxError(
                "-private requires a single list: "
                "-private([atom, pred(A, B), ...])")
        export_list = args[0]
        for item in export_list.elts:
            if isinstance(item, Name):
                # Bare atom: generate zero-arity PredicateMeta class
                transformer._atoms.add(item.id)
                private_info.append(item.id)
                if item.id not in transformer._seen_functors:
                    transformer._register_functor(
                        item.id, [], item, "-private declaration")
                    statements.append(
                        _make_functor_class_ast(item.id, [], expr_stmt)
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
                    transformer._register_functor(
                        functor_name, field_names, item,
                        "-private declaration")
                    statements.append(
                        _make_functor_class_ast(
                            functor_name, field_names, expr_stmt
                        )
                    )
            # Other item shapes (e.g. the ISO ``foo/2`` arity form) are not
            # pre-registered here; the list itself is still well-formed.
        transformer._module_items.append(PrivateDeclItem(items=private_info))
        if not statements:
            return replace(Pass(), expr_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _handle_strict_atoms_directive(transformer, args, expr_stmt):
        """Process ``-strict_atoms`` directive (Phase 3 of GLOBAL_ATOMS_DEFAULT.md).

        Marker directive — no arguments.  Accepts both the canonical bare form
        ``-strict_atoms`` (parsed via the ``UnaryOp(USub, Name(...))`` branch
        in ``visit_Expr``) and the parenthesised form ``-strict_atoms()`` for
        symmetry with other directives.  Any positional arguments are rejected
        because the directive carries no payload.

        Emits a ``StrictAtomsItem`` module item; the auto-mint pass in
        ``compiler_v2._process_bare_atom_refs`` checks for its presence and
        switches to strict mode (raise ``NameError`` instead of minting an
        undeclared bare atom).
        """
        if args:
            raise SyntaxError(
                "-strict_atoms takes no arguments: use bare `-strict_atoms` "
                "or `-strict_atoms()`"
            )
        transformer._module_items.append(StrictAtomsItem())
        return replace(Pass(), expr_stmt)

    def _handle_implicit_atoms_directive(transformer, args, expr_stmt):
        """Process ``-implicit_atoms`` directive.

        Marker directive — no arguments.  Accepts the bare form
        ``-implicit_atoms`` and the parenthesised ``-implicit_atoms()``.
        Emits an ``ImplicitAtomsItem`` module item that opts the file into
        loose (auto-mint) atom resolution — the inverse of ``-strict_atoms``.
        """
        if args:
            raise SyntaxError(
                "-implicit_atoms takes no arguments: use bare "
                "`-implicit_atoms` or `-implicit_atoms()`"
            )
        transformer._module_items.append(ImplicitAtomsItem())
        return replace(Pass(), expr_stmt)

    def _handle_overwrites_directive(transformer, args, expr_stmt):
        """Process ``-overwrites([atom1, atom2, ...])`` directive (Phase 4 of
        GLOBAL_ATOMS_DEFAULT.md).

        Records atom names whose shadowing of an imported name is intentional.
        No PredicateMeta classes are created here; this directive is purely a
        declarative acknowledgement consumed by ``_process_declarations`` (in
        ``clausal/logic/compiler_v2.py``) to suppress
        ``ClausalAtomShadowingWarning``.

        The narrowed Phase-4 trigger means only atom-name shadowing produces
        the warning, so the entries here are bare ``Name`` nodes — a
        predicate-functor call like ``Foo(X)`` is not accepted here and would
        not silence any warning even if it were.
        """
        if not args or not isinstance(args[0], List):
            raise SyntaxError(
                "-overwrites requires a list of bare names, e.g. "
                "-overwrites([red, ok])."
            )
        items_info: list[str] = []
        for elt in args[0].elts:
            if isinstance(elt, Name):
                items_info.append(elt.id)
            else:
                raise SyntaxError(
                    "-overwrites requires a list of bare names (atom names "
                    "only), e.g. -overwrites([red, ok]).  Got a non-Name "
                    "element."
                )
        transformer._module_items.append(OverwritesDeclItem(items=items_info))
        return replace(Pass(), expr_stmt)

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
                transformer._imported_functors.add(local_name)
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
                # A10-F017: a logic-var-shaped alias (e.g. ``T``) is
                # unreachable — visit_Name treats it as a variable before the
                # remap fires, so the call site later fails with a cryptic
                # NotImplementedError. Reject it here at the directive.
                if _is_logic_var_name(local_name):
                    raise SyntaxError(
                        f"-import_from alias {local_name!r} is a logic-variable "
                        f"name; use a TitleCase alias (e.g. Reach)"
                    )
                dotted_key = f"{module_path}.{orig_name}"
                transformer._import_remap[local_name] = dotted_key
                # The ALIAS is what this file binds; the original spelling
                # stays free for a purely local declaration.
                transformer._imported_functors.add(local_name)
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

    # ── Meta-interpreter specialization directive handler ─────────────────

    def _handle_specialize_directive(transformer, args, expr_stmt):
        """Process ``-specialize(MI, Source, alias=Name)`` directive.

        Requests specialization of meta-interpreter MI with respect to
        Source (a predicate name providing the object program), producing
        a new predicate called Name.  The MI pattern is auto-detected by
        ``analyze_mi()``.
        """
        if len(args) < 2:
            raise SyntaxError(
                "-specialize requires at least 2 arguments: "
                "-specialize(MI, Source, alias=NewName)"
            )
        # First arg: MI predicate name.
        mi_arg = args[0]
        if not isinstance(mi_arg, Name):
            raise SyntaxError(
                f"-specialize: first argument must be a predicate name, "
                f"got {dump(mi_arg)}"
            )
        mi_name = mi_arg.id

        # Second arg: source program predicate name.
        source_arg = args[1]
        if not isinstance(source_arg, Name):
            raise SyntaxError(
                f"-specialize: second argument must be a predicate name, "
                f"got {dump(source_arg)}"
            )
        source_program = source_arg.id

        # Keyword args: alias=NewName, depth=N, cpd=True.
        new_name = None
        depth = 0
        cpd = False
        call_node = expr_stmt.value.operand
        for kw in getattr(call_node, 'keywords', []):
            if kw.arg == 'alias' and isinstance(kw.value, Name):
                new_name = kw.value.id
            elif kw.arg == 'alias' and isinstance(kw.value, Constant):
                new_name = kw.value.value
            elif kw.arg == 'depth' and isinstance(kw.value, Constant):
                depth = int(kw.value.value)
            elif kw.arg == 'cpd' and isinstance(kw.value, Constant):
                cpd = bool(kw.value.value)

        # Also check positional args for a third Name argument.
        if new_name is None and len(args) >= 3 and isinstance(args[2], Name):
            new_name = args[2].id

        if new_name is None:
            raise SyntaxError(
                "-specialize requires alias=NewName keyword argument: "
                "-specialize(MI, Source, alias=NewName)"
            )

        transformer._module_items.append(
            SpecializeItem(
                mi_name=mi_name,
                source_program=source_program,
                new_name=new_name,
                depth=depth,
                cpd=cpd,
            )
        )
        # No runtime code needed — handled in compile_module pipeline.
        stmt = copy_location(Pass(), expr_stmt)
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
            transformer._register_functor(
                pred_name, field_names, expr_stmt, "-edcg_pred directive")
            return _make_functor_class_ast(pred_name, field_names, expr_stmt)
        return replace(Pass(), expr_stmt)

    # ── Translations directive ───────────────────────────────────────────────

    def _handle_translations_directive(transformer, args, expr_stmt):
        """Process ``-translations(lang, {English: Translated, ...})`` directive.

        Emits Python calls to ``register_predicate`` / ``register_atom`` from
        ``clausal.logic.translations`` so the translation table is populated
        at module-load time.
        """
        if len(args) != 2:
            raise SyntaxError(
                "-translations requires two arguments: "
                "-translations(lang, {Eng: Trans, ...})"
            )
        lang_node = args[0]
        if not isinstance(lang_node, Name):
            raise SyntaxError(
                f"-translations: first argument must be a language atom, "
                f"got {dump(lang_node)}"
            )
        lang = lang_node.id

        dict_node = args[1]
        if not isinstance(dict_node, Dict):
            raise SyntaxError(
                f"-translations: second argument must be a dict, "
                f"got {dump(dict_node)}"
            )

        predicate_entries = []
        atom_entries = []
        stmts = []

        # Import the registration functions once.
        reg_import = replace(
            ImportFrom(
                module="clausal.logic.translations",
                names=[
                    alias(name="register_predicate", asname="_reg_pred"),
                    alias(name="register_atom", asname="_reg_atom"),
                ],
                level=0,
            ),
            expr_stmt,
        )
        fix_missing_locations(reg_import)
        stmts.append(reg_import)

        for key_node, val_node in zip(dict_node.keys, dict_node.values):
            if isinstance(key_node, Call) and isinstance(val_node, Call):
                # Predicate: Append(LIST, ELEMENT, NEWLIST): 追加(列表, 元素, 新列表)
                eng_func = key_node.func
                trans_func = val_node.func
                if not isinstance(eng_func, Name) or not isinstance(trans_func, Name):
                    raise SyntaxError(
                        f"-translations: predicate entries must have simple names, "
                        f"got {dump(key_node)}: {dump(val_node)}"
                    )
                eng_name = eng_func.id
                trans_name = trans_func.id
                eng_args = []
                for a in key_node.args:
                    if not isinstance(a, Name):
                        raise SyntaxError(
                            f"-translations: predicate arguments must be names, "
                            f"got {dump(a)}"
                        )
                    eng_args.append(a.id)
                trans_args = []
                for a in val_node.args:
                    if not isinstance(a, Name):
                        raise SyntaxError(
                            f"-translations: predicate arguments must be names, "
                            f"got {dump(a)}"
                        )
                    trans_args.append(a.id)
                if len(eng_args) != len(trans_args):
                    raise SyntaxError(
                        f"-translations: arity mismatch for {eng_name}/{trans_name}: "
                        f"{len(eng_args)} vs {len(trans_args)}"
                    )
                arity = len(eng_args)
                arg_map = dict(zip(eng_args, trans_args))
                predicate_entries.append((eng_name, trans_name, arity, arg_map))

                # Emit: _reg_pred("ja", "Append", "追加", 3, {"LIST": "列表", ...})
                arg_map_dict = replace(
                    Dict(
                        keys=[replace(Constant(value=k), expr_stmt) for k in eng_args],
                        values=[replace(Constant(value=v), expr_stmt) for v in trans_args],
                    ),
                    expr_stmt,
                )
                call_stmt = replace(
                    Expr(value=replace(
                        Call(
                            func=replace(Name(id="_reg_pred", ctx=load), expr_stmt),
                            args=[
                                replace(Constant(value=lang), expr_stmt),
                                replace(Constant(value=eng_name), expr_stmt),
                                replace(Constant(value=trans_name), expr_stmt),
                                replace(Constant(value=arity), expr_stmt),
                                arg_map_dict,
                            ],
                            keywords=[],
                        ),
                        expr_stmt,
                    )),
                    expr_stmt,
                )
                fix_missing_locations(call_stmt)
                stmts.append(call_stmt)

            elif isinstance(key_node, Name) and isinstance(val_node, Name):
                # Atom: nil: 空
                eng_atom = key_node.id
                trans_atom = val_node.id
                atom_entries.append((eng_atom, trans_atom))

                # Emit: _reg_atom("ja", "nil", "空")
                call_stmt = replace(
                    Expr(value=replace(
                        Call(
                            func=replace(Name(id="_reg_atom", ctx=load), expr_stmt),
                            args=[
                                replace(Constant(value=lang), expr_stmt),
                                replace(Constant(value=eng_atom), expr_stmt),
                                replace(Constant(value=trans_atom), expr_stmt),
                            ],
                            keywords=[],
                        ),
                        expr_stmt,
                    )),
                    expr_stmt,
                )
                fix_missing_locations(call_stmt)
                stmts.append(call_stmt)

            else:
                raise SyntaxError(
                    f"-translations: each entry must be either "
                    f"Pred(args): Trans(args) or atom: atom, "
                    f"got {dump(key_node)}: {dump(val_node)}"
                )

        # Accumulate metadata for pipeline-split ModuleAST.
        transformer._module_items.append(
            TranslationsItem(
                language=lang,
                predicate_entries=predicate_entries,
                atom_entries=atom_entries,
            )
        )

        # Return statement(s) — the visit_Expr caller handles lists.
        if len(stmts) == 1:
            return stmts[0]
        return stmts

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

        # A12-F005: a -dynamic placeholder must not clobber derived names.
        transformer._unseat_directive_minted(functor_name)
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
        term_transformer = transformer._make_term_transformer(atoms=dcg_atoms)
        transformed_pos = [
            term_transformer.visit(a) for a in orig_pos_args
        ]
        transformed_kw = [
            term_transformer.visit(kw.value) for kw in orig_kw_args
        ]
        body_ast = term_transformer.visit(body_expr_raw)

        anchor = lhs.func if isinstance(lhs, Call) else lhs
        head_args, head_keywords = transformer._build_head_arguments(
            transformer._emit_head_positionally(functor_name, prev_fields),
            arg_field_names, transformed_pos, orig_pos_args,
            kwarg_field_names, transformed_kw, orig_kw_args,
        )
        head_ast = replace(
            Call(
                func=replace(Name(id=functor_name, ctx=load), anchor),
                args=head_args,
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
            transformer._register_functor(
                functor_name, all_field_names, expr_stmt, "first clause")
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
            term_transformer = transformer._make_term_transformer()
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

    def visit_NamedExpr(transformer, node):
        # Walrus operator: only transform the value, never the target.
        # The target must remain a plain Name node.
        node.value = transformer.visit(node.value)
        return node

    def visit_Name(transformer, name):
        # A10-F002 / A10-D001: unescaped ALLCAPS / _leading names in outer
        # Python code are ordinary Python names (constants, JSON, UUID, a local
        # ``_tmp``, ``MAX = 5``) — NOT logic variables, so they are left alone.
        # A logic variable's value is reached inside embedded Python via the
        # ``++`` escape (handled by the PyThunk machinery), not by unboxing a
        # bare Name here. The previous ``X → X.value`` rewrite broke both
        # assignment (``MAX = 5`` → ``MAX.value = 5``) and reads of Python
        # locals (``return _tmp`` → ``5 .value``).
        return name
