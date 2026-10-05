"""``Trealla.consult_file`` dispatches on the file's SURFACE, without Trealla.

After the extension flip ``.clausal`` is Clausal Prolog (ISO syntax) and seam
source is ``.seam``.  consult_file used to translate any ``.clausal`` path as
seam and hand everything else to the engine raw, so a ``.seam`` file reached
Trealla as Python-syntax text and a Clausal Prolog file went through the seam
translator.  Runs without the engine (``*_stubbed.py``): a recording fake
stands in for the native machine, and the real module's logic runs against it.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

SEAM_FACTS = "color(red),\ncolor(blue),\n"
CLAUSAL_PROLOG = (":- module(fam, [color/1]).\n"
                  "color(red).\ncolor(blue).\n"
                  ":- end_module(fam).\n")
PL = "animal(cat). animal(dog).\n"


def _load(path, name, fake_modules, monkeypatch):
    """Import *path* as module *name* with *fake_modules* standing in for
    the engine's native extension, so the real consult_file logic runs
    without the engine being built.  The fakes leave ``sys.modules`` when
    the test ends: a fake left behind would make the package's own
    ``import <ext>`` succeed and report the engine as AVAILABLE."""
    for mod_name, mod in fake_modules.items():
        monkeypatch.setitem(sys.modules, mod_name, mod)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SRC = Path(__file__).resolve().parent.parent / "clausal" / "trealla" / "_trealla.py"


class _Machine:
    def destroy(self):
        pass

    def __init__(self):
        self.strings = []
        self.files = []

    def consult_string(self, source):
        self.strings.append(source)
        return True

    def consult_file(self, path):
        self.files.append(path)
        return True


@pytest.fixture
def trealla(monkeypatch):
    fake_engine = types.ModuleType("clausal.trealla._engine")
    fake_engine.TreallaMachine = _Machine
    mod = _load(_SRC, "_trealla_consult_file_under_test",
                {"clausal.trealla._engine": fake_engine}, monkeypatch)
    return mod.Trealla()


def test_seam_file_is_translated(trealla, tmp_path):
    f = tmp_path / "facts.seam"
    f.write_text(SEAM_FACTS)
    trealla.consult_file(str(f))
    [source] = trealla._machine.strings
    assert "color(red)." in source and "color(blue)." in source
    assert "red)," not in source
    assert trealla._machine.files == []


def test_clausal_prolog_file_is_consulted_as_written(trealla, tmp_path):
    f = tmp_path / "fam.clausal"
    f.write_text(CLAUSAL_PROLOG)
    trealla.consult_file(str(f))
    assert trealla._machine.strings == [
        CLAUSAL_PROLOG.replace(":- end_module(fam).", "% :- end_module(fam).")]
    assert trealla._machine.files == []


def test_pl_file_is_consulted_by_trealla_itself(trealla, tmp_path):
    f = tmp_path / "facts.pl"
    f.write_text(PL)
    trealla.consult_file(str(f))
    assert trealla._machine.files == [str(f)]
    assert trealla._machine.strings == []
