"""The reified if-then-else is spelled ``if_/3``.

``If/3`` is the superseded spelling: still accepted everywhere ``if_`` is, but
it warns at load time and nothing in the library emits it any more.  See
``todo/rename-If-3-to-if_-3.md`` and ``docs/reified_ite.md``.
"""

from __future__ import annotations

import warnings

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.reflection import IfThenElse, reify_source, render_source
from clausal.terms import DictTerm
from clausal.templating.term_rewriting import ClausalDeprecatedSpellingWarning


def _load(name, src_text, tmp_path):
    """Write a .clausal file and load it, returning its logic module."""
    path = tmp_path / f"{name}.clausal"
    path.write_text(src_text)
    return _load_module(name, str(path)).__dict__["$module"]


def _load_quietly(name, src_text, tmp_path):
    """``_load`` with the deprecation lint muted — for the legacy-spelling tests."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ClausalDeprecatedSpellingWarning)
        return _load(name, src_text, tmp_path)


CLASSIFY = 'Classify(X, LABEL) <- {ite}(X >= 0, LABEL is "positive", LABEL is "negative")\n'


# ── The canonical spelling ───────────────────────────────────────────────────


class TestIfUnderscore:
    def test_goal_position_takes_both_branches(self, tmp_path):
        """# nv"""
        mod = _load("ifu_goal", CLASSIFY.format(ite="if_"), tmp_path)
        out = Var()
        assert [deref(out) for _ in call("Classify", 5, out, module=mod)] == [
            mint("positive")]
        out2 = Var()
        assert [deref(out2) for _ in call("Classify", -3, out2, module=mod)] == [
            mint("negative")]

    def test_does_not_warn(self, tmp_path, recwarn):
        """# nv"""
        _load("ifu_quiet", CLASSIFY.format(ite="if_"), tmp_path)
        assert [w for w in recwarn
                if issubclass(w.category, ClausalDeprecatedSpellingWarning)] == []

    def test_dcg_body(self, tmp_path):
        """The DCG body rewriter recognises the new spelling."""
        # nv
        src = (
            "-module(x, [g(S0, S), x, y, z])\n"
            "g >> (if_([x], [y], [z]))\n"
        )
        mod = _load("ifu_dcg", src, tmp_path)
        g = mod.module_dict["g"]
        x = mod.module_dict["x"]
        y = mod.module_dict["y"]
        z = mod.module_dict["z"]
        assert any(True for _ in call("phrase", g, [x, y], module=mod))
        assert any(True for _ in call("phrase", g, [z], module=mod))

    def test_edcg_body(self, tmp_path):
        """The EDCG body rewriter recognises the new spelling.

        Behaviour of the construct itself is pinned in
        ``tests/test_edcg.py::TestEdcgIfThenElse``; this only checks the name.
        """
        # nv
        src = (
            "-module(e, [pick(_cnt0, _cnt)])\n"
            "-edcg_acc(counter, _x, _in, _out, {_out == _in + _x})\n"
            "-edcg_pred(inc, 0, [counter])\n"
            "-edcg_pred(pick, 0, [counter])\n"
            "inc >> ([1] // counter)\n"
            "pick >> (if_({1 == 1}, inc, (inc, inc)))\n"
        )
        mod = _load("ifu_edcg", src, tmp_path)
        out = Var()
        assert [deref(out) for _ in call("pick", 0, out, module=mod)] == [1]

    def test_dict_read_stays_inside_the_taken_branch(self, tmp_path):
        """The read-hoisting scope walker recognises the new spelling."""
        # nv
        src = (
            "-private([kee])\n"
            "yes({kee: 1}),\n"
            "prc(PROF, R) <- if_(yes(PROF), R is PROF.kee, R is 0)\n"
        )
        mod = _load("ifu_dictread", src, tmp_path)
        out = Var()
        # The dict has no `kee`, so the condition fails and the else-branch
        # runs; a read hoisted ahead of the if_ would throw instead.
        assert [deref(out) for _ in
                call("prc", DictTerm({}), out, module=mod)] == [0]


# ── The superseded spelling ──────────────────────────────────────────────────


class TestLegacyIf:
    def test_still_compiles_and_runs(self, tmp_path):
        """# nv"""
        mod = _load_quietly("legacy_run", CLASSIFY.format(ite="If"), tmp_path)
        out = Var()
        assert [deref(out) for _ in call("Classify", 5, out, module=mod)] == [
            mint("positive")]

    def test_warns_naming_the_rewrite(self, tmp_path):
        """# nv"""
        with pytest.warns(ClausalDeprecatedSpellingWarning,
                          match=r"`If` -> `if_`"):
            _load("legacy_warn", CLASSIFY.format(ite="If"), tmp_path)

    def test_warning_locates_the_site(self, tmp_path):
        """# nv"""
        src = "# leading comment\n" + CLASSIFY.format(ite="If")
        with pytest.warns(ClausalDeprecatedSpellingWarning) as caught:
            _load("legacy_where", src, tmp_path)
        message = str(caught[0].message)
        assert "legacy_where.clausal:2" in message
        assert "Classify(X, LABEL)" in message  # the offending source line

    def test_dcg_body_warns(self, tmp_path):
        """A DCG body is rewritten before the term pass — it must still warn."""
        # nv
        src = (
            "-module(x, [g(S0, S), x, y, z])\n"
            "g >> (If([x], [y], [z]))\n"
        )
        with pytest.warns(ClausalDeprecatedSpellingWarning):
            _load("legacy_dcg", src, tmp_path)

    def test_edcg_body_warns(self, tmp_path):
        """Likewise for an EDCG body."""
        # nv
        src = (
            "-module(e, [pick(_cnt0, _cnt)])\n"
            "-edcg_acc(counter, _x, _in, _out, {_out == _in + _x})\n"
            "-edcg_pred(inc, 0, [counter])\n"
            "-edcg_pred(pick, 0, [counter])\n"
            "inc >> ([1] // counter)\n"
            "pick >> (If({1 == 1}, inc, (inc, inc)))\n"
        )
        with pytest.warns(ClausalDeprecatedSpellingWarning):
            _load("legacy_edcg", src, tmp_path)


# ── Canonical spelling is what the library emits ─────────────────────────────


class TestCanonicalOutput:
    @pytest.mark.parametrize("ite", ["if_", "If"])
    def test_renderer_emits_if_underscore(self, ite):
        """Either spelling reifies to IfThenElse and renders back as ``if_``."""
        # nv
        src = f"Pick(X, Y) <- (Y is {ite}(X > 0, 1, 2))\n"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ClausalDeprecatedSpellingWarning)
            (clause,) = [item for item in reify_source(src)
                         if hasattr(item, "goals")]
        (goal,) = clause.goals
        assert isinstance(goal.right, IfThenElse)
        rendered = render_source(clause)
        assert "if_(" in rendered
        assert "If(" not in rendered

    def test_arity_error_names_the_new_spelling(self, tmp_path):
        """# nv"""
        with pytest.raises(SyntaxError, match=r"if_\(condition, then, else\)"):
            _load_quietly("bad_arity", "c(X, L) <- If(X >= 0, L is 1)\n", tmp_path)

    def test_ternary_error_names_the_new_spelling(self, tmp_path):
        """# nv"""
        with pytest.raises(SyntaxError, match=r"if_\(COND, THEN, ELSE\)"):
            _load("ternary", "c(X, L) <- (L is 1 if X >= 0 else 2)\n", tmp_path)
