"""Conftest for the 2026-05-25 string audit adversarial tests.

All tests in this directory are intentionally `xfail(strict=True)` pre-fix.
A test that passes here means either:
  (a) Phase 2 landed a fix — the xfail marker should now be removed; or
  (b) the test is wrong — re-check the ledger entry and the probe.

This conftest does not register any auto-use fixtures; it exists so pytest
treats this directory as its own test scope and to document the discipline.
"""

import pytest

# Re-export so tests can `from .conftest import xfail_ledger` for brevity
# if they prefer; otherwise the standard `@pytest.mark.xfail(strict=True, ...)`
# usage is fine.

def xfail_ledger(finding_id: str, title: str) -> pytest.MarkDecorator:
    """Convenience wrapper: `xfail_ledger("F015", "SegList non-det first split only")`."""
    return pytest.mark.xfail(
        strict=True, reason=f"ledger {finding_id}: {title}"
    )
