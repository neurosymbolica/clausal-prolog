"""module_constant/3: reflect on a module's OWN -constants declarations.

Registration happens in the -constants lowering itself
(EmbedTransformer._handle_constants_directive -> $register_module_constant,
clausal/logic/constants.py) — see tests/test_constants.py for the
declaration/folding side. This file covers the reflection builtin's modes
and the imported-constants-are-NOT-reflected-on-the-importer decision.
"""
import textwrap
import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tmc_{name}", str(path))


def test_lookup_module_and_name_bound(tmp_path):
    _load(tmp_path, "owner1", "-constant_value(c_pi, 3.14159)\n")
    m = _load(tmp_path, "user1", """
        -double_quotes(atom)
        -import_module(tmc_owner1)
        got(X) <- module_constant(tmc_owner1, "c_pi", X)
    """)
    v = Var()
    assert [deref(v) for _ in call("got", v, module=m.__dict__["$module"])] == \
        [3.14159]


def test_lookup_missing_name_fails(tmp_path):
    _load(tmp_path, "owner2", "-constant_value(c_pi, 3.14159)\n")
    m = _load(tmp_path, "user2", """
        -double_quotes(atom)
        -import_module(tmc_owner2)
        got(X) <- module_constant(tmc_owner2, "c_nope", X)
    """)
    v = Var()
    assert list(call("got", v, module=m.__dict__["$module"])) == []


def test_check_mode_true_and_false(tmp_path):
    _load(tmp_path, "owner3", "-constant_value(c_a, 1)\n")
    m = _load(tmp_path, "user3", """
        -double_quotes(atom)
        -import_module(tmc_owner3)
        ok <- module_constant(tmc_owner3, "c_a", 1)
        bad <- module_constant(tmc_owner3, "c_a", 2)
    """)
    module = m.__dict__["$module"]
    assert list(call("ok", module=module))
    assert list(call("bad", module=module)) == []


def test_enumerate_a_modules_constants(tmp_path):
    """(+Module, -Name, ?Value): enumerate."""
    _load(tmp_path, "owner4",
          "-constant_value(c_a, 1)\n-constant_value(c_b, 2)\n")
    m = _load(tmp_path, "user4", """
        -import_module(tmc_owner4)
        got(N, V) <- module_constant(tmc_owner4, N, V)
    """)
    n, v = Var(), Var()
    results = sorted(
        (deref(n), deref(v))
        for _ in call("got", n, v, module=m.__dict__["$module"])
    )
    # THE FLIP (spec §6.4): the NAME position answers ATOMS.
    assert results == [(mint("c_a"), 1), (mint("c_b"), 2)]


def test_module_unbound_enumerates_across_loaded_modules(tmp_path):
    """(-Module, +Name, ?Value): the module argument need not be imported —
    module_constant/3 searches every loaded Clausal module."""
    owner = _load(tmp_path, "owner5", "-constant_value(c_unique5, 777)\n")
    m = _load(tmp_path, "user5", """
        -double_quotes(atom)
        find(M, V) <- module_constant(M, "c_unique5", V)
    """)
    mv, vv = Var(), Var()
    results = [(deref(mv), deref(vv))
              for _ in call("find", mv, vv, module=m.__dict__["$module"])]
    assert len(results) == 1
    mod, val = results[0]
    assert mod is owner
    assert val == 777


def test_imported_constant_is_not_reflected_on_the_importer(tmp_path):
    """Decision (2026-08-25): module_constant/3 only reflects a module's
    OWN -constants declarations. An imported constant is reachable through
    its owning module's own module_constant/3, not re-registered on the
    importer — see docs/import.md."""
    _load(tmp_path, "owner6", "-constant_value(c_pi, 3.14159)\n")
    m = _load(tmp_path, "user6", """
        -import_from(tmc_owner6, [c_pi])
        p(X) <- (X is c_pi)
    """)
    assert m.__dict__["$module"].constants == {}


def test_qualified_import_module_constant_also_not_reflected_on_importer(tmp_path):
    _load(tmp_path, "owner7", "-constant_value(c_pi, 3.14159)\n")
    m = _load(tmp_path, "user7", """
        -import_module(tmc_owner7)
        p(X) <- (X is ++(tmc_owner7.c_pi + 0))
    """)
    assert m.__dict__["$module"].constants == {}


def test_reflected_value_is_the_same_frozen_object(tmp_path):
    """The value module_constant/3 yields is the identical object the
    owning module's own clause bodies embed — not a copy."""
    m = _load(tmp_path, "owner8", "-constant_value(c_l, [1, 2, 3])\n")
    v = Var()
    [result] = [deref(v) for _
                in call("module_constant", m, mint("c_l"), v,
                        module=m.__dict__["$module"])]
    assert result is m.__dict__["c_l"]


# ── A module the test runner loads is still a loaded program ─────────────────
#
# ``clausal.testing.load_clausal_module`` compiles a file as
# ``_clausal_test_<stem>`` and pops it from ``sys.modules``; the enumerating
# reflection builtins read ``sys.modules`` alone, so a test's own
# ``constant_value(plain, V)`` FAILED silently for the file's own
# ``-constant_value(plain, 3)`` while a normal import answered ``V = 3``.

_RUNNER_CV_SRC = """\
-module(cvrun, [plain, a/1, b/1])
-constant_value(plain, 3)
a(V) <- constant_value(plain, V)
b(V) <- module_constant(_, plain, V)
test("plain") <- a(3)
test("module unbound") <- b(3)
"""


def test_constant_value_answers_through_the_test_runner(tmp_path, capsys):
    from clausal.testing import main
    path = tmp_path / "cvrun.seam"
    path.write_text(_RUNNER_CV_SRC)
    rc = main([str(path)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "2 passed, 0 failed" in out


def test_constant_value_answers_for_a_load_clausal_module_module(tmp_path):
    from clausal.testing import load_clausal_module
    path = tmp_path / "cvrun2.seam"
    path.write_text(_RUNNER_CV_SRC)
    mod = load_clausal_module(path)
    v = Var()
    assert [deref(v) for _ in call("a", v, module=mod.__dict__["$module"])] \
        == [3]


def test_a_finished_runner_module_stops_answering(tmp_path):
    """The runner unregisters a file's module once its tests have run, so
    one file's constants do not answer another file's queries."""
    from clausal.logic.constants import loaded_clausal_py_modules
    from clausal.testing import run_file
    path = tmp_path / "cvrun3.seam"
    path.write_text(_RUNNER_CV_SRC)
    res = run_file(path)
    assert [r.passed for r in res.results] == [True, True]
    assert not any(getattr(m, "__name__", None) == "_clausal_test_cvrun3"
                   for m in loaded_clausal_py_modules())


def test_same_stem_runner_modules_do_not_evict_each_other(tmp_path):
    """The runner names a module by file STEM; two same-stem files in
    different directories are two programs, and both stay reachable."""
    from clausal.testing import load_clausal_module
    (tmp_path / "d1").mkdir()
    (tmp_path / "d2").mkdir()
    p1 = tmp_path / "d1" / "same.seam"
    p2 = tmp_path / "d2" / "same.seam"
    p1.write_text("-module(same, [k1, a/1])\n-constant_value(k1, 1)\n"
                  "a(V) <- constant_value(k1, V)\n")
    p2.write_text("-module(same, [k2, a/1])\n-constant_value(k2, 2)\n"
                  "a(V) <- constant_value(k2, V)\n")
    m1 = load_clausal_module(p1)
    m2 = load_clausal_module(p2)
    for m, want in ((m1, [1]), (m2, [2])):
        v = Var()
        assert [deref(v) for _ in call("a", v, module=m.__dict__["$module"])] \
            == want


def test_reloading_one_file_does_not_duplicate_answers(tmp_path):
    from clausal.testing import load_clausal_module
    path = tmp_path / "cvrel.seam"
    path.write_text("-module(cvrel, [krel, a/1])\n-constant_value(krel, 7)\n"
                    "a(V) <- constant_value(krel, V)\n")
    first = load_clausal_module(path)       # noqa: F841 -- kept alive
    second = load_clausal_module(path)
    v = Var()
    assert [deref(v) for _ in call("a", v, module=second.__dict__["$module"])] \
        == [7]
