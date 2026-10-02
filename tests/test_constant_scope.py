"""Constants resolve lexically — declared here, imported here, or owner-named.

See docs/superpowers/specs/2026-09-12-constant-scope-design.md.

The mechanism is COMPILE-TIME MODULE INSERTION. A builtin never receives the
calling module, so `constant_number_units/3` answered for every loaded module
that declared the name, in load order -- a documented compromise, not a
defect. But the COMPILER knows the module, and already hands `$module` to
`$register_constant_units` when a declaration is lowered. Reading now works
the way writing does.
"""
import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tcs_{name}", str(path))


def _rows(module, goal, arity):
    vs = [Var() for _ in range(arity)]
    return [tuple(deref(v) for v in vs) for _ in
            call(goal, *vs, module=module.__dict__["$module"])]


def _two_owners(tmp_path):
    _load(tmp_path, "own_a", """
        -module(own_a, [fee_s])
        -import_from(united_states, [usd])
        -constant_number_units(fee_s, 11.00, usd)
    """)
    _load(tmp_path, "own_b", """
        -module(own_b, [fee_s])
        -import_from(united_states, [usd])
        -constant_number_units(fee_s, 22.00, usd)
    """)


def test_a_module_gets_its_OWN_declaration_only(tmp_path):
    """THE test. Two modules declare `fee_s`; the one asking gets its own,
    once. Before the fix it got both, in load order."""
    _two_owners(tmp_path)
    m = _load(tmp_path, "selfask", """
        -module(selfask, [look/2, fee_s])
        -import_from(united_states, [usd])
        -constant_number_units(fee_s, 33.00, usd)

        look(N, U) <- constant_number_units(fee_s, N, U)
    """)
    assert [n for n, _ in _rows(m, "look", 2)] == [33.0]


def test_an_IMPORTED_constant_answers_slash_3(tmp_path):
    """Fails today: importing carries the value but not the declared pair, so
    the relation was silent for exactly the constant you asked for."""
    _two_owners(tmp_path)
    m = _load(tmp_path, "impask", """
        -module(impask, [look/2])
        -import_from(tcs_own_a, [fee_s])

        look(N, U) <- constant_number_units(fee_s, N, U)
    """)
    assert [n for n, _ in _rows(m, "look", 2)] == [11.0]


def test_an_imported_constant_answers_constant_too(tmp_path):
    """`constant(fee)` after an import raises today -- "nothing declares
    `fee`" -- which tells you to do the thing you just did."""
    _two_owners(tmp_path)
    m = _load(tmp_path, "impval", """
        -module(impval, [look/1])
        -import_from(tcs_own_a, [fee_s])

        look(V) <- (V is constant(fee_s))
    """)
    (v,) = _rows(m, "look", 1)[0]
    assert v.value == 11.0


def test_an_unbound_query_enumerates_THIS_module_only(tmp_path):
    """The back door: if enumeration were not module-scoped too, an unbound
    name would walk every loaded module and the leak would return."""
    _two_owners(tmp_path)
    m = _load(tmp_path, "enumask", """
        -module(enumask, [all/3, fee_e9])
        -import_from(united_states, [usd])
        -constant_number_units(fee_e9, 99.00, usd)

        all(C, N, U) <- constant_number_units(C, N, U)
    """)
    assert [n for _, n, _ in _rows(m, "all", 3)] == [99.0]


def test_a_bound_name_that_is_no_constant_here_RAISES(tmp_path):
    """Operator: referencing a constant that was never defined should be an
    error. `constant()` already raises at load; `/3` failed silently."""
    with pytest.raises(SyntaxError, match="not a constant|nothing declares"):
        _load(tmp_path, "raiser", """
            -module(raiser, [look/2])
            -private([never_a_constant])

            look(N, U) <- constant_number_units(never_a_constant, N, U)
        """)


def test_the_raise_names_the_declaring_module_when_there_is_one(tmp_path):
    """"No such constant" is actively misleading when it exists one import
    away, and the registry already holds what is needed to say so."""
    _two_owners(tmp_path)
    with pytest.raises(SyntaxError) as exc:
        _load(tmp_path, "raiser2", """
            -module(raiser2, [look/2])
            -private([fee_s])

            look(N, U) <- constant_number_units(fee_s, N, U)
        """)
    assert "import" in str(exc.value).lower()


# ── module-prefixed access ───────────────────────────────────────────────────


def test_a_module_prefixed_constant_resolves(tmp_path):
    """`constant(owner.name)` — no import of the NAME needed, because the
    owner is named at the site. The dotted form is read as a QUALIFIED NAME,
    never evaluated as a Python expression, so the property that makes
    `constant()` resolvable at compile time survives."""
    _two_owners(tmp_path)
    m = _load(tmp_path, "prefixed", """
        -module(prefixed, [look/1])
        -import_module(tcs_own_b)

        look(V) <- (V is constant(tcs_own_b.fee_s))
    """)
    (v,) = _rows(m, "look", 1)[0]
    assert v.value == 22.0


def test_prefixing_reaches_the_named_owner_not_another(tmp_path):
    """The discriminator: both owners declare `fee_s`, and the prefix picks."""
    _two_owners(tmp_path)
    m = _load(tmp_path, "prefixed2", """
        -module(prefixed2, [a/1, b/1])
        -import_module(tcs_own_a)
        -import_module(tcs_own_b)

        a(V) <- (V is constant(tcs_own_a.fee_s))
        b(V) <- (V is constant(tcs_own_b.fee_s))
    """)
    assert _rows(m, "a", 1)[0][0].value == 11.0
    assert _rows(m, "b", 1)[0][0].value == 22.0
