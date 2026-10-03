"""py.jax_optax without optax installed: every predicate RAISES the ISO
``existence_error(module, optax)`` (it used to fail, so a query answered
"no solutions").  optax's absence is simulated, so these run whether or not
it is installed."""

from __future__ import annotations

import pytest

pytest.importorskip("jax", reason="jax not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var, deref
import clausal.modules.py as _py
from clausal.modules.py import jax_optax


@pytest.fixture
def no_optax(monkeypatch):
    real = _py._import_stdlib

    def fake(name):
        if name == "optax" or name.startswith("optax."):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real(name)
    monkeypatch.setattr(_py, "_import_stdlib", fake)
    monkeypatch.setattr(jax_optax, "_optax", None)


def _raised(pred, arity, *args):
    dispatch = pred._get_dispatch()
    with pytest.raises(LogicException) as info:
        list(dispatch(None, None, None, None, *args, Trail()))
    return info.value.term


def _err(name, arity):
    return ("error", ("existence_error", "module", "optax"), ("/", name, arity))


@pytest.mark.parametrize("pred,args", [
    (jax_optax.adam, (0.1,)),                    # optimiser constructor
    (jax_optax.adam, (0.1, {})),                 # other arity
    (jax_optax.scale_by_adam, ()),
    (jax_optax.linear_schedule, (1.0, 0.0, 10)),
    (jax_optax.l2_loss, (1.0, 2.0)),
    (jax_optax.optimizer, ("adam",)),            # fact table
])
def test_a_predicate_raises_existence_error_without_optax(no_optax, pred, args):
    arity = len(args) + 1
    assert _raised(pred, arity, *args, Var()) == _err(pred._name, arity)


def test_the_error_is_catchable_from_a_query(no_optax, tmp_path):
    src = tmp_path / f"optax_missing_probe{SEAM_SUFFIX}"
    src.write_text(
        "-import_from(py.jax_optax, [adam])\n"
        "run(X) <- adam(0.1, X)\n"
        "caught(E) <- catch(adam(0.1, _), E, True)\n",
        encoding="utf-8")
    mod = _load_module("optax_missing_probe", str(src))
    module = mod.__dict__["$module"]
    with pytest.raises(LogicException) as info:
        list(call("run", Var(), module=module))
    assert info.value.term == _err("adam", 2)
    e = Var()
    got = [deref(e) for _ in call("caught", e, module=module)]
    assert got == [_err("adam", 2)]


def test_a_broken_optax_install_is_not_reported_absent(monkeypatch):
    # optax present but one of ITS dependencies missing: not
    # existence_error(module, optax); the real import error surfaces.
    real = _py._import_stdlib

    def fake(name):
        if name == "optax":
            raise ModuleNotFoundError("No module named 'chex'", name="chex")
        return real(name)
    monkeypatch.setattr(_py, "_import_stdlib", fake)
    monkeypatch.setattr(jax_optax, "_optax", None)
    term = _raised(jax_optax.adam, 2, 0.1, Var())
    assert term != _err("adam", 2)
