"""All five _is_logic_var_name copies must agree — and none may claim _X_.

The classifier is deliberately duplicated (predicate.py stays free of
templating imports; desugar stays free of engine imports). This test is the
lockstep guard: a corpus of spellings must classify identically everywhere,
and constant-shaped names (_PI_) must be variables NOWHERE.

Known, deliberate divergences pinned at the bottom: clausal_to_prolog treats
bare `_` as a variable; desugar does not exclude dunders or `_`.
"""
import re

import pytest

from clausal.templating.term_rewriting import (
    _is_logic_var_name as tr_var, _is_constant_name)
from clausal.templating.desugar import _is_logic_var_name as ds_var
from clausal.logic.goal_expansion import _is_logic_var_name as ge_var
from clausal.logic.predicate import _is_logic_var_name as pr_var
from clausal.tools.clausal_to_prolog import _is_logic_var_name as cp_var

ALL = [tr_var, ds_var, ge_var, pr_var, cp_var]

# The NAME-position classifier is duplicated for the same reason the variable
# one is (clausal_to_prolog stays free of a templating import), so it gets the
# same lockstep gate -- without one the pair can drift exactly as the five
# below could.
from clausal.templating.term_rewriting import (          # noqa: E402
    _is_var_in_name_position as tr_name)
from clausal.tools.clausal_to_prolog import (            # noqa: E402
    _is_var_in_name_position as cp_name)

NAME_POSITION = [
    # Capital-initial WITH a lowercase letter is a name here, not a variable:
    # a callable, or a component of a qualified name.
    ("Foo", False), ("FooBar", False), ("Metre", False), ("TruncDiv", False),
    # Everything that was a variable before 2026-09-10 still is.
    ("FOO", True), ("X", True), ("N1", True), ("MAX_OF", True),
    ("_foo", True), ("_x", True),
    # And non-variables stay non-variables.
    ("foo", False), ("in_", False), ("_PI_", False), ("__x", False),
]


@pytest.mark.parametrize("spelling,expected", NAME_POSITION)
def test_name_position_copies_agree(spelling, expected):
    got = [(fn.__module__, fn(spelling)) for fn in (tr_name, cp_name)]
    assert all(v == expected for _, v in got), got


def test_name_position_is_the_variable_rule_minus_titlecase():
    """Stated as a property, so a new spelling cannot satisfy the corpus
    above while breaking the relationship the two rules are meant to have."""
    for spelling, _ in CORPUS + NAME_POSITION:
        titlecase = (spelling[:1].isupper()
                     and any(c.islower() for c in spelling))
        assert tr_name(spelling) == (tr_var(spelling) and not titlecase), spelling


def test_name_position_pinned_divergence():
    """clausal_to_prolog's bare-``_`` divergence is inherited, not restated:
    the name-position rule is built on the local variable classifier."""
    assert cp_name("_") is True and tr_name("_") is False

# (spelling, is_variable) — spellings where all five copies must agree.
CORPUS = [
    ("X", True), ("FOO", True), ("MAX_OF", True), ("N1", True),
    ("_x", True), ("_head", True), ("_名前", True),
    ("PI_", True), ("FOO_", True),          # trailing-only: still a variable
    # ``Foo`` is a VARIABLE since 2026-09-10: a capital initial names a
    # variable (ISO), in every one of the five copies.  It is still refused in
    # FUNCTOR position, but that is the TitleCase lint's rule, not this
    # classifier's -- this predicate is lexical and says nothing about
    # position.
    ("Foo", True), ("FooBar", True), ("N1x", True),
    ("foo", False), ("in_", False), ("名前", False),
    # The new constant class: variables NOWHERE.
    ("_PI_", False), ("_pi_", False), ("_MAX_RETRIES_", False),
    ("_a_b_", False), ("_円周率_", False),
]

@pytest.mark.parametrize("spelling,expected", CORPUS)
def test_all_copies_agree(spelling, expected):
    got = [(fn.__module__, fn(spelling)) for fn in ALL]
    assert all(v == expected for _, v in got), got

CONSTANT_SHAPE = [
    ("_PI_", True), ("_a_b_", True), ("_円周率_", True),
    ("_", False), ("__", False), ("___", False),
    ("_X__", False), ("__X_", False),        # exactly one underscore each end
    ("_1_", False),                          # interior must not start with a digit
    ("PI_", False), ("_PI", False), ("PI", False),
]

@pytest.mark.parametrize("spelling,expected", CONSTANT_SHAPE)
def test_constant_shape(spelling, expected):
    assert _is_constant_name(spelling) == expected

def test_pinned_divergences():
    # clausal_to_prolog: bare `_` is a variable there (translation context).
    assert cp_var("_") is True and tr_var("_") is False
    # desugar: no dunder exclusion (sugar-recognition context).
    assert ds_var("__x") is True and tr_var("__x") is False

# Loose token-finder for the census guard: any ``_..._`` run bounded by
# non-word characters. Deliberately looser than _is_constant_name (it does
# not check interior length, leading digit, or doubled boundary
# underscores) — candidates it finds are handed to _is_constant_name itself
# to decide, so the census can never drift out of sync with the classifier
# the way a hand-rolled equivalent-but-independent regex did (roborev
# finding: the old pattern required a >=2-char interior and so missed
# single-char constants like _X_/_a_).
_CONSTANT_TOKEN_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_])_\w+_(?![A-Za-z0-9_])")


def _constant_shaped_tokens(text):
    return [m.group(0) for m in _CONSTANT_TOKEN_CANDIDATE.finditer(text)
            if _is_constant_name(m.group(0))]


def test_census_candidate_regex_delegates_to_classifier():
    """Unit check on the census mechanism itself, independent of any
    fixture corpus: the loose candidate regex plus _is_constant_name must
    agree with the classifier on tokens the old, stricter regex got wrong
    (single non-digit interior char) as well as ones it must still reject."""
    assert _constant_shaped_tokens("x = _X_") == ["_X_"]
    assert _constant_shaped_tokens("x = _a_") == ["_a_"]
    assert _constant_shaped_tokens("x = _1_") == []
    assert _constant_shaped_tokens("x = _X__") == []


# Fixtures that legitimately DECLARE and use a -constants name, and so
# legitimately contain constant-shaped tokens.  The census guard below
# anticipated needing this ("a future fixture that legitimately declares and
# uses a -constants name will need an explicit allowlist"); P3-2 task-2 is the
# first thing to need it.  Keyed by (filename, token) rather than by file, so
# an unrelated constant appearing in an allowlisted fixture is still flagged.
#
# Every entry must be a name the file's own -constants directive declares --
# which is the property that makes it a constant rather than a
# constant-shaped VARIABLE, the thing this census exists to catch.
_DECLARED_CONSTANT_FIXTURES = {
    # tests/test_constants.py::test_constants_rhs_can_construct_an_imported_
    # functor -- a -constants RHS constructing an IMPORTED data functor, the
    # shape that failed to load before P3-2 task-2's fix.
    ("const_functor_importer.clausal", "_W_"),
    ("const_functor_importer.clausal", "_P_"),
    ("const_functor_importer.clausal", "_NEST_"),
}


def test_corpus_has_no_constant_shaped_variables():
    """Census guard: no committed .clausal file contains a _X_-shaped token
    unless its own -constants directive declares it.

    The bar used to be simply "none exist yet"; it is now "none except
    declared constants", enforced through ``_DECLARED_CONSTANT_FIXTURES``
    above plus a check that each allowlisted token really is declared in the
    file that carries it -- so the allowlist cannot be used to wave through a
    constant-shaped VARIABLE, which is the thing this census exists to
    catch."""
    import pathlib
    import re as _re
    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for p in root.rglob("*.clausal"):
        if ".claude" in p.relative_to(root).parts:
            continue
        text = p.read_text()
        for tok in _constant_shaped_tokens(text):
            if (p.name, tok) in _DECLARED_CONSTANT_FIXTURES:
                declared = any(
                    line.lstrip().startswith("-constants(")
                    and _re.search(_re.escape(tok) + r"\s*=", line)
                    for line in text.splitlines()
                )
                assert declared, (p, tok)
                continue
            offenders.append((str(p), tok))
    assert offenders == [], offenders
