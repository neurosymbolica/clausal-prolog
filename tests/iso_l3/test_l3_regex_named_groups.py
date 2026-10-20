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


def _load(native, name, body):
    """Load ``HEAD + body`` as a ``.clausal`` file through the native
    front end, returning (module, singleton warning messages)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = native.load(name, HEAD + body, suffix=".clausal")
    assert type(mod.__loader__) is ih.NativePrologLoader
    singles = [str(w.message) for w in caught
               if "singleton" in str(w.message)]
    return mod, singles


def test_the_fixture_runs_natively_and_every_test_passes():
    from clausal.testing import run_file
    results = run_file(FIXTURE).results
    assert len(results) == 9, [r.name for r in results]
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
])
def test_a_group_inside_a_meta_argument_binds_nothing_and_is_a_singleton(
        native, ans, name, body):
    from clausal.logic.variables import is_var
    mod, singles = _load(native, "rx_" + name,
                         f"{name}(S, X) :- {body}.\n")
    assert any("`X`" in m for m in singles), singles
    [answer] = ans(mod, name, 2, chars("42"))
    assert is_var(answer)
