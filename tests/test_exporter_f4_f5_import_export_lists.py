"""F4 / F5 (multi-arity plan §F, 2026-09-29): the exporter's module and import lists.

F4. An export list names each Name/Arity ONCE. `p(X)` and `p/1` are the same
    export, and a source that lists it twice (or in two spellings) used to
    export it twice. ISO engines tolerate the duplicate; it is still not what
    the source declares.

F5. With no module signatures the exporter cannot know a bare name's arity. It
    used to write the bare atom into the import list: `use_module(lib, [foo])`.
    That is not an ISO import item. Measured 2026-09-29: Scryer refuses the
    FILE at load (`syntax_error(invalid_module_declaration)`), and Trealla
    loads it and imports NOTHING (`existence_error(procedure, foo/1)` at call
    time), the fail-open shape. The export now writes a LISTLESS
    `use_module(lib)`, which imports a superset (every export), drops nothing
    and guesses no arity. A list whose every item has an arity is unchanged.
"""
import os
import shutil
import subprocess

import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog


def _directives(src: str) -> list[str]:
    return [line for line in clausal_source_to_prolog(src, strict=True).splitlines()
            if line.startswith(":-")]


# ── F4 ────────────────────────────────────────────────────────────────

def test_export_list_names_each_indicator_once():
    src = "-module(m, [p/1, p(X), p/2, p/1])\np(1),\np(1, 2),\n"
    assert _directives(src)[0] == ":- module(m, [p/1, p/2])."


def test_export_list_keeps_first_occurrence_order():
    src = "-module(m, [q/0, p/1, q])\np(1),\nq,\n"
    assert _directives(src)[0] == ":- module(m, [q/0, p/1])."


def test_export_list_without_duplicates_is_unchanged():
    src = "-module(m, [p/1, p/2])\np(1),\np(1, 2),\n"
    assert _directives(src)[0] == ":- module(m, [p/1, p/2])."


# ── F5 ────────────────────────────────────────────────────────────────

def test_bare_import_without_signatures_is_listless():
    src = "-import_from(lib, [foo, bar])\nq(X) <- (foo(X))\n"
    assert ":- use_module('lib')." in _directives(src)


def test_mixed_import_without_signatures_is_listless():
    # one bare item is enough: its arity is unknown, so the list cannot be
    # written without guessing
    src = "-import_from(lib, [foo(X), bar])\nq(X) <- (foo(X))\n"
    assert ":- use_module('lib')." in _directives(src)


def test_import_with_every_arity_known_keeps_its_list():
    src = "-import_from(lib, [foo(X)])\nq(X) <- (foo(X))\n"
    assert ":- use_module('lib', [foo/1])." in _directives(src)


def test_no_import_list_item_is_a_bare_atom():
    for src in ("-import_from(lib, [foo, bar])\nq(X) <- (foo(X))\n",
                "-import_from(lib, [foo(X), bar])\nq(X) <- (foo(X))\n"):
        for line in _directives(src):
            if line.startswith(":- use_module('lib', ["):
                items = line[len(":- use_module('lib', ["):-len("]).")].split(", ")
                assert all("/" in item for item in items), line


from tests._oracles import SCRYER


@pytest.mark.skipif(not os.path.exists(SCRYER), reason="Scryer not built here")
def test_listless_import_consults_and_answers_in_scryer(tmp_path):
    """The positive control, on the engine that refused the bare atom."""
    (tmp_path / "lib.pl").write_text(
        ":- module(lib, [foo/1, foo/2]).\nfoo(1).\nfoo(1, 2).\n")
    body = clausal_source_to_prolog(
        "-import_from(lib, [foo])\nq(X, A, B) <- (foo(X), foo(A, B))\n", strict=True)
    (tmp_path / "user_q.pl").write_text(
        body + "\n:- initialization((q(X, A, B), write(ok(X, A, B)), nl, halt)).\n")
    out = subprocess.run([SCRYER, str(tmp_path / "user_q.pl")], cwd=tmp_path,
                         stdin=subprocess.DEVNULL, capture_output=True, text=True,
                         timeout=60)
    assert "ok(1,1,2)" in out.stdout, out.stdout + out.stderr


# ── F4b: an import list names each indicator once, too ────────────────

def test_repeated_import_indicator_is_named_once():
    src = "-import_from(lib, [helper/1, helper/1])\nq(X) <- (helper(X))\n"
    assert ":- use_module('lib', [helper/1])." in _directives(src)


def test_import_indicator_in_two_spellings_is_named_once():
    # `helper(X)` and `helper/1` are the same import; so are `sent//1` and `sent/3`
    src = "-import_from(lib, [helper(X), helper/1, sent//1, sent/3])\nq(X) <- (helper(X))\n"
    assert ":- use_module('lib', [helper/1, sent/3])." in _directives(src)


def test_distinct_arities_of_one_name_are_both_kept():
    src = "-import_from(lib, [helper/1, helper/2])\nq(X) <- (helper(X))\n"
    assert ":- use_module('lib', [helper/1, helper/2])." in _directives(src)
