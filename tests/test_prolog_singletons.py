from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

WITNESS = "schedule_by_criteria(high, no_accepted_medical_use, DEPENDENCE, schedule_i),\n"


def test_head_singleton_emits_underscore_prefixed():
    # Was "_Dependence": the name used to be titlecased on the way out as
    # well as underscore-prefixed here. Names cross unchanged now, so the
    # prefix is the only thing this pass contributes -- which is the
    # subject.
    out = clausal_source_to_prolog(WITNESS, strict=True)
    assert "_DEPENDENCE" in out
    assert " DEPENDENCE" not in out


def test_multi_occurrence_var_unchanged():
    out = clausal_source_to_prolog("same(X, X),\n", strict=True)
    assert "same(X, X)." in out


def test_body_singleton_also_prefixed():
    out = clausal_source_to_prolog(
        "p(X) <- (q(X, TEMP), r(X))\n", strict=True
    )
    assert "_TEMP" in out and " TEMP" not in out


def test_anonymous_stays_anonymous():
    out = clausal_source_to_prolog("p(_, X, X),\n", strict=True)
    assert "p(_, X, X)." in out


def test_underscore_source_singleton_not_double_prefixed():
    """The case is stronger than it was, not weaker.

    ``_only`` used to be titlecased to ``Only`` first, losing its underscore,
    so this pass put one back and the test checked it had not put on two.
    The name keeps its own underscore now, so the pass has to recognise it
    and leave it alone -- the guard is doing real work rather than being
    given nothing to double.
    """
    out = clausal_source_to_prolog("p(_only, X, X),\n", strict=True)
    assert "p(_only, X, X)." in out
    assert "__only" not in out
