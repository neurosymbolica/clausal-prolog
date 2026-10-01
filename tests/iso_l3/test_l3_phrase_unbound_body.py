"""phrase/2,3 with an unbound grammar body raise instantiation_error, as ISO
and Scryer do (measured: all three goals below give instantiation_error).
They used to FAIL silently, so a variable grammar body ``v(B) --> B.``
called with B unbound answered "no" instead of raising."""
from __future__ import annotations

import pytest

SRC = """\
t1(R) :- catch(findall(L, phrase(_, L), R), error(E, _), R = E).
t2(R) :- catch(findall(L, phrase(_, L, []), R), error(E, _), R = E).
t3(R) :- catch(findall(L, phrase(lists:_, L), R), error(E, _), R = E).
"""


@pytest.mark.parametrize("goal", ["t1", "t2", "t3"])
def test_phrase_with_an_unbound_body_is_an_instantiation_error(native, ans,
                                                               goal):
    mod = native.load("l3_phrase_unbound", SRC)
    assert ans(mod, goal) == ["instantiation_error"]
