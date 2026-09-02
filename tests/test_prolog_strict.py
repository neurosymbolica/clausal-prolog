import pytest
from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    UntranslatableConstructError,
)

# Splat not first: task 2 only lowers the splat-FIRST `is`-RHS shape
# (X is {**D, k: v, ...}) to attrs_put/3; splat-not-first stays
# untranslatable, which is what these tests exercise.
DICT_SRC = 'p(X) <- (X is {a: 1, **base()})\n'
PLUSPLUS_SRC = 'p(S) <- (X is ++str(S), q(X))\n'


def test_strict_dict_literal_raises():
    with pytest.raises(UntranslatableConstructError) as exc:
        clausal_source_to_prolog(DICT_SRC, strict=True)
    assert any("dict splat" in c for c in exc.value.constructs)


def test_strict_aggregates_all_constructs():
    src = DICT_SRC + 'p2(X) <- (X is {b: 2, **base2()})\n'
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
