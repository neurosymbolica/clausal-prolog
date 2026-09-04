"""Prolog reader — the §1c contract's data heart.

This module implements the ReaderItem IR (frozen dataclasses per the
locked §1c contract) and the P-tree -> (cell, span_tree, var_names)
transformer that is the substance of that contract.

Parser output (``clausal.tools.prolog_ast`` P-nodes) is pure data: this
module only depends on dataclasses and the P-node types (for isinstance
checks) — never on the engine (``clausal.logic.*``). Task 4 appends
``PrologReader`` (the toklex-driving item-at-a-time reader) below the
IR + transformer section defined here.

Cell mapping (locked):
    PAtom      -> .name (str; quoted flag is irrelevant to cells — mangling
                  is the compiler's job)
    PNumber    -> .value (native int/float)
    PString    -> list of 1-char strings ('' -> [])
    PCompound  -> (functor, *arg_cells)
    PList (proper)   -> Python list [cell, ...]
    PList (with tail) -> right-nested cons cells ('.', H, T), folding the
                  elements right-to-left over the transformed tail
    PCurly     -> ('{}', body_cell)
    PVar       -> VarRef(i), first-occurrence numbering; '_' always
                  allocates a fresh index

Span tree (locked, mirrors the cell shape exactly):
    leaf cell (str atom, number, VarRef, char-list-from-PString)
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
    curly cell ('{}', body_cell)
        -> ((start, end), span(body))
"""

from __future__ import annotations

from dataclasses import dataclass

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
    span: tuple
    message: str
    resumable: bool


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
            return node.name
        if isinstance(node, PNumber):
            return node.value
        if isinstance(node, PString):
            return list(node.value)
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
            return self._cons_span(node.elements, node.tail, _span_of(node))
        raise TypeError(f"transform_term: unsupported P-node {type(node)!r}")

    def _cons_span(self, elements, tail, remaining_span):
        """One level per remaining element; head span = remaining-list
        extent (start of this element, end of the whole remaining list).
        The innermost level's tail span is just the tail P-node's span."""
        if not elements:
            return self.span(tail)
        head, *rest = elements
        head_start, _ = _span_of(head)
        _, remaining_end = remaining_span
        this_span = (head_start, remaining_end)
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


def _lex_error_message(t) -> str:
    """A human-readable message for an L0 ``error`` Tok, mirroring
    ``prolog_tokenizer.tokenize()``'s ``TokenizeError`` text (same
    reasons, message-only rather than raised)."""
    reason, culprit = t.value
    if reason == "unterminated":
        if t.lexeme.startswith('"'):
            return "unterminated string"
        return "unterminated quoted atom"
    if reason == "no_token":
        return f"unexpected character {culprit!r}"
    if reason == "bad_token":
        return f"malformed token {culprit!r}"
    return f"invalid input {culprit!r}"  # 'invalid_encoding'


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
    ``OperatorTable.swi_default()``. The reader owns the table for its
    lifetime -- ``op/3`` directives parsed by one ``read_term()`` call
    apply to the SAME table used by later calls, so they persist.
    """

    def __init__(self, *, op_table=None, dialect=None, nested_comments=True,
                 lexer=None):
        from clausal.tools.prolog_operators import OperatorTable

        if op_table is not None:
            self._op_table = op_table
        elif dialect is not None:
            self._op_table = dialect.operator_table
        else:
            self._op_table = OperatorTable.swi_default()

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
        # a clean 'end' token, a lexical error, or EOF. item_error holds
        # the first lexical-error message seen for the item, if any.
        self._item_start = None
        self._item_end = None
        self._item_error = None
        self._eof = False

    def feed(self, text: str) -> None:
        self._lexer.feed(text)

    def close(self) -> None:
        self._lexer.close()

    def _touch_item(self, t) -> None:
        if self._item_start is None:
            self._item_start = t.start[0]
        self._item_end = t.end[0]

    def _reset_item_state(self) -> None:
        self._item_buf = []
        self._item_start = None
        self._item_end = None
        self._item_error = None

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
        message = _lex_error_message(t)
        reason, _culprit = t.value
        if reason == "unterminated":
            # Terminal: the driver has consumed all remaining input and
            # no 'end' token will ever come (an unclosed quote/comment
            # etc.). Record it and let the EOF branch above close the
            # item out (resumable=False) on the next next_token() call.
            self._touch_item(t)
            self._item_error = message
            return None
        # no_token / bad_token / invalid_encoding: a single skippable bad
        # token; lexing continues normally afterward.
        if self._item_start is None:
            # Between items (nothing buffered yet for a new item) -- a
            # standalone lexical error, not attributable to any item.
            return SyntaxIssue(span=(t.start[0], t.end[0]), message=message,
                                resumable=True)
        # Mid-item: keep buffering: the item's 'end' token still resyncs
        # this later, once it arrives.
        self._touch_item(t)
        if self._item_error is None:
            self._item_error = message
        return None

    def _eof_issue(self) -> "SyntaxIssue":
        span = (self._item_start, self._item_end)
        message = self._item_error or "unterminated item (missing end token)"
        self._reset_item_state()
        self._eof = True  # no more content will ever follow this issue
        return SyntaxIssue(span=span, message=message, resumable=False)

    def _finish_item(self, end_tok):
        span = (self._item_start, self._item_end)
        pending_error = self._item_error
        tokens_buf = self._item_buf
        self._reset_item_state()

        if pending_error is not None:
            return SyntaxIssue(span=span, message=pending_error, resumable=True)

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
            return SyntaxIssue(span=span, message=str(exc), resumable=True)
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
            continue
        items.append(item)
