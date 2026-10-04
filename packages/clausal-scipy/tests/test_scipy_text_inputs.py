"""Name arguments accept a STRING as well as an atom (spec §9.4, "text in").

The scipy adapters' dispatchers dereferenced their arguments one level and
handed them on, so a string -- the chars carrier ``('$chars', s)`` --
reached ``str(...)`` as its repr (``make_rotation/3`` method,
``rotation_as/3,4`` form and sequence, ``from_dense/3`` format,
``to_dense/3`` order), was looked up as the tuple (``lookup/4``), was
passed to scipy as a tuple (``find/2``) or was rejected by an
``isinstance(field, str)`` gate (``result_get/3``).  The probe is written
under ``-double_quotes(chars)`` so ``"..."`` IS a string; each goal has an
atom twin that answered before and must keep answering.
"""

from __future__ import annotations

import pytest

pytest.importorskip("scipy", reason="scipy not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import call


SRC = """\
-double_quotes(chars)
-import_from(scipy_spatial, [make_rotation, rotation_as])
-import_from(scipy_sparse, [from_dense, to_dense])
-import_from(scipy_constants, [lookup, find])
-import_from(scipy_stats, [stats_pearson_correlation, result_get,
                           stats_freeze_dist])
-import_from(scipy_interpolate, [make_linear1d])

rot_text() <- (make_rotation("rotvec", [0.0, 0.0, 0.0], H),
               rotation_as(H, "quat", _))
rot_atom() <- (make_rotation('rotvec', [0.0, 0.0, 0.0], H),
               rotation_as(H, 'quat', _))
euler_text() <- (make_rotation("euler", ["z", [0.0]], H),
                 rotation_as(H, "euler", "zyx", _))
sparse_text() <- (from_dense([[1.0, 0.0], [0.0, 2.0]], "csc", H),
                  to_dense(H, "C", _))
sparse_atom() <- (from_dense([[1.0, 0.0], [0.0, 2.0]], 'csc', H),
                  to_dense(H, 'C', _))
lookup_text() <- lookup("speed of light in vacuum", 299792458.0, _, _)
lookup_atom() <- lookup('speed of light in vacuum', 299792458.0, _, _)
find_text(Ns) <- find("Planck constant", Ns)
field_text() <- (stats_pearson_correlation([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], R),
                 result_get(R, "statistic", S), S > 0.99)
freeze_text() <- stats_freeze_dist("norm", {}, _)
freeze_atom() <- stats_freeze_dist('norm', {}, _)
linear_text() <- make_linear1d([0.0, 1.0, 2.0], [0.0, 2.0, 4.0], "linear", _)
linear_atom() <- make_linear1d([0.0, 1.0, 2.0], [0.0, 2.0, 4.0], 'linear', _)
field_atom() <- (stats_pearson_correlation([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], R),
                 result_get(R, 'statistic', S), S > 0.99)
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("scipytext") / f"scipy_text_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("scipy_text_probe", str(src)).__dict__["$module"]


@pytest.mark.parametrize("name", [
    "rot_text", "rot_atom", "euler_text", "sparse_text", "sparse_atom",
    "lookup_text", "lookup_atom", "field_text", "field_atom",
    "freeze_text", "freeze_atom", "linear_text", "linear_atom",
])
def test_name_argument_accepts_a_string_or_an_atom(module, name):
    assert len(list(call(name, module=module))) == 1


def test_find_takes_a_string_substring(module):
    from clausal.logic.solve import _deref_walk
    from clausal.logic.variables import Var
    ns = Var()
    [got] = [_deref_walk(ns) for _ in call("find_text", ns, module=module)]
    assert any("Planck constant" in str(n) for n in got)
