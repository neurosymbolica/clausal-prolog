"""``register`` is exported from ``clausal`` beside ``to_clausal`` and
``to_python`` (operator request 2026-11-11), and it is the registry's own
function, so a class registered through it crosses both converters."""
import datetime as dt
from dataclasses import dataclass

import clausal
from clausal.logic import python_terms


def test_register_is_exported_and_is_the_registry_function():
    assert "register" in clausal.__all__
    assert clausal.register is python_terms.register


def test_a_class_registered_through_clausal_crosses_both_ways():
    @dataclass
    class Shipment:
        weight: int
        sent: dt.date

    clausal.register(Shipment, "test_register_is_public_shipment",
                     lambda v: ("test_register_is_public_shipment",
                                v.weight, clausal.to_clausal(v.sent)),
                     lambda t: Shipment(*t[1:]))
    try:
        value = {"s": [Shipment(3, dt.date(2026, 11, 11))]}
        term = clausal.to_clausal(value)
        assert term == {"s": [("test_register_is_public_shipment", 3,
                               ("date", 2026, 11, 11))]}
        assert clausal.to_python(term) == value
    finally:
        python_terms.TO_TERM.pop(Shipment, None)
        python_terms.FROM_TERM.pop("test_register_is_public_shipment", None)


def test_an_unregistered_class_names_register():
    class Unregistered:
        pass
    try:
        clausal.to_clausal(Unregistered())
    except TypeError as error:
        assert "register(cls, functor, to_fn, from_fn)" in str(error)
    else:
        raise AssertionError("an unregistered class converted")
