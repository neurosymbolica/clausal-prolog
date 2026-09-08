"""Every ISO canonical builtin must register a 2-ARITY term class.

A builtin's registered FIELDS are its term class's fields, and the class is
the term CONSTRUCTOR — so the translator, the seam (`--'=:='(X, 1)`) and the
reified-term tooling all read the arity from here. Measured 2026-09-09 before
the fix:

    _BUILTIN_FIELDS[('=:=', 2)] == ('a', 'b', 'trail', 'k')
    get_builtin_class('=:=')    -> <Predicate =:=/4, ...>
    p(R) <- (T is '=:='(1, 2), functor(T, N, AR), R is AR)   -> 4
    controls: '#=' -> 2, structural_eq -> 2

All six arithmetic comparisons were affected. The cause was the
closure-capture DEFAULTS in `_arith_cmp`'s inner signature
(`def _cmp(a, b, trail, k, _op=op, _name=name)`): `_registry.
_extract_fields_simple` strips exactly the last two parameters, so the extra
defaults pushed `trail`/`k` into the field tuple.

The check LOOPS over every name the module registers, discovered from the
registry rather than listed here, so a name added later is covered without
anyone remembering to extend a list.
"""
import pytest

import clausal.logic.builtins.iso_compare as iso_compare
from clausal.logic.builtins import _registry


def _owner_module(dispatch_fn):
    """The module of the simple-mode function behind a registered dispatch.

    `_registry._builtin` stores `_simple_to_trampoline(fn)`, a wrapper defined
    in `_registry`, so `__module__` on the stored object names the registry.
    The wrapped function is the wrapper's single closure cell.
    """
    for cell in (dispatch_fn.__closure__ or ()):
        contents = cell.cell_contents
        if callable(contents) and getattr(contents, "__module__", None):
            return contents.__module__
    return getattr(dispatch_fn, "__module__", None)


ISO_KEYS = sorted(
    key for key, fn in _registry._BUILTINS.items()
    if _owner_module(fn) == iso_compare.__name__)


def test_the_discovery_actually_found_the_iso_builtins():
    """A positive control: an empty discovery would make every parametrized
    check below vacuous and the file would still read green."""
    names = {name for name, _arity in ISO_KEYS}
    assert len(ISO_KEYS) >= 17, ISO_KEYS
    # The families the branch registers, spelled out so a silent LOSS of a
    # name is caught as well as a silent gain.
    for expected in ("=:=", "=\\=", "<", ">", "=<", ">=",
                     "is", "=", "\\=", "==", "\\==",
                     "#=", "#\\=", "#<", "#>", "#=<", "#>="):
        assert expected in names, (expected, sorted(names))


@pytest.mark.parametrize("key", ISO_KEYS, ids=[f"{n}/{a}" for n, a in ISO_KEYS])
def test_registered_fields_match_the_declared_arity(key):
    name, arity = key
    fields = _registry._BUILTIN_FIELDS[key]
    assert len(fields) == arity, (
        f"{name}/{arity} registered {len(fields)} fields {fields}: the term "
        f"class is the term constructor, so this IS the functor's arity")
    assert "trail" not in fields and "k" not in fields, (name, fields)


@pytest.mark.parametrize("key", ISO_KEYS, ids=[f"{n}/{a}" for n, a in ISO_KEYS])
def test_the_builtin_class_has_the_declared_arity(key):
    name, arity = key
    cls = _registry.get_builtin_class(name)
    assert cls is not None, name
    # `_arity`/`_fields` are what `PredicateMeta` reports and what its repr
    # (`<Predicate =:=/4 ...>`) is built from — the arity every consumer of
    # the term constructor sees.
    assert cls._arity == arity, (name, repr(cls))
    assert len(cls._fields) == arity, (name, cls._fields)


def test_the_arithmetic_comparison_term_has_arity_two_at_runtime(run_clausal):
    """The end-to-end shape: `functor/3` on a constructed `'=:='` term.
    Answered 4 before the fix."""
    src = ("-module(_hN, [p(R), n])\n-double_quotes(chars)\n"
           "p(R) <- (T is '=:='(1, 2), functor(T, N_UNUSED, AR), R is AR)\n")
    assert run_clausal(src, ("p",)) == ["2"]


def test_the_control_predicates_still_have_arity_two(run_clausal):
    """The controls from the original probe: `'#='` and `structural_eq` were
    never affected, so they must read 2 both before and after."""
    for goal in ("'#='(1, 2)", "structural_eq(1, 2)"):
        src = ("-module(_hN, [p(R)])\n-double_quotes(chars)\n"
               f"p(R) <- (T is {goal}, functor(T, N_UNUSED, AR), R is AR)\n")
        assert run_clausal(src, ("p",)) == ["2"], goal
