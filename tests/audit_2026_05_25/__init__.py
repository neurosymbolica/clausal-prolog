"""Adversarial tests generated from the 2026-05-25 string implementation audit.

Every test here is marked `xfail(strict=True)` because the audit found
bugs / design-gaps that have not been fixed yet. When Phase 2 of the audit
lands a fix, the corresponding xfail flips to a pass, and pytest signals
an unexpected pass — the Phase 2 commit must then remove the xfail marker.

See: docs/superpowers/audits/2026-05-25-string-implementation/findings.md
"""
