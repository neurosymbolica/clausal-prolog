"""listing/1 on an ISO-surface module (``.pl``, Clausal Prolog) prints what
Scryer's ``listing/1`` prints, byte for byte (operator ruling 2026-09-25, "do
what Scryer does"): Scryer's ``portray_clause/1`` layout -- variables
``A``, ``B``, ... with their sharing, operator syntax, quoted atoms,
``"..."`` strings, a rule's goals one per line at three spaces, if-then-else
and disjunction laid out as Scryer lays them out -- and nothing else: no
header line (Scryer prints none, ``:- dynamic`` included).

Each program is listed by Clausal (in process, on every ISO surface it
loads on) and by Scryer (with library(format), which defines its
``listing/1``); both must print the pinned text.  The cut / if-then-else
program is ``.pl`` only: ``.clausal`` refuses those constructs.

One known writer difference is kept out of the programs: Scryer writes an
alphanumeric infix operator before a prefix-operator operand without layout
(``C is-A``), Clausal's writeq with it (``C is -A``) --
todo/writeq-alphanumeric-operator-layout-differs-from-scryer-2026-11-04.md.
"""
from __future__ import annotations

from itertools import count

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
from clausal._suffixes import PROLOG_SUFFIX as PL
from clausal.import_hook import _load_module
from clausal.logic.solve import solve

from tests._oracles import run_scryer

CLAUSAL = CLAUSAL_PROLOG_SUFFIXES[0]

#: Facts and rules over every term shape the writer has a rule for.
TERMS_PROGRAM = ':- dynamic(f/1).\n:- dynamic(r/2).\n:- dynamic(a/0).\nf(x).\nf(\'hello world\').\nf(\'don\'\'t\').\nf("a\\nb").\nf("").\nf([]).\nf(\'[]\').\nf({}).\nf({a,b}).\nf([a,b|c]).\nf([1|_]).\nf([X,Y|X]-Y).\nf(- 1).\nf(-(1)).\nf(-(-(1))).\nf(1 - -1).\nf(- a).\nf(-(-(a))).\nf(-1.5).\nf(1.0e10).\nf(1.5e-10).\nf(0.1).\nf(123456789012345678901234567890).\nf(-0).\nf(\'A\').\nf(\'$VAR\'(1)).\nf(\'a b\'(c)).\nf((a,b)).\nf((:-)).\nf(f(;)).\nf(- (-)).\nf(a:b:c).\nf((a:-b)).\nf(1+2*3-(4-5)).\nf(2**3+2^3^4).\nf(\\+a).\nf(f(A,B,A,_,B)).\nf([a|"bc"]).\nf(\'\\n\').\nf(f(\',\', \'|\', \'[]\', \'{}\', !, ;)).\nr(X, Y) :- X = Y.\nr(X, Y) :- X = f(Y), r(Y, X), X == Y.\nr(X, _) :- \\+ X = 1, \\+ \\+ X = 2, \\+ (X = 3, X = 4).\nr(X, Y) :- ( X = 1 ; X = 2 ), Y = {X}.\nr(X, Y) :- ( X = 1 ; X = 2 ; X = Y ).\nr(X, Y) :- ( (X = 1 ; X = 2) ; X = 3 ), Y = X.\nr(X, Y) :- (X = 1, Y = 2 ; X = 2, Y = 1).\nr(X, Y) :- X = 1, (Y = 2, X = Y), Y = 3.\nr(X, Y) :- Y is X * 2 + 3 mod 2 - (-1), Z is X - 1, Z =:= -1.5e-10.\nr(X, Y) :- X @< Y, X =.. [_|Y], atom_length(X, 3), X \\== Y.\nr(X, Y) :- r(X, "abc"), r(Y, [a|"bc"]), r(\'A\', \'b c\').\nr(_, _) :- true.\nr(_, _) :- fail.\nr(_, _) :- false.\nr(X, Y) :- call(X), Y.\na :- true.\na.\n'

TERMS_SHOW = "show :- listing(f/1), listing(r/2), listing(a/0).\n"

TERMS_EXPECTED = 'f(x).\nf(\'hello world\').\nf(\'don\\\'t\').\nf("a\\nb").\nf([]).\nf([]).\nf([]).\nf({}).\nf({a,b}).\nf([a,b|c]).\nf([1|A]).\nf([A,B|A]-B).\nf(-1).\nf(- (1)).\nf(- - (1)).\nf(1- -1).\nf(-a).\nf(- -a).\nf(-1.5).\nf(10000000000.0).\nf(1.5e-10).\nf(0.1).\nf(123456789012345678901234567890).\nf(0).\nf(\'A\').\nf(\'$VAR\'(1)).\nf(\'a b\'(c)).\nf((a,b)).\nf(:-).\nf(f(;)).\nf(- (-)).\nf(a:b:c).\nf((a:-b)).\nf(1+2*3-(4-5)).\nf(2**3+2^3^4).\nf(\\+a).\nf(f(A,B,A,C,B)).\nf("abc").\nf(\'\\n\').\nf(f(\',\',\'|\',[],{},!,;)).\nr(A,B) :-\n   A=B.\nr(A,B) :-\n   A=f(B),\n   r(B,A),\n   A==B.\nr(A,B) :-\n   \\+A=1,\n   \\+ \\+A=2,\n   \\+ (A=3,A=4).\nr(A,B) :-\n   (  A=1\n   ;  A=2\n   ),\n   B={A}.\nr(A,B) :-\n   (  A=1\n   ;  A=2\n   ;  A=B\n   ).\nr(A,B) :-\n   (  (  A=1\n      ;  A=2\n      )\n   ;  A=3\n   ),\n   B=A.\nr(A,B) :-\n   (  A=1,\n      B=2\n   ;  A=2,\n      B=1\n   ).\nr(A,B) :-\n   A=1,\n   B=2,\n   A=B,\n   B=3.\nr(A,B) :-\n   B is A*2+3 mod 2- -1,\n   C is A-1,\n   C=:= -1.5e-10.\nr(A,B) :-\n   A@<B,\n   A=..[C|B],\n   atom_length(A,3),\n   A\\==B.\nr(A,B) :-\n   r(A,"abc"),\n   r(B,"abc"),\n   r(\'A\',\'b c\').\nr(A,B).\nr(A,B) :-\n   fail.\nr(A,B) :-\n   false.\nr(A,B) :-\n   call(A),\n   call(B).\na.\na.\n'

#: Cut and if-then-else (``.pl`` only).
CUT_PROGRAM = ':- dynamic(c/2).\nc(X, Y) :- X > 0, !, Y = pos.\nc(X, Y) :- ( X > 0 -> Y = pos ; X < 0 -> Y = neg ; Y = zero ).\nc(X, Y) :- ( X > 0 -> Y = pos ; true ), !.\nc(X, Y) :- ( X > 0 -> Y = pos ).\nc(X, Y) :- ( (X > 0 -> Y = a ; Y = b) -> true ; fail ).\nc(X, Y) :- ( X > 0, Y = 1 -> X = 2, Y = 3 ; X = 4 ; X = 5 ).\nc(X, Y) :- ( X = 1 ; X = 2 -> Y = 3 ; Y = 4 ).\nc(X, Y) :- \\+ ( X = 1 -> Y = 2 ; true ).\nc(_, _) :- !.\n'

CUT_SHOW = "show :- listing(c/2).\n"

CUT_EXPECTED = 'c(A,B) :-\n   A>0,\n   !,\n   B=pos.\nc(A,B) :-\n   (  A>0 ->\n      B=pos\n   ;  A<0 ->\n      B=neg\n   ;  B=zero\n   ).\nc(A,B) :-\n   (  A>0 ->\n      B=pos\n   ;  true\n   ),\n   !.\nc(A,B) :-\n   (A>0->B=pos).\nc(A,B) :-\n   (  (  A>0 ->\n         B=a\n      ;  B=b\n      ) ->\n      true\n   ;  fail\n   ).\nc(A,B) :-\n   (  A>0,\n      B=1 ->\n      A=2,\n      B=3\n   ;  A=4\n   ;  A=5\n   ).\nc(A,B) :-\n   (  A=1\n   ;  A=2 ->\n      B=3\n   ;  B=4\n   ).\nc(A,B) :-\n   \\+ (A=1->B=2;true).\nc(A,B) :-\n   !.\n'

PROGRAMS = {
    "terms": (TERMS_PROGRAM + TERMS_SHOW, TERMS_EXPECTED, (PL, CLAUSAL)),
    "cut": (CUT_PROGRAM + CUT_SHOW, CUT_EXPECTED, (PL,)),
}

ENGINE_ROWS = [(name, suffix) for name, (_p, _e, suffixes) in PROGRAMS.items()
               for suffix in suffixes]

_COUNTER = count()


def _diff(got: str, expected: str) -> str:
    import difflib  # noqa: PLC0415
    return "\n".join(difflib.unified_diff(
        expected.splitlines(), got.splitlines(), "expected", "got",
        lineterm=""))


@pytest.mark.parametrize("name,suffix", ENGINE_ROWS,
                         ids=[f"{n}-{s.lstrip('.')}" for n, s in ENGINE_ROWS])
def test_listing_iso_engine(tmp_path, capsys, monkeypatch, name, suffix):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    program, expected, _ = PROGRAMS[name]
    stem = f"_listing_iso_{next(_COUNTER)}"
    path = tmp_path / f"{stem}{suffix}"
    path.write_text(program, encoding="utf-8")
    mod = _load_module(stem, str(path))
    capsys.readouterr()
    for _ in solve("show", mod):
        pass
    got = capsys.readouterr().out
    assert got == expected, _diff(got, expected)


@pytest.mark.parametrize("name", list(PROGRAMS))
def test_listing_iso_scryer(scryer, tmp_path, name):
    del scryer
    program, expected, _ = PROGRAMS[name]
    prelude = tmp_path / "format.pl"
    prelude.write_text(":- use_module(library(format)).\n", encoding="utf-8")
    path = tmp_path / "program.pl"
    path.write_text(program, encoding="utf-8")
    proc = run_scryer([str(prelude), str(path)], ["show, halt."], timeout=60)
    got = "".join(line + "\n" for line in proc.stdout.splitlines()
                  if not line.startswith("% Warning"))
    assert got == expected, (_diff(got, expected), proc.stderr[-500:])
