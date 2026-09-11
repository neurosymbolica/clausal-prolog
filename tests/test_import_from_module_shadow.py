"""`-import_from` must not bind the module NAME where a rulebase can collide.

BUG #2, documented in the corpus at `_tools/split_domain.py:1049` as a silent
import-order hazard, reproduced at engine level by corpus-lane 2026-09-11 and
diagnosed here.

`_process_imports` binds the module object under its user-facing name so that
dotted-name resolution works. That name is a Python MODULE; a bare profile key
of the same spelling is the interned ATOM `('currency',)`. Two different kinds
of thing compete for one namespace slot, which is why the shadow is SILENT
rather than a redefinition error — the lookup simply finds nothing and the
rule returns `unknown([key])`.

Only a SINGLE-SEGMENT module name can collide: it is the only form that is
also a valid Clausal identifier. A dotted path binds under a key like
`'py.units'`, which nothing can write. So the binding is kept for dotted paths
— five tests in imported-atom/functor resolution depend on it — and dropped
for the single-segment form, which is the only form that shadows.

`-import_module` is the directive that binds a module, and it still does.
"""
import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tifms_{name}", str(path))


def test_a_profile_key_survives_an_import_from_of_the_same_name(tmp_path):
    """The bug, in the shape corpus-lane hit within a minute of writing
    peppol's real data: `currency` is both a kit module and the invoice's own
    profile key."""
    m = _load(tmp_path, "shadow", """
        -module(shadow, [look/1])
        -implicit_atoms
        -import_from(currency, [currency_code])

        inv({currency: eur}),
        look(C) <- (inv(I), get(I, currency, C))
    """)
    v = Var()
    rows = [deref(v) for _ in call("look", v, module=m.__dict__["$module"])]
    assert rows == [("eur",)], rows


def test_a_single_segment_import_from_does_not_bind_the_module(tmp_path):
    """The mechanism, asserted directly: it is the BINDING that shadows, so
    the binding is what has to go."""
    import types
    m = _load(tmp_path, "nobind", """
        -module(nobind, [q/0])
        -import_from(currency, [currency_code])

        q <- (1 == 1)
    """)
    assert not isinstance(m.__dict__.get("currency"), types.ModuleType)
    assert m.__dict__.get("currency_code") is not None, (
        "the NAMED import must still arrive — this drops the module, not the "
        "names")


def test_import_module_still_binds_the_module(tmp_path):
    """The negative control, and the reason dropping the other binding is
    safe: `-import_module` is the directive that means "bind this module",
    and it is unaffected."""
    import types
    m = _load(tmp_path, "impmod", """
        -module(impmod, [q/0])
        -import_module(currency)

        q <- (1 == 1)
    """)
    assert isinstance(m.__dict__.get("currency"), types.ModuleType)


def test_a_dotted_import_from_still_binds_its_dotted_key(tmp_path):
    """The half that must NOT change: five tests in imported-atom/functor
    resolution depend on this binding, and a dotted key like `py.units` is not
    a writable Clausal identifier, so it cannot collide with anything."""
    import types
    m = _load(tmp_path, "dotted", """
        -module(dotted, [q/0])
        -import_from(py.units, [metre])

        q <- (1 == 1)
    """)
    assert isinstance(m.__dict__.get("py.units"), types.ModuleType)


def test_the_qualified_form_still_works_through_import_module(tmp_path):
    """What an author does instead, if they were relying on the incidental
    binding: say what they meant."""
    m = _load(tmp_path, "qual", """
        -module(qual, [code/1])
        -import_module(currency)
        -import_from(european_union, [euro])

        code(X) <- currency.currency_code(euro, X)
    """)
    v = Var()
    rows = [deref(v) for _ in call("code", v, module=m.__dict__["$module"])]
    assert rows == ["EUR"], rows
