import os

import pytest

from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.dcg import render_dcg
from clausal.tools.toklex.driver import IncrementalLexer
from tests._oracles import SCRYER, run_scryer

SAMPLES = ["foo(X, 1). ", "=.. = . ", "1. 1.5 1.0e7 ", "'a''b' \"s\" 0'a ",
           "/* c /* n */ */ x ", "a. ",
           # an unclosed comment is one unterminated error token (2026-09-30)
           "a. /* x ", "a. /* c /* n */ x "]


def test_render_is_nonempty_and_mentions_every_state():
    lx = load_lexer()
    src = render_dcg(lx)
    assert ":- module(" in src or "% toklex" in src
    for q in range(len(lx.dfa.delta)):
        assert f"q{q}(" in src


def _normalize(s):
    return s.replace(" ", "").replace('"', "").replace("'", "")


def _scryer_plist(items):
    """The textual shape Scryer's write_canonical/1 actually prints a
    Prolog list in: nested '.'(Head, Tail) functor notation, never
    `[...]` bracket sugar -- verified empirically (see task-12-report.md
    "Scryer quirks"). Building the expected side in this same shape is
    the "adjust the expected-side derivation" the controller brief
    allows for a renderer-wide formatting quirk (as opposed to a
    per-sample v1-scope gap)."""
    s = "[]"
    for item in reversed(items):
        s = f"'.'({item},{s})"
    return s


@pytest.mark.skipif(not os.path.exists(SCRYER), reason="scryer binary not present")
@pytest.mark.parametrize("sample", SAMPLES)
def test_scryer_agrees_with_python_driver(tmp_path, sample):
    lx = load_lexer()
    pl = tmp_path / "toklex_iso.pl"
    pl.write_text(render_dcg(lx))
    goal_file = tmp_path / "goal.pl"
    goal_file.write_text(
        f":- initialization(main).\n"
        f"main :-\n"
        f"    consult('{pl}'),\n"
        f"    toklex_run({_pl_char_list(sample)}, Ts),\n"
        f"    write_canonical(Ts), nl, halt.\n"
    )
    out = run_scryer(str(goal_file), [], timeout=30).stdout.strip()

    py = IncrementalLexer(lx).run(sample)
    want_items = [f'tok({t.kind},"{t.lexeme}")' for t in py]
    want = _scryer_plist(want_items)

    assert _normalize(out) == _normalize(want)


def _pl_char_list(s: str) -> str:
    """A Prolog char-list literal for `s`, built explicitly (rather than
    relying on a `"..."` literal's double_quotes-flag-dependent parse)
    so the test is not sensitive to Scryer's default double_quotes
    setting."""
    chars = ",".join(_pl_char_atom(c) for c in s)
    return f"[{chars}]"


def _pl_char_atom(c: str) -> str:
    if c == "'":
        return "'\\''"
    if c == "\\":
        return "'\\\\'"
    if c == "\n":
        return "'\\n'"
    if c == "\t":
        return "'\\t'"
    return f"'{c}'"
