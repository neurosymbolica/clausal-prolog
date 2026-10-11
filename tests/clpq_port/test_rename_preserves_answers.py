# tests/clpq_port/test_rename_preserves_answers.py
"""The renamed reading copy answers exactly as the original (Scryer copy).

Also pins the two properties of tools/clpq_reference/rename.py that the
reading copy relies on: only unquoted atoms change, and a map that is not
injective, or that would rename onto an atom already in the sources, is
refused before anything is written.
"""
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from tests._oracles import SCRYER, run_scryer

HERE = pathlib.Path(__file__).resolve().parents[2]
RENAME = HERE / "tools/clpq_reference/rename.py"
MAP = HERE / "tools/clpq_reference/rename_map.tsv"
ORIGINAL = pathlib.Path("/workspace/scryer-prolog-clpq/src/lib/clpq.pl")
EXAMPLES = pathlib.Path("/workspace/claude_sicstus_clpq/test_examples_clpq.pl")

needs_oracle = pytest.mark.skipif(
    not (ORIGINAL.exists() and EXAMPLES.exists() and pathlib.Path(SCRYER).exists()),
    reason="needs the local Scryer CLP(Q) build and the 1.3.3 examples")

sys.path.insert(0, str(RENAME.parent))
import rename  # noqa: E402  (tools/clpq_reference is not a package)


def test_only_unquoted_atoms_are_renamed():
    pairs = {"lin": "linear_form", "nf": "normal_form"}
    text = ("p(Lin, T_lin, _lin) :- lin(Lin), 'lin', \"lin\", 0'l, 0b01,\n"
            "  % lin in a comment\n  /* nf too */ nf(T_lin), x_lin.\n")
    assert rename.rename(text, pairs) == (
        "p(Lin, T_lin, _lin) :- linear_form(Lin), 'lin', \"lin\", 0'l, 0b01,\n"
        "  % lin in a comment\n  /* nf too */ normal_form(T_lin), x_lin.\n")


def test_a_map_with_two_atoms_onto_one_is_refused():
    with pytest.raises(rename.MapError, match="both map to 'same'"):
        rename.check_map({"a": "same", "b": "same"}, {"a", "b"})


def test_a_map_onto_an_atom_already_in_the_sources_is_refused():
    with pytest.raises(rename.MapError, match="'ordering' is already an atom"):
        rename.check_map({"order": "ordering"}, {"order", "ordering"})


def test_the_committed_map_is_injective_over_both_sources():
    sources = sorted(pathlib.Path(
        "/workspace/sicstus/lib/sicstus-4.10.1/library/clpq").glob("*.pl"))
    sources.append(ORIGINAL)
    present = [p for p in sources if p.exists()]
    if not present:
        pytest.skip("needs the 1.3.3 sources")
    atoms = set()
    for path in present:
        atoms |= rename.atoms_in(path.read_text())
    rename.check_map(rename.load_map(MAP), atoms)


def _run_examples(clpq_source, directory):
    directory.mkdir()
    shutil.copy(clpq_source, directory / "clpq.pl")
    shutil.copy(EXAMPLES, directory / EXAMPLES.name)
    # The examples file loads clpq.pl from its own directory and runs under
    # `:- initialization(main)`, so it is loaded with no goal.
    return run_scryer(str(directory / EXAMPLES.name), timeout=600, cwd=directory)


def _failed_count(stdout):
    found = re.search(r"\((\d+) FAILED\)", stdout)
    return int(found.group(1)) if found else 0


@needs_oracle
def test_renamed_copy_gives_the_same_example_results(tmp_path):
    renamed = tmp_path / "renamed.pl"
    subprocess.run([sys.executable, RENAME, MAP, ORIGINAL, renamed], check=True)
    before = _run_examples(ORIGINAL, tmp_path / "original")
    after = _run_examples(renamed, tmp_path / "renamed")
    assert "tests passed" in before.stdout
    assert after.stdout == before.stdout
    assert _failed_count(after.stdout) == _failed_count(before.stdout) == 0
    assert "error" not in after.stdout.lower()
