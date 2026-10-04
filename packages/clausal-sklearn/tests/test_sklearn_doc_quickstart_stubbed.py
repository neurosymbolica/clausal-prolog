"""The quick-start in ``docs/sklearn.md`` runs as written.

It destructured the dataset with ``D is ("dataset", X, Y)``.  Without
``-double_quotes(atom)`` that ``"dataset"`` is a STRING, the chars carrier
``('$chars', 'dataset')``, while the adapter tags its terms with the ATOM
``dataset`` -- so the ``is`` failed and the documented predicate answered
nothing.  The doc now writes the quoted atom ``'dataset'``.

The block is read out of the doc itself, so the doc and this test cannot
drift apart.  Runs WITHOUT scikit-learn (``*_stubbed.py``, see
packages/conftest.py): the adapter's cached submodules are fakes.
"""

from __future__ import annotations

import os
import re
import types

import pytest

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var
from clausal.modules.py import sklearn as sk

_DOC = os.path.join(os.path.dirname(__file__), os.pardir, "docs", "sklearn.md")


def _quickstart_block():
    text = open(_DOC, encoding="utf-8").read()
    blocks = re.findall(r"```clausal\n(.*?)```", text, re.S)
    block = next(b for b in blocks if "train_and_predict" in b)
    # no -double_quotes directive: a "..." in it is a string (the default)
    assert "double_quotes" not in block
    return block


def test_quoted_atom_tag_is_the_tag_dataset_builds(tmp_path):
    # ('dataset', X, Y) written in a clause IS what dataset(X, Y) builds
    src = tmp_path / f"sk_tag_probe{SEAM_SUFFIX}"
    src.write_text("tagged(T) <- (T is ('dataset', 1, 2))\n", encoding="utf-8")
    mod = _load_module("sk_tag_probe", str(src)).__dict__["$module"]
    t = Var()
    assert any(True for _ in call("tagged", t, module=mod))
    assert _deref_walk(t) == sk.dataset(1, 2)


@pytest.fixture
def fake_sklearn(monkeypatch):
    class _Bunch:
        data = [[0.0], [1.0], [2.0]]
        target = [0, 1, 1]

    class _Model:
        def __init__(self, **kw):
            self.kw = kw

        def fit(self, x, y):
            self.y = list(y)
            return self

        def predict(self, x):
            return [len(row) for row in x]

    seen = []

    def _cls(algo):
        seen.append(algo)
        return _Model

    monkeypatch.setattr(sk, "_sk", types.SimpleNamespace())
    monkeypatch.setattr(sk, "_sk_datasets",
                        types.SimpleNamespace(load_iris=lambda: _Bunch()))
    monkeypatch.setattr(sk, "_get_sklearn_class", _cls)
    return seen


def test_quickstart_runs_as_documented(tmp_path, fake_sklearn):
    src = tmp_path / f"sk_quickstart{SEAM_SUFFIX}"
    src.write_text(_quickstart_block(), encoding="utf-8")
    mod = _load_module("sk_quickstart", str(src)).__dict__["$module"]
    preds = Var()
    answers = [_deref_walk(preds)
               for _ in call("train_and_predict", "random_forest", "iris",
                             preds, module=mod)]
    assert fake_sklearn == ["random_forest"]
    assert len(answers) == 1 and list(answers[0]) == [1, 1, 1]
