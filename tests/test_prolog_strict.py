import pytest
from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    UntranslatableConstructError,
)

DICT_SRC = 'meta(k, {"label": "x"}),\n'
PLUSPLUS_SRC = 'p(S) <- (X is ++str(S), q(X))\n'


def test_strict_dict_literal_raises():
    with pytest.raises(UntranslatableConstructError) as exc:
        clausal_source_to_prolog(DICT_SRC, strict=True)
    assert any("dict literal" in c for c in exc.value.constructs)


def test_strict_aggregates_all_constructs():
    src = DICT_SRC + 'meta2(k, {"a": 1}),\n'
    with pytest.raises(UntranslatableConstructError) as exc:
        clausal_source_to_prolog(src, strict=True)
    assert len(exc.value.constructs) == 2


def test_strict_plusplus_raises():
    with pytest.raises(UntranslatableConstructError):
        clausal_source_to_prolog(PLUSPLUS_SRC, strict=True)


def test_lenient_default_unchanged():
    out = clausal_source_to_prolog(DICT_SRC)
    assert "untranslatable" in out  # warning comment survives


def test_clean_source_ok_in_strict():
    out = clausal_source_to_prolog("edge(1, 2),\n", strict=True)
    assert "edge(1, 2)." in out


def test_no_placeholder_without_warning():
    """Every ??? in lenient output must be accompanied by a warning comment.

    Guards the fail-open class: a ??? site that forgot _add_warning would
    pass strict mode while emitting garbage.
    """
    for src in (DICT_SRC, PLUSPLUS_SRC):
        out = clausal_source_to_prolog(src)
        if "???" in out:
            assert "untranslatable" in out
