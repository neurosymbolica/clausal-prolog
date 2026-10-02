"""`cannot import name X from M` must say what M *does* export.

See ``todo/done/import-error-should-list-module-exports.md``.  The stock Python
message names the file but never the vocabulary, which is the one piece of
information a repair needs.  The loader knows it exactly, so it appends it at
the raise site — and distinguishes the three cases the author cannot:

* the module exists and is Clausal but does not export that name → list exports,
* the module does not exist at all                              → say so,
  and explicitly say there is no export list rather than printing an empty one,
* the module exists but is not a Clausal module                 → hands off,
  Python's own message verbatim.
"""

import os
import re
import sys

import pytest

from clausal.import_hook import _load_module

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    return os.path.join(FIXTURES, name)


def _load(modname, fixture):
    """Load a fixture under a throwaway module name, isolated from the cache."""
    for stale in [k for k in sys.modules
                  if k.startswith("tests.fixtures.impexp_")]:
        del sys.modules[stale]
    sys.modules.pop(modname, None)
    return _load_module(modname, _fixture(fixture))


def _load_error(modname, fixture):
    with pytest.raises(ImportError) as exc:
        _load(modname, fixture)
    return exc.value


# ── Case 1: module exists, is Clausal, lacks the name ────────────────────────


class TestMissingNameListsExports:

    def test_message_names_the_missing_name_and_module(self):
        msg = str(_load_error("_impexp_use_1", "impexp_use.seam"))
        assert "cannot import name 'within_limit'" in msg
        assert "tests.fixtures.impexp_schema" in msg
        # Python's own first line is preserved verbatim, path and all.
        assert msg.splitlines()[0].endswith("impexp_schema.seam)")

    def test_message_lists_the_export_vocabulary(self):
        msg = str(_load_error("_impexp_use_2", "impexp_use.seam"))
        assert "impexp_schema exports:" in msg
        for name in ("beneficial_owner", "not_beneficial_owner", "holdings",
                     "person", "entity", "overall", "as_of_date",
                     "exceeds_limit"):
            assert name in msg, name

    def test_predicates_carry_arity_atoms_do_not(self):
        msg = str(_load_error("_impexp_use_3", "impexp_use.seam"))
        assert "verdict/2" in msg
        # A bare atom is rendered bare, exactly as -module(...) declares it.
        assert re.search(r"\bbeneficial_owner\b(?!/)", msg)
        assert "beneficial_owner/0" not in msg

    def test_near_miss_suggestion(self):
        msg = str(_load_error("_impexp_use_4", "impexp_use.seam"))
        assert "did you mean" in msg
        assert re.search(r"did you mean:[^\n]*\bexceeds_limit\b", msg)

    def test_message_states_both_remedies(self):
        msg = str(_load_error("_impexp_use_5", "impexp_use.seam"))
        assert "-module(" in msg
        assert "within_limit" in msg
        assert "remove every use" in msg

    def test_alias_form_is_diagnosed_too(self):
        msg = str(_load_error("_impexp_alias", "impexp_alias_use.seam"))
        assert "cannot import name 'within_limit'" in msg
        assert "impexp_schema exports:" in msg
        assert "exceeds_limit" in msg

    def test_error_is_still_an_ImportError_with_intact_attributes(self):
        err = _load_error("_impexp_use_6", "impexp_use.seam")
        assert isinstance(err, ImportError)
        assert err.name == "tests.fixtures.impexp_schema"
        assert err.name_from == "within_limit"
        assert err.path and err.path.endswith("impexp_schema.seam")

    def test_diagnostic_survives_an_import_chain_without_doubling(self):
        """A → B → (stale import) still reports B's failure, enriched once."""
        msg = str(_load_error("_impexp_chain", "impexp_chain_top.seam"))
        assert msg.count("impexp_schema exports:") == 1
        assert "exceeds_limit" in msg


# ── Case 2: the module does not exist at all ─────────────────────────────────


class TestMissingModule:

    def test_says_the_module_does_not_exist(self):
        msg = str(_load_error("_impexp_missing_mod",
                              "impexp_missing_mod_use.seam"))
        assert "tests.fixtures.impexp_no_such_schema" in msg
        assert "does not exist" in msg

    def test_does_not_print_an_empty_export_list(self):
        msg = str(_load_error("_impexp_missing_mod_2",
                              "impexp_missing_mod_use.seam"))
        assert "exports:" not in msg
        assert "no export list" in msg

    def test_names_the_offending_directive_and_file(self):
        msg = str(_load_error("_impexp_missing_mod_3",
                              "impexp_missing_mod_use.seam"))
        assert "-import_from(tests.fixtures.impexp_no_such_schema" in msg
        assert "impexp_missing_mod_use.seam" in msg

    def test_keeps_the_ModuleNotFoundError_class(self):
        with pytest.raises(ModuleNotFoundError):
            _load("_impexp_missing_mod_4", "impexp_missing_mod_use.seam")

    def test_import_module_directive_too(self):
        msg = str(_load_error("_impexp_missing_im",
                              "impexp_missing_import_module_use.seam"))
        assert ("-import_module(tests.fixtures.impexp_no_such_module_either)"
                in msg)
        assert "does not exist" in msg
        assert "exports:" not in msg


# ── Case 3: not a Clausal module — Python's message, untouched ───────────────


class TestPythonModulesPassThrough:

    def test_missing_name_in_a_python_library_is_verbatim(self):
        msg = str(_load_error("_impexp_pylib", "impexp_pylib_use.seam"))
        assert "cannot import name 'impexp_no_such_regex_helper'" in msg
        assert "exports:" not in msg
        assert "did you mean" not in msg
        assert "-module(" not in msg
        # Single line: nothing was appended.
        assert len(msg.splitlines()) == 1

    def test_import_error_raised_inside_a_python_module_is_verbatim(self):
        err = _load_error("_impexp_pyraiser", "impexp_pyraiser_use.seam")
        msg = str(err)
        assert "impexp_definitely_not_a_real_package_zzz" in msg
        assert "exports:" not in msg
        assert "no export list" not in msg
        assert len(msg.splitlines()) == 1


# ── Clausal module that declares no -module(...) at all ──────────────────────


class TestNoModuleDirective:

    def test_says_there_is_no_export_list_and_shows_what_is_defined(self):
        msg = str(_load_error("_impexp_nomodule",
                              "impexp_nomodule_use.seam"))
        assert "no -module(...) export list" in msg
        # Still actionable: the names the module really binds.
        assert "impexp_nm_alpha/1" in msg
        assert "impexp_nm_beta/2" in msg

    def test_an_empty_export_list_says_EMPTY_not_absent(self):
        msg = str(_load_error("_impexp_empty",
                              "impexp_empty_module_use.seam"))
        assert "EMPTY -module(...) export list" in msg
        # Still tells the reader what is actually there.
        assert "impexp_em_helper/1" in msg


class TestUnreadableSource:
    """If the target's source cannot be re-read, claim nothing about it."""

    def test_says_it_could_not_recover_the_module_list(self, monkeypatch):
        # Pre-load the sibling under its real dotted name, so the importer
        # resolves it straight out of sys.modules: the module object is live
        # but its declarations are unrecoverable.
        schema = _load("tests.fixtures.impexp_schema", "impexp_schema.seam")

        def boom(path):
            raise OSError("source is gone")

        # Patch the TARGET module's loader instance only — patching the class
        # would also break the importing file's own cache-hit recovery.
        monkeypatch.setattr(schema.__loader__, "_recover_module_items", boom)
        sys.modules.pop("_impexp_unreadable", None)
        with pytest.raises(ImportError) as exc:
            _load_module("_impexp_unreadable", _fixture("impexp_use.seam"))
        msg = str(exc.value)
        sys.modules.pop("tests.fixtures.impexp_schema", None)
        assert "could not re-read" in msg
        # It must NOT assert the absence of a -module list it never read.
        assert "no -module(...) export list" not in msg


# ── Truncation must announce itself ──────────────────────────────────────────


class TestTruncation:

    def test_long_export_list_is_capped_and_says_so(self):
        msg = str(_load_error("_impexp_wide", "impexp_wide_use.seam"))
        assert "impexp_wide exports:" in msg
        shown = re.findall(r"wide_export_\d\d", msg)
        assert len(set(shown)) < 60, "list was not capped"
        assert "60 total" in msg
        assert "NOT SHOWN" in msg
        # The full path is given so the reader can go and look.
        assert "impexp_wide.seam" in msg

    def test_a_whole_family_of_equal_near_misses_suggests_nothing(self):
        """60 siblings score identically; three of them is a coin toss."""
        msg = str(_load_error("_impexp_wide_2", "impexp_wide_use.seam"))
        assert "did you mean" not in msg


# ── The happy path is untouched ──────────────────────────────────────────────


def test_valid_import_still_works():
    mod = _load("_impexp_ok", "impexp_schema.seam")
    assert mod.exceeds_limit is not None
