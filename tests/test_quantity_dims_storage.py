import marshal
from types import MappingProxyType

import pytest

from clausal.modules import units
from clausal.terms import Quantity


def test_dims_is_stored_as_a_plain_dict():
    q = Quantity(5, units.metre)
    assert type(q._dims) is dict


def test_dims_property_still_returns_an_immutable_view():
    q = Quantity(5, units.metre)
    assert isinstance(q.dims, MappingProxyType)
    with pytest.raises(TypeError):
        q.dims["metre"] = 99


def test_the_stored_mapping_marshals_once_its_keys_are_data():
    # The mappingproxy was the ONE thing blocking it: a plain dict marshals.
    # Keys are still predicate objects at this commit, so stringify them --
    # the rekey is what makes the whole dict marshal unchanged.
    q = Quantity(5, units.metre)
    assert marshal.loads(marshal.dumps({str(k): v for k, v in q._dims.items()}))


def test_hashing_and_equality_are_unaffected():
    a, b = Quantity(5, units.kilometre), Quantity(5000, units.metre)
    assert a == b and hash(a) == hash(b)


def test_a_quantity_built_from_another_does_not_SHARE_its_dims():
    # A plain dict is mutable, so aliasing would let one quantity's mutation
    # reach another's -- and __hash__ is computed from _dims.
    base = Quantity(5, units.kilometre)
    derived = Quantity(2, base)
    assert derived._dims is not base._dims
