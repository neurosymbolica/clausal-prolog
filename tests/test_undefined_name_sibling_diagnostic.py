"""``name 'cite' is not defined`` must name the sibling that exports ``cite``.

A module in a decomposed-DAG package uses a predicate a sibling module exports
and forgets to import it.  CPython's stock ``NameError`` states the absence and
nothing else, while the owner is fully decidable from the package directory —
the sibling's ``-module(...)`` list has the name in it.

Measured, not speculative: in a 24-run local-model formalization study
``NameError: cite`` burned 16 attempts across 3 runs and never recovered, every
retry byte-identical, because there was nothing in the message to act on.  See
``todo/done/nameerror-does-not-name-the-sibling-that-exports-it.md``.

House rule, same as ``tests/test_import_export_diagnostic.py`` and
``tests/test_predicate_not_found_diagnostic.py``: say what is available and
where, not only what is missing — and say nothing at all when the question is
undecidable.
"""

from __future__ import annotations

import importlib
import re
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 - installs the finders
from clausal.predicate_diagnostics import (
    UndefinedNameError,
    enrich_undefined_name,
)
from clausal.testing import main


def _flat(text):
    """*text* with its wrapping collapsed — assert on the sentence, not on
    where ``textwrap`` happened to break it."""
    return " ".join(text.split())


def write(directory, name, src):
    path = directory / name
    path.write_text(textwrap.dedent(src).lstrip())
    return path


@pytest.fixture
def pkg(tmp_path):
    """A two-file package on ``sys.path``, with its modules evicted after."""
    before = set(sys.modules)
    write(tmp_path, "undefsib_citations.clausal", """
        # clausal: no-collect
        -module(undefsib_citations, [cite(KEY), art_9])

        cite(art_9),
    """)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        yield tmp_path
    finally:
        for name in list(sys.modules):
            if name not in before:
                sys.modules.pop(name, None)
        try:
            sys.path.remove(str(tmp_path))
        except ValueError:
            pass
        importlib.invalidate_caches()


# The reported failure verbatim: `cite` used in a dict value, `art_9` imported
# from the sibling, `cite` not.  The NameError fires at solve time, from inside
# the compiled predicate.
SOLVE_TIME_SRC = """
    -import_from(undefsib_citations, [art_9])

    -private([ground_a])

    grounds({ground_a: cite(art_9)}),

    test("grounds are defined with citations") <- (
        grounds(GROUNDS)
    ),
"""


def _run(pkg, src, name="undefsib_use.clausal"):
    path = write(pkg, name, src)
    assert main([str(path)]) == 1
    return path


# ── the sibling is named ─────────────────────────────────────────────────────


class TestSolveTimeRaise:

    def test_names_the_sibling_that_exports_it(self, capsys, pkg):
        _run(pkg, SOLVE_TIME_SRC)
        out = capsys.readouterr().out
        assert "undefsib_citations" in out
        assert "sibling" in out

    def test_gives_the_arity_from_the_export_list(self, capsys, pkg):
        """``cite(KEY)`` in ``-module(...)`` is ``cite/1`` in the text."""
        _run(pkg, SOLVE_TIME_SRC)
        assert "cite/1" in capsys.readouterr().out

    def test_offers_the_extended_import_directive(self, capsys, pkg):
        """The file already imports ``art_9`` from that module — the remedy is
        to add one name to the list it already wrote, not to write a new
        directive beside it."""
        _run(pkg, SOLVE_TIME_SRC)
        out = _flat(capsys.readouterr().out)
        assert "-import_from(undefsib_citations, [art_9, cite])" in out

    def test_an_aliased_import_list_is_reproduced_faithfully(self, capsys,
                                                             pkg):
        """The remedy reprints the directive to *replace* the old one with, so
        an entry it cannot spell would read as an instruction to delete an
        import the file needs."""
        _run(pkg, """
            -import_from(undefsib_citations, [alias(art_9, a9)])

            -private([ground_a])

            grounds({ground_a: cite(a9)}),

            test("aliased import") <- (
                grounds(GROUNDS)
            ),
        """)
        out = _flat(capsys.readouterr().out)
        assert ("-import_from(undefsib_citations, [alias(art_9, a9), cite])"
                in out)

    def test_writes_a_new_directive_when_there_is_none_to_extend(self, capsys,
                                                                 pkg):
        _run(pkg, """
            -private([ground_a])

            grounds({ground_a: cite(1)}),

            test("no existing import") <- (
                grounds(GROUNDS)
            ),
        """)
        out = _flat(capsys.readouterr().out)
        assert "-import_from(undefsib_citations, [cite])" in out

    def test_keeps_the_stock_first_line(self, capsys, pkg):
        """The header a reader greps for must not move."""
        _run(pkg, SOLVE_TIME_SRC)
        out = capsys.readouterr().out
        assert "name 'cite' is not defined" in out


class TestLoadTimeRaise:
    """The same mistake at module-exec time, before any goal runs."""

    SRC = """
        -import_from(undefsib_citations, [art_9])

        REF = cite(art_9)

        grounds(REF),

        test("grounds are defined with citations") <- (
            grounds(GROUNDS)
        ),
    """

    def test_names_the_sibling_that_exports_it(self, capsys, pkg):
        _run(pkg, self.SRC)
        out = capsys.readouterr().out
        assert "<load>" in out
        assert "undefsib_citations" in out
        assert "cite/1" in out


class TestTermClassShape:
    """The other NameError the same mistake produces.

    When the compiler can see ``cite`` as a call target it injects a dispatch
    adapter, and using it to *build* a term raises ``Predicate 'cite/1' is not
    in scope as a term class`` — a different sentence for the identical fault,
    and one that says "import it first" without saying from where.
    """

    SRC = """
        -import_from(undefsib_citations, [art_9])

        grounds([cite(art_9)]),

        test("grounds are defined with citations") <- (
            grounds(GROUNDS)
        ),
    """

    def test_still_names_the_sibling(self, capsys, pkg):
        _run(pkg, self.SRC)
        out = capsys.readouterr().out
        assert "not in scope as a term class" in out
        assert "undefsib_citations" in out


# ── it must not misattribute ─────────────────────────────────────────────────


class TestUndecidableStaysBare:

    NO_OWNER_SRC = """
        -private([ground_a])

        grounds({ground_a: zzz_nobody_exports_this(1)}),

        test("no owner anywhere") <- (
            grounds(GROUNDS)
        ),
    """

    def test_no_sibling_means_no_hint(self, capsys, pkg):
        """Undecidable, and the todo is explicit that it stays as-is."""
        _run(pkg, self.NO_OWNER_SRC)
        out = capsys.readouterr().out
        assert "name 'zzz_nobody_exports_this' is not defined" in out
        # Not `"sibling" not in out`: pytest's tmp_path is named after the
        # test, so that substring is in every path this run prints.
        assert "IS exported by" not in out
        assert "-import_from(" not in out

    def test_a_sibling_that_does_not_export_it_is_not_named(self, capsys, pkg):
        """``undefsib_citations`` is right there and exports ``cite``, not this
        name — naming it anyway would be the misattribution the hint exists to
        avoid."""
        _run(pkg, self.NO_OWNER_SRC)
        assert "undefsib_citations" not in capsys.readouterr().out


def test_a_plain_python_nameerror_is_untouched():
    """A NameError from ordinary Python code is none of this diagnostic's
    business: there is no Clausal module frame to attribute it to."""
    try:
        eval("zzz_nobody_exports_this")  # noqa: S307
    except NameError as exc:
        assert enrich_undefined_name(exc) is None
    else:  # pragma: no cover
        raise AssertionError("expected a NameError")


# ── the exception itself ─────────────────────────────────────────────────────


def _raised(pkg, src):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var

    path = write(pkg, "undefsib_exc.clausal", src)
    mod = _load_module("undefsib_exc", str(path))
    with pytest.raises(NameError) as exc:
        list(call("grounds", Var(), module=mod.__dict__["$module"]))
    return exc.value


class TestTheExceptionObject:

    def test_is_still_a_nameerror(self, pkg):
        assert isinstance(_raised(pkg, SOLVE_TIME_SRC), NameError)

    def test_keeps_the_missing_name_attribute(self, pkg):
        assert _raised(pkg, SOLVE_TIME_SRC).name == "cite"

    def test_the_hint_renders_in_str_only(self, pkg):
        """Same discipline as the ``is``/``==`` note: ``args`` is byte-identical
        to CPython's, so a caught term cannot carry the hint and ``catch/3``
        cannot match on it."""
        exc = _raised(pkg, SOLVE_TIME_SRC)
        assert exc.args == ("name 'cite' is not defined",)
        assert "sibling" not in repr(exc)
        assert "sibling" in str(exc)

    def test_first_line_of_str_is_the_stock_message(self, pkg):
        exc = _raised(pkg, SOLVE_TIME_SRC)
        assert str(exc).splitlines()[0] == "name 'cite' is not defined"

    def test_a_broken_scan_leaves_the_original_error_alone(self, pkg,
                                                           monkeypatch):
        """A diagnostic that fails must not replace one failure with another.

        The scan runs once, in ``enrich_undefined_name``, whose result is
        handed to the exception — so this is where an exploding scan has to be
        survivable.  It must decline (leaving a stock ``NameError`` to
        propagate) rather than let its own RuntimeError escape.
        """
        import clausal.predicate_diagnostics as pd

        def _boom(*a, **k):
            raise RuntimeError("scan exploded")

        monkeypatch.setattr(pd, "_undefined_name_lines", _boom)
        exc = _raised(pkg, SOLVE_TIME_SRC)
        assert type(exc) is NameError
        assert str(exc) == "name 'cite' is not defined"

    def test_a_broken_scan_degrades_to_the_stock_message(self, monkeypatch):
        """The same guarantee on ``__str__``'s own fallback.

        An instance built directly carries no precomputed lines, so rendering
        it does scan — and that scan may not out-fail the error it explains.
        """
        import clausal.predicate_diagnostics as pd

        def _boom(*a, **k):
            raise RuntimeError("scan exploded")

        monkeypatch.setattr(pd, "_undefined_name_lines", _boom)
        exc = UndefinedNameError("name 'cite' is not defined", name="cite",
                                 module_name="pkg.constants",
                                 module_file="/nonexistent/constants.clausal")
        assert exc.hint_lines is None
        assert str(exc) == "name 'cite' is not defined"


# ── cost ─────────────────────────────────────────────────────────────────────


def test_no_scan_on_the_success_path(pkg, monkeypatch):
    """The scan reads sibling sources; it must never run when nothing failed."""
    import clausal.predicate_diagnostics as pd

    def _boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("the sibling scan ran on the success path")

    monkeypatch.setattr(pd, "enrich_undefined_name", _boom)

    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var

    path = write(pkg, "undefsib_ok.clausal", """
        -import_from(undefsib_citations, [art_9, cite])

        grounds(cite(art_9)),
    """)
    mod = _load_module("undefsib_ok", str(path))
    assert len(list(call("grounds", Var(), module=mod.__dict__["$module"]))) == 1


# ── the message builder in isolation ─────────────────────────────────────────


def test_message_shape(pkg):
    exc = _raised(pkg, SOLVE_TIME_SRC)
    text = str(exc)
    assert re.search(r"cite/1 IS exported by", text)
    assert re.search(r"^\s+undefsib_citations\s*$", text, re.M)
    assert "->" in text


def test_the_scan_runs_once_per_failure(pkg, monkeypatch):
    """The directory scan is computed once and carried, not recomputed.

    ``enrich_undefined_name`` has to run it to decide whether there is anything
    to say; rendering must reuse that result.  Rendering twice matters because
    ``catch/3``'s ``python_error_term`` conversion reads ``str(exc)`` on top of
    whatever printed it first.
    """
    import clausal.predicate_diagnostics as pd

    calls = []
    real = pd._undefined_name_lines

    def _counted(*a, **k):
        calls.append(a)
        return real(*a, **k)

    monkeypatch.setattr(pd, "_undefined_name_lines", _counted)
    exc = _raised(pkg, SOLVE_TIME_SRC)
    assert len(calls) == 1

    str(exc)
    str(exc)
    assert len(calls) == 1, "rendering re-scanned the package directory"


def test_no_duplicate_import_advice_when_the_name_is_already_imported(
        monkeypatch):
    """Already importing the name from the exporter is not an import miss.

    The remedy block declines rather than falling through to "write a new
    -import_from", which would advise a second directive for a module the file
    already imports from.
    """
    import clausal.predicate_diagnostics as pd

    export = pd._Export("pkg.citations", "cite/1", "/pkg/citations.clausal")
    directives = [("pkg.citations", "pkg.citations", ["cite"])]
    monkeypatch.setattr(pd, "_import_from_directives", lambda path: directives)

    assert pd._import_remedy("cite", export, "/pkg/constants.clausal",
                             "pkg.constants") == []

    # ...but a name genuinely absent from that directive still gets advice.
    directives[0] = ("pkg.citations", "pkg.citations", ["art_9"])
    remedy = pd._import_remedy("cite", export, "/pkg/constants.clausal",
                               "pkg.constants")
    assert any("art_9, cite" in line for line in remedy)
