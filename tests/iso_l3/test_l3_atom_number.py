"""atom_number/2 did not exist (existence_error(procedure, atom_number/2)).
Neither the reference Scryer build nor Trealla's binary here has it, so the
rows pin the documented semantics: the atom is read as a Prolog number token
(no layout, a ``-`` directly before it), non-number text fails, and the
reverse mode writes the number as number_codes/2 does."""
from __future__ import annotations

SRC = """\
n1(L) :- atom_number('12', L).
n2(L) :- atom_number('12.5', L).
n3(L) :- atom_number(' 12', L).
n4(L) :- atom_number('12 ', L).
n5(L) :- atom_number('-12', L).
n6(L) :- atom_number('- 12', L).
n7(L) :- atom_number('0x1A', L).
n8(L) :- atom_number('0''a', L).
n9(L) :- atom_number(abc, L).
n10(L) :- atom_number(L, 12).
n11(L) :- atom_number(L, 1.5).
n12(E) :- catch(atom_number(_, _), E, true).
n13(E) :- catch(atom_number(12, _), E, true).
n14(E) :- catch(atom_number(_, a), E, true).
n15(L) :- atom_number('12', 12), L = y.
n16(L) :- atom_number('1e10', L).
n17(L) :- atom_number('1.0e10', L).
n19(L) :- atom_number('', L).
n20(L) :- atom_number(L, -3).
n21(L) :- atom_number('12', 13), L = y.
n22(L) :- atom_number('0b101', L).
n23(L) :- atom_number('0o17', L).
n24(L) :- atom_number('-0x1A', L).
n25(L) :- atom_number('0''\\n', L).
n26(N) :- X is 10.0**22, atom_number(A, X), atom_number(A, N).
n27(A) :- X is 10.0**22, atom_number(A, X).
"""


def _err(formal):
    return ("error", formal, ("/", "atom_number", 2))


def test_atom_number(native, ans):
    mod = native.load("l3_atom_number", SRC)
    want = {
        "n1": [12], "n2": [12.5], "n3": [], "n4": [], "n5": [-12], "n6": [],
        "n7": [26], "n8": [97], "n9": [], "n10": ["12"], "n11": ["1.5"],
        "n12": [_err("instantiation_error")],
        "n13": [_err(("type_error", "atom", 12))],
        "n14": [_err(("type_error", "number", "a"))],
        "n15": ["y"], "n16": [], "n17": [1.0e10], "n19": [], "n20": ["-3"],
        "n21": [], "n22": [5], "n23": [15], "n24": [-26], "n25": [10],
        "n26": [1.0e22], "n27": ["1.0e+22"],
    }
    for name, expected in want.items():
        assert ans(mod, name) == expected, name


def test_atom_number_beyond_the_int_str_digit_limit():
    """A 5000-digit integer reads and writes (CPython caps int/str
    conversion at ~4300 digits; it escaped as a bare ValueError)."""
    from clausal.logic.database import Module
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var, deref
    m = Module("an_big")
    n = 7 * 10 ** 4999 + 3
    text = "7" + "0" * 4998 + "3"
    v = Var()
    assert [deref(v) for _ in solve(("atom_number", text, v), m)] == [n]
    a = Var()
    assert [deref(a) for _ in solve(("atom_number", a, n), m)] == [text]
