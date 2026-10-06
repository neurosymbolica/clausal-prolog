"""``to_python`` on a dataclass whose ``__init__`` is its own.

``to_python`` rebuilds a dataclass term as ``type(**fields)``, which only the
generated ``__init__`` accepts.  An Equinox module is such a dataclass
(``eqx.nn.Linear(in_features, out_features, key=...)`` stores ``weight`` and
``bias``), so passing one through a py adapter raised
``TypeError: Linear.__init__() got an unexpected keyword argument 'weight'``
(packages/clausal-jax, every equinox fixture test).
"""
from __future__ import annotations

import dataclasses

from clausal.logic.to_python import to_python
from clausal.logic.variables import Trail, Var, unify


@dataclasses.dataclass
class Layer:
    """Fields ``size`` and ``shape``; the constructor takes neither."""
    size: int
    shape: tuple

    def __init__(self, n):
        self.size = n
        self.shape = (n, n)


@dataclasses.dataclass(frozen=True)
class FrozenLayer:
    size: object

    def __init__(self, n):
        object.__setattr__(self, "size", n)


def test_no_var_inside_crosses_without_calling_init():
    layer = Layer(3)
    out = to_python(layer)
    assert type(out) is Layer and out.size == 3 and out.shape == (3, 3)


def test_atomic_fields_only_cross_as_the_same_object():
    layer = FrozenLayer(3)
    assert to_python(layer) is layer


def test_changed_fields_are_set_on_a_copy_of_the_same_class():
    layer = Layer(3)
    v = Var()
    unify(v, 7, Trail())
    layer.size = v                      # a bound Var inside the object
    out = to_python(layer)
    assert type(out) is Layer and out is not layer
    assert out.size == 7 and out.shape == (3, 3)
    assert layer.size is v              # the original is untouched


def test_frozen_dataclass_with_own_init():
    v = Var()
    unify(v, "x", Trail())
    out = to_python(FrozenLayer(v))
    assert type(out) is FrozenLayer and out.size == "x"


def test_generated_init_still_rebuilds():
    @dataclasses.dataclass
    class Point:
        x: object
        y: int

    v = Var()
    unify(v, 1, Trail())
    out = to_python(Point(v, 2))
    assert out == Point(1, 2)
