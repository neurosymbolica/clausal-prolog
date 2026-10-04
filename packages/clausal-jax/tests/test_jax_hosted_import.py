"""Reaching the REAL ``jax`` module from a .seam file: a hosted Python
``import jax as pyjax`` at module level (ruled 2026-10-04, instead of
widening py.jax's forwarding).

In a seam file ``-import_module(jax)`` / ``-import_from(jax, ...)`` name the
py.jax ADAPTER (the bare-name alias), which forwards only JAX submodules and
classes, so ``++jax.vmap(...)`` cannot reach JAX's function through it --
on purpose: ``-import_from(jax, [grad])`` must not bind JAX's ``grad``.  A
hosted ``import`` is ordinary Python, binds the library under its own
name, and every ``++`` escape (and a qualified call) sees it."""

from __future__ import annotations

import pytest

pytest.importorskip("jax", reason="jax not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
import jax as pyjax
-import_module(jax)
-import_from(jax, [array, array_list])

adapter_name(N) <- (N is ++jax.__name__)
raw_name(N) <- (N is ++pyjax.__name__)
vmapped(L) <- (
    F is ++pyjax.vmap(lambda v: v * 2),
    array([1.0, 2.0], A),
    R is ++F(A),
    array_list(R, L)
)
qualified_call(L) <- (
    R is pyjax.numpy.arange(3),
    array_list(R, L)
)
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("jaxhost") / f"jax_hosted_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("jax_hosted_probe", str(src)).__dict__["$module"]


def _one(module, name):
    x = Var()
    got = [_deref_walk(x) for _ in call(name, x, module=module)]
    assert len(got) == 1, got
    return got[0]


def test_the_bare_name_is_the_adapter_and_the_hosted_import_is_jax(module):
    assert _one(module, "adapter_name") == "clausal.modules.py.jax"
    assert _one(module, "raw_name") == "jax"


def test_a_jax_function_is_reachable_from_an_escape(module):
    assert _one(module, "vmapped") == [2.0, 4.0]


def test_a_qualified_call_reaches_it_too(module):
    assert _one(module, "qualified_call") == [0, 1, 2]
