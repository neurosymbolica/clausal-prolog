"""All five _is_logic_var_name copies must agree, and the rule has no
exceptions.

The classifier is deliberately duplicated (predicate.py stays free of
templating imports; desugar stays free of engine imports). This test is the
lockstep guard: a corpus of spellings must classify identically everywhere.

Since 2026-09-11 the rule is exactly two clauses -- underscore-led or
capital-initial -- with nothing carved out of it. ``_PI_`` used to be the
module-constant class and a variable NOWHERE; constants are spelled like
atoms now, so it is an ordinary variable like any other underscore-led name.
That is stated as a property below, not only as a corpus of spellings, so a
new exception cannot be added without failing a test.

Known, deliberate divergences pinned at the bottom: clausal_to_prolog treats
bare `_` as a variable; desugar does not exclude dunders or `_`.
"""
import re

import pytest

from clausal.templating.term_rewriting import _is_logic_var_name as tr_var
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
    ("foo", False), ("in_", False), ("_PI_", True), ("__x", False),
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
    # These were the module-constant class until 2026-09-11, carved OUT of
    # the variable namespace in all five copies. Constants are spelled like
    # atoms now, so an underscore-led name is a variable whatever its last
    # character is -- no exception, no fifth copy to keep in step.
    ("_PI_", True), ("_pi_", True), ("_MAX_RETRIES_", True),
    ("_a_b_", True), ("_円周率_", True),
]

@pytest.mark.parametrize("spelling,expected", CORPUS)
def test_all_copies_agree(spelling, expected):
    got = [(fn.__module__, fn(spelling)) for fn in ALL]
    assert all(v == expected for _, v in got), got

def test_pinned_divergences():
    # clausal_to_prolog: bare `_` is a variable there (translation context).
    assert cp_var("_") is True and tr_var("_") is False
    # desugar: no dunder exclusion (sugar-recognition context).
    assert ds_var("__x") is True and tr_var("__x") is False

# The census guard below used to be "no committed .clausal file contains a
# _X_-shaped token unless its own -constants directive declares it", because
# such a token was a name that LOOKED like a variable and was not one. That
# hazard is gone: _X_ is now an ordinary variable, so there is nothing to
# catch. What replaces it is the migration guard -- no committed file may
# still DECLARE a constant the retired way, because such a file no longer
# loads at all.
# Both directives in the family. `-constant_number_units` is spelled `number`
# because only numbers carry units (2026-09-11); a pattern that still said
# `_units` after `value` would silently stop matching it -- which is why the
# control below asserts a hit for EACH directive, not just for one.
_RETIRED_CONSTANT_DECL = re.compile(
    r"^\s*-constant_(?:value|number_units)\(\s*_[A-Za-z0-9\u0080-\uffff]"
    r"[A-Za-z0-9_\u0080-\uffff]*_\s*,")


def test_retired_constant_declaration_regex_matches_what_it_should():
    """A positive control on the census mechanism itself, so the guard below
    cannot pass by matching nothing. Without this, a typo in the pattern
    turns the census into a test that reads every file and asserts nothing.
    """
    assert _RETIRED_CONSTANT_DECL.search("-constant_value(_PI_, 3.14)")
    assert _RETIRED_CONSTANT_DECL.search("  -constant_value(_A_, 1)")
    assert _RETIRED_CONSTANT_DECL.search(
        "-constant_number_units(_MAX_, 5000, euro)")
    assert not _RETIRED_CONSTANT_DECL.search("-constant_value(pi, 3.14)")
    assert not _RETIRED_CONSTANT_DECL.search("holds(_PI_),")


def test_no_committed_file_declares_a_constant_the_retired_way():
    """The retired spelling raises at load, so any file still using it is
    already broken -- this finds it by reading rather than by loading, which
    is what catches a fixture no test happens to import."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    scanned = 0
    for p in root.rglob("*.clausal"):
        if ".claude" in p.relative_to(root).parts:
            continue
        scanned += 1
        for line in p.read_text().splitlines():
            if _RETIRED_CONSTANT_DECL.search(line):
                offenders.append((str(p.relative_to(root)), line.strip()))
    assert scanned > 100, f"the census walked only {scanned} files"
    assert offenders == [], offenders


def test_the_variable_rule_has_no_exceptions():
    """The point of retiring _CONSTANT_: underscore-led (but not a dunder,
    not bare _) or capital-initial IS the whole rule, in every copy.

    Stated as a property rather than as a list of spellings, so a new
    exception cannot be introduced while a hand-written corpus still passes.
    """
    for spelling in ["_PI_", "_MAX_RETRIES_", "_a_b_", "_円周率_", "_pi_",
                     "_x", "_head", "_1_", "X", "Foo", "FOO", "N1",
                     "foo", "in_", "名前", "PI_"]:
        expected = (spelling != "_"
                    and not spelling.startswith("__")
                    and (spelling.startswith("_") or spelling[:1].isupper()))
        for fn in ALL:
            if fn is ds_var and (spelling == "_" or spelling.startswith("__")):
                continue        # pinned divergence: desugar excludes neither
            if fn is cp_var and spelling == "_":
                continue        # pinned divergence: bare _ is a variable there
            assert fn(spelling) == expected, (fn.__module__, spelling)
