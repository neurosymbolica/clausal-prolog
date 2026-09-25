"""F4 (ruling 3): the diagnostic arity reader answers a SET of arities.

``predicate_diagnostics`` builds the "did you mean:" near-miss pool from the
namespace bindings of the failing module.  Its reader used to answer ONE arity
or ``None``, and both pool builders guarded with ``if arity:`` -- so a ``p/0``
predicate was falsy and never reached the pool, whether imported or declared
``-dynamic`` without clauses.  RULED: the reader answers the set of arities
(the shape ``Database.arities_for`` returns); the EMPTY set means "not a
predicate here"; several arities are several suggestions.

``Database.arities_for`` itself is LOSSY (it misses a bare ``name/arity``
export entry and an ``-import_from`` adopted row), so the source is
``Database.predicate_arities`` -- the arity twin of ``is_predicate_name`` --
and the class arm keeps the class's own ``_fields`` count, so no case the old
reader answered is lost.  ``TestNothingLost`` measures that over a population
it asserts is non-empty.
"""

from __future__ import annotations

import dataclasses
import re
import sys
import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.predicate import PredicateMeta, predicate_arities_for
from clausal.predicate_diagnostics import describe_missing_predicate
import clausal.predicate_diagnostics as pd
from tests.predicate_api_support import class_arm_predicate


LIB = "f4arity_lib"
USE = "f4arity_use"
REV = "f4arity_rev"

LIB_SRC = f"""
-module({LIB}, [halted_flag/0, go_onward(X), pair_up(A, B), vexport/1])

halted_flag(),

go_onward(1),

pair_up(1, 2),
"""

USE_SRC = f"""
-import_from({LIB}, [halted_flag, go_onward, pair_up])

-import_module({LIB})

-private([colour_code/1])

-dynamic(stopped_flag/0)

-dynamic(ledger_row/1, ledger_row/2)

local_one(1),
"""

# roborev on F4: ``probe_it/1`` is DEFINED (clauses); ``probe_it/2`` is only a
# bare export entry.  Calling ``probe_it/2`` raises an arity mismatch, so it
# must never be listed as defined or suggested.
REV_SRC = f"""
-module({REV}, [probe_it/2, lone_exp/1])

probe_it(1),
"""


def _old_arity_of(obj):
    """The reader as it was before F4, verbatim -- the measurement baseline."""
    if not isinstance(obj, PredicateMeta):
        return None
    fields = getattr(obj, "_fields", None)
    if fields is not None:
        return len(fields)
    arity = getattr(obj, "_arity", None)
    return arity if isinstance(arity, int) else None


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    d = tmp_path_factory.mktemp("f4arity")
    (d / f"{LIB}.clausal").write_text(textwrap.dedent(LIB_SRC).lstrip())
    (d / f"{USE}.clausal").write_text(textwrap.dedent(USE_SRC).lstrip())
    (d / f"{REV}.clausal").write_text(textwrap.dedent(REV_SRC).lstrip())
    for name in (LIB, USE, REV):
        sys.modules.pop(name, None)
    lib = _load_module(LIB, str(d / f"{LIB}.clausal"))
    use = _load_module(USE, str(d / f"{USE}.clausal"))
    _load_module(REV, str(d / f"{REV}.clausal"))
    yield lib, use
    for name in (LIB, USE, REV):
        sys.modules.pop(name, None)


def _db(mod):
    return mod.__dict__["$module"].db


def _did_you_mean(msg):
    """The ``did you mean:`` sentence, with its wrapped continuation lines
    (they are indented deeper than the two-space sentence start)."""
    assert msg.count("did you mean:") <= 1, msg
    m = re.search(r"did you mean:(.*?)(?=\n  \S|\Z)", msg, re.S)
    return " ".join(m.group(1).split()) if m else ""


# ── the p/0 bug: a zero-arity predicate never reached the pool ───────────────


class TestZeroArityReachesThePool:

    def test_imported_zero_arity_predicate_is_suggested(self, mods):
        _lib, use = mods
        msg = describe_missing_predicate("halted_fla", 0, db=_db(use))
        assert "halted_flag/0" in _did_you_mean(msg), msg

    def test_dynamic_zero_arity_predicate_without_clauses_is_suggested(
            self, mods):
        _lib, use = mods
        msg = describe_missing_predicate("stopped_fla", 0, db=_db(use))
        assert "stopped_flag/0" in _did_you_mean(msg), msg

    def test_zero_arity_local_predicate_is_listed_as_defined(self, mods):
        _lib, use = mods
        msg = describe_missing_predicate("zzz_quux", 1, db=_db(use))
        assert re.search(r"defines:.*stopped_flag/0.*no predicate named", msg, re.S), msg


# ── several arities are several suggestions ──────────────────────────────────


class TestSeveralArities:

    def test_every_declared_arity_is_suggested(self, mods):
        _lib, use = mods
        line = _did_you_mean(
            describe_missing_predicate("ledger_rows", 1, db=_db(use)))
        assert "ledger_row/1" in line and "ledger_row/2" in line, line

    def test_reader_answers_the_set(self, mods):
        _lib, use = mods
        assert predicate_arities_for(use.ledger_row) == {1, 2}

    def test_defines_answers_every_arity_of_an_imported_module(self, mods):
        _lib, use = mods
        assert pd._defines(use, "ledger_row") == [1, 2]


# ── the lossy-source cases: still suggested ──────────────────────────────────


class TestLossySourcesStillSuggested:

    def test_bare_export_entry_is_suggested(self, mods):
        """``-private([colour_code/1])``: ``arities_for`` answers ``set()``."""
        _lib, use = mods
        assert _db(use).arities_for("colour_code") == set()  # the trap is live
        line = _did_you_mean(
            describe_missing_predicate("colour_cod", 1, db=_db(use)))
        assert "colour_code/1" in line, line

    def test_import_from_adopted_row_is_suggested(self, mods):
        """An ``-import_from`` row lives in ``_adopted``, which ``arities_for``
        does not scan."""
        _lib, use = mods
        assert ("go_onward", 1) in _db(use)._adopted
        assert _db(use).arities_for("go_onward") == set()  # the trap is live
        line = _did_you_mean(
            describe_missing_predicate("go_onwards", 1, db=_db(use)))
        assert f"go_onward/1 (from {LIB})" in line, line

    def test_database_predicate_arities_sees_both(self, mods):
        _lib, use = mods
        db = _db(use)
        assert db.predicate_arities("colour_code") == {1}
        assert db.predicate_arities("go_onward") == {1}
        assert db.predicate_arities("halted_flag") == {0}


# ── declared-only arities are not suggested beside a defined one ─────────────


class TestDeclaredOnlyArityBesideADefinedOne:
    """``probe_it/1`` has a clause; ``probe_it/2`` is only a bare export
    entry.  Only DEFINED arities (the db's home keys) are reported."""

    def _rev_db(self):
        return _db(sys.modules[REV])

    def test_the_setup_is_what_it_claims(self, mods):
        db = self._rev_db()
        assert ("probe_it", 2) in db._predicate_export
        assert ("probe_it", 2) not in db.owned_keys()
        assert ("probe_it", 1) in db.owned_keys()
        assert db.predicate_arities("probe_it") == {1, 2}  # the lossless union

    def test_defines_lists_only_the_defined_arity(self, mods):
        msg = describe_missing_predicate("probe_it", 3, db=self._rev_db())
        defines = msg.split("defines:", 1)[1].split("did you mean", 1)[0]
        assert "probe_it/1" in defines and "probe_it/2" not in defines, msg

    def test_wrong_arity_call_suggests_only_the_defined_arity(self, mods):
        line = _did_you_mean(
            describe_missing_predicate("probe_it", 3, db=self._rev_db()))
        assert "probe_it/1" in line and "probe_it/2" not in line, line

    def test_near_miss_suggests_only_the_defined_arity(self, mods):
        line = _did_you_mean(
            describe_missing_predicate("probe_itt", 2, db=self._rev_db()))
        assert "probe_it/1" in line and "probe_it/2" not in line, line

    def test_both_eras_answer_the_defined_arity(self, mods):
        assert predicate_arities_for(sys.modules[REV].probe_it) == {1}
        assert predicate_arities_for(mangle(REV, "probe_it")) == {1}

    def test_a_declaration_only_name_still_answers_its_arity(self, mods):
        """No defined arity at all: the declaration is the only thing the
        name can mean, and the class era answers it via ``_fields``."""
        assert predicate_arities_for(sys.modules[REV].lone_exp) == {1}
        assert predicate_arities_for(mangle(REV, "lone_exp")) == {1}


# ── cost: one index per database per message ─────────────────────────────────


def test_one_index_build_per_database_per_message(mods, monkeypatch):
    from clausal.logic.database import Database
    calls = []
    real = Database.arity_maps

    def counting(self):
        calls.append(id(self))
        return real(self)

    monkeypatch.setattr(Database, "arity_maps", counting)
    _lib, use = mods
    ns = dict(use.__dict__)
    bindings = sum(1 for v in ns.values() if predicate_arities_for(v))
    assert bindings >= 8, bindings
    calls.clear()
    describe_missing_predicate("zzz_quux", 1, module_globals=ns)
    assert calls, "the index was never consulted -- the probe is stale"
    assert len(calls) == len(set(calls)), calls


# ── era-agnostic: a module binding that is a mangled atom ────────────────────


class TestMangledBinding:
    """After the PredicateMeta flip a module attribute for a predicate is a
    mangled atom.  A reader or filter keyed on the class shape selects
    NOTHING then; this namespace is that era, built by hand."""

    def test_reader_answers_through_the_owner(self, mods):
        assert predicate_arities_for(mangle(LIB, "pair_up")) == {2}
        assert predicate_arities_for(mangle(LIB, "halted_flag")) == {0}

    def test_imported_mangled_binding_is_suggested(self, mods):
        ns = {"__name__": "f4arity_elsewhere",
              "pair_up": mangle(LIB, "pair_up"),
              "halted_flag": mangle(LIB, "halted_flag")}
        line = _did_you_mean(
            describe_missing_predicate("pair_upp", 2, module_globals=ns))
        assert f"pair_up/2 (from {LIB})" in line, line
        line = _did_you_mean(
            describe_missing_predicate("halted_fla", 0, module_globals=ns))
        assert f"halted_flag/0 (from {LIB})" in line, line

    def test_mangled_lossy_sources_answer(self, mods):
        """The mangled arm has ONLY the owner's db to read, so here the
        lossless source is load-bearing: ``arities_for`` would answer
        ``set()`` for both."""
        assert predicate_arities_for(mangle(USE, "colour_code")) == {1}
        assert predicate_arities_for(mangle(USE, "go_onward")) == {1}

    def test_mangled_bare_export_is_suggested(self, mods):
        ns = {"__name__": USE, "colour_code": mangle(USE, "colour_code")}
        line = _did_you_mean(
            describe_missing_predicate("colour_cod", 1, module_globals=ns))
        assert "colour_code/1" in line, line

    def test_own_mangled_binding_is_listed_as_defined(self, mods):
        ns = {"__name__": LIB, "pair_up": mangle(LIB, "pair_up")}
        msg = describe_missing_predicate("zzz_quux", 1, module_globals=ns)
        assert re.search(r"defines:.*pair_up/2.*no predicate named", msg, re.S), msg


# ── not a predicate: the empty set ───────────────────────────────────────────


@dataclasses.dataclass
class _DataShape:
    a: int


@pytest.mark.parametrize("value", [
    None, 3, "pair_up", mangle("f4arity_no_such_module", "x"), _DataShape,
    object(), str,
])
def test_non_predicates_answer_the_empty_set(value, mods):
    assert predicate_arities_for(value) == set()


def test_class_whose_owner_is_not_loaded_keeps_its_own_arity():
    """The class arm's own ``_fields`` count is kept: measured over the
    fixture population, a db-only reader loses 59 of 910 old answers
    (partially loaded modules, ``make_predicate`` classes, and
    ``term_expansion/4``, which no db records)."""
    cls = class_arm_predicate("f4arity_floating", ["a", "b", "c"])
    assert predicate_arities_for(cls) == {3}
    nullary = class_arm_predicate("f4arity_nullary", [])
    assert predicate_arities_for(nullary) == {0}


def test_unloaded_owner_answers_the_empty_set():
    assert predicate_arities_for(mangle("f4arity_never_loaded", "p")) == set()


# ── the measurement: nothing the old reader answered is lost ─────────────────


class TestNothingLost:

    def test_new_set_contains_every_old_answer(self, mods, monkeypatch):
        """Every namespace binding of every loaded module: where the old
        reader answered an arity, the new set contains it.

        W4b-3 slice 5 took away most of the old reader's population: it
        answered only for a ``PredicateMeta`` class, and nearly all the
        classes in loaded module namespaces were the rewriter's.  The
        rewriter mints none now, so the population is SEEDED with the one
        class shape still made (``make_predicate``, the Python-API arm
        retired at slice 6), bound into a loaded module the way a Python
        caller binds one -- a population of at least one, so ``not lost`` is
        never vacuous -- and no loaded module binds a class of its OWN
        (``__module__`` is the module itself for a class statement in its
        body)."""
        seeded = class_arm_predicate("f4arity_seeded", ["a", "b"])
        monkeypatch.setitem(vars(sys.modules[LIB]), "f4arity_seeded", seeded)
        scanned = 0
        population = 0
        rewriter_made = []
        lost = []
        for modname, mod in list(sys.modules.items()):
            ns = getattr(mod, "__dict__", None)
            if not isinstance(ns, dict) or "$module" not in ns:
                continue
            scanned += 1
            for name, value in list(ns.items()):
                old = _old_arity_of(value)
                if old is None:
                    continue
                population += 1
                if getattr(value, "__module__", None) == ns.get("__name__"):
                    rewriter_made.append((modname, name))
                if old not in predicate_arities_for(value):
                    lost.append((modname, name, old))
        assert scanned >= 3, (
            f"scanned {scanned} Clausal modules -- the fixture did not load")
        assert population >= 1, "population is EMPTY -- the filter is stale"
        assert rewriter_made == [], rewriter_made
        assert not lost, lost

    def test_predicate_arities_agrees_with_is_predicate_name(self, mods):
        """Non-empty iff ``is_predicate_name`` -- same containers."""
        checked = 0
        for mod in mods:
            db = _db(mod)
            names = {f for (f, _a) in db._predicate_export} | set(db.functors())
            for f in names | {"zzz_not_here"}:
                checked += 1
                assert bool(db.predicate_arities(f)) == db.is_predicate_name(f)
                assert db.arities_for(f) <= db.predicate_arities(f)
        assert checked > 5, checked
