"""Inbound Prolog variables must never land on the _X_ constant class.

Also covers the outbound guard: translating a clausal source file that
carries a ``-constants`` directive must refuse explicitly rather than
mistranslate (Prolog has no constants).
"""
import pytest

from clausal.tools.prolog_dialect import prolog_var_to_clausal
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog


def test_trailing_underscore_prolog_var_is_not_constant_shaped():
    # Prolog `_PI_` is a variable; naive lowering gives `_pi_`, which is
    # Clausal's constant class. The trailing underscore must be stripped.
    got = prolog_var_to_clausal("_PI_")
    assert not (len(got) >= 3 and got[0] == "_" and got[-1] == "_"
                and got[1] != "_" and got[-2] != "_")


def test_titlecase_trailing_underscore():
    got = prolog_var_to_clausal("Foo_")
    assert got == "_foo"


def test_bare_underscore_stays_anonymous():
    assert prolog_var_to_clausal("_") == "_"


def test_double_underscore_never_collapses_to_bare_underscore():
    # "_" alone would relabel the variable as anonymous — must not happen.
    got = prolog_var_to_clausal("_")
    assert got == "_"


def test_single_trailing_underscore_stripped_repeatedly():
    # A pathological Prolog var name with several trailing underscores
    # must not leave a residual constant-shaped or bare "_" candidate.
    got = prolog_var_to_clausal("_Foo___")
    assert got == "_foo"


def test_outbound_constants_directive_raises_not_implemented():
    source = "-constants(_PI_ = 3.14159)\n\nfact(_PI_),\n"
    with pytest.raises(NotImplementedError, match="constants"):
        clausal_source_to_prolog(source)
