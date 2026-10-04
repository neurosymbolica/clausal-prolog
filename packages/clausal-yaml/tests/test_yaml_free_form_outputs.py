"""Scalar string VALUES and written documents are STRINGS; keys stay ATOMS.

Ruled 2026-10-04 (adapters are their own entry point, strings spec 9.4): a
string scalar ``read/2``, ``read_all/2`` or ``read_file/2`` loads is
free-form text, the string ``('$chars', s)``, at every depth; a mapping
KEY is a name and stays an atom (a plain ``str``).  The YAML document
``write/2`` and ``write_all/2`` answer is a string.  ``get/3`` hands back
what the data holds, and the ``++`` escape keeps "a Python str is an atom".
"""

from __future__ import annotations

import pytest

pytest.importorskip("yaml", reason="pyyaml not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.cells import chars, is_chars
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-import_from(yaml, [read, read_all, read_file, write, write_all, get])

scalar(S) <- read("hello world", S)
mapping(D) <- read("name: alice\\ntags: [a, b]\\nn: 3", D)
all_docs(L) <- read_all("k: v\\n---\\n- w", L)
from_file(P, D) <- read_file(P, D)
doc(S) <- write({"k": "v"}, S)
docs(S) <- write_all([{"a": 1}, {"b": 2}], S)
get_value(V) <- (read("name: alice", D), get(D, 'name', V))
check_string() <- read("hello", "hello")
check_atom() <- read("hello", 'hello')
check_write_string() <- write({"k": "v"}, "k: v")
check_write_atom() <- write({"k": "v"}, 'k: v')
escape_get(V) <- (D is ++__import__('yaml').safe_load('k: v'), get(D, 'k', V))
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("yamlfree") / f"yaml_free_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("yaml_free_probe", str(src)).__dict__["$module"]


def _one(module, name, *args):
    out = Var()
    [got] = [_deref_walk(out) for _ in call(name, *args, out, module=module)]
    return got


def _holds(module, name):
    return any(True for _ in call(name, module=module))


def test_scalar_is_a_string(module):
    assert _one(module, "scalar") == chars("hello world")


def test_mapping_keys_atoms_values_strings(module):
    got = dict(_one(module, "mapping"))
    assert got == {"name": chars("alice"), "tags": [chars("a"), chars("b")], "n": 3}
    assert all(type(k) is str for k in got)          # keys: atoms


def test_read_all_values_are_strings(module):
    assert _one(module, "all_docs") == [{"k": chars("v")}, [chars("w")]]


def test_read_file_values_are_strings(module, tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("host: db.example.com\n")
    got = dict(_one(module, "from_file", chars(str(p))))
    assert got == {"host": chars("db.example.com")}


def test_written_documents_are_strings(module):
    assert _one(module, "doc") == chars("k: v")
    assert _one(module, "docs") == chars("a: 1\n---\nb: 2")


def test_get_hands_back_the_string(module):
    assert _one(module, "get_value") == chars("alice")


@pytest.mark.parametrize("stem", ["check", "check_write"])
def test_check_mode_takes_the_string_not_the_atom(module, stem):
    # Ruled 2026-10-04: check mode stays STRICT -- a bound result is
    # compared as a term, and the atom of the same spelling is no string.
    assert _holds(module, f"{stem}_string")
    assert not _holds(module, f"{stem}_atom")


def test_escape_data_keeps_atoms(module):
    # a dict built by the ++ escape is Python data: its str value is an atom
    got = _one(module, "escape_get")
    assert type(got) is str and got == "v" and not is_chars(got)
