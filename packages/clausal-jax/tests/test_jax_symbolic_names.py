"""Symbolic names clausal-jax hands back cross as ATOMS ("atom out, text
in", ruled 2026-10-04): a device platform, a device name, mesh axis names,
a PartitionSpec's axis names.  A bound argument may be the atom or the
text.  keystr/2 is a printed representation and stays text."""

from __future__ import annotations

import pytest

pytest.importorskip("jax", reason="jax not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-double_quotes(chars)
-import_from(jax, [zeros, device, null])
-import_from(jax_tree, [keystr])
-import_from(jax_sharding, [jax_device, device_platform, make_mesh,
                            mesh_axis_names, partition_spec])

platform(P) <- (jax_device(D), device_platform(D, P))
platform_atom() <- (jax_device(D), device_platform(D, 'cpu'))
platform_text() <- (jax_device(D), device_platform(D, "cpu"))
dev(N) <- (zeros([2], A), device(A, N))
axes(NAMES) <- (make_mesh([1], ['x'], M), mesh_axis_names(M, NAMES))
axes_from_text(NAMES) <- (make_mesh([1], ["x"], M), mesh_axis_names(M, NAMES))
spec_back(AXES) <- (partition_spec(['x', null], P), partition_spec(AXES, P))
spec_back_text(AXES) <- (partition_spec(["x"], P), partition_spec(AXES, P))
spec_multi(AXES) <- (partition_spec([['x', 'y']], P), partition_spec(AXES, P))
spec_check_text() <- (partition_spec(['x'], P), partition_spec(["x"], P))
key(S) <- keystr((), S)
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("jaxsym") / f"jax_symbolic_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("jax_symbolic_probe", str(src)).__dict__["$module"]


def _one(module, name):
    x = Var()
    got = [_deref_walk(x) for _ in call(name, x, module=module)]
    assert len(got) == 1, got
    return got[0]


def _holds(module, name):
    return len(list(call(name, module=module))) >= 1


def test_device_platform_is_an_atom(module):
    p = _one(module, "platform")
    assert p == "cpu" and type(p) is str


def test_device_platform_check_mode_accepts_atom_and_text(module):
    assert _holds(module, "platform_atom")
    assert _holds(module, "platform_text")


def test_device_name_is_an_atom(module):
    n = _one(module, "dev")
    assert type(n) is str and n          # e.g. 'cpu:0' / 'TFRT_CPU_0'


@pytest.mark.parametrize("name", ["axes", "axes_from_text"])
def test_mesh_axis_names_is_a_list_of_atoms(module, name):
    assert _one(module, name) == ["x"]


def test_partition_spec_backward_gives_atoms(module):
    assert _one(module, "spec_back") == ["x", None]
    assert _one(module, "spec_back_text") == ["x"]


def test_a_multi_axis_entry_is_a_list_of_atoms(module):
    assert _one(module, "spec_multi") == [["x", "y"]]


def test_partition_spec_check_mode_accepts_text(module):
    assert _holds(module, "spec_check_text")


def test_keystr_stays_text(module):
    assert _one(module, "key") == chars("")
