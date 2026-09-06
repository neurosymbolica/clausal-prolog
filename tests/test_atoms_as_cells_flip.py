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
from clausal.logic.variables import Trail, Var, deref, unify
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


# ── Task 12: the Stage A dual-acceptance arms are retired ───────────────────
#
# Stage A kept a bare ``str`` working as an ATOM everywhere so the tree stayed
# green while the cell shape was introduced.  After THE FLIP a ``str`` in one
# of those positions is a STRING, and a string is not a name: each site below
# takes the refusal a string takes everywhere else (§6.4), instead of silently
# reading the spelling.


def test_dispatch_at_refuses_a_string_goal():
    """``predicate._dispatch_at`` accepted a bare ``str`` and built the
    indicator from the spelling.  A string is not callable, and this funnel —
    which the runtime meta-call paths reach — must give the same
    ``type_error(callable, …)`` ``call/N`` and ``solve/1`` already give."""
    from clausal.logic.predicate import _dispatch_at

    with pytest.raises(LogicException) as exc:
        _dispatch_at("t12_str_goal", 1)
    formal = _formal(exc)
    assert formal.functor == "type_error"
    assert formal.args[0] == mint("callable")
    assert formal.args[1] == "t12_str_goal"
    # The ATOM of the same spelling keeps its clean, positioned
    # existence_error — the arm this task leaves in place.
    with pytest.raises(LogicException) as exc:
        _dispatch_at(mint("t12_str_goal"), 1)
    assert _formal(exc).functor == "existence_error"


def test_translate_refuses_a_string_language(builtins_mod):
    """``translate/3``'s *Lang* is an atom read by spelling (§6.4); the Stage A
    arm that took a plain ``str`` as the locale name is gone."""
    with pytest.raises(LogicException) as exc:
        list(solve(("translate", "th", mint("hi"), Var()), builtins_mod))
    formal = _formal(exc)
    assert formal.functor == "type_error"
    assert formal.args[0] == mint("atom")
    assert formal.args[1] == "th"


def test_listing_refuses_a_string_indicator_name(capsys):
    """``io._as_name_arity_indicator`` accepted a plain ``str`` in the NAME
    half of ``Name/Arity``.  The name half is an atom (§6.4); a string there
    is ``type_error(predicate, …)``, the same refusal a bare string gets."""
    from clausal.logic.builtins import get_builtin_dispatch
    from clausal.logic.database import Clause, Database
    from clausal.logic.trampoline import StepGenerator, solutions
    from clausal.terms import Compound

    db = Database()
    db.assertz(Clause(Compound("t12_pt", (Var(), Var())), []))
    dispatch = get_builtin_dispatch("listing", 1, db)

    def _run(val):
        return solutions(
            StepGenerator(dispatch, None, None, None, val, Trail()))

    # The ATOM name half lists the predicate…
    assert len(list(_run(("/", mint("t12_pt"), 2)))) == 1
    assert "t12_pt/2" in capsys.readouterr().out
    # …and the STRING name half is refused, not read as the spelling.
    for shape in (("/", "t12_pt", 2), Compound("/", ("t12_pt", 2))):
        with pytest.raises(LogicException) as exc:
            list(_run(shape))
        formal = exc.value.term.args[0]
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("predicate")


def test_re_pattern_that_is_not_text_raises_type_error():
    """``modules/py/re._compile_pattern`` handed ``re.compile`` the raw term
    when ``to_text`` answered ``None``, so a compound pattern died with a raw
    Python ``TypeError``.  It raises the documented ``type_error(text, …)``
    now, consistently with ``py/sqlite._text``."""
    from clausal.modules.py.re import _compile_pattern

    with pytest.raises(LogicException) as exc:
        _compile_pattern(("t12_pat", 1))
    formal = _formal(exc)
    assert formal.functor == "type_error"
    assert formal.args[0] == mint("text")
    assert formal.args[1] == ("t12_pat", 1)


def test_vary_and_extend_refuse_a_malformed_field_key(builtins_mod):
    """``keyword_ops._field_keys`` answered ``None`` for a key that is neither
    an atom nor an identifier spelling, and both callers turned that into a
    silent failure.  A malformed key is ``type_error(atom, Key, …)``."""
    for goal_name in ("vary", "extend"):
        with pytest.raises(LogicException) as exc:
            list(solve((goal_name, {1: 2}, mint("t12_term"), Var()),
                       builtins_mod))
        formal = _formal(exc)
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("atom")
        assert formal.args[1] == 1
        assert f"{goal_name}/3" in exc.value.term.args[1]


def test_vary_and_extend_report_an_unbound_field_key_as_uninstantiated(
    builtins_mod,
):
    """Fix round 1: an UNBOUND key is the instantiation fault, not the type
    fault.  ``type_error(atom, _G12)`` read as "a variable is the wrong SORT
    of term here" when the term is right and only the binding is missing —
    the same split ``listing/1`` makes for an unfinished indicator."""
    for goal_name in ("vary", "extend"):
        with pytest.raises(LogicException) as exc:
            list(solve((goal_name, {Var(): 2}, mint("t12_term"), Var()),
                       builtins_mod))
        assert _formal(exc) == mint("instantiation_error")
        assert exc.value.term.args[1] == f"{goal_name}/3"


_PREDICATE_MODULE = "clausal.logic.predicate"


def _offender_name(offender: str) -> str:
    """The basename out of an ``_class_test_offenders`` entry."""
    import pathlib
    return pathlib.Path(offender.split(":")[0]).name


def _dotted_package(path, repo_root):
    """The dotted package *path*'s relative imports resolve against.

    A module's relative imports are rooted at its PACKAGE, so the module name
    is dropped — which is also right for ``__init__.py``, since that file IS
    its package and ``from . import x`` there means the same directory.
    """
    parts = path.resolve().relative_to(repo_root.resolve()).with_suffix("").parts
    return parts[:-1]


def _import_from_module(node, package_parts):
    """The absolute dotted module an ``ImportFrom`` names, relative or not."""
    if not node.level:
        return node.module or ""
    # ``from .x import`` (level 1) resolves against the package itself;
    # each extra dot drops one more trailing component.
    base = list(package_parts[: len(package_parts) - (node.level - 1)])
    if node.module:
        base += node.module.split(".")
    return ".".join(base)


def _class_test_offenders(root, repo_root, skip):
    """Every place under *root* that reaches the CLASS test as ``is_atom``.

    Three spellings are covered, because all three would silently resolve
    through the deprecated alias:

    * ``from clausal.logic.predicate import is_atom`` (absolute),
    * ``from ..predicate import is_atom`` (relative — resolved here, since
      ``node.module`` is only the tail for a relative import), and
    * ``predicate.is_atom(...)`` / ``P.is_atom`` attribute access on any name
      bound to the predicate MODULE in that file.
    """
    import ast

    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path.resolve() in skip:
            continue
        package_parts = _dotted_package(path, repo_root)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_aliases = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = _import_from_module(node, package_parts)
                for alias in node.names:
                    # ``from clausal.logic import predicate`` binds the MODULE.
                    if (f"{module}.{alias.name}" == _PREDICATE_MODULE
                            and not node.level):
                        module_aliases.add(alias.asname or alias.name)
                    if module == _PREDICATE_MODULE and alias.name == "is_atom":
                        offenders.append(f"{path}:{node.lineno}: import")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name != _PREDICATE_MODULE:
                        continue
                    # ``import clausal.logic.predicate`` (no asname) binds
                    # ``clausal``; only the aliased form binds a usable name.
                    if alias.asname:
                        module_aliases.add(alias.asname)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == "is_atom"
                    and isinstance(node.value, ast.Name)
                    and node.value.id in module_aliases):
                offenders.append(f"{path}:{node.lineno}: attribute")
    return offenders


def test_the_zero_field_class_test_is_named_is_zero_field_class():
    """``predicate.is_atom`` was the zero-field-CLASS test while
    ``atoms.is_atom`` is the TERM test — one stem, two questions.  The class
    test is ``is_zero_field_class`` now; ``is_atom`` survives in
    ``predicate.py`` only as a deprecated alias for the C symbol.

    The guard below walks the AST of every ``*.py`` under BOTH ``clausal/``
    and ``tests/`` (fix round 1: scanning only the package let
    ``tests/test_funnel_accessors.py`` keep importing the old name) and fails
    on any of the three ways the class test can be reached under that name:
    an absolute import, a relative one, or attribute access on a name bound
    to the predicate module.  Two files are exempt and named explicitly —
    ``predicate.py``, which DEFINES the alias, and this file, which must
    mention it to assert it still exists."""
    import pathlib

    from clausal.logic import predicate
    from clausal.logic.atoms import is_atom as term_is_atom
    from clausal.logic.predicate import make_predicate

    assert predicate.is_zero_field_class is predicate.is_atom
    assert predicate.is_zero_field_class(make_predicate("t12_zero", []))
    assert not predicate.is_zero_field_class(mint("t12_zero"))
    # The TERM test keeps the plain name.
    assert term_is_atom(mint("t12_zero"))

    definition = pathlib.Path(predicate.__file__).resolve()
    package_root = definition.parent.parent          # clausal/
    repo_root = package_root.parent
    tests_root = repo_root / "tests"
    assert tests_root.is_dir(), tests_root           # the root must exist
    skip = {definition, pathlib.Path(__file__).resolve()}

    offenders = (_class_test_offenders(package_root, repo_root, skip)
                 + _class_test_offenders(tests_root, repo_root, skip))
    assert offenders == []


def test_the_class_test_pin_actually_bites(tmp_path):
    """The guard above is only worth having if it catches all three spellings
    — fix round 1 found it silently passing on a live offender it could not
    see.  Feed it each spelling and check it reports it."""
    pkg = tmp_path / "clausal" / "logic"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "absolute.py").write_text(
        "from clausal.logic.predicate import is_atom\n", encoding="utf-8")
    (pkg / "relative.py").write_text(
        "from .predicate import is_atom\n", encoding="utf-8")
    (pkg / "relative_up.py").write_text(
        "from ..logic.predicate import is_atom\n", encoding="utf-8")
    (pkg / "attribute.py").write_text(
        "from clausal.logic import predicate\n"
        "def f(x):\n"
        "    return predicate.is_atom(x)\n", encoding="utf-8")
    (pkg / "clean.py").write_text(
        "from clausal.logic.predicate import is_zero_field_class\n"
        "from clausal.logic.atoms import is_atom\n"
        "def f(x):\n"
        "    return is_atom(x) or is_zero_field_class(x)\n", encoding="utf-8")

    found = _class_test_offenders(tmp_path / "clausal", tmp_path, skip=set())
    assert {_offender_name(f) for f in found} == {
        "absolute.py", "relative.py", "relative_up.py", "attribute.py",
    }
    # ...and the clean file, which uses BOTH names correctly, is not reported.
    assert "clean.py" not in {_offender_name(f) for f in found}


# ── Task 12b: the flip-gap sweep — the sites the flip's sweep did not reach ──
#
# Task 12's census turned up families of site that still read a plain ``str``
# as a NAME.  Unlike the Stage A arms above they were the ONLY arm, so the
# suite was green on the wrong side: a source-written atom — which is what
# every one of these positions actually receives now — failed silently or was
# rendered as a Python tuple repr.  Each family below reads the ATOM and
# refuses the string (§6.4), or crosses text through ``to_text`` (§9.4).


def test_sum_and_scalar_product_read_the_operator_as_an_atom():
    """``sum_/3`` and ``scalar_product/4`` take an ISO operator ATOM.

    ``#=`` cannot be written bare in the surface (``#`` opens a comment), so
    source spells it ``"#="``, which in the default ``-double_quotes(atom)``
    mode is the atom ``("#=",)``.  ``clpfd`` gated on ``isinstance(op, str)``,
    so every source-written call failed silently.
    """
    mod = _load_inline_clausal(
        "_t12b_clpfd",
        's_eq(N) <- sum_([1, 2, 3], "#=", N),\n'
        's_lt() <- sum_([1, 2, 3], "#<", 10),\n'
        's_lt_fails() <- sum_([1, 2, 3], "#<", 5),\n'
        'sp(N) <- scalar_product([2, 3], [4, 5], "#=", N),\n',
    )
    N = Var()
    assert _answers(("s_eq", N), mod, N) == [(6,)]
    assert len(list(solve(("s_lt",), mod))) == 1
    assert list(solve(("s_lt_fails",), mod)) == []
    assert _answers(("sp", N), mod, N) == [(23,)]


def test_sum_and_scalar_product_refuse_a_string_operator(builtins_mod):
    """A STRING in the operator position is not a name (§6.4) — and silence
    is what hid this whole family, so it is a refusal, not a failure."""
    for goal in (("sum_", [1, 2, 3], "#=", 6),
                 ("scalar_product", [2, 3], [4, 5], "#=", 23)):
        with pytest.raises(LogicException) as exc:
            list(solve(goal, builtins_mod))
        formal = _formal(exc)
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("atom")
        assert formal.args[1] == "#="


def test_zcompare_binds_an_atom_and_reads_one():
    """``zcompare/3``'s Order is the ISO order atom ``<``/``=``/``>``.  It
    bound the plain ``str`` ``'<'`` — a STRING after THE FLIP — so a source
    program could never compare the answer against the atom it wrote."""
    from clausal.logic.clpfd import (
        FD_KEY, domain_max, domain_min, in_domain, zcompare,
    )
    from clausal.logic.variables import get_attr as _get_attr

    for x, y, expected in ((1, 5, "<"), (5, 1, ">"), (3, 3, "=")):
        trail = Trail()
        order = Var()
        assert zcompare(order, x, y, trail)
        assert deref(order) == mint(expected)

    # A ground ATOM order narrows the operands…
    trail = Trail()
    a, b = Var(), Var()
    assert in_domain([a, b], 1, 5, trail)
    assert zcompare(mint("<"), a, b, trail)
    assert domain_max(_get_attr(a, FD_KEY).domain) <= 4
    assert domain_min(_get_attr(b, FD_KEY).domain) >= 2
    # A ground ATOM order against ground operands is CHECKED, not just bound.
    assert zcompare(mint("<"), 1, 5, Trail())
    assert not zcompare(mint(">"), 1, 5, Trail())

    # …and a STRING order is refused rather than read as the spelling — in
    # BOTH shapes.  Fix round 1: the ground/ground fast path ran before the
    # Order was validated, so ``zcompare("<", 1, 5)`` merely failed (the
    # string does not unify with the order atom) while ``zcompare("<", X, Y)``
    # raised — the same mistake got two different answers depending on the
    # operands.
    for shape in ((Var(), Var()), (1, 5)):
        with pytest.raises(LogicException) as exc:
            zcompare("<", shape[0], shape[1], Trail())
        formal = _formal(exc)
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("atom")
        assert formal.args[1] == "<"


def test_attribute_keys_are_atoms():
    """``put_attr/3``/``get_attr/3``/``del_attr/2`` gated the Key on
    ``isinstance(key, str)``, so a source-written key — an atom — silently
    failed.  Keys are atoms, stored by their spelling."""
    mod = _load_inline_clausal(
        "_t12b_attrs",
        "-private([t12b_key])\n"
        "roundtrip(OUT) <- (put_attr(X, t12b_key, 7), "
        "get_attr(X, t12b_key, OUT)),\n"
        "attached() <- (put_attr(X, t12b_key, 7), attvar(X)),\n"
        "deleted() <- (put_attr(X, t12b_key, 7), del_attr(X, t12b_key), "
        "not (attvar(X))),\n"
    )
    OUT = Var()
    assert _answers(("roundtrip", OUT), mod, OUT) == [(7,)]
    assert len(list(solve(("attached",), mod))) == 1
    assert len(list(solve(("deleted",), mod))) == 1


def test_a_string_attribute_key_is_refused(builtins_mod):
    """A string is not a name, here as everywhere else (§6.4)."""
    for goal in (("put_attr", Var(), "t12b_str_key", 1),
                 ("get_attr", Var(), "t12b_str_key", Var()),
                 ("del_attr", Var(), "t12b_str_key"),
                 ("put_attrs", Var(), {"t12b_str_key": 1})):
        with pytest.raises(LogicException) as exc:
            list(solve(goal, builtins_mod))
        formal = _formal(exc)
        assert formal.functor == "type_error"
        assert formal.args[0] == mint("atom")
        assert formal.args[1] == "t12b_str_key"


def test_bulk_attributes_round_trip_through_atom_keys():
    """``get_attrs/2`` hands the key half of each pair back, so it mints —
    otherwise ``get_attrs(V, D), put_attrs(W, D)`` would build a dict
    ``put_attrs/2`` then refuses."""
    from clausal.logic.builtins.attributes import _get_attrs__2, _put_attrs__2
    from clausal.terms import DictTerm

    trail = Trail()
    src, dst, out = Var(), Var(), Var()
    assert list(_put_attrs__2(
        src, DictTerm({mint("t12b_a"): 1, mint("t12b_b"): 2}), trail, None,
    )) == [None]
    assert list(_get_attrs__2(src, out, trail, None)) == [None]
    attrs = deref(out)
    assert attrs.data == {mint("t12b_a"): 1, mint("t12b_b"): 2}
    # The round trip closes: what came out goes back in.
    assert list(_put_attrs__2(dst, attrs, trail, None)) == [None]


# ── Task 12c: the result-dict KEY EMISSION sweep ─────────────────────────────
#
# Task 12b fixed how a wrapper READS a dict written in source (§2a of its
# report).  The mirror half was left open and recorded as its residual 1: a
# wrapper that BUILDS a dict for source to consume still keyed it with plain
# ``str``.  Spec §6.8 makes atom and string keys distinct, so ``R.stdout`` on
# such a result raises ``existence_error(dict_key, stdout)`` and
# ``get(R, stdout, V)`` fails silently — the answer was unreadable by the very
# syntax the docs show.  §9.2 already rules the JSON half (object keys →
# atoms); these rows extend that reading to every wrapper result dict, and to
# the NAME positions a status answer occupies (§6.4).


def test_process_create_answers_an_atom_keyed_result_dict():
    """``process_create/3,4`` answers ``{exit_code, stdout, stderr}``; a
    source program reads it with ``R.stdout``, which looks up ``("stdout",)``."""
    mod = _load_inline_clausal(
        "_t12c_process",
        "-import_from(py.process, [process_create])\n"
        "-private([exit_code, stdout, stderr, input])\n"
        "run3(OUT, CODE) <- (process_create(\"echo\", [\"t12c\"], R), "
        "OUT is R.stdout, CODE is R.exit_code),\n"
        "run4(OUT) <- (process_create(\"cat\", [], {input: \"t12c stdin\"}, R), "
        "OUT is R.stdout),\n"
        "err3(ERR) <- (process_create(\"cat\", [\"/nonexistent/t12c\"], R), "
        "ERR is R.stderr),\n"
    )
    OUT, CODE = Var(), Var()
    (out, code), = _answers(("run3", OUT, CODE), mod, OUT, CODE)
    assert out.strip() == "t12c" and code == 0
    OUT = Var()
    assert _answers(("run4", OUT), mod, OUT) == [("t12c stdin",)]
    ERR = Var()
    (err,), = _answers(("err3", ERR), mod, ERR)
    assert "t12c" in err


def test_url_parse_answers_an_atom_keyed_dict_that_join_reads_back():
    """``py.url.parse/2`` builds the parts dict and ``join/2`` consumes one:
    both halves have to agree on what a key is, or the documented round trip
    silently produces an empty URL."""
    mod = _load_inline_clausal(
        "_t12c_url",
        "-double_quotes(chars)\n"
        "-import_from(py.url, [parse, join])\n"
        "-private([scheme, host, port, path])\n"
        "scheme_of(S) <- (parse(\"https://example.com:8080/p?q=1\", P), "
        "S is P.scheme),\n"
        "port_of(N) <- (parse(\"https://example.com:8080/p?q=1\", P), "
        "N is P.port),\n"
        "round_trip(U) <- (parse(\"https://example.com:8080/p?q=1\", P), "
        "join(P, U)),\n"
    )
    S, N, U = Var(), Var(), Var()
    # The VALUE stays text (§9.4); only the KEY is an atom.
    assert _answers(("scheme_of", S), mod, S) == [("https",)]
    assert _answers(("port_of", N), mod, N) == [(8080,)]
    assert _answers(("round_trip", U), mod, U) == [
        ("https://example.com:8080/p?q=1",)]


def test_csv_records_answer_atom_keyed_dicts_and_atom_headers():
    """A CSV header cell is DATA, and §9.2's precedent (JSON object keys →
    atoms) governs data-derived keys too.  The ``Headers`` answer names the
    same columns, so it mints as well — otherwise ``member(H, Headers),
    get(R, H, V)`` fails against the wrapper's own records."""
    mod = _load_inline_clausal(
        "_t12c_csv",
        "-double_quotes(chars)\n"
        "-import_from(py.csv, [parse_records, generate_records])\n"
        "-private([name, age])\n"
        "first_name(N) <- (parse_records(\"name,age\\nalice,30\\n\", _, RS), "
        "RS is [R, *_], N is R.name),\n"
        "headers(H) <- (parse_records(\"name,age\\nalice,30\\n\", H, _)),\n"
        "by_header(V) <- (parse_records(\"name,age\\nalice,30\\n\", H, RS), "
        "H is [K, *_], RS is [R, *_], get(R, K, V)),\n"
        "regenerated(S) <- (parse_records(\"name,age\\nalice,30\\n\", H, RS), "
        "generate_records(H, RS, S)),\n"
    )
    N, H, V, S = Var(), Var(), Var(), Var()
    assert _answers(("first_name", N), mod, N) == [("alice",)]
    assert _answers(("headers", H), mod, H) == [([mint("name"), mint("age")],)]
    assert _answers(("by_header", V), mod, V) == [("alice",)]
    # The round trip closes: what parse_records answered, generate_records
    # writes back out — atom headers and atom record keys included.
    assert _answers(("regenerated", S), mod, S) == [("name,age\r\nalice,30\r\n",)]


def test_z3_satisfiability_answers_an_atom():
    """``z3.satisfiability(R)`` answers a status NAME (§6.4), not text."""
    pytest.importorskip("z3")
    from clausal.logic.clpz3 import in_z3, z3_eq, z3_is_sat

    trail = Trail()
    x = Var()
    assert in_z3(x, 1, 10, trail)
    r = Var()
    assert z3_is_sat(r, trail)
    assert deref(r) == mint("sat")

    trail = Trail()
    y = Var()
    assert in_z3(y, 1, 5, trail)
    assert z3_eq(y, 10, trail)
    r = Var()
    assert z3_is_sat(r, trail)
    assert deref(r) == mint("unsat")
