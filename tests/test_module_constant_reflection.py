"""module_constant/3: reflect on a module's OWN -constants declarations.

Registration happens in the -constants lowering itself
(EmbedTransformer._handle_constants_directive -> $register_module_constant,
clausal/logic/constants.py) — see tests/test_constants.py for the
declaration/folding side. This file covers the reflection builtin's modes
and the imported-constants-are-NOT-reflected-on-the-importer decision.
"""
import textwrap
import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tmc_{name}", str(path))


def test_lookup_module_and_name_bound(tmp_path):
    _load(tmp_path, "owner1", "-constants(c_pi = 3.14159)\n")
    m = _load(tmp_path, "user1", """
        -import_module(tmc_owner1)
        got(X) <- module_constant(tmc_owner1, "c_pi", X)
    """)
    v = Var()
    assert [deref(v) for _ in call("got", v, module=m.__dict__["$module"])] == \
        [3.14159]


def test_lookup_missing_name_fails(tmp_path):
    _load(tmp_path, "owner2", "-constants(c_pi = 3.14159)\n")
    m = _load(tmp_path, "user2", """
        -import_module(tmc_owner2)
        got(X) <- module_constant(tmc_owner2, "c_nope", X)
    """)
    v = Var()
    assert list(call("got", v, module=m.__dict__["$module"])) == []


def test_check_mode_true_and_false(tmp_path):
    _load(tmp_path, "owner3", "-constants(c_a = 1)\n")
    m = _load(tmp_path, "user3", """
        -import_module(tmc_owner3)
        ok <- module_constant(tmc_owner3, "c_a", 1)
        bad <- module_constant(tmc_owner3, "c_a", 2)
    """)
    module = m.__dict__["$module"]
    assert list(call("ok", module=module))
    assert list(call("bad", module=module)) == []


def test_enumerate_a_modules_constants(tmp_path):
    """(+Module, -Name, ?Value): enumerate."""
    _load(tmp_path, "owner4", "-constants(c_a = 1, c_b = 2)\n")
    m = _load(tmp_path, "user4", """
        -import_module(tmc_owner4)
        got(N, V) <- module_constant(tmc_owner4, N, V)
    """)
    n, v = Var(), Var()
    results = sorted(
        (deref(n), deref(v))
        for _ in call("got", n, v, module=m.__dict__["$module"])
    )
    # THE FLIP (spec §6.4): the NAME position answers ATOMS.
    assert results == [(mint("c_a"), 1), (mint("c_b"), 2)]


def test_module_unbound_enumerates_across_loaded_modules(tmp_path):
    """(-Module, +Name, ?Value): the module argument need not be imported —
    module_constant/3 searches every loaded Clausal module."""
    owner = _load(tmp_path, "owner5", "-constants(c_unique5 = 777)\n")
    m = _load(tmp_path, "user5", """
        find(M, V) <- module_constant(M, "c_unique5", V)
    """)
    mv, vv = Var(), Var()
    results = [(deref(mv), deref(vv))
              for _ in call("find", mv, vv, module=m.__dict__["$module"])]
    assert len(results) == 1
    mod, val = results[0]
    assert mod is owner
    assert val == 777


def test_imported_constant_is_not_reflected_on_the_importer(tmp_path):
    """Decision (2026-08-25): module_constant/3 only reflects a module's
    OWN -constants declarations. An imported constant is reachable through
    its owning module's own module_constant/3, not re-registered on the
    importer — see docs/import.md."""
    _load(tmp_path, "owner6", "-constants(c_pi = 3.14159)\n")
    m = _load(tmp_path, "user6", """
        -import_from(tmc_owner6, [c_pi])
        p(X) <- (X is c_pi)
    """)
    assert m.__dict__["$module"].constants == {}


def test_qualified_import_module_constant_also_not_reflected_on_importer(tmp_path):
    _load(tmp_path, "owner7", "-constants(c_pi = 3.14159)\n")
    m = _load(tmp_path, "user7", """
        -import_module(tmc_owner7)
        p(X) <- (X is ++(tmc_owner7.c_pi + 0))
    """)
    assert m.__dict__["$module"].constants == {}


def test_reflected_value_is_the_same_frozen_object(tmp_path):
    """The value module_constant/3 yields is the identical object the
    owning module's own clause bodies embed — not a copy."""
    m = _load(tmp_path, "owner8", "-constants(c_l = [1, 2, 3])\n")
    v = Var()
    [result] = [deref(v) for _
                in call("module_constant", m, mint("c_l"), v,
                        module=m.__dict__["$module"])]
    assert result is m.__dict__["c_l"]
