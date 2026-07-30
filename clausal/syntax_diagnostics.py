"""Actionable diagnostics for a syntax error in a ``.clausal`` source file.

``.clausal`` is Python surface syntax, so a malformed clause reaches the author
as CPython's stock one-liner::

    invalid syntax (m.clausal, line 6)

and nothing else.  Two things are wrong with that, and the second is what makes
it expensive (see ``todo/done/syntax-error-shows-no-source-line.md``: 18 repair
attempts across four runs, 80% never escaping):

1. **No source text.**  The ``SyntaxError`` carries ``text`` and ``offset`` and
   CPython's own traceback renders both — but the loader's message is consumed
   as a single line by the test runner, so the caret never arrives.
2. **The reported line is not the faulty line.**  A parser reports where it gave
   up, which for a rule body is the closing ``)``, the ``).`` or the last goal.
   In the reproduction the mistake is on line 5 (``Y is`` with no right-hand
   side) and the message says line 6.  Every observed instance behaved this way.

Together those two make the message worse than uninformative: it points at a
line that is *perfectly correct* and gives the author no text with which to
disbelieve it.  Rendering the source is what makes the off-by-some-lines
survivable — hence the window below.

**Why a window and not just the reported line.**  Showing only line 6 would
faithfully reproduce CPython and still point at correct code.  Three preceding
lines is the smallest window that covers the observed distance between the
defect and the give-up point (one to two goals), and it is bounded, so a 40-goal
body cannot turn an error into a wall of source.  The enclosing clause head is
added when it falls outside the window — one line, elided in the middle, so the
author always knows *which* clause is broken.  That is the same principle as
``import_diagnostics``: say what is there and where, not only what is missing.

Everything here runs on the error path only.

Scope: ``.clausal`` files exclusively.  A syntax error in a genuine ``.py``
file is CPython's to report and is left untouched, and a ``.pl`` file is not
enriched either — its line numbers belong to the *translated* Clausal text, not
to anything the author wrote.
"""

from __future__ import annotations

import re
import textwrap

# How many lines above the reported line are shown.
#
# Justification: the parser gives up at the end of the construct, so the defect
# sits at or just above the reported line -- in the census it was one or two
# goals earlier, never more.  Three covers that with a margin; beyond it the
# extra rows stop being evidence and start being a haystack, which is the
# failure mode this fix exists to avoid.  The enclosing clause head is shown
# separately (one row, with an elision marker) so an author whose window does
# not reach the head still knows which clause to open.
_CONTEXT_LINES = 3

# How far back to look for the enclosing clause head before concluding there
# isn't one worth showing.
_HEAD_SEARCH_LIMIT = 60

# Longest source line rendered verbatim.  Past this the line is windowed
# around the caret; a generated or minified line must not push the diagnosis
# off the terminal.
_MAX_SRC_COLS = 100

_WIDTH = 78
_INDENT = "  "

_ENRICHED_FLAG = "_clausal_syntax_diagnostic"

_CLAUSAL_SUFFIX = ".clausal"


# ── source utilities ─────────────────────────────────────────────────────────


def _code_part(line: str) -> str:
    """``line``'s code: comment dropped, string *contents* blanked out.

    Blanking rather than deleting keeps every column index valid, so a caret
    computed on this string still points at the right character of the real
    line.  Blanking at all is what stops ``X = "a :- b"`` from being read as a
    Prolog rule, or a ``+`` inside a literal from being read as a dangling
    operator.

    Deliberately simple: single- and double-quoted strings with backslash
    escapes, one line at a time.  A triple-quoted block spanning lines can
    still fool it, which costs at worst one construct guess -- never
    correctness, because the guess is only ever additive to the rendered
    source, which is taken from the file verbatim.
    """
    out = []
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                out.append("  "[:len(line[i:i + 2])])
                i += 2
                continue
            if ch == quote:
                quote = None
            else:
                ch = " "
        elif ch in "'\"":
            quote = ch
        elif ch == "#":
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _previous_code_line(lines: list[str], lineno: int) -> int | None:
    """The nearest line above ``lineno`` carrying code (1-based), or None."""
    n = lineno - 1
    while n >= 1:
        if _code_part(lines[n - 1]).strip():
            return n
        n -= 1
    return None


def _enclosing_head(lines: list[str], lineno: int) -> int | None:
    """The line of the clause head enclosing ``lineno`` (1-based), or None.

    A Clausal clause head starts at column 0; scanning up for the first
    unindented line that opens a rule (``<-``) or a parenthesised group is a
    cheap, purely textual approximation, and a wrong guess costs one row.
    """
    limit = max(1, lineno - _HEAD_SEARCH_LIMIT)
    for n in range(lineno, limit - 1, -1):
        code = _code_part(lines[n - 1])
        if not code.strip() or code[:1].isspace():
            continue
        if "<-" in code or code.rstrip().endswith("("):
            return n
        # An unindented line that is not a head means we have left the clause.
        return None
    return None


def _clip(text: str, col: int | None):
    """``(rendered, col)`` — ``text`` bounded to ``_MAX_SRC_COLS`` columns,
    with ``col`` translated into the rendered string's coordinates.

    Tabs are expanded first: a caret counted in source columns would otherwise
    land nowhere near the character it names.
    """
    if "\t" in text:
        if col is not None:
            col = len(text[:col].expandtabs())
        text = text.expandtabs()
    text = text.rstrip()
    if len(text) <= _MAX_SRC_COLS:
        return text, col
    if col is None or col <= _MAX_SRC_COLS - 10:
        return text[:_MAX_SRC_COLS - 3] + "...", col
    start = max(0, col - _MAX_SRC_COLS // 2)
    return "..." + text[start:start + _MAX_SRC_COLS - 3], col - start + 3


# ── construct inference ──────────────────────────────────────────────────────


class _Guess:
    """A named Clausal-level construct the parser most likely objected to."""

    __slots__ = ("lineno", "col", "reason", "remedy")

    def __init__(self, lineno, col, reason, remedy):
        self.lineno = lineno
        self.col = col
        self.reason = reason
        self.remedy = remedy


# Operators that must be followed by something.  Ordered longest-first so
# ``//`` is not read as ``/`` and ``<-`` is not read as ``<``.
_DANGLING_OPS = [
    "<-", "->", "//", "**", "==", "!=", "<=", ">=", ">>", "<<",
    "+", "-", "*", "/", "%", "<", ">", "=", "&", "|", "^", "@", "~",
]
_DANGLING_WORDS = ["is", "in", "not", "and", "or"]

_DANGLING_RE = re.compile(
    r"(?:(?<![\w])(?:" + "|".join(_DANGLING_WORDS) + r")|"
    + "|".join(re.escape(op) for op in _DANGLING_OPS) + r")$"
)

_ARITH_REMEDY = ("complete the expression, or delete the goal — a Clausal goal "
                 "cannot end on an operator.")
_BODY_REMEDY = ("a rule body spanning several lines must be parenthesised: "
                "`head <- (` then comma-separated goals then `)`.")
_COMMA_REMEDY = ("goals in a rule body are separated by `,` — add the missing "
                 "one, or join the two lines into a single goal.")
_DOT_REMEDY = ("drop the trailing `.` — a Clausal clause ends with `)` or "
               "`),`, never with Prolog's `).`.")
_PROLOG_ARROW_REMEDY = ("Clausal writes a rule as `head <- (body)`, not as "
                        "Prolog's `head :- body.`.")


def _closing_for(msg: str) -> str | None:
    m = re.search(r"'(.)' was never closed", msg or "")
    if not m:
        return None
    return {"(": ")", "[": "]", "{": "}"}.get(m.group(1))


def _guess(lines: list[str], exc) -> _Guess | None:
    """Name the construct at fault, or return None rather than mislead."""
    lineno = exc.lineno
    msg = exc.msg or ""
    reported = _code_part(lines[lineno - 1])

    # CPython already located it: an unclosed bracket is reported at the
    # opening bracket, which IS the construct at fault.
    close = _closing_for(msg)
    if close is not None:
        col = (exc.offset or 1) - 1
        return _Guess(lineno, col,
                      f"this is never closed — no matching `{close}`",
                      f"add the matching `{close}`; a rule body must be closed "
                      f"before the next clause begins.")

    # ...as is a missing separator, which CPython names but in Python's terms.
    if "forgot a comma" in msg:
        return _Guess(lineno, (exc.offset or 1) - 1,
                      "this goal is not followed by `,`", _COMMA_REMEDY)

    if "unterminated" in msg:
        return _Guess(lineno, (exc.offset or 1) - 1, "the quote opens here",
                      "close the string on this line, or use a triple-quoted "
                      "literal to span lines.")

    # Prolog habits.  Both parse as Python and fail a line or two later, so
    # they are worth naming explicitly.
    stripped = reported.strip()
    if stripped.endswith(".") and stripped.rstrip(".").rstrip().endswith(
            (")", "]", "}")):
        return _Guess(lineno, len(reported.rstrip()) - 1,
                      "trailing `.` — this is Prolog's clause terminator",
                      _DOT_REMEDY)

    for n in (lineno, _previous_code_line(lines, lineno)):
        if n is None:
            continue
        code = _code_part(lines[n - 1])
        if ":-" in code:
            return _Guess(n, code.index(":-"),
                          "`:-` is Prolog's rule operator, not Clausal's",
                          _PROLOG_ARROW_REMEDY)

    # The common case: the parser gave up at the *end* of a construct, so the
    # defect is on the reported line or on the last code line above it.  A line
    # that ends on an operator has no right-hand side.
    for culprit in (lineno, _previous_code_line(lines, lineno)):
        if culprit is None:
            continue
        code = _code_part(lines[culprit - 1])
        m = _DANGLING_RE.search(code)
        if not m:
            continue
        op = m.group(0)
        if op == "<-":
            return _Guess(culprit, m.start(),
                          "`<-` has no body on this line", _BODY_REMEDY)
        return _Guess(culprit, m.end(),
                      f"`{op}` has no right-hand side", _ARITH_REMEDY)
    return None


# ── rendering ────────────────────────────────────────────────────────────────


def _arrow(text: str) -> list[str]:
    return textwrap.wrap(
        text, width=_WIDTH, initial_indent=f"{_INDENT}-> ",
        subsequent_indent=f"{_INDENT}   ",
        break_long_words=False, break_on_hyphens=False,
    )


def _render(exc, lines: list[str], guess: _Guess | None) -> list[str]:
    """The body of the report: the source that explains Python's one-liner.

    Returned without that one-liner so the caller can prepend it for ``str``
    and omit it for the traceback note, where CPython has already printed it.
    """
    lineno = exc.lineno
    start = max(1, lineno - _CONTEXT_LINES)
    if guess is not None and guess.lineno < start:
        start = guess.lineno

    head = _enclosing_head(lines, start - 1) if start > 1 else None

    # (lineno | None for the elision row)
    shown: list[int | None] = []
    if head is not None:
        shown.append(head)
        if start - head > 1:
            shown.append(None)
    shown.extend(range(start, lineno + 1))

    # At most one caret per line: the construct we can name, and — when that
    # is some *earlier* line — a marker on the reported line saying explicitly
    # that it is only where the parser stopped, not where the mistake is.
    annotations: dict[int, tuple[int, str]] = {}
    if guess is not None:
        annotations[guess.lineno] = (guess.col, guess.reason)
    if guess is None or guess.lineno != lineno:
        annotations[lineno] = ((exc.offset or 1) - 1,
                               "parse gave up here" if guess is not None
                               else "")

    width = max(len(str(n)) for n in shown if n is not None)
    gutter = " " * width

    out: list[str] = []
    for n in shown:
        if n is None:
            omitted = start - head - 1
            out.append(f"{_INDENT}  {gutter} : ...{omitted} line"
                       f"{'' if omitted == 1 else 's'} omitted")
            continue
        mark = annotations.get(n)
        text, col = _clip(lines[n - 1], mark[0] if mark else None)
        out.append(f"{_INDENT}  {n:>{width}} | {text}")
        if mark is not None:
            caret = " " * max(0, col) + "^"
            out.append(f"{_INDENT}  {gutter} | {caret} {mark[1]}".rstrip())

    if guess is not None:
        out.extend(_arrow(guess.remedy))
    return out


# ── entry point ──────────────────────────────────────────────────────────────


class _ClausalSyntaxReport:
    """Mixin carrying the rendered report as the exception's ``str``.

    Subclassing rather than rewriting ``msg`` is deliberate:

    * ``msg``, ``lineno``, ``offset``, ``text`` and ``filename`` stay exactly
      as CPython set them, so anything inspecting them still works;
    * ``str(exc)`` gains the report — CPython would otherwise append its
      ``(file, line N)`` suffix to the *last* line of a multi-line ``msg``;
    * the subclass keeps the original class's name and base, so ``except
      SyntaxError``, ``except IndentationError`` and traceback headers are
      unaffected.

    The one thing that does change is class *identity*: ``type(exc) is
    SyntaxError`` is now False where ``isinstance`` is still True.  Pickling
    is handled explicitly below, because a dynamically created class named
    ``SyntaxError`` is not the one ``builtins`` holds.
    """

    clausal_report = ""
    _clausal_base = SyntaxError

    def __str__(self):
        return self.clausal_report or super().__str__()

    def __reduce__(self):
        # Degrade to the stock exception rather than raise PicklingError:
        # ``args`` carries the full ``(msg, (filename, lineno, offset, text,
        # end_lineno, end_offset))``, so nothing but the rendered report is
        # lost crossing a process boundary.
        return (self._clausal_base, self.args)


_REPORTING_CLASSES: dict[type, type] = {}


def _reporting_class(base: type) -> type:
    cls = _REPORTING_CLASSES.get(base)
    if cls is None:
        cls = type(base.__name__, (_ClausalSyntaxReport, base),
                   {"__module__": base.__module__, "_clausal_base": base})
        _REPORTING_CLASSES[base] = cls
    return cls


def enrich_syntax_error(exc, source, filename):
    """Return a replacement ``SyntaxError``, or ``None`` to re-raise ``exc``.

    ``source`` must be the text of ``filename`` itself; the caller passes the
    exact string it handed to the parser, so the rendered lines and the
    reported line numbers cannot disagree.
    """
    if getattr(exc, _ENRICHED_FLAG, False):
        return None
    if not isinstance(filename, str) or not filename.endswith(_CLAUSAL_SUFFIX):
        return None
    # An error raised while parsing some *other* file (an embedded import, a
    # nested compile) is not ours to re-render.
    if exc.filename != filename:
        return None
    lineno = exc.lineno
    if not isinstance(lineno, int) or lineno < 1:
        return None
    lines = source.splitlines()
    if lineno > len(lines):
        return None

    try:
        guess = _guess(lines, exc)
        body = _render(exc, lines, guess)
    except Exception:  # pragma: no cover - a diagnostic must never mask
        return None
    if not body:  # pragma: no cover - defensive
        return None

    new = _reporting_class(type(exc))(
        exc.msg, (exc.filename, exc.lineno, exc.offset, exc.text,
                  exc.end_lineno, exc.end_offset))
    new.clausal_report = "\n".join([str(exc), *body])
    setattr(new, _ENRICHED_FLAG, True)
    # PEP 678: the note is how the report reaches a *traceback*, which renders
    # ``msg`` (plus its own file/line/caret) rather than ``str(exc)`` for a
    # syntax error — so the note carries the body only, with no duplicated
    # header.
    new.add_note("\n".join(body))
    return new


class clausal_syntax_diagnostics:
    """Context manager: parse ``.clausal`` source with the report attached."""

    def __init__(self, source, filename):
        self._source = source
        self._filename = filename

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None or not isinstance(exc, SyntaxError):
            return False
        better = enrich_syntax_error(exc, self._source, self._filename)
        if better is None:
            return False
        # Re-raise on the original traceback so the frames still point at the
        # parse site; the report already opens with ``str(exc)``.
        raise better.with_traceback(tb) from None
