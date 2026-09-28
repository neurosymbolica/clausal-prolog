"""D15: a package directory whose ``__init__`` is a ``.clausal`` file must
load as a Clausal package even when it is imported BEFORE
``clausal.import_hook`` has loaded.

The lazy stub finder (``clausal/_lazy_hook.py``) only recognised a FLAT
``name.clausal`` file, so it let the import through to PathFinder, which
claimed the directory as a PEP 420 namespace package: its ``__init__`` never
ran, the module had no ``__clausal_module__``, and its ``-import_from`` of a
sibling file never registered.  Import order must not matter.
"""
import os
import subprocess
import sys
import textwrap

CLONE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _write_package(root):
    pkg = root / "lazyhook_pkg_d15"
    pkg.mkdir()
    (pkg / "__init__.clausal").write_text(
        "-module(lazyhook_pkg_d15, [p(X)])\n"
        "-import_from(lazyhook_pkg_d15.sib, [q])\n"
        "p(X) <- q(X)\n")
    (pkg / "sib.clausal").write_text(
        "-module(sib, [q(X)])\n"
        "q(1),\n")


def _run(tmp_path, first_import):
    code = (f"import sys\n"
            f"sys.path.insert(0, {CLONE!r})\n"
            f"sys.path.insert(0, {str(tmp_path)!r})\n"
            + first_import + "\n" + textwrap.dedent(f"""
        import lazyhook_pkg_d15 as pkg
        print("HOOK_LOADED_BEFORE", {("clausal.import_hook" in first_import)!r})
        print("CLAUSAL_MODULE", hasattr(pkg, "__clausal_module__"))
        from clausal import Var, call
        from clausal.logic.solve import _deref_walk
        X = Var()
        print("ANSWERS", [_deref_walk(X) for _ in
                          call("p", X, module=pkg.__clausal_module__)])
    """))
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=120)


def test_package_imported_before_import_hook(tmp_path):
    _write_package(tmp_path)
    r = _run(tmp_path, "import clausal  # the stub only; no import_hook yet\n"
                       "assert 'clausal.import_hook' not in sys.modules")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CLAUSAL_MODULE True" in r.stdout, r.stdout + r.stderr
    assert "ANSWERS [1]" in r.stdout, r.stdout + r.stderr


def test_package_imported_after_import_hook(tmp_path):
    """The positive control: the same package with the real hook loaded."""
    _write_package(tmp_path)
    r = _run(tmp_path, "import clausal.import_hook")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CLAUSAL_MODULE True" in r.stdout, r.stdout + r.stderr
    assert "ANSWERS [1]" in r.stdout, r.stdout + r.stderr
