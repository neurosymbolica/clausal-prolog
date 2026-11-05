"""The vetted package adapter: clausal-sympy admitted to the sandbox
(operator ruling 2026-11-04, "vetted package: yes"; design
``implementation_plans/sympy-package-adapter-sandbox-2026-11-04.md``).

Every scenario runs in a fresh interpreter (the sandbox is irreversible),
through ``tests/test_sandbox.py``'s harness.  The child splices
``packages/clausal-sympy`` onto ``clausal.modules.py`` the way
``packages/conftest.py`` does, then turns the sandbox on.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap

import importlib.util

import pytest

# Never IMPORTED here: SymPy's own Predicate classes would stay alive in
# the pytest process (tests/test_w4b3_rewriter_mints_no_class.py counts
# live classes of that name).  Every scenario imports it in its child.
if importlib.util.find_spec("sympy") is None:
    pytest.skip("sympy is not installed", allow_module_level=True)

from tests.test_sandbox import (  # noqa: E402
    ENGINE_ROOT, LOAD, PYMOD, PYOBJ, _Sandbox, ok, refused)

PKG = os.path.join(ENGINE_ROOT, "packages", "clausal-sympy")
PKG_PY = os.path.join(PKG, "clausal", "modules", "py")
TIME_LIMIT = "time_limit_exceeded"


def splice(pkg_py: str = PKG_PY) -> str:
    """Child code: the package's adapter directory on the namespace."""
    return (f"        import clausal.modules.py as _cmp\n"
            f"        _cmp.__path__.insert(1, {pkg_py!r})\n")


@pytest.fixture
def sbx(tmp_path):
    return _Sandbox(tmp_path / "proj")


def ball(res, name):
    r = res[name]
    assert not r["ok"], (name, r)
    assert r["term"] == TIME_LIMIT, (name, r)
    return r


IMPORTER = """
-module(phys, [roots/1, inverse/1, simp/2, payload/1, forward/2, quick/1])
# simplify is also a name the runtime binds, which an import may not
# shadow: it is imported under another name.
-import_from(py.sympy, [solve, alias(simplify, sym_simplify), sym_str])
roots(R) <- solve(X**2 - 4, X, R)
quick(R) <- solve(X**2 - 9, X, R)
inverse(R) <- solve((X - 10) * (X - 3) * (X + 7), X, R)
simp(E, R) <- sym_simplify(E, R)
payload(R) <- sym_str(["__import__('os').system('touch PWNED')"], R)
forward(X, Y) <- sym_simplify(X * 3 + X, Y)
"""

SLOW = """
-module(slow, [lmtd_backwards/1, plain/1])
-import_from(py.sympy, [solve_all])
-import_from(py.units, [kelvin])
# The log mean temperature difference solved backwards with float data:
# SymPy offers LambertW candidates and works on them for minutes.
lmtd_backwards(ROOTS) <- solve_all(
    (X - 12.34(kelvin)) / log(X / 12.34(kelvin)) - 18.20(kelvin), X, ROOTS)
plain(R) <- solve_all(X**2 - 2, X, R)
"""


def _enable(extra: str = "") -> str:
    return ("        import clausal.sandbox as sb\n"
            f"        sb.enable(allow_package_adapters=['sympy']{extra})\n")


# ── the pins ────────────────────────────────────────────────────────────────


def test_the_pins_bind_the_files_on_disk():
    """The table's sha256 pins are the files' current content.  When a pinned
    file changes, re-pin it: this test prints the row's new values (see
    docs/sandbox.md, "Re-pinning a vetted package adapter": the change needs
    engine review and a CHANGELOG entry)."""
    import importlib.metadata as md
    from clausal.sandbox import PACKAGE_ADAPTERS
    row = PACKAGE_ADAPTERS["sympy"]
    want = {}
    for module, _sha in row.files:
        rel = module.split(".")[-1] + ".py"
        with open(os.path.join(PKG_PY, rel), "rb") as f:
            want[module] = hashlib.sha256(f.read()).hexdigest()
    versions = {d: md.version(d) for d, _v, _top in row.third_party}
    print("\nPACKAGE_ADAPTERS['sympy'] pins for the files on disk:")
    for module, sha in want.items():
        print(f"    ({module!r}, {sha!r}),")
    for d, v in versions.items():
        print(f"    {d}=={v} (installed)")
    assert dict(row.files) == want, (
        "a pinned clausal-sympy file changed: review the change, then copy "
        "the values printed above into clausal/sandbox.py PACKAGE_ADAPTERS "
        "with a CHANGELOG entry")
    assert {d: v for d, v, _t in row.third_party} == versions
    assert "sym" not in row.predicates and "inf" not in row.predicates
    assert not (row.predicates & {"pi", "e", "inf", "sin", "log", "exp"})


# ── admitted ────────────────────────────────────────────────────────────────


def test_inverse_solve_returns_every_root_under_the_sandbox(sbx):
    sbx.write("phys.seam", IMPORTER)
    res = sbx.run(splice() + _enable() + """
        from clausal import Var
        phys = load("phys")
        R = Var()
        probe("roots", lambda: sorted(answers(("roots", R), phys, R)))
        probe("inverse", lambda: sorted(answers(("inverse", R), phys, R)))
        probe("forward", lambda: answers(("forward", 2, R), phys, R))
        probe("budget", lambda: sb.package_adapter_time_limit())
    """)
    assert ok(res, "budget") == "15.0"
    assert ok(res, "roots") == "[-2, 2]"
    assert ok(res, "inverse") == "[-7, 3, 10]"
    assert ok(res, "forward") == "[8]"


def test_a_clausal_domain_reaches_sympy_through_a_python_free_seam(sbx):
    sbx.write("phys.seam", IMPORTER)
    sbx.write("dom.clausal", """
        :- module(dom, [two/1]).
        :- use_module(phys, [roots/1]).
        two(R) :- roots(R).
        :- end_module(dom).
    """)
    res = sbx.run(splice() + _enable() + """
        from clausal import Var
        dom = load("dom")
        R = Var()
        probe("two", lambda: sorted(answers(("two", R), dom, R)))
    """)
    assert ok(res, "two") == "[-2, 2]"


#: A stand-in for an editable install of clausal-sympy, run at interpreter
#: start (before ``import clausal`` reads the environment): setuptools'
#: editable finder publishes the package's directories in ``NAMESPACES``,
#: which ``clausal/modules/py/__init__.py`` adds to its ``__path__``.
SITECUSTOMIZE = """
import sys, types
mod = types.ModuleType("__editable___clausal_sympy_finder")
mod.NAMESPACES = {"clausal.modules.py": [%r]}
class _Finder:
    @classmethod
    def find_spec(cls, *a, **k):
        return None
_Finder.__module__ = mod.__name__
sys.modules[mod.__name__] = mod
sys.meta_path.append(_Finder)
"""


def test_the_environment_opts_a_child_in(sbx, tmp_path):
    sbx.write("phys.seam", IMPORTER)
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(SITECUSTOMIZE % PKG_PY)
    res = sbx.run("""
        import clausal.sandbox as sb
        from clausal import Var
        probe("on", lambda: sb.is_enabled())
        probe("which", lambda: sorted(sb.allowed_package_adapters()))
        probe("budget", lambda: sb.package_adapter_time_limit())
        phys = load("phys")
        R = Var()
        probe("roots", lambda: sorted(answers(("roots", R), phys, R)))
    """, env={"CLAUSAL_SANDBOX": "1",
              "CLAUSAL_SANDBOX_PACKAGE_ADAPTERS": "sympy",
              "CLAUSAL_SANDBOX_ADAPTER_TIME_LIMIT": "7.5",
              "PYTHONPATH": os.pathsep.join([str(site), ENGINE_ROOT])})
    assert ok(res, "on") == "True"
    assert ok(res, "which") == "['sympy']"
    assert ok(res, "budget") == "7.5"
    assert ok(res, "roots") == "[-2, 2]"


@pytest.mark.parametrize("value", ["scipy_special", "sympy,os"])
def test_the_environment_names_only_vetted_adapters(sbx, value):
    res = sbx.run(splice() + """
        import clausal
    """, env={"CLAUSAL_SANDBOX": "1",
              "CLAUSAL_SANDBOX_PACKAGE_ADAPTERS": value}, check=False)
    assert "is not a vetted package adapter" in res["__stderr__"], res


def test_the_environment_variable_without_the_sandbox_is_an_error(sbx):
    res = sbx.run("        import clausal\n", env={
        "CLAUSAL_SANDBOX_PACKAGE_ADAPTERS": "sympy"}, check=False)
    assert "CLAUSAL_SANDBOX_PACKAGE_ADAPTERS" in res["__stderr__"], res


# ── refused ─────────────────────────────────────────────────────────────────


def test_without_the_opt_in_sympy_stays_refused(sbx):
    sbx.write("phys.seam", IMPORTER)
    res = sbx.run(splice() + """
        import clausal.sandbox as sb
        sb.enable()
        probe("load", lambda: load("phys"))
    """)
    r = refused(res, "load", LOAD, import_error=True)
    assert "py_adapter" in r["msg"]


def test_the_eval_payload_is_refused_inside_and_outside_the_sandbox(sbx):
    sbx.write("phys.seam", IMPORTER)
    body = """
        from clausal import Var
        phys = load("phys")
        R = Var()
        probe("payload", lambda: answers(("payload", R), phys, R))
        probe("ran", lambda: os.path.exists("PWNED"))
    """
    inside = sbx.run(splice() + _enable() + body)
    outside = sbx.run(splice() + body)
    for res in (inside, outside):
        assert ok(res, "ran") == "False"
        r = res["payload"]
        assert (r.get("value") == "[]"
                or "type_error" in (r.get("term") or "")), r


@pytest.mark.parametrize("name", ["sym", "inf", "pi", "sin", "latex"])
def test_an_unlisted_name_is_refused(sbx, name):
    sbx.write("good.seam", """
        -module(good, [t/1])
        -import_from(py.sympy, [expand])
        t(R) <- expand(1 + 1, R)
    """)
    sbx.write("bad.seam", f"""
        -module(bad, [t/1])
        -import_from(py.sympy, [expand, {name}])
        t(R) <- expand(1 + 1, R)
    """)
    res = sbx.run(splice() + _enable() + """
        probe("good", lambda: load("good"))
        probe("load", lambda: load("bad"))
    """)
    assert res["good"]["ok"], res["good"]
    r = refused(res, "load", LOAD, import_error=True)
    assert "py_adapter" in r["msg"], r


def test_the_dotted_route_is_refused(sbx):
    sbx.write("bad.seam", """
        -module(bad, [t/1])
        -import_from(py.sympy, [expand])
        t(R) <- py.sympy.expand((X + 1) ** 2, R)
    """)
    res = sbx.run(splice() + _enable() + """
        probe("load", lambda: load("bad"))
    """)
    r = refused(res, "load", LOAD, import_error=True)
    assert "py_adapter" in r["msg"], r


def test_import_module_is_refused(sbx):
    sbx.write("bad.seam", """
        -module(bad, [t/1])
        -import_module(py.sympy)
        t(R) <- sympy.expand(1 + 1, R)
    """)
    res = sbx.run(splice() + _enable() + """
        probe("load", lambda: load("bad"))
    """)
    r = refused(res, "load", LOAD, import_error=True)
    assert "py_adapter" in r["msg"], r


@pytest.mark.parametrize("python,kind", [
    ("t(R) <- (expand(1 + 1, R), ++print(R))", "escape"),
    ("t(R) <- (R is ++len([1, 2]))", "escape"),
    ('q(X) <- expand(X, X)\nt(R) <- (R is f"{++open(\'/etc/passwd\')}")',
     ""),
    ("t(R) <- (expand(1 + 1, R), --member(R, [2]))", "seam"),
])
def test_an_importer_with_python_in_it_is_refused(sbx, python, kind):
    sbx.write("bad.seam", textwrap.dedent("""
        -module(bad, [t/1])
        -import_from(py.sympy, [expand])
    """) + python + "\n")
    res = sbx.run(splice() + _enable() + """
        probe("load", lambda: load("bad"))
    """)
    r = refused(res, "load", LOAD, import_error=True)
    assert kind in r["msg"], r


def test_other_package_adapters_stay_refused(sbx):
    scipy_py = os.path.join(ENGINE_ROOT, "packages", "clausal-scipy",
                            "clausal", "modules", "py")
    sbx.write("bad.seam", """
        -module(bad, [t/1])
        -import_from(py.scipy_special, [gamma])
        t(R) <- gamma(5, R)
    """)
    res = sbx.run(splice() + splice(scipy_py) + _enable() + """
        probe("load", lambda: load("bad"))
        probe("enable", lambda: sb.enable(
            allow_package_adapters=["scipy_special"]))
    """)
    refused(res, "load", LOAD, import_error=True)
    assert not res["enable"]["ok"]
    assert "not a vetted package adapter" in res["enable"]["msg"]


def test_check_term_refuses_a_symexpr_passed_in_through_solve(sbx):
    sbx.write("phys.seam", IMPORTER)
    res = sbx.run(splice() + _enable() + """
        from clausal import Var, solve
        from clausal.logic.variables import deref
        phys = load("phys")
        def leak():
            X, R = Var(), Var()
            for _ in solve(("simp", ("*", X, X), R), module=phys):
                return type(deref(R)).__name__, deref(R)
        R = Var()
        probe("kind", lambda: leak()[0])
        expr = leak()[1]
        probe("back_in", lambda: answers(("simp", expr, R), phys, R))
    """)
    assert ok(res, "kind") == "'SymExpr'"
    refused(res, "back_in", PYOBJ)


def test_an_unlisted_importer_is_refused(sbx):
    sbx.write("phys.seam", IMPORTER)
    other = sbx.write("other.seam", "-module(other, [])\n")
    res = sbx.run(splice() + f"""
        import clausal.sandbox as sb
        sb.enable(allow_package_adapters=[
            {{"name": "sympy", "importers": [{str(other)!r}]}}])
        probe("load", lambda: load("phys"))
    """)
    r = refused(res, "load", LOAD, import_error=True)
    assert "not an importer" in r["msg"], r


def test_a_listed_importer_with_its_pin_loads(sbx):
    p = sbx.write("phys.seam", IMPORTER)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    res = sbx.run(splice() + f"""
        import clausal.sandbox as sb
        from clausal import Var
        sb.enable(allow_package_adapters=[
            {{"name": "sympy", "importers": [
                {{"path": {str(p)!r}, "sha256": {sha!r}}}]}}])
        phys = load("phys")
        R = Var()
        probe("roots", lambda: sorted(answers(("roots", R), phys, R)))
    """)
    assert ok(res, "roots") == "[-2, 2]"


# ── verification at enable(), failing closed ────────────────────────────────


def _copy_package(tmp_path):
    dst = tmp_path / "clausal-sympy"
    shutil.copytree(PKG, dst, ignore=shutil.ignore_patterns(
        "__pycache__", "tests", "docs"))
    return dst


def _refused_enable(res, reason):
    r = res["enable"]
    assert not r["ok"], r
    assert r["type"] == "PackageAdapterError", r
    assert f"[{reason}]" in r["msg"], r
    assert ok(res, "on") == "False"
    return r


def test_one_changed_byte_in_the_units_helper_refuses(sbx, tmp_path):
    dst = _copy_package(tmp_path)
    f = dst / "clausal" / "modules" / "py" / "_sympy_units.py"
    data = bytearray(f.read_bytes())
    data[-2] = ord(" ") if data[-2] != ord(" ") else ord("\t")
    f.write_bytes(bytes(data))
    res = sbx.run(splice(str(dst / "clausal" / "modules" / "py")) + """
        import clausal.sandbox as sb
        probe("enable", lambda: sb.enable(allow_package_adapters=["sympy"]))
        probe("on", lambda: sb.is_enabled())
        probe("imported", lambda: "clausal.modules.py._sympy_units"
              in sys.modules or "sympy" in sys.modules)
    """)
    r = _refused_enable(res, "sha256_mismatch")
    assert "_sympy_units.py" in r["msg"]
    assert ok(res, "imported") == "False"


def test_a_changed_adapter_file_refuses(sbx, tmp_path):
    dst = _copy_package(tmp_path)
    f = dst / "clausal" / "modules" / "py" / "sympy.py"
    f.write_text(f.read_text() + "\nsym_str = simplify\n")
    res = sbx.run(splice(str(dst / "clausal" / "modules" / "py")) + """
        import clausal.sandbox as sb
        probe("enable", lambda: sb.enable(allow_package_adapters=["sympy"]))
        probe("on", lambda: sb.is_enabled())
    """)
    _refused_enable(res, "sha256_mismatch")


def test_a_wrong_package_version_refuses(sbx, tmp_path):
    dst = _copy_package(tmp_path)
    pp = dst / "pyproject.toml"
    pp.write_text(pp.read_text().replace('version = "0.1.0"',
                                         'version = "0.1.1"'))
    res = sbx.run(splice(str(dst / "clausal" / "modules" / "py")) + """
        import clausal.sandbox as sb
        probe("enable", lambda: sb.enable(allow_package_adapters=["sympy"]))
        probe("on", lambda: sb.is_enabled())
    """)
    _refused_enable(res, "version_mismatch")


def _fake_dist(root, name, version, record_lines=()):
    d = root / f"{name}-{version}.dist-info"
    d.mkdir(parents=True)
    (d / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    (d / "RECORD").write_text("".join(f"{ln},,\n" for ln in record_lines))
    return d


def test_a_wrong_sympy_version_refuses(sbx, tmp_path):
    site = tmp_path / "fake_site"
    _fake_dist(site, "sympy", "1.13.0", ["sympy/__init__.py"])
    res = sbx.run(f"        sys.path.insert(0, {str(site)!r})\n" + splice() + """
        import clausal.sandbox as sb
        probe("enable", lambda: sb.enable(allow_package_adapters=["sympy"]))
        probe("on", lambda: sb.is_enabled())
    """)
    r = _refused_enable(res, "version_mismatch")
    assert "sympy" in r["msg"] and "1.13.0" in r["msg"]


def test_a_dist_info_for_another_sympy_refuses(sbx, tmp_path):
    """The metadata says 1.14.0, but it does not describe the sympy package
    the adapter would import (its RECORD lists no file of it)."""
    import importlib.metadata as md
    site = tmp_path / "fake_site"
    _fake_dist(site, "sympy", md.version("sympy"), ["elsewhere/__init__.py"])
    res = sbx.run(f"        sys.path.insert(0, {str(site)!r})\n" + splice() + """
        import clausal.sandbox as sb
        probe("enable", lambda: sb.enable(allow_package_adapters=["sympy"]))
        probe("on", lambda: sb.is_enabled())
    """)
    _refused_enable(res, "distribution_mismatch")


@pytest.mark.parametrize("name", ["clausal.modules.py.sympy",
                                  "clausal.modules.py._sympy_units",
                                  "sympy", "mpmath"])
def test_an_impostor_in_sys_modules_refuses(sbx, name):
    res = sbx.run(splice() + f"""
        import types
        fake = types.ModuleType({name!r})
        fake.__file__ = os.path.join(os.getcwd(), "impostor.py")
        sys.modules[{name!r}] = fake
        import clausal.sandbox as sb
        probe("enable", lambda: sb.enable(allow_package_adapters=["sympy"]))
        probe("on", lambda: sb.is_enabled())
    """)
    _refused_enable(res, "impostor_module")


def test_a_second_enable_only_narrows(sbx):
    sbx.write("phys.seam", IMPORTER)
    res = sbx.run(splice() + """
        import clausal.sandbox as sb
        from clausal import Var
        sb.enable(allow_package_adapters=["sympy"],
                  package_adapter_time_limit=5)
        phys = load("phys")
        R = Var()
        probe("before", lambda: sorted(answers(("roots", R), phys, R)))
        probe("longer", lambda: sb.enable(package_adapter_time_limit=50))
        probe("shorter", lambda: sb.enable(package_adapter_time_limit=2))
        probe("budget", lambda: sb.package_adapter_time_limit())
        sb.enable(allow_package_adapters=[])
        probe("after", lambda: answers(("roots", R), phys, R))
        probe("widen", lambda: sb.enable(allow_package_adapters=["sympy"]))
    """)
    assert ok(res, "before") == "[-2, 2]"
    assert not res["longer"]["ok"]
    assert res["longer"]["type"] == "PermissionError"
    assert ok(res, "budget") == "2.0"
    refused(res, "after", PYMOD)
    assert not res["widen"]["ok"]
    assert res["widen"]["type"] == "PermissionError"


def test_a_package_adapter_cannot_be_added_by_a_second_enable(sbx):
    res = sbx.run(splice() + """
        import clausal.sandbox as sb
        sb.enable()
        probe("widen", lambda: sb.enable(allow_package_adapters=["sympy"]))
    """)
    assert not res["widen"]["ok"]
    assert res["widen"]["type"] == "PermissionError"


# ── the per-call time budget ────────────────────────────────────────────────


def test_a_slow_call_throws_time_limit_exceeded_within_its_budget(sbx):
    sbx.write("slow.seam", SLOW)
    sbx.write("phys.seam", IMPORTER)
    res = sbx.run(splice() + _enable(", package_adapter_time_limit=2") + """
        import time
        from clausal import Var
        slow = load("slow")
        phys = load("phys")
        R = Var()
        t = time.monotonic()
        probe("slow", lambda: answers(("lmtd_backwards", R), slow, R))
        RES["elapsed"] = time.monotonic() - t
        probe("caught", lambda: answers(
            ("catch", ("lmtd_backwards", R), "time_limit_exceeded",
             ("=", R, "timed_out")), slow, R))
        probe("again", lambda: sorted(answers(("quick", R), phys, R)))
        probe("plain", lambda: answers(("plain", R), slow, R))
        import signal
        probe("timer", lambda: signal.getitimer(signal.ITIMER_REAL))
        probe("handler", lambda: signal.getsignal(signal.SIGALRM))
        from clausal.logic import time_limit
        probe("live", lambda: time_limit.live())
    """)
    ball(res, "slow")
    assert res["elapsed"] < 2 + 1.5, res["elapsed"]
    assert ok(res, "caught") == "['timed_out']"
    assert ok(res, "again") == "[-3, 3]"
    assert ok(res, "plain") == "[[-sqrt(2), sqrt(2)]]"
    assert ok(res, "timer") == "(0.0, 0.0)"
    assert ok(res, "handler") == "<Handlers.SIG_DFL: 0>"
    assert ok(res, "live") == "()"


def test_an_outer_limit_still_fires_through_the_budget(sbx):
    """call_with_time_limit/2 around a budgeted call: the shorter of the two
    wins, and the outer one's ball is the outer one's."""
    sbx.write("slow.seam", SLOW)
    res = sbx.run(splice() + _enable(", package_adapter_time_limit=30") + """
        import time
        from clausal import Var
        slow = load("slow")
        R = Var()
        t = time.monotonic()
        probe("outer", lambda: answers(
            ("call_with_time_limit", 1, ("lmtd_backwards", R)), slow, R))
        RES["elapsed"] = time.monotonic() - t
    """)
    ball(res, "outer")
    assert res["elapsed"] < 1 + 1.5, res["elapsed"]


def test_the_budget_is_off_outside_the_sandbox(monkeypatch):
    """Outside the sandbox no package adapter call is budgeted."""
    from clausal.logic import time_limit
    from clausal.modules.py import ModulePredicate, simple_to_trampoline
    from clausal import call, Var
    pushed = []
    monkeypatch.setattr(time_limit, "new",
                        lambda *a, **k: pushed.append(a))
    monkeypatch.setattr(time_limit, "push",
                        lambda *a, **k: pushed.append(a))

    def _f(x, trail, k):
        yield None
    p = ModulePredicate("f")
    p._register(1, simple_to_trampoline(_f))
    assert list(call(p, Var())) and pushed == []


def test_a_budget_off_the_main_thread_is_refused(sbx):
    sbx.write("phys.seam", IMPORTER)
    res = sbx.run(splice() + _enable() + """
        import threading
        from clausal import Var
        phys = load("phys")
        R = Var()
        out = {}
        def run():
            try:
                out["v"] = answers(("roots", R), phys, R)
            except BaseException as e:
                out["e"] = _render(e)
        th = threading.Thread(target=run); th.start(); th.join()
        RES["thread"] = out
    """)
    assert res["thread"].get("e", "").startswith(
        "error(system_error(time_limit_not_main_thread)"), res["thread"]


def test_no_budget_runs_off_the_main_thread(sbx):
    sbx.write("phys.seam", IMPORTER)
    res = sbx.run(splice() + _enable(", package_adapter_time_limit=None") + """
        import threading
        from clausal import Var
        phys = load("phys")
        R = Var()
        out = {}
        def run():
            out["v"] = sorted(answers(("roots", R), phys, R))
        th = threading.Thread(target=run); th.start(); th.join()
        RES["thread"] = out
    """)
    assert res["thread"] == {"v": [-2, 2]}
