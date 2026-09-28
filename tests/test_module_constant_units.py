"""`module_constant_units/4` — the declared pair, scoped to ONE module.

The module-scoped sibling of `constant_number_units/3`, and the primitive the
compile-time module insertion targets. See
docs/superpowers/specs/2026-09-12-constant-scope-design.md.

Why it has to exist: `constant_number_units/3` answers for EVERY loaded
module that declares the name, in load order. That is not a defect but a
documented compromise — a builtin never receives the calling module (the
registry hands dispatch functions their arguments and a trail, and
`_get_dispatch` is a frozen protocol with out-of-tree implementors). The
existing answer for values is `module_constant/3`; there was no sibling for
the declared PAIR, so this is it.
"""
import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tmcu_{name}", str(path))


def _rows(module, goal, arity):
    vs = [Var() for _ in range(arity)]
    return [tuple(deref(v) for v in vs) for _ in
            call(goal, *vs, module=module.__dict__["$module"])]


def test_it_answers_for_the_named_module_only(tmp_path):
    """THE test. Two modules declare one name; asking a module by name gets
    that module's pair and no other.

    The original version of this test compared against `constant_number_units/3`
    answering BOTH. That comparison is gone because the comparison target is
    gone: /3 is now compiled to this relation with the owner inserted, so a
    module that neither declares nor imports the name cannot write the call at
    all. See tests/test_constant_scope.py.
    """
    _load(tmp_path, "owner_a", """
        -module(owner_a, [fee_mc])
        -import_from(united_states, [usd])
        -constant_number_units(fee_mc, 11.00, usd)
    """)
    _load(tmp_path, "owner_b", """
        -module(owner_b, [fee_mc])
        -import_from(united_states, [usd])
        -constant_number_units(fee_mc, 22.00, usd)
    """)
    m = _load(tmp_path, "asker", """
        -module(asker, [from_a/2, from_b/2])
        -import_module(tmcu_owner_a)
        -import_module(tmcu_owner_b)
        -private([fee_mc])

        from_a(N, U) <- module_constant_units(tmcu_owner_a, fee_mc, N, U)
        from_b(N, U) <- module_constant_units(tmcu_owner_b, fee_mc, N, U)
    """)
    # The discriminator: one name, two owners, two different answers, and
    # each asked for by naming its module.
    assert [n for n, _ in _rows(m, "from_a", 2)] == [11.0]
    assert [n for n, _ in _rows(m, "from_b", 2)] == [22.0]


def test_a_name_the_module_does_not_declare_simply_fails(tmp_path):
    """The relation is a lookup, not an assertion: a module that does not
    declare the name has no pair, and that is a legitimate `no`. The RAISE
    for an undefined constant belongs at the `constant_number_units/3` call
    site, where the compiler knows the name was written as a literal."""
    _load(tmp_path, "owner_c", """
        -module(owner_c, [fee_c1])
        -import_from(united_states, [usd])
        -constant_number_units(fee_c1, 33.00, usd)
    """)
    m = _load(tmp_path, "asker_c", """
        -module(asker_c, [look/2])
        -import_module(tmcu_owner_c)
        -private([not_declared_there])

        look(N, U) <- module_constant_units(tmcu_owner_c, not_declared_there, N, U)
    """)
    assert _rows(m, "look", 2) == []


def test_it_enumerates_that_modules_pairs_with_the_name_unbound(tmp_path):
    _load(tmp_path, "owner_d", """
        -module(owner_d, [fee_d1, fee_d2])
        -import_from(united_states, [usd])
        -constant_number_units(fee_d1, 44.00, usd)
        -constant_number_units(fee_d2, 55.00, usd)
    """)
    m = _load(tmp_path, "asker_d", """
        -module(asker_d, [all/3])
        -import_module(tmcu_owner_d)

        all(C, N, U) <- module_constant_units(tmcu_owner_d, C, N, U)
    """)
    rows = _rows(m, "all", 3)
    assert sorted(n for _, n, _ in rows) == [44.0, 55.0]


def test_the_declared_unit_is_an_atom_not_the_reserved_1_tuple(tmp_path):
    """`U` is the ATOM `usd_cent` (docs/builtins.md: `U = day`) -- not the
    reserved 1-tuple `('usd_cent',)`, which is no atom and unifies with
    nothing a program writes.  A compound unit is a cell of atoms."""
    m = _load(tmp_path, "atom_unit", """
        -module(atom_unit, [look/3, fee_au, speed_au])
        -import_from(united_states, [usd_cent])
        -import_from(units, [metre, second])
        -constant_number_units(fee_au, 500, usd_cent)
        -constant_number_units(speed_au, 3, metre / second)

        look(C, N, U) <- constant_number_units(C, N, U)
    """)
    rows = _rows(m, "look", 3)
    assert ("fee_au", 500, "usd_cent") in rows
    assert ("speed_au", 3, ("/", "metre", "second")) in rows
