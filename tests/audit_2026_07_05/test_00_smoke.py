"""Smoke test for the audit kit itself: scaffolding exists, imports clean,
the path-checker behaves, and the C-toolkit fixtures work."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / "docs/superpowers/audits/2026-07-05-fable-partition"
SCRIPT = REPO / "scripts/audit_2026_07_05/check_prompt_paths.py"


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


def _run_checker(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True, text=True,
    )


def test_path_checker_runs_clean_on_readme():
    # README references test_NN files that don't exist yet, so check the
    # checker on the spec instead (spec names only existing files/dirs).
    spec = REPO / "docs/superpowers/specs/2026-07-05-fable-partition-audit-design.md"
    r = _run_checker(spec)
    assert r.returncode == 0, r.stdout + r.stderr


def test_checker_warns_on_bogus_bare_fragment(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("audit `totally_nonexistent_xyz.py` for bugs")
    r = _run_checker(p)
    # bare fragment naming no repo file => warning, but not a failure by default
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WARNING" in r.stdout
    assert "totally_nonexistent_xyz.py" in r.stdout


def test_checker_strict_fails_on_bogus_bare_fragment(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("audit `totally_nonexistent_xyz.py` for bugs")
    r = _run_checker("--strict", p)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "totally_nonexistent_xyz.py" in r.stdout


def test_checker_no_warn_on_real_bare_fragment(tmp_path):
    # `terms.py` exists in the repo (clausal/terms.py) => no warning
    p = tmp_path / "prompt.md"
    p.write_text("see `terms.py` for the term layer")
    r = _run_checker(p)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WARNING" not in r.stdout


def test_refcount_stable_passes_on_noop(refcount_stable):
    refcount_stable(lambda: None, iterations=100)


def test_refcount_stable_detects_growth(refcount_stable):
    # use a gc-tracked object ([] is tracked; a bare object() is not, so it
    # would not show up in gc.get_objects())
    leaked = []
    with pytest.raises(AssertionError):
        refcount_stable(lambda: leaked.append([]), iterations=200, tol=10)


def test_getrefcount_stable_passes_on_noop(getrefcount_stable):
    obj = []
    getrefcount_stable(obj, lambda: None, iterations=100)


def test_getrefcount_stable_detects_leak(getrefcount_stable):
    obj = []
    holder = []
    with pytest.raises(AssertionError):
        getrefcount_stable(obj, lambda: holder.append(obj), iterations=50, tol=0)
