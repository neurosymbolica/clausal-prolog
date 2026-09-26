"""-module export elements: every spelling the engine accepts crosses; anything else is refused.

``_convert_module_directive`` used to recognise only a call template and a bare
name, and silently DROPPED every other element. So ``-module(m, [edge/2])``,
the ISO predicate-indicator spelling the engine accepts and pins (ruling R6b;
tests/test_clauseless_export.py ISO_PI), exported NOTHING, and the emitted
module's export list shrank without a word.
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
