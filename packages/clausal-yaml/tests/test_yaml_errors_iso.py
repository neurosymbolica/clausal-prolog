"""py.yaml: a file-system failure, text that is not YAML and a term YAML
cannot represent RAISE (RULED 2026-10-02: raise).  Each failed the goal.

- OSError on open, read or write -> the shared ISO mapping
  (``clausal.modules.py.raise_os_error``), identical to ``py.files``:
  a missing file is ``existence_error(source_sink, Path)``, a file that may
  not be opened ``permission_error(open, source_sink, Path)``, ...;
- text that is not YAML -> ``syntax_error(invalid_yaml)``, the family
  ``py.http`` raises for a body that is not JSON (``invalid_json``) or not
  UTF-8 (``invalid_data``, Scryer's term);
- a term with no YAML counterpart -> ``type_error(yaml_term, Culprit)``,
  as ``py.json``'s converter raises ``type_error(json_term, Culprit)``.

The predicates are called at the Python level: these pin the adapter, not
the package's surface names.
"""

from __future__ import annotations

import os
import stat

import pytest

from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import yaml as pyaml


def raised(fn, *args):
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


def solutions(fn, *args):
    return list(fn(*args, Trail(), None))


def _err(formal, name, arity):
    return ("error", formal, ("/", name, arity))


_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores file permissions")


class _Opaque:
    """A Python object PyYAML's safe dumper cannot represent."""


# ── text that is not YAML ────────────────────────────────────────────────


def test_read_2_raises_on_text_that_is_not_yaml():
    assert raised(pyaml._read_2, "{a: [}", Var()) == _err(
        ("syntax_error", "invalid_yaml"), "Read", 2)


def test_read_all_2_raises_on_text_that_is_not_yaml():
    assert raised(pyaml._read_all_2, "a: 1\n---\n{b: [}", Var()) == _err(
        ("syntax_error", "invalid_yaml"), "ReadAll", 2)


def test_read_file_2_raises_on_a_file_that_is_not_yaml(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("{a: [}\n")
    assert raised(pyaml._read_file_2, chars(str(p)), Var()) == _err(
        ("syntax_error", "invalid_yaml"), "ReadFile", 2)


def test_valid_yaml_still_answers(tmp_path):
    # Guard (passes before and after).
    out = Var()
    assert len(solutions(pyaml._read_2, "a: 1", out)) == 1
    assert deref(out) == {"a": 1}
    p = tmp_path / "ok.yaml"
    p.write_text("a: 1\n")
    out = Var()
    assert len(solutions(pyaml._read_file_2, str(p), out)) == 1
    assert deref(out) == {"a": 1}


def test_read_file_2_raises_on_a_file_that_is_not_utf8(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_bytes(b"a: \xff\xfe\n")
    assert raised(pyaml._read_file_2, chars(str(p)), Var()) == _err(
        ("syntax_error", "invalid_data"), "ReadFile", 2)


def test_a_path_that_is_not_text_raises():
    # It used to be ``str()`` of the term: an unbound path named a file
    # after the variable's repr.
    assert raised(pyaml._write_file_2, Var(), {"a": 1})[1] == \
        "instantiation_error"
    assert raised(pyaml._read_file_2, ("f", 1), Var())[1] == (
        "type_error", "text", ("f", 1))


# ── file-system failures: the shared ISO mapping ─────────────────────────


def test_read_file_2_missing_file_is_existence_error(tmp_path):
    path = chars(str(tmp_path / "nope.yaml"))
    assert raised(pyaml._read_file_2, path, Var()) == _err(
        ("existence_error", "source_sink", path), "ReadFile", 2)


def test_read_file_2_directory_is_permission_error(tmp_path):
    path = chars(str(tmp_path))
    assert raised(pyaml._read_file_2, path, Var()) == _err(
        ("permission_error", "open", "source_sink", path), "ReadFile", 2)


@_root
def test_read_file_2_unreadable_is_permission_error(tmp_path):
    p = tmp_path / "secret.yaml"
    p.write_text("a: 1\n")
    os.chmod(p, 0)
    try:
        path = chars(str(p))
        assert raised(pyaml._read_file_2, path, Var()) == _err(
            ("permission_error", "open", "source_sink", path), "ReadFile", 2)
    finally:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)


def test_write_file_2_missing_directory_is_existence_error(tmp_path):
    path = chars(str(tmp_path / "no-such-dir" / "out.yaml"))
    assert raised(pyaml._write_file_2, path, {"a": 1}) == _err(
        ("existence_error", "source_sink", path), "WriteFile", 2)


def test_write_file_2_writes_a_text_path(tmp_path):
    # A string path names the file it spells (it used to be ``str()`` of
    # the term).  Guard for the write path itself.
    p = tmp_path / "out.yaml"
    assert len(solutions(pyaml._write_file_2, chars(str(p)), {"a": 1})) == 1
    assert p.read_text() == "a: 1\n"


# ── a term YAML cannot represent ─────────────────────────────────────────


def test_write_2_raises_type_error_for_an_unrepresentable_term():
    term = raised(pyaml._write_2, {"a": _Opaque()}, Var())
    assert term[0] == "error" and term[2] == ("/", "write", 2)
    assert term[1][:2] == ("type_error", "yaml_term")
    assert isinstance(term[1][2], _Opaque)


def test_write_all_2_raises_type_error_for_an_unrepresentable_term():
    term = raised(pyaml._write_all_2, [{"a": 1}, _Opaque()], Var())
    assert term[1][:2] == ("type_error", "yaml_term")
    assert term[2] == ("/", "WriteAll", 2)


def test_write_file_2_unrepresentable_term_leaves_no_file(tmp_path):
    p = tmp_path / "out.yaml"
    term = raised(pyaml._write_file_2, chars(str(p)), {"a": _Opaque()})
    assert term[1][:2] == ("type_error", "yaml_term")
    assert not p.exists()
