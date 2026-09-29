"""D35's interop half: the truth atoms are Python's ``True``/``False``/
``Undefined`` to the engine, and they LEAVE the engine as those objects --
never as the str of their spelling -- at every boundary that hands a term to
Python: ``to_python``, the ``++``/f-string ``unwrap_atom``, the ``py.*``
wrapper argument conversion, JSON generation, tabling variant keys.

``spelling(True)`` is ``"true"`` (atom_length/2 wants it); ``crossing_value``
is what the boundary uses instead.  Pinned because widening ``is_atom`` to
the truth objects turned every ``spelling(x) if is_atom(x) else x`` boundary
site into a str converter (caught in review, 2026-09-30).
"""
from __future__ import annotations

from clausal.logic.atoms import crossing_value
from clausal.logic.to_python import to_python, unwrap_atom
from clausal.logic.tabling import _normalize_for_key_py
from clausal.terms import Undefined

TRUTH = [True, False, Undefined]


def test_crossing_value_hands_back_the_object():
    for obj in TRUTH:
        assert crossing_value(obj) is obj
    assert crossing_value("foo") == "foo"


def test_to_python_and_unwrap_atom_keep_the_objects():
    for obj in TRUTH:
        assert to_python(obj) is obj
        assert unwrap_atom(obj) is obj
    assert to_python([True, ("f", Undefined)])[0] is True
    assert unwrap_atom("foo") == "foo"


def test_json_generation_keeps_the_booleans():
    from clausal.modules.py.json import _clausal_to_python
    assert _clausal_to_python(True, "generate/2") is True
    assert _clausal_to_python(False, "generate/2") is False
    assert _clausal_to_python({"k": True}, "generate/2") == {"k": True}
    import json
    assert json.dumps(_clausal_to_python([True, False], "generate/2")) == "[true, false]"


def test_py_wrapper_argument_conversion_keeps_the_objects():
    from clausal.modules.py import to_text as conv
    for obj in TRUTH:
        assert conv(obj) is obj


def test_tabling_keys_one_atom_one_variant():
    # the object and its str spelling are ONE atom: one variant key
    assert _normalize_for_key_py(True) == _normalize_for_key_py("true") == "true"
    assert _normalize_for_key_py(False) == "false"
    assert _normalize_for_key_py(True) != _normalize_for_key_py(1)
    try:
        from clausal.logic._tabling_core import _normalize_for_key as c_key
    except ImportError:   # pure-Python build
        return
    for t in (True, False, 1, 0, "true", 1.0):
        assert c_key(t) == _normalize_for_key_py(t), t
