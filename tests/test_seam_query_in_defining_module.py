"""Ruling R13 (2026-09-29): a top-level seam query of a predicate defined in
the SAME module runs while that module is still loading, before its
predicates are compiled.  Chosen: option (b), a clear located error (the
ISO term stays ``existence_error(procedure, p/1)``).  Making it work would
mean compiling the half-loaded module at the first query and again at the
end of the load.
"""
import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.predicate_diagnostics import PredicateNotFoundError


def _load(tmp_path, name, src):
    path = tmp_path / f"{name}.clausal"
    path.write_text(src)
    return _load_module(name, str(path))


@pytest.mark.parametrize("stmt, line", [
    ("xs = [X for X in --r13_p(X)]", 3),
    ("if --r13_p(1):\n    pass", 3),
])
def test_same_module_top_level_query_is_a_located_error(tmp_path, stmt, line):
    name = f"r13_same_{line}_{len(stmt)}"
    with pytest.raises(PredicateNotFoundError) as exc:
        _load(tmp_path, name, f"r13_p(1),\nr13_p(2),\n{stmt}\n")
    msg = str(exc.value)
    assert f"{name}.clausal:{line}: " in msg
    assert "still loading" in msg
    assert "r13_p/1" in msg
    assert exc.value.term[1] == (
        "existence_error", "procedure", ("/", "r13_p", 1))


def test_same_module_query_after_load_works(tmp_path):
    mod = _load(tmp_path, "r13_later",
                "r13_p(1),\nr13_p(2),\n"
                "def later():\n    return [X for X in --r13_p(X)]\n")
    assert mod.later() == [1, 2]


def test_other_module_top_level_query_works(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _load(tmp_path, "r13_owner", "r13_q(1),\nr13_q(2),\n")
    mod = _load(tmp_path, "r13_user",
                "-import_from(r13_owner, [r13_q])\n"
                "xs = [X for X in --r13_q(X)]\n")
    assert mod.xs == [1, 2]


def test_an_unknown_predicate_keeps_its_ordinary_message(tmp_path):
    with pytest.raises(Exception) as exc:
        _load(tmp_path, "r13_unknown", "xs = [X for X in --r13_nosuch(X)]\n")
    assert "still loading" not in str(exc.value)
