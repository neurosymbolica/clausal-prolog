"""``python -m clausal.testing``: an empty scan fails, and ``.pl`` is a test file.

Two runner defects, both of which let a gate read green over nothing:

* An empty scan (no test files, or files without ``test/1`` clauses) printed
  ``0 tests [NO TESTS]`` and exited 0 unless ``--strict`` was given, and files
  the scan passed over were never named.  It now exits ``EXIT_NO_TESTS`` (5)
  by default, ``--allow-empty`` opts out, and skipped files are reported.
* A Prolog ``.pl`` file was a usage error for the CLI and invisible to the
  pytest plugin.  It is now a test file in both, loaded through the same
  ``.pl`` importer ``-import_from`` uses; a file the translator rejects is a
  failing ``<load>`` result, never a skipped file.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from clausal.testing import (
    EXIT_NO_TESTS,
    EXIT_OK,
    EXIT_TESTS_FAILED,
    EXIT_USAGE,
    SKIPPED_LIST_INLINE_MAX,
    main,
)
from tests._suffix import SEAM

REPO_ROOT = Path(__file__).resolve().parent.parent

PASSING_CLAUSAL = '-double_quotes(atom)\ntest("one is one") <- (1 == 1)\n'
FAILING_CLAUSAL = '-double_quotes(atom)\ntest("one is two") <- (1 == 2)\n'

# Two passing test/1 clauses and one failing one, on lines 3, 4 and 5.
ARITH_PL = textwrap.dedent("""\
    double(X, Y) :- Y is X * 2.

    test('double of two is four') :- double(2, 4).
    test('append works') :- append([1], [2], [1, 2]).
    test('double of two is five') :- double(2, Y), Y =:= 5.
""")
PASSING_PL = "test('one is one') :- 1 =:= 1.\n"
BROKEN_PL = "test('broken') :- foo(.\n"


def _run(capsys, argv):
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# ── exit codes are distinct ──────────────────────────────────────────────────


def test_exit_codes_are_distinct():
    # nv
    assert len({EXIT_OK, EXIT_TESTS_FAILED, EXIT_USAGE, EXIT_NO_TESTS}) == 4
    assert EXIT_NO_TESTS == 5  # pytest's "no tests collected"


# ── D9: an empty scan fails by default ───────────────────────────────────────


def test_empty_dir_exits_no_tests(capsys, tmp_path):
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_NO_TESTS
    assert "no test files (.seam, .clausal or .pl) found" in out
    assert "NO TESTS" in out and "--allow-empty" in out
    assert "PASSED" not in out


def test_empty_dir_allowed_by_flag(capsys, tmp_path):
    rc, out, _ = _run(capsys, ["--allow-empty", str(tmp_path)])
    assert rc == EXIT_OK
    assert "NO TESTS" in out


def test_readme_only_dir_names_the_skipped_file(capsys, tmp_path):
    (tmp_path / "README.md").write_text("# notes\n")
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_NO_TESTS
    assert "1 file(s) skipped (unsupported suffix: 1):" in out
    assert "README.md  (unsupported suffix)" in out


def test_dir_of_passing_tests_is_quiet_and_green(capsys, tmp_path):
    (tmp_path / f"a{SEAM}").write_text(PASSING_CLAUSAL)
    (tmp_path / "b.seam").write_text(PASSING_CLAUSAL)
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_OK
    assert "2 passed, 0 failed [PASSED]" in out
    assert "skipped" not in out


def test_failing_test_exits_one(capsys, tmp_path):
    (tmp_path / f"bad{SEAM}").write_text(FAILING_CLAUSAL)
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_TESTS_FAILED
    assert "[FAILED]" in out


def test_testless_file_exits_no_tests_and_strict_is_the_default(capsys, tmp_path):
    p = tmp_path / f"notests{SEAM}"
    p.write_text("foo(1),\n")
    assert main([str(p)]) == EXIT_NO_TESTS
    assert main(["--strict", str(p)]) == EXIT_NO_TESTS
    assert main(["--fail-on-empty", str(p)]) == EXIT_NO_TESTS
    assert main(["--allow-empty", str(p)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "no test/1 clauses found" in out


def test_strict_and_allow_empty_are_exclusive(capsys, tmp_path):
    with pytest.raises(SystemExit) as ei:
        main(["--strict", "--allow-empty", str(tmp_path)])
    assert ei.value.code == 2


def test_testless_file_in_a_dir_is_reported_as_skipped(capsys, tmp_path):
    (tmp_path / f"helpers{SEAM}").write_text("foo(1),\n")
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_OK
    assert f"helpers{SEAM}  (no test/1 clauses)" in out
    assert "1 passed, 0 failed [PASSED]" in out


def test_long_skip_list_is_a_count_unless_verbose(capsys, tmp_path):
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    n = SKIPPED_LIST_INLINE_MAX + 2
    for i in range(n):
        (tmp_path / f"note{i}.txt").write_text("x")
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_OK
    assert f"{n} file(s) skipped (unsupported suffix: {n}); -v lists them" in out
    assert "note0.txt" not in out
    rc, out, _ = _run(capsys, ["-v", str(tmp_path)])
    assert rc == EXIT_OK
    assert all(f"note{i}.txt  (unsupported suffix)" in out for i in range(n))


def test_pycache_and_hidden_files_are_not_reported(capsys, tmp_path):
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ok.cpython-313.pyc").write_bytes(b"")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "x.txt").write_text("x")
    (tmp_path / ".dotfile").write_text("x")
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_OK
    assert "skipped" not in out


def test_real_process_exit_status(tmp_path):
    """``python -m clausal.testing`` hands main's code to the OS."""
    proc = subprocess.run(
        [sys.executable, "-m", "clausal.testing", str(tmp_path)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert proc.returncode == EXIT_NO_TESTS, proc.stdout + proc.stderr


def test_cli_honours_the_no_collect_marker(capsys, tmp_path):
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    (tmp_path / "data.pl").write_text("% clausal: no-collect\n" + BROKEN_PL)
    (tmp_path / f"fixture{SEAM}").write_text(
        "# clausal: no-collect\nthis is not clausal (\n")
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_OK, out
    assert "data.pl  (no-collect marker)" in out
    assert f"fixture{SEAM}  (no-collect marker)" in out
    assert "1 passed, 0 failed [PASSED]" in out


# ── D10: .pl is a test file ──────────────────────────────────────────────────


def test_pl_file_runs_its_test_clauses(capsys, tmp_path):
    p = tmp_path / "arith.pl"
    p.write_text(ARITH_PL)
    rc, out, _ = _run(capsys, ["-v", str(p)])
    assert rc == EXIT_TESTS_FAILED
    assert "PASS  " in out and "arith.pl::double of two is four" in out
    assert "arith.pl::append works" in out
    assert "3 tests: 2 passed, 1 failed [FAILED]" in out
    # No source map: the report must not claim a line of the .pl file.
    assert not re.search(r"arith\.pl:\d+", out), out
    assert "arith.pl :: double of two is five" in out
    assert "Clausal translation" in out


def test_passing_pl_file_is_green(capsys, tmp_path):
    p = tmp_path / "ok.pl"
    p.write_text(PASSING_PL)
    rc, out, _ = _run(capsys, [str(p)])
    assert rc == EXIT_OK
    assert "1 passed, 0 failed [PASSED]" in out


def test_pl_files_are_discovered_under_a_directory(capsys, tmp_path):
    (tmp_path / f"a{SEAM}").write_text(PASSING_CLAUSAL)
    (tmp_path / "b.pl").write_text(PASSING_PL)
    rc, out, _ = _run(capsys, ["-v", str(tmp_path)])
    assert rc == EXIT_OK
    assert "b.pl::one is one" in out
    assert "2 passed, 0 failed [PASSED]" in out


def test_pl_syntax_error_fails_with_the_translator_error(capsys, tmp_path):
    p = tmp_path / "broken.pl"
    p.write_text(BROKEN_PL)
    rc, out, _ = _run(capsys, [str(p)])
    assert rc == EXIT_TESTS_FAILED
    assert "broken.pl :: <load>" in out
    assert "Cannot import" in out and "Unexpected token" in out


def test_pl_syntax_error_in_a_dir_is_not_skipped(capsys, tmp_path):
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    (tmp_path / "broken.pl").write_text(BROKEN_PL)
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_TESTS_FAILED
    assert "broken.pl :: <load>" in out
    assert "skipped" not in out


def test_pl_without_tests_exits_no_tests(capsys, tmp_path):
    p = tmp_path / "facts.pl"
    p.write_text("likes(mary, wine).\n")
    rc, out, _ = _run(capsys, [str(p)])
    assert rc == EXIT_NO_TESTS
    assert "no test/1 clauses found" in out


def test_unsupported_file_argument_is_a_usage_error(capsys, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("x")
    rc, _, err = _run(capsys, [str(p)])
    assert rc == EXIT_USAGE
    assert "not a .seam, .clausal or .pl file" in err


# ── D10: the pytest plugin collects .pl ──────────────────────────────────────

# Load the root conftest by path and take only its collection hook (see
# test_pytest_plugin_diagnostics._SHIM for why).
_SHIM = """\
import importlib.util as _util

_spec = _util.spec_from_file_location("_clausal_root_conftest", {path!r})
_plugin = _util.module_from_spec(_spec)
_spec.loader.exec_module(_plugin)

pytest_collect_file = _plugin.pytest_collect_file
"""


def _run_plugin(tmp_path: Path, files: dict[str, str]) -> subprocess.CompletedProcess:
    (tmp_path / "conftest.py").write_text(
        _SHIM.format(path=str(REPO_ROOT / "conftest.py")))
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-rfE",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )


def test_plugin_collects_pl_test_clauses(tmp_path):
    proc = _run_plugin(tmp_path, {"arith.pl": ARITH_PL})
    out = proc.stdout + proc.stderr
    assert "1 failed, 2 passed" in out, out
    assert "arith.pl::double of two is five" in out, out


def test_plugin_fails_a_pl_that_does_not_translate(tmp_path):
    proc = _run_plugin(tmp_path, {"broken.pl": BROKEN_PL})
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "broken.pl::<load>" in out, out
    assert "Cannot import" in out, out


def test_plugin_honours_the_prolog_no_collect_marker(tmp_path):
    proc = _run_plugin(tmp_path, {
        "ok.pl": PASSING_PL,
        "skip.pl": "% clausal: no-collect\n" + BROKEN_PL,
    })
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "1 passed" in out, out


# ── The CLI honours a conftest's collect_ignore lists ────────────────────────


def test_cli_skips_the_golden_translator_inputs():
    """The golden directory's conftest excludes its .pl inputs and .clausal
    snapshots from the pytest plugin; the CLI skips the same files, so the
    directory is an empty scan, not a run of failing loads."""
    rc = main([str(REPO_ROOT / "tests" / "fixtures" / "prolog_golden")])
    assert rc == EXIT_NO_TESTS


def test_cli_honours_conftest_collect_ignore_glob(capsys, tmp_path):
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    sub = tmp_path / "golden"
    sub.mkdir()
    (sub / "conftest.py").write_text('collect_ignore_glob = ["*.pl"]\n')
    (sub / "input.pl").write_text(BROKEN_PL)
    (sub / f"kept{SEAM}").write_text(PASSING_CLAUSAL)
    rc, out, _ = _run(capsys, ["-v", str(tmp_path)])
    assert rc == EXIT_OK, out
    assert "input.pl  (ignored by conftest.py)" in out, out
    assert "2 passed, 0 failed [PASSED]" in out, out


def test_cli_honours_conftest_collect_ignore_paths(capsys, tmp_path):
    (tmp_path / "conftest.py").write_text(
        f'collect_ignore = ["broken{SEAM}", "data"]\n')
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    (tmp_path / f"broken{SEAM}").write_text("this is not clausal (\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "deep.pl").write_text(BROKEN_PL)
    rc, out, _ = _run(capsys, ["-v", str(tmp_path)])
    assert rc == EXIT_OK, out
    assert f"broken{SEAM}  (ignored by conftest.py)" in out, out
    assert "deep.pl  (ignored by conftest.py)" in out, out
    assert "1 passed, 0 failed [PASSED]" in out, out


def test_annotated_and_extended_conftest_lists_are_read(capsys, tmp_path):
    (tmp_path / "conftest.py").write_text(
        'collect_ignore_glob: list[str] = ["*.pl"]\n'
        'collect_ignore = []\n'
        f'collect_ignore += ["broken{SEAM}"]\n')
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    (tmp_path / f"broken{SEAM}").write_text("this is not clausal (\n")
    (tmp_path / "input.pl").write_text(BROKEN_PL)
    rc, out, _ = _run(capsys, ["-v", str(tmp_path)])
    assert rc == EXIT_OK, out
    assert f"broken{SEAM}  (ignored by conftest.py)" in out, out
    assert "input.pl  (ignored by conftest.py)" in out, out


def test_a_computed_conftest_list_is_not_executed(capsys, tmp_path):
    """The CLI reads literal lists only; it never runs a conftest."""
    (tmp_path / "conftest.py").write_text(
        'raise SystemExit("executed")\n'
        'collect_ignore_glob = ["*" + ".pl"]\n')
    (tmp_path / f"ok{SEAM}").write_text(PASSING_CLAUSAL)
    (tmp_path / "input.pl").write_text(BROKEN_PL)
    rc, out, _ = _run(capsys, [str(tmp_path)])
    assert rc == EXIT_TESTS_FAILED, out
    assert "input.pl" in out, out


def test_a_file_named_explicitly_is_not_conftest_ignored(capsys, tmp_path):
    """As in pytest, an explicit path argument is collected even when a
    conftest list covers it."""
    (tmp_path / "conftest.py").write_text(f'collect_ignore_glob = ["*{SEAM}"]\n')
    target = tmp_path / f"ok{SEAM}"
    target.write_text(PASSING_CLAUSAL)
    rc, out, _ = _run(capsys, [str(target)])
    assert rc == EXIT_OK, out


@pytest.mark.parametrize("rel", [
    "clausal/tools/toklex/specs/clausal.toklex.pl",
    "clausal/tools/toklex/specs/iso.toklex.pl",
    "clausal/tools/prolog_preludes/clausal_constants_scryer.pl",
    "clausal/tools/prolog_preludes/clausal_constants_trealla.pl",
])
def test_package_data_prolog_files_opt_out(rel):
    from clausal.testing import opts_out_of_collection
    assert opts_out_of_collection(REPO_ROOT / rel)
