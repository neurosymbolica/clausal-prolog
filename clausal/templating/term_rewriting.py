from ast import *
from collections import Counter
from copy import deepcopy
import ast as _ast_module  # the star-import above hides the module itself
import keyword as _keyword_module  # `keyword` is ast.keyword here
import os as _os
import re
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
    CrossModeLiteralSites as CrossModeLiteralSitesItem,
    DoubleQuotesMode as DoubleQuotesModeItem,
    HeadFieldNames as HeadFieldNamesItem,
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
from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY, IMPLICIT_FUNCTORS_FLAG, CHARS_TAG
from clausal.logic.generated_names import dollar_name, has_twin

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


def runtime_name_ast(name, source):
    """A reference to a runtime-table class (a ``simple_ast`` node class, an
    injected runtime type) -- spelled through its ``$`` twin, so a user
    predicate of the same spelling can never shadow it (2026-09-09 ruling;
    see ``clausal/logic/generated_names.py``)."""
    return replace(Name(id=dollar_name(name), ctx=load), source)


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
        Call(func=runtime_name_ast(classname, source), args=[], keywords=keywords), source
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

#: The truth-value spellings that name a user predicate when APPLIED
#: (``true(X)``, ``false(X, Y)``): D40, ruled 2026-09-30.  true/0 and
#: false/0 stay the truth values (and the control constructs).
_APPLIED_TRUTH_NAMES = frozenset({"true", "false"})

# The reified if-then-else goal.  ``if_`` is canonical — lower-case like every
# other goal, trailing underscore to dodge the Python keyword, and the spelling
# the reified-conditional literature uses (Neumerkel & Kral's ``if_/3``, see
# docs/reified_ite.md).  ``If`` was the superseded spelling; it is now a
# load-time ERROR like any other TitleCase identifier, so no recogniser
# accepts it and there is no deprecation arm left to warn from.  The lint
# names the rename (``If`` -> ``if_``) rather than the ``++`` escape, even
# though ``If`` is also a seeded AST node class — see
# ``_TITLECASE_RENAMED_SPELLINGS``.
ITE_NAME = "if_"
_ITE_NAMES = frozenset({ITE_NAME})  # ``If`` is TitleCase: a load-time error, no arm

#: The test-clause predicate (``clausal.testing``): predicates are lowercase,
#: so it is ``test/1``.  ``Test/1`` is the superseded spelling, and a file
#: that spells it no longer LOADS — the TitleCase lint is an error — so
#: neither the runner's ``test/1`` union nor ``_warn_deprecated_test_spelling``
#: is reachable from source any more.  Both are retained only until the
#: downstream migration is done, because import lists may still name the old
#: spelling; the exit criterion is in
#: ``todo/remove-Test-1-spelling-union-after-migration-2026-09-10.md``.
TEST_NAME = "test"
TEST_DEPRECATED_NAME = "Test"

# Every spelling under which a ``.clausal`` file reaches the units module.
# Its old names — TitleCase ``Metre``/``SpeedOfLight``, American
# ``kilometer`` — are deprecated aliases of ``metre``/``speed_of_light``/
# ``kilometre``; an ``-import_from`` naming one is rewritten to import the
# current name under the old local name and linted once per file.
_UNITS_MODULE_PATHS = frozenset({
    "units", "py.units", "clausal.modules.units", "clausal.modules.py.units",
})


def _deprecated_unit_renames(module_path: str) -> dict[str, str]:
    """``{OldName: new_name}`` when *module_path* is the units module, else ``{}``."""
    if module_path not in _UNITS_MODULE_PATHS:
        return {}
    from clausal.modules.units import _DEPRECATED_UNIT_NAMES  # noqa: PLC0415
    return _DEPRECATED_UNIT_NAMES


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



def _is_retired_constant_spelling(identifier: str) -> bool:
    """True for the RETIRED module-constant spelling: exactly one leading and
    one trailing underscore with a non-digit-initial interior (``_PI_``,
    ``_MAX_RETRIES_``, ``_円周率_``).

    Nothing classifies with this any more.  Until 2026-09-11 it was carved
    out of the logic-variable namespace in all five copies of
    ``_is_logic_var_name``; it survives in exactly one place, and only so
    that ``_handle_constants_directive`` can recognise the old spelling and
    say what to write instead.  A name of this shape is an ordinary
    underscore-led VARIABLE everywhere else.
    """
    return (
        len(identifier) >= 3
        and identifier[0] == "_" and identifier[-1] == "_"
        and identifier[1] != "_" and identifier[-2] != "_"
        and not identifier[1].isdigit()
    )


def _decimal_string(node):
    """The text of a declared decimal STRING, or None.

    ``-constant_number_units(fee, "292.00", usd)`` (operator, 2026-09-12). A
    written ``292.00`` is a Python float literal and loses its trailing zero
    before any ``Quantity`` exists -- it stores ``Decimal('292.0')``. A string
    carries the digits verbatim, so the scale a statute wrote survives.

    **One rule, consulted by both paths.** The single-value directives gate on
    `_is_certainly_not_a_number` and the table ones on `_literal_number`;
    those are separate predicates, and two copies of one rule is the shape
    that has bitten this file twice (the orphaned suffix list, and the
    derivation the overlap control had stopped checking). So both call here.

    Accepts exactly what ``Decimal`` accepts -- ``"1e5"`` yes, ``"1/3"`` no.
    A rational needs a syntax of its own and does not get one by accident.
    """
    if not (isinstance(node, Constant) and isinstance(node.value, str)):
        return None
    from decimal import Decimal, InvalidOperation         # noqa: PLC0415
    try:
        d = Decimal(node.value)
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite():
        # "Infinity" and "NaN" parse as Decimals and are not amounts.
        return None
    return node.value


def _declared_magnitude_node(value_node, at):
    """AST for the magnitude ``constant_number_units/3`` should report.

    A written number becomes a ``Constant``; a decimal STRING becomes a
    ``$decimal_value(...)`` call, because a ``Decimal`` is not a legal AST
    constant and the whole point of the string form is that the magnitude is
    an exact Decimal. Reporting the string itself would make ``/3`` answer a
    different KIND than the value holds, which is the defect the declared-
    magnitude channel was fixed for on 2026-09-11.
    """
    text = _decimal_string(value_node)
    if text is not None:
        return _decimal_value_call(at, text)
    return replace(Constant(value=_literal_number(value_node)), at)


def _decimal_value_call(node, text):
    """The AST for ``$decimal_value("292.00")``.

    A ``Decimal`` cannot be an AST ``Constant`` -- the compiler admits only
    the literal types -- so the conversion is a call the module makes at load,
    through the same ``$``-helper channel as ``$check_currency_unit``.
    """
    return replace(
        Call(func=replace(Name(id="$decimal_value", ctx=load), node),
             args=[replace(Constant(value=text), node)], keywords=[]),
        node)


def _literal_number(node):
    """The declared magnitude, as a Python number, from the AST.

    Only a literal (optionally negated) is read. Anything computed keeps its
    computed value -- the declaration did not name a number in that case, so
    there is nothing more faithful to record.
    """
    if isinstance(node, Constant) and isinstance(node.value, (int, float)):
        return node.value
    if (isinstance(node, UnaryOp) and isinstance(node.op, USub)
            and isinstance(node.operand, Constant)
            and isinstance(node.operand.value, (int, float))):
        return -node.operand.value
    return None


def _units_ast_to_term(node):
    """Lower a unit EXPRESSION's AST to the term ``constant_number_units/3``
    answers with: atoms, nested in cells for a compound unit --
    ``('/', 'metre', 'second')``.

    Built at compile time from what the declaration WROTE. The same term
    cannot be recovered at runtime from the Quantity: a unit that is not the
    base of its own dimension rescales to that base, so ``30 day`` is stored
    as ``Quantity(2592000, second)`` and the ``day`` is gone.

    Returns None for a shape this cannot lower, so the caller can fall back
    rather than record a wrong answer.
    """
    if isinstance(node, Name):
        # An atom IS its str (atoms-as-str flip, stage 2); ``('x',)`` is a
        # RESERVED shape, not the atom, so it never unifies with ``usd_cent``.
        return node.id
    if isinstance(node, Constant) and isinstance(node.value, int):
        return node.value                      # an exponent
    if isinstance(node, BinOp):
        op = {Mult: "*", Div: "/", Pow: "**"}.get(type(node.op))
        if op is None:
            return None
        left = _units_ast_to_term(node.left)
        right = _units_ast_to_term(node.right)
        if left is None or right is None:
            return None
        return (op, left, right)
    return None


def _is_certainly_not_a_number(node) -> bool:
    """True when *node* CANNOT be a number, decided from the AST alone.

    Deliberately one-sided: it answers True only for shapes that are already
    a value of another kind (a non-numeric literal, or a container display).
    Anything whose value depends on running code -- a ``++`` escape, a name --
    answers False and is left to the units layer, which sees the real value.
    """
    if isinstance(node, Constant):
        if _decimal_string(node) is not None:
            return False            # a decimal STRING is a number, exactly
        return not isinstance(node.value, (int, float)) or isinstance(node.value, bool)
    return isinstance(node, (List, Dict, Set, Tuple, JoinedStr))


def _is_constant_declaration_name(identifier: str) -> bool:
    """True for a name a ``-constants`` declaration may bind.

    Since 2026-09-11 a constant is spelled like an atom, so that the
    logic-variable rule (underscore-led or capital-initial) has no exceptions
    left.  The value is reached with the explicit ``++name`` escape, never by
    a bare load; see ``_handle_constants_directive``.

    "Spelled like an atom" is stated as the COMPLEMENT of the variable rule,
    not as ``islower()``.  An uncased script has no lowercase form either, so
    ``islower()`` would refuse ``円周率`` while offering no other spelling --
    it is not a variable, so no leading underscore would help.  Deriving the
    class from ``_is_logic_var_name`` keeps the two exhaustive by
    construction: every identifier is one or the other.
    """
    return identifier.isidentifier() and not _is_logic_var_name(identifier)




def _raise_constant_rhs_logic_var(identifier: str, node=None, source_lines=None,
                                   filename=None) -> None:
    """A -constants RHS (structured or scalar) referenced a logic-variable-
    shaped name (or the anonymous ``_`` wildcard).

    Groundness is required at COMPILE time for a -constants RHS — not only
    at the runtime ``$check_constant_ground`` gate, which exists as a
    backstop for values a ``++()`` escape can construct outside the parser's
    view. Raised here so the error is located instead of silently minting a
    fresh Var
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
    validation error that isn't the dedicated raiser above
    (``_raise_constant_rhs_logic_var``) —
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


def _import_indicator(node) -> "tuple[str, int] | None":
    """``(name, arity)`` for an ``-import_from`` list entry written as an ISO
    predicate indicator -- ``name/N``, or a DCG nonterminal ``name//N``
    (arity N + 2, ISO 7.14) -- else ``None`` (D20, 2026-09-29)."""
    if (isinstance(node, BinOp) and isinstance(node.op, (Div, FloorDiv))
            and isinstance(node.left, Name)
            and isinstance(node.right, Constant)
            and type(node.right.value) is int and node.right.value >= 0):
        extra = 2 if isinstance(node.op, FloorDiv) else 0
        return node.left.id, node.right.value + extra
    return None


def _is_logic_var_name(identifier: str) -> bool:
    """Return True if ``identifier`` should be treated as a logic variable.

    Two conventions are recognised:

    * **Leading single underscore** — ``_x``, ``_foo``, ``_head``.
      The underscore must be a single leading one; dunders (``__``) and the
      bare ``_`` wildcard are excluded.
    * **Capital initial** — ``X``, ``FOO``, ``Foo``, ``FooBar``, ``N1``.
      The ISO Prolog rule: an identifier whose first character is an
      uppercase letter names a variable.  Underscores and digits are allowed
      after it (``N1``, ``MAX_OF``, ``Foo_bar``).

    ``Foo`` joined the second class on 2026-09-10.  It used to be neither a
    variable nor a legal identifier — TitleCase in ANY Clausal position was a
    load-time error — and it is now a variable wherever a VALUE goes.  The
    lint that refused it survives, narrowed to FUNCTOR position only (see
    ``_lint_titlecase``): this predicate is purely lexical and says nothing
    about position, so the two rules live in different places on purpose.

    There are no other exceptions.  ``_PI_`` was the module-constant class
    until 2026-09-11 and was carved out of all five copies of this predicate;
    constants are spelled like atoms now, so an underscore-led name is a
    variable whatever its last character is.  Pinned as a PROPERTY by
    test_var_classifier_conformance, not merely as a corpus of spellings.
    """
    if identifier == "_":
        return False
    if identifier.startswith("__"):
        return False
    if identifier.startswith("_"):
        return True
    # ``"".isupper()`` is False and a digit is not upper, so a name that is
    # empty, digit-initial or lowercase-initial is correctly rejected.
    return identifier[:1].isupper()


def _suggest_non_var_name(identifier: str) -> str:
    """A spelling of *identifier* that ``_is_logic_var_name`` rejects.

    Only used inside error messages, so "plausible" beats "canonical":
    ``FOO`` -> ``foo``, ``_foo`` -> ``foo``.

    It used to suggest ``Foo`` for ``FOO`` — the closest-looking spelling
    that was not a variable.  Since 2026-09-10 a capital initial IS a
    variable, so every capital-initial suggestion would have named another
    variable; the whole non-variable namespace is lowercase now, and the
    suggestion says so.
    """
    stripped = identifier.lstrip("_").lower()
    if not stripped:
        return "foo"
    candidate = stripped
    if _is_logic_var_name(candidate) or not candidate[:1].isalpha():
        # Nothing lexical is left to lower (a non-alphabetic initial, say),
        # so prefix rather than return a spelling the caller cannot use.
        candidate = "x" + candidate
    return candidate


# ─── TitleCase identifier lint ────────────────────────────────────────────────
#
# Clausal identifiers come in exactly two shapes: lowercase (predicates,
# atoms, functors) and ALL_CAPS / underscore-led (logic variables).
# TitleCase — ``Foo``, ``FooBar``, ``Len`` — is neither.  A Python class is
# reached through the ``++ClassName`` escape, and a functor is lowercase like
# every other predicate, so a TitleCase name in Clausal code is a spelling
# left over from an older convention and the lint says so once per file per
# identifier.  ``EmbedTransformer._lint_titlecase`` is the walk; it is run
# on each CLAUSAL subtree as ``visit_Expr`` (and the ``--`` seam visitors)
# recognise it, never on the hosted Python around them.

#: Severity of the TitleCase-identifier lint: ``"error"`` raises a located
#: ``SyntaxError`` at the identifier's first site; ``"warn"`` emits one
#: ``ClausalTitleCaseIdentifierWarning`` per (file, identifier) instead.
#: It is an error: a TitleCase name in a Clausal position is a spelling the
#: language has retired, and a file carrying one does not load.  Flip this
#: one constant to demote the lint.
TITLECASE_IDENTIFIER_SEVERITY = "error"

#: TitleCase spellings the lint deliberately leaves alone.  ``Undefined`` is
#: the canonical spelling of the third truth value — an injected runtime
#: binding, sibling of the Python literals ``True``/``False`` (which reach the
#: transformer as ``Constant`` nodes and never meet the lint).  Its
#: ISO/XSB alias ``undefined`` folds INTO it (``_TRUTH_ALIASES``), so
#: warning on it would name a rename the language itself does not perform.
_TITLECASE_EXEMPT_NAMES = frozenset({"Undefined"})

# ─── Keyword-argument lint ────────────────────────────────────────────────────
#
# A term is built POSITIONALLY.  ``point(x=1, y=2)`` is Python's keyword-call
# syntax borrowed as a term spelling: no ISO reading, and it is the only way a
# functor's field NAMES could be declared, which made them depend on which
# clause of the predicate came first.  It was also the last surface producer of
# a keyword-term class, a third term representation beside the cell and the
# class instance; that class and its machinery are deleted.  Refused here.

#: Severity of the keyword-argument lint: ``"error"`` raises a located
#: ``SyntaxError`` at the term; ``"warn"`` emits one
#: ``ClausalKeywordArgumentWarning`` per site instead.  Flip this one constant
#: to demote the lint.
KEYWORD_ARGUMENT_SEVERITY = "error"



#: TitleCase spellings the language itself renamed (``If`` -> ``if_``,
#: ``Test`` -> ``test``).  ``If`` is also the name of a reified AST node
#: class seeded into every module namespace, so without this list the lint
#: would tell a user writing the old ``If(...)`` to reach it as ``++If`` —
#: a Python class they never meant.  The remedy for these is the rename.
_TITLECASE_RENAMED_SPELLINGS = frozenset({"If", TEST_DEPRECATED_NAME})


def _is_titlecase_identifier(identifier: str) -> bool:
    """True iff *identifier* is TitleCase in the sense of the lint.

    An initial capital plus at least one lowercase letter somewhere — which
    is exactly what separates ``Foo`` from the ALL-CAPS ``FOO``.

    It used to end with ``and not _is_logic_var_name(identifier)``, described
    there as belt-and-braces "if the variable rule ever widens".  The
    variable rule widened on 2026-09-10 and that clause was not
    belt-and-braces at all: ``_is_logic_var_name`` now accepts every
    capital-initial name, so the conjunct would be False for every TitleCase
    identifier and the lint would silently pass EVERYTHING — a check that
    verifies nothing while still reporting success.  The predicate is
    lexical and independent now: it asks only how the name is SPELLED, and
    ``_lint_titlecase`` decides which POSITIONS it is asked about.
    """
    return identifier[:1].isupper() and any(c.islower() for c in identifier)


def _double_prefix_operand(node, op_type):
    """The operand of an ADJACENT double-prefix operator, else ``None``.

    ``++expr`` / ``--expr`` / ``~~expr`` are single operators spelled with
    two characters, and Python's parser does not know that: ``++X`` arrives
    as ``UnaryOp(UAdd, UnaryOp(UAdd, X))``, which is also exactly what the
    arithmetic ``+ +X`` arrives as.  For ``--`` the collision is worse still
    -- ``a <- -b`` and ``a < --b`` parse to the IDENTICAL tree, because the
    arrow is a ``Lt`` followed by a ``USub``.  Only the source COLUMNS tell
    the operator from the arithmetic, so the adjacency test is not a detail
    of one call site: it is the operator's definition, and every reader of
    these shapes has to apply it.

    Three readers did not, which is why this is one function.  The transform
    (``TermTransformer.visit_UnaryOp``) required adjacency while
    ``_clause_variable_names`` and the TitleCase lint did not, so a spaced
    ``+ +Foo`` was compiled as arithmetic on the logic variable ``Foo`` --
    Clausal code -- while both of those skipped it as a Python escape.  The
    collector thereby threw away the only evidence that ``Foo`` was a
    variable at all, and the lint skipped the functor position it exists to
    refuse.  (The lint's docstring already SAID "adjacent double ``UAdd``";
    the code had never done it.)
    """
    if (isinstance(node, UnaryOp) and isinstance(node.op, op_type)
            and isinstance(node.operand, UnaryOp)
            and isinstance(node.operand.op, op_type)
            and node.lineno == node.operand.lineno
            and node.col_offset == node.operand.col_offset - 1):
        return node.operand.operand
    return None


def _python_escape_operand(node):
    """``++expr`` → ``expr``; anything else → ``None``.  See
    ``_double_prefix_operand`` for why adjacency is part of the question."""
    return _double_prefix_operand(node, UAdd)


def _variable_marker_name(node):
    """``--X`` → ``"X"`` when ``X`` is a logic-variable spelling, else ``None``.

    The explicit half of thunk capture.  Inside an f-string slot or a ``++``
    operand the body is verbatim Python, so a bare ``X`` there is captured as
    a clause variable by NAME, decided against a module-namespace exclusion
    set -- the machinery five rounds of defects were spent on.  ``--X`` says
    it outright and is CHECKED against the clause's own variables, which the
    bare spelling cannot be: a bare name the clause does not bind is a legal,
    intended reference to the module namespace.

    Only a bare ``Name`` counts.  That is what keeps the marker clear of the
    ``--`` SEAM, whose operand is an arbitrary term (``--{}`` takes a
    ``Dict``), and it is what makes the reading exact: the marker names a
    variable, and only an identifier can name one.  A non-variable spelling
    (``--total``) is left as the Python double negation it always was.

    Adjacency does the disambiguating, via ``_double_prefix_operand``: it is
    the only thing separating ``a < --b`` from ``a <- -b``, which parse to
    the identical tree.
    """
    operand = _double_prefix_operand(node, USub)
    if (isinstance(operand, Name) and isinstance(operand.ctx, Load)
            and _is_logic_var_name(operand.id)):
        return operand.id
    return None


def _collect_marked_var_names(node) -> list[str]:
    """Names written with the explicit ``--X`` marker, first-occurrence order.

    ANYWHERE within *node*, not only at its top.  That is the deliberate
    choice: a thunk body is almost always a call, so a top-only rule would
    make the marker unwritable in ``f"{str(Node).upper()}"`` or
    ``++len(Node)`` -- the very places a reader most needs telling which
    names are variables.  Top-only would have been unambiguous for free
    (the arrow form needs a ``Compare`` wrapper, so it cannot BE the top),
    but adjacency already settles that case wherever it appears, and it
    settles it the same way at every depth.

    A marked name is collected unconditionally: no exclusion set is
    consulted, because saying "this is the clause's variable" is the whole
    point of writing the marker.  The walk does not descend into a marker,
    so ``----X`` is not two markers.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    class _Collector(NodeVisitor):
        def visit_UnaryOp(self, unary_op):
            name = _variable_marker_name(unary_op)
            if name is None:
                self.generic_visit(unary_op)
                return
            if name not in seen:
                seen.add(name)
                ordered.append(name)

    _Collector().visit(node)
    return ordered


def _strip_variable_markers(node):
    """A COPY of *node* with every ``--X`` marker replaced by plain ``X``.

    A copy, not an in-place rewrite: the same tree is walked again by the
    reifier and by ``_lint_titlecase``, and a thunk body that had quietly
    lost its ``--`` would make the source and the model disagree about what
    was written.
    """
    class _Stripper(NodeTransformer):
        def visit_UnaryOp(self, unary_op):
            if _variable_marker_name(unary_op) is not None:
                return unary_op.operand.operand
            return self.generic_visit(unary_op)

    return _Stripper().visit(deepcopy(node))


#: Control forms whose every argument is a goal, for the cross-mode literal
#: lint.  The meta-predicates proper (``findall``, ``maplist``, ``catch``,
#: ...) are asked position by position through
#: ``clause_ops._goal_positions``, the compiler's own per-arity table, so a
#: ``findall`` TEMPLATE or a ``catch`` catcher stays data.
_GOAL_CONTROL_FORMS = frozenset({"if_", "not_", "ignore"})


def _clause_scope_exclusions(import_remap) -> frozenset:
    """TitleCase names a CLAUSAL context must not treat as logic variables.

    Exactly the names ``visit_Name`` refuses to read as variables: the
    exempt injected bindings (``Undefined``) and this file's
    ``-import_from`` names.  Module-level because BOTH transformers need it
    -- ``TermTransformer`` for ``_reads_as_variable`` and the unit sugar,
    ``EmbedTransformer`` for the seam -- and a second copy is precisely the
    drift this change has already paid for three times.
    """
    return frozenset(_TITLECASE_EXEMPT_NAMES) | frozenset(
        n for n in (import_remap or ()) if _is_titlecase_identifier(n))


def _clause_variable_names(node, excluded) -> set:
    """Names *node* uses as logic variables OUTSIDE any verbatim-Python body.

    The question a thunk has to answer is "does the surrounding clause use
    this spelling as a variable?", and the surrounding clause is the whole
    clause -- not the part the walk has reached, which would make one clause
    mean two things depending on goal order.

    ``++`` operands and f-strings are skipped on purpose.  A name appearing
    ONLY inside a thunk is not evidence that the clause treats it as a
    variable; it is the ``++Fraction(1, 3)`` case, where the author means the
    module-namespace binding.  A name used outside one is evidence, and that
    is what makes ``tree(Node), f"{Node}"`` format the binding rather than
    ``<class '...nodes.Node'>``.

    The skipping itself lives in ``_collect_logic_var_names`` rather than in
    a collector of its own: the seam needs the SAME answer in first-occurrence
    ORDER, and two walks that were meant to agree but were written twice is
    exactly the drift that produced the defect this delegation removes.
    """
    return set(_collect_logic_var_names(node, excluded,
                                        python_bodies="skip"))


def _python_scope_exclusions(import_remap, python_bound,
                             clause_vars=frozenset()) -> frozenset:
    """Names a VERBATIM-PYTHON context (a ``++`` operand, an f-string slot)
    must not capture as lambda parameters: they resolve in the MODULE
    NAMESPACE when the thunk runs, so capturing one shadows the real binding
    with an unbound ``Var``.

    Everything in that namespace, which is three sets, not one:

    * the clause-scope names (``Undefined``, the ``-import_from`` names);
    * what the file's own hosted Python binds (``_titlecase_python_bound``);
    * ``_python_class_names()`` — the injected runtime builtins, the seeded
      AST node classes, and Python's own builtins.  Missing this third set
      is what broke ``++ValueError`` (``catching classes that do not inherit
      from BaseException``, because the catcher was an unbound Var) and the
      bare ``Var(...)`` call (``'AttVar' object is not callable``).  It is
      the same set the lint consults to decide that a name's remedy is
      ``++Name`` rather than a rename -- which is the giveaway that these
      are exactly the names a ``++`` is FOR.

    Strictly larger than the clause set, deliberately: ``P is Fraction``
    reads ``Fraction`` as a VARIABLE while ``++Fraction(1, 3)`` reads it as
    the class, so one rule cannot serve both scopes.
    """
    return ((_clause_scope_exclusions(import_remap)
             | frozenset(n for n in (python_bound or ())
                         if _is_titlecase_identifier(n))
             | _module_namespace_class_names())
            - frozenset(clause_vars))


_MODULE_NAMESPACE_CLASS_NAMES: frozenset | None = None


def _module_namespace_class_names() -> frozenset:
    """``_python_class_names()`` restricted to TitleCase, WITHOUT importing
    the compiler.

    Same content, different source: the injected runtime names are read from
    ``generated_names``' STATIC list rather than from
    ``INJECTED_RUNTIME_BUILTINS``.  ``_python_class_names`` imports
    ``clausal.logic.compiler.predicate`` to get that table, and reflection
    must never import the compiler -- a pure ``reify_source`` process reads
    ``$Var``/``$PyThunk`` back by name and is pinned, in a subprocess, to do
    it without the compiler ever appearing in ``sys.modules``.  Reaching the
    table the eager way through this path broke that invariant.

    ``generated_names.register_generated_names`` raises if the static list
    and the runtime table ever disagree, and a test pins the two equal, so
    this cannot quietly fall behind.
    """
    global _MODULE_NAMESPACE_CLASS_NAMES
    if _MODULE_NAMESPACE_CLASS_NAMES is None:
        import builtins  # noqa: PLC0415
        from clausal.logic.generated_names import (  # noqa: PLC0415
            BARE_ONLY, INJECTED_TITLECASE_NAMES)
        from clausal.pythonic_ast import nodes as simple_ast  # noqa: PLC0415
        node_names = getattr(simple_ast, "__all__", None) or [
            n for n in dir(simple_ast) if isinstance(getattr(simple_ast, n), type)]
        _MODULE_NAMESPACE_CLASS_NAMES = frozenset(
            n for n in (set(INJECTED_TITLECASE_NAMES) | set(BARE_ONLY)
                        | set(node_names)
                        | {n for n in dir(builtins) if n[:1].isupper()})
            if _is_titlecase_identifier(n))
    return _MODULE_NAMESPACE_CLASS_NAMES


def _is_var_in_name_position(identifier: str) -> bool:
    """True if *identifier*, standing where a NAME goes rather than where a
    value goes, reads as a logic variable — ``FOO`` and ``_foo``, not ``Foo``.

    The ruled asymmetry of 2026-09-10, stated once so every name-position
    guard shares it.  In TERM position a capital initial is a variable, full
    stop (``_is_logic_var_name``).  There are two kinds of name position
    where it is not:

    * the CALLABLE of a call, because a variable there is not ``call/N`` in
      this language — it is the UNIT-ANNOTATION sugar, and ``X(newton)``
      builds a Quantity rather than calling ``X``;
    * a component of a QUALIFIED NAME (``mod.Pred``, ``prolog.TruncDiv``),
      which is a predicate's name spelled in two parts.  The TitleCase lint
      has never read attribute names for exactly this reason.

    So a capital-initial name in either position is one of exactly two
    things, neither of them a variable:

    * a TitleCase name the file has BOUND (an ``-import_from`` name such as
      the reified-AST constructors, or ``Undefined``) — a real functor, which
      must be CALLED, not turned into a unit;
    * an unbound TitleCase name — a load-time error from ``_lint_titlecase``,
      which names the ``++Name`` remedy.

    Reading such a callable as a variable is what silently converts
    ``foldable(Atom(_))`` from a goal into ``++(Quantity(Atom, {_}))``: the
    call disappears, and the failure surfaces much later as "cannot build a
    Quantity from AttVar(...): SI prefixes cannot be used as units", naming
    neither ``Atom`` nor the line it was written on.  ``FOO(3)`` keeps the
    units reading exactly as before.
    """
    return (_is_logic_var_name(identifier)
            and not _is_titlecase_identifier(identifier))


_PYTHON_CLASS_NAMES: frozenset | None = None


def _python_class_names() -> frozenset:
    """TitleCase names that reach a ``.clausal`` module as real Python
    classes, so the lint's remedy for them is the ``++`` escape rather than
    a snake_case rename: the engine-injected runtime names
    (``INJECTED_RUNTIME_BUILTINS`` — ``Var``, ``PyThunk``,
    …), the AST node classes seeded into every module namespace
    (``pythonic_ast.nodes.__all__``), and Python's own builtins
    (``ValueError``, ``AssertionError``, …).  Resolved lazily — the
    runtime modules import this one."""
    global _PYTHON_CLASS_NAMES
    if _PYTHON_CLASS_NAMES is None:
        import builtins  # noqa: PLC0415
        from clausal.logic.compiler.predicate import (  # noqa: PLC0415
            INJECTED_RUNTIME_BUILTINS)
        from clausal.pythonic_ast import nodes as simple_ast  # noqa: PLC0415
        node_names = getattr(simple_ast, "__all__", None) or [
            n for n in dir(simple_ast) if isinstance(getattr(simple_ast, n), type)]
        _PYTHON_CLASS_NAMES = frozenset(
            set(INJECTED_RUNTIME_BUILTINS) | set(node_names)
            | {n for n in dir(builtins) if n[:1].isupper()})
    return _PYTHON_CLASS_NAMES


def _titlecase_to_snake(identifier: str) -> str:
    """The lowercase spelling a rename message suggests: ``FooBar`` ->
    ``foo_bar``, ``Foo`` -> ``foo``, ``HTTPServer`` -> ``http_server``.
    A Python keyword gets the trailing underscore the language uses for
    the same collision (``If`` -> ``if_``, ``Not`` -> ``not_``)."""
    out = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_",
                 identifier).lower()
    if _keyword_module.iskeyword(out):
        out += "_"
    return out


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


def _is_lowerable_goal(goal, excluded=frozenset()) -> bool:
    """True when reads may be extracted out of *goal* to just before it.

    False means "leave this goal alone" — it is not a shape we lower (a
    control construct, a meta-call, a Python escape) or one of its arguments
    is not a plain term.  Refusing only costs sharing: the reads inside stay
    inline, exactly as they compile today.
    """
    if isinstance(goal, Call):
        if isinstance(goal.func, Name):
            if _is_var_in_name_position(goal.func.id):
                return False         # meta-call on a variable goal
        elif (not isinstance(goal.func, Attribute)
                or _is_dict_attr_access(goal.func, excluded)):
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


def _lower_dict_reads_in_scope(goal, mint, excluded=frozenset()):
    """Lower every dict read in one control-construct scope.

    Returns a goal AST for the scope.  Reads minted here do not escape it.
    """
    lowered = []
    shared = {}
    for conjunct in _flatten_conjunction(goal):
        lowered.extend(_lower_dict_reads_in_goal(conjunct, mint, shared, excluded))
    if len(lowered) == 1:
        return lowered[0]
    return replace(Tuple(elts=lowered, ctx=load), goal)


def _lower_dict_reads_in_goal(goal, mint, shared, excluded=frozenset()):
    """Lower one goal; returns the read goals plus the rewritten goal."""
    # Control constructs: each arm is its own scope, so a read is never lifted
    # out of it.  `( a(P) or b(P.k) )` must still succeed via `a(P)` when the
    # key is missing.
    if isinstance(goal, BoolOp):
        return [replace(
            BoolOp(op=goal.op,
                   values=[_lower_dict_reads_in_scope(value, mint, excluded)
                           for value in goal.values]),
            goal,
        )]
    if isinstance(goal, UnaryOp) and isinstance(goal.op, Not):
        return [replace(
            UnaryOp(op=goal.op,
                    operand=_lower_dict_reads_in_scope(
                        goal.operand, mint, excluded)),
            goal,
        )]
    if (isinstance(goal, Call) and isinstance(goal.func, Name)
            and goal.func.id in _ITE_NAMES and len(goal.args) == 3
            and not goal.keywords):
        return [replace(
            Call(func=goal.func,
                 args=[_lower_dict_reads_in_scope(arm, mint, excluded)
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

    if not _is_lowerable_goal(goal, excluded):
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


def _lower_dict_reads(head_ast, body_ast, excluded=frozenset()):
    """Read-once lowering over a whole clause body.  Returns the new body.

    The body is copied first: the pass rewrites in place, and the caller's AST
    is shared with the module tree.  The copy is then run through the shared
    surface-desugar pass, so this pass only ever sees the ``P[key]`` spelling
    — ``P.key`` is expanded once, in one place, by ``desugar_surface``.

    Note that hoisting itself is NOT shared with the SMT prover: minting
    implicit variables and reordering goals is an evaluation strategy, not a
    spelling.  See ``clausal/templating/desugar.py``.
    """
    body_ast = desugar_surface(deepcopy(body_ast), excluded)
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

    return _lower_dict_reads_in_scope(body_ast, mint, excluded)


#: Hand-maintained: spellings the vocabulary does NOT hold. A residue question
#: needs a set the authority has forgotten, and that set cannot be derived —
#: see `_scale_suffixes`. Marked stale-able rather than pretending otherwise.
_HAND_MAINTAINED_SCALE_WORDS = frozenset({
    "pence", "pennies",                                  # penny is irregular
    "centime", "centimes", "fils", "sen", "satoshi",      # no table names
                                                         # these today
    "bps", "pct",                                        # ABBREVIATIONS of
    # ratio units, which no vocabulary holds and no derivation will ever
    # produce. `percent` and `basis_points` were REMOVED from this half on
    # 2026-09-12 when ratio units landed and the derivation took them over.
    # The overlap control below is what named them -- a half designed to
    # shrink needs something that notices when it should have.
})


def _derived_scale_words() -> set:
    from clausal.modules.countries import _data              # noqa: PLC0415
    from clausal.modules import _ratio_data                  # noqa: PLC0415
    out = set()
    for word in list(_data.MINOR_UNIT_WORDS.values()) + list(_ratio_data.RATIO_UNITS):
        out.add(word)
        if not word.endswith("y"):
            out.add(word + "s")
    return out


_SCALE_SUFFIX_CACHE = None


def _scale_suffixes() -> frozenset:
    """Name endings that CLAIM a scale the engine cannot otherwise see.

    Derived from the vocabulary where it can be -- every curated minor-unit
    word and every ratio unit name, plus plurals -- so that giving a currency
    a minor unit, or adding a ratio unit, extends this lint without a second
    edit. What remains hand-maintained is what no vocabulary holds: retired
    spellings, and the ABBREVIATIONS `bps` and `pct`.
    """
    global _SCALE_SUFFIX_CACHE
    if _SCALE_SUFFIX_CACHE is None:
        # One derivation, called from both places that need it: this set and
        # the overlap control below. Two copies of it would let the control
        # go on checking a set the lint no longer uses.
        out = _derived_scale_words()
        # DECLARED UNION, and the two halves have different maintenance
        # obligations (a downstream checker, 2026-09-12, who built the
        # derive-from-the-authority rule as code and bounded it).
        #
        # Deriving from `MINOR_UNIT_WORDS` answers "does this conform to the
        # CURRENT vocabulary". This lint asks a RESIDUE question — does an
        # identifier claim a scale nothing represents — and residue is by
        # definition about words the authority may already have forgotten.
        # If `cent` were renamed, the derived half would stop matching
        # `..._cents` at exactly the moment the rename made matching
        # necessary. So the retired and never-derived spellings are listed by
        # hand and SAY SO, rather than a derived set pretending to be total.
        out.update(_HAND_MAINTAINED_SCALE_WORDS)
        assert out, "positive control: the suffix set is not empty"
        # A half expected to SHRINK needs something that notices when it
        # should have (a downstream checker, 2026-09-12). The control above
        # catches an empty hand list; nothing caught a REDUNDANT one — a word
        # the authority has since taken over, left behind here, which is the
        # same staleness in the other direction. Overlap is exactly that
        # condition, so it raises rather than silently duplicating.
        overlap = _HAND_MAINTAINED_SCALE_WORDS & {
            w for w in out if w in _derived_scale_words()}
        assert not overlap, (
            f"{sorted(overlap)} now come from the vocabulary — drop them from "
            f"_HAND_MAINTAINED_SCALE_WORDS; the hand-maintained half exists "
            f"only for what the authority does NOT hold")
        _SCALE_SUFFIX_CACHE = frozenset(out)
    return _SCALE_SUFFIX_CACHE


def _carries_a_unit(node) -> bool:
    """True for the ``29200 (usd_cent)`` annotation shape — a number applied
    to a unit expression.

    A row carrying one has its scale represented where the ENGINE can read
    it, which is the whole thing the scale lint asks for. Written as a
    property of the ROW rather than as an exemption for the table directive,
    because a hand-written fact with a united column deserves the same
    silence and was warning too.
    """
    if not (isinstance(node, Call) and len(node.args) == 1 and not node.keywords):
        return False
    func = node.func
    if isinstance(func, UnaryOp) and isinstance(func.op, USub):
        func = func.operand
    return (isinstance(func, Constant)
            and isinstance(func.value, (int, float))
            and not isinstance(func.value, bool)
            and _is_unit_expr(node.args[0]))


def _name_claims_a_scale(identifier: str) -> bool:
    return any(identifier.endswith("_" + suffix) for suffix in _scale_suffixes())


def _is_bare_number(node) -> bool:
    """A numeric LITERAL, optionally negated -- not a quantity, not a call.

    The discriminator the lint turns on: a converted site is
    ``155000 (usd_cent)``, a ``Call``, and reads as silent.
    """
    if isinstance(node, UnaryOp) and isinstance(node.op, USub):
        node = node.operand
    return (isinstance(node, Constant) and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool))


#: The table family, mirroring the single-value one: a general-unit form and
#: a money form named for the stricter claim it enforces. Each names its own
#: COLUMN keyword, following the convention the family already uses for its
#: third argument ("units" in one, "currency" in the other).
TABLE_DIRECTIVES = {
    "constants_number_units": ("number_at", False),
    "constants_number_currency": ("money_at", True),
}


def _table_directive_call(stmt):
    """The ``-constants_number_currency(...)`` Call in *stmt*, or None.

    A directive is written ``-name(...)``, which parses as a unary minus over
    a Call, so that is the shape matched here.
    """
    if not isinstance(stmt, Expr):
        return None
    node = stmt.value
    if not (isinstance(node, UnaryOp) and isinstance(node.op, USub)):
        return None
    call = node.operand
    if (isinstance(call, Call) and isinstance(call.func, Name)
            and call.func.id in TABLE_DIRECTIVES):
        return call
    return None


def _expand_currency_table(call):
    """Expand one table directive into the fact statements it declares.

    Source-to-source, run BEFORE the ordinary visit, so the generated facts go
    through exactly the same machinery as hand-written ones -- same clause
    compilation, same indexing, same everything. Generating the LOWERED form
    instead would have made a table a second kind of predicate.

    The declaration DEFINES the predicate the rulebase already calls
    (operator, 2026-09-12), so a domain migrates by replacing N fact lines
    with one declaration and no call site changes. The money COLUMN is
    declared with ``money_at(N)``, 1-based, never inferred: the real corpus
    shapes put money in arg 2 of 2, in arg 3 of 4 and beside a two-date
    validity window, so any positional rule would guess wrong on one of them,
    silently.
    """
    directive = call.func.id
    column_kw, is_money = TABLE_DIRECTIVES[directive]
    spelling = f"-{directive}"
    example = (f"{spelling}(snap_max/2, [(1, 29200), (2, 53600)], "
               f"{'usd_cent' if is_money else 'metre'}, {column_kw}(2))")
    if call.keywords:
        raise SyntaxError(
            f"{spelling}: takes no keyword arguments; the money column is "
            f"named positionally as {column_kw}(N): {example}")
    if len(call.args) != 4:
        raise SyntaxError(
            f"{spelling} takes four arguments — a predicate indicator, the "
            f"rows, the unit, and {column_kw}(N) naming the column. The "
            f"column is never inferred, because a rule that guesses guesses "
            f"silently: {example}")
    indicator, rows_node, unit_node, at_node = call.args

    if not (isinstance(indicator, BinOp) and isinstance(indicator.op, Div)
            and isinstance(indicator.left, Name)
            and isinstance(indicator.right, Constant)
            and isinstance(indicator.right.value, int)):
        raise SyntaxError(
            f"{spelling}: the first argument is a predicate indicator "
            f"`name/arity`, got `{unparse(indicator)}`: {example}")
    pred_name, arity = indicator.left.id, indicator.right.value

    if not (isinstance(at_node, Call) and isinstance(at_node.func, Name)
            and at_node.func.id == column_kw and len(at_node.args) == 1
            and isinstance(at_node.args[0], Constant)
            and isinstance(at_node.args[0].value, int)):
        raise SyntaxError(
            f"{spelling}: the fourth argument names the column as "
            f"{column_kw}(N), 1-based, got `{unparse(at_node)}`: {example}")
    money_at = at_node.args[0].value
    if not 1 <= money_at <= arity:
        raise SyntaxError(
            f"{spelling}: {column_kw}({money_at}) is out of range for "
            f"{pred_name}/{arity} — the column is 1-based and must name one "
            f"of the {arity} arguments.")

    if not isinstance(rows_node, (List, Tuple)):
        raise SyntaxError(
            f"{spelling}: the second argument is the list of rows, got "
            f"`{unparse(rows_node)}`: {example}")
    if not _is_unit_expr(unit_node):
        raise SyntaxError(
            f"{spelling}: `{unparse(unit_node)}` is not a unit expression: "
            f"{example}")

    facts = []
    for row in rows_node.elts:
        if not isinstance(row, (Tuple, List)):
            raise SyntaxError(
                f"{spelling}: every row is a tuple of {arity} columns, got "
                f"`{unparse(row)}`")
        cells = list(row.elts)
        if len(cells) != arity:
            raise SyntaxError(
                f"{spelling}: row `{unparse(row)}` has {len(cells)} columns "
                f"but {pred_name}/{arity} takes {arity} — the arity in the "
                f"indicator is the contract, and a row that does not match it "
                f"would define a predicate of two different shapes.")
        money = cells[money_at - 1]
        # STRICTER than the single-value form on purpose. `-constant_value`
        # accepts a computed RHS (a `++` escape, an earlier constant), so its
        # check is deliberately one-sided and leaves a bare name to the units
        # layer. A table ROW is data, not an expression, and a bare name here
        # would be wrapped as `name(unit)` -- an atom applied as a functor,
        # which is meaningless and would not announce itself. So the money
        # cell must be a numeric LITERAL.
        if _literal_number(money) is None and _decimal_string(money) is None:
            raise SyntaxError(
                f"{spelling}: column {money_at} of `{unparse(row)}` is "
                f"`{unparse(money)}`, which is not a number literal. A table "
                f"row is data: only numbers carry units, and the money column "
                f"takes a written number.")
        # The same shape the `29200 (usd_cent)` annotation sugar builds, so the
        # ordinary visit lowers it and the currency gate runs on it.
        _cell_decimal = _decimal_string(money)
        if _cell_decimal is not None:
            # A string cannot be the CALLEE of the `292.00(usd)` sugar, so
            # emit what that sugar lowers to. The unit gate below still runs
            # -- it gates the unit once for the whole table, not per row.
            cells[money_at - 1] = replace(
                Call(func=replace(Name(id="$Quantity", ctx=load), money),
                     args=[_decimal_value_call(money, _cell_decimal),
                           unit_node],
                     keywords=[]),
                money)
        else:
            cells[money_at - 1] = replace(
                Call(func=money, args=[unit_node], keywords=[]), money)
        # A bodyless clause -- a FACT -- is a one-element Tuple statement.
        fact = Expr(value=replace(
            Tuple(elts=[replace(
                Call(func=replace(Name(id=pred_name, ctx=load), row),
                     args=cells, keywords=[]), row)], ctx=load), row))
        fix_missing_locations(replace(fact, row))
        facts.append(fact)
    if facts and is_money:
        # Gate the UNIT once, at load, through the same check the
        # single-value `-constant_number_currency` uses: the directive is
        # named for the claim that this is MONEY, so a physical unit here is
        # refused rather than quietly producing a table of lengths. One call
        # for the table, not one per row.
        guard = Expr(value=replace(
            Call(func=replace(Name(id="$check_currency_unit", ctx=load), call),
                 args=[replace(Constant(value=f"{pred_name}/{arity}"), call),
                       unit_node,
                       replace(Constant(value=spelling), call)],
                 keywords=[]), call))
        fix_missing_locations(replace(guard, call))
        facts.insert(0, guard)
    return facts


def _is_unit_expr(node) -> bool:
    """True for AST nodes that form a valid unit-type expression.

    Accepts plain Names (e.g. ``metre``) and compound expressions built from
    ``*``, ``/``, ``**`` with Names and numeric Constants as leaves — e.g.
    ``metre**2``, ``metre/second``, ``kilogram*metre/second**2``.
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


def _hosted_python_bindings(module):
    """Every name *module*'s hosted Python binds, in tree order: an
    import (``import x as name``, ``from m import name``), a ``def`` /
    ``async def`` / ``class`` of that name, and the ``Name`` targets of an
    assignment or annotated assignment (``Point = namedtuple(...)``,
    ``Rate: int = 3``, ``A, B = ...``).  Clause statements are expressions
    and bind nothing here, so the result is exactly the Python namespace
    the file builds for itself."""
    out: list[str] = []
    for node in walk(module):
        if isinstance(node, alias):
            out.append(node.asname or node.name.split(".")[0])
        elif isinstance(node, (FunctionDef, AsyncFunctionDef, ClassDef)):
            out.append(node.name)
        elif isinstance(node, (Assign, AnnAssign)):
            targets = node.targets if isinstance(node, Assign) else [node.target]
            for target in targets:
                for sub in walk(target):
                    if isinstance(sub, Name) and isinstance(sub.ctx, Store):
                        out.append(sub.id)
    return out


_REWRITER_FRAME_FILES = frozenset({
    _os.path.basename(__file__),
    _os.path.basename(_ast_module.__file__),
})


def _stacklevel_outside_rewriter() -> int:
    """The ``stacklevel`` that attributes a ``warnings.warn`` issued from
    inside the rewriter to the first frame that is neither this module nor
    the stdlib ``ast`` walker driving it (``NodeTransformer.visit`` /
    ``generic_visit``) — the code that asked for the compile — rather than
    to whichever recursive helper happened to call ``warn``.  Counted from
    the caller's frame, so pass the result straight to ``warn``."""
    frame = sys._getframe(1)
    level = 1
    while (frame.f_back is not None
           and _os.path.basename(frame.f_code.co_filename)
           in _REWRITER_FRAME_FILES):
        frame = frame.f_back
        level += 1
    return level


def _zero_arity_head_prepass(module) -> frozenset:
    """The names every 0-arity clause HEAD in *module* uses -- ``p,`` and
    ``p <- (...)`` -- read from the raw AST before any clause is walked.

    STAGE 2 of the atoms-as-str flip: a 0-arity predicate referenced as a
    VALUE is the atom of its name.  ``visit_Name`` learns a functor from
    ``_seen_functors``, which is filled as heads are VISITED, so a reference
    placed before the predicate's first clause (legal under the old, now
    removed, -implicit_atoms, where nothing else declares the name) fell through to the import-remap
    path and loaded the CLASS at runtime -- a value that prints like the
    atom, is not equal to it and is not a term.  This set closes the order
    gap: it depends only on the file's text.
    """
    heads = set()
    for stmt in getattr(module, "body", ()):
        if not isinstance(stmt, Expr):
            continue
        # ``p,`` / ``p(1),`` parse as a Tuple statement; a clause written
        # without the trailing comma (``p <- true``) is the bare expression.
        elts = stmt.value.elts if isinstance(stmt.value, Tuple) else [stmt.value]
        for elt in elts:
            head = elt.left if isinstance(elt, Compare) else elt
            if isinstance(head, Name):
                heads.add(head.id)
    return frozenset(heads)


def _binds_name(module, name: str) -> bool:
    """True if *module* binds *name* anywhere: an assignment target, a
    def/class of that name, or an import (``import x as name``)."""
    for node in walk(module):
        if isinstance(node, Name) and node.id == name and isinstance(node.ctx, Store):
            return True
        if isinstance(node, (FunctionDef, AsyncFunctionDef, ClassDef)) and node.name == name:
            return True
        if isinstance(node, alias) and (node.asname or node.name) == name:
            return True
        if isinstance(node, arg) and node.arg == name:
            return True
    return False


def _collect_logic_var_names(node, excluded, *,
                             python_bodies="descend") -> list[str]:
    """Collect logic variable names from *node*, in first-occurrence order.

    *excluded* is REQUIRED, and has no default on purpose.  Every caller sits
    in one of two scopes and the answer differs between them, so there is no
    safe default to fall back on — and three review rounds of this change
    were spent on consumers that asked the LEXICAL rule
    (``_is_logic_var_name``) where they had to agree with something else.
    Making the parameter mandatory means a new caller cannot get the lexical
    rule by accident; it has to name its scope.  The two scopes, both
    produced by ``TermTransformer``/``EmbedTransformer`` helpers so no caller
    builds a set by hand:

    * ``_clause_scope_exclusions()`` — CLAUSAL contexts (the ``--`` seam, the
      unit-sugar magnitude).  These must agree with ``visit_Name``, so the
      excluded names are the ones it refuses to read as variables:
      ``Undefined`` and the ``-import_from`` names.  Collecting one of those
      made the seam emit ``(Undefined := $Var())`` into the host Python
      scope, clobbering the injected truth value while the term side
      compiled it as the bound name.

    * ``_python_scope_exclusions()`` — VERBATIM-PYTHON contexts (a ``++``
      operand, an f-string interpolation slot).  A collected name becomes a
      PARAMETER of the lambda these lower to; a name NOT collected resolves
      in the module namespace when the thunk runs.  So the excluded set is
      everything bound in that namespace: the clause-scope names plus what
      the file's own hosted Python binds (``_titlecase_python_bound``).

    The difference between the two is real, not an accident of history: a
    file doing ``from fractions import Fraction`` reads ``P is Fraction`` as
    a VARIABLE (a hosted-Python binding does not carve a name out of the
    Clausal variable rule — see ``_reads_as_variable``) while
    ``++Fraction(1, 3)`` reads it as the class.  One rule cannot serve both.

    Excluding by SPELLING rather than by membership was the round-2 defect:
    it dropped every capital-initial name, so a genuine clause variable
    ``Total`` was not captured either, and ``f"{Total}"`` silently formatted
    an unbound variable's repr while ``f"{TOTAL}"`` -- the identical clause
    -- gave the right answer.

    *python_bodies* says what the walk does with the verbatim-Python bodies
    it meets -- a ``++`` operand, an f-string interpolation slot.  Which of
    the three it wants follows from the caller's scope, not from taste:

    * ``"descend"`` -- a caller ASKING ABOUT a Python body (the two
      ``_python_scope_exclusions`` call sites).  The names it wants are
      precisely the ones written inside, and a nested body (``++f"{X}"``) is
      part of the one lambda it is collecting parameters for.
    * ``"skip"`` -- a caller asking what the surrounding CLAUSE treats as a
      variable.  A name appearing only inside a Python body is not evidence
      about the Clausal text; it is the author naming a module binding.  And
      in a clause a ``--X`` inside a ``++`` is the variable MARKER, which is
      CHECKED against the clause's own variables and so must never be the
      thing that puts a name among them.
    * ``"nested_seams"`` -- the same, for a SEAM.  Identical to ``"skip"``
      but for one carve-out: inside a seam a ``++`` operand is hosted Python
      again, and there ``--expr`` is a nested SEAM rather than a marker (see
      ``_variable_marker_name``: the marker is read only where the thunk body
      is embedded verbatim, with no Python visitor to hand it back to).  A
      nested seam's operand is Clausal text, so its names are variables, and
      they are hoisted to the enclosing seam deliberately -- that is what
      lets the inner seam reuse the variable the outer one bound instead of
      shadowing it inside the lambda.
    """
    if python_bodies not in ("descend", "skip", "nested_seams"):
        raise ValueError(f"unknown python_bodies mode: {python_bodies!r}")
    ordered: list[str] = []
    seen: set[str] = set()

    class _Collector(NodeVisitor):
        def _python_body(self, node):
            """A verbatim-Python body: descend, ignore, or read only the
            nested seams in it, according to *python_bodies*."""
            if python_bodies == "descend":
                self.generic_visit(node)
            elif python_bodies == "nested_seams":
                _visit_nested_seam_operands(node, self)

        def visit_JoinedStr(self, joined):
            self._python_body(joined)

        def visit_UnaryOp(self, unary_op):
            if (python_bodies != "descend"
                    and _python_escape_operand(unary_op) is not None):
                self._python_body(_python_escape_operand(unary_op))
                return
            self.generic_visit(unary_op)

        def visit_Name(self, name):
            ident = name.id
            if (ident != "_" and _is_logic_var_name(ident)
                    and ident not in excluded):
                if ident not in seen:
                    seen.add(ident)
                    ordered.append(ident)
            self.generic_visit(name)

    _Collector().visit(node)
    return ordered


def _visit_nested_seam_operands(node, collector) -> None:
    """Hand *collector* the operand of every ``--expr`` seam written inside
    *node*, and nothing else.

    *node* is verbatim Python -- the inside of a ``++`` escape, or an
    f-string slot -- reached from a SEAM, so a ``--expr`` in it is a nested
    seam whose operand is Clausal text again.  Anywhere in the body counts,
    including inside a further escape, because the enclosing seam's Python
    visitor walks the whole body and lowers every seam it finds there.

    Re-entering *collector* rather than walking with a private rule is the
    point: the nested operand is subject to the same treatment as the outer
    one, so a ``++`` inside IT skips its Python in turn.
    """
    class _Finder(NodeVisitor):
        def visit_UnaryOp(self, unary_op):
            seam = _double_prefix_operand(unary_op, USub)
            if seam is not None:
                collector.visit(seam)
                return
            self.generic_visit(unary_op)

    _Finder().visit(node)




# The lint warning classes live in clausal.lint_warnings (no imports there)
# so a layer that only raises one — units.py's deprecated-spelling alias from
# plain Python — need not load this module.  Re-exported for existing callers.
from clausal.lint_warnings import (  # noqa: E402, F401
    ClausalLintWarning,
    ClausalSingletonWarning,
    ClausalShadowedVariableWarning,
    ClausalBooleanSeamWarning,
    ClausalSeamTextCompareWarning,
    ClausalDeprecatedSpellingWarning,
    ClausalTitleCaseIdentifierWarning,
    ClausalScaleInNameWarning,
    ClausalKeywordArgumentWarning,
    ClausalRetiredQuasiQuoteWarning,
    ClausalStringInCatchPatternWarning,
)


#: The catch forms whose CATCHER is a pattern matched against a thrown term,
#: as ``{name: (arity, catcher position)}``.
_CATCH_PATTERN_FORMS = {"catch": (3, 1), "catch_recover": (3, 1), "catch_error": (2, 1)}

#: The ISO error formals, as ``{name: (arity, descriptor positions)}``.  A
#: DESCRIPTOR (the type in ``type_error(Type, Culprit)``, the action and type
#: in ``permission_error/3`` ...) is always an atom in the engine's errors; the
#: CULPRIT (the last argument of the /2 and /3 forms) is the offending term
#: itself and may well be a string, so it is not judged.
_ERROR_FORMAL_DESCRIPTORS = {
    "type_error": (2, (0,)), "domain_error": (2, (0,)),
    "existence_error": (2, (0,)), "permission_error": (3, (0, 1)),
    "representation_error": (1, (0,)), "evaluation_error": (1, (0,)),
    "resource_error": (1, (0,)), "syntax_error": (1, (0,)),
}


def _lint_string_in_catch_pattern(transformer, call) -> None:
    """Warn for a ``"..."`` STRING at a descriptor position of an ISO error
    formal inside ``error(Formal, _)`` in the catcher of a catch form
    (``ClausalStringInCatchPatternWarning``).

    Reads the SOURCE node, before the transform: the quote character comes
    from the file's quote map, and the mode in force from the transformer --
    only ``chars`` makes ``"..."`` a string.  Not judged under ``reify``
    (reflection and the rewriter read clauses as data; they do not load
    them)."""
    if transformer._double_quotes_mode != "chars" or transformer._reify:
        return
    func = call.func
    if not isinstance(func, Name) or call.keywords:
        return
    form = _CATCH_PATTERN_FORMS.get(func.id)
    if form is None or len(call.args) != form[0]:
        return
    catcher = call.args[form[1]]
    import warnings  # noqa: PLC0415
    for node in walk(catcher):
        if not (isinstance(node, Call) and isinstance(node.func, Name)
                and node.func.id == "error" and node.args):
            continue
        formal = node.args[0]
        if not (isinstance(formal, Call) and isinstance(formal.func, Name)):
            continue
        shape = _ERROR_FORMAL_DESCRIPTORS.get(formal.func.id)
        if shape is None or len(formal.args) != shape[0]:
            continue
        for position in shape[1]:
            lit = formal.args[position]
            if not (isinstance(lit, Constant) and type(lit.value) is str
                    and getattr(lit, "lineno", None) is not None):
                continue
            if _quote_of_positioned(transformer, lit) != '"':
                continue
            atom = "'" + lit.value.replace("\\", "\\\\").replace("'", "\\'") + "'"
            warnings.warn(ClausalStringInCatchPatternWarning(
                f"{transformer._filename or '<unknown>'}:{lit.lineno}:"
                f"{lit.col_offset + 1}: the catcher of {func.id}/{form[0]} has the string "
                f"\"{lit.value}\" in error({formal.func.id}(...), _), which is a STRING under "
                f"-double_quotes(chars); the engine's error terms carry ATOMS, "
                f"so this pattern never matches the error it names and the "
                f"error propagates past the catch. Write the atom {atom} "
                f"instead (an atom in every -double_quotes mode)."
            ), stacklevel=_stacklevel_outside_rewriter())


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
        if isinstance(rhs.func, Name) and _is_var_in_name_position(rhs.func.id):
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
    # There is no constant-reference scan here any more (2026-09-11).  A
    # constant name is atom-shaped now, so it is indistinguishable from any
    # other free Python name in a verbatim body -- ``math``, a helper, a
    # comprehension target -- and a scan by shape would either claim all of
    # them or none.  A mistyped ``++max_fien`` therefore fails as a Python
    # NameError when the clause runs, not as a load-time SyntaxError.  That
    # is the cost of spelling a constant like an atom, and it is the same
    # deal every other name in a ``++`` escape already had.
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
                            func=replace(Name(id="$Var", ctx=load), node),
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
            func=replace(Name(id=dollar_name(thunk_cls), ctx=load), node),
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


def _refuse_double_quoted_functor(transformer, func_node):
    """Refuse a DOUBLE-quoted string used as a functor (ISO 6.3.3).

    A functor is named by an atom, and under the strings design (spec §7) a
    double-quoted literal is not an atom spelling — in `chars` mode it is a
    char list, which cannot name anything.  Refusing it in every mode
    (rather than only after the flip) means the diagnostic is the same
    before and after, and no module quietly changes meaning when the default
    moves.  A `None` answer from the quote map means the quote is unknown
    (no source lines: the REPL, a programmatic AST) and the sugar keeps its
    pre-strings behaviour.

    ``_quote_of_positioned`` is called unconditionally, ``reify`` included:
    the mixed-quote-style error it can raise is a WELL-FORMEDNESS rule, and
    "reflection models more than it compiles" means more legal shapes, never
    malformed input.  `"a" 'b'` has no meaning to model — gating that call on
    ``_reify`` made ``reify_source`` answer with the atom ``ab``, silently
    inventing one of the two readings (fix round 2).  The FUNCTOR refusal,
    by contrast, IS compile-only and so IS exempt under ``reify=True``: it
    rejects a well-formed literal for a reason (ISO 6.3.3) that reflection
    does not care about, and a file must not become un-reifiable over it.
    See the ``_reify`` contract in ``TermTransformer``'s class docstring.

    Both places a string literal is read as a callable go through here — a
    body goal (``TermTransformer.visit_Call``) and a trailing-comma fact
    head (``EmbedTransformer.visit_Expr``) — so the refusal cannot drift
    apart between the head and the body of the same predicate.
    """
    quote = _quote_of_positioned(transformer, func_node)
    if quote != '"' or transformer._reify:
        return
    spelling = func_node.value
    # The suggestion is source text, so it has to survive being re-read: a
    # spelling containing a quote or a backslash needs them escaped or the
    # "fix" would not parse.
    single_quoted = "'{}'".format(
        spelling.replace("\\", "\\\\").replace("'", "\\'"))
    # ...and the bare-name alternative only exists when the spelling IS a
    # name AND is not read as a VARIABLE.  `"a b"(1)` has no bare form, and
    # neither has `"Foo"(1)`: bare in functor position a variable-shaped
    # name is either refused outright (``Foo(1)``, the TitleCase lint) or
    # silently something else (``FOO(1)``, ``_p(1)`` -- the unit-annotation
    # sugar, which dies much later in a message about SI prefixes).  So
    # offering `Foo(...)` would hand the author a second fault as the fix
    # for the first.  Single-quoting is the whole answer for all of them.
    #
    # The test is ``_is_logic_var_name``, not "capital initial": the
    # callable-position carve-out in ``_reads_as_variable`` is TitleCase-
    # only, so a LEADING-UNDERSCORE name in functor position really does
    # read as a variable -- ``_p(N, X) <- (... _p(M, X))`` is refused by
    # ``_check_var_shaped_predicate_names`` for exactly that reason.
    bare_hint = (f', or {spelling}(...) if it is a plain name'
                 if spelling.isidentifier()
                 and not _is_logic_var_name(spelling) else '')
    _raise_located_syntax_error(
        f'a double-quoted string is never a functor (ISO 6.3.3): '
        f'write {single_quoted}(...) for the atom{bare_hint}',
        func_node, transformer._source_lines, transformer._filename)


def _quoted_head_functor_name(transformer, func_node, shape):
    """Read a QUOTED head functor as the ``Name`` the atom stands for.

    ``'foo'(1),`` and ``'foo'(X) <- (...)`` name the predicate ``foo/1``, the
    same way the body goal ``'foo'(X)`` does — a functor is named by an atom
    (ISO 13211-1), and a single-quoted token is an atom whatever its
    capitalisation, so ``'Foo'(1),`` is ``Foo/1`` while the bare ``Foo(1)``
    remains a variable in functor position and is refused.

    Both head shapes go through here so the refusals cannot drift apart
    between a fact and a rule for the same predicate, and so neither drifts
    from the body reading in ``TermTransformer.visit_Call``:

    * ISO 6.3.3 — a double-quoted literal is not an atom spelling and can
      never name a functor (``_refuse_double_quoted_functor``);
    * a head, unlike a body goal, binds its functor as a module-level
      Python NAME (``$declare_head`` binds it, ``$head(<name>, ...)`` reads
      it; W4b-3 slice 5 -- it was a class statement parsed from source by
      ``_make_functor_class_ast``), so the spelling has to be a plain name.
      This is an implementation limit rather than an ISO rule, but it has to be stated HERE: with no
      check the generated source fails to parse and the author is shown
      CPython's complaint about a line of code they never wrote.

      NOT exempt under ``_reify``, unlike the ISO 6.3.3 refusal above, and
      the difference is not a judgement call: ``reify_source`` runs this
      very ``visit_Expr``, which (until W4b-3 slice 5) called
      ``_make_functor_class_ast``, which ``parse()``d the emitted class
      name, and still emits the name as a ``$head`` argument.  So reflection
      DOES emit it, and exempting the check just moves the failure
      downstream -- measured in the class era, ``'foo bar'(X) <- (bar(X))`` then raises ``ReifyError:
      invalid syntax. Perhaps you forgot a comma? (<unknown>, line 4)``,
      the unattributed CPython complaint this check exists to replace.  The
      contract in ``_refuse_double_quoted_functor`` is about rules whose
      REASON does not apply to reflection; this one's reason applies to
      reflection literally.  A quoted fact head has raised here under
      ``reify`` since the check was written, so refusing the rule and DCG
      heads the same way makes the three agree rather than adding a case.
      A BODY goal is legitimately more permissive: it names an atom and
      mints no class, so ``p(X) <- ('foo bar'(X))`` reifies.

    *shape* is the word the second message uses for the construct
    (``"fact"``, ``"clause"``, ``"DCG rule"``), so the diagnostic names what
    the author actually wrote.  A ``-module``/``-private`` export ENTRY
    passes *shape* ``None``: it mints the same class from the same spelling,
    so it owes both checks, but it is not a head and must not be described
    as one.
    """
    _refuse_double_quoted_functor(transformer, func_node)
    spelling = func_node.value
    if not spelling.isidentifier() or _keyword_module.iskeyword(spelling):
        because = (
            f'head a {shape} (a body goal may name it, a {shape} '
            f'head may not): rename it, or give the {shape} a '
            f'head that is a plain name'
            if shape is not None else
            'be declared (a body goal may name it, a declaration entry '
            'may not): rename it, or drop the entry and let the clauses '
            'define the predicate'
        )
        _raise_located_syntax_error(
            f'{spelling!r} is not a plain name, so it cannot {because}',
            func_node, transformer._source_lines, transformer._filename)
    name = Name(id=spelling, ctx=Load())
    copy_location(name, func_node)
    return name


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


# ── pi/e in ARITHMETIC position (ruling Q16, narrowed 2026-09-28) ──────────
#
# The arity-0 evaluables ``pi`` and ``e`` are builtins in an evaluated
# expression -- ``'is'(X, pi)``, ``eval_(2 * e, X)``, ``X == pi`` -- and need
# no declaration there.  Anywhere else (``f(e)``, a fact argument, ``T is e``)
# they are ordinary atoms, declared like any other.  The rewriter cannot see
# its position from ``visit_Name``, so a pre-pass over each module's Python
# AST marks the ``pi``/``e`` Name nodes that stand in arithmetic position
# with an attribute (which survives the rewriter's deepcopy of a body).

_ARITH_CONSTANTS = frozenset({"pi", "e"})
_ARITH_CMP_OPS = (Eq, NotEq, Lt, LtE, Gt, GtE)
#: goal name -> the argument indexes that are evaluated (ISO 8.6, 8.7), and
#: eval_/2's expression
_ARITH_GOAL_ARGS = {
    "is": (1,), "=:=": (0, 1), "=\\=": (0, 1), "<": (0, 1), ">": (0, 1),
    "=<": (0, 1), ">=": (0, 1), "eval_": (0,),
}
_ARITH_MARK = "_clausal_arith_constant"


def _call_name(func) -> "str | None":
    if isinstance(func, Name):
        return func.id
    if isinstance(func, Constant) and isinstance(func.value, str):
        return func.value
    return None


def _mark_arith_position_names(tree) -> None:
    """Mark each ``pi``/``e`` Name in arithmetic position in *tree*:
    an operand of ``==``/``!=``/``<``/``<=``/``>``/``>=``, an evaluated
    argument of a quoted ``'is'``/``'=:='``/``'<'``... or of ``eval_``, and
    below those only through arithmetic operators and evaluable functors."""
    from clausal.logic.exact_arith import EVALUABLE  # noqa: PLC0415
    def expr(node):
        if isinstance(node, Name):
            if node.id in _ARITH_CONSTANTS:
                setattr(node, _ARITH_MARK, True)
        elif isinstance(node, BinOp):
            expr(node.left)
            expr(node.right)
        elif isinstance(node, UnaryOp):
            expr(node.operand)
        elif isinstance(node, Call) and not node.keywords:
            name = _call_name(node.func)
            if name is not None and (name, len(node.args)) in EVALUABLE:
                for a in node.args:
                    expr(a)

    for node in _ast_module.walk(tree):
        if isinstance(node, Compare):
            if all(isinstance(op, _ARITH_CMP_OPS) for op in node.ops):
                for operand in (node.left, *node.comparators):
                    expr(operand)
        elif isinstance(node, Call):
            idxs = _ARITH_GOAL_ARGS.get(_call_name(node.func))
            if idxs and len(node.args) == 2:     # all of these are /2
                for i in idxs:
                    expr(node.args[i])


class TermTransformer(NodeTransformer):
    """Transform a Python expression AST into Python AST that constructs simple_ast nodes."""

    def __init__(transformer, atoms=frozenset(), import_remap=None,
                 source_lines=None, bare_atom_refs=None,
                 logic_var_refs=None, constants=frozenset(), filename=None,
                 reify=False, hidden_atoms=frozenset(), module_name=None,
                 declared_functors=None, atom_functor_sites=None,
                 zero_arity_heads=frozenset(),
                 quote_map=None, double_quotes_mode="chars",
                 seam=False,
                 python_visitor=None, titlecase_python_bound=None,
                 clause_var_names=None, modes_used=None):
        transformer.seen_vars = set()
        # The file's SHARED "which -double_quotes modes governed a literal"
        # sink (``EmbedTransformer.__init__``), a constructor parameter so
        # that no TermTransformer -- per-clause, seam, or arrow-lambda body
        # -- can be built without it (flip review M2: the lambda transformer
        # was built by hand and recorded nothing, so a file whose only
        # literals sat in lambda bodies reported no mode, and a file that
        # switched mode with one mode's literals only in lambdas reported a
        # single mode and was judged when it should have been left alone).
        # A caller with no file (the REPL, reflection) gets a private set.
        transformer._double_quotes_modes_used = (
            modes_used if modes_used is not None else set())
        # THE SEAM (``--term`` in Python-hosted code): ``seam`` marks a
        # transformer serving one seam expression; ``python_visitor`` is the
        # enclosing EmbedTransformer's ``visit``, run over every ``++``
        # operand so seams nest (a ``--`` inside a ``++`` inside a ``--``).
        # Whether the module DECLARED its ``-double_quotes`` mode is the
        # EmbedTransformer's fact alone (``_double_quotes_explicit``, which
        # the DoubleQuotesMode item reports to importers); the per-clause
        # copy that drove the seam "no mode declared" warning went with the
        # warning at the 2026-09-26 flip.
        transformer._seam = seam
        transformer._python_visitor = python_visitor
        # The TitleCase names this file's own hosted Python binds (``from x
        # import Foo``, ``class Foo``, ``Foo = ...``) -- the SAME live set
        # ``EmbedTransformer._titlecase_prepass`` fills, shared not copied,
        # exactly as ``_import_remap`` is.  Used only to decide what a
        # verbatim-Python thunk must NOT capture; it does not affect how a
        # term-position name reads (see ``_reads_as_variable``).
        transformer._titlecase_python_bound = (
            titlecase_python_bound if titlecase_python_bound is not None
            else set())
        # Names THIS clause uses as logic variables outside any thunk body,
        # accumulated by ``visit`` on each outermost call (see
        # ``note_clause_scope``).  A verbatim-Python thunk consults it so a
        # clause variable is captured even when its spelling collides with
        # something in the module namespace.
        # SHARED with a parent transformer (not copied), exactly as
        # ``_titlecase_python_bound`` is: a lambda body and a nested seam are
        # inside the enclosing CLAUSE, so a thunk in them must see the same
        # clause variables.  Starting a sub-transformer with an empty set
        # reintroduced the divergence from the other side -- one spelling
        # meaning two things depending only on whether it sat inside a
        # lambda, which is the invariant
        # ``test_a_thunk_inside_a_lambda_body_uses_the_same_exclusions``
        # exists to hold.
        transformer._clause_var_names: set[str] = (
            clause_var_names if clause_var_names is not None else set())
        transformer._visit_depth = 0
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
        # The 0-arity clause heads of the WHOLE file, collected by
        # ``EmbedTransformer._zero_arity_head_prepass`` before any body is
        # walked -- ``_declared_functors`` only knows a head once its clause
        # has been visited, so a value reference BEFORE the first clause
        # (under the removed -implicit_atoms) used to fall through to the class.
        transformer._zero_arity_heads = zero_arity_heads
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
        # and ``quote_of`` answers ``None`` for each lookup, which reads
        # every text literal as an ATOM: a ``"…"`` string (chars by default)
        # silently becomes an atom there, a wrong answer rather than a
        # refusal.
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
        # True only while visiting a Call's ``func``.  Term position
        # and callable position read a TitleCase name differently --
        # see ``_is_var_in_name_position`` and ``visit_Name``.
        transformer._in_callable_position = False

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
        if _is_dict_attr_access(
                func_expr, transformer._clause_scope_exclusions()):
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
        # D40 (operator ruling 2026-09-30): ``true(X)``/``false(X, Y)`` name
        # the user's own true/N and false/N (N >= 1), as in ISO and Scryer.
        # Only the bare name (arity 0) is the truth value; APPLIED, the
        # spelling is a functor, so the truth-value fold must not run here.
        if isinstance(func_expr, Name) and func_expr.id in _APPLIED_TRUTH_NAMES:
            return node_ast(
                "LoadName", func_expr,
                name=replace(Constant(value=func_expr.id), func_expr))
        prev = transformer._suppress_bare_atom_collection
        prev_callable = transformer._in_callable_position
        transformer._suppress_bare_atom_collection = True
        # Only a bare ``Name`` is a callable position in the sense that
        # matters here.  A nested callable (``f(a)(b)``) must not leak the
        # flag onto ``f(a)``'s own arguments, which are terms.
        transformer._in_callable_position = isinstance(func_expr, Name)
        try:
            return transformer.visit(func_expr)
        finally:
            transformer._suppress_bare_atom_collection = prev
            transformer._in_callable_position = prev_callable

    def visit_Call(transformer, call):
        visit = transformer.visit
        _lint_string_in_catch_pattern(transformer, call)

        # ``q(expr)`` is NOT special here.  It was a quasi-quotation that
        # stripped itself and lowered ``expr``; retired 2026-09-25, because a
        # term in argument position already lowers as DATA (a cell), so the
        # wrapper did nothing a plain term does not -- except hijack the name
        # ``q`` in every module (``--q(1)`` evaluated to 1, and a user's
        # ``q/1`` could not be called or built).  ISO term_expansion takes
        # plain terms; so does Clausal.  An old ``term_expansion(q(...), ...)``
        # rule now builds ``('q', ...)`` cells that match nothing, so
        # ``_lint_retired_quasi_quote`` says so at load time.

        # constant_number_units(Name, N, U) — COMPILE-TIME MODULE INSERTION.
        #
        # A builtin never receives the calling module (the registry hands
        # dispatch functions their arguments and a trail, and `_get_dispatch`
        # is a frozen protocol with out-of-tree implementors), so the /3
        # relation answered for every loaded module declaring the name, in
        # load order. That is the documented compromise at
        # `constant_value/2`, not a defect -- and the way out is that the
        # COMPILER knows the module. It already hands `$module` to
        # `$register_constant_units` when a declaration is lowered; reading
        # now works the way writing does.
        #
        # The module inserted is the name's OWNER, which is not always the
        # caller: an imported constant is registered on the module that
        # DECLARED it (`register_module_constant` records only a module's own
        # declarations, deliberately), so inserting the caller would make an
        # imported constant answer nothing. The import directive recorded the
        # owner in `_import_remap`, so the owner is known statically.
        #
        # Emitted through the ``++`` escape rather than a bespoke lowering,
        # so the module reference uses the one embedding path that already
        # exists and is tested.
        if (isinstance(call.func, Name)
                and call.func.id == "constant_number_units"
                and len(call.args) == 3 and not call.keywords):
            name_node = call.args[0]
            named = (isinstance(name_node, Name)
                     and not _is_logic_var_name(name_node.id))
            if named:
                ident = name_node.id
                if ident in transformer.constants:
                    mod_expr = replace(Name(id="$module", ctx=load), name_node)
                elif ident in transformer._import_remap:
                    owner = transformer._import_remap[ident].rsplit(".", 1)[0]
                    mod_expr = replace(
                        Call(func=replace(Name(id="__import__", ctx=load), name_node),
                             args=[replace(Constant(value=owner), name_node)],
                             keywords=[keyword(
                                 arg="fromlist",
                                 value=replace(List(elts=[replace(Constant(value="_"), name_node)],
                                                    ctx=load), name_node))]),
                        name_node)
                else:
                    raise SyntaxError(
                        f"constant_number_units({ident}, ...): `{ident}` is "
                        f"not a constant in this module. Declare it with "
                        f"-constant_number_units({ident}, <number>, <units>), "
                        f"or import it from the module that does with "
                        f"-import_from(<module>, [{ident}]).")
            else:
                # Unbound name: enumerate, but THIS module only -- an
                # unscoped enumeration is the same leak by another door.
                mod_expr = replace(Name(id="$module", ctx=load), call)
            fix_missing_locations(replace(mod_expr, call))
            # The same builder `constant()` ends in: a late read, evaluated
            # where the clause runs.
            #
            # NOT synthesised as `++expr` and re-visited. `++` is SURFACE
            # SYNTAX, and this code is already INSIDE the transformer that
            # consumes it -- emitting surface forms from here means handing
            # the reader something to re-read, one level below where we are.
            # It also does not work: the escape is recognised from the source
            # shape, so a manufactured double-UAdd is read as a term and the
            # module expression fails as `__import__/2 is not in scope as a
            # term class`. The failure is the symptom; the level confusion is
            # the reason. Build at the level you are at.
            module_term = _build_py_thunk_ast(transformer, call, mod_expr, [])
            if named:
                # The SPELLING, as a Python string, not the name re-visited.
                # In the importing module the imported name resolves to the
                # imported VALUE (a `LoadName` over the dotted remap), so
                # re-visiting it hands the registry a Quantity where it wants
                # a key. The spelling is what the registry is keyed by, and a
                # thunk over a str literal cannot be re-read as an atom, a
                # char list or a string by the -double_quotes ratchet.
                name_term = _build_py_thunk_ast(
                    transformer, call,
                    replace(Constant(value=ident), name_node), [])
                rest = [visit(a) for a in call.args[1:]]
            else:
                name_term = visit(call.args[0])
                rest = [visit(a) for a in call.args[1:]]
            positional = [module_term, name_term] + rest
            return node_ast(
                "Call", call,
                func=node_ast(
                    "LoadName", call,
                    name=replace(Constant(value="module_constant_units"), call)),
                args=list_ast(positional, call),
                kwargs=list_ast([], call))

        # constant(name) — retrieve a declared constant's VALUE.
        #
        # Replaces `++name` as the retrieval form (operator, 2026-09-11).
        # `++` says "what follows is Python", which is the one thing a
        # constant reference is not: the parentheses delimit the name, and
        # restricting the inside to a single atom means there is no shape
        # here that could be read as a Python expression.
        #
        # Lowered to the `++name` AST rather than reimplemented, so the two
        # cannot drift in binding time: this is a late-bound lookup of the
        # module global, exactly as the escape was.
        if isinstance(call.func, Name) and call.func.id == "constant":
            if call.keywords or len(call.args) != 1:
                raise SyntaxError(
                    f"constant() takes exactly one argument, the name of a "
                    f"declared constant: constant(max_fine); got "
                    f"{len(call.args)} arguments")
            target = call.args[0]
            if isinstance(target, Attribute):
                # constant(owner.name) -- module-prefixed access. The dotted
                # form is read as a QUALIFIED NAME, never evaluated as a
                # Python expression, so the invariant the message below
                # states is intact: what is inside still cannot be an
                # arbitrary expression, only a name or a name in a module.
                # Resolution is MORE static this way, not less -- the owner
                # is written at the site rather than inferred from imports.
                if dotted_attr_chain(target) is None:
                    raise SyntaxError(
                        f"constant() takes a bare name or a module-qualified "
                        f"name, not `{unparse(target)}` — the whole point of "
                        f"the parentheses is that what is inside cannot be a "
                        f"Python expression. Write constant(max_fine) or "
                        f"constant(other_module.max_fine).")
                return _build_py_thunk_ast(transformer, call, target, [])
            if not isinstance(target, Name):
                raise SyntaxError(
                    f"constant() takes a bare name or a module-qualified "
                    f"name, not `{unparse(target)}` — the whole point of the "
                    f"parentheses is that what is inside cannot be a Python "
                    f"expression. Write constant(max_fine).")
            if (target.id not in transformer.constants
                    and target.id not in transformer._import_remap):
                # An IMPORTED name passes. The importer genuinely cannot tell
                # a constant from an atom in the owner (2026-09-11) -- but it
                # does know WHO OWNS IT, and the lowering below is a late
                # module-global read that the import has already bound. So
                # the compile-time question is "do I know who owns this",
                # which is answerable statically, rather than "is this a
                # constant", which is not without executing the owner.
                raise SyntaxError(
                    f"constant({target.id}): nothing declares `{target.id}`. "
                    f"Declare it with -constant_value({target.id}, <value>) "
                    f"or -constant_number_units({target.id}, <number>, "
                    f"<units>) above this clause, or import it.")
            # The same builder the ``++`` escape path ends in, so the two
            # cannot drift: a PyThunk over a bare module-global read, with no
            # captured logic variables (a constant name is never one).
            return _build_py_thunk_ast(
                transformer, call,
                replace(Name(id=target.id, ctx=load), target), [])

        # if_(cond, then, else) → IfExpr node.  (``If``, the old spelling,
        # is TitleCase and never reaches here: the lint raises first.)
        if isinstance(call.func, Name) and call.func.id in _ITE_NAMES:
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
            # ...but only the ATOM spelling — see
            # ``_refuse_double_quoted_functor`` for the ISO 6.3.3 rule, the
            # ``reify`` contract, and why the refusal is shared with the
            # fact-head reading of the same sugar.
            _refuse_double_quoted_functor(transformer, call.func)
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
                func=replace(Name(id="$Quantity", ctx=load), call),
                args=[call.func, replace(Dict(keys=[], values=[]), call)],
                keywords=[],
            )
            return _build_py_thunk_ast(transformer, call, inner, [])
        elif (
            not (isinstance(call.func, Name)
                 and not _is_var_in_name_position(call.func.id))
            and not isinstance(call.func, Attribute)
            and len(call.args) == 1
            and _is_unit_expr(call.args[0])
            and not call.keywords
        ):
            # <expr>(Unit) — unit annotation sugar.
            # Any expression that is not a predicate/functor name or attribute
            # access can be annotated with a unit: 5(metre), X(newton),
            # [1,2,3](metre), (A + B)(metre/second), etc.
            # Transforms to: ++(Quantity(<expr>, Unit))
            raw_unit = call.args[0]
            # The magnitude of ``(A + Foo)(metre)`` is Clausal, so a
            # TitleCase name there is a clause variable.
            var_names = _collect_logic_var_names(
                call.func, transformer._clause_scope_exclusions())
            inner = Call(
                func=replace(Name(id="$Quantity", ctx=load), call),
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
                head=_head_ctor_ast(transformer.visit(head_ast)),
                body=transformer.visit(_lower_dict_reads(
                    head_ast, body_ast,
                    transformer._clause_scope_exclusions())),
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

        ``'foo'`` is an atom in every mode; ``"foo"`` is a string under
        ``-double_quotes(chars)`` (the default since 2026-09-26) and an atom
        under ``-double_quotes(atom)``, the opt-out.

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
            if quote == '"':
                # Cross-mode lint (2026-09-26): tell the file's importers
                # which modes its ``"..."`` literals were read under.
                transformer._double_quotes_modes_used.add(transformer._double_quotes_mode)
            if quote == '"' and transformer._double_quotes_mode == "chars":
                # STAGE 1 of the atoms-as-str flip (spec 2026-09-18): a chars
                # string is the CARRIER ``('$chars', text)``, not a bare str.
                # A tuple of constants is a legal ``Constant`` value and
                # marshals into co_consts.
                return replace(Constant(value=(CHARS_TAG, sys.intern(value))), constant)
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
            return replace(Constant(value=sys.intern(value)), constant)   # STAGE 2: the atom is the str
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
            # The EFFECTIVE reading, not the lexical one: a dict key is a
            # term, so a TitleCase key is a variable key now -- but a name
            # this file has BOUND (``Undefined``, an ``-import_from`` name)
            # is an atom key exactly as before.  Asking the lexical rule
            # here sent those down ``visit(key)``, which answers a
            # ``LoadName`` -- unhashable, so the dict blew up at
            # construction with a bare ``TypeError``.
            and not transformer._reads_as_variable(key.id)
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
                func=replace(Name(id="$DictTerm", ctx=load), dict_expr),
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
            modes_used=transformer._double_quotes_modes_used,
            # Inherited for the same reason ``_import_remap`` is: a ``++``
            # or f-string INSIDE a lambda body resolves its free names in
            # the same module namespace, so it must exclude the same ones.
            titlecase_python_bound=transformer._titlecase_python_bound,
            # And the enclosing clause's variables, for the same reason
            # again: a lambda body is inside the clause, so a name the
            # clause binds is a variable there too.
            clause_var_names=transformer._clause_var_names,
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
                        func=runtime_name_ast("PosOrKwParam", source),
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
                    func=runtime_name_ast("Params", source),
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
                    func=runtime_name_ast("Params", source),
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

    def note_clause_scope(transformer, *nodes):
        """Record which names *nodes* use as logic variables outside thunks.

        Accumulates, so it is safe to call more than once and in any order.
        That is what lets ``visit`` call it automatically on every outermost
        root; the auto-note is sufficient ONLY where one transformer visits
        exactly one root, which is the single-goal query and the ``--`` seam.

        Everywhere else the call here is REQUIRED, not an optimisation, and
        each is marked at its call site.  ``visit``'s auto-note fires once
        per outermost root, so wherever a transformer visits SEVERAL roots
        that share one variable scope, a thunk in root 1 is decided before
        root 2's names are known -- and the fault is silent, because the two
        readings differ only in what the thunk formats.  The five sites:

        * the arrow rule, the DCG rule and the bodyless fact -- a clause is
          visited as one root per head argument, then the body, so a thunk
          in the HEAD would otherwise see only earlier arguments;
        * the ``--{}`` block form -- one root per statement in the block;
        * the REPL conjunction path (``import_hook._StarQueryTransformer``)
          -- one root per conjunct.

        (Two earlier versions of this docstring claimed coverage the code
        did not have: first describing the three clause sites while none
        existed, then calling the auto-note sufficient for the ``--{}``
        block and the REPL while both were multi-root.  A claim here is
        worth nothing unless it has been read against the call sites.  If a
        new multi-root shape is added it needs a call too -- the auto-note
        alone makes POSITION decide, which is the fault this whole mechanism
        removes.)

        A sub-transformer SHARES the set rather than noting afresh: see the
        ``clause_var_names`` argument to ``TermTransformer`` and to
        ``_make_term_transformer``.  The ``--`` seam takes no set, and needs
        none: a seam is Python-hosted code, so there is no enclosing clause
        whose variables it could inherit -- its own scope comes from the
        auto-note, and ``_seam_term_ast`` computes ``fresh`` from the same
        clause-scope exclusions.
        """
        excluded = transformer._clause_scope_exclusions()
        for node in nodes:
            if node is not None:
                transformer._clause_var_names |= _clause_variable_names(
                    node, excluded)

    def visit(transformer, node):
        # The OUTERMOST visit is the clause (or term) root: note its variable
        # names before rewriting anything, so a thunk lowered part-way
        # through the walk already knows what the whole clause binds.
        # Depth-counted because ``generic_visit`` recurses through here.
        if transformer._visit_depth == 0:
            transformer.note_clause_scope(node)
        transformer._visit_depth += 1
        try:
            return super().visit(node)
        finally:
            transformer._visit_depth -= 1

    def _refuse_markers_in_format_specs(transformer, joined) -> None:
        """Refuse ``--X`` inside an f-string FORMAT SPEC.

        A nested slot in a format spec (``f"{N:>{--W}}"``) is a ``JoinedStr``
        hanging off ``FormattedValue.format_spec``, and nothing walks
        ``format_spec`` -- not the implicit collector, not the marker
        collector, not the stripper.  So a marker written there is not
        captured, not stripped, and (the part that matters) not CHECKED: it
        reaches the lambda body as literal ``--W`` and resolves in the module
        namespace at search time.  ``f"{N:>{--Match}}"`` died with ``bad
        operand type for unary -: 'type'`` -- having found the AST node class
        -- at query time, with no load diagnostic anywhere.

        That is the marker failing at the single thing it promises over the
        bare name.  The bare spelling has the same hole (a format spec
        captures nothing on either side, which is why ``f"{N:>{W}}"`` is
        broken too), and that is precisely why a reader would reach for the
        explicit marker there and be worse off.  Refusing keeps the promise
        without inventing an asymmetry between the two spellings.

        Only where the marker is recognised at all -- inside a seam the
        ``--`` is not a marker, so there is no promise to keep.
        """
        if transformer._python_visitor is not None:
            return
        for value in joined.values:
            if not isinstance(value, FormattedValue):
                continue
            if value.format_spec is None:
                continue
            stray = _collect_marked_var_names(value.format_spec)
            if stray:
                name = stray[0]
                _raise_located_syntax_error(
                    f"`--{name}` is not supported inside an f-string format "
                    f"spec. A format spec captures no clause variables — "
                    f"neither `{name}` nor `--{name}` — so the marker could "
                    f"not be honoured there. Write the marker in a VALUE "
                    f"slot, or do the whole formatting in a `++` escape, "
                    f"where `--{name}` is honoured.",
                    joined, transformer._source_lines, transformer._filename)

    def _marked_var_names(transformer, subtrees, node) -> list[str]:
        """The ``--X`` markers in *subtrees*, checked against this clause.

        The marker is an ASSERTION -- "``X`` is this clause's logic
        variable" -- and unlike the bare spelling it can be checked, because
        a bare name the clause does not bind is a legal reference to the
        module namespace while a marked one cannot be anything.  So a marked
        name absent from the clause scope is a load-time error rather than a
        fresh unbound ``Var`` silently formatted as ``_7``, or a class
        silently formatted as ``<class '...'>``.  Being loud about it is the
        entire reason the marker is worth having over the bare name; a
        marker that merely agreed would be a synonym.

        NOT recognised where the thunk body is handed back to a Python
        visitor -- i.e. inside a seam.  There a ``++`` operand is hosted
        Python again, and ``--expr`` is already THE SEAM, nesting to any
        depth (see ``EmbedTransformer.visit_UnaryOp``).  Giving one spelling
        a second, narrower meaning in that one context would not be
        additive, and the seam transformer holds no clause scope to check
        against either.
        """
        if transformer._python_visitor is not None:
            return []
        marked: list[str] = []
        for subtree in subtrees:
            for name in _collect_marked_var_names(subtree):
                if name not in marked:
                    marked.append(name)
        for name in marked:
            if name not in transformer._clause_var_names:
                _raise_located_syntax_error(
                    f"`--{name}` marks `{name}` as this clause's logic "
                    f"variable, but no goal outside a thunk uses that name, "
                    f"so it would be captured unbound. Bind `{name}` in the "
                    f"clause, or write `{name}` without the marker to reach "
                    f"the module namespace binding of that name.",
                    node, transformer._source_lines, transformer._filename)
        return marked

    def _clause_scope_exclusions(transformer) -> frozenset:
        """This file's clause-scope exclusions -- see the module function."""
        return _clause_scope_exclusions(transformer._import_remap)

    def _python_scope_exclusions(transformer) -> frozenset:
        """This file's Python-scope exclusions -- see the module function."""
        return _python_scope_exclusions(
            transformer._import_remap, transformer._titlecase_python_bound,
            transformer._clause_var_names)

    def _reads_as_variable(transformer, identifier: str) -> bool:
        """The EFFECTIVE variable reading of *identifier* in this file.

        ``_is_logic_var_name`` is the lexical rule; this is the rule as the
        module actually applies it, and every place that must agree with
        ``visit_Name`` has to ask THIS, not the lexical predicate.  Keeping
        two notions of "is a variable" is what silently produced clause code
        referencing an unregistered ``_v6``: one classifier said ``Clause``
        was a variable while ``visit_Name`` had already compiled it as a
        functor reference.

        Identical to ``_is_logic_var_name`` for every spelling that was a
        variable before 2026-09-10.  For the capital-initial names that
        joined the class then (``Foo``, not ``FOO``) it subtracts the three
        positions where the file has said the name means something else --
        see the comment in ``visit_Name``.
        """
        return _is_logic_var_name(identifier) and not (
            _is_titlecase_identifier(identifier)
            and (transformer._in_callable_position
                 or identifier in transformer._clause_scope_exclusions())
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
        # A bare name is NEVER the constant (operator's rule, 2026-09-11):
        # ``pi`` is the atom, ``++pi`` is the value, and one name carries
        # both without conflict.  So there is no constants branch here --
        # a declared constant name takes the ordinary atom path below,
        # which compiles a DECLARED atom straight to its cell literal
        # ``("pi",)`` and never consults the module global.  The global is
        # left holding the value, which is what ``++pi`` reads.
        #
        # Two things had to move for that to be true, both in compiler_v2:
        # the -module/-private atom binding must not clobber a declared
        # constant's global, and the bare-atom-reference pass must not
        # accept a constant's global as evidence that the name is declared.
        # See ``_process_declarations`` and ``_process_bare_atom_refs``.
        # Anonymous variable: each _ is a fresh Var, never reused.
        if identifier == "_":
            return replace(
                Call(
                    func=replace(Name(id="$Var", ctx=load), name),
                    args=[],
                    keywords=[],
                ),
                name,
            )
        # Logic variable: leading single underscore OR capital initial.
        # Examples (underscore): _x, _foo, _head — all are logic variables.
        # Examples (capital):    X, FOO, HEAD, N1, MAX_OF, Foo, FooBar.
        # Excluded: __, __init__ (dunder-style), lowercase.
        #
        # THE CARVE-OUT, and only for the capital-initial names that joined
        # the class on 2026-09-10 (``Foo``, not ``FOO``).  A TitleCase name
        # is a variable in TERM position only, and not when this file has
        # explicitly BOUND it.  Three cases, all of them TitleCase-only:
        #
        # * CALLABLE POSITION (``transformer._in_callable_position``, set by
        #   ``_visit_call_func``).  ``Foo(X)`` is a functor, never a variable
        #   — a variable there would be the unit-annotation sugar, which is
        #   the whole reason the lint still refuses TitleCase functors.  This
        #   is also what keeps ``_check_var_shaped_predicate_names`` honest:
        #   without it a TitleCase body call registered a variable READ, and
        #   the file was refused for "predicate name also read as a logic
        #   variable" instead of getting the lint's ``++Name`` remedy.
        # * an ``-import_from`` name (``_import_remap``) — otherwise
        #   ``-import_from(py.units, [Metre])`` binds a name no use site can
        #   reach, and every existing units import becomes a load error.
        # * ``_TITLECASE_EXEMPT_NAMES`` (``Undefined``, the injected third
        #   truth value) — otherwise it silently becomes a fresh variable
        #   that unifies with anything instead of the value it names.
        #
        # These are exactly the carve-outs the TitleCase lint has always had,
        # so it is one rule: TitleCase reads as a variable in precisely the
        # positions where the lint used to refuse it.  ALL-CAPS is
        # deliberately NOT carved out anywhere — it was a variable before
        # this change, and nothing may start reading ``FOO`` as a binding.
        if transformer._reads_as_variable(identifier):
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
                            func=replace(Name(id="$Var", ctx=load), name),
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
                Constant(value=mangle(transformer._module_name, identifier)),   # STAGE 2
                name,
            )
        if identifier in transformer.atoms:
            return replace(Constant(value=sys.intern(identifier)), name)   # STAGE 2: the atom is the str
        if (((identifier in transformer._declared_functors
                  and len(transformer._declared_functors[identifier]) == 0)
                 or identifier in transformer._zero_arity_heads)
                and not transformer._in_callable_position):   # a Name in FUNCTION position is a call (_visit_call_func)
            # STAGE 2 (spec 2026-09-18 §1 table, §4): a 0-arity PREDICATE
            # referenced as a VALUE is the atom of its name -- the str, as in
            # ISO -- and not its class: the zero-field-class-as-atom legacy
            # is gone.  In GOAL position the same name is a call (visit_Call).
            return replace(Constant(value=sys.intern(identifier)), name)
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
        if (identifier in _ARITH_CONSTANTS
                and getattr(name, _ARITH_MARK, False)):
            # ``pi``/``e`` in an evaluated expression: the evaluable
            # constant, a builtin needing no declaration there (the atom,
            # which evaluation reads as the number)
            return replace(Constant(value=sys.intern(identifier)), name)
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
        if _is_dict_attr_access(
                attr_node, transformer._clause_scope_exclusions()):
            # Expand the sugar with the SHARED, syntax-only pass (the SMT
            # prover runs the very same function on its own parse), then
            # compile the resulting ``P[key]`` through ``visit_Subscript`` —
            # so the key is routed through ``visit_Name`` exactly as a
            # hand-written subscript's index is: declared atom, imported
            # name, logic variable, or bare-atom reference registered for
            # the mint / strict-atoms passes.  Never intern the attribute
            # name directly.
            return transformer.visit(desugar_surface(
                deepcopy(attr_node),
                transformer._clause_scope_exclusions()))
        # Collect the full dotted chain and validate each part.
        parts = []
        node = attr_node
        while isinstance(node, Attribute):
            # A qualified name's attribute is a NAME component, never a
            # term -- ``mod.Pred`` is this docstring's own example of the
            # supported form, and ``prolog.TruncDiv``/``prolog.Rem`` are how
            # the Prolog bridge spells the ISO operators.  So TitleCase here
            # is a name, matching the lint, which has never read attributes.
            if _is_var_in_name_position(node.attr):
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
        # The EFFECTIVE reading, matching the dict-sugar test just above: a
        # base this file does not read as a variable (``Undefined``, an
        # ``-import_from`` name) is a legitimate qualified base.  Asking the
        # lexical rule refused ``Undefined.k`` outright once the dict-sugar
        # test stopped claiming it.
        if (_is_logic_var_name(node.id)
                and node.id not in transformer._clause_scope_exclusions()):
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
        #
        # ``include_titlecase=False`` for the same reason as a ``++`` operand,
        # and it is the same machinery: both lower to a lambda whose
        # PARAMETERS are the collected names, so collecting ``Fraction`` out
        # of ``f"{Fraction(1, 3)}"`` shadows the module global with an unbound
        # ``Var`` and the interpolation dies at query time with
        # ``'AttVar' object is not callable``.  An interpolation slot is
        # Python by definition, exactly like a ``++`` operand -- and
        # ``_lint_titlecase`` returns early on ``JoinedStr``, so there is no
        # load-time diagnostic to fall back on either.
        var_names = []
        seen: set[str] = set()
        for v in node.values:
            if isinstance(v, FormattedValue):
                for name in _collect_logic_var_names(
                        v.value, transformer._python_scope_exclusions()):
                    if name not in seen:
                        seen.add(name)
                        var_names.append(name)

        # ``--X`` — the EXPLICIT spelling of the same capture.  Read from the
        # slot VALUES, exactly where the implicit rule reads.  A FORMAT SPEC
        # is refused rather than read: neither spelling is captured there
        # (nothing walks ``format_spec``), so a marker in one would survive
        # into the lambda body verbatim and resolve in the module namespace
        # -- ``f"{N:>{--Match}}"`` died at QUERY time with ``bad operand type
        # for unary -: 'type'``, having silently found the class.  The marker
        # is sold as the spelling that cannot be silently misread, so the one
        # position where it could be is a load error, not a quiet no-op.
        transformer._refuse_markers_in_format_specs(node)
        expression = node
        marked = transformer._marked_var_names(
            [v.value for v in node.values if isinstance(v, FormattedValue)],
            node)
        if marked:
            # Every marked name is ALREADY in ``var_names``: the marker is
            # refused unless the name is a clause variable,
            # ``_python_scope_exclusions`` subtracts the clause variables,
            # and the implicit collector above walked the UNSTRIPPED values,
            # where the marked ``Name`` is an ordinary reachable child.  So
            # the marker adds no capture power -- it adds the CHECK.  Stated
            # rather than coded around, because a merge loop here reads as
            # though names could arrive by this route alone and they cannot.
            assert all(n in var_names for n in marked), (marked, var_names)
            expression = deepcopy(node)
            for v in expression.values:
                if isinstance(v, FormattedValue):
                    v.value = _strip_variable_markers(v.value)

        if transformer._double_quotes_mode == "chars" and not transformer._reify:
            # RULED 2026-09-28 (R2): an f-string in a clause is a STRING, the
            # same term a ``"..."`` literal is under the module's
            # ``-double_quotes`` mode -- the chars carrier by default.  It
            # used to be the bare Python ``str`` the f-string evaluates to,
            # which is an ATOM since the flip.  Under ``-double_quotes(atom)``
            # it stays the atom, as ``"..."`` does.  Reflection reads the
            # f-string's own text and is left alone.
            expression = copy_location(Tuple(
                elts=[copy_location(Constant(value=CHARS_TAG), node),
                      expression],
                ctx=load), node)
        return _build_py_thunk_ast(
            transformer, node, expression, var_names, thunk_cls="FStringThunk",
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
        # Adjacency (no space between the two '+' signs) is part of the
        # question -- see ``_double_prefix_operand``.
        escaped = _python_escape_operand(unary_op)
        if escaped is not None:
            expression = escaped
            var_names = _collect_logic_var_names(
                expression, transformer._python_scope_exclusions())
            # ``--X`` — the explicit spelling of the same capture.  Collected
            # from the ORIGINAL operand and stripped before the seam's Python
            # visitor runs, for the same reason the names above are read
            # there: what the author wrote is what the marker is about.
            marked = transformer._marked_var_names([escaped], unary_op)
            if marked:
                # Already captured -- see the same assertion in
                # ``visit_JoinedStr`` for why the marker cannot add a name
                # the implicit collector above did not already take.
                assert all(n in var_names for n in marked), (marked, var_names)
                expression = _strip_variable_markers(escaped)
            if transformer._python_visitor is not None:
                # A seam's ``++`` operand is Python-hosted code again, so it
                # may itself contain ``--`` (nesting to any depth).  The
                # variable names were collected from the ORIGINAL operand
                # above: an inner seam's own new variables are bound inside
                # the thunk and must not become outer parameters.
                expression = transformer._python_visitor(expression)
            return _build_py_thunk_ast(transformer, unary_op, expression, var_names)

        # -n(Unit) / -n(): fold the USub into the numeric callee so the
        # unit-sugar transform sees (-n)(Unit) and yields ++(Quantity(-n, Unit))
        # rather than Negate(++thunk), which term unification never evaluates —
        # so -3(second) works in `is`/argument position, not only after `:=`
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
                        func=runtime_name_ast("PosOnlyParam", argument),
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
                        func=runtime_name_ast("PosOrKwParam", argument),
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
                        func=runtime_name_ast(param_class, argument),
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
                        func=runtime_name_ast("VarPositional", argument),
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
                        func=runtime_name_ast("KwOnlyParam", argument),
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
                        func=runtime_name_ast("VarKeyword", argument),
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
                    func=runtime_name_ast("Params", source),
                    args=[],
                    keywords=[make_keyword_node("params", params_list, source)],
                ),
                source,
            )
        # No parameters at all
        return runtime_name_ast("Params", parameter_spec)


# ─── Functor class generator ──────────────────────────────────────────────────


#: The modes ``-double_quotes(...)`` accepts -- the ONE list, read by the
#: loader (``_handle_double_quotes_directive``) and by the rewrite driver.
DOUBLE_QUOTES_MODES = ("atom", "chars")


def _import_module_prepass(module) -> set:
    """The dotted paths of every top-level ``-import_module(path)`` in the
    file, read before the walk so a seam ABOVE its directive is judged too
    (the cross-mode literal lint's dotted bases)."""
    found = set()
    for stmt in getattr(module, "body", ()):
        value = getattr(stmt, "value", None)
        if (isinstance(stmt, Expr) and isinstance(value, UnaryOp)
                and isinstance(value.op, USub) and isinstance(value.operand, Call)
                and isinstance(value.operand.func, Name)
                and value.operand.func.id == "import_module"
                and len(value.operand.args) == 1):
            path = _dotted_name_from_ast(value.operand.args[0])
            if path is not None:
                found.add(path)
    return found


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

    The name may be QUOTED (``'Foo'/1``).  A functor is named by an atom and
    a single-quoted token is one, so the two spellings mean the same entry --
    and for a capital-initial predicate the quoted spelling is the ONLY one,
    since bare ``Foo`` in that position is a logic variable.  Reading only the
    bare form here made the quoted entry fall through to "other item shapes",
    which registers nothing at all: no class, no signature, no arity check,
    and no diagnostic either.  The caller applies the double-quote and
    plain-name rules to it, exactly as it does for a head.
    """
    if (
        isinstance(node, BinOp)
        and isinstance(node.op, Div)
        and isinstance(node.left, (Name, Constant))
        and isinstance(node.right, Constant)
        and isinstance(node.right.value, int)
        and node.right.value >= 0
    ):
        if isinstance(node.left, Constant):
            if not isinstance(node.left.value, str):
                return None
            return node.left, node.right.value
        return node.left.id, node.right.value
    return None


def _resolved_export_spec(transformer, spec):
    """Turn ``_predicate_export_spec``'s answer into ``(name, arity)``.

    The reader hands back the quoted name's ``Constant`` NODE rather than a
    string, because deciding what that spelling may be is the caller's job
    and needs the node's position: the entry mints a functor class exactly
    as a head does, so it owes the same ISO 6.3.3 refusal and the same
    plain-name limit, attributed to the entry the author wrote.
    """
    name, arity = spec
    if isinstance(name, Constant):
        name = _quoted_head_functor_name(transformer, name, None).id
    return name, arity


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


def _parse_meta_predicate_args(args):
    """Parse ``-meta_predicate(p(1, '?'), q(0, ':', '+'))`` (or one list of
    heads) into ``[(functor, arity, specs), ...]``.

    Operator ruling 2026-09-25 (Scryer's meta_predicate/1).  A spec is what
    Scryer's ``setup_meta_predicate`` accepts: a non-negative integer, or one
    of the atoms ``'+'``, ``'-'``, ``'?'``, ``':'`` -- written quoted, since
    none of them is a Python name.  ``^`` and ``//`` are refused, as Scryer
    refuses them (``InvalidMetaPredicateDecl``).
    """
    from clausal.logic.meta_predicate import valid_spec  # noqa: PLC0415
    if len(args) == 1 and isinstance(args[0], List):
        args = args[0].elts
    heads = []
    for arg in args:
        if not (isinstance(arg, Call) and isinstance(arg.func, Name)
                and not arg.keywords and arg.args):
            raise SyntaxError(
                "Malformed argument in -meta_predicate(...): expected a head "
                f"like apply_all(1, '?'), got {dump(arg)}")
        specs = []
        for spec in arg.args:
            value = spec.value if isinstance(spec, Constant) else None
            if isinstance(value, bool) or not valid_spec(value):
                raise SyntaxError(
                    f"-meta_predicate({arg.func.id}(...)): invalid meta "
                    f"argument specifier {dump(spec)}; expected an integer "
                    "0..N or one of '+', '-', '?', ':'")
            specs.append(value)
        heads.append((arg.func.id, len(specs), tuple(specs)))
    if not heads:
        raise SyntaxError("-meta_predicate(...) requires at least one head")
    return heads


# The guard reference inside the parsed atom-binding template.  A ``$`` name
# cannot be spelled in Python source, so the template names this PLACEHOLDER
# and ``_swap_placeholder`` re-spells it ``$keeps_predicate`` after ``parse``
# (the same mechanism ``_make_atom_str_assign_ast`` uses for ``$mint``).  A
# placeholder, not a bare name: the user's own atom may be spelled like the
# helper, and that name must stay the user's in the rest of the block.  (It
# named ``$PredicateMeta`` while the guard was an ``isinstance`` test and a
# predicate was a class; W4b-3 slice 5.)
_KEEPS_PLACEHOLDER = "__CLAUSAL_KEEPS__"


def _swap_placeholder(block, placeholder, runtime_name):
    """Re-spell every ``Name`` *placeholder* in *block* as the ``$`` twin of
    *runtime_name*; no other name in the block is touched."""
    twin = dollar_name(runtime_name)
    for node in walk(block):
        if isinstance(node, Name) and node.id == placeholder:
            node.id = twin
    return block


def _head_ctor_ast(head_ast):
    """A clause HEAD is constructed like any other term: ``<cls>(...)``.

    P2 Task 3 (2026-09-19) routed it through ``<cls>._clausal_head(...)``
    instead, because ``PredicateMeta.__call__`` had just started building
    CELLS and the compiler's head channel still stored and lowered an
    INSTANCE.  The head flip (step B, 2026-09-19) closed that: every head
    reader takes a cell positionally, so the head channel has no separate
    constructor and this is the identity again.

    Kept as a named function rather than deleted at its six call sites: it is
    where "what a head is built as" is decided, and the next change to that
    question (P4, when the class goes) wants one place to make it.

    W4b-2d task 5 (2026-09-24): the head no longer CALLS the binding.  A
    module-level head ``p(a, X=x)`` is emitted as ``$head(p, a, X=x)``
    (``clausal.logic.predicate.head_cell``): a ``PredicateMeta`` class is
    still called exactly as before (same cell, same errors), and a predicate
    HANDLE -- a ``str``, not callable -- builds the cell from its plain name
    and the owner Database's registered field names, through the same
    ``build_term_cell`` the class uses.  Only a head whose callee is a plain
    ``Name`` is wrapped: an expression-level rule head (``assertz(p(X) <-
    q(X))``) is already a ``$Call(func=$LoadName(...))`` node, lowered at
    compile time, and a ``$``-name is a runtime constructor, never a
    predicate binding.
    """
    if (isinstance(head_ast, Call) and isinstance(head_ast.func, Name)
            and not head_ast.func.id.startswith("$")):
        callee = head_ast.func
        head_ast.func = copy_location(Name(id="$head", ctx=Load()), callee)
        head_ast.args = [callee, *head_ast.args]
    return head_ast


def _make_predicate_decl_ast(functor_name, field_names, source):
    """The statement that declares *functor_name* as a predicate of the
    module, with *field_names* as its head's field names (W4b-3 slice 5).

    Generated code (example for ``fib`` with fields ``n``, ``f``)::

        $declare_head('fib', ('n', 'f'))

    ``$declare_head`` (``clausal.logic.predicate.declare_head``) binds the
    module's own predicate HANDLE under the name and records the field names
    (and this statement's source position) in the namespace's
    ``$predicate_heads`` record, which ``$head`` builds the module's heads
    against and step 4 of ``compiler_v2.compile_module`` stamps as the row's
    ``declared_at``.  It decides WHETHER to bind with the same rules the
    guarded class block this replaced spelled in Python (see
    ``predicate._declares_over``): an unbound name, a runtime-table alias,
    a different-fields ``PredicateMeta``, this module's own handle declared
    with other field names, or the pooled ATOM of the same spelling are
    taken; anything else (an imported handle, a user's own value) is left
    alone.

    This replaced a guarded ``class <functor>(metaclass=$PredicateMeta):
    _fields = (...)`` block -- about 17,000 class creations per suite run --
    whose class the flip turned into this same handle at step 4a-bis.
    """
    stmt = Expr(value=Call(
        func=Name(id="$declare_head", ctx=Load()),
        args=[
            Constant(value=functor_name),
            Tuple(elts=[Constant(value=f) for f in field_names], ctx=Load()),
        ],
        keywords=[],
    ))
    # Position the whole statement at the declaration: the recorded site is
    # the "registered by:" line of a construction error.
    for node in walk(stmt):
        copy_location(node, source)
    return stmt


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

        if not $keeps_predicate('foo'):
            foo = $mint('foo')

    The guard mirrors ``_make_predicate_decl_ast``'s spirit: a name already
    bound to a predicate this module declared (an earlier clause's
    ``$declare_head`` in this same file -- W4b-3 slice 5; it tested
    ``isinstance(.., PredicateMeta)`` while that was a class) is left alone
    rather than clobbered by the atom placeholder; any other existing value
    (unbound, or a stale atom from the process-wide ``predicate_builtins``
    preseed) is safely overwritten with this atom's own spelling.

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
        f"if not {_KEEPS_PLACEHOLDER}({atom_name!r}):",
        f"    {atom_name} = None",
    ]
    tree = parse("\n".join(lines))
    block = tree.body[0]
    _swap_placeholder(block, _KEEPS_PLACEHOLDER, "keeps_predicate")
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

    A name DECLARED at several arities (operator ruling 2026-09-29) comes
    as ``(name, {arity: fields})`` and is registered as that dict: the
    registry is keyed by name, and the value carries each arity's own
    fields (``cells.registry_signatures`` reads both shapes).  A dict value
    rides ``_make_import_signatures_update_ast``'s copy unchanged.

    Returns ``None`` when *entries* is empty (an all-atom ``-module``/
    ``-private`` list has nothing to register).
    """
    if not entries:
        return None
    dict_text = ", ".join(
        f"{name!r}: {(fields if isinstance(fields, dict) else tuple(fields))!r}"
        for name, fields in entries
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


def _wrap_import_for_pl_data(import_stmt, resolved_module, pairs, eligible,
                             source):
    """``try: <import_stmt> except ImportError: <bind .pl data names>``.

    The target's kind (``.pl``, ``.clausal``, Python) is only known at run
    time, so the fallback is emitted for every ``-import_from`` and decides
    there: ``clausal.pl_data_imports.bind_data_names`` answers ``False`` for
    anything but a loaded ``.pl`` module, and the bare ``raise`` then
    re-raises CPython's own error untouched."""
    text = (
        "try:\n"
        "    pass\n"
        "except ImportError as _cs_import_error:\n"
        "    if not __import__('clausal.pl_data_imports', fromlist=['_'])"
        f".bind_data_names(globals(), {resolved_module!r}, {pairs!r}, "
        f"{tuple(eligible)!r}, _cs_import_error):\n"
        "        raise\n"
    )
    block = parse(text).body[0]
    block.body = [import_stmt]
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


#: Module-body record of the arities an ``-import_from``'s ``name/N``
#: entries selected, keyed by the imported HANDLE (D20, 2026-09-29).  Read by
#: ``predicate._foreign_head_verdict`` while the body builds heads -- before
#: ``compile_module`` has planted the adopted rows that record it afterwards
#: -- and dropped by ``compiler_v2._process_imports``.
IMPORT_ARITIES_KEY = "$import_arities"


def _make_import_arities_record_ast(selected, source):
    """``predicate.record_import_arities(globals(), {local: arities})`` --
    *arities* a sorted tuple for a ``name/N`` selection, ``None`` for a bare
    entry (every arity).  ``None`` when *selected* is empty, so a file with
    no ``name/N`` entry compiles byte-identically."""
    if not selected:
        return None
    pairs_text = repr({local: (None if found is None
                               else tuple(sorted(found)))
                       for local, found in sorted(selected.items())})
    text = ("__import__('clausal.logic.predicate', fromlist=['_'])."
            f"record_import_arities(globals(), {pairs_text})")
    block = parse(text).body[0]
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
            # STAGE 1 (spec 2026-09-18): a str terminal is the chars CARRIER
            # -- ``sequence//1`` reads it as its text and hands out carrier
            # remainders, so no bare str is born here.  ``bytes`` unchanged.
            terminal = Constant(value=(CHARS_TAG, value) if isinstance(value, str) else value)
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
      --expr      THE SEAM: expr is a Clausal TERM; yields the runtime term
                  (a cell) built at that point, in the host module's rules
                  (clausal.logic.seam).  ++ escapes back to Python inside it.
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
                 filename=None, interactive=False, reify=False,
                 prolog_singletons=False):
        transformer._scope_depth = 0
        # D19: the ``.pl`` import path (``import_hook.PrologLoader``) only.
        # Prolog's convention (ISO, Scryer): a variable named ``_Name`` is
        # deliberately used once, so it is no singleton.  ``.clausal`` and
        # ``.seam`` source never set it -- their rule has no exceptions.
        transformer._prolog_singletons = prolog_singletons
        # TitleCase-identifier lint state (see ``_lint_titlecase``): the
        # identifiers already reported (once per file), the names an
        # ``-import_from`` list binds (exempt), and the TitleCase names the
        # file's hosted Python binds itself — imports, defs, classes,
        # assignments (their remedy is the ``++`` escape, like an injected
        # runtime class).
        transformer._titlecase_seen: set[str] = set()
        transformer._scale_name_seen: set[str] = set()
        transformer._retired_q_seen: set[int] = set()
        transformer._retired_q_records: list = []
        transformer._retired_q_file_has_q = None
        transformer._titlecase_imported: set[str] = set()
        transformer._titlecase_python_bound: set[str] = set()
        # Reflection models MORE than compiles — see TermTransformer._reify.
        transformer._reify = reify
        # Source file being rewritten, used only to attribute compile-time
        # errors.  A load failure surfaces through the *importing* file, so a
        # message that does not name its own file reads as an error in every
        # test that imports the package — the same trap the -module directive
        # error hit.
        transformer._filename = filename
        # ``Test/1`` (deprecated spelling of ``test/1``) is linted once per
        # file, at its first clause — see _warn_deprecated_test_spelling.
        transformer._warned_test_spelling = False
        # TitleCase unit names in an ``-import_from(py.units, …)`` list are
        # linted once per file per name — see _warn_deprecated_unit_spelling.
        transformer._warned_unit_spellings: set[str] = set()
        # Names the AUTHOR bound as Python locals in each enclosing scope, for
        # the shadowed-variable lint — see ``_author_bound_locals``.
        transformer._python_locals: list[set] = []
        # Names EXPORTED by a goal-position seam, per Python scope (the
        # module body is the outermost): name -> the seam's line.  Read
        # after each scope is rewritten by ``_lint_seam_text_compare``.
        # (``_seam_bound`` below is the term transformer's own stack of the
        # logic-variable names visible to nested seams -- a different thing.)
        transformer._seam_exports: list[dict] = [{}]
        transformer._seen_functors: dict[str, list[str]] = {}
        # Filled by visit_Module's pre-pass; a transformer used outside a module
        # walk (the REPL's seam term, a one-off clause) keeps the empty set.
        transformer._zero_arity_heads = frozenset()
        # Functors whose _seen_functors entry was minted by a -dynamic
        # directive with PLACEHOLDER arg_i field names (A12-F005). The first
        # real clause for such a functor unseats the placeholder so its
        # derived head-var names win — see _unseat_directive_minted.
        transformer._directive_minted_functors: set[str] = set()
        # functor name → (lineno, human description) of whatever first fixed
        # its signature in this file, so a later clause head that disagrees
        # can name the declaration it disagrees with.
        transformer._functor_decl_site: dict[str, tuple[int, str]] = {}
        # EVERY arity a name has in this file, with that arity's field names
        # (operator ruling 2026-09-29, ISO: ``p/1`` and ``p/2`` are unrelated
        # procedures).  ``_seen_functors`` keeps the name's FIRST
        # registration -- the PRIMARY, which every single-arity file only
        # ever has, so its code path and output are unchanged -- and this
        # adds the others.  See ``_head_fields_at``.
        transformer._functor_arities: dict[str, dict[int, list[str]]] = {}
        # (name, arity) -> (lineno, kind) of whatever fixed that arity's
        # field names, for a keyword head refused at a second arity.
        transformer._functor_arity_sites: dict[tuple[str, int], tuple[int, str]] = {}
        # Names with a FIELDED declaration -- a ``-module``/``-private``
        # template entry, ``-edcg_pred`` -- anywhere in the file.  A clause
        # head of such a name must be at an arity a declaration names (D2 of
        # the plan, re-keyed 2026-09-29: "-module(lib, [q(X), q(X, Y)]):
        # allow it" -- field names are per (name, arity), so each declared
        # arity carries its own; an UNDECLARED arity stays the old error).
        transformer._fielded_functors: set[str] = set()
        # name -> {arity: field names} its -module/-private TEMPLATE entries
        # declare (the last entry at an arity wins, as the registry did).
        transformer._fielded_arities: dict[str, dict[int, list[str]]] = {}
        # name -> the arities a field-free PROCEDURE declaration names (an
        # ISO ``name/N`` export/-private entry, ``-dynamic(name/N)``).  Lets
        # a fielded name open that arity with a clause head.
        transformer._procedure_decl_arities: dict[str, set[int]] = {}
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
        # shape.  ``chars`` is the engine default (THE FLIP, 2026-09-26: a
        # ``"..."`` literal is a STRING, as in Scryer/Trealla);
        # ``-double_quotes(atom)`` is the opt-out.
        transformer._double_quotes_mode = "chars"
        transformer._double_quotes_explicit = False
        # The modes that governed at least one ``"..."`` literal in this
        # file -- a SHARED sink every per-clause TermTransformer adds to
        # (``visit_Constant``), reported to importers as a
        # ``DoubleQuotesMode`` item -- and the goal-position seam literals
        # whose target module's mode is decided after the imports execute
        # (``_collect_cross_mode_sites`` -> ``CrossModeLiteralSites``).
        transformer._double_quotes_modes_used: set[str] = set()
        transformer._cross_mode_sites: list = []
        # The dotted paths this file's ``-import_module`` directives bind
        # (``a.b`` for ``-import_module(a.b)``), filled by a PRE-PASS in
        # ``visit_Module`` so a seam above its directive still sees it: the
        # only dotted bases the cross-mode lint may judge, and a seam's base
        # must match one of them whole (``a.b.p`` for ``a.b``, not ``a.c.p``).
        # Any other base is bound by hosted Python -- possibly a module-level
        # default later rebound at run time through ``seam.with_bases`` --
        # and judging the global would judge the wrong module.
        transformer._import_module_bases: set[str] = set()
        # Logic-variable names bound by the seams enclosing the expression
        # being rewritten (innermost last) — see visit_UnaryOp's ``--``.
        transformer._seam_bound: list[set] = []
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
        # MERGED, not replaced: a clause head that unseats a ``-dynamic``
        # placeholder re-registers the primary here, and an arity another
        # head already opened must survive it (roborev round 1).  The
        # placeholder's own arity was dropped by ``_unseat_directive_minted``.
        transformer._functor_arities.setdefault(functor_name, {})[
            len(field_names)] = field_names
        transformer._functor_arity_sites[
            (functor_name, len(field_names))] = (
                getattr(node, "lineno", 0), kind)

    def _register_functor_arity(transformer, functor_name, field_names, node,
                                kind="first clause"):
        """Record ANOTHER arity of a name that already has its primary
        registration (``_head_fields_at`` answered that the head opens one,
        or a -module/-private template entry declares a second arity).
        The name was checked against ``-hide`` when the primary registered."""
        transformer._functor_arities.setdefault(functor_name, {})[
            len(field_names)] = field_names
        transformer._functor_arity_sites[
            (functor_name, len(field_names))] = (
                getattr(node, "lineno", 0), kind)

    def _declare_fielded_entry(transformer, functor_name, field_names, node,
                               kind, statements, expr_stmt):
        """Register a -module/-private TEMPLATE entry ``name(F1, ..., Fn)``.

        The first registration of the name is the old path, byte for byte.
        An entry at an arity the name does not have yet declares THAT arity
        with its own field names (operator ruling 2026-09-29: "-module(lib,
        [q(X), q(X, Y)]): allow it"), so a clause head at either arity is
        built against its own declaration.  An entry at an arity the name
        already has changes nothing, as before."""
        transformer._fielded_functors.add(functor_name)
        transformer._fielded_arities.setdefault(functor_name, {})[
            len(field_names)] = field_names
        if functor_name not in transformer._seen_functors:
            transformer._register_functor(
                functor_name, field_names, node, kind)
        elif len(field_names) not in transformer._functor_arities.get(
                functor_name, {}):
            transformer._register_functor_arity(
                functor_name, field_names, node, kind)
        else:
            return
        statements.append(
            _make_predicate_decl_ast(functor_name, field_names, expr_stmt))

    def _per_arity_signature_entries(transformer, entries):
        """The ``(name, fields)`` pairs for the signature registry, with a
        name DECLARED at several arities folded into one
        ``(name, {arity: fields})`` pair that carries every declared arity
        (earlier directives' included, since ``.update`` replaces the
        name's value).  A single-arity name's pair is unchanged, so its
        emitted registry update is byte-identical."""
        out = []
        folded = set()
        for name, fields in entries:
            by_arity = transformer._fielded_arities.get(name) or {}
            if len(by_arity) < 2:
                out.append((name, fields))
            elif name not in folded:
                folded.add(name)
                out.append((name, {a: tuple(f) for a, f in
                                   sorted(by_arity.items())}))
        return out

    def _late_fielded_arities_before(transformer, functor_name, before):
        """Record, the first time a directive names *functor_name*, the
        arities it had BEFORE the directive (for ``_refuse_late_fielded``)."""
        if functor_name not in before:
            before[functor_name] = set(
                transformer._functor_arities.get(functor_name) or ())

    def _refuse_late_fielded(transformer, before, nodes, kind):
        """D2 regardless of ORDER, per arity: a -module/-private directive
        whose template entries come BELOW clauses that already gave a name
        several arities must declare every one of them.  (One arity before
        the directive is the pre-ruling shape, which loaded, and still
        does.)"""
        for functor_name, arities in before.items():
            if len(arities) < 2:
                continue
            covered = (set(transformer._fielded_arities.get(functor_name, ()))
                       | transformer._procedure_decl_arities.get(
                           functor_name, set()))
            missing = sorted(arities - covered)
            if missing:
                transformer._raise_late_fielded(
                    functor_name, nodes[functor_name], kind, arities,
                    missing)

    def _head_fields_at(transformer, functor_name, arity, has_keywords=False,
                        unseat=True):
        """``(prev_fields, opens)`` for a clause head of *functor_name*
        written at *arity* (positional + keyword count; a DCG head's two
        state arguments included).

        * the name is new -> ``(None, False)``: the first clause, as before;
        * the name is known AT *arity* -> that arity's fields, ``False``;
        * the name is known only at OTHER arities, and a new arity may be
          opened -> ``(None, True)``: the head is its arity's first clause
          (operator ruling 2026-09-29: one name at several arities, as in
          ISO, where ``p/1`` and ``p/2`` are unrelated procedures);
        * otherwise -> the PRIMARY's fields, ``False``, and
          ``_check_head_signature`` refuses the head exactly as it did when
          a name had one arity.

        A new arity may be opened when every earlier head of the name was a
        CLAUSE head (a ``-dynamic`` placeholder or a bare ``name/N`` export
        entry is unseated by the first clause, as before), no FIELDED
        declaration names it (D2), and the head is keyword-free (keywords
        name fields, and fields belong to an arity already declared).

        Every head that reaches the new arm used to be refused, so no
        program that loaded before compiles differently.

        *unseat* is False for a 0-arity fact, which never unseated a
        placeholder (a ``foo,`` after ``-dynamic(foo/0)`` emits no second
        declaration); a placeholder at another arity lets it open ``/0``.
        """
        if unseat:
            transformer._unseat_directive_minted(functor_name)
        primary = transformer._seen_functors.get(functor_name)
        if primary is None:
            return None, False
        known = transformer._functor_arities.get(functor_name) or {}
        if arity in known:
            return known[arity], False
        if has_keywords or functor_name in transformer._edcg_preds:
            return primary, False
        if functor_name in transformer._fielded_functors:
            # D2, per arity: a fielded name opens only an arity a field-free
            # procedure declaration names (``q/2`` in the list, -dynamic).
            # Its template entries registered their own arities already.
            if arity in transformer._procedure_decl_arities.get(
                    functor_name, ()):
                return None, True
            return primary, False
        if (transformer._functor_decl_site.get(
                functor_name, (0, ""))[1] == "first clause"
                or functor_name in transformer._directive_minted_functors):
            return None, True
        return primary, False

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
            if transformer._prolog_singletons and ident.startswith("_"):
                continue
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

    def _refuse_late_fielded_declaration(transformer, functor_name, fields,
                                         node, kind):
        """D2 regardless of ORDER (roborev round 1), for ``-edcg_pred``,
        which keeps one arity per name (Q4): its declaration BELOW clauses
        that already gave *functor_name* several arities.  A name had one
        arity until the 2026-09-29 ruling, so no program that loaded before
        reaches this.  (-module/-private template entries are checked per
        arity: ``_refuse_late_fielded``.)"""
        arities = transformer._functor_arities.get(functor_name) or {}
        if len(arities) < 2:
            return
        lineno = getattr(node, "lineno", 0)
        src = transformer._source_snippet(lineno)
        known = ", ".join(f"{functor_name}/{a}" for a in sorted(arities))
        raise SyntaxError(
            f"{kind} for {functor_name}/{len(fields)} comes after clauses "
            f"that define {known}\n"
            f"  declaration: {transformer._site(lineno)}"
            + (f" — {src}" if src else "")
            + f"\nAn -edcg_pred predicate has one arity in a file, and "
            f"{functor_name} already has {len(arities)}.\n"
            f"  remedy: give the other arities a different name.")

    def _raise_late_fielded(transformer, functor_name, node, kind, arities,
                            missing):
        """A -module/-private directive declares field names for some of
        *functor_name*'s arities, below clauses that define *arities*, and
        leaves *missing* undeclared."""
        lineno = getattr(node, "lineno", 0)
        src = transformer._source_snippet(lineno)
        known = ", ".join(f"{functor_name}/{a}" for a in sorted(arities))
        undeclared = ", ".join(f"{functor_name}/{a}" for a in missing)
        templates = ", ".join(
            f"`{transformer._arity_template(functor_name, transformer._functor_arities[functor_name][a])}`"
            for a in missing)
        raise SyntaxError(
            f"{kind} for {functor_name} comes after clauses that define "
            f"{known}, and does not declare {undeclared}\n"
            f"  declaration: {transformer._site(lineno)}"
            + (f" — {src}" if src else "")
            + f"\nA functor declared with field names has exactly the "
            f"arities its declarations name, each with its own fields.\n"
            f"  remedy: declare {undeclared} in the same list ({templates}),"
            f" or spell it as a predicate indicator (`{functor_name}/"
            f"{missing[0]}`), or give that arity a different name.")

    def _second_arity_note(transformer, functor_name, head_fields,
                           decl_kind):
        """The way to a second arity out of a declared-arity conflict, for a
        -module or -private TEMPLATE entry: declare the head's arity too.
        Each arity carries its own field names (operator ruling 2026-09-29:
        "-module(lib, [q(X), q(X, Y)]): allow it"); ISO's ``name/N`` names
        the procedure without fixing field names."""
        if decl_kind not in ("-module export list", "-private declaration"):
            return ""
        arity = len(head_fields)
        template = transformer._arity_template(functor_name, head_fields)
        return (f"\n  (Two arities of {functor_name} are two procedures, as "
                f"in ISO: to define {functor_name}/{arity} as well, declare "
                f"it in the same list, as `{template}` -- each arity carries "
                f"its own field names -- or as `{functor_name}/{arity}`.)")

    def _check_head_signature(transformer, functor_name, all_field_names,
                              prev_fields, node, has_keywords=False,
                              dcg=False):
        """Reject a clause head that cannot be built against the bound class.

        ``_seen_functors[functor_name]`` is exactly the tuple the guarded
        class block was minted with, so any head field name outside it would
        be emitted as a keyword the class does not have — the bare
        ``__init__() got an unexpected keyword argument 'arg_1'`` failure of
        ``todo/done/functor-field-name-mismatch-diagnostic.md``.

        The overwhelmingly common shape is an *arity* disagreement: a
        ``-module``/``-private`` declaration (or an earlier clause) fixes
        arity N and a later clause head supplies N+k arguments, whose surplus
        positions fall back to ``arg_N`` placeholder names.  A functor whose
        field names are DECLARED has exactly the arities its declarations
        name (each with its own fields, operator ruling 2026-09-29), so a
        head at another arity is a source error, not something to resolve.  (Two CLAUSE heads at two arities
        never reach here: since the 2026-09-29 ruling each is a procedure of
        its own, as in ISO -- ``_head_fields_at``.)

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
        # A head LONGER than the declaration whose surplus positions all
        # remapped onto names the declaration has -- a DCG head, whose two
        # state slots are always ``dcg0``/``dcg1`` -- has no unknown name, but
        # it emits one keyword twice and died in ``compile`` with the raw
        # "keyword argument repeated: dcg1" (triage B3a, 2026-09-28).
        overflow = (not has_keywords
                    and len(all_field_names) > len(prev_fields))
        if not unknown and not deficit and not overflow:
            return
        lineno = getattr(node, "lineno", 0)
        decl_lineno, decl_kind = transformer._functor_arity_sites.get(
            (functor_name, len(prev_fields)),
            transformer._functor_decl_site.get(
                functor_name, (0, "an earlier declaration")),
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
                f"author never wrote. A functor declared with field names "
                f"has exactly the arities its declarations name.\n"
                f"  remedy: write this head at arity {len(visible)} to "
                f"match `{template}` — a position that really means "
                f'"anything" must be spelled `_` — or give the '
                f"{len(all_field_names)}-argument predicate a different "
                f"name."
                + transformer._second_arity_note(
                    functor_name, all_field_names, decl_kind)
            )
        if len(all_field_names) > len(prev_fields):
            raise SyntaxError(
                f"functor {functor_name}/{len(all_field_names)} conflicts "
                f"with the declaration of {functor_name}/{len(prev_fields)} "
                f"in the same file\n{where}\n"
                f"{functor_name} is declared with "
                f"{len(prev_fields)} field(s) {declared}, so a "
                f"{len(all_field_names)}-argument head cannot be built "
                f"against it. A functor declared with field names has exactly "
                f"the arities its declarations name: give the declaration and every clause head of "
                f"{functor_name} the same number of arguments, or rename one "
                f"of them.\n"
                + (f"  (A DCG rule's head carries the two state arguments as "
                   f"well: {functor_name}//{len(all_field_names) - 2} is "
                   f"{functor_name}/{len(all_field_names)}.)\n" if dcg else "")
                + transformer._arity_conflict_remedy(
                    functor_name, all_field_names, prev_fields,
                    decl_kind, decl_lineno,
                )
                + transformer._second_arity_note(
                    functor_name, all_field_names, decl_kind)
            )
        raise SyntaxError(
            f"clause head for {functor_name}/{len(all_field_names)} names "
            f"field(s) {', '.join(unknown)} that {functor_name} does not "
            f"have\n{where}\n"
            f"{functor_name} is declared with fields {declared}. "
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
        from the class to that ``Var``.  The declaration statement
        (``_make_predicate_decl_ast``; a guarded class block until W4b-3
        slice 5) deliberately leaves such a binding alone, so the SECOND clause head then calls the variable:

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
        ``VAR(Unit)`` quantity sugar (``eval_(N(metre), D)``) untouched: ``N``
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
            # Capital-initial WITH a lowercase letter reaches here too since
            # 2026-09-10; saying "an ALL-CAPS name" of ``Foo`` describes a
            # rule the reader can see their name does not match, which reads
            # as a bug in the message rather than a fault in the code.
            else "a capital-initial name is a logic variable"
            if _is_titlecase_identifier(name)
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

    def _spell_edcg_hidden_head_slots(transformer, functor_name, head_args,
                                      head_keywords, anchor):
        """An ``-edcg_pred`` head written at its VISIBLE arity (a plain
        clause, not a ``>>`` rule, which threads its accumulators itself)
        gets its hidden ``_edcg_*`` accumulator slots SPELLED, each a fresh
        ``$Var()``, appended in place.

        They used to be filled by keyword-only construction padding every
        unnamed slot with a fresh ``Var`` -- which the no-padding ruling
        (operator, 2026-09-25) retired, so a construction naming only some
        slots is refused now.  This keeps what the head has always meant
        (the visible arguments, and a free variable in each hidden slot) as
        the compiler's explicit spelling rather than an implicit fill.
        Whether such a fact should instead thread each accumulator unchanged
        (``in = out``, as a ``>>`` rule with no push does) is an open EDCG
        question -- ``todo/construction-padding-audit-2026-09-25.md``.
        """
        spec = transformer._edcg_preds.get(functor_name)
        if spec is None:
            return
        visible_arity = spec[0]
        if len(head_args) + len(head_keywords) != visible_arity:
            return
        fields = transformer._seen_functors.get(functor_name) or ()
        hidden = [f for f in fields if f.startswith("_edcg_")]
        for field in hidden:
            fresh = replace(Call(func=replace(Name(id="$Var", ctx=load), anchor),
                                 args=[], keywords=[]), anchor)
            if head_keywords:
                head_keywords.append(make_keyword_node(field, fresh, anchor))
            else:
                head_args.append(fresh)

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
            placeholder = transformer._seen_functors.pop(functor_name, None)
            if placeholder is not None:
                arities = transformer._functor_arities.get(functor_name)
                if arities is not None:
                    arities.pop(len(placeholder), None)
                    if arities and functor_name in transformer._fielded_functors:
                        # A template entry declared another arity (2026-09-29
                        # ruling): it becomes the primary, so the clause head
                        # being built is checked against the DECLARATIONS,
                        # not taken for the name's first clause.
                        arity, fields = next(iter(arities.items()))
                        transformer._seen_functors[functor_name] = fields
                        transformer._functor_decl_site[functor_name] = (
                            transformer._functor_arity_sites.get(
                                (functor_name, arity), (0, "")))

    def _make_term_transformer(transformer, atoms=None, *, seam=False,
                               clause_var_names=None):
        """Build a TermTransformer sharing this EmbedTransformer's
        bare-atom and logic-variable collection sinks and import-remap table.

        Centralised so every per-clause TermTransformer participates in the
        same Phase 2 (auto-mint) collection without each call site having
        to remember the plumbing.
        """
        term_tf = TermTransformer(
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
            zero_arity_heads=transformer._zero_arity_heads,
            atom_functor_sites=transformer._atom_functor_sites,
            quote_map=transformer._quote_map,
            double_quotes_mode=transformer._double_quotes_mode,
            seam=seam,
            python_visitor=transformer.visit if seam else None,
            titlecase_python_bound=transformer._titlecase_python_bound,
            clause_var_names=clause_var_names,
            modes_used=transformer._double_quotes_modes_used,
        )
        return term_tf

    def _seam_term_ast(transformer, expression, anchor):
        """Lower *expression* through a seam TermTransformer.  Returns
        ``(term_ast, fresh)``: the lowered term and the ordered logic-variable
        names this seam introduces (already-bound names of an enclosing seam
        are excluded).  The caller decides how to bind ``fresh``."""
        outer = set().union(*transformer._seam_bound) if transformer._seam_bound else set()
        # CLAUSAL: ``fresh`` drives ``_var_bind``, which writes these names
        # into the HOST PYTHON scope, so it must name exactly what
        # ``visit_Name`` will read as a variable -- otherwise one seam's
        # two sides disagree about a spelling.
        #
        # ``python_bodies`` is that agreement for the verbatim-Python
        # bodies: ``visit_Name`` never sees inside a ``++`` operand or an
        # f-string slot, because both lower to a lambda whose text is
        # embedded as written.  Collecting through one made a Python name
        # standing there -- ``--f(++Var())``, ``--f(f"{Fraction(1, 2)}")`` --
        # a seam variable, and ``_var_bind`` then wrote ``(Var := $Var())``
        # into the ENCLOSING FUNCTION.  Python decides locality per function,
        # so an EARLIER, ordinary ``Var()`` in that same function started
        # raising ``UnboundLocalError``.
        #
        # THE TRACEBACK LIES ABOUT WHERE THAT HAPPENS.  It points at the
        # earlier line, which is the victim; the line that caused it is the
        # seam below.  Anyone debugging this from the traceback alone will
        # look in the wrong place.
        #
        # It is also the reading the CLAUSAL side already had: the same skip
        # is what ``_clause_variable_names`` does for the sub-transformer's
        # own clause scope, so before this the two halves of one seam
        # disagreed -- the fresh list called the name a variable while the
        # thunk correctly left it resolving in the module namespace.
        #
        # ``"nested_seams"`` rather than a plain skip because a ``--expr``
        # written inside that Python IS a seam again (a marker only where
        # there is no Python visitor), and its operand is Clausal text whose
        # variables the enclosing seam binds ON PURPOSE -- that hoisting is
        # what lets the inner seam reuse the outer one's variable instead of
        # walrusing a fresh one inside the lambda, shadowing the parameter
        # the thunk was handed.
        fresh = [n for n in _collect_logic_var_names(
            expression, _clause_scope_exclusions(transformer._import_remap),
            python_bodies="nested_seams")
            if n not in outer]
        term_tf = transformer._make_term_transformer(seam=True)
        term_tf.seen_vars.update(outer)
        term_tf.seen_vars.update(fresh)
        transformer._seam_bound.append(outer | set(fresh))
        try:
            return term_tf.visit(expression), fresh
        finally:
            transformer._seam_bound.pop()

    def _var_bind(transformer, name, anchor):
        """``(NAME := Var())`` — the term-position binding of one variable."""
        return replace(NamedExpr(
            target=replace(Name(id=name, ctx=Store()), anchor),
            value=replace(Call(func=replace(Name(id="$Var", ctx=Load()), anchor),
                               args=[], keywords=[]), anchor),
        ), anchor)

    def _seam_call(transformer, term_ast, anchor):
        seam_kw = ([keyword(arg="loose", value=Constant(value=True))]
                   if transformer._implicit_atoms_default else [])
        return replace(
            Call(func=Name(id="$seam", ctx=Load()),
                 args=[term_ast, Call(func=Name(id="globals", ctx=Load()), args=[], keywords=[])],
                 keywords=seam_kw),
            anchor,
        )

    # ── goal position ──────────────────────────────────────────────────
    @staticmethod
    def _goal_operand(test):
        """``--X`` -> (X, False); ``not --X`` -> (X, True); else None.
        Adjacency of the two ``-`` is required, as for term position."""
        negated = False
        node = test
        if isinstance(node, UnaryOp) and isinstance(node.op, Not):
            negated, node = True, node.operand
        if (isinstance(node, UnaryOp) and isinstance(node.op, USub)
                and isinstance(node.operand, UnaryOp) and isinstance(node.operand.op, USub)
                and node.col_offset == node.operand.col_offset - 1
                and node.lineno == node.operand.lineno):
            return node.operand.operand, negated
        return None

    def _goal_seam(transformer, expression, anchor):
        """Lower a GOAL: returns ``(pre_stmts, goal_ast, fresh)`` where
        ``pre_stmts`` assign ``$v_<NAME> = Var()`` for every fresh variable
        and ``goal_ast`` is the lowered node with those names in place of the
        variables, handed to ``$once_bind``/``$each`` UNWRAPPED — see the
        comment on the ``return`` below for why this differs from term
        position's ``$seam(...)`` wrapping."""
        term_ast, fresh = transformer._seam_term_ast(expression, anchor)
        transformer._collect_cross_mode_sites(expression, anchor)
        rename = {n: f"$v_{n}" for n in fresh}

        class _Rename(NodeTransformer):
            def visit_Name(self, node):
                if node.id in rename and isinstance(node.ctx, Load):
                    return replace(Name(id=rename[node.id], ctx=Load()), node)
                return node

            def visit_Lambda(self, node):
                # A ``++expr`` / f-string escape lowers to
                # ``PyThunk(lambda IDS: len(IDS), [IDS], ...)``: the lambda
                # takes the DEREFERENCED value of each captured variable as a
                # parameter of the SAME name, and only the ``var_objects``
                # list beside it (still visited — it is a sibling argument of
                # the ``PyThunk`` call, not part of the lambda) holds the
                # seam's variable objects.  Renaming the body's ``IDS`` too
                # would leave the parameter shadowed and hand the escape the
                # variable itself (``len()`` of an AttVar).  So: do not
                # descend.
                return node
        goal_ast = _Rename().visit(term_ast)
        pre = [
            replace(Assign(
                targets=[replace(Name(id=rename[n], ctx=Store()), anchor)],
                value=replace(Call(func=replace(Name(id="$Var", ctx=Load()), anchor),
                                   args=[], keywords=[]), anchor),
            ), anchor)
            for n in fresh
        ]
        for stmt in pre:
            fix_missing_locations(stmt)
        # Unlike term position, the goal is NOT run through `$seam`/`build()`:
        # `once_bind`/`each` hand the node straight to `solve()`, which
        # compiles it exactly as it would a clause body (`Call`/`Unify`/
        # `And`/`TupleLiteral`-as-conjunction all pass straight through
        # `_term_to_goal`) — `build()` only knows how to collapse a node
        # into a plain VALUE, which is term position's job, not a goal's.
        goal_ast = transformer._wrap_runtime_bases(expression, goal_ast, anchor)
        transformer._warn_shadowed_variables(fresh, expression, anchor,
                                             goal_ast)
        return pre, goal_ast, fresh

    def _collect_cross_mode_sites(transformer, expression, anchor):
        """Record every ``"..."`` literal in a goal-position seam whose
        callee lives in ANOTHER module, for the cross-mode literal lint.

        THE HAZARD (seam review, 2026-09-26).  ``visit_Constant`` reads a
        seam literal under the HOST file's ``-double_quotes`` mode, and the
        callee's clauses were compiled under the callee's.  When the two
        differ the goal compares a string with an atom (or the reverse) and
        never matches -- silently.  After the default flips to ``chars``
        every module that pins ``-double_quotes(atom)`` is such a callee.

        The callee's mode is the OWNER's fact, known only once the imports
        have executed, so this records the site and ``compiler_v2.
        _lint_cross_mode_literals`` judges it.  Two statically known
        shapes: a call to a name an ``-import_from`` remapped, and
        ``--base.pred(...)`` over a dotted base (an ``-import_module``'d
        module; a base bound at RUN time -- ``module = _RULE.get()`` inside
        a function -- resolves to nothing at load and is the documented
        gap).  A ``++`` escape is Python, not a Clausal literal, and is
        skipped; a local callee shares the host's mode and is not a site.
        """
        exclusions = _clause_scope_exclusions(transformer._import_remap)

        def _callee(call):
            """``(kind, target, shown)`` when *call*'s callee lives in
            another module and is statically known, else ``None``."""
            func = call.func
            if isinstance(func, Name):
                dotted = transformer._import_remap.get(func.id)
                if dotted is None:
                    return None
                # The local name AND the owner's dotted key: a predicate's
                # binding names its owner itself (a mangled handle), but an
                # imported data FUNCTOR binds the plain atom, and its owner
                # is only knowable from the ``-import_from`` that brought it.
                return "imported", (func.id, dotted), func.id
            if not isinstance(func, Attribute):
                return None
            chain, root = [], func
            while isinstance(root, Attribute):
                chain.append(root.attr)
                root = root.value
            if not isinstance(root, Name):
                return None
            if _is_logic_var_name(root.id) and root.id not in exclusions:
                return None            # dict-attribute sugar, not a module
            chain.reverse()
            if ".".join([root.id, *chain[:-1]]) not in transformer._import_module_bases:
                return None            # not this file's -import_module: the gap
            return "dotted", (root.id, tuple(chain)), ".".join([root.id, *chain])

        def _literals_under(node):
            """Every ``"..."`` literal below *node*, a ``++`` escape excepted."""
            out, stack = [], [node]
            while stack:
                n = stack.pop()
                if _double_prefix_operand(n, UAdd) is not None:
                    continue
                if (isinstance(n, Constant) and type(n.value) is str
                        and _quote_of_positioned(transformer, n) == '"'):
                    out.append(n.value)
                stack.extend(reversed(list(iter_child_nodes(n))))
            return out

        # Only the GOAL-POSITION call runs: a nested ``q("x")`` inside
        # ``p(...)`` is DATA, and ``"x"`` is unified against p's clauses,
        # compiled under p's module's mode -- so every literal below a goal
        # call is that call's (flip review M1 on 571ffb0c, correcting the
        # earlier "innermost callee" reading).  Goal position descends
        # through the control forms -- a conjunction tuple, and/or, not,
        # if_ -- and through exactly the goal ARGUMENTS of a meta-predicate
        # (``_goal_positions``: findall/3's second, catch/3's first and
        # third, maplist's first, ...); its data arguments are data.  A
        # meta-predicate NAME this file rebinds by ``-import_from`` is the
        # import's predicate, not the builtin, and is an ordinary goal.
        # Sites are emitted in source order.
        from clausal.logic.builtins.clause_ops import _goal_positions  # noqa: PLC0415
        sites = []
        stack = [expression]
        while stack:
            node = stack.pop()
            if _double_prefix_operand(node, UAdd) is not None:
                continue
            if isinstance(node, (Tuple, BoolOp)):
                stack.extend(reversed(node.elts if isinstance(node, Tuple) else node.values))
                continue
            if isinstance(node, UnaryOp) and isinstance(node.op, Not):
                stack.append(node.operand)
                continue
            if isinstance(node, Call) and isinstance(node.func, Name) \
                    and node.func.id not in transformer._import_remap:
                name = node.func.id
                positions = (range(len(node.args)) if name in _GOAL_CONTROL_FORMS
                             else _goal_positions(name, len(node.args), None))
                if positions:
                    stack.extend(reversed([node.args[i] for i in positions
                                           if i < len(node.args)]))
                    continue
            if not isinstance(node, Call):
                continue
            callee = _callee(node)
            if callee is None:
                continue
            literals = _literals_under(node)
            if literals:
                sites.append((callee, literals))
        for (kind, target, shown), literals in sites:
            transformer._cross_mode_sites.append((
                kind, target, tuple(literals), transformer._double_quotes_mode,
                f"{transformer._filename}:{getattr(anchor, 'lineno', '?')}",
                f"--{unparse(expression)}", shown))

    def _wrap_runtime_bases(transformer, expression, goal_ast, anchor):
        """Wrap *goal_ast* in ``$with_bases(goal, {"m": lambda: m})`` when the
        goal is written ``--m.pred(...)`` over a dotted base.

        THE DOTTED RUNTIME MODULE FORM (2026-09-21).  The seam resolves a
        goal's NAME at compile time, so ``m.pred`` reached ``solve`` as the
        dotted functor ``"m.pred"``.  The base's live VALUE is the missing
        half, and it cannot be read at run time from ``globals()``: the
        callers this exists for bind their module INSIDE a function
        (``module = _RULE.get()``), so it is a local.  A thunk closes over it
        where it was written, which is the only spelling that sees a local.

        LAZY, and that is load-bearing: a base that is not a Python binding at
        all (a qualified spelling an ``-import_from`` remap already resolved
        statically) must not be EVALUATED here, or emitting the environment
        would turn a working goal into a ``NameError``.  ``with_bases`` calls
        the thunk and swallows that failure; nothing is evaluated unless it
        is about to be used.

        Emitted ONLY when such a base exists, so every goal in a program that
        does not use the form lowers to byte-identical code.
        """
        # ONLY the root of the CALL'S OWN func chain (roborev job 79, finding
        # 6).  Walking the whole expression collected the root of every
        # Attribute in it — inside ``++`` escapes, inside argument terms —
        # and ``with_bases`` reads exactly one of them, so the rest were
        # lambdas built into the emitted AST and never called.
        bases = []
        for node in ([expression.func]
                     if isinstance(expression, Call) else []):
            if not isinstance(node, Attribute):
                continue
            root = node
            while isinstance(root, Attribute):
                root = root.value
            if not isinstance(root, Name):
                continue
            # A logic-variable base is the DICT-ATTRIBUTE sugar (``P.status``
            # -> ``P[status]``), not a qualified name -- ``visit_Attribute``
            # draws the same line, and a thunk over a logic variable would
            # read a name Python never bound.
            if (_is_logic_var_name(root.id)
                    and root.id not in transformer._clause_scope_exclusions()):
                continue
            if root.id not in bases:
                bases.append(root.id)
        if not bases:
            return goal_ast
        env = replace(Dict(
            keys=[replace(Constant(value=b), anchor) for b in bases],
            values=[replace(Lambda(
                args=arguments(posonlyargs=[], args=[], vararg=None,
                               kwonlyargs=[], kw_defaults=[], kwarg=None,
                               defaults=[]),
                body=replace(Name(id=b, ctx=Load()), anchor),
            ), anchor) for b in bases],
        ), anchor)
        wrapped = replace(Call(
            func=replace(Name(id="$with_bases", ctx=Load()), anchor),
            args=[goal_ast, env], keywords=[],
        ), anchor)
        fix_missing_locations(wrapped)
        return wrapped

    def _export_stmts(transformer, names, anchor):
        """``NAME = $export($v_NAME)`` — one assignment per exported name."""
        out = []
        for n in names:
            out.append(replace(Assign(
                targets=[replace(Name(id=n, ctx=Store()), anchor)],
                value=replace(Call(func=replace(Name(id="$export", ctx=Load()), anchor),
                                   args=[replace(Name(id=f"$v_{n}", ctx=Load()), anchor)],
                                   keywords=[]), anchor),
            ), anchor))
        return out

    def _globals_call(transformer, anchor):
        return replace(Call(func=Name(id="globals", ctx=Load()), args=[], keywords=[]), anchor)

    def _declare_locals(transformer, names, anchor):
        """An unreachable ``if False:`` block whose body exports *names* --
        so Python recognizes them as locals of the enclosing function
        without binding them. A stray read after the seam then raises
        ``UnboundLocalError`` instead of silently falling through to a
        same-named module global."""
        exports = transformer._export_stmts(names, anchor)
        return replace(
            If(
                test=replace(Constant(value=False), anchor),
                body=exports if exports else [replace(Pass(), anchor)],
                orelse=[]
            ),
            anchor
        )

    def _visit_stmts(transformer, stmts):
        """Visit each statement, splicing in any LIST result (a nested
        goal-seam ``if`` returns ``pre_stmts + [If]``) instead of nesting it
        as a single body element -- ``compile()`` requires a flat list of
        statements, not a list containing a list."""
        out = []
        for s in stmts:
            r = transformer.visit(s)
            out.extend(r if isinstance(r, list) else [r])
        return out

    def visit_If(transformer, node):
        found = transformer._goal_operand(node.test)
        if found is None:
            return transformer.generic_visit(node)
        expression, negated = found
        transformer._lint_titlecase(expression)
        pre, goal_ast, fresh = transformer._goal_seam(expression, node.test)
        test = replace(Call(func=Name(id="$once_bind", ctx=Load()),
                            args=[goal_ast, transformer._globals_call(node.test)],
                            keywords=[]), node.test)
        if negated:
            test = replace(UnaryOp(op=Not(), operand=test), node.test)
            # In negated case, emit exports in unreachable ``if False:`` block
            # so Python recognizes variables as local without binding them.
            if_false = transformer._declare_locals(fresh, node.test)
            body = [if_false] + transformer._visit_stmts(node.body)
        else:
            transformer._note_seam_bound(fresh, node.test)
            exports = transformer._export_stmts(fresh, node.test)
            body = exports + transformer._visit_stmts(node.body)
        node.test = test
        node.body = body
        # ``elif`` is an If nested in orelse: visit it so it gets the same treatment.
        node.orelse = transformer._visit_stmts(node.orelse)
        fix_missing_locations(node)
        return pre + [node]

    def visit_For(transformer, node):
        found = transformer._goal_operand(node.iter)
        if found is None or found[1]:
            # ``for x in not --goal`` is not a goal position: leave it to Python.
            return transformer.generic_visit(node)
        expression, _ = found
        transformer._lint_titlecase(expression)
        # Targets: a Name, or a Tuple of Names, each a variable of the goal.
        if isinstance(node.target, Name):
            targets = [node.target.id]
        elif isinstance(node.target, Tuple) and all(isinstance(e, Name) for e in node.target.elts):
            targets = [e.id for e in node.target.elts]
        else:
            raise SyntaxError(
                f"{transformer._filename}:{node.lineno}: `for ... in --goal` "
                f"binds plain names (a name or a tuple of names); got "
                f"{unparse(node.target)}")
        pre, goal_ast, fresh = transformer._goal_seam(expression, node.iter)
        for t in targets:
            # A target not fresh here is either absent from the goal, or a
            # name already bound by an enclosing seam -- a ``for`` never
            # shares with an outer seam (spec §4), so both are refused alike.
            if t not in fresh:
                raise SyntaxError(
                    f"{transformer._filename}:{node.lineno}: `{t}` is not a "
                    f"variable of the goal `{unparse(expression)}`")
        # Every goal variable that is not a loop target still becomes a
        # local of the enclosing function (same loudness rule as the
        # negated ``if`` above), so a stray read after the loop raises
        # ``UnboundLocalError`` rather than reading a same-named module
        # global left over from some earlier definition.
        non_targets = [n for n in fresh if n not in targets]
        transformer._note_seam_bound(targets, node.iter)
        declare = transformer._declare_locals(non_targets, node.iter)
        var_refs = replace(Tuple(
            elts=[replace(Name(id=f"$v_{t}", ctx=Load()), node.iter) for t in targets],
            ctx=Load()), node.iter)
        node.iter = replace(Call(func=Name(id="$each", ctx=Load()),
                                 args=[goal_ast, var_refs, transformer._globals_call(node.iter)],
                                 keywords=[]), node.iter)
        node.body = transformer._visit_stmts(node.body)
        node.orelse = transformer._visit_stmts(node.orelse)
        fix_missing_locations(node)
        return pre + [declare, node]

    def _visit_comprehension(transformer, node):
        """Lower a goal seam in the FIRST generator's iterable.

        Mirrors ``visit_For``: the goal's fresh logic variables are bound by
        hoisted ``$Var()`` statements and the iterable becomes a plain
        ``$each(...)`` call, which is legal where an assignment expression is
        not.  The comprehension's target binds the exported values exactly as
        a ``for`` target does.

        FIRST CLAUSE ONLY.  Only the outermost iterable is evaluated in the
        enclosing scope; a later ``for`` clause is re-evaluated once per outer
        iteration, so hoisted binds would be created ONCE and silently shared
        across every iteration — one logic variable for the whole
        comprehension.  That is refused by name rather than emitted, because
        the wrong answer it produces looks like a defect in the module being
        called.  Measured over the downstream callers at the time this was
        written: every comprehension-iterable goal was in the first clause
        and none in a later one.
        """
        # SCANNED UP FRONT (roborev job 79, finding 2).  Refusing inside the
        # loop only fired when clause 1 had NO goal: with a goal in clause 1
        # AND a later one, clause 1 lowered, the method returned, and the
        # later clause went through the generic TERM-position seam — which
        # emits the assignment expression CPython then rejects with the bare
        # "cannot be used in a comprehension iterable expression", pointing at
        # generated code and carrying none of the explanation this refusal
        # exists to give.
        for generator in node.generators:
            for condition in generator.ifs:
                transformer._lint_boolean_seam(
                    condition, "a comprehension's `if` filter")
        carrying = [i for i, g in enumerate(node.generators)
                    if (found := transformer._goal_operand(g.iter)) is not None
                    and not found[1]]
        for index in carrying:
            if index != 0:
                generator = node.generators[index]
                raise SyntaxError(
                    f"{transformer._filename}:{node.lineno}: a `--goal` in a "
                    f"comprehension must be in the FIRST `for` clause; this "
                    f"one is clause {index + 1}.  Only the outermost iterable "
                    f"is evaluated once in the enclosing scope — a later "
                    f"clause re-runs per outer iteration and would share one "
                    f"logic variable across all of them.  Bind it to a name "
                    f"above the comprehension instead.")
        for index in carrying:
            generator = node.generators[index]
            found = transformer._goal_operand(generator.iter)
            expression, _ = found
            transformer._lint_titlecase(expression)
            target = generator.target
            if isinstance(target, Name):
                targets = [target.id]
            elif (isinstance(target, Tuple)
                    and all(isinstance(e, Name) for e in target.elts)):
                targets = [e.id for e in target.elts]
            else:
                raise SyntaxError(
                    f"{transformer._filename}:{node.lineno}: `for ... in "
                    f"--goal` binds plain names (a name or a tuple of names); "
                    f"got {unparse(target)}")
            pre, goal_ast, fresh = transformer._goal_seam(
                expression, generator.iter)
            transformer._note_seam_bound(targets, generator.iter)
            for t in targets:
                if t not in fresh:
                    raise SyntaxError(
                        f"{transformer._filename}:{node.lineno}: `{t}` is not "
                        f"a variable of the goal `{unparse(expression)}`")
            # RE-ENTRANT, NOT HOISTED (roborev job 79, finding 1).  ``pre`` is
            # the ``$v_N = $Var()`` statements ``visit_For`` puts before the
            # loop; a comprehension has nowhere to put a statement, and
            # hoisting them above the enclosing STATEMENT is correct only
            # where that statement is re-executed per evaluation.  In a lambda
            # body, a ``while`` test or a nested comprehension it is not, and
            # one ``Var`` is then shared across every evaluation -- measured,
            # a live generator left unexhausted made the next evaluation see
            # one answer instead of three.  So the binds become PARAMETERS of
            # a lambda that ``each_fresh`` calls once per evaluation, which
            # needs no statement and no walrus (Python refuses an assignment
            # expression in a comprehension iterable even inside a lambda).
            del pre
            maker = replace(Lambda(
                args=arguments(
                    posonlyargs=[],
                    args=[replace(arg(arg=f"$v_{n}", annotation=None),
                                  generator.iter) for n in fresh],
                    vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None,
                    defaults=[]),
                body=replace(Tuple(elts=[
                    goal_ast,
                    replace(Tuple(
                        elts=[replace(Name(id=f"$v_{t}", ctx=Load()),
                                      generator.iter) for t in targets],
                        ctx=Load()), generator.iter),
                ], ctx=Load()), generator.iter),
            ), generator.iter)
            new_iter = replace(Call(
                func=Name(id="$each_fresh", ctx=Load()),
                args=[maker, transformer._globals_call(generator.iter)],
                keywords=[]), generator.iter)
            fix_missing_locations(new_iter)
            generator.iter = new_iter
            # Everything EXCEPT the lowered iterable still needs visiting —
            # generic_visit would walk back into the goal we just lowered.
            generator.ifs = [transformer.visit(i) for i in generator.ifs]
            for other in node.generators[index + 1:]:
                other.iter = transformer.visit(other.iter)
                other.ifs = [transformer.visit(i) for i in other.ifs]
            for field in ("elt", "key", "value"):
                if getattr(node, field, None) is not None:
                    setattr(node, field, transformer.visit(getattr(node, field)))
            fix_missing_locations(node)
            return node
        return transformer.generic_visit(node)

    visit_ListComp = _visit_comprehension
    visit_SetComp = _visit_comprehension
    visit_DictComp = _visit_comprehension
    visit_GeneratorExp = _visit_comprehension

    def visit_While(transformer, node):
        found = transformer._goal_operand(node.test)
        if found is None:
            return transformer.generic_visit(node)
        expression, negated = found
        transformer._lint_titlecase(expression)
        # ``pre`` is unused on purpose: unlike ``if``/``for``, the fresh
        # ``Var()`` binds must be re-created every iteration, so they are
        # emitted INSIDE the loop test (as a bind-then-call tuple index)
        # rather than once before the loop.
        _pre, goal_ast, fresh = transformer._goal_seam(expression, node.test)
        call = replace(Call(func=Name(id="$once_bind", ctx=Load()),
                            args=[goal_ast, transformer._globals_call(node.test)],
                            keywords=[]), node.test)
        if fresh:
            binds = [replace(NamedExpr(
                target=replace(Name(id=f"$v_{n}", ctx=Store()), node.test),
                value=replace(Call(func=replace(Name(id="$Var", ctx=Load()), node.test),
                                   args=[], keywords=[]), node.test)), node.test)
                for n in fresh]
            call = replace(Subscript(
                value=replace(Tuple(elts=[*binds, call], ctx=Load()), node.test),
                slice=replace(Constant(value=-1), node.test), ctx=Load()), node.test)
        if negated:
            node.test = replace(UnaryOp(op=Not(), operand=call), node.test)
            # Loudness rule (as for negated ``if``): none of the fresh
            # variables are exported, so declare them as locals without
            # binding, so a stray read raises ``UnboundLocalError`` rather
            # than falling through to a same-named module global.
            declare = transformer._declare_locals(fresh, node.test)
            exports = [declare]
        else:
            node.test = call
            transformer._note_seam_bound(fresh, node.test)
            exports = transformer._export_stmts(fresh, node.test)
        node.body = exports + transformer._visit_stmts(node.body)
        node.orelse = transformer._visit_stmts(node.orelse)
        fix_missing_locations(node)
        return node

    def _warn_deprecated_test_spelling(transformer, functor_name, arity, node):
        """Lint a ``Test(...)`` clause head (see ClausalDeprecatedSpellingWarning).

        The one-per-file lint for the
        test-clause predicate: ``test/1`` is the spelling, ``Test/1`` the
        old one.  A test file holds many such clauses, so — unlike the
        per-site ``If`` lint — this fires ONCE per file, at the first
        clause, so the rename is named without drowning the load in one
        warning per test.  Message shape follows ``EmbedTransformer._site``.
        """
        if (functor_name != TEST_DEPRECATED_NAME or arity != 1
                or transformer._warned_test_spelling):
            return
        transformer._warned_test_spelling = True
        import warnings  # noqa: PLC0415
        lineno = getattr(node, "lineno", None)
        if transformer._filename:
            where = f"{transformer._filename}:{lineno or '?'}"
        else:
            where = f"line {lineno}" if lineno else "unknown site"
        snippet = ""
        lines = transformer._source_lines
        if lines and lineno and 1 <= lineno <= len(lines):
            snippet = " — " + lines[lineno - 1].strip()
        warnings.warn(
            f"{where}{snippet}: `{TEST_DEPRECATED_NAME}` is the old spelling of "
            f"the test-clause predicate {TEST_NAME}/1. Rename "
            f"`{TEST_DEPRECATED_NAME}` -> `{TEST_NAME}` "
            f"({TEST_NAME}(DESCRIPTION) <- BODY); the old spelling still works "
            f"but will be removed in a future release",
            ClausalDeprecatedSpellingWarning,
            stacklevel=2,
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
        transformer._warn_deprecated_test_spelling(
            functor_name, len(orig_pos_args) + len(orig_kw_args), src_node)
        arg_field_names = _derive_field_names(orig_pos_args)
        kwarg_field_names = [kw.arg for kw in orig_kw_args]
        all_field_names = arg_field_names + kwarg_field_names

        prev_fields, opens_arity = transformer._head_fields_at(
            functor_name, len(all_field_names),
            has_keywords=bool(kwarg_field_names))
        if prev_fields is not None:
            for i in range(len(arg_field_names)):
                if i < len(prev_fields):
                    arg_field_names[i] = prev_fields[i]
            all_field_names = arg_field_names + kwarg_field_names
            transformer._check_head_signature(
                functor_name, all_field_names, prev_fields, expr_stmt,
                has_keywords=bool(kwarg_field_names))

        term_transformer = transformer._make_term_transformer()
        # A fact has no body, but its arguments are still one scope: a thunk
        # in argument 1 must see a name argument 2 binds.
        term_transformer.note_clause_scope(
            *orig_pos_args, *(kw.value for kw in orig_kw_args))
        transformed_pos = [term_transformer.visit(a) for a in orig_pos_args]
        transformed_kw = [term_transformer.visit(kw.value) for kw in orig_kw_args]

        head_args, head_keywords = transformer._build_head_arguments(
            transformer._emit_head_positionally(functor_name, prev_fields),
            arg_field_names, transformed_pos, orig_pos_args,
            kwarg_field_names, transformed_kw, orig_kw_args,
        )
        transformer._spell_edcg_hidden_head_slots(
            functor_name, head_args, head_keywords, anchor)
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
            head=_head_ctor_ast(head_ast),
            body=replace(Constant(value=True), expr_stmt.value),
        )
        define_stmt = _make_define_stmt(predicate_ast, expr_stmt)
        transformer._warn_singletons(term_transformer, expr_stmt)

        statements = []
        if functor_name not in transformer._seen_functors:
            transformer._register_functor(
                functor_name, all_field_names, expr_stmt, "first clause")
            statements.append(
                _make_predicate_decl_ast(functor_name, all_field_names, expr_stmt)
            )
        elif opens_arity:
            transformer._register_functor_arity(
                functor_name, all_field_names, expr_stmt)
            statements.append(
                _make_predicate_decl_ast(functor_name, all_field_names, expr_stmt)
            )
        statements.append(define_stmt)
        return statements if len(statements) > 1 else statements[0]

    def _build_zero_arity_fact_statements(transformer, functor_name, name_node,
                                          expr_stmt):
        """Build AST for a zero-arity bodyless fact ``flag`` / ``flag,``."""
        prev_fields, opens_arity = transformer._head_fields_at(
            functor_name, 0, unseat=False)
        if prev_fields:
            # ``foo,`` after ``foo(a, b),`` used to pad into a foo(_, _)
            # clause matching EVERYTHING — the /0 instance of the same
            # under-supply refusal _check_head_signature now makes.  Since
            # the 2026-09-29 ruling it opens ``foo/0`` instead
            # (``_head_fields_at``), unless ``foo``'s fields were DECLARED.
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
            head=_head_ctor_ast(head_ast),
            body=replace(Constant(value=True), expr_stmt.value),
        )
        define_stmt = _make_define_stmt(predicate_ast, expr_stmt)
        statements = []
        if functor_name not in transformer._seen_functors:
            transformer._register_functor(
                functor_name, [], expr_stmt, "first clause")
            statements.append(
                _make_predicate_decl_ast(functor_name, [], expr_stmt)
            )
        elif opens_arity:
            transformer._register_functor_arity(functor_name, [], expr_stmt)
            statements.append(
                _make_predicate_decl_ast(functor_name, [], expr_stmt)
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

    def _titlecase_prepass(transformer, module):
        """Collect, from the RAW module, the two name sets ``_lint_titlecase``
        consults: the names an ``-import_from`` list binds (exempt at every
        use — a name the file imports is the exporter's to spell), and the
        TitleCase names the file's hosted Python binds itself (``from
        fractions import Fraction``, ``class Helper``, ``Point =
        namedtuple(...)``, ``def Mk``), which ARE Python objects here, so a
        Clausal-position use of one is told to reach it as ``++Name``
        rather than to rename it.  The one carve-out is
        ``_TITLECASE_RENAMED_SPELLINGS`` (``If``, ``Test``): the language
        renamed those spellings, so they name the rename (``if_``, ``test``)
        even though a same-named class is seeded (``If`` is a reified AST
        node) — see ``_lint_titlecase``."""
        for stmt in module.body:
            if (isinstance(stmt, Expr) and isinstance(stmt.value, UnaryOp)
                    and isinstance(stmt.value.op, USub)
                    and isinstance(stmt.value.operand, Call)
                    and isinstance(stmt.value.operand.func, Name)
                    and stmt.value.operand.func.id == "import_from"):
                call = stmt.value.operand
                if len(call.args) == 2 and isinstance(call.args[1], List):
                    for item in call.args[1].elts:
                        if isinstance(item, Name):
                            transformer._titlecase_imported.add(item.id)
                        elif (isinstance(item, Call)
                                and isinstance(item.func, Name)
                                and item.func.id == "alias" and item.args):
                            # ``alias(Orig, Local)``: ``Orig`` is the
                            # exporter's to spell; ``Local`` is the name THIS
                            # file chooses, so it is linted like any name the
                            # file declares (``_lint_titlecase_alias_targets``).
                            if isinstance(item.args[0], Name):
                                transformer._titlecase_imported.add(
                                    item.args[0].id)
                        elif isinstance(item, Call):
                            for arg in item.args:
                                if isinstance(arg, Name):
                                    transformer._titlecase_imported.add(arg.id)
        for bound in _hosted_python_bindings(module):
            if _is_titlecase_identifier(bound):
                transformer._titlecase_python_bound.add(bound)

    #: Directives whose arguments NAME predicates and atoms this module
    #: declares.  Their entries are functor positions even though none of
    #: them is syntactically a call: a ``pred/arity`` spec parses as
    #: ``BinOp(Name, Div, Constant)`` and a list entry as a bare ``Name``, so
    #: narrowing the lint walk to ``Call.func`` dropped every one of them.
    #: ``-constants`` is deliberately absent: its list holds TERMS.
    _DECLARATION_DIRECTIVES = frozenset({
        "module", "private", "hide",
        "dynamic", "discontiguous", "table", "shallow",
        # These read a bare ``Name`` argument directly (``node.id``) rather
        # than a list or a pred/arity spec, so the term walk skipped them and
        # the file got CONTRADICTORY answers about one name:
        # ``-edcg_pred(Foo, 2, [...])`` registered a TitleCase predicate
        # silently while a later ``Foo(...)`` call was still refused.
        "edcg_pred", "edcg_acc", "edcg_pass", "specialize", "translations",
    })

    def _lint_titlecase_declared_names(transformer, args):
        """Lint the predicate/atom NAMES a declaration directive lists.

        Handles the three shapes those directives accept, at the one nesting
        level they use: a bare ``Name`` (``-private([foo])``), a
        ``pred/arity`` spec (``-dynamic(foo/2)``), and a call
        (``-module(m, [foo(A)])``, whose functor the ordinary walk reads).
        A list wrapper is transparent -- both the positional and the
        single-list spellings reach the same entries.
        """
        def each(node):
            if isinstance(node, List):
                for element in node.elts:
                    each(element)
            elif (isinstance(node, BinOp) and isinstance(node.op, Div)
                    and isinstance(node.left, Name)):
                transformer._lint_titlecase(node.left, root_is_functor=True)
            elif isinstance(node, Name):
                transformer._lint_titlecase(node, root_is_functor=True)
            else:
                transformer._lint_titlecase(node)
        for arg in args:
            each(arg)

    def _lint_titlecase_alias_targets(transformer, args):
        """Lint the LOCAL name of each ``alias(Orig, Local)`` in an
        ``-import_from`` list.  The imported names are the exporter's to
        spell and stay exempt, but ``Local`` is chosen here: an alias to a
        TitleCase name is refused like any other TitleCase functor this file
        writes (``-import_from(m, [alias(fib, Fibo)])`` used to load, and
        ``Fibo(0, X)`` then answered)."""
        if len(args) != 2 or not isinstance(args[1], List):
            return
        for item in args[1].elts:
            if (isinstance(item, Call) and isinstance(item.func, Name)
                    and item.func.id == "alias" and len(item.args) == 2
                    and isinstance(item.args[1], Name)):
                transformer._lint_titlecase(item.args[1], root_is_functor=True)

    def _expand_currency_tables(transformer, module):
        """Rewrite every ``-constants_number_currency`` into its fact
        statements, in place, BEFORE the ordinary visit sees the body.

        Source-to-source on purpose: the generated facts are then transformed
        by exactly the machinery that transforms hand-written ones, so a
        declared table is the same kind of predicate as the fact lines it
        replaces -- not a second kind wearing the same name.
        """
        body = []
        changed = False
        for stmt in module.body:
            call = _table_directive_call(stmt)
            if call is None:
                body.append(stmt)
                continue
            body.extend(_expand_currency_table(call))
            changed = True
        if changed:
            module.body = body

    def _lint_scale_in_name(transformer, *nodes):
        """Warn for a FUNCTOR that claims a scale and carries a bare number.

        ``minimum_leverage_bps(300)`` puts "basis points" in the identifier
        and nothing where the engine can read it, so the 300 is a bare
        integer: it sums with another currency's integer in silence, and a
        comparison against a threshold in another scale returns a REVERSED
        answer rather than a wrong number. See ClausalScaleInNameWarning.

        Piggybacks on ``_lint_titlecase``'s call sites rather than adding
        nineteen of its own -- those are exactly the points at which the
        transformer has recognised a CLAUSAL subtree, which is the set this
        wants. **The coupling is deliberate and worth knowing about: removing
        a ``_lint_titlecase`` call would silently narrow this lint too.**

        The discriminator is a bare numeric LITERAL. A converted site is
        ``155000 (usd_cent)`` -- a ``Call`` -- so doing the right thing
        silences the warning, which is what makes this a migration worklist
        rather than a permanent complaint.
        """
        def walk_(node):
            if isinstance(node, Call):
                func = node.func
                if (isinstance(func, Name)
                        and _name_claims_a_scale(func.id)
                        and func.id not in transformer._scale_name_seen
                        and any(_is_bare_number(a) for a in node.args)
                        # ...and NOTHING in the row carries a unit. A row with
                        # a united column has its scale where the engine can
                        # check it, so the lint has nothing left to ask for --
                        # which is what makes the count fall as sites convert,
                        # the property the whole lint was offered for.
                        and not any(_carries_a_unit(a) for a in node.args)):
                    transformer._scale_name_seen.add(func.id)
                    import warnings                            # noqa: PLC0415
                    lineno = getattr(node, "lineno", None)
                    where = (transformer._site(lineno) if lineno
                             else transformer._filename)
                    warnings.warn(
                        f"{where}: `{func.id}` names a "
                        f"scale but carries a bare number — the scale exists "
                        f"only in the identifier, where nothing can check it. "
                        f"Declare the amount with -constant_number_currency "
                        f"(or -constant_number_units) and use it here, so the "
                        f"unit is a fact the engine holds.",
                        ClausalScaleInNameWarning, stacklevel=2)
            for child in iter_child_nodes(node):
                walk_(child)

        for node in nodes:
            if node is not None:
                walk_(node)

    def _lint_retired_quasi_quote(transformer, *nodes):
        """RECORD ``q(<one argument>)`` sites for the retired-q() warning;
        ``_settle_retired_quasi_quote`` decides at the end of the module.

        ``q()`` quasi-quotation was retired 2026-09-25 (``q`` is an ordinary
        name now), so an old expansion rule written with it builds
        ``('q', ...)`` cells that match no item: the module would load with
        the expansion silently missing.  Warned for a clause that is part of
        the expansion -- one containing a ``term_expansion(_, _, _, _)``
        call (its head, or a body calling it), or a clause of a predicate
        REACHABLE from a term_expansion body in this file (the delegating
        shape ``term_expansion(I, O, S, S) <- helper(I, O)`` with the q()
        patterns in ``helper``'s clauses).  That is what keeps a user's own
        ``q/1`` quiet everywhere else.  Not read: a ``q(...)`` that is itself
        a body GOAL (a call of the user's ``q/1``, meaningful either way),
        and anything inside a ``++`` Python escape (Python's own ``q(x)``).
        Reachability is by name within this file only: a helper imported
        from another module is not followed.

        Piggybacks on ``_lint_titlecase``'s call sites, like
        ``_lint_scale_in_name``.  Cheap on the common path: a file whose
        source has no ``q(`` is never walked.
        """
        if transformer._retired_q_file_has_q is None:
            lines = transformer._source_lines
            transformer._retired_q_file_has_q = (
                lines is None or any("q(" in line for line in lines))
        if not transformer._retired_q_file_has_q:
            return
        for top in nodes:
            if top is None or id(top) in transformer._retired_q_seen:
                continue
            transformer._retired_q_seen.add(id(top))
            head, body = top, None
            if isinstance(top, Compare):
                try:
                    arrow = _detect_arrow(top.left, top.ops, top.comparators,
                                          transformer._source_lines)
                except SyntaxError:     # the rewriter reports it, not a lint
                    arrow = None
                if arrow is not None:
                    head, body = arrow
            head_name = (head.func.id if isinstance(head, Call)
                         and isinstance(head.func, Name) else None)
            goals = {id(head)}      # a clause of q/1 is not a pattern
            stack = [body]
            while stack:
                g = stack.pop()
                if isinstance(g, Tuple):
                    stack.extend(g.elts)
                elif isinstance(g, BoolOp):
                    stack.extend(g.values)
                elif isinstance(g, UnaryOp) and isinstance(g.op, Not):
                    stack.append(g.operand)
                elif g is not None:
                    goals.add(id(g))
            q_sites, calls, has_te = [], set(), False

            def walk_(node):
                nonlocal has_te
                if isinstance(node, (Constant, JoinedStr)):
                    return
                if _python_escape_operand(node) is not None:
                    return
                if isinstance(node, Call) and isinstance(node.func, Name):
                    fid = node.func.id
                    if (fid == "term_expansion"
                            and len(node.args) + len(node.keywords) == 4):
                        has_te = True
                    if (fid == "q" and len(node.args) == 1
                            and not node.keywords and id(node) not in goals):
                        q_sites.append(node)
                    calls.add(fid)
                elif isinstance(node, Name):
                    calls.add(node.id)
                for child in iter_child_nodes(node):
                    walk_(child)

            walk_(top)
            # Every clause is recorded (in a file that has a ``q(``), not
            # only those with q() sites: a clause with none can still be a
            # LINK on the path from term_expansion to one that has.
            transformer._retired_q_records.append(
                (head_name, has_te, calls, q_sites))

    def _settle_retired_quasi_quote(transformer):
        """Emit ClausalRetiredQuasiQuoteWarning for the recorded clauses
        that belong to the expansion -- see ``_lint_retired_quasi_quote``.
        Once per clause, at its first ``q(...)``."""
        records = transformer._retired_q_records
        if not records:
            return
        reachable, frontier = set(), ["term_expansion"]
        callees = {}
        for head_name, has_te, calls, _q in records:
            if head_name is not None:
                callees.setdefault(head_name, set()).update(calls)
            if has_te:
                frontier.extend(calls)
        while frontier:
            name = frontier.pop()
            if name in reachable:
                continue
            reachable.add(name)
            frontier.extend(callees.get(name, ()))
        import warnings                                        # noqa: PLC0415
        reported = set()    # a subtree can be linted from two call sites
        for head_name, has_te, _calls, q_sites in records:
            if not (has_te or head_name in reachable):
                continue
            fresh = [n for n in q_sites if id(n) not in reported]
            reported.update(id(n) for n in q_sites)
            if not fresh:
                continue
            first = fresh[0]
            lineno = getattr(first, "lineno", None)
            where = (transformer._site(lineno) if lineno
                     else transformer._filename)
            via = ("a term_expansion/4 clause" if has_te else
                   f"a clause of {head_name}, reached from term_expansion/4")
            warnings.warn(
                f"{where}: `q(...)` in {via}: q() quasi-quotation was "
                f"retired 2026-09-25 and `q` is an ordinary name now, so "
                f"this builds a ('q', ...) term that matches nothing and the "
                f"expansion silently does not fire. Write the pattern as a "
                f"plain term, as in ISO term_expansion: "
                f"term_expansion(fact(X), [fact(X)], S, S).",
                ClausalRetiredQuasiQuoteWarning,
                stacklevel=_stacklevel_outside_rewriter())
        records.clear()

    def _lint_keyword_argument(transformer, *nodes):
        """Refuse a TERM written with KEYWORD arguments inside the CLAUSAL
        subtrees *nodes* (see ClausalKeywordArgumentWarning).

        POSITION.  Only a ``Call`` whose ``func`` is a bare ``Name`` is read
        -- a clause head, a goal, a term in an argument, at any depth.  Like
        ``_lint_titlecase`` (whose call sites this piggybacks on, rather than
        adding nineteen of its own) it sees only what the transformer has
        recognised as Clausal, so hosted Python in the same file is never
        read, and it stops at a ``++`` escape, which is Python by definition
        -- ``++(dict(a=1))`` and ``++(__import__('m', fromlist=['x']))`` are
        ordinary Python calls that happen to stand in a Clausal position.

        TWO CARVE-OUTS, both surface spellings that are not term arguments:

        * a ``-directive``'s OPTIONS (``-specialize(solve, p, alias=q)``).
          Nothing is needed here for them: the directive call site hands this
          walk the directive's ARGS and its keyword VALUES, never the
          directive ``Call`` itself, so its own ``alias=`` is not in the tree
          being walked.  (Said out loud because it is load-bearing and
          invisible: change that call site to pass ``neg.operand`` and every
          directive option in the repository starts failing to load.)
        * an EDCG hidden argument (``p(L, _edcg_counter_in=0)``).  Those
          address a GENERATED argument of an EDCG predicate, are ``_``-led by
          construction (a bare ``_foo`` is a logic-variable spelling, so no
          declared field can collide with one), and do not declare a field
          name.  That is the ``_``-prefix test below.
        """
        import warnings  # noqa: PLC0415

        def report(node, functor, named, arity):
            lineno = getattr(node, "lineno", None)
            where = transformer._site(lineno) if lineno else "unknown site"
            snippet = transformer._source_snippet(lineno) if lineno else ""
            if snippet:
                snippet = " — " + snippet
            shown = ", ".join(f"{k}=" if k else "**" for k in named)
            # functor/ARITY, not the bare name: the arity is what tells a
            # reader which declaration to go and look at, and two predicates
            # of one name at different arities are ordinary here.
            functor = f"{functor}/{arity}"
            msg = (
                f"{where}{snippet}: `{functor}` is written with keyword "
                f"arguments ({shown}): a term is built positionally. Write "
                f"the arguments in the declared order, and declare the "
                f"functor with `-private([...])` "
                f"if it is data. (Keyword terms were the only way to name a "
                f"functor's fields, which made those names depend on clause "
                f"order; the spelling has no ISO Prolog reading and was "
                f"retired 2026-09-19. A `-directive`'s options and an EDCG "
                f"`_`-led hidden argument keep their keywords.)"
            )
            if KEYWORD_ARGUMENT_SEVERITY == "error":
                _raise_located_syntax_error(
                    msg, node, transformer._source_lines,
                    transformer._filename)
            warnings.warn(msg, ClausalKeywordArgumentWarning,
                          stacklevel=_stacklevel_outside_rewriter())

        def walk_(node):
            if node is None or isinstance(node, (Constant, JoinedStr)):
                return
            if _python_escape_operand(node) is not None:
                return
            if isinstance(node, Call):
                named = [kw.arg for kw in node.keywords
                         if kw.arg is None or not kw.arg.startswith("_")]
                if named and isinstance(node.func, Name):
                    report(node, node.func.id, named,
                           len(node.args) + len(node.keywords))
                for child in iter_child_nodes(node):
                    walk_(child)
                return
            for child in iter_child_nodes(node):
                walk_(child)

        for node in nodes:
            walk_(node)

    def _lint_titlecase(transformer, *nodes, root_is_functor=False):
        """Lint every TitleCase ``Name`` in FUNCTOR position within the
        CLAUSAL subtrees *nodes* (see ClausalTitleCaseIdentifierWarning),
        once per (file, identifier).

        POSITION.  Only the ``func`` of a ``Call`` is read, and only when it
        is a bare ``Name`` — a clause head's functor, and a goal called in a
        body, at any nesting depth (so the ``Fraction`` of
        ``bar(Fraction(1, 3))`` is reached even though the call sits in an
        argument).  A QUOTED callable (``'Foo'(1)``) is an atom, not an
        identifier, and is not linted: ISO names a functor with any atom, so
        only the bare spelling is refused.  A capital-initial name standing
        anywhere a VALUE goes is a logic variable since 2026-09-10
        (``_is_logic_var_name``) and is not linted at all.  ``root_is_functor``
        marks the two callers that hand over a bare ``Name`` which IS a
        functor — the zero-arity fact heads ``flag,`` and ``flag`` — since
        nothing in the node itself says so.

        Called from each point where the transformer recognises a Clausal
        position in the raw parse tree — a clause (``head <- body``, a DCG
        rule), a bodyless fact (trailing comma, or the comma-optional form
        of a DECLARED predicate), a query, the arguments of a ``-directive``,
        and the operand of a ``--`` seam — with the raw nodes, before any
        rewriting, so it sees the author's spelling.  Nothing else in the
        file is read: module-level Python (assignments, imports, ``raise``,
        ``try``, an undeclared bare call such as ``isinstance(...)``) and
        ``def``/``class`` bodies are hosted Python, where a TitleCase class
        is legitimate and ``++X`` is Python's own double unary plus — the
        ``++`` remedy would be wrong advice there.  Within a Clausal subtree
        it does NOT read:

        * a ``++`` Python escape (adjacent double ``UAdd`` --
          ``_python_escape_operand``, the same predicate the TRANSFORM
          applies, so a spaced ``+ +Foo`` that compiles as Clausal is linted
          as Clausal): Python code by definition, the very place a TitleCase
          class name belongs;
        * string literals and f-strings: text, not identifiers — including a
          string used as the CALLABLE (``'Foo'(1)``), which is a quoted atom
          naming the predicate ``Foo/1``, not the identifier ``Foo``;
        * a name bound by an ``-import_from`` list (for ``alias(Orig,
          Local)``, only ``Orig``: the local name is this file's choice and
          is linted) — see ``_titlecase_prepass``;
        * ``_TITLECASE_EXEMPT_NAMES`` (``Undefined``).

        And one carve-out in the REMEDY: ``_TITLECASE_RENAMED_SPELLINGS``
        (``If`` -> ``if_``, ``Test`` -> ``test``) name the rename the
        language itself performed, never the ``++`` escape, even though
        ``If`` is also a seeded AST node class.

        Python's ``True``/``False``/``None`` arrive as ``Constant`` nodes and
        never reach the walk.  Attribute names (``X.Foo``) and keyword
        argument names (``foo(Key=1)``) are not ``Name`` nodes and are not
        linted either.

        A name that IS a Python class in the module's namespace
        (``_python_class_names``: injected runtime names, AST node classes,
        Python builtins — or one the file's own hosted Python binds,
        ``_titlecase_python_bound``) still warns, but the remedy it names is
        the ``++`` escape rather than a snake_case rename.

        Severity is ``TITLECASE_IDENTIFIER_SEVERITY``: ``"warn"`` emits the
        warning at the identifier's first site, ``"error"`` raises there.
        """
        # Same subtrees, different question — see _lint_scale_in_name and
        # _lint_keyword_argument, which piggyback here rather than on
        # nineteen call sites each.
        transformer._lint_scale_in_name(*nodes)
        transformer._lint_keyword_argument(*nodes)
        transformer._lint_retired_quasi_quote(*nodes)
        import warnings  # noqa: PLC0415

        def _is_escape(node):
            return _python_escape_operand(node) is not None

        def consider(ident, node):
            if (ident not in transformer._titlecase_seen
                    and ident not in _TITLECASE_EXEMPT_NAMES
                    and _is_titlecase_identifier(ident)):
                transformer._titlecase_seen.add(ident)
                if ident not in transformer._titlecase_imported:
                    report(ident, node)

        def walk_(node, functor_position=False):
            # Text, not identifiers — and that holds in FUNCTOR position too,
            # which is where ``'Foo'(1)`` lands: the generic ``Call`` arm
            # below hands the callable over with ``functor_position=True``
            # and it stops here.  A single-quoted token is an ATOM by
            # construction (its spelling is data), and ISO names a functor
            # with any atom, so the capitalisation rule further down — which
            # decides what a BARE token means — has nothing to say about it.
            # ``'Foo'(1)`` is the predicate ``Foo/1``; the bare ``Foo(1)``
            # stays refused, which is ISO's own asymmetry
            # (``variable_cannot_be_functor``).
            #
            # This arm used to read the string as the identifier it names and
            # lint it, on the grounds that the sugar would otherwise bypass
            # the gate.  That was right while TitleCase had no legitimate
            # reading anywhere, and wrong from the moment a capital-initial
            # BARE name became a logic variable: quoting then became the only
            # way to SAY the atom, so linting it refused the very spelling
            # the rest of the language had just made necessary.
            #
            # Nothing is bypassed by allowing it.  ``"Foo"(1)`` is refused one
            # layer down by ``_refuse_double_quoted_functor`` (ISO 6.3.3) —
            # which the lint used to pre-empt, so that case now gets its own
            # message instead of advice about renaming an identifier — and a
            # quoted fact head still has to be a plain name, because its
            # functor class name is emitted as Python source.
            if isinstance(node, (Constant, JoinedStr)) or _is_escape(node):
                return
            if isinstance(node, Name):
                # THE POSITION RULE.  A capital-initial name standing where a
                # VALUE goes is a logic variable (``_is_logic_var_name``), so
                # there is nothing to lint about it; only the FUNCTOR of a
                # call — a clause head's functor, or a goal in a body — is
                # still refused.
                #
                # Why the functor case is not simply allowed to be a variable
                # too: a variable in functor position is NOT ``call/N`` in
                # this language, it is the UNIT-ANNOTATION sugar.
                # ``run(G, X) <- (G(X))`` does not call ``G``; it builds a
                # Quantity whose unit is ``G`` and dies at RUNTIME with
                # "cannot build a Quantity from AttVar(...): SI prefixes
                # cannot be used as units".  So if TitleCase were a variable
                # here as well, a bare Python class in a clause body
                # (``bar(Fraction(1, 3))``) would stop being a load error
                # that names the ``++Fraction`` escape and would quietly
                # become a units expression failing much later, in a message
                # about SI prefixes that names neither ``Fraction`` nor the
                # line it was written on.  The asymmetry this creates is
                # deliberate and was ruled on 2026-09-10: ``FOO(3)`` is legal
                # units sugar with a computed unit, ``Foo(3)`` is refused.
                if functor_position:
                    consider(node.id, node)
                return
            if isinstance(node, Call):
                walk_(node.func, functor_position=True)
                for child in node.args:
                    walk_(child)
                for kw in node.keywords:
                    walk_(kw.value)
                return
            for child in iter_child_nodes(node):
                walk_(child)

        def report(ident, node):
            lineno = getattr(node, "lineno", None)
            where = transformer._site(lineno) if lineno else "unknown site"
            snippet = transformer._source_snippet(lineno) if lineno else ""
            if snippet:
                snippet = " — " + snippet
            convention = (
                "Clausal identifiers are lowercase (predicates, atoms, "
                "functors) or ALL_CAPS / underscore-led (logic variables); "
                "TitleCase has no role"
            )
            # The renamed-spelling carve-out speaks for the LANGUAGE (``If``
            # is also a seeded AST node class, but the remedy is ``if_``),
            # so it must not overrule a class the FILE ITSELF binds: a
            # module whose hosted Python defines or imports its own ``Test``
            # means that class, and telling its author to "Rename `Test` ->
            # `test`" names a predicate that does not exist.
            renamed_by_the_language = (
                ident in _TITLECASE_RENAMED_SPELLINGS
                and ident not in transformer._titlecase_python_bound)
            if (not renamed_by_the_language
                    and (ident in _python_class_names()
                         or ident in transformer._titlecase_python_bound)):
                msg = (
                    f"{where}{snippet}: `{ident}` is TitleCase: `{ident}` is "
                    f"a Python class; reach it as `++{ident}`. {convention}"
                )
            else:
                msg = (
                    f"{where}{snippet}: `{ident}` is TitleCase. {convention} "
                    f"— a Python class is reached as `++{ident}`. Rename "
                    f"`{ident}` -> `{_titlecase_to_snake(ident)}`"
                )
            if TITLECASE_IDENTIFIER_SEVERITY == "error":
                _raise_located_syntax_error(
                    msg, node, transformer._source_lines,
                    transformer._filename)
            warnings.warn(msg, ClausalTitleCaseIdentifierWarning,
                          stacklevel=_stacklevel_outside_rewriter())

        for node in nodes:
            if node is not None:
                walk_(node, functor_position=root_is_functor)

    def visit_Module(transformer, module):
        """Visit the module body, then emit a final ``BareAtomRefs`` item
        carrying every bare reference the per-clause transformers saw.

        The auto-mint pass in ``compiler_v2._process_bare_atom_refs`` reads
        this item and decides per-name whether to install the global atom.

        This is also the first point at which the file's clause-head functors
        and its logic-variable reads are both complete, so it is where
        ``_check_var_shaped_predicate_names`` can compare them.
        """
        # Text crossings (``str(x)``, f-string ``{x}``) in Python-hosted code
        # route through ``$text`` -- unless the file binds ``str`` itself, in
        # which case its own binding wins and nothing is rewritten.
        transformer._str_shadowed = _binds_name(module, "str")
        transformer._zero_arity_heads = _zero_arity_head_prepass(module)
        # Snapshot the file's OWN Python bindings before the walk. Read
        # afterwards it would include generated code -- the -module rewrite
        # emits an assignment for every declared atom, so `pi` would look
        # like a hosted binding and the constant/atom pair this design is
        # built around would be refused. See _check_constant_name_is_free.
        transformer._hosted_names = set(_hosted_python_bindings(module))
        transformer._import_module_bases.update(_import_module_prepass(module))
        transformer._expand_currency_tables(module)
        transformer._titlecase_prepass(module)
        _mark_arith_position_names(module)
        result = transformer.generic_visit(module)
        transformer._lint_seam_text_compare(result, transformer._seam_exports[0])
        transformer._check_var_shaped_predicate_names()
        transformer._check_constant_name_is_free()
        transformer._settle_atom_functor_sites()
        transformer._settle_retired_quasi_quote()
        # The field names each functor's head carries, as the rewriter
        # settled them (first registration wins).  compile_module step 4
        # stamps ``row.signature`` from this -- the class is no longer the
        # vehicle (todo/done/step4-signature-comes-from-the-class-2026-09-24.md).
        # Only when there is a functor to name, like BareAtomRefs below: the
        # consumer (``compiler_v2._head_field_names``) reads an absent item as
        # ``{}``, so an empty one would say nothing and only add noise to
        # the item list.
        if transformer._seen_functors:
            transformer._module_items.append(HeadFieldNamesItem(
                fields={
                    name: tuple(fields)
                    for name, fields in transformer._seen_functors.items()},
                by_arity={
                    (name, arity): tuple(fields)
                    for name, arities in transformer._functor_arities.items()
                    for arity, fields in arities.items()}))
        if transformer._bare_atom_refs:
            transformer._module_items.append(
                BareAtomRefsItem(names=frozenset(transformer._bare_atom_refs))
            )
        if transformer._implicit_atoms_default and not any(
            isinstance(it, (StrictAtomsItem, ImplicitAtomsItem))
            for it in transformer._module_items
        ):
            transformer._module_items.append(ImplicitAtomsItem())
        # Cross-mode literal lint (2026-09-26): what this file's importers
        # need to know about its ``-double_quotes`` mode, and the seam
        # sites this file could not judge before its own imports ran.
        # Only when the file SAYS something about its mode -- a declaration
        # or a governed literal -- so a file with neither carries no item
        # and its importers' lint reads its mode as unknown, not as a guess.
        if transformer._double_quotes_modes_used or transformer._double_quotes_explicit:
            transformer._module_items.append(DoubleQuotesModeItem(
                mode=transformer._double_quotes_mode,
                explicit=transformer._double_quotes_explicit,
                modes_used=tuple(sorted(transformer._double_quotes_modes_used))))
        if transformer._cross_mode_sites:
            transformer._module_items.append(CrossModeLiteralSitesItem(
                sites=tuple(transformer._cross_mode_sites)))
        return result

    def _check_constant_name_is_free(transformer):
        """A constant declaration must not overwrite an existing binding.

        ``-constant_value(name, ...)`` lowers to a module-level assignment,
        so it writes into the file's own Python namespace. Left unchecked it
        silently replaces whatever was there: an import (``-constant_value(
        math, 3)``), a helper ``def``, a functor class, an imported
        predicate. The value would be right and every OTHER use of that name
        would quietly become the constant.

        An ATOM of the same spelling is the one deliberate exception, and
        the reason this check exists as a whitelist rather than a plain "is
        it bound": ``pi`` the atom and ``++pi`` the constant are meant to
        coexist, and ``_process_declarations`` is what keeps the atom from
        binding over the value.

        Checked once the whole module has been walked, because a ``def``
        BELOW the declaration overwrites it just as surely as one above.
        """
        if not transformer._constants:
            return
        hosted = {}
        for name in getattr(transformer, "_hosted_names", ()):
            hosted.setdefault(name, "hosted Python (an import, def, class "
                                     "or assignment)")
        for name in transformer._seen_functors:
            hosted.setdefault(name, "a functor or predicate declared in this "
                                    "file")
        for name in transformer._imported_functors:
            hosted.setdefault(name, "an -import_from entry")
        clashes = sorted(n for n in transformer._constants if n in hosted)
        if not clashes:
            return
        first = clashes[0]
        names = ", ".join(f"`{n}`" for n in clashes)
        subject = f"{names} are" if len(clashes) > 1 else f"{names} is"
        raise SyntaxError(
            f"-constant_value: {subject} already bound by {hosted[first]}. "
            f"A constant declaration writes a module global, so it would "
            f"overwrite that binding and every other use of the name would "
            f"silently become the constant. Rename the constant. (An ATOM "
            f"of the same spelling is fine and is the intended case: `{first}` "
            f"the atom and `++{first}` the constant coexist.)")

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

    def visit_Call(transformer, call):
        if (isinstance(call.func, Name) and call.func.id == "bool"
                and len(call.args) == 1 and not call.keywords):
            transformer._lint_boolean_seam(call.args[0], "`bool(...)`")
        call = transformer.generic_visit(call)
        # ``str(x)`` in Python-hosted code: the atom-aware text crossing.
        if (isinstance(call.func, Name) and call.func.id == "str"
                and not getattr(transformer, "_str_shadowed", False)
                and len(call.args) == 1 and not call.keywords
                and not isinstance(call.args[0], Starred)):
            return replace(
                Call(func=replace(Name(id="$text", ctx=Load()), call.func),
                     args=call.args, keywords=[]),
                call,
            )
        return call

    def visit_JoinedStr(transformer, joined):
        joined = transformer.generic_visit(joined)
        # f-string ``{x}`` / ``{x!s}`` (with or without a format spec) in
        # Python-hosted code: interpolate the atom-aware text.  ``!r`` and
        # ``!a`` are left alone -- they ask for the repr on purpose.
        #
        # A bare ``{x}`` goes through ``$text_value`` (spell an atom, pass
        # anything else unchanged) so a format spec still meets the VALUE:
        # ``f"{n:02d}"`` must give ``"06"``, not raise because ``format()``
        # was handed the string ``"6"``.  An explicit ``{x!s}`` keeps
        # Python's own meaning -- ``str`` first, then the spec -- through
        # ``$text``.
        if getattr(transformer, "_str_shadowed", False):
            return joined
        for part in joined.values:
            if isinstance(part, FormattedValue) and part.conversion in (-1, 115):
                helper = "$text" if part.conversion == 115 else "$text_value"
                part.value = replace(
                    Call(func=replace(Name(id=helper, ctx=Load()), part.value),
                         args=[part.value], keywords=[]),
                    part.value,
                )
                part.conversion = -1
        return joined

    def visit_FunctionDef(transformer, node):
        if is_template_func(node):
            return compile_template_func(node, transformer._quote_map)
        transformer._scope_depth += 1
        # Scanned BEFORE the walk, so the lint sees the names the AUTHOR
        # bound and not the ones the seam lowering is about to add: an
        # exported goal variable becomes a local (``_export_stmts``,
        # ``_declare_locals``), and scanning afterwards would report every
        # correct site in a program.
        transformer._python_locals.append(
            transformer._author_bound_locals(node))
        transformer._seam_exports.append({})
        try:
            result = transformer.generic_visit(node)
            transformer._lint_seam_text_compare(result, transformer._seam_exports[-1])
        finally:
            transformer._seam_exports.pop()
            transformer._python_locals.pop()
            transformer._scope_depth -= 1
        return result

    def _author_bound_locals(transformer, node) -> set:
        """Names *node*'s own body binds as Python locals, author-written.

        Params, assignments, ``with``/``except``/``import`` aliases, and
        ``for`` targets — but NOT a ``for`` target over a ``--goal`` iterable,
        which is a binding the SEAM introduces and is the name of a logic
        variable by construction.  Counting those would fire the lint on
        every correct goal-position seam ever written.

        Nested ``def``/``class`` bodies are their own scope and are skipped;
        comprehension targets are comprehension-scoped in Python 3 and are
        not function locals at all.
        """
        bound: set = set()
        for a in (list(node.args.posonlyargs) + list(node.args.args)
                  + list(node.args.kwonlyargs)
                  + [node.args.vararg, node.args.kwarg]):
            if a is not None:
                bound.add(a.arg)

        def _targets(target):
            if isinstance(target, Name):
                bound.add(target.id)
            elif isinstance(target, (Tuple, List)):
                for e in target.elts:
                    _targets(e)

        def _walk(body):
            for item in body:
                if isinstance(item, (FunctionDef, AsyncFunctionDef, ClassDef)):
                    bound.add(item.name)
                    continue                       # its own scope
                if isinstance(item, (Assign, AugAssign, AnnAssign)):
                    for t in (item.targets if isinstance(item, Assign)
                              else [item.target]):
                        _targets(t)
                elif isinstance(item, (For, AsyncFor)):
                    found = transformer._goal_operand(item.iter)
                    if found is None:
                        _targets(item.target)      # an ordinary Python loop
                elif isinstance(item, With):
                    for w in item.items:
                        if w.optional_vars is not None:
                            _targets(w.optional_vars)
                elif isinstance(item, Try):
                    for h in item.handlers:
                        if h.name:
                            bound.add(h.name)
                elif isinstance(item, (Import, ImportFrom)):
                    for alias_node in item.names:
                        spelling = alias_node.asname or alias_node.name
                        bound.add(spelling.split(".")[0])
                for field in ("body", "orelse", "finalbody"):
                    inner = getattr(item, field, None)
                    if isinstance(inner, list):
                        _walk(inner)
                for h in getattr(item, "handlers", []) or []:
                    _walk(h.body)
        _walk(node.body)
        return bound

    def _warn_shadowed_variables(transformer, fresh, expression, anchor,
                                 goal_ast=None):
        """Warn for each name lowered as a LOGIC VARIABLE that is also an
        author-bound Python local in this scope.

        Two sources, and the second is the one that bites.  ``fresh`` is the
        goal's own variables.  A name captured by a ``++`` escape is NOT in
        it: the escape lowers to ``PyThunk(lambda P: P, [(P := $Var())])``,
        whose walrus REBINDS the author's own name to a fresh variable — so
        the local's value is clobbered on the way in, and reading the emitted
        walrus targets is what finds it.  Measured: ``P = 2`` then
        ``for V in --pair(++P, V)`` answers every row.
        """
        if not transformer._python_locals:
            return
        locals_here = transformer._python_locals[-1]
        captured = set(fresh)
        if goal_ast is not None:
            for node in walk(goal_ast):
                if (isinstance(node, NamedExpr)
                        and isinstance(node.target, Name)):
                    captured.add(node.target.id)
        for name in sorted(captured):
            if name not in locals_here:
                continue
            import warnings  # noqa: PLC0415
            warnings.warn(ClausalShadowedVariableWarning(
                f"{transformer._filename}:{getattr(anchor, 'lineno', '?')}: "
                f"`{name}` is bound as a Python local here, but inside the "
                f"seam `{unparse(expression)}` it is a LOGIC VARIABLE — the "
                f"local's value does not reach the goal, and `++{name}` does "
                f"not change that. The goal is less constrained than it "
                f"reads, so it answers every row rather than the one you "
                f"meant, and nothing raises. Rename the local to lower case "
                f"(`{name.lower()}`) and pass `++{name.lower()}`, or rename "
                f"the variable if you did mean a fresh one."
            ), stacklevel=2)

    visit_AsyncFunctionDef = visit_FunctionDef

    # ── boolean-context lint ───────────────────────────────────────────
    def _note_seam_bound(transformer, names, anchor):
        """Record *names* as bound by a goal-position seam in the current
        Python scope (the innermost ``def``, else the module body)."""
        scope = transformer._seam_exports[-1]
        for n in names:
            scope.setdefault(n, anchor.lineno)

    def _lint_seam_text_compare(transformer, scope_node, bound):
        """Warn for each comparison of a seam-bound name with a Python str
        LITERAL inside *scope_node* (a rewritten ``def``, or the module).
        See ``ClausalSeamTextCompareWarning`` for the shapes and the
        deliberate gaps.  Runs AFTER the scope is rewritten: a ``--"x"`` on
        the other side is a ``$seam(...)`` call by now, so it cannot be
        mistaken for a literal, and a plain Python literal is still a
        ``Constant``.  Nested ``def``s are their own scopes and were scanned
        (and their names popped) before this runs, so they are skipped."""
        if not bound:
            return
        import warnings  # noqa: PLC0415
        names = dict(bound)
        # a plain alias ``y = T`` in this scope shares the diagnosis
        for node in walk(scope_node):
            if (isinstance(node, Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], Name)
                    and isinstance(node.value, Name) and node.value.id in names):
                names.setdefault(node.targets[0].id, names[node.value.id])

        def is_str_lit(n):
            return isinstance(n, Constant) and type(n.value) is str

        def str_lits(n):
            if is_str_lit(n):
                return [n.value]
            if isinstance(n, (List, Tuple, Set)) and n.elts and all(is_str_lit(e) for e in n.elts):
                return [e.value for e in n.elts]
            return None

        def warn(anchor, name, spelled, lit):
            warnings.warn(ClausalSeamTextCompareWarning(
                f"{transformer._filename}:{anchor.lineno}:{anchor.col_offset + 1}: "
                f"`{name}` comes from the seam at line {names[name]} and is a "
                f"Clausal term, so `{spelled}` is False for a STRING answer and "
                f"True only for an ATOM: compare with --\"{lit}\" (or "
                f"to_python({name}) == \"{lit}\")"), stacklevel=2)

        skip = set()
        for node in walk(scope_node):
            if node is scope_node:
                continue
            if isinstance(node, (FunctionDef, AsyncFunctionDef, Lambda, ClassDef)):
                for inner in walk(node):
                    skip.add(id(inner))
        for node in walk(scope_node):
            if id(node) in skip:
                continue
            if isinstance(node, Compare):
                left = node.left
                for op, right in zip(node.ops, node.comparators):
                    if isinstance(op, (Eq, NotEq)):
                        for a, b in ((left, right), (right, left)):
                            if isinstance(a, Name) and a.id in names and is_str_lit(b):
                                sym = "==" if isinstance(op, Eq) else "!="
                                warn(node, a.id, f"{a.id} {sym} {b.value!r}", b.value)
                    elif isinstance(op, (In, NotIn)):
                        lits = str_lits(right)
                        if isinstance(left, Name) and left.id in names and lits:
                            sym = "in" if isinstance(op, In) else "not in"
                            warn(node, left.id, f"{left.id} {sym} {unparse(right)}", lits[0])
                    left = right
            elif isinstance(node, Match) and isinstance(node.subject, Name) and node.subject.id in names:
                for case in node.cases:
                    pats = [case.pattern]
                    if isinstance(case.pattern, MatchOr):
                        pats = list(case.pattern.patterns)
                    lits = [p.value.value for p in pats
                            if isinstance(p, MatchValue) and is_str_lit(p.value)]
                    if lits:
                        warn(case.pattern, node.subject.id,
                             f"match {node.subject.id}: case {unparse(case.pattern)}", lits[0])

    def _lint_boolean_seam(transformer, operand, context):
        """Warn when *operand* is a ``--`` seam read as a truth value.

        Called only for operands in a BOOLEAN context that is not a goal
        position -- goal positions (``if --g:``, ``while not --g:``, ``for X
        in --g:``, a comprehension's first iterable) are lowered by their
        own visitors before any generic visit reaches here.  Outside them
        ``--g`` is the CELL, a non-empty tuple, so the test is always true
        (``not --g`` always false) and the goal never runs.  See
        ``ClausalBooleanSeamWarning``."""
        expression = _double_prefix_operand(operand, USub)
        if expression is None:
            return
        import warnings  # noqa: PLC0415
        warnings.warn(ClausalBooleanSeamWarning(
            f"{transformer._filename}:{operand.lineno}:{operand.col_offset + 1}: "
            f"`--{unparse(expression)}` is used as a truth value in {context}, "
            f"which is not a goal position: there `--` builds the cell (a "
            f"non-empty tuple), so it is ALWAYS TRUE and the goal never runs. "
            f"To run the goal, put it in goal position (`if --g:`, "
            f"`if not --g:`, `while --g:`, `for X in --g:`), or, as an "
            f"expression, `any(True for X in --g)` with X a variable of "
            f"the goal."
        ), stacklevel=2)

    def visit_Assert(transformer, node):
        transformer._lint_boolean_seam(node.test, "an `assert`")
        return transformer.generic_visit(node)

    def visit_BoolOp(transformer, node):
        word = "an `and`" if isinstance(node.op, And) else "an `or`"
        for value in node.values:
            transformer._lint_boolean_seam(value, word)
        return transformer.generic_visit(node)

    def visit_IfExp(transformer, node):
        transformer._lint_boolean_seam(
            node.test, "a conditional expression's test (`x if --g else y`)")
        return transformer.generic_visit(node)

    def visit_ClassDef(transformer, node):
        transformer._scope_depth += 1
        result = transformer.generic_visit(node)
        transformer._scope_depth -= 1
        return result

    def visit_UnaryOp(transformer, unary_op):
        if isinstance(unary_op.op, Not):
            # ``if not --g:`` / ``while not --g:`` never get here (their
            # visitors lower the whole test); any other ``not --g`` is.
            transformer._lint_boolean_seam(unary_op.operand, "a `not`")
        # ``--`` and ``~~`` must be written without a space, and for ``--``
        # that is not a nicety: ``a <- -b`` and ``a < --b`` parse to the same
        # tree, so the columns are the only thing that says which was
        # written.  ``_double_prefix_operand`` is the one place that test
        # lives -- see its docstring for the three readers that each had
        # their own copy, one of them without the test at all.
        expression = _double_prefix_operand(unary_op, USub)
        if expression is not None:
            # THE SEAM: ``--term`` yields the runtime TERM, built at
            # the point of execution in the host module's namespace
            # (clausal.logic.seam.seam_term), never a rewriter node.
            # Every logic variable of the expression is bound up
            # front, so a ``++`` thunk that names a variable first
            # written later in the same term still finds it, and an
            # inner seam (inside that ``++``) reuses the variables an
            # enclosing seam already bound rather than shadowing them.
            transformer._lint_titlecase(expression)
            term_ast, fresh = transformer._seam_term_ast(expression, unary_op)
            if fresh:
                # term position: bind the fresh variables inline
                binds = [transformer._var_bind(n, unary_op) for n in fresh]
                term_ast = replace(
                    Subscript(
                        value=replace(Tuple(elts=[*binds, term_ast], ctx=Load()), unary_op),
                        slice=replace(Constant(value=-1), unary_op),
                        ctx=Load(),
                    ),
                    unary_op,
                )
            return transformer._seam_call(term_ast, unary_op)
        expression = _double_prefix_operand(unary_op, Invert)
        if expression is not None:
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
                # The directive's arguments are Clausal (export lists,
                # ``pred/arity`` specs, ``-private([...])`` heads); its NAME
                # is not an identifier of the program, and the whole of an
                # ``-import_*`` is a module path plus names that are the
                # exporter's to spell.
                if directive_name in transformer._DECLARATION_DIRECTIVES:
                    # The keyword VALUES were linted before this branch
                    # existed and must stay linted: ``-specialize``'s
                    # ``alias=Foo`` NAMES the predicate the specialisation
                    # defines, so it is a functor position.
                    transformer._lint_titlecase_declared_names(
                        list(directive_args)
                        + [kw.value for kw in neg.operand.keywords])
                elif directive_name == "import_from":
                    transformer._lint_titlecase_alias_targets(directive_args)
                elif directive_name != "import_module":
                    transformer._lint_titlecase(
                        *directive_args,
                        *(kw.value for kw in neg.operand.keywords))
                return transformer._handle_directive(
                    directive_name, directive_args, expr_stmt
                )
            # Bare -directive at module level (no parens, no args).
            # ``-strict_atoms`` uses this form (as did the removed
            # ``-implicit_atoms``, which now raises); other
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
                and (isinstance(single_element.func, Name)
                     or (isinstance(single_element.func, Constant)
                         and isinstance(single_element.func.value, str)))
                and transformer._scope_depth == 0
            ):
                # Trailing-comma fact: ``edge(1, 2),`` — build via shared helper.
                # ``'edge'(1, 2),`` is the string-callable sugar for the same
                # name (the form a body goal already accepts); read as a
                # fact here so the lint sees it — otherwise the tuple falls
                # through as hosted Python and dies at exec with a
                # misleading ``'str' object is not callable``.
                transformer._lint_titlecase(single_element)
                func = single_element.func
                if isinstance(func, Constant):
                    # The head reads as the body form does, so it owes the
                    # same ISO 6.3.3 refusal — otherwise `"foo"(1),` would
                    # load as a fact for foo/1 while `"foo"(X)` in a body is
                    # refused, and the head would quietly change meaning
                    # when the double_quotes default flips to chars — plus
                    # the plain-name limit a head carries and a body goal
                    # does not.  Shared with the rule head below.
                    func = _quoted_head_functor_name(
                        transformer, func, "fact")
                return transformer._build_fact_statements(
                    func.id,
                    single_element.args,
                    single_element.keywords,
                    func,
                    single_element,
                    expr_stmt,
                )
            case Tuple(elts=[Name(id=functor_name) as name_node], ctx=Load()) if (
                transformer._scope_depth == 0
                and (not _is_logic_var_name(functor_name)
                     # A zero-arity fact head is a FUNCTOR position, so a
                     # TitleCase one is still refused — but it has to reach
                     # the lint to be refused, and the variable rule now
                     # accepts the spelling.  Without this arm ``Foo,`` fell
                     # through to hosted Python and died at exec with a bare
                     # ``NameError: name 'Foo' is not defined``, naming
                     # neither the convention nor the ``++`` remedy.
                     or _is_titlecase_identifier(functor_name))
            ):
                # A10-F011: zero-arity trailing-comma fact ``flag,`` — shared helper.
                transformer._lint_titlecase(name_node, root_is_functor=True)
                return transformer._build_zero_arity_fact_statements(
                    functor_name, name_node, expr_stmt,
                )
            case BinOp(left=lhs, op=RShift(), right=rhs) if (
                transformer._scope_depth == 0
            ):
                # DCG / EDCG rule: head >> (body)
                # Parse LHS for pushback: (head, [pushback]) >> (body)
                transformer._lint_titlecase(expr_stmt.value)
                pushback = None
                if isinstance(lhs, Tuple) and len(lhs.elts) == 2:
                    head_part, pb_part = lhs.elts
                    if isinstance(pb_part, List):
                        pushback = pb_part.elts
                        lhs = head_part

                # A quoted head functor reads here as it does for a fact and
                # for a ``<-`` rule — a DCG head is a head, and leaving it
                # out would make ``'Foo'(X) >> (...)`` the one head shape
                # that still dies at exec instead of naming its own fault.
                if (isinstance(lhs, Call) and isinstance(lhs.func, Constant)
                        and isinstance(lhs.func.value, str)):
                    lhs = replace(
                        Call(
                            func=_quoted_head_functor_name(
                                transformer, lhs.func, "DCG rule"),
                            args=list(lhs.args),
                            keywords=list(lhs.keywords),
                        ),
                        lhs,
                    )
                # Extract functor name and user args from the head.
                if isinstance(lhs, Call) and isinstance(lhs.func, Name):
                    functor_name = lhs.func.id
                    orig_pos_args = list(lhs.args)
                    orig_kw_args = list(lhs.keywords)
                elif isinstance(lhs, Name):
                    functor_name = lhs.id
                    orig_pos_args = []
                    orig_kw_args = []
                    # Zero-arity DCG head -- same bare-``Name`` functor
                    # position as the arrow rule above.
                    transformer._lint_titlecase(lhs, root_is_functor=True)
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
                transformer._lint_titlecase(expr_stmt.value)
                _, body_expr = arrow
                # ``'foo'(X) <- (...)``: the head functor named by a quoted
                # ATOM, the shape a fact head and a body goal both already
                # accept.  Normalise it to the bare ``Name`` the atom stands
                # for BEFORE the extraction below, so a rule head reads the
                # same as the fact head for the same predicate.  Without
                # this the statement fell through to hosted Python and died
                # at exec with ``'str' object is not callable`` — or, with
                # variables in the head, a ``NameError`` naming one of them.
                if (isinstance(left, Call) and isinstance(left.func, Constant)
                        and isinstance(left.func.value, str)):
                    left = replace(
                        Call(
                            func=_quoted_head_functor_name(
                                transformer, left.func, "clause"),
                            args=list(left.args),
                            keywords=list(left.keywords),
                        ),
                        left,
                    )
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
                    # A ZERO-ARITY head is a functor position like any other
                    # head, but it is a bare ``Name`` rather than a ``Call``,
                    # so the whole-node walk above reaches it as a term and
                    # says nothing.  Without this, ``Foo <- (...)`` LOADED and
                    # registered a predicate named ``Foo`` with no lint at
                    # all -- the one invariant this change was required to
                    # keep, escaping through the one head shape that is not a
                    # call.
                    transformer._lint_titlecase(left, root_is_functor=True)
                else:
                    return transformer.generic_visit(expr_stmt)

                _warn_cons_bar_head(orig_pos_args, orig_kw_args, expr_stmt,
                                    transformer._source_lines)
                transformer._warn_deprecated_test_spelling(
                    functor_name, len(orig_pos_args) + len(orig_kw_args),
                    expr_stmt)
                arg_field_names = _derive_field_names(orig_pos_args)
                kwarg_field_names = [kw.arg for kw in orig_kw_args]
                all_field_names = arg_field_names + kwarg_field_names

                # If the functor was already seen, remap positional arg field
                # names to the established signature by position — unless the
                # entry is a -dynamic placeholder (A12-F005): the first REAL
                # clause's derived head-var names win.
                prev_fields, opens_arity = transformer._head_fields_at(
                    functor_name, len(all_field_names),
                    has_keywords=bool(kwarg_field_names))
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
                # Note head AND body up front, so a thunk in the HEAD sees
                # the variables the BODY binds.  The auto-note in ``visit``
                # fires per outermost root, and each head argument is its own
                # root visited before the body, so without this a head thunk
                # saw only earlier arguments -- position deciding the reading,
                # which is the fault this whole mechanism removes.
                term_transformer.note_clause_scope(
                    *orig_pos_args, *(kw.value for kw in orig_kw_args),
                    body_expr)
                transformed_pos = [term_transformer.visit(a) for a in orig_pos_args]
                transformed_kw = [term_transformer.visit(kw.value) for kw in orig_kw_args]
                # Read-once lowering: dict reads (``P.key`` / ``P[key]``) become
                # explicit read goals at their first-occurrence position, scoped
                # to the innermost enclosing control construct.
                body_ast = term_transformer.visit(
                    _lower_dict_reads(
                        left, body_expr,
                        term_transformer._clause_scope_exclusions())
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
                transformer._spell_edcg_hidden_head_slots(
                    functor_name, head_args, head_keywords, anchor)
                head_ast = replace(
                    Call(
                        func=replace(Name(id=functor_name, ctx=load), anchor),
                        args=head_args,
                        keywords=head_keywords,
                    ),
                    left,
                )

                predicate_ast = node_ast(
                    "Predicate", expr_stmt.value, head=_head_ctor_ast(head_ast), body=body_ast
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
                        _make_predicate_decl_ast(functor_name, all_field_names, expr_stmt)
                    )
                elif opens_arity:
                    transformer._register_functor_arity(
                        functor_name, all_field_names, expr_stmt)
                    statements.append(
                        _make_predicate_decl_ast(functor_name, all_field_names, expr_stmt)
                    )
                statements.append(define_stmt)
                return statements if len(statements) > 1 else statements[0]
            case Starred():
                # *(goal_expr) query syntax — leave untouched for
                # _StarQueryTransformer in IPython, which applies TermTransformer
                # to the inner expression.  Returning expr_stmt unchanged prevents
                # EmbedTransformer.visit_Name (X → X.value) from mangling the
                # names that TermTransformer needs to see as plain Name nodes.
                transformer._lint_titlecase(expr_stmt.value)
                return expr_stmt
            case Call(func=Name(id="_clausal_star_query_")):
                # Sentinel form of *(…) after text-level input transformer
                # rewrites it for Python ≥ 3.14 compatibility.  Same treatment
                # as Starred(): leave untouched for _StarQueryTransformer.
                transformer._lint_titlecase(*expr_stmt.value.args)
                return expr_stmt
            case Call(func=Name(id=functor_name)) if (
                transformer._scope_depth == 0
                and transformer._is_module_compile()
            ):
                if functor_name in transformer._seen_functors:
                    # Comma-optional bodyless fact for a DECLARED predicate.
                    # (An UNDECLARED bare call below is hosted Python — an
                    # ``isinstance(...)``, a macro — and is not linted.)
                    src = expr_stmt.value
                    transformer._lint_titlecase(src)
                    return transformer._build_fact_statements(
                        functor_name, src.args, src.keywords, src.func, src,
                        expr_stmt,
                    )
                # Undeclared: guard so an undefined functor yields a comma hint.
                return transformer._guard_bare_call(functor_name, expr_stmt)
            case Name(id=functor_name) if (
                transformer._scope_depth == 0
                # The same disjunct as the trailing-comma arm above, for the
                # same reason: a comma-LESS bare statement for a name already
                # seen as a functor is a functor position, and without this
                # ``Foo`` fell through to hosted Python while ``foo`` reached
                # the arity-conflict diagnosis -- two spellings of one
                # statement disagreeing.
                and (not _is_logic_var_name(functor_name)
                     or _is_titlecase_identifier(functor_name))
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
                    transformer._lint_titlecase(expr_stmt.value,
                                                root_is_functor=True)
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
                transformer._procedure_decl_arities.setdefault(
                    functor, set()).add(arity)
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
                        _make_predicate_decl_ast(functor, field_names, expr_stmt))
            predspec = transformer._handle_predspec_directive(
                "mark_dynamic", args, expr_stmt)
            if isinstance(predspec, list):
                statements.extend(predspec)
            else:
                statements.append(predspec)
            return statements if len(statements) > 1 else statements[0]
        if name == "meta_predicate":
            heads = _parse_meta_predicate_args(args)
            transformer._module_items.append(
                DirectiveItem(name="meta_predicate", specs=heads))
            load = Load()
            statements = []
            for functor, arity, specs in heads:
                # $module.db.mark_meta_predicate("functor", arity, (spec, ...))
                call_node = replace(
                    Expr(value=Call(
                        func=Attribute(
                            value=Attribute(
                                value=Name(id="$module", ctx=load),
                                attr="db", ctx=load),
                            attr="mark_meta_predicate", ctx=load),
                        args=[Constant(value=functor), Constant(value=arity),
                              Tuple(elts=[Constant(value=v) for v in specs],
                                    ctx=load)],
                        keywords=[])),
                    expr_stmt)
                fix_missing_locations(call_node)
                statements.append(call_node)
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
            raise SyntaxError(
                "-implicit_atoms was removed; declare atoms with "
                "-private([...]) or quote them")
        if name == "allow_singletons":
            return transformer._handle_allow_singletons_directive(args, expr_stmt)
        if name == "constant_value":
            return transformer._handle_constant_value_directive(
                args, expr_stmt)
        if name == "constant_number_units":
            return transformer._handle_constant_value_directive(
                args, expr_stmt, with_units=True)
        if name == "constant_number_currency":
            return transformer._handle_constant_value_directive(
                args, expr_stmt, with_units=True, currency=True)
        if name == "constants":
            raise SyntaxError(
                "-constants(name = value, ...) is retired. Declare one "
                "constant per directive: -constant_value(pi, 3.14159), or "
                "-constant_number_units(max_fine, 5000, euro) to keep the "
                "unit out of the value. The keyword form could not have a "
                "family, and one line per constant reads better in a diff.")
        if name == "implicit_functors":
            return transformer._handle_implicit_functors_directive(args, expr_stmt)
        if name == "double_quotes":
            return transformer._handle_double_quotes_directive(args, expr_stmt)
        if name == "set_prolog_flag":
            return transformer._handle_set_prolog_flag_directive(args, expr_stmt)
        raise SyntaxError(
            f"Unknown directive: -{name}(...)  "
            f"(known directives: -module, -private, -hide, -dynamic, -discontiguous, "
            f"-table, -shallow, -import_from, -import_module, "
            f"-specialize, -edcg_acc, -edcg_pass, -edcg_pred, -translations, "
            f"-strict_atoms, -allow_singletons, "
            f"-constant_value, -constant_number_units, "
            f"-constant_number_currency, -constants_number_units, "
            f"-constants_number_currency, -implicit_functors, -double_quotes, "
            f"-set_prolog_flag)"
        )

    def _handle_double_quotes_directive(transformer, args, expr_stmt):
        """Process ``-double_quotes(atom|chars)`` — the strings-migration
        RATCHET.

        Step 2 of the strings/atom-tag program (canonical
        ``todo/strings-lost-in-the-atom-pivot-double-quotes-are-char-lists-2026-09-06.md``,
        ruling R-S4): a module that still relies on ``"..."`` denoting an
        ATOM declares ``-double_quotes(atom)`` so it keeps that meaning
        now that the engine default is ``chars`` (``"..."`` = a string
        unifying with its char list; flipped 2026-09-26, as in Scryer and
        Trealla).  ``-double_quotes(atom)`` is the opt-out.

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
        if mode in DOUBLE_QUOTES_MODES:
            transformer._double_quotes_mode = mode
            transformer._double_quotes_explicit = True
            return replace(Pass(), expr_stmt)
        raise SyntaxError(
            f"-double_quotes({mode}): unknown mode; the accepted modes are "
            f"`chars` (the engine default: \"...\" is a string — the list of "
            f"its char atoms) and `atom` (\"...\" is an atom).  Codes are "
            f"spelled b\"...\" and have no mode."
        )

    def _handle_set_prolog_flag_directive(transformer, args, expr_stmt):
        """Process ``-set_prolog_flag(Flag, Value)`` -- ISO 8.17.1 as a
        directive (``clausal.logic.builtins.flags``).

        Validated here, at load, with the runtime builtin's own checks: a
        refused setting is a ``SyntaxError`` carrying the ISO error term.
        ``double_quotes`` is the ``-double_quotes`` mode (position-sensitive,
        governing the literals below it); every other flag becomes a
        ``set_prolog_flag`` directive item that ``compiler_v2`` applies to
        this module's database (a module-scoped flag) or to the process.
        """
        from clausal.logic.builtins.flags import check_setting  # noqa: PLC0415
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415

        def _arg(node):
            if isinstance(node, Name):
                return node.id
            if isinstance(node, Constant) and isinstance(
                    node.value, (str, bool, int)):
                return node.value
            if (isinstance(node, UnaryOp) and isinstance(node.op, USub)
                    and isinstance(node.operand, Constant)
                    and type(node.operand.value) is int):
                return -node.operand.value
            raise SyntaxError(
                "-set_prolog_flag(Flag, Value): Flag and Value must be atoms "
                "or numbers, e.g. -set_prolog_flag(assert_creates_dynamic, "
                "true)")

        if len(args) != 2:
            raise SyntaxError(
                "-set_prolog_flag takes two arguments: "
                "-set_prolog_flag(Flag, Value)")
        flag, value = _arg(args[0]), _arg(args[1])
        if flag == "require_end_module":
            # end_module/1 is a Prolog module directive: the seam has none,
            # and no setting of it reaches a seam file (operator ruling
            # 2026-09-30).  A .pl file's own directive is its front end's.
            raise SyntaxError(
                f"-set_prolog_flag({flag}, {value}): require_end_module "
                f"says whether a Prolog module file must end with "
                f":- end_module(Name).; it does not apply to a seam file. "
                f"Set it process-wide with set_prolog_flag/2 as a goal, "
                f"CLAUSAL_REQUIRE_END_MODULE, or "
                f"clausal.end_module.set_require_end_module")
        try:
            name, v = check_setting(flag, value, directive=True)
        except LogicException as exc:
            from clausal.logic.exceptions import render_error_term  # noqa: PLC0415
            text = render_error_term(exc.term)
            if exc.message:
                text = f"{text}: {exc.message}"
            raise SyntaxError(
                f"-set_prolog_flag({flag}, {value}): {text}") from None
        if name == "double_quotes":
            transformer._double_quotes_mode = v
            transformer._double_quotes_explicit = True
            return replace(Pass(), expr_stmt)
        transformer._module_items.append(
            DirectiveItem(name="set_prolog_flag", specs=[(name, v)]))
        return replace(Pass(), expr_stmt)

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
        transformer._procedure_decl_arities.setdefault(functor, set()).add(
            arity)
        if functor not in transformer._seen_functors:
            field_names = [f"arg_{i}" for i in range(arity)]
            transformer._register_functor(
                functor, field_names, entry_node, source_label)
            transformer._directive_minted_functors.add(functor)
            statements.append(
                _make_predicate_decl_ast(functor, field_names, expr_stmt)
            )
        # The entry's own location rides on the item, so a load-time lint
        # about the entry (compiler_v2's export-arity check) can point at it.
        item = DirectiveItem(name="predicate_export", specs=[(functor, arity)])
        if getattr(entry_node, "lineno", None) is not None:
            item.position = (entry_node.lineno, entry_node.col_offset,
                             entry_node.end_lineno, entry_node.end_col_offset)
        transformer._module_items.append(item)

    def _handle_module_directive(transformer, args, expr_stmt):
        """Process ``-module(Name, [export1(A,B), export2(X,Y)])`` directive.

        Extracts predicate signatures from the export list and emits
        ``_make_predicate_decl_ast`` declarations for each, pre-registering
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
        late_before: dict[str, set[int]] = {}  # see _refuse_late_fielded
        late_nodes: dict = {}
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
                        _resolved_export_spec(transformer, _pred_export),
                        export, expr_stmt, statements,
                        "-module export list (name/arity)")
                    continue
                if isinstance(export, Name):
                    # Bare atom: global by spelling (§1b/R2) — no class is
                    # minted any more (no ``_register_functor``/
                    # ``_make_predicate_decl_ast`` statement).  Record the
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
                    # NOT emitted for a name this file has already declared
                    # with ``-constant_value``: the assignment would bind the
                    # atom over the constant's module global, which is what
                    # ``++name`` reads. In the other declaration order the
                    # constant's own assignment runs later and overwrites
                    # this one, so the constant wins the global either way --
                    # and a DECLARED atom compiles to its cell literal, so it
                    # never needed the binding.
                    transformer._atoms.add(export.id)
                    exports_info.append(export.id)
                    if export.id not in transformer._constants:
                        statements.append(
                            _make_atom_str_assign_ast(export.id, expr_stmt)
                        )
                elif isinstance(export, Call) and isinstance(
                        export.func, (Name, Constant)):
                    # ``'foo'(A, B)`` is the same entry as ``foo(A, B)`` --
                    # an atom names the functor -- and for a capital-initial
                    # predicate it is the only spelling, bare ``Foo`` there
                    # being a logic variable.  Read only as a ``Name``, the
                    # quoted entry fell through to "other item shapes" and
                    # registered NOTHING: no class, no signature, and so no
                    # arity check either, while the file still loaded.
                    if isinstance(export.func, Constant):
                        export = replace(
                            Call(
                                func=_quoted_head_functor_name(
                                    transformer, export.func, None),
                                args=list(export.args),
                                keywords=list(export.keywords),
                            ),
                            export,
                        )
                    functor_name = export.func.id
                    # Use raw Name ids as field names (not lowercased) so they
                    # match keyword arg names in clauses like fib(N=0, F=0).
                    field_names = [
                        arg.id if isinstance(arg, Name) else f"arg_{i}"
                        for i, arg in enumerate(export.args)
                    ]
                    field_names += [kw.arg for kw in export.keywords]
                    transformer._late_fielded_arities_before(
                        functor_name, late_before)
                    late_nodes.setdefault(functor_name, export)
                    exports_info.append((functor_name, field_names))
                    signature_entries.append((functor_name, field_names))
                    transformer._declare_fielded_entry(
                        functor_name, field_names, export,
                        "-module export list", statements, expr_stmt)
                # Other item shapes are not pre-registered here — the
                # signature is taken from the first clause — but the list
                # itself is well-formed.  (The ISO ``foo/2`` arity form IS
                # handled, above: R6b, a PREDICATE export.)
        transformer._refuse_late_fielded(
            late_before, late_nodes, "-module export entry")
        transformer._module_items.append(
            ModuleDeclItem(module_name=module_name, exports=exports_info)
        )
        sig_stmt = _make_functor_signatures_update_ast(
            transformer._per_arity_signature_entries(signature_entries),
            expr_stmt)
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
        signature_entries = []  # (name, fields) pairs -- see _make_functor_signatures_update_ast
        late_before: dict[str, set[int]] = {}  # see _refuse_late_fielded
        late_nodes: dict = {}
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
                    _resolved_export_spec(transformer, _pred_export),
                    item, expr_stmt, statements,
                    "-private declaration (name/arity)")
                continue
            if isinstance(item, Name):
                # Bare atom: global by spelling (§1b/R2) — no class minted;
                # a guarded assignment runs at this position instead (mid-
                # file exec-time consumers, e.g. a dict-literal atom key);
                # see the matching comment in ``_handle_module_directive``.
                transformer._atoms.add(item.id)
                private_info.append(item.id)
                # Skipped for a name already declared with -constant_value;
                # see the matching guard in ``_handle_module_directive``.
                if item.id not in transformer._constants:
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
                transformer._late_fielded_arities_before(
                    functor_name, late_before)
                late_nodes.setdefault(functor_name, item)
                private_info.append((functor_name, field_names))
                signature_entries.append((functor_name, field_names))
                transformer._declare_fielded_entry(
                    functor_name, field_names, item,
                    "-private declaration", statements, expr_stmt)
            # Other item shapes are not pre-registered here; the list itself
            # is still well-formed.  (The ISO ``foo/2`` arity form IS handled,
            # above: R6b, a PREDICATE entry.)
        transformer._refuse_late_fielded(
            late_before, late_nodes, "-private entry")
        transformer._module_items.append(
            PrivateDeclItem(items=private_info))
        sig_stmt = _make_functor_signatures_update_ast(
            transformer._per_arity_signature_entries(signature_entries),
            expr_stmt)
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
          reference is governed by the strict-atoms rule
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

    def _handle_constant_value_directive(transformer, args, expr_stmt,
                                         with_units=False, currency=False):
        """Process ``-constant_value(pi, 3.14159)`` and
        ``-constant_number_units(max_fine, 5000, euro)``.

        One constant per directive, positionally, so the two forms are a
        FAMILY -- which the old keyword form could not be, and which reads
        one line per constant in a diff.

        Each lowers to ``<name> = $check_constant_ground('<name>', <rhs>)``
        at module level, so the value is bound (and gated for groundness)
        before any clause statement executes, followed by a
        ``$register_module_constant`` call backing ``constant_value/2``.
        The units form wraps the value in ``$Quantity(<value>, <units>)``,
        so the module global holds ``Quantity(5000, euro)`` -- the same
        object the ``5000 (euro)`` annotation sugar builds.

        The name is spelled like an atom and the value is reached with the
        explicit ``++name`` escape. A bare ``pi`` in term position is the
        ATOM ``("pi",)``, never the value, so one name carries both readings
        without conflict; see ``visit_Name`` and
        ``compiler_v2._process_declarations``.

        Interactive sessions (IPython/REPL) reject this directive outright:
        each cell gets a fresh transformer, so ``_constants`` is forgotten
        between cells. Half-working (bind in the declaring cell, forget it in
        the next) is worse than a clear refusal, so this is checked before
        any of the usual validation.
        """
        spelling = ("-constant_number_currency" if currency else
                    "-constant_number_units" if with_units else "-constant_value")
        arity = 3 if with_units else 2
        example = ("-constant_number_currency(max_fine, 5000, euro)" if currency
                   else "-constant_number_units(max_fine, 5000, euro)" if with_units
                   else "-constant_value(pi, 3.14159)")
        if transformer._interactive:
            raise SyntaxError(
                f"{spelling} is not supported interactively yet; declare "
                f"constants in a .clausal module and import it")
        if len(args) != arity:
            raise SyntaxError(
                f"{spelling} takes {arity} arguments, a name then a value"
                + (" then a unit expression" if with_units else "")
                + f": {example}")
        name_node = args[0]
        if not isinstance(name_node, Name):
            raise SyntaxError(
                f"{spelling}: the first argument names the constant and must "
                f"be a bare name: {example}; got `{unparse(name_node)}`")
        ident = name_node.id
        if _is_retired_constant_spelling(ident):
            new = ident.strip("_").lower()
            raise SyntaxError(
                f"{spelling}: `{ident}` uses the retired constant spelling; "
                f"constants are lowercase names now, and the value is "
                f"reached with the ++ escape. Write "
                f"`{spelling}({new}, ...)` and `++{new}` at every use site.")
        if not _is_constant_declaration_name(ident):
            raise SyntaxError(
                f"{spelling}: {ident!r} is not a constant name — a constant "
                f"is spelled like an atom, which is to say anything the "
                f"logic-variable rule does not claim: not underscore-led and "
                f"not capital-initial. e.g. {example}")
        if ident in transformer._constants:
            raise SyntaxError(
                f"{spelling}: `{ident}` is already bound (an earlier "
                f"constant declaration or an import)")
        if ident.endswith("_UNUSED"):
            # Decided edge (todo/done/module-level-constants-open-
            # questions.md #3): legal, but visually collides with the
            # singleton-suppression suffix.
            import warnings  # noqa: PLC0415
            warnings.warn(
                f"{spelling}: `{ident}` ends in _UNUSED, which reads as the "
                f"unused-variable marker; consider another name",
                ClausalLintWarning, stacklevel=2)
        value_node = args[1]
        if (not with_units and _name_claims_a_scale(ident)
                and _is_bare_number(value_node)
                and ident not in transformer._scale_name_seen):
            # The declaration half of the scale-in-a-name lint. A directive is
            # not a clause, so `_lint_scale_in_name`'s walk never reaches it --
            # and this is the form a constants migration produces most, where
            # `-constant_value` takes no unit and the scale in the NAME is the
            # only record there is. See ClausalScaleInNameWarning.
            transformer._scale_name_seen.add(ident)
            import warnings  # noqa: PLC0415
            warnings.warn(
                f"{spelling}: `{ident}` names a scale but is declared without "
                f"one — the scale exists only in the identifier, where nothing "
                f"can check it. Use -constant_number_currency(name, number, "
                f"<currency or minor unit>) so the unit is a fact the engine "
                f"holds.",
                ClausalScaleInNameWarning, stacklevel=2)
        if with_units and _is_certainly_not_a_number(value_node):
            # The directive is NAMED for this claim -- only numbers carry
            # units -- so it enforces it rather than letting the units layer
            # raise. Without this the message is a raw `InvalidOperation:
            # ConversionSyntax` or a TypeError about Decimal coercion, neither
            # of which names the directive or the offending value.
            #
            # Only the DECIDABLE cases are refused here. A `++` escape's value
            # is not known until the module runs, so that one still reaches the
            # units layer.
            raise SyntaxError(
                f"{spelling}: `{unparse(value_node)}` is not a number, and "
                f"only numbers carry units. Use -constant_value for a value "
                f"that is not a quantity.")
        _declared_decimal = _decimal_string(value_node) if with_units else None
        if _declared_decimal is not None:
            # ONLY under `with_units`. `-constant_value(greeting, "hi")` is a
            # string constant and stays one; it is the directives NAMED for
            # carrying a unit that read a decimal string as the number.
            #
            # Built INSTEAD of running `_transform_constant_rhs`, not before
            # it: that validator checks the functors a user wrote, and would
            # refuse `$decimal_value` as undeclared. Engine-emitted helpers go
            # in after it -- the same order `$check_currency_unit` uses below.
            rhs = _decimal_value_call(value_node, _declared_decimal)
        else:
            rhs = transformer._transform_constant_rhs(value_node, ident)
        if with_units:
            unit_node = args[2]
            if currency and not isinstance(unit_node, (Name, Attribute)):
                # Money is an AMOUNT. `usd / second` is a perfectly good unit
                # expression and belongs to the general directive; allowing it
                # here would make the name a lie.
                raise SyntaxError(
                    f"{spelling}: `{unparse(unit_node)}` is not a single "
                    f"currency. This directive declares an amount of money, "
                    f"so its third argument names one currency; use "
                    f"-constant_number_units for a compound unit such as a "
                    f"rate.")
            if not _is_unit_expr(unit_node):
                raise SyntaxError(
                    f"{spelling}: `{unparse(unit_node)}` is not a unit "
                    f"expression — a unit is a name, or names combined with "
                    f"`*`, `/` and `**`: {example}")
            gated = unit_node
            if currency:
                gated = replace(
                    Call(func=replace(Name(id="$check_currency_unit", ctx=load),
                                      value_node),
                         args=[replace(Constant(value=ident), value_node),
                               unit_node,
                               replace(Constant(value=spelling), value_node)],
                         keywords=[]),
                    value_node)
            rhs = replace(
                Call(func=replace(Name(id="$Quantity", ctx=load), value_node),
                     args=[rhs, gated], keywords=[]),
                value_node)
        transformer._constants.add(ident)
        statements = []
        assign = replace(
            Assign(
                targets=[replace(Name(id=ident, ctx=store), value_node)],
                value=replace(
                    Call(
                        func=replace(
                            Name(id="$check_constant_ground", ctx=load),
                            value_node),
                        args=[replace(Constant(value=ident), value_node), rhs],
                        keywords=[],
                    ), value_node),
            ), expr_stmt)
        fix_missing_locations(assign)
        statements.append(assign)
        # Record (name, value) on $module for constant_value/2 reflection.
        # $module is ALREADY BOUND here but is a THROWAWAY placeholder
        # Module; _run_v2_pipeline carries the registrations across the swap
        # (``logic_module.constants.update(dummy_logic_module.constants)``)
        # precisely because they land here first.
        register = replace(
            Expr(value=replace(
                Call(
                    func=replace(
                        Name(id="$register_module_constant", ctx=load),
                        value_node),
                    args=[replace(Name(id="$module", ctx=load), value_node),
                          replace(Constant(value=ident), value_node),
                          replace(Name(id=ident, ctx=load), value_node)],
                    keywords=[],
                ), value_node),
            ), expr_stmt)
        fix_missing_locations(register)
        statements.append(register)
        # Record what the DECLARATION said, for constant_number_units/3.
        # Lowered here, at compile time, because it is not recoverable from
        # the value -- see _units_ast_to_term.
        if with_units:
            units_term = _units_ast_to_term(args[2])
            if units_term is not None:
                declared = replace(
                    Expr(value=replace(
                        Call(
                            func=replace(
                                Name(id="$register_constant_units", ctx=load),
                                value_node),
                            args=[
                                replace(Name(id="$module", ctx=load), value_node),
                                replace(Constant(value=ident), value_node),
                                _declared_magnitude_node(args[1], value_node),
                                replace(Constant(value=units_term), value_node),
                                # The VALUE, so the declared magnitude can be
                                # recorded in the same numeric kind the value
                                # uses -- see register_constant_units. The
                                # module global is already assigned above.
                                replace(Name(id=ident, ctx=load), value_node),
                            ],
                            keywords=[],
                        ), value_node),
                    ), expr_stmt)
                fix_missing_locations(declared)
                statements.append(declared)
        return statements


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
            # ``-constant_value(b, true)`` raised "neither a previously
            # declared constant nor a declared atom" while the equivalent
            # ``-constant_value(b, True)`` (and a dict KEY spelled ``true``,
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
            # ++expr: raw Python, load-time eval.  Declared-earlier
            # constants are legal here — by exec time they are already-bound
            # module globals.  Legal as a structured RHS's ELEMENT too (this
            # branch is reached the same way whether ``node`` is the whole
            # RHS or an element/key/value/arg a container branch recursed
            # into).  There is no undeclared-reference scan: see
            # ``_build_py_thunk_ast`` for why a constant name can no longer
            # be recognised by shape.  An undeclared one is a NameError from
            # the module-level exec, which is still load time.
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
                    func=replace(Name(id="$SetTerm", ctx=load), node),
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
                    func=replace(Name(id="$DictTerm", ctx=load), node),
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
        # The EFFECTIVE reading, mirroring the twin in ``_visit_dict_key``
        # -- which moved to it and left this copy behind.  ``Undefined`` is
        # capital-initial now, so the lexical rule called it a variable, this
        # branch was skipped, and ``-constant_value(d, {undefined: 1})`` was
        # refused with "``Undefined`` is a logic-variable name".  The alias
        # fold just above rewrites a lowercase ``undefined`` key to
        # ``Name("Undefined")`` first, so BOTH spellings were affected --
        # including the one this method's docstring promises to handle.
        if (isinstance(key, Name) and key.id != "_"
                and not (_is_logic_var_name(key.id)
                         and key.id not in _clause_scope_exclusions(
                             transformer._import_remap))
                and key.id not in transformer._constants):
            transformer._bare_atom_refs.add(key.id)
            return replace(
                Call(
                    func=replace(Name(id="$intern_atom", ctx=load), key),
                    args=[replace(Constant(value=key.id), key)],
                    keywords=[],
                ), key)
        # The NIL key (fix round 3, item 2), mirroring the clause-literal
        # path in ``_visit_dict_key``: ``'[]'`` is the reserved atom ``'[]'``,
        # which IS the empty list, and the canonical KEY form of that term is
        # the hashable empty TUPLE (``atoms.NIL_KEY``).  Without this a
        # structured ``-constants`` RHS built a plain ``str`` key ``"[]"``
        # (a different key from the one every other path produces) and a bare
        # ``{[]: 1}`` raised a raw ``TypeError`` -- a list cannot key a dict.
        # The quote test guards ONE spelling: a double-quoted ``"[]"`` in
        # ``chars`` mode is the two-character STRING and keeps its own
        # meaning, exactly as ``visit_Constant`` decides it.  It says nothing
        # about the EMPTY string (fix round 5, item 2): ``{"": 1}`` does not
        # reach either branch above -- it falls to the ``$dict_key`` wrap
        # below and folds to ``()`` at exec time like every other nil
        # spelling, while a source-written ``{"": 1}`` in a CLAUSE compiles
        # to the atom ``("",)``.  That divergence is the open design question
        # in todo/source-empty-string-dict-key-is-an-atom-not-nil-2026-09-07.md
        # (ISO has an empty-spelling atom `''` distinct from `[]`, so both
        # readings are defensible); it needs the operator ruling `'[]'` got,
        # and is not decided here.
        if isinstance(key, List) and not key.elts:
            return replace(Tuple(elts=[], ctx=load), key)
        if isinstance(key, Constant) and key.value == NIL_SPELLING:
            quote = _quote_of_positioned(transformer, key)
            if not (quote == '"'
                    and transformer._double_quotes_mode == "chars"):
                return replace(Tuple(elts=[], ctx=load), key)
        # Everything left is a key whose VALUE is only known at exec time --
        # in practice a reference to an earlier constant, possibly under
        # arithmetic or a ``++`` escape.  It cannot be folded statically, and
        # a ``-constants`` list value is FROZEN, so
        # ``-constant_value(n, [])`` + ``-constant_value(d, {n: 1})`` handed the plain dict
        # literal an unhashable ``_FrozenList`` and raised a raw, unlocated
        # ``TypeError`` at load -- before ``DictTerm`` (which folds every nil
        # spelling) ever saw the key.  Fold at exec time instead, through
        # ``$dict_key`` (``runtime.dict_ops._dict_key``) -- the SAME helper a
        # clause body's computed ``{K: V}`` key is wrapped in, whose answer
        # is ``atoms.as_dict_key``'s -- so a constant reference that
        # evaluates to nil is the SAME key as the literal spellings above
        # (Task 15 fix round 4, item 4).  Load-time code, run once: the extra
        # call costs nothing measurable, and a non-nil key passes straight
        # through it.
        return replace(
            Call(
                func=replace(Name(id="$dict_key", ctx=load), key),
                args=[transformer._transform_constant_rhs(key, ident)],
                keywords=[],
            ), key)

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

    def _warn_deprecated_unit_spelling(transformer, renames, node):
        """Lint the old unit spellings of one ``-import_from(py.units, …)``.

        The counterpart of ``_warn_deprecated_test_spelling`` for the units
        module: ``metre`` is the spelling, ``Metre`` the old one.  A file
        imports its units in one list, so this fires ONCE per file for that
        list — naming every rename in it — rather than once per use site.
        A name already warned about in this file is not repeated.  Message
        shape follows ``EmbedTransformer._site``.
        """
        fresh = [(old, new) for old, new in renames
                 if old not in transformer._warned_unit_spellings]
        if not fresh:
            return
        transformer._warned_unit_spellings.update(old for old, _ in fresh)
        import warnings  # noqa: PLC0415
        lineno = getattr(node, "lineno", None)
        if transformer._filename:
            where = f"{transformer._filename}:{lineno or '?'}"
        else:
            where = f"line {lineno}" if lineno else "unknown site"
        snippet = ""
        lines = transformer._source_lines
        if lines and lineno and 1 <= lineno <= len(lines):
            snippet = " — " + lines[lineno - 1].strip()
        listed = ", ".join(f"`{old}` -> `{new}`" for old, new in fresh)
        noun = "spellings" if len(fresh) > 1 else "spelling"
        warnings.warn(
            f"{where}{snippet}: old unit {noun} in this import. Rename "
            f"{listed}; the old spelling still works but will be removed in "
            f"a future release",
            ClausalDeprecatedSpellingWarning,
            stacklevel=2,
        )

    def _handle_import_from_directive(transformer, args, expr_stmt):
        """Process ``-import_from(dotted.module, [Pred1, alias(Pred2, Local)])`` directive.

        A deprecated TitleCase unit name in a units import (``metre``) is
        imported as its lowercase unit under the old local name (``from
        py.units import metre as Metre``) and linted once per file, so the
        file keeps working while the load names the rename.

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
        unit_renames = _deprecated_unit_renames(module_path)
        renamed_units: list[tuple[str, str]] = []
        aliases = []
        # D20 (2026-09-29): ``name/N`` (or ``name//N``, a DCG nonterminal,
        # N + 2) imports ONE arity, as Scryer's ``use_module(m, [p/1])``.
        # ``arities`` maps each LOCAL name to the arities its entries
        # selected, or ``None`` once any entry for it is a bare name (which
        # brings every arity).  ``bound`` maps a local name to the alias
        # entry already emitted for it, so an entry that repeats one
        # (``[g/1, g/2]``, ``[baz, baz]``) is ONE Python import.
        arities: dict[str, "set[int] | None"] = {}
        bound: dict[str, str] = {}
        for item in args[1].elts:
            arity = None
            if _import_indicator(item) is not None:
                name_id, arity = _import_indicator(item)
                item = copy_location(Name(id=name_id, ctx=Load()), item)
            elif (isinstance(item, Call) and isinstance(item.func, Name)
                  and item.func.id == "alias" and len(item.args) == 2
                  and _import_indicator(item.args[0]) is not None):
                name_id, arity = _import_indicator(item.args[0])
                item = copy_location(Call(
                    func=item.func,
                    args=[copy_location(Name(id=name_id, ctx=Load()),
                                        item.args[0]), item.args[1]],
                    keywords=[]), item)
            n_before = len(aliases)
            if isinstance(item, Name):
                # Map local name → "module.path.Name" for dotted globals key
                local_name = item.id
                # An import binds the local name as a module global, so a
                # name this file already declared as a constant would be
                # silently overwritten by it -- the same shape the
                # constant/atom collision check refuses, one directive over.
                if local_name in transformer._constants:
                    raise SyntaxError(
                        f"-import_from: `{local_name}` is already bound by "
                        f"an earlier -constants in this file; the import "
                        f"would overwrite the constant. Import it under "
                        f"another name: alias({{local_name}}, other_name)")
                # There is no imported-constant branch here (2026-09-11).  A
                # constant name is atom-shaped now, so the importer cannot
                # tell a constant from an atom or a predicate in the owner
                # module -- that is the OWNER's fact and the name no longer
                # carries it.  Every imported name takes the ordinary path
                # below, whose ImportFrom binds the owner's module global,
                # which is all ``++name`` needs to reach a constant.  The
                # cost: importing a constant and then CALLING it fails at
                # solve time rather than at load time, exactly as it already
                # did for an imported atom.
                # Same unreachability as the ``alias(…)`` form below: a
                # var-shaped local binding is read as a logic variable by
                # ``visit_Name`` before the remap is ever consulted, so the
                # import can never be called.  Unlike a var-shaped *local*
                # clause head (which at least works head-only — see
                # ``_check_var_shaped_predicate_names``), an imported name
                # exists only to be called, so there is nothing to preserve.
                #
                # TitleCase is exempt: ``visit_Name`` consults the remap
                # BEFORE the variable rule for a TitleCase name (see the
                # carve-out there), so an imported ``Metre`` IS reachable and
                # the unreachability this guard exists to prevent does not
                # arise.  Without the exemption the deprecated-unit-spelling
                # path below became unreachable itself and every
                # ``-import_from(py.units, [Metre])`` in the wild turned into
                # a load error overnight.
                if (_is_logic_var_name(local_name)
                        and not _is_titlecase_identifier(local_name)):
                    raise SyntaxError(
                        f"-import_from name {local_name!r} is a logic-variable "
                        f"name; a call to it is read as a variable, never as "
                        f"{module_path}.{local_name}. Import it under a "
                        f"non-variable alias: "
                        f"alias({local_name}, "
                        f"{_suggest_non_var_name(local_name)})"
                    )
                unit_name = unit_renames.get(local_name)
                if unit_name is not None:
                    renamed_units.append((local_name, unit_name))
                    dotted_key = f"{module_path}.{unit_name}"
                    transformer._import_remap[local_name] = dotted_key
                    transformer._imported_functors.add(local_name)
                    aliases.append(alias(name=unit_name, asname=local_name))
                    continue
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
                # An import binds the local name as a module global, so a
                # name this file already declared as a constant would be
                # silently overwritten by it -- the same shape the
                # constant/atom collision check refuses, one directive over.
                if local_name in transformer._constants:
                    raise SyntaxError(
                        f"-import_from: `{local_name}` is already bound by "
                        f"an earlier -constants in this file; the import "
                        f"would overwrite the constant. Import it under "
                        f"another name: alias({{orig_name}}, other_name)")
                # No constant-alias branch either -- see the bare-name form
                # above.  ``alias(max_fine, cap)`` is an ordinary rename now,
                # and the shape-matching rule it used to enforce ("a constant
                # must alias to a constant") has nothing left to match on.
                # A10-F017: a logic-var-shaped alias (e.g. ``T``) is
                # unreachable — visit_Name treats it as a variable before the
                # remap fires, so the call site later fails with a cryptic
                # NotImplementedError. Reject it here at the directive.
                # TitleCase is exempt here for the same reason as the
                # bare-name form above (visit_Name consults the remap first
                # for it); a TitleCase LOCAL name is refused by the TitleCase
                # lint before this point (``_lint_titlecase_alias_targets``).
                if (_is_logic_var_name(local_name)
                        and not _is_titlecase_identifier(local_name)):
                    raise SyntaxError(
                        f"-import_from alias {local_name!r} is a logic-variable "
                        f"name; use a non-variable alias: "
                        f"alias({orig_name}, "
                        f"{_suggest_non_var_name(local_name)})"
                    )
                unit_name = unit_renames.get(orig_name)
                if unit_name is not None:
                    renamed_units.append((orig_name, unit_name))
                    orig_name = unit_name
                dotted_key = f"{module_path}.{orig_name}"
                transformer._import_remap[local_name] = dotted_key
                # The ALIAS is what this file binds; the original spelling
                # stays free for a purely local declaration.
                transformer._imported_functors.add(local_name)
                aliases.append(alias(name=orig_name, asname=local_name))
            else:
                raise SyntaxError(
                    f"-import_from: import list items must be names, "
                    f"indicators name/N, or alias(OrigName, LocalName), got "
                    f"{dump(item)}"
                )
            if len(aliases) == n_before:
                continue
            entry = aliases[-1]
            local = entry.asname or entry.name
            if local in bound and bound[local] != entry.name:
                # F3: ONE local name for two different predicates.  Python's
                # ``from m import f as x, g as x`` would keep the last one
                # silently; say which two collide instead.
                raise SyntaxError(
                    f"-import_from({module_path}, [...]): the local name "
                    f"`{local}` is bound twice, to {module_path}'s "
                    f"`{bound[local]}` and to its `{entry.name}`. One name "
                    f"names one predicate here: give one of them another "
                    f"local name with alias({entry.name}, other_name)")
            if local in bound:
                del aliases[-1]              # the same import, once
            else:
                bound[local] = entry.name
            if arity is None or (local in arities and arities[local] is None):
                arities[local] = None
            else:
                arities.setdefault(local, set()).add(arity)
        # One predicate under SEVERAL local names shares one remapped
        # reference (``module.orig``), which cannot record which spelling a
        # call used (review round 5's residual).  With the same arities for
        # every spelling that is harmless; with DIFFERENT ones
        # (``[g/1, alias(g/2, gg)]``, across directives too) a call would
        # reach the wrong spelling's arities, so it is refused (D20).
        spellings = transformer.__dict__.setdefault("_import_spellings", {})
        for a in aliases:
            local = a.asname or a.name
            per_orig = spellings.setdefault((module_path, a.name), {})
            found = arities.get(local)
            per_orig[local] = (None if found is None or per_orig.get(
                local, ()) is None else frozenset(per_orig.get(local, ()))
                | frozenset(found))
            if len(set(per_orig.values())) > 1:
                shown = ", ".join(
                    f"`{name}` ("
                    + ("every arity" if sel is None else ", ".join(
                        f"{a.name}/{n}" for n in sorted(sel))) + ")"
                    for name, sel in per_orig.items())
                raise SyntaxError(
                    f"-import_from({module_path}, [...]): {module_path}'s "
                    f"`{a.name}` is imported under several names at "
                    f"different arities: {shown}. The names share one "
                    f"reference, so a call could not tell them apart; import "
                    f"`{a.name}` under one name, or at the same arities "
                    f"under each")
        if renamed_units:
            transformer._warn_deprecated_unit_spelling(renamed_units, expr_stmt)
        # Accumulate import info for pipeline-split ModuleAST.
        import_names = []
        for a in aliases:
            if a.asname:
                import_names.append((a.name, a.asname))
            else:
                import_names.append(a.name)
        transformer._module_items.append(
            ImportFromItem(
                module=module_path, names=import_names,
                arities={local: frozenset(found)
                         for local, found in arities.items()
                         if found is not None},
                line=getattr(expr_stmt, "lineno", 0) or 0)
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
        # Ruling 2026-09-30: against a .pl module, a bare name the module
        # neither defines as a predicate nor binds is DATA, and resolves to
        # its atom (clausal/pl_data_imports.py).  A ``name/N`` entry names a
        # predicate, so only the bare-name locals are eligible.  A SEAM
        # importer only: a .pl importer (either front end; the native one's
        # import bookkeeping, ``iso_l3_directives.imported``, reads this
        # statement as an ``ast.ImportFrom``) keeps the plain import.
        if not transformer._prolog_singletons:
            stmt = _wrap_import_for_pl_data(
                stmt, resolved,
                {a.asname or a.name: a.name for a in aliases},
                sorted(local for local, found in arities.items()
                       if found is None),
                expr_stmt)
        # Copy the imported names' functor-signature registry entries into
        # this file's own registry, keyed by the LOCAL spelling (mirroring
        # Python's own ``from X import a, b as a`` shadowing rule: the
        # constant branches above also land here, harmlessly -- a name with
        # no registry entry in the owner is silently skipped, see
        # ``_make_import_signatures_update_ast``).
        name_pairs = [(a.asname or a.name, a.name) for a in aliases]
        sig_stmt = _make_import_signatures_update_ast(resolved, name_pairs, expr_stmt)
        # The body-time record (``$import_arities``) is emitted from the
        # first directive with a ``name/N`` entry on, and then carries EVERY
        # bare local seen in the file so far as "every arity" too: the
        # record merges per handle, and a bare import of a handle must
        # widen a selection made for it elsewhere (roborev, 2026-09-29).
        bare_seen = transformer.__dict__.setdefault("_import_bare_locals", [])
        bare_seen.extend(local for local, found in arities.items()
                         if found is None)
        if any(found is not None for found in arities.values()):
            transformer._import_selected_seen = True
        record = {}
        if getattr(transformer, "_import_selected_seen", False):
            record = {local: None for local in bare_seen}
            record.update({local: found for local, found in arities.items()
                           if found is not None})
        arities_stmt = _make_import_arities_record_ast(record, expr_stmt)
        out = [s for s in (stmt, sig_stmt, arities_stmt) if s is not None]
        return out[0] if len(out) == 1 else out

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
        transformer._import_module_bases.add(module_path)
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
                # The directive's source line: the specialized predicate's
                # declaration site (W4b-3 slice 4 -- the make_predicate class
                # used to carry one as ``_registered_at``).
                position=(expr_stmt.lineno, expr_stmt.col_offset,
                          getattr(expr_stmt, "end_lineno", expr_stmt.lineno),
                          getattr(expr_stmt, "end_col_offset", 0)),
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
        transformer._refuse_late_fielded_declaration(
            pred_name, [None] * visible_arity, expr_stmt, "-edcg_pred")
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
            return _make_predicate_decl_ast(pred_name, field_names, expr_stmt)
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

        # A12-F005: a -dynamic placeholder must not clobber derived names
        # (``_head_fields_at`` unseats it).  ``state//1`` beside
        # ``state//2`` is ``state/3`` beside ``state/4``: each opens its own
        # arity (operator ruling 2026-09-29).
        prev_fields, opens_arity = transformer._head_fields_at(
            functor_name, len(all_field_names),
            has_keywords=bool(kwarg_field_names))
        if prev_fields is not None:
            for i in range(len(arg_field_names)):
                if i < len(prev_fields):
                    arg_field_names[i] = prev_fields[i]
            all_field_names = arg_field_names + kwarg_field_names
            if (len(set(all_field_names)) != len(all_field_names)
                    or len(all_field_names) != len(prev_fields)):
                # A DECLARED name at another arity (a SHORTER head used to
                # slip past the duplicate test and die building the head at
                # load): ``state//1`` then
                # ``state//2`` remaps the second head's surplus onto
                # ``dcg1`` twice.  Refuse it here, naming both rules, as an
                # arrow rule's head is.
                transformer._check_head_signature(
                    functor_name, all_field_names, prev_fields, expr_stmt,
                    has_keywords=bool(kwarg_field_names), dcg=True)

        # Ensure all synthetic AST nodes have source positions.
        copy_location(body_expr_raw, src)
        fix_missing_locations(body_expr_raw)

        # Non-terminal call targets in the rewritten body must be
        # treated as predicate references (LoadName), not as atom
        # string constants.  Exclude them from the atom set.
        dcg_call_names = _collect_call_func_names(body_expr_raw)
        dcg_atoms = transformer._atoms - dcg_call_names
        term_transformer = transformer._make_term_transformer(atoms=dcg_atoms)
        # Head AND body up front -- see the arrow rule for why.
        term_transformer.note_clause_scope(
            *orig_pos_args, *(kw.value for kw in orig_kw_args), body_expr_raw)
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
            "Predicate", src, head=_head_ctor_ast(head_ast), body=body_ast
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
                _make_predicate_decl_ast(
                    functor_name, all_field_names, expr_stmt
                )
            )
        elif opens_arity:
            transformer._register_functor_arity(
                functor_name, all_field_names, expr_stmt)
            statements.append(
                _make_predicate_decl_ast(
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
            return isinstance(_double_prefix_operand(ctx, op_type), Dict)

        if _is_double(USub):
            # with --{} as target: — block form of --; produces simple_ast terms.
            transformer._lint_titlecase(
                *(stmt.value for stmt in with_statement.body
                  if isinstance(stmt, Expr)))
            term_transformer = transformer._make_term_transformer()
            roots = [stmt.value for stmt in with_statement.body
                     if isinstance(stmt, Expr)]
            # Every statement in the block is one outermost root sharing ONE
            # variable scope, so note them all before visiting any -- see the
            # arrow rule for why.  The auto-note in ``visit`` accumulates per
            # root, which made the reading of a thunk depend on where in the
            # block it was written: ``f"{Node}"`` before ``tree(Node)``
            # formatted the module-namespace class, and the reverse order the
            # binding, with nothing to say the two blocks differed.
            term_transformer.note_clause_scope(*roots)
            elements = [term_transformer.visit(root) for root in roots]
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
