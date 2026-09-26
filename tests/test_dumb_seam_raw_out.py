"""The dumb seam, step (c) (operator GO 2026-09-26).

(c) RAW OUT: a goal-position seam -- ``if``/``while``/``for``, a
comprehension or generator expression, ``each``/``once_bind``/``with_bases``
-- hands back the engine's INTERNAL form: an atom is the plain ``str``, a
string is the carrier ``('$chars', s)``, a dict is the ``DictTerm``, and
nothing is walked or converted unless a SNAPSHOT is needed for correctness
(a value the engine will unbind again on backtracking).  Python text is
``to_python(T)``; comparisons are against ``--``-wrapped terms.

Step (d) -- the leak rule at the doors ``wrap_text`` never sees -- is
tests/test_leak_doors.py.
"""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import atom, is_atom
from clausal.logic.cells import chars, is_chars
from clausal.terms import DictTerm, Var


def _load(name, source):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.seam")
    with open(p, "w") as fh:
        fh.write(source)
    return _load_module(name, p)


RB = (
    "-module({name}, [verdict(V), result(A, B, C), sp(X), txt(T), pair(K, N), "
    "dct(D), kv(K, V), mk(P), color(C), big(X, D)])\n"
    "-double_quotes(chars)\n"
    "-private([permitted, art_6, k, red, blue, x])\n"
    "from clausal import to_python\n"
    "\n"
    "verdict(result(permitted, \"Article 6(1)\", art_6)),\n"
    "sp(permitted),\n"
    "txt(\"some text\"),\n"
    "pair(permitted, 1),\n"
    "pair(art_6, 2),\n"
    "dct({{k: \"text\", permitted: 1}}),\n"
    "kv(permitted, \"one\"),\n"
    "kv(k, permitted),\n"
    "mk(pair(A, B)) <- (between(1, 2, A), B is A),\n"
    "color(red),\n"
    "color(blue),\n"
    "doc = [(\"row\", i, (\"cell\", \"a\", i * 2)) for i in range(20000)]\n"
    "big(x, D) <- (D is ++doc),\n"
)


def _rb(name, body):
    return _load(name, RB.format(name=name) + body)


# ── (c) the internal form comes out ─────────────────────────────────────────

class TestRawOut:
    def test_an_atom_is_the_plain_str(self):
        m = _rb("_ro_a", "def go():\n    for X in --sp(X):\n        return X\n")
        v = m.go()
        assert v == "permitted" and type(v) is str and is_atom(v)

    def test_a_string_is_the_carrier_and_compares_with_a_seam_literal(self):
        m = _rb("_ro_b", (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return T, (T == --\"some text\"), (T == \"some text\"), to_python(T)\n"
        ))
        t, eq_seam, eq_py, text = m.go()
        assert is_chars(t) and t == chars("some text")
        assert eq_seam is True, "a string answer IS the seam literal under -double_quotes(chars)"
        assert eq_py is False, "and is not a Python str -- ask to_python for text"
        assert text == "some text" and type(text) is str

    def test_a_compound_answer_is_the_cell_with_nothing_converted(self):
        m = _rb("_ro_c", "def go():\n    for V in --verdict(V):\n        return V\n")
        v = m.go()
        assert v == ("result", "permitted", chars("Article 6(1)"), "art_6")
        assert type(v[1]) is str and is_chars(v[2])

    def test_a_compound_answer_equals_its_seam_literal(self):
        m = _rb("_ro_c2", (
            "def go():\n"
            "    for V in --verdict(V):\n"
            "        return V == --result(permitted, \"Article 6(1)\", art_6)\n"
        ))
        assert m.go() is True

    def test_a_dict_answer_is_the_dictterm(self):
        m = _rb("_ro_d", "def go():\n    for D in --dct(D):\n        return D\n")
        d = m.go()
        assert isinstance(d, DictTerm)
        assert is_chars(d["k"]) and d["permitted"] == 1

    def test_if_exports_the_same_form_as_for(self):
        m = _rb("_ro_e", (
            "def go():\n"
            "    if --txt(T):\n"
            "        return T\n"
        ))
        assert is_chars(m.go())

    def test_a_dict_comprehension_and_a_generator_are_raw_too(self):
        m = _rb("_ro_f", (
            "def comp():\n"
            "    return {K: V for K, V in --kv(K, V)}\n"
            "def gen():\n"
            "    return list(X for X in --sp(X))\n"
        ))
        d = m.comp()
        assert set(d) == {"permitted", "k"} and all(type(k) is str for k in d)
        assert is_chars(d["permitted"]) and d["k"] == "permitted"
        assert m.gen() == ["permitted"]

    def test_with_bases_hands_back_the_raw_form(self, tmp_path):
        rb = tmp_path / "ro_lib.clausal"
        rb.write_text("-module(ro_lib, [txt(T)])\n-double_quotes(chars)\ntxt(\"t\"),\n")
        host = _rb("_ro_g", (
            "from clausal.import_hook import _load_module\n"
            "def go(path):\n"
            "    m = _load_module('ro_lib_alias', path)\n"
            "    for T in --m.txt(T):\n"
            "        return T\n"
        ))
        assert host.go(str(rb)) == chars("t")

    def test_the_boundary_walk_is_gone(self):
        import clausal.logic.seam as seam
        assert not hasattr(seam, "_to_boundary")


# ── (c) the snapshot rule: walk only what backtracking would unbind ─────────

class TestSnapshot:
    def test_a_for_loop_collects_stable_answers_built_from_body_variables(self):
        """mk/1 builds pair(A, B) from variables bound in the body; the engine
        unbinds them on backtracking.  What the loop collected must still read
        as the answers, not as a tuple of unbound variables."""
        m = _rb("_ss_a", (
            "def go():\n"
            "    return [P for P in --mk(P)]\n"
        ))
        got = m.go()
        assert got == [("pair", 1, 1), ("pair", 2, 2)], got
        assert all(type(x) is int for p in got for x in p[1:])

    def test_an_if_answer_built_from_body_variables_equals_its_literal(self):
        m = _rb("_ss_b", (
            "def go():\n"
            "    if --mk(P):\n"
            "        return P == --pair(1, 1)\n"
        ))
        assert m.go() is True

    def test_a_stored_ground_answer_is_not_walked(self, monkeypatch):
        """THE PERF CONTRACT: ``if --big(X, D)`` with a large DOC hands the
        stored object back untouched -- zero walks -- because nothing inside
        it was bound during the solve."""
        import clausal.logic.seam as seam
        calls = []
        real = seam._deref_walk
        monkeypatch.setattr(seam, "_deref_walk", lambda v: (calls.append(1), real(v))[1])
        m = _rb("_ss_c", (
            "def go():\n"
            "    if --big(X, D):\n"
            "        return D\n"
            "def loop():\n"
            "    return [D for X, D in --big(X, D)]\n"
        ))
        d = m.go()
        assert d is m.doc, "the stored object itself, by identity"
        assert calls == [], f"the DOC was walked {len(calls)} time(s)"
        assert m.loop()[0] is m.doc
        assert calls == []

    def test_a_body_built_answer_is_walked_exactly_when_needed(self, monkeypatch):
        import clausal.logic.seam as seam
        calls = []
        real = seam._deref_walk
        monkeypatch.setattr(seam, "_deref_walk", lambda v: (calls.append(1), real(v))[1])
        m = _rb("_ss_d", "def go():\n    if --mk(P):\n        return P\n")
        assert m.go() == ("pair", 1, 1)
        assert len(calls) == 1
