"""toklex regex rendering target: the compiled spec as one Python `re`
master pattern (chars mode).

Third rendering of the same annotated ``Lexer`` (after the table-driven
step function in ``driver.py`` and the DCG in ``dcg.py``): every token
and trivia rule's RE IR is rendered to a named alternative of a single
``re`` pattern, so the per-character scanning loop runs inside the C
regex engine. ``RegexLexer`` exposes the same public surface as
``IncrementalLexer`` (``feed``/``close``/``next_token``/``run``,
``NEED_MORE``/``EOF``, ``Tok`` with identical spans/values/glue).

Semantics strategy — nothing is re-specified, and the reference driver
remains the authority:

- **Ordering.** Alternatives appear in declaration order (trivia first,
  then tokens), which for the shipped specs makes Python's
  leftmost-first alternation agree with the DFA's longest-match (the
  spec declares float before integer, char_code/radix ints before
  integer, `end` before `graphic_tok`, and the `but_not` prefix
  exclusion is a lookahead). The agreement is *verified*, not assumed:
  the differential tests compare this lexer against the table driver
  token-for-token.
- **Maximal munch while streaming.** In open mode a match is emitted
  only if it ends strictly before the end of fed text — a match
  touching the boundary might still extend with unseen input (the
  design's emission invariant), so it is held as ``NEED_MORE``. On
  ``close()`` a second master (identical but with ``\\Z`` allowed in
  ``followed_by`` lookaheads for ``follow_eof`` rules) finishes the
  tail.
- **Endgame delegation.** Anywhere the closed-mode master has no match
  (an unterminated quote, a character no token can start with), the
  next token is produced by running the reference ``IncrementalLexer``
  on the remaining tail and rebasing its span — commit-region /
  unterminated / no_token semantics are therefore *inherited*, never
  duplicated. Note the scope honestly: once delegation starts it drains
  the WHOLE remaining input on the table driver (correct — delegation
  only starts in closed mode, where the table driver is definitionally
  right). For well-formed input that region is empty; for input with an
  early lexical error followed by lots of valid text, the remainder
  runs at table-driver speed rather than regex speed.
- **Nested comments** are non-regular and keep the sub-scan (depth
  counter + ``str.find`` fast-skip), driven by the rendered open/close
  patterns.
- **Scope:** chars mode only. Byte mode (``feed_bad`` markers) stays on
  the table driver via ``decode.Utf8Feeder``; ``RegexLexer`` does not
  implement ``feed_bad``.
"""

from __future__ import annotations

import re
from bisect import bisect_right

from clausal.tools.toklex.builders import ISO_BUILDERS
from clausal.tools.toklex.driver import EOF, NEED_MORE, IncrementalLexer, Tok
from clausal.tools.toklex.spec import Alt, ButNot, Lit, Opt, Plus, Seq, SpecError, Star

_FULL_IVS = ((0, 0x10FFFF),)


# ── RE IR -> re pattern text ─────────────────────────────────────────


def _compile(pattern: str, what: str):
    """re.compile with renderer errors surfaced as SpecError, so the
    shim's fallback-to-table-driver catches ANY unrenderable spec, not
    only shapes the renderer knows to reject up front."""
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise SpecError("regex target could not compile %s: %s" % (what, exc)) from exc


def _class_re(cs) -> str:
    """A CharSet as a regex character class (or single escaped char)."""
    if not cs.ivs:
        raise SpecError("regex target: empty character class is unrenderable")
    if cs.ivs == _FULL_IVS:
        return r"[\s\S]"
    parts = []
    single = None
    for lo, hi in cs.ivs:
        if lo == hi:
            parts.append(re.escape(chr(lo)))
        elif hi - lo == 1:
            parts.append(re.escape(chr(lo)) + re.escape(chr(hi)))
        else:
            parts.append(re.escape(chr(lo)) + "-" + re.escape(chr(hi)))
    if len(cs.ivs) == 1 and cs.ivs[0][0] == cs.ivs[0][1]:
        single = re.escape(chr(cs.ivs[0][0]))
    return single if single is not None else "[" + "".join(parts) + "]"


def _needs_group(node) -> bool:
    # Star/Plus/Opt included: quantifying an already-quantified operand
    # without a group renders invalid syntax ("a+*" -> re.error) -- the
    # Star(Plus(...)) shape is reachable through def-composition.
    return isinstance(node, (Seq, Alt, ButNot, Star, Plus, Opt))


def _expr_re(node) -> str:
    if isinstance(node, Lit):
        return _class_re(node.cs)
    if isinstance(node, Seq):
        return "".join(_expr_re(p) if not isinstance(p, Alt) else "(?:%s)" % _expr_re(p)
                       for p in node.parts)
    if isinstance(node, Alt):
        return "|".join(_expr_re(p) for p in node.parts)
    if isinstance(node, (Star, Plus, Opt)):
        inner = _expr_re(node.x)
        if _needs_group(node.x):
            inner = "(?:%s)" % inner
        return inner + {"Star": "*", "Plus": "+", "Opt": "?"}[type(node).__name__]
    if isinstance(node, ButNot):
        # Only the prefix-exclusion shape is renderable:
        #   A but_not (p1 then p2 ... then any*)   ==>   (?!p1p2...)A
        # which is exactly language subtraction when B = prefix.Sigma*.
        b = node.b
        if (isinstance(b, Seq) and b.parts
                and isinstance(b.parts[-1], Star)
                and isinstance(b.parts[-1].x, Lit)
                and b.parts[-1].x.cs.ivs == _FULL_IVS
                and all(isinstance(p, Lit) for p in b.parts[:-1])):
            prefix = "".join(_class_re(p.cs) for p in b.parts[:-1])
            a = _expr_re(node.a)
            if isinstance(node.a, Alt):
                a = "(?:%s)" % a
            return "(?!%s)%s" % (prefix, a)
        raise SpecError(
            "but_not is only renderable to a regex as a prefix exclusion "
            "(A but_not (prefix then any*)); rule uses a general subtraction")
    raise SpecError("unrenderable RE node for regex target: %r" % (node,))


def _first_chars(expr) -> str | None:
    """Chars that can begin `expr`, when cheaply enumerable (for the
    nested-comment fast skip); None -> fall back to per-char stepping."""
    node = expr
    while isinstance(node, Seq):
        node = node.parts[0]
    if isinstance(node, Lit):
        chars = []
        for lo, hi in node.cs.ivs:
            if hi - lo > 3 or hi > 126:
                return None
            chars.extend(chr(c) for c in range(lo, hi + 1))
        return "".join(chars) if 0 < len(chars) <= 8 else None
    return None


# ── master assembly ──────────────────────────────────────────────────


class _Compiled:
    __slots__ = ("master_open", "master_closed", "group_rule",
                 "nest_rules", "nest_pat", "nest_skip", "nest_maxlen",
                 "commit_trigger", "extend_syms")

    def __init__(self):
        self.group_rule = {}   # group name -> (kind, rule name); kind in {token, trivia, nest}
        self.nest_rules = {}
        self.nest_pat = {}
        self.nest_skip = {}
        self.nest_maxlen = {}  # rule -> max chars an open/close delimiter can span
        self.commit_trigger = {}  # rule -> frozenset[symbol]; see _commit_triggers
        self.extend_syms = {}     # rule -> frozenset[symbol]; all DFA-extendable next-syms


def _expr_maxlen(node):
    """Maximum length of a string in the expr's language, or None if
    unbounded (Star/Plus)."""
    if isinstance(node, Lit):
        return 1
    if isinstance(node, Seq):
        total = 0
        for p in node.parts:
            m = _expr_maxlen(p)
            if m is None:
                return None
            total += m
        return total
    if isinstance(node, Alt):
        best = 0
        for p in node.parts:
            m = _expr_maxlen(p)
            if m is None:
                return None
            best = max(best, m)
        return best
    if isinstance(node, Opt):
        return _expr_maxlen(node.x)
    if isinstance(node, (Star, Plus)):
        return None
    if isinstance(node, ButNot):
        return _expr_maxlen(node.a)
    return None


def _commit_triggers(lexer) -> dict:
    """Per rule: the partition symbols that can extend one of its accepts
    toward a COMMIT region of the DFA. A regex match followed by such a
    char is exactly the case leftmost/backtracking matching cannot judge:
    the DFA's maximal munch would keep going and either find a longer
    token or resolve via the commit rule (unterminated-whole vs
    distance-gated backup) — semantics the `re` engine cannot reproduce
    (it backtracks to the *shorter* parse: the `'ab''cc<EOF>` doubling
    case). The RegexLexer holds (open stream) or delegates to the table
    driver (closed) whenever a match trips this set. Conservative
    over-approximation is safe: a false trigger only costs a delegation."""
    dfa, commit = lexer.dfa, lexer.commit
    # states from which a commit state is reachable (forward reachability
    # into `commit`, computed by reverse BFS from the commit set)
    rev: dict[int, set] = {}
    for q, row in enumerate(dfa.delta):
        for dest in row.values():
            rev.setdefault(dest, set()).add(q)
    can_reach = set(commit)
    frontier = list(commit)
    while frontier:
        q = frontier.pop()
        for p in rev.get(q, ()):
            if p not in can_reach:
                can_reach.add(p)
                frontier.append(p)
    triggers: dict[str, set] = {}
    extends: dict[str, set] = {}
    for q, labels in enumerate(dfa.accepts):
        if not labels:
            continue
        for sym, dest in dfa.delta[q].items():
            for label in labels:
                extends.setdefault(label, set()).add(sym)
                if dest in can_reach:
                    triggers.setdefault(label, set()).add(sym)
    return ({r: frozenset(s) for r, s in triggers.items()},
            {r: frozenset(s) for r, s in extends.items()})


def _render(lexer) -> _Compiled:
    spec = lexer.spec
    c = _Compiled()
    alts_open, alts_closed = [], []
    seen = set()

    def add(kind, rule, body_open, body_closed):
        g = "g%d" % len(c.group_rule)
        c.group_rule[g] = (kind, rule)
        alts_open.append("(?P<%s>%s)" % (g, body_open))
        alts_closed.append("(?P<%s>%s)" % (g, body_closed))

    for tr in spec.trivia:
        body = _expr_re(tr.expr)
        if tr.nest_close is not None:
            add("nest", tr.name, body, body)
            c.nest_rules[tr.name] = tr
            c.nest_pat[tr.name] = (
                _compile(_expr_re(tr.expr), "nest open %r" % tr.name),
                _compile(_expr_re(tr.nest_close), "nest close %r" % tr.name),
            )
            ml_open = _expr_maxlen(tr.expr)
            ml_close = _expr_maxlen(tr.nest_close)
            if ml_open is None or ml_close is None:
                raise SpecError(
                    "regex target requires bounded-length nest delimiters "
                    "(rule %r has an unbounded open/close pattern)" % tr.name)
            c.nest_maxlen[tr.name] = max(ml_open, ml_close)
            skips = (_first_chars(tr.expr), _first_chars(tr.nest_close))
            c.nest_skip[tr.name] = (
                "".join(sorted(set((skips[0] or "") + (skips[1] or ""))))
                if skips[0] is not None and skips[1] is not None else None)
        else:
            add("trivia", tr.name, body, body)
        seen.add(tr.name)

    for tok in spec.tokens:
        body = _expr_re(tok.expr)
        if tok.follow is not None or tok.follow_eof:
            follow_cls = _class_re(tok.follow) if tok.follow is not None else None
            open_look = "(?=%s)" % follow_cls if follow_cls else None
            closed_alts = [a for a in (follow_cls, r"\Z" if tok.follow_eof else None) if a]
            closed_look = "(?=%s)" % "|".join(closed_alts)
            if open_look is None:
                # eof-only follow: can never be satisfied while the stream
                # is open (more input may come) -> impossible alternative.
                open_look = r"(?!\s\S)(?=\s\S)"  # never matches
            add("token", tok.name, body + open_look, body + closed_look)
        else:
            add("token", tok.name, body, body)
        seen.add(tok.name)

    c.master_open = _compile("|".join(alts_open), "master pattern (open mode)")
    c.master_closed = _compile("|".join(alts_closed), "master pattern (closed mode)")
    c.commit_trigger, c.extend_syms = _commit_triggers(lexer)
    return c


def _compiled_for(lexer) -> _Compiled:
    cached = getattr(lexer, "_regex_compiled", None)
    if cached is None:
        cached = _render(lexer)
        object.__setattr__(lexer, "_regex_compiled", cached)  # frozen dataclass
    return cached


# ── the driver ───────────────────────────────────────────────────────


class RegexLexer:
    """`IncrementalLexer`-compatible chars-mode lexer over the rendered
    master pattern. See the module docstring for the semantics strategy."""

    def __init__(self, lexer, builders=ISO_BUILDERS, nested_comments: bool = True):
        self.lexer = lexer
        self.builders = builders
        self.nested_comments = nested_comments
        self._c = _compiled_for(lexer)

        self._text = ""
        self._pos = 0
        self._line_starts = [0]
        self._closed = False
        self._eof_returned = False
        self._glue = "spaced"
        self._nest = None  # {'rule', 'depth', 'start'} as in IncrementalLexer
        self._delegate = None  # (base_offset, IncrementalLexer) draining the tail

    # ── feeding (identical position bookkeeping to IncrementalLexer) ─

    def feed(self, text: str) -> None:
        if self._closed:
            raise ValueError("cannot feed a closed RegexLexer")
        base = len(self._text)
        self._text += text
        find = text.find
        i = find("\n")
        while i != -1:
            self._line_starts.append(base + i + 1)
            i = find("\n", i + 1)

    def close(self) -> None:
        self._closed = True

    def run(self, text: str) -> list:
        self.feed(text)
        self.close()
        out = []
        while (t := self.next_token()) is not EOF:
            out.append(t)
        return out

    def _pos_tuple(self, off: int) -> tuple:
        starts = self._line_starts
        i = bisect_right(starts, off) - 1
        return (off, i + 1, off - starts[i] + 1)

    # ── main loop ────────────────────────────────────────────────────

    def next_token(self):
        if self._eof_returned:
            return EOF
        text = self._text
        n = len(text)
        while True:
            if self._delegate is not None:
                t = self._next_delegated()
                if t is not None:
                    return t
                continue
            if self._nest is not None:
                r = self._nest_step()
                if r is NEED_MORE:
                    return NEED_MORE
                if r is not None:
                    return r  # the unterminated-comment error token
                continue
            pos = self._pos
            if pos >= n:
                if self._closed:
                    self._eof_returned = True
                    return EOF
                return NEED_MORE
            master = self._c.master_closed if self._closed else self._c.master_open
            m = master.match(text, pos)
            if m is None:
                if not self._closed:
                    return NEED_MORE  # more input may complete a token here
                self._start_delegation()
                continue
            if not self._closed and m.end() == n:
                return NEED_MORE  # touching the boundary: might still extend
            kind, rule = self._c.group_rule[m.lastgroup]
            end = m.end()
            if end < n:
                ext = self._c.extend_syms.get(rule)
                if ext is not None:
                    ch = text[end]
                    o = ord(ch)
                    sym = (self.lexer.partition.ascii_table()[o] if o < 128
                           else self.lexer.partition.symbol_of(ch))
                    if sym in ext:
                        # The next char can extend this rule's accept per
                        # the DFA -- the one place `re`'s leftmost /
                        # backtracking behavior can disagree with maximal
                        # munch.
                        if sym in self._c.commit_trigger.get(rule, ()):
                            # extension enters a COMMIT region (doubling /
                            # escape-terminator tails): unbounded lookahead
                            # the regex cannot judge. Hold while open; hand
                            # the region to the reference driver on close.
                            if not self._closed:
                                return NEED_MORE
                            self._start_delegation()
                            continue
                        if not self._closed and end + self.lexer.max_backup + 1 >= n:
                            # Non-commit extension near the boundary: a
                            # greedy match may have GIVEN BACK an optional
                            # suffix (float's `1.0e` -> `1.0`) whose
                            # viability depends on unseen input. Such a
                            # pending stretch is <= max_backup chars
                            # (Task 5/8's bound, +1 for an accept at the
                            # window edge), so beyond that margin the stop
                            # is final; within it, hold.
                            return NEED_MORE
                        # far from the boundary (or closed): every char the
                        # extension could have consumed was visible to the
                        # greedy engine, so its stop here is final.
            self._pos = end
            if kind == "trivia":
                self._glue = "spaced"
                continue
            if kind == "nest":
                self._nest = {"rule": rule, "depth": 1, "start": m.start()}
                continue
            return self._emit(rule, m.start(), m.end())

    # ── token emission (mirrors IncrementalLexer._emit) ──────────────

    def _emit(self, label: str, start_off: int, end_off: int) -> Tok:
        lexeme = self._text[start_off:end_off]
        builder_name = self.lexer.builder.get(label)
        builder = self.builders.get(builder_name) if builder_name else None
        start = self._pos_tuple(start_off)
        end = self._pos_tuple(end_off)
        glue = self._glue
        self._glue = "glued"
        if builder is not None:
            try:
                value = builder(lexeme)
            except Exception:
                # same defense-in-depth contract as the table driver
                return Tok(kind="error", value=("bad_token", lexeme), lexeme=lexeme,
                           start=start, end=end, glue=glue)
        else:
            value = lexeme
        return Tok(kind=label, value=value, lexeme=lexeme, start=start, end=end, glue=glue)

    def _error_tok(self, reason: str, start_off: int, end_off: int) -> Tok:
        """An ``error`` Tok over ``text[start_off:end_off]``, culprit =
        lexeme -- the shape and glue ``IncrementalLexer._error_tok``
        gives the same span."""
        lexeme = self._text[start_off:end_off]
        glue = self._glue
        self._glue = "glued"
        return Tok(kind="error", value=(reason, lexeme), lexeme=lexeme,
                   start=self._pos_tuple(start_off),
                   end=self._pos_tuple(end_off), glue=glue)

    # ── endgame delegation to the reference driver ───────────────────

    def _start_delegation(self) -> None:
        base = self._pos
        inner = IncrementalLexer(self.lexer, builders=self.builders,
                                 nested_comments=self.nested_comments)
        inner.feed(self._text[base:])
        inner.close()
        self._delegate = (base, inner)

    def _next_delegated(self):
        base, inner = self._delegate
        t = inner.next_token()
        if t is EOF:
            self._delegate = None
            self._pos = len(self._text)
            return None
        # rebase the span onto the full text; recompute line/col globally
        start = self._pos_tuple(base + t.start[0])
        end = self._pos_tuple(base + t.end[0])
        # the delegate's stream-start glue default is 'spaced'; the true
        # glue at the splice point is ours, unless the delegate consumed
        # leading trivia first (then 'spaced' is correct anyway)
        glue = t.glue
        if t.start[0] == 0 and glue == "spaced":
            glue = self._glue
        self._glue = "glued"
        self._pos = base + t.end[0]
        return Tok(kind=t.kind, value=t.value, lexeme=t.lexeme,
                   start=start, end=end, glue=glue)

    # ── nested comments (regex-rendered open/close + fast skip) ──────

    def _nest_step(self):
        rule = self._nest["rule"]
        open_pat, close_pat = self._c.nest_pat[rule]
        text = self._text
        n = len(text)
        pos = self._pos

        if not self._closed and n - pos < self._c.nest_maxlen[rule]:
            # `re.match` cannot distinguish "pattern fails here" from
            # "pattern cut by the input boundary" (a lone '*' that the
            # next chunk completes to '*/'). Delimiter patterns are
            # bounded-length by construction, so hold whenever fewer
            # chars remain than a delimiter could span.
            return NEED_MORE
        m = close_pat.match(text, pos)
        if m is not None:
            if not self._closed and m.end() + self.lexer.max_backup >= n:
                # over-cautious hold: with bounded-length delimiters the
                # nest_maxlen guard above already guarantees visibility,
                # so this margin is not strictly required — kept because
                # over-holding is always safe (chunk-insensitive) and it
                # costs at most one extra NEED_MORE round near an edge
                return NEED_MORE
            self._pos = m.end()
            self._nest["depth"] -= 1
            if self._nest["depth"] == 0:
                self._nest = None
                self._glue = "spaced"
            return None
        if self.nested_comments:
            m2 = open_pat.match(text, pos)
            if m2 is not None:
                if not self._closed and m2.end() + self.lexer.max_backup >= n:
                    return NEED_MORE
                self._pos = m2.end()
                self._nest["depth"] += 1
                return None
        if pos >= n:
            if not self._closed:
                return NEED_MORE
            # EOF with depth > 0: a syntax error (ruled 2026-09-30), the
            # same `unterminated` token IncrementalLexer emits -- the whole
            # comment from its outermost opener.
            start = self._nest["start"]
            self._nest = None
            return self._error_tok("unterminated", start, n)
        # neither pattern starts here: consume one char, fast-skip ahead
        pos += 1
        skip = self._c.nest_skip[rule]
        if skip is not None and pos < n:
            best = n
            for ch in skip:
                j = text.find(ch, pos, n)
                if j != -1 and j < best:
                    best = j
            pos = best
        self._pos = pos
        return None
