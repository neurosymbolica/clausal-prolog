"""Text arguments accept a STRING as well as an atom (spec §9.4, "text in").

The adapter read algorithm names, metric names, paths, dataset names,
attribute and parameter keys with ``str(deref(x))``, so a string -- the
chars carrier ``('$chars', s)`` -- reached scikit-learn (or joblib, or a
registry lookup) as the repr ``"('$chars', 's')"``; parameter values and
data were handed over dereferenced one level, so a string inside them was
a Python tuple.

Runs WITHOUT scikit-learn (``*_stubbed.py``, see packages/conftest.py):
the adapter imports sklearn and joblib lazily, so fakes on the adapter's
cached submodule globals and in ``sys.modules['joblib']`` record exactly
what the adapter hands the library.
"""

from __future__ import annotations

import sys
import types

import pytest

from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import sklearn as sk
from clausal.terms import DictTerm


class _Model:
    """A fake estimator class: records its kwargs and what it was fit on."""
    made = []

    def __init__(self, **kw):
        self.kw = kw
        self.fit_args = None
        _Model.made.append(self)

    def get_params(self):
        return {"C": 1.0, "kernel": "linear"}

    def fit(self, x, y):
        self.fit_args = (x, y)
        return self


@pytest.fixture
def fake(monkeypatch):
    _Model.made = []
    seen = {}

    def accuracy_score(y_true, y_pred):
        seen["metric"] = (y_true, y_pred)
        return 1.0

    def normalize(x, norm):
        seen["norm"] = norm
        return x

    monkeypatch.setattr(sk, "_sk", types.SimpleNamespace())
    monkeypatch.setattr(sk, "_sk_metrics",
                        types.SimpleNamespace(accuracy_score=accuracy_score))
    monkeypatch.setattr(sk, "_sk_model_selection",
                        types.SimpleNamespace(LeaveOneOut=lambda: "LOO"))
    monkeypatch.setattr(sk, "_sk_preprocessing",
                        types.SimpleNamespace(normalize=normalize))
    monkeypatch.setattr(sk, "_get_sklearn_class",
                        lambda algo: seen.setdefault("class_for", algo) and _Model)

    joblib = types.SimpleNamespace(
        dump=lambda model, path: seen.setdefault("dump", path),
        load=lambda path: seen.setdefault("load", path) and _Model())
    monkeypatch.setitem(sys.modules, "joblib", joblib)
    return seen


def _simple(fn, *args):
    return list(fn(*args, Trail(), None))


def _nondet(fn, *args):
    proceed, fail = object(), object()
    return [s for s in fn(None, proceed, fail, None, *args, Trail())
            if s[0] is proceed]


def test_metric_name_and_labels_may_be_strings(fake):
    s = Var()
    _simple(sk._metric_4, chars("accuracy"),
            [chars("cat"), "dog"], [chars("cat"), chars("dog")], s)
    assert deref(s) == 1.0
    assert fake["metric"] == (["cat", "dog"], ["cat", "dog"])


def test_make_est_reads_text_algorithm_and_keys(fake):
    e = Var()
    _simple(sk._make_est_3, chars("svc"),
            DictTerm({chars("kernel"): chars("rbf")}), e)
    assert fake["class_for"] == "svc"
    tag, algo, params = deref(e)
    assert (tag, algo) == ("Est", "svc")
    # The key is its text; the VALUE handed back is the term as given.
    assert params["kernel"] == chars("rbf")


def test_fit_hands_sklearn_plain_strings(fake):
    est = sk.Est(chars("svc"), DictTerm({chars("kernel"): chars("rbf")}))
    data = sk.Dataset([[0.0], [1.0]], [chars("no"), chars("yes")])
    _simple(sk._fit_3, est, data, Var())
    [model] = _Model.made
    assert model.kw == {"kernel": "rbf"}
    assert model.fit_args == ([[0.0], [1.0]], ["no", "yes"])


@pytest.mark.parametrize("name", [chars("svc"), "svc"])
def test_algorithm_check_mode_accepts_text(name):
    assert len(_nondet(sk._algorithm_2, name, "classifier")) == 1


def test_cv_strategy_name_may_be_a_string(fake):
    assert sk._make_cv(chars("loo")) == "LOO"


def test_normalize_norm_may_be_a_string(fake):
    _simple(sk._normalize_3, [[1.0]], chars("l2"), Var())
    assert fake["norm"] == "l2"


def test_save_and_load_fitted_take_a_text_path(fake):
    handle = sk._register_model(_Model())
    fitted = sk.Fitted(sk.Est("svc", {}), handle)
    _simple(sk._save_fitted_2, fitted, chars("/tmp/m.joblib"))
    _simple(sk._load_fitted_2, chars("/tmp/m.joblib"), Var())
    assert fake["dump"] == "/tmp/m.joblib" and fake["load"] == "/tmp/m.joblib"


def test_a_compound_path_is_a_type_error(fake):
    with pytest.raises(LogicException) as info:
        _simple(sk._load_fitted_2, ("f", 1), Var())
    assert info.value.term[1][:2] == ("type_error", "text")
