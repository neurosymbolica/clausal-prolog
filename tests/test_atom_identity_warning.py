"""Atoms are global-by-spelling after the P3-1 atom pivot (§1b/R2).

Pre-pivot, two modules that each ``-module``/``-private``-*declared* the same
atom held **distinct** module-local ``PredicateMeta`` classes, so unifying a
value carrying one against a value carrying the other failed silently — no
error, no solution.  ``CLAUSAL_WARN_ATOM_IDENTITY=1`` opted into a diagnostic
``__unify__`` hook (``ClausalAtomIdentityMismatchWarning``) that named both
owning modules on such a compare, one-shot per pair.

Under the pivot, a bare atom lowers to an interned, global-by-spelling Python
``str``: two same-spelled atoms declared in different modules are the
identical object, so they always unify and there is nothing left to
diagnose. The by-identity machinery this file used to pin
(``register_atom_identity``/``atom_by_id``/``_ATOM_IDENTITY_TABLE``,
``_make_atom_identity_unify``/``_atom_identity_warned``/
``_warn_atom_identity_enabled``, ``ClausalAtomIdentityMismatchWarning``, and
the ``CLAUSAL_WARN_ATOM_IDENTITY`` env-var hook) is deleted outright rather
than kept dark — this file is inverted to a compact "atoms are global" suite
asserting both the new unify behaviour and that the machinery is gone.

See ``implementation_plans/phase3-decomposition-and-p31-atom-pivot.md``
Task 3.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
import warnings

from clausal.logic.atoms import mint
from clausal.logic.compiler_v2 import _process_declarations


_SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestIdentityMachineryDeleted:
    """The by-identity atom machinery no longer exists anywhere it used to."""

    def test_predicate_module_has_no_identity_table(self):
        import clausal.logic.predicate as predicate_mod
        for name in (
            "register_atom_identity", "atom_by_id", "_ATOM_IDENTITY_TABLE",
            "_make_atom_identity_unify", "_atom_identity_warned",
            "_warn_atom_identity_enabled",
        ):
            assert not hasattr(predicate_mod, name), name

    def test_identity_symbols_not_in_predicate_all(self):
        import clausal.logic.predicate as predicate_mod
        assert "register_atom_identity" not in predicate_mod.__all__
        assert "atom_by_id" not in predicate_mod.__all__

    def test_atom_identity_mismatch_warning_class_is_gone(self):
        import clausal.logic.compiler_v2 as cv2
        assert not hasattr(cv2, "ClausalAtomIdentityMismatchWarning")

    def test_terms_to_ast_has_no_identity_lowering(self):
        import clausal.logic.compiler.terms_to_ast as terms_to_ast
        assert not hasattr(terms_to_ast, "atom_identity_lowering")
        assert not hasattr(terms_to_ast, "atom_identity_expr")
        assert not hasattr(terms_to_ast, "_ATOM_IDENTITY_DEPTH")

    def test_compiled_predicate_globals_carry_no_dollar_atom(self):
        """``$atom`` (the by-identity injection into every compiled
        predicate's globals) is gone from the injected runtime builtins."""
        from clausal.logic.compiler.predicate import INJECTED_RUNTIME_BUILTINS
        assert "$atom" not in INJECTED_RUNTIME_BUILTINS


class TestEnvFlagHasNoEffect:
    """``CLAUSAL_WARN_ATOM_IDENTITY`` is inert: no reads left anywhere, so a
    freshly minted zero-field class carries no diagnostic ``__unify__``
    regardless of the flag."""

    def test_flag_on_installs_no_unify_hook(self, monkeypatch):
        from clausal.logic.predicate import PredicateMeta
        monkeypatch.setenv("CLAUSAL_WARN_ATOM_IDENTITY", "1")
        atom = PredicateMeta("t3_flag_on_atom", (), {"_fields": ()})
        assert "__unify__" not in atom.__dict__

    def test_flag_off_installs_no_unify_hook(self, monkeypatch):
        from clausal.logic.predicate import PredicateMeta
        monkeypatch.delenv("CLAUSAL_WARN_ATOM_IDENTITY", raising=False)
        atom = PredicateMeta("t3_flag_off_atom", (), {"_fields": ()})
        assert "__unify__" not in atom.__dict__


class TestAtomsAreGlobal:
    """Cross-module same-spelled atoms are the identical object and unify."""

    def test_declared_atom_is_a_plain_str(self):
        module_dict = {"__name__": "pkg.owner", "__file__": "<pkg.owner>"}
        from clausal.import_hook import EmbedTransformer
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse("-private([t3_owned_atom])\n")
            t = EmbedTransformer()
            t.visit(tree)
        _process_declarations(t._module_items, module_dict)
        assert module_dict["t3_owned_atom"] == mint("t3_owned_atom")
        assert module_dict["t3_owned_atom"] == mint("t3_owned_atom")

    def test_two_modules_declaring_the_same_atom_get_the_same_object(self):
        """Two independently-run ``_process_declarations`` passes for
        different owning modules, same atom spelling: the pivot's global
        pool (``predicate_builtins``) means both bind the identical str."""
        from clausal.import_hook import EmbedTransformer

        def _declare(mod_name):
            module_dict = {"__name__": mod_name, "__file__": f"<{mod_name}>"}
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tree = ast.parse("-private([t3_shared_atom])\n")
                t = EmbedTransformer()
                t.visit(tree)
            _process_declarations(t._module_items, module_dict)
            return module_dict

        mod_a = _declare("pkg.a3")
        mod_b = _declare("pkg.b3")
        assert mod_a["t3_shared_atom"] is mod_b["t3_shared_atom"]

    def test_unify_of_same_named_declared_atoms_succeeds(self):
        from clausal.logic.variables import unify
        from clausal.logic.variables._variables import Trail
        assert unify("t3_unify_me", "t3_unify_me", Trail()) is True


# ── End-to-end two-module package: the OLD "no solution" repro now succeeds ──

_LIB_SRC = textwrap.dedent("""\
    -module(atomlib, [approved, check(X)])

    check(approved),
""")

_CALLER_SRC = textwrap.dedent("""\
    -import_from(atomid_pkg.atomlib, [check])
    -private([approved])

    ask() <- check(approved)
""")

_DRIVER = textwrap.dedent("""\
    import sys
    import clausal  # noqa: F401  (installs the .clausal import hook)
    from clausal.logic.solve import call

    import atomid_pkg.caller as caller

    lm = caller.__dict__["$module"]
    # ask/0 calls check(approved) where `approved` is the CALLER's local
    # declaration and check comes from atomlib whose clause head carries
    # atomlib's `approved` -- pre-pivot these were distinct classes and the
    # query had no solution; post-pivot both are the same global str.
    solutions = list(call("ask", module=lm))
    print("SOLUTION_COUNT", len(solutions))
""")


def _write_package(tmp_path):
    pkg = tmp_path / "atomid_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "atomlib.clausal").write_text(_LIB_SRC)
    (pkg / "caller.clausal").write_text(_CALLER_SRC)
    return tmp_path


def _run_driver(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), _SRC_ROOT])
    env.pop("CLAUSAL_WARN_ATOM_IDENTITY", None)
    proc = subprocess.run(
        [sys.executable, "-c", _DRIVER],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"driver failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    for line in proc.stdout.splitlines():
        if line.startswith("SOLUTION_COUNT"):
            return int(line.split()[1])
    raise AssertionError(f"no SOLUTION_COUNT line:\n{proc.stdout}")


def test_package_repro_now_finds_a_solution(tmp_path):
    """Two-module package, duplicate declared atom: the query that used to
    silently fail now succeeds (§1b/R2 — global-by-spelling atoms)."""
    root = _write_package(tmp_path)
    assert _run_driver(root) == 1
