"""toklex incremental driver (design doc §5-6, chars mode).

``IncrementalLexer`` scans a compiled ``Lexer`` (Task 5's ``annotate``
output) over text fed incrementally: maximal munch with derived
emission (an accept is only taken when nothing longer can still
succeed), follow-disqualification (``followed_by`` constraints prune
which accept wins), bounded pushback (over-consumed characters are
pushed back onto the front of the input, positions intact), trivia
recording with ``Glue`` propagation, nested-comment handling, error
tokens, and ``NEED_MORE`` suspension when the buffer runs out before a
token can be resolved.

Internal representation (perf rework, feat/toklex-perf): input is one
append-only text string with an integer cursor, not a per-char deque.
Pushback is a cursor decrement; positions are derived lazily from a
line-start index only at token boundaries; the partition symbol for
ASCII chars comes from a 128-entry direct-index table. Invalid-byte
markers from ``feed_bad`` live in a side queue keyed by text offset
(a marker sits *before* the char at its offset). None of this changes
observable semantics: the token stream, spans, glue, error tokens, and
NEED_MORE/EOF behavior are identical to the deque implementation, and
chunk-boundary insensitivity holds because offsets are stable under
append-only feeding.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import deque
from dataclasses import dataclass

from clausal.tools.toklex.builders import ISO_BUILDERS


class _Sentinel:
    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return self._name


NEED_MORE = _Sentinel("NEED_MORE")
EOF = _Sentinel("EOF")

# Internal-only: signals next_token's outer loop to keep looping (an
# attempt resolved to trivia, or entered nest mode) without a value to
# return yet.
_CONTINUE = _Sentinel("_CONTINUE")

_NO_BAD = 1 << 62  # "no pending bad marker" cursor bound


@dataclass
class Tok:
    kind: str
    value: object
    lexeme: str
    start: tuple  # (offset, line, col) -- line/col 1-based
    end: tuple  # position just past the last consumed char
    glue: str  # 'glued' | 'spaced'


class IncrementalLexer:
    """Feed text with ``.feed()``, pull tokens with ``.next_token()``
    (returns ``NEED_MORE`` while more input might still extend the
    current attempt, ``EOF`` forever once the closed input is drained).
    ``.run(text)`` is the non-incremental batch helper."""

    def __init__(self, lexer, builders=ISO_BUILDERS, nested_comments: bool = True):
        self.lexer = lexer
        self.builders = builders
        self.nested_comments = nested_comments
        self.partition = lexer.partition
        self.dfa = lexer.dfa

        self._text = ""
        self._pos = 0
        self._line_starts = [0]
        self._bad: deque = deque()  # (offset, raw) -- marker sits before text[offset]
        self._closed = False
        self._eof_returned = False
        self._ascii_syms = self.partition.ascii_table()
        # nest fast-skip strings depend only on the (immutable, shared)
        # compiled Lexer, so the cache lives there: one IncrementalLexer
        # is created per tokenize() call, and per-instance caching would
        # redo the derivation for every file (perf-review finding).
        cache = getattr(lexer, "_nest_skip_cache", None)
        if cache is None:
            cache = {}
            object.__setattr__(lexer, "_nest_skip_cache", cache)  # frozen dataclass
        self._nest_skip_cache = cache

        # attempt state (kept as instance state so NEED_MORE can resume
        # a token attempt anywhere it left off):
        self._q = self.dfa.start
        self._start = 0  # attempt start offset; pending == text[_start:_pos]
        self._accepts: list = []  # list[(length, labels)]
        self._glue = "spaced"  # glue for the token being attempted (start-of-stream)
        self._nest = None  # {'rule': name, 'depth': int} or None

    # ── feeding ──────────────────────────────────────────────────────

    def feed(self, text: str) -> None:
        if self._closed:
            raise ValueError("cannot feed a closed IncrementalLexer")
        base = len(self._text)
        self._text += text
        find = text.find
        i = find("\n")
        while i != -1:
            self._line_starts.append(base + i + 1)
            i = find("\n", i + 1)

    def feed_bad(self, raw: bytes) -> None:
        """Enqueue an invalid-byte-sequence marker (byte-mode decode
        stage, ``decode.Utf8Feeder``). The marker occupies the position
        the next *valid* character would have received -- zero-width.
        It is consumed by ``next_token()`` as a zero-width ``error``
        token; see ``_resolve`` for how it interacts with an
        in-progress attempt and with follow checks."""
        if self._closed:
            raise ValueError("cannot feed a closed IncrementalLexer")
        self._bad.append((len(self._text), raw))

    def close(self) -> None:
        self._closed = True

    def run(self, text: str) -> list:
        self.feed(text)
        self.close()
        out = []
        while (t := self.next_token()) is not EOF:
            out.append(t)
        return out

    # ── positions (lazy: derived only at token boundaries) ───────────

    def _pos_tuple(self, off: int) -> tuple:
        starts = self._line_starts
        i = bisect_right(starts, off) - 1
        return (off, i + 1, off - starts[i] + 1)

    # ── attempt-state helpers ───────────────────────────────────────

    def _reset_attempt(self) -> None:
        self._q = self.dfa.start
        self._start = self._pos
        self._accepts = []

    def _follow_ok(self, label: str, after_char, after_is_eof: bool) -> bool:
        follow = self.lexer.follow
        if label not in follow:
            return True
        syms, eof_ok = follow[label]
        if after_is_eof:
            return eof_ok
        return self.partition.symbol_of(after_char) in syms

    def _bad_bound(self) -> int:
        return self._bad[0][0] if self._bad else _NO_BAD

    # ── the driver loop ─────────────────────────────────────────────

    def next_token(self):
        if self._eof_returned:
            return EOF
        # hot-loop locals (attribute lookups hoisted out of the per-char path)
        delta = self.dfa.delta
        accepts = self.dfa.accepts
        tbl = self._ascii_syms
        symbol_of = self.partition.symbol_of

        while True:
            if self._nest is not None:
                r = self._nest_step()
                if r is NEED_MORE:
                    return NEED_MORE
                if r is not None:
                    # a bad-byte marker reached inside nest mode resolves
                    # to its own zero-width error token (R6: invalid
                    # entities are ordinary error tokens uniformly,
                    # comments included) -- nest state is untouched, so
                    # the enclosing comment keeps scanning afterward.
                    return r
                continue

            text = self._text
            n = len(text)
            limit = self._bad_bound()
            if limit > n:
                limit = n
            pos = self._pos
            q = self._q
            acc = self._accepts
            start = self._start

            # consume while a transition exists (maximal munch; the
            # emission decision happens at the stuck point in _resolve)
            while pos < limit:
                ch = text[pos]
                o = ord(ch)
                sym = tbl[o] if o < 128 else symbol_of(ch)
                dest = delta[q].get(sym)
                if dest is None:
                    break
                q = dest
                pos += 1
                labels = accepts[q]
                if labels:
                    acc.append((pos - start, labels))
            self._pos = pos
            self._q = q

            if pos == limit:
                if pos == self._bad_bound():
                    result = self._resolve(kind="bad")
                elif not self._closed:
                    return NEED_MORE
                else:
                    result = self._resolve(kind="eof")
            else:
                result = self._resolve(kind="char")

            if result is _CONTINUE:
                continue
            if result is EOF:
                self._eof_returned = True
            return result

    # ── attempt resolution (no accept, or choosing among accepts) ───

    def _resolve(self, kind: str):
        # kind: 'char' (stuck on text[self._pos], no transition),
        #       'eof'  (closed input exhausted),
        #       'bad'  (cursor reached a feed_bad marker)
        text = self._text
        start = self._start
        pending_len = self._pos - start

        # Commit region (annotate.py's `Lexer.commit`): this attempt has
        # already crossed at least one accept and is now stuck inside a
        # DFA region proven NOT to have a constant backup bound in
        # general -- a real ISO ambiguity (quote-doubling; an escape's
        # optional closing backslash; task-8/task-10 fix rounds).
        #
        # distance-gated commit: d = pending - longest recorded accept.
        # Beyond `lexer.max_backup` (the proven bound for the acyclic
        # part of the pending graph) only a genuine unbounded-lookahead
        # ambiguity can be in play -> commit to one `unterminated` error
        # over the whole span (the `"ab""ccc<EOF>` case). Within the
        # bound, this stuck point is reachable by an ORDINARY bounded
        # backup from a real accept -> fall through to the normal walk
        # (the `'\x41\'.` case), which reproduces the reference greedy
        # tokenizer. The gate is what keeps bounded pushback a runtime
        # invariant: any backup taken out of a commit state below is,
        # by construction of this check, <= max_backup.
        if self._accepts and self._q in self.lexer.commit:
            longest_accept = max(length for length, _labels in self._accepts)
            if pending_len - longest_accept > self.lexer.max_backup:
                return self._error_tok("unterminated", text[start:self._pos],
                                       start, self._pos)
            # else: fall through to the normal reversed-accepts walk.

        # A bad-decode marker is, for follow-disqualification purposes
        # ONLY, treated exactly like end-of-input-with-eof_ok: the
        # invalid byte sequence terminates the character stream locally
        # the same way EOF does (an `end` token whose follow accepts eof
        # also survives before garbage bytes). This does NOT make 'bad'
        # behave like real EOF below.
        if kind == "bad":
            nxt_char, after_is_eof_default = None, True
        elif kind == "eof":
            nxt_char, after_is_eof_default = None, True
        else:
            nxt_char, after_is_eof_default = text[self._pos], False

        for length, labels in reversed(self._accepts):
            if length < pending_len:
                after_char, after_is_eof = text[start + length], False
            else:
                after_char, after_is_eof = nxt_char, after_is_eof_default
            for label in labels:
                if self._follow_ok(label, after_char, after_is_eof):
                    self._pos = start + length  # push back the over-consumed tail
                    return self._emit(label, start, start + length)

        # no accept survives this attempt
        if pending_len == 0:
            if kind == "eof":
                return EOF
            if kind == "bad":
                off, raw = self._bad.popleft()
                return self._bad_tok(off, raw)
            self._pos += 1  # consume the offending char
            return self._error_tok("no_token", text[start], start, self._pos)
        if kind == "eof":
            # unterminated: consume all pending, do NOT push back (would loop)
            return self._error_tok("unterminated", text[start:self._pos],
                                   start, self._pos)
        self._pos = start + 1  # keep first pending char, push back the rest
        return self._error_tok("no_token", text[start], start, self._pos)

    def _error_tok(self, reason: str, culprit: str, start_off: int, end_off: int) -> Tok:
        glue = self._glue
        self._glue = "glued"
        lexeme = self._text[start_off:end_off]
        self._reset_attempt()
        return Tok(kind="error", value=(reason, culprit), lexeme=lexeme,
                   start=self._pos_tuple(start_off), end=self._pos_tuple(end_off),
                   glue=glue)

    def _bad_tok(self, off: int, raw: bytes) -> Tok:
        """Emit the zero-width `error` token for an invalid byte
        sequence enqueued via `feed_bad`. Called only once any
        in-progress attempt has already been resolved (see `_resolve`)
        and the marker is at the cursor with no pending chars ahead."""
        start = self._pos_tuple(off)
        glue = self._glue
        self._glue = "glued"
        self._reset_attempt()
        return Tok(kind="error", value=("invalid_encoding", raw), lexeme="",
                   start=start, end=start, glue=glue)

    # ── emitting a resolved accept ──────────────────────────────────

    def _emit(self, label: str, start_off: int, end_off: int):
        kind = self.lexer.kind[label]
        if kind == "trivia":
            self._reset_attempt()
            if label in self.lexer.nest:
                self._nest = {"rule": label, "depth": 1}
            else:
                self._glue = "spaced"
            return _CONTINUE

        lexeme = self._text[start_off:end_off]
        builder_name = self.lexer.builder.get(label)
        builder = self.builders.get(builder_name) if builder_name else None

        start = self._pos_tuple(start_off)
        end = self._pos_tuple(end_off)
        glue = self._glue

        if builder is not None:
            try:
                value = builder(lexeme)
            except Exception:
                # Defense in depth: a builder is expected to be total over
                # whatever its token rule can match, but the grammar and a
                # builder's own re-decoding of the lexeme (e.g. char_code's
                # escape re-parse) don't always agree at the edges -- see
                # the toklex final-wave findings (malformed 0x_/0'\...
                # shapes). The public contract is that tokenize() never
                # raises anything but a positioned TokenizeError, so a
                # builder exception here becomes an `error` token instead
                # of propagating a bare ValueError/TypeError/IndexError;
                # the shim (prolog_tokenizer.py) turns this into a
                # positioned TokenizeError.
                self._glue = "glued"
                self._reset_attempt()
                return Tok(kind="error", value=("bad_token", lexeme), lexeme=lexeme,
                           start=start, end=end, glue=glue)
        else:
            value = lexeme

        self._glue = "glued"
        self._reset_attempt()
        return Tok(kind=label, value=value, lexeme=lexeme, start=start, end=end, glue=glue)

    # ── nested-comment sub-loop ──────────────────────────────────────

    def _match_dfa(self, dfa):
        """Greedy longest match of `dfa` against the text at the cursor,
        without consuming. Returns matched length (>=0), or None if the
        pattern never accepts, or NEED_MORE if the input runs out before
        the walk can be resolved. A pending bad-byte marker bounds the
        walk exactly like unmatchable content (never like EOF)."""
        text = self._text
        n = len(text)
        limit = self._bad_bound()
        hit_marker = limit <= n
        if not hit_marker:
            limit = n
        tbl = self._ascii_syms
        symbol_of = self.partition.symbol_of
        delta = dfa.delta
        accepts = dfa.accepts
        q = dfa.start
        i = self._pos
        last_accept = None
        while True:
            if i >= limit:
                if not hit_marker and not self._closed:
                    return NEED_MORE
                break
            ch = text[i]
            o = ord(ch)
            sym = tbl[o] if o < 128 else symbol_of(ch)
            dest = delta[q].get(sym)
            if dest is None:
                break
            q, i = dest, i + 1
            if accepts[q]:
                last_accept = i - self._pos
        return last_accept

    def _nest_skip_chars(self, rule: str):
        """Chars that could begin this nest rule's close or open pattern,
        as a string for `str.find`-based fast skipping over comment
        bodies -- or None when the first-symbol cells are too wide to
        enumerate cheaply (then the caller falls back to char-by-char).
        Derived from the compiled DFAs, so it is spec-agnostic."""
        if rule in self._nest_skip_cache:
            return self._nest_skip_cache[rule]
        chars: list[str] = []
        ok = True
        cells = self.partition.cells()
        for dfa in self.lexer.nest[rule]:
            for sym in dfa.delta[dfa.start]:
                lo, hi = cells[sym]
                if hi - lo > 3 or hi > 126:
                    ok = False
                    break
                chars.extend(chr(c) for c in range(lo, hi + 1))
            if not ok:
                break
        result = "".join(sorted(set(chars))) if ok and 0 < len(chars) <= 8 else None
        self._nest_skip_cache[rule] = result
        return result

    def _nest_step(self):
        rule = self._nest["rule"]
        open_dfa, close_dfa = self.lexer.nest[rule]

        m = self._match_dfa(close_dfa)
        if m is NEED_MORE:
            return NEED_MORE
        if m is not None:
            self._pos += m
            self._start = self._pos
            self._nest["depth"] -= 1
            if self._nest["depth"] == 0:
                self._nest = None
                self._glue = "spaced"
            return None

        if self.nested_comments:
            m2 = self._match_dfa(open_dfa)
            if m2 is NEED_MORE:
                return NEED_MORE
            if m2 is not None:
                self._pos += m2
                self._start = self._pos
                self._nest["depth"] += 1
                return None

        n = len(self._text)
        limit = self._bad_bound()
        if limit > n:
            limit = n
        if self._pos < limit:
            # neither pattern matches here: consume this char, then fast-skip
            # to the next position where a close/open pattern could possibly
            # begin (C-speed scan over the comment body). Equivalent to the
            # old one-char-at-a-time fallback: only chars that can start
            # neither pattern are skipped, and the scan never crosses a bad
            # marker or the end of fed text.
            self._pos += 1
            skip = self._nest_skip_chars(rule)
            if skip is not None and self._pos < limit:
                text = self._text
                best = limit
                for c in skip:
                    j = text.find(c, self._pos, limit)
                    if j != -1 and j < best:
                        best = j
                self._pos = best
            self._start = self._pos
            return None
        if self._pos == self._bad_bound():
            off, raw = self._bad.popleft()
            return self._bad_tok(off, raw)
        if not self._closed:
            return NEED_MORE

        # EOF with depth > 0 -- leave nest mode silently (parity-mandated
        # lenient behavior). (Setting glue here is unreachable-in-effect:
        # the next resolve at true EOF returns EOF; kept for symmetry.)
        self._nest = None
        self._start = self._pos
        self._glue = "spaced"
        return None
