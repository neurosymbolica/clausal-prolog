from clausal.tools.clausal_to_prolog import clausal_source_to_prolog


def test_dict_lowers_to_sorted_attribute_list():
    out = clausal_source_to_prolog(
        "profile_for(s1, {zeta: True, alpha: False}),\n", strict=True
    )
    assert "profile_for(s1, [attribute(alpha, false), attribute(zeta, true)])." in out


def test_empty_dict_lowers_to_empty_list():
    out = clausal_source_to_prolog("profile_for(s2, {}),\n", strict=True)
    assert "profile_for(s2, [])." in out


def test_nested_dict_lowers_recursively():
    out = clausal_source_to_prolog(
        "cfg(x, {outer: {inner: True}}),\n", strict=True
    )
    assert "cfg(x, [attribute(outer, [attribute(inner, true)])])." in out


def test_dict_in_rule_body():
    out = clausal_source_to_prolog(
        "q_limb_a(P) <- (P is {technique_subliminal: True})\n", strict=True
    )
    assert "[attribute(technique_subliminal, true)]" in out


def test_dict_splat_still_untranslatable():
    import pytest
    from clausal.tools.clausal_to_prolog import UntranslatableConstructError
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog("p(X) <- (X is {**base_profile()})\n", strict=True)


def test_get_maps_to_profile_get():
    out = clausal_source_to_prolog(
        "v(P, V) <- get(P, exception_d_supports_human_assessment, V)\n",
        strict=True,
    )
    assert "profile_get(P, exception_d_supports_human_assessment, V)" in out
    assert "get(P," not in out


def test_tri_get_passes_through():
    out = clausal_source_to_prolog("v(P, V) <- tri_get(P, k, V)\n", strict=True)
    assert "tri_get(P, k, V)" in out
