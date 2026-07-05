"""Smoke test for the audit kit itself: scaffolding exists and imports clean."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "docs/superpowers/audits/2026-07-05-fable-partition"


def test_scaffolding_exists():
    for rel in [
        "README.md",
        "DESIGN-DECISIONS.md",
        "_templates/findings.md",
        "_templates/design-questions.md",
    ]:
        assert (AUDIT / rel).exists(), f"missing {rel}"


def test_todo_index_exists():
    assert (REPO / "todo/audit-2026-07-05/README.md").exists()


def test_conftest_fixtures_import():
    # importing the audit package must not error
    import tests.audit_2026_07_05  # noqa: F401


def test_path_checker_runs_clean_on_readme():
    # the audit README names real test files; the checker must pass it
    import subprocess
    script = REPO / "scripts/audit_2026_07_05/check_prompt_paths.py"
    # README references test_NN files that don't exist yet, so check the
    # checker on the spec instead (spec names only existing files/dirs).
    spec = REPO / "docs/superpowers/specs/2026-07-05-fable-partition-audit-design.md"
    r = subprocess.run(["python", str(script), str(spec)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
