"""Smoke tests verifying the package is installable and discoverable."""

from __future__ import annotations


def test_python_imports():
    """The Python public surface is importable."""
    from clausal.modules.provenance import (
        boolean,
        evaluate,
        query,
        bottom_up_,
        pure_,
        solve,
        recover,
        Provenance,
        AggregateProvenance,
        Boolean,
        PurityError,
        NonGroundTupleError,
        StratificationError,
    )
    # Smoke: each public symbol has the right type
    assert isinstance(boolean, Boolean)
    assert callable(evaluate)
    assert callable(query)


def test_boolean_semiring_algebra():
    from clausal.modules.provenance import boolean
    assert boolean.zero() is False
    assert boolean.one() is True
    assert boolean.add(False, True) is True
    assert boolean.add(True, True) is True
    assert boolean.add(False, False) is False
    assert boolean.mult(True, True) is True
    assert boolean.mult(True, False) is False
    assert boolean.negate(True) is False
    assert boolean.negate(False) is True


def test_clausal_import_from_works(tmp_path):
    """`-import_from(provenance, [...])` resolves from .clausal source."""
    from clausal.import_hook import _load_module
    src = (
        "-import_from(provenance, [bottom_up_, pure_, solve, boolean])\n"
        "-module(smoke, [Foo(X)])\n"
    )
    p = tmp_path / "smoke.clausal"
    p.write_text(src)
    mod = _load_module("smoke", str(p))
    # All four names are in the loaded module's namespace.
    assert hasattr(mod, "bottom_up_")
    assert hasattr(mod, "pure_")
    assert hasattr(mod, "solve")
    assert hasattr(mod, "boolean")
