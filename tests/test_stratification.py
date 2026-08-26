"""Compile-time stratification analysis (todo/no-stratification-analysis.md).

A cycle through negation in the predicate dependency graph makes plain NAF
loop or answer wrongly; only ``-table`` (well-founded semantics) gives it a
defined meaning. Nothing used to detect this — an untabled non-stratified
program compiled silently and died with a bare ``RecursionError`` at query
time. The analysis REPORTS (never refuses): a non-stratified SCC whose
members are all tabled is a legitimate WFS program and stays silent.
"""

import os
import warnings

import pytest

from clausal.logic.stratification import ClausalStratificationWarning

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

_loaded = {}


@pytest.fixture(scope="module")
def load(tmp_path_factory):
    def _load(name, source, expect_warnings=False):
        d = tmp_path_factory.mktemp("strat")
        p = d / f"{name}.clausal"
        p.write_text(source)
        from clausal.import_hook import _load_module
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            mod = _load_module(f"strat_{name}", str(p))
        strat = [w for w in caught
                 if issubclass(w.category, ClausalStratificationWarning)]
        return mod, strat
    yield _load


UNTABLED_CYCLE = """-allow_singletons

Pu() <- (not Qu())
Qu() <- (not Pu())
"""

TABLED_CYCLE = """-table(Win/1)

Move(1, 2),
Move(2, 1),

Win(X) <- (Move(X, Y), not Win(Y))
"""

STRATIFIED_NAF = """
Item(1),
Item(2),
Danger(2),

Safe(X) <- (Item(X), not Danger(X))
"""

SELF_NEGATION = """
Item(1),

Odd(X) <- (Item(X), not Odd(X))
"""

POSITIVE_CYCLE = """-table(Reach/2)

Edge(1, 2),
Edge(2, 1),

Reach(X, Y) <- Edge(X, Y)
Reach(X, Y) <- (Edge(X, Z), Reach(Z, Y))
"""

MIXED_TABLING = """-table(Ta/1)

Seed(1),

Ta(X) <- (Seed(X), not Ub(X))
Ub(X) <- (Seed(X), not Ta(X))
"""


class TestNonStratifiedDetection:
    def test_untabled_cycle_warns_with_names(self, load):
        """The todo's two-clause program gets a named diagnostic at load."""
        _, strat = load("untabled_cycle", UNTABLED_CYCLE)
        assert len(strat) == 1
        msg = str(strat[0].message)
        assert "Pu/0" in msg and "Qu/0" in msg
        assert "not" in msg
        assert "-table" in msg  # points at the WFS remedy

    def test_self_negation_warns(self, load):
        _, strat = load("self_neg", SELF_NEGATION)
        assert len(strat) == 1
        assert "Odd/1" in str(strat[0].message)

    def test_mixed_tabling_warns(self, load):
        """A negation cycle with an UNTABLED member still misbehaves —
        the diagnostic names the untabled predicates."""
        _, strat = load("mixed", MIXED_TABLING)
        assert len(strat) == 1
        assert "Ub/1" in str(strat[0].message)


class TestStratifiedSilence:
    def test_tabled_cycle_is_silent(self, load):
        """wfs_win's shape: non-stratified AND fully tabled → fine, no noise."""
        _, strat = load("tabled_cycle", TABLED_CYCLE)
        assert strat == []

    def test_stratified_naf_is_silent(self, load):
        """Negation with no cycle through it — the overwhelmingly common
        case — must produce no diagnostic at all."""
        _, strat = load("stratified", STRATIFIED_NAF)
        assert strat == []

    def test_positive_cycle_is_silent(self, load):
        """Recursion without negation is not non-stratification."""
        _, strat = load("positive_cycle", POSITIVE_CYCLE)
        assert strat == []

    def test_engine_fixture_wfs_win_is_silent(self, load):
        src = open(os.path.join(FIXTURES, "wfs_win.clausal")).read()
        _, strat = load("wfs_win_copy", src)
        assert strat == []


class TestUnitGraphAnalysis:
    def test_report_shape(self):
        """Direct unit call: the report names the cycle in order."""
        from clausal.logic.stratification import find_negation_cycles
        edges = {
            ("P", 0): [(("Q", 0), True)],
            ("Q", 0): [(("P", 0), True)],
            ("R", 0): [(("P", 0), True)],   # outside the cycle
        }
        cycles = find_negation_cycles(edges)
        assert len(cycles) == 1
        (members, path) = cycles[0]
        assert members == {("P", 0), ("Q", 0)}
        # path is [(node, edge_to_next_is_negative), ...] closing back to
        # path[0][0]; at least one traversed edge is negative.
        assert {n for n, _ in path} == members
        assert any(neg for _, neg in path)

    def test_positive_scc_not_reported(self):
        from clausal.logic.stratification import find_negation_cycles
        edges = {
            ("P", 0): [(("Q", 0), False)],
            ("Q", 0): [(("P", 0), False)],
        }
        assert find_negation_cycles(edges) == []


OR_BODY_CYCLE = """
Seed(1),

Pa(X) <- (Seed(X) or not Pb(X))
Pb(X) <- (Seed(X), not Pa(X))
"""

ITE_TEST_CYCLE = """
Seed(1),

Qa(X) <- if_(Qb(X), Seed(X), Seed(X))
Qb(X) <- (Seed(X), not Qa(X))
"""


class TestCompositeBodies:
    def test_or_body_cycle_warns(self, load):
        """Negation inside a disjunction arm still records the edge (and the
        walker survives the binary Or node — it once crashed module load)."""
        _, strat = load("or_cycle", OR_BODY_CYCLE)
        assert len(strat) == 1
        msg = str(strat[0].message)
        assert "Pa/1" in msg and "Pb/1" in msg

    def test_ite_test_edge_warns(self, load):
        """An if-else test is a negative dependency for its else branch."""
        _, strat = load("ite_cycle", ITE_TEST_CYCLE)
        assert len(strat) == 1
        msg = str(strat[0].message)
        assert "Qa/1" in msg and "Qb/1" in msg
