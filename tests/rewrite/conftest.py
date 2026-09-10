"""Shared rule-module fixtures for the rewrite suite."""

from pathlib import Path

import pytest

RULES_DIR = Path(__file__).resolve().parents[2] / "clausal" / "rewrite" / "rules"


@pytest.fixture(scope="session")
def head_fold_rules():
    """The shipped head-fold rule class, as the driver takes it: paths."""
    return [RULES_DIR / "head_fold.clausal"]


@pytest.fixture(scope="session")
def broken_head_fold_rules():
    """The deliberately-broken control: head-fold minus one legality goal."""
    return [RULES_DIR / "_broken_head_fold_control.clausal"]


@pytest.fixture(scope="session")
def unnecessary_lambda_rules():
    """The shipped eta-reduction rule class, as the driver takes it: paths."""
    return [RULES_DIR / "unnecessary_lambda.clausal"]


@pytest.fixture(scope="session")
def shipped_rules():
    """Every rule class a bare ``clausal-rewrite`` applies, in default order."""
    from clausal.rewrite.cli import default_rule_names, rule_paths

    # Through the CLI's own resolver, not a rebuilt path: a rule file spelled
    # `.seam` is found by `default_rule_names` and must be found here too, or
    # the whole rewrite suite would point at files that do not exist.
    return rule_paths(default_rule_names())
