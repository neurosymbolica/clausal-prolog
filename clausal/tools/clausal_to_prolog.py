"""Clausal → Prolog translation (Phase 1.2).

Pipeline: .clausal source → Python AST → Prolog AST → .pl text

Public API:
    emit_term(pterm, op_table)          — Prolog AST term → text
    emit_item(pitem, op_table)          — Prolog AST clause/directive → text
    emit_module(pmodule, op_table)      — full PModule → text
    clausal_source_to_prolog_ast(src)   — .clausal source → PModule
    clausal_source_to_prolog(src, ...)  — .clausal source → .pl text
"""

from __future__ import annotations

import ast as python_ast
import keyword as _keyword_module
import posixpath
import re
from typing import Iterator

from clausal.templating.quote_map import build_quote_map, quote_of
from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PComment, PModule,
    PTerm, PItem, PrologVisitor, PrologTransformer, subterms,
)
from clausal.tools.prolog_operators import OperatorTable
# The engine's canonical `<-` detection primitives. The lambda arrow `<-` and
# the arithmetic comparison `< -` parse to an IDENTICAL AST
# (Compare(Lt, UnaryOp(USub, ...))); only the SOURCE SPACING separates them.
# We import the engine's own predicates rather than re-implementing them so
# the translator's term-position rule cannot drift from the clause-level rule
# the engine enforces (see _lower_arrow_lambda_in_term_position).
from clausal.templating.term_rewriting import (
    _is_arrow_adjacent as _engine_is_arrow_adjacent,
    _leftmost_usub as _engine_leftmost_usub,
    _table_directive_call as _engine_table_directive_call,
    _expand_currency_table as _engine_expand_currency_table,
)
from clausal.tools.prolog_dialect import (
    Dialect,
    pascal_to_snake, snake_to_pascal,
    clausal_var_to_prolog, prolog_var_to_clausal,
    resolve_name,
)

# Re-export naming helpers so tests can import from this module.
__all__ = [
    "emit_term", "emit_item", "emit_module",
    "clausal_source_to_prolog", "clausal_source_to_prolog_ast",
    "module_export_signature",
    "pascal_to_snake", "snake_to_pascal",
    "clausal_var_to_prolog", "prolog_var_to_clausal",
    "UntranslatableConstructError",
]


class UntranslatableConstructError(NotImplementedError):
    """Raised in strict mode when source contains constructs with no ISO Prolog equivalent."""

    def __init__(self, constructs: list[str]):
        self.constructs = constructs
        listing = "\n  ".join(constructs)
        super().__init__(
            f"{len(constructs)} untranslatable construct(s):\n  {listing}"
        )


# Dotted clausal module → the file name it is exported under at the root of
# the export tree. These libraries are flattened out of their source package
# so every exported module can reach them by climbing to the root.
_LIBRARY_REMAP = {
    "clausal.stdlib.kleene": "clausal_kleene",
}


# ── Prolog text emission ─────────────────────────────────────────────

# Operators that are typically displayed with spaces around them
_INFIX_NO_SPACE = frozenset()  # all infix operators get spaces


# ISO 6.4.2 graphic chars — the characters a "graphic token" (symbolic atom
# such as ``-``, ``-->``, ``=..``) is built from. Two adjacent graphic chars
# always lex as ONE token, which is why _terminate_clause below cannot let a
# symbolic atom sit flush against the clause-terminating ``.``.
_GRAPHIC_CHARS = frozenset("#$&*+-./:<=>?@^~\\")

# Atoms that are their own token and need no quotes. ``,`` is deliberately
# NOT here: a bare ``,`` in argument position is the argument separator, so
# ``p(,)`` is a syntax error (Scryer: syntax_error(incomplete_reduction)).
_SOLO_UNQUOTED_ATOMS = frozenset(("[]", "{}", "!", ";"))

_ASCII_LOWER = frozenset("abcdefghijklmnopqrstuvwxyz")
_ASCII_ALNUM_UNDERSCORE = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _needs_quoting(name: str) -> bool:
    """True if an atom name needs single-quoting in Prolog.

    Three unquoted atom shapes exist in ISO 6.4.2, and nothing else:

    * a **name token** — a lowercase ASCII letter followed by ASCII letters,
      digits and underscores. ``str.isalnum()`` cannot be the test here: it is
      true of characters no ISO reader accepts unquoted (``a²``, and letters
      outside ASCII), and the migrated literals are arbitrary author text, so
      the check is written against the ASCII repertoire explicitly.
    * a **graphic token** — all chars drawn from :data:`_GRAPHIC_CHARS`, with
      two exclusions. A solitary ``.`` is indistinguishable from the end
      token, so ``X = .`` reads as an unterminated clause; ``'.'`` is accepted
      everywhere, so a lone dot is always quoted. And a token may not BEGIN
      with the comment-open sequence ``/*`` (ISO 6.4.2): at the start of a
      token ``/*`` opens a comment, so ``t(/*).`` swallows the rest of the
      file and the reader reports ``syntax_error(incomplete_reduction)``.
      The rule is LEADING-position only -- tokenization is maximal munch, so
      once inside a graphic token ``/*`` is just more graphic characters and
      ``*/*``, ``//*``, ``-/*`` and ``+/*+`` all consult fine (verified in
      Scryer; ``/*``, ``/*/`` and ``/**/`` are the ones that break).
    * the **solo tokens** in :data:`_SOLO_UNQUOTED_ATOMS`.

    Every case is verified against real Scryer by
    ``tests/test_prolog_emit.py::TestAtomQuotingIsIsoSafe``.
    """
    if not name:
        return True
    if (name[0] in _ASCII_LOWER
            and all(c in _ASCII_ALNUM_UNDERSCORE for c in name)):
        return False
    if (name != "."
            and not name.startswith("/*")
            and all(c in _GRAPHIC_CHARS for c in name)):
        return False
    if name in _SOLO_UNQUOTED_ATOMS:
        return False
    return True



# ISO 6.4.2 control escape sequences (emitter leg of F034 — the tokenizer
# already reads all of these). NUL uses the octal form `\0\` (the closing
# backslash keeps a following digit from being absorbed into the escape).
_ATOM_ESCAPES = {
    "\\": "\\\\",
    "'":  "\\'",
    "\n": "\\n",
    "\t": "\\t",
    "\r": "\\r",
    "\b": "\\b",
    "\f": "\\f",
    "\v": "\\v",
    "\a": "\\a",
    "\0": "\\0\\",
}


def _escape_body(text: str, quote_char: str) -> str:
    """Escape *text* for the inside of a quoted token delimited by
    *quote_char*, per ISO 6.4.2: backslash, the delimiter itself, the named
    control escapes, and ``\\xHH\\`` for every other control character.

    A RAW newline inside a quoted token terminates the token's line and the
    reader reports ``syntax_error(missing_quote)`` -- the class-G defect that
    failed 16 corpus domains at G2.
    """
    out: list[str] = []
    for ch in text:
        if ch == quote_char:
            out.append("\\" + ch)
            continue
        esc = _ATOM_ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):x}\\")
        else:
            out.append(ch)
    return "".join(out)


def _escape_string_body(text: str) -> str:
    """Escape *text* for the inside of a Prolog double-quoted token."""
    return _escape_body(text, '"')


def _quote_atom(name: str) -> str:
    """Single-quote an atom, escaping quotes and control characters.

    Control characters without a named ISO escape are emitted with the
    ISO hex form ``\\xHH\\`` — raw control chars inside a quoted atom are
    not valid ISO Prolog text (F034).
    """
    return "'" + _escape_body(name, "'") + "'"


#: Atoms that are operators in a LIBRARY the emitted file imports, but not in
#: the ISO operator table. They are deliberately absent from that table -- it
#: drives INFIX rendering, and `#=` is not ISO, so the emission is functional
#: `#=(X, Y)` by design. Bracketing is a separate question from rendering: the
#: reader that consults the emitted file has the library's `:- op/3` in force,
#: so where an operator atom must be bracketed it must be bracketed here too.
#: `[#=/2]` in an import list is a syntax error in Scryer
#: (`syntax_error(incomplete_reduction)`); `[(#=)/2]` is right.
#:
#: QUOTING IS NOT A SUBSTITUTE, and the mistake is easy to make because Scryer
#: ACCEPTS `['(#=)'/2]` -- but a control with a bogus indicator
#: (`[nonexistent_thing/2]`) is accepted just as happily, so acceptance of the
#: directive proves nothing about the indicator. `'(#=)'` names an atom spelled
#: `(#=)`, which is not the operator.
_LIBRARY_OPERATOR_ATOMS = frozenset({"#=", "#\\=", "#<", "#>", "#=<", "#>="})


def _is_operator_atom(name: str, op_table: OperatorTable) -> bool:
    """True if *name* is declared as an operator in *op_table* (any fixity),
    or is a library operator the emitted file's reader will have in force."""
    return (op_table.lookup_infix(name) is not None
            or op_table.lookup_prefix(name) is not None
            or op_table.lookup_postfix(name) is not None
            or name in _LIBRARY_OPERATOR_ATOMS)


#: Internal sentinel wrapping a discarded unit while a term is being rendered.
#: Stripped by _attach_unit_notes before any text leaves emit_item, so it can
#: never reach a .pl file. U+0001 cannot occur in Clausal source.
_UNIT_MARK = "\x01"
#: value + marked unit. The value class must EXCLUDE the marker itself, or a
#: greedy match runs straight through one pair into the next.
_UNIT_RE = re.compile(
    r"([^\s(,)" + _UNIT_MARK + r"]+)" + _UNIT_MARK
    + r"([^" + _UNIT_MARK + r"]+)" + _UNIT_MARK)


def _unit_marker(term) -> str:
    unit = getattr(term, "unit", None)
    return f"{_UNIT_MARK}{unit}{_UNIT_MARK}" if unit else ""


def _attach_unit_notes(text: str) -> str:
    """Move each line's discarded units into ONE trailing `%` comment.

    `X =:= 5000 + 3000.` -> `X =:= 5000 + 3000.  % Clausal units: 5000 (euro), 3000 (euro)`

    Trailing rather than above: a `%` runs to end of line, which is harmless
    once the line's code is complete, and it costs no extra lines. Per LINE
    rather than per clause so the note sits next to the values it describes;
    a line normally carries one or two.
    """
    out = []
    for line in text.split("\n"):
        if _UNIT_MARK not in line:
            out.append(line)
            continue
        pairs = [(m.group(1), m.group(2)) for m in _UNIT_RE.finditer(line)]
        clean = _UNIT_RE.sub(r"\1", line)
        note = ", ".join(f"{value} ({unit})" for value, unit in pairs)
        out.append(f"{clean}  % Clausal units: {note}")
    return "\n".join(out)


def emit_term(term: PTerm, op_table: OperatorTable, *,
              context_prec: int = 1201, context_assoc: str = "",
              operand_of_op: bool = False) -> str:
    """Render a Prolog AST term as text.

    *context_prec* and *context_assoc* control parenthesization based
    on the enclosing operator's precedence and associativity.

    *operand_of_op* says this term is the immediate operand of an operator
    (rather than a compound argument or a list element). ISO 6.3.1.3 forbids
    an atom that is itself an operator from standing there unbracketed, so
    ``X = -`` must be emitted ``X = (-)``. QUOTING DOES NOT SUBSTITUTE: the
    rule is about the atom's declared PRIORITY, not its spelling, and Scryer
    rejects ``X = '-'`` exactly as it rejects ``X = -`` (both verified). An
    operator atom in a compound argument (``f(-, a)``) or a list element
    (``[-, a]``) is fine unbracketed and is left alone.
    """
    if isinstance(term, PAtom):
        if term.quoted or _needs_quoting(term.name):
            text = _quote_atom(term.name)
        else:
            text = term.name
        if operand_of_op and _is_operator_atom(term.name, op_table):
            return "(" + text + ")"
        return text
    if isinstance(term, PVar):
        return term.name + _unit_marker(term)
    if isinstance(term, PNumber):
        text = (repr(term.value) if isinstance(term.value, float)
                else str(term.value))
        return text + _unit_marker(term)
    if isinstance(term, PString):
        return '"' + _escape_string_body(term.value) + '"'
    if isinstance(term, PList):
        return _emit_list(term, op_table)
    if isinstance(term, PCurly):
        inner = emit_term(term.body, op_table)
        return "{" + inner + "}"
    if isinstance(term, PCompound):
        return _emit_compound(term, op_table, context_prec, context_assoc)
    return str(term)


def _emit_list(lst: PList, op_table: OperatorTable) -> str:
    """Render a PList as [a, b, c] or [H|T]."""
    if not lst.elements and lst.tail is None:
        return "[]"
    parts = [emit_term(e, op_table, context_prec=999) for e in lst.elements]
    if lst.tail is not None:
        tail_str = emit_term(lst.tail, op_table, context_prec=999)
        return "[" + ", ".join(parts) + "|" + tail_str + "]"
    return "[" + ", ".join(parts) + "]"


def _emit_compound(term: PCompound, op_table: OperatorTable,
                   context_prec: int, context_assoc: str) -> str:
    """Render a PCompound — either as f(a,b) or as infix/prefix operator."""
    functor = term.functor
    arity = len(term.args)

    # Zero-arity compound
    if arity == 0:
        if _needs_quoting(functor):
            return _quote_atom(functor)
        return functor

    # Try infix operator (arity 2)
    if arity == 2:
        entry = op_table.lookup_infix(functor)
        if entry is not None:
            return _emit_infix(term, entry, op_table, context_prec, context_assoc)

    # Try prefix operator (arity 1)
    if arity == 1:
        entry = op_table.lookup_prefix(functor)
        if entry is not None:
            return _emit_prefix(term, entry, op_table, context_prec, context_assoc)

    # Try postfix operator (arity 1)
    if arity == 1:
        entry = op_table.lookup_postfix(functor)
        if entry is not None:
            return _emit_postfix(term, entry, op_table, context_prec, context_assoc)

    # Standard compound: f(a, b, c)
    # Arguments separated by ',' (prec 1000) sit at context_prec 999, so
    # any contained operator with prec >= 1000 (', ;, :- etc.) gets parens.
    args_str = ", ".join(emit_term(a, op_table, context_prec=999) for a in term.args)
    if _needs_quoting(functor):
        return _quote_atom(functor) + "(" + args_str + ")"
    return functor + "(" + args_str + ")"


def _emit_infix(term: PCompound, entry, op_table: OperatorTable,
                context_prec: int, context_assoc: str) -> str:
    """Render infix operator: left op right."""
    prec = entry.precedence
    spec = entry.specifier  # xfx, xfy, yfx

    # Determine child context for left and right operands
    left_prec = prec if spec.startswith("y") else prec - 1
    right_prec = prec if spec.endswith("y") else prec - 1
    left_assoc = spec if spec.startswith("y") else ""
    right_assoc = spec if spec.endswith("y") else ""

    left_str = emit_term(term.args[0], op_table,
                         context_prec=left_prec, context_assoc=left_assoc,
                         operand_of_op=True)
    right_str = emit_term(term.args[1], op_table,
                          context_prec=right_prec, context_assoc=right_assoc,
                          operand_of_op=True)

    # Comma is special: "a, b" not "a , b"
    # Slash in predicate indicators: "f/2" not "f / 2"
    if term.functor == ",":
        result = left_str + ", " + right_str
    elif term.functor == "/":
        result = left_str + "/" + right_str
    else:
        result = left_str + " " + term.functor + " " + right_str

    # Parenthesize if this operator binds looser than the context, or has equal
    # precedence in a non-associative (xfx) parent position. The caller already
    # encodes whether an equal-precedence child is allowed by passing the
    # parent's specifier as context_assoc only on the y-side (see left_assoc /
    # right_assoc above), so an x-side child arrives with context_assoc "xfx".
    if prec > context_prec:
        return "(" + result + ")"
    if prec == context_prec and context_assoc == "xfx":
        return "(" + result + ")"
    return result


def _emit_prefix(term: PCompound, entry, op_table: OperatorTable,
                 context_prec: int, context_assoc: str) -> str:
    """Render prefix operator: op arg."""
    prec = entry.precedence
    spec = entry.specifier  # fx or fy

    arg_prec = prec if spec == "fy" else prec - 1
    arg_str = emit_term(term.args[0], op_table, context_prec=arg_prec,
                        operand_of_op=True)

    result = term.functor + " " + arg_str

    if prec > context_prec:
        return "(" + result + ")"
    return result


def _emit_postfix(term: PCompound, entry, op_table: OperatorTable,
                  context_prec: int, context_assoc: str) -> str:
    """Render postfix operator: arg op."""
    prec = entry.precedence
    spec = entry.specifier  # xf or yf

    arg_prec = prec if spec == "yf" else prec - 1
    arg_str = emit_term(term.args[0], op_table, context_prec=arg_prec,
                        operand_of_op=True)

    result = arg_str + " " + term.functor

    if prec > context_prec:
        return "(" + result + ")"
    return result


# ── Item emission ────────────────────────────────────────────────────

def _terminate(text: str) -> str:
    """Append the clause-terminating ``.`` without letting it MERGE into the
    token before it.

    Two adjacent graphic characters lex as one token, so a clause whose last
    token is a symbolic atom would otherwise be corrupted: ``X = ..`` plus the
    terminator reads as ``X = ...`` and the reader reports
    ``syntax_error(incomplete_reduction)`` (verified in Scryer). A single
    space is enough to end the graphic token. Clauses ending in ``)``, ``]``
    or an alphanumeric -- i.e. essentially all of them -- are unaffected.
    """
    if text and text[-1] in _GRAPHIC_CHARS:
        return text + " .\n"
    return text + ".\n"


def emit_item(item: PItem, op_table: OperatorTable) -> str:
    return _attach_unit_notes(_emit_item(item, op_table))


def _emit_item(item: PItem, op_table: OperatorTable) -> str:
    """Render a single PItem (clause, DCG rule, directive) as Prolog text."""
    if isinstance(item, PClause):
        head_str = emit_term(item.head, op_table)
        if item.body is None:
            return _terminate(head_str)
        body_str = _emit_body(item.body, op_table)
        return _terminate(head_str + " :-\n    " + body_str)
    if isinstance(item, PDCGRule):
        head_str = emit_term(item.head, op_table)
        body_str = _emit_dcg_body(item.body, op_table)
        return _terminate(head_str + " -->\n    " + body_str)
    if isinstance(item, PDirective):
        body_str = emit_term(item.body, op_table)
        return _terminate(":- " + body_str)
    if isinstance(item, PComment):
        if item.text.startswith("%"):
            # Already written as Prolog line comment(s) — emit verbatim so a
            # one-line note does not become a block comment.
            return item.text.rstrip("\n") + "\n"
        return "/* " + item.text + " */\n"
    # PQuery
    body_str = emit_term(item.body, op_table)
    return _terminate("?- " + body_str)


def _emit_body(body: PTerm, op_table: OperatorTable) -> str:
    """Render a clause body, handling conjunction layout."""
    # Flatten top-level conjunctions for indented layout
    goals = _flatten_conjunction(body)
    if len(goals) == 1:
        return emit_term(goals[0], op_table)
    parts = [emit_term(g, op_table, context_prec=999) for g in goals]
    return (",\n    ").join(parts)


def _emit_dcg_body(body: PTerm, op_table: OperatorTable) -> str:
    """Render a DCG rule body."""
    # DCG bodies use comma-separated items
    goals = _flatten_conjunction(body)
    if len(goals) == 1:
        return emit_term(goals[0], op_table)
    parts = [emit_term(g, op_table, context_prec=999) for g in goals]
    return ", ".join(parts)


def _flatten_conjunction(term: PTerm) -> list[PTerm]:
    """flatten nested ','(A, B) into a flat list of goals."""
    if isinstance(term, PCompound) and term.functor == "," and len(term.args) == 2:
        return _flatten_conjunction(term.args[0]) + _flatten_conjunction(term.args[1])
    return [term]


# ── Module emission ──────────────────────────────────────────────────

#: Said ONCE at the top of any file that lost a unit, so a reader meets the
#: caveat before the code rather than inferring it from scattered notes.
_LOSSY_HEADER = ("% Clausal to Prolog translation has removed units from some "
                 "numbers. See comments below.")


def emit_module(pmodule: PModule, op_table: OperatorTable) -> str:
    """Render a full PModule as Prolog source text."""
    parts = [emit_item(item, op_table) for item in pmodule.items]
    body = "\n".join(parts)
    if "% Clausal units:" in body:
        body = _LOSSY_HEADER + "\n\n" + body
    return body


# ── Clausal source → Prolog AST conversion ───────────────────────────

def _base_unit_names() -> frozenset[str]:
    """Every unit NAME whose declared magnitude is also the stored magnitude.

    A unit that carries a FACTOR rescales: ``day`` is ``Quantity(86400,
    second)`` and ``cent`` is ``Quantity(Decimal('0.01'), dollar)``, so the
    number in the declaration is not the number the engine holds. A unit that
    is a ``_UnitsPredicate`` carries no factor -- base dimensions (``metre``,
    ``second``) and factor-1 derived units (``newton``) alike -- and neither
    does a currency, which is a base dimension of its own.

    Reading the engine's unit vocabulary is not executing the file being
    translated: these are names resolved against static data, exactly as the
    import directives already are.
    """
    from clausal.modules import units as _units                 # noqa: PLC0415
    from clausal.modules.countries import _data                 # noqa: PLC0415
    names = {n for n, v in vars(_units).items()
             if isinstance(v, _units._UnitsPredicate)}
    # The BINDINGS, not the words: a shared word is not bound at all, so
    # source writes `usd`, and a set keyed on "dollar" would refuse it as a
    # scaled unit while silently accepting a word nothing can name.
    names |= set(_data.CURRENCY_BINDINGS.values())
    return frozenset(names)


def _is_known_scaled_unit(name: str) -> bool:
    """True for a unit name KNOWN to carry a factor, so that dropping it
    changes the magnitude: ``cent``, ``day``, ``kilometre``, ``gram``…

    Deliberately the opposite polarity to `_base_unit_names`, which the
    DECLARATION path uses. A declaration in a scaled unit had zero occurrences
    anywhere when this landed, so refusing everything not known to be safe
    costs nothing there. The inline ``5000(euro)`` form is used throughout the
    corpus and the tests, and it has been exported this way since the
    2026-09-08 ruling -- so here an unrecognised name (a user-defined unit, or
    the still-supported TitleCase ``Metre`` alias) keeps working, and only the
    known hazard is refused. Under-refusing in the direction of the
    established behaviour, rather than breaking exports to close a hole that
    nothing in the corpus reaches.
    """
    from clausal.modules import units as _units                 # noqa: PLC0415
    from clausal.modules.countries import _data                 # noqa: PLC0415
    from clausal.terms import Quantity                          # noqa: PLC0415
    # NOT `and v.dims`. That clause excluded a DIMENSIONLESS scaled unit,
    # which is exactly a ratio unit's shape -- and it excluded nothing at all
    # on the day it was written, because there were no dimensionless Quantity
    # constants then, so nothing could notice it was wrong. Ratio units are
    # the first values it is wrong about, and dropping `basis_point` from
    # `300(basis_point)` emits 300 against a stored 0.03 (2026-09-12). The
    # thing that makes a unit hazardous here is carrying a FACTOR, which has
    # nothing to do with having a dimension.
    scaled = {n for n, v in vars(_units).items() if isinstance(v, Quantity)}
    scaled |= set(_data.MINOR_UNITS.values())
    return name in scaled or name.lower() in scaled


def _group_digits(numerator: int, places: int) -> str:
    """`155000`, 2 places -> `"1_550_00"`. The minor units separated from the
    major, which is how the amount is written in the statute. Both reference
    systems accept underscore grouping in integers; verified 2026-09-13."""
    text = str(abs(numerator)).rjust(places + 1, "0")
    major, minor = (text[:-places], text[-places:]) if places else (text, "")
    # thousands in the major part too, so a large statutory amount stays
    # legible: 1234567890 at 2 places -> 12_345_678_90
    chunks = []
    while len(major) > 3:
        chunks.insert(0, major[-3:])
        major = major[:-3]
    chunks.insert(0, major)
    grouped = "_".join(chunks + ([minor] if minor else []))
    return ("-" + grouped) if numerator < 0 else grouped


def _integral_if_whole(value):
    """A Decimal that equals a whole number becomes an int, for USE SITES.

    Reported by iso-export-lane on canonical 750e6ae1: the scaled fold emitted
    `1550.00`, which Prolog reads as a FLOAT, where the exact integer 1550 was
    available -- and the unscaled path stayed integer, so only scaling lost
    exactness. The engine holds currency exactly, so this was discarding
    exactness at emission.

    A genuinely fractional result stays a float, which is a known limit: a use
    site must be arithmetically usable, and under the `#=` ruling CLP(Z) is
    integer-only, so there is no exact form for fractional money to convert to.
    """
    from decimal import Decimal                                  # noqa: PLC0415
    if (isinstance(value, PNumber) and isinstance(value.value, Decimal)
            and value.value == value.value.to_integral_value()):
        return PNumber(int(value.value))
    return value


def _scale_constant_value(value, factor):
    """*value* times *factor*, as a Prolog term, exactly.

    Kept exact: a `Decimal` factor times an int stays a Decimal, so
    `155000 * Decimal('0.01')` is `Decimal('1550.00')` and never 1550.0000001.
    A factor of 1 is returned UNCHANGED rather than multiplied, so a base-unit
    constant cannot acquire a decimal point it did not have -- that is the
    regression guard, not an optimisation.
    """
    if factor == 1:
        return value
    if not isinstance(value, PNumber):
        raise NotImplementedError(
            "clausal_to_prolog: a constant in a scaled unit must have a "
            f"numeric magnitude to convert; got {value!r}")
    return PNumber(value.value * factor)


def _unscale_constant_value(value, factor):
    """*value* divided by *factor*, as a Prolog term, exactly.

    The inverse of :func:`_scale_constant_value`, for a USE SITE that asks for
    a constant's magnitude in a named unit: a declaration stores the BASE
    magnitude, so `constant(cap) / usd_cent` has to convert back out.

    Exact by construction. `Decimal('1550.00') / Decimal('0.01')` is
    `Decimal('155000')`, never 154999.99999. A factor of 1 returns the value
    UNCHANGED rather than dividing, for the same reason the forward helper
    does: a base-unit constant must not acquire a decimal point it never had.
    Integral results are handed back as `int`, because `1550.00 / 0.01` is the
    integer 155000 and emitting `155000.0` would reintroduce the float defect
    this path exists to remove.
    """
    if factor == 1:
        return value
    if not isinstance(value, PNumber):
        raise NotImplementedError(
            "clausal_to_prolog: a constant asked for in a scaled unit must "
            f"have a numeric magnitude to convert; got {value!r}")
    out = value.value / factor
    if out == int(out):
        out = int(out)
    return PNumber(out)


def _unit_factor(names: list[str]):
    """The factor a declared unit multiplies by to reach its base, or None.

    Resolved from STATIC DATA only -- the `Quantity` literal in
    ``clausal.modules.units``, a currency's ISO scale via ``_data``, or
    ``RATIO_UNITS``. Reading the unit vocabulary is not executing the file
    being translated, which is the objection that does not apply here (the
    exporter already resolves the import directives it turns into
    ``use_module``).

    A base dimension, a currency, or a factor-1 derived unit answers 1.
    Anything the vocabulary does not hold answers None, and the caller
    REFUSES rather than guessing -- a wrong factor is a wrong number in an
    exported legal program, which is the defect this whole path exists for.

    Only a SINGLE leaf is resolved. A compound (`usd / second`) would need
    the factors composed with the operator, and getting that subtly wrong is
    worse than refusing it; compounds of base units already answer 1 because
    every leaf does.
    """
    from decimal import Decimal                                 # noqa: PLC0415
    from clausal.modules import units as _units                 # noqa: PLC0415
    from clausal.terms import Quantity                          # noqa: PLC0415
    factor = 1
    for leaf in names:
        obj = getattr(_units, leaf, None)
        if obj is None:
            cf = _currency_factor(leaf)
            if cf is None:
                return None
            if cf != 1:
                if factor != 1:
                    return None        # a compound of two SCALED units
                factor = cf
            continue
        if isinstance(obj, Quantity):
            if factor != 1:
                return None            # a compound of two SCALED units
            factor = obj.value
        elif not isinstance(obj, _units._UnitsPredicate):
            return None
    return factor


def _currency_factor(leaf: str):
    """The factor for a currency or minor-unit NAME, or None if neither.

    Read from `_data`'s tables rather than by importing a jurisdiction module:
    a currency is a base dimension of its own, so its factor is 1; a minor
    unit's factor is its currency's ISO scale, the same `scaleb` the engine's
    `_make_minor_unit` derives it from -- so the two cannot drift.
    """
    from decimal import Decimal                                 # noqa: PLC0415
    from clausal.modules.countries import _data                 # noqa: PLC0415
    if leaf in set(_data.CURRENCY_BINDINGS.values()):
        return 1                                    # a base dimension
    for code, word in _data.MINOR_UNITS.items():
        if word != leaf:
            continue
        for row in _data.CURRENCIES:
            if row["code"] == code:
                return Decimal(1).scaleb(-row["scale"])
        return None
    return None


def _is_arrow_lambda_shape(node, source_lines) -> bool:
    """True iff *node* is a `<-` lambda rather than a `< -` comparison.

    One predicate, asked by both the call site and the lowering, so the two
    can never disagree about what an arrow lambda is. `<-` and `< -` parse to
    the same AST and only source spacing separates them; with no source
    positions (a programmatically built AST) we cannot tell, and the answer is
    False so the pre-existing comparison behavior stands.
    """
    if not isinstance(node, python_ast.Compare) or not node.ops:
        return False
    if not isinstance(node.ops[0], python_ast.Lt):
        return False
    usub_node, _depth = _engine_leftmost_usub(node.comparators[0])
    if usub_node is None:
        return False
    try:
        return _engine_is_arrow_adjacent(node.left, usub_node, source_lines)
    except ValueError:
        return False


def _variable_names(node) -> frozenset[str]:
    """Every LOGIC VARIABLE name mentioned anywhere under *node*."""
    return frozenset(
        n.id for n in python_ast.walk(node)
        if isinstance(n, python_ast.Name) and _is_logic_var_name(n.id))


def _names_bound_in(node) -> frozenset[str]:
    """Variables *node* puts in an OUTPUT position: the left of `is`/`==`.

    Deliberately NOT "every variable passed as an argument". A variable handed
    to a predicate is usually an input, and treating argument position as an
    output would refuse nearly every closure in a corpus. This set is the
    shape that is unambiguous from the source alone.
    """
    out: set[str] = set()
    for n in python_ast.walk(node):
        if (isinstance(n, python_ast.Compare) and len(n.ops) == 1
                and isinstance(n.ops[0], (python_ast.Eq, python_ast.Is))):
            out |= _variable_names(n.left)
        elif isinstance(n, python_ast.Assign):
            for target in n.targets:
                out |= _variable_names(target)
    return frozenset(out)


def _lambda_parameter_names(node) -> list[str] | None:
    """The parameter list of a `<-` lambda, or None if it is not one.

    `(U, V) <- Body` gives ``["U", "V"]``; a single `S <- Body` gives
    ``["S"]``. Anything that is not a plain variable — a literal, a call, a
    nested tuple — returns None, and the caller refuses rather than guessing
    what the author meant.
    """
    if isinstance(node, python_ast.Tuple):
        elements = list(node.elts)
    else:
        elements = [node]
    names = []
    for element in elements:
        if not (isinstance(element, python_ast.Name)
                and _is_logic_var_name(element.id)):
            return None
        names.append(element.id)
    return names or None


def _unit_divisor_factor(node):
    """The factor for a `/ <unit>` DIVISOR, or None if it is not a unit at all.

    :func:`_unit_factor` answers 1 for an EMPTY name list, by design: a
    compound of base units resolves to 1 because every leaf does. A NUMERIC
    divisor also names no unit, so it reached that same 1 and the division was
    folded away to nothing -- `PCT * SUB / 10000` emitted `PCT * SUB`, silently,
    off by four orders of magnitude. Both fold paths went through it and the
    constant one had shipped with the hole.

    So a divisor must NAME something before its factor is even looked up. This
    is the divisor-position guard only; a declaration's unit (which is a unit by
    syntax, not by inference) keeps calling _unit_factor directly.
    """
    names = _unit_leaf_names(node)
    if not names:
        # A QUANTITY-literal divisor -- `/ 1(euro)` -- names its unit inside a
        # Call, which _unit_leaf_names does not descend into. Three corpus
        # sites spell it that way, and they used to fold only by ACCIDENT
        # through the very hole this function closes: the Call named no leaf,
        # the factor came back 1, and dividing by 1 happened to be right.
        unit = _quantity_divisor_unit(node)
        if unit is None:
            return None
        names = [unit]
    return _unit_factor(names)


def _quantity_divisor_unit(node) -> str | None:
    """The unit of a `1(unit)` Quantity-literal divisor, else None.

    ONLY a magnitude of exactly 1, because only that is a pure unit
    conversion: `/ 5(euro)` is a division by five euro, and folding it away as
    though it merely named a unit would be off by a factor of five.
    """
    if (not isinstance(node, python_ast.Call) or node.keywords
            or len(node.args) != 1):
        return None
    func = node.func
    if not (isinstance(func, python_ast.Constant)
            and not isinstance(func.value, bool)
            and func.value == 1):
        return None
    unit = node.args[0]
    if not isinstance(unit, python_ast.Name) or _is_var_in_name_position(unit.id):
        return None
    return unit.id


def _unit_leaf_names(node) -> list[str]:
    """The NAMES a unit expression mentions, in order. Exponents are skipped;
    a qualified ``european_union.euro`` contributes ``euro``."""
    if isinstance(node, python_ast.Name):
        return [node.id]
    if isinstance(node, python_ast.Attribute):
        return [node.attr]
    if isinstance(node, python_ast.BinOp):
        return (_unit_leaf_names(node.left) + _unit_leaf_names(node.right))
    if isinstance(node, python_ast.UnaryOp):
        return _unit_leaf_names(node.operand)
    return []                       # a numeric exponent names no unit


def _is_logic_var_name(identifier: str) -> bool:
    """Return True if identifier should be treated as a logic variable.

    Bare ``_`` stays a variable here (translation context) — pinned by
    test_var_classifier_conformance, which also pins the constant-shape
    exclusion below.
    """
    if identifier == "_":
        return True
    if identifier.startswith("__"):
        return False
    if identifier.startswith("_"):
        return True
    # Capital initial (ISO): ``X``, ``FOO``, ``Foo``.  ``Foo`` joined
    # this class on 2026-09-10 -- see term_rewriting._is_logic_var_name,
    # which is the copy that carries the full rationale.  All five
    # copies move together (test_var_classifier_conformance).
    return identifier[:1].isupper()


def _is_var_in_name_position(identifier: str) -> bool:
    """``FOO``/``_foo`` yes, ``Foo`` no -- see
    ``term_rewriting._is_var_in_name_position`` for the full rationale.
    Mirrored here for the same reason the classifier itself is: this module
    stays free of a templating import.  The three call sites are the
    ``X(unit)`` quantity-literal shape, where reading a TitleCase callable as
    a variable would discard a real functor call as a unit annotation.
    """
    titlecase = (identifier[:1].isupper()
                 and any(c.islower() for c in identifier))
    return _is_logic_var_name(identifier) and not titlecase


def _leftmost_usub(node):
    """Find the leftmost USub in a Python AST expression (for <- detection).

    Returns (usub_node, depth) or (None, 0).
    """
    if isinstance(node, python_ast.UnaryOp) and isinstance(node.op, python_ast.USub):
        return node, 0
    if isinstance(node, python_ast.BinOp):
        result, depth = _leftmost_usub(node.left)
        if result is not None:
            return result, depth + 1
    if isinstance(node, python_ast.Compare):
        result, depth = _leftmost_usub(node.left)
        if result is not None:
            return result, depth + 1
    return None, 0


class _ClausalToProlog:
    """Convert Python AST (from .clausal source) to Prolog AST.

    Recognizes clausal DSL patterns: trailing-comma facts, <- rules,
    >> DCG rules, -directives.
    """

    def __init__(self, dialect: Dialect, strict: bool = False, *,
                 module_path: str | None = None,
                 module_signatures: dict[str, set[tuple[str, int]]] | None = None,
                 meta_modes: MetaModeMap | None = None,
                 source_lines: list[str] | None = None):
        self.dialect = dialect
        self.strict = strict
        # Original source, split into lines. Required to tell the lambda arrow
        # `<-` from the comparison `< -`, which are indistinguishable in the
        # AST and differ only in source spacing. None when the caller built the
        # AST programmatically; the arrow-lambda refusal then cannot fire (the
        # engine's own fallback heuristic is used, matching clause-level).
        self._source_lines = source_lines
        # Item J (2026-09-07): the literal rule. A str literal lowers by the
        # MODULE's -double_quotes mode and by its own quote character, exactly
        # as the compiler decides the literal's runtime value
        # (term_rewriting.visit_Constant + _handle_double_quotes_directive),
        # so translator and runtime agree by construction. `ast` erases the
        # quote character; the compiler's quote map rebuilds it from the
        # token stream, keyed by position. Empty when the caller built the
        # AST programmatically: every lookup then answers None and the mode
        # alone decides. Position-sensitive like the compiler's: the mode
        # governs the literals BELOW the directive, so it is walk state.
        self._quote_map = build_quote_map(source_lines) if source_lines else {}
        self._double_quotes = "chars"
        # Dotted path of the module being translated. When set, use_module
        # file paths are emitted relative to this module's package directory
        # (Scryer resolves a consulted path against the consulting file).
        self.module_path = module_path
        # The `-module(...)` name, for the `facts` dialects that need the
        # module filled in at export time. Captured when that directive is
        # converted; falls back to the module path's basename, because a file
        # may declare a constant before (or without) `-module`.
        self._module_name: str | None = None
        #: Set when a constant declaration is emitted, so the prelude import is
        #: added only to files that need it.
        self._emitted_constant_declaration = False
        #: True once a `<-` lambda has been lowered, so the module gets
        #: `:- use_module(library(lambda))`. Set by
        #: :meth:`_lower_arrow_lambda_in_term_position`.
        self._emitted_arrow_lambda = False
        #: True once a CLP arithmetic equality (`#=`) has been emitted, so the
        #: module imports the dialect's constraint library. `#=` is not ISO and
        #: no engine has it without the import: the file raises
        #: `existence_error(procedure, #=/2)` at CALL time, never at consult
        #: time, so a missing import is a silent wrong answer rather than a
        #: load failure.
        self._emitted_clp_arith_eq = False
        #: The same for the CLP disequality `#\=` (ruling R16: a numeric
        #: `!=`), imported beside `#=`.
        self._emitted_clp_arith_neq = False
        #: Variable names bound by the head of the clause currently being
        #: converted. A lambda's body variable that is NOT a parameter and
        #: IS in this set is a CAPTURE, which is the only thing the lowering
        #: has to reason about. Saved and restored around each clause, so a
        #: nested conversion cannot see an outer clause's head.
        self._enclosing_head_vars: frozenset[str] = frozenset()
        # Dotted target path → that target's FILTERED export set, as returned
        # by module_export_signature. When set, import lists are narrowed to
        # names the target really exports.
        self.module_signatures = module_signatures
        # module_path -> {(name, arity): per-argument modes}. Supplies the meta
        # positions that this module's own text cannot show -- a THREADING host,
        # whose argument is only ever called further down the chain, often in
        # another module (the `find_mus/4` / `failing_ids/4` shape). Computed by
        # the exporter's cross-module fixpoint and keyed by exactly the
        # `module_path` string the exporter hands this translation.
        self.meta_modes = meta_modes
        self._items: list[PItem] = []
        self._warnings: list[str] = []
        #: Lossy-but-successful lowerings (units discarded). NOT warnings: a
        #: warning marks a construct as untranslatable and makes strict mode
        #: raise, whereas these DID translate — with documented information
        #: loss. Kept separate so a lossy file still counts as clean.
        #: Unit atoms seen in Quantity literals, collected by a pre-pass over
        #: the module before any statement is converted -- the import that
        #: names a unit is EARLIER in the file than the use that reveals it.
        self._unit_atoms: set[str] = set()
        #: Declared constants, name -> already-converted Prolog term, in file
        #: order. A constant has no Prolog representation of its own: ISO's
        #: evaluable-functor set is fixed and ``++/1`` is not in it, so an
        #: emitted NAME raises type_error(evaluable, ...) in every conformant
        #: system (measured against Scryer and Trealla, 2026-09-10). The value
        #: is known here -- the declaration is in the same file -- so use sites
        #: get the value instead. See tests/test_prolog_constant_fold.py.
        self._constants: dict[str, PTerm] = {}
        #: True only while converting a ``-constant_value`` RHS. A bare name
        #: means the ATOM everywhere else (2026-09-11 rule), and must NOT be
        #: folded; inside the directive's own RHS it means an earlier
        #: constant, which is that directive's grammar.
        self._in_constant_rhs: bool = False
        self._lossy: list[str] = []
        self._all_lossy: list[str] = []
        self._all_warnings: list[str] = []
        # Top-level statement currently being converted. The provably-list
        # analysis behind the negated-membership refusal is CLAUSE-LOCAL: it
        # reads only this statement's own AST, never other clauses.
        self._current_stmt: python_ast.stmt | None = None
        self._provable_lists: set[str] | None = None

    def _meta_predicate_directives(self, seen_order: list[tuple[str, int]],
                                   defined: set[tuple[str, int]]) -> list[PDirective]:
        """Build the `:- meta_predicate` directives for this module.

        Per-argument union of two sources, under ONE contract shared with
        :func:`collect_local_meta_modes` and the exporter's fixpoint: a position with
        ANY goal evidence is annotated -- with its call arity when that is
        single-valued, else with :data:`MODE_MODULE_SENSITIVE` -- and a position with
        NO goal evidence is emitted as `?`, never guessed. Two sources that disagree
        make the position module-sensitive rather than letting either win, which is
        what makes the shipped behaviour equal the documented one: an earlier draft
        used `setdefault` here, and body-local evidence quietly reinstated a position
        the fixpoint had deliberately left alone.

        `?` is the LOUD outcome: a bare reference consumed at an unannotated position
        raises existence_error at the call site. A guessed mode is the quiet one, and
        would module-qualify a term that may not be a goal at all.

        Emitted in first-appearance order, like the discontiguous pass, so the output
        is byte-stable across runs.
        """
        local = collect_local_meta_modes(PModule(tuple(self._items)))
        supplied = (self.meta_modes or {}).get(self.module_path or "", {})

        merged: dict[tuple[str, int], dict[int, int | str]] = {
            key: dict(positions) for key, positions in local.items()
        }
        for key, modes in supplied.items():
            slot = merged.setdefault(key, {})
            for index, mode in enumerate(modes):
                if mode is None:
                    continue
                previous = slot.get(index, mode)
                slot[index] = mode if previous == mode else MODE_MODULE_SENSITIVE

        already = set()
        for item in self._items:
            already |= _existing_meta_predicate_indicators(item)

        directives: list[PDirective] = []
        for name, arity in seen_order:
            key = (name, arity)
            positions = merged.get(key)
            if not positions or arity == 0 or key in already or key not in defined:
                continue
            args = tuple(
                _mode_term(positions[index]) if index in positions else PAtom("?")
                for index in range(arity)
            )
            directives.append(
                PDirective(PCompound("meta_predicate", (PCompound(name, args),))))
        return directives

    def _add_warning(self, construct: str) -> None:
        """Record an untranslatable construct warning."""
        self._warnings.append(construct)
        self._all_warnings.append(construct)

    def _add_lossy(self, construct: str) -> None:
        """Record a lowering that SUCCEEDED but dropped information."""
        self._lossy.append(construct)
        self._all_lossy.append(construct)

    @staticmethod
    def _call_target_diagnosis(node: python_ast.Call) -> str:
        """Name the COMPOUND UNIT case instead of the generic refusal.

        ``5(m/s)`` and ``10(m**2)`` are a documented Clausal surface form
        (docs/units.md, "Two syntactic styles") whose argument is a BinOp
        rather than a bare unit atom, so the quantity lowering does not accept
        them. They fail SAFE -- refused, never mis-lowered -- but the generic
        "unsupported call target: 5" sends a reader hunting for a bug in a
        number. Say what it actually is.
        """
        func = node.func
        if (isinstance(func, python_ast.Constant)
                and isinstance(func.value, (int, float))
                and not isinstance(func.value, bool)
                and len(node.args) == 1 and not node.keywords):
            return ("compound unit expression: "
                    f"{python_ast.unparse(node)} -- only a bare unit atom is "
                    "lowered (the magnitude is kept, the unit discarded); a "
                    "unit built with operators is not")
        return f"unsupported call target: {python_ast.unparse(func)}"

    def _try_quantity(self, node: python_ast.Call):
        """Clausal Quantity literal -> its bare magnitude, unit DISCARDED.

        ``5000(euro)``, ``0(baht)``, ``DEPOSIT(baht)`` are Quantity literals:
        a magnitude applied to a unit atom. They are NOT terms — a quantity is
        a value with a unit, represented at the Python level — and ISO Prolog
        cannot represent one: a number may not be a functor, and evaluable
        functors are a closed set, so a term-shaped money value could not use
        ``is/2`` even if it parsed (Scryer: ``type_error(evaluable, euro/1)``).

        Carrying units into ISO would mean a quantity class plus our own
        arithmetic on every site that might touch one, which loses CLP(Z) and
        every other facility defined over ordinary numbers. So the export drops
        the unit and keeps the magnitude. Dimensional analysis stays where it
        works: the Clausal runtime. Operator ruling 2026-09-08.

        THE TRANSLATION IS THEREFORE LOSSY. Recorded via _add_lossy, not
        _add_warning: these lower cleanly and must not make strict mode raise.
        Each discard is echoed as a `%` LINE comment above the clause, so a
        reader can still see what Clausal treated the value as. Line, not
        block: `%` is the portable comment form, and it cannot sit inline
        because it would swallow the rest of the clause.

        PRECONDITION -- the export is sound only for DIMENSIONALLY VALID
        sources. Discarding units loses a safety property, not just detail:
        ``5000(euro) + 3000(baht)`` is a UnitsMismatch in Clausal but exports
        as ``5000 + 3000`` and yields 8000. The export does NOT re-check
        dimensions; run the source under Clausal first. _check_unit_mixing is
        a cheap syntactic guard over the obvious case, not a replacement for
        that check.

        SCOPE -- only the arity-1 shape whose argument is a bare unit atom.
        ``5(m/s)`` and ``10(m**2)`` (compound units) are refused with a
        specific diagnosis; ``5(THING)`` and ``5(euro, baht)`` are refused too.
        """
        if node.keywords or len(node.args) != 1:
            return None
        unit = node.args[0]
        if isinstance(unit, python_ast.Attribute):
            # A QUALIFIED unit atom -- `united_states.usd`, the spelling the
            # table-directive expansion produces because the declaration names
            # its unit through the importing module. `_unit_leaf_names` has
            # always resolved this shape ("a qualified european_union.euro
            # contributes euro"); this lowering did not, so a qualified unit
            # was refused as a "compound unit expression" and took its whole
            # module down with it. The two now agree, which is the point: one
            # notion of what a unit atom is, not two that differ by a dot.
            unit = python_ast.Name(id=unit.attr, ctx=python_ast.Load())
        if not isinstance(unit, python_ast.Name) or _is_var_in_name_position(unit.id):
            # A unit is a NAME position -- the same argument as the callable
            # and the qualified-name cases.  Asking the LEXICAL rule here
            # made the still-supported ``-import_from(py.units, [Metre])``
            # spelling stop lowering: ``_try_quantity`` returned None and the
            # clause exported as the unrepresentable ``X = ???(_Metre)``
            # under a bogus "compound unit expression" refusal -- a working
            # quantity silently exported as something else.
            return None
        func = node.func
        if isinstance(func, python_ast.Constant) and isinstance(
                func.value, (int, float)) and not isinstance(func.value, bool):
            self._refuse_scaled_unit(node, unit.id)
            self._add_lossy(f"unit discarded: {func.value}({unit.id}) -> {func.value}")
            return PNumber(func.value, unit=unit.id)
        if isinstance(func, python_ast.Name) and _is_var_in_name_position(func.id):
            self._refuse_scaled_unit(node, unit.id)
            self._add_lossy(f"unit discarded: {func.id}({unit.id}) -> {func.id}")
            lowered = self._convert_expr(func)
            return (PVar(lowered.name, unit=unit.id)
                    if isinstance(lowered, PVar) else lowered)
        return None

    def _refuse_scaled_unit(self, node, unit_name: str) -> None:
        """Refuse an inline quantity whose unit carries a FACTOR.

        The SECOND shape a minor-unit amount takes: `pay(155000(cent))`
        reaches this lowering rather than `_collect_constant`, and dropping
        the unit keeps the WRITTEN magnitude, not the one the engine holds
        once a unit rescales. Refusing one shape and not the other would
        leave a hole in the middle of the guarantee (corpus-lane,
        2026-09-11).

        Called only once the node is known to BE a quantity -- an ordinary
        call like `implements(k1)` reaches `_try_quantity` too and leaves by
        the `return None` below, so a check placed before that returns a
        refusal for every one-argument predicate call in the corpus.
        """
        if _is_known_scaled_unit(unit_name):
            raise NotImplementedError(
                f"clausal_to_prolog: {python_ast.unparse(node)} is a quantity "
                f"in a scaled unit ({unit_name}), and units are discarded on "
                f"export -- which keeps the written magnitude, not the one "
                f"the engine holds once a unit rescales. Write the amount in "
                f"a base unit, or fix the exporter to convert to the base "
                f"magnitude; see todo/exporter-folds-scaled-units-to-the-"
                f"wrong-magnitude-2026-09-11.md")

    def _collect_unit_atoms(self, tree: python_ast.Module) -> None:
        """Pre-pass: every unit atom named by a Quantity literal in this module.

        Needed because -import_from(european_union, [euro]) is converted BEFORE
        the clause that reveals `euro` is a unit rather than a predicate. Once
        the unit is discarded from every use site, that import names a symbol
        the emitted program never mentions, in a module the export never stages
        -- so it must go too, or the file trades an "unsupported call target"
        refusal for an "unresolvable use_module target" one.
        """
        for node in python_ast.walk(tree):
            if not isinstance(node, python_ast.Call):
                continue
            if node.keywords or len(node.args) != 1:
                continue
            unit = node.args[0]
            if not isinstance(unit, python_ast.Name) or _is_var_in_name_position(unit.id):
                continue
            func = node.func
            if (isinstance(func, python_ast.Constant)
                    and isinstance(func.value, (int, float))
                    and not isinstance(func.value, bool)):
                self._unit_atoms.add(unit.id)
            elif isinstance(func, python_ast.Name) and _is_var_in_name_position(func.id):
                self._unit_atoms.add(unit.id)

    @staticmethod
    def _quantity_unit(node) -> str | None:
        """The unit atom of a Quantity literal, else None."""
        if not isinstance(node, python_ast.Call) or node.keywords \
                or len(node.args) != 1:
            return None
        unit = node.args[0]
        if not isinstance(unit, python_ast.Name) or _is_var_in_name_position(unit.id):
            return None
        func = node.func
        if (isinstance(func, python_ast.Constant)
                and isinstance(func.value, (int, float))
                and not isinstance(func.value, bool)):
            return unit.id
        if isinstance(func, python_ast.Name) and _is_var_in_name_position(func.id):
            return unit.id
        return None

    def _check_unit_mixing(self, stmt) -> None:
        """Refuse an arithmetic expression mixing two DIFFERENT units.

        Discarding units does not merely lose detail, it loses a SAFETY
        PROPERTY: ``5000(euro) + 3000(baht)`` is a UnitsMismatch in Clausal but
        would export as ``5000 + 3000`` and quietly yield 8000 -- a dimensional
        error becoming a silent wrong answer in a program that runs clean.

        The export is therefore sound only for DIMENSIONALLY VALID sources; it
        does not re-derive Clausal's unit checking. This guard is the cheap
        syntactic half of that precondition: it catches the obvious case and
        cannot fire on input Clausal itself would accept, because Clausal
        rejects mixed units in one arithmetic expression too.

        KNOWN LIMIT -- IT IS NOT A DIMENSIONAL CHECK. It reads the DIRECT
        operands of a +/- node, so a unit nested under another operator is
        invisible to it:

            5000(euro) + 3000(baht)       refused
            5000(euro) + 3000(baht) * 2   NOT refused -- exports as 5000 + 3000 * 2

        Catching that needs the unit of each operand SUBTREE, i.e. real
        dimension inference, which is deliberately out of scope: `*` and `/`
        legitimately combine different units (m/s), so a naive "all units in
        this expression must agree" rule would reject valid input. Deciding
        which of those is which is exactly the job Clausal's runtime already
        does, and the reason the precondition above exists. Pinned in
        tests/test_prolog_quantity_units.py so nobody reads this guard as a
        complete check.
        """
        for node in python_ast.walk(stmt):
            if not isinstance(node, python_ast.BinOp):
                continue
            if not isinstance(node.op, (python_ast.Add, python_ast.Sub)):
                continue          # only +/- require matching dimensions
            units = {u for side in (node.left, node.right)
                     if (u := self._quantity_unit(side)) is not None}
            if len(units) > 1:
                self._add_warning(
                    "mixed units in one arithmetic expression: "
                    + " vs ".join(sorted(units))
                    + " -- units are discarded on export, so this would become "
                      "a silent wrong answer instead of a dimensional error")

    def convert_module(self, tree: python_ast.Module) -> PModule:
        """Convert a full Python AST Module to a PModule."""
        self._collect_unit_atoms(tree)
        for stmt in tree.body:
            self._warnings.clear()
            self._lossy.clear()
            self._check_unit_mixing(stmt)
            self._current_stmt = stmt
            self._provable_lists = None
            item = self._convert_stmt(stmt)
            # Emit any warnings accumulated during conversion
            for w in self._warnings:
                self._items.append(PComment(
                    f"WARNING: untranslatable clausal construct: {w}\n"
                    f"   Replace with Prolog equivalent manually."
                ))
            if item is not None:
                if isinstance(item, list):
                    self._items.extend(_prefix_singletons(i) for i in item)
                else:
                    self._items.append(_prefix_singletons(item))

        # Post-pass: (1) keep only locally-defined predicates in :- module
        # exports. Scryer raises permission_error(...
        # module_does_not_contain_claimed_export...) on an export with no
        # backing clause (signature-only kernels, term constructors like
        # cite/1, 0-arity atoms), so a name only ever *declared* in the
        # export list must not survive into the emitted directive.
        # (2) emit :- discontiguous(Name/Arity) for every predicate whose
        # clause run is interrupted by another item — Scryer treats an
        # interrupted run as a silent redefinition, so leaving it unmarked
        # is a correctness hazard, not a style nicety.
        defined: set[tuple[str, int]] = set()
        existing_discontiguous: set[tuple[str, int]] = set()
        seen_order: list[tuple[str, int]] = []   # first-appearance order
        seen_set: set[tuple[str, int]] = set()
        interrupted: set[tuple[str, int]] = set()
        last_key: tuple[str, int] | None = None
        for item in self._items:
            dcg_key = _dcg_head_key(item)
            if dcg_key is not None:
                defined.add(dcg_key)

            existing_discontiguous |= _existing_discontiguous_indicators(item)

            # Run-tracking covers both PClause and PDCGRule (+2 arity) —
            # an interrupted DCG rule run is the same Scryer silent-
            # redefinition hazard as an interrupted plain clause run.
            key = _run_key(item)
            if key is None:
                continue
            defined.add(key)  # no-op when this is the dcg_key already added above
            if key != last_key and key in seen_set:
                interrupted.add(key)
            if key not in seen_set:
                seen_order.append(key)
                seen_set.add(key)
            last_key = key

        discontiguous_directives = [
            PDirective(PCompound("discontiguous", (
                PCompound("/", (PAtom(name), PNumber(arity))),
            )))
            for name, arity in seen_order
            if (name, arity) in interrupted and (name, arity) not in existing_discontiguous
        ]

        # (3) emit :- meta_predicate(Name(Mode, ...)) for every locally-defined
        # predicate with a known meta position. Scryer resolves a meta-call in the
        # CALLEE's module, so a bare predicate reference handed to a higher-order
        # predicate raises existence_error without this -- even same-module (the
        # design note's §3.2/§3.3, both measured in Scryer). Two sources, unioned
        # per argument: body-local evidence read off the clauses being emitted, and
        # the caller-supplied map for positions no single module can see.
        meta_directives = self._meta_predicate_directives(seen_order, defined)

        # (4) For an `expansion` dialect, the emitted file must pull in the
        # term_expansion prelude, or its `:- constant_number_units(...)` lines
        # are unknown directives and the declarations vanish. Emitted ONLY when
        # this file actually declares a constant -- a prelude import in every
        # file would be noise in 1560 of them.
        #
        # The `discontiguous` declarations go with it because the expansion
        # emits facts under the public names directly, and a file's constant
        # declarations are not guaranteed to be contiguous in the output.
        prelude_directives: list = []
        if self._emitted_arrow_lambda:
            # `\\`/`^` are library(lambda)'s operators; without the import the
            # file is a syntax error rather than a wrong answer. Both reference
            # engines ship it and export the SAME list (measured 2026-09-14).
            #
            # THE IMPORT LIST IS EXPLICIT ON PURPOSE, and a listless
            # `use_module(library(lambda))` is a real defect rather than a
            # tidier spelling: a consumer that decides whether a predicate is
            # already supplied cannot see inside a library, so a listless
            # import reads as "this might supply anything" and suppresses
            # every other library import that file needed. Measured while
            # building this: one listless line silently removed the
            # `library(dif)` import from a module that calls `dif/2`, and the
            # module then failed at CALL time with existence_error — never at
            # consult time.
            lambda_exports = (
                [PCompound("/", (PAtom("\\"), PNumber(n))) for n in range(1, 9)]
                + [PCompound("/", (PAtom("^"), PNumber(n))) for n in range(3, 11)])
            prelude_directives.append(PDirective(PCompound(
                "use_module", (PCompound("library", (PAtom("lambda"),)),
                               PList(tuple(lambda_exports))))))
        clp_ops = [op for op, used in (("#=", self._emitted_clp_arith_eq),
                                       ("#\\=", self._emitted_clp_arith_neq))
                   if used]
        if clp_ops and self.dialect.clpfd_needs_import:
            # THE INDICATOR IS PARENTHESISED ON PURPOSE. An import-list item is
            # read as a TERM, and `#=` is an operator in every system that has
            # it, so `[#=/2]` is a SYNTAX ERROR and the file does not consult.
            # `[(#=)/2]` is what both ladder engines accept. Alphanumeric names
            # are left bare -- `[(dif)/2]` parses but reads as a mistake.
            #
            # The list is EXPLICIT for the same reason library(lambda)'s is: a
            # consumer deciding whether a predicate is already supplied cannot
            # see inside a library, so a listless import reads as "this might
            # supply anything" and suppresses every other import the file needs.
            prelude_directives.append(PDirective(PCompound(
                "use_module", (PCompound("library", (PAtom(self.dialect.clpfd_module),)),
                               PList(tuple(PCompound("/", (PAtom(op), PNumber(2)))
                                           for op in clp_ops))))))
        prelude = getattr(self.dialect, "constants_prelude", None)
        if prelude is not None and self._emitted_constant_declaration:
            load, prelude_module = prelude
            prelude_directives.append(
                PDirective(PCompound(load, (PAtom(prelude_module),))))
            for functor, arity in (("constant_number_units", 3),
                                   ("module_constant_units", 4),
                                   ("constant_value", 2),
                                   ("module_constant", 3)):
                prelude_directives.append(PDirective(PCompound(
                    "discontiguous",
                    (PCompound("/", (PAtom(functor), PNumber(arity))),))))

        # Only the `:- module` directive moves: it goes FIRST. Everything the
        # source wrote above it keeps its relative order, still ahead of the
        # generated prelude, exactly as before -- only the module line changes
        # position. Measured 2026-09-26 on both engines, a library imported via
        # use_module, each item placed ABOVE vs BELOW `:- module`:
        #
        #   meta_predicate    above: Scryer ok, Trealla a caller-module goal
        #                     FAILS silently.            below: both ok
        #   op/3 (body use)   above: Trealla syntax_error. below: both ok
        #   op/3 (exported)   above: BOTH syntax_error.   below: both ok
        #   use_module        above: Scryer existence_error. below: both ok
        #   double_quotes     either: both ok
        #
        # So nothing is known to need to precede `:- module`, and three things
        # are known to break there. A meta_predicate written above -module thus
        # lands below the module line but AHEAD of the generated prelude (clpz,
        # library(lambda)). Measured 2026-09-26 on Scryer and Trealla: a library
        # imported via use_module, its meta declarations placed ahead of vs
        # behind the clpz + library(lambda) imports, exercised by a
        # caller-module goal through a 1-meta and a 2-meta, a library(lambda)
        # `\X^Goal` passed through the meta predicate, and #= in the body --
        # identical answers in both positions on both engines.
        module_item: PItem | None = None
        before_module: list[PItem] = []
        rest: list[PItem] = []
        for item in self._items:
            if _is_module_directive(item):
                # EVERY module directive is filtered, as it always was; a
                # second one stays where it was written (no generated block is
                # repeated after it -- two module directives is not a valid
                # file on either engine whatever follows them).
                filtered = _filter_module_exports(item, defined)
                if module_item is None:
                    module_item = filtered
                else:
                    rest.append(filtered)
            elif module_item is None:
                before_module.append(item)
            else:
                rest.append(item)
        generated = prelude_directives + meta_directives + discontiguous_directives
        if module_item is None:
            self._items = generated + before_module
        else:
            self._items = [module_item] + before_module + generated + rest

        # A hand-written `-meta_predicate(a(...), b(...))` reaches here as N
        # arguments; both engines need one directive PER SPEC. Normalised at the
        # last moment so every path that can put such a directive in _items is
        # covered, rather than only the one that was noticed.
        self._items = [out for item in self._items
                       for out in _split_meta_predicate_directive(item)]

        if self.strict and self._all_warnings:
            raise UntranslatableConstructError(list(self._all_warnings))
        return PModule(tuple(self._items))

    def _convert_stmt(self, stmt) -> PItem | list[PItem] | None:
        """Convert a top-level statement to PItem(s).

        FAIL-CLOSED NET: every exit path below either returns a PItem(s) it
        produced, or calls ``_add_warning`` before returning None. There is
        no bare ``return None`` left in this method — an unrecognized
        top-level shape must never vanish silently (strict mode is the only
        thing standing between a translation bug and a corpus that looks
        clean while dropping clauses; see the 2026-09 rule-drop incident).
        """
        if not isinstance(stmt, python_ast.Expr):
            self._add_warning(
                "unsupported top-level statement (not an expression): "
                f"{type(stmt).__name__}"
            )
            return None

        value = stmt.value

        # -directive(...): unary minus on a call, or the bare -name form.
        # Directives are a fully recognized construct that can legitimately
        # emit nothing (a dialect-gated skip, e.g. GNU Prolog has no module
        # system; or -private(...), which has no Prolog emission at all) —
        # so they are dispatched via _try_convert_directive, exempt from
        # the fail-closed net's warning, both here AND inside a
        # comma-joined statement tuple below (a directive's translation
        # does not depend on whether a trailing comma put it next to
        # sibling statements — same uniformity argument as
        # _convert_clause_value).
        handled, item = self._try_convert_directive(value)
        if handled:
            return item

        # Trailing-comma statement(s): Foo(1, 2), or a comma-joined run of
        # facts/rules/directives sharing one Python statement:
        # Foo(1, 2), Bar(x) <- (...), -dynamic(baz/1),
        # A 1-tuple is the common case (one fact, or — the bug this comment
        # marks the fix for — one `<-` RULE, both followed by the ordinary
        # fact-separator comma); a multi-element tuple is the same AST shape
        # for several comma-joined statements on one line. Every element is
        # dispatched through _try_convert_directive then _convert_clause_value
        # so a rule (or directive) in ANY tuple position translates
        # identically to an unwrapped one.
        if isinstance(value, python_ast.Tuple):
            if not value.elts:
                # `()` as a bare statement -- Expr(Tuple([])). Not a fact,
                # not a rule, not anything: previously fell straight
                # through to `return items or None` with an empty list,
                # silently. There is no legitimate empty-tuple statement.
                self._add_warning("empty tuple statement: ()")
                return None
            items: list[PItem] = []
            for elt in value.elts:
                elt_handled, elt_item = self._try_convert_directive(elt)
                if not elt_handled:
                    elt_item = self._convert_clause_value(elt)
                if elt_item is None:
                    if not elt_handled:
                        self._add_warning(
                            "unsupported statement in comma group: "
                            f"{python_ast.unparse(elt)}"
                        )
                    continue
                if isinstance(elt_item, list):
                    items.extend(elt_item)
                else:
                    items.append(elt_item)
            return items or None

        item = self._convert_clause_value(value)
        if item is not None:
            return item

        self._add_warning(
            f"unsupported top-level statement: {python_ast.unparse(value)}"
        )
        return None

    def _try_convert_directive(self, value) -> tuple[bool, PItem | list[PItem] | None]:
        """Recognize and dispatch a `-directive(...)` / bare `-name` shape.

        Returns ``(True, item)`` when *value* IS a directive shape (`item`
        may legitimately be ``None`` — a dialect-gated skip, ``-private``,
        ``-strict_atoms`` — none of that is a fail-closed-net violation),
        or ``(False, None)`` when *value* is not a directive at all, in
        which case the caller must try ``_convert_clause_value`` and warn
        if THAT also fails to recognize it. Shared by ``_convert_stmt``'s
        bare-statement case and its comma-joined-tuple case so a directive
        translates the same whether or not it shares a Python statement
        with sibling facts/rules.
        """
        if isinstance(value, python_ast.UnaryOp) and isinstance(value.op, python_ast.USub):
            operand = value.operand
            if isinstance(operand, python_ast.Call) and isinstance(operand.func, python_ast.Name):
                return True, self._convert_directive(operand)
            # -strict_atoms: a parenless, argument-less
            # directive (UnaryOp(USub(Name)), not Call) — engine-only atom-
            # resolution bookkeeping with no Prolog equivalent, same
            # legitimately-silent category as -private(...) above. 523
            # corpus sites (2026-09 rule-drop census) would otherwise all
            # start refusing under strict once the fail-closed net below
            # stopped exempting unrecognized UnaryOp shapes.
            if isinstance(operand, python_ast.Name):
                return True, self._convert_bare_directive(operand.id)
        return False, None

    def _convert_clause_value(self, value) -> PItem | list[PItem] | None:
        """Convert one fact/rule/DCG-rule expression.

        Used both for a bare top-level statement and for each element of a
        comma-joined statement tuple (see _convert_stmt) — the same
        dispatch either way, so a rule's position relative to a trailing
        comma or sibling statements never changes how it translates.

        Returns None when *value* matches none of the recognized clause
        shapes; the caller is responsible for warning in that case (this
        method never emits nothing without a caller-visible signal).
        """
        # Bare fact (no trailing comma): Foo(1, 2)
        if isinstance(value, python_ast.Call):
            head = self._convert_head(value)
            return PClause(head)

        # Bare 0-arity fact with no parens at all: foo, / foo -- the engine
        # compiles this to Clause(head=foo, body=[True]) (a real fact, not
        # a reference), and the corpus uses it deliberately (e.g.
        # "explicit facts for conformance" for profile-key atoms later
        # used only as data elsewhere) -- same PAtom the parenthesized
        # 0-arg spelling already produces via _convert_head.
        if isinstance(value, python_ast.Name):
            functor = resolve_name(value.id, self.dialect)
            return PClause(PAtom(functor))

        # head <- body (Compare with Lt followed by USub)
        if isinstance(value, python_ast.Compare):
            arrow = self._detect_arrow(value)
            if arrow is not None:
                head_ast, body_ast = arrow
                head = self._convert_head(head_ast)
                outer_head_vars = self._enclosing_head_vars
                self._enclosing_head_vars = _variable_names(head_ast)
                try:
                    body = self._convert_expr(body_ast, goal_position=True)
                finally:
                    self._enclosing_head_vars = outer_head_vars
                return PClause(head, body)
            return None

        # head >> body (DCG rule — RShift)
        if (isinstance(value, python_ast.BinOp)
                and isinstance(value.op, python_ast.RShift)):
            head = self._convert_expr(value.left)
            body = self._convert_dcg_body(value.right)
            return PDCGRule(head, body)

        return None

    def _detect_arrow(self, compare: python_ast.Compare):
        """Detect <- pattern in a Compare node."""
        if not compare.ops or not isinstance(compare.ops[0], python_ast.Lt):
            return None
        first_comp = compare.comparators[0]
        usub_node, depth = _leftmost_usub(first_comp)
        if usub_node is None:
            return None
        if depth > 0 or len(compare.ops) > 1:
            return None
        return compare.left, usub_node.operand

    def _convert_bare_directive(self, name: str) -> PItem | list[PItem] | None:
        """Convert a parenless, argument-less directive: ``-strict_atoms``.

        These are clausal-engine-only bookkeeping (atom-resolution mode)
        with no Prolog equivalent — always a legitimate no-op, not an
        unrecognized shape, so this does NOT fall through to the
        fail-closed net's warning. An actually-unknown bare directive
        still warns below: only the names the engine itself recognizes
        (clausal/reflection.py's StrictAtomsDeclaration) are exempted.
        (-implicit_atoms was removed; the engine refuses it at load.)
        """
        if name == "strict_atoms":
            return None
        self._add_warning(f"-{name}")
        return None

    def _convert_directive(self, call: python_ast.Call) -> PItem | list[PItem] | None:
        """Convert a -directive(...) call."""
        name = call.func.id

        if name == "module":
            if self.dialect.module_system == "none":
                # GNU Prolog has no module system — skip module declarations
                return None
            return self._convert_module_directive(call)
        if name == "import_from":
            if self.dialect.module_system == "none":
                # GNU Prolog: library predicates are built-in, no import needed
                return None
            return self._convert_import_from(call)
        if name == "import_module":
            if self.dialect.module_system == "none":
                return None
            return self._convert_import_module(call)
        if name == "private":
            # Private is not emitted in Prolog (module exports handle visibility)
            return None
        if name == "double_quotes":
            return self._convert_double_quotes_directive(call)
        if (name == "set_prolog_flag" and len(call.args) == 2
                and isinstance(call.args[0], python_ast.Name)
                and call.args[0].id == "assert_creates_dynamic"):
            # Clausal's own flag: ISO Prolog's assert already creates a
            # missing procedure as dynamic (7.5.2(2)), which is what ``true``
            # selects, so there is nothing to emit; and the reference systems
            # do not know the flag, so writing it would be a load error there.
            return None
        if name in ("constant_value", "constant_number_units",
                    "constant_number_currency"):
            self._collect_constant(name, call)
            return None          # folded at the use sites; nothing to emit
        if name in ("constants",):
            # The eventual answer is `constant_value/2` -- Markus Triska's
            # name for the cross-implementation convention -- emitted either
            # as the declared LITERAL (runs anywhere, needs no prelude) or
            # as the operator form with an expansion prelude. Neither is
            # built, and the packaging of the prelude is unsolved in both
            # reference systems, so this still refuses rather than emitting
            # something that parses and does not run. See
            # todo/retire-underscore-constants-for-an-iso-safe-surface-
            # 2026-09-10.md.
            raise NotImplementedError(
                f"clausal_to_prolog: -{name} files are not translatable "
                "yet — a constant must export as its literal value or "
                "through a constant_value/2 expansion prelude; see "
                "todo/retire-underscore-constants-for-an-iso-safe-surface"
                "-2026-09-10.md")
        if name in ("dynamic", "discontiguous", "table"):
            return self._convert_meta_directive(name, call)
        # Generic directive
        args = tuple(self._convert_expr(a) for a in call.args)
        return PDirective(PCompound(name, args))

    def _convert_double_quotes_directive(self, call: python_ast.Call) -> PDirective | None:
        """``-double_quotes(atom|chars)`` -- the strings-migration RATCHET
        (todo/strings-lost-in-the-atom-pivot-...md, ruling R-S4), mirrored
        from the compiler's ``_handle_double_quotes_directive``: it sets the
        mode for every literal BELOW it (see ``_convert_str_literal``).

        Emission: ``chars`` becomes ``:- set_prolog_flag(double_quotes,
        chars).`` -- the ISO spelling (7.11.2.5). NOT ``:- double_quotes(chars).``:
        Scryer refuses that at load (``domain_error(directive,
        double_quotes/1)``) and Trealla warns, so under G2's warnings-as-errors
        consult every chars-mode module would fail on both engines (measured
        2026-09-07). Both engines already default to chars, so the flag is a
        statement of the module's dependency rather than a change of state.
        ``atom`` emits nothing: every literal below it is emitted as an atom,
        so the target engine has no string to misread. ``codes`` is refused
        exactly as the compiler refuses it (codes are spelled ``b"..."``).

        Since the engine default flipped to ``chars`` (2026-09-26) a file
        that opens with ``-double_quotes(chars)`` says what a file that
        declares nothing already says; the flag is STILL emitted for it --
        the directive is a statement of the module's dependency, and the
        emission stays a faithful transcription of the source rather than
        of the walk state (pinned by tests/test_prolog_literal_rule.py).
        """
        args = call.args
        if len(args) != 1 or not isinstance(args[0], python_ast.Name):
            raise SyntaxError(
                "-double_quotes takes exactly one bare argument: "
                "-double_quotes(atom) or -double_quotes(chars)")
        mode = args[0].id
        if mode not in ("atom", "chars"):
            raise SyntaxError(
                f"-double_quotes({mode}) is not a clausal mode: use atom or "
                f"chars (codes are spelled b\"...\")")
        self._double_quotes = mode
        if mode == "atom":
            return None
        return PDirective(PCompound("set_prolog_flag",
                                    (PAtom("double_quotes"), PAtom("chars"))))

    def _convert_module_directive(self, call: python_ast.Call) -> PDirective:
        """Convert -module(name, [exports]).

        Every export spelling the engine reads (term_rewriting's
        ``_handle_module_directive`` / ``_predicate_export_spec``) crosses:

        * the ISO predicate indicator ``edge/2`` -> ``edge/2``;
        * a call template ``edge(A, B)`` -> ``edge/2``;
        * a bare name ``edge`` -> ``edge/0``;
        * the QUOTED forms of the first two, ``'Edge'/2`` and ``'edge'(A, B)``.
          A capital-initial predicate can only be written quoted -- bare
          ``Edge`` is a logic variable -- and a quoted name crosses AS WRITTEN,
          never through the snake-case name mapping. Accepted exactly when the
          ENGINE accepts it (``_quoted_export_name``): never double-quoted, in
          any mode, and a plain name. A quoted template's keyword arguments
          count toward its arity, as in the engine; a BARE template with
          keyword arguments is refused, as in the engine.

        Anything else is REFUSED. It used to be dropped without a word, so the
        module's export list silently shrank.

        What the engine DECLARES by each spelling differs, and the export does
        not carry that difference: under R6/R6b a bare name or call template
        with NO clauses in the file is DATA (an atom, a data functor), while
        ``name/arity`` always declares a procedure. The export keeps an entry
        only when the file defines clauses at that name/arity
        (``_filter_module_exports``), which is exactly the engine's rule for
        when a data-spelled entry is in fact a predicate (measured on the
        engine 2026-09-26: an exported call template or bare name WITH clauses
        is ``declared_kind == predicate`` and an importer's call resolves it).
        So data exports never reach the Prolog -- ISO terms need no export --
        and every export that does is a predicate on both sides.
        """
        mod_name = self._get_string_or_name(call.args[0])
        self._module_name = mod_name
        exports = []
        if len(call.args) > 1 and isinstance(call.args[1], python_ast.List):
            for elt in call.args[1].elts:
                reserved = _reserved_truth_export_name(elt)
                if reserved is not None:
                    raise NotImplementedError(
                        f"clausal_to_prolog: -module({mod_name}, [...]) cannot export "
                        f"`{reserved}`: the truth values True, False and Undefined "
                        "(aliases true, false, undefined) are builtins, not predicates "
                        "-- the engine refuses to declare them. Rename it.")
                if (isinstance(elt, python_ast.Call) and isinstance(elt.func, python_ast.Name)
                        and not elt.keywords):
                    # A bare template with keyword arguments is REFUSED by the
                    # engine ("written with keyword arguments"), so it falls
                    # through to the refusal below rather than being counted.
                    functor = resolve_name(elt.func.id, self.dialect)
                    arity = len(elt.args)
                    exports.append(PCompound("/", (PAtom(functor), PNumber(arity))))
                elif isinstance(elt, python_ast.Name):
                    functor = resolve_name(elt.id, self.dialect)
                    exports.append(PCompound("/", (PAtom(functor), PNumber(0))))
                elif (isinstance(elt, python_ast.BinOp) and isinstance(elt.op, python_ast.Div)
                      and isinstance(elt.left, python_ast.Name)
                      and isinstance(elt.right, python_ast.Constant)
                      and type(elt.right.value) is int and elt.right.value >= 0):
                    functor = resolve_name(elt.left.id, self.dialect)
                    exports.append(PCompound("/", (PAtom(functor), PNumber(elt.right.value))))
                elif (isinstance(elt, python_ast.BinOp) and isinstance(elt.op, python_ast.Div)
                      and self._quoted_export_name(elt.left) is not None
                      and isinstance(elt.right, python_ast.Constant)
                      and type(elt.right.value) is int and elt.right.value >= 0):
                    exports.append(PCompound("/", (
                        PAtom(self._quoted_export_name(elt.left)), PNumber(elt.right.value))))
                elif (isinstance(elt, python_ast.Call)
                      and self._quoted_export_name(elt.func) is not None):
                    # The engine counts keyword arguments into the arity here:
                    # 'Edge'(A, b=B) is declared Edge/2 (measured 2026-09-26,
                    # declared_kind('Edge', 2) == 'predicate').
                    exports.append(PCompound("/", (
                        PAtom(self._quoted_export_name(elt.func)),
                        PNumber(len(elt.args) + len(elt.keywords)))))
                else:
                    raise NotImplementedError(
                        f"clausal_to_prolog: -module({mod_name}, [...]) export "
                        f"`{python_ast.unparse(elt)}` is not an export element -- "
                        "write a call template `name(A, B)`, a predicate indicator "
                        "`name/2` (either may quote the name), or a bare name. It used to be dropped silently, "
                        "exporting less than the source declares.")
        # F4 (2026-09-29): each Name/Arity once, first occurrence kept --
        # `p(X)` and `p/1` are the same export, and so is a repeated entry.
        unique, seen = [], set()
        for exp in exports:
            key = (exp.args[0].name, exp.args[1].value)
            if key not in seen:
                seen.add(key)
                unique.append(exp)
        export_list = PList(tuple(unique))
        return PDirective(PCompound("module", (PAtom(mod_name), export_list)))

    def _quoted_export_name(self, node) -> str | None:
        """The functor a QUOTED export name denotes, or None -- the ENGINE's rule.

        Mirrors term_rewriting's ``_quoted_head_functor_name`` /
        ``_refuse_double_quoted_functor``, which a quoted ``-module`` entry
        goes through (``_resolved_export_spec``), so the exporter accepts
        exactly what the engine accepts:

        * a name whose quote is KNOWN to be ``"`` is refused in EVERY
          -double_quotes mode (ISO 6.3.3: a double-quoted literal is never an
          atom spelling). An UNKNOWN quote (no source lines) is accepted, as
          the engine accepts it;
        * the spelling must be a plain name -- ``str.isidentifier()`` and not a
          Python keyword -- because the engine binds a declared functor as a
          module-level name. ``'foo bar'`` and ``'class'`` are refused.

        The -double_quotes MODE plays no part. (The first version of this
        helper used the translator's literal rule, which is mode-sensitive,
        and so accepted ``"Edge"/2`` in atom mode where the engine refuses it.)
        """
        if not (isinstance(node, python_ast.Constant) and isinstance(node.value, str)):
            return None
        try:
            quote = quote_of(self._quote_map, node)
        except SyntaxError:
            # A mixed-quote literal (`'Ed' "ge"`) -- the engine refuses it too.
            # quote_of's own SyntaxError carries no position, so it is folded
            # into the export-element refusal, which names the element.
            return None
        if quote == '"':
            return None
        spelling = node.value
        if not spelling.isidentifier() or _keyword_module.iskeyword(spelling):
            return None
        return spelling

    def _module_reference(self, mod_path: str) -> PTerm | None:
        """The term naming *mod_path* in a use_module directive.

        Dialect libraries keep their ``library(name)`` form. Everything else
        is a file path with dots turned into slashes. Without ``module_path``
        that path is the dotted path verbatim. With it — the export-tree case
        — the libraries in :data:`_LIBRARY_REMAP` are first relocated to the
        root of the tree they are exported into, then the whole path is made
        relative to the consuming module's own package, because Scryer
        resolves a consulted path against the consulting file.

        Returns None when the relative path does not name a file: a consumer
        whose own package IS the target (``shared_lib.helper`` importing
        ``shared_lib``) relativizes to ``'.'``, and one nested inside it
        to ``'..'``. Both are directory references that Scryer cannot consult,
        so the import is recorded as an untranslatable construct instead —
        raising under strict, a warning comment otherwise — rather than
        emitting a path that only fails at load time.
        """
        library_name = self.dialect.library_map.get(mod_path)
        if library_name is not None:
            # Known library: parse "library(clpfd)" → library(clpfd).
            lib_inner = library_name[len("library("):-1]  # "clpfd"
            return PCompound("library", (PAtom(lib_inner),))

        if self.module_path is None:
            # Single-file use: absolute dotted path, unchanged.
            return PAtom(mod_path.replace(".", "/"), quoted=True)

        target = _LIBRARY_REMAP.get(mod_path, mod_path)
        consumer_pkg = "/".join(self.module_path.split(".")[:-1])
        prolog_path = posixpath.relpath(target.replace(".", "/"), consumer_pkg or ".")
        if posixpath.basename(prolog_path) in ("", ".", ".."):
            self._add_warning(
                f"unresolvable use_module path: consumer package "
                f"'{consumer_pkg}' shadows root target '{target}'"
            )
            return None
        return PAtom(prolog_path, quoted=True)

    def _import_list(self, mod_path: str, elts: list) -> list[PTerm] | None:
        """The import-list elements for -import_from(*mod_path*, [*elts*]).

        With no ``module_signatures`` the requested names are emitted as they
        always were (bare atoms, or Name/Arity when written with arguments).
        With signatures, each requested name is resolved the same way a
        predicate name is (PascalCase → snake_case, builtin remaps) and then
        looked up in the target's export set; names the target does not export
        — atoms, term constructors, signature-only predicates — are dropped,
        because Scryer raises at load time on an import it cannot satisfy.
        """
        requested: list[tuple[str, int | None]] = []
        for elt in elts:
            if isinstance(elt, python_ast.Call) and isinstance(elt.func, python_ast.Name):
                requested.append((resolve_name(elt.func.id, self.dialect), len(elt.args)))
            elif isinstance(elt, python_ast.Name):
                requested.append((resolve_name(elt.id, self.dialect), None))
            elif (isinstance(elt, python_ast.BinOp)
                  and isinstance(elt.op, (python_ast.Div, python_ast.FloorDiv))
                  and isinstance(elt.left, python_ast.Name)
                  and isinstance(elt.right, python_ast.Constant)
                  and type(elt.right.value) is int):
                # ``name/N`` (D20) is already the ISO indicator; ``name//N``
                # is the nonterminal, ``name/N+2``.
                extra = 2 if isinstance(elt.op, python_ast.FloorDiv) else 0
                requested.append((resolve_name(elt.left.id, self.dialect),
                                  elt.right.value + extra))

        if self.module_signatures is None:
            if self.module_path is not None:
                # Relative-path mode without signatures: no way to tell which
                # requested names the target really exports, so import its
                # whole export set instead of naming any of them.
                return None
            # F5 (2026-09-29): a BARE name's arity is unknown here, and a bare
            # atom is not an ISO import item -- Scryer refuses the file at load
            # (syntax_error(invalid_module_declaration)) and Trealla imports
            # NOTHING, failing at call time. Import the whole export set
            # instead (a listless use_module): a superset, no guessed arity.
            if any(arity is None for _, arity in requested):
                return None
            return [PCompound("/", (PAtom(name), PNumber(arity)))
                    for name, arity in requested]

        exported = self.module_signatures.get(mod_path)
        if exported is None:
            # Target outside the export set being built: nothing to filter
            # against, so import everything it exports (a listless use_module
            # can never claim an export the target does not have).
            return None

        imports: list[PTerm] = []
        seen: set[tuple[str, int]] = set()
        for name, arity in requested:
            arities = ([arity] if arity is not None
                       else sorted(a for n, a in exported if n == name))
            for a in arities:
                if (name, a) in exported and (name, a) not in seen:
                    seen.add((name, a))
                    imports.append(PCompound("/", (PAtom(name), PNumber(a))))
        return imports

    def _convert_import_from(self, call: python_ast.Call) -> PDirective | PComment:
        """Convert -import_from(module, [names]).

        Uses the dialect's library_map to resolve known clausal modules to
        Prolog library(...) form. Python-only modules emit a warning.
        """
        mod_path = self._get_string_or_name(call.args[0])

        # Check if this is a Python-only module (no Prolog equivalent)
        if mod_path.startswith("py.") or mod_path.startswith("clausal.modules.py."):
            self._add_warning(f"-import_from({mod_path}, ...)")
            return PComment(
                f"WARNING: Python-only module import: -import_from({mod_path}, ...)\n"
                f"   No Prolog equivalent available."
            )

        prolog_mod = self._module_reference(mod_path)
        if prolog_mod is None:
            # No path names this target from here — _module_reference has
            # already recorded the warning.
            return PComment(
                f"WARNING: unresolvable use_module path: "
                f"-import_from({mod_path}, ...)\n"
                f"   No relative path from this module names that file."
            )

        elts = (call.args[1].elts
                if len(call.args) > 1 and isinstance(call.args[1], python_ast.List)
                else [])
        # Drop names that are UNITS: the export discards units at every use
        # site, so importing one leaves a symbol the emitted program never
        # mentions -- and the unit's home is an engine module the export does
        # not stage, so the directive would not resolve at all.
        kept = [e for e in elts
                if not (isinstance(e, python_ast.Name) and e.id in self._unit_atoms)]
        if len(kept) != len(elts):
            dropped = sorted({e.id for e in elts
                              if isinstance(e, python_ast.Name)
                              and e.id in self._unit_atoms})
            self._add_lossy(
                f"unit import dropped: -import_from({mod_path}, {dropped})")
            if not kept:
                return PComment(
                    f"% skipped: {mod_path} imported only units "
                    f"({', '.join(dropped)}) -- units are discarded on export")
        elts = kept
        imports = self._import_list(mod_path, elts)

        if imports is None:
            # Unknown or unfiltered target: import its whole export set.
            return PDirective(PCompound("use_module", (prolog_mod,)))
        if not imports and self.module_signatures is not None:
            # Nothing the target exports was asked for — a use_module naming
            # predicates it does not export would abort the consult.
            #
            # The wording is about the INTERSECTION, not the target: this
            # branch is reached whenever the filtered list comes back empty,
            # which is usually a target that exports plenty, just none of the
            # names this import asked for. Saying "exports nothing" there is
            # simply false, and sends a reader looking for a bug in the target
            # module instead of at the import list in front of them.
            return PComment(
                f"% skipped: {mod_path} exports none of the requested names")

        return PDirective(PCompound("use_module", (prolog_mod, PList(tuple(imports)))))

    def _convert_import_module(self, call: python_ast.Call) -> PDirective | PComment:
        """Convert -import_module(module)."""
        mod_path = self._get_string_or_name(call.args[0])

        if mod_path.startswith("py.") or mod_path.startswith("clausal.modules.py."):
            self._add_warning(f"-import_module({mod_path})")
            return PComment(
                f"WARNING: Python-only module import: -import_module({mod_path})\n"
                f"   No Prolog equivalent available."
            )

        prolog_mod = self._module_reference(mod_path)
        if prolog_mod is None:
            return PComment(
                f"WARNING: unresolvable use_module path: "
                f"-import_module({mod_path})\n"
                f"   No relative path from this module names that file."
            )
        return PDirective(PCompound("use_module", (prolog_mod,)))

    def _convert_meta_directive(self, name: str, call: python_ast.Call) -> PDirective | list | PComment | None:
        """Convert -dynamic(pred/arity), -table(...), -discontiguous(...).

        Any argument _convert_pred_spec cannot parse is warned (fail-closed
        net) and dropped from the emitted spec list -- but if EVERY
        argument drops out this way (or there were no arguments at all),
        the directive must not be emitted at all: `:- dynamic([]).` /
        `:- dynamic.` is a different, MALFORMED directive (declares
        nothing dynamic), not a faithful partial translation, and strict
        mode must not wave it through as clean.
        """
        specs = []
        any_dropped = False
        for arg in call.args:
            spec = self._convert_pred_spec(arg)
            if spec is None:
                self._add_warning(
                    f"-{name}(...) predicate spec: {python_ast.unparse(arg)}"
                )
                any_dropped = True
                continue
            specs.append(spec)

        if not specs:
            if not any_dropped:
                # -name() with no arguments at all -- nothing to warn per-
                # spec above, but emitting an empty directive still
                # changes its meaning, so it gets its own warning here.
                self._add_warning(f"-{name}() with no predicate arguments")
            return None

        if len(specs) == 1:
            directive = PDirective(PCompound(name, (specs[0],)))
        else:
            directive = PDirective(PCompound(name, (PList(tuple(specs)),)))

        # GNU Prolog has no tabling support — emit warning comment
        if name == "table" and not self.dialect.tabling_directive:
            return PComment(
                "WARNING: GNU Prolog does not support tabling.\n"
                "   :- table directive skipped."
            )

        # Scryer needs :- use_module(library(tabling)) before :- table
        if name == "table" and self.dialect.name == "scryer":
            use_tabling = PDirective(PCompound("use_module", (
                PCompound("library", (PAtom("tabling"),)),
            )))
            return [use_tabling, directive]
        return directive

    def _convert_pred_spec(self, node) -> PTerm | None:
        """Convert a predicate specification: Foo(X, Y) -> foo/2, the bare
        atom Foo -> foo, or the Name/Arity spelling Foo/2 (a BinOp Div at
        Python-AST level -- standard predicate-indicator syntax, e.g.
        `-dynamic(vacuous_property/1)`) -> foo/2 directly."""
        if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Name):
            functor = resolve_name(node.func.id, self.dialect)
            arity = len(node.args)
            return PCompound("/", (PAtom(functor), PNumber(arity)))
        if (isinstance(node, python_ast.BinOp)
                and isinstance(node.op, python_ast.Div)
                and isinstance(node.left, python_ast.Name)
                and isinstance(node.right, python_ast.Constant)
                and isinstance(node.right.value, int)
                and not isinstance(node.right.value, bool)):
            functor = resolve_name(node.left.id, self.dialect)
            return PCompound("/", (PAtom(functor), PNumber(node.right.value)))
        if isinstance(node, python_ast.Name):
            functor = resolve_name(node.id, self.dialect)
            return PAtom(functor)
        return None

    def _convert_head(self, call) -> PTerm:
        """Convert a clause head (a Call node) to a PCompound."""
        if isinstance(call, python_ast.Call) and isinstance(call.func, python_ast.Name):
            functor = resolve_name(call.func.id, self.dialect)
            args = [self._convert_expr(a) for a in call.args]
            for kw in call.keywords:
                args.append(self._convert_expr(kw.value))
            args = tuple(args)
            if not args:
                return PAtom(functor)
            return PCompound(functor, args)
        return self._convert_expr(call)

    def _convert_expr(self, node, goal_position: bool = False) -> PTerm:
        """Convert a Python AST expression node to a Prolog AST term.

        *goal_position* is True exactly when *node* is being converted as a
        goal — the whole clause body, or a body conjunct — rather than as
        data nested inside an argument/value position (a Call argument, a
        list element, a dict value, ...). It defaults to False and is only
        propagated True through the constructs that combine sub-goals
        (a parenthesized comma-body Tuple, ``and``/``or`` BoolOp) from a
        caller that itself received True. It gates constructs whose Prolog
        lowering is only valid as an executed goal (e.g. the `is`-RHS
        dict-splat → ``attrs_put/3`` rewrite) — see `_convert_compare`.
        """
        if isinstance(node, python_ast.Constant):
            return self._convert_constant(node.value, node)

        if isinstance(node, python_ast.Name):
            return self._convert_name(node.id)

        if isinstance(node, python_ast.Call):
            return self._convert_call(node)

        if isinstance(node, python_ast.List):
            return self._convert_list(node)

        if isinstance(node, python_ast.Tuple):
            # Single-element tuple used for trailing-comma facts in nested context
            if len(node.elts) == 1:
                return self._convert_expr(node.elts[0], goal_position=goal_position)
            # Multi-element tuple → Prolog comma-separated (conjunction-like)
            if len(node.elts) >= 2:
                result = self._convert_expr(node.elts[-1], goal_position=goal_position)
                for elt in reversed(node.elts[:-1]):
                    result = PCompound(",", (
                        self._convert_expr(elt, goal_position=goal_position),
                        result,
                    ))
                return result
            return PAtom("true")

        if isinstance(node, python_ast.BoolOp):
            return self._convert_boolop(node, goal_position=goal_position)

        if isinstance(node, python_ast.UnaryOp):
            return self._convert_unaryop(node)

        if isinstance(node, python_ast.BinOp):
            return self._convert_binop(node)

        if isinstance(node, python_ast.Compare):
            return self._convert_compare(node, goal_position=goal_position)

        if isinstance(node, python_ast.IfExp):
            return self._convert_ifexp(node)

        # python_ast.NamedExpr (':=') no longer reaches here: the Clausal
        # transformer rejects it with a SyntaxError (use eval_/2, ==, or is).

        if isinstance(node, python_ast.Starred):
            # *X in list context — handled by _convert_list
            return self._convert_expr(node.value)

        # Attribute access: mod.pred
        if isinstance(node, python_ast.Attribute):
            base = self._convert_expr(node.value)
            if isinstance(base, PAtom):
                return PAtom(base.name + ":" + node.attr)
            return PCompound(":", (base, PAtom(node.attr)))

        # f-string: f"Hello {Name}" → format/2 (SWI) or warning
        if isinstance(node, python_ast.JoinedStr):
            return self._convert_fstring(node)

        # Dict literal → SWI dict or warning
        if isinstance(node, python_ast.Dict):
            return self._convert_dict(node)

        # Set literal: single-element sets are DCG inline goals {Goal}
        if isinstance(node, python_ast.Set):
            if len(node.elts) == 1:
                # {Goal} — DCG inline goal
                return PCurly(self._convert_expr(node.elts[0]))
            self._add_warning("set literal {" + ", ".join(
                python_ast.unparse(e) for e in node.elts
            ) + "}")
            return PAtom("???")

        # Fallback: no conversion rule for this Python AST node type
        self._add_warning(f"unsupported expression: {python_ast.unparse(node)}")
        return PAtom("???")

    def _convert_constant(self, value, node=None) -> PTerm:
        """Convert a Python constant to a Prolog term.

        *node* is the ``ast.Constant`` the value came from, when the caller
        has one: a str literal's quote character is recovered from it (see
        ``_quote_map`` in ``__init__``). Callers that synthesize a value pass
        no node, and the module's -double_quotes mode alone decides.
        """
        if isinstance(value, bool):
            return PAtom("true" if value else "false")
        if isinstance(value, int):
            return PNumber(value)
        if isinstance(value, float):
            return PNumber(value)
        if isinstance(value, str):
            return self._convert_str_literal(value, node)
        if value is None:
            return PAtom("none")
        return PAtom(str(value))

    def _convert_str_literal(self, value: str, node) -> PTerm:
        """THE LITERAL RULE (item J of the strings todo; operator go
        2026-09-07), the compiler's own rule mirrored:

        * ``'...'`` is an ATOM in every mode (ISO 6.4.2 quoted token);
        * ``"..."`` is a STRING (a Prolog double-quoted token; both target
          engines default to ``double_quotes=chars``) under
          ``-double_quotes(chars)`` -- the engine default since 2026-09-26
          -- and an ATOM under ``-double_quotes(atom)``.

        Before this rule the translator lowered every str literal one way
        regardless of mode: to a string (the flip) or to an atom (bda6b039).
        Either is a SILENT WRONG ANSWER for the modules in the other mode --
        an atom in the engine becomes a char list in the export, or vice
        versa -- pinned both ways by tests/test_prolog_literal_rule.py and
        the execution harness (tests/test_prolog_execution.py).
        """
        quote = quote_of(self._quote_map, node) if node is not None else None
        if quote == "'" or self._double_quotes == "atom":
            # `"[]"` / `"{}"` need no special case any more: under THE FLIP
            # (2026-09-06-atoms-as-cells-strings §11) the atom `[]` IS the
            # empty list in the engine too (`atom([])` is true, exactly as in
            # ISO 6.3.5), so the emitted `[]` matches on both sides and the
            # collapse f47e1a8e warned about is now faithful -- pinned as an
            # AGREEMENT by tests/test_prolog_execution.py::
            # TestBracketAtomLiteralAgrees.
            return PAtom(value)
        return PString(value)

    def _declared_magnitude_term(self, value):
        """The magnitude as the dialect represents it in a DECLARATION.

        `float` leaves the number alone. `rational` emits the unevaluated term
        `1_550_00/100`, which is plain ISO syntax and keeps the scale -- a
        float literal loses it, because Prolog has no decimal type (measured in
        both reference systems: `1550.00` reads and prints as `1550.0`, while
        `155000/100` as a TERM is preserved exactly).

        Underscore digit grouping is used because both systems accept it and it
        makes the minor units legible: `1_550_00` reads as 1550 and 00.
        """
        if getattr(self.dialect, "decimal_repr", "float") != "rational":
            return value
        if not isinstance(value, PNumber):
            return value
        from decimal import Decimal                              # noqa: PLC0415
        v = value.value
        if not isinstance(v, Decimal):
            return value                  # ints and floats: nothing to preserve
        exponent = v.as_tuple().exponent
        if not isinstance(exponent, int) or exponent >= 0:
            return value                  # no fractional digits to keep
        denominator = 10 ** (-exponent)
        numerator = int(v.scaleb(-exponent))
        return PCompound("/", (PNumber(_group_digits(numerator, -exponent)),
                               PNumber(denominator)))

    def _constant_declaration(self, directive, name, value, unit, cap):
        """The declaration item for this dialect: a directive or a fact."""
        unit_term = self._convert_expr(unit)
        args = (PAtom(name), self._declared_magnitude_term(value), unit_term)
        if cap == "expansion":
            return PDirective(PCompound(directive, args))
        module = (self._module_name
                  or (posixpath.basename(self.module_path or "").split(".")[0]
                      if self.module_path else None)
                  or "user")
        return PClause(PCompound(directive, (PAtom(module),) + args))

    def _collect_constant(self, directive: str, call: python_ast.Call) -> None:
        """Record a ``-constant_value`` / ``-constant_number_units`` declaration.

        The value is converted NOW, in file order, so a later declaration may
        refer to an earlier one and every use site gets a fully resolved term.
        Nothing is emitted: a constant exists in the exported program only as
        the literal it folds to.

        The units form loses its unit. Prolog has no unit system, and the
        exporter already discards units from an inline ``5000(euro)`` literal
        the same way -- this follows that precedent rather than inventing a
        policy, but it is recorded as LOSSY so it is never silent.
        """
        args = call.args if isinstance(call, python_ast.Call) else ()
        united = directive in ("constant_number_units",
                               "constant_number_currency")
        expected = 3 if united else 2
        if len(args) != expected or not isinstance(args[0], python_ast.Name):
            # Malformed: the engine refuses this at load time, so a file that
            # reaches the translator should not contain one. Do not guess.
            self._add_warning(f"-{directive}(...)")
            return
        name = args[0].id
        previous = self._in_constant_rhs
        self._in_constant_rhs = True
        try:
            value = self._fold_arithmetic(self._convert_expr(args[1]))
        finally:
            self._in_constant_rhs = previous
        if united:
            unit = args[2]
            unit_text = (unit.id if isinstance(unit, python_ast.Name)
                         else python_ast.unparse(unit))
            # A SCALED unit's declared magnitude is not the stored one, so
            # folding it emits a number the engine never held -- `155000 cent`
            # became `155000` where the engine holds 1550.00 dollar, a 100x
            # money error announced only by a comment. Refuse instead: loud,
            # dated and recoverable, where a wrong magnitude in an exported
            # legal program is none of those. Ruled 2026-09-11, after three
            # censuses agreed nothing declares a constant in a scaled unit
            # today; see todo/exporter-folds-scaled-units-to-the-wrong-
            # magnitude-2026-09-11.md for the fix that lifts this.
            cap = getattr(self.dialect, "constants", "facts")
            if cap == "none":
                raise NotImplementedError(
                    f"clausal_to_prolog: -{directive}({name}, ..., "
                    f"{unit_text}) cannot be exported to the "
                    f"{self.dialect.name} dialect, which has no way to receive "
                    f"a constant declaration (constants capability 'none'). "
                    f"Refusing rather than emitting something that parses and "
                    f"does not run.")
            factor = _unit_factor(_unit_leaf_names(unit))
            if factor is None:
                raise NotImplementedError(
                    f"clausal_to_prolog: -{directive}({name}, ..., "
                    f"{unit_text}) declares a constant in a unit the exporter "
                    f"cannot resolve from static data, so it cannot convert "
                    f"the magnitude to the one the engine holds. Refusing "
                    f"rather than guessing: a wrong factor is a wrong number "
                    f"in an exported legal program.")
            # The BASE magnitude -- the one the engine actually holds. Emitting
            # the DECLARED magnitude is the defect this path existed for:
            # `155000 usd_cent` is 1550.00 dollars, and `155000` was a 100x
            # money error announced only by a comment.
            value = _scale_constant_value(value, factor)
            # The declaration CROSSES now, carrying its unit, so nothing is
            # discarded and there is no LOSSY note to write. How it crosses is
            # the dialect's business: a system with `prolog_load_context/2`
            # takes the directive and expands it; one without gets the module
            # filled in here, by the exporter, which knows it statically --
            # exactly as the engine's transformer does for
            # `constant_number_units/3`.
            self._items.append(
                self._constant_declaration(directive, name, value, unit, cap))
            self._emitted_constant_declaration = True
            # Use sites want the EXACT number; the declaration wants the SCALE.
            # They differ, and folding them was the bug: `155000 aud_cent` is
            # Decimal('1550.00'), so a declaration should be able to render
            # `1_550_00/100` while a use site must read as exact `1550` rather
            # than the float `1550.00`. Integralising in the shared scaler broke
            # the declaration's scale; integralising here does not.
            value = _integral_if_whole(value)
        self._constants[name] = value

    #: Arithmetic that folds over numeric literals. Deliberately NOT a general
    #: evaluator: the translator must never execute the file it is translating,
    #: so a ``++`` escape in a constant RHS is not run, and anything it cannot
    #: fold is left as an expression (which Prolog evaluates identically in an
    #: arithmetic context).
    _FOLDABLE = {
        "+": lambda a, b: a + b, "-": lambda a, b: a - b,
        "*": lambda a, b: a * b,
    }

    def _fold_arithmetic(self, term: PTerm) -> PTerm:
        """Collapse arithmetic over numeric literals to a single number.

        ``base * 4 + 2`` with ``base`` already folded to 10 becomes 42, not the
        compound ``10 * 4 + 2``. The compound would evaluate identically under
        ``>`` and ``is``, but a constant also reaches TERM positions
        (``p(++limit)``), where the engine binds 42 and an unfolded expression
        would bind a compound -- a real divergence between the exported program
        and the one it was translated from.
        """
        if not isinstance(term, PCompound) or len(term.args) != 2:
            return term
        fn = self._FOLDABLE.get(term.functor)
        if fn is None:
            return term
        left = self._fold_arithmetic(term.args[0])
        right = self._fold_arithmetic(term.args[1])
        if (isinstance(left, PNumber) and isinstance(right, PNumber)
                and left.unit is None and right.unit is None):
            return PNumber(fn(left.value, right.value))
        return PCompound(term.functor, (left, right))

    def _convert_name(self, name: str) -> PTerm:
        """Convert a Python name to PVar or PAtom."""
        if self._in_constant_rhs and name in self._constants:
            # Only inside a ``-constant_value`` RHS. Everywhere else a bare
            # name is the ATOM and folding it would be wrong.
            return self._constants[name]
        if name == "_":
            return PVar("_")
        # ``Undefined`` — the Kleene (K3) third truth value builtin — maps OUTBOUND
        # to the plain Prolog atom ``undefined``, the spelling XSB and SWI use for
        # the well-founded third value (originally ``unknown``, decision 4 of
        # todo/kleene-unknown-builtin-and-stdlib.md; renamed with the builtin).
        # This mapping is DELIBERATELY asymmetric: ``prolog_to_clausal`` is left
        # unchanged, so an inbound atom ``undefined`` stays a plain atom rather
        # than being rewritten to the builtin — auto-rewriting would silently
        # change the identity semantics of existing Prolog imports.
        # (``pascal_to_snake`` would also yield ``undefined`` here, but this
        # explicit case documents the intent and pins it against future
        # name-resolution changes.)
        if name == "Undefined":
            return PAtom("undefined")
        if _is_logic_var_name(name):
            return PVar(clausal_var_to_prolog(name))
        # Atoms: lowercase or PascalCase predicate name
        return PAtom(resolve_name(name, self.dialect))

    # Reverse mapping from clausal qualified names (e.g. prolog.TruncDiv)
    # back to Prolog infix operators.  These are the operators that
    # prolog_to_clausal emits as ``prolog.<Name>(X, Y)`` because their
    # ISO semantics differ from Python's.
    _QUALIFIED_OP_REVERSE: dict[tuple[str, str], str] = {
        ("prolog", "TruncDiv"): "//",
        ("prolog", "TruncMod"): "mod",
        ("prolog", "Rem"):      "rem",
    }

    # CLP(FD) constraint names. Written as canonical forms in Clausal source
    # (`'#='(A, B)`) because Python has no `#=` operator, but they have no ISO
    # Prolog meaning and must not be lowered to arithmetic look-alikes.
    _CLPFD_CANONICAL = frozenset({"#=", "#\\=", "#<", "#>", "#=<", "#>="})

    def _fold_constant_call(self, node: python_ast.Call):
        """``constant(name)`` -> the declared literal, or None if not that.

        The retrieval form since 2026-09-11, replacing the ``++name`` escape.
        Folded for the same reason: ISO has no evaluable ``constant/1`` any
        more than it has ``++/1``, and the value is known here.
        """
        if not (isinstance(node.func, python_ast.Name)
                and node.func.id == "constant"
                and len(node.args) == 1
                and isinstance(node.args[0], python_ast.Name)):
            return None
        return self._constants.get(node.args[0].id)

    def _convert_call(self, node: python_ast.Call) -> PTerm:
        """Convert a function call to a PCompound."""
        folded = self._fold_constant_call(node)
        if folded is not None:
            return folded
        quantity = self._try_quantity(node)
        if quantity is not None:
            return quantity
        if isinstance(node.func, python_ast.Name):
            # Clausal has no cut: a Cut() goal in source is a call to an
            # undefined predicate, and exporting it (as `cut` or as `!`)
            # would launder cut through cut-free Clausal (F036). Reject.
            if node.func.id == "Cut":
                from clausal.tools.prolog_to_clausal import PrologTranslationError
                raise PrologTranslationError(
                    "Cut() cannot be translated to Prolog.\n"
                    "Clausal has no Cut predicate — cut is intentionally "
                    "omitted (it breaks declarative semantics and "
                    "monotonicity), so a Cut() goal in Clausal source is "
                    "already an error and must not be exported as Prolog "
                    "!/0 or as an undefined `cut` predicate.\n"
                    "Rewrite using once/1, dif/2 guards, or reified "
                    "conditionals. See: docs/for_prolog_programmers.md"
                )
            if node.func.id == "eval_" and len(node.args) == 2 \
                    and not node.keywords:
                # eval_(EXPR, RESULT) — eager arithmetic evaluate-and-bind —
                # is Prolog's is/2: RESULT is EXPR.
                expr = self._convert_expr(node.args[0])
                result = self._convert_expr(node.args[1])
                return PCompound("is", (result, expr))
            functor = resolve_name(node.func.id, self.dialect)
        elif (isinstance(node.func, python_ast.Constant)
                and isinstance(node.func.value, str)
                and node.func.value):
            # THE ISO CANONICAL FORM (spec 2026-09-08 §3.2). `'@<'(X, Y)` is
            # Python for a string literal CALLED, so it arrives as a Constant
            # target rather than a Name, and every one of these was refused
            # with "unsupported call target" until now. The engine registered
            # the names in d4f4c486, so a site migrated to a canonical form
            # ran correctly and then failed to EXPORT — turning a G3 red
            # (exports, fails in Scryer) into a G1 red (does not export),
            # which is strictly worse while looking like progress.
            #
            # For `@<` and friends there is no alternative spelling to fall
            # back on: `X @< Y` is not valid Python.
            #
            # Emission already does the rest. `PCompound("@<", (X, Y))` emits
            # `X @< Y` through the operator table, and a functor with no
            # operator entry (compare/3) emits as an ordinary compound, so
            # nothing here needs to know which names are infix.
            functor = node.func.value
            if functor in self._CLPFD_CANONICAL:
                # CLP(FD) constraints have NO ISO meaning. Lowering `'#='` to
                # `X #= Y` would emit a file that errors in any target without
                # clpz loaded, and lowering it to `=:=` or `=` would silently
                # change the semantics from a constraint to a test. Refuse
                # loudly; targeting a clpz-capable dialect is a separate
                # decision. See todo/clp-domain-spans-reals-while-clpz-is-integers-2026-09-09.md
                self._add_warning(
                    f"CLP(FD) constraint has no ISO form: {functor}")
                functor = "???"
        elif isinstance(node.func, python_ast.Attribute):
            # Check for qualified operator calls (e.g. prolog.TruncDiv)
            # that should be emitted as infix operators.
            op = self._try_qualified_op(node.func, node.args)
            if op is not None:
                return op
            # Qualified call: mod.pred(...)
            functor = self._qualified_name(node.func)
        else:
            self._add_warning(self._call_target_diagnosis(node))
            functor = "???"

        args = [self._convert_expr(a) for a in node.args]
        # Keyword args become positional (kwarg names are field labels in clausal)
        for kw in node.keywords:
            args.append(self._convert_expr(kw.value))
        args = tuple(args)
        return PCompound(functor, args)

    def _try_qualified_op(
        self, attr: python_ast.Attribute, args: list,
    ) -> PTerm | None:
        """If *attr* is a qualified operator (e.g. ``prolog.TruncDiv``),
        return the corresponding Prolog infix ``PCompound``; else ``None``."""
        if not isinstance(attr.value, python_ast.Name) or len(args) != 2:
            return None
        key = (attr.value.id, attr.attr)
        op_str = self._QUALIFIED_OP_REVERSE.get(key)
        if op_str is None:
            return None
        left = self._convert_expr(args[0])
        right = self._convert_expr(args[1])
        return PCompound(op_str, (left, right))

    def _qualified_name(self, attr: python_ast.Attribute) -> str:
        """Get a qualified name from an Attribute node."""
        if isinstance(attr.value, python_ast.Name):
            base = resolve_name(attr.value.id, self.dialect)
            pred = resolve_name(attr.attr, self.dialect)
            return base + ":" + pred
        return resolve_name(attr.attr, self.dialect)

    def _convert_list(self, node: python_ast.List) -> PTerm:
        """Convert a Python list literal to a PList.

        Handles [H, *T] → [H|T] (star-unpack as list tail).
        """
        elements = []
        tail = None
        for i, elt in enumerate(node.elts):
            if isinstance(elt, python_ast.Starred):
                # *T is the tail — must be the last element
                tail = self._convert_expr(elt.value)
                # Elements before starred are the head elements
                break
            elements.append(self._convert_expr(elt))
        else:
            # No starred element — proper list
            return PList(tuple(elements))

        return PList(tuple(elements), tail=tail)

    def _convert_boolop(self, node: python_ast.BoolOp, goal_position: bool = False) -> PTerm:
        """Convert 'and'/'or' to ','/';'.

        Each operand is itself a body conjunct/disjunct, so *goal_position*
        (whatever this BoolOp itself was converted under) propagates
        unchanged to every operand.
        """
        if isinstance(node.op, python_ast.And):
            op = ","
        else:
            op = ";"

        result = self._convert_expr(node.values[-1], goal_position=goal_position)
        for val in reversed(node.values[:-1]):
            result = PCompound(op, (
                self._convert_expr(val, goal_position=goal_position),
                result,
            ))
        return result

    def _convert_unaryop(self, node: python_ast.UnaryOp) -> PTerm:
        """Convert unary operators."""
        if isinstance(node.op, python_ast.Not):
            # `not (X in XS)` is the OTHER spelling of negated membership: it
            # reaches _convert_compare as a POSITIVE `In` under this `\+`, so
            # the refusal has to be applied here, where the negation is
            # visible (2026-09-03). `X not in XS` is caught in _convert_compare.
            operand = node.operand
            if isinstance(operand, python_ast.Compare):
                refused = False
                for op, comp in zip(operand.ops, operand.comparators):
                    if isinstance(op, python_ast.In):
                        refused |= self._check_negated_membership(comp)
                if refused:
                    return PAtom("???")
            return PCompound("\\+", (self._convert_expr(node.operand),))
        if isinstance(node.op, python_ast.USub):
            inner = self._convert_expr(node.operand)
            if isinstance(inner, PNumber):
                return PNumber(-inner.value, unit=inner.unit)
            return PCompound("-", (inner,))
        if isinstance(node.op, python_ast.UAdd):
            # ++expr is the Python interop escape. Over a DECLARED CONSTANT it
            # folds to the value; over anything else the value is not known at
            # export time, so it stays untranslatable rather than emitting
            # something plausible.
            if (isinstance(node.operand, python_ast.UnaryOp)
                    and isinstance(node.operand.op, python_ast.UAdd)):
                inner = node.operand.operand
                if isinstance(inner, python_ast.Name) and inner.id in self._constants:
                    return self._constants[inner.id]
                self._add_warning("++(" + python_ast.unparse(inner) + ")")
                return PAtom("???")
            return self._convert_expr(node.operand)
        if isinstance(node.op, python_ast.Invert):
            return PCompound("\\", (self._convert_expr(node.operand),))
        return self._convert_expr(node.operand)

    def _fold_constant_over_unit(self, node: python_ast.BinOp):
        """``constant(c) / <unit>`` -> c's magnitude IN that unit, or None.

        A declaration stores the BASE magnitude, so a use site that asks for a
        constant in a named unit has to convert back. Without this the constant
        folded and the DIVISOR survived, emitting `CENTS =:= 1550.00/usd_cent`
        -- and a unit atom is not an evaluable functor, so both reference
        engines answer `type_error(evaluable, usd_cent/0)`. 65 single-goal
        corpus clauses were this exact shape (measured 2026-09-13); the derived
        predicate could never have answered.

        Returns None -- leaving the ordinary binop path to run -- whenever the
        shape is not a constant over a resolvable unit. A `/` between two
        ordinary terms is real division and must stay real division.
        """
        if not isinstance(node.op, python_ast.Div):
            return None
        if not isinstance(node.left, python_ast.Call):
            return None
        base = self._fold_constant_call(node.left)
        if base is None:
            return None
        factor = _unit_divisor_factor(node.right)
        if factor is None:
            # A divisor the unit vocabulary does not hold is not a unit at all
            # -- `constant(c) / COUNT` is division, and so is `constant(c) /
            # 10000`. Refusing here would break arithmetic that has always been
            # legal.
            return None
        return _unscale_constant_value(base, factor)

    def _fold_term_over_unit(self, node: python_ast.BinOp):
        """``<term> / <unit>`` -> that term scaled INTO the unit, or None.

        The other half of :meth:`_fold_constant_over_unit`, which requires the
        left operand to be a ``constant(c)`` Call and so declines the far more
        common ``CENTS == A / eur_cent`` -- a RUNTIME value asked for in a named
        unit. The defect is identical: a unit atom is not an evaluable functor,
        so the surviving divisor makes the goal dead. Measured 2026-09-19 over
        the emitted AST, 13 of the corpus's 18 `/`-bearing `#=` goals are this
        shape, across 13 domains, and every one of them was equally dead BEFORE
        the 2026-09-18 ruling -- `=:=` raises on the atom exactly as `#=` does.

        EMITS MULTIPLICATION, NOT DIVISION, and that is the point rather than a
        tidier spelling: the reciprocal of every scaled unit in the vocabulary
        is an exact integer (cents 100, basis points 10000), so the folded goal
        leaves CLP(Z)'s exact-division limit entirely instead of landing inside
        it, where an inexact quotient fails SILENTLY.

        REFUSES rather than guesses, on the same discipline as the constant
        path: a divisor the unit vocabulary does not hold is not a unit at all
        (`AVG == TOTAL / COUNT` is real division and must stay real division),
        and a factor whose reciprocal is not an exact integer is left alone
        rather than rounded -- a wrong factor is a wrong number in an exported
        legal program.
        """
        if not isinstance(node.op, python_ast.Div):
            return None
        factor = _unit_divisor_factor(node.right)
        if factor is None:
            return None
        left = self._convert_expr(node.left)
        if factor == 1:
            # Dividing by a base unit converts nothing. Return the term
            # UNCHANGED rather than multiplying by 1, for the same reason
            # _unscale_constant_value does: it must not acquire arithmetic it
            # never had.
            return left
        if isinstance(left, PNumber):
            # A literal magnitude converts exactly and stays a number, rather
            # than becoming `5000*100` for a reader to evaluate.
            return _unscale_constant_value(left, factor)
        reciprocal = 1 / factor
        if reciprocal != int(reciprocal):
            return None
        return PCompound("*", (left, PNumber(int(reciprocal))))

    def _convert_binop(self, node: python_ast.BinOp) -> PTerm:
        """Convert binary operators to Prolog operators."""
        folded = self._fold_constant_over_unit(node)
        if folded is not None:
            return folded
        folded = self._fold_term_over_unit(node)
        if folded is not None:
            return folded
        left = self._convert_expr(node.left)
        right = self._convert_expr(node.right)

        op_map = {
            python_ast.Add: "+",
            python_ast.Sub: "-",
            python_ast.Mult: "*",
            python_ast.Div: "/",
            # Clausal/Python // is floored; Prolog // truncates toward zero, so
            # emit SWI/Scryer `div` (floored) to preserve semantics (F031). The
            # forward direction routes Prolog // through prolog.TruncDiv for the
            # same reason. Python % and Prolog mod are both floored — mod is OK.
            python_ast.FloorDiv: "div",
            python_ast.Mod: "mod",
            # A bare ``**`` is Python's power (``2 ** 3`` is the integer 8;
            # operator rulings 2026-09-28), which is ISO ``^`` for integers;
            # ISO ``**`` always answers a float (8.0).  Known gap: a NEGATIVE
            # integer exponent is 0.5 in Python (``2 ** -1``) and
            # ``type_error(float, 2)`` for ISO ``^``.
            python_ast.Pow: "^",
            python_ast.BitAnd: "/\\",
            python_ast.BitOr: "\\/",
            python_ast.BitXor: "xor",
            python_ast.LShift: "<<",
            python_ast.RShift: ">>",
        }
        op_str = op_map.get(type(node.op))
        if op_str is None:
            self._add_warning(f"unsupported operator: {type(node.op).__name__}")
            op_str = "???"
        return PCompound(op_str, (left, right))

    #: The expressions CLP(Z) evaluates, by arity: exactly the heads Scryer's
    #: library(clpz) `parse_clpz/2` accepts (src/lib/clpz.pl, the `m(...)`
    #: rows), which covers what `_convert_binop` / `_convert_unaryop` emit
    #: and the evaluable CALLS (`abs(Y)`, `min(A, B)`, ...). The dialects
    #: have no evaluable table of their own to consult; both ladder engines
    #: use this clpz. A converted term headed by one of these is arithmetic.
    _ARITH_FUNCTORS_2 = frozenset({
        "+", "-", "*", "/", "//", "div", "mod", "rem", "^", "min", "max",
        "<<", ">>", "/\\", "\\/", "xor"})
    _ARITH_FUNCTORS_1 = frozenset({
        "-", "\\", "abs", "sign", "msb", "lsb", "popcount"})

    def _not_equal(self, left: PTerm, right: PTerm) -> PTerm:
        """Clausal's `!=` constraint in Prolog (ruling R16, 2026-09-29).

        `!=` is a CONSTRAINT, not a test: it waits for its arguments, so a
        plain `\\==` or `=\\=` (what this used to write) means something else
        when an argument is unbound.  A NUMERIC `!=` is the CLP(Z)
        disequality `#\\=`; anything else -- not numeric, or not known to
        be -- is `dif/2`, which is sound for numbers too (it only loses the
        arithmetic: `X + 1 != 3` must be `#\\=`).

        "Numeric" is decided on the CONVERTED terms (`_is_clpz_term`), i.e.
        on what the exporter actually writes, so a quantity literal
        (`5000(euro)` -> `5000`), a negative literal and a folded constant
        are classified by the number they become (D17).  A float is not
        numeric here: CLP(Z) is over the integers and raises
        `domain_error(clpz_expression, F)` on one.
        """
        if self._is_clpz_term(left) or self._is_clpz_term(right):
            self._emitted_clp_arith_neq = True
            return PCompound("#\\=", (left, right))
        return PCompound("dif", (left, right))

    @classmethod
    def _is_clpz_term(cls, term: PTerm) -> bool:
        """True if the exported *term* is an integer or arithmetic (R16/D17).

        An integer `PNumber` (whatever it came from: a literal, `-3`, a
        quantity's magnitude, a folded constant) or a compound headed by an
        arithmetic functor or evaluable clpz function (`abs(Y)`: as dif/2
        it would compare X against the UNEVALUATED term).  A float `PNumber` is not.  An arithmetic
        compound counts even if a float sits inside it -- `#\\=` then raises
        in the target, as `#=` does for `==` (ruling 2026-09-19), which is
        louder than the structural `dif/2` silently comparing `X` against
        the unevaluated term `1.5 * 2`.
        """
        if isinstance(term, PNumber):
            return type(term.value) is int
        if isinstance(term, PCompound):
            arity = len(term.args)
            return ((arity == 2 and term.functor in cls._ARITH_FUNCTORS_2)
                    or (arity == 1 and term.functor in cls._ARITH_FUNCTORS_1))
        return False

    # ── Interim refusals (operator decision, 2026-09-03) ──────────────
    #
    # See docs/iso-export-pilot-2026-09.md, "Operator decision — 2026-09-03
    # (dict-membership fail-open, class P census)", recorded downstream.
    # Two shapes that used to translate SILENTLY WRONG now refuse.

    # Goals whose output argument is guaranteed to be a proper list, keyed by
    # (name, arity) → index of that output argument. Deliberately tiny: each
    # entry is checkable from the clause's own AST with no cross-clause
    # inference and no doubt about the callee's contract.
    _LIST_PRODUCING_GOALS = {
        ("findall", 3): 2,
        ("bagof", 3): 2,
        ("setof", 3): 2,
        ("msort", 2): 1,
        ("sort", 2): 1,
        ("sort", 4): 3,
    }

    def _clause_binding_sites(self):
        """Every binding occurrence in the CURRENT clause, as name → [RHS].

        A "binding" is any place the clause can give a name its value:

        * ``V is X`` — Clausal's ``is`` is UNIFICATION, and unification is
          symmetric, so this binds ``V`` to ``X`` and, when ``X`` is itself a
          name, ``X`` to ``V``. Both directions are recorded.
        * a call to a goal in :attr:`_LIST_PRODUCING_GOALS` whose output
          argument is a name — recorded as ``None``, meaning "bound to a
          proper list by construction".

        Clause-local by construction: the walk never leaves
        ``self._current_stmt``.
        """
        bindings: dict[str, list] = {}
        stmt = self._current_stmt
        if stmt is None:
            return bindings
        for sub in python_ast.walk(stmt):
            if (isinstance(sub, python_ast.Compare)
                    and len(sub.ops) == 1
                    and isinstance(sub.ops[0], python_ast.Is)):
                left, right = sub.left, sub.comparators[0]
                if isinstance(left, python_ast.Name):
                    bindings.setdefault(left.id, []).append(right)
                if isinstance(right, python_ast.Name):
                    bindings.setdefault(right.id, []).append(left)
            if (isinstance(sub, python_ast.Call)
                    and isinstance(sub.func, python_ast.Name)
                    and not sub.keywords):
                idx = self._LIST_PRODUCING_GOALS.get(
                    (sub.func.id, len(sub.args)))
                if idx is not None:
                    out = sub.args[idx]
                    if isinstance(out, python_ast.Name):
                        bindings.setdefault(out.id, []).append(None)
        return bindings

    def _clause_local_list_vars(self) -> set[str]:
        """Names this clause proves to be a proper list on EVERY binding.

        A name qualifies only when it has at least one binding in the clause
        and **all** of its bindings are list-producing — a list display, a
        list-producing goal's output, or another qualifying name. A single
        binding that is not provably a list DISQUALIFIES the name outright.

        That "all bindings" rule is the whole point, and it is what makes the
        analysis control-flow-safe without tracking control flow. The walk
        cannot tell a disjunct from a conjunct, so an earlier version that
        qualified a name on ANY list binding was unsound via aliasing::

            p(K, D) <- ((V is D) or (V is [a, b]), K not in V)

        There ``V`` may be the dict ``D`` at the membership site, and
        ``\\+ member(K, V)`` is silently always true — precisely the hazard
        this refusal exists to close. Requiring every binding to be
        list-producing rejects that clause, because ``V is D`` is not.

        The result is therefore a CONSERVATIVE approximation of control flow:
        merging all branches and demanding they all produce a list can only
        *narrow* what is accepted relative to any single real execution path,
        so an imprecision here costs an extra refusal, never a missed one.

        Resolution is a LEAST fixpoint, starting from nothing and adding only
        names whose bindings are already known provable. Cyclic bindings
        (``V is [a, *V]``) therefore never qualify — fail-closed.
        """
        if self._provable_lists is not None:
            return self._provable_lists
        bindings = self._clause_binding_sites()
        qualified: set[str] = set()
        while True:
            added = False
            for name, rhss in bindings.items():
                if name in qualified:
                    continue
                if rhss and all(
                        self._binding_is_list(r, qualified) for r in rhss):
                    qualified.add(name)
                    added = True
            if not added:
                break
        self._provable_lists = qualified
        return qualified

    def _binding_is_list(self, node, qualified: set[str]) -> bool:
        """True when a single binding RHS provably yields a proper list.

        *qualified* is the set of names already proven, threaded through so
        the fixpoint in :meth:`_clause_local_list_vars` stays monotone (this
        must NOT call back into ``_clause_local_list_vars``, which would
        recurse).
        """
        if node is None:
            return True                      # list-producing goal output
        if isinstance(node, python_ast.List):
            return all(
                self._binding_is_list(e.value, qualified)
                for e in node.elts
                if isinstance(e, python_ast.Starred)
            )
        if isinstance(node, python_ast.Name):
            return node.id in qualified
        return False

    def _is_provably_list(self, node: python_ast.expr) -> bool:
        r"""True when *node* is PROVABLY a proper list at this site.

        The rule is deliberately minimal and syntactic — there is no type
        inference here, and anything not matched below refuses:

        (a) a list display ``[a, b, c]``. A display with a splat tail
            (``[H, *T]``, Clausal's ``[H|T]``) qualifies only when the tail is
            itself provably a list, because ``[H|T]`` with an unbound ``T`` is
            a PARTIAL list and ``\+ member/2`` over one is exactly as unsound
            as over a dict.
        (b) a variable ALL of whose clause-local bindings produce a list —
            see :meth:`_clause_local_list_vars`.

        Everything else — a bare parameter, a call result, an attribute, a
        dict — is NOT provably a list. Exported dicts (attribute-lists) land
        here, which is the point: ``\+ member(K, Dict)`` is silently
        always-true, and that is the emission this refusal removes.
        """
        if isinstance(node, python_ast.List):
            return all(
                self._is_provably_list(e.value)
                for e in node.elts
                if isinstance(e, python_ast.Starred)
            )
        if isinstance(node, python_ast.Name):
            return node.id in self._clause_local_list_vars()
        return False

    def _check_negated_membership(self, right: python_ast.expr) -> bool:
        """Refuse a NEGATED membership whose RHS is not provably a list.

        Returns True when the site was refused. Positive membership is NOT
        checked here: the operator explicitly deferred that polarity, because
        positive ``member/2`` over a dict fails loudly (absent derivation)
        rather than succeeding silently.
        """
        if self._is_provably_list(right):
            return False
        self._add_warning(
            "negated membership over a value not provably a list: "
            + python_ast.unparse(right)
            + " — if the RHS is a dict/profile, respell via the accessor "
            "(not profile_has(P, K)); see the 2026-09-03 decision"
        )
        return True

    def _lower_arrow_lambda_in_term_position(
            self, node: python_ast.Compare) -> PTerm | None:
        """Lower a `<-` lambda in TERM position to `library(lambda)`.

        `(U, V) <- Body` becomes `\\U^V^Body`, a real closure both reference
        engines can meta-call. Until 2026-09-14 this site refused instead: the
        emission before that was inert `</2` operator soup — `include(D < -(…))`
        — data rather than a closure, which never ran and said nothing.

        The lambda arrow `<-` and the comparison `< -` parse to the SAME AST;
        only source spacing separates them, so this mirrors the engine's own
        clause-level rule via :func:`_engine_is_arrow_adjacent`. `a < -b`, a
        genuine comparison against a negated term, is untouched.

        CAPTURE SEMANTICS, WHICH IS THE WHOLE OF THE DESIGN HERE. A body
        variable that is neither a parameter nor local — one the enclosing
        clause's head also binds — is a CAPTURE. `library(lambda)`'s plain
        `\\` copies the closure per call, so a capture flows its VALUE in;
        `+\\` opts into true sharing instead. This emits `\\`, matching the
        capture-by-value rule the lambda design note records, under which a
        bound capture flows in and an unbound one contributes a fresh variable
        per call.

        Measured 2026-09-14 on both reference engines:

            maplist(\\X^Y^(Y is X*2), [1,2,3], L)        L = [2,4,6]
            P = 7, maplist(P+\\X^Y^(Y is X+P), [1], L)   L = [8]
            unbound F, undeclared                        fresh var per call

        WHY OUTPUT-THROUGH-A-CAPTURE IS REFUSED RATHER THAN LOWERED. The
        interpreter today SHARES a capture, so a binding made inside a lambda
        reaches the enclosing clause. Under `\\` it would not, and the
        difference is SILENT — a different answer, never an error. That
        capability is deliberately unsettled pending a design decision
        (operator, 2026-09-14: "I'm trying to avoid them"), so a lambda that
        binds one of its captures is refused here, by name, instead of being
        lowered into a quiet behaviour change. Refusing makes "avoid output
        captures" checkable rather than a convention.

        A capture the lambda only READS is unaffected: copy-per-call and
        sharing flow the same value, so the lowering is answer-preserving.

        Returns the lowered term, or None when the site was refused (a warning
        has been recorded in that case).
        """
        if not _is_arrow_lambda_shape(node, self._source_lines):
            return None
        usub_node, _depth = _engine_leftmost_usub(node.comparators[0])

        source = python_ast.unparse(node)
        params = _lambda_parameter_names(node.left)
        if params is None:
            self._add_warning(
                "`<-` lambda in term position with a non-variable parameter: "
                + source
                + " — a lambda's parameters must be plain variables to lower "
                "to library(lambda); write them as variables, or define a "
                "named auxiliary predicate and pass its name instead")
            return None

        body_ast = usub_node.operand
        captures = (_variable_names(body_ast) - set(params)) & self._enclosing_head_vars
        written = captures & _names_bound_in(body_ast)
        if written:
            self._add_warning(
                "`<-` lambda in term position binds a CAPTURED variable ("
                + ", ".join(sorted(written)) + "): " + source
                + " — the interpreter shares a capture, so that binding is "
                "visible to the enclosing clause; library(lambda)'s `\\` "
                "copies per call and it would not be, silently. Output "
                "through a capture is an open design question, so this is "
                "refused rather than lowered. Pass the value out through a "
                "lambda PARAMETER, or define a named auxiliary predicate.")
            return None

        body = self._convert_expr(body_ast, goal_position=True)
        term = body
        for name in reversed(params):
            term = PCompound("^", (PVar(clausal_var_to_prolog(name)), term))
        self._emitted_arrow_lambda = True
        return PCompound("\\", (term,))

    def _convert_compare(self, node: python_ast.Compare, goal_position: bool = False) -> PTerm:
        """Convert comparison operators.

        Handles special clausal patterns:
        - X is Y → X = Y (Unify)
        - X is not Y → dif(X, Y) (DoesNotUnify)
        - X == Y → X == Y (structural) / X =:= Y+1 (arithmetic operand)
        - X != Y → X \\== Y (structural) / X =\\= Y+1 (arithmetic operand)

        *goal_position* gates the `is`-RHS dict-splat → `attrs_put/3` lowering
        (see `_convert_is_rhs_splat`) AND the dict-subscript →
        `profile_get_strict/3` lowering (see `_convert_is_subscript`): both
        rewrites produce a goal, which is only valid Prolog when the `is`
        comparison is itself executed as a goal (the whole clause body, or a
        body conjunct). Reached in a nested/argument position (e.g.
        `q(X is {**D, k: v})` or `q(P[k])`, an argument to `q`),
        `attrs_put(...)`/`profile_get_strict(...)` would sit there as an
        inert, never-called data term — silently wrong output. So when
        *goal_position* is False, both stay on the generic untranslatable
        warning path.

        `attrs_put/3` and `profile_get_strict/3` are ISO-export staging
        predicates — neither exists under SWI dict semantics, so both
        lowerings also require `not self.dialect.has_dicts`. Under a
        `has_dicts` dialect the splat instead falls through to the plain
        `X = Dict` unify, where `_convert_dict`'s SWI branch renders the
        splat's `**D` entry as a `_=D` pair inside `dict_create/3`
        (pre-existing behavior, unchanged by this gate); a subscript under a
        `has_dicts` dialect falls through unchanged too (no SWI-native
        subscript lowering is implemented — out of scope here, same as
        before this change).

        `profile_get_strict/3` (companion-defined in
        tools/iso_export/companion/clausal_profiles.pl, trunk repo) mirrors
        the engine's strict, throw-on-missing-key subscript-read semantics
        exactly (`clausal/logic/runtime/dict_ops.py:_subscript`) — it is
        deliberately NOT `profile_get/3`, which is the dialect's rename
        target for the engine's soft, fail-on-missing `get/3` builtin
        (`prolog_dialect.py`'s `"get": {"iso": "profile_get"}`) and has the
        OPPOSITE missing-key behavior. Reusing `profile_get` here would
        silently turn "profile is missing a required field" into "clause
        fails" in every exported program — probed and rejected, see
        `_convert_is_subscript`'s docstring and
        .superpowers/sdd/2026-09-05-class-M/c-pre-report.md (trunk repo).
        """
        # A `<-` lambda reaching term position is a CLOSURE, lowered to
        # library(lambda) (2026-09-14; it was refused outright from
        # 2026-09-03). Checked before any Lt lowering, and on the chained
        # path too. A refusal returns None having warned, and in strict mode
        # the warning is what raises, so the placeholder is never emitted.
        if _is_arrow_lambda_shape(node, self._source_lines):
            lowered = self._lower_arrow_lambda_in_term_position(node)
            return lowered if lowered is not None else PAtom("???")

        # Handle single comparison
        if len(node.ops) == 1:
            op = node.ops[0]

            # Membership. Negated membership over a value not provably a list
            # is untranslatable (2026-09-03); positive membership is
            # unchanged — the operator deferred that polarity.
            if isinstance(op, python_ast.In):
                return PCompound("member", (
                    self._convert_expr(node.left),
                    self._convert_expr(node.comparators[0]),
                ))
            if isinstance(op, python_ast.NotIn):
                if self._check_negated_membership(node.comparators[0]):
                    return PAtom("???")
                return PCompound("\\+", (
                    PCompound("member", (
                        self._convert_expr(node.left),
                        self._convert_expr(node.comparators[0]),
                    )),
                ))

            if (goal_position and not self.dialect.has_dicts
                    and isinstance(op, python_ast.Is)
                    and isinstance(node.comparators[0], python_ast.Dict)):
                splat_goal = self._convert_is_rhs_splat(
                    node.left, node.comparators[0])
                if splat_goal is not None:
                    return splat_goal

            if (goal_position and not self.dialect.has_dicts
                    and isinstance(op, python_ast.Is)):
                subscript_goal = self._convert_is_subscript(
                    node.left, node.comparators[0])
                if subscript_goal is not None:
                    return subscript_goal

            left = self._convert_expr(node.left)
            right = self._convert_expr(node.comparators[0])

            if isinstance(op, python_ast.Is):
                # Check for "is not"
                if (isinstance(node.comparators[0], python_ast.Compare)
                        and len(node.comparators[0].ops) == 1
                        and isinstance(node.comparators[0].ops[0], python_ast.Not)):
                    # This shouldn't happen with standard Python parsing
                    pass
                return PCompound("=", (left, right))

            if isinstance(op, python_ast.IsNot):
                return PCompound("dif", (left, right))

            if isinstance(op, python_ast.Eq):
                # Operator ruling 2026-09-18: UNQUOTED `==` in .seam means
                # arithmetic in the CLP sense. It compiles to `nodes.ArithEq`,
                # a CLP(FD) constraint that BINDS and PROPAGATES -- not a test
                # that happens to bind -- so `#=` is the only ISO-reachable
                # spelling correct in every mode. ISO term identity is written
                # `'=='(L, R)`, which reaches the quoted-functor path, not this
                # one.
                #
                # WHAT THIS REPLACES. The choice was `_is_arith_operand`: eight
                # lines, purely syntactic, with NO "cannot tell" branch -- where
                # it saw no BinOp it did not refuse, it DEFAULTED to structural.
                # Measured over 641,437 executions at 903 sites, 45 sites take
                # TWO arithmetic modes at one call site, binding on one call and
                # testing on another. `=:=` raises instantiation_error on the
                # binding call and `is` is wrong for the testing one, so no
                # static rule could have been right for those 45.
                #
                # THE ORDER MATTERED. All 167 measured-structural sites were
                # respelled to `'=='(L, R)` FIRST (corpus 10ed4f72 + ed7f9d21,
                # downstream 379075d). Landing this first would have turned 167
                # identity comparisons into constraints, silently.
                #
                # COST, accepted with the ruling: `#=` is the dialect's
                # constraint library, not ISO, so a domain using one is no
                # longer pure-ISO. The import travels with the emission --
                # see `_emitted_clp_arith_eq` and the prelude.
                #
                # LIMIT, ruled 2026-09-19 after it was measured: the CLP(Z)
                # solvers are over the INTEGERS, so a FLOAT operand raises
                # `domain_error(clpz_expression, F)` where `=:=` would have
                # succeeded. `#=` therefore expresses INTEGER arithmetic
                # equality only. Accepted because the alternative is a static
                # operand-shape test, which is what this ruling replaced, and
                # which cannot see a float that arrives through a variable
                # anyway. Corpus exposure when the ruling was taken: 0 of 361
                # unquoted `==` sites carried a float literal or a Decimal.
                self._emitted_clp_arith_eq = True
                return PCompound("#=", (left, right))

            if isinstance(op, python_ast.NotEq):
                return self._not_equal(left, right)

            if isinstance(op, python_ast.Lt):
                # <- is Lt + USub (handled at statement level); pure Lt is <.
                return PCompound("<", (left, right))

            if isinstance(op, python_ast.LtE):
                return PCompound("=<", (left, right))

            if isinstance(op, python_ast.Gt):
                return PCompound(">", (left, right))

            if isinstance(op, python_ast.GtE):
                return PCompound(">=", (left, right))

        # Multi-comparison: chain into conjunction
        parts = []
        prev = self._convert_expr(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self._convert_expr(comp)
            if isinstance(op, python_ast.Is):
                parts.append(PCompound("=", (prev, right)))
            elif isinstance(op, python_ast.IsNot):
                parts.append(PCompound("dif", (prev, right)))
            elif isinstance(op, python_ast.Eq):
                parts.append(PCompound("==", (prev, right)))
            elif isinstance(op, python_ast.NotEq):
                parts.append(self._not_equal(prev, right))
            elif isinstance(op, python_ast.Lt):
                parts.append(PCompound("<", (prev, right)))
            elif isinstance(op, python_ast.LtE):
                parts.append(PCompound("=<", (prev, right)))
            elif isinstance(op, python_ast.Gt):
                parts.append(PCompound(">", (prev, right)))
            elif isinstance(op, python_ast.GtE):
                parts.append(PCompound(">=", (prev, right)))
            elif isinstance(op, python_ast.In):
                parts.append(PCompound("member", (prev, right)))
            elif isinstance(op, python_ast.NotIn):
                if self._check_negated_membership(comp):
                    parts.append(PAtom("???"))
                else:
                    parts.append(PCompound("\\+", (
                        PCompound("member", (prev, right)),
                    )))
            prev = right

        if len(parts) == 1:
            return parts[0]
        result = parts[-1]
        for p in reversed(parts[:-1]):
            result = PCompound(",", (p, result))
        return result

    def _convert_ifexp(self, node: python_ast.IfExp) -> PTerm:
        """Reject Clausal if-then-else → Prolog (C -> T ; E) translation.

        Clausal's reified if-then-else has monotonic, three-valued semantics
        that cannot be faithfully represented by Prolog's committed-choice
        (C -> T ; E), which is defined in terms of cut.
        """
        from clausal.tools.prolog_to_clausal import PrologTranslationError
        raise PrologTranslationError(
            "Clausal's if-then-else (THEN if COND else ELSE) cannot be "
            "translated to Prolog.\n"
            "Clausal's reified ITE has monotonic, three-valued semantics "
            "that differ from Prolog's committed-choice (C -> T ; E), "
            "which is defined in terms of cut.\n"
            "To translate this program, rewrite as separate clauses with "
            "dif/2 guards or constraint-based branching."
        )

    def _convert_dcg_body(self, node) -> PTerm:
        """Convert DCG rule body, wrapping inline goals in {curly}."""
        # For now, treat the same as regular body conversion
        return self._convert_expr(node)

    def _get_string_or_name(self, node) -> str:
        """Extract string from a Constant or Name node."""
        if isinstance(node, python_ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, python_ast.Name):
            return node.id
        # Attribute chain: foo.bar.baz
        if isinstance(node, python_ast.Attribute):
            parts = []
            current = node
            while isinstance(current, python_ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, python_ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return str(node)

    def _convert_fstring(self, node: python_ast.JoinedStr) -> PTerm:
        """Convert f-string to format/2 (SWI) or warning.

        f"Hello {Name}, you have {Count} items"
        → format("Hello ~w, you have ~w items", [Name, Count])  (SWI)
        → warning comment + ??? (ISO/Scryer)
        """
        fmt_parts = []
        args = []
        for value in node.values:
            if isinstance(value, python_ast.Constant) and isinstance(value.value, str):
                # Literal text — escape ~ for Prolog format
                fmt_parts.append(value.value.replace("~", "~~"))
            elif isinstance(value, python_ast.FormattedValue):
                fmt_parts.append("~w")
                args.append(self._convert_expr(value.value))
            else:
                fmt_parts.append("~w")
                args.append(self._convert_expr(value))
        fmt_string = "".join(fmt_parts)

        if self.dialect.name == "swi":
            return PCompound("format", (
                PString(fmt_string),
                PList(tuple(args)),
            ))
        # ISO / Scryer: untranslatable
        self._add_warning(f'f-string: f"{fmt_string}"')
        return PAtom("???")

    def _dict_attr_list(self, keys, values) -> tuple[PTerm, ...]:
        """Build a key-sorted ``attribute(K, V)`` list from parallel
        key/value node sequences.

        Callers must ensure *keys* contains no splat (``**``, i.e. ``None``)
        entries — this only builds the plain-pair list shared by
        :meth:`_convert_dict` (ISO branch) and :meth:`_convert_is_rhs_splat`.
        """
        pairs = [(self._convert_expr(k), self._convert_expr(v))
                 for k, v in zip(keys, values)]
        pairs.sort(key=lambda kv: emit_term(kv[0], self.dialect.operator_table))
        return tuple(PCompound("attribute", (k, v)) for k, v in pairs)

    def _convert_is_rhs_splat(self, left_node, dict_node: python_ast.Dict):
        """Lower ``X is {**D, k1: v1, ...}`` to
        ``attrs_put(D, [attribute(k1, v1), ...], X)``.

        Only the single-splat-FIRST shape (the downstream ``override_key``
        idiom) is translatable this way. Returns ``None`` for any other
        shape — no splat, splat not first, or more than one splat — so the
        caller falls through to the generic ``is``/dict handling, which
        keeps the existing warning/strict-raise path for those cases.
        """
        keys, values = dict_node.keys, dict_node.values
        if not keys or keys[0] is not None:
            return None  # no splat, or the splat isn't the first entry
        if any(k is None for k in keys[1:]):
            return None  # multi-splat — stays untranslatable

        left = self._convert_expr(left_node)
        splat_target = self._convert_expr(values[0])
        attr_list = self._dict_attr_list(keys[1:], values[1:])
        return PCompound("attrs_put", (splat_target, PList(attr_list), left))

    def _convert_is_subscript(self, left_node, right_node) -> PTerm | None:
        """Lower a goal-position ``is`` comparison with a dict-subscript on
        EITHER side to ``profile_get_strict(Profile, Key, Value)``.

        ``is``/2 is symmetric in Clausal (``_convert_compare`` just converts
        both sides and unifies them), and the corpus actually uses both
        spellings: ``V is P[K]`` (the shape named in the C-pre brief) and
        ``P[K] is V`` (three real downstream sites, e.g.
        ``PROFILE[grounds] is GROUND_LIST``). Whichever side is the
        Subscript becomes ``profile_get_strict``'s first two arguments; the
        other side becomes its third.

        Returns ``None`` — falling through to the generic untranslatable
        path, exactly like :meth:`_convert_is_rhs_splat` — for every shape
        this does NOT cover:

        - neither side is a Subscript (an ordinary ``is``, unrelated to this
          lowering);
        - the Subscript's own base is itself a Subscript (chained, ``P[a][b]``)
          or a Call result (``f()[a]``) — no downstream consumer for either
          (censused: every subscript site is unchained and none is
          call-based), so these refuse rather than inventing
          semantics for an unwitnessed shape; falling through re-converts
          the Subscript via the generic ``_convert_expr`` path, which has no
          Subscript case and so warns/strict-raises, same as before this
          lowering existed.

        ``profile_get_strict/3`` is a NEW companion-defined staging
        predicate (tools/iso_export/companion/clausal_profiles.pl, trunk
        repo) — deliberately not ``profile_get/3``. ``profile_get/3`` is the
        dialect's rename target for the engine's ``get/3`` builtin
        (``prolog_dialect.py``'s ``"get": {"iso": "profile_get"}``), which
        FAILS on a missing key by design
        (``clausal/logic/builtins/dict_set.py``'s ``_get__3`` docstring).
        The engine's strict subscript read instead RAISES a catchable
        ``existence_error(dict_key, Key)`` on a missing key
        (``clausal/logic/runtime/dict_ops.py:_subscript``, pinned by
        ``tests/test_dict_set_compiler.py::test_subscript_missing_throws``).
        Lowering the strict read to the soft-fail predicate was probed and
        rejected (.superpowers/sdd/2026-09-05-class-M/c-pre-report.md, trunk
        repo, "BLOCKED" section) — it would silently turn "profile is
        missing a required field" into "clause fails" in every exported
        program. ``profile_get_strict/3`` exists so the exported program's
        missing-key behavior matches the live engine's instead.
        """
        if isinstance(left_node, python_ast.Subscript):
            subscript_node, value_node = left_node, right_node
        elif isinstance(right_node, python_ast.Subscript):
            subscript_node, value_node = right_node, left_node
        else:
            return None  # neither side is a subscript — not this lowering

        base = subscript_node.value
        if isinstance(base, (python_ast.Subscript, python_ast.Call)):
            return None  # chained / subscript-on-call-result — refuse

        profile = self._convert_expr(base)
        key_node = subscript_node.slice
        if isinstance(key_node, python_ast.Index):  # pre-3.9 AST compat
            key_node = key_node.value
        key = self._convert_expr(key_node)
        value = self._convert_expr(value_node)
        return PCompound("profile_get_strict", (profile, key, value))

    def _convert_dict(self, node: python_ast.Dict) -> PTerm:
        """Convert dict literal: SWI dict, or key-sorted attribute-list (ISO)."""
        if self.dialect.has_dicts:
            # SWI dict: tag{key: val, ...}
            # Emit as: dict_create(D, _, [key=val, ...]) or use Tag.put_dict
            # For now, emit as a compound with key=value pairs
            pairs = []
            for k, v in zip(node.keys, node.values):
                key = self._convert_expr(k) if k is not None else PAtom("_")
                val = self._convert_expr(v)
                pairs.append(PCompound("=", (key, val)))
            if not pairs:
                return PAtom("_{}")
            return PCompound("dict_create", (
                PVar("_"),
                PAtom("_"),
                PList(tuple(pairs)),
            ))
        # ISO / Scryer / Trealla: lower to a key-sorted attribute(K, V) list.
        if any(k is None for k in node.keys):  # {**expr} splat — no static key set
            self._add_warning("dict splat " + python_ast.unparse(node))
            return PAtom("???")
        return PList(self._dict_attr_list(node.keys, node.values))


# ── Singleton variable post-pass ────────────────────────────────────────

def _prefix_singletons(item: PItem) -> PItem:
    """Rename every singleton (exactly-one-occurrence) variable in *item*
    to a ``_``-prefixed name.

    ISO engines (Scryer) warn on a singleton variable — a name occurring
    only once anywhere it appears. The corpus deliberately writes some
    variables exactly once (a fact-head "any value" position, e.g.
    ``schedule_by_criteria(high, no_accepted_medical_use, DEPENDENCE,
    schedule_i)``), relying on Prolog's convention that a leading ``_``
    silences the warning. ``DEPENDENCE`` crosses unchanged and carries no
    leading underscore, so Scryer would warn on it — this pass adds one at
    emission time without touching source semantics (a rename only;
    unification is unaffected). It used to have a second job: names were
    mangled on the way out, and ``clausal_var_to_prolog`` turned a Clausal
    ``_x``-style singleton into ``X``, un-silencing a warning the source had
    deliberately silenced. Names cross unchanged now, so ALL-CAPS singletons
    are what this pass is still for.

    Counted over *item* alone (clause head+body together, a fact's args,
    or a DCG rule's head+body), because a variable name has no meaning
    across top-level items in the first place. This used to be phrased as
    "the same scope convert_module resets its variable-rename table on";
    that table is gone, and per-item is now this pass's own rule rather
    than one borrowed from it.
    The anonymous variable (``_``) is exempt — every occurrence is already
    independent, so it is never "a singleton" in the sense that matters
    here. A name already spelled with a leading underscore (every Clausal
    ``_x``-style singleton, now that names cross unchanged) is left as-is
    rather than double-prefixed.

    Two further cases DECLINE the rename, and both were unreachable while
    variable names were mangled on the way out. The old mangler stripped
    leading underscores and made every base name distinct, so ``"_" + name``
    was guaranteed to be both free and variable-shaped. This pass never
    depended on the rename table's PURPOSE, but it did depend on that
    property of its OUTPUT, and the property left with it:

    * **The target is already a live name.** A source may carry both ``X``
      and ``_X``. If ``X`` is a singleton, prefixing it produces ``_X`` --
      the other variable -- and the clause silently unifies two distinct
      arguments. That is the F022 defect exactly, reached by a pass that maps
      no names at all. Counts are taken over the whole item before any
      rename, so the check sees every name including ones this pass would
      not touch.
    * **The result would not be a variable.** ``X_`` is a legal Clausal
      variable; ``_X_`` is a module CONSTANT, so prefixing emits a name that
      does not read back as a variable, and a file that loaded fine exports
      to a `.pl` whose re-import will not load. (The inbound translator used
      to strip trailing underscores and absorb this; it no longer renames.)

    Declining costs a singleton warning from the target engine. That is worth
    strictly less than a wrong answer or an unloadable round trip, and unlike
    either of those it is visible to the user.

    A plain AST rewrite, applied per item by construction: walking every
    PVar in the item's subterms means DCG hidden args, nested compounds,
    and list elements are all covered without enumerating term shapes by
    hand.
    """
    counts: dict[str, int] = {}

    class _Counter(PrologVisitor):
        def visit_PVar(self, node):
            if node.name != "_":
                counts[node.name] = counts.get(node.name, 0) + 1

    _Counter().visit(item)

    singletons = {name for name, n in counts.items() if n == 1}
    if not singletons:
        return item

    class _Renamer(PrologTransformer):
        def visit_PVar(self, node):
            if node.name not in singletons or node.name.startswith("_"):
                return node
            prefixed = "_" + node.name
            if prefixed in counts:
                return node          # already another variable in this item
            return PVar(prefixed, unit=node.unit)

    return _Renamer().visit(item)


# ── Module export / discontiguous post-pass ────────────────────────────
#
# Shared by convert_module's post-pass (Task 4: filter dead module
# exports; Task 5: emit :- discontiguous for interrupted clause runs).

def _clause_key(item: PItem) -> tuple[str, int] | None:
    """(functor, arity) for a PClause head; None for any other item kind.

    DCG rules deliberately return None here — a DCG predicate's real
    callable arity (written arity + 2 hidden state args) is computed
    separately by _dcg_head_key. Combined with it via _run_key for
    clause-run/interruption tracking, so both PClause and PDCGRule runs
    are covered.
    """
    if not isinstance(item, PClause):
        return None
    head = item.head
    if isinstance(head, PCompound):
        return (head.functor, len(head.args))
    if isinstance(head, PAtom):
        return (head.name, 0)
    return None


def _dcg_head_key(item: PItem) -> tuple[str, int] | None:
    """(functor, explicit_arity + 2) for a PDCGRule head; None otherwise.

    A ``-->`` clause is expanded (by the Prolog engine, not this
    translator) to take two extra difference-list state arguments, so a
    DCG predicate's real callable arity is the written arity plus 2. A
    pushback/semicontext head arrives as a comma pair
    ``(Call, PushbackList)`` — the callable predicate is the left side.
    """
    if not isinstance(item, PDCGRule):
        return None
    head = item.head
    if isinstance(head, PCompound) and head.functor == "," and len(head.args) == 2:
        head = head.args[0]
    if isinstance(head, PCompound):
        return (head.functor, len(head.args) + 2)
    if isinstance(head, PAtom):
        return (head.name, 2)
    return None


def _run_key(item: PItem) -> tuple[str, int] | None:
    """(name, arity) for clause-run/interruption tracking; None to be skipped.

    Unifies PClause (as written) and PDCGRule (+2 hidden state args, via
    _dcg_head_key — the same indicator Scryer calls the translated DCG
    predicate with, and the same one _filter_module_exports uses for
    module exports) into one run-tracking key. Anything else — module
    directives, discontiguous directives, comments — returns None and is
    skipped by the caller: it neither starts nor breaks a run.
    """
    key = _clause_key(item)
    if key is not None:
        return key
    return _dcg_head_key(item)


#: Meta-callers the body-local detector recognises, as
#: ``(functor, arity) -> (index of the goal argument, arguments appended to it)``.
#: The appended count IS the mode Scryer wants: ``call_goal(G, A, B, C)`` applies G
#: to three arguments, so G's position is mode ``3`` (§3.3, measured).
#:
#: `call_goal/N` is the downstream higher-order protocol and, measured over it,
#: the only meta-caller a real host reaches. `call/N` is registered in the engine as
#: an alias of the same trampolines
#: (``clausal/logic/builtins/higher_order.py:46-50``) and is here for that reason.
#:
#: NOTHING SPECULATIVE BELONGS IN THIS TABLE. An earlier draft carried `include/3`,
#: `exclude/3`, `max_by/3` and `min_by/3` on the reasoning that a host reaching one
#: *would* be a meta host. They were removed: no downstream host reaches any of them, and
#: they are exactly the shapes a legal corpus is most likely to use as ordinary data
#: constructors, so carrying them bought nothing and risked annotating a data
#: position. Step B re-adds `include/3` when the `clausal_hof` companion exists and
#: something actually consumes it.
META_CALLER_SIGNATURES: dict[tuple[str, int], tuple[int, int]] = {
    **{("call_goal", n): (0, n - 1) for n in range(1, 9)},
    **{("call", n): (0, n - 1) for n in range(1, 9)},
}

#: The mode for a position that IS a goal but whose call arity is not single-valued.
#: ISO's "module-sensitive term": Scryer qualifies the argument at the call site
#: WITHOUT binding it to a name/arity. See :func:`collect_local_meta_modes` for why an
#: integer cannot be used there, and why ``0`` is not a safe stand-in either.
MODE_MODULE_SENSITIVE = ":"

#: What a caller may hand the translator as *meta_modes*: a module path, then each of
#: that module's predicates, then one mode per argument -- an ``int`` for a goal called
#: at that fixed arity, :data:`MODE_MODULE_SENSITIVE` for a goal whose call arity
#: varies, ``None`` for a position that is not a meta position at all. Mirrors
#: *module_signatures*' shape and is keyed the same way.
MetaModeMap = dict[str, dict[tuple[str, int], tuple[int | str | None, ...]]]

#: Goal combinators, as ``(functor, arity) -> indexes of the arguments that are GOALS``.
#: Used to walk a clause body through goal positions only. Everything absent from this
#: table is a leaf as far as the walk is concerned: it is itself a goal, but its
#: arguments are DATA and are never descended into.
GOAL_TRANSPARENT: dict[tuple[str, int], tuple[int, ...]] = {
    (",", 2): (0, 1),
    (";", 2): (0, 1),
    ("->", 2): (0, 1),
    ("*->", 2): (0, 1),
    ("\\+", 1): (0,),
    ("not", 1): (0,),
    ("once", 1): (0,),
    ("ignore", 1): (0,),
    ("call", 1): (0,),
    ("forall", 2): (0, 1),
    ("catch", 3): (0, 2),
    ("findall", 3): (1,),
    ("findall", 4): (1,),
    ("bagof", 3): (1,),
    ("setof", 3): (1,),
    ("aggregate_all", 3): (1,),
    ("^", 2): (1,),
}


def goal_subterms(body: PTerm) -> Iterator[PTerm]:
    """Yield the goals of a clause *body*, and ONLY the goals.

    Descends through the goal combinators of :data:`GOAL_TRANSPARENT` -- so a goal
    under ``once/1``, in a ``findall/3`` goal argument, or in either branch of a
    ``;/2`` is reached -- and stops at everything else: a plain compound is yielded
    as a goal, but its arguments are DATA and are not walked.

    THIS IS A CORRECTNESS FENCE, NOT AN OPTIMISATION. A blanket ``subterms`` walk
    cannot tell a meta-call from a term that merely LOOKS like one, so a clause that
    only BUILDS such a term --

        mk(D, X, Y, T) <- unify(T, include(D, X, Y))

    -- would have ``D`` read as a meta position, and the emitted directive would make
    Scryer module-qualify an ordinary data argument at every call site. Measured
    consequence: the caller gets back ``user_m:foo`` where it passed ``foo``, so a
    later ``X == foo`` FAILS, silently and with no error anywhere. That is precisely
    the class of silent wrongness this ladder exists to remove, so the walk is
    fenced at the source rather than filtered afterwards.
    """
    stack = [body]
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, PCompound):
            continue
        for index in GOAL_TRANSPARENT.get((node.functor, len(node.args)), ()):
            if index < len(node.args):
                stack.append(node.args[index])


def collect_local_meta_modes(pmodule: PModule) -> dict[tuple[str, int], dict[int, int | str]]:
    """Meta positions provable from *pmodule*'s own clause bodies.

    A predicate has a meta position at argument *i* when one of its clauses applies a
    known meta-caller (:data:`META_CALLER_SIGNATURES`) to the variable sitting at head
    position *i*. The search runs over :func:`goal_subterms`, i.e. over GOAL POSITIONS
    ONLY -- a term that merely looks like a meta-call, sitting in an argument of some
    other goal, is data and is never read as evidence.

    Returns ``{(name, arity): {argument index: mode}}``. This is a LOWER BOUND, and
    deliberately so: a host that only threads its argument onward has no body-local
    evidence at all, and guessing one would be worse than the loud failure. Measured
    over the downstream sources, the bound covers most lambda-site hosts; the other
    116 sit at threading hosts and are the exporter fixpoint's job.

    THE AMBIGUOUS-POSITION CONTRACT (controller ruling of 2026-09-05, implemented with
    the mechanism the ruling's premise got wrong -- see below). When two clauses call
    the same argument with DIFFERENT arities the position is still, beyond doubt, a
    goal; only the integer is in question. It is annotated
    :data:`MODE_MODULE_SENSITIVE` (``:``), which qualifies the argument without binding
    an arity, so EVERY chain works. ``?`` stays reserved for positions with NO goal
    evidence at all.

    WHY NOT THE MAXIMUM, AND WHY NOT ``0``. The ruling assumed Scryer reads the integer
    as merely "meta"/"not meta" and ignores its value, which would have made any
    candidate safe. Measured, it does not: **mode ``N`` resolves the argument against
    ``name/N`` in the CALLER's module.** With a caller defining both ``p/2`` and
    ``p/3``, and a host calling its argument at both arities:

        mode 2 -> [short]        only the 2-appended clause resolves
        mode 3 -> [long]         only the 3-appended clause resolves
        mode 0 -> [short,long]   ... but only because no p/0 exists
        mode : -> [short,long]

    so the maximum candidate silently drops the other chain. ``0`` looks like a safe
    stand-in until the caller happens to define ``p/0``, at which point the argument
    binds to that and the caller gets back unbound variables -- no error, wrong
    answers. ``:`` is the only spelling right in all four rows.

    Where a position DOES have a single call arity the integer is emitted: it is the
    most precise annotation and is what §3.3's verified probe uses.
    """
    found: dict[tuple[str, int], dict[int, int | str]] = {}
    for item in pmodule.items:
        if not isinstance(item, PClause) or item.body is None:
            continue
        head = item.head
        if not isinstance(head, PCompound):
            continue
        key = (head.functor, len(head.args))
        position: dict[str, int] = {}
        for index, arg in enumerate(head.args):
            if isinstance(arg, PVar) and arg.name != "_":
                position.setdefault(arg.name, index)
        if not position:
            continue
        for node in goal_subterms(item.body):
            if not isinstance(node, PCompound):
                continue
            signature = META_CALLER_SIGNATURES.get((node.functor, len(node.args)))
            if signature is None:
                continue
            goal_index, appended = signature
            goal = node.args[goal_index]
            if not isinstance(goal, PVar):
                continue
            index = position.get(goal.name)
            if index is None:
                continue
            slot = found.setdefault(key, {})
            previous = slot.get(index, appended)
            slot[index] = appended if previous == appended else MODE_MODULE_SENSITIVE
    return found


def _mode_term(mode: int | str) -> PTerm:
    """One argument of a meta_predicate spec: an integer arity, or ``:``."""
    return PNumber(mode) if isinstance(mode, int) else PAtom(mode)


def _existing_meta_predicate_indicators(item: PItem) -> set[tuple[str, int]]:
    """(name, arity) already declared by a hand-written :- meta_predicate directive.

    THREE spellings count, and the third is the one this missed. ISO permits one
    directive to carry a COMMA-SEPARATED list of specs --
    ``:- meta_predicate(foo(0, ?), bar(?, 2)).`` parses as a single ``,``/2
    argument -- but a Clausal source directive ``-meta_predicate(foo(...),
    bar(...))`` arrives here as meta_predicate/2, N separate arguments, and the
    old ``len(body.args) == 1`` guard returned the empty set for it. Nothing was
    then suppressed, so the emitted file carried BOTH a generated directive per
    predicate AND the hand-written one -- and the hand-written one is invalid
    ISO at arity > 1, which is the half that actually broke the export (Scryer:
    ``domain_error(directive, meta_predicate/4)``; Trealla: unknown directive).
    Read all three; EMIT only one directive per spec -- Scryer rejects the
    comma-list outright. See :func:`_split_meta_predicate_directive`.

    A hand-written directive in ANY of the three spellings must suppress the
    generated one for every predicate it names.
    """
    if not isinstance(item, PDirective):
        return set()
    body = item.body
    if not (isinstance(body, PCompound) and body.functor == "meta_predicate"
            and len(body.args) >= 1):
        return set()

    found: set[tuple[str, int]] = set()
    pending = list(body.args)
    while pending:
        spec = pending.pop()
        if not isinstance(spec, PCompound):
            continue
        if spec.functor == "," and len(spec.args) == 2:
            pending.extend(spec.args)
            continue
        found.add((spec.functor, len(spec.args)))
    return found


def _split_meta_predicate_directive(item: PItem) -> list[PItem]:
    """Split ``meta_predicate(A, B, C)`` into one directive PER SPEC.

    MEASURED on both target engines 2026-09-26, because the obvious readings are
    both wrong and one of them was my first fix:

        :- meta_predicate(a(?, 1)).            }  one per spec
        :- meta_predicate(b(?, 2)).            }  scryer OK, trealla OK
        :- meta_predicate((a(?,1), b(?,2))).      scryer syntax_error(
                                                    invalid_meta_predicate_decl)
        :- meta_predicate a(?,1), b(?,2).         BOTH syntax_error
        :- meta_predicate(a(?,1), b(?,2)).        scryer domain_error(directive,
                                                    meta_predicate/2); trealla
                                                    warns and DROPS it

    So one directive per spec is the only spelling both engines accept, and the
    comma-list that ISO permits is not usable here whatever the standard says.

    A Clausal ``-meta_predicate(a(...), b(...))`` translates literally to the
    last of those, so a library that declared several meta specs in one
    directive -- to get Scryer's callee-module meta-call resolution -- failed to
    consult in Scryer and silently lost the declarations in Trealla.

    The ONE-argument comma-list spelling is split too, and must be: the
    indicator reader counts every spec it names as already declared, so a
    comma-list that passed through unsplit would suppress the generated
    fallback and leave the file with only the spelling Scryer rejects.
    """
    if not isinstance(item, PDirective):
        return [item]
    body = item.body
    if not (isinstance(body, PCompound) and body.functor == "meta_predicate"):
        return [item]
    specs: list[PTerm] = []
    pending = list(body.args)
    while pending:                      # left-to-right, descending `,`/2
        spec = pending.pop(0)
        if isinstance(spec, PCompound) and spec.functor == "," and len(spec.args) == 2:
            pending[0:0] = list(spec.args)
        else:
            specs.append(spec)
    if len(specs) == 1 and len(body.args) == 1:
        return [item]
    return [PDirective(PCompound("meta_predicate", (spec,))) for spec in specs]


_RESERVED_TRUTH_EXPORT_NAMES = {"true", "false", "undefined", "Undefined"}


def _reserved_truth_export_name(elt) -> str | None:
    """The truth value a -module export entry would declare, or None.

    Mirrors the engine's ``_reserved_truth_decl_name``, which its -module
    handler applies BEFORE looking at an entry's shape: ``True``/``False``
    arrive as bool ``Constant``s, ``true``/``false``/``undefined``/
    ``Undefined`` as ``Name``s, bare or applied. Extended to the indicator
    forms ``true/0`` and ``'true'/0`` and the quoted template ``'true'(X)``,
    which the engine also refuses (measured 2026-09-26 -- the indicator forms
    by a different route, a NameError at load), so that every spelling of a
    truth value is refused here as it is there.
    """
    if isinstance(elt, python_ast.BinOp) and isinstance(elt.op, python_ast.Div):
        elt = elt.left
    elif isinstance(elt, python_ast.Call):
        elt = elt.func
    if isinstance(elt, python_ast.Constant):
        if isinstance(elt.value, bool):
            return "True" if elt.value else "False"
        if isinstance(elt.value, str) and elt.value in _RESERVED_TRUTH_EXPORT_NAMES:
            return elt.value
        return None
    if isinstance(elt, python_ast.Name) and elt.id in _RESERVED_TRUTH_EXPORT_NAMES:
        return elt.id
    return None


def _is_module_directive(item: PItem) -> bool:
    """True if *item* is a ``:- module(Name, Exports).`` directive."""
    return (
        isinstance(item, PDirective)
        and isinstance(item.body, PCompound)
        and item.body.functor == "module"
        and len(item.body.args) == 2
    )


def _export_pairs(directive: PDirective) -> set[tuple[str, int]]:
    """The (name, arity) pairs a ``:- module(...)`` directive's export list names."""
    exports = directive.body.args[1]
    pairs: set[tuple[str, int]] = set()
    if not isinstance(exports, PList):
        return pairs
    for elt in exports.elements:
        if (isinstance(elt, PCompound) and elt.functor == "/" and len(elt.args) == 2
                and isinstance(elt.args[0], PAtom) and isinstance(elt.args[1], PNumber)):
            pairs.add((elt.args[0].name, int(elt.args[1].value)))
    return pairs


def _filter_module_exports(directive: PDirective,
                            defined: set[tuple[str, int]]) -> PDirective:
    """Rebuild *directive*'s export list keeping only Name/Arity pairs in *defined*."""
    mod_name, exports = directive.body.args
    if not isinstance(exports, PList):
        return directive
    kept = tuple(
        elt for elt in exports.elements
        if isinstance(elt, PCompound) and elt.functor == "/" and len(elt.args) == 2
        and isinstance(elt.args[0], PAtom) and isinstance(elt.args[1], PNumber)
        and (elt.args[0].name, int(elt.args[1].value)) in defined
    )
    return PDirective(PCompound("module", (mod_name, PList(kept))))


def _existing_discontiguous_indicators(item: PItem) -> set[tuple[str, int]]:
    """(name, arity) pairs an already-present ``:- discontiguous(...)`` names.

    A hand-written ``-discontiguous(...)`` (via _convert_meta_directive)
    emits either a single spec or a PList of specs, each either
    ``Name/Arity`` (PCompound) or a bare 0-arity atom (PAtom). Used so the
    auto-inserted directive (below) never duplicates one the source
    already wrote out.
    """
    if not (isinstance(item, PDirective) and isinstance(item.body, PCompound)
            and item.body.functor == "discontiguous" and len(item.body.args) == 1):
        return set()
    spec = item.body.args[0]
    specs = spec.elements if isinstance(spec, PList) else (spec,)
    pairs: set[tuple[str, int]] = set()
    for s in specs:
        if (isinstance(s, PCompound) and s.functor == "/" and len(s.args) == 2
                and isinstance(s.args[0], PAtom) and isinstance(s.args[1], PNumber)):
            pairs.add((s.args[0].name, int(s.args[1].value)))
        elif isinstance(s, PAtom):
            pairs.add((s.name, 0))
    return pairs


def module_export_signature(pmodule: PModule) -> set[tuple[str, int]]:
    """The (name, arity) set the emitted :- module directive exports."""
    for item in pmodule.items:
        if _is_module_directive(item):
            return _export_pairs(item)
    return set()


# ── Public API ───────────────────────────────────────────────────────

def clausal_source_to_prolog_ast(source: str, *,
                                  dialect: Dialect | None = None,
                                  strict: bool = False,
                                  module_path: str | None = None,
                                  module_signatures: dict[str, set[tuple[str, int]]] | None = None,
                                  meta_modes: MetaModeMap | None = None,
                                  ) -> PModule:
    """Parse .clausal source text and return a Prolog AST (PModule).

    Uses Python's parser on the clausal source, then converts the
    Python AST patterns (trailing comma facts, <- rules, -directives)
    directly into Prolog AST nodes.

    When *strict* is True, any construct with no ISO Prolog equivalent
    raises :class:`UntranslatableConstructError` instead of emitting a
    ``???`` placeholder plus a warning comment.

    *module_path* is the dotted path of the module being translated
    (``"eu.ai_act.prohibited_practices.prohibition"``). When given,
    ``use_module`` file paths are emitted relative to that module's package
    directory, which is what Scryer resolves a consulted path against.

    *module_signatures* maps a dotted target path to that target's filtered
    export set (:func:`module_export_signature`'s return value). When given,
    import lists are narrowed to ``Name/Arity`` pairs the target really
    exports; when omitted alongside *module_path*, the import list is dropped
    entirely (``:- use_module('path').``).

    *meta_modes* supplies ``:- meta_predicate`` argument modes this module's own
    text cannot show -- see :data:`MetaModeMap`. It is looked up under
    *module_path* exactly as passed, and unioned per argument with the body-local
    detection of :func:`collect_local_meta_modes`. Only predicates this module
    actually defines are declared.
    """
    if dialect is None:
        dialect = Dialect.iso()
    tree = python_ast.parse(source)
    _expand_table_directives(tree)
    # keepends=True is load-bearing, not style. build_quote_map feeds tokenize
    # through readline, which reads a bare "" -- any blank line without its
    # ending -- as end of file. Plain splitlines() cut the quote map short at
    # the first blank line (empty for most files), every quote lookup then
    # answered "unknown", and a single-quoted atom fell back to the file's
    # -double_quotes mode: a STRING wherever that mode is chars. See
    # tests/test_prolog_quote_map_line_endings.py.
    converter = _ClausalToProlog(dialect, strict=strict,
                                 module_path=module_path,
                                 module_signatures=module_signatures,
                                 meta_modes=meta_modes,
                                 source_lines=source.splitlines(keepends=True))
    return converter.convert_module(tree)


def _expand_table_directives(tree) -> None:
    """Rewrite every `-constants_number_*` table directive into its facts, in
    place, BEFORE the converter walks the tree.

    THE DEFECT THIS CLOSES. The SINGULAR declarations (`constant_value`,
    `constant_number_units`, `constant_number_currency`) are routed to
    `_collect_constant`, which honours the dialect's `constants` capability and
    REFUSES for a dialect that cannot receive one. The PLURAL table family
    (`constants_number_units`, `constants_number_currency`) had no handler here
    at all, so it fell through to generic directive emission and landed in the
    .pl verbatim. ISO has no such directive, so every one was
    `domain_error(directive, constants_number_currency/4)` at LOAD -- the
    exported program did not run at all. Measured 2026-09-17: 10 sites in 6
    corpus files, and it is one of the two classes holding G3 at zero across the
    whole roster.

    A second data shape of the same declaration family, arriving after the first
    was handled and never swept for. The names differ by one letter and an
    arity, which is why a grep for the singular form finds nothing wrong.

    WHY EXPANSION RATHER THAN A NEW EMITTER. The engine already answers this
    question -- `term_rewriting._expand_currency_tables` rewrites the directive
    into plain fact statements source-to-source, BEFORE the ordinary visit, so a
    declared table becomes the same kind of predicate as the fact lines it
    replaces rather than a second kind wearing the same name. Doing the same
    here means the exporter translates facts it already knows how to translate,
    and the two sides cannot drift: there is one expansion, called twice.

    Deliberately NOT capability-gated. Expansion yields ordinary facts, which
    every dialect can receive -- the `constants` capability governs whether a
    *declaration* can cross, and after this runs there is no declaration left to
    cross. That is also why this is the right fix for `Dialect.iso()`, whose
    capability is "none": the facts are plain ISO.
    """
    body = []
    changed = False
    for stmt in tree.body:
        call = _engine_table_directive_call(stmt)
        if call is None:
            body.append(stmt)
            continue
        body.extend(_engine_expand_currency_table(call))
        changed = True
    if changed:
        tree.body = body


def clausal_source_to_prolog(source: str, *,
                              dialect: Dialect | None = None,
                              strict: bool = False,
                              module_path: str | None = None,
                              module_signatures: dict[str, set[tuple[str, int]]] | None = None,
                              meta_modes: MetaModeMap | None = None,
                              ) -> str:
    """Translate .clausal source text to Prolog source text.

    Full pipeline: .clausal → Python AST → Prolog AST → .pl text.

    When *strict* is True, any construct with no ISO Prolog equivalent
    raises :class:`UntranslatableConstructError` instead of emitting a
    ``???`` placeholder plus a warning comment.

    *module_path* and *module_signatures* control ``use_module`` emission —
    see :func:`clausal_source_to_prolog_ast`.
    """
    if dialect is None:
        dialect = Dialect.iso()
    pmodule = clausal_source_to_prolog_ast(source, dialect=dialect, strict=strict,
                                           module_path=module_path,
                                           module_signatures=module_signatures,
                                           meta_modes=meta_modes)
    return emit_module(pmodule, dialect.operator_table)


# ── CLI ──────────────────────────────────────────────────────────────

def _main() -> None:
    """Command-line interface for clausal → Prolog translation.

    Usage:
        python -m clausal.tools.clausal_to_prolog input.clausal [-o output.pl] [--dialect swi|scryer|gprolog|iso]
        cat input.clausal | python -m clausal.tools.clausal_to_prolog [--dialect swi]
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="clausal_to_prolog",
        description="Translate .clausal source files to Prolog (.pl).",
    )
    parser.add_argument(
        "input", nargs="?", default=None,
        help="Input .clausal file (reads stdin if omitted)",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output .pl file (writes stdout if omitted)",
    )
    parser.add_argument(
        "--dialect", choices=["iso", "swi", "scryer", "gprolog"], default="iso",
        help="Target Prolog dialect (default: iso)",
    )
    args = parser.parse_args()

    dialect_map = {"iso": Dialect.iso, "swi": Dialect.swi, "scryer": Dialect.scryer,
                   "gprolog": Dialect.gprolog}
    dialect = dialect_map[args.dialect]()

    if args.input is None:
        source = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as f:
            source = f.read()

    result = clausal_source_to_prolog(source, dialect=dialect)

    if args.output is None:
        sys.stdout.write(result)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)


if __name__ == "__main__":
    _main()
