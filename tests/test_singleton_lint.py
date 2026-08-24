"""Singleton lint: a named variable occurring once per clause warns.

Exemptions: bare `_`; names suffixed `_UNUSED` (sole canonical spelling —
`_unused` is NOT exempt); files carrying -allow_singletons. Inverse lint: a
_UNUSED-suffixed name occurring MORE than once warns the other way.
"""
import warnings
import textwrap
import pytest

from clausal.import_hook import _load_module
from clausal.templating.term_rewriting import ClausalSingletonWarning


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tsl_{name}", str(path))


def _singleton_warnings(recorder):
    return [w for w in recorder if issubclass(w.category, ClausalSingletonWarning)]


def test_singleton_warns_all_caps(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "a", "p(X, Y) <- (X == 1)\n")
    msgs = [str(w.message) for w in _singleton_warnings(rec)]
    assert any("Y" in m and "singleton" in m.lower() for m in msgs)


def test_singleton_warns_underscore_style(tmp_path):
    """_x is a first-class variable style, so it is linted too (unlike
    Prolog's _X convention — see the spec's Triska-gotcha rationale)."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "b", "p(_x, _y) <- (_x == 1)\n")
    msgs = [str(w.message) for w in _singleton_warnings(rec)]
    assert any("_y" in m for m in msgs)


def test_unused_suffix_exempts(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "c", "p(X, Y_UNUSED) <- (X == 1)\n")
    assert _singleton_warnings(rec) == []


def test_lowercase_unused_is_not_exempt(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "d", "p(X, _y_unused) <- (X == 1)\n")
    assert len(_singleton_warnings(rec)) == 1


def test_join_variable_does_not_warn(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "e", "p(X) <- (q(X, N), r(N))\n"
                             "q(A, B) <- (B == A)\n"
                             "r(_n) <- (_n == 1)\n")
    assert _singleton_warnings(rec) == []


def test_inverse_lint_marked_unused_but_used(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "f", "p(X_UNUSED) <- (X_UNUSED == 1)\n")
    msgs = [str(w.message) for w in _singleton_warnings(rec)]
    assert any("more than once" in m for m in msgs)


def test_allow_singletons_directive_silences(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "g", "-allow_singletons\n"
                             "p(X, Y) <- (X == 1)\n")
    assert _singleton_warnings(rec) == []


def test_fstring_use_counts_as_occurrence(tmp_path):
    """Variables reaching a PyThunk (f-string / ++) are occurrences."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "h", 'show(X) <- ++print(X)\n')
    assert _singleton_warnings(rec) == []
