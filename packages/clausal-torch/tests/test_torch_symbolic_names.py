"""A tensor's device crosses as an ATOM ("atom out, text in", ruled
2026-10-04); a bound device may be the atom or the text."""

from __future__ import annotations

import pytest

pytest.importorskip("torch", reason="torch not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-double_quotes(chars)
-import_from(torch, [zeros, device])

dev(D) <- (zeros([2], T), device(T, D))
dev_atom() <- (zeros([2], T), device(T, 'cpu'))
dev_text() <- (zeros([2], T), device(T, "cpu"))
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("torchsym") / f"torch_symbolic_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("torch_symbolic_probe", str(src)).__dict__["$module"]


def test_device_is_an_atom(module):
    d = Var()
    [got] = [_deref_walk(d) for _ in call("dev", d, module=module)]
    assert got == "cpu" and type(got) is str


@pytest.mark.parametrize("name", ["dev_atom", "dev_text"])
def test_device_check_mode_accepts_atom_and_text(module, name):
    assert len(list(call(name, module=module))) == 1
