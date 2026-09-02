import pytest
from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog, UntranslatableConstructError,
)

OVERRIDE_KEY = """override_key(DICT, KEY, VALUE, NEW_DICT) <- (
    NEW_DICT is {**DICT, KEY: VALUE}
)
"""


def test_is_rhs_splat_lowers_to_attrs_put():
    out = clausal_source_to_prolog(OVERRIDE_KEY, strict=True)
    assert "attrs_put(Dict, [attribute(Key, Value)], New_dict)" in out
    assert "**" not in out and "is" not in out.split(":-")[1]


def test_multiple_pairs_sorted():
    out = clausal_source_to_prolog(
        "p(D, OUT) <- (OUT is {**D, zeta: 1, alpha: 2})\n", strict=True
    )
    assert "attrs_put(D, [attribute(alpha, 2), attribute(zeta, 1)], Out)" in out


def test_multi_splat_still_untranslatable():
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog("p(A, B, X) <- (X is {**A, **B})\n", strict=True)


def test_splat_outside_is_rhs_still_untranslatable():
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog("p(D) <- q({**D, k: v})\n", strict=True)


def test_kit_query_combinators_translates_strict():
    import pathlib
    src = pathlib.Path(
        "/workspace/clausify-executor-train/kit/query_combinators.clausal"
    ).read_text()
    out = clausal_source_to_prolog(src, strict=True)  # must not raise
    assert "attrs_put(" in out
