"""py.jax_flax / py.jax_equinox without their library: every predicate
RAISES the ISO ``existence_error(module, flax|equinox)`` -- it used to fail,
so a query answered "no solutions" (the defect py.jax_optax had).  The
absence is simulated, so these run whether or not the library is
installed."""

from __future__ import annotations

import pytest

pytest.importorskip("jax", reason="jax not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var, deref
import clausal.modules.py as _py
from clausal.modules.py import jax_equinox, jax_flax


def _hide(monkeypatch, lib):
    real = _py._import_stdlib

    def fake(name):
        if name == lib or name.startswith(lib + "."):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real(name)
    monkeypatch.setattr(_py, "_import_stdlib", fake)


@pytest.fixture
def no_flax(monkeypatch):
    _hide(monkeypatch, "flax")
    monkeypatch.setattr(jax_flax, "_flax", None)


@pytest.fixture
def no_equinox(monkeypatch):
    _hide(monkeypatch, "equinox")
    monkeypatch.setattr(jax_equinox, "_equinox", None)


def _raised(pred, *args):
    dispatch = pred._get_dispatch()
    with pytest.raises(LogicException) as info:
        list(dispatch(None, None, None, None, *args, Trail()))
    return info.value.term


def _err(lib, name, arity):
    return ("error", ("existence_error", "module", lib), ("/", name, arity))


@pytest.mark.parametrize("pred,args", [
    (jax_flax.dense, (4,)),                     # layer constructor
    (jax_flax.dense, (4, {})),                  # other arity
    (jax_flax.layer_norm, ()),
    (jax_flax.layer_class, (Var(),)),           # fact table
])
def test_a_flax_predicate_raises_existence_error(no_flax, pred, args):
    arity = len(args) + 1
    assert _raised(pred, *args, Var()) == _err("flax", pred._name, arity)


@pytest.mark.parametrize("pred,args", [
    (jax_equinox.linear, (2, 3, Var())),        # layer constructor
    (jax_equinox.layer_class, (Var(),)),        # fact table
    (jax_equinox.is_stateful, ()),              # check predicate
])
def test_an_equinox_predicate_raises_existence_error(no_equinox, pred, args):
    arity = len(args) + 1
    assert _raised(pred, *args, Var()) == _err("equinox", pred._name, arity)


def test_the_error_is_catchable_from_a_query(no_flax, tmp_path):
    src = tmp_path / f"flax_missing_probe{SEAM_SUFFIX}"
    src.write_text(
        "-import_from(py.jax_flax, [dense])\n"
        "run(X) <- dense(4, X)\n"
        "caught(E) <- catch(dense(4, _), E, True)\n",
        encoding="utf-8")
    module = _load_module("flax_missing_probe", str(src)).__dict__["$module"]
    with pytest.raises(LogicException) as info:
        list(call("run", Var(), module=module))
    assert info.value.term == _err("flax", "dense", 2)
    e = Var()
    assert [deref(e) for _ in call("caught", e, module=module)] == [
        _err("flax", "dense", 2)]


@pytest.mark.parametrize("lib,mod,pred,args", [
    ("flax", jax_flax, "dense", (4,)),
    ("equinox", jax_equinox, "layer_class", (Var(),)),
])
def test_a_broken_install_is_not_reported_absent(monkeypatch, lib, mod,
                                                 pred, args):
    # The library is present but one of ITS dependencies is missing: not
    # existence_error(module, lib); the real import error surfaces.
    real = _py._import_stdlib

    def fake(name):
        if name == lib:
            raise ModuleNotFoundError("No module named 'chex'", name="chex")
        return real(name)
    monkeypatch.setattr(_py, "_import_stdlib", fake)
    monkeypatch.setattr(mod, f"_{lib}", None)
    p = getattr(mod, pred)
    dispatch = p._get_dispatch()
    with pytest.raises(Exception) as info:
        list(dispatch(None, None, None, None, *args, Var(), Trail()))
    assert getattr(info.value, "term", None) != _err(lib, pred, len(args) + 1)
