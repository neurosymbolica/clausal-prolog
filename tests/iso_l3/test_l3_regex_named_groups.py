"""Regex named-group auto-binding in Clausal Prolog (``.clausal``).

A static ``match/2`` / ``search/2`` pattern from ``library(re)`` whose group
names are spelled like variables binds each group to the clause variable of
exactly that name (``clausal/logic/goal_expansion.py``).  The goal expansion
reads the names from ``Predicate.var_names``, which the native front end
fills from the reader's variable names: before it did, a ``.clausal`` head
arrived with positional ``arg_0..`` fields and every group bound a fresh
variable, so ``parse_date("2024-03", Y, M)`` succeeded with ``Y`` and ``M``
unbound (todo/clausal-surface-gaps-found-moving-the-docs-2026-10-17.md,
engine bugs, item 3).

The behaviour itself is pinned by the ``test/1`` clauses of
``tests/fixtures/regex_named_groups.clausal``; this file loads that fixture
under the native front end, and checks what the clauses cannot: the
singleton lint, and that a group which names no variable stays regex-only.
"""
from __future__ import annotations

import pathlib
import warnings

import pytest

from clausal import import_hook as ih
from clausal.logic.cells import chars

FIXTURE = (pathlib.Path(__file__).resolve().parent.parent / "fixtures"
           / "regex_named_groups.clausal")

HEAD = """\
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re), [match/2, search/2]).
"""


def _load(native, name, body, head=HEAD):
    """Load ``head + body`` as a ``.clausal`` file through the native
    front end, returning (module, singleton warning messages)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = native.load(name, head + body, suffix=".clausal")
    assert type(mod.__loader__) is ih.NativePrologLoader
    singles = [str(w.message) for w in caught
               if "singleton" in str(w.message)]
    return mod, singles


def test_the_fixture_runs_natively_and_every_test_passes():
    from clausal.testing import run_file
    results = run_file(FIXTURE).results
    assert len(results) == 11, [r.name for r in results]
    failed = [(r.name, r.error) for r in results if not r.passed]
    assert not failed, failed


def test_head_variables_bind(native, ans):
    mod, _ = _load(native, "rx_head", """\
parse_date(D, YEAR, MONTH) :- match("(?P<YEAR>\\\\d{4})-(?P<MONTH>\\\\d{2})", D).
""")
    assert ans(mod, "parse_date", 3, chars("2024-03")) == [
        (chars("2024"), chars("03"))]


def test_body_variable_binds(native, ans):
    mod, _ = _load(native, "rx_body", """\
body_year(D, Y) :- match("(?P<YEAR>\\\\d{4})", D), Y = YEAR.
""")
    assert ans(mod, "body_year", 2, chars("2024")) == [chars("2024")]


def test_a_lowercase_group_binds_nothing(native, ans):
    """A lowercase group name is an atom spelling, so it is regex-only: the
    head variable YEAR is not the group ``year``."""
    mod, singles = _load(native, "rx_lower", """\
lower(D, YEAR) :- match("(?P<year>\\\\d{4})", D).
""")
    from clausal.logic.variables import is_var
    [answer] = ans(mod, "lower", 2, chars("2024"))
    assert is_var(answer)
    # ... and so YEAR really is a singleton
    assert any("`YEAR`" in m for m in singles), singles


def test_a_group_named_variable_is_not_a_singleton(native):
    """The singleton lint counts a variable-shaped group of a static
    library(re) pattern as an occurrence of that variable: the group binds
    it, so "binds nothing" would be false."""
    _, singles = _load(native, "rx_single", """\
parse_date(D, YEAR, MONTH) :- match("(?P<YEAR>\\\\d{4})-(?P<MONTH>\\\\d{2})", D).
port(URL, PORT) :- search(":(?P<PORT>\\\\d+)", URL).
""")
    assert singles == []


def test_a_variable_no_group_names_is_still_a_singleton(native):
    _, singles = _load(native, "rx_single2", """\
f(D, YEAR, OTHER) :- match("(?P<YEAR>\\\\d{4})", D).
""")
    assert len(singles) == 1 and "`OTHER`" in singles[0], singles


# A group binds only where goal expansion reaches it: the clause body's
# control constructs.  It never descends into a meta-argument (once/1,
# catch/3, forall/2, findall/3 ...), and a binding under \+ never escapes
# it, so a group there binds nothing, and the singleton lint must not count
# it either.
@pytest.mark.parametrize("name, body", [
    ("once_group", 'once(match("(?P<X>\\\\d+)", S))'),
    ("catch_group", 'catch(match("(?P<X>\\\\d+)", S), _, true)'),
    ("forall_group", 'forall(match("(?P<X>\\\\d+)", S), true)'),
    ("naf_group", '\\+ match("(?P<X>\\\\d+)x", S)'),
    ("once_qualified", 'once(re:match("(?P<X>\\\\d+)", S))'),
    ("findall_qualified", 'findall(x, re:search("(?P<X>\\\\d+)", S), _)'),
])
def test_a_group_inside_a_meta_argument_binds_nothing_and_is_a_singleton(
        native, ans, name, body):
    from clausal.logic.variables import is_var
    mod, singles = _load(native, "rx_" + name,
                         f"{name}(S, X) :- {body}.\n")
    assert any("`X`" in m for m in singles), singles
    [answer] = ans(mod, name, 2, chars("42"))
    assert is_var(answer)


# ── module-qualified calls ──────────────────────────────────────────────────
#
# ``re:match(P, S)`` lowers to the dotted call ``clausal.library.re.match``;
# goal expansion resolves that callee the way the compiler does and binds
# its groups exactly as it does an unqualified call's.

WHOLE_MODULE = """\
:- set_prolog_flag(double_quotes, chars).
:- use_module(library(re)).
"""


@pytest.mark.parametrize("head", [HEAD, WHOLE_MODULE],
                         ids=["import_list", "whole_module"])
def test_a_qualified_call_binds_its_groups(native, ans, head):
    mod, singles = _load(native, "rx_qual_" + str(len(head)), """\
qdate(D, YEAR, MONTH) :- re:match("(?P<YEAR>\\\\d{4})-(?P<MONTH>\\\\d{2})", D).
qport(URL, PORT) :- re:search(":(?P<PORT>\\\\d+)", URL).
qbody(D, Y) :- re:match("(?P<YEAR>\\\\d{4})", D), Y = YEAR.
""", head=head)
    assert ans(mod, "qdate", 3, chars("2024-03")) == [
        (chars("2024"), chars("03"))]
    assert ans(mod, "qport", 2, chars("http://h:8080/")) == [chars("8080")]
    assert ans(mod, "qbody", 2, chars("2024")) == [chars("2024")]
    # ... and the singleton lint counts the groups, as it does unqualified
    assert singles == [], singles


def test_a_qualified_dynamic_pattern_binds_at_run_time(native, ans):
    mod, _ = _load(native, "rx_qual_dyn", """\
qdyn(P, S, YEAR) :- re:match(P, S).
""")
    assert ans(mod, "qdyn", 3, chars("(?P<YEAR>\\d{4})"),
               chars("2024")) == [chars("2024")]


def test_a_qualified_lowercase_group_is_still_a_singleton(native):
    _, singles = _load(native, "rx_qual_lower", """\
lower(D, YEAR) :- re:match("(?P<year>\\\\d{4})", D).
""")
    assert any("`YEAR`" in m for m in singles), singles


def test_another_modules_match_is_not_expanded(native, ans, tmp_path):
    """A qualified ``match/2`` of a module that is not library(re) is that
    module's predicate: its pattern argument is passed through untouched,
    and a group-shaped name in it binds nothing (nor counts for the
    singleton lint)."""
    (tmp_path / "rx_other_re.clausal").write_text(
        ":- module(rx_other_re, [match/2]).\n"
        "match(P, P).\n"
        ":- end_module(rx_other_re).\n", encoding="utf-8")
    mod, singles = _load(native, "rx_other_user", """\
:- use_module(rx_other_re).
other(D, YEAR) :- rx_other_re:match("(?P<YEAR>x)", D).
""")
    from clausal.logic.variables import is_var
    [answer] = ans(mod, "other", 2, chars("(?P<YEAR>x)"))
    assert is_var(answer)
    assert any("`YEAR`" in m for m in singles), singles


def test_a_spelled_out_qualifier_without_an_import_is_still_a_singleton(
        native):
    """The lint counts a qualified call's groups only through a module
    alias a use_module of library(re) recorded: a spelled-out module path
    imports nothing, so whether its groups bind depends on what loaded
    first, and the lint does not vouch for it."""
    _, singles = _load(native, "rx_qual_spelled", """\
fqdate(D, YEAR) :- 'clausal.library.re':match("(?P<YEAR>\\\\d{4})", D).
""", head=":- set_prolog_flag(double_quotes, chars).\n")
    assert any("`YEAR`" in m for m in singles), singles


# ── term expansion ──────────────────────────────────────────────────────────
#
# A clause term expansion hands back unchanged (the identity rule, or the
# clause inside a one-to-many list) is the very clause node the front end
# built, so it keeps its variable-name table and its groups bind.  A clause
# a term_expansion rule BUILDS has no table (docs/regex.md, Auto-Binding).

@pytest.mark.parametrize("rule, copies", [
    ("term_expansion(T, T, S, S).", 1),
    ("term_expansion(T, [T], S, S).", 1),
    ("term_expansion(T, [T, T], S, S).", 2),
], ids=["identity", "singleton_list", "duplicated"])
def test_a_clause_term_expansion_returns_unchanged_still_binds(
        native, ans, rule, copies):
    mod, singles = _load(native, "rx_te_" + str(len(rule)), f"""\
{rule}
pd(D, YEAR, MONTH) :- match("(?P<YEAR>\\\\d{{4}})-(?P<MONTH>\\\\d{{2}})", D).
qd(D, YEAR) :- re:match("(?P<YEAR>\\\\d{{4}})", D).
""")
    assert ans(mod, "pd", 3, chars("2024-03")) == [
        (chars("2024"), chars("03"))] * copies
    assert ans(mod, "qd", 2, chars("2024")) == [chars("2024")] * copies
    assert singles == [], singles
