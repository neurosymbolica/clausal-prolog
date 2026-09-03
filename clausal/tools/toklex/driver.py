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
"""

from __future__ import annotations

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


class _BadMarker:
    """Internal buffer entry for an invalid byte sequence enqueued via
    ``IncrementalLexer.feed_bad`` (design doc §5-6 R6: byte-mode decode
    stage). Distinguished from ordinary ``(ch, offset, line, col)``
    buffer entries by *type*, not by any sentinel character value, so
    the driver loop can special-case it without risking collision with
    real input."""

    __slots__ = ("raw", "offset", "line", "col")

    def __init__(self, raw: bytes, offset: int, line: int, col: int) -> None:
        self.raw = raw
        self.offset = offset
        self.line = line
        self.col = col


@dataclass
class Tok:
    kind: str
    value: object
    lexeme: str
    start: tuple  # (offset, line, col) -- line/col 1-based
    end: tuple  # position just past the last consumed char
    glue: str  # 'glued' | 'spaced'


def _next_pos(off: int, line: int, col: int, ch: str) -> tuple:
    """The position one char past (off, line, col), given the char there
    was `ch` -- mirrors the same cursor rule `feed` uses when assigning
    positions in the first place."""
    if ch == "\n":
        return (off + 1, line + 1, 1)
    return (off + 1, line, col + 1)


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

        self._buf: deque = deque()  # (ch, offset, line, col)
        self._closed = False
        self._feed_off = 0
        self._feed_line = 1
        self._feed_col = 1
        self._eof_returned = False

        # attempt state (kept as instance state so NEED_MORE can resume
        # a token attempt anywhere it left off):
        self._q = self.dfa.start
        self._pending: list = []  # list[(ch, offset, line, col)]
        self._accepts: list = []  # list[(length, labels)]
        self._glue = "spaced"  # glue for the token being attempted (start-of-stream)
        self._nest = None  # {'rule': name, 'depth': int} or None

    # ── feeding ──────────────────────────────────────────────────────

    def feed(self, text: str) -> None:
        if self._closed:
            raise ValueError("cannot feed a closed IncrementalLexer")
        for ch in text:
            self._buf.append((ch, self._feed_off, self._feed_line, self._feed_col))
            self._feed_off += 1
            if ch == "\n":
                self._feed_line += 1
                self._feed_col = 1
            else:
                self._feed_col += 1

    def feed_bad(self, raw: bytes) -> None:
        """Enqueue an invalid-byte-sequence marker (byte-mode decode
        stage, ``decode.Utf8Feeder``). The marker occupies the position
        the next *valid* character would have received -- zero-width:
        offset/line/col are the current feed cursor, unadvanced. It is
        consumed by ``next_token()`` as a zero-width ``error`` token;
        see ``_resolve`` for how it interacts with an in-progress
        attempt and with follow checks."""
        if self._closed:
            raise ValueError("cannot feed a closed IncrementalLexer")
        self._buf.append(_BadMarker(raw, self._feed_off, self._feed_line, self._feed_col))

    def close(self) -> None:
        self._closed = True

    def run(self, text: str) -> list:
        self.feed(text)
        self.close()
        out = []
        while (t := self.next_token()) is not EOF:
            out.append(t)
        return out

    # ── attempt-state helpers ───────────────────────────────────────

    def _reset_attempt(self) -> None:
        self._q = self.dfa.start
        self._pending = []
        self._accepts = []

    def _unread(self, entries: list) -> None:
        for e in reversed(entries):
            self._buf.appendleft(e)

    def _follow_ok(self, label: str, after_char, after_is_eof: bool) -> bool:
        follow = self.lexer.follow
        if label not in follow:
            return True
        syms, eof_ok = follow[label]
        if after_is_eof:
            return eof_ok
        return self.partition.symbol_of(after_char) in syms

    # ── the driver loop ─────────────────────────────────────────────

    def next_token(self):
        if self._eof_returned:
            return EOF
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

            entry = self._buf[0] if self._buf else None
            if entry is None and not self._closed:
                return NEED_MORE

            if entry is not None and not isinstance(entry, _BadMarker):
                ch = entry[0]
                sym = self.partition.symbol_of(ch)
                dest = self.dfa.delta[self._q].get(sym)
                if dest is not None:
                    self._buf.popleft()
                    self._pending.append(entry)
                    self._q = dest
                    labels = self.dfa.accepts[dest]
                    if labels:
                        self._accepts.append((len(self._pending), labels))
                    continue

            result = self._resolve(entry)
            if result is _CONTINUE:
                continue
            if result is EOF:
                self._eof_returned = True
            return result

    # ── attempt resolution (no accept, or choosing among accepts) ───

    def _resolve(self, entry):
        pending = self._pending
        is_eof = entry is None
        is_bad = isinstance(entry, _BadMarker)
        # A bad-decode marker (feed_bad) is, for follow-disqualification
        # purposes ONLY, treated exactly like end-of-input-with-eof_ok:
        # the invalid byte sequence terminates the character stream
        # locally the same way EOF does, so e.g. an `end` token whose
        # follow constraint accepts eof also survives when what follows
        # is garbage bytes rather than true input end. This does NOT
        # make `is_bad` behave like real EOF below (an empty attempt
        # facing a bad marker resolves to a bad token, not to EOF).
        if is_bad:
            nxt_char, after_is_eof_default = None, True
        else:
            nxt_char, after_is_eof_default = (entry[0], False) if entry is not None else (None, True)

        for length, labels in reversed(self._accepts):
            if length < len(pending):
                after_char, after_is_eof = pending[length][0], False
            else:
                after_char, after_is_eof = nxt_char, after_is_eof_default
            for label in labels:
                if self._follow_ok(label, after_char, after_is_eof):
                    matched = pending[:length]
                    self._unread(pending[length:])
                    return self._emit(label, matched)

        # no accept survives this attempt
        if not pending:
            if is_eof:
                return EOF
            if is_bad:
                marker = self._buf.popleft()
                return self._bad_tok(marker)
            culprit = self._buf.popleft()
            return self._error_tok("no_token", culprit[0], [culprit])
        if is_eof:
            # unterminated: consume all pending, do NOT push back (would loop)
            text = "".join(e[0] for e in pending)
            tok = self._error_tok("unterminated", text, pending)
            return tok
        self._unread(pending[1:])
        return self._error_tok("no_token", pending[0][0], pending[:1])

    def _error_tok(self, reason: str, culprit: str, consumed: list) -> Tok:
        start = consumed[0][1:]
        last = consumed[-1]
        end = _next_pos(last[1], last[2], last[3], last[0])
        glue = self._glue
        self._glue = "glued"
        self._reset_attempt()
        return Tok(kind="error", value=(reason, culprit), lexeme="".join(e[0] for e in consumed),
                   start=start, end=end, glue=glue)

    def _bad_tok(self, marker: _BadMarker) -> Tok:
        """Emit the zero-width `error` token for an invalid byte
        sequence enqueued via `feed_bad`. Called only once any
        in-progress attempt has already been resolved (see `_resolve`)
        and the marker is at the front of the buffer with no pending
        chars ahead of it."""
        start = (marker.offset, marker.line, marker.col)
        glue = self._glue
        self._glue = "glued"
        self._reset_attempt()
        return Tok(kind="error", value=("invalid_encoding", marker.raw), lexeme="",
                   start=start, end=start, glue=glue)

    # ── emitting a resolved accept ──────────────────────────────────

    def _emit(self, label: str, matched: list):
        kind = self.lexer.kind[label]
        if kind == "trivia":
            self._reset_attempt()
            if label in self.lexer.nest:
                self._nest = {"rule": label, "depth": 1}
            else:
                self._glue = "spaced"
            return _CONTINUE

        lexeme = "".join(e[0] for e in matched)
        builder_name = self.lexer.builder.get(label)
        builder = self.builders.get(builder_name) if builder_name else None
        value = builder(lexeme) if builder is not None else lexeme

        start = matched[0][1:]
        last = matched[-1]
        end = _next_pos(last[1], last[2], last[3], last[0])
        glue = self._glue
        self._glue = "glued"
        self._reset_attempt()
        return Tok(kind=label, value=value, lexeme=lexeme, start=start, end=end, glue=glue)

    # ── nested-comment sub-loop ──────────────────────────────────────

    def _match_dfa(self, dfa):
        """Greedy longest match of `dfa` against the buffer, from index 0,
        without consuming. Returns matched length (>=0), or None if the
        pattern never accepts, or NEED_MORE if the buffer runs out before
        the walk can be resolved."""
        q = dfa.start
        i = 0
        last_accept = None
        while True:
            if i < len(self._buf):
                entry = self._buf[i]
                if isinstance(entry, _BadMarker):
                    # a bad marker can't be matched as comment content;
                    # stop the walk here as if the pattern couldn't extend.
                    break
                ch = entry[0]
            else:
                if not self._closed:
                    return NEED_MORE
                break
            sym = self.partition.symbol_of(ch)
            dest = dfa.delta[q].get(sym)
            if dest is None:
                break
            q, i = dest, i + 1
            if dfa.accepts[q]:
                last_accept = i
        return last_accept

    def _nest_step(self):
        rule = self._nest["rule"]
        open_dfa, close_dfa = self.lexer.nest[rule]

        m = self._match_dfa(close_dfa)
        if m is NEED_MORE:
            return NEED_MORE
        if m is not None:
            for _ in range(m):
                self._buf.popleft()
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
                for _ in range(m2):
                    self._buf.popleft()
                self._nest["depth"] += 1
                return None

        if self._buf:
            if isinstance(self._buf[0], _BadMarker):
                marker = self._buf.popleft()
                return self._bad_tok(marker)
            self._buf.popleft()
            return None

        # buffer empty here implies self._closed (else _match_dfa above
        # would have returned NEED_MORE already): EOF with depth > 0 --
        # leave nest mode silently (parity-mandated lenient behavior).
        self._nest = None
        self._glue = "spaced"
        return None
