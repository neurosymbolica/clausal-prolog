"""The exporter prefers ISO / Scryer over SWI (operator rule, 2026-09-29).

A. The `iso` dialect (the exporter's default) spells `time_goal` as `time` and
   `all_different` as `all_distinct`, Scryer's names, both measured on Scryer
   and Trealla. `in_domain` and `divmod_` are left alone: the map's Scryer
   spellings for them are themselves wrong (see below).
B. The Dialect dataclass default library for CLP(Z) is `clpz`, the name Scryer
   and Trealla ship; `clpfd` is SWI's.
C. A directive whose functor is a prefix operator is emitted in functional
   notation, `:- discontiguous(p/1).`, which every reader parses. The prefix
   form `:- discontiguous p/1.` (the SWI dialect's output) is unreadable under
   Scryer's builtin operator table.
"""
import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_dialect import BUILTIN_NAME_MAP, Dialect, resolve_name
from clausal.tools.prolog_operators import OperatorTable
from clausal.tools.prolog_reader import read_module


# ── A ─────────────────────────────────────────────────────────────────
# Measured 2026-09-29 on Scryer and Trealla: `time/1` (library(time)) and
# `all_distinct/1` (library(clpz)) run on both, so the iso export uses them.
# The map's OTHER Scryer spellings are NOT safe to adopt: `ins/3` is an
# existence_error on both (Scryer's `ins` is the binary operator, `Vs ins
# Lo..Hi` -- a structural rewrite, not a rename), and Scryer has no
# `divmod/4` at all. Adopting them would trade one missing predicate for
# another, so iso keeps the Clausal name there, pinned below.

@pytest.mark.parametrize("clausal_name, iso_name", [
    ("time_goal", "time"), ("all_different", "all_distinct")])
def test_iso_export_uses_the_measured_scryer_spelling(clausal_name, iso_name):
    assert resolve_name(clausal_name, Dialect.iso()) == iso_name


@pytest.mark.parametrize("clausal_name", ["in_domain", "divmod_"])
def test_iso_export_does_not_adopt_a_wrong_scryer_spelling(clausal_name):
    assert resolve_name(clausal_name, Dialect.iso()) == clausal_name


def test_an_explicit_iso_key_still_wins():
    iso = Dialect.iso()
    for k, e in BUILTIN_NAME_MAP.items():
        if e.get("iso") is not None:
            assert resolve_name(k, iso) == e["iso"], k


def test_other_dialects_are_unaffected():
    # in_domain has no swi entry any more: D21 rewrites it structurally for
    # every dialect but gprolog (tests/test_d21_in_domain_divmod.py).
    assert resolve_name("in_domain", Dialect.gprolog()) == BUILTIN_NAME_MAP["in_domain"]["gprolog"]
    assert resolve_name("all_different", Dialect.swi()) == "all_different"


# ── B ─────────────────────────────────────────────────────────────────

def test_dialect_default_clp_library_is_clpz():
    d = Dialect(name="custom", operator_table=OperatorTable.iso_default())
    assert d.clpfd_module == "clpz"
    assert Dialect.swi().clpfd_module == "clpfd"      # SWI keeps its own name


# ── C ─────────────────────────────────────────────────────────────────

SRC = "p(1),\nq(1),\np(2),\n-dynamic(counter/1)\n"


@pytest.mark.parametrize("dialect", ["iso", "scryer", "swi", "trealla", "gprolog"])
def test_prefix_operator_directives_are_functional(dialect):
    out = clausal_source_to_prolog(SRC, strict=True, dialect=getattr(Dialect, dialect)())
    directives = [l for l in out.splitlines() if l.startswith(":- d")]
    assert ":- discontiguous(p/1)." in directives
    assert ":- dynamic(counter/1)." in directives


@pytest.mark.parametrize("dialect", ["iso", "scryer", "swi", "trealla", "gprolog"])
def test_every_dialects_output_reads_under_scryers_table(dialect):
    out = clausal_source_to_prolog(SRC, strict=True, dialect=getattr(Dialect, dialect)())
    items = read_module(out, op_table=OperatorTable.scryer_builtin_default())
    issues = [i for i in items if type(i).__name__ == "SyntaxIssue"]
    assert items and not issues, [i.message for i in issues]


def test_a_conjunction_argument_is_bracketed():
    from clausal.tools.clausal_to_prolog import emit_item
    from clausal.tools.prolog_ast import PAtom, PCompound, PDirective, PNumber
    ind = lambda n, a: PCompound("/", (PAtom(n), PNumber(a)))
    d = PDirective(PCompound("discontiguous", (PCompound(",", (ind("a", 1), ind("b", 2))),)))
    text = emit_item(d, Dialect.swi().operator_table).strip()
    assert text == ":- discontiguous((a/1, b/2))."
