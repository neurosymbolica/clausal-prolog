from ast import *
from collections import Counter
from copy import deepcopy
import sys

from .parser import is_template_func
from .compiler import compile_template_func
from .desugar import desugar_surface, dotted_attr_chain, is_dict_attr_access
# The quote character ``ast`` erased, recovered from the token stream — the
# one thing that tells ``'foo'`` (an atom in every mode) from ``"foo"``
# (mode-dependent, and never a functor).  See spec §7.
from .quote_map import build_quote_map, quote_of

# Module-level item types for the pipeline-split ModuleAST.
from clausal.pythonic_ast.nodes import (
    AtomAppliedAsFunctor as AtomAppliedAsFunctorItem,
    BareAtomRefs as BareAtomRefsItem,
    Directive as DirectiveItem,
    EdcgAccDecl,
    EdcgPassDecl,
    EdcgPredDecl,
    HideDeclaration as HideDeclItem,
    ImportFromDirective as ImportFromItem,
    ImportModuleDirective as ImportModuleItem,
    ModuleDeclaration as ModuleDeclItem,
    PrivateDeclaration as PrivateDeclItem,
    Predicate as PredicateItem,
    SpecializeDirective as SpecializeItem,
    ImplicitAtomsDeclaration as ImplicitAtomsItem,
    StrictAtomsDeclaration as StrictAtomsItem,
    TranslationsDirective as TranslationsItem,
)

from clausal.logic.atoms import NIL_SPELLING, mangle
# The module-namespace key the ``-module``/``-private`` rewrite emits a
# functor-signature registry under.  Single source of truth lives with the
# cell primitives that registry feeds.
from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY, IMPLICIT_FUNCTORS_FLAG

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

def _arrow_body_error(node=None, source_lines=None, filename=None):
    """`_ARROW_BODY_ERROR` as a LOCATED SyntaxError.

    Raised bare, this error names the rule but not the clause. That is affordable for a
    human reading a short file and expensive for anything else: a 20-clause module whose
    legal nested `<-` forms look exactly like what the message warns about gives the
    reader nothing to bisect on. Measured 2026-08-08 against an LLM authoring loop:
    four authoring attempts spent guessing the line, then the run was abandoned.

    Every raise site holds an AST node, so the coordinates are already in hand. Setting
    them also fixes the message for free — `str(SyntaxError)` renders as
    `msg (file, line N)` once filename/lineno are set — so consumers that only print the
    exception gain the location without changing. Located parser errors are already the
    norm here; this raise was the outlier.
    """
    lineno = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    text = None
    if source_lines and lineno and 1 <= lineno <= len(source_lines):
        text = source_lines[lineno - 1]
    if lineno is None:
        return SyntaxError(_ARROW_BODY_ERROR)
    return SyntaxError(_ARROW_BODY_ERROR,
                       (filename, lineno, (col + 1) if col is not None else None, text))


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
        raise _arrow_body_error(usub_node, source_lines)

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
        raise _arrow_body_error(usub_node, source_lines)


# ─── Logic variable name helper ───────────────────────────────────────────────


# ── Truth-value spelling aliases ────────────────────────────────────────────
#
# ISO Prolog spells the booleans ``true``/``false``; XSB and SWI spell the
# well-founded third value ``undefined``.  Clausal borrows Python's parser, so
# its canonical spellings are ``True``/``False`` (which arrive as ``Constant``
# and never reach name resolution) and ``Undefined`` (an injected runtime
# binding arriving as a ``Name``).  An author coming from Prolog writes the
# lowercase form and, under strict atoms, meets an undeclared-atom error whose
# five remedies do not include the right one.
#
# Folding the aliases here — at the single point where a bare ``Name`` is
# classified — makes them indistinguishable from the canonical spelling in
# everything downstream: the same node, the same term, the same index key, the
# same Prolog output.  Nothing else in the compiler learns a second spelling.
#
# The cost is that ``true``, ``false`` and ``undefined`` are no longer available
# as user atom or predicate names.  The corpus uses none of the three.
#
# ``unknown`` is deliberately absent: it was ``Undefined``'s name before the
# rename and binding it too would restore the two-names-for-one-value ambiguity
# the rename removed.  ``clausal.atom_diagnostics`` catches it instead.
_TRUTH_ALIASES = {
    "true": "True",
    "false": "False",
    "undefined": "Undefined",
}

_BOOL_ALIAS_VALUES = {"True": True, "False": False}

# The reified if-then-else goal.  ``if_`` is canonical — lower-case like every
# other goal, trailing underscore to dodge the Python keyword, and the spelling
# the reified-conditional literature uses (Neumerkel & Kral's ``if_/3``, see
# docs/reified_ite.md).  ``If`` is the superseded spelling: every recogniser
# below accepts it, the term pass warns once per site, and nothing in the
# library emits it any more.
ITE_NAME = "if_"
ITE_DEPRECATED_NAME = "If"
_ITE_NAMES = frozenset({ITE_NAME, ITE_DEPRECATED_NAME})


def _reserved_truth_decl_name(item) -> str | None:
    """The truth-value spelling *item* tries to declare, or ``None``.

    Declaration lists are parsed straight off the Python AST, before the alias
    fold, so a truth value reaches here in one of two shapes: ``True``/``False``
    as a ``Constant`` (Python parsed them as literals) and
    ``undefined``/``Undefined`` as a ``Name``.  Both the bare form
    (``-private([True])``) and the arity form (``-private([True(X)])``) count.

    Without this, a bool-valued entry matched neither the ``Name`` branch nor
    the ``Call``-of-``Name`` branch and fell through the "other item shapes"
    fallthrough, declaring nothing at all and saying nothing about it — the
    exact silent no-op A10-F012 removed for malformed ``-private`` lists.
    """
    if isinstance(item, Call):
        item = item.func
    if isinstance(item, Constant) and isinstance(item.value, bool):
        return "True" if item.value else "False"
    if isinstance(item, Name) and item.id in _RESERVED_TRUTH_DECL_NAMES:
        return item.id
    return None


_RESERVED_TRUTH_DECL_NAMES = {"true", "false", "undefined", "Undefined"}


def _raise_reserved_truth_decl(name: str, directive: str) -> None:
    raise SyntaxError(
        f"{directive} cannot declare `{name}`: the three truth values "
        f"`True`, `False` and `Undefined` (aliases `true`, `false`, "
        f"`undefined`) are builtins, not predicates or atoms. Every "
        f"reference to that name resolves to the value, so the declared "
        f"predicate could never be called. Rename it."
    )



def _is_constant_name(identifier: str) -> bool:
    """True for the module-constant lexical class: exactly one leading and
    one trailing underscore with a non-digit-initial interior (``_PI_``,
    ``_MAX_RETRIES_``, ``_円周率_``).

    Carved OUT of the logic-variable namespace — every ``_is_logic_var_name``
    copy excludes this shape (pinned by test_var_classifier_conformance).
    ``_1_`` is rejected: a constant named ``1`` invites confusion with the
    literal. See implementation_plans/module-level-constants.md.
    """
    return (
        len(identifier) >= 3
        and identifier[0] == "_" and identifier[-1] == "_"
        and identifier[1] != "_" and identifier[-2] != "_"
        and not identifier[1].isdigit()
    )


def _raise_undeclared_constant(identifier: str, node=None, source_lines=None,
                                filename=None) -> None:
    """Shared message for a constant-shaped reference nothing declares.

    Raised both from ``visit_Name`` (ordinary term position) and from
    ``_build_py_thunk_ast`` (the ``++``/f-string/unit-sugar raw-Python
    escapes — their body never passes through ``visit_Name``, so it would
    otherwise silently fall through to a Python ``NameError`` at solve time
    instead of a load-time ``SyntaxError``).

    *node*/*source_lines*/*filename* mirror ``_arrow_body_error``: every raise
    site holds the offending AST node, so the coordinates are already in
    hand.  Setting filename/lineno on the ``SyntaxError`` (rather than only
    naming the site inside the message) is what qualifies it for
    ``clausal_syntax_diagnostics``'s caret/window enrichment — see
    syntax_diagnostics.py, which requires ``exc.filename == filename`` and a
    valid ``exc.lineno``.
    """
    lineno = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    text = None
    if source_lines and lineno and 1 <= lineno <= len(source_lines):
        text = source_lines[lineno - 1]
    msg = (
        f"`{identifier}` is a constant name (one leading and one "
        f"trailing underscore) but nothing declares it. Declare "
        f"-constants({identifier} = <ground value>) before this "
        f"clause, or import it: -import_from(mod, [{identifier}]) — "
        f"or if you meant a logic variable, drop one of the underscores "
        f"(`_x` or `x_`)."
    )
    if lineno is None:
        raise SyntaxError(msg)
    raise SyntaxError(
        msg, (filename, lineno, (col + 1) if col is not None else None, text))


def _raise_constant_rhs_logic_var(identifier: str, node=None, source_lines=None,
                                   filename=None) -> None:
    """A -constants RHS (structured or scalar) referenced a logic-variable-
    shaped name (or the anonymous ``_`` wildcard).

    Groundness is required at COMPILE time for a -constants RHS — not only
    at the runtime ``$check_constant_ground`` gate, which exists as a
    backstop for values a ``++()`` escape can construct outside the parser's
    view. Raised here so the error is located (mirrors
    ``_raise_undeclared_constant``) instead of silently minting a fresh Var
    (which would then only surface, unlocated, as a ConstantNotGroundError
    once the module finishes loading).
    """
    lineno = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    text = None
    if source_lines and lineno and 1 <= lineno <= len(source_lines):
        text = source_lines[lineno - 1]
    shown = "_" if identifier == "_" else f"`{identifier}`"
    msg = (
        f"-constants RHS references {shown}, a logic-variable name — "
        f"-constants values must be fully ground at compile time. Use a "
        f"declared constant, a declared atom, or a ground literal instead."
    )
    if lineno is None:
        raise SyntaxError(msg)
    raise SyntaxError(
        msg, (filename, lineno, (col + 1) if col is not None else None, text))


def _raise_located_syntax_error(msg: str, node, source_lines=None,
                                filename=None) -> None:
    """Raise *msg* as a ``SyntaxError`` located at *node*.

    The generic located raiser: shared by every ``-constants`` RHS
    validation error that isn't one of the two dedicated raisers above
    (``_raise_undeclared_constant``, ``_raise_constant_rhs_logic_var``) —
    the dict-splat rejection, the undeclared-functor error, the generic
    unsupported-RHS fallthrough in
    ``EmbedTransformer._transform_constant_rhs`` — and by the visit-site
    construct rejections (slice subscripts, comprehension loop targets).
    Every such error is a compile-time error with an AST node in hand, so
    there is no excuse for any of them to come back as a bare,
    unattributed ``SyntaxError`` — the caller always has *node*, exactly
    like the two dedicated raisers.
    """
    lineno = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    text = None
    if source_lines and lineno and 1 <= lineno <= len(source_lines):
        text = source_lines[lineno - 1]
    if lineno is None:
        raise SyntaxError(msg)
    raise SyntaxError(
        msg, (filename, lineno, (col + 1) if col is not None else None, text))


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

    Constant-shaped names (``_PI_``) are excluded too — pinned by
    test_var_classifier_conformance.
    """
    if identifier == "_":
        return False
    if identifier.startswith("__"):
        return False
    if _is_constant_name(identifier):
        return False
    if identifier.startswith("_"):
        return True
    # ALL-CAPS: str.isupper() is True iff all cased chars are uppercase AND
    # there is at least one cased character — exactly what we want.
    return identifier.isupper()


def _suggest_non_var_name(identifier: str) -> str:
    """A spelling of *identifier* that ``_is_logic_var_name`` rejects.

    Only used inside error messages, so "plausible" beats "canonical":
    ``FOO`` -> ``Foo``, ``_foo`` -> ``foo``, ``F`` -> ``Fx`` (a single letter
    title-cased is still all-caps).
    """
    stripped = identifier.lstrip("_")
    if not stripped:
        return "foo"
    if identifier.startswith("_"):
        candidate = stripped
    else:
        candidate = stripped[0] + stripped[1:].lower()
    if _is_logic_var_name(candidate):
        candidate = candidate + "x"
    return candidate


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
            and goal.func.id in _ITE_NAMES and len(goal.args) == 3
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


def _collect_constant_refs(node) -> list[str]:
    """Collect FREE constant-shaped (``_X_``) names, in first-occurrence order.

    Mirrors ``_collect_logic_var_names`` but for the constants class — used
    by ``_build_py_thunk_ast`` to validate the raw-Python escapes (``++()``,
    f-strings, unit sugar), whose body is embedded verbatim as a Python
    lambda and so never passes through ``visit_Name``.

    "Free" excludes any identifier locally bound *within this same escape
    subtree* — a comprehension target (``_ITEM_`` in ``[x for _ITEM_ in
    ...]``) or a walrus target (``(_X_ := ...)``) is a plain ``Store``-ctx
    ``Name`` node reachable by the same walk, not a reference to a module
    global, so it must never be flagged as an undeclared constant. Two
    passes: first collect every ``Store``-ctx identifier anywhere in the
    subtree (its local-binding set), then collect ``Load``-ctx
    constant-shaped names that are not in that set.
    """
    bound: set[str] = set()

    class _BindCollector(NodeVisitor):
        def visit_Name(self, name):
            if isinstance(name.ctx, Store):
                bound.add(name.id)
            self.generic_visit(name)

    _BindCollector().visit(node)

    ordered: list[str] = []
    seen: set[str] = set()

    class _Collector(NodeVisitor):
        def visit_Name(self, name):
            ident = name.id
            if (
                isinstance(name.ctx, Load)
                and _is_constant_name(ident)
                and ident not in bound
                and ident not in seen
            ):
                seen.add(ident)
                ordered.append(ident)
            self.generic_visit(name)

    _Collector().visit(node)
    return ordered


class ClausalLintWarning(UserWarning):
    """Load-time lint diagnostic for a likely-footgun Clausal construct."""


class ClausalSingletonWarning(ClausalLintWarning):
    """A named logic variable occurring exactly once in its clause.

    Suppress per-variable with the ``_UNUSED`` suffix, per-file with
    ``-allow_singletons``. The suffix is the sole canonical spelling —
    case-based exemptions are blind for caseless scripts, which the
    ``isupper()`` rule forces into leading-underscore variables.
    """


class ClausalDeprecatedSpellingWarning(ClausalLintWarning):
    """A construct written with a superseded surface spelling.

    Not a ``DeprecationWarning``: those are silenced by default outside
    ``__main__``, and a load-time lint that nobody sees is the silent alias
    this warning exists to avoid.  Suppress it the way the other lints are
    suppressed — ``warnings.filterwarnings`` on this class.
    """


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


def _find_cons_bar_in_head(arg_nodes) -> "BinOp | None":
    """The first ``A | B`` in a head argument that reads as Prolog cons, or None.

    Two shapes qualify, both observed in generated code (see
    ``todo/done/C1-ill-typed-interop-calls-are-silent-failures.md``):

    * ``[H | T]`` — a BitOr as a direct element of a list display; Python
      parses the Prolog cons brackets as a one-element list of ``H | T``;
    * ``[W, S] | REST`` — a BitOr with a list literal as an operand.

    A BitOr over bare names (``holds(A | B)``) is left alone: that is a
    plausible structural pattern over BitOr terms (clpb et al.), and nothing
    marks it as list intent.
    """
    for arg_node in arg_nodes:
        for node in walk(arg_node):
            if (isinstance(node, BinOp) and isinstance(node.op, BitOr)
                    and (isinstance(node.left, List)
                         or isinstance(node.right, List))):
                return node
            if isinstance(node, List):
                for element in node.elts:
                    if (isinstance(element, BinOp)
                            and isinstance(element.op, BitOr)):
                        return element
    return None


def _warn_cons_bar_head(pos_args, kw_args, node, source_lines) -> None:
    """Warn when a clause head spells list cons the Prolog way.

    The head still compiles — to a pattern over a BitOr *term* — so every
    clause silently never matches a real list.  Same load-time lint channel
    as ``_warn_isnot_partial_pattern``.
    """
    bar = _find_cons_bar_in_head(
        list(pos_args) + [kw.value for kw in kw_args])
    if bar is None:
        return
    import warnings  # noqa: PLC0415
    lineno = getattr(bar, "lineno", None) or getattr(node, "lineno", None)
    snippet = ""
    if source_lines and lineno and 1 <= lineno <= len(source_lines):
        snippet = " — " + source_lines[lineno - 1].strip()
    where = f" (line {lineno})" if lineno else ""
    warnings.warn(
        f"`A | B` in a clause head{where}{snippet}: this builds a bitwise-or "
        "term, not a list, so the clause can never match a real list — "
        "did you mean `[H, *T]`? (Clausal's spelling of Prolog `[H|T]`)",
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
    # Constant-shaped free names in the thunk body never pass through
    # visit_Name either (the body is embedded verbatim as a Python lambda),
    # so an undeclared one would otherwise silently defer to a Python
    # NameError at solve time instead of a load-time SyntaxError.
    for ident in _collect_constant_refs(expression):
        if ident not in transformer.constants:
            _raise_undeclared_constant(
                ident, node, transformer._source_lines, transformer._filename)
    # An f-string / ``++()`` use is an occurrence for the singleton lint —
    # these names never pass through visit_Name, so bump the counter here.
    # Exact multiplicity within one thunk body is not needed; one bump per
    # captured name is enough to take it out of "singleton" territory.
    for name in var_names:
        transformer.var_occurrences[name] += 1
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
        # A thunk's captured free names are logic variables by the same rule
        # ``visit_Name`` applies, but they never pass through it — the unit
        # sugar ``FOO(Unit)`` and the f-string / ``++()`` paths mint their
        # ``Var()``s here.  Record them in the same sink so that
        # ``_check_var_shaped_predicate_names`` sees them: a body goal
        # ``FOO(X)`` for a declared ``FOO/1`` lands in exactly this branch,
        # silently reinterpreted as ``Quantity(FOO, X)``.
        transformer._logic_var_refs.setdefault(name, getattr(node, "lineno", 0))
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


def _quote_of_positioned(transformer, node):
    """``quote_of`` for the node, with this file's position on any error.

    ``quote_map.quote_of`` raises a BARE ``SyntaxError`` for a literal
    written in two quote styles: that module holds no filename and no source
    text, and a half-filled position (``filename=None``) would opt the error
    out of ``syntax_diagnostics.enrich_syntax_error``, which bails unless
    ``exc.filename`` is the file it is rendering.  So the position is
    attached HERE, where the transformer knows both — the same treatment the
    functor refusal below gets.

    Task 11 widens the map from the callee position to every literal, which
    means many more call sites; they all go through this one wrapper so the
    diagnostic cannot drift apart between them.
    """
    try:
        return quote_of(transformer._quote_map, node)
    except SyntaxError as exc:
        _raise_located_syntax_error(
            exc.msg, node, transformer._source_lines, transformer._filename)


def _atom_as_functor_message(name, filename, lineno, owner=None):
    """The refusal for a declared ATOM applied with arguments.

    One text, three raise sites (P3-3 Task 4 fix round 2): the ``-hide``-en
    case decided during the walk, the local case decided by
    ``EmbedTransformer.visit_Module`` once the walk is complete, and the
    ``-import_from``'d case decided by ``compiler_v2.
    _check_atoms_applied_as_functors`` once the owner has executed.  Built
    where the call site's file and line are known, carried to whichever site
    ends up raising it.
    """
    where = f"{filename}:{lineno}" if filename else f"line {lineno}"
    if owner is not None:
        return (
            f"{where}: `{name}` is declared as an atom in `{owner}` and "
            f"locally, but is applied as a functor here.  Nothing declares "
            f"`{name}` with arguments: declare it as `{name}(X)` in "
            f"`{owner}`'s -module functor list, or reference it bare as the "
            f"atom it is."
        )
    return (
        f"{where}: `{name}` is declared as an atom (a bare name in -module, "
        f"or -private/-hide) but is applied as a functor here.  Declare it "
        f"with arguments in the -module functor list (e.g. `{name}(X)`), or "
        f"reference it bare as the atom it is."
    )


# ─── Term Transformer ─────────────────────────────────────────────────────────


class TermTransformer(NodeTransformer):
    """Transform a Python expression AST into Python AST that constructs simple_ast nodes."""

    def __init__(transformer, atoms=frozenset(), import_remap=None,
                 source_lines=None, bare_atom_refs=None,
                 logic_var_refs=None, constants=frozenset(), filename=None,
                 reify=False, hidden_atoms=frozenset(), module_name=None,
                 declared_functors=None, atom_functor_sites=None,
                 quote_map=None, double_quotes_mode="atom"):
        transformer.seen_vars = set()
        # Reflection models MORE than compiles: ``reify_source`` reuses this
        # transformer but must keep accepting shapes the compiler refuses —
        # e.g. a logic-variable comprehension target, pinned by the renderer
        # round-trip suite.  ``reify=True`` (set only by clausal.reflection)
        # suppresses the compile-only rejections.
        transformer._reify = reify
        # Per-clause occurrence count of each logic-variable name, keyed by
        # identifier — feeds the ClausalSingletonWarning lint (see
        # EmbedTransformer._warn_singletons). Every TermTransformer starts a
        # fresh Counter; the arrow-clause build's shared instance (head +
        # body) is what makes "per clause" the right granularity.
        transformer.var_occurrences = Counter()
        transformer._logic_var_refs = (
            logic_var_refs if logic_var_refs is not None else {})
        transformer.atoms = atoms
        # P3-1 Task 6 (§1a/§1b R1): the current file's ``-hide``-en bare
        # spellings and its own declared module name, threaded through from
        # ``EmbedTransformer`` by ``_make_term_transformer`` — see
        # ``visit_Name``'s atom branch, which checks ``_hidden_atoms``
        # BEFORE the general ``atoms`` membership check so a hidden name
        # substitutes the mangled ``Constant`` instead of the plain one.
        transformer._hidden_atoms = hidden_atoms
        # P3-3 Task 4 fix round 1 (I-1): the EmbedTransformer's LIVE
        # ``_seen_functors`` dict (functor name -> field names), not a copy --
        # a functor registered later in the file is visible here the moment it
        # is registered.  Read by ``_visit_call_func`` only, to tell a name
        # declared as an atom AND as a functor (whose applied form is the
        # FUNCTOR) from one declared as an atom alone (whose applied form is a
        # mistake).
        transformer._declared_functors = (
            declared_functors if declared_functors is not None else {})
        # Fix round 2 (O1): the SHARED list ``EmbedTransformer.visit_Module``
        # drains once the walk is over.  ``_declared_functors`` is the
        # walk-time set, so "declared as an atom and NOT as a functor" cannot
        # be answered while the walk is still running -- a functor can be
        # established by a clause LATER in the file.  ``_visit_call_func``
        # records candidates here instead of deciding on the spot.
        transformer._atom_functor_sites = (
            atom_functor_sites if atom_functor_sites is not None else [])
        transformer._module_name = module_name
        # -constants (Task 5): names bound to a ground value before any
        # clause statement executes. A plain Name reference to one embeds
        # the value in the clause term — see visit_Name.
        transformer.constants = constants
        transformer._import_remap = import_remap or {}
        transformer._source_lines = source_lines
        # P3-3 strings program (spec §7): the file's ``(lineno, byte col) ->
        # quote char`` map, built ONCE by the owning EmbedTransformer and
        # shared by every per-clause TermTransformer, plus the
        # ``-double_quotes`` mode in force at the point this transformer was
        # made (the directive is position-sensitive, so a transformer built
        # for a clause below the directive sees the new mode and one built
        # above it does not).  An empty map means "quotes unknown" — the
        # REPL/IPython transform site and every programmatic AST land there,
        # and ``quote_of`` answers ``None`` for each lookup, which every
        # reader treats as the pre-strings behaviour.
        transformer._quote_map = quote_map if quote_map is not None else {}
        transformer._double_quotes_mode = double_quotes_mode
        # Source file being rewritten, used only to attribute compile-time
        # errors (mirrors EmbedTransformer._filename) — threaded through so
        # an undeclared-constant SyntaxError raised from here qualifies for
        # clausal_syntax_diagnostics's caret/window enrichment.
        transformer._filename = filename
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
        # P3-3 Task 4: an ATOM applied as a functor.  ``visit_Name``'s atom
        # branch answers a declared atom with its ``str`` spelling, which in
        # func position lowered to ``Call(func='bound2', ...)`` -- a shape
        # every downstream ``isinstance(func, LoadName)`` branch skips, so the
        # clause was present, indexed and unmatchable in a head and the AST
        # node leaked into user data in a body, both SILENTLY.
        #
        # Fix round 1 (I-1): a spelling can be declared as BOTH -- ``-module(m,
        # [dual, dual(G)])`` is legal and live, and its ``dual/1`` answers.
        # For a dual-declared name the APPLIED form is the FUNCTOR (it is the
        # bare-``str`` lowering that was wrong, not the declaration), so the
        # atom branch is bypassed here and the functor reference emitted
        # directly -- ``visit_Name`` cannot do it, because its atom test runs
        # before its import-remap and fallthrough branches.
        #
        # Fix round 2 (O1/O2): "and NOT as a functor" is not answerable HERE.
        # A functor can be established by a clause later in the file, and an
        # ``-import_from``'d name is a functor only if its OWNER declared it
        # so -- which this file cannot know until the owner has executed.  So
        # the functor reference is emitted optimistically and the candidate
        # recorded; ``visit_Module`` settles the local half once the walk is
        # complete, and ``compiler_v2._check_atoms_applied_as_functors``
        # settles the imported half against the signature registry.  A
        # ``-hide``-en name is decided on the spot: it can never be
        # dual-declared (``_register_functor`` refuses that collision
        # head-on) and it can never be imported (the mangling is file-local).
        if isinstance(func_expr, Name) and (
            func_expr.id in transformer._hidden_atoms
            or func_expr.id in transformer.atoms
        ):
            identifier = func_expr.id
            if identifier in transformer._hidden_atoms:
                raise SyntaxError(_atom_as_functor_message(
                    identifier, transformer._filename,
                    getattr(func_expr, "lineno", None)))
            # An imported functor is "declared as a functor" too, and its
            # reference is the DOTTED remap ``visit_Name`` would emit.
            dotted = transformer._import_remap.get(identifier)
            transformer._atom_functor_sites.append(
                (identifier, getattr(func_expr, "lineno", None), dotted))
            return node_ast(
                "LoadName", func_expr,
                name=replace(Constant(value=dotted or identifier), func_expr))
        prev = transformer._suppress_bare_atom_collection
        transformer._suppress_bare_atom_collection = True
        try:
            return transformer.visit(func_expr)
        finally:
            transformer._suppress_bare_atom_collection = prev

    def _warn_deprecated_ite_spelling(transformer, call):
        """Lint one ``If(...)`` site (see ClausalDeprecatedSpellingWarning).

        Every surface path funnels through ``visit_Call`` eventually.  The DCG
        body rewriter runs first, but it rebuilds the node with the author's
        own spelling rather than normalising to ``if_``, so an ``If`` inside a
        grammar body is warned about here too instead of being laundered
        upstream.  Message shape follows ``EmbedTransformer._site``.
        """
        import warnings  # noqa: PLC0415
        lineno = getattr(call, "lineno", None)
        if transformer._filename:
            where = f"{transformer._filename}:{lineno or '?'}"
        else:
            where = f"line {lineno}" if lineno else "unknown site"
        snippet = ""
        lines = transformer._source_lines
        if lines and lineno and 1 <= lineno <= len(lines):
            snippet = " — " + lines[lineno - 1].strip()
        warnings.warn(
            f"{where}{snippet}: `{ITE_DEPRECATED_NAME}` is the old spelling of "
            f"the reified if-then-else. Rename "
            f"`{ITE_DEPRECATED_NAME}` -> `{ITE_NAME}` "
            f"({ITE_NAME}(COND, THEN, ELSE)); the old spelling still works but "
            f"will be removed in a future release",
            ClausalDeprecatedSpellingWarning,
            stacklevel=2,
        )

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

        # if_(cond, then, else) → IfExpr node.  ``If`` is the old spelling.
        if isinstance(call.func, Name) and call.func.id in _ITE_NAMES:
            if call.func.id == ITE_DEPRECATED_NAME:
                transformer._warn_deprecated_ite_spelling(call)
            if call.keywords or len(call.args) != 3:
                raise SyntaxError(
                    f"{ITE_NAME}() takes exactly 3 positional arguments: "
                    f"{ITE_NAME}(condition, then, else)"
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
            # ...but only the ATOM spelling.  ISO 6.3.3: a functor is named by
            # an atom, and under the strings design (spec §7) a double-quoted
            # literal is not an atom spelling — in `chars` mode it is a char
            # list, which cannot name anything.  Refusing it in every mode
            # (rather than only after the flip) means the diagnostic is the
            # same before and after, and no module quietly changes meaning
            # when the default moves.  A `None` answer means the quote is
            # unknown (no source lines: the REPL, a programmatic AST) and the
            # sugar keeps its pre-strings behaviour.
            # Unconditional, ``reify`` included: the mixed-quote-style error
            # this can raise is a WELL-FORMEDNESS rule, and "reflection models
            # more than it compiles" means more legal shapes, never malformed
            # input.  `"a" 'b'` has no meaning to model — gating this call on
            # ``_reify`` made ``reify_source`` answer with the atom ``ab``,
            # silently inventing one of the two readings (fix round 2).
            quote = _quote_of_positioned(transformer, call.func)
            # The FUNCTOR refusal, by contrast, IS compile-only and so IS
            # exempt under ``reify=True``: it rejects a well-formed literal
            # for a reason (ISO 6.3.3) that reflection does not care about,
            # and a file must not become un-reifiable over it.  See the
            # ``_reify`` contract in the class docstring.
            if quote == '"' and not transformer._reify:
                spelling = call.func.value
                # The suggestion is source text, so it has to survive being
                # re-read: a spelling containing a quote or a backslash needs
                # them escaped or the "fix" would not parse.
                single_quoted = "'{}'".format(
                    spelling.replace("\\", "\\\\").replace("'", "\\'"))
                # ...and the bare-name alternative only exists when the
                # spelling IS a name.  `"a b"(1)` has no bare form.
                bare_hint = (f', or {spelling}(...) if it is a plain name'
                             if spelling.isidentifier() else '')
                _raise_located_syntax_error(
                    f'a double-quoted string is never a functor (ISO 6.3.3): '
                    f'write {single_quoted}(...) for the atom{bare_hint}',
                    call.func, transformer._source_lines,
                    transformer._filename)
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
            # An assertz'd rule head has the same silently-never-matches
            # cons failure mode as a module-level one — lint the raw head
            # before it is transformed.
            if isinstance(head_ast, Call):
                _warn_cons_bar_head(head_ast.args, head_ast.keywords,
                                    compare, transformer._source_lines)
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
        """A literal is a term directly — except a text literal, which is an
        ATOM or a STRING depending on how it was quoted (spec §7).

        ``'foo'`` is an atom in every mode; ``"foo"`` is an atom under
        ``-double_quotes(atom)`` (today's default) and a string under
        ``-double_quotes(chars)``.  An atom is the arity-0 cell
        ``("foo",)``; a string is the ``str`` itself.

        The quote character is not in the AST, so it comes from the file's
        quote map (``quote_map.py``), keyed by position.  A SYNTHETIC
        ``Constant`` — one the compiler built rather than read — has no
        position, so the map answers ``None``, which reads as "an atom":
        every compiler-built text literal is a spelling.

        The map is consulted UNCONDITIONALLY for a text literal, including
        under ``reify``: the mixed-quote-styles ``SyntaxError`` it can raise
        is a well-formedness rule about the source, not a compilation
        choice, so it fires wherever the source is read.

        Everything else (int, float, bytes, bool, ``None``, Ellipsis) is
        returned unchanged; ``b"…"`` is checked as ``bytes`` here, before
        the map is reached, because the codes model is quote-insensitive.
        """
        value = constant.value
        if type(value) is str:
            quote = _quote_of_positioned(transformer, constant)
            # A DCG terminal literal is a char sequence to consume, not an
            # atom — see ``_dcg_body_ast``'s Constant case.  The lookup above
            # still runs: it is unconditional (the mixed-quote-styles
            # ``SyntaxError`` is a rule about the SOURCE), and only the
            # ANSWER is exempt.
            if getattr(constant, "_dcg_terminal_text", False):
                return constant
            if quote == '"' and transformer._double_quotes_mode == "chars":
                return constant                     # a string
            if value == NIL_SPELLING:
                # Fix round 1, item 2 (operator-ruled 2026-09-07): a
                # source-written ``'[]'`` IS the empty list, as it is in ISO
                # and in Scryer.  ``atoms.mint`` makes the same substitution
                # at runtime and the two must agree -- a ``("[]",)`` cell
                # would compare unequal to the ``[]`` every other path
                # produces, and ``sort([[], '[]'], L)`` would keep two
                # elements.  A LIST cannot be a Python ``Constant`` (it is
                # mutable and does not marshal into ``co_consts``), so this
                # emits a list DISPLAY, which also gives a fresh list per
                # evaluation -- what a mutable value requires.
                return replace(List(elts=[], ctx=load), constant)
            return replace(Constant(value=(sys.intern(value),)), constant)
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
        # A truth-value alias in key position resolves to whatever its canonical
        # spelling resolves to, or ``{true: 1}`` and ``{True: 1}`` would build
        # dicts that do not unify.  ``true``/``false`` are ``Constant`` keys like
        # the literals they alias; ``undefined`` is rewritten to ``Undefined``
        # and then takes the ordinary key path below, unchanged.
        if isinstance(key, Name) and key.id in _TRUTH_ALIASES:
            aliased = _TRUTH_ALIASES[key.id]
            if aliased in _BOOL_ALIAS_VALUES:
                return replace(Constant(value=_BOOL_ALIAS_VALUES[aliased]), key)
            key = replace(Name(id=aliased, ctx=key.ctx), key)
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
        visited = transformer.visit(key)
        if isinstance(visited, List) and not visited.elts:
            # The NIL key (fix round 2, item 2, operator-ruled 2026-09-07).
            # ``'[]'`` in key position is the atom ``'[]'``, which IS the
            # empty list, and ``visit_Constant`` emits a list display for it
            # -- unhashable, so the dict literal blew up with a raw
            # ``TypeError`` at construction.  A bare ``{[]: 1}`` reaches here
            # as an empty ``List`` node too.  The empty TUPLE is the same
            # term and is hashable, so it is the canonical key form
            # (``atoms.NIL_KEY``); ``DictTerm`` normalises every other nil
            # spelling onto it, so nothing downstream can tell them apart.
            return replace(Tuple(elts=[], ctx=load), key)
        return visited

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
            f"use {ITE_NAME}(COND, THEN, ELSE) instead"
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
            logic_var_refs=transformer._logic_var_refs,
            constants=transformer.constants,
            filename=transformer._filename,
            reify=transformer._reify,
            hidden_atoms=transformer._hidden_atoms,
            module_name=transformer._module_name,
            declared_functors=transformer._declared_functors,
            atom_functor_sites=transformer._atom_functor_sites,
            quote_map=transformer._quote_map,
            double_quotes_mode=transformer._double_quotes_mode,
        )
        lambda_transformer.seen_vars = transformer.seen_vars.copy()
        # Shared object (not a copy): occurrences inside the lambda body
        # count toward the enclosing clause's singleton lint.
        lambda_transformer.var_occurrences = transformer.var_occurrences

        logic_var_params = [p for p in param_names if _is_logic_var_name(p)]
        # A parameter's binding is itself an occurrence — without this, a
        # param referenced exactly once in the body reads as count 1 (a
        # false-positive singleton warning: it's genuinely bound-and-used,
        # 2 real occurrences) and a param never referenced in the body
        # never appears in the Counter at all (a false-negative: a truly
        # inert binding that should warn). See ClausalSingletonWarning.
        for param in logic_var_params:
            transformer.var_occurrences[param] += 1
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
        # ISO/XSB truth-value spellings.  ``true``/``false`` become the very
        # ``Constant`` a literal ``True``/``False`` produces, so goal position
        # (unit / ``Fail``), head position, indexing and the Prolog bridges all
        # behave identically with no second spelling to teach them.
        # ``undefined`` folds into ``Undefined`` and then takes the ordinary
        # injected-builtin path below.  See ``_TRUTH_ALIASES``.
        if identifier in _TRUTH_ALIASES:
            identifier = _TRUTH_ALIASES[identifier]
            if identifier in _BOOL_ALIAS_VALUES:
                return replace(Constant(value=_BOOL_ALIAS_VALUES[identifier]), name)
        # Declared or imported constant: a module global holding a ground
        # value, bound before any clause statement executes. A plain Name
        # load embeds the value in the clause term — indexing sees the
        # literal, no Var is involved.
        if identifier in transformer.constants:
            return replace(Name(id=identifier, ctx=load), name)
        if _is_constant_name(identifier):
            _raise_undeclared_constant(
                identifier, name, transformer._source_lines,
                transformer._filename)
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
            transformer.var_occurrences[identifier] += 1
            transformer._logic_var_refs.setdefault(
                identifier, getattr(name, "lineno", 0))
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
        # Atom: declared in -module(...)/-private([...]).  Atoms are global
        # by spelling (design doc §1b/§5, R2 — no per-module identity, no
        # minted class): emit a compile-time str Constant directly rather
        # than a Name load that used to resolve a module-local class in
        # ``module_dict``.  Declaration only matters for STRICTNESS (this
        # name is never collected into ``_bare_atom_refs`` below, so
        # ``-strict_atoms``/the default-strict mode never flags it as
        # undeclared) — see ``_handle_module_directive``/
        # ``_handle_private_directive`` (no longer mint a zero-field class)
        # and ``compiler_v2._process_declarations`` (binds the plain str
        # into ``module_dict`` so ``-import_from`` of a declared atom still
        # works).  The truth-value spellings (``true``/``false``/
        # ``undefined``) are NOT atoms — the ``_TRUTH_ALIASES`` fold above
        # intercepts them first, ahead of this branch.
        # Hidden atom (P3-1 Task 6, ``-hide``, §1a/§1b R1): checked BEFORE
        # the general ``atoms`` membership below so a hidden spelling
        # substitutes the compiler-mangled Constant instead of the plain
        # one.  ``_hidden_atoms`` is per-file transformer state (never
        # populated from another module's declarations), so any match here
        # is by construction a reference from WITHIN the owning module —
        # every such reference compiles to the SAME interned mangled str
        # (``clausal.logic.atoms.mangle``), so they unify with each other;
        # a different module's bare use of the same spelling never reaches
        # this branch and resolves to the plain global atom instead (§1b:
        # "other modules simply can't spell it").
        # THE FLIP (2026-09-06-atoms-as-cells-strings §5.1): the emitted
        # Constant is the arity-0 CELL ``("bar",)``, not the bare spelling —
        # a bare ``str`` is a string now.  A tuple of a str folds into
        # ``co_consts`` and is marshal-clean, so the ``.pyc`` carries it
        # (verified; §5.2).  The constant unmarshalled from a cache is not
        # the ``mint``ed instance, which is fine: nothing may compare an
        # atom by identity.
        if identifier in transformer._hidden_atoms:
            return replace(
                Constant(value=(mangle(transformer._module_name, identifier),)),
                name,
            )
        if identifier in transformer.atoms:
            return replace(Constant(value=(sys.intern(identifier),)), name)
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
        # A slice subscript would flow through as a raw ``ast.Slice`` inside
        # the LoadSubscript and only die much later — an internal
        # NotImplementedError out of terms_to_ast, with no source line.
        # Refuse it here, by name, like the method-call form and ``:=``.
        if isinstance(subscript.slice, Slice):
            _raise_located_syntax_error(
                f"a slice subscript `{unparse(subscript)}` is not supported "
                f"in a clause body: a Clausal list is a term with no slice "
                f"evaluation rule. Use nth0/3 to take one element, or "
                f"take/3, drop/3 or split_at/4 for sublists.",
                subscript, transformer._source_lines, transformer._filename)
        return node_ast(
            "LoadSubscript",
            subscript,
            object=transformer.visit(subscript.value),
            index=transformer.visit(subscript.slice),
        )

    def visit_Tuple(transformer, tuple_expr):
        if type(tuple_expr.ctx) != Load:
            # Backstop: the one legal Store-context tuple surface (a
            # comprehension loop target) is refused by name in
            # ``_visit_comprehension`` before this is reached; anything else
            # that stores into a tuple has no clause-body meaning either, and
            # used to die here as a bare AssertionError with no message.
            _raise_located_syntax_error(
                f"a tuple assignment target `{unparse(tuple_expr)}` is not "
                f"supported in a clause body.",
                tuple_expr, transformer._source_lines, transformer._filename)
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
        # A comprehension in a clause body is inert term structure — nothing
        # iterates it, so nothing ever binds its loop target.  A declared
        # (lowercase) loop atom and the anonymous ``_`` are fine: they resolve
        # like any other term.  A logic-variable target is never meaningful
        # and, left alone, dies at import as a bare ``NameError`` with no
        # line; a tuple target died as a bare AssertionError in visit_Tuple.
        # Refuse both by name, pointing at the working spelling.
        # Reify mode keeps the logic-variable target: reflection models the
        # shape (the renderer round-trips `[x for X in L]`) even though the
        # compiler refuses it.
        target = generator_clause.target
        if (not transformer._reify and isinstance(target, Name)
                and target.id != "_" and _is_logic_var_name(target.id)):
            _raise_located_syntax_error(
                f"the comprehension loop variable `{target.id}` is a logic "
                f"variable, but a comprehension in a clause body is inert "
                f"term structure — nothing iterates it or binds "
                f"`{target.id}`. Use findall/3 to collect a goal's "
                f"solutions; for an inert comprehension term, declare a "
                f"lowercase loop name instead (e.g. -private([...])).",
                target, transformer._source_lines, transformer._filename)
        if isinstance(target, Tuple):
            _raise_located_syntax_error(
                f"a tuple loop target `for {unparse(target)} in ...` is not "
                f"supported in a clause-body comprehension — a comprehension "
                f"here is inert term structure that iterates nothing. Use "
                f"findall/3 with a compound template to collect a goal's "
                f"solutions.",
                target, transformer._source_lines, transformer._filename)
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


def _predicate_export_spec(node):
    """``name/arity`` in a ``-module``/``-private`` export list → (name, arity).

    P3-2 Task 2, ruling R6b.  Post-flip a field-carrying export entry
    (``verdict(OUTCOME, CITES)``) declares a DATA functor: it binds its
    interned spelling and its references compile to cells.  That leaves the
    "vocabulary module" idiom — export a PREDICATE here, supply its clauses in
    a downstream module — with no way to say so, since a declaration-only
    predicate is locally indistinguishable from data.

    The ISO export spelling is that way to say it: module exports in ISO
    Prolog ARE ``name/arity``, which is the compatibility direction this whole
    program serves.  Such an entry means "predicate export; clauses may live
    elsewhere" — the class is minted exactly as before the flip, no
    functor-signature registry entry is emitted, and the binding stays a
    class, which is all the binding-shape rule needs to keep treating every
    reference to it as a predicate.

    Returns ``None`` for any other node shape, so the caller falls through to
    its existing branches.  Same node shape ``_parse_pred_arity_args`` accepts
    for ``-dynamic``/``-table``/``-discontiguous``/``-shallow``.
    """
    if (
        isinstance(node, BinOp)
        and isinstance(node.op, Div)
        and isinstance(node.left, Name)
        and isinstance(node.right, Constant)
        and isinstance(node.right.value, int)
        and node.right.value >= 0
    ):
        return node.left.id, node.right.value
    return None


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
            if 'fib' not in globals():
                raise NameError
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

    P3-1 Task 2 (§1b/R2): a bare atom no longer mints a class at all — an
    earlier file's auto-accepted or declared atom of this exact spelling
    sits in ``predicate_builtins``/this module's globals as the ATOM of
    that spelling.  That shape gets the same re-raise-and-mint treatment as
    the old arity-mismatched class: an atom placeholder of the SAME spelling
    is exactly as safe to override as the old 0-arity class was, and for the
    same reason (Phenomenon A — an atom name and an N-arity predicate of the
    same spelling can coexist across files; the predicate wins in the file
    that actually declares it).  A binding that is NOT that atom (some
    unrelated user value) is left alone, same as any other
    non-``PredicateMeta`` binding.

    THE FLIP (2026-09-06-atoms-as-cells-strings) changed what that atom
    placeholder LOOKS like: it is the arity-0 cell ``('bar',)``, not the
    ``str`` ``'bar'``, so the guard tests the cell.  Without the update the
    seeded atom survived, and the very next statement — the fact
    ``bar(1),`` — called it: ``TypeError: 'tuple' object is not callable``
    at load, in any process where some EARLIER module had declared ``bar``
    as an atom.

    The guard is deliberately narrowed to ``isinstance(.., PredicateMeta)``:
    a non-``PredicateMeta`` binding of the same name (e.g. a user-defined
    ``def Foo(...)`` in the .clausal file) is left alone and the predicate
    block is skipped.  Clobbering a non-``PredicateMeta`` value would
    silently destroy user code; failing loudly later (when the clause body
    tries to use ``Foo`` as a predicate) preserves the pre-Phase-2 behavior
    for that edge case.

    "Bound" means bound in the MODULE dict, probed via ``globals()``
    membership.  A bare-name probe would fall through to ``__builtins__``,
    so a head named after a Python builtin (``reversed``, ``sorted``, …)
    read as "already bound", was skipped by the guard above, and the head
    call then invoked the real builtin — a load-time ``TypeError`` naming
    neither the predicate nor the cause.  The user never bound those names,
    so the left-alone rule does not apply to them: they mint normally.
    """
    fields_tuple = repr(tuple(field_names))
    lines = [
        "try:",
        f"    if {functor_name!r} not in globals():",
        "        raise NameError",
        f"    if isinstance({functor_name}, PredicateMeta) and getattr(",
        f"            {functor_name}, '_fields', None) != {fields_tuple}:",
        "        raise NameError",
        # The seeded-pool ATOM placeholder.  ``type(...) is tuple`` FIRST:
        # the name may be bound to anything the user put there, and a value
        # with a broadcasting ``__eq__`` (a numpy array, a pandas frame)
        # would raise at LOAD time on the bare ``==`` — the isinstance
        # short-circuit the pre-flip ``isinstance(.., str)`` guard had.
        f"    if type({functor_name}) is tuple and "
        f"{functor_name} == {(functor_name,)!r}:",
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


def _make_atom_str_assign_ast(atom_name, source, value=None):
    """Generate a guarded statement binding a declared atom's SPELLING at
    the ``-module``/``-private`` directive's OWN position in the generated
    code (P3-1 Task 2, §1b/R2).

    *value* defaults to ``atom_name`` itself (the ordinary global-atom
    case).  P3-1 Task 6 (``-hide``) passes the atom's MANGLED spelling
    instead — binding the bare Python name, in THIS module's own
    namespace only (never the process-wide ``predicate_builtins`` pool),
    to the mangled str.  This is what makes a hidden atom used as a
    dict-literal key (``{secret: 1}``, resolved eagerly by
    ``import_hook._make_intern_atom``'s ``$intern_atom`` — see below) see
    the correctly mangled value instead of tripping the undeclared-atom
    strict check or, worse, silently registering the BARE spelling.

    Bare atoms mint no class any more, so at first glance the declaration
    site needs no exec-time statement at all — ``compiler_v2.
    _process_declarations`` binds ``module_dict[name] = name`` AFTER the
    whole file has exec'd, which is enough for every ordinary reference
    (they compile to a literal ``Constant`` now, not a lookup).  But one
    consumer runs mid-exec, at the directive's own file position, and reads
    ``module_dict`` directly: a dict-literal atom key (``{foo: 1}``) is
    resolved by ``import_hook._make_intern_atom``'s ``$intern_atom`` helper
    EAGERLY, because dict literals build during ``exec`` — before
    ``_process_declarations`` (or even ``_process_bare_atom_refs``) ever
    runs.  Without a statement here, ``-private([foo])`` followed later in
    the same file by ``{foo: 1}`` wrongly hits ``$intern_atom``'s
    undeclared-atom strict check, even though ``foo`` genuinely is
    declared — a real regression (not a ruled inversion), caught via
    ``tests/test_dict_set_compiler.py``.

    Generated code (example for ``foo``)::

        if not isinstance(globals().get('foo'), PredicateMeta):
            foo = $mint('foo')

    The guard mirrors ``_make_functor_class_ast``'s spirit: a name already
    bound to a genuine ``PredicateMeta`` (a real predicate, minted by an
    earlier clause/import in this same file) is left alone rather than
    clobbered by the atom placeholder; any other existing value (unbound,
    or a stale atom from the process-wide ``predicate_builtins`` preseed) is
    safely overwritten with this atom's own spelling.

    THE FLIP (2026-09-06-atoms-as-cells-strings §9.3): the RHS is
    ``$mint(spelling)`` — the module attribute ``mod.foo`` is the atom CELL
    ``("foo",)`` with an interned slot 0, not the bare spelling (a bare
    ``str`` is a string now).  ``$mint`` is an injected runtime builtin
    (``INJECTED_RUNTIME_BUILTINS``); a ``$`` name cannot be spelled in
    Python source, so the assignment's RHS is built as an AST node and
    swapped in after ``parse``.
    """
    if value is None:
        value = atom_name
    lines = [
        f"if not isinstance(globals().get({atom_name!r}), PredicateMeta):",
        f"    {atom_name} = None",
    ]
    tree = parse("\n".join(lines))
    block = tree.body[0]
    assign = block.body[0]
    assign.value = Call(
        func=Name(id="$mint", ctx=load),
        args=[Constant(value=value)],
        keywords=[],
    )
    for node in walk(block):
        copy_location(node, source)
    return block


def _make_functor_signatures_update_ast(entries, source):
    """Generate a module-level update to the functor-signature registry.

    *entries* is a list of ``(functor_name, field_names)`` pairs -- the same
    tuple shape ``-module``/``-private`` already accumulate into their
    ``exports_info``/``private_info`` lists for the pipeline-split
    ``ModuleAST``.  Predicates are included alongside data functors
    (harmless: the data/predicate split is decided by binding shape --
    whether the functor has clauses -- not by anything this registry
    records).

    ``globals().setdefault(KEY, {}).update({...})`` rather than a plain
    ``KEY = {...}`` assignment: a file may carry more than one ``-module``/
    ``-private`` directive (or an ``-import_from`` copying entries in
    between them -- see ``_make_import_signatures_update_ast``), and each
    directive's generated statement must ADD to the registry, not clobber
    an earlier one's entries.

    Returns ``None`` when *entries* is empty (an all-atom ``-module``/
    ``-private`` list has nothing to register).
    """
    if not entries:
        return None
    dict_text = ", ".join(
        f"{name!r}: {tuple(fields)!r}" for name, fields in entries
    )
    lines = [
        f"globals().setdefault({FUNCTOR_SIGNATURES_KEY!r}, {{}})"
        f".update({{{dict_text}}})",
    ]
    tree = parse("\n".join(lines))
    block = tree.body[0]
    for node in walk(block):
        copy_location(node, source)
    return block


def _make_import_signatures_update_ast(resolved_module, name_pairs, source):
    """Copy an ``-import_from``'s imported names' registry entries across.

    *name_pairs* is a list of ``(local_name, orig_name)`` pairs -- keyed by
    the LOCAL name (the identifier this file actually binds and calls),
    matching Python's own ``from X import a, b as a`` shadowing rule: two
    different originals bound to the same local name, last one wins, is a
    user mistake this mirrors rather than tries to fix.

    This can only run at RUNTIME, after the ``from resolved_module import
    ...`` statement immediately before it has executed and loaded the owner
    module -- ``_handle_import_from_directive`` runs at AST-rewrite time,
    before either module has executed, so it cannot read the owner's
    registry directly.  ``__import__(resolved_module, fromlist=[...])`` is
    the same mechanism ``from resolved_module import ...`` itself uses to
    reach the (by now already-loaded, already-registered) owner module
    object for a dotted path -- reused here (twice: the dict access and the
    membership test each need it) rather than binding a new name into the
    importer's namespace.

    A name with no entry in the owner's registry (a constant, an atom, or a
    functor the owner declared with no fields) is silently skipped -- the
    dict comprehension's ``if`` clause -- rather than treated as an error;
    only functor names ever have registry entries, and this list mixes them
    with every other kind of ``-import_from`` name.

    Returns ``None`` when *name_pairs* is empty.
    """
    if not name_pairs:
        return None
    pairs_text = repr({local: orig for local, orig in name_pairs})
    lines = [
        f"globals().setdefault({FUNCTOR_SIGNATURES_KEY!r}, {{}}).update("
        f"{{_cs_local: __import__({resolved_module!r}, fromlist=['_'])."
        f"__dict__.get({FUNCTOR_SIGNATURES_KEY!r}, {{}})[_cs_orig] "
        f"for _cs_local, _cs_orig in {pairs_text}.items() "
        f"if _cs_orig in __import__({resolved_module!r}, fromlist=['_'])."
        f"__dict__.get({FUNCTOR_SIGNATURES_KEY!r}, {{}})}})",
    ]
    tree = parse("\n".join(lines))
    block = tree.body[0]
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
    available ``_dcg{N}`` intermediate variable index.
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
            #
            # THE FLIP (2026-09-06-atoms-as-cells-strings): a terminal
            # literal stays DESTRUCTURED AS CHARS regardless of quote style
            # and regardless of the file's ``-double_quotes`` mode — a
            # terminal is a sequence of tokens to consume, never an atom, so
            # ``>> ('hi')`` and ``>> ("hi")`` must keep meaning the same
            # thing.  ``_dcg_terminal_text`` tells ``visit_Constant`` to
            # leave this ``str`` alone (a string IS that char list now, so
            # the pre-flip behaviour survives verbatim).  Making the quote
            # style matter here is Plan 2's question, parked.
            terminal = Constant(value=value)
            terminal._dcg_terminal_text = True
            call = Call(
                func=Name(id="sequence", ctx=load),
                args=[
                    terminal,
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
            name in _ITE_NAMES and len(args) == 3
        ):
            # If-then-else: if_(cond, then, else).  The rebuilt node keeps
            # *name* rather than normalising to ``if_`` so that a deprecated
            # spelling still reaches the term pass's lint.
            cond, then_, else_ = args
            mid = f"_dcg{counter}"
            counter += 1
            cond_r, counter = _rewrite_dcg_body(cond, s_in, mid, counter, source)
            then_r, counter = _rewrite_dcg_body(then_, mid, s_out, counter, source)
            else_r, counter = _rewrite_dcg_body(else_, s_in, s_out, counter, source)
            result = Call(
                func=Name(id=name, ctx=load),
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
            fresh = f"_dcg{counter}"
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
                fresh = f"_dcg{counter}"
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
            fresh = f"_dcg{counter}"
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
                next_state = f"_dcg{counter}"
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
    return f"_edcg_{acc_name}_in{suffix}", f"_edcg_{acc_name}_out{suffix}"


def _edcg_pass_var(pass_name):
    """Return the variable name for an EDCG passed argument."""
    return f"_edcg_{pass_name}"


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


def _edcg_join_vars(acc_states, counter):
    """One fresh join variable per accumulator, plus the advanced *counter*.

    A branching construct (disjunction, if-then-else) makes every alternative
    end at the same variable so the body can carry on from a single place.
    That meeting point must be *fresh* rather than the accumulator's
    ``out_var``: ``out_var`` is the head's output, and closing to it mid-body
    would force the rest of the body to be a no-op.  ``_rewrite_edcg_rule``
    unifies the last link with ``out_var`` after the whole body is rewritten.
    """
    joins = {}
    for acc_name in acc_states:
        joins[acc_name] = f"_edcg_{acc_name}_{counter}"
        counter += 1
    return joins, counter


def _edcg_close_branch(rewritten, targets, final_states, source):
    """``And``-append ``final_in is target`` for each accumulator left open.

    *targets* maps accumulator name to the variable this alternative must end
    at (see :func:`_edcg_join_vars`); *final_states* is what rewriting the
    alternative reported.  An alternative that pushed fewer times than its
    siblings ends short, and unifying the two ends closes the gap.
    """
    closers = []
    for acc_name, target in targets.items():
        final_in, _ = final_states.get(acc_name, (target, target))
        if final_in != target:
            eq = Compare(
                left=Name(id=final_in, ctx=load),
                ops=[Is()],
                comparators=[Name(id=target, ctx=load)],
            )
            closers.append(replace(eq, source))
    if not closers:
        return rewritten
    return replace(BoolOp(op=And(), values=[rewritten] + closers), source)


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
        mid = f"_edcg_{acc_name}_{counter}"
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
            mid = f"_edcg_dcg_{counter}"
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

        case Call(func=Name(id=name), args=[cond, then_, else_], keywords=[]) if (
            name in _ITE_NAMES
        ):
            # If-then-else.  Must precede BOTH Call cases below: they match any
            # call, and until 2026-08-26 this case sat after them and so never
            # ran at all (todo/done/edcg-ite-case-is-unreachable.md).  Ordering it
            # first also makes ``if_`` a reserved control construct here, which
            # is what it already is in an ordinary clause body — TermTransformer
            # .visit_Call recognises it before any user predicate of that name.
            #
            # Condition and then-branch are one chain (in → cond → then → out);
            # the else-branch runs in → out, so a push made by a *failing*
            # condition never reaches it.  Mirrors _rewrite_dcg_body's ITE arm,
            # which threads the same three edges through s_in/mid/s_out.
            #
            # The rebuilt node keeps *name* rather than normalising to ``if_``
            # so that a deprecated spelling still reaches the term pass's lint.
            joins, counter = _edcg_join_vars(acc_states, counter)
            mid_states = {}
            for acc_name, (in_var, out_var) in acc_states.items():
                mid = f"_edcg_{acc_name}_{counter}"
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
                then_states[acc_name] = (cin, joins[acc_name])
            then_r, then_final, counter = _rewrite_edcg_body(
                then_, then_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
            then_r = _edcg_close_branch(then_r, joins, then_final, source)
            # Else branch starts from the original in — a push made by a
            # condition that failed must not be counted.
            else_states = {
                acc_name: (in_var, joins[acc_name])
                for acc_name, (in_var, _) in acc_states.items()
            }
            else_r, else_final, counter = _rewrite_edcg_body(
                else_, else_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
            else_r = _edcg_close_branch(else_r, joins, else_final, source)
            result = Call(
                func=Name(id=name, ctx=load),
                args=[cond_r, then_r, else_r],
                keywords=[],
            )
            # Both branches end at the join var, so the next body element
            # continues from there rather than restarting at in_var.
            joined_states = {
                acc_name: (joins[acc_name], out_var)
                for acc_name, (_, out_var) in acc_states.items()
            }
            return replace(result, source), joined_states, counter

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
                mid = f"_edcg_dcg_{counter}"
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
                mid = f"_edcg_dcg_{counter}"
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
            # Disjunction: each branch gets the same starting acc_states and
            # must independently close to the shared join var.
            joins, counter = _edcg_join_vars(acc_states, counter)
            rewritten = []
            max_counter = counter
            for elem in elements:
                branch_states = {
                    acc_name: (in_var, joins[acc_name])
                    for acc_name, (in_var, _) in acc_states.items()
                }
                r, branch_final, c = _rewrite_edcg_body(
                    elem, branch_states, dict(pass_states),
                    edcg_accs, edcg_passes, edcg_preds, counter, source
                )
                # Close any open accumulator chains in this branch.
                r = _edcg_close_branch(r, joins, branch_final, source)
                rewritten.append(r)
                if c > max_counter:
                    max_counter = c
            result = BoolOp(op=Or(), values=rewritten)
            # After the disjunction every accumulator is at its join var.
            joined_states = {
                acc_name: (joins[acc_name], out_var)
                for acc_name, (_, out_var) in acc_states.items()
            }
            return replace(result, source), joined_states, max_counter

        case UnaryOp(op=Not(), operand=inner):
            # NAF: doesn't affect accumulator state.
            # Create fresh out vars for the inner goal.
            inner_acc_states = {}
            for acc_name, (in_var, out_var) in acc_states.items():
                fresh = f"_edcg_{acc_name}_{counter}"
                counter += 1
                inner_acc_states[acc_name] = (in_var, fresh)
            inner_r, _, counter = _rewrite_edcg_body(
                inner, inner_acc_states, pass_states,
                edcg_accs, edcg_passes, edcg_preds, counter, source
            )
            result = UnaryOp(op=Not(), operand=inner_r)
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
                mid = f"_edcg_{ap_name}_{counter}"
                counter += 1
                full_args.append(Name(id=in_var, ctx=load))
                full_args.append(Name(id=mid, ctx=load))
                new_acc_states[ap_name] = (mid, out_var)
            else:
                # Caller doesn't use this accumulator — use fresh vars.
                fresh_in = f"_edcg_{ap_name}_{counter}"
                counter += 1
                fresh_out = f"_edcg_{ap_name}_{counter}"
                counter += 1
                full_args.append(Name(id=fresh_in, ctx=load))
                full_args.append(Name(id=fresh_out, ctx=load))
        elif ap_name in edcg_passes:
            # Pass: thread the value.
            if ap_name in pass_states:
                full_args.append(Name(id=pass_states[ap_name], ctx=load))
            else:
                # Caller doesn't have this pass — use fresh var.
                fresh = f"_edcg_{ap_name}_{counter}"
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
      head>>(body) DCG rule: rewrites to head(_dcg0,_dcg1)<-(rewritten body).
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
                 filename=None, interactive=False, reify=False):
        transformer._scope_depth = 0
        # Reflection models MORE than compiles — see TermTransformer._reify.
        transformer._reify = reify
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
        # P3-1 Task 6 (§1a/§1b, ruling R1): this file's OWN ``-module(...)``
        # name, set by ``_handle_module_directive`` the moment that
        # directive is seen.  ``-hide`` mangling is keyed by this identity
        # (there is no principled name to mangle into without one — a
        # ``-hide`` before any ``-module`` in the same file is a compile
        # error, see ``_handle_hide_directive``).
        transformer._module_name: str | None = None
        # Bare (unmangled) spellings declared ``-hide``-en in THIS file so
        # far.  A member here is ALSO added to ``transformer._atoms``
        # (strictness — see ``_handle_hide_directive``); this second set is
        # what ``visit_Name``'s atom branch checks FIRST to decide whether
        # to substitute the mangled ``Constant`` instead of the plain one.
        transformer._hidden_atoms: set[str] = set()
        # name -> the ``-hide(...)`` directive's own lineno that declared
        # it hidden -- used only to POSITION the hide/functor-collision
        # diagnostic (``_reject_hide_functor_collision``); every hidden
        # name in ``_hidden_atoms`` has an entry here.
        transformer._hidden_atom_decl_site: dict[str, int] = {}
        # Names bound by -constants (Task 5) so far in this file — a plain
        # module global holding a ground value, threaded into every
        # per-clause TermTransformer by _make_term_transformer. Task 6 also
        # adds imported constant names to this set.
        transformer._constants: set[str] = set()
        transformer._import_remap: dict[str, str] = {}
        # Local names bound by an -import_from seen SO FAR in this file. A
        # clause head for one of these binds by position rather than by field
        # name — see _emit_head_positionally.
        transformer._imported_functors: set[str] = set()
        transformer._module_items: list = []
        transformer._source_lines = source_lines
        # P3-3 strings program (spec §7).  ``ast`` erases the quote character,
        # so it is recovered ONCE per file from the token stream and threaded
        # into every per-clause TermTransformer by _make_term_transformer.
        # Without source lines (the REPL/IPython transform site, and any
        # programmatically built tree) there is no token stream to read and
        # the map is empty — every lookup then answers "unknown", which is
        # exactly the pre-strings behaviour.
        transformer._quote_map = build_quote_map(source_lines)
        # The ``-double_quotes`` mode in force at the CURRENT point in the
        # file.  Unlike the module-item directives (drained after the walk,
        # so they cannot govern only the literals below them) this is
        # position-sensitive state on the instance, the ``-allow_singletons``
        # shape.  ``atom`` is the engine default until the flip.
        transformer._double_quotes_mode = "atom"
        # When True (set by the REPL/IPython transform site), the file
        # defaults to loose auto-mint: visit_Module seeds an
        # ImplicitAtomsDeclaration unless the cell states its own mode.
        transformer._implicit_atoms_default = implicit_atoms_default
        # Set by the REPL/IPython transform site (same caller as
        # implicit_atoms_default, but a distinct axis): -constants has no
        # cross-cell persistence story, so ``_handle_constants_directive``
        # rejects the directive outright rather than half-working — see
        # roborev finding "constants crashes in IPython and forgets across
        # cells".
        transformer._interactive = interactive
        # Shared bare-atom collection sink — every per-clause TermTransformer
        # writes into this single set so the union is naturally accumulated.
        # ``visit_Module`` emits a final ``BareAtomRefs`` module item that
        # ``compiler_v2._process_bare_atom_refs`` consumes for auto-minting
        # (Phase 2 of GLOBAL_ATOMS_DEFAULT.md).
        transformer._bare_atom_refs: set[str] = set()
        # Fix round 2 (O1/O2): ``(name, lineno, dotted_or_None)`` per call
        # site where a declared ATOM was applied with arguments.  Drained by
        # ``visit_Module``; see ``TermTransformer._visit_call_func``.
        transformer._atom_functor_sites: list = []
        # name -> lineno of the first place a TermTransformer read that name as
        # a logic variable.  See _check_var_shaped_predicate_names.
        transformer._logic_var_refs: dict[str, int] = {}
        # EDCG declarations: populated by -edcg_acc, -edcg_pass, -edcg_pred directives.
        transformer._edcg_accs: dict[str, dict] = {}   # name → {val, in_, out, joiner_ast}
        transformer._edcg_passes: set[str] = set()      # set of pass names
        transformer._edcg_preds: dict[str, tuple[int, list[str]]] = {}  # pred → (visible_arity, [acc/pass names])
        # Per-file opt-out for ClausalSingletonWarning, set by -allow_singletons.
        transformer._allow_singletons = False

    def _reject_hide_functor_collision(transformer, functor_name,
                                       hide_lineno, functor_lineno,
                                       functor_kind):
        """Raise: *functor_name* is both ``-hide``-en (a hidden ATOM) and a
        predicate functor in the same file (P3-1 Task 6 fix round).

        An ordinary ``-private``/``-module`` ATOM entry peacefully loses to
        a same-named predicate at exec time (Phenomenon A,
        ``compiler_v2._process_declarations`` — "the predicate wins, do
        not clobber it back to a plain str").  A ``-hide``-en atom cannot
        use that same graceful resolution: its substitution
        (``visit_Name``) happens at COMPILE TIME, at every bare-spelling
        occurrence, INCLUDING a call-target position (``_visit_call_func``
        suppresses bare-atom *collection* but still runs the same
        hidden-atom substitution) — so a predicate call through this
        spelling compiles to calling a plain ``str`` (an opaque
        ``TypeError: 'str' object is not callable`` at the FIRST body-level
        call site, not the declaration), while any other occurrence of the
        bare spelling compiles to the mangled atom instead of dispatching
        the predicate at all. There is no runtime shape where one bare
        spelling correctly means both — reject at compile time, in EITHER
        declaration order (``-hide`` before the functor, or after).
        """
        hide_src = transformer._source_snippet(hide_lineno)
        functor_src = transformer._source_snippet(functor_lineno)
        where_hide = transformer._site(hide_lineno)
        where_functor = transformer._site(functor_lineno)
        where = (
            f"  -hide:     {where_hide}"
            + (f" — {hide_src}" if hide_src else "")
            + f"\n  {functor_kind}: {where_functor}"
            + (f" — {functor_src}" if functor_src else "")
        )
        raise SyntaxError(
            f"`{functor_name}` is both -hide'd (a module-private ATOM) and "
            f"a predicate functor in the same file\n{where}\n"
            f"A -hide'd atom's every bare-spelling occurrence compiles to "
            f"its mangled spelling — including a call-target position, "
            f"where calling the resulting str raises an opaque runtime "
            f"TypeError ('str' object is not callable) instead of "
            f"dispatching the predicate; a non-call occurrence silently "
            f"means the hidden atom instead of the predicate. One bare "
            f"spelling cannot mean both.\n"
            f"  remedy: rename the atom (edit the -hide entry and its "
            f"reference sites to a different spelling), or drop "
            f"`{functor_name}` from -hide if it was only ever meant as a "
            f"predicate name."
        )

    def _register_functor(transformer, functor_name, field_names, node, kind):
        """Record *functor_name*'s signature and where it was fixed.

        Every site that writes ``_seen_functors`` goes through here so the
        arity-conflict error can attribute the *first* declaration —
        AND (P3-1 Task 6 fix round) so a functor registered AFTER its name
        was already ``-hide``-en is caught here too (the mirror-image check
        lives in ``_handle_hide_directive``, for the OTHER declaration
        order — a functor registered BEFORE its name is ``-hide``-en).
        """
        if functor_name in transformer._hidden_atoms:
            transformer._reject_hide_functor_collision(
                functor_name,
                transformer._hidden_atom_decl_site.get(functor_name, 0),
                getattr(node, "lineno", 0),
                kind,
            )
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

    def _warn_singletons(transformer, term_transformer, expr_stmt):
        """Clause-end singleton check (see ClausalSingletonWarning)."""
        if transformer._allow_singletons:
            return
        import warnings  # noqa: PLC0415
        lineno = getattr(expr_stmt, "lineno", None)
        where = transformer._site(lineno) if lineno else "unknown site"
        for ident, count in term_transformer.var_occurrences.items():
            if ident.endswith("_UNUSED"):
                if count > 1:
                    warnings.warn(
                        f"{where}: variable `{ident}` is marked _UNUSED but "
                        f"occurs more than once in its clause",
                        ClausalSingletonWarning, stacklevel=2)
            elif count == 1:
                warnings.warn(
                    f"{where}: singleton variable `{ident}` — a variable "
                    f"occurring once binds nothing. Misspelling? Rename to "
                    f"`{ident}_UNUSED` (or `_`) if deliberate, or add "
                    f"-allow_singletons to the file",
                    ClausalSingletonWarning, stacklevel=2)

    def _arity_template(transformer, functor_name, fields):
        """The copyable ``name(FIELD, ...)`` template form for *fields*.

        Field names uppercased into logic-variable spelling; a name that
        already reads as a logic variable is left exactly as it is
        (uppercasing ``_x`` would print a name that mints a different field).
        """
        names = [n if _is_logic_var_name(n) else n.upper() for n in fields]
        return f"{functor_name}({', '.join(names)})"

    def _arity_conflict_remedy(transformer, functor_name, all_field_names,
                               prev_fields, decl_kind, decl_lineno):
        """The copyable template-form edit for an arity conflict.

        A Clausal declaration prefers the TEMPLATE form
        ``predicate_name(ARGUMENT_1, ..., ARGUMENT_N)`` over Prolog's ``name/N``
        notation, which leaves the argument positions to be guessed — so a
        message that says only "give them the same number of arguments" states
        the fault without showing the edit.  The offending head is in hand at
        the raise site (it is already printed on the ``clause:`` line), so
        print the declaration to paste.

        Argument-name synthesis is deliberately dumb: the head's own variable
        names uppercased, ``ARG_N`` for the positions that have none (a literal
        argument, an ``_``).  The value is the template form itself, not clever
        naming.  A field name that already reads as a logic variable is left
        exactly as it is — uppercasing ``_edcg_cnt_in`` would produce a name
        the compiler does not mint.

        The *where* half is tailored to the recorded ``decl_kind`` so the
        remedy never sends a reader to edit a ``-private`` list their file does
        not have, and never calls an earlier clause a declaration.  Directive
        kinds whose own syntax is not the template form (``-dynamic``, a
        ``-edcg_pred`` with no accumulators) take the neutral wording rather
        than a made-up rewrite of the directive.

        ``-edcg_pred``-minted ``_edcg_*`` accumulator fields suppress the
        template half entirely.  Those positions are compiler-minted and a
        source head never spells them; they appear in ``all_field_names`` only
        because the declared tuple is overlaid onto the head by POSITION, so
        the template would print names for arguments the author wrote as
        something else.  ``-edcg_pred`` also takes a VISIBLE arity, so
        "give the declaration the same arity" would move the hidden fields
        somewhere other than where the template shows them.  That case speaks
        visible arity instead, and both of its halves are edits that load.
        """
        def _template(fields):
            return transformer._arity_template(functor_name, fields)

        minted = [n for n in prev_fields if n.startswith("_edcg_")]
        if minted:
            visible = [n for n in prev_fields if not n.startswith("_edcg_")]
            fields = "field" if len(minted) == 1 else "fields"
            return (f"  remedy: {functor_name} is declared at VISIBLE arity "
                    f"{len(visible)} plus {len(minted)} compiler-minted "
                    f"accumulator {fields} that a source head does not write "
                    f"({', '.join(minted)}) — write every clause head as "
                    f"`{_template(visible)}`, or raise the visible arity at "
                    f"{transformer._site(decl_lineno)} to "
                    f"{len(all_field_names)}.")

        template = _template(all_field_names)
        surplus = len(all_field_names) - len(prev_fields)
        args = "argument" if surplus == 1 else "arguments"
        if prev_fields:
            drop = (f"drop the surplus {args} from every clause head of "
                    f"{functor_name} to match `{_template(prev_fields)}`")
        else:
            # A 0-arity declaration: the usual shape is a bare vocabulary atom
            # that a later clause head gave an argument to.
            drop = (f"drop the {args} from every clause head of "
                    f"{functor_name} if a bare value atom was intended")
        decl_site = {
            "-private declaration": "the -private([...]) list",
            "-module export list": "the -module(..., [...]) export list",
        }.get(decl_kind)
        if decl_site:
            return (f"  remedy: declare it as `{template}` in {decl_site} "
                    f"(an entry MAY carry arguments), or {drop}.")
        if decl_kind == "first clause":
            return (f"  remedy: the arity was fixed by an earlier clause at "
                    f"{transformer._site(decl_lineno)}, not by a declaration "
                    f"— write that head as `{template}` too, or {drop}.")
        return (f"  remedy: write every clause head as `{template}` and give "
                f"the declaration at {transformer._site(decl_lineno)} "
                f"({decl_kind}) the same arity, or {drop}.")

    def _check_head_signature(transformer, functor_name, all_field_names,
                              prev_fields, node, has_keywords=False):
        """Reject a clause head that cannot be built against the bound class.

        ``_seen_functors[functor_name]`` is exactly the tuple the guarded
        class block was minted with, so any head field name outside it would
        be emitted as a keyword the class does not have — the bare
        ``__init__() got an unexpected keyword argument 'arg_1'`` failure of
        ``todo/done/functor-field-name-mismatch-diagnostic.md``.

        The overwhelmingly common shape is an *arity* disagreement: a
        ``-module``/``-private`` declaration (or an earlier clause) fixes
        arity N and a later clause head supplies N+k arguments, whose surplus
        positions fall back to ``arg_N`` placeholder names.  A functor name
        has exactly one arity in Clausal, so that is a source error, not
        something to resolve.

        Positional UNDER-supply is the same error in the other direction
        (``todo/done/same-name-two-arities-silently-merge.md``): it used to
        build a partial head whose trailing fields became fresh ``Var()``s,
        silently absorbing what the author meant as ``foo/1`` into ``foo/2``
        as a ``foo(a, _)`` clause that matches calls nobody wrote.  Two
        shapes stay legal, because both spell the remainder explicitly
        rather than falling into it: a head with KEYWORD arguments
        (*has_keywords* — ``f(A=1)`` names exactly which fields it binds),
        and an ``-edcg_pred`` head at its VISIBLE arity (the compiler-minted
        ``_edcg_*`` accumulator fields are never written by a source head,
        so the deficit is measured against the visible fields only).
        """
        visible = [n for n in prev_fields if not n.startswith("_edcg_")]
        deficit = (not has_keywords
                   and len(all_field_names) < len(visible))
        unknown = [n for n in all_field_names if n not in prev_fields]
        if not unknown and not deficit:
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
        if deficit:
            n_missing = len(visible) - len(all_field_names)
            args = "variable" if n_missing == 1 else "variables"
            template = transformer._arity_template(functor_name, visible)
            raise SyntaxError(
                f"functor {functor_name}/{len(all_field_names)} conflicts "
                f"with the declaration of {functor_name}/{len(visible)} "
                f"in the same file\n{where}\n"
                f"A clause head is not a partial term: this "
                f"{len(all_field_names)}-argument head would be silently "
                f"padded with {n_missing} fresh {args} into a "
                f"{len(visible)}-argument clause that matches calls its "
                f"author never wrote. A functor name has exactly one arity "
                f"in Clausal.\n"
                f"  remedy: write this head at arity {len(visible)} to "
                f"match `{template}` — a position that really means "
                f'"anything" must be spelled `_` — or give the '
                f"{len(all_field_names)}-argument predicate a different "
                f"name."
            )
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
                f"of them.\n"
                + transformer._arity_conflict_remedy(
                    functor_name, all_field_names, prev_fields,
                    decl_kind, decl_lineno,
                )
            )
        raise SyntaxError(
            f"clause head for {functor_name}/{len(all_field_names)} names "
            f"field(s) {', '.join(unknown)} that {functor_name} does not "
            f"have\n{where}\n"
            f"{functor_name}'s class is minted with fields {declared}. "
            f"Use those names, or change the declaration to match."
        )

    def _check_var_shaped_predicate_names(transformer):
        """Reject a predicate whose name this file also reads as a variable.

        ALL-CAPS and leading-underscore identifiers are logic VARIABLES in
        Clausal (``_is_logic_var_name``).  Nothing stops such a name from also
        being a clause-head functor — the head's functor position is not
        routed through ``visit_Name`` — so ``P/2`` mints a class named ``P``
        quite happily.  Every *other* position disagrees:

            P(N, X) <- (N > 0, M is N - 1, P(M, X))
            P(N, X) <- (X is N)

        The body's ``P(M, X)`` is not a call to ``P/2``; ``visit_Name`` reads
        ``P`` as a fresh logic variable, so the clause lowers to a meta-call on
        an unbound ``Var`` AND the module-level walrus rebinds the global ``P``
        from the class to that ``Var``.  The guarded class block of
        ``_make_functor_class_ast`` deliberately leaves a non-``PredicateMeta``
        binding alone, so the SECOND clause head then calls the variable:

            TypeError: 'clausal.logic.variables.AttVar' object is not callable

        — a message that names neither ``P`` nor the naming convention that
        caused it.  Reverse the two clauses and there is no crash at all, just
        a body goal that silently means something else.  See
        ``todo/done/predicate-name-collides-with-unit-quantity-parser.md``.

        The check is deliberately the INTERSECTION, not "no var-shaped functor
        names".  Var-shaped heads that are never read as a variable in their
        own file work today and are used as shorthand throughout this repo's
        test snippets (``A(X) <- B(X)``, ``LP(X, Y, OBJ) <- …``); rejecting
        those would be a rename campaign for no defect.  It also leaves the
        ``VAR(Unit)`` quantity sugar (``eval_(N(Metre), D)``) untouched: ``N``
        there is a variable, not a clause head, so the sets do not meet.
        """
        clashes = sorted(
            set(transformer._seen_functors) & set(transformer._logic_var_refs)
        )
        if not clashes:
            return
        name = clashes[0]
        head_lineno = transformer._functor_decl_site.get(name, (0, ""))[0]
        var_lineno = transformer._logic_var_refs[name]
        why = (
            "a leading underscore marks a logic variable"
            if name.startswith("_")
            else "an ALL-CAPS name is a logic variable"
        )
        where = ""
        for label, lineno in (("predicate:", head_lineno),
                              ("read as a variable:", var_lineno)):
            if not lineno:
                continue
            snippet = transformer._source_snippet(lineno)
            where += (f"\n  {label} {transformer._site(lineno)}"
                      + (f" — {snippet}" if snippet else ""))
        raise SyntaxError(
            f"predicate name {name!r} is also read as a logic variable in this "
            f"file{where}\n"
            f"In Clausal {why}, so {name!r} outside a clause head is a fresh "
            f"Var, never a call to {name}. That makes {name}'s own clauses "
            f"unable to refer to it and overwrites the module binding, which "
            f"surfaces later as \"'AttVar' object is not callable\". Rename "
            f"the predicate to a non-variable name "
            f"(e.g. {_suggest_non_var_name(name)})."
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
        (``todo/done/functor-field-name-mismatch-diagnostic.md``).

        A positional head binds against whatever class the import supplied, so
        a module-local labelling can no longer contradict a foreign class.  A
        genuine disagreement is an ARITY disagreement, which still raises —
        with full attribution — from ``PredicateMeta.__call__``.

        Deliberately narrow on two axes:

        * ``prev_fields is not None`` means no guarded class block is emitted
          at this head.  When one *is* emitted (the functor's first clause) it
          re-mints the class to exactly the derived fields unless they already
          match, so the bound class is known here and keyword emission is
          precise.  That is the shape ``tests/fixtures/impord_atom_then_pred.clausal``
          pins: import a 0-arity vocabulary atom, then define a same-named
          predicate whose first clause re-mints over the import.
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
        bare-atom and logic-variable collection sinks and import-remap table.

        Centralised so every per-clause TermTransformer participates in the
        same Phase 2 (auto-mint) collection without each call site having
        to remember the plumbing.
        """
        return TermTransformer(
            atoms=atoms if atoms is not None else transformer._atoms,
            import_remap=transformer._import_remap,
            source_lines=transformer._source_lines,
            bare_atom_refs=transformer._bare_atom_refs,
            logic_var_refs=transformer._logic_var_refs,
            constants=frozenset(transformer._constants),
            filename=transformer._filename,
            reify=transformer._reify,
            hidden_atoms=transformer._hidden_atoms,
            module_name=transformer._module_name,
            declared_functors=transformer._seen_functors,
            atom_functor_sites=transformer._atom_functor_sites,
            quote_map=transformer._quote_map,
            double_quotes_mode=transformer._double_quotes_mode,
        )

    def _build_fact_statements(transformer, functor_name, orig_pos_args,
                               orig_kw_args, anchor, src_node, expr_stmt):
        """Build AST for a bodyless fact ``functor(args)`` (arity >= 0 via args).

        Shared by the trailing-comma fact case and the comma-optional
        declared-predicate case. Returns ``[functor_class_def?, define_stmt]``
        (a single statement when no class needs emitting).
        """
        _warn_cons_bar_head(orig_pos_args, orig_kw_args, src_node,
                            transformer._source_lines)
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
                functor_name, all_field_names, prev_fields, expr_stmt,
                has_keywords=bool(kwarg_field_names))

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
        transformer._warn_singletons(term_transformer, expr_stmt)

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
        prev_fields = transformer._seen_functors.get(functor_name)
        if prev_fields:
            # ``foo,`` after ``foo(a, b),`` used to pad into a foo(_, _)
            # clause matching EVERYTHING — the /0 instance of the same
            # under-supply refusal _check_head_signature now makes.
            transformer._check_head_signature(
                functor_name, [], prev_fields, expr_stmt)
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

        This is also the first point at which the file's clause-head functors
        and its logic-variable reads are both complete, so it is where
        ``_check_var_shaped_predicate_names`` can compare them.
        """
        result = transformer.generic_visit(module)
        transformer._check_var_shaped_predicate_names()
        transformer._settle_atom_functor_sites()
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

    def _settle_atom_functor_sites(transformer):
        """Decide every deferred "atom applied as a functor" candidate.

        Called from ``visit_Module`` once the walk is complete, which is the
        first moment ``_seen_functors`` holds every functor the FILE
        establishes -- including one whose only declaration is a clause
        BELOW the call site (fix round 2, O1: reading the walk-time set made
        the answer depend on statement order).

        A name that reached a functor declaration is simply accepted.  A name
        that did not, and is not imported, is refused here.  An imported one
        cannot be decided yet -- whether it is a functor is the OWNER's fact,
        and the owner has not executed -- so it travels to
        ``compiler_v2._check_atoms_applied_as_functors`` as a module item,
        carrying the message this site would have raised.
        """
        deferred = []
        for name, lineno, dotted in transformer._atom_functor_sites:
            if name in transformer._seen_functors:
                continue
            if dotted is None:
                raise SyntaxError(_atom_as_functor_message(
                    name, transformer._filename, lineno))
            owner = dotted.rsplit(".", 1)[0]
            deferred.append((name, _atom_as_functor_message(
                name, transformer._filename, lineno, owner=owner)))
        if deferred:
            transformer._module_items.append(
                AtomAppliedAsFunctorItem(sites=tuple(deferred)))

    def visit_FunctionDef(transformer, node):
        if is_template_func(node):
            return compile_template_func(node, transformer._quote_map)
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
                        raise _arrow_body_error(
                            head, transformer._source_lines,
                            transformer._filename)
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
                # Add DCG state args (_dcg0, _dcg1) to the head.
                dcg_in = replace(Name(id="_dcg0", ctx=load), src)
                dcg_out = replace(Name(id="_dcg1", ctx=load), src)
                orig_pos_args.append(dcg_in)
                orig_pos_args.append(dcg_out)

                # Rewrite DCG body to ordinary clause body AST.
                if pushback is not None:
                    # (head, [pb...]) >> body → body s_out is _dcg_pb,
                    # then _dcg1 is [pb..., *_dcg_pb]
                    body_raw, _ = _rewrite_dcg_body(
                        rhs, "_dcg0", "_dcg_pb", 2, src
                    )
                    pb_starred = replace(
                        Starred(value=Name(id="_dcg_pb", ctx=load), ctx=load), src
                    )
                    pb_list = replace(
                        List(elts=list(pushback) + [pb_starred], ctx=load), src
                    )
                    pb_unify = replace(Compare(
                        left=Name(id="_dcg1", ctx=load),
                        ops=[Is()],
                        comparators=[pb_list],
                    ), src)
                    body_expr_raw = replace(
                        BoolOp(op=And(), values=[body_raw, pb_unify]), src
                    )
                else:
                    body_expr_raw, _ = _rewrite_dcg_body(
                        rhs, "_dcg0", "_dcg1", 2, src
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

                _warn_cons_bar_head(orig_pos_args, orig_kw_args, expr_stmt,
                                    transformer._source_lines)
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
                        functor_name, all_field_names, prev_fields, expr_stmt,
                        has_keywords=bool(kwarg_field_names))

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
                transformer._warn_singletons(term_transformer, expr_stmt)

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
                if (
                    functor_name in transformer._seen_functors
                    # P3-1 Task 2 (§1b/R2): a declared atom never enters
                    # ``_seen_functors`` any more (no class minted, no
                    # arity reserved), but a bare ``flag`` statement with
                    # NO trailing comma is still the comma-optional
                    # bodyless-fact spelling when the name is a known
                    # declared atom -- without this it silently fell
                    # through to ``_guard_bare_call``'s harmless-looking
                    # "resolve and discard" no-op (the atom IS resolvable,
                    # so no error either) and the fact was never asserted.
                    or functor_name in transformer._atoms
                ):
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
        if name == "hide":
            return transformer._handle_hide_directive(args, expr_stmt)
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
        if name == "allow_singletons":
            return transformer._handle_allow_singletons_directive(args, expr_stmt)
        if name == "constants":
            return transformer._handle_constants_directive(args, expr_stmt)
        if name == "implicit_functors":
            return transformer._handle_implicit_functors_directive(args, expr_stmt)
        if name == "double_quotes":
            return transformer._handle_double_quotes_directive(args, expr_stmt)
        raise SyntaxError(
            f"Unknown directive: -{name}(...)  "
            f"(known directives: -module, -private, -hide, -dynamic, -discontiguous, "
            f"-table, -shallow, -import_from, -import_module, "
            f"-specialize, -edcg_acc, -edcg_pass, -edcg_pred, -translations, "
            f"-strict_atoms, -implicit_atoms, -allow_singletons, "
            f"-constants, -implicit_functors, -double_quotes)"
        )

    def _handle_double_quotes_directive(transformer, args, expr_stmt):
        """Process ``-double_quotes(atom|chars)`` — the strings-migration
        RATCHET.

        Step 2 of the strings/atom-tag program (canonical
        ``todo/strings-lost-in-the-atom-pivot-double-quotes-are-char-lists-2026-09-06.md``,
        ruling R-S4): a module that still relies on ``"..."`` denoting an
        ATOM declares ``-double_quotes(atom)`` so it keeps that meaning
        after the engine flips the default to ``chars`` (``"..."`` = a
        string unifying with its char list).  ``atom`` remains the engine
        default, so declaring it is still a no-op that states a dependency.

        THE FLIP (2026-09-06-atoms-as-cells-strings §7) makes ``chars`` real:
        below a ``-double_quotes(chars)`` directive a ``"..."`` literal
        compiles to the ``str`` — a STRING, which unifies with its char-atom
        list — while ``'...'`` stays an atom in every mode.  ``codes`` is
        refused: codes are spelled ``b"..."``.

        Both modes are file-scoped and POSITION-SENSITIVE: the mode governs
        the literals BELOW the directive, so it is instance state set during
        the walk (the ``-allow_singletons`` shape) rather than a module item
        drained after it.  ``visit_Constant`` reads it.

        Lifetime: the directive is deleted from the engine — and its use
        pinned as a load error — once the last module has dropped it.  It
        is not a compatibility flag; a string-bearing Prolog is a
        translation-layer concern.
        """
        if len(args) != 1 or not isinstance(args[0], Name):
            raise SyntaxError(
                "-double_quotes takes exactly one bare argument: "
                "`-double_quotes(atom)`"
            )
        mode = args[0].id
        if mode in ("atom", "chars"):
            transformer._double_quotes_mode = mode
            return replace(Pass(), expr_stmt)
        raise SyntaxError(
            f"-double_quotes({mode}): unknown mode; the accepted modes are "
            f"`atom` (the engine default: \"...\" is an atom) and `chars` "
            f"(\"...\" is a string — the list of its char atoms).  Codes are "
            f"spelled b\"...\" and have no mode."
        )

    def _declare_predicate_export(transformer, spec, entry_node, expr_stmt,
                                  statements, source_label):
        """Mint the class for a ``name/arity`` export entry (R6b).

        Mirrors the ``-dynamic`` treatment exactly — synthesized ``arg_i``
        field names, registered in ``_seen_functors`` and marked
        ``_directive_minted_functors`` so a later real clause in this file
        unseats the placeholder names in favour of its own head vars — because
        it is the same situation: a predicate that is declared here and may
        get its clauses somewhere else (or later).

        Deliberately emits NO functor-signature registry entry: the registry
        is the slot layout of a functor whose data compiles to cells, and this
        entry says the opposite.  The name is recorded as a
        ``predicate_export`` directive item so ``compiler_v2``'s Step 3 sees a
        PREDICATE (and therefore leaves the class alone) rather than a
        clause-free declaration it would rebind to a str.
        """
        functor, arity = spec
        if functor not in transformer._seen_functors:
            field_names = [f"arg_{i}" for i in range(arity)]
            transformer._register_functor(
                functor, field_names, entry_node, source_label)
            transformer._directive_minted_functors.add(functor)
            statements.append(
                _make_functor_class_ast(functor, field_names, expr_stmt)
            )
        transformer._module_items.append(
            DirectiveItem(name="predicate_export", specs=[(functor, arity)])
        )

    def _handle_module_directive(transformer, args, expr_stmt):
        """Process ``-module(Name, [export1(A,B), export2(X,Y)])`` directive.

        Extracts predicate signatures from the export list and emits
        ``_make_functor_class_ast`` definitions for each, pre-registering
        them in ``_seen_functors`` so that subsequent clauses use the
        declared field names rather than inferring them from the first clause.
        Bare (zero-arity) entries are ATOMS — global by spelling (§1b/R2) —
        and mint no class at all; only predicate (field-carrying) entries
        go through the class-minting path described above.

        Also emits a module-level ``__clausal_functor_signatures__ = {...}``
        registry update (``_make_functor_signatures_update_ast``) covering
        every field-carrying entry — predicates included, since the
        data/predicate split is decided by binding shape, not by this
        registry.  See ``clausal.logic.cells.FUNCTOR_SIGNATURES_KEY``.
        """
        statements = []
        exports_info = []  # for ModuleAST accumulation
        signature_entries = []  # (name, fields) pairs -- see _make_functor_signatures_update_ast
        # A10-F012: validate shape instead of silently dropping malformed
        # parts (every other directive raises on bad args).
        if len(args) < 1 or len(args) > 2 or not isinstance(args[0], Name):
            raise SyntaxError(
                "-module requires a bare name and an export list: "
                "-module(name, [ ... ]); got -module("
                f"{', '.join(unparse(a) for a in args)}) — a dotted "
                "package path is not a valid module name")
        module_name = args[0].id
        # P3-1 Task 6: record the declared module name for ``-hide`` keying
        # (must be set before any ``-hide`` directive later in this file —
        # see ``_handle_hide_directive``).
        transformer._module_name = module_name
        if len(args) == 2 and not isinstance(args[1], List):
            raise SyntaxError(
                "-module requires a name and an export list: "
                f"-module(name, [ ... ]); got -module({module_name}, "
                f"{unparse(args[1])}) — second argument must be a list")
        # args[1] should be the export list: ast.List of Call / Name nodes.
        if len(args) == 2:
            for export in args[1].elts:
                reserved = _reserved_truth_decl_name(export)
                if reserved is not None:
                    _raise_reserved_truth_decl(reserved, "-module")
                _pred_export = _predicate_export_spec(export)
                if _pred_export is not None:
                    transformer._declare_predicate_export(
                        _pred_export, export, expr_stmt, statements,
                        "-module export list (name/arity)")
                    continue
                if isinstance(export, Name) and _is_constant_name(export.id):
                    raise SyntaxError(
                        f"-module cannot list constant `{export.id}`: "
                        f"constants are public module globals — declare "
                        f"with -constants and import with -import_from; no "
                        f"export listing is needed")
                if isinstance(export, Name):
                    # Bare atom: global by spelling (§1b/R2) — no class is
                    # minted any more (no ``_register_functor``/
                    # ``_make_functor_class_ast`` statement).  Record the
                    # name for ``visit_Name``'s strictness check
                    # (``transformer.atoms``) and for the ModuleAST info
                    # ``compiler_v2._process_declarations`` reads (rebinds
                    # the plain str into ``module_dict`` after the whole
                    # file execs, so an ``-import_from`` of this atom still
                    # works).  A guarded assignment ALSO runs right here,
                    # at the directive's own position, so a mid-file
                    # exec-time consumer of ``module_dict`` (a dict-literal
                    # atom key via ``$intern_atom`` — see
                    # ``_make_atom_str_assign_ast``) sees the atom without
                    # waiting for post-exec processing.
                    transformer._atoms.add(export.id)
                    exports_info.append(export.id)
                    statements.append(
                        _make_atom_str_assign_ast(export.id, expr_stmt)
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
                    signature_entries.append((functor_name, field_names))
                    if functor_name not in transformer._seen_functors:
                        transformer._register_functor(
                            functor_name, field_names, export,
                            "-module export list")
                        statements.append(
                            _make_functor_class_ast(
                                functor_name, field_names, expr_stmt
                            )
                        )
                # Other item shapes are not pre-registered here — the
                # signature is taken from the first clause — but the list
                # itself is well-formed.  (The ISO ``foo/2`` arity form IS
                # handled, above: R6b, a PREDICATE export.)
        transformer._module_items.append(
            ModuleDeclItem(module_name=module_name, exports=exports_info)
        )
        sig_stmt = _make_functor_signatures_update_ast(signature_entries, expr_stmt)
        if sig_stmt is not None:
            statements.append(sig_stmt)
        if not statements:
            return replace(Pass(), expr_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _handle_private_directive(transformer, args, expr_stmt):
        """Process ``-private([atom1, pred(A, B), ...])`` directive.

        Declares atoms and predicate signatures that are internal to the
        module.  Has the same compilation effect as ``-module`` exports
        (atom registration for strictness, predicate functor class
        generation + pre-registration in ``_seen_functors``) but
        communicates that these names are not part of the module's public
        API.  Bare (zero-arity) entries are ATOMS — global by spelling
        (§1b/R2) — and mint no class; see ``_handle_module_directive``.
        """
        statements = []
        private_info = []  # for ModuleAST accumulation
        private_constants = []  # documentation-only constant listings
        signature_entries = []  # (name, fields) pairs -- see _make_functor_signatures_update_ast
        # A10-F012: a missing/malformed list (e.g. -private(helper(X))) used to
        # silently become a no-op, so the predicate signature was later
        # inferred from the first clause with no warning. Raise instead.
        if len(args) != 1 or not isinstance(args[0], List):
            raise SyntaxError(
                "-private requires a single list: "
                "-private([atom, pred(A, B), ...])")
        export_list = args[0]
        for item in export_list.elts:
            reserved = _reserved_truth_decl_name(item)
            if reserved is not None:
                _raise_reserved_truth_decl(reserved, "-private")
            _pred_export = _predicate_export_spec(item)
            if _pred_export is not None:
                # ISO ``name/arity``: a PREDICATE entry (R6b) — see
                # ``_declare_predicate_export``.
                transformer._declare_predicate_export(
                    _pred_export, item, expr_stmt, statements,
                    "-private declaration (name/arity)")
                continue
            if isinstance(item, Name) and _is_constant_name(item.id):
                # Documentation-only: visibility is advisory throughout, so a
                # constant listing just records "implementation detail" — no
                # class is minted (the constant stays a public module global,
                # which is why -module still rejects the same shape).
                private_constants.append(item.id)
                continue
            if isinstance(item, Name):
                # Bare atom: global by spelling (§1b/R2) — no class minted;
                # a guarded assignment runs at this position instead (mid-
                # file exec-time consumers, e.g. a dict-literal atom key);
                # see the matching comment in ``_handle_module_directive``.
                transformer._atoms.add(item.id)
                private_info.append(item.id)
                statements.append(
                    _make_atom_str_assign_ast(item.id, expr_stmt)
                )
            elif isinstance(item, Call) and isinstance(item.func, Name):
                functor_name = item.func.id
                field_names = [
                    arg.id if isinstance(arg, Name) else f"arg_{i}"
                    for i, arg in enumerate(item.args)
                ]
                field_names += [kw.arg for kw in item.keywords]
                private_info.append((functor_name, field_names))
                signature_entries.append((functor_name, field_names))
                if functor_name not in transformer._seen_functors:
                    transformer._register_functor(
                        functor_name, field_names, item,
                        "-private declaration")
                    statements.append(
                        _make_functor_class_ast(
                            functor_name, field_names, expr_stmt
                        )
                    )
            # Other item shapes are not pre-registered here; the list itself
            # is still well-formed.  (The ISO ``foo/2`` arity form IS handled,
            # above: R6b, a PREDICATE entry.)
        transformer._module_items.append(
            PrivateDeclItem(items=private_info, constants=private_constants))
        sig_stmt = _make_functor_signatures_update_ast(signature_entries, expr_stmt)
        if sig_stmt is not None:
            statements.append(sig_stmt)
        if not statements:
            return replace(Pass(), expr_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _handle_hide_directive(transformer, args, expr_stmt):
        """Process ``-hide([atom1, atom2, ...])`` directive (P3-1 Task 6,
        design doc §1a/§1b, ruling R1).

        Compiler-renames each listed atom into a reader-unwritable,
        module-scoped spelling (``clausal.logic.atoms.mangle`` — a single
        ``HIDDEN_SEP`` = US (0x1F) codepoint the surface reader refuses
        inside any atom token, R1-revised, 2026-09-05; was U+E000 under
        R1).  Every reference to the atom WITHIN the owning module
        compiles to the identical mangled ``Constant``
        (``visit_Name``'s atom branch, extended for this directive), so
        such references unify with each other exactly as an ordinary
        global atom's references do; a bare same-spelling reference in a
        DIFFERENT module resolves to the plain (unmangled, or
        differently-mangled) global atom instead and never unifies with
        this one — "other modules simply can't spell it" (§1b).

        **The guarantee is uniqueness + analysis soundness, NOT runtime
        security** (§1b, the Ciao/Python-name-mangling stance): the mangled
        spelling embeds the module name and is entirely deterministic, so
        ``atom_chars/2``/``atom_codes/2`` and similar character-level
        builtins CAN forge it from its known pieces (a module name and a
        bare atom spelling an attacker/author already knows). This is
        documented out-of-warranty, not blocked — the same stance §1b
        already takes for the general str-atom domain.

        **Requires a preceding ``-module(name, [...])`` in the same file.**
        The mangled spelling embeds the module name, so a ``-hide`` before
        any ``-module`` (or in a module-less file) has no principled
        identity to mangle into; rather than inventing an implicit/
        anonymous namespace (which would silently stop being module-scoped
        the moment the file gained a real ``-module`` later, or collide
        across separately-loaded module-less files), this is a compile-
        time ``SyntaxError`` — the simplest sound rule.

        Entries are bare atoms ONLY (unlike ``-private``, no ``foo(A, B)``
        predicate-signature shape): predicate names are already
        module-local through Python's own module/``PredicateMeta`` scoping
        — hiding is purely an ATOM concern.

        Each entry registers in ``transformer._atoms`` (so
        ``-strict_atoms``/the default-strict mode treats it as declared —
        a hidden atom counts as declared for strictness purposes even
        though its OWN mangled spelling is what actually compiles in) AND
        in ``transformer._hidden_atoms`` (consulted by ``visit_Name``
        ahead of the general ``atoms`` check, so the mangled Constant wins
        over the plain one).

        ``-private`` relationship: ``-private`` keeps its current
        (visibility-advisory, now-global-identity, §1b/R2) meaning
        unchanged by this task; ``-hide`` is the new, STRONGER tool
        (compiler-enforced uniqueness, not just documentation) — the two
        directives are independent and a name may appear in either, both,
        or neither. Full migration guidance is Task 8 (docs close-out).
        """
        if transformer._module_name is None:
            raise SyntaxError(
                "-hide requires a preceding -module(name, [...]) "
                "declaration in the same file: the mangled spelling "
                "embeds the module name, so there is no owning module to "
                "hide atoms into without one")
        if len(args) != 1 or not isinstance(args[0], List):
            raise SyntaxError(
                "-hide requires a single list of bare atoms: "
                "-hide([atom1, atom2, ...])")
        statements = []
        hidden_names = []
        for item in args[0].elts:
            reserved = _reserved_truth_decl_name(item)
            if reserved is not None:
                _raise_reserved_truth_decl(reserved, "-hide")
            if not isinstance(item, Name):
                raise SyntaxError(
                    "-hide entries must be bare atoms (predicates are "
                    "already module-local, so hiding does not apply to "
                    f"them): got `{unparse(item)}`")
            atom_name = item.id
            if _is_constant_name(atom_name):
                raise SyntaxError(
                    f"-hide cannot list constant `{atom_name}`: constants "
                    f"are public module globals — declare with -constants")
            hide_lineno = getattr(expr_stmt, "lineno", 0)
            if atom_name in transformer._seen_functors:
                # Mirror-image of the check in ``_register_functor`` — this
                # is the OTHER declaration order: a functor already
                # registered (an earlier clause, or an earlier -module/
                # -private declaration) before THIS -hide entry is
                # processed. See ``_reject_hide_functor_collision``.
                functor_lineno, functor_kind = (
                    transformer._functor_decl_site.get(atom_name, (0, "a "
                    "predicate declaration"))
                )
                transformer._reject_hide_functor_collision(
                    atom_name, hide_lineno, functor_lineno, functor_kind)
            mangled = mangle(transformer._module_name, atom_name)
            transformer._atoms.add(atom_name)
            transformer._hidden_atoms.add(atom_name)
            transformer._hidden_atom_decl_site[atom_name] = hide_lineno
            hidden_names.append(atom_name)
            statements.append(
                _make_atom_str_assign_ast(atom_name, expr_stmt, value=mangled)
            )
        transformer._module_items.append(HideDeclItem(items=hidden_names))
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

    def _handle_implicit_functors_directive(transformer, args, expr_stmt):
        """Process ``-implicit_functors`` — P3-2 Task 6, user ruling R7.

        Marker directive — no arguments.  Accepts the bare form
        ``-implicit_functors`` and the parenthesised ``-implicit_functors()``.

        Opts THIS file into open-world (OWA) functor construction: a
        keyword-free reference to ANY functor at ANY arity — declared or
        not, at its declared arity or not — compiles to a cell literal
        instead of the default-ON checks (``NameError`` for an undeclared
        functor, compile-time ``SyntaxError`` for an over-arity reference to
        a declared one; see
        ``clausal.logic.compiler.terms_to_ast.cell_signature_for_name``).
        Declared signatures in a flagged module become advisory for that
        shape of reference — §1 of
        ``implementation_plans/tagged-tuple-term-representation.md``: "any
        arity/functor constructs a cell".

        WHAT THE FLAG DOES NOT COVER:

        - **Keyword construction/matching still needs a real signature.**
          ``wibble(x=1)`` for an undeclared (or OWA-unknown-arity) ``wibble``
          is a compile-time error naming the functor and requiring a
          signature for keyword placement — there is no field-name list to
          place a keyword against otherwise. A functor WITH a matching
          registry signature still places keywords exactly as it does
          without the flag.
        - **A PREDICATE reference is unaffected.**  A name bound to a
          ``PredicateMeta`` class (a functor with clauses) keeps class/goal
          emission even under OWA — calling it is a goal, not data; see
          ``clausal.logic.compiler.terms_to_ast.cell_signature_for_name``'s
          own binding-shape rule, which this flag layers on top of rather
          than replaces.
        - **Atoms stay outside this flag's scope.**  A bare 0-arity
          reference is governed by ``-strict_atoms``/``-implicit_atoms``
          exclusively; this directive opens functor CONSTRUCTION, not atom
          vocabulary, and the two mechanisms compose independently (a
          flagged module can still be ``-strict_atoms`` and reject an
          undeclared bare atom).
        - **Head-side symmetry.**  The identical OWA rule applies to clause
          HEADS (``clausal.logic.compiler.head_match.head_to_match_pattern``'s
          ``Call(LoadName)`` branch), so a flagged module's clause heads
          over an unknown/advisory-arity functor pattern-match the cells its
          own bodies build — construction and matching answer alike, the
          phase's standing principle.

        Compiles to a module-level ``__clausal_implicit_functors__ = True``
        assignment (an ``Assign``, not a ``module_items`` entry) so the flag
        survives the ``.pyc``-cached load path — the compiler entrypoints
        read it back off the module namespace they are handed as
        ``globals_``/``lowering_globals()``.  See
        ``clausal.logic.cells.IMPLICIT_FUNCTORS_FLAG``.
        """
        if args:
            raise SyntaxError(
                "-implicit_functors takes no arguments: use bare "
                "`-implicit_functors` or `-implicit_functors()`"
            )
        return replace(
            Assign(
                targets=[Name(id=IMPLICIT_FUNCTORS_FLAG, ctx=store)],
                value=Constant(value=True),
            ),
            expr_stmt,
        )

    def _handle_allow_singletons_directive(transformer, args, expr_stmt):
        """Process ``-allow_singletons`` directive.

        Marker directive — no arguments.  Accepts the bare form
        ``-allow_singletons`` and the parenthesised ``-allow_singletons()``.
        Opts this file out of ``ClausalSingletonWarning`` entirely — a
        load-time-only flag, so no module item is emitted (nothing for
        ``compiler_v2`` to consume; the lint never runs past load).
        """
        if args:
            raise SyntaxError(
                "-allow_singletons takes no arguments: use bare "
                "`-allow_singletons` or `-allow_singletons()`"
            )
        transformer._allow_singletons = True
        return replace(Pass(), expr_stmt)

    def _handle_constants_directive(transformer, args, expr_stmt):
        """Process ``-constants(_PI_ = 3.14159, _MAX_ = _PI_ * 2)``.

        Declarations arrive as keyword arguments on the directive call. Each
        lowers to ``<name> = $check_constant_ground('<name>', <rhs>)`` at
        module level, so the value is bound (and gated for groundness) before
        any clause statement executes; references are plain Name loads and the
        value lands inside clause terms — folding, without a Var anywhere.
        See implementation_plans/module-level-constants.md.

        Interactive sessions (IPython/REPL) reject this directive outright:
        each cell gets a fresh transformer, so ``_constants`` is forgotten
        between cells — a constant declared in one cell would raise the
        undeclared-constant SyntaxError from the next. Half-working (bind in
        the declaring cell, forget it in the next) is worse than a clear
        refusal, so this is checked before any of the usual validation.
        """
        if transformer._interactive:
            raise SyntaxError(
                "-constants is not supported interactively yet; declare "
                "constants in a .clausal module and import it")
        call_node = expr_stmt.value.operand  # the Call under the USub
        # Bare ``-constants`` (no parens) hands a Name operand here, not a
        # Call — it has no ``keywords`` attribute at all. getattr (mirroring
        # -specialize's defence against the same shape) turns that into the
        # ordinary usage error below instead of an AttributeError.
        if args or not getattr(call_node, 'keywords', None):
            raise SyntaxError(
                "-constants takes name = value pairs: "
                "-constants(_PI_ = 3.14159, _MAX_ = 3)")
        statements = []
        for kw in call_node.keywords:
            ident = kw.arg
            if ident is None or not _is_constant_name(ident):
                raise SyntaxError(
                    f"-constants: {ident!r} is not a constant name — "
                    f"constants spell with exactly one leading and one "
                    f"trailing underscore, e.g. _PI_")
            if ident in transformer._constants:
                raise SyntaxError(
                    f"-constants: `{ident}` is already bound (earlier "
                    f"-constants or an import)")
            if ident[1:-1].endswith("_UNUSED"):
                # Decided edge (todo/done/module-level-constants-open-
                # questions.md #3): legal, but visually collides with the
                # singleton-suppression suffix.
                import warnings  # noqa: PLC0415
                warnings.warn(
                    f"-constants: `{ident}` ends in _UNUSED, which reads as "
                    f"the unused-variable marker; consider another name",
                    ClausalLintWarning, stacklevel=2)
            rhs = transformer._transform_constant_rhs(kw.value, ident)
            transformer._constants.add(ident)
            assign = replace(
                Assign(
                    targets=[replace(Name(id=ident, ctx=store), kw.value)],
                    value=replace(
                        Call(
                            func=replace(
                                Name(id="$check_constant_ground", ctx=load),
                                kw.value),
                            args=[replace(Constant(value=ident), kw.value),
                                  rhs],
                            keywords=[],
                        ), kw.value),
                ), expr_stmt)
            fix_missing_locations(assign)
            statements.append(assign)
            # Record (name, value) on $module for module_constant/3
            # reflection (docs/builtins.md). $module is ALREADY BOUND by
            # the time this statement executes (set before
            # exec_with_import_diagnostics runs — see _run_v2_pipeline
            # in import_hook.py) — but it is only a THROWAWAY placeholder
            # Module at this point
            # (compile_module below builds the real one afterward and
            # swaps it in); _run_v2_pipeline carries the registrations
            # across that swap (``logic_module.constants.update(
            # dummy_logic_module.constants)``) precisely because they land
            # here first. `ident` is already bound (by the Assign just
            # above) to the gated, frozen value.
            register = replace(
                Expr(value=replace(
                    Call(
                        func=replace(
                            Name(id="$register_module_constant", ctx=load),
                            kw.value),
                        args=[replace(Name(id="$module", ctx=load), kw.value),
                              replace(Constant(value=ident), kw.value),
                              replace(Name(id=ident, ctx=load), kw.value)],
                        keywords=[],
                    ), kw.value),
                ), expr_stmt)
            fix_missing_locations(register)
            statements.append(register)
        return statements if len(statements) > 1 else statements[0]

    def _transform_constant_rhs(transformer, node, ident):
        """Validate and return the Python AST for a -constants RHS.

        Grammar: scalar Constant, previously declared constant, declared
        atom, unary/binary arithmetic over those, a ``++`` escape (adjacent
        double UAdd) whose operand is emitted verbatim as Python, and —
        2026-08-25 — structured literals (list/tuple/set/dict) and functor
        calls, nested arbitrarily, mixing any of the above at any depth.

        Structured construction deliberately does NOT reuse
        ``_make_term_transformer()``/``TermTransformer.visit`` wholesale:
        that machinery is built for CLAUSE bodies, where a functor call or a
        set/tuple literal lowers to an uninstantiated ``pythonic_ast`` node
        (``Call``/``TupleLiteral``/``SetLiteral``) that only becomes a real
        term later, when ``compiler_v2`` walks the STATIC clause tree and
        generates the bytecode a predicate invocation runs. A -constants
        RHS has no such second compile pass — the emitted code here runs
        exactly once, directly, as an ordinary module-level statement — so
        this method instead emits AST that constructs the REAL runtime term
        directly on that one pass: a genuine ``list``/``tuple``, a real
        ``SetTerm``/``DictTerm`` (the same real construction
        ``TermTransformer.visit_Dict`` already uses for clause bodies), or a
        direct call to the already-bound functor class. This is exactly
        what ``clausal/logic/compiler/terms_to_ast.py``'s
        ``term_to_ast_expr`` generates for a clause body's compiled
        function — so the value built here is the identical shape, just
        built once instead of once per invocation.
        """
        if isinstance(node, Constant):
            return node
        if isinstance(node, Name):
            # ISO/XSB truth-value spellings fold the same way they do in
            # ordinary term position (visit_Name / _TRUTH_ALIASES) — a
            # -constants RHS is a term position too. Without this,
            # ``-constants(_B_ = true)`` raised "neither a previously
            # declared constant nor a declared atom" while the equivalent
            # ``-constants(_B_ = True)`` (and a dict KEY spelled ``true``,
            # via _transform_constant_dict_key) already worked — one
            # spelling of the same value should not be RHS-illegal while
            # the other is legal.
            if node.id in _TRUTH_ALIASES:
                aliased = _TRUTH_ALIASES[node.id]
                if aliased in _BOOL_ALIAS_VALUES:
                    return replace(Constant(value=_BOOL_ALIAS_VALUES[aliased]), node)
                return replace(Name(id=aliased, ctx=load), node)
            if node.id in transformer._constants or node.id in transformer._atoms:
                return node
            if node.id == "_" or _is_logic_var_name(node.id):
                _raise_constant_rhs_logic_var(
                    node.id, node, transformer._source_lines,
                    transformer._filename)
            raise SyntaxError(
                f"-constants: `{ident}` RHS references `{node.id}`, which is "
                f"neither a previously declared constant nor a declared atom")
        if (isinstance(node, UnaryOp) and isinstance(node.op, UAdd)
                and isinstance(node.operand, UnaryOp)
                and isinstance(node.operand.op, UAdd)):
            # ++expr: raw Python, load-time eval. The operand never passes
            # through visit_Name (same reason as _build_py_thunk_ast's
            # f-string/++ escapes elsewhere), so an undeclared constant
            # reference inside it would otherwise fall through to a raw
            # NameError at exec time instead of a located, load-time
            # SyntaxError. Declared-earlier constants (transformer._constants
            # at this point in the file) are legal here — by exec time they
            # are already-bound module globals. Legal as a structured RHS's
            # ELEMENT too (this branch is reached the same way whether
            # ``node`` is the whole RHS or an element/key/value/arg a
            # container branch below recursed into).
            for ident in _collect_constant_refs(node.operand.operand):
                if ident not in transformer._constants:
                    _raise_undeclared_constant(
                        ident, node, transformer._source_lines,
                        transformer._filename)
            return node.operand.operand
        if isinstance(node, UnaryOp):
            return replace(UnaryOp(op=node.op, operand=transformer.
                           _transform_constant_rhs(node.operand, ident)), node)
        if isinstance(node, BinOp):
            return replace(BinOp(
                left=transformer._transform_constant_rhs(node.left, ident),
                op=node.op,
                right=transformer._transform_constant_rhs(node.right, ident),
            ), node)
        if isinstance(node, List):
            elements = [transformer._transform_constant_rhs(e, ident)
                       for e in node.elts]
            return replace(List(elts=elements, ctx=load), node)
        if isinstance(node, Tuple):
            # A real Python tuple — the same construction
            # term_to_ast_expr gives a clause body's TupleLiteral (tuples
            # are immutable already; no freezing needed).
            elements = [transformer._transform_constant_rhs(e, ident)
                       for e in node.elts]
            return replace(Tuple(elts=elements, ctx=load), node)
        if isinstance(node, Set):
            elements = [transformer._transform_constant_rhs(e, ident)
                       for e in node.elts]
            return replace(
                Call(
                    func=replace(Name(id="SetTerm", ctx=load), node),
                    args=[replace(List(elts=elements, ctx=load), node)],
                    keywords=[],
                ), node)
        if isinstance(node, Dict):
            if any(k is None for k in node.keys):
                _raise_located_syntax_error(
                    f"-constants: `{ident}` RHS: dict-splat (**) is not "
                    f"supported in a structured constant",
                    node, transformer._source_lines, transformer._filename)
            keys = [transformer._transform_constant_dict_key(k, ident)
                   for k in node.keys]
            values = [transformer._transform_constant_rhs(v, ident)
                     for v in node.values]
            dict_ast = replace(Dict(keys=keys, values=values), node)
            return replace(
                Call(
                    func=replace(Name(id="DictTerm", ctx=load), node),
                    args=[dict_ast],
                    keywords=[make_keyword_node(
                        "_position", pos_ast(node), node)],
                ), node)
        if isinstance(node, Call):
            if not isinstance(node.func, Name):
                _raise_located_syntax_error(
                    f"-constants: unsupported RHS for `{ident}`: "
                    f"{unparse(node)}",
                    node, transformer._source_lines, transformer._filename)
            functor_name = node.func.id
            if (functor_name not in transformer._seen_functors
                    and functor_name not in transformer._imported_functors):
                _raise_located_syntax_error(
                    f"-constants: `{ident}` RHS calls `{functor_name}(...)`, "
                    f"which is not a declared functor above this "
                    f"-constants directive — declare it with -module/"
                    f"-private/-dynamic before -constants, or import it "
                    f"with -import_from/-import_module",
                    node, transformer._source_lines, transformer._filename)
            pos_args = [transformer._transform_constant_rhs(a, ident)
                       for a in node.args]
            kw_args = [
                replace(keyword(
                    arg=kw.arg,
                    value=transformer._transform_constant_rhs(kw.value, ident),
                ), kw)
                for kw in node.keywords
            ]
            # P3-2 Task 2 (THE FLIP): route the construction through
            # ``$constant_functor_term`` rather than calling the name
            # directly.  A declared DATA functor binds its interned spelling
            # (R6), not a class -- an IMPORTED one has no class in this
            # module at all -- so a direct call raised ``TypeError: 'str'
            # object is not callable`` from the -constants line.  The helper
            # decides at exec time on the same binding-shape rule the
            # compiler uses: a ``PredicateMeta`` binding is constructed, a
            # spelling becomes a cell placed against the signature registry.
            # See ``clausal.logic.constants.constant_functor_term``.
            return replace(
                Call(
                    func=replace(
                        Name(id="$constant_functor_term", ctx=load),
                        node.func),
                    args=[
                        replace(Constant(value=functor_name), node.func),
                        replace(List(elts=pos_args, ctx=load), node),
                        replace(
                            Dict(keys=[replace(Constant(value=kw.arg), kw)
                                       for kw in kw_args],
                                 values=[kw.value for kw in kw_args]),
                            node),
                        replace(
                            Call(func=replace(Name(id="globals", ctx=load),
                                              node),
                                 args=[], keywords=[]),
                            node),
                    ],
                    keywords=[]),
                node)
        _raise_located_syntax_error(
            f"-constants: unsupported RHS for `{ident}`: {unparse(node)}",
            node, transformer._source_lines, transformer._filename)

    def _transform_constant_dict_key(transformer, key, ident):
        """Transform a dict-literal KEY inside a structured -constants RHS.

        Mirrors ``TermTransformer._visit_dict_key``'s atom-key convention (a
        bare lowercase identifier key resolves to its interned atom, via
        ``$intern_atom`` — the same helper ordinary clause dict literals
        use) but routes everything else through ``_transform_constant_rhs``
        instead of the generic ``TermTransformer.visit`` — a logic-variable-
        shaped key must be a compile-time SyntaxError here, not a freshly
        minted Var, and a computed key must be materialized eagerly, not
        left as an uninstantiated node (see ``_transform_constant_rhs``'s
        docstring for why the generic term transformer isn't reused).
        """
        if isinstance(key, Name) and key.id in _TRUTH_ALIASES:
            aliased = _TRUTH_ALIASES[key.id]
            if aliased in _BOOL_ALIAS_VALUES:
                return replace(Constant(value=_BOOL_ALIAS_VALUES[aliased]), key)
            key = replace(Name(id=aliased, ctx=key.ctx), key)
        if (isinstance(key, Name) and key.id != "_"
                and not _is_logic_var_name(key.id)
                and key.id not in transformer._constants):
            transformer._bare_atom_refs.add(key.id)
            return replace(
                Call(
                    func=replace(Name(id="$intern_atom", ctx=load), key),
                    args=[replace(Constant(value=key.id), key)],
                    keywords=[],
                ), key)
        return transformer._transform_constant_rhs(key, ident)

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
        compiler's ``_inject_resolved_targets`` picks them up.

        Also emits a runtime copy of the imported names' functor-signature
        registry entries into this file's own registry (see
        ``_make_import_signatures_update_ast``), keyed by their LOCAL
        spelling.
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
                if _is_constant_name(local_name):
                    # Imported constant: the ImportFrom emitted below binds
                    # the owner's ground value as a module global here; use
                    # sites resolve through the constants branch of
                    # ``visit_Name`` (a plain Name load), not the predicate
                    # remap — so no ``_import_remap``/``_imported_functors``
                    # bookkeeping for this name.
                    if local_name in transformer._constants:
                        raise SyntaxError(
                            f"-import_from: `{local_name}` is already bound "
                            f"by an earlier -constants or import in this "
                            f"file; use alias({local_name}, _OTHER_)"
                        )
                    transformer._constants.add(local_name)
                    aliases.append(alias(name=local_name))
                    continue
                # Same unreachability as the ``alias(…)`` form below: a
                # var-shaped local binding is read as a logic variable by
                # ``visit_Name`` before the remap is ever consulted, so the
                # import can never be called.  Unlike a var-shaped *local*
                # clause head (which at least works head-only — see
                # ``_check_var_shaped_predicate_names``), an imported name
                # exists only to be called, so there is nothing to preserve.
                if _is_logic_var_name(local_name):
                    raise SyntaxError(
                        f"-import_from name {local_name!r} is a logic-variable "
                        f"name; a call to it is read as a variable, never as "
                        f"{module_path}.{local_name}. Import it under a "
                        f"non-variable alias: "
                        f"alias({local_name}, "
                        f"{_suggest_non_var_name(local_name)})"
                    )
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
                if _is_constant_name(orig_name) or _is_constant_name(local_name):
                    # Constant alias: both sides must be constant-shaped —
                    # an alias mixing a constant with a predicate name would
                    # otherwise silently pick one binding path or the other.
                    if not (_is_constant_name(orig_name)
                            and _is_constant_name(local_name)):
                        raise SyntaxError(
                            "constant imports must alias to a constant "
                            "name (alias(_PI_, _MYPI_))"
                        )
                    if local_name in transformer._constants:
                        raise SyntaxError(
                            f"-import_from: `{local_name}` is already bound "
                            f"by an earlier -constants or import in this "
                            f"file; use alias({orig_name}, _OTHER_)"
                        )
                    transformer._constants.add(local_name)
                    aliases.append(alias(name=orig_name, asname=local_name))
                    continue
                # A10-F017: a logic-var-shaped alias (e.g. ``T``) is
                # unreachable — visit_Name treats it as a variable before the
                # remap fires, so the call site later fails with a cryptic
                # NotImplementedError. Reject it here at the directive.
                if _is_logic_var_name(local_name):
                    raise SyntaxError(
                        f"-import_from alias {local_name!r} is a logic-variable "
                        f"name; use a non-variable alias: "
                        f"alias({orig_name}, "
                        f"{_suggest_non_var_name(local_name)})"
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
        # Copy the imported names' functor-signature registry entries into
        # this file's own registry, keyed by the LOCAL spelling (mirroring
        # Python's own ``from X import a, b as a`` shadowing rule: the
        # constant branches above also land here, harmlessly -- a name with
        # no registry entry in the owner is silently skipped, see
        # ``_make_import_signatures_update_ast``).
        name_pairs = [(a.asname or a.name, a.name) for a in aliases]
        sig_stmt = _make_import_signatures_update_ast(resolved, name_pairs, expr_stmt)
        if sig_stmt is None:
            return stmt
        return [stmt, sig_stmt]

    def _handle_import_module_directive(transformer, args, expr_stmt):
        """Process ``-import_module(dotted.module)`` directive.

        Emits a Python ``import dotted.module`` statement.  The module object
        lands in globals; qualified calls like ``mod.Pred(X_)`` are resolved
        at compile time via ``_inject_resolved_targets``.
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
        # args use _edcg_{name}_in, _edcg_{name}_out, _edcg_{name}.
        field_names = [f"arg_{i}" for i in range(visible_arity)]
        for ap_name in acc_pass_names:
            if ap_name in transformer._edcg_accs or ap_name == "dcg":
                field_names.append(f"_edcg_{ap_name}_in")
                field_names.append(f"_edcg_{ap_name}_out")
            elif ap_name in transformer._edcg_passes:
                field_names.append(f"_edcg_{ap_name}")

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
        # orig_pos_args already carries the appended _dcg0/_dcg1 state
        # args (bare Name nodes) — harmless to the cons lint, which only
        # fires on lists.
        _warn_cons_bar_head(orig_pos_args, orig_kw_args, expr_stmt,
                            transformer._source_lines)
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
