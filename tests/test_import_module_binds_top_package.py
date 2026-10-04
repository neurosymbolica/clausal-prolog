"""``-import_module(a.b)`` binds ``a`` to the top-level PACKAGE.

It bound ``a`` to the LEAF module ``a.b`` (``compiler_v2._process_imports``),
so a dotted reference walked from the wrong object: after
``-import_module(py.re)``, the term ``py.re.match`` -- a closure handed to
``call/N`` or ``maplist/N`` -- raised ``AttributeError: module
'clausal.modules.py.re' has no attribute 're'``.  A body call
``py.re.match(...)`` was unaffected (its resolution falls back to
``sys.modules``), which is why it went unseen.  Python's own ``import a.b``
binds ``a`` to the package; so does this now.
"""
from __future__ import annotations

import pytest

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-import_module(py.re)
-import_module(py.os)

closure() <- call(py.re.match, "a", "abc")
closure_maplist() <- maplist(py.re.match("a"), ["abc", "abd"])
closure_other(X) <- call(py.os.platform, X)
body() <- py.re.match("a", "abc")
"""


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    src = tmp_path_factory.mktemp("imp_top") / f"imp_top_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("imp_top_probe", str(src))


def test_the_top_name_is_the_package(loaded):
    import clausal.modules.py as pkg
    assert loaded.__dict__["py"] is pkg


def test_a_dotted_closure_runs(loaded):
    m = loaded.__dict__["$module"]
    assert len(list(call("closure", module=m))) == 1
    assert len(list(call("closure_maplist", module=m))) == 1
    x = Var()
    import sys
    assert [_deref_walk(x) for _ in call("closure_other", x, module=m)] == [
        sys.platform]


def test_the_body_call_is_unchanged(loaded):
    assert len(list(call("body", module=loaded.__dict__["$module"]))) == 1
