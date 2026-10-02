"""The clausal-fmt command line."""

import subprocess
import sys
from tests._suffix import SEAM

UNFORMATTED = "p(X)  <-  (q(X), r(X))\n"
FORMATTED = "p(X) <- (\n    q(X),\n    r(X)\n)\n"


def _fmt(*args):
    return subprocess.run(
        [sys.executable, "-m", "clausal.fmt.cli", *args],
        capture_output=True,
        text=True,
    )


def test_cli_check_and_write(tmp_path):
    f = tmp_path / f"x{SEAM}"
    f.write_text(UNFORMATTED)
    assert _fmt("--check", str(f)).returncode == 1  # would change
    assert _fmt(str(f)).returncode == 0
    assert f.read_text() == FORMATTED
    assert _fmt("--check", str(f)).returncode == 0  # now stable


def test_cli_diff_changes_nothing(tmp_path):
    f = tmp_path / f"x{SEAM}"
    f.write_text(UNFORMATTED)
    result = _fmt("--diff", str(f))
    assert result.returncode == 1
    assert "-p(X)  <-  (q(X), r(X))" in result.stdout
    assert "+    q(X)," in result.stdout
    assert f.read_text() == UNFORMATTED


def test_cli_recurses_into_directories(tmp_path):
    (tmp_path / "sub").mkdir()
    f = tmp_path / "sub" / f"y{SEAM}"
    f.write_text(UNFORMATTED)
    (tmp_path / "sub" / "not_clausal.py").write_text("x  =  1\n")
    assert _fmt(str(tmp_path)).returncode == 0
    assert f.read_text() == FORMATTED
    assert (tmp_path / "sub" / "not_clausal.py").read_text() == "x  =  1\n"


def test_cli_reports_a_syntax_error_without_writing(tmp_path):
    f = tmp_path / f"broken{SEAM}"
    f.write_text("p(X <- (q(X))\n")
    result = _fmt(str(f))
    assert result.returncode == 2
    assert f"broken{SEAM}" in result.stderr
    assert f.read_text() == "p(X <- (q(X))\n"


def test_cli_leaves_already_formatted_files_untouched(tmp_path):
    f = tmp_path / f"x{SEAM}"
    f.write_text(FORMATTED)
    before = f.stat().st_mtime_ns
    assert _fmt(str(f)).returncode == 0
    assert f.stat().st_mtime_ns == before


# ── ``.seam`` is an alias extension for ``.clausal`` ─────────────────────────


def test_cli_formats_a_seam_file(tmp_path):
    f = tmp_path / "x.seam"
    f.write_text(UNFORMATTED)
    assert _fmt("--check", str(f)).returncode == 1  # would change
    assert _fmt(str(f)).returncode == 0
    assert f.read_text() == FORMATTED


def test_cli_directory_walk_finds_seam_files(tmp_path):
    (tmp_path / "sub").mkdir()
    seam = tmp_path / "sub" / "y.seam"
    seam.write_text(UNFORMATTED)
    other = tmp_path / "sub" / "z.txt"
    other.write_text(UNFORMATTED)
    assert _fmt(str(tmp_path)).returncode == 0
    assert seam.read_text() == FORMATTED
    assert other.read_text() == UNFORMATTED
