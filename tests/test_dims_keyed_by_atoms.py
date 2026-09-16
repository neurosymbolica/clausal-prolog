import marshal

from clausal.modules import units
from clausal.modules.countries import european_union
from clausal.terms import Quantity


def test_dims_keys_are_plain_strings():
    q = Quantity(5, units.metre)
    assert [type(k) for k in q.dims] == [str]
    assert list(q.dims) == ["metre"]


def test_a_currency_key_is_its_binding_atom():
    q = Quantity(1550.00, european_union.euro)
    assert list(q.dims) == ["euro"]


def test_the_whole_dims_dict_now_marshals_unchanged():
    q = Quantity(5, units.metre)
    assert marshal.loads(marshal.dumps(q._dims)) == {"metre": 1}


def test_dims_can_now_be_SORTED():
    # sorted() raised TypeError on predicate-object keys -- "'<' not supported
    # between instances of '_UnitsPredicate'". That is why the canonical sort
    # was downstream of this rekey rather than independent of it.
    q = Quantity(1, units.metre) * Quantity(1, units.second)
    assert sorted(q._dims.items()) == [("metre", 1), ("second", 1)]


def test_the_wire_form_falls_out_of_the_sorted_items():
    q = Quantity(1, units.metre) * Quantity(1, units.second)
    wire = ("dimensions", *sorted(q._dims.items()))
    assert wire == ("dimensions", ("metre", 1), ("second", 1))
    assert dict(wire[1:]) == q._dims          # dict() accepts the pair form


def test_a_derived_unit_is_keyed_by_atoms_too():
    q = Quantity(1, units.watt)
    assert sorted(q._dims) == ["kilogram", "metre", "second"]


def test_currency_behaviour_survives_the_flip():
    q = Quantity(155000, european_union.eur_cent)
    assert str(q) == "1550.00 (euro)"
    assert format(q, "code") == "1550.00 EUR"


def test_ratio_units_are_still_dimensionless():
    assert dict(Quantity(5, units.percent).dims) == {}
