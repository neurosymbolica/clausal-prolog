"""THE FLIP — the acceptance rows of the atoms-as-cells / strings design.

One test per row of §13 of
``docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md``:
an atom is the arity-0 cell ``("bar",)``, a plain ``str`` is a STRING (the
list of its char atoms), and ``"..."`` means one or the other according to
the module's ``-double_quotes`` mode.

Source-level rows are written as ``.clausal`` snippets loaded through
``_load_inline_clausal``; builtin-level rows are driven through ``solve``
with cell goals.
"""

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import char_atom, mint
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve, _deref_walk
from clausal.logic.variables import Trail, Var, unify
from clausal.terms import term_canonical, term_str


def _load_inline_clausal(name: str, source: str):
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


def _formal(exc_info):
    """The FORMAL term of a raised ``error(Formal, Context)``.

    Asserting on ``str(exc)`` cannot tell ``type_error(atom, X)`` from a
    context string that merely mentions "atom"; every refusal row here goes
    through this and names the formal term and its type ATOM (spec §6.4).
    """
    return exc_info.value.term.args[0]


def _answers(goal, mod, *vars_):
    """Every solution's walked bindings for *vars_* (walked INSIDE the loop)."""
    out = []
    for _ in solve(goal, mod):
        out.append(tuple(_deref_walk(v) for v in vars_))
    return out


@pytest.fixture(scope="module")
def builtins_mod():
    """A module with no clauses of its own — a home for builtin-only goals."""
    return _load_inline_clausal(
        "_flip_builtins_home", "-private([bar, foo, a, b, c, hi, x, y, z])\n"
    )


# ── Rows 1-6: the term model at the surface ─────────────────────────────────


def test_row_01_bare_and_quoted_names_are_atoms():
    mod = _load_inline_clausal(
        "_flip_row01",
        "-private([bar])\n"
        "r1_bare(bar),\n"
        "r1_quoted('bar'),\n"
        "r1_is_atom(X) <- atom(X),\n",
    )
    X = Var()
    assert _answers(("r1_bare", X), mod, X) == [(("bar",),)]
    assert _answers(("r1_quoted", X), mod, X) == [(("bar",),)]
    assert len(list(solve(("r1_is_atom", mint("bar")), mod))) == 1


def test_row_02_double_quoted_in_chars_mode_is_a_string():
    mod = _load_inline_clausal(
        "_flip_row02",
        "-double_quotes(chars)\n"
        "r2(\"bar\"),\n"
        "r2_atom(X) <- atom(X),\n"
        "r2_string(X) <- string(X),\n"
        "r2_is_list(X) <- is_list(X),\n",
    )
    X = Var()
    assert _answers(("r2", X), mod, X) == [("bar",)]
    assert list(solve(("r2_atom", "bar"), mod)) == []
    assert len(list(solve(("r2_string", "bar"), mod))) == 1
    assert len(list(solve(("r2_is_list", "bar"), mod))) == 1


def test_row_03_atom_equals_quoted_atom_but_not_a_string():
    mod = _load_inline_clausal(
        "_flip_row03",
        "-double_quotes(chars)\n"
        "-private([bar])\n"
        "r3_same() <- (bar is 'bar'),\n"
        "r3_string() <- (bar is \"bar\"),\n"
        "r3_value(bar),\n",
    )
    assert len(list(solve(("r3_same",), mod))) == 1
    assert list(solve(("r3_string",), mod)) == []
    X = Var()
    # ``bar == ("bar",)`` seen from Python.
    assert _answers(("r3_value", X), mod, X) == [(("bar",),)]


def test_row_04_a_string_unifies_with_its_char_list():
    mod = _load_inline_clausal(
        "_flip_row04",
        "-double_quotes(chars)\n"
        "-private([a, b, c])\n"
        "r4() <- (\"abc\" is [a, b, c]),\n",
    )
    assert len(list(solve(("r4",), mod))) == 1
    # …and directly, both orientations.
    assert unify("abc", [mint("a"), mint("b"), mint("c")], Trail())
    assert unify([mint("a"), mint("b"), mint("c")], "abc", Trail())


def test_row_05_a_string_destructures_head_and_tail():
    mod = _load_inline_clausal(
        "_flip_row05",
        "-double_quotes(chars)\n"
        "r5([H, *T], H, T),\n"
        "r5_string(X) <- string(X),\n",
    )
    H, T = Var(), Var()
    assert _answers(("r5", "abc", H, T), mod, H, T) == [((("a",), "bc"))]
    assert len(list(solve(("r5_string", "bc"), mod))) == 1


def test_row_06_the_empty_string_is_the_empty_list():
    from clausal.logic.builtins._helpers import _standard_order_key

    assert unify("", [], Trail())
    assert _standard_order_key("") == _standard_order_key([])


# ── Rows 7-12: the name position ────────────────────────────────────────────


def test_row_07_functor_of_a_cell_answers_an_atom(builtins_mod):
    N, A = Var(), Var()
    assert _answers(
        ("functor", ("foo", ("a",)), N, A), builtins_mod, N, A
    ) == [(("foo",), 1)]
    assert len(list(solve(("atom", ("foo",)), builtins_mod))) == 1


def test_row_08_functor_constructs_a_cell(builtins_mod):
    T = Var()
    (built,), = _answers(("functor", T, mint("foo"), 2), builtins_mod, T)
    assert type(built) is tuple and built[0] == "foo" and len(built) == 3


def test_row_09_functor_refuses_a_string_name(builtins_mod):
    with pytest.raises(LogicException) as exc:
        list(solve(("functor", Var(), "foo", 1), builtins_mod))
    assert "atomic" in str(exc.value)


def test_row_10_unpack_answers_the_atom_name(builtins_mod):
    L = Var()
    (parts,), = _answers(
        ("unpack", ("foo", ("a",), "b"), L), builtins_mod, L)
    assert parts == [mint("foo"), mint("a"), "b"]
    # ``L = [foo, a, [b]]`` is the same answer, spelled as a char list.
    assert unify(parts, [mint("foo"), mint("a"), [char_atom("b")]], Trail())


def test_row_11_unpack_constructs_a_cell(builtins_mod):
    T = Var()
    (built,), = _answers(
        ("unpack", T, [mint("foo"), 1]), builtins_mod, T)
    assert built == ("foo", 1)


def test_row_12_unpack_refuses_a_string_name(builtins_mod):
    with pytest.raises(LogicException) as exc:
        list(solve(("unpack", Var(), ["foo", 1]), builtins_mod))
    formal = _formal(exc)
    assert formal.functor == "type_error"
    assert formal.args[0] == mint("atom")
    assert formal.args[1] == "foo"          # the culprit is the STRING
    with pytest.raises(LogicException) as exc:
        list(solve(("unpack", Var(), ["foo"]), builtins_mod))
    formal = _formal(exc)
    assert formal.functor == "type_error"
    assert formal.args[0] == mint("atomic")
    assert formal.args[1] == "foo"


def test_row_13_call_takes_an_atom_and_refuses_a_string():
    mod = _load_inline_clausal(
        "_flip_row13",
        "r13_foo(1),\n"
        "r13_call(G, X) <- call(G, X),\n",
    )
    X = Var()
    assert _answers(("r13_call", mint("r13_foo"), X), mod, X) == [(1,)]
    with pytest.raises(LogicException) as exc:
        list(solve(("r13_call", "r13_foo", Var()), mod))
    assert "callable" in str(exc.value)


# ── Rows 14-15: the chars family ────────────────────────────────────────────


def test_row_14_atom_chars_reads_and_builds_atoms(builtins_mod):
    A = Var()
    assert _answers(("atom_chars", A, "hi"), builtins_mod, A) == [(("hi",),)]
    assert len(list(solve(("atom_chars", mint("hi"), "hi"), builtins_mod))) == 1
    with pytest.raises(LogicException) as exc:
        list(solve(("atom_chars", "hi", Var()), builtins_mod))
    assert "atom" in str(exc.value)


def test_row_15_atom_length_refuses_a_string(builtins_mod):
    assert len(list(solve(("atom_length", mint("hi"), 2), builtins_mod))) == 1
    with pytest.raises(LogicException) as exc:
        list(solve(("atom_length", "hi", Var()), builtins_mod))
    assert "atom" in str(exc.value)


# ── Rows 16-17: standard order ──────────────────────────────────────────────


def test_row_16_msort_orders_atom_before_string_before_compound(builtins_mod):
    L = Var()
    items = [mint("b"), "a", 1, ("foo", ("x",)), [mint("z")]]
    (ordered,), = _answers(("msort", items, L), builtins_mod, L)
    assert ordered == [1, mint("b"), "a", [mint("z")], ("foo", ("x",))]


def test_row_17_sort_dedups_a_string_against_its_char_list(builtins_mod):
    L = Var()
    (ordered,), = _answers(
        ("sort", ["ab", [mint("a"), mint("b")]], L), builtins_mod, L)
    assert ordered == ["ab"]


# ── Rows 18-18c: the writers ────────────────────────────────────────────────


def test_row_18_write_and_writeq():
    term = ("foo", ("bar",), "baz")
    assert term_str(term, quoted=False) == "foo(bar, baz)"
    assert term_str(term, quoted=True) == 'foo(bar, "baz")'
    assert term_str(mint("a b"), quoted=True) == "'a b'"
    assert term_str([mint("a"), mint("b")], quoted=True) == '"ab"'


def test_row_18b_write_canonical_prints_the_cons_structure(builtins_mod):
    assert term_canonical("hello") == "'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))"
    assert term_canonical([1, 2]) == "'.'(1,'.'(2,[]))"
    assert term_canonical(("foo", ("a",), "b")) == "foo(a,'.'(b,[]))"
    N, A, T = Var(), Var(), Var()
    assert _answers(("functor", "hello", N, A), builtins_mod, N, A) == [
        ((".",), 2)
    ]
    assert _answers(("arg", 2, "hello", T), builtins_mod, T) == [("ello",)]


def test_row_18c_construction_through_the_name_position_keeps_shapes(
        builtins_mod):
    T = Var()
    (built,), = _answers(
        ("unpack", T, [mint("."), mint("a"), "bc"]), builtins_mod, T)
    assert built == "abc"
    T2 = Var()
    (built2,), = _answers(
        ("unpack", T2, [mint("."), 1, [2]]), builtins_mod, T2)
    assert built2 == [1, 2]
    T3 = Var()
    (built3,), = _answers(("functor", T3, mint("."), 2), builtins_mod, T3)
    # A partial list, never a ``(".", H, T)`` cell (spec §5.4).
    assert not (type(built3) is tuple and built3 and built3[0] == ".")


# ── Rows 19-23: dicts, JSON, boundaries ─────────────────────────────────────


def test_row_19_atom_and_string_dict_keys_are_distinct():
    mod = _load_inline_clausal(
        "_flip_row19",
        "-private([foo])\n"
        "r19_atom_dict({foo: 1}),\n"
        "r19_dot(D, V) <- (V is D.foo),\n",
    )
    from clausal.terms import DictTerm
    D, V = Var(), Var()
    (d,), = _answers(("r19_atom_dict", D), mod, D)
    assert list(d.keys()) == [mint("foo")]
    assert _answers(("r19_dot", d, V), mod, V) == [(1,)]
    assert not unify(d, DictTerm({"foo": 1}), Trail())


def test_row_20_json_parse_makes_atom_keys_and_string_values():
    mod = _load_inline_clausal(
        "_flip_row20",
        "-import_from(py.json, [parse])\n"
        "r20(S, D) <- parse(S, D),\n"
        "r20_atom(X) <- atom(X),\n"
        "r20_string(X) <- string(X),\n",
    )
    D = Var()
    (parsed,), = _answers(("r20", '{"k": "v"}', D), mod, D)
    assert list(parsed.keys()) == [mint("k")]
    assert parsed[mint("k")] == "v"
    assert len(list(solve(("r20_atom", mint("k")), mod))) == 1
    assert len(list(solve(("r20_string", "v"), mod))) == 1


def test_row_21_a_module_attribute_is_the_minted_atom():
    mod = _load_inline_clausal("_flip_row21", "-private([bar])\n")
    assert mod.bar == mint("bar")


def test_row_22_a_text_returning_wrapper_answers_a_string():
    mod = _load_inline_clausal(
        "_flip_row22",
        "-import_from(py.os, [environment_variable])\n"
        "r22(N, V) <- environment_variable(N, V),\n"
        "r22_string(X) <- string(X),\n",
    )
    os.environ["_FLIP_ROW22"] = "home-value"
    try:
        X = Var()
        assert _answers(("r22", "_FLIP_ROW22", X), mod, X) == [("home-value",)]
        assert len(list(solve(("r22_string", "home-value"), mod))) == 1
    finally:
        del os.environ["_FLIP_ROW22"]


def test_row_23_an_atom_crossing_to_python_comes_back_a_string():
    mod = _load_inline_clausal(
        "_flip_row23",
        "-private([bar])\n"
        "r23(X, Y) <- (X is bar, Y is ++X),\n",
    )
    X, Y = Var(), Var()
    (x, y), = _answers(("r23", X, Y), mod, X, Y)
    assert x == mint("bar")
    assert y == "bar" and type(y) is str
    assert x != y


# ── Rows 24-27: the surface ─────────────────────────────────────────────────


def test_row_24_a_double_quoted_functor_is_refused():
    with pytest.raises(SyntaxError) as exc:
        _load_inline_clausal(
            "_flip_row24", "-private([p])\nr24() <- \"foo\"(1),\n")
    assert "functor" in str(exc.value)


def test_row_25_a_single_quoted_functor_is_the_functor():
    mod = _load_inline_clausal(
        "_flip_row25",
        "-private([foo(a1)])\n"
        "r25_probe('foo'(1)),\n",
    )
    X = Var()
    assert _answers(("r25_probe", X), mod, X) == [(("foo", 1),)]


def test_row_26_double_quotes_chars_is_accepted_after_the_flip():
    chars_mod = _load_inline_clausal(
        "_flip_row26_chars",
        "-double_quotes(chars)\n"
        "r26(\"ab\"),\n",
    )
    atom_mod = _load_inline_clausal(
        "_flip_row26_atom",
        "-double_quotes(atom)\n"
        "r26(\"ab\"),\n",
    )
    X = Var()
    assert _answers(("r26", X), chars_mod, X) == [("ab",)]
    assert _answers(("r26", X), atom_mod, X) == [(("ab",),)]


def test_row_27_a_pl_file_loads_its_strings_as_strings(tmp_path):
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    source = prolog_to_clausal('p("ab").\n')
    assert "-double_quotes(chars)" in source
    mod = _load_inline_clausal("_flip_row27", source)
    X = Var()
    assert _answers(("P", X), mod, X) == [("ab",)]


# ── Rows 28-30: reader, bytecode cache, listing ─────────────────────────────


def test_row_28_the_reader_makes_atoms_and_strings():
    from clausal.tools.prolog_ast import PAtom, PString
    from clausal.tools.prolog_reader import transform_term

    cell, _span, _names = transform_term(PAtom("hi"))
    assert cell == ("hi",)
    cell, _span, _names = transform_term(PString("hi"))
    assert cell == "hi"


def test_row_29_the_bytecode_tag_invalidates_a_pre_flip_pyc():
    from clausal.import_hook import CLAUSAL_BYTECODE_TAG
    assert CLAUSAL_BYTECODE_TAG == 9


def test_row_30_listing_takes_an_atom_and_refuses_a_string(capsys):
    mod = _load_inline_clausal(
        "_flip_row30",
        "-private([foo])\n"
        "r30_foo(1),\n"
        "r30_list(P) <- listing(P),\n",
    )
    # ``listing/1`` takes the predicate INDICATOR ``Name/Arity``, whose name
    # half is an atom.
    indicator = ("/", mint("r30_foo"), 1)
    assert len(list(solve(("r30_list", indicator), mod))) == 1
    assert "r30_foo/1" in capsys.readouterr().out
    # ...and the bare ATOM names the /0 predicate of that spelling (§6.4).
    with pytest.raises(LogicException) as exc:
        list(solve(("r30_list", mint("r30_foo")), mod))
    formal = _formal(exc)
    assert formal.functor == "existence_error"      # r30_foo/0, not r30_foo/1
    assert formal.args[0] == mint("procedure")
    capsys.readouterr()
    # A STRING is not a predicate indicator: type_error(predicate, "…").
    with pytest.raises(LogicException) as exc:
        list(solve(("r30_list", "r30_foo"), mod))
    formal = _formal(exc)
    assert formal.functor == "type_error"
    assert formal.args[0] == mint("predicate")
    assert formal.args[1] == "r30_foo"


# ── Carry-forward pins (items Stage A deferred to THE FLIP) ─────────────────


def test_seg_string_iteration_yields_char_atoms():
    """Task 7 carry-forward: ``SegString``'s sequence protocol answers CHAR
    ATOMS — the elements of the list a string denotes."""
    from clausal.terms import SegString
    ss = SegString(["abc"])
    assert list(ss) == [char_atom("a"), char_atom("b"), char_atom("c")]
    assert ss[0] == char_atom("a")
    assert ss[1:] == "bc"          # a slice of a string is a string (R-S2)
    assert char_atom("b") in ss
    assert "b" not in ss           # a one-element STRING is not an element


def test_membership_over_a_plain_str_yields_char_atoms(builtins_mod):
    """Task 7 carry-forward: ``X in "abc"`` binds ``X = ("a",)``."""
    from clausal.logic.runtime.body_star_unify import _in_iter
    assert list(_in_iter("abc", False)) == [
        char_atom("a"), char_atom("b"), char_atom("c")]
    X = Var()
    assert _answers(("in_", X, "abc"), builtins_mod, X) == [
        (char_atom("a"),), (char_atom("b"),), (char_atom("c"),)]


def test_a_promoted_seglist_decodes_back_to_char_atoms():
    """Task 7 re-review carry-forward: ``list_unify``'s SegList branch decodes
    a promoted ``str`` back with ``str_chars``.  That was lossy while two char
    shapes coexisted; with one shape it is exact, so a SegList whose star is
    bound to a cell-char SegList unifies with the plain char list."""
    from clausal.terms import ConcreteSeg, SegList, VarSeg
    trail = Trail()
    inner = Var()
    assert unify(inner, SegList([ConcreteSeg([char_atom("a"),
                                              char_atom("b")])]), trail)
    outer = SegList([VarSeg(inner)])
    out = Var()
    assert unify(out, outer, trail)
    assert _deref_walk(out) == "ab"
    assert unify(outer, [char_atom("a"), char_atom("b")], Trail())


def test_var_head_cons_onto_a_string_unifies_with_the_string(builtins_mod):
    """Task 5 carry-forward: ``T =.. ['.', X, "bc"]`` with ``X`` unbound is a
    partial string; once ``X = a`` it IS ``"abc"`` (row 4/18c)."""
    X, T = Var(), Var()
    for _ in solve(("unpack", T, [mint("."), X, "bc"]), builtins_mod):
        trail = Trail()
        assert unify(X, char_atom("a"), trail)
        assert unify(_deref_walk(T), "abc", trail)
        break
    else:
        raise AssertionError("=.. with a var head produced no solution")


def test_global_atom_guard_mode_compares_two_cells(builtins_mod):
    """Task 5 carry-forward: ``global_atom(foo, foo)`` — guard mode compares
    the pooled atom with the caller's, and both are cells now."""
    A = Var()
    # mint-on-demand registers it…
    (registered,), = _answers(
        ("global_atom", mint("flip_ga_probe"), A), builtins_mod, A)
    assert registered == mint("flip_ga_probe")
    # …and guard mode then compares two CELLS by equality.
    assert len(list(solve(
        ("global_atom", mint("flip_ga_probe"), mint("flip_ga_probe")),
        builtins_mod))) == 1
    # Reverse lookup answers the NAME as an atom.
    N = Var()
    assert _answers(("global_atom", N, mint("flip_ga_probe")),
                    builtins_mod, N) == [(mint("flip_ga_probe"),)]


def test_the_atom_pool_is_compared_by_equality_not_identity():
    """Task 9 carry-forward: the three surviving ``is`` pins on the pool are
    ``==`` now — a freshly minted atom is the same atom as the pooled one."""
    import inspect

    from clausal import import_diagnostics, predicate_diagnostics
    for mod in (import_diagnostics, predicate_diagnostics):
        src = inspect.getsource(mod)
        assert "predicate_builtins.get(name) is value" not in src
