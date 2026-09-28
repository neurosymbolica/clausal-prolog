"""Tests for the translation system: registry, Translate/3, directive, display.

Translations are a display/surface layer — they map functor and atom names
to another language for rendering.  They do NOT create new term structures.
"""

from __future__ import annotations

import os
import pytest

from clausal.logic.atoms import mint
from clausal.logic.translations import (
    TranslatedEntry,
    register_predicate,
    register_atom,
    translate_predicate,
    reverse_translate_predicate,
    translate_atom,
    reverse_translate_atom,
    get_all_predicates,
    get_all_atoms,
    get_languages,
    _clear,
)
from tests.predicate_api_support import term_ctor
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.cells import chars, is_chars, chars_text
from clausal.terms import KWTerm, term_str, TermStyle
from clausal.import_hook import _load_module


# ── Fixture: clean registry per test ─────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_registry(request):
    # Skip clearing for integration tests that rely on directive-loaded translations.
    if request.node.cls is not None and request.node.cls.__name__ == "TestDirectiveIntegration":
        yield
        return
    _clear()
    yield
    _clear()


# ══════════════════════════════════════════════════════════════════════════════
# Registry unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRegistry:

    def test_register_predicate(self):
        # nv
        register_predicate("th", "append", "ต่อท้าย", 3, {"LIST": "รายการ", "ELEMENT": "สมาชิก", "NEWLIST": "รายการใหม่"})
        entry = translate_predicate("th", "append", 3)
        assert entry is not None
        assert entry.translated_functor == "ต่อท้าย"
        assert entry.arg_map == {"LIST": "รายการ", "ELEMENT": "สมาชิก", "NEWLIST": "รายการใหม่"}

    def test_reverse_predicate(self):
        # nv
        register_predicate("th", "append", "ต่อท้าย", 3, {"LIST": "รายการ"})
        entry = reverse_translate_predicate("th", "ต่อท้าย", 3)
        assert entry is not None
        assert entry.english_functor == "append"
        assert entry.reverse_arg_map == {"รายการ": "LIST"}

    def test_register_atom(self):
        # nv
        register_atom("th", "nil", "ว่าง")
        assert translate_atom("th", "nil") == "ว่าง"
        assert reverse_translate_atom("th", "ว่าง") == "nil"

    def test_missing_lookup_returns_none(self):
        # nv
        assert translate_predicate("th", "Nonexistent", 2) is None
        assert reverse_translate_predicate("th", "Nonexistent", 2) is None
        assert translate_atom("th", "missing") is None
        assert reverse_translate_atom("th", "missing") is None

    def test_multiple_languages(self):
        # nv
        register_predicate("th", "append", "ต่อท้าย", 3)
        register_predicate("ja", "append", "追加", 3)
        assert translate_predicate("th", "append", 3).translated_functor == "ต่อท้าย"
        assert translate_predicate("ja", "append", 3).translated_functor == "追加"

    def test_additive_merge(self):
        # nv
        register_predicate("th", "append", "ต่อท้าย", 3)
        register_predicate("th", "member", "สมาชิกของ", 2)
        assert translate_predicate("th", "append", 3) is not None
        assert translate_predicate("th", "member", 2) is not None

    def test_get_all_predicates(self):
        # nv
        register_predicate("th", "append", "ต่อท้าย", 3)
        register_predicate("th", "member", "สมาชิกของ", 2)
        register_predicate("ja", "append", "追加", 3)
        entries = get_all_predicates("th")
        assert len(entries) == 2
        names = {e.translated_functor for e in entries}
        assert names == {"ต่อท้าย", "สมาชิกของ"}

    def test_get_all_atoms(self):
        # nv
        register_atom("th", "nil", "ว่าง")
        register_atom("th", "true", "จริง")
        atoms = get_all_atoms("th")
        assert atoms == {"nil": "ว่าง", "true": "จริง"}

    def test_get_languages(self):
        # nv
        register_predicate("th", "append", "ต่อท้าย", 3)
        register_atom("ja", "nil", "空")
        assert get_languages() == {"th", "ja"}

    def test_arity_discrimination(self):
        # nv
        register_predicate("th", "Foo", "ฟู", 2)
        register_predicate("th", "Foo", "ฟูสาม", 3)
        assert translate_predicate("th", "Foo", 2).translated_functor == "ฟู"
        assert translate_predicate("th", "Foo", 3).translated_functor == "ฟูสาม"


# ══════════════════════════════════════════════════════════════════════════════
# Display integration — term_str with locale
# ══════════════════════════════════════════════════════════════════════════════

class TestDisplayLocale:

    def setup_method(self):
        register_predicate("th", "append", "ต่อท้าย", 3)
        register_atom("th", "nil", "ว่าง")

    def test_compound_with_locale(self):
        # nv
        t = ("append", 1, 2, 3)
        s = term_str(t, TermStyle(locale="th"))
        assert "ต่อท้าย" in s
        assert "append" not in s

    def test_compound_without_locale(self):
        # nv
        t = ("append", 1, 2, 3)
        s = term_str(t)
        assert "append" in s

    def test_nested_with_locale(self):
        # nv
        t = ("append", "x", ("append", 1, 2, 3), [])
        s = term_str(t, TermStyle(locale="th"))
        assert "ต่อท้าย" in s
        assert "append" not in s

    def test_predicate_meta_with_locale(self):
        # nv
        Greeting = term_ctor("greeting", ["NAME", "MESSAGE"])
        register_predicate("th", "greeting", "ทักทาย", 2)
        t = Greeting(NAME="hello", MESSAGE="world")
        s = term_str(t, TermStyle(locale="th"))
        assert "ทักทาย" in s

    def test_no_translation_passthrough(self):
        # nv
        t = ("Undefined", 1, 2)
        s = term_str(t, TermStyle(locale="th"))
        assert "Undefined" in s

    def test_atom_in_compound_arg(self):
        """Atom names inside compound args are NOT translated (strings are data)."""
        # nv
        t = ("append", chars("nil"), chars("hello"), [])
        s = term_str(t, TermStyle(locale="th"))
        # "nil" is a STRING (chars) value here, rendered DOUBLE-quoted (spec
        # §6.7) -- not an atom, which would render bare (or translated).
        assert '"nil"' in s

    def test_zero_arity_atom_with_locale(self):
        """Zero-arity PredicateMeta atoms get their name translated in display."""
        # nv
        # the atom (a make_predicate class until W4b-3 slice 6)
        nil_atom = "nil"
        s = term_str(nil_atom, TermStyle(locale="th"))
        assert "ว่าง" in s


# ══════════════════════════════════════════════════════════════════════════════
# Translate/3 builtin — produces strings
# ══════════════════════════════════════════════════════════════════════════════

class TestTranslateBuiltin:

    def setup_method(self):
        register_predicate("th", "append", "ต่อท้าย", 3)
        register_atom("th", "nil", "ว่าง")

    def test_forward_produces_string(self):
        # nv
        from clausal.logic.builtins.translations_builtin import _translate__3
        trail = Trail()
        result_var = Var()
        t = ("append", 1, 2, 3)
        gen = _translate__3(mint("th"), t, result_var, trail, None)
        sol = next(gen, "NO_SOLUTION")
        assert sol is None
        result = deref(result_var)
        assert is_chars(result)
        assert "ต่อท้าย" in chars_text(result)

    def test_result_is_string_not_term(self):
        # nv
        from clausal.logic.builtins.translations_builtin import _translate__3
        trail = Trail()
        result_var = Var()
        t = ("append", 1, 2, 3)
        gen = _translate__3(mint("th"), t, result_var, trail, None)
        next(gen, None)
        result = deref(result_var)
        # Must be a string
        assert is_chars(result)

    def test_unbound_lang_fails(self):
        # nv
        from clausal.logic.builtins.translations_builtin import _translate__3
        trail = Trail()
        t = ("append", 1, 2, 3)
        solutions = list(_translate__3(Var(), t, Var(), trail, None))
        assert len(solutions) == 0

    def test_atom_lang_accepted(self):
        """Language can be a zero-arity PredicateMeta atom."""
        # nv
        from clausal.logic.builtins.translations_builtin import _translate__3
        trail = Trail()
        result_var = Var()
        # the atom (a make_predicate class until W4b-3 slice 6)
        th_atom = "th"
        t = ("append", 1, 2, 3)
        gen = _translate__3(th_atom, t, result_var, trail, None)
        sol = next(gen, "NO_SOLUTION")
        assert sol is None
        result = deref(result_var)
        assert is_chars(result)
        assert "ต่อท้าย" in chars_text(result)

    def test_nested_translation(self):
        # nv
        from clausal.logic.builtins.translations_builtin import _translate__3
        register_predicate("th", "member", "สมาชิกของ", 2)
        trail = Trail()
        result_var = Var()
        t = ("append", "x", ("member", "a", "b"), [])
        gen = _translate__3(mint("th"), t, result_var, trail, None)
        next(gen, None)
        result = deref(result_var)
        assert "ต่อท้าย" in chars_text(result)
        assert "สมาชิกของ" in chars_text(result)
        assert "append" not in result
        assert "member" not in result


# ══════════════════════════════════════════════════════════════════════════════
# Directive parsing + .clausal integration
# ══════════════════════════════════════════════════════════════════════════════

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


class TestDirectiveIntegration:

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("translations_basic")

    def test_predicate_translations_loaded(self):
        # nv
        entry = translate_predicate("th", "append", 3)
        assert entry is not None
        assert entry.translated_functor == "ต่อท้าย"
        assert entry.arg_map["LIST"] == "รายการ"

        entry2 = translate_predicate("th", "member", 2)
        assert entry2 is not None
        assert entry2.translated_functor == "สมาชิกของ"

        entry3 = translate_predicate("th", "greeting", 2)
        assert entry3 is not None
        assert entry3.translated_functor == "ทักทาย"

    def test_atom_translations_loaded(self):
        # nv
        assert translate_atom("th", "nil") == "ว่าง"
        assert translate_atom("th", "hello") == "สวัสดี"
        assert reverse_translate_atom("th", "ว่าง") == "nil"

    @pytest.mark.parametrize("name", [
        "translate produces string",
        "translate produces nonempty",
    ])
    def test_fixture(self, name):
        # nv
        from clausal.logic.solve import call
        # THE FLIP: a test/1 description written ``"..."`` in the fixture is
        # an ATOM under this file's ``-double_quotes(atom)``.
        for _ in call("test", mint(name), module=self.mod):
            return
        pytest.fail(f"Test predicate '{name}' failed")
