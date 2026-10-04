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


# ── a dotted .seam module, and the leaf fallback ──

def test_a_dotted_seam_module_binds_its_package(tmp_path, monkeypatch):
    import importlib
    import sys
    pkg = tmp_path / "imp_top_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / f"lib{SEAM_SUFFIX}").write_text("p(1),\np(2)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    src = tmp_path / f"imp_top_user{SEAM_SUFFIX}"
    src.write_text(
        "-import_module(imp_top_pkg.lib)\n"
        "body(X) <- imp_top_pkg.lib.p(X)\n"
        "closure(X) <- call(imp_top_pkg.lib.p, X)\n", encoding="utf-8")
    try:
        loaded = _load_module("imp_top_user", str(src))
        assert loaded.__dict__["imp_top_pkg"] is sys.modules["imp_top_pkg"]
        m = loaded.__dict__["$module"]
        for name in ("body", "closure"):
            x = Var()
            assert [_deref_walk(x) for _ in call(name, x, module=m)] == [1, 2]
    finally:
        for k in ("imp_top_pkg", "imp_top_pkg.lib", "imp_top_user"):
            sys.modules.pop(k, None)


def test_a_leaf_whose_name_does_not_walk_keeps_the_old_binding():
    import types
    from clausal.logic.compiler_v2 import _top_package_of
    leaf = types.ModuleType("nowhere_pkg_xyz.leaf")       # parent not loaded
    assert _top_package_of(leaf, ["a", "leaf"]) is leaf
    assert _top_package_of(leaf, ["leaf"]) is leaf
    import clausal.modules.py as pkg
    import clausal.modules.py.re as re_mod
    assert _top_package_of(re_mod, ["py", "re"]) is pkg
