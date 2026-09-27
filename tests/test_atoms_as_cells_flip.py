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
from clausal.logic.atoms import char_atom, is_atom, mint
from clausal.logic.cells import chars, chars_text, is_chars
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve, _deref_walk
from clausal.logic.variables import Trail, Var, deref, unify
from clausal import cell_args, cell_functor
from clausal.terms import Compound, term_canonical, term_str
from clausal.modules.py.datetime import _dt_to_term as _T
from clausal.modules.py.datetime import _term_to_dt as _P  # py datetime -> its TERM


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
    return cell_args(exc_info.value.term)[0]


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
    assert _answers(("r1_bare", X), mod, X) == [("bar",)]
    assert _answers(("r1_quoted", X), mod, X) == [("bar",)]
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
    assert _answers(("r2", X), mod, X) == [(("$chars", "bar"),)]   # stage 1: the chars CARRIER
    assert list(solve(("r2_atom", chars("bar")), mod)) == []
    assert len(list(solve(("r2_string", chars("bar")), mod))) == 1
    assert len(list(solve(("r2_is_list", chars("bar")), mod))) == 1


def test_row_03_atom_equals_quoted_atom_but_not_a_string():
    mod = _load_inline_clausal(
        "_flip_row03",
        "-double_quotes(chars)\n"
        "-private([bar])\n"
        "r3_same() <- (bar is 'bar'),\n"
        "r3_string() <- (bar is \"bar\"),\n"
        "r3_value(bar),\n",
    )
    assert len(list(solve("r3_same", mod))) == 1
    assert list(solve("r3_string", mod)) == []
    X = Var()
    # ``bar == "bar"`` seen from Python (stage 2: an atom is the str).
    assert _answers(("r3_value", X), mod, X) == [("bar",)]


def test_row_04_a_string_unifies_with_its_char_list():
    mod = _load_inline_clausal(
        "_flip_row04",
        "-double_quotes(chars)\n"
        "-private([a, b, c])\n"
        "r4() <- (\"abc\" is [a, b, c]),\n",
    )
    assert len(list(solve("r4", mod))) == 1
    # …and directly, both orientations.
    assert unify(chars("abc"), [mint("a"), mint("b"), mint("c")], Trail())
    assert unify([mint("a"), mint("b"), mint("c")], chars("abc"), Trail())


def test_row_05_a_string_destructures_head_and_tail():
    mod = _load_inline_clausal(
        "_flip_row05",
        "-double_quotes(chars)\n"
        "r5([H, *T], H, T),\n"
        "r5_string(X) <- string(X),\n",
    )
    H, T = Var(), Var()
    assert _answers(("r5", chars("abc"), H, T), mod, H, T) == [(("a", chars("bc")))]
    assert len(list(solve(("r5_string", chars("bc")), mod))) == 1


def test_row_06_the_empty_string_is_the_empty_list():
    from clausal.logic.builtins._helpers import _standard_order_key

    assert unify(chars(""), [], Trail())
    assert _standard_order_key(chars("")) == _standard_order_key([])


# ── Rows 7-12: the name position ────────────────────────────────────────────


def test_row_07_functor_of_a_cell_answers_an_atom(builtins_mod):
    N, A = Var(), Var()
    assert _answers(
        ("functor", ("foo", "a"), N, A), builtins_mod, N, A
    ) == [("foo", 1)]
    assert len(list(solve(("atom", "foo"), builtins_mod))) == 1


def test_row_08_functor_constructs_a_cell(builtins_mod):
    T = Var()
    (built,), = _answers(("functor", T, mint("foo"), 2), builtins_mod, T)
    assert type(built) is tuple and built[0] == "foo" and len(built) == 3


def test_row_09_functor_refuses_a_string_name(builtins_mod):
    with pytest.raises(LogicException) as exc:
        list(solve(("functor", Var(), chars("foo"), 1), builtins_mod))
    assert "atomic" in str(exc.value)


def test_row_10_unpack_answers_the_atom_name(builtins_mod):
    L = Var()
    (parts,), = _answers(
        ("unpack", ("foo", "a", chars("b")), L), builtins_mod, L)
    assert parts == [mint("foo"), mint("a"), chars("b")]
    # ``L = [foo, a, [b]]`` is the same answer, spelled as a char list.
    assert unify(parts, [mint("foo"), mint("a"), [char_atom("b")]], Trail())


def test_row_11_unpack_constructs_a_cell(builtins_mod):
    T = Var()
    (built,), = _answers(
        ("unpack", T, [mint("foo"), 1]), builtins_mod, T)
    assert built == ("foo", 1)


def test_row_12_unpack_refuses_a_string_name(builtins_mod):
    with pytest.raises(LogicException) as exc:
        list(solve(("unpack", Var(), [chars("foo"), 1]), builtins_mod))
    formal = _formal(exc)
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal)[0] == mint("atom")
    assert cell_args(formal)[1] == chars("foo")   # the culprit is the STRING
    with pytest.raises(LogicException) as exc:
        list(solve(("unpack", Var(), [chars("foo")]), builtins_mod))
    formal = _formal(exc)
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal)[0] == mint("atomic")
    assert cell_args(formal)[1] == chars("foo")


def test_row_13_call_takes_an_atom_and_a_string_goal_has_no_procedure():
    """Task 15 item 3 (RULED 2026-09-07): a string goal is the compound
    ``'.'(f, …)``, so it IS callable (§6.3) and the error is that no
    procedure ``'.'/2`` exists — an ``existence_error``, not a
    ``type_error(callable, …)``.  Scryer answers ``existence_error(procedure,
    './3')`` for ``call("foo", X)``; a ``type_error(callable, …)`` beside a
    true ``callable("foo")`` would contradict itself."""
    mod = _load_inline_clausal(
        "_flip_row13",
        "r13_foo(1),\n"
        "r13_call(G, X) <- call(G, X),\n",
    )
    X = Var()
    assert _answers(("r13_call", mint("r13_foo"), X), mod, X) == [(1,)]
    with pytest.raises(LogicException) as exc:
        list(solve(("r13_call", chars("r13_foo"), Var()), mod))
    formal = _formal(exc)
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[0] == mint("procedure")
    # call/2 folds one extra argument onto the ``'.'/2`` goal, as Scryer does.
    assert cell_args(formal)[1] == ("/", mint("."), 3)


def test_row_13b_a_string_goal_in_solve_has_no_procedure(builtins_mod):
    with pytest.raises(LogicException) as exc:
        list(solve(chars("r13_nope"), builtins_mod))
    formal = _formal(exc)
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[0] == mint("procedure")
    assert cell_args(formal)[1] == ("/", mint("."), 2)
    assert "solve/1" in exc.value.message


def test_row_13c_the_empty_string_goal_names_the_nil_atom(builtins_mod):
    """``""`` is ``[]``, the ATOM ``'[]'``, so the missing procedure is
    ``'[]'/0`` — Scryer's answer for ``call([])`` and ``call("")``."""
    with pytest.raises(LogicException) as exc:
        list(solve(chars(""), builtins_mod))
    formal = _formal(exc)
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[1] == ("/", mint("[]"), 0)


# ── Rows 14-15: the chars family ────────────────────────────────────────────


def test_row_14_atom_chars_reads_and_builds_atoms(builtins_mod):
    A = Var()
    assert _answers(("atom_chars", A, chars("hi")), builtins_mod, A) == [("hi",)]
    assert len(list(solve(("atom_chars", mint("hi"), chars("hi")), builtins_mod))) == 1
    with pytest.raises(LogicException) as exc:
        list(solve(("atom_chars", chars("hi"), Var()), builtins_mod))
    assert "atom" in str(exc.value)


def test_row_15_atom_length_refuses_a_string(builtins_mod):
    assert len(list(solve(("atom_length", mint("hi"), 2), builtins_mod))) == 1
    with pytest.raises(LogicException) as exc:
        list(solve(("atom_length", chars("hi"), Var()), builtins_mod))
    assert "atom" in str(exc.value)


# ── Rows 16-17: standard order ──────────────────────────────────────────────


def test_row_16_msort_orders_lists_and_strings_as_cons_compounds(builtins_mod):
    """Task 15 item 1 (ISO 7.2.1, Scryer ``compare/3``): a list and a string
    are the ``'.'/2`` compound, so they sort by ARITY among the compounds --
    after the arity-1 ``foo(x)``, and among themselves by name ``.`` then by
    elements."""
    L = Var()
    items = [mint("b"), chars("a"), 1, ("foo", "x"), [mint("z")]]
    (ordered,), = _answers(("msort", items, L), builtins_mod, L)
    assert ordered == [1, mint("b"), ("foo", "x"), chars("a"), [mint("z")]]


def test_row_17_sort_dedups_a_string_against_its_char_list(builtins_mod):
    L = Var()
    (ordered,), = _answers(
        ("sort", [chars("ab"), [mint("a"), mint("b")]], L), builtins_mod, L)
    assert ordered == [chars("ab")]


# ── Rows 18-18c: the writers ────────────────────────────────────────────────


def test_row_18_write_and_writeq():
    term = ("foo", "bar", chars("baz"))
    assert term_str(term, quoted=False) == "foo(bar, baz)"
    assert term_str(term, quoted=True) == 'foo(bar, "baz")'
    assert term_str(mint("a b"), quoted=True) == "'a b'"
    assert term_str([mint("a"), mint("b")], quoted=True) == '"ab"'


def test_row_18b_write_canonical_prints_the_cons_structure(builtins_mod):
    assert term_canonical(chars("hello")) == "'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))"
    assert term_canonical([1, 2]) == "'.'(1,'.'(2,[]))"
    assert term_canonical(("foo", "a", chars("b"))) == "foo(a,'.'(b,[]))"
    N, A, T = Var(), Var(), Var()
    assert _answers(("functor", chars("hello"), N, A), builtins_mod, N, A) == [
        (".", 2)
    ]
    assert _answers(("arg", 2, chars("hello"), T), builtins_mod, T) == [(chars("ello"),)]


def test_row_18c_construction_through_the_name_position_keeps_shapes(
        builtins_mod):
    T = Var()
    (built,), = _answers(
        ("unpack", T, [mint("."), mint("a"), chars("bc")]), builtins_mod, T)
    assert built == chars("abc")
    T2 = Var()
    (built2,), = _answers(
        ("unpack", T2, [mint("."), 1, [2]]), builtins_mod, T2)
    assert built2 == [1, 2]
    T3 = Var()
    (built3,), = _answers(("functor", T3, mint("."), 2), builtins_mod, T3)
    # A partial list, never a ``(".", H, T)`` cell (spec §5.4).
    assert not (type(built3) is tuple and built3 and built3[0] == ".")


def test_row_18d_write_of_the_empty_string_prints_the_empty_list(capsys):
    """``write("")`` prints ``[]`` (spec §6.7's ``""``/``[]`` row; Scryer).

    ``""`` and ``[]`` are one term, so no writer may render them
    differently: ``write("")`` printing nothing while ``write([])``
    printed ``[]`` was the last place the ``str`` REPRESENTATION leaked
    into an answer.  Task 15 item 4 as amended adds the TEXT family to the
    writers that have to agree.
    """
    from clausal.logic.builtins.io import _format_term_as_text

    assert term_str(chars(""), quoted=False) == "[]"
    assert term_str(chars(""), quoted=True) == "[]"
    assert term_str(chars(""), double_quotes=False) == "[]"
    assert _format_term_as_text(chars("")) == "[]"

    mod = _load_inline_clausal("_flip_row18d", "-double_quotes(chars)\n")
    list(solve(("write", chars("")), mod))
    list(solve(("write", []), mod))
    list(solve(("write_text", chars("")), mod))
    list(solve(("writeq", chars("")), mod))
    assert capsys.readouterr().out == "[][][][]"


# ── The string/1 family answers for the TERM ────────────────────────────────


def _string_answers(mod, value):
    """``(string(V), is_str(V))`` for one *value* — the two must agree."""
    return (
        bool(list(solve(("string", value), mod))),
        bool(list(solve(("is_str", value), mod))),
    )


def test_string_holds_for_every_spelling_of_a_string(builtins_mod):
    """``string/1``/``is_str/1`` answer for the TERM, not the storage.

    ``""`` and ``[]`` are one term and so are ``"ab"`` and
    ``['a', 'b']`` (spec §6.3's ``""``/``[]`` column), so the check cannot
    key on the ``str`` representation.  A list with a non-char element is
    not a string; nor is an atom, a cell or a number.
    """
    from clausal.terms import SegString

    for value in (chars("bar"), chars(""), [], [mint("a"), mint("b")], [mint("a")]):
        assert _string_answers(builtins_mod, value) == (True, True), value

    for value in ([1, 2], [mint("a"), 1], [mint("ab")], mint("bar"),
                  ("f", 1), 42, b"ab"):
        assert _string_answers(builtins_mod, value) == (False, False), value

    # A ground SegString is a string; a non-ground one is not.  A Seg* cannot
    # be compiled into a goal's argument list, so these two go through
    # ``call`` (the runtime entry the audit suite uses for Seg* rows).
    from clausal.logic.solve import call
    from clausal.terms import VarSeg

    for name in ("string", "is_str"):
        assert any(True for _ in call(name, SegString(["ab"]),
                                      module=builtins_mod))
        assert not any(True for _ in call(name, SegString(["a", VarSeg(Var())]),
                                          module=builtins_mod))


def test_must_be_string_agrees_with_the_string_builtin(builtins_mod):
    """``must_be(string, X)`` and ``string(X)`` cannot drift apart."""
    assert list(solve(("must_be", mint("string"), [mint("a"), mint("b")]),
                      builtins_mod))
    assert list(solve(("must_be", mint("str"), []), builtins_mod))
    with pytest.raises(LogicException) as exc_info:
        list(solve(("must_be", mint("string"), [1, 2]), builtins_mod))
    assert cell_args(_formal(exc_info))[0] == mint("string")


# ── Task 15 item 2: the ISO type table for [] and for lists (§6.3) ──────────


def _holds(mod, pred, value):
    return bool(list(solve((pred, value), mod)))


class TestEmptyListIsTheAtomNil:
    """``[]`` is the ATOM ``'[]'`` (ISO; Scryer 0.10.0 verified), and ``""``
    and ``b""`` are the same term, so all three answer alike."""

    def test_atom_and_atomic_hold_for_every_spelling_of_nil(self, builtins_mod):
        for value in ([], chars(""), b""):
            assert _holds(builtins_mod, "atom", value), value
            assert _holds(builtins_mod, "atomic", value), value

    def test_nil_is_not_compound(self, builtins_mod):
        for value in ([], chars(""), b""):
            assert not _holds(builtins_mod, "compound", value), value

    def test_nil_is_callable(self, builtins_mod):
        for value in ([], chars(""), b""):
            assert _holds(builtins_mod, "callable_", value), value

    def test_must_be_agrees_with_the_builtins(self, builtins_mod):
        assert list(solve(("must_be", mint("atom"), []), builtins_mod))
        assert list(solve(("must_be", mint("callable"), []), builtins_mod))
        # Fix round 1, item 6: the ``atomic`` row the table was missing --
        # ``must_be(atomic, [])`` used to be domain_error(type, atomic)
        # while ``atomic([])`` succeeded.
        assert list(solve(("must_be", mint("atomic"), []), builtins_mod))
        assert list(solve(("must_be", mint("atomic"), mint("bar")),
                          builtins_mod))
        assert list(solve(("must_be", mint("atomic"), 42), builtins_mod))
        for culprit in (chars("abc"), [1, 2], b"ab", ("f", 1)):
            with pytest.raises(LogicException) as exc:
                list(solve(("must_be", mint("atomic"), culprit), builtins_mod))
            assert cell_args(_formal(exc))[0] == mint("atomic"), culprit
        with pytest.raises(LogicException):
            list(solve(("must_be", mint("compound"), []), builtins_mod))

    def test_the_nil_atom_canonicalises_to_the_empty_list(self, builtins_mod):
        """Fix round 1, item 2 (operator-ruled): in ISO ``'[]'`` IS ``[]``,
        and Scryer round-trips it -- ``atom_chars(X, ['[',']'])`` gives
        ``X = []``, ``T =.. [[]]`` gives ``T = []``, ``functor(T, [], 0)``
        gives ``T = []``, ``atom_concat('[', ']', X)`` gives ``X = []``.  So
        ``mint("[]")`` is the empty list, not a ``("[]",)`` cell that would
        compare unequal to the list it denotes."""
        assert mint("[]") == []
        X = Var()
        assert _answers(("atom_chars", X, [char_atom("["), char_atom("]")]),
                        builtins_mod, X) == [([],)]
        T = Var()
        assert _answers(("unpack", T, [[]]), builtins_mod, T) == [([],)]
        F = Var()
        assert _answers(("functor", F, [], 0), builtins_mod, F) == [([],)]
        C = Var()
        assert _answers(("atom_concat", char_atom("["), char_atom("]"), C),
                        builtins_mod, C) == [([],)]
        # …and above arity 0 the name is an ordinary functor spelled ``[]``:
        # Scryer answers ``T =.. [[], a]`` with ``[](a)``.
        T2 = Var()
        assert _answers(("unpack", T2, [[], mint("a")]),
                        builtins_mod, T2) == [(("[]", mint("a")),)]

    def test_sort_keeps_one_element_for_nil_and_the_nil_atom(self, builtins_mod):
        """The point of the canonicalisation: ``[]`` and ``'[]'`` are ONE
        term, so ``sort/2`` legitimately keeps one element."""
        L = Var()
        assert _answers(("sort", [[], mint("[]")], L), builtins_mod, L) == [
            ([[]],)
        ]

    def test_spelling_of_the_empty_list_is_the_two_brackets(self):
        from clausal.logic.atoms import spelling
        for nil in ([], chars(""), b"", ()):
            assert spelling(nil) == "[]", nil

    def test_calling_the_nil_atom_raises_in_every_spelling(self, builtins_mod):
        """Fix round 2, item 4: ``call("")`` raised while ``call([])`` failed
        silently, for one and the same term.  One term, one answer."""
        from clausal.logic.solve import call
        for nil in ([], chars(""), ()):
            with pytest.raises(LogicException) as exc:
                list(call("call_goal", nil, module=builtins_mod))
            formal = _formal(exc)
            assert cell_functor(formal) == "existence_error", nil
            assert cell_args(formal)[1] == ("/", mint("[]"), 0), nil
        for nil in ([], chars("")):
            with pytest.raises(LogicException) as exc:
                list(solve(nil, builtins_mod))
            assert cell_functor(_formal(exc)) == "existence_error", nil


class TestTheNilAtomInAKeyPosition:
    """Fix round 2, item 2 (operator-ruled 2026-09-07).  ``mint("[]")`` is
    the empty LIST, which is mutable and so unhashable: a nil atom reaching a
    dict-key position crashed with a raw ``TypeError``.  The empty TUPLE is
    the same term and IS hashable, so it is the canonical key form
    (``atoms.NIL_KEY``); ``atoms.key_of`` builds it at the three key-building
    sites and ``DictTerm`` folds every other nil spelling onto it."""

    def test_key_of_answers_the_hashable_nil(self):
        from clausal.logic.atoms import NIL_KEY, key_of
        assert key_of("[]") == NIL_KEY == ()
        hash(key_of("[]"))               # must not raise
        assert key_of("foo") == mint("foo")
        # ...and it is the same TERM as every other nil spelling.
        assert unify(key_of("[]"), [], Trail())
        assert unify(key_of("[]"), chars(""), Trail())

    def test_dict_term_folds_every_nil_spelling_onto_one_key(self):
        from clausal.terms import DictTerm
        for spelled in ((), chars(""), b""):
            d = DictTerm({spelled: 1})
            assert list(d.keys()) == [()], spelled
            for lookup in ((), chars(""), b"", []):
                assert d[lookup] == 1, (spelled, lookup)
                assert lookup in d, (spelled, lookup)
                assert d.get(lookup) == 1, (spelled, lookup)
        # A raw dict on the right of == / unification is normalised too.
        assert DictTerm({(): 1}) == {chars(""): 1}
        assert unify(DictTerm({(): 1}), DictTerm({b"": 1}), Trail())

    def test_json_parse_makes_a_nil_key_usable(self):
        """``json.parse('{"[]": 1}')`` raised a raw ``TypeError``."""
        mod = _load_inline_clausal(
            "_fix2_json_nil",
            "-import_from(py.json, [parse])\n"
            "j(S, D) <- parse(S, D),\n",
        )
        D = Var()
        (parsed,), = _answers(("j", chars('{"[]": 1, "a": 2}'), D), mod, D)
        assert list(parsed.keys()) == [(), mint("a")]
        assert parsed[()] == 1 and parsed[[]] == 1

    def test_a_source_written_nil_dict_key_compiles(self):
        """Fix round 2, item 6: ``{'[]': 1}`` raised a bare ``TypeError`` at
        dict construction because the key compiled to a list display."""
        mod = _load_inline_clausal(
            "_fix2_dict_nil",
            "-private([a])\n"
            "d({'[]': 1, a: 2}),\n",
        )
        D = Var()
        (d,), = _answers(("d", D), mod, D)
        assert list(d.keys()) == [(), mint("a")]
        assert d[[]] == 1

    def test_get_attrs_survives_a_nil_attribute_name(self, builtins_mod):
        """``attributes.py`` built its answer dict with ``mint(key)``."""
        from clausal.logic.solve import call
        V, D = Var(), Var()
        assert len(list(call("put_attr", V, mint("[]"), 7,
                             module=builtins_mod))) == 1
        got = [_deref_walk(D)
               for _ in call("get_attrs", V, D, module=builtins_mod)]
        assert len(got) == 1 and got[0][()] == 7

    def test_every_raw_mapping_reader_folds_the_nil_key(self, builtins_mod):
        """Fix round 3, item 1: ``dict_set``'s builtins, the subscript path
        and ``py.json``'s ``get/3`` read ``.data`` directly instead of going
        through ``DictTerm.__getitem__``, so they had to fold the nil
        spellings themselves.  Before: ``dict_get('[]', D, V)`` raised a raw
        ``TypeError`` (``[]`` is unhashable), ``dict_get("", …)`` and
        ``(b"", …)`` missed, and only ``()`` hit."""
        from clausal.logic.runtime.dict_ops import _subscript
        from clausal.logic.solve import call
        from clausal.terms import DictTerm

        d = DictTerm({(): 1, mint("a"): 2})
        for nil in ([], chars(""), b"", ()):
            V = Var()
            got = [deref(V)
                   for _ in call("dict_get", nil, d, V, module=builtins_mod)]
            assert got == [1], nil
            assert _subscript(d, nil) == 1, nil

    def test_dict_put_stores_a_nil_key_in_its_canonical_form(self, builtins_mod):
        from clausal.logic.solve import call
        from clausal.terms import DictTerm

        for nil in ([], chars(""), b"", ()):
            D2 = Var()
            (built,) = [_deref_walk(D2)
                        for _ in call("dict_put", nil, 9, DictTerm({}), D2,
                                      module=builtins_mod)]
            assert list(built.keys()) == [()], nil
            assert built[[]] == 9, nil

    def test_json_get_3_folds_the_nil_key(self):
        mod = _load_inline_clausal(
            "_fix3_json_get",
            "-import_from(py.json, [parse, get])\n"
            "j(S, D) <- parse(S, D),\n"
            "g(D, K, V) <- get(D, K, V),\n",
        )
        D = Var()
        (parsed,), = _answers(("j", chars('{"[]": 1}'), D), mod, D)
        for nil in ([], chars(""), b"", ()):
            V = Var()
            assert _answers(("g", parsed, nil, V), mod, V) == [(1,)], nil

    def test_a_constants_structured_dict_key_folds_nil(self):
        """Fix round 3, item 2: a structured ``-constants`` RHS took its own
        dict-key path, which built a plain ``str`` key ``"[]"`` for
        ``{'[]': 1}`` and raised a raw ``TypeError`` for ``{[]: 1}``."""
        mod = _load_inline_clausal(
            "_fix3_constants_nil",
            "-private([a])\n"
            "-constant_value(c_d, {'[]': 1, a: 2})\n"
            "-constant_value(c_e, {[]: 3})\n"
            "c1(++c_d),\n"
            "c2(++c_e),\n",
        )
        X = Var()
        (d,), = _answers(("c1", X), mod, X)
        assert list(d.keys()) == [(), mint("a")]
        assert d[[]] == 1
        Y = Var()
        (e,), = _answers(("c2", Y), mod, Y)
        assert list(e.keys()) == [()] and e[chars("")] == 3

    def test_a_constants_reference_in_key_position_folds_nil(self):
        """Fix round 4, item 4: fix round 3 folded the two nil LITERAL
        spellings at compile time, but a key written as a reference to an
        earlier constant is only known at exec time — and a ``-constants``
        list value is frozen, so ``{c_n: 1}`` with ``c_n = []`` built a raw
        ``TypeError: unhashable type: '_FrozenList'`` at load, before
        ``DictTerm`` ever saw the key."""
        mod = _load_inline_clausal(
            "_fix4_constants_ref_nil",
            "-double_quotes(atom)\n-private([a])\n"
            "-constant_value(c_n, [])\n"
            "-constant_value(c_s, \"\")\n"
            "-constant_value(c_d, {c_n: 1, a: 2})\n"
            "-constant_value(c_e, {c_s: 3})\n"
            "-constant_value(c_f, {\"\": 4})\n"
            "c1(++c_d),\n"
            "c2(++c_e),\n"
            "c3(++c_f),\n"
            "c4(D) <- (D is {\"\": 1}),\n",
        )
        X = Var()
        (d,), = _answers(("c1", X), mod, X)
        assert list(d.keys()) == [(), mint("a")]
        for nil in ([], chars(""), b"", ()):
            assert d[nil] == 1, nil
        Y = Var()
        (e,), = _answers(("c2", Y), mod, Y)
        # Stage 2: a bare Python ``""`` is the ATOM ``''``, NOT nil, so the
        # reference ``c_s`` keys the dict with that atom -- distinct from
        # ``[]``.  Only ``[]`` (``c_n``) is a nil spelling here now.
        assert list(e.keys()) == [""] and e[""] == 3 and [] not in e
        # A LITERAL empty-string key in a -constants RHS reads the same way,
        # and so does the same literal in a CLAUSE: stage 2 closes the
        # divergence fix round 5 pinned here (the ``$dict_key`` wrap folded
        # ``""`` to ``()`` while the clause literal compiled to the atom).
        # todo/source-empty-string-dict-key-is-an-atom-not-nil-2026-09-07.md
        Z = Var()
        (f,), = _answers(("c3", Z), mod, Z)
        assert list(f.keys()) == [""] and f[""] == 4 and [] not in f
        W = Var()
        (clause_dict,), = _answers(("c4", W), mod, W)
        assert list(clause_dict.keys()) == [""]

    def test_a_frozen_empty_list_is_the_nil_key(self):
        """The value half of item 4: ``atoms.as_dict_key`` tested the EXACT
        type, so a ``_FrozenList([])`` — the empty list a ``-constants``
        value is — did not fold, even though it IS the empty list."""
        from clausal.logic.atoms import NIL_KEY, as_dict_key
        from clausal.logic.constants import _FrozenList
        from clausal.terms import DictTerm

        assert as_dict_key(_FrozenList([])) == NIL_KEY
        # …and so it can KEY a dict, which an unfolded ``_FrozenList``
        # cannot (the pairs form: a plain ``{k: 1}`` literal is built by
        # Python before ``DictTerm`` is called, so it raises first).
        assert DictTerm([(_FrozenList([]), 1)])[[]] == 1
        # A non-empty frozen list is NOT nil and stays unfolded.
        frozen = _FrozenList([1, 2])
        assert as_dict_key(frozen) is frozen

    def test_dictterm_materialises_a_one_shot_iterable(self):
        """Fix round 4, item 2: ``__init__``'s ``except TypeError`` arm
        re-iterated *data* after ``dict(data)`` had already consumed it, so a
        GENERATOR of pairs carrying an unhashable nil key silently lost every
        entry ``dict()`` had drained before it raised."""
        from clausal.terms import DictTerm

        d = DictTerm(iter([([], 1), (mint("a"), 2)]))
        assert d.data == {(): 1, mint("a"): 2}
        # The unhashable key LAST as well — the arm must not depend on where
        # ``dict()`` gave up.
        d2 = DictTerm(iter([(mint("a"), 2), ([], 1)]))
        assert d2.data == {(): 1, mint("a"): 2}
        # A generator with no nil key is unaffected (the fast arm).
        d3 = DictTerm((k, v) for k, v in ((mint("a"), 1), (mint("b"), 2)))
        assert d3.data == {mint("a"): 1, mint("b"): 2}
        # A re-iterable list of pairs and a plain mapping keep working.
        assert DictTerm([([], 1)]).data == {(): 1}
        assert DictTerm({chars(""): 1}).data == {(): 1}

    def test_an_empty_seg_unifies_with_every_nil_spelling(self):
        """Fix round 3, item 3: the three ``Seg*`` ``__unify__``/``__eq__``
        gates accept ``list``/``str``/``bytes`` only, so ``()`` was rejected
        outright and the str/bytes cross pairs fell to the wrong arm."""
        from clausal.terms import ConcreteSeg, SegBytes, SegList, SegString

        # The six pairs the item names: each of the three empty ``Seg*``
        # against ``()`` and against ``[]``.
        empties = (SegList([ConcreteSeg([])]), SegString([""]),
                   SegBytes([b""]))
        for seg in empties:
            for nil in ((), []):
                assert unify(seg, nil, Trail()), (seg, nil)
                assert seg == nil, (seg, nil)
        # …and each still unifies with its OWN concrete spelling.
        assert unify(SegList([ConcreteSeg([])]), chars(""), Trail())
        assert unify(SegString([""]), chars(""), Trail())
        assert unify(SegBytes([b""]), b"", Trail())
        # A non-empty Seg is unaffected.
        assert not unify(SegString(["ab"]), [], Trail())
        assert unify(SegString(["ab"]), chars("ab"), Trail())
        # Fix round 4, item 5: the two str/bytes CROSS pairs -- an empty
        # ``SegString`` against ``b""``, an empty ``SegBytes`` against ``""``
        # -- were the residual non-transitivity round 3 left behind, and now
        # hold.  The round-3 NARROWING is still in force where it belongs:
        # it was about a NON-empty/``VarSeg`` case (``[*A] = ""`` binds
        # ``A = ""``, pinned by tests/test_string_list_unification.py), and
        # an OPEN ``Seg*`` does not walk to nothing, so it never reaches the
        # empty-Seg branch.  Full matrix in
        # tests/test_segstring.py::TestAnEmptySegIsTheEmptyList.
        assert unify(SegString([""]), b"", Trail())
        assert unify(SegBytes([b""]), chars(""), Trail())
        assert SegString([""]) == b"" and SegBytes([b""]) == chars("")

    def test_the_nil_goal_error_is_worded_for_nil(self, builtins_mod):
        """Fix round 3, item 6: the shared message said "a string goal is the
        list of its characters" for ``[]``, which has no characters."""
        from clausal.logic.solve import call
        with pytest.raises(LogicException) as exc:
            list(call("call_goal", [], module=builtins_mod))
        context = exc.value.message
        assert "the empty list is not a callable term" in context
        assert "list of its characters" not in context
        # …and a real string still gets the string wording, at call/1 and
        # with an extra argument.  (Round 2 had made call/1 of a string a
        # type_error; FLIPPED back, operator rule 2026-09-25, ISO first: a non-empty list or string is the callable compound '.'/2, so call/1 of one names the missing procedure '.'/2; Scryer disagrees with itself (literal call([a]) -> existence_error, run-time G = [a], call(G) -> type_error).)
        with pytest.raises(LogicException) as exc:
            list(call("call_goal", chars("foo"), Var(), module=builtins_mod))
        assert "list of its characters" in exc.value.message
        with pytest.raises(LogicException) as exc:
            list(call("call_goal", chars("foo"), module=builtins_mod))
        assert "list of its characters" in exc.value.message
        assert cell_functor(cell_args(exc.value.term)[0]) == "existence_error"

    def test_a_py_wrapper_option_table_survives_a_nil_name(self):
        """``modules/py/__init__.py``'s ``option``/``has_option`` looked the
        key up with ``mint(name)``."""
        from clausal.modules.py import has_option, option
        from clausal.terms import DictTerm
        opts = DictTerm({(): 7, mint("k"): 9})
        assert option(opts, "[]", None) == 7
        assert option(opts, "k", None) == 9
        assert has_option(opts, "[]") and not has_option(opts, "nope")

    def test_nil_reads_its_spelling_as_the_two_bracket_characters(
            self, builtins_mod):
        """``atom_length([], 2)`` and ``atom_chars([], ['[', ']'])`` —
        Scryer-verified."""
        N = Var()
        assert _answers(("atom_length", [], N), builtins_mod, N) == [(2,)]
        assert _answers(("atom_length", chars(""), N), builtins_mod, N) == [(2,)]
        C = Var()
        (nil_chars,), = _answers(("atom_chars", [], C), builtins_mod, C)
        # ``['[', ']']`` and ``"[]"`` are the same term; the builtin answers
        # the explicit char list, and both spellings unify with it.
        assert unify(nil_chars, [char_atom("["), char_atom("]")], Trail())
        assert unify(nil_chars, chars("[]"), Trail())


class TestANonEmptyListIsACompound:
    """A non-empty list is the ``'.'/2`` compound (ISO; Scryer 0.10.0
    verified), so ``compound/1`` and ``callable/1`` hold for it — and for a
    string and a code list, which ARE lists."""

    def test_compound_holds_for_lists_strings_and_code_lists(self, builtins_mod):
        for value in ([1, 2], chars("abc"), b"ab", [mint("a")]):
            assert _holds(builtins_mod, "compound", value), value

    def test_callable_holds_for_lists_strings_and_code_lists(self, builtins_mod):
        for value in ([1, 2], chars("abc"), b"ab", [mint("a")]):
            assert _holds(builtins_mod, "callable_", value), value

    def test_a_non_empty_list_is_not_atomic_and_not_an_atom(self, builtins_mod):
        for value in ([1, 2], chars("abc"), b"ab"):
            assert not _holds(builtins_mod, "atomic", value), value
            assert not _holds(builtins_mod, "atom", value), value

    def test_must_be_agrees_with_the_builtins(self, builtins_mod):
        assert list(solve(("must_be", mint("compound"), chars("abc")), builtins_mod))
        assert list(solve(("must_be", mint("callable"), [1, 2]), builtins_mod))


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
    assert not unify(d, DictTerm({chars("foo"): 1}), Trail())


def test_row_20_json_parse_makes_atom_keys_and_string_values():
    mod = _load_inline_clausal(
        "_flip_row20",
        "-import_from(py.json, [parse])\n"
        "r20(S, D) <- parse(S, D),\n"
        "r20_atom(X) <- atom(X),\n"
        "r20_string(X) <- string(X),\n",
    )
    D = Var()
    (parsed,), = _answers(("r20", chars('{"k": "v"}'), D), mod, D)
    assert list(parsed.keys()) == [mint("k")]
    assert parsed[mint("k")] == chars("v")
    assert len(list(solve(("r20_atom", mint("k")), mod))) == 1
    assert len(list(solve(("r20_string", chars("v")), mod))) == 1


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
        assert _answers(("r22", chars("_FLIP_ROW22"), X), mod, X) == [(chars("home-value"),)]
        assert len(list(solve(("r22_string", chars("home-value")), mod))) == 1
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
    # Stage 2 (spec §3 Q1): the Python ``str`` crossing back through ``++``
    # is the ATOM, the same term ``bar`` -- not the chars carrier.
    assert y == mint("bar") and is_atom(y) and not is_chars(y)
    assert x == y


# ── Rows 24-27: the surface ─────────────────────────────────────────────────


def test_row_24_a_double_quoted_functor_is_refused():
    with pytest.raises(SyntaxError) as exc:
        _load_inline_clausal(
            "_flip_row24", "-double_quotes(atom)\n-private([p])\nr24() <- \"foo\"(1),\n")
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
    assert _answers(("r26", X), chars_mod, X) == [(("$chars", "ab"),)]   # stage 1
    assert _answers(("r26", X), atom_mod, X) == [("ab",)]


def test_row_27_a_pl_file_loads_its_strings_as_strings(tmp_path):
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    source = prolog_to_clausal('p("ab").\n')
    assert "-double_quotes(chars)" in source
    mod = _load_inline_clausal("_flip_row27", source)
    X = Var()
    assert _answers(("p", X), mod, X) == [(("$chars", "ab"),)]   # stage 1


# ── Rows 28-30: reader, bytecode cache, listing ─────────────────────────────


def test_row_28_the_reader_makes_atoms_and_strings():
    from clausal.tools.prolog_ast import PAtom, PString
    from clausal.tools.prolog_reader import transform_term

    cell, _span, _names = transform_term(PAtom("hi"))
    assert cell == "hi"                       # STAGE 2: an atom IS the str
    cell, _span, _names = transform_term(PString("hi"))
    assert cell == chars("hi")                # ...and a string is the carrier


def test_row_29_the_bytecode_tag_invalidates_a_pre_flip_pyc():
    """Bumped 9 -> 10 by fix round 1, item 2: a source-written ``'[]'``
    compiles to a list DISPLAY now, so a tag-9 ``.pyc`` still carrying the
    ``("[]",)`` cell must not be loaded against this runtime.

    Bumped 10 -> 11 by fix round 4, item 4: a ``-constants`` dict key the
    compiler cannot decide statically is emitted wrapped in
    ``$dict_key(...)``, so a tag-10 ``.pyc`` carries the bare key expression
    and still raises the raw ``TypeError`` the fix removes.

    Bumped 11 -> 12 by fix round 5, item 1: an ``in`` goal in KEY mode emits
    ``$in_iter($deref(coll), False)`` instead of a bare ``$deref(coll)``, so a
    tag-11 ``.pyc`` still iterates the collection raw and still gives the
    pre-fix answers for a plain dict's nil key and for a ``str``.

    Bumped 12 -> 13 on 2026-09-11, and for a different KIND of reason worth
    recording: not one fix, but a GAP. Fifty-five commits touched the
    transformer between the 11 -> 12 bump and that date with no bump at all,
    and at least one of them (``7a4d7407``) changes emitted code -- a seam no
    longer collects a name through a ``++`` escape, so a tag-12 ``.pyc``
    still emits the walrus and still raises the ``UnboundLocalError`` the fix
    removes.

    That this assertion exists is what makes a bump a decision rather than a
    slip -- it is the reason the 12 -> 13 change could not be made quietly
    (and 13 -> 14, the -double_quotes default flip of 2026-09-26, which
    changes the code emitted for every file that declares no mode).
    What it cannot do is notice the CONVERSE: fifty-five transformer commits
    that should have bumped the tag and did not, because nothing here fails
    when the tag stays still. See
    todo/clausal-bytecode-tag-is-manual-and-goes-stale-2026-09-11.md for
    deriving the tag from an engine fingerprint, which closes that side."""
    from clausal.import_hook import CLAUSAL_BYTECODE_TAG
    assert CLAUSAL_BYTECODE_TAG == 14


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
    # ...and the bare ATOM is not an indicator at all.  Operator ruling 2026-09-25 ("do what Scryer does"):
    # type_error(predicate_indicator, r30_foo) -- it named r30_foo/0 and
    # raised existence_error before 2026-09-25.
    with pytest.raises(LogicException) as exc:
        list(solve(("r30_list", mint("r30_foo")), mod))
    formal = _formal(exc)
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal) == (mint("predicate_indicator"), mint("r30_foo"))
    capsys.readouterr()
    # A STRING is not a predicate indicator either (it was
    # type_error(predicate, "…") before 2026-09-25).
    with pytest.raises(LogicException) as exc:
        list(solve(("r30_list", chars("r30_foo")), mod))
    formal = _formal(exc)
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal)[0] == mint("predicate_indicator")
    assert cell_args(formal)[1] == chars("r30_foo")


# ── Carry-forward pins (items Stage A deferred to THE FLIP) ─────────────────


def test_seg_string_iteration_yields_char_atoms():
    """Task 7 carry-forward: ``SegString``'s sequence protocol answers CHAR
    ATOMS — the elements of the list a string denotes."""
    from clausal.terms import SegString
    ss = SegString(["abc"])
    assert list(ss) == [char_atom("a"), char_atom("b"), char_atom("c")]
    assert ss[0] == char_atom("a")
    assert ss[1:] == chars("bc")   # a slice of a string is a string (R-S2)
    assert char_atom("b") in ss
    assert chars("b") not in ss    # a one-element STRING is not an element


def test_membership_over_a_plain_str_yields_char_atoms(builtins_mod):
    """Task 7 carry-forward: ``X in "abc"`` binds ``X = ("a",)``.

    All THREE spellings of membership, because they used to disagree: the
    ``_in_iter`` funnel and the ``in_/2`` predicate answered char atoms while
    the ``in`` OPERATOR — the only one whose key-mode lowering emitted a bare
    ``deref(coll)`` and let Python's own ``iter(str)`` run — answered 1-char
    ``str``s, which are one-element STRINGS, not chars (Task 15 fix round 5,
    item 1: both modes go through ``_in_iter`` now)."""
    from clausal.logic.runtime.body_star_unify import _in_iter
    char_atoms = [char_atom("a"), char_atom("b"), char_atom("c")]
    assert list(_in_iter(chars("abc"), False)) == char_atoms
    X = Var()
    assert _answers(("in_", X, chars("abc")), builtins_mod, X) == [(c,) for c in char_atoms]
    op_mod = _load_inline_clausal(
        "_flip_in_operator_str", "enum_elems(X, C) <- (X in C)\n")
    Y = Var()
    assert _answers(("enum_elems", Y, chars("abc")), op_mod, Y) == [
        (c,) for c in char_atoms]
    # …and the operator still enumerates an ordinary list unchanged.
    Z = Var()
    assert _answers(("enum_elems", Z, [1, 2]), op_mod, Z) == [(1,), (2,)]


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
    assert _deref_walk(out) == chars("ab")
    assert unify(outer, [char_atom("a"), char_atom("b")], Trail())


def test_var_head_cons_onto_a_string_unifies_with_the_string(builtins_mod):
    """Task 5 carry-forward: ``T =.. ['.', X, "bc"]`` with ``X`` unbound is a
    partial string; once ``X = a`` it IS ``"abc"`` (row 4/18c)."""
    X, T = Var(), Var()
    for _ in solve(("unpack", T, [mint("."), X, chars("bc")]), builtins_mod):
        trail = Trail()
        assert unify(X, char_atom("a"), trail)
        assert unify(_deref_walk(T), chars("abc"), trail)
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
    indicator from the spelling.  A string names no predicate, and this
    funnel — which the runtime meta-call paths reach — must give the same
    refusal ``call/N`` and ``solve/1`` give: Task 15 item 3's
    ``existence_error(procedure, '.'/N)``, not a read of the spelling."""
    from clausal.logic.predicate import _dispatch_at

    with pytest.raises(LogicException) as exc:
        _dispatch_at(chars("t12_str_goal"), 1)
    formal = _formal(exc)
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[0] == mint("procedure")
    assert cell_args(formal)[1] == ("/", mint("."), 3)
    # The ATOM of the same spelling keeps its clean, positioned
    # existence_error — the arm this task leaves in place.
    with pytest.raises(LogicException) as exc:
        _dispatch_at(mint("t12_str_goal"), 1)
    assert cell_functor(_formal(exc)) == "existence_error"


def test_translate_refuses_a_string_language(builtins_mod):
    """``translate/3``'s *Lang* is an atom read by spelling (§6.4); the Stage A
    arm that took a plain ``str`` as the locale name is gone."""
    with pytest.raises(LogicException) as exc:
        list(solve(("translate", chars("th"), mint("hi"), Var()), builtins_mod))
    formal = _formal(exc)
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal)[0] == mint("atom")
    assert cell_args(formal)[1] == chars("th")


def test_listing_refuses_a_string_indicator_name(capsys):
    """``io._as_name_arity_indicator`` accepted a plain ``str`` in the NAME
    half of ``Name/Arity``.  The name half is an atom (§6.4).  Operator ruling 2026-09-25 ("do what Scryer does"): a
    string there is ``functor/3``'s ``type_error(atomic, "…")`` -- a string
    is the (compound) list it denotes; it was ``type_error(predicate, …)``
    before 2026-09-25."""
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
    for shape in (("/", chars("t12_pt"), 2), Compound("/", (chars("t12_pt"), 2))):
        with pytest.raises(LogicException) as exc:
            list(_run(shape))
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal) == (mint("atomic"), chars("t12_pt"))


def test_re_pattern_that_is_not_text_raises_type_error():
    """``modules/py/re._compile_pattern`` handed ``re.compile`` the raw term
    when ``to_text`` answered ``None``, so a compound pattern died with a raw
    Python ``TypeError``.  It raises the documented ``type_error(text, …)``
    now, consistently with ``py/sqlite._text``."""
    from clausal.modules.py.re import _compile_pattern

    with pytest.raises(LogicException) as exc:
        _compile_pattern(("t12_pat", 1))
    formal = _formal(exc)
    assert cell_functor(formal) == "type_error"
    assert cell_args(formal)[0] == mint("text")
    assert cell_args(formal)[1] == ("t12_pat", 1)


def test_vary_and_extend_refuse_a_malformed_field_key(builtins_mod):
    """``keyword_ops._field_keys`` answered ``None`` for a key that is neither
    an atom nor an identifier spelling, and both callers turned that into a
    silent failure.  A malformed key is ``type_error(atom, Key, …)``."""
    for goal_name in ("vary", "extend"):
        with pytest.raises(LogicException) as exc:
            list(solve((goal_name, {1: 2}, mint("t12_term"), Var()),
                       builtins_mod))
        formal = _formal(exc)
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom")
        assert cell_args(formal)[1] == 1
        assert cell_args(exc.value.term)[1] == ("/", goal_name, 3)


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
        assert cell_args(exc.value.term)[1] == ("/", goal_name, 3)
        assert exc.value.message is None


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
        # ``__transformed__/`` holds DUMPS of transformed Clausal source
        # (clausal.tools.dump_transformed writes them there).  They carry
        # ``$``-names, so they are not valid Python and ``ast.parse`` dies on
        # them — the guard then fails for a reason that has nothing to do with
        # the name it exists to police.  They are gitignored, so a clean
        # worktree never has any and a long-lived CHECKOUT does: two from
        # 2026-03-11 are why /workspace/clausal read one more failure than any
        # worktree at the same sha for six months.
        if "__transformed__" in path.parts:
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
    source spells it ``"#="``, which under ``-double_quotes(atom)``
    mode is the atom ``("#=",)``.  ``clpfd`` gated on ``isinstance(op, str)``,
    so every source-written call failed silently.
    """
    mod = _load_inline_clausal(
        "_t12b_clpfd",
        '-double_quotes(atom)\ns_eq(N) <- sum_([1, 2, 3], "#=", N),\n'
        's_lt() <- sum_([1, 2, 3], "#<", 10),\n'
        's_lt_fails() <- sum_([1, 2, 3], "#<", 5),\n'
        'sp(N) <- scalar_product([2, 3], [4, 5], "#=", N),\n',
    )
    N = Var()
    assert _answers(("s_eq", N), mod, N) == [(6,)]
    assert len(list(solve("s_lt", mod))) == 1
    assert list(solve("s_lt_fails", mod)) == []
    assert _answers(("sp", N), mod, N) == [(23,)]


def test_sum_and_scalar_product_refuse_a_string_operator(builtins_mod):
    """A STRING in the operator position is not a name (§6.4) — and silence
    is what hid this whole family, so it is a refusal, not a failure."""
    for goal in (("sum_", [1, 2, 3], chars("#="), 6),
                 ("scalar_product", [2, 3], [4, 5], chars("#="), 23)):
        with pytest.raises(LogicException) as exc:
            list(solve(goal, builtins_mod))
        formal = _formal(exc)
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom")
        assert cell_args(formal)[1] == chars("#=")


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
            zcompare(chars("<"), shape[0], shape[1], Trail())
        formal = _formal(exc)
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom")
        assert cell_args(formal)[1] == chars("<")


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
    assert len(list(solve("attached", mod))) == 1
    assert len(list(solve("deleted", mod))) == 1


def test_a_string_attribute_key_is_refused(builtins_mod):
    """A string is not a name, here as everywhere else (§6.4)."""
    for goal in (("put_attr", Var(), chars("t12b_str_key"), 1),
                 ("get_attr", Var(), chars("t12b_str_key"), Var()),
                 ("del_attr", Var(), chars("t12b_str_key")),
                 ("put_attrs", Var(), {chars("t12b_str_key"): 1})):
        with pytest.raises(LogicException) as exc:
            list(solve(goal, builtins_mod))
        formal = _formal(exc)
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom")
        assert cell_args(formal)[1] == chars("t12b_str_key")


def _ground_segstring(text):
    """A ground ``SegString`` that walks to *text* — the OTHER string shape.

    A partial string that has since been completed is still a ``SegString``
    object, so a funnel that tests ``type(x) is str`` never sees it.
    """
    from clausal.terms import SegString, VarSeg

    hole = Var()
    seg = SegString([text[:1], VarSeg(hole)])
    unify(hole, chars(text[1:]), Trail())
    assert seg.__walk__() == chars(text)
    return seg


def test_both_string_shapes_are_refused_the_same_way_in_a_name_position():
    """A ground ``SegString`` is a STRING, so it must raise where a plain
    ``str`` raises — it used to fall past the ``type(x) is str`` test and
    fail SILENTLY, which is the reporting hole these funnels exist to close.
    ``put_attr/3``'s Key and ``sum_/3``'s Op are the two funnels that read a
    value a partial string can reach."""
    from clausal.logic.builtins.attributes import _storage_key
    from clausal.logic.clpfd import _op_spelling

    for funnel, text, context in ((_storage_key, "segkey", "put_attr/3"),
                                  (_op_spelling, "#=", "sum_/3")):
        for value in (chars(text), _ground_segstring(text)):
            with pytest.raises(LogicException) as exc:
                funnel(value, context)
            formal = cell_args(exc.value.term)[0]
            assert cell_functor(formal) == "type_error"
            assert cell_args(formal)[0] == mint("atom")
            assert cell_args(formal)[1] == chars(text)


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
        "-double_quotes(atom)\n-import_from(py.process, [process_create])\n"
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
    assert chars_text(out).strip() == "t12c" and code == 0
    OUT = Var()
    assert _answers(("run4", OUT), mod, OUT) == [(chars("t12c stdin"),)]
    ERR = Var()
    (err,), = _answers(("err3", ERR), mod, ERR)
    assert "t12c" in chars_text(err)


def test_url_parse_answers_an_atom_keyed_dict_that_join_reads_back():
    """``py.url.parse/2`` builds the parts dict and ``join/2`` consumes one:
    both halves have to agree on what a key is, or the documented round trip
    silently produces an empty URL."""
    mod = _load_inline_clausal(
        "_t12c_url",
        # Written in the DEFAULT atom mode: Task 12c had to spell this snippet
        # ``-double_quotes(chars)`` because ``parse/2`` still gated its Url on
        # ``isinstance(u, str)``; Task 12d put that argument on ``to_text``,
        # so the documented spelling is what the test drives.
        "-double_quotes(atom)\n-import_from(py.url, [parse, join])\n"
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
    assert _answers(("scheme_of", S), mod, S) == [(chars("https"),)]
    assert _answers(("port_of", N), mod, N) == [(8080,)]
    assert _answers(("round_trip", U), mod, U) == [
        (chars("https://example.com:8080/p?q=1"),)]


def test_csv_records_answer_atom_keyed_dicts_and_atom_headers():
    """A CSV header cell is DATA, and §9.2's precedent (JSON object keys →
    atoms) governs data-derived keys too.  The ``Headers`` answer names the
    same columns, so it mints as well — otherwise ``member(H, Headers),
    get(R, H, V)`` fails against the wrapper's own records."""
    mod = _load_inline_clausal(
        "_t12c_csv",
        # Default atom mode, as above: Task 12d put ``parse_records/3``'s
        # String argument on ``to_text``, so the ``-double_quotes(chars)``
        # workaround Task 12c needed here is gone.
        "-double_quotes(atom)\n-import_from(py.csv, [parse_records, generate_records])\n"
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
    assert _answers(("first_name", N), mod, N) == [(chars("alice"),)]
    assert _answers(("headers", H), mod, H) == [([mint("name"), mint("age")],)]
    assert _answers(("by_header", V), mod, V) == [(chars("alice"),)]
    # The round trip closes: what parse_records answered, generate_records
    # writes back out — atom headers and atom record keys included.
    assert _answers(("regenerated", S), mod, S) == [(chars("name,age\r\nalice,30\r\n"),)]


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


# ── Task 12d: the last ``py.*`` text-position sweep ──────────────────────────
#
# Spec §9.1/§9.4: a text position in a ``py.*`` wrapper accepts an ATOM (its
# spelling) or a STRING, and both convert to the same ``str``; the funnel is
# ``modules.py.to_text``.  Task 12b migrated ``http``, ``process``, ``tcp`` and
# ``uuid``; Task 11 part 2 migrated ``logging``, ``re``, ``sqlite`` and
# ``files``'s PATHS.  Everything below still gated its text on
# ``isinstance(x, str)`` / ``expect_type(x, str, …)``, so in the default
# ``-double_quotes(atom)`` mode — where a source-written ``"x"`` IS the atom
# ``("x",)`` — each of these predicates failed SILENTLY when called exactly
# the way its own documentation shows.  One row per wrapper, each asserting
# the real effect (the digest, the parsed date, the env value, the bytes on
# disk), never the guard.


def test_os_env_and_working_directory_take_atom_text():
    """``py.os``'s env-var NAMES and VALUES and ``change_directory``'s path
    are text (§9.4): a name handed to ``os.environ`` is still text, not a
    Python-``str``-only position."""
    import os as _pyos

    with tempfile.TemporaryDirectory() as tmpdir:
        real_tmpdir = _pyos.path.realpath(tmpdir)
        mod = _load_inline_clausal(
            "_t12d_os",
            "-import_from(py.os, [environment_variable, "
            "set_environment_variable, unset_environment_variable, "
            "working_directory, change_directory])\n"
            "-private([t12d_name, t12d_value])\n"
            "set_it() <- set_environment_variable(t12d_name, t12d_value),\n"
            "read_it(V) <- environment_variable(t12d_name, V),\n"
            "unset_it() <- unset_environment_variable(t12d_name),\n"
            "cd_and_read(D) <- (change_directory(\"" + real_tmpdir + "\"), "
            "working_directory(D)),\n",
        )
        prev_cwd = _pyos.getcwd()
        prev_env = _pyos.environ.get("t12d_name")
        try:
            assert len(list(solve("set_it", mod))) == 1
            assert _pyos.environ["t12d_name"] == "t12d_value"
            V = Var()
            # The wrapper ANSWERS text as a string (§9.4); only the argument
            # positions accept an atom.
            assert _answers(("read_it", V), mod, V) == [(chars("t12d_value"),)]
            assert len(list(solve("unset_it", mod))) == 1
            assert "t12d_name" not in _pyos.environ
            D = Var()
            assert _answers(("cd_and_read", D), mod, D) == [(chars(real_tmpdir),)]
        finally:
            _pyos.chdir(prev_cwd)
            if prev_env is None:
                _pyos.environ.pop("t12d_name", None)
            else:
                _pyos.environ["t12d_name"] = prev_env


def test_datetime_string_predicates_take_atom_text():
    """A strftime FORMAT and an ISO-8601 date string are text (§9.4).  The
    format is a Python identifier-ish literal handed to a library, which is
    exactly the position §9.1 rules text: ``'%Y-%m-%d'`` and ``"%Y-%m-%d"``
    denote the same thing."""
    import datetime as _dt

    mod = _load_inline_clausal(
        "_t12d_datetime",
        "-double_quotes(atom)\n-import_from(py.datetime, [datetime_string, date_string_iso, "
        "datetime_string_iso])\n"
        "parsed(DT) <- datetime_string(DT, \"2026-09-07 08:30\", "
        "\"%Y-%m-%d %H:%M\"),\n"
        "iso_date(D) <- date_string_iso(D, \"2026-09-07\"),\n"
        "iso_dt(DT) <- datetime_string_iso(DT, \"2026-09-07T08:30:00\"),\n"
        "formatted(S) <- (date_string_iso(D, \"2026-09-07\"), "
        "datetime_string(D, S, \"%d/%m/%Y\")),\n",
    )
    DT, D, S = Var(), Var(), Var()
    assert _answers(("parsed", DT), mod, DT) == [
        (_T(_dt.datetime(2026, 9, 7, 8, 30)),)]
    assert _answers(("iso_date", D), mod, D) == [(_T(_dt.date(2026, 9, 7)),)]
    DT = Var()
    assert _answers(("iso_dt", DT), mod, DT) == [
        (_T(_dt.datetime(2026, 9, 7, 8, 30)),)]
    assert _answers(("formatted", S), mod, S) == [(chars("07/09/2026"),)]


def test_hash_takes_an_atom_algorithm_name():
    """``hash/3``'s Algorithm is a NAME handed to ``hashlib`` — text (§9.4).
    The digest is asserted, so a wrapper that read the tuple repr
    ``"('sha256',)"`` cannot pass by failing quietly."""
    mod = _load_inline_clausal(
        "_t12d_hash",
        "-double_quotes(atom)\n-import_from(py.hash, [hash, hash_bytes])\n"
        "-private([sha256])\n"
        "hex_of(H) <- hash(sha256, \"abc\", H),\n"
        "raw_of(B) <- hash_bytes(sha256, \"abc\", B),\n",
    )
    H, B = Var(), Var()
    assert _answers(("hex_of", H), mod, H) == [
        (chars("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),)]
    assert _answers(("raw_of", B), mod, B) == [
        (bytes.fromhex(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        ),)]


def test_hmac_takes_an_atom_algorithm_and_an_atom_digest():
    """``sign/4``'s Algorithm and ``verify/4``'s Hex are both text (§9.4) —
    the Hex especially, because a source program compares against a literal
    it wrote, which in the default mode is an atom."""
    expected = "7c0e03d85b6ccac680ea6500e7dc506720bd332aa9aa8e24e6cbf8e0afeea228"
    mod = _load_inline_clausal(
        "_t12d_hmac",
        "-double_quotes(atom)\n-import_from(py.hmac, [sign, verify])\n"
        "-private([sha256])\n"
        "signed(H) <- sign(sha256, \"k3y\", \"msg\", H),\n"
        "ok() <- verify(sha256, \"k3y\", \"msg\", \"" + expected + "\"),\n"
        "bad() <- verify(sha256, \"k3y\", \"msg\", \"" + "0" * 64 + "\"),\n",
    )
    H = Var()
    assert _answers(("signed", H), mod, H) == [(chars(expected),)]
    assert len(list(solve("ok", mod))) == 1
    assert list(solve("bad", mod)) == []


def test_csv_reading_predicates_take_atom_text():
    """``py.csv``'s String and Path arguments are text (§9.4).  A path that
    went through ``str()`` would have opened a file named ``('/tmp/x',)`` —
    the very accident §9.4 was written after."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "t12d.csv")
        mod = _load_inline_clausal(
            "_t12d_csv",
            "-double_quotes(atom)\n-import_from(py.csv, [parse_row, parse, parse_records, "
            "read_file, write_file])\n"
            "-private([name])\n"
            "row(R) <- parse_row(\"a,b,c\", R),\n"
            "rows(RS) <- parse(\"a,b\\nc,d\\n\", RS),\n"
            "first_name(N) <- (parse_records(\"name,age\\nalice,30\\n\", _, RS), "
            "RS is [R, *_], N is R.name),\n"
            "wrote() <- write_file(\"" + path + "\", [[\"x\", \"y\"]]),\n"
            "read_back(RS) <- read_file(\"" + path + "\", RS),\n",
        )
        R, RS, N = Var(), Var(), Var()
        assert _answers(("row", R), mod, R) == [([chars("a"), chars("b"), chars("c")],)]
        assert _answers(("rows", RS), mod, RS) == [([[chars("a"), chars("b")], [chars("c"), chars("d")]],)]
        assert _answers(("first_name", N), mod, N) == [(chars("alice"),)]
        assert len(list(solve("wrote", mod))) == 1
        # The file is where the ATOM said, not where its repr would have been.
        assert os.path.isfile(path)
        assert os.listdir(tmpdir) == ["t12d.csv"]
        RS = Var()
        assert _answers(("read_back", RS), mod, RS) == [([[chars("x"), chars("y")]],)]


def test_json_parse_and_file_predicates_take_atom_text():
    """``py.json``'s String and Path arguments are text (§9.4).  The values
    a parsed object carries stay strings and its keys are atoms (§9.2, Task
    8) — this row is only about the ARGUMENT positions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "t12d.json")
        mod = _load_inline_clausal(
            "_t12d_json",
            "-double_quotes(atom)\n-import_from(py.json, [parse, read_file, write_file])\n"
            "-private([a])\n"
            "parsed(V) <- (parse('{\"a\": 1}', T), V is T.a),\n"
            "parsed3(V) <- (parse('{\"a\": 1}', T, []), V is T.a),\n"
            "wrote() <- (parse('{\"a\": 1}', T), "
            "write_file(\"" + path + "\", T)),\n"
            "read_back(V) <- (read_file(\"" + path + "\", T), V is T.a),\n",
        )
        V = Var()
        assert _answers(("parsed", V), mod, V) == [(1,)]
        V = Var()
        assert _answers(("parsed3", V), mod, V) == [(1,)]
        assert len(list(solve("wrote", mod))) == 1
        assert os.listdir(tmpdir) == ["t12d.json"]
        V = Var()
        assert _answers(("read_back", V), mod, V) == [(1,)]


def test_url_predicates_take_atom_text_including_the_port():
    """``py.url``'s String/Url arguments are text (§9.4), and so is a PORT
    written as a name: ``str(("8080",))`` spliced ``example.com:('8080',)``
    into the netloc."""
    mod = _load_inline_clausal(
        "_t12d_url",
        "-double_quotes(atom)\n-import_from(py.url, [encode, decode, parse, join])\n"
        "-private([scheme, host, port, path])\n"
        "enc(E) <- encode(\"hello world\", E),\n"
        "dec(S) <- decode(\"hello%20world\", S),\n"
        "sch(S) <- (parse(\"https://example.com:8080/p?q=1\", P), "
        "S is P.scheme),\n"
        "joined(U) <- join({scheme: \"https\", host: \"example.com\", "
        "port: \"8080\", path: \"/p\"}, U),\n"
        "joined_int(U) <- join({scheme: \"https\", host: \"example.com\", "
        "port: 8080, path: \"/p\"}, U),\n",
    )
    E, S, U = Var(), Var(), Var()
    assert _answers(("enc", E), mod, E) == [(chars("hello%20world"),)]
    assert _answers(("dec", S), mod, S) == [(chars("hello world"),)]
    S = Var()
    assert _answers(("sch", S), mod, S) == [(chars("https"),)]
    assert _answers(("joined", U), mod, U) == [(chars("https://example.com:8080/p"),)]
    U = Var()
    assert _answers(("joined_int", U), mod, U) == [
        (chars("https://example.com:8080/p"),)]


def test_files_write_and_append_take_atom_contents():
    """``py.files``'s PATHS were migrated in Task 11; its CONTENTS were not.
    Text is text on both sides of the call (§9.4)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "t12d.txt")
        mod = _load_inline_clausal(
            "_t12d_files",
            "-import_from(py.files, [write_string_to_file, "
            "append_string_to_file, read_file_to_string])\n"
            "wrote() <- (write_string_to_file(\"" + path + "\", \"hello \"), "
            "append_string_to_file(\"" + path + "\", \"world\")),\n"
            "read_back(S) <- read_file_to_string(\"" + path + "\", S),\n",
        )
        assert len(list(solve("wrote", mod))) == 1
        S = Var()
        assert _answers(("read_back", S), mod, S) == [(chars("hello world"),)]
        # The bytes on disk, not just what the wrapper says it wrote.
        with open(path, encoding="utf-8") as f:
            assert f.read() == "hello world"
