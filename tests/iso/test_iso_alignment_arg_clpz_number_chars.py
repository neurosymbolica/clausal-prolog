"""Three ISO/Scryer alignments ruled 2026-09-30, pinned against Scryer.

* ``arg/3`` with N unbound is ``instantiation_error`` (ISO 8.5.2.3 a); it
  used to ENUMERATE the (N, Arg) pairs, SWI's extension (D51).
* The clpz ``#`` family refuses a non-arithmetic operand with clpz's
  ``domain_error(clpz_expression, Culprit)``; a ground one used to fail,
  succeed or raise type_error(orderable, _) depending on the operator.
* ``number_chars/2`` and ``number_codes/2`` READ their text as Scryer does
  and raise ``syntax_error(Kind)`` on text that is not a number; they used
  to parse with Python's int()/float() and fail (A09-F030).

The same Prolog program runs in the engine (the native ``.pl`` front end)
and in Scryer.  Each row catches ``error(F, C)`` and answers ``F`` (the clpz
rows: Scryer's context is its library's internal ``unknown(foo)-1``, which
is not compared) or ``[F, C]``.  The seam spellings are pinned engine-only.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from .test_iso_answers_scryer import _engine_answers, _load_seam, _scryer_answers

#: (row name, body binding R, what both print)
ROWS = [
    # arg/3
    ("arg unbound N", "catch(arg(N, f(a, b), X), error(F, C), R = [F, C])",
     ["[instantiation_error,arg/3]"]),
    ("arg unbound N given arg",
     "catch(arg(N, f(a, b), b), error(F, C), R = [F, C])",
     ["[instantiation_error,arg/3]"]),
    ("arg bound N", "arg(2, f(a, b), R)", ["b"]),
    # the clpz # family
    ("#= ground atom", "catch(1 #= foo, error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#\\= ground atom", "catch(1 #\\= foo, error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#< ground atom", "catch(1 #< foo, error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#> ground atom", "catch(foo #> 1, error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#=< ground atom", "catch(1 #=< foo, error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#>= ground atom", "catch(1 #>= foo, error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#= atom both sides", "catch(foo #= foo, error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#= atom in a sum", "catch(X #= foo + 1, error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#= true", "catch(X #= true, error(F, _), R = F)",
     ["domain_error(clpz_expression,true)"]),
    ("#= unknown compound", "catch(1 #= f(a), error(F, _), R = F)",
     ["domain_error(clpz_expression,f(a))"]),
    ("#= list", "catch(X #= [1], error(F, _), R = F)",
     ["domain_error(clpz_expression,[1])"]),
    ("reified", "catch(B #<==> (1 #= foo), error(F, _), R = F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#= still solves", "X #= 1 + 2 * Y, Y = 3, R = X", ["7"]),
    # number_chars/2, number_codes/2
    ("nc letter", "catch(number_chars(N, [a]), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_end_of_file),number_chars/2]"]),
    ("nc trailing letter",
     "catch(number_chars(N, ['1', a]), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_char),number_chars/2:0]"]),
    ("nc trailing layout",
     "catch(number_chars(N, ['1', ' ']), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_char),number_chars/2:0]"]),
    ("nc empty", "catch(number_chars(N, []), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_end_of_file),number_chars/2]"]),
    ("nc plus", "catch(number_chars(N, ['+', '1']), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_char),number_chars/2:0]"]),
    ("nc inf", "catch(number_chars(N, [i, n, f]), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_end_of_file),number_chars/2]"]),
    ("nc no fraction",
     "catch(number_chars(N, ['1', e, '5']), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_char),number_chars/2:0]"]),
    ("nc both bound", "catch(number_chars(1, [a]), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_end_of_file),number_chars/2]"]),
    ("nc leading layout", "number_chars(R, [' ', '1'])", ["1"]),
    ("nc minus layout", "number_chars(R, ['-', ' ', '1'])", ["-1"]),
    ("nc hex", "number_chars(R, ['0', x, '1', 'A'])", ["26"]),
    ("nc char code", "number_chars(R, ['0', '''', a])", ["97"]),
    ("nc digit groups", "number_chars(R, ['1', '_', '0'])", ["10"]),
    ("nc float", "number_chars(R, ['1', '.', '5', e, '-', '3'])", ["0.0015"]),
    ("nc reads, not compares", "number_chars(1, ['0', '1']), R = y", ["y"]),
    ("ncodes letter",
     "catch(number_codes(N, [0'a]), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_end_of_file),number_codes/2]"]),
    ("ncodes trailing letter",
     "catch(number_codes(N, [0'1, 0'a]), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_char),number_codes/2:0]"]),
    ("ncodes ok", "number_codes(R, [0'4, 0'2])", ["42"]),
    ("ncodes both bound", "number_codes(12, [0'1, 0'2]), R = y", ["y"]),
    ("nc lone bang", "catch(number_chars(N, [!]), error(F, C), R = [F, C])",
     ["[syntax_error(cannot_parse_big_int),number_chars/2:0]"]),
    ("nc infinite float",
     "catch(number_chars(N, ['1', '.', '0', e, '4', '0', '0']), error(F, C),"
     " R = [F, C])",
     ["[syntax_error(infinite_float),number_chars/2:0]"]),
    ("nc unterminated comment",
     "catch(number_chars(N, [/, *]), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_end_of_file),number_chars/2]"]),
    ("nc comments lead", r"number_chars(R, ['%', c, '\n', /, *, *, /, '1'])",
     ["1"]),
    ("nc hex escape", r"number_chars(R, ['0', '''', '\\', x, '4', '1', '\\'])",
     ["65"]),
    ("nc radix no digits",
     "catch(number_chars(N, ['0', x]), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_end_of_file),number_chars/2]"]),
    ("nc radix bad digit",
     "catch(number_chars(N, ['0', o, '8']), error(F, C), R = [F, C])",
     ["[syntax_error(unexpected_char),number_chars/2:0]"]),
    ("nc partial list",
     "catch(number_chars(N, ['1'|_]), error(F, C), R = [F, C])",
     ["[instantiation_error,number_chars/2]"]),
]

PROGRAM = ":- use_module(library(clpz)).\n" + "".join(
    f"r{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(ROWS))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("iso_align")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_iso_align_0930"
    (d / f"{name}.pl").write_text(PROGRAM)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 5) == ROWS[i][2]


def test_oracle(scryer):
    del scryer   # the fixture only asserts the binary is there
    got = _scryer_answers(PROGRAM, [(f"r{i}(R)", 5) for i in range(len(ROWS))])
    assert got == [r[2] for r in ROWS]


# ── the seam spellings (engine only) ─────────────────────────────────────────

_SEAM_FACTS = "-allow_singletons\n-private([foo, y, n])\n"

#: (row name, seam body binding R, what the engine prints)
SEAM_ROWS = [
    ("arg unbound N", "catch(arg(N, [1, 2], X), error(F, C), R is F)",
     ["instantiation_error"]),
    ("#= ground atom", "catch('#='(1, foo), error(F, C), R is F)",
     ["domain_error(clpz_expression,foo)"]),
    ("#\\= ground atom", "catch('#\\\\='(1, foo), error(F, C), R is F)",
     ["domain_error(clpz_expression,foo)"]),
    # ruled 2026-09-30: a boolean in arithmetic is an error; a Python bool
    # used to count as 1 (`'#='(X, True)` bound X = 1); D47: it is the atom
    # true, and writes as one
    ("#= a Python bool", "catch('#='(X, True), error(F, C), R is F)",
     ["domain_error(clpz_expression,true)"]),
    ("#< a Python bool in a sum", "catch('#<'(0, False + 1), error(F, C), R is F)",
     ["domain_error(clpz_expression,false)"]),
    # floats: unchanged by this ruling (a separate one)
    ("#= a float", "'#='(R, 1.5)", ["1.5"]),
    ("number_chars", "catch(number_chars(N, ['1', 'x']), error(F, C), R is F)",
     ["syntax_error(unexpected_char)"]),
]


@pytest.fixture(scope="module")
def seam_mod(tmp_path_factory):
    rows = [(name, body, None, None, None) for name, body, _ in SEAM_ROWS]
    return _load_seam(tmp_path_factory.mktemp("iso_align_seam"),
                      "_iso_align_seam_0930", _SEAM_FACTS, rows)


@pytest.mark.parametrize("i", range(len(SEAM_ROWS)), ids=[r[0] for r in SEAM_ROWS])
def test_seam_engine(seam_mod, i):
    assert _engine_answers(seam_mod, f"r{i}", 5) == SEAM_ROWS[i][2]
