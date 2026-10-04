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
                 "-import_from(units, [meter])\np(1),\n")
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
    ("-import_from(date_time, [date, days_between])\n",
     "p(N) <- (days_between(date(2026, 1, 31), date(2026, 1, 1), N))\n"),
    ("-import_from(py.datetime, [date, days_between])\n",
     "p(N) <- (days_between(date(2026, 1, 31), date(2026, 1, 1), N))\n"),
    ("-import_module(py.datetime)\n-import_from(date_time, [date])\n",
     "p(N) <- (py.datetime.days_between(date(2026, 1, 31), "
     "date(2026, 1, 1), N))\n"),
    ("-import_from(clausal.library.datetime, [days_between])\n"
     "-import_from(date_time, [date])\n",
     "p(N) <- (days_between(date(2026, 1, 31), date(2026, 1, 1), N))\n"),
])
def test_engine_shipped_adapters_keep_a_seam_python_free(proj, imports,
                                                          body):
    """Ruling (1): the engine's own Python adapters are its whitelist.  A
    .seam whose only Python contact is importing one (by py.X, a seam alias
    such as date_time, or its library facade) is case (2)."""
    path = proj.seam("clean", "-module(@clean, [p/1])\n" + imports + body)
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
    assert file_python_routes(str(path)) == [("py_adapter", 2)]
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
    assert ("python_module", 3) in file_python_routes(str(path))
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
                                                      monkeypatch):
    """Non-editable install: the optional distributions share the
    site-packages/clausal tree, so only the engine's RECORD decides."""
    import clausal
    pb = engine_rule
    root = os.path.dirname(os.path.realpath(clausal.__file__))
    site = os.path.dirname(root)
    record = ["clausal/__init__.py", "clausal/library/py_os.seam"]
    monkeypatch.setattr(pb, "_engine_distribution",
                        lambda: _FakeDist(site, record))
    assert pb._engine_rule()[0] == "record"
    assert is_engine_shipped("clausal.library.py_os",
                             os.path.join(root, "library", "py_os.seam"))
    # In the same tree, but not in the engine's RECORD: another
    # distribution's file.
    assert not is_engine_shipped(
        "clausal.library.datetime",
        os.path.join(root, "library", "datetime.seam"))


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
