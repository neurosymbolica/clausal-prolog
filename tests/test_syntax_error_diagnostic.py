"""A ``.clausal`` syntax error must show the source line, a caret and a reason.

See ``todo/done/syntax-error-shows-no-source-line.md``.  The stock message is

    invalid syntax (m.clausal, line 6)

and nothing else — and the line it names is where the *parser gave up*, not
where the mistake is (the census found the reported line was a ``)``, a ``).``
or the last body goal in every observed instance).  So the author is pointed at
a line that is perfectly correct, with no text to contradict it.

These assertions are about the *content* of the report, because the consumer is
an automated repair loop.
"""

from __future__ import annotations

import textwrap
import traceback

import pytest

from clausal.import_hook import _load_module
from clausal.testing import main


# ── helpers ──────────────────────────────────────────────────────────────────


_counter = 0


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


def load_error(tmp_path, name, src):
    """Load a broken .clausal file; return the SyntaxError it raises."""
    global _counter
    _counter += 1
    p = write(tmp_path, name, src)
    with pytest.raises(SyntaxError) as exc:
        _load_module(f"_syndiag_{_counter}", str(p))
    return exc.value


def source_rows(message):
    """The ``   5 | ...`` numbered source rows of a report."""
    rows = []
    for line in message.splitlines():
        head, sep, rest = line.strip().partition(" | ")
        if sep and head.isdigit():
            rows.append((int(head), rest))
    return rows


# ── the todo's own reproduction ──────────────────────────────────────────────


M_SRC = """
-module(m, [f(A)])

f(X) <- (
    X > 1,
    Y is
)
"""

TEST_LOAD_SRC = """
-import_from(m, [f])

Test("t") <- (
    f(2)
)
"""


def test_reproduction_end_to_end(capsys, tmp_path, monkeypatch):
    """The todo's reproduction, through ``python -m clausal.testing``."""
    write(tmp_path, "m.clausal", M_SRC)
    p = write(tmp_path, "test_load.clausal", TEST_LOAD_SRC)
    monkeypatch.syspath_prepend(str(tmp_path))
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    # Python's own one-liner is still there, verbatim.
    assert "invalid syntax (m.clausal, line 6)" in out
    # ...and now the source it was hiding.
    assert "Y is" in out
    assert "^" in out
    rows = source_rows(out)
    assert (5, "    Y is") in rows
    assert (6, ")") in rows


def test_reproduction_names_the_construct(tmp_path):
    exc = load_error(tmp_path, "m.clausal", M_SRC)
    assert "`is` has no right-hand side" in str(exc)


def test_reported_line_is_marked_as_where_the_parse_gave_up(tmp_path):
    """The reported line is correct code; say so rather than implying blame."""
    exc = load_error(tmp_path, "m.clausal", M_SRC)
    assert "parse gave up here" in str(exc)


def test_first_line_is_pythons_own_message(tmp_path):
    exc = load_error(tmp_path, "m.clausal", M_SRC)
    assert str(exc).splitlines()[0] == "invalid syntax (m.clausal, line 6)"


def test_caret_sits_under_the_offending_column(tmp_path):
    exc = load_error(tmp_path, "m.clausal", M_SRC)
    lines = str(exc).splitlines()
    src_row = next(i for i, ln in enumerate(lines)
                   if ln.strip().startswith("5 | "))
    caret_row = lines[src_row + 1]
    # the caret must fall at or past the end of `Y is`, not at column 0
    assert caret_row.index("^") > lines[src_row].index("Y")
    # and the reported line's caret is at its column 1
    gave_up = next(ln for ln in lines if "parse gave up here" in ln)
    assert gave_up.index("^") == lines[src_row].index("Y") - 4


# ── attributes and type are preserved ────────────────────────────────────────


def test_exception_attributes_are_preserved(tmp_path):
    exc = load_error(tmp_path, "m.clausal", M_SRC)
    assert isinstance(exc, SyntaxError)
    assert exc.msg == "invalid syntax"          # unchanged, not the report
    assert exc.lineno == 6
    assert exc.offset == 1
    assert exc.text == ")\n"
    assert exc.filename.endswith("m.clausal")


def test_enriched_error_still_pickles(tmp_path):
    """It degrades to the stock exception rather than raising PicklingError."""
    import pickle

    exc = load_error(tmp_path, "m.clausal", M_SRC)
    round_tripped = pickle.loads(pickle.dumps(exc))
    assert type(round_tripped) is SyntaxError
    assert round_tripped.lineno == 6
    assert round_tripped.text == ")\n"


def test_indentation_error_keeps_its_class(tmp_path):
    exc = load_error(tmp_path, "indent.clausal",
                     "f(X) <- (\n    X > 1,\n  )\n   g(X),\n")
    assert isinstance(exc, IndentationError)
    assert type(exc).__name__ == "IndentationError"
    assert "unexpected indent" in str(exc).splitlines()[0]


def test_report_reaches_the_traceback(tmp_path):
    exc = load_error(tmp_path, "m.clausal", M_SRC)
    rendered = "".join(traceback.format_exception(type(exc), exc,
                                                  exc.__traceback__))
    assert "`is` has no right-hand side" in rendered
    # CPython already prints the file, line and its own caret there — the note
    # must add the context, not repeat the header.
    assert rendered.count("invalid syntax") == 1


# ── genuine Python .py syntax errors are untouched ───────────────────────────


def test_python_file_syntax_error_is_not_reformatted(tmp_path, monkeypatch):
    """A real .py file must get CPython's message, unmodified."""
    import importlib

    write(tmp_path, "_syndiag_broken_py.py", """
    def f():
        x = (
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(SyntaxError) as exc:
        importlib.import_module("_syndiag_broken_py")
    msg = str(exc.value)
    assert "\n" not in msg
    assert "|" not in msg
    assert "parse gave up here" not in msg


def _raw_error(src, filename):
    try:
        compile(src, filename, "exec")
    except SyntaxError as exc:
        return exc
    raise AssertionError("source unexpectedly parsed")


def test_only_clausal_files_are_enriched():
    """.py and .pl are out of scope, at the enrichment boundary itself."""
    from clausal.syntax_diagnostics import enrich_syntax_error

    src = "f(X) <- (\n    Y is\n)\n"
    # .pl line numbers belong to the *translated* Clausal text, not to
    # anything the author wrote, so a .pl file is deliberately left alone.
    for name in ("m.py", "m.pl", "<string>"):
        exc = _raw_error(src, name)
        assert enrich_syntax_error(exc, src, name) is None, name
    exc = _raw_error(src, "m.clausal")
    assert enrich_syntax_error(exc, src, "m.clausal") is not None


def test_error_from_another_file_is_not_re_rendered():
    """A SyntaxError raised while parsing some other file is not ours."""
    from clausal.syntax_diagnostics import enrich_syntax_error

    src = "f(X) <- (\n    Y is\n)\n"
    exc = _raw_error(src, "other.clausal")
    assert enrich_syntax_error(exc, src, "m.clausal") is None


def test_reify_file_gets_the_same_report(tmp_path):
    from clausal.reflection import ReifyError, reify_file

    p = write(tmp_path, "m.clausal", M_SRC)
    with pytest.raises(ReifyError) as exc:
        reify_file(str(p))
    assert "`is` has no right-hand side" in str(exc.value)


def test_python_syntax_error_inside_clausal_is_still_enriched(tmp_path):
    """Embedded Python lives in the .clausal file, so it gets the treatment."""
    exc = load_error(tmp_path, "emb.clausal", """
    def helper(x):
        return x +

    f(X) <- (helper(X) > 1)
    """)
    assert (2, "    return x +") in source_rows(str(exc))


def test_tab_indented_source_keeps_the_caret_aligned(tmp_path):
    exc = load_error(tmp_path, "tabbed.clausal", "f(X) <- (\n\tX > 1,\n\tY is\n)\n")
    lines = str(exc).splitlines()
    src_row = next(i for i, ln in enumerate(lines)
                   if ln.strip().startswith("3 | "))
    # tabs are expanded, so the caret must land past `is`, not at column 5
    assert lines[src_row + 1].index("^") > lines[src_row].index("Y")


# ── construct inference ──────────────────────────────────────────────────────


def test_prolog_clause_terminator_named(tmp_path):
    exc = load_error(tmp_path, "dot.clausal", """
    f(X) <- (
        X > 1,
    ).
    """)
    msg = str(exc)
    assert "trailing `.`" in msg
    assert "Prolog" in msg


def test_unparenthesised_rule_body_named(tmp_path):
    exc = load_error(tmp_path, "arrow.clausal", """
    f(X) <-
        X > 1,
        g(X)
    """)
    msg = str(exc)
    assert "parenthesis" in msg.lower()
    assert "<-" in msg


def test_never_closed_body_shows_the_opening_line(tmp_path):
    exc = load_error(tmp_path, "open.clausal", """
    -module(m, [f(A)])

    f(X) <- (
        X > 1,
        g(X)
    """)
    msg = str(exc)
    assert "never closed" in msg
    assert (3, "f(X) <- (") in source_rows(msg)


def test_missing_comma_between_goals_named(tmp_path):
    exc = load_error(tmp_path, "comma.clausal", """
    f(X) <- (
        X > 1
        Y = 2,
        g(Y)
    )
    """)
    msg = str(exc)
    assert "X > 1" in msg
    assert "goal" in msg
    assert "," in msg


def test_operators_inside_string_literals_are_not_diagnosed(tmp_path):
    """`:-` in a string is not a Prolog rule; blame the real dangling `+`."""
    exc = load_error(tmp_path, "quoted.clausal", """
    f(X, Y) <- (
        Y = "a :- b" +
    )
    """)
    msg = str(exc)
    assert "`+` has no right-hand side" in msg
    assert "Prolog" not in msg


def test_dangling_arithmetic_operator_named(tmp_path):
    exc = load_error(tmp_path, "arith.clausal", """
    f(X, Y) <- (
        Y is X +
    )
    """)
    assert "`+` has no right-hand side" in str(exc)


# ── the context window is a window, not a wall ───────────────────────────────


LONG_BODY = """
-module(m, [f(A)])

f(X) <- (
    a(X),
    b(X),
    c(X),
    d(X),
    e(X),
    g(X),
    h(X),
    i(X),
    j(X),
    Y is
)
"""


def test_context_window_is_bounded(tmp_path):
    exc = load_error(tmp_path, "long.clausal", LONG_BODY)
    rows = source_rows(str(exc))
    assert len(rows) <= 6, f"too much source shown: {rows}"
    assert any(n == 14 for n, _ in rows)      # the reported line
    assert any(n == 13 for n, _ in rows)      # the culprit
    assert not any(n == 4 for n, _ in rows)   # not the whole body


def test_enclosing_clause_head_is_shown(tmp_path):
    """Which clause am I in?  Say where, not only what."""
    exc = load_error(tmp_path, "long.clausal", LONG_BODY)
    rows = source_rows(str(exc))
    assert (3, "f(X) <- (") in rows, rows
    assert "omitted" in str(exc)


def test_report_has_a_remedy_line(tmp_path):
    exc = load_error(tmp_path, "m.clausal", M_SRC)
    assert any(ln.strip().startswith("->") for ln in str(exc).splitlines())


# ── ``.seam`` is an alias extension for ``.clausal`` ─────────────────────────


def test_seam_file_gets_the_same_report(tmp_path):
    """The report is gated on the file's extension; the alias must pass it."""
    exc = load_error(tmp_path, "m.seam", M_SRC)
    assert str(exc).splitlines()[0] == "invalid syntax (m.seam, line 6)"
    assert "`is` has no right-hand side" in str(exc)
    assert (5, "    Y is") in source_rows(str(exc))
