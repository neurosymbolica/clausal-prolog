"""Python bridges: what a Clausal Prolog importer may reach (operator ruling
2026-10-04, :mod:`clausal.python_bridges`).

From a ``.clausal`` importer, Python is reachable only through (1) engine-
shipped modules (the ``library(...)`` facades, the stdlib), (2) a ``.seam``
module with no Python in it, checked at load, and (3) a ``.seam`` module
WITH Python that the importer's project lists in ``[tool.clausal]
python_bridges`` of its nearest ``pyproject.toml`` (optionally sha256-
pinned).  Anything else is ``permission_error(import, python_bridge, M)``:
at load for ``use_module``, at run time for ``M:G`` into a module someone
else loaded.  ``.seam`` and ``.pl`` importers are not affected.
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import os
import shutil
import sys
import textwrap

import pytest

from clausal import _suffixes
from clausal import import_hook as ih  # noqa: F401 -- installs the finders
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.python_bridges import (
    ROUTE_KINDS, bridge_refusal, file_python_routes, find_project_file,
    is_engine_shipped, python_routes)


REFUSAL = "permission_error(import, python_bridge, {m})"


# ── python_routes: the one detector ─────────────────────────────────────────


def _routes(src: str):
    src = textwrap.dedent(src)
    return python_routes(ast.parse(src), src)


def _kinds(src: str):
    return [k for k, _line in _routes(src)]


CLEAN = """\
-module(clean, [p/1, q/2, greeting/1])
-private([a, b])
-dynamic(seen/1)
\"\"\"A docstring is no Python.\"\"\"
p(a),
p(b)
p(c),
edge(1, 2),
q(X, Y) <- (edge(X, Y), X < Y)
q(X, Y) <- (findall(Z, p(Z), Y), X is 1 + 2)
greeting >> ([h, i])
greeting(S) <- (S is f"hello {S}")
r(L) <- (L is [X for X in [1, 2, 3]])
s(P, V) <- (V is P.key)
flag,
*(p(X))
"""


def test_a_python_free_module_has_no_routes():
    assert _routes(CLEAN) == []


@pytest.mark.parametrize("kind, src, line", [
    ("escape", "p(X) <- (X is ++os.getcwd())\n", 1),
    ("escape", "p(X) <- (q(X), X is ++len([1]))\n", 1),
    ("seam", "p(X) <- (X is --Y)\n", 1),
    ("fstring", 'p(S) <- (S is f"{len(S)}")\n', 1),
    ("fstring", 'p(S) <- (S is f"{S.upper()}")\n', 1),
    ("fstring", 'p(S, W) <- (S is f"{S:>{W + 1}}")\n', 1),
    ("python_import", "import os\n", 1),
    ("python_import", "from os import getcwd\n", 1),
    ("python_def", "def f():\n    return 1\n", 1),
    ("python_def", "@{}\ndef t(X):\n    {X}\n", 2),
    ("python_class", "class C:\n    pass\n", 1),
    ("python_statement", "x = 1\n", 1),
    ("python_statement", "x += 1\n", 1),
    ("python_statement", "if True:\n    pass\n", 1),
    ("python_statement", "for i in []:\n    pass\n", 1),
    ("python_statement", "with open('f') as f:\n    pass\n", 1),
    ("python_statement", 'print("hi")\n', 1),
    ("python_statement", "os.system('ls')\n", 1),
    ("python_statement", "x == 1\n", 1),
])
def test_each_route_kind_is_detected(kind, src, line):
    assert kind in ROUTE_KINDS
    assert (kind, line) in _routes(src), _routes(src)


def test_routes_carry_their_lines_in_order():
    src = ("-module(m, [p/1])\n"
           "import os\n"
           "p(X) <- (X is ++os.getcwd())\n"
           "x = 1\n")
    assert _routes(src) == [("python_import", 2), ("escape", 3),
                            ("python_statement", 4)]


def test_an_inert_fstring_slot_is_no_python():
    """Interpolating a bare name (with a constant spec, any conversion)
    evaluates nothing."""
    assert _kinds('p(S, N) <- (S is f"{N!r:>8} and {N}")\n') == []


def test_a_comma_less_fact_needs_an_earlier_head():
    """``f(1)`` without a comma is a fact only for a functor an earlier
    clause established (the compiler's rule); before that it is a hosted
    Python call."""
    assert _kinds("f(0),\nf(1)\n") == []
    assert _kinds("f(1)\nf(0),\n") == ["python_statement"]


def test_spaced_plus_plus_is_arithmetic_not_an_escape():
    assert _kinds("p(X, Y) <- (X is + +Y)\n") == []


def test_file_routes_include_python_module_imports(tmp_path):
    f = tmp_path / "pm.seam"
    f.write_text("-module(pm, [p/1])\n-import_from(os, [getcwd])\n"
                 "-import_from(units, [metre])\np(1),\n")
    # os is Python and not the engine's; units is the engine's own module.
    assert file_python_routes(str(f)) == [("python_module", 2)]


def test_engine_shipped():
    import clausal.library
    lib = os.path.join(os.path.dirname(clausal.library.__file__),
                       "py_os.seam")
    assert is_engine_shipped("clausal.library.py_os", lib)
    # A clausal.* NAME alone is not enough: the file must be in the package.
    assert not is_engine_shipped("clausal.library.fake", "/tmp/fake.seam")


def test_find_project_file_is_the_nearest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    f = sub / "m.clausal"
    f.write_text("")
    assert find_project_file(str(f)) == str(tmp_path / "pyproject.toml")
    (tmp_path / "a" / "pyproject.toml").write_text("")
    assert find_project_file(str(f)) == str(tmp_path / "a" /
                                            "pyproject.toml")


# ── the gate, end to end ────────────────────────────────────────────────────


class Project:
    """A project root on sys.path with its own pyproject.toml."""

    def __init__(self, root, monkeypatch, prefix):
        self.root = root
        self.prefix = prefix
        self.names: list[str] = []
        root.mkdir(parents=True, exist_ok=True)
        monkeypatch.syspath_prepend(str(root))
        self.allow([])

    def n(self, name):
        return f"{self.prefix}_{name}"

    def allow(self, entries, raw=None):
        body = raw if raw is not None else (
            "[project]\nname = \"x\"\n[tool.clausal]\npython_bridges = ["
            + ", ".join(entries) + "]\n")
        p = self.root / "pyproject.toml"
        p.write_text(body)
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))

    def write(self, name, suffix, text):
        path = self.root / (self.n(name) + suffix)
        path.write_text(text.replace("@", self.prefix + "_"))
        self.names.append(self.n(name))
        sys.modules.pop(self.n(name), None)
        return path

    def seam(self, name, text):
        return self.write(name, ".seam", text)

    def clausal(self, name, imports, body):
        m = self.n(name)
        return self.write(name, ".clausal",
                          f":- module({m}, [t/1]).\n{imports}{body}"
                          f":- end_module({m}).\n")

    def load(self, name, *, keep_cache=False):
        if not keep_cache:
            for p in self.root.rglob("__pycache__"):
                shutil.rmtree(p, ignore_errors=True)
        importlib.invalidate_caches()
        sys.modules.pop(self.n(name), None)
        return importlib.import_module(self.n(name))

    def close(self):
        for n in self.names:
            sys.modules.pop(n, None)
        for p in self.root.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        importlib.invalidate_caches()


@pytest.fixture
def proj(tmp_path, monkeypatch):
    assert _suffixes.CLAUSAL_PROLOG_SUFFIXES == (".clausal",)
    p = Project(tmp_path / "proj", monkeypatch, "pb" + str(abs(hash(
        str(tmp_path))) % 10_000_000))
    yield p
    p.close()


def _answers(mod, pred="t"):
    x = Var()
    return [walk(deref(x)) for _ in call(pred, x, module=mod)]


def _refused(proj, name) -> str:
    with pytest.raises((SyntaxError, ImportError)) as ei:
        proj.load(name)
    return str(ei.value)


#: A Python bridge: cwd/1 answers the working directory through ++.
BRIDGE = ("import os\n-module(@helper, [cwd/1])\n"
          "cwd(D) <- (D is ++os.getcwd())\n")
CLEAN_LIB = "-module(@clean, [p/1])\np(1),\np(2),\n"
IMPORT_HELPER = ":- use_module(@helper, [cwd/1]).\n"
CWD_BODY = "t(D) :- cwd(D).\n"


#: One Python-hosting .seam per route kind (each loads fine as .seam).
ROUTE_SEAMS = {
    "escape": "-module(@helper, [cwd/1])\ncwd(D) <- (D is ++(1 + 1))\n",
    "seam": "-module(@helper, [cwd/1])\ncwd(D) <- (D is --{})\n",
    "fstring": '-module(@helper, [cwd/1])\ncwd(D) <- (D is f"{1 + 1}")\n',
    "py_adapter": "-module(@helper, [cwd/1])\n"
                  "-import_from(py.pbfake, [value])\ncwd(1),\n",
    "python_import": BRIDGE,
    "python_def": "-module(@helper, [cwd/1])\ndef f():\n    return 1\n"
                  "cwd(1),\n",
    "python_class": "-module(@helper, [cwd/1])\nclass C:\n    pass\n"
                    "cwd(1),\n",
    "python_statement": "-module(@helper, [cwd/1])\nprint('x')\ncwd(1),\n",
    "python_module": "-module(@helper, [cwd/1])\n"
                     "-import_from(os, [getcwd])\ncwd(1),\n",
}


@pytest.fixture
def spliced_adapter(tmp_path, monkeypatch):
    """An adapter an optional package splices into clausal.modules.py
    (as packages/clausal-* do): the same namespace, NOT the engine's file."""
    import clausal.modules.py as pyns
    d = tmp_path / "pkgsplice"
    d.mkdir()
    (d / "pbfake.py").write_text("value = 42\n")
    monkeypatch.setattr(pyns, "__path__", [*pyns.__path__, str(d)])
    yield "clausal.modules.py.pbfake"
    sys.modules.pop("clausal.modules.py.pbfake", None)
    sys.modules.pop("py.pbfake", None)


@pytest.mark.parametrize("kind", sorted(ROUTE_SEAMS))
def test_each_route_kind_is_refused_from_clausal_prolog(
        proj, kind, spliced_adapter):
    assert kind in ROUTE_KINDS
    proj.seam("helper", ROUTE_SEAMS[kind])
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg
    assert kind in msg, msg
    # The message says how to allowlist it, and where.
    assert "[tool.clausal]" in msg and "python_bridges" in msg, msg
    assert str(proj.root / "pyproject.toml") in msg, msg


def test_a_python_free_seam_is_allowed(proj):
    proj.seam("clean", CLEAN_LIB)
    proj.clausal("main", ":- use_module(@clean, [p/1]).\n",
                 "t(X) :- p(X).\n")
    assert _answers(proj.load("main")) == [1, 2]


def test_an_allowlisted_bridge_by_module_name(proj):
    proj.seam("helper", BRIDGE)
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    proj.allow([f'"{proj.n("helper")}"'])
    assert _answers(proj.load("main")) == [os.getcwd()]


def test_an_allowlisted_bridge_by_path(proj):
    proj.seam("helper", BRIDGE)
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    proj.allow([f'"{proj.n("helper")}.seam"'])
    assert _answers(proj.load("main")) == [os.getcwd()]


def test_an_allowlisted_bridge_with_its_sha_pin(proj):
    path = proj.seam("helper", BRIDGE)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    proj.allow([f'{{ module = "{proj.n("helper")}", sha256 = "{sha}" }}'])
    assert _answers(proj.load("main")) == [os.getcwd()]
    proj.allow([f'{{ path = "{path.name}", sha256 = "{sha.upper()}" }}'])
    assert _answers(proj.load("main")) == [os.getcwd()]


def test_a_wrong_sha_pin_is_refused_with_both_hashes(proj):
    path = proj.seam("helper", BRIDGE)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    wrong = "0" * 64
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    proj.allow([f'{{ module = "{proj.n("helper")}", sha256 = "{wrong}" }}'])
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg
    assert wrong in msg and actual in msg, msg


@pytest.mark.parametrize("raw", [
    "[tool.clausal]\npython_bridges = \"helper\"\n",
    "[tool.clausal]\npython_bridges = [{ sha256 = \"00\" }]\n",
    "[tool.clausal]\npython_bridges = [{ module = \"h\", sha256 = \"0\" }]\n",
    "[tool.clausal]\npython_bridges = [\"not a module\"]\n",
    "[tool.clausal\n",
    "[tool]\nclausal = \"x\"\n",
    "tool = 3\n",
])
def test_a_malformed_allowlist_fails_closed(proj, raw):
    proj.seam("helper", BRIDGE)
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    proj.allow([], raw=raw)
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg
    assert "could not be used" in msg, msg


def test_engine_library_facades_still_work(proj):
    proj.clausal("main", ":- use_module(library(datetime), "
                 "[days_between/3]).\n",
                 "t(N) :- days_between(date(2026, 1, 31), "
                 "date(2026, 1, 1), N).\n")
    assert _answers(proj.load("main")) == [30]


def test_a_seam_importer_is_not_affected(proj):
    proj.seam("helper", BRIDGE)
    proj.seam("user", "-module(@user, [t/1])\n-import_from(@helper, [cwd])\n"
                      "t(D) <- (cwd(D))\n")
    assert _answers(proj.load("user")) == [os.getcwd()]


def test_a_pl_importer_is_not_affected(proj):
    proj.seam("helper", BRIDGE)
    proj.write("user", ".pl", ":- module(@user, [t/1]).\n"
                              ":- use_module(@helper, [cwd/1]).\n"
                              "t(D) :- cwd(D).\n")
    assert _answers(proj.load("user")) == [os.getcwd()]


def test_import_order_cannot_bypass_the_gate(proj):
    """The bridge was loaded first by a .seam importer: a .clausal
    use_module of it is refused all the same (the FILE is judged, not the
    module object)."""
    proj.seam("helper", BRIDGE)
    proj.seam("loader", "-module(@loader, [])\n-import_from(@helper, [cwd])\n")
    proj.load("loader")
    assert proj.n("helper") in sys.modules
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg


@pytest.mark.parametrize("body", [
    "t(D) :- @helper:cwd(D).\n",
    "t(D) :- call(@helper:cwd(D)).\n",
    "t(D) :- G = @helper:cwd(D), call(G).\n",
])
def test_a_qualified_call_into_a_loaded_bridge_is_refused(proj, body):
    """Run time: M:G from Clausal Prolog into a Python bridge some other
    importer loaded raises the same error term, catchable by catch/3."""
    proj.seam("helper", BRIDGE)
    proj.seam("loader", "-module(@loader, [])\n-import_from(@helper, [cwd])\n")
    proj.load("loader")
    proj.clausal("main", "", body)
    mod = proj.load("main")
    with pytest.raises(LogicException) as ei:
        _answers(mod)
    term = ei.value.term
    assert term[0] == "error" and term[1][:4] == (
        "permission_error", "import", "python_bridge", proj.n("helper")), term
    # Allowlisted, the same call runs.
    proj.allow([f'"{proj.n("helper")}"'])
    assert _answers(proj.load("main")) == [os.getcwd()]


def test_the_refusal_is_catchable_in_clausal_prolog(proj):
    proj.seam("helper", BRIDGE)
    proj.seam("loader", "-module(@loader, [])\n-import_from(@helper, [cwd])\n")
    proj.load("loader")
    proj.clausal("main", "", "t(K) :- catch(@helper:cwd(_), "
                 "error(permission_error(A, K0, M), _), K = [A, K0, M]).\n")
    assert _answers(proj.load("main")) == [
        ["import", "python_bridge", proj.n("helper")]]


def test_a_cached_importer_is_judged_again(proj):
    """The bytecode cache does not carry the decision: the cache-hit path
    re-lowers the directives, so removing the allowlist entry refuses the
    next load."""
    proj.seam("helper", BRIDGE)
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    proj.allow([f'"{proj.n("helper")}"'])
    assert _answers(proj.load("main")) == [os.getcwd()]
    proj.allow([])
    with pytest.raises((SyntaxError, ImportError)) as ei:
        proj.load("main", keep_cache=True)
    assert REFUSAL.format(m=proj.n("helper")) in str(ei.value)


def test_a_pass_through_seam_is_checked_transitively(proj):
    """A Python-free .seam is a pass-through: the Python .seam it imports
    must itself be allowlisted, and the refusal names it and the chain."""
    proj.seam("helper", BRIDGE)
    proj.seam("mid", "-module(@mid, [cwd/1])\n-import_from(@helper, [cwd])\n")
    proj.clausal("main", ":- use_module(@mid, [cwd/1]).\n", CWD_BODY)
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg
    assert f"{proj.n('mid')} (line 2)" in msg, msg
    proj.allow([f'"{proj.n("helper")}"'])
    assert _answers(proj.load("main")) == [os.getcwd()]


def test_a_dotted_call_in_a_pass_through_is_a_reference(proj):
    proj.seam("helper", BRIDGE)
    proj.seam("mid", "-module(@mid, [cwd/1])\n"
                     "cwd(D) <- (@helper.cwd(D))\n")
    proj.clausal("main", ":- use_module(@mid, [cwd/1]).\n", CWD_BODY)
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg


def test_an_allowlisted_bridge_s_own_imports_are_its_business(proj):
    proj.seam("inner", "import os\n-module(@inner, [cwd/1])\n"
                       "cwd(D) <- (D is ++os.getcwd())\n")
    proj.seam("helper", "import sys\n-module(@helper, [cwd/1])\n"
                        "-import_from(@inner, [cwd])\n")
    proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    proj.allow([f'"{proj.n("helper")}"'])
    assert _answers(proj.load("main")) == [os.getcwd()]


def test_the_importer_s_project_decides_not_the_entry_project(
        tmp_path, monkeypatch):
    """Two project roots: the process's ENTRY project (the working
    directory, whose pyproject allowlists the bridge) and the IMPORTING
    file's project (whose pyproject does not).  The importer's nearest
    pyproject.toml is the one consulted; cwd and sys.argv play no part."""
    entry = tmp_path / "entry"
    importer = Project(tmp_path / "corpus", monkeypatch, "pbent")
    try:
        entry.mkdir()
        importer.seam("helper", BRIDGE)
        importer.clausal("main", IMPORT_HELPER, CWD_BODY)
        (entry / "pyproject.toml").write_text(
            "[tool.clausal]\npython_bridges = "
            f"[\"{importer.n('helper')}\", "
            f"\"{importer.root / (importer.n('helper') + '.seam')}\"]\n")
        monkeypatch.chdir(entry)
        monkeypatch.setattr(sys, "argv", [str(entry / "main.py")])
        msg = _refused(importer, "main")
        assert REFUSAL.format(m=importer.n("helper")) in msg, msg
        assert str(importer.root / "pyproject.toml") in msg, msg
        # And the other way round: the importer's project trusts it, the
        # entry project does not -- allowed.
        (entry / "pyproject.toml").write_text(
            "[tool.clausal]\npython_bridges = []\n")
        importer.allow([f'"{importer.n("helper")}"'])
        assert _answers(importer.load("main")) == [str(entry)]
    finally:
        importer.close()


def test_bridge_refusal_api(proj):
    path = proj.seam("helper", BRIDGE)
    main = proj.clausal("main", IMPORT_HELPER, CWD_BODY)
    r = bridge_refusal(str(main), proj.n("helper"), str(path))
    assert r is not None and r.module == proj.n("helper")
    assert r.term_text == REFUSAL.format(m=proj.n("helper"))
    proj.allow([f'"{proj.n("helper")}"'])
    assert bridge_refusal(str(main), proj.n("helper"), str(path)) is None


def test_a_run_time_call_follows_the_allowlist_without_a_reload(proj):
    """``call/N`` resolves at run time: editing the allowlist changes the
    answer for the module already loaded (no process-lifetime cache)."""
    proj.seam("helper", BRIDGE)
    proj.seam("loader", "-module(@loader, [])\n-import_from(@helper, [cwd])\n")
    proj.load("loader")
    proj.clausal("main", "", "t(D) :- G = @helper:cwd(D), call(G).\n")
    mod = proj.load("main")
    with pytest.raises(LogicException):
        _answers(mod)
    proj.allow([f'"{proj.n("helper")}"'])
    assert _answers(mod) == [os.getcwd()]
    proj.allow([])
    with pytest.raises(LogicException):
        _answers(mod)


@pytest.mark.parametrize("init", [
    "open({marker!r}, 'w').write('ran')\n",
    "open({marker!r}, 'w').write('ran')\nraise RuntimeError('boom')\n",
])
def test_the_gate_imports_nothing_it_judges(proj, init):
    """A pass-through naming a Python package: the package's ``__init__``
    does not run while the gate decides (it is refused first), and an
    ``__init__`` that would raise does not replace the refusal."""
    marker = proj.root / "marker.txt"
    pkg = proj.root / (proj.n("pkg"))
    pkg.mkdir()
    (pkg / "__init__.py").write_text(init.format(marker=str(marker)))
    (pkg / "sub.py").write_text("x = 1\n")
    proj.names.append(proj.n("pkg"))
    proj.seam("mid", "-module(@mid, [p/1])\n-import_from(@pkg.sub, [x])\n"
                     "p(1),\n")
    proj.clausal("main", ":- use_module(@mid, [p/1]).\n", "t(X) :- p(X).\n")
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("mid")) in msg, msg
    assert "python_module at line 2" in msg, msg
    assert not marker.exists()


@pytest.mark.parametrize("imports, body", [
    ("-import_from(date_time, [days_between])\n",
     "p(N) <- (days_between(date(2026, 1, 31), date(2026, 1, 1), N))\n"),
    ("-import_from(py.datetime, [days_between])\n",
     "p(N) <- (days_between(date(2026, 1, 31), date(2026, 1, 1), N))\n"),
    ("-import_module(py.datetime)\n",
     "p(N) <- (py.datetime.days_between(date(2026, 1, 31), "
     "date(2026, 1, 1), N))\n"),
    ("-import_from(clausal.library.datetime, [days_between])\n",
     "p(N) <- (days_between(date(2026, 1, 31), date(2026, 1, 1), N))\n"),
])
def test_engine_shipped_adapters_keep_a_seam_python_free(proj, imports,
                                                          body):
    """Ruling (1): the engine's own Python adapters are its whitelist.  A
    .seam whose only Python contact is importing one (by py.X, a seam alias
    such as date_time, or its library facade) is case (2)."""
    path = proj.seam("clean", "-module(@clean, [p/1])\n"
                     "-private([date(y, m, d)])\n" + imports + body)
    assert file_python_routes(str(path)) == []
    proj.clausal("main", ":- use_module(@clean, [p/1]).\n",
                 "t(N) :- p(N).\n")
    assert _answers(proj.load("main")) == [30]


def test_a_spliced_package_adapter_needs_a_bridge(proj, spliced_adapter):
    """An optional package's adapter shares the clausal.modules.py
    namespace but is not engine-shipped (decided by path, not name)."""
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_from(py.pbfake, [value])\n"
                               "v(X) <- (X is value)\n")
    assert ("py_adapter", 2) in file_python_routes(str(path))
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg
    proj.allow([f'"{proj.n("helper")}"'])
    assert _answers(proj.load("main")) == [42]


def test_engine_shipped_is_decided_by_path():
    import clausal.modules.py.datetime as engine_adapter
    assert is_engine_shipped("clausal.modules.py.datetime",
                             engine_adapter.__file__)
    assert not is_engine_shipped("clausal.modules.py.pbfake",
                                 "/elsewhere/clausal/modules/py/pbfake.py")


# ── security review (job 333) ───────────────────────────────────────────────


def test_a_spliced_adapter_in_a_data_position_is_a_route(proj,
                                                          spliced_adapter):
    """The reviewer's case: a trusted ``-import_module(py.datetime)`` binds
    ``py``, through which ``py.pbfake.value`` -- a VALUE, no call --
    reaches an adapter an optional package spliced in.  Every dotted chain
    is a reference, not only a callee."""
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_module(py.datetime)\n"
                               "v(X) <- (X is py.pbfake.value)\n")
    assert ("py_adapter", 3) in file_python_routes(str(path))
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg
    assert "clausal.modules.py.pbfake" not in sys.modules
    proj.allow([f'"{proj.n("helper")}"'])
    assert _answers(proj.load("main")) == [42]


@pytest.mark.parametrize("body", [
    "v(X) <- (call(py.pbfake.p, X))\n",
    "v(X) <- (X is [py.pbfake.value])\n",
    "v(X) <- (X is py.pbfake.value.real)\n",
    "v(X) <- (findall(Y, py.pbfake.p(Y), X))\n",
])
def test_every_dotted_chain_is_a_reference(proj, spliced_adapter, body):
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_module(py.datetime)\n" + body)
    assert ("py_adapter", 3) in file_python_routes(str(path))


def test_an_unresolvable_py_reference_fails_closed(proj):
    """``py.X`` that the engine's adapters do not resolve could fall through
    to some other ``py`` package at run time: it is a route."""
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_module(py.datetime)\n"
                               "v(X) <- (X is py.pbnosuch.value)\n")
    assert ("non_export", 3) in file_python_routes(str(path))
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_from(py.pbnosuch, [value])\n"
                               "v(1),\n")
    assert ("python_module", 2) in file_python_routes(str(path))


class _FakeDist:
    def __init__(self, base, files):
        self.base = base
        self.files = files

    def locate_file(self, f):
        return os.path.join(self.base, f)


@pytest.fixture
def engine_rule(monkeypatch):
    from clausal import python_bridges as pb
    monkeypatch.setattr(pb, "_ENGINE_RULE", None)
    yield pb
    pb._ENGINE_RULE = None


def test_an_installed_engine_is_decided_by_its_record(engine_rule,
                                                      monkeypatch, tmp_path):
    """Non-editable install: the optional distributions share the
    site-packages/clausal tree, so only the engine's RECORD decides."""
    import clausal
    pb = engine_rule
    site = tmp_path / "lib" / "site-packages"
    root = site / "clausal"
    (root / "library").mkdir(parents=True)
    (root / "__init__.py").write_text("")
    monkeypatch.setattr(clausal, "__file__", str(root / "__init__.py"))
    record = ["clausal/__init__.py", "clausal/library/py_os.seam"]
    monkeypatch.setattr(pb, "_engine_distribution",
                        lambda: _FakeDist(str(site), record))
    assert pb._engine_rule()[0] == "record"
    assert is_engine_shipped("clausal.library.py_os",
                             str(root / "library" / "py_os.seam"))
    # In the same tree, but not in the engine's RECORD: another
    # distribution's file.
    assert not is_engine_shipped("clausal.library.datetime",
                                 str(root / "library" / "datetime.seam"))


def test_an_egg_info_in_a_source_checkout_does_not_decide(engine_rule,
                                                          monkeypatch):
    """REGRESSION (2026-10-05): a stale ``clausal.egg-info`` in the source
    checkout (an editable install or a build leaves one) is found by
    importlib.metadata BESIDE the package, and its file list predates newer
    files -- the engine's own facades (``library/countries/*``) were
    refused.  Outside site-packages the directory decides."""
    import clausal
    pb = engine_rule
    root = os.path.dirname(os.path.realpath(clausal.__file__))
    if {"site-packages", "dist-packages"} & set(root.split(os.sep)):
        pytest.skip("the engine itself is installed here")
    site = os.path.dirname(root)
    stale = ["clausal/__init__.py"]           # lists the __init__ only
    monkeypatch.setattr(pb, "_engine_distribution",
                        lambda: _FakeDist(site, stale))
    assert pb._engine_rule() == ("dir", root)
    facade = os.path.join(root, "library", "countries", "european_union.seam")
    assert os.path.exists(facade)
    assert is_engine_shipped("clausal.library.countries.european_union",
                             facade)


def test_an_editable_checkout_uses_the_directory(engine_rule, monkeypatch):
    import clausal
    pb = engine_rule
    monkeypatch.setattr(pb, "_engine_distribution",
                        lambda: _FakeDist("/nowhere", ["clausal/_x.pth"]))
    root = os.path.dirname(os.path.realpath(clausal.__file__))
    if {"site-packages", "dist-packages"} & set(root.split(os.sep)):
        pytest.skip("the engine itself is installed here")
    assert pb._engine_rule() == ("dir", root)
    assert is_engine_shipped("clausal.library.datetime",
                             os.path.join(root, "library", "datetime.seam"))


def test_an_undecidable_engine_fails_closed(engine_rule, monkeypatch,
                                            tmp_path):
    """No RECORD lists the imported __init__, and the package sits in a
    site-packages tree: nothing counts as engine-shipped."""
    import clausal
    pb = engine_rule
    fake = tmp_path / "lib" / "site-packages" / "clausal"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text("")
    monkeypatch.setattr(clausal, "__file__", str(fake / "__init__.py"))
    monkeypatch.setattr(pb, "_engine_distribution", lambda: None)
    assert pb._engine_rule() == ("none", None)
    assert not is_engine_shipped("clausal.library.x",
                                 str(fake / "library" / "x.seam"))


# ── security review (job 334) ───────────────────────────────────────────────


@pytest.mark.parametrize("imports, value", [
    ("-import_module(py.csv)\n", "py.csv.io.open('/etc/hostname')"),
    ("-import_module(py.files)\n", "py.files.pathlib.Path.cwd()"),
    ("-import_module(units)\n", "units.os.getcwd()"),
])
def test_a_chain_into_a_module_s_namespace_is_a_route(proj, imports, value):
    """A trusted engine adapter's NAMESPACE is not trusted: ``py.csv.io``
    is the stdlib ``io`` the adapter imported, and walking on from it is
    arbitrary Python.  A qualified name is ``module.name``, never deeper."""
    path = proj.seam("helper", "-module(@helper, [v/1])\n" + imports
                     + f"v(X) <- (X is {value})\n")
    assert ("non_export", 3) in file_python_routes(str(path))
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg


def test_a_module_dot_name_is_still_fine(proj):
    path = proj.seam("clean", "-module(@clean, [p/1])\n"
                              "-private([date(y, m, d)])\n"
                              "-import_module(py.datetime)\n"
                              "p(N) <- (py.datetime.days_between("
                              "date(2026, 1, 31), date(2026, 1, 1), N))\n")
    assert file_python_routes(str(path)) == []


@pytest.mark.parametrize("where, entry", [
    ("elsewhere", "clausal/library/datetime.seam"),   # dist-info not beside
    ("beside", "ABS"),                                 # absolute entry
    ("beside", "../{site}/clausal/library/datetime.seam"),  # a .. entry
])
def test_a_planted_record_cannot_vouch_for_files(engine_rule, monkeypatch,
                                                 tmp_path, where, entry):
    import clausal
    pb = engine_rule
    root = os.path.dirname(os.path.realpath(clausal.__file__))
    site = os.path.dirname(root)
    target = os.path.join(root, "library", "datetime.seam")
    if entry == "ABS":
        entry = target
    entry = entry.format(site=os.path.basename(site))
    base = str(tmp_path) if where == "elsewhere" else site
    record = ["clausal/__init__.py", entry]
    if where == "elsewhere":
        # A dist-info planted elsewhere on sys.path, whose RECORD points
        # (by relative paths) at the real engine __init__ and at the file
        # it wants trusted.
        record = [os.path.relpath(os.path.realpath(clausal.__file__), base),
                  os.path.relpath(target, base)]
    monkeypatch.setattr(pb, "_engine_distribution",
                        lambda: _FakeDist(base, record))
    assert not (pb._engine_rule()[0] == "record"
                and is_engine_shipped("clausal.library.datetime", target))


# ── allow-list: every external name is a declared export (job 335) ──────────


@pytest.mark.parametrize("imports, value", [
    ("-import_from(py.files, [alias(pathlib, zz)])\n", "zz.Path.cwd()"),
    ("-import_from(py.csv, [alias(io, yy)])\n", "yy.open('/etc/hostname')"),
])
def test_an_aliased_import_of_a_non_export_is_a_route(proj, imports, value):
    """The reviewer's exploits: an adapter's own imports (pathlib, io) are
    no exports, aliased or not."""
    path = proj.seam("helper", "-module(@helper, [v/1])\n" + imports
                     + f"v(X) <- (X is {value})\n")
    routes = file_python_routes(str(path))
    assert ("non_export", 2) in routes, routes
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("helper")) in msg, msg


def test_an_attribute_of_an_imported_export_is_a_route(proj):
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_from(py.datetime, [days_between])\n"
                               "v(X) <- (X is days_between.__class__)\n")
    # Since bd0a6ed6 an underscore-led attribute is a compile error.
    assert ("uncompilable", 0) in file_python_routes(str(path))


def test_a_name_a_clausal_module_does_not_export_is_a_route(proj):
    proj.seam("lib", "-module(@lib, [p/1])\np(1),\nq(2),\n")
    path = proj.seam("user", "-module(@user, [v/1])\n"
                             "-import_from(@lib, [q])\nv(X) <- (q(X))\n")
    assert ("non_export", 2) in file_python_routes(str(path))
    path = proj.seam("user", "-module(@user, [v/1])\n"
                             "-import_from(@lib, [p])\nv(X) <- (p(X))\n")
    assert file_python_routes(str(path)) == []


def test_a_dotted_chain_must_name_an_export(proj):
    proj.seam("lib", "-module(@lib, [p/1])\np(1),\nq(2),\n")
    path = proj.seam("user", "-module(@user, [v/1])\n"
                             "-import_module(@lib)\nv(X) <- (@lib.q(X))\n")
    assert ("non_export", 3) in file_python_routes(str(path))
    path = proj.seam("user", "-module(@user, [v/1])\n"
                             "-import_module(@lib)\nv(X) <- (@lib.p(X))\n")
    assert file_python_routes(str(path)) == []


def _engine_adapter_modules():
    """Every engine Python module a .seam can import: clausal/modules/*.py
    and clausal/modules/py/*.py (the engine's own, by file)."""
    import clausal.modules as mods
    root = os.path.dirname(mods.__file__)
    out = []
    for sub, pkg in (("", "clausal.modules"), ("py", "clausal.modules.py")):
        d = os.path.join(root, sub)
        for f in sorted(os.listdir(d)):
            if f.endswith(".py") and not f.startswith("_"):
                out.append(f"{pkg}.{f[:-3]}")
    return out



@pytest.mark.parametrize("dunder", ["__dict__", "__spec__", "__loader__",
                                    "__builtins__"])
def test_an_export_list_cannot_vouch_for_a_module_attribute(proj, dunder):
    """job 336: a Clausal module's export list is its author's text; a
    dunder in it names the module object's own Python attribute, which no
    declaration binds, so it is no export -- by import or by chain."""
    proj.seam("lib", f"-module(@lib, [p/1, {dunder}])\np(1),\n")
    for text, line in (
            (f"-import_module(@lib)\nv(X) <- (X is @lib.{dunder})\n", 3),
            (f"-import_from(@lib, [alias({dunder}, d)])\n"
             f"v(X) <- (X is d)\n", 2)):
        path = proj.seam("user", "-module(@user, [v/1])\n" + text)
        routes = file_python_routes(str(path))
        assert (("non_export", line) in routes
                or ("uncompilable", 0) in routes), routes
    proj.clausal("main", ":- use_module(@user, [v/1]).\n",
                 "t(X) :- v(X).\n")
    msg = _refused(proj, "main")
    assert REFUSAL.format(m=proj.n("user")) in msg, msg


# ── the compiler record decides (job 337) ───────────────────────────────────


def test_a_titlecase_export_head_is_a_qualified_base(proj):
    """job 337: an imported TitleCase name is no logic variable to the
    compiler, so ``SI_Area.x`` is a real attribute chain on the imported
    value.  The reviewer's exploit dies at COMPILE time (an underscore-led
    attribute is no qualified name), and any other attribute of an imported
    value is a route in the compiler's record."""
    exploit = ("-module(@helper, [v/1])\n-import_from(py.units, [SI_Area])\n"
               "v(X) <- (X is SI_Area.__class__.__init__.__globals__)\n")
    path = proj.seam("helper", exploit)
    assert ("uncompilable", 0) in file_python_routes(str(path))
    with pytest.raises(SyntaxError, match="underscore-led attribute"):
        proj.load("helper")
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    assert REFUSAL.format(m=proj.n("helper")) in _refused(proj, "main")
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_from(py.units, [SI_Area])\n"
                               "v(X) <- (X is SI_Area.dimension)\n")
    assert ("non_export", 3) in file_python_routes(str(path))
    # Since the units rename, SI_Area is the deprecated spelling of si_area
    # (imported as si_area under the local name SI_Area).
    assert ("attr", "SI_Area", "py.units.si_area", ("dimension",), 3) in (
        __import__("clausal.python_bridges").python_bridges
        .compiler_record(str(path)))


@pytest.mark.parametrize("value, kind", [
    ("db.__globals__", "uncompilable"),
    ("db.__call__", "uncompilable"),
    ("db.dispatch", "non_export"),
])
def test_an_aliased_export_cannot_be_walked(proj, value, kind):
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_from(date_time, "
                               "[alias(days_between, db)])\n"
                               f"v(X) <- (X is {value})\n")
    routes = file_python_routes(str(path))
    assert any(k == kind for k, _ln in routes), routes
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    assert REFUSAL.format(m=proj.n("helper")) in _refused(proj, "main")


def test_an_underscore_led_qualified_name_is_a_compile_error(tmp_path):
    from clausal.python_bridges import compiler_record
    # (``__builtins__.open`` is dict sugar on a VARIABLE -- a subscript,
    # no attribute walk -- in the compiler and in the pre-scan alike.)
    for value in ("units.__dict__", "units._x", "Undefined.__class__"):
        f = tmp_path / "u.seam"
        f.write_text(f"-module(u, [v/1])\nv(X) <- (X is {value})\n")
        assert compiler_record(str(f)) is None, value


def _routes_per_line(tmp_path, header, lines):
    """Write *header* + one line per entry of *lines*; -> (routes,
    uncompilable)."""
    f = tmp_path / "prop.seam"
    f.write_text("-module(prop, [p/1])\n" + header + "".join(lines))
    routes = file_python_routes(str(f))
    return routes, ("uncompilable", 0) in routes


def test_no_non_export_attribute_of_any_engine_adapter_is_reachable(
        tmp_path):
    """PROPERTY: for EVERY engine adapter module, every public module-level
    attribute that is no declared export is a route by EVERY spelling that
    reaches it: the module path (as a value and as a call), a plain import,
    a lowercase alias, a TitleCase alias, an attribute of a TitleCase or
    lowercase EXPORT (which the compiler reads as a qualified base, not a
    dict-sugar variable), and the exempt injected name ``Undefined``.  The
    whole class, not instances.  Where a whole file does not compile (a
    TitleCase alias is a load-time lint error), each attribute is retried
    alone and must be refused alone."""
    import keyword
    from clausal.python_bridges import _exports, _find
    from clausal.templating.term_rewriting import _is_logic_var_name
    covered = spellings = 0
    for dotted in _engine_adapter_modules():
        try:
            mod = importlib.import_module(dotted)
        except Exception:  # noqa: BLE001 -- an optional dependency
            continue
        exports = sorted(_exports(dotted, _find(dotted)))
        attrs = [n for n in sorted(vars(mod))
                 if not (n.startswith("_") or n in exports
                         or keyword.iskeyword(n) or not n.isidentifier()
                         or _is_logic_var_name(n))]
        if not attrs:
            continue
        covered += len(attrs)
        heads = [e for e in exports if e[:1].isupper()][:1] + [
            e for e in exports if e[:1].islower()][:1]
        variants = [
            ("", lambda i, a: f"-import_from({dotted}, [{a}])\n"),
            ("", lambda i, a: f"-import_from({dotted}, [alias({a}, zz{i})])\n"),
            ("", lambda i, a: f"-import_from({dotted}, [alias({a}, Zz{i})])\n"),
            (f"-import_module({dotted})\n",
             lambda i, a: f"p(X) <- (X is {dotted}.{a})\n"),
            (f"-import_module({dotted})\n",
             lambda i, a: f"p(X) <- ({dotted}.{a}(X))\n"),
            ("", lambda i, a: f"p(X) <- (X is Undefined.{a})\n"),
        ] + [(f"-import_from({dotted}, [{h}])\n",
              lambda i, a, h=h: f"p(X) <- (X is {h}.{a})\n") for h in heads]
        for header, line_of in variants:
            first = 2 + header.count("\n")
            lines = [line_of(i, a) for i, a in enumerate(attrs)]
            routes, broken = _routes_per_line(tmp_path, header, lines)
            if broken:
                for i, a in enumerate(attrs):
                    r, _b = _routes_per_line(tmp_path, header,
                                             [line_of(i, a)])
                    assert r, (dotted, a, header, line_of(i, a))
            else:
                hit = {ln for _k, ln in routes}
                for i, a in enumerate(attrs):
                    assert first + i in hit, (dotted, a, line_of(i, a),
                                              routes)
            spellings += len(attrs)
    print(f"covered {covered} non-export attributes, {spellings} spellings")
    assert covered > 100


def test_the_compiler_record_and_the_scanner_agree_on_every_fixture():
    """DIFFERENTIAL: for every .seam file in the repository that the
    compiler finds Python-free, the static pre-scan and the compiler record
    name the same external references (imports, -import_module, qualified
    chains).  The gate decides from the record; a divergence here means
    the pre-scan has stopped describing what the compiler does."""
    import subprocess
    from clausal import python_bridges as pb
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = subprocess.run(
        ["git", "-c", "safe.directory=*", "ls-files", "*.seam"],
        capture_output=True, text=True, cwd=root).stdout.split()
    if not files:
        pytest.skip("not a git checkout")

    def norm(refs):
        out = set()
        for r in refs:
            if r[0] == "import_from":
                out.add(("from", r[1], r[2]))
            elif r[0] == "import_module":
                out.add(("module", r[1]))
            elif r[0] == "attr":
                out.add(("attr", r[1], *r[3]))
        return out

    compared, diverged = 0, []
    for rel in files:
        path = os.path.join(root, rel)
        record = pb.compiler_record(path)
        if record is None or any(r[0] == "python" for r in record):
            continue
        compared += 1
        static = norm(pb._static_refs(pb._scan(path).refs))
        if static != norm(record):
            diverged.append((rel, sorted(static - norm(record))[:3],
                             sorted(norm(record) - static)[:3]))
    assert compared > 100
    assert not diverged, diverged



# ── every thunk is in the record (job 338) ──────────────────────────────────


@pytest.mark.parametrize("body", [
    "v(X) <- (X is (exec(\"open('{marker}', 'w')\"))(metre))\n",
    "v(X) <- (X is [exec(\"open('{marker}', 'w')\")](metre))\n",
    "v(X) <- (X is (len([1]) + 1)(metre))\n",
])
def test_unit_sugar_over_python_is_a_route(proj, tmp_path, body):
    """job 338: ``<expr>(Unit)`` lowers *expr* as raw Python inside a
    thunk.  Every thunk the lowering builds is in the compiler's record, so
    a magnitude that calls anything is a ``python_thunk`` route."""
    marker = tmp_path / "pwned"
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_from(units, [metre])\n"
                               + body.format(marker=marker))
    from clausal.python_bridges import compiler_record
    assert ("python", "python_thunk", 3) in compiler_record(str(path))
    assert ("python_thunk", 3) in file_python_routes(str(path))
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    assert REFUSAL.format(m=proj.n("helper")) in _refused(proj, "main")
    assert not marker.exists()


def test_inert_unit_sugar_stays_python_free(proj):
    path = proj.seam("clean", "-module(@clean, [v/1])\n"
                              "-import_from(units, [metre, second])\n"
                              "v(X) <- (X is 5(metre))\n"
                              "v(X) <- (X is (2 + 3)(metre / second ** 2))\n"
                              "v(X) <- (has_units(X, metre / second))\n")
    assert file_python_routes(str(path)) == []


@pytest.mark.parametrize("text", [
    "v(X) <- (has_units(X, Undefined.__class__.__init__ * metre))\n",
    "-constant_number_units(c, 5, Undefined.__class__.__init__.__globals__)\n"
    "v(c),\n",
    "v(X) <- (X is 5(Undefined.__class__))\n",
])
def test_an_underscore_led_unit_expression_is_refused(proj, text):
    path = proj.seam("helper", "-module(@helper, [v/1])\n"
                               "-import_from(units, [metre])\n" + text)
    routes = file_python_routes(str(path))
    assert routes, routes
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    assert REFUSAL.format(m=proj.n("helper")) in _refused(proj, "main")


def test_constant_number_units_goal_is_python_free(proj):
    """The engine's own thunk (the owner's module read) is no route."""
    proj.seam("lib", "-module(@lib, [fee])\n"
                     "-constant_number_units(fee, 5, euro)\n")
    path = proj.seam("user", "-module(@user, [v/1])\n"
                             "-import_from(@lib, [fee])\n"
                             "v(N) <- (constant_number_units(fee, N, _))\n")
    from clausal.python_bridges import compiler_record
    assert not any(r[0] == "python" for r in compiler_record(str(path)))


# ── THE DECIDER: the audit of the final generated Python ────────────────────


#: Every exploit the security reviews found (rounds 1-5), as a .seam module
#: that a .clausal importer must not reach -- plus the original gap.
EXPLOITS = {
    "original_gap": "import os\n-module(@helper, [v/1])\n"
                    "v(D) <- (D is ++os.getcwd())\n",
    "r2_data_position": "-module(@helper, [v/1])\n"
                        "-import_module(py.datetime)\n"
                        "v(X) <- (X is py.pbfake.value)\n",
    "r2_unresolved_py": "-module(@helper, [v/1])\n"
                        "-import_from(py.pbnosuch, [value])\nv(1),\n",
    "r3_py_csv_io": "-module(@helper, [v/1])\n-import_module(py.csv)\n"
                    "v(X) <- (X is py.csv.io.open('/etc/hostname'))\n",
    "r3_py_files_pathlib": "-module(@helper, [v/1])\n"
                           "-import_module(py.files)\n"
                           "v(X) <- (X is py.files.pathlib.Path.cwd())\n",
    "r3_units_os": "-module(@helper, [v/1])\n-import_module(units)\n"
                   "v(X) <- (X is units.os.getcwd())\n",
    "r4_alias_pathlib": "-module(@helper, [v/1])\n"
                        "-import_from(py.files, [alias(pathlib, zz)])\n"
                        "v(X) <- (X is zz.Path.cwd())\n",
    "r4_alias_io": "-module(@helper, [v/1])\n"
                   "-import_from(py.csv, [alias(io, yy)])\n"
                   "v(X) <- (X is yy.open('/etc/hostname'))\n",
    "r5_titlecase_head": "-module(@helper, [v/1])\n"
                         "-import_from(py.units, [SI_Area])\n"
                         "v(X) <- (X is SI_Area.dimension)\n",
    "r5_titlecase_dunder": "-module(@helper, [v/1])\n"
                           "-import_from(py.units, [SI_Area])\n"
                           "v(X) <- (X is SI_Area.__class__.__init__)\n",
    "r5_alias_globals": "-module(@helper, [v/1])\n"
                        "-import_from(date_time, [alias(days_between, db)])\n"
                        "v(X) <- (X is db.__globals__)\n",
    "r5_alias_attr": "-module(@helper, [v/1])\n"
                     "-import_from(date_time, [alias(days_between, db)])\n"
                     "v(X) <- (X is db.dispatch)\n",
    "r6_unit_exec": "-module(@helper, [v/1])\n-import_from(units, [metre])\n"
                    "v(X) <- (X is (exec(\"print(1)\"))(metre))\n",
    "r6_unit_list_exec": "-module(@helper, [v/1])\n"
                         "-import_from(units, [metre])\n"
                         "v(X) <- (X is [exec(\"print(1)\")](metre))\n",
    "r6_has_units_dunder": "-module(@helper, [v/1])\n"
                           "-import_from(units, [metre])\n"
                           "v(X) <- (has_units(X, Undefined.__class__ * "
                           "metre))\n",
    "r6_constant_units_dunder": "-module(@helper, [v/1])\n"
                                "-constant_number_units(c, 5, "
                                "Undefined.__class__.__init__)\nv(c),\n",
    "hosted_call": "-module(@helper, [v/1])\nprint('x')\nv(1),\n",
    "hosted_def": "-module(@helper, [v/1])\ndef f():\n    return 1\nv(1),\n",
    "hosted_class": "-module(@helper, [v/1])\nclass C:\n    pass\nv(1),\n",
    "python_module": "-module(@helper, [v/1])\n-import_from(os, [getcwd])\n"
                     "v(1),\n",
    "escape_call": "-module(@helper, [v/1])\n"
                   "v(X) <- (X is ++len([1, 2]))\n",
    "fstring_call": "-module(@helper, [v/1])\n"
                    "v(X) <- (X is f\"{len([1, 2])}\")\n",
    # review 340: a bare -import_module binding is the module OBJECT
    "r7_bare_module_value": "-module(@helper, [v/1])\n"
                            "-import_module(units)\nv(D) <- (D is units)\n",
    "r7_bare_py_value": "-module(@helper, [v/1])\n"
                        "-import_module(py.datetime)\nv(D) <- (D is py)\n",
    # review 339: author-written statements shaped like the plumbing
    "r8_signatures_key": "-module(@helper, [v/1])\n"
                         "globals().setdefault('__builtins__', {})"
                         ".update({'v': ('x',)})\nv(1),\n",
    "r8_signatures_dict_get": "-module(@helper, [v/1])\n"
                              "-import_from(units, [metre])\n"
                              "globals().setdefault("
                              "'__clausal_functor_signatures__', {}).update("
                              "{_cs_local: __import__('clausal.modules.units',"
                              " fromlist=['_']).__dict__.get('__builtins__',"
                              " {})[_cs_orig] for _cs_local, _cs_orig in "
                              "{'metre': 'metre'}.items() if _cs_orig in "
                              "__import__('clausal.modules.units', fromlist="
                              "['_']).__dict__.get('__builtins__', {})})\n"
                              "v(1),\n",
    "r8_translations_import": "-module(@helper, [v/1])\n"
                              "from clausal.logic.translations import "
                              "register_predicate as _reg_pred, "
                              "register_atom as _reg_atom\n"
                              "_reg_atom('th', 'v', 'x')\nv(1),\n",
    "r8_hosted_walrus": "-module(@helper, [v/1])\n(name := 1)\nv(1),\n",
    # job 341: the translations names re-bound to an adapter export
    "r9_reg_atom_rebound": "-module(@helper, [v/1, ok])\n"
                           "-translations(th, {v: ok})\n"
                           "from clausal.modules.units import metre as "
                           "_reg_atom\ny = _reg_atom(1)\nv(1),\n",
    "r9_extra_registration": "-module(@helper, [v/1, ok])\n"
                             "-translations(th, {v: ok})\n"
                             "y = _reg_atom('th', 'other', 'x')\n"
                             "v(1),\n",
    # task 342: a bare clause-data name the module does not bind
    "r9_bare_open": "-module(@helper, [v/1])\nv(X) <- (X is open)\n",
    "r9_bare_getattr_goal": "-module(@helper, [v/1])\n"
                            "v(X) <- (getattr(X, a, 1))\n",
    "r9_bare_eval_goal": "-module(@helper, [v/1])\nv(X) <- (eval(X))\n",
    "r9_bare_globals": "-module(@helper, [v/1])\nv(X) <- (X is globals)\n",
    "r9_reserved_var_name": "-module(@helper, [v/1])\n"
                            "v(X) <- (X is PyThunk)\n",
}


@pytest.mark.parametrize("name", sorted(EXPLOITS))
def test_every_exploit_is_refused_by_the_audit_alone(proj, name,
                                                     spliced_adapter,
                                                     monkeypatch):
    """(a) With the record and the pre-scan switched off, the audit of the
    final generated Python refuses every exploit of every review round."""
    from clausal import python_bridges as pb
    monkeypatch.setattr(pb, "_DIAGNOSTICS", False)
    lib = ("-module(@lib, [p/1, __dict__])\np(1),\n")
    proj.seam("lib", lib)
    path = proj.seam("helper", EXPLOITS[name])
    routes = file_python_routes(str(path))
    assert routes, (name, routes)
    proj.clausal("main", ":- use_module(@helper, [v/1]).\n",
                 "t(X) :- v(X).\n")
    assert REFUSAL.format(m=proj.n("helper")) in _refused(proj, "main")


def test_the_audit_and_the_record_gate_agree_on_every_fixture():
    """(b) Over every .seam in the repository that the compiler record
    finds Python-free, the audit ALLOWS exactly what the record-based gate
    allows -- except the files listed here, each a real route the audit
    finds and the record did not."""
    import subprocess
    from clausal import python_bridges as pb
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = subprocess.run(
        ["git", "-c", "safe.directory=*", "ls-files", "*.seam"],
        capture_output=True, text=True, cwd=root).stdout.split()
    if not files:
        pytest.skip("not a git checkout")
    real_routes = {
        # ``5.0(Metre)``: a name the module never binds, read inside a
        # thunk -- Python resolves it through builtins.
        "tests/fixtures/titlecase_unit_spelling_witness.seam",
        # Bare clause names nothing binds (the allow-list for bare names):
        # each fixture exists to show that name failing when it runs --
        # ``point/2`` never declared, an unknown functor without
        # -implicit_functors, ``citation`` called unqualified.
        "tests/clausal_modules/undeclared_compound_head.seam",
        "tests/fixtures/implicit_functors_unknown_plain.seam",
        "tests/fixtures/prednf_impmod_use.seam",
    }
    compared = allowed = 0
    disagree = []
    for rel in files:
        path = os.path.join(root, rel)
        record = pb.compiler_record(path)
        if record is None or any(r[0] == "python" for r in record):
            continue
        compared += 1
        audit = bool(pb.audit_routes(path)[0])
        old = bool(pb._check_refs(record)[0])
        allowed += not audit
        if audit != old and rel not in real_routes:
            disagree.append((rel, audit, old))
    print(f"compared {compared}, audit allows {allowed}")
    assert compared > 500
    assert not disagree, disagree


def _clean_generated_tree():
    """A generated tree exercising every allowed node kind."""
    import ast as _ast
    from clausal.seam_audit import generated_tree
    src = (
        "-module(m, [p/1, q/2, k, atomx])\n"
        "-private([a, b])\n"
        "-dynamic(r/1)\n"
        "-import_from(units, [metre])\n"
        "-import_module(py.datetime)\n"
        "-constant_value(k, [1, 2])\n"
        "p(1),\n"
        "q(X, Y) <- (p(X), Y is (2 + 3)(metre), Z is X + 1, "
        "S is f\"{X}\", py.datetime.days_between(a, b, Y), Z > 0)\n")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = generated_tree(src, "m.seam")
    return tree


def _audit(tree):
    from clausal import python_bridges as pb
    from clausal.seam_audit import audit_tree
    routes, children = [], []
    found, _ = audit_tree(tree, pb.audit_checker(routes, children))
    return routes + found


def _mutate(tree, match, replace):
    """A copy of *tree* with the FIRST node *match* accepts replaced by
    *replace(node)*; asserts one was found."""
    import ast as _ast
    import copy
    tree = copy.deepcopy(tree)
    done = []

    class _M(_ast.NodeTransformer):
        def generic_visit(self, node):
            if not done and match(node):
                done.append(node)
                return replace(node)
            return super().generic_visit(node)

    tree = _M().visit(tree)
    assert done, "no node to mutate"
    _ast.fix_missing_locations(tree)
    return tree


def _call(name, *args):
    import ast as _ast
    return _ast.Call(func=_ast.Name(id=name, ctx=_ast.Load()),
                     args=list(args), keywords=[])


def _is_call(name):
    import ast as _ast
    return lambda n: (isinstance(n, _ast.Call)
                      and isinstance(n.func, _ast.Name) and n.func.id == name)


def _kw(name, value):
    import ast as _ast

    def rep(node):
        for k in node.keywords:
            if k.arg == name:
                k.value = value
        return node
    return rep


def _mutations():
    import ast as _ast
    C = _ast.Constant
    exec_call = lambda *_: _call("exec", C("print(1)"))  # noqa: E731
    return {
        # literal -> a call
        "constant": (lambda n: isinstance(n, _ast.Constant)
                     and n.value == "atomx", exec_call),
        # engine helper -> a helper not in the engine's tables / a builtin
        "helper_unknown": (_is_call("$Var"),
                           lambda n: _call("$no_such_helper")),
        "helper_builtin": (_is_call("$Var"), lambda n: _call("open",
                                                             C("/x"))),
        # a name the module binds -> one it does not
        "own_name": (lambda n: isinstance(n, _ast.Name)
                     and n.id == "metre", lambda n: _ast.Name(
                         id="open", ctx=_ast.Load())),
        # thunk body -> a call
        "lambda_body": (lambda n: isinstance(n, _ast.Lambda),
                        lambda n: _ast.Lambda(args=n.args,
                                              body=exec_call())),
        # walrus value -> a call
        "walrus": (lambda n: isinstance(n, _ast.NamedExpr),
                   lambda n: _ast.NamedExpr(target=n.target,
                                            value=exec_call())),
        # $LoadName -> a dotted Python path / a dunder
        "load_name_dotted": (_is_call("$LoadName"), _kw("name",
                                                        C("os.system"))),
        "load_name_dunder": (_is_call("$LoadName"), _kw("name",
                                                        C("__import__"))),
        # $LoadAttr -> a non-export / an underscore attribute / deeper
        "load_attr_nonexport": (_is_call("$LoadAttr"),
                                _kw("attr", C("os"))),
        "load_attr_dunder": (_is_call("$LoadAttr"),
                             _kw("attr", C("__class__"))),
        # import -> a non-export name / a Python module
        "import_nonexport": (lambda n: isinstance(n, _ast.ImportFrom)
                             and n.module.endswith("units"),
                             lambda n: _ast.ImportFrom(
                                 module=n.module, level=0,
                                 names=[_ast.alias(name="os")])),
        "import_python": (lambda n: isinstance(n, _ast.Import),
                          lambda n: _ast.Import(
                              names=[_ast.alias(name="os")])),
        # plumbing -> another module in its __import__
        "plumbing_module": (lambda n: isinstance(n, _ast.Constant)
                            and n.value == "clausal.pl_data_imports",
                            lambda n: C("os")),
        # $-rooted attribute -> an underscore attribute
        "dollar_attr": (lambda n: isinstance(n, _ast.Attribute)
                        and n.attr == "mark_dynamic",
                        lambda n: _ast.Attribute(value=n.value,
                                                 attr="__class__",
                                                 ctx=_ast.Load())),
        # assignment target -> a dunder
        "assign": (lambda n: isinstance(n, _ast.Assign),
                   lambda n: _ast.Assign(targets=[_ast.Name(
                       id="__builtins__", ctx=_ast.Store())],
                       value=n.value)),
        # f-string slot -> a call
        "fstring_slot": (lambda n: isinstance(n, _ast.FormattedValue),
                         lambda n: _ast.FormattedValue(
                             value=exec_call(), conversion=-1,
                             format_spec=None)),
        # arithmetic operand -> a call
        "binop": (lambda n: isinstance(n, _ast.BinOp),
                  lambda n: _ast.BinOp(left=exec_call(), op=n.op,
                                       right=n.right)),
        # a keyword argument -> a call
        "keyword": (lambda n: isinstance(n, _ast.keyword)
                    and n.arg == "position",
                    lambda n: _ast.keyword(arg="position",
                                           value=exec_call())),
        # an engine data node -> an effect node (an attribute STORE)
        "effect_node": (_is_call("$Var"), lambda n: _call("$StoreAttr")),
        # $module.db.mark_X -> another attribute of the database
        "dollar_attr_other": (lambda n: isinstance(n, _ast.Attribute)
                              and n.attr == "mark_dynamic",
                              lambda n: _ast.Attribute(value=n.value,
                                                       attr="clear",
                                                       ctx=_ast.Load())),
        # a walrus target -> an injected runtime name
        "walrus_reserved": (lambda n: isinstance(n, _ast.NamedExpr),
                            lambda n: _ast.NamedExpr(
                                target=_ast.Name(id="PyThunk",
                                                 ctx=_ast.Store()),
                                value=n.value)),
        # the import guard -> binding names of ANOTHER import
        "guard_names": (lambda n: isinstance(n, _ast.Dict)
                        and n.keys and isinstance(n.keys[0], _ast.Constant)
                        and n.keys[0].value == "metre",
                        lambda n: _ast.Dict(keys=[_ast.Constant("os")],
                                            values=[_ast.Constant("os")])),
        # a statement -> a def
        "statement": (lambda n: isinstance(n, _ast.Pass),
                      lambda n: _ast.parse("def f():\n    pass").body[0]),
    }


def test_the_clean_generated_tree_passes_the_audit():
    assert _audit(_clean_generated_tree()) == []


@pytest.mark.parametrize("kind", sorted(_mutations()))
def test_a_minimally_altered_dangerous_variant_is_refused(kind):
    """(c) MUTATION: for each node kind the audit allows, the smallest
    dangerous change to it is refused."""
    match, replace = _mutations()[kind]
    base = _clean_generated_tree()
    assert _audit(base) == []
    try:
        mutated = _mutate(base, match, replace)
    except AssertionError:
        if kind == "statement":
            import ast as _ast
            mutated = _clean_generated_tree()
            mutated.body.append(_ast.parse("def f():\n    pass").body[0])
        else:
            raise
    assert _audit(mutated), kind


def test_the_engine_name_tables_cover_every_injected_name(proj):
    """The audit's engine names are the compiler's own tables: every ``$``
    name a loaded module's namespace holds is in them."""
    from clausal import import_hook
    proj.seam("clean", CLEAN_LIB)
    mod = proj.load("clean")
    dollar = {n for n in vars(mod) if n.startswith("$")}
    allowed = ({n for n in import_hook.runtime_builtins if n.startswith("$")}
               | import_hook.PER_MODULE_RUNTIME_NAMES)
    assert dollar - allowed == set(), dollar - allowed


def test_a_translations_directive_still_passes_the_audit(tmp_path):
    from clausal.python_bridges import audit_routes
    f = tmp_path / "tr.seam"
    f.write_text("-module(tr, [v/1, ok])\n-translations(th, {v: ok})\n"
                 "v(1),\n")
    assert audit_routes(str(f))[0] == []


def test_clause_code_runs_on_the_engine_builtins_only(proj):
    """task 342 (defensive): a compiled clause's ``__builtins__`` is the
    engine's minimal table, so a bare name the call-target step missed
    raises NameError instead of reaching ``open``/``eval``/``getattr``."""
    from clausal.logic.compiler.predicate import CLAUSE_BUILTINS
    proj.seam("clean", CLEAN_LIB)
    mod = proj.load("clean")
    fn = vars(mod)["$module"].db.get_dispatch("p", 1)
    assert fn.__globals__["__builtins__"] is CLAUSE_BUILTINS
    for name in ("open", "eval", "exec", "getattr",
                 "globals", "compile", "setattr", "vars", "type"):
        assert name not in CLAUSE_BUILTINS, name
    # The engine's C helpers import their Python twins through the calling
    # frame's builtins: only an engine module.
    imp = CLAUSE_BUILTINS["__import__"]
    got = imp("clausal.logic.runtime.list_unify")
    assert not isinstance(got, type(pytest))
    assert vars(got) == {}
    assert not hasattr(got, "__builtins__")
    for bad, kw in (("pb_surely_not_loaded_module", {}),
                    ("list_unify", {"level": 1}),
                    ("builtins", {}), ("os", {}), ("importlib", {}),
                    ("clausal", {}),
                    ("clausal.logic.predicate", {}),
                    ("clausal.logic.predicate", {"fromlist": ["os"]}),
                    ("clausal.logic.runtime.list_unify",
                     {"fromlist": ["_head_list_unify_input_py"]}),
                    ("clausal", {"fromlist": ["pb_no_such_submodule"]})):
        with pytest.raises(ImportError):
            imp(bad, None, None, kw.get("fromlist", ()), kw.get("level", 0))
    code = compile("open('/etc/hostname')", "<t>", "eval")
    with pytest.raises(NameError):
        eval(code, dict(fn.__globals__))


#: Item 4: each lowering path not yet reviewed, with an attempt to reach
#: non-allowlisted Python through it.
PATH_EXPLOITS = {
    "comprehension_iter": "v(M) <- (M is [x for x in open('/etc/hostname')])",
    "comprehension_elt": "v(M) <- (M is [getattr(x, 'a') for x in [1]])",
    "comprehension_if": "v(M) <- (M is [x for x in [1] if eval('1')])",
    "comprehension_module": "v(M) <- (M is [units.os for x in [1]])",
    "fstring_call": "v(S) <- (S is f\"{len([1])}\")",
    "fstring_attr": "v(S) <- (S is f\"{S.__class__}\")",
    "fstring_spec": "v(S) <- (S is f\"{S:{len([1])}}\")",
    "lambda_goal": "v(F) <- (F is ((X) <- (open(X))))",
    "lambda_module": "v(F) <- (F is ((X) <- (X is units.os)))",
    "lambda_nested": "v(F) <- (F is ((X) <- (call((Y) <- (eval(Y)), X))))",
}


@pytest.mark.parametrize("name", sorted(PATH_EXPLOITS))
def test_unreviewed_lowering_paths_are_refused_by_the_audit_alone(
        tmp_path, name, monkeypatch):
    from clausal import python_bridges as pb
    monkeypatch.setattr(pb, "_DIAGNOSTICS", False)
    f = tmp_path / "e.seam"
    f.write_text("-module(e, [v/1])\n-private([x])\n-import_module(units)\n"
                 + PATH_EXPLOITS[name] + "\n")
    assert file_python_routes(str(f)), name


def test_the_same_paths_used_cleanly_pass(tmp_path):
    from clausal import python_bridges as pb
    f = tmp_path / "e.seam"
    f.write_text("-module(e, [v/1, w/1, u/1])\n-private([x])\n"
                 "v(M) <- (M is [x * x for x in [1, 2]])\n"
                 "w(S) <- (S is f\"{S!r:>8}\")\n"
                 "u(F) <- (F is ((X) <- (X > 1)))\n")
    assert pb.audit_routes(str(f))[0] == []


def test_mark_directives_carry_only_constants():
    """``$module.db.mark_<x>(...)`` is accepted only with data arguments:
    a directive names predicates, it cannot carry a call."""
    import ast as _ast
    from clausal.seam_audit import generated_tree
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = generated_tree("-module(m, [p/1])\n-dynamic(getattr/2)\n"
                              "-table(p/1)\np(1),\n", "m.seam")
    assert _audit(tree) == []
    for attr in ("mark_dynamic", "mark_tabled"):
        bad = _mutate(tree, lambda n, a=attr: isinstance(n, _ast.Call)
                      and isinstance(n.func, _ast.Attribute)
                      and n.func.attr == a,
                      lambda n: _ast.Call(func=n.func, args=[
                          _call("exec", _ast.Constant("print(1)"))],
                          keywords=[]))
        assert _audit(bad), attr
        other = _mutate(tree, lambda n, a=attr: isinstance(n, _ast.Attribute)
                        and n.attr == a,
                        lambda n: _ast.Attribute(
                            value=_ast.Attribute(value=n.value,
                                                 attr="rows",
                                                 ctx=_ast.Load()),
                            attr="clear", ctx=_ast.Load()))
        assert _audit(other), attr
