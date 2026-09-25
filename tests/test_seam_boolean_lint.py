"""``--goal`` read as a BOOLEAN outside goal position warns at load.

Outside goal position ``--g`` builds the cell, a non-empty tuple, so a truth
test of it is always true and the goal never runs: ``assert --edge(zzz, X)``
passes whatever ``edge/2`` holds.  ``ClausalBooleanSeamWarning`` names each
such site; goal positions and a cell used as data stay quiet.
"""
import os
import tempfile
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.lint_warnings import ClausalBooleanSeamWarning

_HEADER = (
    "-module({name}, [edge(A, B), a, b, zzz])\n"
    "-double_quotes(chars)\n"
    "edge(a, b),\n"
)


def _load(name, body):
    """Load a host module whose hosted Python is *body*; return
    ``(module, [boolean-seam warning messages])``."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}.clausal")
        with open(path, "w") as fh:
            fh.write(_HEADER.format(name=name) + body)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            module = _load_module(name, path)
    return module, [str(w.message) for w in caught
                    if issubclass(w.category, ClausalBooleanSeamWarning)]


# (id, hosted-Python body, what the always-true reading returns)
_BOOLEAN = [
    ("assert", "def f():\n    assert --edge(zzz, X)\n    return 'passed'\n",
     "passed"),
    ("if-and", "def f():\n    if --edge(zzz, X) and True:\n        return 'taken'\n"
     "    return 'not taken'\n", "taken"),
    ("or-operand", "def f():\n    return bool(False or --edge(zzz, X))\n", True),
    ("ifexp", "def f():\n    return 'yes' if --edge(zzz, X) else 'no'\n", "yes"),
    ("bool-call", "def f():\n    return bool(--edge(zzz, X))\n", True),
    ("not-outside-if", "def f():\n    return not --edge(zzz, X)\n", False),
    ("while-and", "def f():\n    n = 0\n    while --edge(zzz, X) and n < 2:\n"
     "        n += 1\n    return n\n", 2),
    ("comprehension-filter",
     "def f():\n    return [i for i in range(2) if --edge(zzz, X)]\n", [0, 1]),
]


@pytest.mark.parametrize("body, always", [c[1:] for c in _BOOLEAN],
                         ids=[c[0] for c in _BOOLEAN])
def test_a_boolean_context_warns_and_is_in_fact_always_true(body, always):
    # nv
    module, messages = _load("_bsl_warn", body)
    assert len(messages) == 1, messages
    msg = messages[0]
    assert "_bsl_warn.clausal:" in msg, msg          # names the site
    assert "--edge(zzz, X)" in msg, msg
    assert "ALWAYS TRUE" in msg, msg
    assert "if --g:" in msg and "any(True for X in --g)" in msg, msg
    # The warning is TRUE: edge(zzz, _) has no solution, yet the boolean
    # reading answers as if it had.
    assert module.f() == always


_GOAL_POSITION = [
    ("if", "def f():\n    if --edge(zzz, X):\n        return 'taken'\n"
     "    return 'not taken'\n", "not taken"),
    ("if-not", "def f():\n    if not --edge(zzz, X):\n        return 'none'\n"
     "    return 'some'\n", "none"),
    ("elif", "def f():\n    if False:\n        return 0\n"
     "    elif --edge(a, X):\n        return X\n    return None\n", "b"),
    ("while", "def f():\n    n = 0\n    while --edge(zzz, X):\n        n += 1\n"
     "    return n\n", 0),
    ("while-not", "def f():\n    n = 0\n    while not --edge(zzz, X):\n"
     "        n += 1\n        if n == 2:\n            break\n    return n\n", 2),
    ("for", "def f():\n    return [X for X in --edge(a, X)]\n", ["b"]),
    ("for-stmt", "def f():\n    out = []\n    for X in --edge(a, X):\n"
     "        out.append(X)\n    return out\n", ["b"]),
    ("any-idiom", "def f():\n    return any(True for X in --edge(zzz, X))\n",
     False),
    ("any-idiom-true", "def f():\n    return any(True for X in --edge(a, X))\n",
     True),
]


@pytest.mark.parametrize("body, answer", [c[1:] for c in _GOAL_POSITION],
                         ids=[c[0] for c in _GOAL_POSITION])
def test_goal_position_does_not_warn(body, answer):
    # nv
    module, messages = _load("_bsl_goal", body)
    assert messages == []
    assert module.f() == answer


_TERM_POSITION = [
    ("assigned", "CELL = --edge(a, b)\ndef f():\n    return CELL\n",
     ("edge", "a", "b")),
    ("local", "def f():\n    c = --edge(a, b)\n    return c\n", ("edge", "a", "b")),
    ("returned", "def f():\n    return --edge(a, b)\n", ("edge", "a", "b")),
    ("compared", "def f():\n    return --edge(a, b) == ('edge', 'a', 'b')\n", True),
    ("in-a-list", "def f():\n    return [--edge(a, b)]\n", [("edge", "a", "b")]),
    # A NAME holding a cell in a boolean context is not flagged: the lint
    # reads the `--` operand itself, not data flow.
    ("name-in-and", "def f():\n    c = --edge(a, b)\n    return bool(c and 1)\n",
     True),
]


@pytest.mark.parametrize("body, value", [c[1:] for c in _TERM_POSITION],
                         ids=[c[0] for c in _TERM_POSITION])
def test_a_cell_used_as_data_does_not_warn(body, value):
    # nv
    module, messages = _load("_bsl_term", body)
    assert messages == []
    assert module.f() == value


def test_the_warning_is_a_lint_warning():
    # nv
    from clausal.lint_warnings import ClausalLintWarning
    from clausal.templating.term_rewriting import (
        ClausalBooleanSeamWarning as reexported)
    assert issubclass(ClausalBooleanSeamWarning, ClausalLintWarning)
    assert reexported is ClausalBooleanSeamWarning


def test_each_site_warns_once_with_its_own_line():
    # nv
    body = ("def f():\n    assert --edge(zzz, X)\n"
            "def g():\n    assert --edge(a, X)\n")
    _module, messages = _load("_bsl_sites", body)
    assert len(messages) == 2, messages
    lines = sorted(m.split(".clausal:")[1].split(":")[0] for m in messages)
    assert lines == ["5", "7"], messages
