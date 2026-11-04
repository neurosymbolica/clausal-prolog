"""A set prints its elements in the standard order of terms (operator
ruling 2026-11-03), in every printer: write/1, print/1, writeq/1, the
toplevel answer, ``term_str``, ``term_pformat`` and ``term_html``.  They
used to print in Python ``repr`` order, which put the atom ``'B c'`` before
the numbers and ``2.0`` wherever its repr fell.

The order is the one msort/2 gives; Scryer has no set term, so the oracle
row checks Scryer's standard order of the same elements (keysort/2, which
is stable and orders keys by the standard order).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
from clausal._suffixes import PROLOG_SUFFIX as PL
from clausal.logic.atoms import mint
from clausal.terms import SetTerm, term_html, term_pformat, term_str, term_write
from tests._oracles import SCRYER, run_scryer

CLAUSAL = CLAUSAL_PROLOG_SUFFIXES[0]
REPO_ROOT = Path(__file__).resolve().parent.parent

ELEMENTS_TEXT = "[b,10,f(x),a,2.0,g(1,2),1,'B c']"
#: The standard order (ISO 7.2), Scryer's: floats, then integers, each by
#: value; then atoms; then compounds by arity, name, args.
ORDERED = "2.0,1,10,'B c',a,b,f(x),g(1,2)"


def _set():
    return SetTerm({mint("b"), 10, ("f", mint("x")), mint("a"), 2.0,
                    ("g", 1, 2), 1, mint("B c")})


def test_term_write_orders_the_elements():
    assert term_write(_set(), quoted=True) == "{" + ORDERED + "}"
    assert term_write(_set(), quoted=False) == "{" + ORDERED.replace(
        "'B c'", "B c") + "}"


def test_term_str_orders_the_elements():
    assert term_str(_set()) == "{2.0, 1, 10, 'B c', a, b, f(x), g(1, 2)}"


def test_term_pformat_orders_the_elements():
    flat = re.sub(r"\s+", "", term_pformat(_set(), width=4))
    assert flat == "{" + ORDERED.replace("'B c'", "'Bc'") + "}"


def test_term_html_orders_the_elements():
    import html
    text = html.unescape(re.sub(r"<[^>]*>", "", term_html(_set())))
    assert text.replace(" ", "") == "{" + ORDERED.replace("'B c'", "'Bc'") + "}"


def test_mixed_numbers():
    # (A set holds one of 1 and 1.0: Python's set equality merges them.)
    s = SetTerm({3, 1.5, 2, 0.5, 1})
    # Every float before every integer, as in Scryer (ISO 7.2.2).
    assert term_write(s, quoted=True) == "{0.5,1.5,1,2,3}"


@pytest.mark.parametrize("suffix", [PL, CLAUSAL], ids=["pl", "clausal"])
def test_writers_from_prolog(tmp_path, suffix):
    path = tmp_path / f"w{suffix}"
    path.write_text("z.\n")
    goal = (f"set_list(S, {ELEMENTS_TEXT}), writeq(S), nl, print(S), nl, "
            f"write(S), nl")
    out = subprocess.run(
        [sys.executable, "-m", "clausal", str(path), "-g", goal],
        capture_output=True, text=True, timeout=120, cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(REPO_ROOT)))
    assert out.stdout.splitlines() == [
        "{" + ORDERED + "}",
        "{" + ORDERED + "}",
        "{" + ORDERED.replace("'B c'", "B c") + "}",
        "S = {" + ORDERED + "}.",
    ], out.stderr


def test_standard_order_oracle():
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    pairs = "[b-0,10-0,f(x)-0,a-0,2.0-0,g(1,2)-0,1-0,'B c'-0]"
    goal = f"keysort({pairs}, Ks), writeq(Ks), nl"
    out = run_scryer(None, [goal + ", false"], timeout=30)
    keys = "2.0-0,1-0,10-0,'B c'-0,a-0,b-0,f(x)-0,g(1,2)-0"
    assert out.stdout.splitlines()[0] == "[" + keys + "]", out.stdout
