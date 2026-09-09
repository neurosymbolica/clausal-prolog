"""Generated code reaches the injected runtime names through ``$``-prefixed
bindings (2026-09-09 ruling: TitleCase has no role in Clausal code; a Python
class is reached via ``++ClassName``).

Every compiled ``.clausal`` module's namespace used to carry ~170 bare
TitleCase names that exist only for GENERATED code: the AST node classes
seeded from ``simple_ast.__all__`` (``Predicate``, ``Call``, ``Add``, ...)
and ``INJECTED_RUNTIME_BUILTINS`` (``Var``, ``Compound``, ``Quantity``,
``PyThunk``, ...).  Because they were plain globals, a user predicate named
like one of them (``Sub/2``, ``Node/1``, ``Var/1``) shadowed the class the
generated code needed and the module failed to load.

This round: every namespace that seeds those names binds each one under
its ``$`` twin as well (ONE table, ``with_dollar_twins``), every emitter
references the ``$`` twin, and the bare aliases stay for a deprecation
window (see todo/remove-bare-injected-titlecase-globals-after-deprecation-
2026-09-09.md).  ``Undefined`` is the canonical Kleene value and stays bare
by design -- it gets no twin.
"""

from __future__ import annotations

import ast
import importlib
import os
import sys
import tempfile
import warnings

import pytest

from clausal import Var, solve
from clausal.import_hook import _load_module, runtime_builtins
from clausal.logic.compiler.predicate import INJECTED_RUNTIME_BUILTINS
from clausal.pythonic_ast import nodes as simple_ast
from clausal.templating.term_rewriting import EmbedTransformer

from tests.tagged_terms_support import capture_predicate_codegen


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_inline(name: str, source: str):
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def _transformed_source(source: str) -> str:
    """The EmbedTransformer output for *source*, unparsed."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(source)
        tree = EmbedTransformer(
            source_lines=source.splitlines(keepends=True)).visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _generated_names(source_text: str) -> set[str]:
    """Every ``ast.Name`` id in *source_text* (``$`` made parseable)."""
    tree = ast.parse(source_text.replace("$", "DOLLAR_"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id.replace("DOLLAR_", "$"))
        elif isinstance(node, ast.MatchClass) and isinstance(node.cls, ast.Name):
            names.add(node.cls.id.replace("DOLLAR_", "$"))
    return names


_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def temp_fixture_module():
    """Write a ``.clausal`` file under tests/fixtures and import it as
    ``tests.fixtures.<name>`` so ``capture_predicate_codegen`` can re-drive
    its predicates; removed afterwards."""
    created = []

    def _make(name: str, source: str):
        path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
        with open(path, "w") as f:
            f.write(source)
        created.append((name, path))
        return importlib.import_module(f"tests.fixtures.{name}")

    yield _make
    for name, path in created:
        sys.modules.pop(f"tests.fixtures.{name}", None)
        if os.path.exists(path):
            os.unlink(path)


_INJECTED_BARE = [
    "Var", "Compound", "DictTerm", "SetTerm", "KWTerm", "Trail", "PyThunk",
    "FStringThunk", "Quantity", "PredicateMeta", "BoolEq", "BoolImpl",
]
_NODE_CLASSES = ["Predicate", "Call", "LoadName", "Add", "Sub", "Node", "Module"]


# ── (a) the $ twins exist, in every seeding namespace ───────────────────────

class TestDollarTwinsAreBound:
    @pytest.mark.parametrize("name", _INJECTED_BARE)
    def test_injected_table_binds_dollar_twin(self, name):
        assert INJECTED_RUNTIME_BUILTINS[f"${name}"] is INJECTED_RUNTIME_BUILTINS[name]

    @pytest.mark.parametrize("name", _INJECTED_BARE + _NODE_CLASSES)
    def test_runtime_builtins_binds_dollar_twin(self, name):
        assert runtime_builtins[f"${name}"] is runtime_builtins[name]

    def test_node_class_twins_are_the_simple_ast_classes(self):
        for name in simple_ast.__all__:
            assert runtime_builtins[f"${name}"] is getattr(simple_ast, name), name

    def test_undefined_stays_bare_only(self):
        # The canonical Kleene value: bare by ruling, no twin.
        assert "Undefined" in INJECTED_RUNTIME_BUILTINS
        assert "$Undefined" not in INJECTED_RUNTIME_BUILTINS
        assert "$Undefined" not in runtime_builtins

    def test_compiled_module_globals_carry_the_twins(self):
        mod = _load_inline(
            "_dollar_globals_probe",
            "-module(dollar_globals_probe, [P(X)])\nP(1),\n",
        )
        g = vars(mod)
        for name in _INJECTED_BARE + _NODE_CLASSES:
            assert g[f"${name}"] is runtime_builtins[name], name

    def test_bare_query_globals_carry_the_twins(self):
        """The bare-query path derives its globals from the module dict plus
        the compiler's own base_globals; the twins must reach it too."""
        from clausal.logic.solve import Module, _compile_as_query
        from clausal.terms import Compound

        mod = Module("_dollar_qg", module_dict={})
        dispatch_fn, _ = _compile_as_query(Compound("=", (Var(), Var())), mod)
        g = dispatch_fn.__globals__
        for name in _INJECTED_BARE:
            assert g[f"${name}"] is INJECTED_RUNTIME_BUILTINS[name], name


# ── (a) generated code references the $ twins ───────────────────────────────

_EMIT_SOURCE = (
    "-allow_singletons\n"
    "-module(dollar_emit_probe, [Speed(V), Fresh(L), Esc(X, Y), Dct(D), "
    "Sett(S), Fs(X, S), Arith(X, Y), Go(Y)])\n"
    "-import_from(py.units, [m])\n"
    "Speed(V) <- (V == 5(m))\n"
    "Fresh(L) <- (L == [A, B])\n"
    "Esc(X, Y) <- (Y == ++(X + 1))\n"
    "Dct(D) <- (D == {'a': 1})\n"
    "Sett(S) <- (S == {1, 2})\n"
    "Fs(X, S) <- (S == f\"v={X}\")\n"
    "Arith(X, Y) <- (Y is X + 1)\n"
    "Go(Y) <- (Arith(1, Y))\n"
)


class TestEmbedTransformerEmitsDollarNames:
    def test_clause_constructors_are_dollar_prefixed(self):
        src = _transformed_source(_EMIT_SOURCE)
        names = _generated_names(src)
        for name in ("Predicate", "Call", "LoadName", "Var", "Quantity",
                     "PyThunk", "FStringThunk", "DictTerm", "SetLiteral",
                     "Unify", "Add", "PredicateMeta"):
            assert f"${name}" in names, f"${name} not referenced:\n{src}"
            assert name not in names, f"bare {name} still referenced:\n{src}"

    def test_no_bare_runtime_name_survives_in_generated_code(self):
        """The general form of the test above: NOTHING generated code
        references is a bare runtime-table name."""
        names = _generated_names(_transformed_source(_EMIT_SOURCE))
        bare_table = {n for n in runtime_builtins if not n.startswith("$")}
        leaked = sorted((names & bare_table) - {"Undefined"})
        assert not leaked, leaked


class TestCompiledPredicateCodeEmitsDollarNames:
    def test_fresh_var_quantity_and_arith_node_are_dollar_prefixed(
            self, temp_fixture_module):
        temp_fixture_module(
            "dollar_codegen_probe",
            "-allow_singletons\n"
            "-module(dollar_codegen_probe, [Fresh(L), Arith(X, Y), "
            "Pair(A, B, P)])\n"
            "Fresh(L) <- (L == [A, B])\n"
            "Arith(X, Y) <- (Y == X + 1)\n"
            "Pair(A, B, (A, B)),\n",
        )
        src = capture_predicate_codegen("tests.fixtures.dollar_codegen_probe")
        names = _generated_names(src)
        assert "$Var" in names, src
        assert "Var" not in names, src
        assert "$Add" in names, src
        assert "Add" not in names, src
        bare_table = {n for n in runtime_builtins if not n.startswith("$")}
        leaked = sorted((names & bare_table) - {"Undefined"})
        assert not leaked, (leaked, src)


# ── (b) the deprecation window: bare aliases still work ─────────────────────

class TestBareAliasesStayForTheDeprecationWindow:
    @pytest.mark.parametrize("name", _INJECTED_BARE)
    def test_bare_injected_name_still_bound(self, name):
        assert name in INJECTED_RUNTIME_BUILTINS
        assert runtime_builtins[name] is INJECTED_RUNTIME_BUILTINS[name]

    def test_bare_var_call_in_user_code_still_works(self):
        """A ``++Var()`` escape (user code, not generated code) still finds
        the bare alias in the module namespace this round."""
        mod = _load_inline(
            "_dollar_bare_var_probe",
            "-module(dollar_bare_var_probe, [Mk(X), Chk(X)])\n"
            "Mk(X) <- (X == ++Var())\n"
            "Chk(1),\n",
        )
        from clausal.logic.variables import deref, is_var
        # ``++Var()`` hands back a fresh, unbound variable.
        X = Var()
        answers = [is_var(deref(X)) for _ in solve(mod.Mk(X), mod)]
        assert answers == [True]
        assert len(list(solve(mod.Chk(Var()), mod))) == 1


# ── (c) the collision class the change removes ──────────────────────────────

_COLLIDING = {
    # user predicate spelled like a simple_ast node class / injected name
    # (``==`` is arithmetic evaluation; ``is`` is unification)
    "Sub": "Sub(X, Y) <- (Y == X - 1)\nGo(Y) <- (Sub(5, Y))\n",
    "Add": "Add(X, Y) <- (Y == X - 1)\nGo(Y) <- (Add(5, Y))\n",
    "Call": "Call(X) <- (X == 4)\nGo(Y) <- (Call(Y))\n",
    "Node": "Node(4),\nGo(Y) <- (Node(Y))\n",
    "Module": "Module(4),\nGo(Y) <- (Module(Y))\n",
    "Var": "Var(4),\nGo(Y) <- (Var(Y))\n",
    "Predicate": "Predicate(4),\nGo(Y) <- (Predicate(Y))\n",
    "Quantity": "Quantity(4),\nGo(Y) <- (Quantity(Y))\n",
    "LoadName": "LoadName(4),\nGo(Y) <- (LoadName(Y))\n",
}


class TestUserPredicateNamedLikeARuntimeClass:
    @pytest.mark.parametrize("name", sorted(_COLLIDING))
    def test_loads_and_runs(self, name):
        body = _COLLIDING[name]
        arity = 2 if name in ("Sub", "Add") else 1
        head = f"{name}(X, Y)" if arity == 2 else f"{name}(X)"
        mod = _load_inline(
            f"_dollar_collide_{name}",
            f"-module(dollar_collide_{name}, [{head}, Go(Y)])\n{body}",
        )
        from clausal.logic.variables import deref
        # Read the binding inside the loop -- backtracking unwinds the
        # trail once the generator is exhausted.
        Y = Var()
        answers = [deref(Y) for _ in solve(mod.Go(Y), mod)]
        assert answers == [4]

    def test_lowercase_spelling_never_collided(self):
        mod = _load_inline(
            "_dollar_collide_sub_lower",
            "-module(dollar_collide_sub_lower, [sub(X, Y), go(Y)])\n"
            "sub(X, Y) <- (Y == X - 1)\ngo(Y) <- (sub(5, Y))\n",
        )
        assert len(list(solve(mod.go(Var()), mod))) == 1
