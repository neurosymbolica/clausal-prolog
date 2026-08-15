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
