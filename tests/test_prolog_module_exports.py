"""-module export elements: every spelling the engine reads crosses; anything else is refused.

``_convert_module_directive`` used to recognise only a call template and a bare
name, and silently DROPPED every other element. So ``-module(m, [edge/2])``,
the ISO predicate-indicator spelling the engine accepts and pins (ruling R6b;
tests/test_clauseless_export.py ISO_PI), exported NOTHING, and the emitted
module's export list shrank without a word.

The engine also reads the QUOTED forms ``'Edge'/2`` and ``'edge'(A, B)``
(``_predicate_export_spec``): for a capital-initial predicate the quoted form
is the only spelling, because bare ``Edge`` is a variable. A quoted name
crosses as written, and only when the literal rule makes it an atom.
"""

import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

_BODY = "edge(A, B) <- (A == B)\nnode(A) <- (A == 1)\n"


def _module_line(out):
    return next(line for line in out.splitlines() if line.startswith(":- module("))


def test_the_iso_predicate_indicator_crosses():
    # nv
    out = clausal_source_to_prolog("-module(m, [edge/2])\n\n" + _BODY)
    assert _module_line(out) == ":- module(m, [edge/2])."


def test_a_call_template_crosses():
    # nv
    out = clausal_source_to_prolog("-module(m, [edge(A, B)])\n\n" + _BODY)
    assert _module_line(out) == ":- module(m, [edge/2])."


def test_both_spellings_in_one_list():
    # nv
    out = clausal_source_to_prolog("-module(m, [edge/2, node(A)])\n\n" + _BODY)
    assert _module_line(out) == ":- module(m, [edge/2, node/1])."


@pytest.mark.parametrize("element", ["edge/two", "edge/-1", "edge/2.0", "3", "'edge'", "m.edge"])
def test_an_unclassifiable_element_is_refused(element):
    # nv
    with pytest.raises(NotImplementedError, match="is not an export element"):
        clausal_source_to_prolog(f"-module(m, [{element}])\n\n" + _BODY)


def test_a_quoted_capital_initial_indicator_crosses_as_written():
    """Measured 2026-09-26: the emitted ``:- module(m, ['Edge'/2]).`` plus
    ``'Edge'(1, 10).`` imports and answers ``[1-10,2-20]`` on both Scryer and
    Trealla."""
    # nv
    out = clausal_source_to_prolog("-module(m, ['Edge'/2])\n\n'Edge'(A, B) <- (A == B)\n")
    assert _module_line(out) == ":- module(m, ['Edge'/2])."


def test_a_quoted_functor_call_template_crosses_as_written():
    # nv
    out = clausal_source_to_prolog("-module(m, ['Edge'(A, B)])\n\n'Edge'(A, B) <- (A == B)\n")
    assert _module_line(out) == ":- module(m, ['Edge'/2])."


def test_a_quoted_lowercase_name_is_the_same_atom_as_the_bare_one():
    # nv
    out = clausal_source_to_prolog("-module(m, ['edge'(A, B)])\n\n" + _BODY)
    assert _module_line(out) == ":- module(m, [edge/2])."


def test_a_double_quoted_name_is_an_atom_only_in_atom_mode():
    """The literal rule, as the engine applies it: ``"..."`` is an atom under
    the default -double_quotes(atom) and a char list under chars, where it
    names no functor and is refused like any other non-name."""
    # nv
    atom_mode = clausal_source_to_prolog(
        '-module(m, ["Edge"/2])\n\n\'Edge\'(A, B) <- (A == B)\n')
    assert _module_line(atom_mode) == ":- module(m, ['Edge'/2])."
    with pytest.raises(NotImplementedError, match="is not an export element"):
        clausal_source_to_prolog(
            '-double_quotes(chars)\n-module(m, ["Edge"/2])\n\n\'Edge\'(A, B) <- (A == B)\n')
