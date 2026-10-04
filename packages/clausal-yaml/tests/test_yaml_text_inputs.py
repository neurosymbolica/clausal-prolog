"""``write/2``, ``write_all/2`` and ``write_file/2`` serialise a STRING as
the text it denotes (spec §9.4, "text in").

The data was handed to ``yaml.safe_dump`` dereferenced one level only, so
a string -- the chars carrier ``('$chars', s)`` -- nested in a mapping or
a list reached PyYAML as a Python tuple, which the safe dumper cannot
represent (``type_error(yaml_term, _)``).  The probe is written under
``-double_quotes(chars)`` so ``"..."`` IS a string.  Only the INPUT
changes here; what ``write/2`` hands back (a string since 2026-10-04) is
pinned in test_yaml_free_form_outputs.py.
"""

from __future__ import annotations

import pytest

pytest.importorskip("yaml", reason="pyyaml not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.cells import chars, chars_text, is_chars
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var


SRC = """\
-double_quotes(chars)
-import_from(yaml, [write, write_all, write_file, read])

mapping(S) <- write({"name": "bob", "tags": ["a", 'b']}, S)
docs(S) <- write_all([{"a": "x"}, ["y"]], S)
top(S) <- write("plain", S)
to_file(P) <- write_file(P, {"name": "bob"})
roundtrip(D) <- (write({"name": "bob"}, S), read(S, D))
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("yamltext") / f"yaml_text_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("yaml_text_probe", str(src)).__dict__["$module"]


def _text(module, name):
    s = Var()
    [got] = [_deref_walk(s) for _ in call(name, s, module=module)]
    return chars_text(got) if is_chars(got) else got


def test_write_nested_strings(module):
    assert _text(module, "mapping") == "name: bob\ntags:\n- a\n- b"


def test_write_all_nested_strings(module):
    assert _text(module, "docs") == "a: x\n---\n- y"


def test_write_top_level_string(module):
    assert _text(module, "top") == "plain"


def test_write_file_nested_strings(module, tmp_path):
    p = tmp_path / "out.yaml"
    assert len(list(call("to_file", chars(str(p)), module=module))) == 1
    assert p.read_text() == "name: bob\n"


def test_write_then_read(module):
    d = Var()
    [got] = [_deref_walk(d) for _ in call("roundtrip", d, module=module)]
    # the value read back is a STRING; the key stays an atom
    assert dict(got) == {"name": chars("bob")}
