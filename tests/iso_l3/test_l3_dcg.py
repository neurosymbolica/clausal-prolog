"""Native ``.pl``: DCG grammar rules (ISO 7.14, Scryer's library(dcgs)).

A ``-->`` rule is translated to the clause Scryer's ``dcg_rule/2`` gives
and lowered as a clause; ``phrase/2,3`` call the nonterminal ``name//N``
as the procedure ``name/(N+2)``.  Every expected answer below was measured
on Scryer Prolog (scryer-prolog-clpq, 2026-10-01) with the same program.
Until 2026-10-01 the native front end refused every ``-->`` rule at load
("DCG is out of scope"), so every load here failed.

Clausal is cut-free: ``!`` and ``->`` in a grammar body are refused with
the clause-body refusal, word for word; ``{!}`` is the cut ``!, S0 = S``
in the rule's clause and is refused too.  ``\\+`` is refused as Scryer
refuses it, representation_error(dcg_body).
"""
from __future__ import annotations

import textwrap

import pytest

GRAMMAR = """\
:- use_module(library(dcgs)).
g1 --> [a, b].
g2 --> "ab".
g3 --> [].
digit(D) --> [D], { member(D, "0123") }.
digits([D|T]) --> digit(D), digits(T).
digits([D]) --> digit(D).
ab --> [a] ; [b].
ab2 --> [a] | [b].
e(X) --> {X = 5}.
e2(X) --> {X = 5}, [z].
twice(X) --> [X, X].
cl(G) --> call(G).
cl2(G, X) --> call(G, X).
look(X), [X] --> [X].
v(B) --> B.
ph(B) --> phrase(B).
q --> lists:append([a]).
t1(R) :- findall(L, phrase(g1, L), R).
t2(R) :- findall(Rest, phrase(g1, [a,b,c], Rest), R).
t3(R) :- findall(L, phrase(g2, L), R).
t4(R) :- findall(L, phrase(g3, L), R).
t5(R) :- findall(D-Rest, phrase(digits(D), "12x", Rest), R).
t6(R) :- findall(L, phrase(ab, L), R).
t7(R) :- findall(L, phrase(ab2, L), R).
t8(R) :- findall(X-Rest, phrase(e(X), [a], Rest), R).
t9(R) :- findall(X-Rest, phrase(e2(X), [z,y], Rest), R).
t10(R) :- findall(L, phrase(cl(twice(q)), L), R).
t11(R) :- findall(L, phrase(cl2(twice, q), L), R).
t12(R) :- findall(X-Rest, phrase(look(X), [a,b], Rest), R).
t13(R) :- findall(L, phrase(v([x]), L), R).
t15(R) :- findall(L, phrase(ph(g1), L), R).
t16(R) :- findall(Rest, phrase(q, [a,b], Rest), R).
t17(R) :- findall(x, phrase(g1, [a]), R).
t18(R) :- catch(findall(L, phrase(v(_), L), R), error(E, _), R = E).
t19(R) :- findall(x, phrase(g2, "ab"), R).
"""

#: Scryer's answers (``write/1`` of R), as Clausal terms.
SCRYER = {
    "t1": [["a", "b"]],
    "t2": [["c"]],
    "t3": [["a", "b"]],
    "t4": [[]],
    "t5": [("-", ["1", "2"], ["x"]), ("-", ["1"], ["2", "x"])],
    "t6": [["a"], ["b"]],
    "t7": [["a"], ["b"]],
    "t8": [("-", 5, ["a"])],
    "t9": [("-", 5, ["y"])],
    "t10": [["q", "q"]],
    "t11": [["q", "q"]],
    "t12": [("-", "a", ["a", "b"])],
    "t13": [["x"]],
    "t15": [["a", "b"]],
    "t16": [["a", "a", "b"]],
    "t17": [],
    "t18": "instantiation_error",
    "t19": ["x"],
}


def _n(t):
    """A chars carrier as the list of chars it is (Scryer writes both as
    [a,b])."""
    if type(t) is tuple and len(t) == 2 and t[0] == "$chars":
        return list(t[1])
    if type(t) is list:
        return [_n(x) for x in t]
    if type(t) is tuple:
        return tuple(_n(x) for x in t)
    return t


@pytest.mark.parametrize("goal", sorted(SCRYER, key=lambda k: int(k[1:])))
def test_each_construct_answers_as_scryer(native, ans, goal):
    mod = native.load("l3_dcg_grammar", GRAMMAR)
    assert [_n(r) for r in ans(mod, goal)] == [_n(SCRYER[goal])]


def test_a_variable_body_with_a_disjunction_leaves_the_rest_open(native, ans):
    """Scryer: phrase(v(([x];[y])), L, Rest) gives L = [x|Rest] and
    L = [y|Rest]."""
    mod = native.load("l3_dcg_var_body", GRAMMAR + textwrap.dedent("""\
        t14(R) :- findall(L-Rest, phrase(v(([x];[y])), L, Rest), R0),
                  findall(H-T, (member(L-Rest, R0), L = [H|T0], T0 == Rest,
                                T = open), R).
        """))
    assert ans(mod, "t14") == [[("-", "x", "open"), ("-", "y", "open")]]


@pytest.mark.parametrize("flag, want", [
    ("codes", [[97, 98]]),
    ("chars", [["a", "b"]]),
])
def test_a_string_terminal_follows_the_double_quotes_flag(native, ans, flag,
                                                         want):
    mod = native.load(f"l3_dcg_dq_{flag}", textwrap.dedent(f"""\
        :- set_prolog_flag(double_quotes, {flag}).
        g --> "ab".
        t(R) :- findall(L, phrase(g, L), R).
        """))
    assert [_n(r) for r in ans(mod, "t")] == [want]


def test_a_string_under_double_quotes_atom_names_a_nonterminal(native, ans):
    """Scryer: under double_quotes atom, "abc" in a grammar body is the
    atom abc, the nonterminal abc//0."""
    mod = native.load("l3_dcg_dq_atom", textwrap.dedent("""\
        :- set_prolog_flag(double_quotes, atom).
        abc --> [x].
        g --> "abc".
        t(R) :- findall(L, phrase(g, L), R).
        """))
    assert [_n(r) for r in ans(mod, "t")] == [[["x"]]]


def test_the_bar_needs_library_dcgs_as_in_scryer(native):
    """``|`` is library(dcgs)'s op(1105, xfy, '|'): without the import the
    rule does not read (Scryer: syntax_error(incomplete_reduction))."""
    with pytest.raises(SyntaxError) as ei:
        native.load("l3_dcg_bar_noimport", "ab --> [a] | [b].\n")
    assert "syntax error" in str(ei.value)


CUT_FREE = ("Clausal is cut-free with no committed choice, by design "
            "(ruling): !, -> and *-> are refused")


@pytest.mark.parametrize("name, rule, clause", [
    ("bang", "s --> [a], !.", "s :- a, !."),
    ("bang_whole", "s --> !.", "s :- !."),
    ("brace_bang", "s --> {!}.", "s :- !."),
    ("brace_bang_seq", "s --> [a], {!}.", "s :- a, !."),
    ("ite", "s --> ([a] -> [b] ; [c]).", "s :- (a -> b ; c)."),
    ("it", "s --> [a] -> [b].", "s :- a -> b."),
    ("brace_ite", "s --> {a -> b ; c}.", "s :- (a -> b ; c)."),
    ("call_bang", "s --> call(!).", "s :- call(!)."),
])
def test_cut_and_if_then_are_refused_as_in_a_clause_body(native, name, rule,
                                                        clause):
    """The DCG refusal is the clause-body refusal, word for word."""
    def refusal(text, mod):
        with pytest.raises(SyntaxError) as ei:
            native.load(mod, "a. b. c.\n" + text + "\n")
        assert ei.value.lineno == 2
        msg = str(ei.value)
        return msg.split(f"{mod}.pl:2: ", 1)[1].rsplit(" (", 1)[0]
    got = refusal(rule, f"l3_dcg_cut_{name}")
    want = refusal(clause, f"l3_dcg_cutc_{name}")
    assert got == want and CUT_FREE in got, (got, want)


@pytest.mark.parametrize("rule, fragment", [
    ("s --> \\+ [a], [b].", "representation_error(dcg_body)"),
    ("s --> [a|_].", "partial list"),
    ("s --> [a|b].", "improper list"),
    ("s, foo --> [a].", "pushback foo is not a list"),
    ("X --> [a].", "head is a variable"),
    ("m:s --> [a].", "module-qualified head"),
    ("s --> 3.", "not callable"),
])
def test_what_scryer_refuses_in_a_grammar_rule_is_refused(native, rule,
                                                         fragment):
    with pytest.raises(SyntaxError) as ei:
        native.load("l3_dcg_refused", "a.\n" + rule + "\n")
    assert fragment in str(ei.value) and ei.value.lineno == 2, str(ei.value)


# ── modules: name//N in export and import lists ──

LIB = """\
:- module(l3dcg_lib, [greeting//0, word//1]).
greeting --> [hello], word(_).
word(W) --> [W].
"""


def _lib(native, name="l3dcg_lib"):
    (native.tmp / f"{name}.pl").write_text(LIB.replace("l3dcg_lib", name),
                                           encoding="utf-8")


def test_an_import_of_name_slash_slash_n_brings_only_that_nonterminal(
        native, ans):
    """Scryer: t -> [[hello,_]], t2 -> existence_error(procedure, word/3),
    t3 -> [[]]."""
    _lib(native, "l3dcg_lib1")
    mod = native.load("l3_dcg_imp1", textwrap.dedent("""\
        :- use_module(l3dcg_lib1, [greeting//0]).
        t(R) :- findall(L, phrase(greeting, L), R0),
                findall(H, member([H, _], R0), R).
        t2(R) :- catch((phrase(word(X), [a]), R = X), error(E, _), R = E).
        t3(R) :- findall(L, phrase(greeting, [hello, there], L), R).
        """))
    assert ans(mod, "t") == [["hello"]]
    assert ans(mod, "t2") == [("existence_error", "procedure",
                               ("/", "word", 3))]
    assert ans(mod, "t3") == [[[]]]


@pytest.mark.parametrize("imports", ["[word/3]", "[word//1]", None])
def test_a_nonterminal_imports_as_name_n_plus_2_or_listless(native, ans,
                                                            imports):
    """Scryer: word//1 is word/3 -- either spelling imports it, and a
    listless use_module brings every export."""
    _lib(native, "l3dcg_lib2")
    spec = "l3dcg_lib2" if imports is None else f"l3dcg_lib2, {imports}"
    tag = {None: "none", "[word/3]": "pi", "[word//1]": "nt"}[imports]
    mod = native.load(f"l3_dcg_imp2_{tag}", textwrap.dedent(f"""\
        :- use_module({spec}).
        t(R) :- findall(X-L, phrase(word(X), [a], L), R).
        """))
    assert [_n(r) for r in ans(mod, "t")] == [[("-", "a", [])]]


def test_an_exported_nonterminal_is_qualified_callable(native, ans):
    _lib(native, "l3dcg_lib3")
    mod = native.load("l3_dcg_imp3", textwrap.dedent("""\
        :- use_module(l3dcg_lib3, []).
        :- use_module(l3dcg_lib3, [word//1]).
        s --> l3dcg_lib3:word(x), [y].
        t(R) :- findall(L, phrase(s, L), R).
        """))
    assert [_n(r) for r in ans(mod, "t")] == [[["x", "y"]]]


def test_a_grammar_rule_counts_as_a_lowered_clause(native):
    mod = native.load("l3_dcg_stats", "a --> [x].\nb --> a, a.\n")
    st = mod.__loader__.l3_stats
    assert st["read"] == 2 and st["lowered"] == 2 and st["refused"] == 0


def test_translate_dcg_rule_gives_scryers_clause():
    """The translation itself: Scryer's dcg_rule/2 for a pushback rule."""
    from clausal.tools.iso_l3 import read_iso, translate_dcg_rule
    from clausal.tools.prolog_reader import VarRef
    it = read_iso("look(X), [X] --> [X], {true}.\n")[0]
    clause, _spans, names = translate_dcg_rule(it.term, it.spans,
                                               it.var_names)
    x = VarRef(0)
    s0, s, s1, mid = (VarRef(i) for i in (1, 2, 3, 4))
    assert clause == (":-", ("look", x, s0, s),
                      (",", (",", ("=", s0, (".", x, mid)),
                             (",", "true", ("=", mid, s1))),
                       ("=", s, (".", x, s1))))
    assert all(names[v.i].startswith("_") for v in (s0, s, s1, mid))
