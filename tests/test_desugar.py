"""Tests for the shared surface-desugar seam (clausal/templating/desugar.py).

This pass is a CONTRACT, not an internal detail: an independent SMT-based
checker maintained by a downstream consumer runs the very same function on
its own ``ast.parse`` so a surface sugar is expanded once rather than once
per front end.  The tests
below pin the three things a second consumer depends on:

* the rewrite itself (``P.key`` → ``P[key]``, chains, variable keys),
* purity and position preservation (a prover reports counterexample lines),
* totality — every shape the pass does not recognise comes out untouched, so
  a consumer that does not model it still reaches its own "unsupported" path.
"""
import ast
import copy

import pytest

from clausal.templating.desugar import (
    desugar_surface,
    dotted_attr_chain,
    is_dict_attr_access,
)


def _expr(src: str):
    return ast.parse(src, mode="eval").body


def _round(src: str) -> str:
    """Desugar an expression and unparse the result."""
    return ast.unparse(desugar_surface(_expr(src)))


# ── the rewrite ───────────────────────────────────────────────────────────────

def test_attribute_on_logic_var_becomes_subscript():
    """``P.key`` is exactly ``P[key]`` — that is the whole definition."""
    # nv
    assert _round("P.key") == "P[key]"


def test_chain_folds_left_to_right():
    """``P.a.b`` → ``P[a][b]``: the outermost attribute is the outer index."""
    # nv
    assert _round("P.a.b") == "P[a][b]"


def test_uppercase_attribute_is_a_variable_key():
    """``P.KEY`` → ``P[KEY]`` — the key is a logic variable, not an atom."""
    # nv
    assert _round("P.KEY") == "P[KEY]"


def test_underscore_base_is_a_logic_variable():
    """``_p.k`` — a leading-underscore name is a logic variable too."""
    # nv
    assert _round("_p.k") == "_p[k]"


def test_rewrite_reaches_nested_positions():
    """Sugar is expanded wherever it occurs, not just at the top level."""
    # nv
    assert _round("foo(P.k, [Q.j], {a: R.i})") == "foo(P[k], [Q[j]], {a: R[i]})"


def test_key_node_is_a_bare_name_not_a_string():
    """The index must be a ``Name`` so it resolves like any other bare atom.

    Interning the attribute *text* would bypass the atom-declaration rules and
    make ``P.status`` behave differently from ``P[status]``.
    """
    # nv
    node = desugar_surface(_expr("P.status"))
    assert isinstance(node, ast.Subscript)
    assert isinstance(node.slice, ast.Name) and node.slice.id == "status"


# ── what must NOT be rewritten ────────────────────────────────────────────────

def test_dotted_module_path_untouched():
    """``mod.pred`` is a qualified name — a different, pre-existing feature."""
    # nv
    assert _round("mod.pred") == "mod.pred"
    assert _round("myapp.graphs.utils") == "myapp.graphs.utils"


def test_qualified_call_untouched():
    """``mod.pred(A)`` stays a qualified predicate call."""
    # nv
    assert _round("mod.pred(A)") == "mod.pred(A)"


def test_method_call_form_left_alone():
    """``P.foo(A)`` is RESERVED, not sugar.

    The engine raises a SyntaxError for it and the prover must leave it
    unsupported.  Rewriting it to ``P[foo](A)`` would change the shape under
    both of them, so the ``func`` position is never touched.
    """
    # nv
    assert _round("P.foo(A)") == "P.foo(A)"
    assert _round("P.a.foo(A)") == "P.a.foo(A)"


def test_method_call_arguments_are_still_desugared():
    """Only the callee is protected; the arguments are ordinary terms."""
    # nv
    assert _round("P.foo(Q.k)") == "P.foo(Q[k])"


def test_python_escape_payload_untouched():
    """``++(D.value)`` is real Python — surface sugar does not apply inside it.

    The escape's operand is evaluated by the Python interpreter at search
    time, where ``.value`` is genuine attribute access on a Python object.
    """
    # nv
    assert _round("++(D.value)") == "++D.value"
    assert _round("++(D.value.other)") == "++D.value.other"


def test_spaced_plus_is_not_an_escape():
    """``+ +(D.k)`` (with a space) is not the escape, so the sugar applies."""
    # nv
    assert _round("+ +(D.k)") == "++D[k]"


def test_attribute_on_a_non_name_base_untouched():
    """``f(x).a`` does not bottom out in a Name — leave it exactly as parsed."""
    # nv
    assert _round("f(x).a") == "f(x).a"


def test_unrecognised_shapes_pass_through_verbatim():
    """Totality: anything the pass does not model round-trips unchanged."""
    # nv
    for src in ("a < -b", "X + 1", "[1, 2, 3]", "{k: V}", "not foo(X)",
                "findall(X, p(X), L)", "P[k]", "P['k']", "P[K]"):
        assert _round(src) == ast.unparse(_expr(src))


# ── purity and source positions ───────────────────────────────────────────────

def test_positions_are_preserved():
    """Every synthesised node carries the position of the construct it replaces.

    The prover reports counterexample locations by line, and the engine's
    ``<-`` arrow detection reads source columns, so a dropped position is a
    real bug in both.
    """
    # nv
    src = "foo(A) <- (\n    V is P.key,\n    bar(V)\n)"
    tree = desugar_surface(ast.parse(src))
    read = tree.body[0].value.comparators[0].operand.elts[0]
    subscript = read.comparators[0]
    assert isinstance(subscript, ast.Subscript)
    assert subscript.lineno == 2
    assert subscript.col_offset == 9          # column of `P` in `V is P.key`
    assert subscript.slice.lineno == 2
    # every node in the rewritten tree has a position
    for node in ast.walk(tree):
        if isinstance(node, (ast.expr, ast.stmt)):
            assert node.lineno is not None and node.col_offset is not None


def test_pass_is_pure_ast_to_ast():
    """No engine state: the module imports nothing but ``ast``."""
    # nv
    import clausal.templating.desugar as desugar_module
    source = ast.parse(open(desugar_module.__file__).read())
    imported = set()
    for node in ast.walk(source):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported == {"ast"}, imported


def test_desugaring_is_idempotent():
    """Running the pass twice is the same as running it once."""
    # nv
    once = desugar_surface(_expr("foo(P.a.b, Q.c)"))
    twice = desugar_surface(copy.deepcopy(once))
    assert ast.unparse(once) == ast.unparse(twice)


# ── the recognition predicates ────────────────────────────────────────────────

def test_is_dict_attr_access_predicate():
    # nv
    assert is_dict_attr_access(_expr("P.k"))
    assert is_dict_attr_access(_expr("P.a.b"))
    assert not is_dict_attr_access(_expr("mod.pred"))
    assert not is_dict_attr_access(_expr("f(x).a"))
    assert not is_dict_attr_access(_expr("P[k]"))


def test_dotted_attr_chain_splits_base_and_keys():
    # nv
    base, keys = dotted_attr_chain(_expr("P.a.b"))
    assert base.id == "P" and keys == ["a", "b"]
    assert dotted_attr_chain(_expr("f(x).a")) is None


# ── the engine really does go through this one implementation ─────────────────

def test_engine_visit_attribute_uses_the_shared_pass(monkeypatch):
    """``TermTransformer`` must not carry a second copy of the rewrite."""
    # nv
    from clausal.templating import term_rewriting

    calls = []
    real = term_rewriting.desugar_surface

    def spy(tree, *args, **kwargs):
        # ``*args`` absorbs the exclusion set the engine passes (the names it
        # does not read as variables); the spy asserts WHICH TREE reaches the
        # shared pass, not the call's arity.
        calls.append(ast.unparse(tree))
        return real(tree, *args, **kwargs)

    monkeypatch.setattr(term_rewriting, "desugar_surface", spy)
    term_rewriting.TermTransformer().visit(_expr("P.key"))
    assert calls == ["P.key"]


def test_engine_and_shared_pass_agree_on_the_compiled_shape():
    """``P.key`` and ``P[key]`` compile to the SAME simple_ast.

    Compared modulo the embedded ``position=`` metadata, which legitimately
    differs: the two spellings occupy different source columns.
    """
    # nv
    from clausal.templating.term_rewriting import TermTransformer

    class _StripPositions(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            node.keywords = [kw for kw in node.keywords
                             if "position" not in (kw.arg or "")]
            return node

    def compile_term(src):
        node = TermTransformer().visit(_expr(src))
        return ast.dump(ast.fix_missing_locations(_StripPositions().visit(node)))

    assert compile_term("P.key") == compile_term("P[key]")
    assert compile_term("P.a.b") == compile_term("P[a][b]")


def test_method_call_form_is_still_a_syntax_error():
    """The reserved shape must not have been desugared into something legal."""
    # nv
    from clausal.templating.term_rewriting import TermTransformer

    with pytest.raises(SyntaxError, match="[Mm]ethod-call"):
        TermTransformer().visit(_expr("P.foo(A)"))
