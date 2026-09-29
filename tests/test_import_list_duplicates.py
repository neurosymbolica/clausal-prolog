"""F3 (multi-arity plan section F): an ``-import_from`` list that names the
same thing twice is deduplicated silently (``[baz, baz]``, ``[baz/1, baz/1]``,
``[baz, baz/1]`` -- a bare name already brings every arity); two entries that
bind ONE local name to two different things are an error."""

from __future__ import annotations

import pytest

from clausal import Var

from tests.test_import_by_indicator import _answers, _load, lib_dir  # noqa: F401


class TestDuplicateEntries:
    """F3: the same entry twice means it once; one local name bound to two
    different things is an error."""

    @pytest.mark.parametrize("entries", [
        "[g, g]", "[g/1, g/1]", "[g, g/1]", "[g/1, g]",
        "[alias(g, gg), alias(g, gg)]",
    ])
    def test_a_repeated_entry_is_one_import(self, lib_dir, entries):
        mod = _load(lib_dir, "ibi_dup", f"""
            -import_from(ibi_lib, {entries})
            ok,
        """)
        [item] = [i for i in mod.__dict__["__clausal_import_from__"]]
        assert item[1] == "ibi_lib"

    def test_bare_plus_indicator_is_every_arity(self, lib_dir):
        mod = _load(lib_dir, "ibi_dup_union", """
            -import_from(ibi_lib, [g/1, g])
            both(A, B) <- (g(A), g(B, 5))
        """)
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(1, 5)]

    def test_one_local_name_for_two_originals_is_an_error(self, lib_dir):
        with pytest.raises(SyntaxError) as info:
            _load(lib_dir, "ibi_dup_conflict", """
                -import_from(ibi_lib, [alias(g, x), alias(h, x)])
            """)
        text = " ".join(str(info.value).split())
        assert "`x`" in text and "g" in text and "h" in text

    def test_a_bare_name_and_an_alias_onto_it_conflict(self, lib_dir):
        with pytest.raises(SyntaxError, match="`h`"):
            _load(lib_dir, "ibi_dup_conflict2", """
                -import_from(ibi_lib, [h, alias(g, h)])
            """)

    def test_two_local_names_for_one_original_still_load(self, lib_dir):
        """Pinned before this change (review round 5): one predicate under
        several spellings is not a conflict."""
        mod = _load(lib_dir, "ibi_two_names", """
            -import_from(ibi_lib, [h, alias(h, hh)])
            both(A, B) <- (h(A), hh(B))
        """)
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(7, 7)]


def test_the_translator_emits_a_repeated_name_once():
    """F3's trigger: ``use_module(bar, [baz/1, baz/2])`` became
    ``-import_from(bar, [baz, baz])``.  A bare name imports every arity, so
    one ``baz`` says it all."""
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal(":- use_module(bar, [baz/1, baz/2, qux/1]).\n")
    assert "-import_from(bar, [baz, qux])" in out
