"""A field-named ``-module`` entry beside ``-import_from`` of a clause-less
``-dynamic`` predicate: the IMPORT wins, in both eras.

``todo/done/field-named-export-of-an-imported-dynamic-splits-identity-2026-09-24.md``
(operator ruling 2026-09-24, option A).  Before: the export entry
``d(STATUS, NOTES)`` (no local clauses) was taken for a DATA functor and
bound the ATOM, so ``assertz`` through the importer went to a row neither
module read -- silently.  Against a DEFINING exporter the import already won.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

_OWNER = """\
-dynamic(fdx_verdict/2)
-module({o}, [fdx_verdict(STATUS, CITATIONS)])
"""

_USER = """\
-module({u}, [fdx_verdict({spec}), rx_add(S), rx_chk(R)])
-import_from({o}, [fdx_verdict])
rx_add(S) <- assertz(fdx_verdict(S, []))
rx_chk(R) <- fdx_verdict(R, C_UNUSED)
"""


def _bind_imports_as_owner_handles(monkeypatch, owner_name, owner_db):
    """The handle era for ``-import_from`` (ruling D1): every name the import
    bound to the owner's class is re-bound to the owner's handle."""
    import clausal.logic.compiler_v2 as cv
    orig = cv._process_imports
    seen = []

    def flipped(items, module_dict, db=None):
        orig(items, module_dict, db)
        for k, v in list(module_dict.items()):
            if (isinstance(v, PredicateMeta) and v._row is not None
                    and v._row._db is owner_db):
                module_dict[k] = mangle(owner_name, v._row._key[0])
                seen.append(k)

    monkeypatch.setattr(cv, "_process_imports", flipped)
    return seen


def _load(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"
    p.write_text(textwrap.dedent(src))
    return _load_module(name, str(p))


def _answers(lm, name):
    r = Var()
    return sorted(deref(r) for _ in call(name, r, module=lm))


@pytest.mark.parametrize("spec", ["STATUS, CITATIONS", "S, NOTES"],
                         ids=["same-fields", "other-fields"])
@pytest.mark.parametrize("era", ["class", "handle"])
def test_the_import_wins_over_a_field_named_export(
        tmp_path, monkeypatch, era, spec):
    monkeypatch.syspath_prepend(str(tmp_path))
    tag = f"{era}_{'s' if spec.startswith('STATUS') else 'o'}"
    o, u = f"fdx_own_{tag}", f"fdx_use_{tag}"
    try:
        owner = _load(tmp_path, o, _OWNER.format(o=o))
        om = owner.__dict__["$module"]
        seen = []
        if era == "handle":
            seen = _bind_imports_as_owner_handles(monkeypatch, o, om.db)
        user = _load(tmp_path, u, _USER.format(o=o, u=u, spec=spec))
        um = user.__dict__["$module"]
        binding = user.__dict__["fdx_verdict"]
        if era == "handle":
            assert "fdx_verdict" in seen, "the handle era did not engage"
            assert binding == mangle(o, "fdx_verdict")
        else:
            assert binding is owner.__dict__["fdx_verdict"], binding
        assert next(call("rx_add", "ok", module=um), None) is not None
        assert _answers(um, "rx_chk") == ["ok"]
        x, y = Var(), Var()
        assert [deref(x) for _ in call("fdx_verdict", x, y, module=om)] == ["ok"]
    finally:
        sys.modules.pop(u, None)
        sys.modules.pop(o, None)


def test_a_field_named_export_at_another_arity_is_still_local_data(tmp_path, monkeypatch):
    """Only an import AT THE ENTRY'S ARITY wins; a mismatched one leaves the
    entry the module's own data functor, as before."""
    monkeypatch.syspath_prepend(str(tmp_path))
    o, u = "fdx_own_ar", "fdx_use_ar"
    try:
        _load(tmp_path, o, _OWNER.format(o=o))
        user = _load(tmp_path, u, (
            f"-module({u}, [fdx_verdict(A, B, C)])\n"
            f"-import_from({o}, [fdx_verdict])\n"))
        assert user.__dict__["fdx_verdict"] == "fdx_verdict"
    finally:
        sys.modules.pop(u, None)
        sys.modules.pop(o, None)
