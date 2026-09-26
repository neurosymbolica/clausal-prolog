"""Census: where does Python code still use the deprecated ``atom`` CLASS?

``clausal.logic.atoms.atom`` (a ``str`` subclass that tagged a value as an
atom at the Python boundary) is deprecated by the dumb seam, step (f),
2026-09-27, and removed in 2.0: an atom IS the plain ``str``.  This tool
finds, by AST, every

* CONSTRUCTION -- ``atom('x')``, ``A.atom('x')``, ``atoms.atom('x')``, ...
  (each one emits ``ClausalAtomClassDeprecationWarning`` at run time);
* TYPE TEST -- ``isinstance(v, atom)`` (also inside a tuple of classes),
  ``issubclass(t, atom)``, ``type(v) is atom`` / ``is not`` / ``==`` /
  ``!=``, and a ``case atom(...)`` class pattern.  These do NOT warn at run
  time, and every one of them is now simply FALSE for anything the engine
  hands out, so a collector that filtered on it went silently empty -- this
  is the population a run-time warning cannot find;
* OTHER reference -- the class named anywhere else (subclassed, passed as a
  value, ``atom.__new__``, ``atom._interned``).

A name counts only when the IMPORT resolves to the class:
``from clausal.logic.atoms import atom [as A]``, ``import
clausal.logic.atoms [as M]`` then ``M.atom``, ``from clausal.logic import
atoms`` then ``atoms.atom``, a relative import of the same module, or an
import of ``atom`` from an engine module that itself binds the class (found
by scanning the engine tree the same way -- e.g. ``clausal.logic.to_python``).
The BUILTIN ``atom/1`` (``from clausal import atom``) is a different object
and is never counted; neither is a name the file binds to both, which is
reported as AMBIGUOUS instead.  Resolution is per scope (module, function,
class) and flow-insensitive within one.

SAFE TO RUN ON SOMEONE ELSE'S TREE, REPORT-ONLY.  It reads each file and
calls ``ast.parse`` on it -- it never imports, compiles to bytecode or
executes a scanned file, never imports ``clausal``, and writes nothing
except the ``--json`` file you name.  Run it with ``PYTHONDONTWRITEBYTECODE=1``
anyway so not even the tool's own ``.pyc`` lands anywhere::

    PYTHONDONTWRITEBYTECODE=1 python3 tools/atom_class_census/census.py \\
        --self-test
    PYTHONDONTWRITEBYTECODE=1 python3 tools/atom_class_census/census.py \\
        [--engine-root <engine tree>/clausal] [--sites] [--json OUT] ROOT...

It scans ``*.py`` plus ``*.clausal`` / ``*.seam`` (their hosted Python
parses as Python; a file that does not parse is COUNTED and listed, never
dropped).  It prints the SIZE of every population -- files found, parsed,
unparsed, files that import the class, and each count -- so an empty result
can be told from a scan that saw nothing.  ``--self-test`` runs a POSITIVE
control (every form above, with exact expected counts) and a NEGATIVE control
(the builtin ``atom/1``, ``is_atom``, a local ``def atom``, the text
``atom(`` in a string) that must count zero; a run whose controls fail exits
non-zero.  Exit status: 0 on a clean scan, 1 if any file failed to parse, 2
on a failed self-test.

Not seen, by construction: a use through ``getattr(m, "atom")``, a
``from clausal.logic.atoms import *`` (``atom`` is not in ``__all__``, so
that binds nothing), source held in a string (a ``.seam`` body written by a
test), and any re-export chain longer than engine-module -> file.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

ATOMS_MODULE = "clausal.logic.atoms"
CLASS_NAME = "atom"
SUFFIXES = (".py", ".clausal", ".seam")
SKIP_DIRS = {"venv", ".venv", "build", "dist", ".git", "__pycache__",
             "node_modules", "site-packages", ".tox", ".mypy_cache"}

CLASS = "CLASS"          # a name bound to the class itself
MODULE = "MODULE"        # a name bound to clausal.logic.atoms
REEXPORT = "REEXPORT"    # a name bound to an engine module that re-exports the class
OTHER = "OTHER"          # a name bound to anything else in that scope


def _module_of(path: Path) -> str | None:
    """Dotted module name of *path* by walking up through ``__init__.py``
    packages; ``None`` for a file outside any package."""
    parts = [path.stem] if path.stem != "__init__" else []
    d = path.parent
    while (d / "__init__.py").exists():
        parts.insert(0, d.name)
        d = d.parent
    return ".".join(parts) if parts else None


def _resolve_from(node: ast.ImportFrom, this_module: str | None,
                  is_package: bool) -> str | None:
    """Absolute module named by a ``from X import ...`` (relative resolved)."""
    if not node.level:
        return node.module
    if this_module is None:
        return None
    base = this_module.split(".")
    if not is_package:
        base = base[:-1]
    if node.level > 1:
        base = base[: len(base) - (node.level - 1)]
    if node.module:
        base = base + node.module.split(".")
    return ".".join(base) if base else None


class _Scope:
    def __init__(self, parent):
        self.parent = parent
        self.bindings: dict[str, set] = {}

    def bind(self, name, kind):
        self.bindings.setdefault(name, set()).add(kind)

    def lookup(self, name):
        s = self
        while s is not None:
            if name in s.bindings:
                return s.bindings[name]
            s = s.parent
        return set()


class _Binder(ast.NodeVisitor):
    """Pass 1: every scope's name -> {CLASS, MODULE, OTHER} bindings."""

    def __init__(self, this_module, is_package, reexporters):
        self.this_module = this_module
        self.is_package = is_package
        self.reexporters = reexporters     # engine modules binding the class at module level
        self.scopes: dict[int, _Scope] = {}
        self.stack: list[_Scope] = []

    def _enter(self, node):
        sc = _Scope(self.stack[-1] if self.stack else None)
        self.scopes[id(node)] = sc
        self.stack.append(sc)

    def _bind(self, name, kind):
        self.stack[-1].bind(name, kind)

    def visit_Module(self, node):
        self._enter(node)
        self.generic_visit(node)
        self.stack.pop()

    def _visit_scoped(self, node):
        if not isinstance(node, ast.Lambda):
            self._bind(node.name, OTHER)
        for d in getattr(node, "decorator_list", []):
            self.visit(d)
        if isinstance(node, ast.ClassDef):
            for b in node.bases + [k.value for k in node.keywords]:
                self.visit(b)
            self._enter(node)
            for s in node.body:
                self.visit(s)
            self.stack.pop()
            return
        a = node.args
        for dflt in a.defaults + [x for x in a.kw_defaults if x is not None]:
            self.visit(dflt)
        self._enter(node)
        for arg in a.posonlyargs + a.args + a.kwonlyargs + \
                [x for x in (a.vararg, a.kwarg) if x is not None]:
            self._bind(arg.arg, OTHER)
        body = node.body if isinstance(node.body, list) else [node.body]
        for s in body:
            self.visit(s)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _visit_scoped

    def visit_Lambda(self, node):
        a = node.args
        for dflt in a.defaults + [x for x in a.kw_defaults if x is not None]:
            self.visit(dflt)
        self._enter(node)
        for arg in a.posonlyargs + a.args + a.kwonlyargs + \
                [x for x in (a.vararg, a.kwarg) if x is not None]:
            self._bind(arg.arg, OTHER)
        self.visit(node.body)
        self.stack.pop()

    def visit_Import(self, node):
        for al in node.names:
            if al.asname:
                kind = (MODULE if al.name == ATOMS_MODULE else
                        REEXPORT if al.name in self.reexporters else OTHER)
                self._bind(al.asname, kind)
            else:
                # `import clausal.logic.atoms` binds `clausal`; the
                # attribute chain is resolved at the use (see _Counter).
                self._bind(al.name.split(".")[0], "PKG:" + al.name)

    def visit_ImportFrom(self, node):
        mod = _resolve_from(node, self.this_module, self.is_package)
        for al in node.names:
            if al.name == "*":
                continue
            local = al.asname or al.name
            full = f"{mod}.{al.name}" if mod else None
            if al.name == CLASS_NAME and mod in ({ATOMS_MODULE} | self.reexporters):
                kind = CLASS
            elif full == ATOMS_MODULE:
                kind = MODULE
            elif full in self.reexporters:
                kind = REEXPORT
            else:
                kind = OTHER
            self._bind(local, kind)

    def _store(self, target):
        for n in ast.walk(target):
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                self._bind(n.id, OTHER)

    def visit_Assign(self, node):
        self.visit(node.value)
        for t in node.targets:
            self._store(t)
            self.visit(t)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.visit(node.value)
        self._store(node.target)

    def visit_AugAssign(self, node):
        self.visit(node.value)

    def visit_NamedExpr(self, node):
        self.visit(node.value)
        self._store(node.target)

    def visit_For(self, node):
        self._store(node.target)
        self.generic_visit(node)

    visit_AsyncFor = visit_For

    def visit_With(self, node):
        for it in node.items:
            if it.optional_vars is not None:
                self._store(it.optional_vars)
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node):
        if node.name:
            self._bind(node.name, OTHER)
        self.generic_visit(node)

    def visit_Global(self, node):
        pass


def _kinds(scope: _Scope, name: str) -> set:
    return scope.lookup(name)


class _Counter(ast.NodeVisitor):
    """Pass 2: classify every reference that resolves to the class."""

    def __init__(self, scopes, reexporters):
        self.scopes = scopes
        self.reexporters = reexporters
        self.stack: list[_Scope] = []
        self.sites: list[dict] = []
        self.consumed: set[int] = set()   # ids of reference nodes already classified

    # -- scope tracking (the same nodes the binder opened) ------------------
    def _scoped(self, node):
        sc = self.scopes.get(id(node))
        if sc is None:
            return self.generic_visit(node)
        self.stack.append(sc)
        self.generic_visit(node)
        self.stack.pop()

    visit_Module = visit_FunctionDef = visit_AsyncFunctionDef = _scoped
    visit_ClassDef = visit_Lambda = _scoped

    # -- resolution ------------------------------------------------------------
    def _refers(self, node) -> str | None:
        """'CLASS' if *node* denotes the class, 'AMBIGUOUS' if it might,
        else None."""
        scope = self.stack[-1]
        if isinstance(node, ast.Name):
            k = _kinds(scope, node.id)
            if CLASS in k:
                return CLASS if k == {CLASS} else "AMBIGUOUS"
            return None
        if isinstance(node, ast.Attribute) and node.attr == CLASS_NAME:
            chain = []
            v = node.value
            while isinstance(v, ast.Attribute):
                chain.insert(0, v.attr)
                v = v.value
            if not isinstance(v, ast.Name):
                return None
            k = _kinds(scope, v.id)
            dotted = ".".join([v.id] + chain)
            mods = k & {MODULE, REEXPORT}
            if mods and not chain:
                return CLASS if k == mods else "AMBIGUOUS"
            pkgs = {x[4:] for x in k if isinstance(x, str) and x.startswith("PKG:")}
            if pkgs and dotted in ({ATOMS_MODULE} | self.reexporters):
                return CLASS if len(k) == 1 or all(
                    isinstance(x, str) and x.startswith("PKG:") for x in k) else "AMBIGUOUS"
        return None

    def _site(self, node, category, ref):
        self.sites.append({"line": node.lineno, "col": node.col_offset,
                           "category": category if ref == CLASS else "ambiguous",
                           "form": category})

    def _mark(self, ref_node):
        for n in ast.walk(ref_node):
            self.consumed.add(id(n))

    def visit_Call(self, node):
        ref = self._refers(node.func)
        if ref:
            self._site(node, "construction", ref)
            self._mark(node.func)
        elif isinstance(node.func, ast.Name) and node.func.id in ("isinstance", "issubclass") \
                and len(node.args) == 2:
            cls = node.args[1]
            cands = cls.elts if isinstance(cls, ast.Tuple) else [cls]
            for c in cands:
                r = self._refers(c)
                if r:
                    self._site(node, "type_test", r)
                    self._mark(c)
        self.generic_visit(node)

    def visit_Compare(self, node):
        # type(v) is atom / is not / == / !=, in either order
        operands = [node.left] + node.comparators
        for i, op in enumerate(node.ops):
            if not isinstance(op, (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)):
                continue
            a, b = operands[i], operands[i + 1]
            for x, y in ((a, b), (b, a)):
                r = self._refers(y)
                if r and isinstance(x, ast.Call) and isinstance(x.func, ast.Name) \
                        and x.func.id == "type":
                    self._site(node, "type_test", r)
                    self._mark(y)
        self.generic_visit(node)

    def visit_MatchClass(self, node):
        r = self._refers(node.cls)
        if r:
            self._site(node, "type_test", r)
            self._mark(node.cls)
        self.generic_visit(node)

    def visit_Name(self, node):
        if id(node) not in self.consumed and isinstance(node.ctx, ast.Load):
            r = self._refers(node)
            if r:
                self._site(node, "other", r)

    def visit_Attribute(self, node):
        if id(node) not in self.consumed and isinstance(node.ctx, ast.Load):
            r = self._refers(node)
            if r:
                self._site(node, "other", r)
                self._mark(node)
                return
        self.generic_visit(node)


def scan_source(src: str, path: Path, reexporters: frozenset) -> dict:
    """Census one file's source.  Never executes it."""
    tree = ast.parse(src, filename=str(path))
    this = _module_of(path)
    binder = _Binder(this, path.stem == "__init__", reexporters)
    binder.visit(tree)
    counter = _Counter(binder.scopes, reexporters)
    counter.visit(tree)
    # "imports the class": the class itself, or clausal.logic.atoms as a
    # module (a re-exporter imported AS A MODULE is not counted -- it is
    # imported for its own names; a use through it is still a site)
    wanted = {CLASS, MODULE, "PKG:" + ATOMS_MODULE}
    imports = any(k in wanted for s in binder.scopes.values()
                  for ks in s.bindings.values() for k in ks)
    counts = Counter(s["category"] for s in counter.sites)
    return {"imports_class": imports, "sites": counter.sites, "counts": dict(counts)}


def _binds_class_at_module_level(src: str, path: Path, reexporters) -> bool:
    tree = ast.parse(src, filename=str(path))
    binder = _Binder(_module_of(path), path.stem == "__init__", reexporters)
    binder.visit(tree)
    top = binder.scopes[id(tree)]
    return CLASS in top.bindings.get(CLASS_NAME, set())


def find_reexporters(engine_root: Path | None) -> frozenset:
    """Engine modules that bind ``atom`` (the class) at module level, so that
    ``from <them> import atom`` is the class too.  Fixpoint over the tree."""
    if engine_root is None or not engine_root.is_dir():
        return frozenset()
    files = [p for p in _walk([engine_root]) if p.suffix == ".py"]
    srcs = {}
    for p in files:
        try:
            srcs[p] = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    found: set[str] = set()
    while True:
        new = set(found)
        for p, src in srcs.items():
            mod = _module_of(p)
            if mod is None or mod == ATOMS_MODULE or mod in new:
                continue
            try:
                if _binds_class_at_module_level(src, p, frozenset(new)):
                    new.add(mod)
            except SyntaxError:
                pass
        if new == found:
            return frozenset(found)
        found = new


def _walk(roots):
    for root in roots:
        root = Path(root)
        if root.is_file():
            if root.suffix in SUFFIXES:
                yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS
                                 and not d.endswith(".egg-info"))
            for f in sorted(filenames):
                if f.endswith(SUFFIXES):
                    yield Path(dirpath) / f


def census(roots, reexporters) -> dict:
    files = list(_walk(roots))
    per_file, unparsed = {}, []
    totals = Counter()
    for p in files:
        try:
            src = p.read_text(encoding="utf-8")
            res = scan_source(src, p, reexporters)
        except (SyntaxError, UnicodeDecodeError, ValueError, RecursionError) as e:
            unparsed.append({"path": str(p), "error": f"{type(e).__name__}: {e}"})
            continue
        if res["imports_class"] or res["sites"]:
            per_file[str(p)] = res
        totals.update(res["counts"])
    return {
        "roots": [str(r) for r in roots],
        "reexporters": sorted(reexporters),
        "files_found": len(files),
        "files_parsed": len(files) - len(unparsed),
        "files_unparsed": len(unparsed),
        "unparsed": unparsed,
        "files_importing_class": sum(1 for r in per_file.values() if r["imports_class"]),
        "files_with_sites": sum(1 for r in per_file.values() if r["sites"]),
        "totals": {k: totals.get(k, 0) for k in ("construction", "type_test", "other", "ambiguous")},
        "files": per_file,
    }


def _print(report, sites: bool):
    print(f"roots: {', '.join(report['roots'])}")
    print(f"re-exporting engine modules: {report['reexporters'] or '(none / no --engine-root)'}")
    print(f"files found {report['files_found']}  parsed {report['files_parsed']}  "
          f"UNPARSED {report['files_unparsed']}")
    print(f"files importing the atom class {report['files_importing_class']}  "
          f"files with a site {report['files_with_sites']}")
    t = report["totals"]
    print(f"constructions {t['construction']}  type tests {t['type_test']}  "
          f"other refs {t['other']}  ambiguous {t['ambiguous']}")
    for path, res in sorted(report["files"].items()):
        c = res["counts"]
        print(f"  {path}: construction={c.get('construction', 0)} "
              f"type_test={c.get('type_test', 0)} other={c.get('other', 0)} "
              f"ambiguous={c.get('ambiguous', 0)}"
              + ("" if res["sites"] else "  (imports it, no use)"))
        if sites:
            for s in res["sites"]:
                print(f"    {path}:{s['line']}:{s['col']}  {s['category']}"
                      + (f" ({s['form']})" if s["category"] == "ambiguous" else ""))
    for u in report["unparsed"]:
        print(f"  UNPARSED {u['path']}: {u['error']}")


# ── self-test ────────────────────────────────────────────────────────────────

_POSITIVE = '''
from clausal.logic.atoms import atom
from clausal.logic.atoms import atom as Tag
import clausal.logic.atoms
import clausal.logic.atoms as A
from clausal.logic import atoms
from clausal.logic.to_python import atom as Via

a = atom("x")                                   # construction 1
b = Tag("y")                                    # construction 2
c = clausal.logic.atoms.atom("z")               # construction 3
d = A.atom("w")                                 # construction 4
e = atoms.atom("v")                             # construction 5
f = Via("u")                                    # construction 6 (re-export)
if isinstance(a, atom): pass                    # type test 1
if isinstance(a, (int, A.atom)): pass           # type test 2
if type(a) is atom: pass                        # type test 3
if atom is not type(a): pass                    # type test 4
if issubclass(type(a), atoms.atom): pass        # type test 5
match a:
    case atom(): pass                           # type test 6
class Sub(atom): pass                           # other 1
cls = atom                                      # other 2
def inner():
    from clausal.logic.atoms import atom as local
    return local("t")                           # construction 7
'''
_POSITIVE_EXPECT = {"construction": 7, "type_test": 6, "other": 2, "ambiguous": 0}

_NEGATIVE = '''
from clausal import atom
from clausal.logic.atoms import is_atom, mint
import clausal.logic.atoms as A
goal = atom("X")                                # the BUILTIN atom/1
ok = is_atom("x") and type("x") is str
s = "atom('x') and isinstance(v, atom)"         # text, not code
t = A.is_atom("y")
def shadow():
    def atom(x): return x
    return atom("q"), isinstance(1, atom)
class K:
    atom = 3
    def m(self): return self.atom
'''

_AMBIGUOUS = '''
from clausal import atom
from clausal.logic.atoms import atom
x = atom("a")                                   # which one? the file binds both
'''


def self_test() -> int:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "pos.py").write_text(_POSITIVE)
        (root / "neg.py").write_text(_NEGATIVE)
        (root / "amb.py").write_text(_AMBIGUOUS)
        (root / "broken.py").write_text("def (:\n")
        reex = frozenset({"clausal.logic.to_python"})
        rep = census([root], reex)
    ok = True

    def check(label, got, want):
        nonlocal ok
        mark = "ok  " if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"  {mark} {label}: got {got!r}, want {want!r}")

    print("self-test")
    check("files found", rep["files_found"], 4)
    check("files unparsed (a broken file is COUNTED, not dropped)", rep["files_unparsed"], 1)
    pos = next(v for k, v in rep["files"].items() if k.endswith("pos.py"))
    got = {k: pos["counts"].get(k, 0) for k in _POSITIVE_EXPECT}
    check("POSITIVE control counts", got, _POSITIVE_EXPECT)
    neg = [v for k, v in rep["files"].items() if k.endswith("neg.py")]
    check("NEGATIVE control sites", [s for v in neg for s in v["sites"]], [])
    amb = next(v for k, v in rep["files"].items() if k.endswith("amb.py"))
    check("ambiguous binding reported as ambiguous", amb["counts"], {"ambiguous": 1})
    print("self-test PASSED" if ok else "self-test FAILED")
    return 0 if ok else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("roots", nargs="*")
    parser.add_argument("--engine-root", type=Path,
                        default=Path(__file__).resolve().parents[2] / "clausal",
                        help="the engine's clausal/ package dir, scanned for re-exporters "
                             "(default: the tree this tool sits in)")
    parser.add_argument("--sites", action="store_true", help="list every site")
    parser.add_argument("--json", help="write the full report here")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.roots:
        parser.error("give at least one ROOT (or --self-test)")
    reex = find_reexporters(args.engine_root)
    rep = census(args.roots, reex)
    _print(rep, args.sites)
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=1))
    return 1 if rep["files_unparsed"] else 0


if __name__ == "__main__":
    sys.exit(main())
