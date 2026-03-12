"""Classic SLG resolution tests — programs that only terminate with tabling.

Each test here would loop infinitely under naive depth-first search.
Tabling (SLG resolution) detects repeated subgoals and suspends them,
guaranteeing termination.
"""

import os
import pytest

from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.logic.solve import call


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    from clausal.import_hook import _load_module
    return _load_module(name, os.path.join(FIXTURES, f"{name}.clausal"))


def _module(mod):
    return mod.__dict__["$module"]


# ── Left-recursive transitive closure ─────────────────────────────────────
# path(X,Y) :- edge(X,Y).              ← base case (listed first)
# path(X,Y) :- path(X,Z), edge(Z,Y).   ← recursive call BEFORE edge
#
# The second clause is left-recursive: the first body goal is path/2 itself.
# Without tabling, SLD resolution on path(1,Y) tries clause 2, which calls
# path(1,Z), which tries clause 2, which calls path(1,Z2), ... diverging
# even on this acyclic graph (1→2→3→4). With tabling, the repeated
# path(1,_) subgoal is detected and suspended.


class TestLeftRecursion:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _load("tabled_left_rec")
        self.lm = _module(self.mod)

    def test_terminates_and_finds_all(self):
        """Left-recursive path/2 finds all reachable nodes from 1."""
        Y = Var()
        results = set()
        for trail in call("path", 1, Y, module=self.lm):
            results.add(deref(Y))
        assert results == {2, 3, 4}

    def test_single_hop(self):
        results = list(call("path", 3, 4, module=self.lm))
        assert len(results) >= 1

    def test_multi_hop(self):
        results = list(call("path", 1, 4, module=self.lm))
        assert len(results) >= 1

    def test_no_path(self):
        """No backward edges in this acyclic graph."""
        results = list(call("path", 4, 1, module=self.lm))
        assert len(results) == 0

    def test_all_pairs(self):
        """Enumerate all (X,Y) pairs."""
        X, Y = Var(), Var()
        results = set()
        for trail in call("path", X, Y, module=self.lm):
            results.add((deref(X), deref(Y)))
        expected = {
            (1, 2), (1, 3), (1, 4),
            (2, 3), (2, 4),
            (3, 4),
        }
        assert results == expected

    def test_table_entries_complete(self):
        X = Var()
        list(call("path", 1, X, module=self.lm))
        for entry in self.lm.db.table_store.values():
            assert entry.status == "complete"


# ── Same generation ───────────────────────────────────────────────────────
# sg(X, Y) :- X = Y.                             ← reflexive
# sg(X, Y) :- parent(X, P), sg(P, Q), parent(Y, Q).
#
# Classic deductive database benchmark (Bancilhon et al. 1986).
# Without tabling, sg/2 generates an infinite search tree: sg(P,Q) can
# re-expand sg(P',Q') at the next level, and so on.
#
# Family tree:
#       1
#      / \
#     2   3
#    /|   |\
#   4  5  5  6     (5 has two parents: 2 and 3)
#
# Level 0: {1}
# Level 1: {2, 3}
# Level 2: {4, 5, 6}


class TestSameGeneration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _load("tabled_same_gen")
        self.lm = _module(self.mod)

    def test_reflexive(self):
        """Every node is in the same generation as itself."""
        for node in [1, 2, 3, 4, 5, 6]:
            results = list(call("sg", node, node, module=self.lm))
            assert len(results) >= 1, f"sg({node}, {node}) should succeed"

    def test_same_gen_siblings(self):
        """2 and 3 are siblings (both children of 1) → same generation."""
        results = list(call("sg", 2, 3, module=self.lm))
        assert len(results) >= 1

    def test_same_gen_cousins(self):
        """4 and 6: 4 is child of 2, 6 is child of 3, 2 and 3 are same-gen."""
        results = list(call("sg", 4, 6, module=self.lm))
        assert len(results) >= 1

    def test_same_gen_shared_child(self):
        """4 and 5 are same-gen (both children of 2). Also via 3→5, 1→2→4."""
        results = list(call("sg", 4, 5, module=self.lm))
        assert len(results) >= 1

    def test_not_same_gen_different_levels(self):
        """1 is root, 4 is grandchild — not same generation."""
        results = list(call("sg", 1, 4, module=self.lm))
        assert len(results) == 0

    def test_not_same_gen_parent_child(self):
        """2 is parent of 4 — different generations."""
        results = list(call("sg", 2, 4, module=self.lm))
        assert len(results) == 0

    def test_enumerate_cross_gen_pairs(self):
        """Collect non-reflexive same-generation pairs via recursive clause."""
        X, Y = Var(), Var()
        results = set()
        for trail in call("sg", X, Y, module=self.lm):
            x, y = deref(X), deref(Y)
            if not (is_var(x) or is_var(y)):
                results.add((x, y))
        # Level 1 cross-pairs
        assert (2, 3) in results
        assert (3, 2) in results
        # Level 2 cross-pairs
        assert (4, 5) in results
        assert (4, 6) in results
        assert (5, 6) in results
        assert (5, 4) in results
        assert (6, 4) in results
        assert (6, 5) in results

    def test_table_entries_complete(self):
        X, Y = Var(), Var()
        list(call("sg", X, Y, module=self.lm))
        for entry in self.lm.db.table_store.values():
            assert entry.status == "complete"


# ── Mutual recursion ─────────────────────────────────────────────────────
# reach_a(X,Y) :- link_a(X,Y).
# reach_a(X,Y) :- reach_b(X,Z), link_a(Z,Y).
# reach_b(X,Y) :- link_b(X,Y).
# reach_b(X,Y) :- reach_a(X,Z), link_b(Z,Y).
#
# Graph: 1 -a→ 2 -b→ 3 -a→ 4 -b→ 1  (cycle via alternating link types)
# reach_a and reach_b call each other, creating mutual recursion.
# Without tabling, this diverges: reach_a → reach_b → reach_a → ...


class TestMutualRecursion:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mod = _load("tabled_mutual_rec")
        self.lm = _module(self.mod)

    def test_reach_a_from_1(self):
        """reach_a(1, Y): direct link_a(1,2) + reach_b(1,3)→link_a(3,4)."""
        Y = Var()
        results = set()
        for trail in call("reach_a", 1, Y, module=self.lm):
            results.add(deref(Y))
        assert results == {2, 4}

    def test_reach_b_from_2(self):
        """reach_b(2, Y): direct link_b(2,3); also reach_a(2,4),link_b(4,1)."""
        Y = Var()
        results = set()
        for trail in call("reach_b", 2, Y, module=self.lm):
            results.add(deref(Y))
        assert results == {3, 1}

    def test_reach_a_from_3(self):
        """reach_a(3, Y): link_a(3,4) direct; also reach_b(3,1),link_a(1,2)."""
        Y = Var()
        results = set()
        for trail in call("reach_a", 3, Y, module=self.lm):
            results.add(deref(Y))
        assert results == {4, 2}

    def test_mutual_cycle_terminates(self):
        """Must terminate despite the 1→2→3→4→1 cycle."""
        Y = Var()
        results = set()
        for trail in call("reach_a", 1, Y, module=self.lm):
            results.add(deref(Y))
        assert len(results) >= 1

    def test_both_tabled(self):
        assert self.lm.db.is_tabled("reach_a", 2)
        assert self.lm.db.is_tabled("reach_b", 2)

    def test_table_entries_complete(self):
        Y = Var()
        list(call("reach_a", 1, Y, module=self.lm))
        for entry in self.lm.db.table_store.values():
            assert entry.status == "complete"
