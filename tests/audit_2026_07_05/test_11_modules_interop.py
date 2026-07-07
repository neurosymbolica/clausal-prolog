"""A11 audit — modules, interop & Prolog tools (2026-07-05 Fable partition).

Adversarial tests + regression guards for:
  clausal/modules/{graphs,imperial,units,reflection,prolog}.py,
  clausal/modules/py/* (stdlib wrappers), clausal/regex.py, clausal/reflection.py,
  clausal/tools/{prolog_ast,prolog_parser,prolog_tokenizer,prolog_operators,
                 prolog_dialect,prolog_to_clausal,clausal_to_prolog}.py

Suspected-bug tests assert the CORRECT behavior and are marked
``xfail(strict=False)`` — they turn into passing guards when fixed.
Everything else is a plain regression guard for behavior confirmed correct.

Run per file only:
  PYTHONPATH=<clone> python -m pytest tests/audit_2026_07_05/test_11_modules_interop.py -v
"""
import ast
import textwrap

import pytest

from clausal import Var, solve
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Trail, deref

_COUNTER = [0]


def _load(tmp_path, src, stem="a11mod"):
    """Write *src* to a uniquely-named .clausal file and load it fresh.

    Unique module names avoid the module-scoped-atom double-load pitfall.
    """
    _COUNTER[0] += 1
    name = f"a11_{stem}_{_COUNTER[0]}"
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(src))
    return _load_module(name, str(path))


def _logic(mod):
    return mod.__dict__["$module"]


def _values(goal, var, module=None):
    out = []
    for _ in solve(goal, module=module):
        out.append(deref(var))
    return out


def _gsols(fn, *args, out=None):
    """Drive a trampoline-mode graphs fn; collect one entry per solution."""
    trail = Trail()
    sols = []
    for parent, _v in fn(None, "P", "F", None, *args, trail):
        if parent != "P":
            break
        sols.append(deref(out) if out is not None else True)
    return sols


# ═════════════════════════════════════════════════════════════════════════════
# Regex — shim, subject coercion, expansion gating, error paths (F001–F009)
# ═════════════════════════════════════════════════════════════════════════════


def test_F001_regex_shim_importable():
    """A11-F001 (fixed): clausal/regex.py re-exports modules/py/re.py."""
    import clausal.regex
    assert hasattr(clausal.regex, "match")


def test_F002_search_unbound_subject_no_solution():
    # A11-F002 (fixed): unbound subject fails cleanly, no repr scanning.
    from clausal.modules.py.re import _search_2
    sols = list(_search_2(r"^_\d+$", Var(), Trail(), None))
    assert sols == []


def test_F002_match_charlist_equals_string(tmp_path):
    # A11-F002 (fixed): char-list subject joined per strings-as-lists Liskov.
    m = _load(tmp_path, '''
        -import_from(regex, [match, replace])
        M2(S) <- match(r"\\d+", S)
        R4(S, R) <- replace(r"b", "X", S, R)
    ''', "f002")
    assert len(list(solve(m.M2(["1", "2", "3"]), module=m))) == 1
    R = Var()
    assert _values(m.R4(["a", "b", "c"], R), R, m) == ["aXc"]


def test_F002_charlist_repr_false_positive(tmp_path):
    # A11-F002 (fixed): char-list joins to "a", no repr-quote false positive.
    m = _load(tmp_path, '''
        -import_from(regex, [search])
        SQ(S) <- search(r"'", S)
    ''', "f002b")
    # char-list "a" contains no quote; the repr "['a']" does — current code
    # falsely succeeds by scanning the repr
    assert list(solve(m.SQ(["a"]), module=m)) == []


def test_F003_user_defined_match_not_hijacked(tmp_path):
    # A11-F003 (fixed): regex expansion gated on object identity, not name.
    m = _load(tmp_path, '''
        match(A, B) <- (A is B)
        Caller(X) <- match("hello", X)
    ''', "f003")
    X = Var()
    assert _values(m.Caller(X), X, m) == ["hello"]


def test_F004_invalid_pattern_catchable(tmp_path):
    # A11-F004 (fixed): module-predicate errors are catchable via catch/3.
    m = _load(tmp_path, '''
        -private([caught])
        -import_from(regex, [match])
        CatchRegex(R) <- catch(match("(", "x"), _, (R is caught))
    ''', "f004")
    R = Var()
    out = _values(m.CatchRegex(R), R, m)
    assert [str(v) for v in out] == ["caught"]


def test_F004_replace_unbound_repl_fails_cleanly():
    # A11-F004 (fixed): unbound replacement fails cleanly.
    from clausal.modules.py.re import _replace_4
    sols = list(_replace_4("x", Var(), "x", Var(), Trail(), None))
    assert sols == []


def test_F005_wrong_arity_is_an_error_not_silent_failure(tmp_path):
    # A11-F005 (fixed): unregistered arity raises a catchable existence error.
    m = _load(tmp_path, '''
        -import_from(regex, [match])
        Bad(S) <- match(r"x", S, G, H)
    ''', "f005")
    with pytest.raises(Exception):
        list(solve(m.Bad("x"), module=m))


def test_F006_mixed_groups_expose_positional_values(tmp_path):
    # A11-F006 (fixed): unnamed groups added under 1-based int keys.
    m = _load(tmp_path, '''
        -import_from(regex, [match])
        M(S, G) <- match(r"(?P<A>\\d+)-(\\d+)", S, G)
    ''', "f006")
    G = Var()
    (g,) = _values(m.M("1-2", G), G, m)
    assert g.get("A") == "1" and "2" in g.values()


def test_F007_dynamic_pattern_autobind_or_documented(tmp_path):
    # A11-F007 (fixed): dynamic patterns auto-bind present named groups.
    m = _load(tmp_path, '''
        -import_from(regex, [match])
        Dyn(P, S, YEAR) <- match(P, S)
    ''', "f007")
    Y = Var()
    assert _values(m.Dyn(r"(?P<YEAR>\d+)", "2026", Y), Y, m) == ["2026"]


def test_F008_guard_unmatched_optional_group_binds_none(tmp_path):
    """A11-F008 (design, current behavior guard): unmatched optional named
    group auto-binds Python None — Python-consistent, undocumented."""
    m = _load(tmp_path, '''
        -import_from(regex, [match])
        OptG(S, TAG) <- match(r"(?P<TAG>\\d+)?x", S)
    ''', "f008")
    T = Var()
    assert _values(m.OptG("x", T), T, m) == [None]


def test_F009_guard_findall_single_group_is_string(tmp_path):
    """A11-F009 (doc-drift guard): single-group findall yields bare strings
    (matches the re.findall oracle; the docstring claims tuples)."""
    m = _load(tmp_path, '''
        -import_from(regex, [findall])
        FA(S, M) <- findall(r"(\\d)x", S, M)
    ''', "f009")
    M = Var()
    assert _values(m.FA("1x2x", M), M, m) == ["1", "2"]


def test_guard_regex_ground_modes_match_re_oracle(tmp_path):
    m = _load(tmp_path, '''
        -import_from(regex, [match, replace, split])
        G1(S) <- match(r"\\d+", S)
        G2(S, R) <- replace(r"b", "X", S, R)
        G3(S, PARTS) <- split(r",", S, PARTS)
    ''', "oracle")
    assert len(list(solve(m.G1("123"), module=m))) == 1
    assert list(solve(m.G1("abc"), module=m)) == []
    R = Var()
    assert _values(m.G2("abc", R), R, m) == ["aXc"]
    P = Var()
    assert _values(m.G3("a,b", P), P, m) == [["a", "b"]]


# ═════════════════════════════════════════════════════════════════════════════
# Reflection — reifier fidelity + builtins (F010–F014)
# ═════════════════════════════════════════════════════════════════════════════


def test_F010_keyword_head_reify_matches_runtime_order():
    # A11-F010 (fixed): keyword heads reify as [name, value] kwargs pairs.
    from clausal.reflection import reify_source
    items = reify_source('kp(x=1, y=2),\nkp(y=20, x=10),\n')
    second = items[1].head
    # Either canonical field order, or kwargs pairs preserving the names.
    assert list(second.args) == [10, 20] or ["x", 10] in list(second.kwargs)


def test_F011_anon_var_does_not_alias_user_underscore_one():
    # A11-F011 (fixed): anonymous vars use non-identifier #anonN names.
    from clausal.reflection import reify_source
    clause = reify_source('Foo(_1, _, X) <- Bar(_1, _, X)\n')[0]
    a0, a1 = clause.head.args[0], clause.head.args[1]
    assert a0 != a1  # user _1 and anonymous _ are distinct at runtime


def test_F012_reify_ast_preserves_lt_negative():
    # A11-F012 (fixed): only the top-level arrow is repaired.
    from clausal.reflection import reify_ast, reify_source
    got = reify_ast(ast.parse('Foo(X) <- (X < -1)'))
    want = reify_source('Foo(X) <- (X < -1)')[0]
    assert type(got.goals[0]).__name__ == type(want.goals[0]).__name__ == "Lt"


def test_F013_dict_literal_pattern_matches(tmp_path):
    # A11-F013 (fixed): dict literals reify as raw dicts, matching patterns.
    m = _load(tmp_path, '''
        -import_from(reflection, [reified_clause])
        DictPattern(SRC) <- reified_clause(SRC, Pt({"k": 5}) <- True)
    ''', "f013")
    assert len(list(solve(m.DictPattern('Pt({"k": 5}),\n'), module=m))) == 1


def test_F014_reified_item_unbound_source_instantiation_error(tmp_path):
    # A11-F014 (fixed): unbound source raises instantiation_error.
    from clausal.logic.exceptions import LogicException
    m = _load(tmp_path, '''
        -import_from(reflection, [reified_item])
        AI(S, I) <- reified_item(S, I)
    ''', "f014")
    with pytest.raises(LogicException):
        list(solve(m.AI(Var(), Var()), module=m))


def test_guard_reified_item_enumerates(tmp_path):
    m = _load(tmp_path, '''
        -import_from(reflection, [reified_item])
        AI(SRC, ITEM) <- reified_item(SRC, ITEM)
    ''', "reify")
    src = 'Edge2(1, 2),\nConn(X, Y) <- Edge2(X, Y)\n'
    assert len(list(solve(m.AI(src, Var()), module=m))) == 2


# ═════════════════════════════════════════════════════════════════════════════
# py wrappers — datetime, url, http, hash (F015–F019)
# ═════════════════════════════════════════════════════════════════════════════


def test_F015_date4_rejects_float_components():
    # A11-F015 (fixed): float components rejected, not truncated.
    from clausal.modules.py.datetime import _date_4
    sols = list(_date_4(2020.9, 1.9, 5, Var(), Trail(), None))
    assert sols == []  # stdlib datetime.date raises TypeError on floats


def test_F015_guard_date4_construct_and_decompose():
    import datetime as pydt
    from clausal.modules.py.datetime import _date_4
    D = Var()
    sols = list(_date_4(2020, 1, 5, D, Trail(), None))
    assert len(sols) == 1 and deref(D) == pydt.date(2020, 1, 5)


def test_F016_date_between_mixed_types_fails_cleanly():
    # A11-F016 (fixed): date/datetime mix fails cleanly.
    import datetime as pydt
    from clausal.modules.py.datetime import _date_between_3
    gen = _date_between_3(None, "P", "F", None,
                          pydt.date(2020, 1, 1), pydt.datetime(2020, 1, 3),
                          Var(), Trail())
    sols = [1 for parent, _v in gen if parent == "P"]  # must not raise
    assert sols == []


def test_F017_url_parse_bad_port_fails_cleanly():
    # A11-F017 (fixed): out-of-range port fails cleanly.
    from clausal.modules.py.url import _parse_2
    sols = list(_parse_2("http://h:99999/", Var(), Trail(), None))
    assert sols == []


def test_F018_http_get_malformed_url_fails_cleanly():
    # A11-F018 (fixed): malformed URL fails cleanly.
    from clausal.modules.py.http import _get_2
    sols = list(_get_2("not-a-url", Var(), Trail(), None))
    assert sols == []


def test_F019_hash_shake_fails_cleanly():
    # A11-F019 (fixed): shake_* variable-length digest fails cleanly.
    from clausal.modules.py.hash import _hash_3
    sols = list(_hash_3("shake_128", "abc", Var(), Trail(), None))
    assert sols == []


def test_F019_guard_hash_sha256_matches_hashlib():
    import hashlib
    from clausal.modules.py.hash import _hash_3
    H = Var()
    sols = list(_hash_3("sha256", "abc", H, Trail(), None))
    assert len(sols) == 1
    assert deref(H) == hashlib.sha256(b"abc").hexdigest()


# ═════════════════════════════════════════════════════════════════════════════
# Prolog tools — modules/prolog.py arithmetic (F020, F021)
# ═════════════════════════════════════════════════════════════════════════════


def test_F020_mod_is_floored():
    # A11-F020 (fixed): TruncMod is floored ISO mod (sign follows divisor).
    from clausal.modules.prolog import TruncMod
    assert TruncMod(-7, 3) == 2      # ISO: -7 mod 3 =:= 2
    assert TruncMod(7, -3) == -2     # sign follows divisor


def test_F021_truncdiv_bignum_exact():
    # A11-F021 (fixed): TruncDiv uses exact integer arithmetic.
    from clausal.modules.prolog import TruncDiv
    n = 10 ** 18 + 1
    assert TruncDiv(n, 1) == n
    assert TruncDiv(-(10 ** 19) - 3, 10) == -(10 ** 18)  # trunc toward zero


# ═════════════════════════════════════════════════════════════════════════════
# Prolog tools — dialect / translator pl→clausal (F022–F027)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.xfail(strict=False, reason="A11-F022: Foo and FOO both map to "
                   "_foo — distinct Prolog variables silently merged")
def test_F022_var_mapping_injective():
    import re as _re
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal("p(Foo, FOO) :- Foo = 1, FOO = 2.\n")
    v1, v2 = _re.findall(r"P\((\w+), (\w+)\)", out)[0]
    assert v1 != v2


@pytest.mark.xfail(strict=False, reason="A11-F023: ','/2 argument flattened "
                   "in emission — foo/2 fact silently becomes Foo/3")
def test_F023_tuple_arg_arity_preserved():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal("foo(a, (b, c)).\n")
    assert "Foo(a, b , c)" not in out


@pytest.mark.xfail(strict=False, reason="A11-F024: -> in metacall args emitted "
                   "as ->(...) instead of the designed rejection (sibling of A10-F001)")
def test_F024_arrow_rejected_in_term_position():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal, PrologTranslationError
    with pytest.raises(PrologTranslationError):
        prolog_to_clausal("q(L) :- findall(X, (c(X) -> t ; e), L).\n")


@pytest.mark.xfail(strict=False, reason="A11-F025: quoted/keyword/graphic "
                   "atoms emitted bare — invalid or silently different Clausal")
def test_F025_atom_emission_fidelity():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal("p('hello world').\np(class).\n")
    ast.parse(out)  # must at minimum be syntactically valid Python


@pytest.mark.xfail(strict=False, reason="A11-F026: ISO ops @< @> @=< @>= ^ div "
                   "missing from every operator table (bagof ^ unparseable)")
def test_F026_iso_operator_table_complete():
    from clausal.tools.prolog_parser import parse_term
    t = parse_term("bagof(X, Y^p(X,Y), L)")
    assert t.functor == "bagof" and t.args[1].functor == "^"
    assert parse_term("X @< Y").functor == "@<"


@pytest.mark.xfail(strict=False, reason="A11-F027: bare ':- dynamic p/1.' "
                   "(SWI prefix-op form) fails to parse")
def test_F027_bare_dynamic_directive():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    assert "-dynamic(P/1)" in prolog_to_clausal(":- dynamic p/1.\n")


def test_F027_guard_paren_dynamic_directive():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    assert "-dynamic(P/1)" in prolog_to_clausal(":- dynamic(p/1).\n")


# ═════════════════════════════════════════════════════════════════════════════
# Prolog tools — parser/tokenizer conformance (F028, F029, F034, F035, F037, F038, F040)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.xfail(strict=False, reason="A11-F028: xfx chaining accepted "
                   "(a=b=c, 2**3**2, x:-y:-z) — ISO syntax errors")
def test_F028_xfx_not_chainable():
    from clausal.tools.prolog_parser import parse_term, ParseError
    with pytest.raises(ParseError):
        parse_term("a = b = c")
    with pytest.raises(ParseError):
        parse_term("2 ** 3 ** 2")


@pytest.mark.xfail(strict=False, reason="A11-F029: quoted functor 'foo'(1) "
                   "unparseable (adjacency uses unquoted token length)")
def test_F029_quoted_functor():
    from clausal.tools.prolog_parser import parse
    m = parse("'foo'(1).")
    assert m.items[0].head.functor == "foo"


@pytest.mark.xfail(strict=False, reason="A11-F034: ISO escapes (\\r, \\x41\\, "
                   "octal, 0''', line continuation) mangled or fatal")
def test_F034_iso_escapes():
    from clausal.tools.prolog_tokenizer import tokenize
    assert tokenize(r"'\r'.")[0].value == "\r"
    assert tokenize(r"'\x41\'.")[0].value == "A"
    assert tokenize("X = 0'''.")[2].value == 39


@pytest.mark.xfail(strict=False, reason="A11-F035: PAtom.quoted never set by "
                   "the parser; docs promise quoted atoms → Python strings")
def test_F035_quoted_flag_set():
    from clausal.tools.prolog_parser import parse_term
    assert parse_term("'red'").quoted is True


@pytest.mark.xfail(strict=False, reason="A11-F037: spaced '- 1' folded to "
                   "integer -1 (ISO: -(1)); breaks emit→parse fixpoint")
def test_F037_spaced_minus_is_compound():
    from clausal.tools.prolog_parser import parse_term
    from clausal.tools.prolog_ast import PCompound
    assert isinstance(parse_term("- 1"), PCompound)


@pytest.mark.xfail(strict=False, reason="A11-F038: ':- op(0, xfx, Name)' does "
                   "not remove the operator (ISO 8.14.3.4 requires removal)")
def test_F038_op_zero_removes():
    from clausal.tools.prolog_parser import parse, ParseError
    with pytest.raises(ParseError):
        parse(":- op(0, xfx, ===).\na === b.")


@pytest.mark.xfail(strict=False, reason="A11-F040: malformed numeric literals "
                   "raise bare ValueError instead of TokenizeError with position")
def test_F040_malformed_number_tokenize_error():
    from clausal.tools.prolog_tokenizer import tokenize, TokenizeError
    with pytest.raises(TokenizeError):
        tokenize("X = 0x.")


def test_guard_tokenizer_radix_and_bignum():
    from clausal.tools.prolog_tokenizer import tokenize
    assert tokenize("X = 0x1f.")[2].value == 31
    assert tokenize("X = 12345678901234567890123.")[2].value == 12345678901234567890123


# ═════════════════════════════════════════════════════════════════════════════
# Prolog tools — emission fidelity both directions (F030–F033, F036, F039, F041)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.xfail(strict=False, reason="A11-F030: (2**3)**2 emitted as "
                   "2 ** 3 ** 2 — Python right-assoc gives 512, Prolog 64")
def test_F030_pow_grouping_preserved():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal("q(X) :- X is (2 ** 3) ** 2.\n")
    assert "(2 ** 3) ** 2" in out


@pytest.mark.xfail(strict=False, reason="A11-F031: Clausal // (floor div) "
                   "exported as Prolog // (truncating)")
def test_F031_floordiv_export_semantics():
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    out = clausal_source_to_prolog("P(X, A, B) <- (X := A // B)\n")
    assert " A // B" not in out  # must be div / floored equivalent


@pytest.mark.xfail(strict=False, reason="A11-F032: =:= → == round-trips to "
                   "structural \\== semantics; arithmetic nature lost")
def test_F032_arith_eq_roundtrip():
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    back = clausal_source_to_prolog("Q(X, Y) <- (X == Y + 1)\n")
    assert "=:=" in back or " is " in back


@pytest.mark.xfail(strict=False, reason="A11-F033: =.. and lists:member emit "
                   "invalid Clausal; docs promise unpack/2 and lists.in_")
def test_F033_univ_and_qualified_emission():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal("q(T, L) :- T =.. L.\n")
    ast.parse(out)
    assert "unpack" in out


@pytest.mark.xfail(strict=False, reason="A11-F036: Cut() exported as ! — the "
                   "exporter emits the construct Clausal forbids")
def test_F036_no_cut_emission():
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    out = clausal_source_to_prolog("P() <- (Q(), Cut())\n")
    assert "!" not in out


@pytest.mark.xfail(strict=False, reason="A11-F039: DCG pushback head emits "
                   "invalid Python silently instead of a clear rejection")
def test_F039_dcg_pushback_clear_error_or_valid():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal, PrologTranslationError
    try:
        out = prolog_to_clausal("h, [t] --> b.\n")
    except PrologTranslationError:
        return  # clear rejection is acceptable
    ast.parse(out)  # otherwise the output must at least be valid


@pytest.mark.xfail(strict=False, reason="A11-F041: *-> gives generic "
                   "ParseError token soup, not the designed clear rejection")
def test_F041_soft_cut_clear_error():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal, PrologTranslationError
    with pytest.raises(PrologTranslationError, match="soft|[*]->"):
        prolog_to_clausal("p :- (a *-> b ; c).\n")


def test_guard_body_ite_rejected():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal, PrologTranslationError
    with pytest.raises(PrologTranslationError):
        prolog_to_clausal("p :- (c -> t ; e).\n")


def test_guard_cut_rejected_in_metacall_conjunction():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal, PrologTranslationError
    with pytest.raises(PrologTranslationError):
        prolog_to_clausal("q(L) :- findall(X, (member(X, L), !), R).\n")


def test_guard_contract_mappings():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal(
        "q(X, L) :- nth0(0, L, X), memberchk(X, L), member(X, L).\n")
    flat = out.replace(" ", "")
    assert "list_item(0,L,X)" in flat
    assert "in_check(X,L)" in flat
    assert "XinL" in flat


def test_guard_pow_emit_parse_fixpoint_c2p():
    """clausal_to_prolog gets ** grouping right (contrast A11-F030)."""
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    out = clausal_source_to_prolog("P(X) <- (X := (2 ** 3) ** 2)\n")
    assert "(2 ** 3) ** 2" in out


# ═════════════════════════════════════════════════════════════════════════════
# Graphs (F043–F054, F058)
# ═════════════════════════════════════════════════════════════════════════════

from clausal.modules import graphs as G  # noqa: E402


def test_F043_has_cycle_deep_graph():
    # A11-F043 (fixed): iterative 3-color DFS handles deep graphs.
    edges = [[i, i + 1] for i in range(3000)] + [[3000, 0]]
    assert _gsols(G._has_cycle__1, edges) == [True]


def test_F044_find_path_long_chain():
    # A11-F044 (fixed): iterative path DFS handles long chains.
    edges = [[i, i + 1] for i in range(2500)]
    p = Var()
    sols = _gsols(G._find_path__4, edges, 0, 2500, p, out=p)
    assert sols and len(sols[0]) == 2501


def test_F045_shortest_path_negative_weight():
    # A11-F045 (fixed): negative weights fail cleanly (Dijkstra precondition).
    edges = [["a", "b", 1], ["a", "c", 5], ["c", "b", -100]]
    p = Var()
    sols = _gsols(G._shortest_path__4, edges, "a", "b", p, out=p)
    # correct behavior: the true shortest path, or a clean failure/typed error
    assert sols == [] or sols[0] == ["a", "c", "b"]


def test_F046_is_isolated_enumerate():
    # A11-F046 (fixed): 1-element [v] entries make enumerate mode reachable.
    n = Var()
    sols = _gsols(G._is_isolated__2, [["a", "b"], ["c"]], n, out=n)
    assert sols == ["c"]


def test_F046_guard_nonvertex_counts_isolated():
    """A11-F046 current-behavior guard: any non-vertex passes the check."""
    assert _gsols(G._is_isolated__2, [["a", "b"]], "zzz") == [True]


def test_F049_path_cost_parallel_edges_min():
    # A11-F049 (fixed): path_cost keeps the minimum parallel-edge weight.
    c = Var()
    sols = _gsols(G._path_cost__3, [["a", "b", 3], ["a", "b", 5]],
                  ["a", "b"], c, out=c)
    assert sols == [3]


def test_F050_mst_disconnected_fails():
    # A11-F050 (fixed): disconnected graph has no spanning tree, fails.
    t, c = Var(), Var()
    sols = _gsols(G._min_spanning_tree__3, [["a", "b", 1], ["c", "d", 2]], t, c)
    assert sols == []  # no spanning tree exists


def test_F051_find_path_dup_edges_single_solution():
    # A11-F051 (fixed): deduped adjacency yields one path.
    p = Var()
    sols = _gsols(G._find_path__4, [["a", "b"], ["a", "b"]], "a", "b", p, out=p)
    assert sols == [["a", "b"]]


def test_F051_neighbors_dedup():
    # A11-F051 (fixed): neighbor lists are deduped.
    n = Var()
    sols = _gsols(G._neighbors__3, [["a", "b"], ["a", "b"]], "a", n, out=n)
    assert sols == [["b"]]


def test_F052_mst_mixed_vertex_types():
    # A11-F052 (fixed): monotone counter breaks weight ties before vertices.
    t, c = Var(), Var()
    sols = _gsols(G._min_spanning_tree__3,
                  [["a", "b", 1], ["a", 2, 1], [2, "b", 1]], t, c)
    assert sols  # should not raise TypeError


def test_F052_vertices_unhashable_vertex():
    # A11-F052 (fixed): unhashable vertices fall back to identity.
    v = Var()
    sols = _gsols(G._vertices__2, [[{"k": 1}, "b"]], v, out=v)
    assert isinstance(sols, list)  # clean fail/success, not TypeError


def test_F053_multi_dispatch_forwards_all_params():
    # A11-F053 (fixed): graph predicates use the shared ModulePredicate base.
    gp = G._GraphPredicate("fake")
    gp._register(2, G._vertices__2)
    gp._register(3, G._neighbors__3)
    v = Var()
    gen = gp._get_dispatch()(None, "P", "F", None, [["a", "b"]], v, Trail())
    assert next(gen)[0] == "P"


def test_F054_guard_has_edge_directional():
    """A11-F054 current-behavior guard: has_edge is directional while
    neighbors/paths treat the same edge list as undirected."""
    assert _gsols(G._has_edge__3, [["a", "b"]], "a", "b") == [True]
    assert _gsols(G._has_edge__3, [["a", "b"]], "b", "a") == []
    n = Var()
    assert _gsols(G._neighbors__3, [["a", "b"]], "b", n, out=n) == [["a"]]


def test_F058_guard_doc_drift_batch():
    """A11-F058 current-behavior guards: merge=concat (docs say union),
    self-loop degree 1, phantom BFS source."""
    m = Var()
    assert _gsols(G._merge_graphs__3, [["a", "b"]],
                  [["a", "b"], ["c", "d"]], m, out=m) == \
        [[["a", "b"], ["a", "b"], ["c", "d"]]]
    d = Var()
    assert _gsols(G._degree__3, [["a", "a"]], "a", d, out=d) == [1]
    n = Var()
    assert _gsols(G._breadth_first_nodes__3, [["a", "b"]], "z", n, out=n) == [["z"]]


def test_guard_graphs_classic_dijkstra_and_mst():
    p = Var()
    edges = [["a", "b", 4], ["a", "c", 2], ["b", "c", 5], ["b", "d", 10],
             ["c", "e", 3], ["e", "d", 4], ["d", "f", 11], ["e", "f", 15]]
    sols = _gsols(G._shortest_path__4, edges, "a", "d", p, out=p)
    assert sols == [["a", "c", "e", "d"]]
    t, c = Var(), Var()
    sols = _gsols(G._min_spanning_tree__3, [["a", "b", 1], ["b", "c", 2]], t, c, out=c)
    assert sols == [3]


# ═════════════════════════════════════════════════════════════════════════════
# Units & imperial (F047, F048, F055–F057, F059)
# ═════════════════════════════════════════════════════════════════════════════


def test_F047_negative_unit_literal_in_is(tmp_path):
    # A11-F047 (fixed): -n(Unit) folds negation into the sugar constant.
    mod = _load(tmp_path, '''
        -import_from(py.units, [Second, strip_units])
        T(V) <- (Q is -3(Second), strip_units(Q, V))
    ''', "f047")
    v = Var()
    assert [deref(v) for _ in call("T", v, module=_logic(mod))] == [-3]


def test_F047_guard_negative_unit_literal_in_assign(tmp_path):
    """The := position of the same literal works (the documented example)."""
    mod = _load(tmp_path, '''
        -import_from(py.units, [Second, strip_units])
        T(V) <- (Q := -3(Second), strip_units(Q, V))
    ''', "f047g")
    v = Var()
    assert [deref(v) for _ in call("T", v, module=_logic(mod))] == [-3]


def test_F048_byte_call_style_from_docs():
    # A11-F048 (fixed): Quantity.__call__ scales (Byte(1) == 1*Byte).
    from clausal.modules.units import Byte, mebi
    assert (1 * mebi * Byte(1)).value == 8 * 2 ** 20


def test_F048_guard_byte_noncall_style():
    from clausal.modules.units import Byte, mebi
    assert (1 * mebi * Byte).value == 8 * 2 ** 20


def test_F055_psi_consistent_with_lbf_per_sq_inch():
    # A11-F055 (fixed): psi derived from lbf/in^2.
    from clausal.modules.imperial import psi, pound_force, inch
    assert psi.value == pytest.approx(pound_force.value / inch.value ** 2,
                                      rel=1e-12)


def test_F056_guard_imperial_in_unit_parens_works(tmp_path):
    """A11-F056: docs deny n(imperial) sugar, but it works — guard it."""
    mod = _load(tmp_path, '''
        -import_from(py.imperial, [inch])
        -import_from(py.units, [strip_units])
        T(V) <- (Q := 5(inch), strip_units(Q, V))
    ''', "f056")
    v = Var()
    (got,) = [deref(v) for _ in call("T", v, module=_logic(mod))]
    assert got == pytest.approx(0.127)


def test_F056_prefix_in_unit_parens_clean_error():
    # A11-F056 (fixed): prefix-as-unit raises a designed TypeError.
    from clausal.terms import Quantity, UnitsMismatch
    with pytest.raises((TypeError, UnitsMismatch)):
        Quantity(5, 1000)  # currently AttributeError


def test_F057_unit_pred_pow_integer_only():
    # A11-F057 (fixed): float exponents rejected.
    from clausal.modules.units import Metre
    with pytest.raises(Exception):
        Metre ** 0.5


def test_F059_docs_quickstart_import_line(tmp_path):
    # A11-F059 (fixed): has_units re-exported from py.units.
    _load(tmp_path, '''
        -import_from(py.units, [m, kg, s, Newton, kilo, has_units, strip_units])
        T(V) <- strip_units(5(m), V)
    ''', "f059")  # must not raise ImportError


def test_guard_units_mismatch_catchable(tmp_path):
    mod = _load(tmp_path, '''
        -private([caught])
        -import_from(py.units, [Metre, Second])
        T(R) <- catch((Q := 3(Metre) + 2(Second)), UnitsMismatch(_), (R is caught))
    ''', "unitsm")
    r = Var()
    out = [str(deref(r)) for _ in call("T", r, module=_logic(mod))]
    assert out == ["caught"]
