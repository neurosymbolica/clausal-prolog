"""Spec §9.1: the outbound conversions — deep for py.*, top-level for ++.

One deep ``to_python`` is what every ``py.*`` wrapper crosses its arguments
with.  The ``++``/f-string thunk path takes ``unwrap_atom`` instead — §9.1's
pre-stated fallback, applied 2026-09-07 after Task 14's interleaved A/B put
``bench_thunk_atoms`` at B/A = 1.074 against the 3 % bar.  Both halves are
pinned here, including that they are DIFFERENT.
"""

from clausal.modules.py._helpers import to_python
from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.terms import DictTerm
from tests._suffix import SEAM


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
    assert to_python(mint("bar")) == "bar"
    assert to_python([mint("a"), ("f", mint("b"))]) == ["a", ("f", "b")]
    assert to_python(DictTerm({mint("k"): mint("v")})) == {"k": "v"}


def test_to_python_walks_a_ground_segstring():
    # §9.1: "string → str (a ground SegString walks first)".  ``deref``
    # follows Var bindings only, so without the dedicated arm a SegString
    # crosses out as the term object and a Python callee sees no text.
    # NB the assertion must pin the TYPE: SegString.__eq__ compares equal to
    # the str it walks to, so `to_python(seg) == "hello"` holds even with no
    # conversion at all and would be a vacuous test.
    from clausal.terms import SegString
    out = to_python(SegString(["hel", "lo"]))
    assert type(out) is str and out == "hello"
    nested = to_python([SegString(["a", "b"])])
    assert type(nested[0]) is str and nested == ["ab"]


def test_to_python_leaves_a_non_ground_segstring_raw():
    from clausal.logic.variables import Var
    from clausal.terms import SegString, VarSeg
    seg = SegString(["hel", VarSeg(Var())])
    assert to_python(seg) is seg


def test_to_python_lives_in_the_core_module_and_is_re_exported():
    # The compiler binds this function as $to_python, so its home must be on
    # the clausal.logic side: clausal.logic must not import clausal.modules.py
    # at module level.  The py.* wrappers re-export it, alias included.
    import clausal.logic.to_python as core
    from clausal.modules.py._helpers import _deep_deref
    assert core.to_python is to_python
    assert _deep_deref is to_python


def test_compiler_has_no_module_level_edge_into_modules_py():
    # Importing the compiler entrypoint must not drag clausal.modules.py in.
    import subprocess
    import sys
    code = (
        "import sys; import clausal.logic.compiler.predicate; "
        "print('clausal.modules.py' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr


def test_thunk_argument_takes_the_top_level_unwrap_not_the_deep_walk():
    # The ROUTE, pinned in the emitted AST: a ++ thunk argument lowers to
    # $unwrap_atom (spec §9.1's fallback, applied 2026-09-07 on Task 14's
    # perf gate), NOT to the deep $to_python the py.* wrappers get.
    import ast
    from clausal.logic.compiler.terms_to_ast import term_to_ast_expr
    from clausal.terms import PyThunk
    from clausal.logic.variables import Var
    v = Var()
    dumped = ast.dump(term_to_ast_expr(PyThunk(lambda x: x, [v]), {}))
    assert "$unwrap_atom" in dumped
    assert "$to_python" not in dumped


def test_unwrap_atom_takes_a_top_level_atom_and_nothing_deeper():
    from clausal.logic.to_python import unwrap_atom
    from clausal.logic.variables import Var
    assert unwrap_atom(mint("bar")) == "bar"
    assert type(unwrap_atom(mint("bar"))) is str
    # A container crosses RAW — this is the whole content of the fallback.
    nested = [mint("a"), ("f", mint("b"))]
    assert unwrap_atom(nested) is nested
    d = DictTerm({mint("k"): mint("v")})
    assert unwrap_atom(d) is d
    # …and the deep conversion is still one import away, for code that wants it
    assert to_python(nested) == ["a", ("f", "b")]
    assert to_python(d) == {"k": "v"}


def test_both_conversions_are_injected_as_runtime_builtins():
    from clausal.logic.compiler.predicate import INJECTED_RUNTIME_BUILTINS
    from clausal.logic.to_python import unwrap_atom
    # The deep one stays bound (the py.* wrappers' conversion, and generated
    # code may still reach it by name); the thunk path gets the shallow one.
    assert INJECTED_RUNTIME_BUILTINS["$to_python"] is to_python
    assert INJECTED_RUNTIME_BUILTINS["$unwrap_atom"] is unwrap_atom


def test_a_cell_atom_reaches_a_thunk_as_its_spelling(tmp_path):
    # The end-to-end route, not just the emitted AST: a ++ escape calling a
    # str method on an arity-0 cell atom only works if the argument was
    # converted on the way out.  Under the old single-level $deref the thunk
    # would see the 1-tuple and raise AttributeError.
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref

    src = tmp_path / f"boundary_thunk{SEAM}"
    src.write_text("to_upper(_s, _r) <- (_r is ++_s.upper())\n")
    mod = _load_module("boundary_thunk", str(src))
    logic_mod = mod.__dict__["$module"]

    out = Var()
    results = [deref(out) for _ in call("to_upper", mint("hello"), out,
                                        module=logic_mod)]
    # Stage 2 (spec §3 Q1): a thunk's str result is the ATOM, not the carrier.
    assert results == [mint("HELLO")]
