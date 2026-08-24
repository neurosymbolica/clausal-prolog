"""All five _is_logic_var_name copies must agree — and none may claim _X_.

The classifier is deliberately duplicated (predicate.py stays free of
templating imports; desugar stays free of engine imports). This test is the
lockstep guard: a corpus of spellings must classify identically everywhere,
and constant-shaped names (_PI_) must be variables NOWHERE.

Known, deliberate divergences pinned at the bottom: clausal_to_prolog treats
bare `_` as a variable; desugar does not exclude dunders or `_`.
"""
import pytest

from clausal.templating.term_rewriting import (
    _is_logic_var_name as tr_var, _is_constant_name)
from clausal.templating.desugar import _is_logic_var_name as ds_var
from clausal.logic.goal_expansion import _is_logic_var_name as ge_var
from clausal.logic.predicate import _is_logic_var_name as pr_var
from clausal.tools.clausal_to_prolog import _is_logic_var_name as cp_var

ALL = [tr_var, ds_var, ge_var, pr_var, cp_var]

# (spelling, is_variable) — spellings where all five copies must agree.
CORPUS = [
    ("X", True), ("FOO", True), ("MAX_OF", True), ("N1", True),
    ("_x", True), ("_head", True), ("_名前", True),
    ("PI_", True), ("FOO_", True),          # trailing-only: still a variable
    ("foo", False), ("Foo", False), ("in_", False), ("名前", False),
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

def test_corpus_has_no_constant_shaped_variables():
    """Census guard: no .clausal file may use a _X_-shaped name until the
    constants feature gives it meaning (and after that, only declared ones)."""
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parent.parent
    pat = re.compile(r"(?<![A-Za-z0-9_])_[^\W\d_][\w]*?[^\W_]_(?![A-Za-z0-9_])")
    offenders = []
    for p in root.rglob("*.clausal"):
        if ".claude" in p.relative_to(root).parts:
            continue
        for m in pat.finditer(p.read_text()):
            offenders.append((str(p), m.group(0)))
    assert offenders == [], offenders
