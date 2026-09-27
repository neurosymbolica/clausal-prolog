"""The OUT boundary — what a goal-position `--` hands to Python.

THE DUMB SEAM (operator GO 2026-09-26), superseding the 2026-09-21 tagged
boundary this file used to pin (`atom('x')` out, plain text for a string):

    atom     ->  the plain str          (the atom IS the str)
    string   ->  ('$chars', text)       (the carrier, unconverted)
    compound ->  the cell               (nothing inside converted)
    dict     ->  the DictTerm

No walk and no conversion: what the engine holds is what Python gets.  Text
is `to_python(T)`; a comparison is against a `--`-wrapped term.  The only
copy ever made is a SNAPSHOT of a value the engine would unbind again on
backtracking (tests/test_dumb_seam_raw_out.py::TestSnapshot).

The IN direction (`++`) keeps its meaning — a plain `str` is the atom — and
the LEAK RULE stays: an `atom` instance handed back through `++` is
normalised to a plain `str`, so no term ever holds one.
"""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import atom, is_atom
from clausal.logic.cells import chars, is_chars
from clausal.terms import DictTerm


def _load(name, source):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.seam")
    with open(p, "w") as fh:
        fh.write(source)
    return _load_module(name, p)


RB = (
    "-module({name}, [verdict(V), result(A, B, C), sp(X), txt(T), pair(K, N), dct(D)])\n"
    "-double_quotes(chars)\n"
    "-private([permitted, art_6, k])\n"
    "from clausal import to_python\n"
    "\n"
    "verdict(result(permitted, \"Article 6(1)\", art_6)),\n"
    "sp(permitted),\n"
    "txt(\"some text\"),\n"
    "pair(permitted, 1),\n"
    "pair(art_6, 2),\n"
    "dct({{k: \"text\"}}),\n"
)


class TestAnAtomComesOutAsTheStr:
    def test_a_bare_atom_answer(self):
        m = _load("_out_a", RB.format(name="_out_a") + (
            "def go():\n"
            "    for X in --sp(X):\n"
            "        return X, type(X).__name__\n"
        ))
        v, kind = m.go()
        assert v == 'permitted' and kind == 'str', kind
        assert is_atom(v) and not isinstance(v, atom), "the atom IS the plain str; no tag"

    def test_atoms_nested_in_a_compound(self):
        m = _load("_out_b", RB.format(name="_out_b") + (
            "def go():\n"
            "    for V in --verdict(V):\n"
            "        return V\n"
        ))
        v = m.go()
        assert v[0] == 'result' and type(v[1]) is str and type(v[3]) is str
        assert v[1] == 'permitted' and v[3] == 'art_6'


class TestAStringComesOutAsTheCarrier:
    def test_a_bare_string_answer(self):
        m = _load("_out_c", RB.format(name="_out_c") + (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return T, T == --\"some text\", to_python(T)\n"
        ))
        t, same, text = m.go()
        assert is_chars(t) and t == chars('some text')
        assert same is True, "a string answer IS the seam literal under -double_quotes(chars)"
        assert text == 'some text' and type(text) is str, "text is asked for by name"

    def test_a_string_nested_in_a_compound(self):
        """The class-2 failure of the 2026-09-18 flip (a carrier reaching
        sorted/dict-key code) is now the DOCUMENTED shape, not a leak: the
        answer is the cell, and the converter is one call away."""
        m = _load("_out_d", RB.format(name="_out_d") + (
            "def go():\n"
            "    for V in --verdict(V):\n"
            "        return V, V == --result(permitted, \"Article 6(1)\", art_6), to_python(V)\n"
        ))
        v, same, py = m.go()
        assert is_chars(v[2]) and same is True
        assert py == ('result', 'permitted', 'Article 6(1)', 'art_6') and type(py[2]) is str

    def test_a_dict_answer_is_the_dictterm(self):
        m = _load("_out_e", RB.format(name="_out_e") + (
            "def go():\n"
            "    for D in --dct(D):\n"
            "        return D, to_python(D)\n"
        ))
        d, py = m.go()
        assert isinstance(d, DictTerm) and is_chars(d['k'])
        assert py == {'k': 'text'} and type(py['k']) is str


class TestTheLeakRule:
    """`atom` must never reach term space, whichever door a value enters by."""

    def test_an_exported_atom_fed_back_through_the_escape_round_trips(self):
        """The local is LOWER CASE deliberately.  Written `++X` on an ALL_CAPS
        name, the escape rebinds `X` to a fresh logic variable — the hazard
        `ClausalShadowedVariableWarning` exists for — and the goal then matches
        VACUOUSLY; `pair` has two clauses so the RIGHT one is asserted."""
        m = _load("_out_f", RB.format(name="_out_f") + (
            "def go():\n"
            "    for X in --sp(X):\n"
            "        a = X\n"
            "        for N in --pair(++a, N):\n"
            "            return N, type(a).__name__\n"
            "    return None\n"
        ))
        got = m.go()
        assert got is not None, "an atom fed back through ++ did not unify with the atom it came from"
        n, kind = got
        assert n == 1 and kind == 'str'

    def test_a_string_answer_fed_back_through_the_escape_round_trips(self):
        """THE trip the tagged boundary broke (export flattened the carrier to
        a str, ++ read the str as an atom): under raw out it is identity."""
        m = _load("_out_g", RB.format(name="_out_g") + (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        t = T\n"
            "        if --txt(++t):\n"
            "            return 'round-trip'\n"
            "    return None\n"
        ))
        assert m.go() == 'round-trip'

    def test_wrap_text_normalises_an_atom_to_plain_str(self):
        from clausal.logic.to_python import wrap_text
        from clausal.lint_warnings import ClausalAtomClassDeprecationWarning
        with pytest.warns(ClausalAtomClassDeprecationWarning):   # the class is deprecated (step (f)); the strip still works
            tagged = atom('permitted')
        out = wrap_text(tagged)
        assert type(out) is str and is_atom(out)

    def test_wrap_text_leaves_a_plain_str_alone(self):
        from clausal.logic.to_python import wrap_text
        assert wrap_text('text') == 'text' and type(wrap_text('text')) is str


class TestNothingIsInvented:
    """There is no walk any more, so there are no shapes for it to get
    wrong: the reserved 1-tuple and nil cross exactly as the engine holds
    them, because everything does."""

    def test_the_boundary_walk_is_gone(self):
        import clausal.logic.seam as seam
        assert not hasattr(seam, "_to_boundary")

    def test_export_is_deref_only(self):
        from clausal.logic.seam import export
        from clausal.logic.variables import Var, Trail, unify
        v = Var()
        assert unify(v, ('c',), Trail())
        assert export(v) == ('c',) and type(export(v)[0]) is str
        w = Var()
        assert unify(w, [], Trail())
        assert export(w) == []

    def test_the_engine_itself_refuses_the_reserved_shape(self):
        from clausal.logic.cells import compound_cell_shape
        with pytest.raises(TypeError, match="reserved"):
            compound_cell_shape(('c',))
