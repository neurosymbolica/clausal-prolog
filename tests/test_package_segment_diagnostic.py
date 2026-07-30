"""A dotted import that fails on a non-identifier directory says so.

``eu/state-aid/`` on disk cannot be the ``state_aid`` segment of a dotted
import — a package directory's name IS its import segment, and ``state-aid``
is not a Python identifier.  The finder therefore misses, and the author was
told ``No module named 'eu.state_aid'`` while looking straight at the
directory.  Two separate defects made that message wrong:

* the *intermediate*-segment shape (``-import_from(eu.state_aid.gber, …)``
  against a hyphenated ``eu/state-aid/``) raised with ``name='eu.state_aid'``,
  a strict prefix of the declared path, so ``enrich_import_error`` did not
  recognise it as this file's own directive at all and CPython's bare one-liner
  escaped;
* even when it was recognised, the message asserted that no such file "is on
  the import path", which is false when the directory is sitting right there.

See ``todo/done/package-finder-nonidentifier-segment-diagnostic.md``.
"""

from __future__ import annotations

import importlib
import sys

import pytest

import clausal.import_hook  # installs the finders
from clausal.import_hook import _load_module


def _flat(text):
    """*text* with its wrapping collapsed.

    The message is wrapped to 78 columns, so a sentence pinned by a test
    straddles line breaks at path lengths the test cannot control.  Assert on
    the sentence, not on where textwrap happened to break it.
    """
    return " ".join(text.split())


@pytest.fixture
def on_path(tmp_path):
    """``tmp_path`` on ``sys.path``, with every module it introduced evicted."""
    before = set(sys.modules)
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


@pytest.fixture
def two_dirs_on_path(tmp_path):
    """``(d1, d2)`` on ``sys.path`` in that order — d1 searched first.

    Order is the whole point of these tests, so it is fixed here rather than
    left to whatever ``sys.path`` already held.
    """
    before = set(sys.modules)
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    sys.path.insert(0, str(d2))
    sys.path.insert(0, str(d1))
    importlib.invalidate_caches()
    try:
        yield d1, d2
    finally:
        for name in list(sys.modules):
            if name not in before:
                sys.modules.pop(name, None)
        for entry in (str(d1), str(d2)):
            try:
                sys.path.remove(entry)
            except ValueError:
                pass
        importlib.invalidate_caches()


def _pkg(root, *segments, exports="Aid/1"):
    """A package directory ``root/seg/…`` carrying an ``__init__.clausal``."""
    d = root
    for seg in segments:
        d = d / seg
    d.mkdir(parents=True)
    name = segments[-1].replace("-", "_")
    (d / "__init__.clausal").write_text(
        f"-module({name}, [{exports}])\n{exports.split('/')[0]}(1),\n")
    return d


def _load_error(root, source, modname="_seg_use"):
    """Write *source* as the importing file and return the ImportError."""
    use = root / "use.clausal"
    use.write_text(source)
    sys.modules.pop(modname, None)
    with pytest.raises(ImportError) as exc:
        _load_module(modname, str(use))
    return exc.value


# ── the hyphenated directory, named ──────────────────────────────────────────


class TestHyphenatedDirectory:

    def test_the_directory_and_the_identifier_rule_are_both_named(self, on_path):
        pkg = _pkg(on_path, "eu", "state-aid")
        msg = _flat(str(_load_error(
            on_path, "-import_from(eu.state_aid, [Aid])\n")))

        assert (f"{pkg} is there, but 'state-aid' is not a valid Python "
                f"identifier, so no dotted import can name it — 'state_aid' "
                f"is a different segment, not a spelling of it." in msg)

    def test_the_remedy_is_the_rename(self, on_path):
        _pkg(on_path, "eu", "state-aid")
        msg = _flat(str(_load_error(
            on_path, "-import_from(eu.state_aid, [Aid])\n")))

        assert ("-> rename the directory 'state-aid' to 'state_aid'. Renaming "
                "is the only repair: a package directory is importable only "
                "under its own name, so the import cannot be adjusted to meet "
                "it." in msg)

    def test_an_intermediate_hyphenated_segment_is_diagnosed(self, on_path):
        """The shape from the migration: the hyphen is *not* the last segment,
        so ``exc.name`` is a strict prefix of the declared path."""
        pkg = _pkg(on_path, "eu", "state-aid")
        (pkg / "gber.clausal").write_text(
            "-module(gber, [Gber/1])\nGber(1),\n")

        # ``Gber``, not ``G``: an ALL-CAPS imported name is refused at load
        # time as a logic-variable name (term_rewriting's
        # ``-import_from`` check), which would preempt the import failure this
        # test is about.  The name is incidental here either way.
        msg = _flat(str(_load_error(
            on_path, "-import_from(eu.state_aid.gber, [Gber])\n")))

        # Previously this escaped enrichment entirely: no directive, no file,
        # no directory — just "No module named 'eu.state_aid'".
        assert "-import_from(eu.state_aid.gber, [Gber])" in msg
        assert ("the segment 'state_aid' did not resolve, so neither can "
                "'eu.state_aid.gber'" in msg)
        assert f"{pkg} is there, but 'state-aid' is not a valid Python" in msg

    def test_import_module_directive_too(self, on_path):
        _pkg(on_path, "eu", "state-aid")
        msg = _flat(str(_load_error(
            on_path, "-import_module(eu.state_aid)\n")))

        assert "-import_module(eu.state_aid)" in msg
        assert "rename the directory 'state-aid' to 'state_aid'" in msg

    def test_a_top_level_hyphenated_directory_is_found_too(self, on_path):
        """No parent package: the search path is ``sys.path`` itself."""
        pkg = _pkg(on_path, "state-aid")
        msg = _flat(str(_load_error(
            on_path, "-import_from(state_aid, [Aid])\n")))

        assert f"{pkg} is there, but 'state-aid' is not a valid Python" in msg

    def test_it_stays_a_ModuleNotFoundError(self, on_path):
        _pkg(on_path, "eu", "state-aid")
        use = on_path / "use.clausal"
        use.write_text("-import_from(eu.state_aid, [Aid])\n")
        sys.modules.pop("_seg_cls", None)
        with pytest.raises(ModuleNotFoundError):
            _load_module("_seg_cls", str(use))


class TestHyphenatedSourceFile:

    def test_a_hyphenated_clausal_file_is_named_as_the_reason(self, on_path):
        pkg = _pkg(on_path, "eu", exports="Eu/1")
        (pkg / "state-aid.clausal").write_text(
            "-module(state_aid, [Aid/1])\nAid(1),\n")

        msg = _flat(str(_load_error(
            on_path, "-import_from(eu.state_aid, [Aid])\n")))

        assert (f"{pkg / 'state-aid.clausal'} is there, but 'state-aid' is not "
                f"a valid Python identifier" in msg)
        assert ("rename the file 'state-aid.clausal' to 'state_aid.clausal'. "
                "Renaming is the only repair: a module file is importable only "
                "under its own name" in msg)


# ── the old sentence, kept where it was right ────────────────────────────────


class TestGenuinelyAbsentModule:

    def test_absent_module_keeps_the_missing_module_sentence(self, on_path):
        _pkg(on_path, "eu", exports="Eu/1")
        msg = _flat(str(_load_error(
            on_path, "-import_from(eu.no_such_thing, [Aid])\n")))

        assert "names a module that does not exist" in msg
        assert "no export list to show" in msg
        # Nothing on disk resembles the segment, so claiming a naming fault
        # would be an invention.
        assert "not a valid Python identifier" not in msg
        assert "rename the directory" not in msg

    def test_absent_intermediate_segment_says_where_it_stopped(self, on_path):
        """A prefix miss with nothing to point at still names the segment
        rather than blaming the whole dotted path."""
        _pkg(on_path, "eu", exports="Eu/1")
        msg = _flat(str(_load_error(
            on_path, "-import_from(eu.nope.deeper, [Aid])\n")))

        assert "-import_from(eu.nope.deeper, [Aid])" in msg
        assert ("the segment 'nope' did not resolve, so neither can "
                "'eu.nope.deeper'" in msg)
        assert "not a valid Python identifier" not in msg


# ── the scan itself ─────────────────────────────────────────────────────────


class TestMisnamedPathEntryScan:
    """``_misnamed_path_entry`` is the whole risk surface: it must claim a
    naming fault only when the claim is a tautology."""

    @staticmethod
    def _scan(dotted):
        from clausal.import_diagnostics import _misnamed_path_entry
        return _misnamed_path_entry(dotted)

    def test_finds_a_hyphenated_directory(self, on_path):
        _pkg(on_path, "eu", "state-aid")
        importlib.import_module("eu")

        hit = self._scan("eu.state_aid")

        assert hit is not None
        assert hit.entry == "state-aid"
        assert hit.stem == "state-aid"
        assert hit.kind == "directory"

    def test_says_nothing_when_the_correctly_named_entry_also_exists(
            self, on_path):
        """If ``state_aid`` is on the search path too, the import failed for
        some other reason and the hyphenated sibling is not the story."""
        _pkg(on_path, "eu", "state-aid")
        _pkg(on_path / "eu", "state_aid")
        importlib.import_module("eu")

        assert self._scan("eu.state_aid") is None

    def test_a_correct_spelling_in_a_LATER_directory_still_aborts_the_scan(
            self, two_dirs_on_path):
        """The abort is a property of the search path, not of one directory.

        Checked per-directory it depended on order: ``d1/state-aid`` was
        reported while ``d2/state_aid`` sat correctly spelled further down the
        path, and the author was told to rename a directory that was not the
        reason for anything.  ``d2/state_aid`` here is a plain file, so the
        import still fails — the point is that the hyphen is no longer offered
        as the explanation.
        """
        d1, d2 = two_dirs_on_path
        _pkg(d1, "state-aid")
        (d2 / "state_aid").write_text("not an importable module\n")

        assert self._scan("state_aid") is None

    def test_a_later_correct_spelling_keeps_the_absent_module_sentence(
            self, two_dirs_on_path):
        """End to end: no rename advice, because renaming would repair nothing."""
        d1, d2 = two_dirs_on_path
        _pkg(d1, "state-aid")
        (d2 / "state_aid").write_text("not an importable module\n")
        msg = _flat(str(_load_error(
            d1, "-import_from(state_aid, [Aid])\n", modname="_seg_order")))

        assert "names a module that does not exist" in msg
        assert "not a valid Python identifier" not in msg
        assert "rename the directory" not in msg

    def test_says_nothing_about_an_unrelated_hyphenated_directory(
            self, on_path):
        _pkg(on_path, "eu", "some-other-thing")
        importlib.import_module("eu")

        assert self._scan("eu.state_aid") is None

    def test_ignores_files_that_are_not_importable_sources(self, on_path):
        _pkg(on_path, "eu", exports="Eu/1")
        (on_path / "eu" / "state-aid.txt").write_text("notes\n")
        importlib.import_module("eu")

        assert self._scan("eu.state_aid") is None

    def test_says_nothing_when_the_parent_package_is_unimportable(self):
        """No parent in ``sys.modules`` means no search path to scan; the scan
        must decline rather than guess at ``sys.path``."""
        assert self._scan("no_such_parent_pkg.state_aid") is None
