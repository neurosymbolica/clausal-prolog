"""A10 audit — term rewriting, templating & import (2026-07-05 Fable partition).

Adversarial tests + regression guards for:
  clausal/templating/{term_rewriting,compiler,parser}.py, clausal/import_hook.py,
  clausal/_lazy_hook.py, clausal/codegen.py, clausal/logic/goal_expansion.py,
  clausal/pythonic_ast/{node_class,nodes,transform,conversion_from_python_ast}.py

Suspected-bug tests assert the CORRECT behavior and are marked
``xfail(strict=False)`` — they turn into passing guards when fixed.
Everything else is a plain regression guard for behavior confirmed correct.

Run per file only:
  PYTHONPATH=<clone> python -m pytest tests/audit_2026_07_05/test_10_rewriting_import.py -v
"""
import ast
import os
import subprocess
import sys
import textwrap

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal import Var, solve
from clausal.import_hook import _load_module, _load_prolog_module
from clausal.logic.solve import call

_COUNTER = [0]


def _load(tmp_path, src, stem="a10mod"):
    """Write *src* to a uniquely-named .clausal file and load it fresh.

    Unique module names avoid the module-scoped-atom double-load pitfall.
    """
    _COUNTER[0] += 1
    name = f"a10_{stem}_{_COUNTER[0]}"
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(src))
    return _load_module(name, str(path))


def _logic(mod):
    return mod.__dict__["$module"]


def _values(goal, var):
    out = []
    for _ in solve(goal):
        out.append(var.value)
    return out


# ═════════════════════════════════════════════════════════════════════════════
# A10-F001 — .pl import: cut must be rejected, not translated to a dead goal
# ═════════════════════════════════════════════════════════════════════════════


def test_F001_pl_cut_rejected_at_import(tmp_path):
    pl = tmp_path / "a10_cut.pl"
    pl.write_text("f(X) :- X > 0, !.\n")
    with pytest.raises(SyntaxError, match="[Cc]ut"):
        _load_prolog_module("a10_cutmod", str(pl))


def test_F001_guard_pl_ite_rejected(tmp_path):
    """(C -> T ; E) is properly rejected with a clear message."""
    pl = tmp_path / "a10_ite.pl"
    pl.write_text("g(X) :- ( X > 0 -> Y = pos ; Y = neg ), h(Y).\n")
    with pytest.raises(SyntaxError, match="If-then-else"):
        _load_prolog_module("a10_itemod", str(pl))


def test_F001_guard_pl_non_utf8_rejected(tmp_path):
    pl = tmp_path / "a10_latin.pl"
    pl.write_bytes("f(a).\n% caf\xe9\n".encode("latin-1"))
    with pytest.raises(SyntaxError, match="UTF-8"):
        _load_prolog_module("a10_latinmod", str(pl))


# ═════════════════════════════════════════════════════════════════════════════
# A10-F002 — Store-context logic-var-shaped names in embedded Python code
# ═════════════════════════════════════════════════════════════════════════════


def test_F002_allcaps_python_assignment_loads(tmp_path):
    m = _load(tmp_path, """
        MAX = 5
        p(1),
    """)
    assert m.MAX == 5


def test_F002_underscore_python_local_loads(tmp_path):
    m = _load(tmp_path, """
        def helper():
            _tmp = 5
            return _tmp
        p(1),
    """)
    assert m.helper() == 5


def test_F002_guard_lowercase_python_code_ok(tmp_path):
    m = _load(tmp_path, """
        max_val = 5
        p(1),
    """)
    assert m.max_val == 5


# ═════════════════════════════════════════════════════════════════════════════
# A10-F003 — EDCG: plain-DCG nonterminals in a sequence break state threading
# ═════════════════════════════════════════════════════════════════════════════


def test_F003_edcg_sequence_of_plain_dcg_nonterminals(tmp_path):
    m = _load(tmp_path, """
        a >> (["a"])
        b >> (["b"])
        -edcg_pred(p, 0, [dcg])
        p >> (a, b)
    """)
    lm = _logic(m)
    assert len(list(call("p", [mint("a"), mint("b")], [], module=lm))) == 1
    assert len(list(call("p", [mint("b"), mint("a")], [], module=lm))) == 0


def test_F003_guard_plain_dcg_sequence(tmp_path):
    m = _load(tmp_path, """
        a >> (["a"])
        b >> (["b"])
        p >> (a, b)
    """)
    lm = _logic(m)
    assert len(list(call("p", [mint("a"), mint("b")], [], module=lm))) == 1
    assert len(list(call("p", [mint("b"), mint("a")], [], module=lm))) == 0


def test_F003_guard_edcg_accumulator_with_plain_call(tmp_path):
    """A single plain-DCG call between accumulator pushes threads correctly."""
    m = _load(tmp_path, """
        -edcg_acc(cnt, V_, In_, Out_, {Out_ == In_ + V_})
        w >> (["w"])
        -edcg_pred(q, 0, [cnt, dcg])
        q >> ([1] // cnt, w, [2] // cnt)
    """)
    lm = _logic(m)
    out = Var()
    vals = [out.value for _ in call("q", 0, out, [mint("w")], [], module=lm)]
    assert vals == [3]


# ═════════════════════════════════════════════════════════════════════════════
# A10-F004 — clause on an -import_from name clobbers the source predicate
# ═════════════════════════════════════════════════════════════════════════════


def test_F004_local_clause_does_not_clobber_imported_predicate(tmp_path):
    """A10-D003 resolved 2026-08-25 as option (a): a load-time error.

    Was ``xfail`` — the importer's clause silently replaced the library's
    clause list process-wide.  Extending it instead is not available (step 5
    compiles ONE dispatch from ONE clause list against ONE ``globals_``), so
    the shape is refused at load time and the library keeps its own answers.
    See ``todo/done/imported-functor-clause-list-replaced-not-extended.md`` and
    ``tests/test_imported_functor_clause_clobber.py``.
    """
    lib_path = tmp_path / "a10_f004_lib.clausal"
    lib_path.write_text('twice(X, Y) <- (Y == X * 2)\n')
    lib = _load_module("a10_f004_lib", str(lib_path))

    b = Var()
    assert _values(lib.twice(4, b), b) == [8]

    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, """
            -import_from(a10_f004_lib, [twice])
            twice(0, "zero") <- (1 is 1)
            use(A, B) <- twice(A, B)
        """)
    assert "twice/2" in str(exc_info.value)

    b2 = Var()
    assert _values(lib.twice(4, b2), b2) == [8], \
        "importer's local clause destroyed the library's own predicate"


def test_F004_guard_plain_import_does_not_disturb_source(tmp_path):
    lib_path = tmp_path / "a10_f004b_lib.clausal"
    lib_path.write_text('twice(X, Y) <- (Y == X * 2)\n')
    lib = _load_module("a10_f004b_lib", str(lib_path))
    m = _load(tmp_path, """
        -import_from(a10_f004b_lib, [twice])
        use(A, B) <- twice(A, B)
    """)
    b = Var()
    assert _values(lib.twice(4, b), b) == [8]
    b2 = Var()
    assert _values(m.use(4, b2), b2) == [8]


# ═════════════════════════════════════════════════════════════════════════════
# A10-F005 — regex auto-binding: body-only named groups silently lose binding
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.xfail(strict=False, reason="A10-F005: find_var_for_group only "
                   "resolves head FIELD names; a group naming a body-only var "
                   "binds a fresh Var and the binding is silently lost")
def test_F005_regex_body_only_group_binds(tmp_path):
    m = _load(tmp_path, """
        -import_from(regex, [match])
        grab(S, R) <- (
            match(r"(?P<VAL>\\d+)x", S),
            R is VAL
        )
    """)
    r = Var()
    vals = _values(m.grab("42x", r), r)
    assert vals == ["42"]


def test_F005_guard_regex_head_var_group_binds(tmp_path):
    m = _load(tmp_path, """
        -import_from(regex, [match])
        year_of(S, YEAR) <- (
            match(r"(?P<YEAR>\\d{4})-\\d{2}", S)
        )
    """)
    y = Var()
    assert _values(m.year_of("2026-03", y), y) == ["2026"]


def test_F005_guard_regex_pattern_precompiled(tmp_path):
    m = _load(tmp_path, """
        -import_from(regex, [match])
        chk(S) <- match(r"a+b", S)
    """)
    assert any(k.startswith("_re_") for k in m.__dict__), \
        "static pattern should be interned into module globals"


# ═════════════════════════════════════════════════════════════════════════════
# A10-F006 — arrow-lambda inner transformer loses source_lines (heuristic arrow)
# ═════════════════════════════════════════════════════════════════════════════


def test_F006_lambda_body_lt_negative_literal(tmp_path):
    m = _load(tmp_path, """
        f(L, R) <- include((X <- (X< -3)), L, R)
    """)
    r = Var()
    assert _values(m.f([-10, -5, 0, 2], r), r) == [[-10, -5]]


def test_F006_guard_top_level_lt_negative_literal(tmp_path):
    m = _load(tmp_path, """
        g(X) <- (X< -3)
    """)
    assert len(list(solve(m.g(-10)))) == 1
    assert len(list(solve(m.g(0)))) == 0


def test_F006_guard_lambda_body_spaced_comparison(tmp_path):
    m = _load(tmp_path, """
        f(L, R) <- include((X <- (X < -3)), L, R)
    """)
    r = Var()
    assert _values(m.f([-10, -5, 0, 2], r), r) == [[-10, -5]]


def test_F006_guard_module_atom_in_lambda_body(tmp_path):
    m = _load(tmp_path, """
        -private([red, blue])
        pick(L, R) <- include((X <- (X is red)), L, R)
        mk(A, B) <- (A is red, B is blue)
    """)
    a, b = Var(), Var()
    for _ in solve(m.mk(a, b)):
        r = Var()
        vals = _values(m.pick([a.value, b.value], r), r)
        assert len(vals) == 1 and len(vals[0]) == 1


# ═════════════════════════════════════════════════════════════════════════════
# A10-F007 — dump_transformed oracle: black except-clause + missing source_lines
# ═════════════════════════════════════════════════════════════════════════════


def test_F007_dump_source_runs_without_black(tmp_path):
    try:
        import black  # noqa: F401
        pytest.skip("black installed here; failure mode needs black absent")
    except ImportError:
        pass
    from clausal.tools.dump_transformed import dump_source
    path = tmp_path / "a10_dump.clausal"
    path.write_text('p(1),\n')
    out = dump_source(str(path))
    assert "$define_predicate" in out


def test_F007_dump_source_arrow_fidelity(tmp_path):
    from clausal.tools.dump_transformed import dump_source
    path = tmp_path / "a10_dumpfid.clausal"
    path.write_text('g(X) <- (X< -3)\n')
    out = dump_source(str(path))
    assert "Lt(" in out and "Lambda(" not in out, \
        "oracle must parse 'X< -3' exactly as the import hook does (Lt goal)"


# ═════════════════════════════════════════════════════════════════════════════
# A10-F008 — TermExpansion q()-pattern doc examples are non-functional
# ═════════════════════════════════════════════════════════════════════════════


def test_F008_te_doc_quick_example(tmp_path):
    m = _load(tmp_path, """
        TermExpansion(
            q(fact(X)),
            [q(fact(X)), q(logged_fact(X))],
            STATE, STATE
        ),
        fact("a"),
        fact("b"),
    """)
    lm = _logic(m)
    assert len(lm.db.clauses_for("fact", 1)) == 2
    assert len(lm.db.clauses_for("logged_fact", 1)) == 2


def test_F008_te_doc_suppression_example(tmp_path):
    m = _load(tmp_path, """
        TermExpansion(q(debug(X)), [], STATE, STATE) <- True
        debug("x"),
        keep(1),
    """)
    lm = _logic(m)
    assert len(lm.db.clauses_for("debug", 1)) == 0
    assert len(lm.db.clauses_for("keep", 1)) == 1


def test_F008_guard_te_var_pattern_one_to_many(tmp_path):
    """The tested-and-working TE idiom: a plain variable pattern."""
    m = _load(tmp_path, """
        TermExpansion(TERM, [TERM, TERM], STATE, STATE) <- True
        color("red"),
    """)
    lm = _logic(m)
    assert len(lm.db.clauses_for("color", 1)) == 2


# ═════════════════════════════════════════════════════════════════════════════
# A10-F009 — CompareChain goals are produced but not compilable
# ═════════════════════════════════════════════════════════════════════════════


def test_F009_compare_chain_goal(tmp_path):
    m = _load(tmp_path, """
        mid(X) <- (0 < X < 10)
    """)
    assert len(list(solve(m.mid(5)))) == 1
    assert len(list(solve(m.mid(20)))) == 0


def test_F009_guard_single_comparisons(tmp_path):
    m = _load(tmp_path, """
        mid(X) <- (0 < X, X < 10)
    """)
    assert len(list(solve(m.mid(5)))) == 1
    assert len(list(solve(m.mid(20)))) == 0


# ═════════════════════════════════════════════════════════════════════════════
# A10-F010 — stdlib shadowing by .clausal/.pl files (docs claim it can't happen)
# ═════════════════════════════════════════════════════════════════════════════

_SHADOW_PROBE = """
import sys
sys.path.insert(0, {clone!r})
import clausal.import_hook
sys.path.insert(0, {shadow!r})
import wave
print("PYFILE" if (wave.__file__ or "").endswith(".py") else wave.__file__)
"""


@pytest.mark.timeout(60)
def test_F010_stdlib_not_shadowed_by_clausal_file(tmp_path):
    clone = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "wave.clausal").write_text("f(1),\n")
    code = _SHADOW_PROBE.format(clone=clone, shadow=str(shadow))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=50)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "PYFILE", \
        f"stdlib 'wave' was shadowed: {r.stdout.strip()!r}"


# ═════════════════════════════════════════════════════════════════════════════
# A10-F011 — zero-arity trailing-comma fact is silently a no-op
# ═════════════════════════════════════════════════════════════════════════════


def test_F011_zero_arity_fact(tmp_path):
    m = _load(tmp_path, """
        -private([flag])
        flag,
        p(1),
    """)
    lm = _logic(m)
    assert len(lm.db.clauses_for("flag", 0)) == 1


def test_F011_guard_zero_arity_rule(tmp_path):
    m = _load(tmp_path, """
        -private([flag])
        flag <- True
    """)
    lm = _logic(m)
    assert len(list(call("flag", module=lm))) == 1


# ═════════════════════════════════════════════════════════════════════════════
# A10-F012 — malformed -private / -module silently ignored
# ═════════════════════════════════════════════════════════════════════════════


def test_F012_malformed_private_raises(tmp_path):
    with pytest.raises(SyntaxError):
        _load(tmp_path, """
            -private(helper(X))
            p(1),
        """)


def test_F012_malformed_module_exports_raise(tmp_path):
    with pytest.raises(SyntaxError):
        _load(tmp_path, """
            -module(m, exports)
            p(1),
        """)


def test_F012_guard_unknown_directive_raises(tmp_path):
    with pytest.raises(SyntaxError, match="Unknown directive"):
        _load(tmp_path, """
            -no_such_directive(foo/1)
            p(1),
        """)


def test_F012_guard_import_from_arity_errors(tmp_path):
    with pytest.raises(SyntaxError, match="import_from"):
        _load(tmp_path, """
            -import_from(some.module)
            p(1),
        """)


# ═════════════════════════════════════════════════════════════════════════════
# A10-F013 (boundary → A11) — clausal.call shadowed by the builtin call class
# ═════════════════════════════════════════════════════════════════════════════


def test_F013_clausal_call_is_query_api():
    import clausal
    from clausal.logic.solve import call as solve_call
    assert clausal.call is solve_call


# ═════════════════════════════════════════════════════════════════════════════
# A10-F014 — templating: kwonly __args__ raises raw StopIteration
# ═════════════════════════════════════════════════════════════════════════════


def test_F014_magic_args_kwonly_clean_error():
    from clausal.templating.compiler import compile_template_func
    from clausal.templating.parser import TemplateCompileError
    src = "@{}\ndef t(FN):\n    def inner(*, __args__={FN}):\n        pass\n"
    node = ast.parse(src).body[0]
    with pytest.raises(TemplateCompileError):
        compile_template_func(node)


# ═════════════════════════════════════════════════════════════════════════════
# A10-F015 — codegen._infer_args: walrus target visited before value
# ═════════════════════════════════════════════════════════════════════════════


def test_F015_infer_args_walrus_load_before_store():
    from clausal.codegen import _infer_args
    stmts = ast.parse("y = (x := x + 1)").body
    assert [a.arg for a in _infer_args(stmts).args] == ["x"]


def test_F015_guard_infer_args_basics():
    from clausal.codegen import _infer_args
    def params(src):
        return [a.arg for a in _infer_args(ast.parse(textwrap.dedent(src)).body).args]
    assert params("x += 1") == ["x"]
    assert params("r = [i for i in xs]") == ["xs"]
    assert params("for i in seq: use(i)") == ["seq", "use"]


# ═════════════════════════════════════════════════════════════════════════════
# A10-F016 — pythonic_ast: traversal gaps, dead REMOVED sentinel, __all__ holes
# ═════════════════════════════════════════════════════════════════════════════


def test_F016_list_literal_transform_children():
    from clausal.pythonic_ast.nodes import ListLiteral, IntLiteral
    lit = ListLiteral(elements=[IntLiteral(value=1)])
    replaced = lit.transform_children(lambda n: IntLiteral(value=99))
    assert replaced.elements[0].value == 99


def test_F016_removed_sentinel_honored():
    from clausal.pythonic_ast.nodes import REMOVED, IntLiteral
    from clausal.pythonic_ast.transform import _transform_node_list
    out = _transform_node_list([IntLiteral(value=1), IntLiteral(value=2)],
                               lambda n: REMOVED if n.value == 1 else n)
    assert all(getattr(n, "value", None) != 1 and n is not REMOVED for n in out)


def test_F016_all_exports_module_items():
    from clausal.pythonic_ast import nodes
    for name in ("SpecializeDirective", "EdcgAccDecl", "EdcgPassDecl",
                 "EdcgPredDecl"):
        assert name in nodes.__all__, f"{name} missing from nodes.__all__"


def test_F016_guard_yield_dataclass_traversal_documented():
    """Yield holds a child node but inherits the no-op traversal (latent)."""
    from clausal.pythonic_ast.nodes import Yield, IntLiteral
    y = Yield(value=IntLiteral(value=1))
    assert y.children() == []  # current (inconsistent) behavior — see F016


# ═════════════════════════════════════════════════════════════════════════════
# A10-F017 — single-letter -import_from alias: no load-time validation
# ═════════════════════════════════════════════════════════════════════════════


def test_F017_single_letter_alias_rejected_at_load(tmp_path):
    lib = tmp_path / "a10_f017_lib.clausal"
    lib.write_text('twice(X, Y) <- (Y == X * 2)\n')
    _load_module("a10_f017_lib", str(lib))
    with pytest.raises(SyntaxError):
        _load(tmp_path, """
            -import_from(a10_f017_lib, [alias(twice, T)])
            use(A, B) <- T(A, B)
        """)


def test_F017_guard_titlecase_alias_works(tmp_path):
    lib = tmp_path / "a10_f017b_lib.clausal"
    lib.write_text('twice(X, Y) <- (Y == X * 2)\n')
    _load_module("a10_f017b_lib", str(lib))
    m = _load(tmp_path, """
        -import_from(a10_f017b_lib, [alias(twice, Dbl)])
        use(A, B) <- Dbl(A, B)
    """)
    b = Var()
    assert _values(m.use(4, b), b) == [8]


# ═════════════════════════════════════════════════════════════════════════════
# Regression guards — behavior probed and confirmed correct
# ═════════════════════════════════════════════════════════════════════════════


def test_guard_arrow_body_guards(tmp_path):
    for src in ("h(X) <- p(X) or q(X)",
                "h(X) <- p(X), q(X),",
                "h(X) <- X + 1"):
        with pytest.raises(SyntaxError, match="parenthesized"):
            _load(tmp_path, src)


def test_guard_strict_atoms(tmp_path):
    with pytest.raises(NameError, match="undeclared"):
        _load(tmp_path, """
            -strict_atoms
            v(X) <- (X is undeclared_atom_a10)
        """)


def test_guard_bare_atom_automint(tmp_path):
    # -implicit_atoms: this test verifies the auto-mint behaviour itself
    m = _load(tmp_path, "-implicit_atoms\nv(X) <- (X is a10_minted_atom)")
    x = Var()
    assert _values(m.v(x), x) == [mint("a10_minted_atom")]


def test_guard_dcg_parse_generate_if_not_str(tmp_path):
    m = _load(tmp_path, """
        greeting >> (["hello"], name)
        name >> (["world"])
        opt >> if_(["a"], ["b"], ["c"])
        nox >> (not ["x"], ["y"])
        hi >> ("hi")
    """)
    lm = _logic(m)
    assert len(list(call("greeting", [mint("hello"), mint("world")], [],
                         module=lm))) == 1
    s = Var()
    assert len(list(call("greeting", s, [], module=lm))) == 1
    assert len(list(call("opt", [mint("a"), mint("b")], [], module=lm))) == 1
    assert len(list(call("opt", [mint("c")], [], module=lm))) == 1
    assert len(list(call("opt", [mint("a"), mint("c")], [], module=lm))) == 0
    assert len(list(call("nox", [mint("y")], [], module=lm))) == 1
    assert len(list(call("nox", [mint("x")], [], module=lm))) == 0
    # ``hi >> ("hi")`` is a STRING terminal routed through ``sequence//1``,
    # so it consumes the string and, equivalently, its char-ATOM list.
    assert len(list(call("hi", "hi", "", module=lm))) == 1
    assert len(list(call("hi", [char_atom("h"), char_atom("i")], [],
                         module=lm))) == 1


def test_guard_dcg_pushback_and_meta_nonterminal(tmp_path):
    m = _load(tmp_path, """
        v >> (["x"])
        (u, ["p"]) >> (v)
        run(G) >> (G)
        word >> (["w"])
    """)
    lm = _logic(m)
    rest = Var()
    n = 0
    for _ in call("u", [mint("x"), mint("y")], rest, module=lm):
        n += 1
        got = rest.value
        # strings-as-lists: [("p",), ("y",)] may surface as "py" -- the
        # same term either way (spec §6.2)
        assert got in ([mint("p"), mint("y")], "py")
    assert n == 1
    assert len(list(call("run", m.word, [mint("w")], [], module=lm))) == 1


def test_guard_qualified_import_and_var_rejection(tmp_path):
    lib = tmp_path / "a10_qlib.clausal"
    lib.write_text('twice(X, Y) <- (Y == X * 2)\n')
    _load_module("a10_qlib", str(lib))
    m = _load(tmp_path, """
        -import_module(a10_qlib)
        use(A, B) <- a10_qlib.twice(A, B)
    """)
    b = Var()
    assert _values(m.use(3, b), b) == [6]
    with pytest.raises(SyntaxError, match="Logic variable"):
        _load(tmp_path, "u(A) <- a10_qlib.FOO.twice(A, 1)")


def test_guard_escapes_and_literals(tmp_path):
    m = _load(tmp_path, """
        node = ~~(1 + 2)
        term = --(foo(X, 1))
        with --{} as goals:
            foo(X, 1)
            bar(Y)
        p(-3),
        p(2),
        d(D, V) <- (V is ++D["k"])
        sub(L, E) <- (E is ++L[1:3])
        greet(NAME, S) <- (S is f"hello {NAME}!")
    """)
    assert isinstance(m.node, ast.BinOp)
    assert type(m.term).__name__ == "Call"
    assert [type(g).__name__ for g in m.goals] == ["Call", "Call"]
    x = Var()
    assert _values(m.p(x), x) == [-3, 2]
    v = Var()
    assert _values(m.d({"k": 7}, v), v) == [7]
    e = Var()
    assert _values(m.sub([0, 1, 2, 3], e), e) == [[1, 2]]
    s = Var()
    assert _values(m.greet("bob", s), s) == ["hello bob!"]


def test_guard_binop_structural_unify(tmp_path):
    m = _load(tmp_path, """
        mk(A, B, T) <- (T is A + B)
        un(T, A, B) <- (T is A + B)
    """)
    t = Var()
    for _ in solve(m.mk(1, 2, t)):
        term = t.value
        a, b = Var(), Var()
        assert [(x, y) for x, y in
                ((a.value, b.value) for _ in solve(m.un(term, a, b)))] == [(1, 2)]


def test_guard_facts_inside_module_level_if(tmp_path):
    """Conditional facts: module-level if-blocks are still clause scope."""
    m = _load(tmp_path, """
        if True:
            p(1),
        q(2),
    """)
    lm = _logic(m)
    assert len(lm.db.clauses_for("p", 1)) == 1


@pytest.mark.timeout(90)
def test_guard_pyc_cache_hit_preserves_directives(tmp_path):
    """Cached (.pyc) import recovers module_items — -dynamic still applies."""
    clone = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    moddir = tmp_path / "cachemod"
    moddir.mkdir()
    (moddir / "a10dyncache.clausal").write_text("-dynamic(seen/1)\nseen(0),\n")
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(clone)!r})
        import clausal.import_hook
        sys.path.insert(0, {str(moddir)!r})
        import a10dyncache
        lm = a10dyncache.__dict__["$module"]
        print(lm.db.is_dynamic("seen", 1), len(lm.db.clauses_for("seen", 1)))
    """)
    r1 = subprocess.run([sys.executable, "-c", code], capture_output=True,
                        text=True, timeout=40)
    r2 = subprocess.run([sys.executable, "-c", code], capture_output=True,
                        text=True, timeout=40)
    assert r1.returncode == 0 and r1.stdout.strip() == "True 1", r1.stderr
    assert r2.returncode == 0 and r2.stdout.strip() == "True 1", r2.stderr
    assert list(moddir.glob("__pycache__/*.pyc")), "no .pyc written"


@pytest.mark.timeout(60)
def test_guard_lazy_hook_activates_and_removes_itself(tmp_path):
    clone = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    moddir = tmp_path / "lazymod"
    moddir.mkdir()
    (moddir / "a10lazyfacts.clausal").write_text("p(1),\np(2),\n")
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(clone)!r})
        import clausal
        import wave                    # bare stdlib import must survive the stub
        sys.path.insert(0, {str(moddir)!r})
        import a10lazyfacts
        lm = a10lazyfacts.__dict__["$module"]
        real = any(type(f).__name__ == "PredicateFinder" for f in sys.meta_path)
        lazy = any(type(f).__name__ == "_LazyHookFinder" for f in sys.meta_path)
        print(len(lm.db.clauses_for("p", 1)), real, lazy, wave.__name__)
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=50)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "2 True False wave"


def test_guard_if_call_syntax_errors(tmp_path):
    with pytest.raises(SyntaxError, match="if_"):
        _load(tmp_path, "c(X, L) <- if_(X >= 0, L is 1)")


def test_guard_lambda_keyword_rejected(tmp_path):
    with pytest.raises(SyntaxError, match="lambda"):
        _load(tmp_path, "f(L, R) <- include(lambda x: x, L, R)")


def test_guard_ternary_rejected(tmp_path):
    with pytest.raises(SyntaxError, match="if_"):
        _load(tmp_path, 'c(X, L) <- (L is (1 if X else 2))')


# ═════════════════════════════════════════════════════════════════════════════
# A10-F018 — .pyc cache invalidation on transformer upgrade (version tag)
# ═════════════════════════════════════════════════════════════════════════════


def test_F018_path_stats_folds_bytecode_tag(tmp_path):
    """A10-F018: the transformer-version tag is folded into the reported mtime
    so bumping it invalidates cached bytecode even when the source is
    unchanged. Consistent per version, so cache hits still work.

    The reported mtime uses *nanosecond* precision
    (``(st_mtime_ns ^ TAG) & 0xFFFFFFFF``) so a same-size edit within the same
    integer second still invalidates (see tests/test_pycache.py); the tag XOR
    still participates, so a tag bump still invalidates old caches."""
    import os
    from clausal.import_hook import _ClausalSourceLoader, CLAUSAL_BYTECODE_TAG
    src = tmp_path / "a10f018.clausal"
    src.write_text("fact(1),\n")
    loader = _ClausalSourceLoader("a10f018", str(src))
    stats = loader.path_stats(str(src))
    raw_ns = os.stat(str(src)).st_mtime_ns
    assert stats["mtime"] == (raw_ns ^ CLAUSAL_BYTECODE_TAG) & 0xFFFFFFFF
    # Idempotent within a version.
    assert loader.path_stats(str(src))["mtime"] == stats["mtime"]
    # Tag still participates: a different tag yields a different reported mtime
    # (so a tag bump invalidates cached bytecode), confirmed by recomputing
    # with a hypothetical bumped tag.
    bumped = (raw_ns ^ (CLAUSAL_BYTECODE_TAG + 1)) & 0xFFFFFFFF
    assert bumped != stats["mtime"]
