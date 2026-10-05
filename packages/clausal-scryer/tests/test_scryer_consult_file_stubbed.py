"""``Scryer.consult_file`` dispatches on the file's SURFACE, without Scryer.

After the extension flip ``.clausal`` is Clausal Prolog (ISO syntax) and seam
source is ``.seam``.  consult_file used to translate any ``.clausal`` path as
seam and hand everything else to the engine raw, so a ``.seam`` file reached
Scryer as Python-syntax text and a Clausal Prolog file went through the seam
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


_SRC = Path(__file__).resolve().parent.parent / "clausal" / "scryer" / "_scryer.py"


class _Machine:
    def close(self):
        pass

    def __init__(self):
        self.loaded = []          # (module, source)

    def consult_module_string(self, module, source):
        self.loaded.append((module, source))


@pytest.fixture
def scryer(monkeypatch):
    fake_ext = types.ModuleType("_scryer_ext")
    fake_ext.RawScryerMachine = _Machine
    mod = _load(_SRC, "_scryer_consult_file_under_test",
                {"_scryer_ext": fake_ext}, monkeypatch)
    return mod.Scryer()


def test_seam_file_is_translated(scryer, tmp_path):
    f = tmp_path / "facts.seam"
    f.write_text(SEAM_FACTS)
    scryer.consult_file(str(f))
    [(module, source)] = scryer._machine.loaded
    assert module == "user"
    assert "color(red)." in source and "color(blue)." in source
    assert "red)," not in source            # no seam trailing comma left


def test_clausal_prolog_file_is_consulted_as_written(scryer, tmp_path):
    f = tmp_path / "fam.clausal"
    f.write_text(CLAUSAL_PROLOG)
    scryer.consult_file(str(f))
    [(_, source)] = scryer._machine.loaded
    # Not run through the seam translator: the text is the file's own,
    # with only end_module (which Scryer refuses) commented out in place.
    assert source == CLAUSAL_PROLOG.replace(":- end_module(fam).",
                                            "% :- end_module(fam).")


def test_pl_file_is_consulted_as_written(scryer, tmp_path):
    f = tmp_path / "facts.pl"
    f.write_text(PL)
    scryer.consult_file(str(f))
    assert scryer._machine.loaded == [("user", PL)]
