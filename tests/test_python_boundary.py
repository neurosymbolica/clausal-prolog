"""Spec §9.1: one outbound conversion for py.* wrappers and ++ thunks."""

from clausal.modules.py._helpers import to_python
from clausal.logic.atoms import mint
from clausal.terms import DictTerm


def test_to_python_unwraps_atoms_everywhere():
    assert to_python(mint("bar")) == "bar"
    assert to_python([mint("a"), ("f", mint("b"))]) == ["a", ("f", "b")]
    assert to_python(DictTerm({mint("k"): mint("v")})) == {"k": "v"}


def test_to_python_unwraps_a_cell_atom():
    # Stage A: ``mint`` still returns a ``str``, so the assertions above are
    # identities today.  A literal arity-0 cell is the shape Stage B makes
    # canonical — it is what actually exercises the unwrap.  A cell of
    # arity >= 1 stays a tuple with converted elements, exactly as
    # ``_deep_deref`` preserves tuples today.
    assert to_python(("bar",)) == "bar"
    assert to_python([("a",), ("f", ("b",))]) == ["a", ("f", "b")]
    assert to_python(DictTerm({("k",): ("v",)})) == {"k": "v"}


def test_deep_deref_is_still_exported_as_an_alias():
    from clausal.modules.py._helpers import _deep_deref
    assert _deep_deref is to_python


def test_thunk_argument_is_converted():
    # a ++ thunk receiving an atom sees its spelling (Plan 0: same object; the
    # assertion pins the ROUTE — the compiled body must call $to_python)
    import ast
    from clausal.logic.compiler.terms_to_ast import term_to_ast_expr
    from clausal.terms import PyThunk
    from clausal.logic.variables import Var
    v = Var()
    expr = term_to_ast_expr(PyThunk(lambda x: x, [v]), {})
    assert "$to_python" in ast.dump(expr)


def test_to_python_is_injected_as_a_runtime_builtin():
    from clausal.logic.compiler.predicate import INJECTED_RUNTIME_BUILTINS
    assert INJECTED_RUNTIME_BUILTINS["$to_python"] is to_python


def test_a_cell_atom_reaches_a_thunk_as_its_spelling(tmp_path):
    # The end-to-end route, not just the emitted AST: a ++ escape calling a
    # str method on an arity-0 cell atom only works if the argument was
    # converted on the way out.  Under the old single-level $deref the thunk
    # would see the 1-tuple and raise AttributeError.
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref

    src = tmp_path / "boundary_thunk.clausal"
    src.write_text("to_upper(_s, _r) <- (_r is ++_s.upper())\n")
    mod = _load_module("boundary_thunk", str(src))
    logic_mod = mod.__dict__["$module"]

    out = Var()
    results = [deref(out) for _ in call("to_upper", ("hello",), out,
                                        module=logic_mod)]
    assert results == ["HELLO"]
