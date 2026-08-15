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
    from clausal.rewrite.cli import default_rule_names

    return [RULES_DIR / f"{name}.clausal" for name in default_rule_names()]
