"""The process-wide sandbox (:mod:`clausal.sandbox`, operator ruling D14).

The sandbox is irreversible and process-wide, so every scenario runs in a
fresh interpreter (``_Sandbox.run``): the child builds a project on disk,
turns the sandbox on, loads, queries, and reports each probe's outcome --
the answer, or the exception and its ISO term -- as JSON.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

import clausal

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(
    clausal.__file__)))

LOAD = "permission_error(load,python_escape,"
PYMOD = "permission_error(access,python_module,"
PLMOD = "permission_error(access,prolog_module,"
PYOBJ = "permission_error(access,python_object,"
PRIVATE = "permission_error(access,private_procedure,"

PRELUDE = r'''
import json, os, sys
sys.path.insert(0, os.getcwd())
RES = {}

def _render(e):
    t = getattr(e, "term", None)
    if t is None:
        return None
    from clausal.logic.exceptions import render_error_term
    return render_error_term(t)

def probe(name, fn):
    try:
        v = fn()
        RES[name] = {"ok": True, "value": repr(v)}
    except BaseException as e:
        RES[name] = {"ok": False, "type": type(e).__name__,
                     "term": _render(e), "msg": str(e)[:3000],
                     "import_error": isinstance(e, ImportError)}

def answers(goal, module, var):
    from clausal import solve, deref
    from clausal.logic.variables import walk
    return [walk(deref(var)) for _ in solve(goal, module=module)]

def load(name):
    import importlib
    return importlib.import_module(name)
'''

EPILOGUE = '\nprint("@@RES@@" + json.dumps(RES))\n'


class _Sandbox:
    """A project directory (with a ``pyproject.toml``) and a runner that
    executes a script in a fresh interpreter with the project as cwd."""

    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.pyproject([])

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text).lstrip("\n"))
        return p

    def pyproject(self, bridges):
        self.write("pyproject.toml",
                   "[project]\nname = \"sbx\"\n[tool.clausal]\n"
                   "python_bridges = [" + ", ".join(bridges) + "]\n")

    def run(self, body, *, env=None, check=True) -> dict:
        script = PRELUDE + textwrap.dedent(body) + EPILOGUE
        e = dict(os.environ)
        e.pop("CLAUSAL_SANDBOX", None)
        e["PYTHONPATH"] = ENGINE_ROOT
        e["CLAUSAL_ROOT"] = ENGINE_ROOT
        e["PYTHONDONTWRITEBYTECODE"] = "1"
        e.update(env or {})
        proc = subprocess.run([sys.executable, "-c", script], cwd=self.root,
                              env=e, capture_output=True, text=True,
                              timeout=600)
        out = [ln for ln in proc.stdout.splitlines()
               if ln.startswith("@@RES@@")]
        if check:
            assert out, (proc.returncode, proc.stdout[-3000:],
                         proc.stderr[-3000:])
        res = json.loads(out[-1][len("@@RES@@"):]) if out else {}
        res["__stderr__"] = proc.stderr
        res["__stdout__"] = "\n".join(
            ln for ln in proc.stdout.splitlines()
            if not ln.startswith("@@RES@@"))
        return res


@pytest.fixture
def sbx(tmp_path):
    return _Sandbox(tmp_path / "proj")


def ok(res, name):
    r = res[name]
    assert r["ok"], (name, r)
    return r["value"]


def refused(res, name, term_prefix, *, import_error=None):
    r = res[name]
    assert not r["ok"], (name, r)
    assert r["term"] is not None and r["term"].startswith(
        "error(" + term_prefix), (name, r)
    if import_error is not None:
        assert r["import_error"] is import_error, (name, r)
    return r


# ── the consumer scenario ───────────────────────────────────────────────────

DOMAIN = """
:- module(dom, [eligible/2, deadline/3, span/3, dim/2, fee/2]).
:- use_module(library(datetime), [date_add/3]).
:- use_module(library(units), [dimension_of/2]).
:- use_module(helpers, [adult/1, between_days/3]).
person(bob, 30).
person(ann, 12).
eligible(P, A) :- person(P, A), adult(A).
deadline(D, N, D2) :- date_add(D, N, D2).
span(A, B, N) :- between_days(A, B, N).
dim(Q, D) :- dimension_of(Q, D).
fee(P, F) :- person(P, A), F is A * 2.
:- end_module(dom).
"""

HELPERS = """
-module(helpers, [adult/1, between_days/3])
-import_from(py.datetime, [days_between])
-import_from(units, [compatible_units])
adult(X) <- (X >= 18)
between_days(A, B, N) <- days_between(A, B, N)
"""


def _consumer(sbx):
    sbx.write("dom.clausal", DOMAIN)
    sbx.write("helpers.seam", HELPERS)


def test_the_consumer_scenario_works_in_the_sandbox(sbx):
    """A .clausal domain over Python-free .seam helpers, library(datetime)
    and library(units), queried with goals built as in-memory terms (as a
    worker builds them from validated JSON)."""
    _consumer(sbx)
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var, Quantity
        import clausal.modules.units as U
        probe("on", lambda: sb.is_enabled())
        dom = load("dom")
        X, Y = Var(), Var()
        probe("eligible", lambda: answers(("eligible", X, Y), dom, X))
        probe("deadline", lambda: answers(
            ("deadline", ("date", 2024, 2, 28), ("timedelta", 2, 0, 0), X),
            dom, X))
        probe("span", lambda: answers(
            ("span", ("date", 2024, 3, 1), ("date", 2024, 1, 1), X), dom, X))
        probe("dim", lambda: answers(("dim", U.metre(7), X), dom, X))
        probe("fee", lambda: answers(("fee", "ann", X), dom, X))
        probe("json_like", lambda: answers(
            ("eligible", "bob", 30), dom, X))
    """)
    assert ok(res, "on") == "True"
    assert ok(res, "eligible") == "['bob']"
    assert ok(res, "deadline") == "[('date', 2024, 3, 1)]"
    assert ok(res, "span") == "[60]"
    assert "metre" in ok(res, "dim")
    assert ok(res, "fee") == "[24]"
    assert ok(res, "json_like") != "[]"


# ── LOAD: every route kind of the audit, loaded directly ────────────────────


def _bridge_fixtures():
    from tests.test_python_bridges import EXPLOITS, ROUTE_SEAMS
    return ROUTE_SEAMS, EXPLOITS


SPLICE = """
import clausal.modules.py as _pyns
_d = os.path.join(os.getcwd(), "_splice")
os.makedirs(_d, exist_ok=True)
open(os.path.join(_d, "pbfake.py"), "w").write("value = 42\\n")
_pyns.__path__.append(_d)
"""


def _exploit_body(sources: dict, prefix: str) -> str:
    """Each source written as its own module, imported directly (by Python)
    in the sandbox; and once more through a .clausal importer."""
    return SPLICE + f"""
import clausal.sandbox as sb
sb.enable()
SOURCES = {sources!r}
for name, src in SOURCES.items():
    mod = "{prefix}_" + name
    open(mod + ".seam", "w").write(src.replace("@", "{prefix}_"))
    probe("direct:" + name, lambda mod=mod: load(mod))
open("{prefix}_lib.seam", "w").write("-module({prefix}_lib, [p/1, __dict__])\\np(1),\\n")
"""


def test_every_seam_route_kind_is_refused_at_load(sbx):
    route_seams, _ = _bridge_fixtures()
    res = sbx.run(_exploit_body(route_seams, "rk"))
    assert set(route_seams) <= {k.split(":", 1)[1] for k in res
                                if k.startswith("direct:")}
    for kind in route_seams:
        r = refused(res, "direct:" + kind, LOAD, import_error=True)
        assert "rk_" in r["term"], r


def test_every_bridge_exploit_is_still_refused_in_the_sandbox(sbx):
    """Every exploit of every review round of the Python-bridge gate,
    loaded DIRECTLY by Python (no .clausal importer, which is what the
    bridge gate needs) in the sandbox: all refused at load."""
    _, exploits = _bridge_fixtures()
    assert len(exploits) >= 30
    res = sbx.run(_exploit_body(exploits, "ex"))
    for name in exploits:
        r = res["direct:" + name]
        if r["type"] == "SyntaxError":
            # The compiler itself refuses it (an underscore-led attribute),
            # before the audit sees a tree.
            assert not r["ok"], (name, r)
            continue
        refused(res, "direct:" + name, LOAD, import_error=True)


def test_the_same_exploits_from_a_clausal_importer(sbx):
    _, exploits = _bridge_fixtures()
    body = SPLICE + """
import clausal.sandbox as sb
sb.enable()
"""
    for name, src in exploits.items():
        m = f"cx_{name}"
        sbx.write(f"cx_{name}_helper.seam",
                  src.replace("@", f"cx_{name}_"))
        sbx.write(f"{m}.clausal",
                  f":- module({m}, [t/1]).\n"
                  f":- use_module(cx_{name}_helper, [v/1]).\n"
                  f"t(X) :- v(X).\n:- end_module({m}).\n")
        body += f"probe({name!r}, lambda: load({m!r}))\n"
    res = sbx.run(body)
    for name in exploits:
        r = res[name]
        # Refused at load: by the bridge gate of the .clausal's use_module
        # (a SyntaxError naming python_bridge), the compiler, or the
        # sandbox's own audit.
        assert not r["ok"], (name, r)
        assert r["type"] in ("SyntaxError", "SandboxLoadError"), (name, r)
        assert ("python_bridge" in r["msg"] or "python_escape" in r["msg"]
                or "qualified name" in r["msg"]), (name, r)


def test_a_clean_seam_loads_and_an_allowed_adapter_import_is_fine(sbx):
    sbx.write("clean.seam", "-module(clean, [p/1, d/3])\n"
              "-import_from(py.datetime, [date_add])\n"
              "-import_from(clausal.library.re, [match])\n"
              "p(1),\np(2),\n"
              "d(A, N, B) <- date_add(A, N, B)\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        m = load("clean")
        X = Var()
        probe("p", lambda: answers(("p", X), m, X))
    """)
    assert ok(res, "p") == "[1, 2]"


@pytest.mark.parametrize("imports", [
    "-import_from(py.os, [pid])",
    "-import_from(clausal.modules.py.process, [shell])",
    "-import_from(clausal.library.py_os, [pid])",
    "-import_module(py.files)",
    "-import_from(py.datetime, [now])",
    "-import_from(clausal.library.datetime, [today])",
    "-import_from(clausal.sandbox, [enable])",
    "-import_from(clausal.examples.hello_world, [greeting])",
])
def test_a_seam_reaching_a_denied_engine_module_is_refused(sbx, imports):
    """Engine-shipped is not enough in the sandbox: the adapter (or the
    predicate) must be on the allowlist, and no other engine module may be
    imported."""
    sbx.write("bad.seam", f"-module(bad, [p/1])\n{imports}\np(1),\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        probe("load", lambda: load("bad"))
    """)
    refused(res, "load", LOAD, import_error=True)


# ── LOAD: .pl and .clausal ──────────────────────────────────────────────────


PL_PY = """
:- module(plpy, [p/1]).
:- use_module(py/os, [pid/1]).
p(X) :- pid(X).
"""

PL_CLEAN = """
:- module(plclean, [q/1]).
q(X) :- member(X, [1, 2, 3]).
"""

PL_ALLOWED = """
:- module(plok, [d/3]).
:- use_module(py/datetime, [date_add/3]).
d(A, N, B) :- date_add(A, N, B).
"""


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_a_pl_py_import_is_refused_unless_the_adapter_is_allowed(
        sbx, frontend):
    sbx.write("plpy.pl", PL_PY)
    sbx.write("plclean.pl", PL_CLEAN)
    sbx.write("plok.pl", PL_ALLOWED)
    sbx.write("plusr.pl", ":- module(plusr, [p/1]).\n"
              ":- use_module(usrpy, [f/1]).\np(X) :- f(X).\n")
    sbx.write("usrpy.py", "import os\nopen('RAN', 'w').write('x')\n"
              "f = None\n")
    # A .pl module is no query frame in the sandbox: a .seam wrapper asks.
    sbx.write("plwrap.seam", "-module(plwrap, [qq/1, dd/3])\n"
              "-import_from(plclean, [q])\n-import_from(plok, [d])\n"
              "qq(X) <- q(X)\ndd(A, N, B) <- d(A, N, B)\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        X = Var()
        probe("plpy", lambda: load("plpy"))
        probe("plusr", lambda: load("plusr"))
        probe("ran", lambda: os.path.exists("RAN"))
        w = load("plwrap")
        probe("plclean", lambda: answers(("qq", X), w, X))
        probe("plok", lambda: answers(
            ("dd", ("date", 2020, 1, 1), ("timedelta", 1, 0, 0), X), w, X))
    """, env={"CLAUSAL_PL_FRONTEND": frontend})
    refused(res, "plpy", LOAD, import_error=True)
    refused(res, "plusr", LOAD, import_error=True)
    # The user's Python module was never imported: nothing of it ran.
    assert ok(res, "ran") == "False"
    assert ok(res, "plclean") == "[1, 2, 3]"
    assert ok(res, "plok") == "[('date', 2020, 1, 2)]"


@pytest.mark.parametrize("frontend, suffix, text", [
    ("translator", ".pl", ":- module(pk, [t/1]).\n"
                          ":- use_module(usrpkg/m, [f/1]).\nt(X) :- f(X).\n"),
    ("native", ".pl", ":- module(pk, [t/1]).\n"
                      ":- use_module(usrpkg/m, [f/1]).\nt(X) :- f(X).\n"),
    ("native", ".clausal", ":- module(pk, [t/1]).\n"
                           ":- use_module(usrpkg/m, [f/1]).\n"
                           "t(X) :- f(X).\n:- end_module(pk).\n"),
    ("native", ".seam", "-module(pk, [t/1])\n-import_from(usrpkg.m, [f])\n"
                        "t(X) <- f(X)\n"),
    ("native", ".seam", "-module(pk, [t/1])\n-import_from(usrpkg.c, [f])\n"
                        "t(X) <- f(X)\n"),
    # Security review round 2 (High): a namespace package above it.
    ("native", ".seam", "-module(pk, [t/1])\n"
                        "-import_from(nsx.usrpkg.c, [f])\nt(X) <- f(X)\n"),
    ("native", ".pl", ":- module(pk, [t/1]).\n"
                      ":- use_module(nsx/usrpkg/d, [f/1]).\nt(X) :- f(X).\n"),
    ("translator", ".pl", ":- module(pk, [t/1]).\n"
                          ":- use_module(nsx/usrpkg/d, [f/1]).\n"
                          "t(X) :- f(X).\n"),
])
def test_a_python_package_s_init_never_runs(sbx, frontend, suffix, text):
    """Security review round 1 (High): resolving ``usrpkg/m`` imported the
    parent package -- running its ``__init__.py`` -- before the gate
    refused.  Nothing is imported to resolve a name in the sandbox, and a
    Clausal module inside a Python package is refused (importing it would
    run the package)."""
    sbx.write("usrpkg/__init__.py",
              "open(__file__ + '.RAN', 'w').write('x')\n")
    sbx.write("usrpkg/m.py", "f = None\n")
    sbx.write("usrpkg/c.seam", "-module(c, [f/1])\nf(1),\n")
    sbx.write("nsx/usrpkg/__init__.py",
              "open(__file__ + '.RAN', 'w').write('x')\n")
    sbx.write("nsx/usrpkg/c.seam", "-module(c, [f/1])\nf(1),\n")
    sbx.write("nsx/usrpkg/d.pl", ":- module(d, [f/1]).\nf(1).\n")
    sbx.write("pk" + suffix, text)
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        probe("load", lambda: load("pk"))
        probe("ran", lambda: [p for p in ("usrpkg/__init__.py.RAN",
                                          "nsx/usrpkg/__init__.py.RAN")
                              if os.path.exists(p)])
        probe("imported", lambda: [m for m in ("usrpkg", "nsx.usrpkg")
                                   if m in sys.modules])
    """, env={"CLAUSAL_PL_FRONTEND": frontend})
    assert not res["load"]["ok"], res["load"]
    assert ok(res, "ran") == "[]"
    assert ok(res, "imported") == "[]"


def test_a_pl_reached_through_a_pass_through_seam_is_refused(sbx):
    """.clausal -> Python-free .seam -> .pl -> py/os: closed in the
    sandbox, at the .pl's own load."""
    sbx.write("plpy.pl", PL_PY)
    sbx.write("passthru.seam", "-module(passthru, [p/1])\n"
              "-import_from(plpy, [p])\n")
    sbx.write("top.clausal", ":- module(top, [t/1]).\n"
              ":- use_module(passthru, [p/1]).\nt(X) :- p(X).\n"
              ":- end_module(top).\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        probe("top", lambda: load("top"))
        probe("passthru", lambda: load("passthru"))
    """)
    for name in ("top", "passthru"):
        r = res[name]
        assert not r["ok"] and r["import_error"], (name, r)
        assert "plpy" in r["msg"], r


@pytest.mark.parametrize("directive", [
    ":- use_module(library(py_os), [pid/1]).",
    ":- use_module(library(py_process), [shell/1]).",
    ":- use_module(library(datetime), [now/1]).",
    ":- use_module(library(logging), [info/1]).",
])
def test_a_clausal_import_of_a_denied_facade_is_refused(sbx, directive):
    sbx.write("cf.clausal", f":- module(cf, [t/1]).\n{directive}\n"
              "t(1).\n:- end_module(cf).\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        probe("load", lambda: load("cf"))
    """)
    refused(res, "load", LOAD, import_error=True)


# ── RUN TIME ────────────────────────────────────────────────────────────────


RUNTIME = """
import clausal.sandbox as sb
sb.enable()
from clausal import Var, Module
import clausal.modules.py.os, clausal.modules.py.process
import clausal.library.py_os, clausal.library.py_process
dom = load("dom")
plm = load("plclean")
X = Var()
G = {goals}
{extra}
for name, goal in G.items():
    probe(name, lambda goal=goal: answers(goal, dom, X))
"""


def _runtime(sbx, goals: str, extra: str = "") -> dict:
    _consumer(sbx)
    sbx.write("plclean.pl", PL_CLEAN)
    return sbx.run(RUNTIME.format(goals=goals,
                                  extra=textwrap.dedent(extra)))


def test_python_objects_in_a_goal_are_refused(sbx):
    res = _runtime(sbx, """{
        "function": ("call", os.getcwd),
        "builtin_in_arg": ("eligible", os.system, X),
        "module": ("eligible", os, X),
        "class": ("eligible", type, X),
        "object": ("eligible", object(), X),
        "lambda": ("call", lambda *a: None),
        "nested": ("eligible", [1, ("f", {"k": os})], X),
        "module_designator": (":", dom, ("eligible", X, 30)),
        "adapter_object": ("call", clausal.modules.py.os.pid, X),
        "bound_var": ("eligible", Var(), X),
    }""", extra="""
        _v = Var()
        from clausal.logic.variables import Trail, unify
        unify(_v, os, Trail())
        G["var_bound_to_module"] = ("eligible", _v, X)
        import clausal.pythonic_ast.nodes as N
        G["ast_node"] = ("call", N.LoadName(name="x"))
    """)
    for name in ("function", "builtin_in_arg", "module", "class", "object",
                 "lambda", "nested", "module_designator", "adapter_object",
                 "var_bound_to_module", "ast_node"):
        refused(res, name, PYOBJ)
    assert ok(res, "bound_var") == "[30]"


def test_a_dotted_adapter_goal_is_refused_unless_allowed(sbx):
    """Goal cells as a JSON-to-term worker builds them: a dotted functor
    is just an atom, whatever spelling it uses."""
    res = _runtime(sbx, """{
        "py_os_full": ("clausal.modules.py.os.pid", X),
        "py_os_short": ("py.os.pid", X),
        "facade": ("clausal.library.py_os.pid", X),
        "process": ("clausal.modules.py.process.shell", "true"),
        "process_facade": ("clausal.library.py_process.shell", "true"),
        "qualified": (":", "clausal.modules.py.os", ("pid", X)),
        "qualified_facade": (":", "clausal.library.py_os", ("pid", X)),
        "call": ("call", ("clausal.modules.py.os.pid", X)),
        "call_n": ("call", "clausal.modules.py.process.shell", "true"),
        "findall": ("findall", X, ("clausal.library.py_os.pid", X), Var()),
        "maplist": ("maplist", "clausal.library.py_process.shell", ["true"]),
        "denied_pred": ("clausal.modules.py.datetime.now", X),
        "denied_pred_facade": ("clausal.library.datetime.today", X),
        "allowed": ("clausal.modules.py.datetime.date_add",
                    ("date", 2020, 1, 1), ("timedelta", 1, 0, 0), X),
        "allowed_facade": ("clausal.library.datetime.date_add",
                           ("date", 2020, 1, 1), ("timedelta", 1, 0, 0), X),
    }""")
    for name in ("py_os_full", "facade", "process", "process_facade",
                 "qualified", "qualified_facade", "call", "call_n",
                 "findall", "maplist", "denied_pred", "denied_pred_facade"):
        refused(res, name, PYMOD)
    assert not res["py_os_short"]["ok"], res["py_os_short"]
    assert ok(res, "allowed") == "[('date', 2020, 1, 2)]"
    assert ok(res, "allowed_facade") == "[('date', 2020, 1, 2)]"


def test_a_dotted_goal_never_reads_an_attribute_of_python(sbx):
    """A dotted functor is walked only through Clausal modules and allowed
    adapter modules: reading an attribute of any other object can run
    Python (a module ``__getattr__``, a property).  An underscore-led
    segment is never walked."""
    _consumer(sbx)
    sbx.write("probe_mod.py",
              "def __getattr__(name):\n"
              "    open('GETATTR_' + name, 'w').write('x')\n"
              "    raise AttributeError(name)\n")
    res = sbx.run("""
        import probe_mod                     # the worker's own module
        class Probe:
            def __getattr__(self, name):
                open("GETATTR_obj_" + name, "w").write("x")
                raise AttributeError(name)
        sys.modules["probe_obj"] = Probe()   # a non-module sys.modules entry
        import clausal.modules.py.re as _re
        _re.probeobj = Probe()               # an object an adapter binds
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        dom = load("dom")
        X = Var()
        G = {
            "attr": ("probe_mod.anything", X),
            "deep": ("probe_mod.sub.thing", X),
            "call": ("call", "probe_mod.anything", X),
            "callc": ("call", ("probe_mod.anything", X)),
            "findall": ("findall", X, ("probe_mod.deep.x", X), Var()),
            "under": ("dom.__class__.mro", X),
            "under2": ("clausal.__spec__.loader", X),
            "engine_fn": ("clausal.logic.solve.solve", X),
            "qual": (":", "probe_mod", ("foo", X)),
            "qual_call": ("call", (":", "probe_mod", ("foo", X))),
            "qual_assert": ("assertz", (":", "probe_mod", ("foo", 1))),
            "obj_qual": (":", "probe_obj", ("foo", X)),
            "obj_dotted": ("probe_obj.foo", X),
            "obj_attr": ("clausal.modules.py.re.probeobj.foo", X),
            "obj_attr_call": ("call", "clausal.modules.py.re.probeobj.foo",
                              X),
        }
        for name, goal in G.items():
            probe(name, lambda goal=goal: answers(goal, dom, X))
        probe("pycall", lambda: list(__import__("clausal").call(
            "probe_mod.anything", X, module=dom)))
        probe("markers", lambda: sorted(f for f in os.listdir(".")
                                        if f.startswith("GETATTR_")))
    """)
    for name in ("attr", "deep", "call", "callc", "findall", "under",
                 "under2", "engine_fn", "pycall", "qual", "qual_call",
                 "qual_assert", "obj_qual", "obj_dotted", "obj_attr",
                 "obj_attr_call"):
        assert not res[name]["ok"], (name, res[name])
    assert ok(res, "markers") == "[]"


def test_a_query_is_a_clausal_prolog_frame(sbx):
    """M:G, call/N, assert/retract/clause into a .pl or a Python module."""
    res = _runtime(sbx, """{
        "pl_qualified": (":", "plclean", ("q", X)),
        "pl_call": ("call", (":", "plclean", ("q", X))),
        "pl_assert": ("assertz", (":", "plclean", ("r", 1))),
        "pl_retract": ("retract", (":", "plclean", ("q", X))),
        "pl_clause": ("clause", (":", "plclean", ("q", X)), Var()),
        "pl_findall": ("findall", X, (":", "plclean", ("q", X)), Var()),
        "py_qualified": (":", "os", ("getcwd", X)),
        "py_assert": ("assertz", (":", "clausal.modules.py.os", ("r", 1))),
        "sandbox_module": (":", "clausal.sandbox", "enable"),
        "state_module": (":", "clausal._sandbox_state", ("x", X)),
    }""")
    for name in ("pl_qualified", "pl_call", "pl_assert", "pl_retract",
                 "pl_clause", "pl_findall"):
        refused(res, name, PLMOD)
    for name in ("py_qualified", "py_assert", "sandbox_module",
                 "state_module"):
        refused(res, name, PYMOD)


def test_a_pl_module_is_no_query_frame(sbx):
    _consumer(sbx)
    sbx.write("plclean.pl", PL_CLEAN)
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        X = Var()
        plm = load("plclean")
        probe("solve_in_pl", lambda: answers(("q", X), plm, X))
    """)
    refused(res, "solve_in_pl", PLMOD)


def test_side_effect_builtins_are_private_procedures(sbx):
    res = _runtime(sbx, """{
        "halt": ("call", "halt"),
        "halt1": ("halt", 3),
        "write": ("write", "x"),
        "format": ("format", "x"),
        "nl": ("call", "nl"),
        "set_flag": ("set_prolog_flag", "sandbox", "false"),
        "flag_debug": ("set_prolog_flag", "debug", "true"),
        "gensym": ("gensym", "a", X),
        "time": ("current_time", X),
        "global_atom": ("global_atom", "zz", X),
        "z3": ("z3_set_option", "trace", "true"),
        "z3_stats": ("z3_stats", X),
        "catchable": ("catch", ("write", "x"), ("error", X, Var()), "true"),
    }""")
    for name in ("halt", "halt1", "write", "format", "nl", "set_flag",
                 "flag_debug", "gensym", "time", "global_atom", "z3",
                 "z3_stats"):
        refused(res, name, PRIVATE)
    assert "private_procedure" in ok(res, "catchable")


def test_the_engine_s_attributes_are_not_the_program_s(sbx):
    """Thorough review: put_attr/3 could hand the freeze hook (which CALLS
    every element of its list) an arbitrary value, and get_attr/3 read the
    solvers' Python state into a term."""
    res = _runtime(sbx, """{
        "put_freeze": ("put_attr", Var(), "freeze", ["abc"]),
        "put_fd": ("put_attr", Var(), "fd", 1),
        "put_attrs": ("put_attrs", Var(), {"freeze": ["abc"]}),
        "own_key": ("put_attr", Var(), "mine", 1),
    }""", extra="""
        G["get_freeze"] = ("get_attr", Var(), "freeze", X)
        G["del_freeze"] = ("del_attr", Var(), "freeze")
    """)
    for name in ("put_freeze", "put_fd", "put_attrs", "del_freeze",
                 "get_freeze"):
        refused(res, name, "permission_error(access,attribute,")
    ok(res, "own_key")


def test_module_constant_names_a_module_by_its_atom(sbx):
    sbx.write("consts.seam", "-module(consts, [lim/1])\n"
              "-constant_value(limit, 42)\nlim(1),\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        load("consts")
        dom = load("consts")
        M, V = Var(), Var()
        probe("enum", lambda: answers(("module_constant", M, "limit", V),
                                      dom, M))
        probe("bound", lambda: answers(("module_constant", "consts",
                                        "limit", V), dom, V))
    """)
    assert ok(res, "enum") == "['consts']"
    assert ok(res, "bound") == "[42]"


def test_reflection_reads_no_foreign_module(sbx):
    """Security review round 5: module_constant/3 with M unbound read
    ``__clausal_module__`` of every sys.modules entry by getattr."""
    sbx.write("consts.seam", "-module(consts, [lim/1])\n"
              "-constant_value(limit, 42)\nlim(1),\n")
    sbx.write("probe_mod.py",
              "def __getattr__(name):\n"
              "    open('GETATTR_' + name, 'w').write('x')\n"
              "    raise AttributeError(name)\n")
    res = sbx.run("""
        import probe_mod
        class Probe:
            def __getattr__(self, name):
                open("GETATTR_obj_" + name, "w").write("x")
                raise AttributeError(name)
        sys.modules["probe_obj"] = Probe()
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        dom = load("consts")
        M, N, V = Var(), Var(), Var()
        probe("enum", lambda: answers(("module_constant", M, N, V), dom, M))
        probe("value", lambda: answers(("constant_value", "limit", V),
                                       dom, V))
        probe("markers", lambda: sorted(f for f in os.listdir(".")
                                        if f.startswith("GETATTR_")))
    """)
    assert ok(res, "enum") == "['consts']"
    assert ok(res, "markers") == "[]"


def test_a_query_scans_no_directory_and_writes_nothing(sbx):
    """Thorough review: a miss listed the sibling files that define the
    name (a directory probe), and a deprecated unit spelling reached by a
    dotted goal warned on stderr (the units module's __getattr__)."""
    _consumer(sbx)
    sbx.write("hidden.seam", "-module(hidden, [topsecret_rule/3])\n"
              "topsecret_rule(1, 2, 3),\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        import clausal.modules.units
        dom = load("dom")
        X = Var()
        probe("miss", lambda: answers(("topsecret_rule", 1, 2, X), dom, X))
        probe("deprecated", lambda: answers(
            ("clausal.modules.units.Metre", X), dom, X))
        probe("hidden_loaded", lambda: "hidden" in sys.modules)
    """)
    r = res["miss"]
    assert not r["ok"] and "hidden" not in r["msg"], r
    assert not res["deprecated"]["ok"]
    assert "Metre" not in res["__stderr__"], res["__stderr__"][-2000:]
    assert ok(res, "hidden_loaded") == "False"


def test_every_engine_attribute_key_is_listed():
    """Every ``*_KEY = "..."`` constant of the engine that is registered as
    an attribute hook or PUT on a variable (security review round 5: the
    SAT and OR-Tools keys register no hook) is in ENGINE_ATTR_KEYS, and
    the sandbox reads each one's value from source."""
    import re
    from clausal.sandbox import ENGINE_ATTR_KEYS, _engine_attr_keys
    root = os.path.join(ENGINE_ROOT, "clausal")
    found = set()
    for d, _subdirs, files in os.walk(root):
        for f in files:
            if not f.endswith(".py"):
                continue
            text = open(os.path.join(d, f), encoding="utf-8").read()
            mod = os.path.relpath(os.path.join(d, f[:-3]),
                                  ENGINE_ROOT).replace(os.sep, ".")
            consts = set(re.findall(r"^(\w+_KEY)\s*=\s*[\"']", text, re.M))
            for c in consts:
                if re.search(r"(register_attr_hook|put_attr)\(\s*[^,]*,?\s*"
                             + re.escape(c) + r"\b", text) or re.search(
                                 r"register_attr_hook\(" + re.escape(c),
                                 text):
                    found.add((mod, c))
    assert {("clausal.logic.clportools", "OR_KEY"),
            ("clausal.logic.clpsat", "SAT_KEY")} <= found, found
    assert found <= set(ENGINE_ATTR_KEYS), found - set(ENGINE_ATTR_KEYS)
    assert len(_engine_attr_keys()) == len(ENGINE_ATTR_KEYS)


def test_every_denied_builtin_exists_in_the_registries():
    """A rename must not silently drop a name from the denial."""
    from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS
    from clausal.sandbox import DENIED_BUILTINS
    names = {k[0] for k in _BUILTINS} | {k[0] for k in _DB_BUILTINS}
    from clausal.logic.builtins.clause_ops import SPECIAL_FORMS
    names |= {n for n, _a in SPECIAL_FORMS}
    assert set(DENIED_BUILTINS) <= names, set(DENIED_BUILTINS) - names


# ── the Python entry points ─────────────────────────────────────────────────


#: Every Python-side entry that runs a goal: each must refuse a Python
#: object, refuse a .pl target, and still answer a clean goal.
ENTRY_POINTS = {
    "solve": "lambda g: list(clausal.solve(g, module=dom))",
    "once": "lambda g: clausal.once(g, module=dom)",
    "query": "lambda g: list(clausal.query(g, {'X': X}, module=dom))",
    "query_wfs": "lambda g: clausal.query_wfs(g, {'X': X}, module=dom)",
    "Solutions": "lambda g: list(clausal.Solutions(g, module=dom)._iter)",
    "judged_answers": ("lambda g: list(__import__('clausal.logic.seam', "
                       "fromlist=['x']).judged_answers(g, dom.__clausal_module__, [X], "
                       "clausal.Trail()))"),
    "call": "lambda g: list(clausal.call(g[0], *g[1:], module=dom))",
    # clausal.aio, the async twins (driven on an event loop):
    "asolve": ("lambda g: asyncio.run(_alist(clausal.aio.asolve("
               "g, module=dom)))"),
    "aonce": "lambda g: asyncio.run(clausal.aio.aonce(g, module=dom))",
    "acall": ("lambda g: asyncio.run(_alist(clausal.aio.acall("
              "g[0], *g[1:], module=dom)))"),
    "adrive": ("lambda g: asyncio.run(_alist(clausal.aio.adrive("
               "clausal.solve(g, module=dom))))"),
    "Solutions_await": ("lambda g: asyncio.run(_await(clausal.Solutions("
                        "g, module=dom)))"),
}


def test_every_python_entry_point_is_covered(sbx):
    _consumer(sbx)
    sbx.write("plclean.pl", PL_CLEAN)
    body = """
import warnings
warnings.simplefilter("ignore")
import clausal.sandbox as sb
sb.enable()
import clausal
import clausal.library.py_os
import asyncio
import clausal.aio
from clausal import Var


async def _alist(agen):
    return [x async for x in agen]


async def _await(sols):
    return await sols


dom = load("dom")
load("plclean")
X = Var()
"""
    for name, fn in ENTRY_POINTS.items():
        body += f"""
f = {fn}
probe("{name}:clean", lambda f=f: f(("eligible", X, 30)))
probe("{name}:object", lambda f=f: f(("eligible", os.getcwd, X)))
probe("{name}:pl", lambda f=f: f((":", "plclean", ("q", X))) if
      "{name}" != "call" else f(("plclean.q", X)))
probe("{name}:adapter", lambda f=f: f(("clausal.library.py_os.pid", X)))
"""
    res = sbx.run(body)
    for name in ENTRY_POINTS:
        assert res[f"{name}:clean"]["ok"], (name, res[f"{name}:clean"])
        refused(res, f"{name}:object", PYOBJ)
        assert not res[f"{name}:pl"]["ok"], (name, res[f"{name}:pl"])
        assert not res[f"{name}:adapter"]["ok"], (name,
                                                   res[f"{name}:adapter"])
        assert PYMOD in (res[f"{name}:adapter"]["term"] or ""), res[
            f"{name}:adapter"]


def test_the_entry_point_list_is_complete():
    """Every public name of clausal.logic.solve that runs a goal is in
    ENTRY_POINTS (a new one must be added there, and gated)."""
    import clausal.logic.solve as s
    runs_goals = {"call", "solve", "query", "query_wfs", "once"}
    assert set(s.__all__) - {"resolve_module", "_deref_walk"} == runs_goals
    assert runs_goals <= set(ENTRY_POINTS)
    # clausal.aio: every public goal driver is pinned (await_only waits on
    # a Python awaitable and async_predicate builds an adapter the
    # allowlist refuses at run time; neither takes a goal).
    import clausal.aio as aio
    assert set(aio.__all__) - {"await_only", "async_predicate"} \
        <= set(ENTRY_POINTS)


# ── enable(): irreversible, env, fail closed, narrowing only ────────────────


def test_enable_is_irreversible(sbx):
    _consumer(sbx)
    res = sbx.run("""
        import clausal.sandbox as sb
        from clausal import Var
        sb.enable()
        dom = load("dom")
        X = Var()
        probe("no_disable", lambda: [n for n in dir(sb)
                                     if "disable" in n or "off" in n])
        probe("flag_query", lambda: answers(
            ("set_prolog_flag", "sandbox", "false"), dom, X))
        probe("state_query", lambda: answers(
            ("clausal._sandbox_state.ACTIVE", X), dom, X))
        probe("enable_query", lambda: answers(
            ("clausal.sandbox.enable",), dom, X))
        probe("widen", lambda: sb.enable(allow_adapters=["py.os"]))
        probe("default_again", lambda: sb.enable())
        probe("narrow", lambda: sb.enable(allow_adapters=["py.datetime"]))
        probe("rewiden", lambda: sb.enable(allow_adapters=["py.json"]))
        probe("still_on", lambda: sb.is_enabled())
        probe("narrowed", lambda: sorted(sb.allowed_adapters()))
        probe("after_narrow", lambda: answers(
            ("clausal.modules.py.json.parse", ('$chars', "[1]"), X), dom, X))
    """)
    assert ok(res, "no_disable") == "[]"
    refused(res, "flag_query", PRIVATE)
    assert not res["state_query"]["ok"]
    assert not res["enable_query"]["ok"]
    assert res["widen"]["type"] == "PermissionError"
    ok(res, "default_again")
    ok(res, "narrow")
    assert res["rewiden"]["type"] == "PermissionError"
    assert ok(res, "still_on") == "True"
    assert ok(res, "narrowed") == "['clausal.modules.py.datetime']"
    refused(res, "after_narrow", PYMOD)


def test_the_environment_variable_turns_it_on(sbx):
    _consumer(sbx)
    sbx.write("bad.seam", "import os\n-module(bad, [p/1])\np(1),\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        probe("on", lambda: sb.is_enabled())
        probe("bad", lambda: load("bad"))
        probe("dom", lambda: load("dom") and True)
    """, env={"CLAUSAL_SANDBOX": "1"})
    assert ok(res, "on") == "True"
    refused(res, "bad", LOAD, import_error=True)
    ok(res, "dom")
    off = sbx.run("""
        import clausal.sandbox as sb
        probe("on", lambda: sb.is_enabled())
    """, env={"CLAUSAL_SANDBOX": "0"})
    assert ok(off, "on") == "False"
    bogus = sbx.run("""
        probe("import", lambda: __import__("clausal"))
    """, env={"CLAUSAL_SANDBOX": "maybe"})
    assert bogus["import"]["type"] == "ImportError", bogus


def test_enable_after_a_user_load_fails_closed(sbx):
    _consumer(sbx)
    res = sbx.run("""
        import clausal.sandbox as sb
        load("dom")
        probe("enable", lambda: sb.enable())
        probe("on", lambda: sb.is_enabled())
    """)
    r = res["enable"]
    assert r["type"] == "RuntimeError" and "dom" in r["msg"] \
        and "helpers" in r["msg"], r
    assert ok(res, "on") == "False"


BRIDGE = "import os\n-module(brg, [cwd/1])\ncwd(D) <- (D is ++os.getcwd())\n"


BRIDGE_IMPORTER = (":- module(bimp, [t/1]).\n"
                   ":- use_module(brg, [cwd/1]).\nt(D) :- cwd(D).\n"
                   ":- end_module(bimp).\n")


def test_allow_bridges_only_narrows_the_importer_project_check(sbx):
    """Ruling S5: enable() reads no project file (no cwd lookup);
    allow_bridges narrows the python_bridges check a .clausal importer's
    project makes.  A bridge loads only when BOTH say so."""
    import hashlib
    sbx.write("brg.seam", BRIDGE)
    sbx.write("bimp.clausal", BRIDGE_IMPORTER)
    sha = hashlib.sha256(BRIDGE.encode()).hexdigest()
    probe_body = """
        import clausal.sandbox as sb
        sb.enable(allow_bridges={bridges})
        from clausal import Var
        X = Var()
        probe("on", lambda: sb.is_enabled())
        probe("via_clausal", lambda: answers(("t", X), load("bimp"), X))
    """
    # No pyproject anywhere: enable() does not look for one (before S5 it
    # raised PermissionError here); the importer's project has no list, so
    # the bridge is refused at the .clausal's use_module.
    (sbx.root / "pyproject.toml").unlink()
    res = sbx.run(probe_body.format(bridges="['brg']"))
    assert ok(res, "on") == "True"
    assert "python_bridge" in res["via_clausal"]["msg"], res["via_clausal"]
    # Listed in the importer's project and named: loads and runs Python.
    sbx.pyproject(['"brg"'])
    res = sbx.run(probe_body.format(bridges="['brg']"))
    assert ok(res, "via_clausal") == repr([str(sbx.root)])
    # Listed in the project but not named by the worker: refused.
    res = sbx.run(probe_body.format(bridges="[]"))
    refused(res, "via_clausal", LOAD, import_error=True)
    # Named and listed, but loaded directly by Python: no importer
    # project approved it -- refused.
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable(allow_bridges=["brg"])
        probe("direct", lambda: load("brg"))
    """)
    refused(res, "direct", LOAD, import_error=True)
    # Pinned to another sha in the importer's project: refused.
    sbx.pyproject(['{ module = "brg", sha256 = "' + "0" * 64 + '" }'])
    res = sbx.run(probe_body.format(bridges="['brg']"))
    assert not res["via_clausal"]["ok"], res["via_clausal"]
    sbx.pyproject(['{ module = "brg", sha256 = "' + sha + '" }'])
    res = sbx.run(probe_body.format(bridges="['brg']"))
    assert ok(res, "via_clausal") == repr([str(sbx.root)])
    # A second enable() may only narrow.
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable(allow_bridges=[])
        probe("widen", lambda: sb.enable(allow_bridges=["brg"]))
    """)
    assert res["widen"]["type"] == "PermissionError", res["widen"]


def test_allow_adapters_only_narrows_the_default(sbx):
    res = sbx.run("""
        import clausal.sandbox as sb
        probe("widen", lambda: sb.enable(allow_adapters=["py.process"]))
        probe("unknown", lambda: sb.enable(allow_adapters=["py.nosuch"]))
        probe("on", lambda: sb.is_enabled())
        probe("narrow", lambda: sb.enable(allow_adapters=["date_time",
                                                          "units"]))
        probe("set", lambda: sorted(sb.allowed_adapters()))
    """)
    assert res["widen"]["type"] == "PermissionError"
    assert res["unknown"]["type"] == "ValueError"
    assert ok(res, "set") == repr(sorted(["clausal.modules.py.datetime",
                                          "clausal.modules.units"]))


# ── the classification ──────────────────────────────────────────────────────


def test_every_engine_adapter_module_is_classified():
    from clausal.sandbox import adapter_row, engine_adapter_modules
    missing = [m for m in engine_adapter_modules() if adapter_row(m) is None]
    assert not missing, missing


def test_the_denied_predicates_exist():
    import importlib
    from clausal.modules.py import ModulePredicate
    from clausal.sandbox import ADAPTERS
    for m, row in ADAPTERS.items():
        if not row.denied:
            continue
        mod = importlib.import_module(m)
        for name in row.denied:
            assert isinstance(getattr(mod, name, None), ModulePredicate), (
                m, name)


@pytest.mark.parametrize("module", [
    "clausal.modules.py.os", "clausal.modules.py.process",
    "clausal.modules.py.files", "clausal.modules.py.http",
    "clausal.modules.py.tcp", "clausal.modules.py.sqlite",
    "clausal.modules.py.logging", "clausal.modules.py.random",
    "clausal.modules.py.asyncio", "clausal.modules.reflection"])
def test_side_effecting_adapters_are_denied(module):
    from clausal.sandbox import ADAPTERS
    assert ADAPTERS[module].allowed is False


# ── namespace packages (a deep namespace layout) ──────────────────────────────────

PKG_INIT = """
:- module(pkx, [lic/2]).
:- use_module(clib/util, [double/2]).
base(major, 3).
base(minor, 1).
lic(K, F) :- base(K, B), double(B, F).
:- end_module(pkx).
"""

LIB_UTIL = """
:- module(util, [double/2]).
double(X, Y) :- Y is X * 2.
:- end_module(util).
"""


def _ns_layout(sbx, root="."):
    """``<root>/nsa/pay/pkx/{__init__.clausal, pkx.clausal,
    tests/*.clausal}`` with no ``__init__`` above it (``nsa`` and
    ``nsa.pay`` are PEP 420 namespace packages), and a regular Clausal
    package ``clib`` beside it."""
    sbx.write(f"{root}/nsa/pay/pkx/__init__.clausal", PKG_INIT)
    sbx.write(f"{root}/nsa/pay/pkx/pkx.clausal",
              ":- module(pkx_rules, [klass/1]).\nklass(major).\n"
              ":- end_module(pkx_rules).\n")
    sbx.write(f"{root}/nsa/pay/pkx/tests/test_lic.clausal",
              ":- module(test_lic, [t/1]).\n"
              ":- use_module(nsa/pay/pkx, [lic/2]).\n"
              "t(F) :- lic(major, F).\n:- end_module(test_lic).\n")
    sbx.write(f"{root}/clib/__init__.seam", "-module(clib, [])\n")
    sbx.write(f"{root}/clib/util.clausal", LIB_UTIL)


def test_a_namespace_package_resolves_in_the_sandbox(sbx):
    """Regression (9cfb8ff1): python_bridges._find answered
    <unresolvable> below a namespace package nobody imported (PathFinder's
    _NamespacePath reads the parent's __path__ from sys.modules), so every
    module below a namespace package was refused at load."""
    _ns_layout(sbx)
    sbx.write("main.clausal", ":- module(main, [t/1, k/1]).\n"
              ":- use_module(nsa/pay/pkx, [lic/2]).\n"
              ":- use_module(nsa/pay/pkx/pkx, [klass/1]).\n"
              "t(F) :- lic(major, F).\nk(K) :- klass(K).\n"
              ":- end_module(main).\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        X = Var()
        main = load("main")
        probe("t", lambda: answers(("t", X), main, X))
        probe("k", lambda: answers(("k", X), main, X))
        probe("tests", lambda: answers(
            ("t", X), load("nsa.pay.pkx.tests.test_lic"), X))
    """)
    assert ok(res, "t") == "[6]"
    assert ok(res, "k") == "['major']"
    assert ok(res, "tests") == "[6]"


def test_two_path_roots_contribute_portions_of_one_namespace(sbx):
    _ns_layout(sbx, "rootA")
    sbx.write("rootB/nsa/fin/fx_y/__init__.clausal",
              ":- module(fx_y, [rate/1]).\nrate(7).\n:- end_module(fx_y).\n")
    sbx.write("rootB/nsa/pay/pky/__init__.clausal",
              ":- module(pky, [p/1]).\np(1).\n:- end_module(pky).\n")
    sbx.write("main.clausal", ":- module(main, [t/1]).\n"
              ":- use_module(nsa/pay/pkx, [lic/2]).\n"
              ":- use_module(nsa/fin/fx_y, [rate/1]).\n"
              ":- use_module(nsa/pay/pky, [p/1]).\n"
              "t(F) :- lic(major, A), rate(R), p(P), F is A + R + P.\n"
              ":- end_module(main).\n")
    res = sbx.run("""
        sys.path[0:0] = [os.path.abspath("rootA"), os.path.abspath("rootB")]
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        X = Var()
        probe("t", lambda: answers(("t", X), load("main"), X))
    """)
    assert ok(res, "t") == "[14]"


def test_a_python_package_below_a_namespace_never_runs(sbx):
    sbx.write("nsa/evil/__init__.py",
              "open(__file__ + '.RAN', 'w').write('x')\n")
    sbx.write("nsa/evil/m.clausal", ":- module(m, [f/1]).\nf(1).\n"
              ":- end_module(m).\n")
    sbx.write("main.clausal", ":- module(main, [t/1]).\n"
              ":- use_module(nsa/evil/m, [f/1]).\nt(X) :- f(X).\n"
              ":- end_module(main).\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        probe("load", lambda: load("main"))
        probe("ran", lambda: os.path.exists("nsa/evil/__init__.py.RAN"))
        probe("imported", lambda: [m for m in ("nsa", "nsa.evil")
                                   if m in sys.modules])
    """)
    assert not res["load"]["ok"], res["load"]
    assert ok(res, "ran") == "False"
    assert ok(res, "imported") == "[]"


def test_a_symlink_loop_or_an_unreadable_dir_fails_closed(sbx):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root reads any directory")
    sbx.write("nsa/locked/m.clausal", ":- module(m, [f/1]).\nf(1).\n"
              ":- end_module(m).\n")
    (sbx.root / "nsa" / "loop").symlink_to(sbx.root / "nsa")
    os.symlink("selfloop", sbx.root / "nsa" / "selfloop")
    sbx.write("a.clausal", ":- module(a, [t/1]).\n"
              ":- use_module(nsa/locked/m, [f/1]).\nt(X) :- f(X).\n"
              ":- end_module(a).\n")
    sbx.write("b.clausal", ":- module(b, [t/1]).\n"
              ":- use_module(nsa/loop/loop/loop/nosuch, [f/1]).\n"
              "t(X) :- f(X).\n:- end_module(b).\n")
    sbx.write("c.clausal", ":- module(c, [t/1]).\n"
              ":- use_module(nsa/selfloop/m, [f/1]).\nt(X) :- f(X).\n"
              ":- end_module(c).\n")
    os.chmod(sbx.root / "nsa" / "locked", 0)
    try:
        res = sbx.run("""
            import clausal.sandbox as sb
            sb.enable()
            probe("a", lambda: load("a"))
            probe("b", lambda: load("b"))
            probe("c", lambda: load("c"))
        """)
    finally:
        os.chmod(sbx.root / "nsa" / "locked", 0o755)
    for name in ("a", "b", "c"):
        assert not res[name]["ok"], (name, res[name])


def test_the_default_gate_resolves_namespace_children(tmp_path, monkeypatch):
    """The bridge gate (sandbox off) shares python_bridges._find: a module
    below a namespace package resolves, and nothing is imported."""
    from clausal import python_bridges as pb
    root = tmp_path / "nsroot"
    root.mkdir()
    sb = _Sandbox(root)
    _ns_layout(sb)
    # Not syspath_prepend: it fixes up namespace packages by IMPORTING them.
    monkeypatch.setattr(sys, "path", [str(root), *sys.path])
    import importlib
    importlib.invalidate_caches()
    origin = pb._find("nsa.pay.pkx")
    assert origin == str(root / "nsa/pay/pkx/__init__.clausal")
    assert pb._find("nsa.pay") is None        # a namespace: no file
    assert pb._find("nsa.pay.pkx.pkx").endswith("pkx.clausal")
    assert "nsa" not in sys.modules and "nsa.pay" not in sys.modules, (
        sys.modules.get("nsa"))
    seam = root / "nsuser.seam"
    seam.write_text("-module(nsuser, [p/1])\n-private([major])\n"
                    "-import_from(nsa.pay.pkx, [lic])\n"
                    "p(F) <- lic(major, F)\n")
    assert pb.file_python_routes(str(seam)) == []


def test_the_default_gate_audits_a_seam_below_a_namespace(tmp_path,
                                                           monkeypatch):
    """On a4fbe93f (sandbox off) a .seam referencing
    a module below a namespace package nobody had imported got
    <unresolvable> from _find -- the gate REFUSED it as Python (fail
    closed, order-dependent: once some import had loaded the namespace it
    passed).  Now it resolves without importing and is AUDITED: a clean
    chain passes, Python behind it is still refused."""
    from clausal import python_bridges as pb
    root = tmp_path / "nsroot"
    (root / "nsb" / "proc").mkdir(parents=True)
    (root / "nsb/proc/thresholds.seam").write_text(
        "-module(thresholds, [t/1])\nt(1),\n")
    (root / "nsb/proc/evilt.seam").write_text(
        "import os\n-module(evilt, [t/1])\nt(X) <- (X is ++os.getcwd())\n")
    (root / "nsb/proc/chain.seam").write_text(
        "-module(chain, [t/1])\n-import_from(nsb.proc.thresholds, [t])\n")
    (root / "nsb/proc/chain2.seam").write_text(
        "-module(chain2, [t/1])\n-import_from(nsb.proc.evilt, [t])\n")
    monkeypatch.setattr(sys, "path", [str(root), *sys.path])
    importlib.invalidate_caches()
    importer = str(root / "m.clausal")
    assert pb.file_python_routes(str(root / "nsb/proc/chain.seam")) == []
    assert pb.bridge_refusal(importer, "nsb.proc.chain",
                             str(root / "nsb/proc/chain.seam")) is None
    refusal = pb.bridge_refusal(importer, "nsb.proc.chain2",
                                str(root / "nsb/proc/chain2.seam"))
    assert refusal is not None and "evilt" in refusal.message
    assert "nsb" not in sys.modules


def test_a_loose_clausal_file_loads_library_facades(tmp_path):
    """A loose .clausal (no project, no package) importing
    library(datetime) and library(units) loads under the sandbox."""
    d = tmp_path / "loose"
    d.mkdir()
    (d / "lz.clausal").write_text(
        ":- module(lz, [d/3, dim/2]).\n"
        ":- use_module(library(datetime), [date_add/3]).\n"
        ":- use_module(library(units), [dimension_of/2]).\n"
        "d(A, N, B) :- date_add(A, N, B).\n"
        "dim(Q, D) :- dimension_of(Q, D).\n:- end_module(lz).\n")
    e = dict(os.environ, PYTHONPATH=ENGINE_ROOT, CLAUSAL_ROOT=ENGINE_ROOT,
             CLAUSAL_SANDBOX="1", PYTHONDONTWRITEBYTECODE="1")
    script = ("import sys, clausal\nsys.path.insert(0, %r)\n"
              "from clausal import solve, Var, deref\nimport lz\nX = Var()\n"
              "print([deref(X) for _ in solve(('d', ('date', 2020, 1, 1), "
              "('timedelta', 1, 0, 0), X), module=lz)])\n" % str(d))
    proc = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                          env=e, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert "[('date', 2020, 1, 2)]" in proc.stdout


def test_a_refusal_names_the_source_lines_and_every_site(sbx):
    """Two Lows: a denied predicate's refusal named a spurious
    line 1 (the native lowering's clause statement carries the module
    directive's line; the clause data carries the real position), and the
    message stopped after six sites."""
    sbx.write("tq.clausal", ":- module(tq, [t/1]).\n"
              ":- use_module(library(datetime), [today/1, days_between/3]).\n"
              "t(X) :- today(X).\n:- end_module(tq).\n")
    body = "".join(f"p{i}(X) <- (X is ++({i} + 1))\n" for i in range(9))
    sbx.write("many.seam", "-module(many, [p0/1])\n" + body)
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        probe("tq", lambda: load("tq"))
        probe("many", lambda: load("many"))
    """)
    msg = refused(res, "tq", LOAD)["msg"]
    import re
    assert sorted(set(re.findall(r"sandbox_adapter at line (\d+)", msg))) \
        == ["2", "3"], msg
    msg = refused(res, "many", LOAD)["msg"]
    lines = set(re.findall(r"escape at line (\d+)", msg))
    assert lines == {str(i) for i in range(2, 11)}, msg
    assert "more" not in msg


def test_a_bare_import_names_the_denied_predicates_it_brings_in(sbx):
    """Ruling D26: a bare import of an allowed adapter that has denied
    predicates stays refused at load, and the refusal names the library,
    every denied predicate the import brought in, and how to list the
    predicates needed instead (it read as if the adapter were not
    allowed)."""
    sbx.write("bare.clausal", ":- use_module(library(datetime)).\n"
              "go(X) :- date_add(date(2020, 1, 1), 1, X).\n")
    sbx.write("listed.clausal",
              ":- use_module(library(datetime), [date_add/3]).\n"
              "go(X) :- date_add(date(2020, 1, 1), 1, X).\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        probe("bare", lambda: load("bare"))
        probe("listed", lambda: load("listed"))
    """)
    msg = refused(res, "bare", LOAD)["msg"]
    assert "sandbox_adapter at line 1" in msg, msg
    assert ("library(datetime) brings in denied now/1, now_utc/1, "
            "timestamp/2, today/1") in msg, msg
    assert ("list the predicates you need, e.g. "
            "use_module(library(datetime), [date_add/3])") in msg, msg
    assert res["listed"]["ok"], res["listed"]


def test_the_sandbox_forces_the_native_pl_front_end(sbx):
    """Ruling S1: a .pl loads through the native front end in the sandbox,
    whatever CLAUSAL_PL_FRONTEND says.  The translator lowers a float
    evaluable to Python's math, which the audit refuses."""
    sbx.write("fl.pl", ":- module(fl, [r/1]).\nr(X) :- X is sqrt(16.0).\n")
    sbx.write("flw.seam", "-module(flw, [rr/1])\n-import_from(fl, [r])\n"
              "rr(X) <- r(X)\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        from clausal import Var
        from clausal.import_hook import pl_frontend
        X = Var()
        probe("frontend", pl_frontend)
        probe("rr", lambda: answers(("rr", X), load("flw"), X))
    """, env={"CLAUSAL_PL_FRONTEND": "translator"})
    assert ok(res, "frontend") == "'native'"
    assert ok(res, "rr") == "[4.0]"


def test_a_pl_behind_a_python_free_seam_reaches_python_by_default(sbx):
    """Ruling Y1 (pinned, documented): with the sandbox OFF, a .clausal
    file importing a Python-free .seam that imports a .pl doing
    use_module(py/os) reaches Python with no bridge -- Python in a
    .seam/.pl chain is the Python programmer's responsibility.  The sandbox
    refuses the same chain (the .pl's own load)."""
    sbx.write("plpy.pl", PL_PY)
    sbx.write("passthru.seam", "-module(passthru, [p/1])\n"
              "-import_from(plpy, [p])\n")
    sbx.write("top.clausal", ":- module(top, [t/1]).\n"
              ":- use_module(passthru, [p/1]).\nt(X) :- p(X).\n"
              ":- end_module(top).\n")
    body = """
        from clausal import Var
        X = Var()
        probe("t", lambda: answers(("t", X), load("top"), X)
              == [os.getpid()])
    """
    res = sbx.run(body)
    assert ok(res, "t") == "True"
    res = sbx.run("import clausal.sandbox as sb\nsb.enable()\n"
                  + textwrap.dedent(body))
    assert not res["t"]["ok"] and res["t"]["import_error"], res["t"]


def test_a_source_compiled_from_memory_has_no_project(tmp_path, monkeypatch):
    """Ruling Y4: a .clausal compiled from memory has no file and so no
    project -- no python_bridges apply (fail closed) -- instead of the
    pyproject found from the working directory."""
    from clausal import python_bridges as pb
    from clausal.tools import iso_l3
    proj = tmp_path / "ymproj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[tool.clausal]\npython_bridges = ["ymbrg"]\n')
    brg = proj / "ymbrg.seam"
    brg.write_text(BRIDGE.replace("brg", "ymbrg"))
    monkeypatch.chdir(proj)
    monkeypatch.setattr(sys, "path", [str(proj), *sys.path])
    importlib.invalidate_caches()
    # A file importer in the project: allowlisted.
    assert pb.bridge_refusal(str(proj / "imp.clausal"), "ymbrg",
                             str(brg)) is None
    # No file: no project, even though the cwd has one listing it.
    refusal = pb.bridge_refusal(None, "ymbrg", str(brg))
    assert refusal is not None and "none was found" in refusal.message
    src = (":- module(mem, [t/1]).\n:- use_module(ymbrg, [cwd/1]).\n"
           "t(D) :- cwd(D).\n:- end_module(mem).\n")
    with pytest.raises(Exception) as ei:
        iso_l3.lower_source(src, "mem.clausal")
    assert "python_bridge" in str(ei.value), ei.value


@pytest.mark.parametrize("frontend, lib", [
    ("native", "library(units)"), ("translator", "library(units)"),
    ("native", "py/units")])
def test_a_quoted_old_unit_spelling_names_the_new_one(sbx, frontend, lib):
    """Ruling Z1: use_module(library(units), ['SI_Force']) in a .pl stays
    refused (no .pl aliasing) and the refusal names si_force."""
    sbx.write("zf.pl", f":- module(zf, [f/1]).\n"
              f":- use_module({lib}, ['SI_Force']).\nf(1).\n")
    res = sbx.run("""
        import clausal
        probe("load", lambda: load("zf"))
    """, env={"CLAUSAL_PL_FRONTEND": frontend})
    r = res["load"]
    assert not r["ok"], r
    assert "si_force" in r["msg"], r


# ── E1: a package __init__.seam's re-exports are exports ────────────────────

EU_RULES = "-module(rules, [p/1, q/1])\np(1),\np(2),\nq(X) <- p(X)\n"


def _pk_layout(sbx):
    """``nsb/x/__init__.seam`` with NO -module list, only re-imports from
    ``nsb/x/rules.seam`` (a re-exporting package), and bad packages that
    re-export what is no export."""
    sbx.write("nsb/x/__init__.seam", "-import_from(nsb.x.rules, [p/1, q])\n")
    sbx.write("nsb/x/rules.seam", EU_RULES)
    sbx.write("nsb/bad1/__init__.seam",
              "-import_from(nsb.x, [rules])\n")             # a submodule
    sbx.write("nsb/bad2/__init__.seam",
              "-import_from(clausal.modules.py.datetime, "
              "[date_term_to_python])\n")                   # a Python fn
    sbx.write("nsb/bad3/__init__.seam",
              "-import_from(nsb.x.rules, [p, nosuch])\n")    # not an export
    sbx.write("nsb/ok2/__init__.seam",
              "-import_from(clausal.modules.py.datetime, [date_add])\n"
              "-import_from(units, [metre])\n")             # engine exports


def test_package_reexports_are_exports(sbx):
    """Ruling E1: names a listless package __init__.seam re-imports are
    exports, so nsb/ seam domains load in the sandbox -- from a .clausal
    and from a .seam test file."""
    _pk_layout(sbx)
    sbx.write("nbmain.clausal", ":- module(nbmain, [t/1]).\n"
              ":- use_module(nsb/x, [p/1, q/1]).\n"
              "t(X) :- q(X).\n:- end_module(nbmain).\n")
    sbx.write("nbtest.seam", "-module(nbtest, [t/1])\n"
              "-import_from(nsb.x, [p])\nt(X) <- p(X)\n")
    sbx.write("nbok.seam", "-module(nbok, [d/3])\n"
              "-import_from(nsb.ok2, [date_add, metre])\n"
              "d(A, N, B) <- date_add(A, N, B)\n")
    body = """
        from clausal import Var
        X = Var()
        probe("clausal", lambda: answers(("t", X), load("nbmain"), X))
        probe("seam", lambda: answers(("t", X), load("nbtest"), X))
        probe("engine", lambda: answers(
            ("d", ("date", 2020, 1, 1), ("timedelta", 1, 0, 0), X),
            load("nbok"), X))
    """
    res = sbx.run("import clausal.sandbox as sb\nsb.enable()\n"
                  + textwrap.dedent(body))
    off = sbx.run(body)
    assert ok(res, "seam") == "[1, 2]"
    # A .clausal importer naming a re-export by INDICATOR (p/1) is refused
    # by the compiler's own import check (module_signatures leaves
    # re-exports out) -- with the sandbox off exactly as on: the sandbox
    # adds no refusal of its own.  (Pending a ruling on module_signatures.)
    assert res["clausal"]["ok"] == off["clausal"]["ok"]
    if not res["clausal"]["ok"]:
        assert "existence_error(procedure, p/1)" in res["clausal"]["msg"]
        assert "python_escape" not in res["clausal"]["msg"]
    assert ok(res, "engine") == "[('date', 2020, 1, 2)]"


@pytest.mark.parametrize("pkg, name", [
    ("bad1", "rules"), ("bad2", "date_term_to_python"), ("bad3", "nosuch"),
    ("x", "__dict__"), ("x", "__spec__"), ("x", "rules")])
def test_a_reexport_of_no_export_is_still_refused(sbx, pkg, name):
    """E1 security: a package's re-export counts only when it is an export
    of its source -- never a module, a Python function, an attribute of
    the module object, or a name the source does not offer."""
    _pk_layout(sbx)
    sbx.write("nbbad.seam", f"-module(nbbad, [t/1])\n"
              f"-import_from(nsb.{pkg}, [{name}])\nt(1),\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        probe("load", lambda: load("nbbad"))
    """)
    assert not res["load"]["ok"], res["load"]


def test_listless_exports_are_filtered(tmp_path, monkeypatch):
    from clausal import python_bridges as pb
    sb = _Sandbox(tmp_path / "e1")
    _pk_layout(sb)
    sb.write("nsb/bad4/__init__.seam",
             "-import_from(nsb.x.rules, [p])\n-import_module(nsb.x)\n")
    monkeypatch.setattr(sys, "path", [str(sb.root), *sys.path])
    importlib.invalidate_caches()
    exp = {p: pb._exports(f"nsb.{p}", pb._find(f"nsb.{p}"))
           for p in ("x", "bad1", "bad2", "bad3", "bad4", "ok2")}
    assert exp["x"] == {"p", "q"}
    assert exp["bad1"] == frozenset() and exp["bad2"] == frozenset()
    assert exp["bad3"] == {"p"}
    assert exp["bad4"] == {"p"}
    assert exp["ok2"] == {"date_add", "metre"}
    assert not any(n.startswith("_") for e in exp.values() for n in e)


def test_an_allowed_bridge_is_a_file_not_a_name(sbx):
    """Security review round 10 (High): allow_bridges=["brg"] matched any
    module NAMED brg that some importer's own pyproject allowlisted -- a
    rulebase earlier on sys.path could ship its own brg.seam and
    pyproject.  An entry now names one file (a dotted name is resolved
    when enable() runs; a table may pin its sha256)."""
    import hashlib
    sbx.pyproject(['"brg"'])
    sbx.write("brg.seam", BRIDGE)
    sbx.write("bimp.clausal", BRIDGE_IMPORTER)
    evil = BRIDGE.replace("os.getcwd()", "os.getpid()")
    sbx.write("rb/brg.seam", evil)
    sbx.write("rb/pyproject.toml", '[tool.clausal]\npython_bridges = ["brg"]\n')
    sbx.write("rb/x.clausal", BRIDGE_IMPORTER.replace("bimp", "x"))
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable(allow_bridges=["brg"])         # resolves to ./brg.seam
        sys.path.insert(0, os.path.abspath("rb"))  # the rulebase, first
        from clausal import Var
        X = Var()
        probe("evil", lambda: answers(("t", X), load("x"), X))
    """)
    assert not res["evil"]["ok"], res["evil"]
    # A sha256 pin in the entry: the right content loads, other does not.
    good = hashlib.sha256(BRIDGE.encode()).hexdigest()
    for sha, expect in ((good, True), ("0" * 64, False)):
        res = sbx.run(f"""
            import clausal.sandbox as sb
            sb.enable(allow_bridges=[{{"module": "brg", "sha256": "{sha}"}}])
            from clausal import Var
            X = Var()
            probe("t", lambda: answers(("t", X), load("bimp"), X))
        """)
        assert res["t"]["ok"] is expect, res["t"]


def test_only_an_admitting_load_approves_a_bridge(tmp_path, monkeypatch):
    """Security review round 10 (Medium): an approval was recorded by any
    walk -- a run-time check, a walk that went on to refuse."""
    from clausal import python_bridges as pb
    proj = tmp_path / "apr"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(
        '[tool.clausal]\npython_bridges = ["aprbrg"]\n')
    brg = proj / "aprbrg.seam"
    brg.write_text(BRIDGE.replace("brg", "aprbrg"))
    bad = proj / "aprbad.seam"
    bad.write_text("import os\n-module(aprbad, [v/1])\nv(1),\n")
    pas = proj / "aprpass.seam"
    pas.write_text("-module(aprpass, [cwd/1, v/1])\n"
                   "-import_from(aprbrg, [cwd])\n-import_from(aprbad, [v])\n")
    monkeypatch.setattr(sys, "path", [str(proj), *sys.path])
    monkeypatch.setattr(pb, "APPROVED_BRIDGES", {})
    importlib.invalidate_caches()
    imp = str(proj / "i.clausal")
    assert pb.bridge_refusal(imp, "aprbrg", str(brg)) is None
    assert pb.APPROVED_BRIDGES == {}               # not a load: no approval
    assert pb.bridge_refusal(imp, "aprpass", str(pas), record=True)
    assert pb.APPROVED_BRIDGES == {}               # refused walk: none
    assert pb.bridge_refusal(imp, "aprbrg", str(brg), record=True) is None
    assert set(pb.APPROVED_BRIDGES) == {os.path.realpath(brg)}


def test_a_name_held_as_a_module_is_no_export(sbx):
    """E1 security review (Medium): a declared or re-exported name that
    the module object ends up holding as a MODULE -- rebound by an
    -import_module after the clauses, or overwritten by a submodule import
    -- was an export, so an importer could hold the clausal package."""
    sbx.write("nsb/pkg/sub.seam", "-module(sub, [s/1])\ns(1),\n")
    sbx.write("nsb/pkg/a.seam", "-module(a, [x/1])\nx(1),\n")
    sbx.write("nsb/pkg/x.seam", "-module(x, [y/1])\ny(2),\n")
    sbx.write("nsb/pkg/__init__.seam",
              "nsb(1),\nclausal(1),\n-import_module(nsb.pkg.sub)\n"
              "-import_module(clausal.modules.units)\n"
              "-import_from(nsb.pkg.a, [x])\n")
    sbx.write("cons1.seam", "-module(cons1, [t/1])\n"
              "-import_from(nsb.pkg, [clausal])\nt(V) <- (V is clausal)\n")
    sbx.write("cons2.seam", "-module(cons2, [t/1])\n"
              "-import_from(nsb.pkg, [nsb])\nt(V) <- (V is nsb)\n")
    sbx.write("cons3.seam", "-module(cons3, [t/1])\n"
              "-import_from(nsb.pkg.x, [y])\n-import_from(nsb.pkg, [x])\n"
              "t(V) <- (V is x)\n")
    body = """
        for m in ("cons1", "cons2", "cons3"):
            probe(m, lambda m=m: load(m) and True)
        from clausal.python_bridges import _exports, _find
        probe("exports", lambda: sorted(_exports("nsb.pkg", _find("nsb.pkg"))))
    """
    for pre in ("", "import clausal.sandbox as sb\nsb.enable()\n"):
        res = sbx.run("import clausal\n" + pre + textwrap.dedent(body))
        assert ok(res, "exports") == "[]", res["exports"]
        if pre:
            for m in ("cons1", "cons2", "cons3"):
                assert not res[m]["ok"], (m, res[m])


def test_a_submodule_created_later_is_still_no_export(tmp_path, monkeypatch):
    """Security review round 12 (Low): the submodule filter was cached
    under the package file's hash only."""
    from clausal import python_bridges as pb
    root = tmp_path / "late"
    (root / "lpk").mkdir(parents=True)
    (root / "lpk/__init__.seam").write_text("n(1),\n")
    monkeypatch.setattr(sys, "path", [str(root), *sys.path])
    importlib.invalidate_caches()
    origin = pb._find("lpk")
    assert pb._exports("lpk", origin) == {"n"}
    (root / "lpk/n.seam").write_text("-module(n, [z/1])\nz(1),\n")
    importlib.invalidate_caches()
    sys.path_importer_cache.clear()
    assert pb._exports("lpk", origin) == frozenset()



def _same_named_layout(sbx):
    """Packages whose ``__init__`` re-exports a name FROM the submodule of
    the same name: ``nsa/pkx`` (Clausal Prolog, ``pkx/2`` from
    ``nsa/pkx/pkx``) and ``nsa/pky`` (seam, ``pky`` from ``nsa.pky.pky``)."""
    sbx.write("nsa/pkx/pkx.clausal", ":- module(pkx, [pkx/2]).\n"
              "pkx(a, 1).\npkx(b, 2).\n:- end_module(pkx).\n")
    sbx.write("nsa/pkx/__init__.clausal", ":- module(pkx, [pkx/2]).\n"
              ":- use_module(nsa/pkx/pkx, [pkx/2]).\n:- end_module(pkx).\n")
    sbx.write("nsa/pky/pky.seam", "-module(pky, [pky/1])\npky(7),\n")
    sbx.write("nsa/pky/__init__.seam",
              "-module(pky, [pky/1])\n-import_from(nsa.pky.pky, [pky])\n")
    sbx.write("cind.clausal", ":- module(cind, [q/1]).\n"
              ":- use_module(nsa/pkx, [pkx/2]).\n"
              "q(V) :- pkx(b, V).\n:- end_module(cind).\n")
    sbx.write("cseam.seam", "-module(cseam, [t/2])\n"
              "-import_from(nsa.pkx, [pkx])\nt(K, V) <- pkx(K, V)\n")
    sbx.write("cyind.clausal", ":- module(cyind, [q/1]).\n"
              ":- use_module(nsa/pky, [pky/1]).\n"
              "q(V) :- pky(V).\n:- end_module(cyind).\n")
    sbx.write("cyseam.seam", "-module(cyseam, [t/1])\n"
              "-import_from(nsa.pky, [pky])\nt(V) <- pky(V)\n")


@pytest.mark.parametrize("first", ["package", "submodule"])
def test_a_reexport_of_the_same_named_submodule_is_an_export(sbx, first):
    """A package ``__init__`` with an export list that re-exports ``n``
    FROM its submodule ``pkg.n`` (the usual generated layout) is imported
    by indicator (``.clausal``) and by name (``.seam``), in default mode
    and in the sandbox: the init loads ``pkg.n`` before it binds ``n``, so
    the package holds the predicate -- also when an importer loaded the
    submodule first."""
    _same_named_layout(sbx)
    body = """
        from clausal import Var
        from clausal.python_bridges import _exports, _find
        if FIRST == "submodule":
            load("nsa.pkx.pkx"); load("nsa.pky.pky")
        X = Var()
        for m in ("cind", "cseam", "cyind", "cyseam"):
            g = (("q", X) if m.endswith("ind") else
                 ("t", Var(), X) if m == "cseam" else ("t", X))
            probe(m, lambda m=m, g=g: answers(g, load(m), X))
        probe("attrs", lambda: [type(load(p).__dict__[n]).__name__
                                for p, n in (("nsa.pkx", "pkx"),
                                             ("nsa.pky", "pky"))])
        probe("exports", lambda: [sorted(_exports(p, _find(p)))
                                  for p in ("nsa.pkx", "nsa.pky")])
    """.replace("FIRST", repr(first))
    for pre in ("import clausal\n",
                "import clausal.sandbox as sb\nsb.enable()\n"):
        res = sbx.run(pre + textwrap.dedent(body))
        assert ok(res, "cind") == "[2]", (pre, res["cind"])
        assert ok(res, "cseam") == "[1, 2]", (pre, res["cseam"])
        assert ok(res, "cyind") == "[7]", (pre, res["cyind"])
        assert ok(res, "cyseam") == "[7]", (pre, res["cyseam"])
        assert ok(res, "attrs") == "['str', 'str']", (pre, res["attrs"])
        assert ok(res, "exports") == "[['pkx'], ['pky']]", (pre, res)


def test_a_defined_name_beside_its_submodule_is_still_no_export(sbx):
    """The exception is the re-export FROM ``pkg.n`` only: an ``__init__``
    that DEFINES ``n`` and imports other names from ``pkg.n`` ends up
    holding the submodule under ``n`` (the submodule's first load writes
    the attribute after the definition), so ``n`` stays no export."""
    sbx.write("nsa/pkz/pkz.clausal", ":- module(pkz, [m/1]).\nm(1).\n"
              ":- end_module(pkz).\n")
    sbx.write("nsa/pkz/__init__.clausal", ":- module(pkz, [pkz/1, m/1]).\n"
              ":- use_module(nsa/pkz/pkz, [m/1]).\npkz(1).\n"
              ":- end_module(pkz).\n")
    sbx.write("dind.clausal", ":- module(dind, [q/1]).\n"
              ":- use_module(nsa/pkz, [pkz/1]).\n"
              "q(V) :- pkz(V).\n:- end_module(dind).\n")
    sbx.write("dseam.seam", "-module(dseam, [t/1])\n"
              "-import_from(nsa.pkz, [pkz])\nt(V) <- (V is pkz)\n")
    body = """
        from clausal.python_bridges import _exports, _find
        probe("pkg", lambda: load("nsa.pkz") and True)
        probe("exports", lambda: sorted(_exports("nsa.pkz", _find("nsa.pkz"))))
        for m in ("dind", "dseam"):
            probe(m, lambda m=m: load(m) and True)
    """
    res = sbx.run("import clausal\n" + textwrap.dedent(body))
    # Sandbox off, the clobber shows: the package's own pkz is the module.
    assert "'module' object is not callable" in res["pkg"]["msg"], res
    assert ok(res, "exports") == "['m']", res["exports"]
    res = sbx.run("import clausal.sandbox as sb\nsb.enable()\n"
                  + textwrap.dedent(body))
    assert ok(res, "exports") == "['m']", res["exports"]
    for m in ("dind", "dseam"):
        r = refused(res, m, LOAD, import_error=True)
        assert "submodule_name" in r["msg"], r


def test_a_reexport_read_inside_its_init_is_no_export(sbx):
    """The window of the exception: between the submodule's first load
    and the ``__init__``'s binding the package attribute is the module.  A
    module the ``__init__`` loads first that loads the submodule and then
    imports the name from the still-initialising package would hold the
    module object; the re-export counts only once the package has
    finished initialising (or before it starts)."""
    sbx.write("nsc/pkc/pkc.seam", "-module(pkc, [pkc/1, m/1])\n"
              "pkc(1),\nm(2),\n")
    sbx.write("nsc/pkc/other.seam", "-module(other, [o/1])\n"
              "-import_from(nsc.pkc.pkc, [m])\n"
              "-import_from(nsc.pkc, [pkc])\no(V) <- (V is pkc)\n")
    sbx.write("nsc/pkc/__init__.seam", "-module(pkc, [pkc/1, o/1])\n"
              "-import_from(nsc.pkc.other, [o])\n"
              "-import_from(nsc.pkc.pkc, [pkc])\n")
    body = """
        import sys
        probe("pkg", lambda: load("nsc.pkc") and True)
        probe("other", lambda: type(
            sys.modules["nsc.pkc.other"].__dict__.get("pkc")).__name__)
    """
    res = sbx.run("import clausal\n" + textwrap.dedent(body))
    assert ok(res, "other") == "'module'", res      # the window, sandbox off
    res = sbx.run("import clausal.sandbox as sb\nsb.enable()\n"
                  + textwrap.dedent(body))
    r = refused(res, "pkg", LOAD, import_error=True)
    assert "submodule_name" in r["msg"], r
    assert not res["other"]["ok"], res["other"]   # never loaded



def test_await_escapes_and_async_goals_are_refused_at_load(sbx):
    """1.0.0's ``++await`` in a clause and ``--goal`` inside ``async def``
    are escapes / hosted Python: the audit refuses the module."""
    src = open(os.path.join(ENGINE_ROOT, "tests", "fixtures",
                            "aio_seam.seam")).read()
    sbx.write("aio_seam.seam", src)
    sbx.write("aw1.seam", "-module(aw1, [g/1])\n"
              "g(X) <- (X is ++await f())\n")
    sbx.write("aw2.seam", "-module(aw2, [h/1])\n-private([x])\n"
              "h(1),\nasync def run():\n    return [X for X in --h(X)]\n")
    sbx.write("aw3.clausal", ":- module(aw3, [t/1]).\n"
              ":- use_module(library(asyncio), [sleep/1]).\n"
              "t(X) :- sleep(0), X = 1.\n:- end_module(aw3).\n")
    res = sbx.run("""
        import clausal.sandbox as sb
        sb.enable()
        for m in ("aio_seam", "aw1", "aw2", "aw3"):
            probe(m, lambda m=m: load(m))
    """)
    for m in ("aio_seam", "aw1", "aw2", "aw3"):
        r = refused(res, m, LOAD, import_error=True)
    assert "escape" in res["aw1"]["msg"], res["aw1"]
    assert "python_def" in res["aw2"]["msg"], res["aw2"]


# ── M3: module_signatures includes a listless package's re-exports ──────────


def test_a_clausal_imports_a_package_reexport_by_indicator(sbx):
    """Ruling M3: use_module(nsb/x, [p/1]) against a
    listless package loads and answers, in default mode and in the
    sandbox (module_signatures now offers the package's re-exports)."""
    _pk_layout(sbx)
    sbx.write("nbmain.clausal", ":- module(nbmain, [t/1, u/1]).\n"
              ":- use_module(nsb/x, [p/1, q/1]).\n"
              "t(X) :- p(X).\nu(X) :- q(X).\n:- end_module(nbmain).\n")
    body = """
        from clausal import Var, module_signatures
        X = Var()
        m = load("nbmain")
        probe("t", lambda: answers(("t", X), m, X))
        probe("u", lambda: answers(("u", X), m, X))
        probe("sigs", lambda: sorted(module_signatures(load("nsb.x")).items()))
    """
    for pre in ("import clausal\n",
                "import clausal.sandbox as sb\nsb.enable()\n"):
        res = sbx.run(pre + textwrap.dedent(body))
        assert ok(res, "t") == "[1, 2]", (pre, res["t"])
        assert ok(res, "u") == "[1, 2]", (pre, res["u"])
        assert ok(res, "sigs") == (
            "[('p', frozenset({1})), ('q', frozenset({1}))]")


@pytest.mark.parametrize("pkg", ["bad1", "bad2", "bad4", "pkg"])
def test_module_signatures_offers_no_python_through_a_reexport(sbx, pkg):
    """M3 security: the E1 exclusions hold for module_signatures too --
    a re-exported submodule, Python function, non-export, a name an
    -import_module binds, or one a submodule import overwrites, is no
    predicate it offers; nothing underscore-led ever is."""
    _pk_layout(sbx)
    sbx.write("nsb/bad4/__init__.seam",
              "-import_from(nsb.x.rules, [p])\n-import_module(nsb.x)\n")
    sbx.write("nsb/pkg/sub.seam", "-module(sub, [s/1])\ns(1),\n")
    sbx.write("nsb/pkg/a.seam", "-module(a, [x/1])\nx(1),\n")
    sbx.write("nsb/pkg/x.seam", "-module(x, [y/1])\ny(2),\n")
    sbx.write("nsb/pkg/__init__.seam",
              "nsb(1),\n-import_module(nsb.pkg.sub)\n"
              "-import_from(nsb.pkg.a, [x])\n")
    res = sbx.run(f"""
        import clausal
        from clausal import module_signatures
        load("nsb.pkg.x")                     # overwrites nsb.pkg.x
        probe("sigs", lambda: sorted(module_signatures(
            load("nsb.{pkg}"))))
    """)
    expect = {"bad1": [], "bad2": [], "bad4": ["p"], "pkg": []}[pkg]
    assert ok(res, "sigs") == repr(expect), res["sigs"]


def _m3_layout(sbx):
    _pk_layout(sbx)
    sbx.write("nsb/x/rules.seam",
              "-module(rules, [p/1, q/1, low, pt(x, y)])\n"
              "p(1),\np(2),\nq(X) <- p(X)\n")
    sbx.write("nsb/x/__init__.seam",
              "-import_from(nsb.x.rules, [p/1, q, low, pt])\n")
    sbx.write("nsb/sm/a.seam", "-module(a, [lim/3, k/1])\n"
              "lim(1, 2, 3),\nk(1),\n")
    sbx.write("nsb/sm/lim.seam", "-module(lim, [z/1])\nz(1),\n")
    sbx.write("nsb/sm/__init__.seam", "-import_from(nsb.sm.a, [lim, k])\n")


def test_use_module_1_imports_a_listless_package(sbx):
    """M3: use_module(pkg) (no list) on a listless package __init__ used
    to refuse ("declares no module/2 export list"); it imports what the
    package re-exports, in default mode and in the sandbox."""
    _m3_layout(sbx)
    sbx.write("nb1.clausal", ":- module(nb1, [t/1]).\n"
              ":- use_module(nsb/x).\nt(X) :- q(X).\n:- end_module(nb1).\n")
    body = """
        from clausal import Var
        X = Var()
        probe("t", lambda: answers(("t", X), load("nb1"), X))
    """
    for pre in ("import clausal\n",
                "import clausal.sandbox as sb\nsb.enable()\n"):
        res = sbx.run(pre + textwrap.dedent(body))
        assert ok(res, "t") == "[1, 2]", (pre, res["t"])


def test_listless_exports_include_atoms_and_constructors(tmp_path,
                                                         monkeypatch):
    """M3 item 2: names, not only predicates -- a re-imported atom or
    constructor is an export (arity None); module_signatures still lists
    predicates only."""
    from clausal import python_bridges as pb
    from clausal.tools.iso_l3_directives import _declared_exports
    sb = _Sandbox(tmp_path / "m3a")
    _m3_layout(sb)
    monkeypatch.setattr(sys, "path", [str(sb.root), *sys.path])
    importlib.invalidate_caches()
    init = str(sb.root / "nsb/x/__init__.seam")
    entries = _declared_exports(init)[1]
    assert ("p", 1) in entries and ("q", 1) in entries
    assert ("low", None) in entries and ("pt", None) in entries
    assert pb._exports("nsb.x", init) == {"p", "q", "low", "pt"}
    # The switch for re-exports from OUTSIDE the package (ruling pending).
    ok2 = str(sb.root / "nsb/ok2/__init__.seam")
    assert {n for n, _a in pb.listless_exports(ok2)} == {"date_add", "metre"}
    monkeypatch.setattr(pb, "REEXPORTS_FROM_OUTSIDE_PACKAGE", False)
    assert pb.listless_exports(ok2) == []
    assert {n for n, _a in pb.listless_exports(init)} == {
        "p", "q", "low", "pt"}


def test_a_reexport_named_like_a_submodule_says_so(sbx):
    """M3 item 3: lim/3 re-exported by a package that also has the
    submodule nsb.sm.lim is no export; the refusal says why."""
    _m3_layout(sbx)
    sbx.write("smc.clausal", ":- module(smc, [t/1]).\n"
              ":- use_module(nsb/sm, [lim/3]).\nt(X) :- lim(X, _, _).\n"
              ":- end_module(smc).\n")
    sbx.write("sms.seam", "-module(sms, [t/1])\n-import_from(nsb.sm, [lim])\n"
              "t(X) <- lim(X, _, _)\n")
    sbx.write("smk.seam", "-module(smk, [t/1])\n-import_from(nsb.sm, [k])\n"
              "t(X) <- k(X)\n")
    res = sbx.run("""
        import clausal
        from clausal import Var
        X = Var()
        load("nsb.sm.lim")
        probe("clausal", lambda: load("smc"))
        probe("k", lambda: answers(("t", X), load("smk"), X))
        from clausal.python_bridges import file_python_routes
        probe("routes", lambda: file_python_routes(os.path.abspath(
            "sms.seam")))
    """)
    assert "is also the submodule nsb.sm.lim; import it from the submodule" \
        in res["clausal"]["msg"], res["clausal"]
    assert ok(res, "k") == "[1]"
    assert "submodule_name" in ok(res, "routes")


def test_the_exporter_lists_a_package_reexport(tmp_path, monkeypatch):
    """M3 item 5: clausal_to_prolog's plain-layout import list filters on
    module_signatures, so a re-imported predicate now exports as p/1
    (it exported as nothing before)."""
    from clausal.tools import clausal_to_prolog as c2p
    sb = _Sandbox(tmp_path / "m3x")
    _m3_layout(sb)
    monkeypatch.setattr(sys, "path", [str(sb.root), *sys.path])
    importlib.invalidate_caches()
    c2p._engine_signature.cache_clear()
    src = ("-module(user1, [t/1])\n-import_from(nsb.x, [p, q])\n"
           "t(X) <- (p(X), q(X))\n")
    out = c2p.clausal_source_to_prolog(src, module_path="user1",
                                       module_specs="plain")
    line = [ln for ln in out.splitlines() if "use_module" in ln]
    assert line and "p/1" in line[0] and "q/1" in line[0], out


# ── engine container terms in a goal (a user report) ────────────────────────


def test_a_goal_may_hold_the_engines_dict_and_set_terms():
    """``docs/sandbox.md`` allows dicts of data in a goal; the engine's own
    DictTerm and SetTerm were refused as Python objects although a plain
    dict passed.  They are walked like a dict: every key, value and
    element must itself be data."""
    from clausal.logic.variables import Var
    from clausal.sandbox import check_term
    from clausal.terms import DictTerm, SetTerm
    check_term(DictTerm({"k": 1, "n": [1, ("f", "a")]}))
    check_term(SetTerm({1, "a", ("f", 2)}))
    check_term(("p", DictTerm({"k": SetTerm({"a"})}), Var()))


@pytest.mark.parametrize("shape", [
    "dict_value", "dict_key", "set_element", "nested", "subclass_dict",
    "subclass_set"])
def test_python_inside_a_dict_or_set_term_is_refused(shape):
    from clausal.logic.exceptions import LogicException
    from clausal.sandbox import check_term
    from clausal.terms import DictTerm, SetTerm

    class D(DictTerm):
        pass

    class S(SetTerm):
        pass

    term = {
        "dict_value": lambda: DictTerm({"k": os}),
        "dict_key": lambda: DictTerm({os: 1}),
        "set_element": lambda: SetTerm({os}),
        "nested": lambda: ("p", [DictTerm({"k": SetTerm({object()})})]),
        "subclass_dict": lambda: D({"k": 1}),
        "subclass_set": lambda: S({1}),
    }[shape]()
    with pytest.raises(LogicException) as e:
        check_term(term)
    assert "python_object" in str(e.value)
