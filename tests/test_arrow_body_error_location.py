"""Regression: the arrow-body SyntaxError must say WHERE, not only WHAT.

`clause body must be parenthesized or a single call` was raised as a bare
one-argument SyntaxError from all three of its sites in
`clausal/templating/term_rewriting.py`, which leaves `filename`, `lineno`, `offset`
and `text` set to None. Every one of those sites is holding an AST node with
`.lineno` when it raises.

Measured cost (a measured authoring study, 2026-08-08): an LLM producer authoring a
20-clause module — six of whose clauses contain LEGAL nested `<-` forms that look
exactly like what the error warns about — burned four attempts guessing which clause
was meant and the run was abandoned. It never had the rule wrong; it could not find
the line.

The location also reaches a consumer for free: `str(SyntaxError)` renders as
`msg (file, line N)` once filename/lineno are set, so any tool already printing the
exception gains the coordinates without changing.

This is the norm elsewhere in the loader, not a new expectation — a clause ended with
`.` instead of `,` already reports filename, lineno, offset and the source text,
because that error comes from Python's own parser. Only the hand-raised arrow-body
error dropped it.
"""

import os

import pytest

from clausal.import_hook import _load_module


def _load(tmp_path, source: str, name: str):
    path = os.path.join(str(tmp_path), f"{name}.clausal")
    with open(path, "w") as f:
        f.write(source)
    return _load_module(name, path)


# `bad_clause` is on line 6 in each source below, with legal clauses above it, so a
# raise that reports "somewhere in this file" cannot pass by accident.
_PRELUDE = (
    "-module({mod}, [ good_one(X), good_two(X), bad_clause(X) ])\n"
    "thing(a),\n"
    "other(a),\n"
    "good_one(X) <- (thing(X)),\n"
    "good_two(X) <- thing(X),\n"
)


def test_unparenthesised_multi_goal_body_reports_its_line(tmp_path):
    src = _PRELUDE.format(mod="abl_a") + "bad_clause(X) <- thing(X), other(X),\n"
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, src, "abl_a")
    e = ei.value
    assert "parenthesized" in str(e)
    assert e.lineno == 6, f"expected the offending clause's line, got {e.lineno!r}"
    assert e.filename and e.filename.endswith("abl_a.clausal")
    assert e.text and "bad_clause" in e.text


def test_unparenthesised_operator_body_reports_its_line(tmp_path):
    """The other route into the same error: an operator body absorbs the USub deeper."""
    src = _PRELUDE.format(mod="abl_b") + "bad_clause(X) <- thing(X) and other(X),\n"
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, src, "abl_b")
    e = ei.value
    assert "parenthesized" in str(e)
    assert e.lineno == 6, f"expected the offending clause's line, got {e.lineno!r}"


def test_the_location_reaches_str_so_existing_printers_gain_it(tmp_path):
    """What the downstream loader actually surfaces is `str(e)`. No consumer change needed."""
    src = _PRELUDE.format(mod="abl_c") + "bad_clause(X) <- thing(X), other(X),\n"
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, src, "abl_c")
    assert "line 6" in str(ei.value)


def test_legal_nested_arrow_forms_are_still_accepted(tmp_path):
    """The six shapes that made the un-located error so expensive must keep loading:
    a parenthesised `<-` inside a call argument is legal and must not be flagged."""
    src = (
        "-module(abl_d, [ q(OUT) ])\n"
        "pairs([[1, 1], [2, 2]]),\n"
        "q(OUT) <- (pairs(L), filter_map(L, ((A, B) <- (B is A)), OUT)),\n"
    )
    _load(tmp_path, src, "abl_d")   # must not raise
