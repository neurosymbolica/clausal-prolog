"""An aliased import is REFUSED on export, not mistranslated.

`-import_from(m, [alias(g/2, gg)])` binds the local name `gg` to m's `g/2`.
ISO Prolog has no import renaming, and the ruling of 2026-09-29 is that there
is none in Clausal Prolog either: a name clash is resolved by module
qualification, `m:g(X, Y)`. The exporter used to read the alias entry as a
predicate named `alias` -- `[alias(g, gg)]` became `use_module(m, [alias/2])`,
and `[alias(g/2, gg), h]` a listless import -- so the body's `gg(...)` called
a predicate nothing defines, an existence_error at CALL time. It is now a
translation warning, and in strict mode an UntranslatableConstructError.
"""
import pytest

from clausal.tools.clausal_to_prolog import (
    UntranslatableConstructError, clausal_source_to_prolog)


@pytest.mark.parametrize("entry", ["alias(g/2, gg)", "alias(g, gg)", "alias(g(A, B), gg)"])
@pytest.mark.parametrize("kw", [{}, {"module_path": "pkg.here"}])
def test_strict_mode_refuses_an_aliased_import(entry, kw):
    src = f"-import_from(a.b, [{entry}, h])\np(X) <- (gg(X, 1), h(X))\n"
    with pytest.raises(UntranslatableConstructError, match="m:p"):
        clausal_source_to_prolog(src, strict=True, **kw)


def test_the_alias_is_never_read_as_a_predicate_named_alias():
    out = clausal_source_to_prolog("-import_from(a.b, [alias(g, gg)])\np(X) <- (gg(X, 1))\n")
    assert "alias/2" not in out
    assert "WARNING" in out and "alias(g, gg)" in out


def test_an_ordinary_import_list_is_unaffected():
    out = clausal_source_to_prolog("-import_from(a.b, [g/2])\np(X) <- (g(X, 1))\n",
                                   strict=True)
    assert "use_module('a/b', [g/2])" in out
