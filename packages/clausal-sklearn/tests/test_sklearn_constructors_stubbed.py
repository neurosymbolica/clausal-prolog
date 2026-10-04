"""The term constructors are lower_snake_case: ``est``, ``dataset``,
``fitted``, ``split`` -- and so are the tags of the terms they build.

They were ``Est``/``Dataset``/``Fitted``/``Split`` building
``("Est", algo, params)`` ...; TitleCase has no role in Clausal positions
(the identifier lint), so they are renamed with no aliases, and the tags
with them: ``est(svc, {})`` written in a clause IS the term the adapter
builds and reads.

Runs WITHOUT scikit-learn (``*_stubbed.py``, see packages/conftest.py):
every ``.seam`` fixture of the package is LOADED, and the cases that need
no scikit-learn (the algorithm registry, ``param/3`` over an ``est``
term) are RUN; ``split_data/3`` and ``fit/3`` run against fakes on the
adapter's cached submodules.  Everything else in the fixtures needs real
scikit-learn and is not run here.
"""

from __future__ import annotations

import glob
import os
import types

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import sklearn as sk

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_SEAMS = sorted(glob.glob(os.path.join(_FIXTURES, "**", "*.seam"), recursive=True))


def test_constructors_are_lowercase_with_no_titlecase_aliases():
    assert sk.est("svc") == ("est", "svc", {})
    assert sk.dataset([[0]], [1]) == ("dataset", [[0]], [1])
    assert sk.fitted(sk.est("pca"), 3) == ("fitted", ("est", "pca", {}), 3)
    assert sk.split("tr", "te") == ("split", "tr", "te")
    for old in ("Est", "Dataset", "Fitted", "Split"):
        assert not hasattr(sk, old), old


@pytest.mark.parametrize("path", _SEAMS, ids=os.path.basename)
def test_fixture_loads(path):
    name = "sk_ctor_" + os.path.splitext(os.path.basename(path))[0]
    src = open(path, encoding="utf-8").read()
    for old in ("Est", "Dataset", "Fitted", "Split"):
        assert f'"{old}"' not in src and f"{old}(" not in src, (path, old)
    assert _load_module(name, path).__dict__["$module"] is not None


@pytest.fixture(scope="module")
def basic():
    path = os.path.join(_FIXTURES, "sklearn_basic.seam")
    return _load_module("sk_ctor_run_basic", path).__dict__["$module"]


@pytest.mark.parametrize("case", [
    "algorithm random_forest is classifier",
    "algorithm pca is transformer",
    "algorithm kmeans is clusterer",
    "param from est term",
])
def test_sklearn_free_fixture_cases_run(basic, case):
    # the fixture keeps -double_quotes(atom): test names are atoms
    assert any(True for _ in call("test", case, module=basic)), case


def test_split_and_fit_build_lowercase_tagged_terms(monkeypatch):
    class _Model:
        def __init__(self, **kw):
            self.kw = kw

        def fit(self, x, y):
            return self

    def train_test_split(x, y, test_size):
        return x[:1], x[1:], y[:1], y[1:]

    monkeypatch.setattr(sk, "_sk", types.SimpleNamespace())
    monkeypatch.setattr(sk, "_sk_model_selection",
                        types.SimpleNamespace(train_test_split=train_test_split))
    monkeypatch.setattr(sk, "_get_sklearn_class", lambda algo: _Model)

    out = Var()
    list(sk._split_data_3(sk.dataset([[0], [1]], [0, 1]), 0.5, out, Trail(), None))
    tag, train, test = deref(out)
    assert (tag, train[0], test[0]) == ("split", "dataset", "dataset")

    out = Var()
    list(sk._fit_3(sk.est("svc", {}), train, out, Trail(), None))
    tag, inner, _handle = deref(out)
    assert (tag, inner[0]) == ("fitted", "est")
