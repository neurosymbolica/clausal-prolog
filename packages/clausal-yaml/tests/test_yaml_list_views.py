"""The rest of a long list reaches yaml's get/3 as a list.

Matching ``[_|Rest]`` against a list of 64 or more elements binds ``Rest`` to
a list view (``terms.SegListView``), not a Python ``list``.  get/3 took a path
that was not a list as ONE key, so a long path held as a view silently failed.
The package adapters read their arguments through ``terms.plain_deref``, as
the engine's own Python-backed modules do (operator ruling 2026-10-13,
extending D38 and 2026-10-12).
"""
from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_SRC = """\
-import_from(yaml, [get])

get_rest(DATA, [_, *REST], R) <- get(DATA, REST, R)
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("yaml_views") / "yaml_views.seam"
    p.write_text(_SRC)
    return load_clausal_module(p)


@pytest.mark.parametrize("n", [30, 100])
def test_get_follows_the_rest_of_a_long_path(mod, n):
    data = "leaf"
    for _ in range(n):
        data = [data]
    r = Var()       # the rule takes PATH apart: its rest is a view when long
    assert next(solve(("get_rest", data, [0] * (n + 1), r), mod), None) is not None
    assert deref(r) == "leaf"
