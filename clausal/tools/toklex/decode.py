"""toklex incremental UTF-8 decode stage (design doc §5-6, byte mode, R6).

``Utf8Feeder`` wraps an ``IncrementalLexer`` (Task 6) and accepts raw
bytes instead of ``str``: it validates the byte stream against the
standard UTF-8 grammar, batches contiguous valid runs into single
``lexer.feed(str)`` calls, and turns any byte sequence that no
continuation can repair into a zero-width ``error`` token via
``lexer.feed_bad(raw)``. A valid multi-byte prefix that is still
incomplete when a ``feed()`` call ends is held as pending input --
never treated as invalid -- until more bytes arrive or ``close()``
forces it out.

Follow-check note (binding decision, see also
``driver.IncrementalLexer._resolve``): for the driver's
follow-disqualification checks, a bad marker behaves exactly like
end-of-input-with-eof_ok. Rationale: an invalid byte sequence
terminates the character stream locally the same way real EOF does,
so e.g. ``end.`` immediately followed by garbage bytes still lexes as
an ``end`` token rather than being disqualified because "what comes
after '.'" isn't a layout character. This is deliberately simpler than
the ISO substitution-of-maximal-subparts convention's "what actually
follows" semantics; see the task brief for the exact ruling.
"""

from __future__ import annotations


def _lead_info(b: int):
    """For a lead byte `b` (0x80-0xFF), return
    ``(continuations_needed, first_continuation_lo, first_continuation_hi)``,
    or ``None`` if `b` can never start a valid UTF-8 sequence (stray
    continuation 0x80-0xBF, overlong lead 0xC0-0xC1, or 0xF5-0xFF)."""
    if 0xC2 <= b <= 0xDF:
        return (1, 0x80, 0xBF)
    if b == 0xE0:
        return (2, 0xA0, 0xBF)
    if b == 0xED:
        return (2, 0x80, 0x9F)
    if 0xE1 <= b <= 0xEF:
        return (2, 0x80, 0xBF)
    if b == 0xF0:
        return (3, 0x90, 0xBF)
    if b == 0xF4:
        return (3, 0x80, 0x8F)
    if 0xF1 <= b <= 0xF3:
        return (3, 0x80, 0xBF)
    return None


class Utf8Feeder:
    """Feed raw bytes with ``.feed()``/``.close()``, pull tokens with
    ``.next_token()`` (delegated straight to the wrapped lexer)."""

    def __init__(self, lexer) -> None:
        self.lexer = lexer
        # Partial multi-byte sequence held across feed() calls: the
        # lead byte plus whatever continuation bytes have been
        # validated so far. `_need` is how many more continuation
        # bytes are still required; `_first_range` is the allowed
        # range for the NEXT continuation byte only when it is the
        # very first one after the lead (E0/ED/F0/F4 have a restricted
        # first-continuation range; every later continuation byte in
        # the sequence, and every lead's first continuation otherwise,
        # is the standard 0x80-0xBF).
        self._seq = bytearray()
        self._need = 0
        self._first_range = None
        self._closed = False

    def next_token(self):
        return self.lexer.next_token()

    def feed(self, data: bytes) -> None:
        if self._closed:
            raise ValueError("cannot feed a closed Utf8Feeder")
        run = bytearray()  # contiguous validated bytes not yet flushed to the lexer
        for byte in data:
            if self._need > 0:
                lo, hi = self._first_range if self._first_range is not None else (0x80, 0xBF)
                if lo <= byte <= hi:
                    self._seq.append(byte)
                    self._first_range = None
                    self._need -= 1
                    if self._need == 0:
                        run.extend(self._seq)
                        self._seq = bytearray()
                    continue
                # Invalid continuation byte: the pending prefix (without
                # this byte) is the maximal invalid subpart -> one bad
                # event for it, then reprocess `byte` fresh below (it
                # may itself be ASCII, a new lead, or another invalid
                # byte -- each handled on its own terms).
                if run:
                    self.lexer.feed(bytes(run).decode("utf-8"))
                    run = bytearray()
                self.lexer.feed_bad(bytes(self._seq))
                self._seq = bytearray()
                self._need = 0
                self._first_range = None
                # fall through -- no `continue`: handle `byte` fresh

            if byte <= 0x7F:
                run.append(byte)
                continue

            info = _lead_info(byte)
            if info is None:
                if run:
                    self.lexer.feed(bytes(run).decode("utf-8"))
                    run = bytearray()
                self.lexer.feed_bad(bytes([byte]))
                continue

            extra, lo, hi = info
            self._seq = bytearray([byte])
            self._need = extra
            self._first_range = (lo, hi)

        if run:
            self.lexer.feed(bytes(run).decode("utf-8"))

    def close(self) -> None:
        if self._closed:
            return
        if self._seq:
            # Truncated valid prefix at end of input -> one bad event,
            # not "invalid" and not silently dropped.
            self.lexer.feed_bad(bytes(self._seq))
            self._seq = bytearray()
            self._need = 0
            self._first_range = None
        self._closed = True
        self.lexer.close()
