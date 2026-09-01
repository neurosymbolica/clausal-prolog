"""Slice / `...` / comprehension misuse in a clause body must be diagnosed.

Three surfaces `EmbedTransformer` happily rewrites were rejected only much
later, by an internal exception with no source line and no suggestion — where
every other unsupported surface gets a `SyntaxError` from `term_rewriting.py`
naming the construct (todo/slice-and-ellipsis-in-clause-body-crash-with-
notimplementederror.md):

- a slice `L[1:3]`      → NotImplementedError from terms_to_ast
- `X is ...`            → NotImplementedError from terms_to_ast
- `[Y for Y in L]`      → bare NameError at import (Y is a logic variable the
                          inert comprehension never binds)
- `[x for x, y in L]`   → bare AssertionError from visit_Tuple

Contract pinned here: each is a `SyntaxError` naming the construct and a
working spelling.  The visit-site rejections (slice, comprehension targets)
also carry the offending line.  NOT rejected at the visit site: `...` — it
must keep REIFYING (render inverts reify; TestPlainConstants round-trips
`X is ...`), so its rejection lives in the goal compiler, located via the
clause-position stack.
"""

import os

import pytest

from clausal.import_hook import _load_module


def _load(tmp_path, source: str, name: str):
    path = os.path.join(str(tmp_path), f"{name}.clausal")
    with open(path, "w") as f:
        f.write(source)
    return _load_module(name, path)


# `bad_clause` is on line 6 in each source below, with legal clauses above it,
# so a raise that reports "somewhere in this file" cannot pass by accident.
_PRELUDE = (
    "-module({mod}, [ good_one(X), good_two(X), bad_clause(X, Y), a ])\n"
    "thing(a),\n"
    "other(a),\n"
    "good_one(X) <- (thing(X)),\n"
    "good_two(X) <- thing(X),\n"
)


def test_slice_reports_line_and_alternatives(tmp_path):
    src = _PRELUDE.format(mod="bcd_a") + "bad_clause(L, S) <- (thing(L), S is L[1:3]),\n"
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, src, "bcd_a")
    e = ei.value
    assert "slice" in str(e)
    assert "nth0" in str(e)
    assert e.lineno == 6, f"expected the offending clause's line, got {e.lineno!r}"
    assert e.filename and e.filename.endswith("bcd_a.clausal")


def test_ellipsis_is_a_syntax_error_with_the_clause_line(tmp_path):
    src = _PRELUDE.format(mod="bcd_b") + "bad_clause(X, _Y) <- (X is ...),\n"
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, src, "bcd_b")
    e = ei.value
    assert "..." in str(e) or "Ellipsis" in str(e)
    # Located via the compiler's clause-position stack — the clause's line.
    assert e.lineno == 6, f"expected the offending clause's line, got {e.lineno!r}"


def test_logic_var_comprehension_target_names_var_and_findall(tmp_path):
    src = _PRELUDE.format(mod="bcd_c") + "bad_clause(L, M) <- (M is [Y for Y in L]),\n"
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, src, "bcd_c")
    e = ei.value
    assert "`Y`" in str(e)
    assert "findall" in str(e)
    assert e.lineno == 6, f"expected the offending clause's line, got {e.lineno!r}"
    assert e.filename and e.filename.endswith("bcd_c.clausal")


def test_underscore_led_logic_var_target_is_rejected_too(tmp_path):
    src = _PRELUDE.format(mod="bcd_d") + "bad_clause(L, M) <- (M is [_y for _y in L]),\n"
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, src, "bcd_d")
    assert "findall" in str(ei.value)


def test_tuple_comprehension_target_is_a_syntax_error(tmp_path):
    src = _PRELUDE.format(mod="bcd_e") + (
        "bad_clause(L, M) <- (M is [x for x, y in L]),\n"
    )
    with pytest.raises(SyntaxError) as ei:
        _load(tmp_path, src, "bcd_e")
    e = ei.value
    assert "findall" in str(e)
    assert e.lineno == 6, f"expected the offending clause's line, got {e.lineno!r}"


def test_declared_lowercase_comprehension_target_still_compiles(tmp_path):
    # The legal spelling stays legal: a declared loop atom makes the
    # comprehension an inert term that imports, runs, and binds.
    src = (
        "-module(bcd_f, [ sq(L, M) ])\n"
        "-private([x])\n"
        "\n"
        "sq(L, M) <- (M is [x * x for x in L])\n"
    )
    _load(tmp_path, src, "bcd_f")


def test_anonymous_wildcard_comprehension_target_still_compiles(tmp_path):
    # `for _ in L` mints a fresh anonymous Var per occurrence; nothing needs
    # binding, so it must stay accepted.
    src = (
        "-module(bcd_g, [ blanks(L, M) ])\n"
        "-private([z])\n"
        "\n"
        "blanks(L, M) <- (M is [z for _ in L])\n"
    )
    _load(tmp_path, src, "bcd_g")
