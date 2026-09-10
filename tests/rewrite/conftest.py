"""Shared rule-module fixtures for the rewrite suite.

Every fixture resolves its rule through ``clausal.rewrite.cli.rule_path``
rather than rebuilding ``RULES_DIR / f"{name}.clausal"``.  ``.clausal`` and
``.seam`` are aliases, so a shipped rule renamed to `.seam` must still be
found here: a rebuilt path would simply not exist, and the driver's
``os.path.getmtime`` would raise ``FileNotFoundError`` for every test that
consumes the fixture — a rename breaking the suite in a way that names no
suffix anywhere in the traceback.
"""

import pytest

from clausal.rewrite.cli import default_rule_names, rule_path, rule_paths


def _one(name):
    """The path to rule class *name*, or a failure that names the rule.

    ``rule_path`` applies no leading-underscore filter — that lives in
    ``default_rule_names`` — so the deliberately-broken control resolves here
    too.  Asserting non-``None`` makes a typo fail at fixture time with the
    name in the message, instead of inside the driver on a missing file.
    """
    path = rule_path(name)
    assert path is not None, f"no rule file for {name!r} (either suffix)"
    return [path]


@pytest.fixture(scope="session")
def head_fold_rules():
    """The shipped head-fold rule class, as the driver takes it: paths."""
    return _one("head_fold")


@pytest.fixture(scope="session")
def broken_head_fold_rules():
    """The deliberately-broken control: head-fold minus one legality goal."""
    return _one("_broken_head_fold_control")


@pytest.fixture(scope="session")
def unnecessary_lambda_rules():
    """The shipped eta-reduction rule class, as the driver takes it: paths."""
    return _one("unnecessary_lambda")


@pytest.fixture(scope="session")
def shipped_rules():
    """Every rule class a bare ``clausal-rewrite`` applies, in default order."""
    return rule_paths(default_rule_names())
