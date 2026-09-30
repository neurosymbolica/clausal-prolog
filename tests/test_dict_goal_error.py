"""``{}`` in goal position is the empty DICT (Python's reading), not an empty
constraint set: it reached the goal converter's ``_not_yet`` and surfaced a
raw internal ``NotImplementedError`` ("goal shape not yet supported
(DictTerm)").  It is now a load-time :class:`DictGoalError` naming the
predicate; a non-empty set of comparisons stays the CLP(Q) constraint set."""
from __future__ import annotations

import importlib
import sys

import pytest

from clausal.logic.compiler.terms_to_goalop import DictGoalError


def _load(tmp_path, monkeypatch, name, src):
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / f"{name}.seam").write_text(src, encoding="utf-8")
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        return importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize("body", [
    "{}",
    "(X is 1, {})",
    "(X is 1 or {})",
    "findall(Y, {}, X)",
])
def test_empty_dict_goal_is_a_load_error(tmp_path, monkeypatch, body):
    name = f"dict_goal_{abs(hash(body))}"
    with pytest.raises(DictGoalError) as ei:
        _load(tmp_path, monkeypatch, name, f"p(X) <- {body}\n")
    msg = str(ei.value)
    assert "`{}` is an empty dict, not a goal" in msg
    assert "p/1" in msg
    assert not isinstance(ei.value, NotImplementedError)


def test_nonempty_dict_goal_is_a_load_error(tmp_path, monkeypatch):
    with pytest.raises(DictGoalError, match="is a dict, not a goal"):
        _load(tmp_path, monkeypatch, "dict_goal_keys",
              'p(X) <- {"a": X}\n')


def test_constraint_set_goal_unchanged(tmp_path, monkeypatch):
    from clausal.logic.solve import call
    from clausal.logic.variables import Var
    mod = _load(tmp_path, monkeypatch, "dict_goal_clpq", "p(X) <- {X >= 1}\n")
    assert len(list(call(mod.p, Var()))) == 1
