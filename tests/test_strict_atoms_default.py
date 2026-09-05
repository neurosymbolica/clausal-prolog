"""Tests for strict-atoms-by-default (staged binary flip).

See docs/superpowers/specs/2026-07-24-strict-atoms-default-design.md.
Atom names are prefixed ``sad_`` (strict-atoms-default) and unique per
test so the process-wide predicate_builtins dict is not cross-polluted.
"""
from __future__ import annotations

import ast
import os
import tempfile
import warnings

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
import clausal.logic.compiler_v2 as _compiler_v2
from clausal.import_hook import _load_module, predicate_builtins, runtime_builtins
from clausal.logic.compiler_v2 import ClausalStrictAtomsDeprecationWarning
from clausal.logic.predicate import PredicateMeta
from clausal.pythonic_ast import nodes as simple_ast
from clausal.pythonic_ast.nodes import ImplicitAtomsDeclaration
from clausal.templating.term_rewriting import EmbedTransformer


def _load_inline_clausal(name: str, source: str):
    """Write `source` to a temp .clausal file and load it (avoids the
    conftest .clausal collector that would surface persistent fixtures)."""
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def test_implicit_atoms_mints_undeclared_bare_atom():
    """`-implicit_atoms` opts into loose auto-accept: an undeclared bare
    atom is accepted into the global dict (today's default behavior).

    P3-1 Task 2 (§1b/R2): the accepted value is now the plain interned str
    itself, not a minted ``PredicateMeta`` class -- the shared-identity
    claim (``mod.x is predicate_builtins[x]``) is unaffected.
    """
    assert "sad_implicit_red" not in predicate_builtins
    source = (
        "-implicit_atoms\n"
        "\n"
        "ColorImplicit(sad_implicit_red),\n"
    )
    mod = _load_inline_clausal("_sad_implicit_mints", source)
    assert isinstance(predicate_builtins["sad_implicit_red"], str)
    assert mod.sad_implicit_red is predicate_builtins["sad_implicit_red"]


def test_implicit_atoms_parenthesised_form():
    """`-implicit_atoms()` is accepted, same as the bare form."""
    source = (
        "-implicit_atoms()\n"
        "\n"
        "ColorImplicitParen(sad_implicit_paren_blue),\n"
    )
    mod = _load_inline_clausal("_sad_implicit_paren", source)
    # P3-1 Task 2 (§1b/R2): accepted atoms are plain strs, not classes.
    assert isinstance(mod.sad_implicit_paren_blue, str)


def test_implicit_atoms_rejects_arguments():
    """`-implicit_atoms(foo)` is a SyntaxError — the marker takes no args."""
    source = "-implicit_atoms(foo)\n\nX(y),\n"
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_sad_implicit_args", source)
    assert "-implicit_atoms takes no arguments" in str(exc_info.value)


def test_strict_and_implicit_mutually_exclusive():
    """A file carrying both directives is a SyntaxError."""
    source = (
        "-strict_atoms\n"
        "-implicit_atoms\n"
        "\n"
        "X(sad_both_atom),\n"
    )
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_sad_both", source)
    msg = str(exc_info.value)
    assert "mutually exclusive" in msg


def test_repl_transformer_injects_implicit_atoms():
    """A transformer in REPL mode seeds an ImplicitAtomsDeclaration so
    interactive cells auto-mint even under the strict file default."""
    tree = ast.parse("Color(sad_repl_undeclared),\n")
    t = EmbedTransformer(implicit_atoms_default=True)
    t.visit(tree)
    assert any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )


def test_file_transformer_does_not_inject_implicit_atoms():
    """The default (file) transformer does NOT seed implicit mode."""
    tree = ast.parse("Color(sad_file_undeclared),\n")
    t = EmbedTransformer()
    t.visit(tree)
    assert not any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )


def test_repl_transformer_respects_explicit_strict():
    """REPL mode must not override an explicit -strict_atoms in the cell."""
    tree = ast.parse("-strict_atoms\nColor(sad_repl_strict),\n")
    t = EmbedTransformer(implicit_atoms_default=True)
    t.visit(tree)
    assert not any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )


def test_undeclared_bare_atom_raises_by_default():
    """With no directive, an undeclared bare atom is a NameError."""
    assert "sad_default_red" not in predicate_builtins
    source = "ColorDefault(sad_default_red),\n"
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_sad_default_strict", source)
    msg = str(exc_info.value)
    assert "sad_default_red" in msg
    assert "-module" in msg and "-private" in msg
    assert "sad_default_red" not in predicate_builtins


def test_implicit_atoms_still_mints_after_flip():
    """`-implicit_atoms` remains the loose escape hatch after the flip.

    P3-1 Task 2 (§1b/R2): accepted atoms are plain strs, not classes.
    """
    source = "-implicit_atoms\nColorStill(sad_still_green),\n"
    mod = _load_inline_clausal("_sad_still_mints", source)
    assert isinstance(mod.sad_still_green, str)


def test_strict_atoms_deprecation_warns_once_per_process():
    """`-strict_atoms` still enforces strict, and emits the deprecation
    warning at most once per process."""
    _compiler_v2._strict_atoms_deprecation_emitted = False  # reset guard
    src = "-strict_atoms\n-module(m, [ok])\nUse(ok),\n"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load_inline_clausal("_sad_dep_1", src)
        _load_inline_clausal("_sad_dep_2", src)
    dep = [
        w for w in caught
        if issubclass(w.category, ClausalStrictAtomsDeprecationWarning)
    ]
    assert len(dep) == 1


def test_runtime_dict_key_intern_strict_by_default_no_pollution():
    """A neither-directive file (strict default) with an undeclared bare-atom
    dict key must fail WITHOUT the eager runtime key-intern minting the atom.

    The runtime ``$intern_atom`` helper builds dict literals during exec,
    before the compile-time strict pass runs. Under the strict default it must
    refuse to mint an undeclared key (matching the value-position default),
    rather than auto-minting and leaving the compile-time pass to raise after
    the atom already leaked into ``predicate_builtins``.
    """
    assert "sad_rtkey_indigo" not in predicate_builtins
    source = (
        "with_key(V) <- (V is {sad_rtkey_indigo: 1}[sad_rtkey_indigo]),\n"
    )
    with pytest.raises(NameError):
        _load_inline_clausal("_sad_rtkey_default", source)
    # Strict by default: the eager key-intern must not have leaked the atom.
    assert "sad_rtkey_indigo" not in predicate_builtins


def test_runtime_dict_key_intern_implicit_still_mints():
    """`-implicit_atoms` keeps the loose runtime key-intern behaviour."""
    assert "sad_rtkey_amber" not in predicate_builtins
    source = (
        "-implicit_atoms\n"
        "read_key(V) <- (V is {sad_rtkey_amber: 7}[sad_rtkey_amber]),\n"
    )
    mod = _load_inline_clausal("_sad_rtkey_implicit", source)
    assert mod.sad_rtkey_amber is predicate_builtins["sad_rtkey_amber"]


class TestDeclarednessIsPerModuleNotProcessWide:
    """P3-1 Task 7 fix round 1 (Critical, review-caught) regression tests.

    ``_process_bare_atom_refs``/``_make_intern_atom`` used to treat a name
    already present in ``module_dict`` as "already resolved" for
    STRICTNESS purposes -- but ``module_dict`` is pre-seeded at exec start
    with the entire process-wide ``predicate_builtins`` pool, so an atom
    some OTHER, earlier-loaded module declared (which installs it into
    that pool) silently satisfied a DIFFERENT module's own undeclared bare
    reference, regardless of that second module ever declaring/importing
    it itself. §1b is explicit that declaredness is a per-module compiler
    lint against the declared vocabulary -- separate from, and unaffected
    by, atom UNIFICATION identity being global by spelling (§1b/R2,
    deliberate, unchanged). These tests reproduce the reviewer's exact
    probe shape for both the bare-atom-reference path
    (``compiler_v2._process_bare_atom_refs``) and the dict-key path
    (``import_hook._make_intern_atom``), in both load orders, plus a
    control confirming the legitimate (declare-then-use) case still works.
    """

    def test_bare_atom_raises_even_though_another_module_declared_it_first(self):
        """Module A privately declares an atom; module B references the
        SAME spelling bare, undeclared. B must NameError -- A's declaration
        (and the process-pool entry it created) must not silently satisfy
        B's own strictness check."""
        _load_inline_clausal(
            "_t7leak_ab_owner",
            "-module(t7leak_ab_owner, [P(X)])\n"
            "-private([t7leak_ab_atom])\n"
            "P(t7leak_ab_atom),\n",
        )
        assert "t7leak_ab_atom" in predicate_builtins  # sanity: A did declare it
        with pytest.raises(NameError) as exc_info:
            _load_inline_clausal(
                "_t7leak_ab_user",
                "-module(t7leak_ab_user, [Q(X)])\n"
                "Q(X) <- (X == t7leak_ab_atom)\n",
            )
        msg = str(exc_info.value)
        assert "strict_atoms" in msg
        assert "t7leak_ab_atom" in msg

    def test_bare_atom_raises_regardless_of_load_order(self):
        """Same atom spelling, reversed timing: the undeclared module fails
        BEFORE anything has declared it, a LEGITIMATE declaration then
        succeeds, and a THIRD, still-undeclared module fails AFTER the
        pool already carries the spelling -- proving the fix is not merely
        "first loader wins" but genuinely per-module."""
        with pytest.raises(NameError):
            _load_inline_clausal(
                "_t7leak_ba_user_before",
                "-module(t7leak_ba_user_before, [Q(X)])\n"
                "Q(X) <- (X == t7leak_ba_atom)\n",
            )
        mod_owner = _load_inline_clausal(
            "_t7leak_ba_owner",
            "-module(t7leak_ba_owner, [P(X)])\n"
            "-private([t7leak_ba_atom])\n"
            "P(t7leak_ba_atom),\n",
        )
        assert isinstance(mod_owner.t7leak_ba_atom, str)
        with pytest.raises(NameError) as exc_info:
            _load_inline_clausal(
                "_t7leak_ba_user_after",
                "-module(t7leak_ba_user_after, [R(X)])\n"
                "R(X) <- (X == t7leak_ba_atom)\n",
            )
        msg = str(exc_info.value)
        assert "strict_atoms" in msg
        assert "t7leak_ba_atom" in msg

    def test_bare_atom_control_declaring_it_locally_compiles(self):
        """Control: a module that declares the atom itself compiles fine
        (the fix does not break the legitimate, intended case)."""
        mod = _load_inline_clausal(
            "_t7leak_ctrl",
            "-module(t7leak_ctrl, [P(X)])\n"
            "-private([t7leak_ctrl_atom])\n"
            "P(t7leak_ctrl_atom),\n",
        )
        assert isinstance(mod.t7leak_ctrl_atom, str)

    def test_dict_key_atom_raises_even_though_another_module_declared_it_first(self):
        """Dict-key path (``import_hook._make_intern_atom``) counterpart of
        ``test_bare_atom_raises_even_though_another_module_declared_it_first``."""
        _load_inline_clausal(
            "_t7leakd_ab_owner",
            "-module(t7leakd_ab_owner, [P(X)])\n"
            "-private([t7leakd_ab_atom])\n"
            "P(t7leakd_ab_atom),\n",
        )
        assert "t7leakd_ab_atom" in predicate_builtins  # sanity
        with pytest.raises(NameError) as exc_info:
            _load_inline_clausal(
                "_t7leakd_ab_user",
                "-module(t7leakd_ab_user, [Q(X)])\n"
                "Q(X) <- (X == {t7leakd_ab_atom: 1}[t7leakd_ab_atom])\n",
            )
        msg = str(exc_info.value)
        assert "strict_atoms" in msg
        assert "t7leakd_ab_atom" in msg
        assert "dict key" in msg

    def test_dict_key_atom_raises_regardless_of_load_order(self):
        """Dict-key path counterpart of
        ``test_bare_atom_raises_regardless_of_load_order``."""
        with pytest.raises(NameError):
            _load_inline_clausal(
                "_t7leakd_ba_user_before",
                "-module(t7leakd_ba_user_before, [Q(X)])\n"
                "Q(X) <- (X == {t7leakd_ba_atom: 1}[t7leakd_ba_atom])\n",
            )
        mod_owner = _load_inline_clausal(
            "_t7leakd_ba_owner",
            "-module(t7leakd_ba_owner, [P(X)])\n"
            "-private([t7leakd_ba_atom])\n"
            "P(t7leakd_ba_atom),\n",
        )
        assert isinstance(mod_owner.t7leakd_ba_atom, str)
        with pytest.raises(NameError) as exc_info:
            _load_inline_clausal(
                "_t7leakd_ba_user_after",
                "-module(t7leakd_ba_user_after, [R(X)])\n"
                "R(X) <- (X == {t7leakd_ba_atom: 1}[t7leakd_ba_atom])\n",
            )
        msg = str(exc_info.value)
        assert "strict_atoms" in msg
        assert "t7leakd_ba_atom" in msg

    def test_dict_key_control_declaring_it_locally_compiles(self):
        """Control: dict-key path counterpart -- a module that declares the
        atom itself compiles fine."""
        mod = _load_inline_clausal(
            "_t7leakd_ctrl",
            "-module(t7leakd_ctrl, [P(X)])\n"
            "-private([t7leakd_ctrl_atom])\n"
            "P(X) <- (X == {t7leakd_ctrl_atom: 1}[t7leakd_ctrl_atom])\n",
        )
        assert mod.P is not None


class TestPredicateBuiltinsPoolSplit:
    """P3-2 Task 8: ``predicate_builtins``/``runtime_builtins`` pool split.

    Closes ``todo/done/pythonic-ast-names-leak-into-strict-atom-namespace-
    2026-09-04.md``: ``import_hook.py`` used to seed every
    ``clausal.pythonic_ast.nodes.__all__`` class object (``Add``, ``Call``,
    ``Match``, ...) into the SAME process-wide ``predicate_builtins`` dict
    that backs the §1b/R2 global atom pool -- so a bare reference to one of
    these internal AST-node names resolved as a declared atom in a strict
    module with ZERO declarations, no other file needing to run first
    (unlike the P3-1 Task 7 leak, this one needed no prior module at all --
    the seed happens at process bootstrap).  The fix splits the one dict
    into two: ``runtime_builtins`` (the compilation-support namespace,
    still fully seeded into every module and still NOT atom-visible) and
    ``predicate_builtins`` (the atom pool, now genuinely empty until an
    atom is declared/accepted).  A unique ``simple_ast.__all__`` name is
    used per test below so no test's declaration can leak into another's
    (mirrors this file's own "unique name per test" discipline).
    """

    def test_todo_repro_undeclared_simple_ast_name_raises(self):
        """The todo's own repro, verbatim: a strict module with zero atom
        declarations, referencing ``Add`` bare in a clause body, must raise
        the strict-atoms diagnostic -- not silently resolve to
        ``clausal.pythonic_ast.nodes.Add``."""
        assert "Add" not in predicate_builtins
        assert runtime_builtins["Add"] is simple_ast.Add
        with pytest.raises(NameError) as exc_info:
            _load_inline_clausal(
                "_p8_pool_leak_probe",
                "-module(pool_leak_probe, [Chk(X)])\n"
                "Chk(X) <- (X == Add)\n",
            )
        msg = str(exc_info.value)
        assert "strict_atoms" in msg
        assert "Add" in msg
        # The pool must not have been polluted by the (failed) reference.
        assert "Add" not in predicate_builtins

    def test_declaring_the_colliding_name_as_atom_compiles_and_unifies_globally(
        self,
    ):
        """A module that DECLARES the colliding spelling as an atom still
        compiles, and the atom unifies globally (§1b/R2, unchanged) -- the
        split closes the LEAK, not legitimate declared use.  Two
        independent modules privately declaring the same spelling get the
        identical str object back from the shared atom pool."""
        mod_a = _load_inline_clausal(
            "_p8_sub_a",
            "-module(p8_sub_a, [P(X)])\n"
            "-private([Sub])\n"
            "P(Sub),\n",
        )
        assert isinstance(mod_a.Sub, str) and mod_a.Sub == "Sub"
        assert mod_a.Sub is not simple_ast.Sub
        assert predicate_builtins["Sub"] is mod_a.Sub
        # runtime_builtins is untouched by the declaration.
        assert runtime_builtins["Sub"] is simple_ast.Sub

        mod_b = _load_inline_clausal(
            "_p8_sub_b",
            "-module(p8_sub_b, [Q(X)])\n"
            "-private([Sub])\n"
            "Q(Sub),\n",
        )
        assert mod_b.Sub is mod_a.Sub  # global identity by spelling

    def test_simple_ast_name_raises_regardless_of_load_order(self):
        """Same pattern as ``TestDeclarednessIsPerModuleNotProcessWide``:
        an undeclared reference raises BEFORE anything has declared the
        spelling (proving the leak needs no earlier module at all -- the
        todo's point), a legitimate declaration then succeeds, and a THIRD,
        still-undeclared module fails AFTER the pool carries the spelling
        -- proving per-module declaredness, not first-loader-wins."""
        with pytest.raises(NameError):
            _load_inline_clausal(
                "_p8_mult_before",
                "-module(p8_mult_before, [Q(X)])\n"
                "Q(X) <- (X == Mult)\n",
            )
        mod_owner = _load_inline_clausal(
            "_p8_mult_owner",
            "-module(p8_mult_owner, [P(X)])\n"
            "-private([Mult])\n"
            "P(Mult),\n",
        )
        assert isinstance(mod_owner.Mult, str)

        with pytest.raises(NameError) as exc_info:
            _load_inline_clausal(
                "_p8_mult_after",
                "-module(p8_mult_after, [R(X)])\n"
                "R(X) <- (X == Mult)\n",
            )
        msg = str(exc_info.value)
        assert "strict_atoms" in msg
        assert "Mult" in msg

    def test_dict_key_path_also_rejects_simple_ast_name(self):
        """``import_hook._make_intern_atom`` (the dict-key path) counterpart:
        the same leak shape existed there too (``{Div: 1}[Div]`` resolved
        via the runtime class), so the split's identity check was applied
        to both consumers, not just ``_process_bare_atom_refs``."""
        assert "Div" not in predicate_builtins
        with pytest.raises(NameError) as exc_info:
            _load_inline_clausal(
                "_p8_div_dictkey",
                "-module(p8_div_dictkey, [Q(X)])\n"
                "Q(X) <- (X == {Div: 1}[Div])\n",
            )
        msg = str(exc_info.value)
        assert "strict_atoms" in msg
        assert "Div" in msg
        assert "dict key" in msg
        assert "Div" not in predicate_builtins

    def test_functor_declaration_shadows_simple_ast_name_locally(self):
        """§7.2 answer (P3-2 Task 2 report, carried into Task 8's scope): a
        module-local, field-carrying functor declaration whose spelling
        collides with a ``simple_ast.__all__`` name (``Call``) ALWAYS wins
        over the runtime-support binding, in THAT module's own namespace
        only -- exactly the same "declared wins locally" rule the bare-atom
        branch follows, and consistent with P3-2 Task 2's deliberate choice
        to bind a declared data functor's spelling through module_dict
        ONLY, never through the shared predicate_builtins pool (so this
        local shadowing cannot leak into, or be affected by, any other
        module's namespace)."""
        mod = _load_inline_clausal(
            "_p8_call_functor",
            "-module(p8_call_functor, [Call(x, y)])\n"
            "Result(V) <- (V is Call(1, 2))\n",
        )
        from clausal.logic.solve import call as _call
        from clausal.logic.variables import Var, deref, walk

        v = Var()
        results = [walk(deref(v)) for _ in _call(mod.Result, v)]
        assert results == [("Call", 1, 2)]
        # Locally shadowed to the plain interned spelling (P3-2 Task 2,
        # R6 revised) -- no longer the runtime class in THIS module.
        assert mod.Call == "Call"
        assert mod.Call is not simple_ast.Call
        # ...but never routed through the shared atom pool (Task 2,
        # deliberate) and the runtime pool itself is untouched -- purely a
        # per-module rebinding, so every OTHER module still sees the real
        # simple_ast.Call class under that name.
        assert "Call" not in predicate_builtins
        assert runtime_builtins["Call"] is simple_ast.Call

    def test_generated_code_fixture_with_fstrings_and_arith_still_loads(self):
        """Regression: every clause's generated code constructs a bare
        ``Predicate(head=..., body=...)`` at module-exec time
        (EmbedTransformer's rewrite) -- a ``simple_ast`` name that must
        still resolve via ``runtime_builtins`` post-split.
        ``quantity_head_literal.clausal`` is an existing, already
        suite-covered fixture (``tests/test_quantity_head_literal.py``)
        combining an f-string clause head (``Tagd(f"v{0}", tagged_)``)
        with arithmetic/quantity clause bodies."""
        from clausal.logic.solve import call as _call
        from clausal.logic.variables import Var, deref

        path = os.path.join(
            os.path.dirname(__file__), "clausal_modules",
            "quantity_head_literal.clausal",
        )
        mod = _load_module("_p8_qty_fixture_regress", path)
        n = Var()
        results = [
            getattr(deref(n), "__name__", deref(n)) for _ in _call(mod.ChkTag, n)
        ]
        assert results == ["tagged_"]
