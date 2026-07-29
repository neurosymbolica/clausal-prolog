"""Unit test for the add_implicit_atoms codemod (Task 3)."""
from __future__ import annotations

import importlib.util
import os

_SPEC = importlib.util.spec_from_file_location(
    "add_implicit_atoms",
    os.path.join(os.path.dirname(__file__), "add_implicit_atoms.py"),
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
add_implicit_atoms = _MOD.add_implicit_atoms


def test_inserts_before_first_code_line(tmp_path):
    f = tmp_path / "a.clausal"
    f.write_text("# a comment\n\nColor(red),\n")
    changed = add_implicit_atoms(str(f))
    assert changed is True
    lines = f.read_text().splitlines()
    # Directive goes before the first non-comment, non-blank line.
    assert "-implicit_atoms" in lines
    assert lines.index("-implicit_atoms") < lines.index("Color(red),")
    # Leading comment is preserved above the directive.
    assert lines[0] == "# a comment"


def test_skips_file_with_strict_atoms(tmp_path):
    f = tmp_path / "b.clausal"
    original = "-strict_atoms\n\nColor(red),\n"
    f.write_text(original)
    changed = add_implicit_atoms(str(f))
    assert changed is False
    assert f.read_text() == original


def test_idempotent(tmp_path):
    f = tmp_path / "c.clausal"
    f.write_text("Color(red),\n")
    assert add_implicit_atoms(str(f)) is True
    assert add_implicit_atoms(str(f)) is False
    assert f.read_text().count("-implicit_atoms") == 1
