"""The seam text-compare lint (dumb seam step (g), 2026-09-27).

Under raw out a goal-position answer is the engine's term: a string is the
carrier ``('$chars', s)`` and an atom the plain ``str``.  So ``T == "x"``
in hosted Python is silently False for a string answer and silently True
for an atom answer -- the asymmetry that makes it a trap.  The lint warns at
LOAD, once per site, when a name bound by a goal-position seam (``if`` /
``while`` / ``for``, a comprehension's first clause) is compared with a
Python str LITERAL in the same function: ``==``, ``!=``, ``in`` / ``not
in`` a literal container of str, ``match``/``case`` str patterns; and the
same through a plain alias (``y = T``).  ``ClausalSeamTextCompareWarning``.
"""
import os
import tempfile
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.lint_warnings import ClausalSeamTextCompareWarning
from tests._suffix import SEAM


def _load(name, source):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.seam")
    with open(p, "w") as fh:
        fh.write(source)
    return _load_module(name, p)


RB = (
    "-module({name}, [txt(T), sp(X), kv(K, V), nxt(N, M)])\n"
    "-private([a])\n"
    "txt(\"some text\"),\n"
    "sp(a),\n"
    "kv(a, \"one\"),\n"
    "nxt(N, M) <- (N < 2, M is ++(N + 1)),\n"
)


def _firings(name, body):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load(name, RB.format(name=name) + body)
    return [str(w.message) for w in caught if issubclass(w.category, ClausalSeamTextCompareWarning)]


# ── positive controls: each shape fires exactly where it should ─────────────

class TestFires:
    def test_eq_with_a_str_literal(self):
        got = _firings("_lt_a", (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return T == \"some text\"\n"
        ))
        assert len(got) == 1, got
        assert "T" in got[0] and '--"some text"' in got[0] and "to_python(T)" in got[0]
        assert ":9:" in got[0], "the comparison's line (6 rulebase lines + 3)"

    def test_ne_and_reversed_operands(self):
        got = _firings("_lt_b", (
            "def go():\n"
            "    if --txt(T):\n"
            "        a = T != \"x\"\n"
            "        b = \"x\" == T\n"
            "        return a, b\n"
        ))
        assert len(got) == 2, got

    def test_in_a_literal_container_of_str(self):
        got = _firings("_lt_c", (
            "def go():\n"
            "    for X in --sp(X):\n"
            "        return X in [\"a\", \"b\"], X not in (\"c\",), X in {\"d\"}\n"
        ))
        assert len(got) == 3, got

    def test_through_a_plain_alias(self):
        got = _firings("_lt_d", (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        y = T\n"
            "        return y == \"some text\"\n"
        ))
        assert len(got) == 1, got
        assert "y" in got[0]

    def test_while_and_comprehension_targets(self):
        got = _firings("_lt_e", (
            "def loop():\n"
            "    cur = 0\n"
            "    while --nxt(++cur, N):\n"
            "        cur = N\n"
            "        if N == \"2\":\n"
            "            break\n"
            "def comp():\n"
            "    return [K == \"a\" for K, V in --kv(K, V)]\n"
        ))
        assert len(got) == 2, got

    def test_match_case_str_pattern(self):
        got = _firings("_lt_f", (
            "def go():\n"
            "    for X in --sp(X):\n"
            "        match X:\n"
            "            case \"a\" | \"b\":\n"
            "                return 1\n"
            "            case 3:\n"
            "                return 2\n"
        ))
        assert len(got) == 1, got

    def test_module_level_seam_over_an_imported_predicate(self, tmp_path):
        rb = tmp_path / f"lt_lib{SEAM}"
        rb.write_text("-module(lt_lib, [t(T)])\nt(\"x\"),\n")
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            got = _firings("_lt_g", (
                "-import_module(lt_lib)\n"
                "for T in --lt_lib.t(T):\n"
                "    same = T == \"x\"\n"
            ))
        finally:
            sys.path.remove(str(tmp_path))
        assert len(got) == 1, got


# ── no false positives ──────────────────────────────────────────────────────

class TestSilent:
    def test_comparing_with_a_seam_literal_is_the_right_spelling(self):
        assert _firings("_ls_a", (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return T == --\"some text\", T != --\"other\"\n"
        )) == []

    def test_to_python_then_a_str_literal_is_fine(self):
        assert _firings("_ls_b", (
            "from clausal import to_python\n"
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return to_python(T) == \"some text\"\n"
        )) == []

    def test_a_non_str_literal_and_a_non_literal_container(self):
        assert _firings("_ls_c", (
            "NAMES = [\"a\"]\n"
            "def go():\n"
            "    for X in --sp(X):\n"
            "        return X == 1, X != None, X in NAMES, X in [1, 2]\n"
        )) == []

    def test_a_name_not_bound_by_a_seam(self):
        assert _firings("_ls_d", (
            "def go(t):\n"
            "    for X in --sp(X):\n"
            "        pass\n"
            "    return t == \"x\"\n"
        )) == []

    def test_a_seam_name_compared_in_another_function(self):
        assert _firings("_ls_e", (
            "def go():\n"
            "    for T in --txt(T):\n"
            "        return T\n"
            "def other(T):\n"
            "    return T == \"x\"\n"
        )) == []

    def test_a_negated_test_binds_nothing(self):
        assert _firings("_ls_f", (
            "def go(T):\n"
            "    if not --txt(T):\n"
            "        return T == \"x\"\n"
        )) == []
