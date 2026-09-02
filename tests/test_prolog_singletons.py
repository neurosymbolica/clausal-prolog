from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

WITNESS = "schedule_by_criteria(high, no_accepted_medical_use, DEPENDENCE, schedule_i),\n"


def test_head_singleton_emits_underscore_prefixed():
    out = clausal_source_to_prolog(WITNESS, strict=True)
    assert "_Dependence" in out
    assert " Dependence" not in out


def test_multi_occurrence_var_unchanged():
    out = clausal_source_to_prolog("same(X, X),\n", strict=True)
    assert "same(X, X)." in out


def test_body_singleton_also_prefixed():
    out = clausal_source_to_prolog(
        "p(X) <- (q(X, TEMP), r(X))\n", strict=True
    )
    assert "_Temp" in out and " Temp" not in out


def test_anonymous_stays_anonymous():
    out = clausal_source_to_prolog("p(_, X, X),\n", strict=True)
    assert "p(_, X, X)." in out


def test_underscore_source_singleton_not_double_prefixed():
    out = clausal_source_to_prolog("p(_only, X, X),\n", strict=True)
    assert "_Only" in out and "__Only" not in out
