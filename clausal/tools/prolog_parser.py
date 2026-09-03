"""Prolog Pratt parser (Phase 3.2).

Parses a token stream into Prolog AST nodes.  Uses the OperatorTable for
dynamic operator-precedence parsing.  Handles ``op/3`` directives mid-file
so that user-defined operators take effect immediately.

Public API:
    parse(source, *, dialect=None, op_table=None) -> PModule
    parse_term(source, *, op_table=None) -> PTerm

The parser produces the same AST nodes as ``prolog_ast.py``.
"""

from __future__ import annotations

from clausal.tools.prolog_tokenizer import Token, TokenType, tokenize
from clausal.tools.prolog_ast import (
    PAtom, PVar, PNumber, PString, PCompound, PList, PCurly,
    PClause, PDCGRule, PDirective, PQuery, PModule,
    PTerm, PItem,
)
from clausal.tools.prolog_operators import OperatorTable, OpEntry
from clausal.tools.prolog_dialect import Dialect


class ParseError(Exception):
    """Raised when the parser encounters a syntax error."""

    def __init__(self, message: str, line: int = 0, col: int = 0):
        self.line = line
        self.col = col
        super().__init__(f"{message} at {line}:{col}")


# ── Public API ───────────────────────────────────────────────────────


def parse(source: str, *, dialect: Dialect | None = None,
          op_table: OperatorTable | None = None) -> PModule:
    """Parse Prolog source text into a PModule AST.

    Parameters
    ----------
    source : str
        Complete Prolog source text.
    dialect : Dialect, optional
        Dialect configuration.  If provided, its operator table is used
        as the starting point (unless *op_table* is also given).
    op_table : OperatorTable, optional
        Explicit operator table.  Takes precedence over *dialect*.
    """
    if op_table is None:
        if dialect is not None:
            op_table = dialect.operator_table
        else:
            op_table = OperatorTable.swi_default()
    tokens = tokenize(source)
    parser = PrologParser(tokens, op_table)
    return parser.parse_program()


def parse_term(source: str, *, op_table: OperatorTable | None = None) -> PTerm:
    """Parse a single Prolog term (no trailing dot required).

    Useful for testing and REPL-style interaction.
    """
    if op_table is None:
        op_table = OperatorTable.swi_default()
    tokens = tokenize(source)
    parser = PrologParser(tokens, op_table)
    return parser.parse_term_public(1200)


# ── Parser ───────────────────────────────────────────────────────────


class PrologParser:
    """Pratt parser for Prolog terms."""

    _CLOSER_TYPES = frozenset({
        TokenType.RPAREN, TokenType.RBRACKET, TokenType.RCURLY,
        TokenType.BAR, TokenType.COMMA, TokenType.DOT, TokenType.END,
    })

    def __init__(self, tokens: list[Token], op_table: OperatorTable):
        self._tokens = tokens
        self._pos = 0
        self._ops = op_table

    # ── Program-level parsing ────────────────────────────────────────

    def parse_program(self) -> PModule:
        """Parse a sequence of clauses/directives terminated by '.'."""
        items: list[PItem] = []
        while not self._at_end():
            items.append(self._parse_item())
        return PModule(tuple(items))

    def parse_term_public(self, max_prec: int = 1200) -> PTerm:
        """Public entry point for parsing a single term."""
        return self._parse_term(max_prec)

    def _parse_item(self) -> PItem:
        """Parse one clause, directive, or query, consuming the trailing '.'."""
        term = self._parse_term(1200)
        self._expect(TokenType.DOT)
        return self._classify_item(term)

    def _classify_item(self, term: PTerm) -> PItem:
        """Classify a top-level term as clause, directive, DCG rule, or query."""
        # Directive: :-(Body)  i.e. PCompound(':-', (body,))
        if isinstance(term, PCompound) and term.functor == ":-" and len(term.args) == 1:
            body = term.args[0]
            # Check for op/3 directive — apply immediately
            self._maybe_apply_op_directive(body)
            return PDirective(body)

        # Query: ?-(Body)
        if isinstance(term, PCompound) and term.functor == "?-" and len(term.args) == 1:
            return PQuery(term.args[0])

        # Rule: Head :- Body  i.e. PCompound(':-', (head, body))
        if isinstance(term, PCompound) and term.functor == ":-" and len(term.args) == 2:
            return PClause(term.args[0], term.args[1])

        # DCG rule: Head --> Body  i.e. PCompound('-->', (head, body))
        if isinstance(term, PCompound) and term.functor == "-->" and len(term.args) == 2:
            return PDCGRule(term.args[0], term.args[1])

        # Fact: just a term
        return PClause(term)

    def _maybe_apply_op_directive(self, body: PTerm) -> None:
        """If *body* is ``op(Prec, Spec, Name)``, apply it to the operator table."""
        if not isinstance(body, PCompound):
            return
        if body.functor != "op" or len(body.args) != 3:
            return
        prec_t, spec_t, name_t = body.args
        if not isinstance(prec_t, PNumber) or not isinstance(prec_t.value, int):
            return
        if not isinstance(spec_t, PAtom):
            return
        # Name can be an atom
        if isinstance(name_t, PAtom):
            self._ops.define(prec_t.value, spec_t.name, name_t.name)
        # Or a list of atoms
        elif isinstance(name_t, PList):
            for elem in name_t.elements:
                if isinstance(elem, PAtom):
                    self._ops.define(prec_t.value, spec_t.name, elem.name)

    # ── Term parsing (Pratt) ─────────────────────────────────────────

    def _parse_term(self, max_prec: int) -> PTerm:
        """Parse a term with operators up to *max_prec*."""
        left = self._parse_primary(max_prec)
        # Priority of the term built so far. Primaries (atoms, numbers, vars,
        # functor(...) calls, parenthesised terms) have priority 0; an operator
        # compound gets the operator's priority. Used to enforce xfx/xfy/yfx
        # argument-priority limits so `a = b = c` / `2 ** 3 ** 2` are rejected
        # (F028) rather than silently accepted.
        left_prec = 0
        while True:
            tok = self._peek()
            if tok.type == TokenType.END:
                break

            # Try infix or postfix operator
            name = self._operator_name_from_token(tok)
            if name is None:
                break

            # Try infix first
            infix_entry = self._ops.lookup_infix(name)
            postfix_entry = self._ops.lookup_postfix(name)

            # Pick the applicable entry
            entry = None
            if infix_entry and infix_entry.precedence <= max_prec:
                entry = infix_entry
                # Guarded postfix fallback: if we have both infix and postfix,
                # and the next token cannot start a term, use postfix instead
                if postfix_entry and postfix_entry.precedence <= max_prec \
                        and not self._can_start_term_conservative(self._peek(1)):
                    entry = postfix_entry
            elif postfix_entry and postfix_entry.precedence <= max_prec:
                entry = postfix_entry

            if entry is None:
                # Could be infix with too-high precedence — stop
                break

            # Enforce the left-argument priority limit (x → strictly less,
            # y → less-or-equal). A violation is an ISO priority-clash error.
            if left_prec > self._left_prec(entry):
                raise ParseError(
                    f"operator priority clash: {name!r} cannot take a "
                    f"left operand of priority {left_prec}",
                    tok.line, tok.col,
                )

            if entry.specifier in ("xfx", "xfy", "yfx"):
                self._advance()
                r_prec = self._right_prec(entry)
                right = self._parse_term(r_prec)
                left = PCompound(entry.name, (left, right))
                left_prec = entry.precedence
            elif entry.specifier in ("xf", "yf"):
                self._advance()
                left = PCompound(entry.name, (left,))
                left_prec = entry.precedence
            else:
                break

        return left

    def _parse_primary(self, context_prec: int = 1200) -> PTerm:
        """Parse a primary (non-operator) term."""
        tok = self._peek()

        if tok.type == TokenType.INTEGER:
            self._advance()
            return PNumber(tok.value)

        if tok.type == TokenType.FLOAT:
            self._advance()
            return PNumber(tok.value)

        if tok.type == TokenType.STRING:
            self._advance()
            return PString(tok.value)

        if tok.type == TokenType.VAR:
            self._advance()
            return PVar(tok.value)

        if tok.type == TokenType.LPAREN:
            return self._parse_parenthesized()

        if tok.type == TokenType.LBRACKET:
            return self._parse_list()

        if tok.type == TokenType.LCURLY:
            return self._parse_curly()

        if tok.type == TokenType.ATOM:
            return self._parse_atom_or_compound(context_prec)

        # Check for prefix operator on non-atom tokens
        # (e.g., - as prefix for negative numbers)
        name = self._operator_name_from_token(tok)
        if name is not None:
            prefix_entry = self._ops.lookup_prefix(name)
            if prefix_entry and prefix_entry.precedence <= context_prec:
                return self._parse_prefix(prefix_entry)

        raise ParseError(
            f"Unexpected token {tok.type.value} ({tok.value!r})",
            tok.line, tok.col,
        )

    def _parse_atom_or_compound(self, context_prec: int = 1200) -> PTerm:
        """Parse an atom, possibly followed by (...) arguments, or a prefix operator."""
        tok = self._advance()
        name = tok.value
        assert isinstance(name, str)

        # Check if followed by '(' with no space → compound term
        nxt = self._peek()
        if nxt.type == TokenType.LPAREN and self._is_functor_paren(tok, nxt):
            return self._parse_compound_args(name, tok.line, tok.col)

        # Check for prefix operator
        prefix_entry = self._ops.lookup_prefix(name)
        if prefix_entry and prefix_entry.precedence <= context_prec:
            # But not if it's also an atom that's being used as a term
            # Heuristic: if next token can start a term, treat as prefix
            if self._can_start_term():
                # Special case: - IMMEDIATELY before a number → negative
                # literal. ISO 6.3.1.2: only an adjacent `-1` is a negative
                # number; a spaced `- 1` is the compound -(1) (F037).
                nxt = self._peek()
                if (name == "-"
                        and nxt.type in (TokenType.INTEGER, TokenType.FLOAT)
                        and self._adjacent(tok, nxt)):
                    self._advance()
                    return PNumber(-nxt.value)
                r_prec = self._prefix_right_prec(prefix_entry)
                operand = self._parse_term(r_prec)
                return PCompound(name, (operand,))

        return PAtom(name, quoted=tok.quoted)

    def _parse_compound_args(self, functor: str, line: int, col: int) -> PCompound:
        """Parse f(arg1, arg2, ...) after the functor name."""
        self._advance()  # consume (
        args: list[PTerm] = []
        if self._peek().type != TokenType.RPAREN:
            args.append(self._parse_term(999))  # args are parsed at prec 999
            while self._peek().type == TokenType.COMMA:
                self._advance()  # consume ,
                args.append(self._parse_term(999))
        self._expect(TokenType.RPAREN)
        return PCompound(functor, tuple(args))

    def _parse_parenthesized(self) -> PTerm:
        """Parse ( term )."""
        self._advance()  # consume (
        term = self._parse_term(1200)
        self._expect(TokenType.RPAREN)
        return term

    def _parse_list(self) -> PTerm:
        """Parse [elem1, elem2, ... | tail] or []."""
        self._advance()  # consume [
        if self._peek().type == TokenType.RBRACKET:
            self._advance()
            return PList((), None)

        elements: list[PTerm] = []
        elements.append(self._parse_term(999))
        while self._peek().type == TokenType.COMMA:
            self._advance()
            # Check for | after comma — some Prolog allows [a, b | T]
            if self._peek().type == TokenType.BAR:
                break
            elements.append(self._parse_term(999))

        tail = None
        if self._peek().type == TokenType.BAR:
            self._advance()  # consume |
            tail = self._parse_term(999)

        self._expect(TokenType.RBRACKET)
        return PList(tuple(elements), tail)

    def _parse_curly(self) -> PTerm:
        """Parse {term} (DCG inline goal or set notation)."""
        self._advance()  # consume {
        if self._peek().type == TokenType.RCURLY:
            self._advance()
            return PAtom("{}")
        body = self._parse_term(1200)
        self._expect(TokenType.RCURLY)
        return PCurly(body)

    def _parse_prefix(self, entry: OpEntry) -> PTerm:
        """Parse a prefix operator application."""
        tok = self._advance()
        name = entry.name

        # Special case: - IMMEDIATELY before a number → negative literal
        # (a spaced `- 1` is the compound -(1), ISO 6.3.1.2) — F037.
        nxt = self._peek()
        if (name == "-"
                and nxt.type in (TokenType.INTEGER, TokenType.FLOAT)
                and self._adjacent(tok, nxt)):
            self._advance()
            return PNumber(-nxt.value)

        r_prec = self._prefix_right_prec(entry)
        operand = self._parse_term(r_prec)
        return PCompound(name, (operand,))

    @staticmethod
    def _adjacent(left: Token, right: Token) -> bool:
        """True if *right* immediately follows *left* with no gap."""
        if left.end_col:
            return right.line == left.end_line and right.col == left.end_col
        # Fallback when no end position is recorded.
        return (right.line == left.line and
                right.col == left.col + len(str(left.value)))

    # ── Precedence helpers ───────────────────────────────────────────

    def _right_prec(self, entry: OpEntry) -> int:
        """Right-side precedence from infix specifier."""
        if entry.specifier in ("xfx", "yfx"):
            return entry.precedence - 1
        if entry.specifier == "xfy":
            return entry.precedence
        return entry.precedence - 1

    def _left_prec(self, entry: OpEntry) -> int:
        """Left-side precedence from infix specifier."""
        if entry.specifier == "yfx":
            return entry.precedence
        # xfx, xfy: left must be strictly less
        return entry.precedence - 1

    def _prefix_right_prec(self, entry: OpEntry) -> int:
        """Right-side precedence from prefix specifier."""
        if entry.specifier == "fy":
            return entry.precedence
        # fx: strictly less
        return entry.precedence - 1

    # ── Token helpers ────────────────────────────────────────────────

    def _peek(self, offset: int = 0) -> Token:
        pos = self._pos + offset
        if pos < len(self._tokens):
            return self._tokens[pos]
        return Token(TokenType.END, "", 0, 0)

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _at_end(self) -> bool:
        return self._peek().type == TokenType.END

    def _expect(self, tt: TokenType) -> Token:
        tok = self._peek()
        if tok.type != tt:
            raise ParseError(
                f"Expected {tt.value!r}, got {tok.type.value!r} ({tok.value!r})",
                tok.line, tok.col,
            )
        return self._advance()

    def _operator_name_from_token(self, tok: Token) -> str | None:
        """Extract operator name from a token, if it could be an operator."""
        if tok.type == TokenType.ATOM:
            return tok.value if isinstance(tok.value, str) else None
        if tok.type == TokenType.COMMA:
            return ","
        if tok.type == TokenType.BAR:
            return "|"
        return None

    def _is_functor_paren(self, functor_tok: Token, lparen_tok: Token) -> bool:
        """True if the LPAREN immediately follows the functor (no space).

        in_ Prolog, ``f(X)`` is a compound term, but ``f (X)`` is the atom
        ``f`` followed by ``(X)`` in an operator context.  We detect this
        by checking column adjacency.
        """
        # Use the token's recorded end position rather than col + len(value):
        # a quoted functor like 'foo'(1) has a value ("foo") shorter than its
        # source span ('foo'), so the length-based check wrongly rejected it
        # (F029).
        if functor_tok.end_col:
            return (lparen_tok.line == functor_tok.end_line and
                    lparen_tok.col == functor_tok.end_col)
        return (lparen_tok.line == functor_tok.line and
                lparen_tok.col == functor_tok.col + len(str(functor_tok.value)))

    def _can_start_term(self) -> bool:
        """True if the next token can start a primary term."""
        tok = self._peek()
        return tok.type in (
            TokenType.ATOM, TokenType.VAR, TokenType.INTEGER, TokenType.FLOAT,
            TokenType.STRING, TokenType.LPAREN, TokenType.LBRACKET, TokenType.LCURLY,
        )

    def _can_start_term_conservative(self, tok: Token) -> bool:
        """Conservative: can *tok* begin a term? Used only to disambiguate an
        atom that is declared both infix and postfix (never true of default
        tables). An infix/postfix-only operator atom is treated as unable to
        start a term (`a* then b`), at the cost of requiring parens for the
        rare `a * (then)`."""
        if tok.type in self._CLOSER_TYPES:
            return False
        if tok.type == TokenType.ATOM:
            name = tok.value
            if (self._ops.lookup_infix(name) or self._ops.lookup_postfix(name)) \
                    and not self._ops.lookup_prefix(name):
                return False
        return True
