"""The CROSS-MODE literal lint: a ``"..."`` inside a goal-position seam that
targets a module whose ``-double_quotes`` mode differs from the host file's.

The hazard (seam review, 2026-09-26): a seam literal takes the HOST file's
mode (``term_rewriting.visit_Constant``), not the target module's.  So a
chars-mode host calling ``--p("x")`` into an atom-mode module sends the
STRING ``"x"`` to clauses written against the ATOM ``x``: the goal compares
a string with an atom, never matches, and nothing raises.  With the engine
default flipping to ``chars`` (2026-09-26) every module that pins
``-double_quotes(atom)`` becomes such a target.

The lint fires at LOAD, where the target is statically known: an
``-import_from``'d predicate, or ``--m.pred(...)`` over an
``-import_module``'d base.  A base bound at run time (``module =
_RULE.get()`` inside a function) is the documented gap -- see
``compiler_v2._lint_cross_mode_literals``.
"""
import sys
import textwrap
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.lint_warnings import ClausalCrossModeLiteralWarning


def _load(tmp_path, monkeypatch, name, body):
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}.clausal"
    p.write_text(textwrap.dedent(body).lstrip())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    hits = [w for w in caught
            if isinstance(w.message, ClausalCrossModeLiteralWarning)]
    return mod, hits


ATOM_OWNER = """
    -double_quotes(atom)
    -module({name}, [p/1])
    p("x"),
"""

CHARS_OWNER = """
    -double_quotes(chars)
    -module({name}, [p/1])
    p("x"),
"""

HOST = """
    -double_quotes({mode})
    -import_from({owner}, [p])

    def go():
        if --p({lit}):
            return True
        return False
"""


def test_a_chars_host_into_an_atom_module_warns_and_names_both_modes(
        tmp_path, monkeypatch):
    _load(tmp_path, monkeypatch, "xm_owner_a1", ATOM_OWNER.format(name="xm_owner_a1"))
    host, hits = _load(tmp_path, monkeypatch, "xm_host_a1",
                       HOST.format(mode="chars", owner="xm_owner_a1", lit='"x"'))
    # The hazard is real: the goal never matches, and nothing raised.
    assert host.go() is False
    assert len(hits) == 1
    msg = str(hits[0].message)
    assert "xm_host_a1.clausal:5" in msg
    assert '"x"' in msg and "p" in msg and "xm_owner_a1" in msg
    assert "chars" in msg and "atom" in msg
    assert "'x'" in msg            # the remedy: an atom in every mode


def test_an_atom_host_into_a_chars_module_warns(tmp_path, monkeypatch):
    _load(tmp_path, monkeypatch, "xm_owner_c1", CHARS_OWNER.format(name="xm_owner_c1"))
    host, hits = _load(tmp_path, monkeypatch, "xm_host_c1",
                       HOST.format(mode="atom", owner="xm_owner_c1", lit='"x"'))
    assert host.go() is False
    assert len(hits) == 1
    msg = str(hits[0].message)
    assert "-double_quotes(chars)" in msg     # the remedy for this direction


@pytest.mark.parametrize("mode,owner_src", [
    ("atom", ATOM_OWNER), ("chars", CHARS_OWNER)])
def test_the_same_mode_on_both_sides_is_silent(tmp_path, monkeypatch, mode,
                                               owner_src):
    owner = f"xm_owner_same_{mode}"
    _load(tmp_path, monkeypatch, owner, owner_src.format(name=owner))
    host, hits = _load(tmp_path, monkeypatch, f"xm_host_same_{mode}",
                       HOST.format(mode=mode, owner=owner, lit='"x"'))
    assert host.go() is True
    assert hits == []


def test_a_single_quoted_literal_is_an_atom_in_every_mode_so_no_warning(
        tmp_path, monkeypatch):
    _load(tmp_path, monkeypatch, "xm_owner_sq", ATOM_OWNER.format(name="xm_owner_sq"))
    host, hits = _load(tmp_path, monkeypatch, "xm_host_sq",
                       HOST.format(mode="chars", owner="xm_owner_sq", lit="'x'"))
    assert host.go() is True
    assert hits == []


def test_a_python_escape_is_not_a_clausal_literal(tmp_path, monkeypatch):
    """``++"x"`` hands the goal a Python str through the boundary; the seam
    literal rule does not apply to it and neither does this lint."""
    _load(tmp_path, monkeypatch, "xm_owner_esc", ATOM_OWNER.format(name="xm_owner_esc"))
    _, hits = _load(tmp_path, monkeypatch, "xm_host_esc",
                    HOST.format(mode="chars", owner="xm_owner_esc", lit='++"x"'))
    assert hits == []


def test_a_local_predicate_shares_the_host_mode_so_no_warning(
        tmp_path, monkeypatch):
    _, hits = _load(tmp_path, monkeypatch, "xm_host_local", """
        -double_quotes(chars)
        p("x"),

        def go():
            if --p("x"):
                return True
            return False
    """)
    assert hits == []


def test_the_dotted_module_form_over_an_import_module_base_warns(
        tmp_path, monkeypatch):
    _load(tmp_path, monkeypatch, "xm_owner_dot", ATOM_OWNER.format(name="xm_owner_dot"))
    host, hits = _load(tmp_path, monkeypatch, "xm_host_dot", """
        -double_quotes(chars)
        -import_module(xm_owner_dot)

        def go():
            if --xm_owner_dot.p("x"):
                return True
            return False
    """)
    assert host.go() is False
    assert len(hits) == 1
    assert "xm_owner_dot.p" in str(hits[0].message)


def test_a_target_that_switches_mode_mid_file_is_not_judged(
        tmp_path, monkeypatch):
    """A module whose ``"..."`` literals were read under BOTH modes has no
    single mode to compare against; the lint says nothing rather than
    guess."""
    _load(tmp_path, monkeypatch, "xm_owner_mixed", """
        -double_quotes(atom)
        -module(xm_owner_mixed, [p/1, q/1])
        p("x"),
        -double_quotes(chars)
        q("y"),
    """)
    _, hits = _load(tmp_path, monkeypatch, "xm_host_mixed",
                    HOST.format(mode="chars", owner="xm_owner_mixed", lit='"x"'))
    assert hits == []


def test_every_offending_literal_in_the_goal_is_named_once(
        tmp_path, monkeypatch):
    _load(tmp_path, monkeypatch, "xm_owner_two", """
        -double_quotes(atom)
        -module(xm_owner_two, [pair/2])
        pair("a", "b"),
    """)
    _, hits = _load(tmp_path, monkeypatch, "xm_host_two", """
        -double_quotes(chars)
        -import_from(xm_owner_two, [pair])

        def go():
            if --pair("a", "b"):
                return True
            return False
    """)
    assert len(hits) == 1
    msg = str(hits[0].message)
    assert '"a"' in msg and '"b"' in msg


# ── flip review (job 239): the paths the first tests left uncovered ──────────


def test_an_aliased_import_is_judged_under_its_local_name(tmp_path, monkeypatch):
    _load(tmp_path, monkeypatch, "xm_owner_alias", ATOM_OWNER.format(name="xm_owner_alias"))
    host, hits = _load(tmp_path, monkeypatch, "xm_host_alias", """
        -double_quotes(chars)
        -import_from(xm_owner_alias, [alias(p, pp)])

        def go():
            if --pp("x"):
                return True
            return False
    """)
    assert host.go() is False
    assert len(hits) == 1 and "`pp`" in str(hits[0].message)


# No keyword-argument case: a term written with keyword arguments
# (``pt(x="a")``) has been a load error since 2026-09-19, so a goal seam
# can never carry one and the collector's walk over ``call.keywords`` is
# reached only for the directive/EDCG shapes that keep their keywords.


def test_a_nested_imported_call_is_one_site_per_literal(tmp_path, monkeypatch):
    """``--p(q("x"))`` with both imported: ``"x"`` is an argument of ``q``
    and meets ``q``'s module, so it is reported once, against ``q``."""
    _load(tmp_path, monkeypatch, "xm_owner_nest", """
        -double_quotes(atom)
        -module(xm_owner_nest, [p/1, q(v)])
        p(q("x")),
    """)
    _, hits = _load(tmp_path, monkeypatch, "xm_host_nest", """
        -double_quotes(chars)
        -import_from(xm_owner_nest, [p, q])

        def go():
            if --p(q("x")):
                return True
            return False
    """)
    assert len(hits) == 1
    assert "`q`" in str(hits[0].message) and "`p`" not in str(hits[0].message)


def test_a_literal_only_inside_an_arrow_lambda_still_counts_as_a_mode(
        tmp_path, monkeypatch):
    """M2: the arrow-lambda TermTransformer must feed the same modes sink.
    This owner switches to chars after ``p``, and its only chars literal is
    inside a lambda body -- so it is MIXED and must not be judged.  Before
    the fix the lambda literal went unrecorded, the owner reported ``atom``
    alone, and a chars host calling ``p("x")`` was warned falsely."""
    _load(tmp_path, monkeypatch, "xm_owner_lam", """
        -double_quotes(atom)
        -module(xm_owner_lam, [p/1, q/1])
        p("x"),
        -double_quotes(chars)
        q(L) <- maplist((E <- (E == "y")), L)
    """)
    _, hits = _load(tmp_path, monkeypatch, "xm_host_lam",
                    HOST.format(mode="chars", owner="xm_owner_lam", lit='"x"'))
    assert hits == []


def test_every_term_transformer_shares_the_modes_sink():
    """The unit half of M2: a file whose only ``"..."`` literal sits in an
    arrow-lambda body reports that mode."""
    import ast
    from clausal.templating.term_rewriting import EmbedTransformer
    src = 'q(L) <- maplist((E <- (E == "y")), L)\n'
    t = EmbedTransformer(source_lines=src.splitlines(keepends=True),
                         filename="lam.clausal")
    t.visit(ast.parse(src))
    assert t._double_quotes_modes_used == {"chars"}


def test_a_dotted_base_bound_by_hosted_python_is_not_judged(tmp_path, monkeypatch):
    """The documented gap stays silent: a base that is a module-level Python
    binding (here, of the atom-mode module itself) rather than an
    ``-import_module`` is not this file's import and is left alone."""
    _load(tmp_path, monkeypatch, "xm_owner_rt", ATOM_OWNER.format(name="xm_owner_rt"))
    _, hits = _load(tmp_path, monkeypatch, "xm_host_rt", """
        -double_quotes(chars)
        import xm_owner_rt as base

        def go():
            if --base.p("x"):
                return True
            return False
    """)
    assert hits == []


def test_a_callee_with_no_recorded_mode_is_not_judged(tmp_path, monkeypatch):
    """A Python module's predicate has no Database and no mode: unknown, not
    a mode to compare against."""
    _, hits = _load(tmp_path, monkeypatch, "xm_host_pymod", """
        -double_quotes(chars)
        -import_from(py.re, [match])

        def go():
            if --match("a+", "aaa"):
                return True
            return False
    """)
    assert hits == []


def test_the_warning_survives_the_bytecode_cache(tmp_path, monkeypatch):
    """A second load of the same host file is a cache hit: its module items
    are recovered by re-transforming the source, so the sites and the
    warning come back."""
    _load(tmp_path, monkeypatch, "xm_owner_cache", ATOM_OWNER.format(name="xm_owner_cache"))
    _, first = _load(tmp_path, monkeypatch, "xm_host_cache",
                     HOST.format(mode="chars", owner="xm_owner_cache", lit='"x"'))
    assert len(first) == 1
    from clausal.import_hook import _load_module
    p = tmp_path / "xm_host_cache.clausal"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load_module("xm_host_cache_again", str(p))
    again = [w for w in caught if isinstance(w.message, ClausalCrossModeLiteralWarning)]
    assert len(again) == 1
