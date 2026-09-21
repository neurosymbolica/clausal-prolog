"""Step 2: the OUT boundary — what `--` hands to Python.

Spec: docs/superpowers/specs/2026-09-21-python-boundary-atom-and-string-design.md

    atom   ->  atom('x')   a str subclass, advisory
    string ->  'text'      a plain Python str

Step 2 changes the OUT direction only.  The IN direction (`++`) keeps today's
meaning — a plain `str` a thunk hands back is still the atom — EXCEPT that it
now normalises an `atom` instance back to a plain `str`, which is the LEAK
RULE and is tested here because step 2 is what first makes a leak possible.
"""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import atom, is_atom


def _load(name, source):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.seam")
    with open(p, "w") as fh:
        fh.write(source)
    return _load_module(name, p)


RB = (
    "-module({name}, [verdict(V), result(A, B, C), sp(X), txt(T), pair(K, N)])\n"
    "-double_quotes(chars)\n"
    "-private([permitted, art_6])\n"
    "\n"
    "verdict(result(permitted, \"Article 6(1)\", art_6)),\n"
    "sp(permitted),\n"
    "txt(\"some text\"),\n"
    "pair(permitted, 1),\n"
    "pair(art_6, 2),\n"
)


class TestAnAtomComesOutTagged:
    def test_a_bare_atom_answer(self):
        m = _load("_out_a", RB.format(name="_out_a") + (
            "def go():\n"
            "    for X in --sp(X):\n"
            "        return X, type(X).__name__\n"
        ))
        v, kind = m.go()
        assert v == 'permitted', "advisory: still equal to its text"
        assert kind == 'atom', f"expected the tag, got {kind}"
        assert isinstance(v, atom)

    def test_atoms_nested_in_a_compound(self):
        m = _load("_out_b", RB.format(name="_out_b") + (
            "def go():\n"
            "    for V in --verdict(V):\n"
            "        return V\n"
        ))
        v = m.go()
        assert v[0] == 'result'
        assert isinstance(v[1], atom) and v[1] == 'permitted'
        assert isinstance(v[3], atom) and v[3] == 'art_6'


class TestAStringComesOutAsPlainText:
    def test_a_bare_string_answer(self):
        m = _load("_out_c", RB.format(name="_out_c") + (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return T, type(T).__name__\n"
        ))
        v, kind = m.go()
        assert v == 'some text'
        assert kind == 'str', f"a string must cross as plain text, got {kind}"
        assert not isinstance(v, atom)

    def test_a_string_nested_in_a_compound(self):
        """THE CLASS-2 FAILURE, fixed at the boundary: a string used to arrive
        as the carrier tuple and land in `sorted`/dict-key code as a 2-tuple."""
        m = _load("_out_d", RB.format(name="_out_d") + (
            "def go():\n"
            "    for V in --verdict(V):\n"
            "        return V\n"
        ))
        v = m.go()
        assert v[2] == 'Article 6(1)', f"expected plain text, got {v[2]!r}"
        assert type(v[2]) is str

    def test_a_string_is_hashable_and_sorts_with_text(self):
        m = _load("_out_e", RB.format(name="_out_e") + (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return {T: 1}, sorted([T, 'a'])\n"
        ))
        d, order = m.go()
        assert d == {'some text': 1}
        assert order == ['a', 'some text']


class TestTheLeakRule:
    """`atom` must never reach term space.  Step 2 makes a leak possible for
    the first time — an exported `atom` handed straight back through `++` —
    so the normalisation and its test land together."""

    def test_an_exported_atom_fed_back_through_the_escape_does_not_leak(self):
        """The local is LOWER CASE deliberately.  Written `++X` on an ALL_CAPS
        name, the escape rebinds `X` to a fresh logic variable — the hazard
        `ClausalShadowedVariableWarning` exists for — and the goal then matches
        VACUOUSLY.  The first draft of this test did exactly that and passed
        while measuring nothing, which is why `pair` has two clauses now: a
        vacuous match would return either, so asserting the RIGHT one is what
        makes the round trip real."""
        m = _load("_out_f", RB.format(name="_out_f") + (
            "def go():\n"
            "    for X in --sp(X):\n"
            "        a = X\n"
            "        for N in --pair(++a, N):\n"
            "            return N, type(a).__name__\n"
            "    return None\n"
        ))
        got = m.go()
        assert got is not None, (
            "the round trip failed to match: an atom fed back through ++ did "
            "not unify with the atom it came from"
        )
        n, kind = got
        assert n == 1, (
            "the atom must match ITS OWN clause (1), not the other one (2) — "
            f"got {n}, which would also be what a vacuous match returns"
        )
        assert kind == 'atom', "and it was tagged on the way out"

    def test_wrap_text_normalises_an_atom_to_plain_str(self):
        """The normalisation itself, unit-level: whatever a thunk hands back,
        no `atom` instance may enter a term."""
        from clausal.logic.to_python import wrap_text
        out = wrap_text(atom('permitted'))
        assert type(out) is str, f"an atom leaked into term space as {type(out).__name__}"
        assert is_atom(out), "and it must still BE an atom once normalised"

    def test_wrap_text_leaves_a_plain_str_alone(self):
        """Step 2 does NOT change what `++` means for ordinary text — that is
        step 4.  A plain str a thunk hands back is still the atom."""
        from clausal.logic.to_python import wrap_text
        assert wrap_text('text') == 'text'
        assert type(wrap_text('text')) is str
