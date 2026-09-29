"""Slice 2: directives and modules on the native ``.pl`` front end (plan
native-iso-reader-step2 §4 Slice 2, D10-D12).

Every directive goes through the SEAM's own handler with synthesized
arguments (§1.5); these tests pin what each ISO directive does and that each
refusal is an import-time ``SyntaxError`` naming the ``.pl`` line.  Every load
clears ``__pycache__`` and asserts the native loader ran over a non-zero
population (the ``native`` fixture).
"""
from __future__ import annotations

import importlib
import sys
import textwrap
import warnings

import pytest

from clausal.lint_warnings import ClausalBareAtomImportWarning
from clausal.tools import iso_l3 as L3


def _write(native, rel: str, text: str) -> None:
    path = native.tmp / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    init = path.parent / "__init__.py"
    if path.parent != native.tmp and not init.exists():
        init.write_text("")
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    dotted = rel.rsplit(".", 1)[0].replace("/", ".")
    native._names.append(dotted)
    native._names.append(dotted.split(".")[0])


def _refusal(native, name, text):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, textwrap.dedent(text))
    assert name not in sys.modules
    return ei.value


# ── module/2 ──


def test_module_exports_and_its_op_entries_govern_its_own_clauses(native, ans):
    mod = native.load("s2_mod", ":- module(s2_mod, [p/1, op(700, xfx, ===>)]).\n"
                                "p(a ===> b).\np(c).\n")
    assert ans(mod, "p") == [("===>", "a", "b"), "c"]
    assert mod.__loader__.l3_stats["directives"] == 1


def test_a_module_export_entry_that_is_no_indicator_is_refused(native):
    err = _refusal(native, "s2_badexp", ":- module(s2_badexp, [p/1, foo]).\n"
                                        "p(1).\n")
    assert err.lineno == 1 and "foo is not a predicate indicator" in str(err)


# ── use_module ──


LIB_PL = """\
    :- module(s2plib, [twice/2, pair/2, op(200, xfy, ^^)]).
    twice(X, Y) :- Y is 2 * X.
    pair(a, 1).
    pair(b, 2).
    hidden(z).
    """

LIB_SEAM = """\
    -module(s2slib, [triple/2, kind/1])
    -private([vowel])
    triple(X, Y) <- (Y == 3 * X)
    kind(vowel)
    """


@pytest.mark.parametrize("spec", ["s2p/s2plib", "'s2p/s2plib'"])
def test_use_module_1_of_a_pl_module_by_either_path_spelling(native, ans, spec):
    _write(native, "s2p/s2plib.pl", LIB_PL)
    mod = native.load("s2_use1", f":- use_module({spec}).\n"
                                 "t(Y) :- twice(3, Y).\n"
                                 "t(K) :- pair(K, _).\n"
                                 "t(X) :- X = (a ^^ b).\n")
    assert ans(mod, "t") == [6, "a", "b", ("^^", "a", "b")]


def test_use_module_2_imports_only_the_listed_predicates(native, ans):
    _write(native, "s2p/s2plib.pl", LIB_PL)
    mod = native.load("s2_use2", ":- use_module(s2p/s2plib, [pair/2]).\n"
                                 "t(K) :- pair(K, _).\n")
    assert ans(mod, "t") == ["a", "b"]
    assert not mod.__dict__.get("twice")


def test_a_pl_module_imports_a_seam_module_and_vice_versa(native, ans):
    _write(native, "s2p/s2plib.pl", LIB_PL)
    _write(native, "s2p/s2slib.seam", textwrap.dedent(LIB_SEAM) + textwrap.dedent("""\
        -import_from(s2p.s2plib, [twice/2])
        six(Y) <- twice(3, Y)
        """))
    mod = native.load("s2_mixed", ":- use_module(s2p/s2slib).\n"
                                  "t(Y) :- triple(2, Y).\n"
                                  "t(K) :- kind(K).\n")
    assert ans(mod, "t") == [6, "vowel"]
    seam = importlib.import_module("s2p.s2slib")
    assert ans(seam, "six") == [6]
    assert type(sys.modules["s2p.s2plib"].__loader__).__name__ \
        == "NativePrologLoader"


def test_a_qualified_call_reaches_the_module_beside_a_local_predicate(
        native, ans):
    """D10: a name clash is resolved by qualification (batch G's pinned
    behaviour, on the native path): facts:pair/2 is the module's, even though
    it is NOT imported and the file defines its own pair/2."""
    _write(native, "s2p/s2plib.pl", LIB_PL)
    mod = native.load("s2_qual", ":- use_module(s2p/s2plib, [twice/2]).\n"
                                 "pair(local, 0).\n"
                                 "theirs(K) :- s2plib:pair(K, _).\n"
                                 "hid(X) :- s2plib:hidden(X).\n"
                                 "mine(K) :- pair(K, _).\n"
                                 "lib(L) :- lists:append([1], [2], L).\n")
    assert ans(mod, "theirs") == ["a", "b"]
    assert ans(mod, "hid") == ["z"]
    assert ans(mod, "mine") == ["local"]
    assert ans(mod, "lib") == [[1, 2]]


def test_use_module_1_of_a_module_without_an_export_list_is_refused(native):
    _write(native, "s2p/plain.pl", "q(1).\n")
    err = _refusal(native, "s2_noexp", "a.\n:- use_module(s2p/plain).\n")
    assert err.lineno == 2 and "declares no module/2 export list" in str(err)


def test_a_missing_module_is_a_located_error(native):
    err = _refusal(native, "s2_missing", "a.\n:- use_module(nope/nothere).\n")
    assert err.lineno == 2 and "no module nope.nothere" in str(err)


@pytest.mark.parametrize("lib", ["lists", "apply", "dif"])
def test_built_in_libraries_import_nothing(native, ans, lib):
    mod = native.load(f"s2_lib_{lib}",
                      f":- use_module(library({lib})).\n"
                      "t(L) :- append([1], [2], L).\n"
                      "t(L) :- maplist(integer, [1]), L = ok.\n"
                      "t(L) :- dif(L, a), L = b.\n")
    assert ans(mod, "t") == [[1, 2], "ok", "b"]


def test_library_reif_imports_from_the_stdlib_module(native, ans):
    mod = native.load("s2_reif",
                      ":- use_module(library(reif), [memberd_t/3, if_/3]).\n"
                      "t(T) :- memberd_t(b, [a, b], T).\n")
    assert ans(mod, "t") == [True]


def test_library_clpz_adds_its_operators_to_the_reader_table(native, ans):
    mod = native.load("s2_clpz",
                      ":- use_module(library(clpz)).\n"
                      "t(X) :- X #= 1 + 2.\n"
                      "d(x in 1..3).\n"
                      "d(#\\ a).\n")
    assert ans(mod, "t") == [3]
    assert ans(mod, "d") == [("in", "x", ("..", 1, 3)), ("#\\", "a")]


def test_without_library_clpz_its_operators_do_not_read(native):
    err = _refusal(native, "s2_noclpz", "a.\nd(X in 1..3).\n")
    assert err.lineno == 2 and "syntax error" in str(err)


def test_a_clpz_import_the_engine_lacks_is_refused_by_name(native):
    # (in/2 was the example here until slice 5 made it a builtin, then
    # fd_dom/2 until it became one.)
    err = _refusal(native, "s2_clpz_in",
                   ":- use_module(library(clpz), [(#=)/2, lex_chain/1]).\n")
    assert err.lineno == 1 and "lex_chain/1 is not available" in str(err)


def test_an_unknown_library_is_a_located_error(native):
    err = _refusal(native, "s2_unklib", "a.\n:- use_module(library(nosuch)).\n")
    assert err.lineno == 2 and "library(nosuch)" in str(err)


# ── D10 refusals ──


@pytest.mark.parametrize("spec", ["'./s2p/s2plib'", "'../s2p/s2plib'",
                                  "'/abs/s2plib'"])
def test_a_relative_or_absolute_path_is_refused(native, spec):
    _write(native, "s2p/s2plib.pl", LIB_PL)
    err = _refusal(native, "s2_rel", f"a.\n\n:- use_module({spec}).\n")
    assert err.lineno == 3 and "ruling D10" in str(err), str(err)


def test_as_aliasing_is_refused_as_scryer_reads_it(native):
    """Scryer has no `as` operator, so the reader gives a syntax error; the
    message says why."""
    _write(native, "s2p/s2plib.pl", LIB_PL)
    err = _refusal(native, "s2_as",
                   "a.\n:- use_module(s2p/s2plib, [pair/2 as duo]).\n")
    assert err.lineno == 2 and "aliasing with `as` is refused" in str(err)


def test_as_aliasing_in_canonical_form_is_refused_too(native):
    _write(native, "s2p/s2plib.pl", LIB_PL)
    err = _refusal(native, "s2_as2",
                   "a.\n:- use_module(s2p/s2plib, [as(pair/2, duo)]).\n")
    assert err.lineno == 2 and "aliasing with `as` is refused" in str(err)


def test_an_empty_import_list_with_a_path_is_a_domain_error(native):
    _write(native, "s2p/s2plib.pl", LIB_PL)
    err = _refusal(native, "s2_empty", "a.\n:- use_module(s2p/s2plib, []).\n")
    assert err.lineno == 2 and "module_specifier" in str(err)


# ── D11: bare atoms in an import list ──


def test_bare_atoms_in_import_lists_give_one_counted_warning_per_file(
        native, ans):
    _write(native, "s2p/s2plib.pl", LIB_PL)
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        mod = native.load("s2_bare",
                          "a.\n:- use_module(s2p/s2plib, [s2_cite_atom, pair/2]).\n"
                          ":- use_module(s2p/s2plib, [twice/2, s2_rule_atom]).\n"
                          "t(K) :- pair(K, _).\n")
    ours = [w for w in got if w.category is ClausalBareAtomImportWarning]
    assert len(ours) == 1, [str(w.message) for w in got]
    msg = str(ours[0].message)
    assert "2 bare atom entries" in msg and "(s2_cite_atom, s2_rule_atom)" in msg, msg
    assert "s2_bare.pl:2" in msg
    assert ans(mod, "t") == ["a", "b"]
    # Nothing is imported from s2plib; the entry is a USE of the global atom,
    # which slice 3 auto-declares (bound to its own spelling, as a seam
    # facade's -import_from of an atom binds it).
    assert mod.__dict__.get("s2_cite_atom") == "s2_cite_atom"
    assert "s2_cite_atom" not in vars(sys.modules["s2p.s2plib"])


# ── D12 and unknown directives ──


@pytest.mark.parametrize("text, fragment", [
    (":- initialization(main).", "initialization/1 is refused (ruling D12)"),
    (":- initialization(main, now).", "initialization/2 is refused"),
    (":- ensure_loaded(foo).", "unknown directive ensure_loaded/1"),
    (":- foo.", "unknown directive foo/0"),
    (":- dynamic d/1.", "syntax error"),     # D2: Scryer's prefix-free table
    ("?- a.", "Query is not lowered"),
])
def test_refused_directives_name_their_line(native, text, fragment):
    err = _refusal(native, "s2_refd", "a.\n\n" + text + "\n")
    assert err.lineno == 3 and fragment in str(err), str(err)


# ── dynamic, discontiguous, table, meta_predicate ──


def test_dynamic_in_every_iso_spelling_and_assertz(native, ans):
    mod = native.load("s2_dyn", ":- dynamic(d/1).\n"
                                ":- dynamic([e/1, f/2]).\n"
                                ":- dynamic((g/1, h/0)).\n"
                                "add(X) :- assertz(d(X)), assertz(g(X)).\n"
                                "get(X-Y) :- add(1), d(X), g(Y).\n"
                                "none(X) :- e(X).\n")
    assert ans(mod, "get") == [("-", 1, 1)]
    assert ans(mod, "none") == []


def test_assert_creates_dynamic_for_an_undeclared_predicate(native, ans):
    mod = native.load("s2_acd", "add(X) :- assertz(jotting(X)).\n"
                                "all(L) :- add(a), add(b), findall(X, jotting(X), L).\n")
    assert ans(mod, "all") == [["a", "b"]]


def test_table_discontiguous_and_meta_predicate(native, ans):
    mod = native.load("s2_tdm", ":- table(fib/2).\n"
                                ":- discontiguous(k/1).\n"
                                ":- meta_predicate(twice(0)).\n"
                                "k(1).\n"
                                "fib(0, 0).\nfib(1, 1).\n"
                                "fib(N, F) :- N > 1, A is N-1, B is N-2, "
                                "fib(A, FA), fib(B, FB), F is FA+FB.\n"
                                "twice(G) :- call(G), call(G).\n"
                                "k(2).\n"
                                "t(F) :- fib(15, F).\n"
                                "t(ok) :- twice(k(1)).\n")
    assert ans(mod, "t") == [610, "ok"]
    assert ans(mod, "k") == [1, 2]


def test_a_malformed_predicate_indicator_is_a_located_error(native):
    err = _refusal(native, "s2_badpi", "a.\n:- dynamic(foo).\n")
    assert err.lineno == 2 and "not a predicate indicator" in str(err)


# ── set_prolog_flag, op/3 ──


def test_double_quotes_is_honoured_per_literal(native, ans):
    mod = native.load("s2_dq", "c(X) :- X = \"ab\".\n"
                               ":- set_prolog_flag(double_quotes, codes).\n"
                               "d(X) :- X = \"ab\".\n"
                               ":- set_prolog_flag(double_quotes, atom).\n"
                               "e(X) :- X = \"ab\".\n"
                               ":- set_prolog_flag(double_quotes, chars).\n"
                               "f(X) :- X = \"ab\".\n"
                               "g :- f([a, b]).\n")
    assert ans(mod, "c") == [("$chars", "ab")]
    assert ans(mod, "d") == [[97, 98]]
    assert ans(mod, "e") == ["ab"]
    assert ans(mod, "f") == [("$chars", "ab")]
    assert ans(mod, "g", 0) == [()]


def test_the_double_quotes_mode_is_reported_by_current_prolog_flag(native, ans):
    mod = native.load("s2_dqf", ":- set_prolog_flag(double_quotes, atom).\n"
                                "m(M) :- current_prolog_flag(double_quotes, M).\n")
    assert ans(mod, "m") == ["atom"]


def test_a_bad_double_quotes_value_is_refused(native):
    err = _refusal(native, "s2_dqbad",
                   "a.\n:- set_prolog_flag(double_quotes, bytes).\n")
    assert err.lineno == 2 and "domain_error(flag_value" in str(err)


def test_another_flag_goes_through_the_seam_handler(native, ans):
    mod = native.load("s2_flag",
                      ":- set_prolog_flag(assert_creates_dynamic, false).\n"
                      "m(V) :- current_prolog_flag(assert_creates_dynamic, V).\n")
    # The engine answers a boolean flag as Python False (plan §1.4), the
    # seam path's answer too.
    assert ans(mod, "m") == [False]
    err = _refusal(native, "s2_flag2", "a.\n:- set_prolog_flag(bounded, false).\n")
    assert err.lineno == 2 and "permission_error" in str(err), str(err)


def test_op_3_is_applied_by_the_reader_and_checked(native, ans):
    mod = native.load("s2_op", ":- op(200, xfy, ^^).\np(a ^^ b ^^ c).\n")
    assert ans(mod, "p") == [("^^", "a", ("^^", "b", "c"))]
    err = _refusal(native, "s2_opbad", "a.\n:- op(1201, xfx, foo).\n")
    assert err.lineno == 2 and "operator_priority" in str(err)


# ── the cache-hit path ──


def test_the_cache_hit_path_re_lowers_only_the_directives(native, ans):
    text = (":- dynamic(d/1).\n:- set_prolog_flag(double_quotes, atom).\n"
            "add :- assertz(d(1)).\nget(X) :- add, d(X).\n"
            "m(M) :- current_prolog_flag(double_quotes, M).\n")
    mod = native.load("s2_hit", text)
    assert ans(mod, "get") == [1] and ans(mod, "m") == ["atom"]
    # Load again WITHOUT clearing __pycache__: served from the cache.
    from clausal import import_hook as ih
    calls = []
    orig = ih.NativePrologLoader.source_to_code

    def spy(self, data, path="<string>"):
        calls.append(path)
        return orig(self, data, path)
    native._mp.setattr(ih.NativePrologLoader, "source_to_code", spy)
    sys.modules.pop("s2_hit", None)
    importlib.invalidate_caches()
    mod2 = importlib.import_module("s2_hit")
    assert calls == [], "the second load was not a cache hit"
    st = mod2.__loader__.l3_stats
    assert st["directives"] == 2 and st["skipped"] == 3 and st["lowered"] == 2
    assert ans(mod2, "get") == [1] and ans(mod2, "m") == ["atom"]


# ── the translator stays the default ──


def test_with_the_variable_unset_the_translator_loads_use_module(native, ans):
    _write(native, "s2p/s2plib.pl", LIB_PL)
    mod = native.load("s2_tr", ":- use_module(s2p/s2plib, [pair/2]).\n"
                               "t(K) :- pair(K, _).\n", frontend=None)
    assert type(mod.__loader__).__name__ == "PrologLoader"
    assert ans(mod, "t") == ["a", "b"]


def test_directive_lowering_needs_no_loader(native):
    """lower_items counts directives with the rest of the population."""
    src = ":- dynamic(d/1).\nd(1).\n:- discontiguous(d/1).\n"
    _, st = L3.lower_items(L3.read_iso(src), source=src, filename="x.pl")
    assert (st["read"], st["lowered"], st["directives"]) == (3, 3, 2), st


# ── review round: dependencies, module names, the cache ──


def test_a_module_that_baked_in_another_files_exports_is_not_cached(native):
    """use_module/1 copies the target's export list into this file's code;
    the cache key covers this file only, so the bytecode is not written.
    use_module/2 of a module that exports op/3s reads that module's source
    too (which of its ops arrive -- slice 5), so it is not cached either;
    use_module/2 of one exporting no op is."""
    _write(native, "s2p/s2plib.pl", LIB_PL)
    _write(native, "s2p/s2pnoop.pl", LIB_PL.replace(", op(200, xfy, ^^)", "")
           .replace("s2plib", "s2pnoop"))
    def written():   # (each load clears __pycache__ first)
        return {p.name.split(".")[0]
                for p in native.tmp.glob("__pycache__/*.pyc")}
    native.load("s2_dep3", ":- use_module(s2p/s2plib, [pair/2]).\n"
                           "t(K) :- pair(K, _).\n")
    assert "s2_dep3" not in written(), written()
    native.load("s2_dep1", ":- use_module(s2p/s2plib).\nt(Y) :- twice(1, Y).\n")
    native.load("s2_dep2", ":- use_module(s2p/s2pnoop, [pair/2]).\n"
                           "t(K) :- pair(K, _).\n")
    assert "s2_dep2" in written() and "s2_dep1" not in written(), written()


def test_a_qualified_goal_through_an_unknown_module_fails_when_called(
        native, ans):
    """As in Scryer (D27): resolved when the goal runs, an existence_error
    unless some module loaded it."""
    from clausal.predicate_diagnostics import PredicateNotFoundError
    mod = native.load("s2_qunk", "a.\nt(X) :- nosuchmod:p(X).\n")
    with pytest.raises(PredicateNotFoundError, match="nosuchmod"):
        ans(mod, "t")


def test_a_module_name_two_imports_claim_is_ambiguous(native):
    _write(native, "s2a/lib.pl", ":- module(lib, [p/1]).\np(a).\n")
    _write(native, "s2b/lib.pl", ":- module(lib, [q/1]).\nq(b).\n")
    err = _refusal(native, "s2_amb", ":- use_module(s2a/lib, [p/1]).\n"
                                     ":- use_module(s2b/lib, [q/1]).\n"
                                     "t(X) :- lib:p(X).\n")
    assert err.lineno == 3 and "ambiguous" in str(err), str(err)


def test_the_files_own_module_name_qualifies_a_local_goal(native, ans):
    mod = native.load("s2_own", ":- module(s2_own, [t/1]).\n"
                                "p(1).\nt(X) :- s2_own:p(X).\n")
    assert ans(mod, "t") == [1]


def test_the_cache_hit_path_keeps_the_double_quotes_modes_used(native):
    text = ":- set_prolog_flag(double_quotes, atom).\ns(X) :- X = \"ab\".\n"
    mod = native.load("s2_dqhit", text)
    fresh = [i for i in mod.__loader__._recover_module_items(
        mod.__file__) if type(i).__name__ == "DoubleQuotesMode"]
    assert len(fresh) == 1 and fresh[0].modes_used == ("atom",), fresh


# ── D27: use_module(M, []) is Scryer's remove_module/2 ──
#
# Measured against the Scryer binary (src/loader.pl remove_module/2), with
# m.pl = ":- module(m, [p/1, r/1]). p(1). p(2). r(9).":
#   use_module(m, [p/1]), use_module(m, [])  then p(X)  -> existence_error(procedure, p/1)
#   use_module(m, [])  alone, then m:p(X)                -> existence_error(procedure, p/1)
#   use_module(m, [p/1]), use_module(m, []) then m:p(X) -> 1 (m stays loaded)
#   ... use_module(m, []), use_module(m, [p/1]) then p   -> 1 (a re-import restores)
#   t(X) :- p(X). before both directives                -> existence_error (resolved at call)
#   use_module(pk/m, [])                                  -> domain_error(module_specifier, pk/m)

D27_LIB = ":- module(dzmod, [dzp/1, dzr/1]).\ndzp(1).\ndzp(2).\ndzr(9).\n"


def _existence_error(call_it):
    """The engine's existing existence_error shape: a PredicateNotFoundError
    whose ISO term is error(existence_error(procedure, dzp/1), dzp/1)."""
    from clausal.logic.exceptions import render_error_term
    from clausal.predicate_diagnostics import PredicateNotFoundError
    with pytest.raises(PredicateNotFoundError) as ei:
        call_it()
    term = render_error_term(ei.value.term)
    assert "existence_error(procedure,dzp/1)" in term.replace(" ", ""), term
    return ei.value


def test_d27_an_empty_list_drops_the_names_imported_from_the_module(
        native, ans):
    _write(native, "dzmod.pl", D27_LIB)
    mod = native.load("s2_d27a", "early(X) :- dzp(X).\n"
                                 ":- use_module(dzmod, [dzp/1]).\n"
                                 ":- use_module(dzmod, []).\n"
                                 "late(X) :- dzp(X).\n"
                                 "qual(X) :- dzmod:dzp(X).\n")
    _existence_error(lambda: ans(mod, "late"))
    _existence_error(lambda: ans(mod, "early"))
    assert ans(mod, "qual") == [1, 2]          # m stays loaded, as in Scryer
    assert not mod.__dict__.get("dzp")


def test_d27_a_re_import_after_the_drop_restores_the_name(native, ans):
    _write(native, "dzmod.pl", D27_LIB)
    mod = native.load("s2_d27b", ":- use_module(dzmod, [dzp/1]).\n"
                                 ":- use_module(dzmod, []).\n"
                                 ":- use_module(dzmod, [dzp/1]).\n"
                                 "t(X) :- dzp(X).\n")
    assert ans(mod, "t") == [1, 2]


def test_d27_an_empty_list_alone_does_not_load_the_module(native, ans):
    _write(native, "dzmod.pl", D27_LIB)
    sys.modules.pop("dzmod", None)
    mod = native.load("s2_d27c", ":- use_module(dzmod, []).\n"
                                 "t(X) :- dzmod:dzp(X).\n")
    assert "dzmod" not in sys.modules
    err = _existence_error(lambda: ans(mod, "t"))
    # The engine's own existence_error shape (PredicateNotFoundError).
    assert type(err).__name__ == "PredicateNotFoundError"
    assert "module 'dzmod' is not loaded" in str(err)


def test_d27_a_path_is_a_domain_error_as_in_scryer(native):
    _write(native, "dzp2/dzmod.pl", D27_LIB)
    err = _refusal(native, "s2_d27d", "a.\n:- use_module(dzp2/dzmod, []).\n")
    assert err.lineno == 2 and "domain_error(module_specifier" in str(err)


def test_d27_a_library_cannot_be_dropped_and_says_so(native):
    err = _refusal(native, "s2_d27e", "a.\n:- use_module(library(lists), []).\n")
    assert err.lineno == 2 and "remove_module/2" in str(err)


@pytest.fixture
def scryer_bin():
    import os
    s = "/workspace/scryer-prolog/target/release/scryer-prolog"
    if not os.path.exists(s):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip("the Scryer oracle is not built")
        pytest.fail(f"the Scryer oracle is not built at {s}")
    return s


@pytest.mark.parametrize("text, goal, want", [
    (":- use_module(dzmod, [dzp/1]).\n:- use_module(dzmod, []).\n"
     "t(X) :- dzp(X).\n", "t", "existence_error(procedure,dzp/1)"),
    (":- use_module(dzmod, []).\nt(X) :- dzmod:dzp(X).\n", "t",
     "existence_error(procedure,dzp/1)"),
    (":- use_module(dzmod, [dzp/1]).\n:- use_module(dzmod, []).\n"
     "t(X) :- dzmod:dzp(X).\n", "t", "[1,2]"),
])
def test_d27_scryer_answers_as_the_native_path(native, ans, scryer_bin,
                                               text, goal, want):
    import subprocess
    (native.tmp / "dzmod.pl").write_text(D27_LIB)
    (native.tmp / "dzmain.pl").write_text(text)
    proc = subprocess.run(
        [scryer_bin, "dzmain.pl"], cwd=native.tmp, capture_output=True,
        text=True, timeout=60,
        input=f"catch((findall(X, {goal}(X), L), write(L)), error(E, _), "
              f"write(E)), nl, halt.\n")
    assert proc.stdout.strip().splitlines()[-1] == want, proc.stdout
    sys.modules.pop("dzmod", None)
    native._names.append("dzmod")
    mod = native.load("s2_d27s", text)
    if want.startswith("["):
        assert ans(mod, goal) == [1, 2]
    else:
        _existence_error(lambda: ans(mod, goal))
