"""Term-position ``--m.pred(...)`` / ``--m.name``: the dotted reference.

``seam.seam_term``'s ``dotted()`` walked a ``LoadAttr`` chain through the
attribute ``.value`` -- ``AttrNode`` has ``.object`` -- so EVERY term-position
seam whose functor or name was written with a dot raised ``AttributeError:
'LoadAttr' object has no attribute 'value'`` (found by the 2026-09-26 design
review's cross-module probe).  ``with_bases`` (goal position) reads
``attr.object`` and never hit it.
"""
import textwrap

from clausal.import_hook import _load_module
from tests._suffix import SEAM


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(name, str(path))


def _lib(tmp_path):
    return _load(tmp_path, "tsd_lib", """
        -module(tsd_lib, [pt(X, Y), red])
        -double_quotes(chars)
        pt(1, 2)
    """)


def test_a_dotted_functor_in_term_position_builds_the_cell(tmp_path):
    _lib(tmp_path)
    host = _load(tmp_path, "tsd_host_f", """
        -module(tsd_host_f, [])
        -import_module(tsd_lib)

        def go():
            return --tsd_lib.pt(1, 2)
    """)
    got = host.go()
    assert type(got) is tuple and got[1:] == (1, 2), got
    assert type(got[0]) is str and got[0].endswith("pt"), got


def test_a_dotted_atom_in_term_position_is_the_atom(tmp_path):
    _lib(tmp_path)
    host = _load(tmp_path, "tsd_host_a", """
        -module(tsd_host_a, [])
        -import_module(tsd_lib)

        def go():
            return --tsd_lib.red
    """)
    got = host.go()
    assert got == "red" and type(got) is str, got


def test_the_dotted_term_agrees_with_the_goal_position_answer(tmp_path):
    """The term a caller BUILDS with ``--m.pt(1, 2)`` is the term the goal
    ``--m.pt(X, Y)`` answers with -- one cell, both doors."""
    _lib(tmp_path)
    host = _load(tmp_path, "tsd_host_g", """
        -module(tsd_host_g, [])
        -import_module(tsd_lib)

        def built():
            return --tsd_lib.pt(1, 2)

        def answered():
            for X, Y in --tsd_lib.pt(X, Y):
                return (X, Y)
    """)
    assert host.built()[1:] == host.answered()
