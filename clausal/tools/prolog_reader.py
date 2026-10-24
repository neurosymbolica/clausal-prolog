"""Prolog reader — the §1c contract's data heart.

This module implements the ReaderItem IR (frozen dataclasses per the
locked §1c contract) and the P-tree -> (cell, span_tree, var_names)
transformer that is the substance of that contract.

Parser output (``clausal.tools.prolog_ast`` P-nodes) is pure data: this
module only depends on dataclasses and the P-node types (for isinstance
checks) — never on the engine (``clausal.logic.*``). Task 4 appends
``PrologReader`` (the toklex-driving item-at-a-time reader) below the
IR + transformer section defined here.

Cell mapping (locked; the two atom/string lines updated by THE FLIP,
2026-09-06-atoms-as-cells-strings §9.7):
    PAtom      -> the arity-0 CELL (.name,) — an atom (quoted flag is
                  irrelevant to cells — mangling is the compiler's job)
    PNumber    -> .value (native int/float)
    PString    -> .value (a str — a STRING, which denotes the list of its
                  char atoms; '' -> "", which denotes [])
    PCompound  -> (functor, *arg_cells)
    PList (proper)   -> Python list [cell, ...]
    PList (with tail) -> right-nested cons cells ('.', H, T), folding the
                  elements right-to-left over the transformed tail
    PCurly     -> ('{}', body_cell)
    PVar       -> VarRef(i), first-occurrence numbering; '_' always
                  allocates a fresh index

Span tree (locked, mirrors the cell shape exactly):
    leaf cell (atom cell, number, VarRef, string-from-PString)
        -> the P-node's (start, end), or (-1, -1) when the P-node's span
           is None (e.g. hand-built P-trees in tests)
    compound tuple cell ('f', c1, ..., cN)
        -> ((start, end), span(c1), ..., span(cN))
    Python-list cell [c1, ..., cN]
        -> ((start, end), [span(c1), ..., span(cN)])
    cons chain synthesized from a PList-with-tail: each synthesized
        ('.', H, T) level gets a compound-shaped span node
        ((start_of_H, end_of_whole_remaining_list), span(H), span(T))
        — i.e. the head span at each level is the REMAINING-LIST extent,
        computed from the current element's start and the tail P-node's
        end (falling back through nested elements/tail when spans are
        None); the innermost T's span is just the tail P-node's own span.
        EXCEPTION: the OUTERMOST level uses the PList node's own span
        verbatim instead of the remaining-extent rule, so it covers the
        opening '[' too (e.g. `[a, b | T]`'s top cons node spans the
        whole bracketed expression, not just from 'a' onward); every
        level below it still follows the remaining-extent rule.
    curly cell ('{}', body_cell)
        -> ((start, end), span(body))
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple
import sys as _sys

from clausal.tools.prolog_ast import (
    PAtom,
    PClause,
    PCompound,
    PCurly,
    PDCGRule,
    PDirective,
    PList,
    PNumber,
    PQuery,
    PString,
    PVar,
)

__all__ = [
    "VarRef",
    "Clause",
    "Directive",
    "DCGRule",
    "Query",
    "SyntaxIssue",
    "syntax_error_term",
    "transform_term",
    "PrologReader",
    "read_module",
    "NEED_MORE",
    "EOF",
]

# ── IR ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class VarRef:
    i: int


@dataclass(frozen=True, slots=True)
class Clause:  # fact or rule; term = whole item term as read
    term: object
    spans: object
    var_names: dict


@dataclass(frozen=True, slots=True)
class Directive:  # term = directive body
    term: object
    spans: object
    var_names: dict


@dataclass(frozen=True, slots=True)
class DCGRule:  # term = ('-->', H, B)
    term: object
    spans: object
    var_names: dict


@dataclass(frozen=True, slots=True)
class Query:  # term = query body
    term: object
    spans: object
    var_names: dict


@dataclass(frozen=True, slots=True)
class SyntaxIssue:
    """A syntax error the reader recovered from (or, ``resumable=False``,
    one at the end of the text).  *message* is the human text, with the
    fault's ``line:col`` and, where one is cheap and certain, a hint;
    *kind* is the formal ``syntax_error(Kind)`` atom, Scryer's vocabulary
    for the same input (operator ruling 2026-10-24: ``incomplete_reduction``,
    ``invalid_single_quoted_character``, ``missing_quote``,
    ``unexpected_char``, ``back_quoted_string``, ``infinite_float``,
    ``cannot_parse_big_int``, ``utf8_conversion_error``); *line*/*column*
    locate the fault (1-based) and *expected*/*found*, when the parser
    knows them, say what it wanted and what it saw (atoms, numbers, or
    ``priority(N)``).  :meth:`error_term` is the ISO term."""

    span: tuple
    message: str
    resumable: bool
    kind: str = "incomplete_reduction"
    line: "int | None" = None
    column: "int | None" = None
    expected: object = None
    found: object = None

    def error_term(self, who: str = "read_term/3") -> tuple:
        """``error(syntax_error(Kind), context(PI, Details))`` for this
        issue, read by the predicate *who* (``"read_term/3"``)."""
        return syntax_error_term(self.kind, who, line=self.line,
                                 column=self.column, expected=self.expected,
                                 found=self.found)


def _indicator_cell(who: str) -> tuple:
    name, _, arity = who.rpartition("/")
    return ("/", name, int(arity))


def syntax_error_term(kind: str, who: str, *, line=None, column=None,
                      expected=None, found=None) -> tuple:
    """The ISO term of a syntax error, as plain cells (atoms are ``str``,
    compounds tuples, so this stays engine-free)::

        error(syntax_error(Kind), context(Name/Arity, Details))

    *Kind* is Scryer's atom for the situation (ISO 7.12.2 h leaves it
    implementation dependent; Scryer's vocabulary is followed for
    portability).  The context is ISO's implementation-defined slot
    (operator ruling 2026-10-24): ``context(PI, Details)`` where *Details*
    is a list of ``line(L)``, ``column(C)`` (1-based, when the position is
    known), ``expected(What)`` and ``found(Token)`` (when the parser knows
    them), in that order -- richer than Scryer's ``read_term/3:Line`` while
    portable code matching ``error(syntax_error(_), _)`` sees no
    difference.  Every syntax error the engine raises -- the reader's
    (loading a file, ``read_term/2,3``, ``term_to_atom/2``,
    ``atom_to_term/3``) and ``number_chars/2``'s family -- has this shape.
    """
    details = []
    if line is not None:
        details.append(("line", line))
    if column is not None:
        details.append(("column", column))
    if expected is not None:
        details.append(("expected", expected))
    if found is not None:
        details.append(("found", found))
    return ("error", ("syntax_error", kind),
            ("context", _indicator_cell(who), details))


# ── P-tree -> (cell, span_tree, var_names) transformer ───────────────

_NO_SPAN = (-1, -1)


def _span_of(node) -> tuple:
    """The (start, end) span of a P-node, or the (-1, -1) placeholder."""
    span = getattr(node, "span", None)
    if span is None:
        return _NO_SPAN
    return span


class _Transform:
    """One transform_term() call's mutable state: name -> first-occurrence
    var index. '_' never reuses an index — every occurrence is fresh."""

    def __init__(self) -> None:
        self._index_by_name: dict[str, int] = {}
        self.var_names: dict[int, str] = {}

    def var_index(self, name: str) -> int:
        if name != "_" and name in self._index_by_name:
            return self._index_by_name[name]
        i = len(self.var_names)
        self.var_names[i] = name
        if name != "_":
            self._index_by_name[name] = i
        return i

    def cell(self, node):
        if isinstance(node, PAtom):
            # THE FLIP (§9.7): an atom is the arity-0 cell.  Built inline
            # rather than through ``clausal.logic.atoms.mint`` — this module
            # is the §1c contract's data heart and must not grow an import
            # edge into the engine — but it is the same term ``mint`` makes,
            # interned spelling included.
            if node.name == "[]":
                # ISO 6.3.5 / D70: `'[]'` and `[]` are the same atom, and
                # the empty list is carried as the Python empty list.
                return []
            return _sys.intern(node.name)   # STAGE 2: an atom IS the interned str
        if isinstance(node, PNumber):
            return node.value
        if isinstance(node, PString):
            # STAGE 2: a string is the chars CARRIER (``cells.chars``, spelled
            # inline -- this module grows no import edge into the engine); it
            # denotes the list of its char atoms and is equal to it everywhere.
            return ("$chars", node.value)   # == clausal.logic.cells.CHARS_TAG; pinned by tests/test_atoms_as_str_stage2.py
        if isinstance(node, PVar):
            return VarRef(self.var_index(node.name))
        if isinstance(node, PCompound):
            return (node.functor, *(self.cell(a) for a in node.args))
        if isinstance(node, PCurly):
            return ("{}", self.cell(node.body))
        if isinstance(node, PList):
            if node.tail is None:
                return [self.cell(e) for e in node.elements]
            return self._cons_cell(node.elements, node.tail)
        raise TypeError(f"transform_term: unsupported P-node {type(node)!r}")

    def _cons_cell(self, elements, tail):
        if not elements:
            return self.cell(tail)
        head, *rest = elements
        return (".", self.cell(head), self._cons_cell(rest, tail))

    def span(self, node):
        if isinstance(node, (PAtom, PNumber, PVar)):
            return _span_of(node)
        if isinstance(node, PString):
            return _span_of(node)
        if isinstance(node, PCompound):
            return (_span_of(node), *(self.span(a) for a in node.args))
        if isinstance(node, PCurly):
            return (_span_of(node), self.span(node.body))
        if isinstance(node, PList):
            if node.tail is None:
                return (_span_of(node), [self.span(e) for e in node.elements])
            return self._cons_span(node.elements, node.tail, _span_of(node),
                                    outermost=True)
        raise TypeError(f"transform_term: unsupported P-node {type(node)!r}")

    def _cons_span(self, elements, tail, remaining_span, outermost=False):
        """One level per remaining element; head span = remaining-list
        extent (start of this element, end of the whole remaining list) --
        EXCEPT the outermost level, whose span is the PList node's own
        span verbatim (`remaining_span` unchanged), so it covers the
        opening '[' too rather than starting at the first element. The
        innermost level's tail span is just the tail P-node's span."""
        if not elements:
            return self.span(tail)
        head, *rest = elements
        head_start, _ = _span_of(head)
        _, remaining_end = remaining_span
        this_span = remaining_span if outermost else (head_start, remaining_end)
        return (
            this_span,
            self.span(head),
            self._cons_span(rest, tail, this_span),
        )


def transform_term(pterm) -> tuple[object, object, dict[int, str]]:
    """P-tree -> (cell, span_tree, var_names) per the locked decisions.

    A fresh numbering state is used per call: named variables are numbered
    by first occurrence, and every '_' occurrence allocates a fresh index.
    """
    xf = _Transform()
    cell = xf.cell(pterm)
    span_tree = xf.span(pterm)
    return cell, span_tree, xf.var_names


# ── PrologReader: the incremental L1 core (Task 4) ────────────────────
#
# A resumable item-at-a-time reader over the toklex L0 token stream. It
# owns an L0 lexer (RegexLexer, falling back to IncrementalLexer on a
# SpecError -- the same policy prolog_tokenizer.tokenize() uses) and its
# own OperatorTable, which persists across read_term() calls so op/3
# directives parsed in one item stay in effect for later ones.
#
# Deferred imports below mirror prolog_tokenizer.tokenize()'s reason:
# clausal.tools.toklex.spec parses spec files with prolog_parser, which
# imports prolog_tokenizer for Token/TokenType/tokenize -- an eager
# module-level import of the toklex/parser stack here risks the same
# import-order fragility, so it's deferred to first use instead.

from clausal.tools.toklex import EOF, NEED_MORE  # re-exported


def _to_compat_token(t):
    """One L0 ``Tok`` -> a compat ``Token`` (prolog_tokenizer.Token),
    reusing the shim's own kind map so the mapping never drifts from
    tokenize()'s."""
    from clausal.tools.prolog_tokenizer import Token, _KIND_MAP

    return Token(
        _KIND_MAP[t.kind], t.value, t.start[1], t.start[2],
        quoted=(t.kind == "quoted_atom"),
        end_line=t.end[1], end_col=t.end[2],
        offset=t.start[0], end_offset=t.end[0],
    )


def _joined_span(a, b):
    """(start, end) covering P-nodes *a* and *b*, or None if either has
    no span of its own."""
    a_span = getattr(a, "span", None)
    b_span = getattr(b, "span", None)
    if a_span is None or b_span is None:
        return None
    return (a_span[0], b_span[1])


class _LexFault(NamedTuple):
    """A lexical error, diagnosed: the message, Scryer's formal atom, the
    fault's position and what was expected / found (see ``SyntaxIssue``)."""
    message: str
    kind: str
    line: "int | None"
    column: "int | None"
    expected: object
    found: object


#: Scryer's formal for a fault inside a quoted token, by the token's kind
#: (``diagnose.quoted_fault_detail``'s) and the fault's code.  Measured
#: 2026-10-24 (tests/iso/test_syntax_error_terms_scryer.py): a raw
#: newline, a bad escape or a raw control character is
#: ``invalid_single_quoted_character`` in a quoted atom and
#: ``missing_quote`` in a string, ``unexpected_char`` after ``0'``; an
#: octal or hex escape with no closing backslash, or ``\x`` with no digit,
#: is ``incomplete_reduction`` everywhere.
_QUOTED_FAULT_KIND = {
    "quoted atom": "invalid_single_quoted_character",
    "string": "missing_quote",
    "0' character code": "unexpected_char",
}

#: A quoted token's escape whose code is no character: ``\777777777\``,
#: ``\xFFFFFFFF\`` (Scryer: ``utf8_conversion_error``).
_ESCAPE_CODE = re.compile(r"\\(x[0-9a-fA-F]+|[0-7]+)\\")


def _escape_out_of_range(lexeme: str) -> bool:
    for m in _ESCAPE_CODE.finditer(lexeme):
        digits = m.group(1)
        code = int(digits[1:], 16) if digits[0] == "x" else int(digits, 8)
        if code >= 0x110000:
            return True
    return False


def _lex_error(t, text: str | None = None, pos=None) -> _LexFault:
    """An L0 ``error`` Tok diagnosed: the human message (mirroring
    ``prolog_tokenizer.tokenize()``'s ``TokenizeError`` text, message-only
    rather than raised), Scryer's formal atom for the same input, the
    fault's line:col, and what was expected and found.

    With the lexer's *text*, a refused quoted token is diagnosed
    (``toklex.diagnose.quoted_fault_detail``): the message names the
    offending escape or character and its line:col. *pos* maps an offset
    to ``(offset, line, col)`` (the lexer's ``_pos_tuple``, a bisect over
    its line starts); without it the line is counted, which is linear in
    the text, so a reader diagnosing many errors must pass it."""
    reason, culprit = t.value
    _, line, col = t.start

    def at(off):
        if pos is not None:
            _, l, c = pos(off)
            return l, c
        if text is None:
            return None, None
        return (text.count("\n", 0, off) + 1,
                off - (text.rfind("\n", 0, off) + 1) + 1)

    if text is not None:
        off = None
        if reason == "no_token" and culprit in ("'", '"'):
            off = t.start[0]
        elif reason == "unterminated" and t.lexeme[:1] in ("'", '"'):
            off = t.start[0]
        elif reason == "unterminated" and t.lexeme.startswith("0'"):
            off = t.start[0] + 1
        if off is not None:
            from clausal.tools.toklex.diagnose import quoted_fault_detail
            fault = quoted_fault_detail(text, off)
            if fault is not None:
                fline, fcol = at(fault.at)
                if fault.code == "escape_unclosed":
                    kind, expected = "incomplete_reduction", "\\"
                elif fault.code == "escape_nodigits":
                    kind, expected = "incomplete_reduction", "hex_digit"
                else:
                    kind, expected = _QUOTED_FAULT_KIND[fault.kind], None
                if fault.code == "newline":
                    expected = text[off]       # the closing quote
                return _LexFault(f"{fault.message} at {fline}:{fcol}", kind,
                                 fline, fcol, expected, fault.found)
    if reason == "unterminated":
        if t.lexeme.startswith("/*"):
            # ISO: an unclosed block comment is a syntax error; Scryer's
            # formal for it is incomplete_reduction (ruled 2026-09-30).
            # The opener's line is named here because an issue's span
            # starts at its ITEM, which may begin lines earlier.
            return _LexFault(
                f"unterminated block comment opened at line {t.start[1]} "
                f"(syntax_error(incomplete_reduction))",
                "incomplete_reduction", line, col, "*/", "end_of_file")
        # A quote still open at the end of the text: Scryer reads on to
        # the end and reports incomplete_reduction (not missing_quote,
        # which it keeps for a string broken by a newline or escape).
        if t.lexeme.startswith('"'):
            return _LexFault(f"unterminated string at {line}:{col}",
                             "incomplete_reduction", line, col, '"',
                             "end_of_file")
        if t.lexeme.startswith("0'"):
            return _LexFault(f"unterminated quoted atom at {line}:{col}",
                             "incomplete_reduction", line, col, None,
                             "end_of_file")
        return _LexFault(f"unterminated quoted atom at {line}:{col}",
                         "incomplete_reduction", line, col, "'", "end_of_file")
    if reason == "no_token":
        if culprit == "`":
            # ISO 6.4.7's back quoted string: no meaning as a term.
            # Scryer: back_quoted_string when the string closes,
            # incomplete_reduction when it runs to the end of the text.
            closed = text is not None and "`" in text[t.start[0] + 1:]
            return _LexFault(f"unexpected character {culprit!r} at {line}:{col}",
                             "back_quoted_string" if closed
                             else "incomplete_reduction",
                             line, col, None, culprit)
        return _LexFault(f"unexpected character {culprit!r} at {line}:{col}",
                         "unexpected_char", line, col, None, culprit)
    if reason == "bad_token":
        kind = ("utf8_conversion_error" if _escape_out_of_range(culprit)
                else "incomplete_reduction")
        return _LexFault(f"malformed token {culprit!r} at {line}:{col}", kind,
                         line, col, None, culprit)
    return _LexFault(f"invalid input {culprit!r} at {line}:{col}",  # 'invalid_encoding'
                     "utf8_conversion_error", line, col, None, culprit)


def _lex_error_message(t, text: str | None = None, pos=None) -> str:
    """The message of :func:`_lex_error` alone."""
    return _lex_error(t, text, pos).message


def _classify_pitem(pitem):
    """One parsed ``PItem`` -> the matching ``ReaderItem``. Where an item
    has two P-subtrees that must share variable numbering (a rule's head
    and body; a DCG rule's head and body), a synthetic whole-item
    PCompound is built and transformed ONCE, so ``transform_term``'s
    first-occurrence numbering runs over both halves together.

    ``PrologParser.parse_program()`` never emits a ``PComment`` PItem (no
    lexical construct in the grammar reduces to one today), so the
    ``TypeError`` fallback below is a deliberate "should be unreachable"
    guard, not a gap in this mapping.
    """
    if isinstance(pitem, PClause):
        if pitem.body is None:
            cell, spans, var_names = transform_term(pitem.head)
        else:
            whole = PCompound(":-", (pitem.head, pitem.body),
                               span=_joined_span(pitem.head, pitem.body))
            cell, spans, var_names = transform_term(whole)
        return Clause(cell, spans, var_names)
    if isinstance(pitem, PDirective):
        cell, spans, var_names = transform_term(pitem.body)
        return Directive(cell, spans, var_names)
    if isinstance(pitem, PQuery):
        cell, spans, var_names = transform_term(pitem.body)
        return Query(cell, spans, var_names)
    if isinstance(pitem, PDCGRule):
        whole = PCompound("-->", (pitem.head, pitem.body),
                           span=_joined_span(pitem.head, pitem.body))
        cell, spans, var_names = transform_term(whole)
        return DCGRule(cell, spans, var_names)
    raise TypeError(f"PrologReader: unclassifiable P-item {type(pitem)!r}")


class PrologReader:
    """Resumable item-at-a-time L1 reader over the toklex L0 stream.

    ``op_table`` precedence: explicit > ``dialect.operator_table`` >
    ``OperatorTable.scryer_builtin_default()`` (Scryer's table with no library
    loaded -- ISO first, then Scryer; it was ``swi_default`` until 2026-09-29,
    whose non-ISO prefix ``dynamic`` and ``*->`` Scryer refuses). The reader owns the table for its
    lifetime -- ``op/3`` directives parsed by one ``read_term()`` call
    apply to the SAME table used by later calls, so they persist. This
    ownership is exposed: see the ``op_table`` property below.

    WARNING: when constructed with ``dialect=``, the reader does NOT copy
    ``dialect.operator_table`` -- it takes and mutates that SAME table
    object, so any ``op/3`` directive read from the source also mutates
    the ``Dialect`` instance's table (and is visible to anything else
    sharing it). This is a deliberate, plan-sanctioned ownership choice
    (no defensive copy), not an oversight -- pass an explicit ``op_table``
    of your own if you need the dialect's defaults left untouched.
    """

    def __init__(self, *, op_table=None, dialect=None, nested_comments=True,
                 lexer=None):
        from clausal.tools.prolog_operators import OperatorTable

        if op_table is not None:
            self._op_table = op_table
        elif dialect is not None:
            self._op_table = dialect.operator_table
        else:
            self._op_table = OperatorTable.scryer_builtin_default()

        if lexer is not None:
            self._lexer = lexer
        else:
            from clausal.tools.toklex import IncrementalLexer, load_lexer
            from clausal.tools.toklex.regex_target import RegexLexer
            from clausal.tools.toklex.spec import SpecError

            l0 = load_lexer()
            try:
                self._lexer = RegexLexer(l0, nested_comments=nested_comments)
            except SpecError:
                self._lexer = IncrementalLexer(l0, nested_comments=nested_comments)

        self._item_buf: list = []
        # Current-item-attempt bookkeeping (Task 5): item_start/item_end
        # track the extent of whatever has been touched for the item in
        # progress (real Toks AND error Toks alike -- an error can be the
        # very first thing in an item, e.g. an unterminated quote), so a
        # SyntaxIssue's span is always available whether the item ends via
        # a clean 'end' token, a lexical error, or EOF. _item_fault holds
        # the first lexical fault diagnosed for the item, if any.
        self._item_start = None
        self._item_end = None
        self._item_fault = None
        self._eof = False
        #: The offset (into everything fed so far) just past the end token
        #: of the item the last ``read_term()`` returned -- what a reader
        #: over a stream has consumed (``read/1`` pushes the rest back).
        self.last_item_end = 0

    def feed(self, text: str) -> None:
        self._lexer.feed(text)

    def close(self) -> None:
        self._lexer.close()

    @property
    def op_table(self):
        """The ``OperatorTable`` this reader owns (§1c: L1 exposes it).
        ``op/3`` directives read from the source mutate this SAME table
        object as items are read -- what this property returns after N
        items reflects every ``op/3`` seen among those N, not just the
        table as constructed."""
        return self._op_table

    def _touch_item(self, t) -> None:
        if self._item_start is None:
            self._item_start = t.start[0]
        self._item_end = t.end[0]

    def _reset_item_state(self) -> None:
        self._item_buf = []
        self._item_start = None
        self._item_end = None
        self._item_fault = None      # the item's first _LexFault, if any

    def read_term(self):
        """-> ReaderItem | SyntaxIssue | NEED_MORE | EOF.

        Pulls L0 tokens into the item buffer until a ``kind == "end"``
        token completes one item, then parses and classifies it.

        Recovery (§1c contract): a Pratt ``ParseError`` on a completed
        item, or an L0 ``error`` Tok, becomes a ``SyntaxIssue`` instead of
        raising -- resync is inherent because the ``end`` token (or EOF)
        already bounds the damaged item, so reading always continues.
        """
        if self._eof:
            return EOF
        while True:
            t = self._lexer.next_token()
            if t is NEED_MORE:
                return NEED_MORE
            if t is EOF:
                if self._item_start is None:
                    self._eof = True
                    return EOF
                return self._eof_issue()
            if t.kind == "error":
                issue = self._handle_error_tok(t)
                if issue is not None:
                    return issue
                continue
            self._touch_item(t)
            self._item_buf.append(t)
            if t.kind == "end":
                return self._finish_item(t)

    def _handle_error_tok(self, t):
        """Handle one L0 ``error`` Tok. Returns a ``SyntaxIssue`` to
        return from ``read_term()`` now, or ``None`` to keep looping."""
        fault = _lex_error(t, getattr(self._lexer, "_text", None),
                           getattr(self._lexer, "_pos_tuple", None))
        reason, _culprit = t.value
        if reason == "unterminated":
            # Terminal: the driver has consumed all remaining input and
            # no 'end' token will ever come (an unclosed quote/comment
            # etc.). Record it and let the EOF branch above close the
            # item out (resumable=False) on the next next_token() call.
            self._touch_item(t)
            # Keep an earlier diagnosis of this item: an unclosed quote at
            # the end of the text follows the fault that left it unclosed.
            if self._item_fault is None:
                self._item_fault = fault
            return None
        # no_token / bad_token / invalid_encoding: a single skippable bad
        # token; lexing continues normally afterward.
        if self._item_start is None:
            # Between items (nothing buffered yet for a new item) -- a
            # standalone lexical error, not attributable to any item.
            self.last_item_end = t.end[0]
            return self._issue((t.start[0], t.end[0]), fault, resumable=True)
        # Mid-item: keep buffering: the item's 'end' token still resyncs
        # this later, once it arrives.
        self._touch_item(t)
        if self._item_fault is None:
            self._item_fault = fault
        return None

    @staticmethod
    def _issue(span, fault: _LexFault, *, resumable: bool) -> "SyntaxIssue":
        return SyntaxIssue(span=span, message=fault.message, resumable=resumable,
                           kind=fault.kind, line=fault.line, column=fault.column,
                           expected=fault.expected, found=fault.found)

    def position(self, offset: int) -> tuple:
        """``(line, column)`` of a character *offset* in the text fed so
        far (1-based), or ``(None, None)`` when the lexer cannot say."""
        pos = getattr(self._lexer, "_pos_tuple", None)
        if pos is None or offset is None:
            return None, None
        _, line, col = pos(offset)
        return line, col

    def _eof_issue(self) -> "SyntaxIssue":
        span = (self._item_start, self._item_end)
        fault = self._item_fault
        if fault is None:
            # The text ended inside an item: Scryer's incomplete_reduction.
            line, col = self.position(self._item_end)
            where = f" at {line}:{col}" if line is not None else ""
            fault = _LexFault(f"unterminated item (missing end token){where}",
                              "incomplete_reduction", line, col, "end",
                              "end_of_file")
        self._reset_item_state()
        self.last_item_end = span[1]
        self._eof = True  # no more content will ever follow this issue
        return self._issue(span, fault, resumable=False)

    def _finish_item(self, end_tok):
        span = (self._item_start, self._item_end)
        pending_fault = self._item_fault
        tokens_buf = self._item_buf
        self._reset_item_state()
        self.last_item_end = span[1]

        if pending_fault is not None:
            return self._issue(span, pending_fault, resumable=True)

        from clausal.tools.prolog_parser import ParseError, PrologParser
        from clausal.tools.prolog_tokenizer import Token, TokenType

        tokens = [_to_compat_token(t) for t in tokens_buf]
        end_off = span[1]
        tokens.append(Token(TokenType.END, "", end_tok.end[1], end_tok.end[2],
                             end_line=end_tok.end[1], end_col=end_tok.end[2],
                             offset=end_off, end_offset=end_off))
        try:
            module = PrologParser(tokens, self._op_table).parse_program()
        except ParseError as exc:
            # The 'end' token already bounds this item -- resync is
            # inherent, so drop it and keep reading (F5 recovery).
            return SyntaxIssue(span=span, message=str(exc), resumable=True,
                               kind=exc.kind, line=exc.line or None,
                               column=exc.col or None, expected=exc.expected,
                               found=exc.found)
        assert len(module.items) == 1, (
            f"expected exactly one item, got {len(module.items)}")
        return _classify_pitem(module.items[0])


def read_module(source: str, **kw) -> list:
    """Batch helper: feed the whole *source*, close, and drain every
    item (``SyntaxIssue``s included)."""
    reader = PrologReader(**kw)
    reader.feed(source)
    reader.close()
    items: list = []
    while True:
        item = reader.read_term()
        if item is EOF:
            return items
        if item is NEED_MORE:
            # Unreachable in practice: feed()+close() means every future
            # next_token() call either resolves a token or hits EOF, never
            # suspends again. Fail loud rather than spin silently if that
            # invariant is ever violated (a lexer bug, or an injected
            # `lexer=` that doesn't honor close()).
            raise RuntimeError("lexer returned NEED_MORE after close()")
        items.append(item)
