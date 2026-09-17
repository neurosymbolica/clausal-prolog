"""The tuple-DATA tag is a reserved quoted atom, not the `tuple` type object.

`(tuple, 1, 2)` cannot be marshalled, and that single fact is why emitted code
has to reach the tag by name through a `$cells` namespace instead of folding it
into a constant. `'()'` is marshal-clean, distinct from every nil spelling, and
valid ISO -- `'()'(1, 2)` reads and writeq-round-trips in SWI and Scryer.

It completes a convention rather than inventing one: ISO gives each bracket
syntax a reserved quoted-atom functor, and this engine already stores `{X}` as
the cell `('{}', X)` and spells nil `'[]'`.
"""
import marshal

from clausal.logic.cells import TUPLE_TAG, is_cell, compound_cell_shape


def test_a_tuple_data_cell_is_marshal_clean():
    """So it can fold into co_consts instead of needing a runtime name."""
    marshal.dumps((TUPLE_TAG, 1, 2))


def test_the_tag_is_the_reserved_spelling():
    assert TUPLE_TAG == "()"


def test_tuple_data_is_still_a_cell():
    assert is_cell((TUPLE_TAG, 1, 2)) is True
    assert is_cell((TUPLE_TAG,)) is True


def test_tuple_data_is_NOT_a_compound_that_can_name_a_predicate():
    """The distinction the old type-object tag got for free, and the one a str
    tag must be given deliberately."""
    ok, functor = compound_cell_shape((TUPLE_TAG, 1, 2))
    assert ok is False, f"tuple-data was read as the compound {functor!r}/2"
    assert compound_cell_shape(("foo", 1, 2)) == (True, "foo")


def test_the_tag_is_distinct_from_every_nil_spelling():
    from clausal.logic.variables import unify, Trail
    for other in ((), "", [], "[]"):
        t = Trail()
        assert unify((TUPLE_TAG,), (other,), t) is False, f"collided with {other!r}"
