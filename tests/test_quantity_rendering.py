"""`str(Quantity)` emits text that parses back to an equal value.

Operator's ruling, 2026-09-12. What it produced before resembled source,
was not valid input, and named a unit the language no longer has:

    29200 * usd_cent   ->  '292.00 dollar'      `dollar` is not bound; bare
                                                juxtaposition is a SyntaxError
    7 * gram           ->  '0.007 kilogram'
    3 m/s              ->  '3 metre·second^-1'  `·` and `^` are not syntax
    dimensionless      ->  '4 1'                meaningless

Two faults in the money case alone. `292 usd` does not parse, and `dollar`
stopped resolving at the ISO-code rename — so `str()` named a unit that does
not exist and, for the 22 currencies sharing that word, could not say which
one. Exactly the ambiguity the rename removed, reappearing on the display
path, and it reaches users through every diagnostic, log and query result
that carries a quantity.

**The round trip is exact for what is STORED, never for what was written.**
A minor unit normalises at construction, so `29200 usd_cent` prints
`292.00 (usd)` and `7 gram` prints `0.007 (kilogram)`. That is correct and it
is not what the author typed; `constant_number_units/3` remains the channel
that reports the declared pair.

The identifier printed comes from `_data.CURRENCY_BINDINGS`, never from
`_name` — which is what produced `dollar`. It keeps the plain word where the
word is unique (`euro`, `baht`, `sterling`) and uses the code only where it
is shared, so the output stays readable rather than uniformly cryptic.
"""
import textwrap

import pytest

from decimal import Decimal

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import Quantity


def _reparse(tmp_path, name, text, imports):
    """Evaluate *text* as a clausal term and return the value.

    Goes through the real loader rather than a Python eval, because the claim
    is that the OUTPUT IS VALID INPUT — and only the parser this language
    actually uses can settle that.
    """
    src = imports + f"\nv(X) <- eval_({text}, X)\n"
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(src).lstrip())
    m = _load_module(f"tqr_{name}", str(path))
    v = Var()
    rows = [deref(v) for _ in call("v", v, module=m.__dict__["$module"])]
    assert len(rows) == 1, f"{text!r} gave {len(rows)} solutions"
    return rows[0]


UNIT_IMPORTS = (
    "-module(r, [v/1])\n"
    "-import_from(py.units, [metre, second, kilogram, dimensionless])\n"
    "-import_from(united_states, [usd, usd_cent])\n"
    "-import_from(european_union, [euro, eur_cent])\n"
    "-import_from(australia, [aud])\n"
)


def _cases():
    from clausal.modules.countries.united_states import usd, usd_cent
    from clausal.modules.countries.european_union import euro, eur_cent
    from clausal.modules.units import metre, second, gram
    return [
        ("money", 29200 * usd_cent),
        ("money_eur", 300000 * eur_cent),
        ("whole_currency", Quantity(Decimal("5"), euro)),
        ("physical_scaled", 7 * gram),          # an exact Decimal magnitude since 2026-09-18
        ("physical_float", Quantity(2.5, metre)),  # a float magnitude: 2.5 beside an int factor stays float (Q4)
        ("physical_base", Quantity(3, metre)),
        ("compound", Quantity(3, {metre: 1, second: -1})),
        ("power", Quantity(3, {metre: 2})),
        ("dimensionless", Quantity(4, {})),
        # A currency Quantity keeps an exact Fraction (the CLP lane, today),
        # so `10.00(usd) / 3` renders with a `/` in the VALUE. Absent from
        # the first eight shapes, and the shape that broke the property:
        # `10/3 (usd)` parses as `10 / 3(usd)`, inverting the dimension.
        ("fraction_money", Quantity(Decimal("10.00"), usd) / 3),
        ("fraction_negative", Quantity(Decimal("-10.00"), usd) / 3),
        ("negative_money", Quantity(Decimal("-5.00"), usd)),
    ]


@pytest.mark.parametrize("label,q", _cases(), ids=[c[0] for c in _cases()])
def test_str_round_trips_to_an_equal_value(tmp_path, label, q):
    """The PROPERTY, not a golden string: it cannot drift, and it covers every
    shape at once. A shape that cannot round-trip is the finding."""
    text = str(q)
    back = _reparse(tmp_path, f"rt_{label}", text, UNIT_IMPORTS)
    # TYPE as well as equality. Equality alone could pass on a coincidence —
    # a bare number comparing equal to a dimensionless Quantity, say — and
    # "is my assertion the weaker one?" is the right question to ask of a
    # passing round-trip test (a downstream user, 2026-09-12, who could not
    # reproduce this shape and asked it rather than assuming).
    assert type(back) is type(q), (
        f"{text!r} parsed back as {type(back).__name__}, not "
        f"{type(q).__name__}: {back!r}")
    if type(q.value) is Decimal and type(back.value) is float:
        # RULED Q4 (2026-09-17): a decimal literal in source IS a float, so an
        # exact Decimal magnitude cannot come back as a Decimal through
        # source text; what round-trips is its DIGITS (the shortest repr of
        # the float is the written literal).  A read-time -float_literals
        # directive would restore the kind; noted, not ruled.
        assert Decimal(repr(back.value)) == q.value, (
            f"{text!r} parsed back as {back!r}: digits differ from {q!r}")
    else:
        assert back == q, f"{text!r} parsed back as {back!r}, not {q!r}"
    assert dict(back.dims) == dict(q.dims), (
        f"{text!r} parsed back with dims {dict(back.dims)}, not {dict(q.dims)}")


def test_the_money_form_is_the_ruled_spelling():
    """Spelled out once, because the round-trip property would also accept
    `292.00(usd)` and the operator asked for the spaced form."""
    from clausal.modules.countries.united_states import usd_cent
    assert str(29200 * usd_cent) == "292.00 (usd)"


def test_the_identifier_comes_from_the_bindings_not_the_display_word():
    """`dollar` is the `_name` and does not resolve; `usd` is what is bound.
    For the 22 currencies sharing the word, `_name` cannot say which."""
    from clausal.modules.countries.united_states import usd
    from clausal.modules.countries.australia import aud
    assert str(Quantity(Decimal("1"), usd)) == "1 (usd)"
    assert str(Quantity(Decimal("1"), aud)) == "1 (aud)"
    assert usd._name == aud._name == "dollar", "the display word is shared"


def test_a_unique_currency_word_stays_the_word():
    """The bindings keep the plain word where it is unambiguous, so the
    output does not become uniformly cryptic."""
    from clausal.modules.countries.european_union import euro
    from clausal.modules.countries.thailand import baht
    assert str(Quantity(Decimal("5"), euro)) == "5 (euro)"
    assert str(Quantity(Decimal("5"), baht)) == "5 (baht)"


def test_a_dimensionless_quantity_names_dimensionless():
    """`4` alone re-reads as a plain number and loses that it is a Quantity;
    `4 ()` is not a unit annotation. `dimensionless` is a real unit predicate,
    so naming it makes the round trip TOTAL rather than leaving one shape
    exempt."""
    assert str(Quantity(4, {})) == "4 (dimensionless)"


def test_a_minor_unit_prints_its_BASE_unit(tmp_path):
    """Stated as its own test because someone will expect to see back what
    they wrote. The value does not hold the declared pair — normalisation
    discarded it — and `constant_number_units/3` is the channel that does."""
    from clausal.modules.countries.united_states import usd_cent
    assert str(29200 * usd_cent) == "292.00 (usd)"
    from clausal.modules.units import gram
    assert str(7 * gram) == "0.007 (kilogram)"


def test_the_shape_list_covers_every_magnitude_type_a_quantity_holds():
    """A guard against the shape list going STALE rather than being wrong.

    The eight original shapes were total over the shapes CHOSEN, and they were
    chosen before a currency Quantity began holding an exact `Fraction` — so
    the list did not become incorrect, it stayed the same while the thing it
    measures moved. That is a maintenance obligation distinct from
    correctness, and nothing was watching it.

    The shape here is: derive the instrument's coverage from the AUTHORITY
    rather than from a hand list. `_to_decimal` enumerates the magnitude types
    a currency accepts; if one is added, this fails until a round-trip shape
    covers it. The scale lint uses the same trick, taking its suffixes from
    `MINOR_UNIT_WORDS` so a new minor unit extends it with no second edit.
    """
    import inspect
    from clausal import terms

    source = inspect.getsource(terms._to_decimal)
    accepted = {name for name in ("int", "float", "Decimal", "Fraction")
                if f"isinstance(x, {name}" in source
                or f", {name})" in source or f"({name}," in source}
    assert accepted, "positive control: the authority names magnitude types"

    covered = {type(q.value).__name__ for _, q in _cases()}
    missing = accepted - covered - {"bool"}
    assert not missing, (
        f"magnitude types accepted by the engine but absent from the "
        f"round-trip shapes: {sorted(missing)} — add a case, or the property "
        f"is total only over the shapes someone chose earlier")
