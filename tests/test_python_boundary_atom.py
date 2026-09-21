"""``atom`` — an atom at the Python boundary, ADVISORY form.

Spec: docs/superpowers/specs/2026-09-21-python-boundary-atom-and-string-design.md

Step 1 of the implementation: the class alone.  Nothing converts to or from it
yet, so this file pins the class's own behaviour, the DISCRIMINATOR that later
steps read, and the LEAK RULE they depend on.

Lower case by operator ruling: a Python class at the same level as ``str``.
"""
import pytest

from clausal.logic.atoms import atom, is_atom


class TestItIsAdvisory:
    """``==`` is text equality.  Ruled 2026-09-21: the discriminator is the
    TYPE, not equality, so equality is left alone."""

    def test_equal_to_the_text_it_tags(self):
        assert atom('a') == 'a'
        assert 'a' == atom('a')
        assert atom('a') == atom('a')

    def test_not_equal_to_different_text(self):
        assert atom('a') != 'b'
        assert 'b' != atom('a')

    def test_a_strict_class_would_have_broken_these(self):
        """Why advisory, pinned as a fact rather than left in a comment: a
        downstream body comparing an answer to a plain string literal is the
        overwhelmingly common idiom — 1007 such comparisons across all 82
        downstream bodies — and every atom-side one would silently flip True
        to False under a strict ``__eq__``.  A comparison that quietly changes
        its answer is the defect class this boundary exists to remove."""
        verdict = atom('permitted')
        assert verdict == 'permitted'
        assert verdict in ('permitted', 'refused')
        assert {'permitted': 1}[verdict] == 1


class TestTheDiscriminator:
    """What ``++`` will read. This is the whole mechanism."""

    def test_type_tells_atom_from_text(self):
        assert isinstance(atom('a'), atom)
        assert not isinstance('a', atom)
        assert type(atom('a')) is atom
        assert type('a') is str

    def test_equality_does_NOT_tell_them_apart(self):
        """Stated as a test so nobody later 'fixes' it."""
        assert atom('a') == 'a'
        assert not (type(atom('a')) is type('a'))


class TestIdentityAndHashing:
    def test_interned(self):
        assert atom('a') is atom('a')

    def test_hashes_and_keys_as_text(self):
        """The counterpart of advisory equality: an atom and its text are ONE
        dict key, not two.  Deliberate — a split key space is what made a
        downstream failure silent in the first place."""
        assert hash(atom('a')) == hash('a')
        assert len({atom('a'): 1, 'a': 2}) == 1
        assert len({atom('a'), 'a'}) == 1


class TestItIsStillTextShaped:
    def test_string_operations(self):
        assert atom('ab').upper() == 'AB'
        assert '-'.join(atom('ab')) == 'a-b'
        assert f"{atom('ab')}" == 'ab'
        assert len(atom('ab')) == 2

    def test_isinstance_str_is_true(self):
        assert isinstance(atom('a'), str)

    def test_sorts_with_plain_strings_by_text(self):
        """Ruled: mixing by text is accepted.  Standard order of terms belongs
        on the Clausal side and comes back as a list, so the boundary is not
        asked to separate them."""
        assert sorted([atom('b'), 'a', atom('c')]) == ['a', 'b', 'c']


class TestTheTagIsFragileAndThatIsNotAdvisorysFault:
    """The tag survives being STORED and MOVED; it is lost by anything that
    builds a NEW string.  Pinned because a caller must know it, and because a
    STRICT class would lose it in exactly the same places — the fragility is a
    property of subclassing ``str``, not a cost of being advisory."""

    @pytest.mark.parametrize("move", [
        lambda a: {'k': a}['k'],
        lambda a: [a][0],
        lambda a: (a,)[0],
        lambda a: sorted([a])[0],
        lambda a: (lambda x: x)(a),
        lambda a: next(iter({a: 1})),
    ])
    def test_survives_storage_and_movement(self, move):
        assert type(move(atom('a'))) is atom

    @pytest.mark.parametrize("transform", [
        lambda a: a.upper(),
        lambda a: a[:],
        lambda a: f"{a}",
        lambda a: ''.join([a]),
        lambda a: a + '',
        lambda a: str(a),
    ])
    def test_lost_by_transformation(self, transform):
        assert type(transform(atom('a'))) is str


class TestTheLeakRule:
    """``atom`` lives ONLY at the boundary.  ``++`` will normalise it to a
    plain ``str`` on the way in, and no term may hold one.

    ``is_atom`` is ``type(term) is str``, so it answers False for an ``atom``
    — and that is what makes a leak detectable rather than silent.  A class
    named ``atom`` for which ``is_atom`` is False reads oddly on purpose:
    ``is_atom`` asks whether a TERM is an atom, and this is not a term."""

    def test_type_is_str_is_false(self):
        assert type(atom('a')) is not str

    def test_is_atom_refuses_it(self):
        assert is_atom(atom('a')) is False
        assert is_atom('a') is True
