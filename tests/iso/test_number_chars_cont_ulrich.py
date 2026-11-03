"""number_chars/2, ruled 2026-10-13 against Ulrich Neumerkel's contemporary
comparison (https://www.complang.tuwien.ac.at/ulrich/iso-prolog/number_chars_cont),
cases #9, #41-#45, #54, #86, #89 -- all pinned against Scryer.

Three independent defects, all in ``clausal/logic/builtins/chars.py``:

* Number bound, Chars not a ground proper list (an atom/int, an improper
  list, or a proper list with a bad element behind an unbound one): the
  ``number_chars/2`` builtin used to skip straight to a blind output-mode
  ``unify``, which just FAILED instead of raising the Cor.2:2012 type_error
  -- ``number_chars(1, 1)`` used to fail silently instead of raising
  ``type_error(list, 1)``. ``_refuse_bound_chars_shape`` now validates the
  determinable shape/elements first; its check ORDER (tail-shape before
  element-type) is measured against Scryer, not guessed -- case #45 has
  both a bad head and a bad tail, and Scryer raises ``type_error(list,
  ...)``, not ``type_error(character, ...)``.
* ``_CHAR_ESCAPES`` listed ``"0"`` as a complete single-char escape
  (atom_number/2's shorthand), which pre-empted ``_char_code_token``'s
  octal-digit-run branch for the digit ``0`` specifically: ``0'\\0`` (no
  closing backslash) wrongly SUCCEEDED as NUL, and ``0'\\0\\`` (the
  complete, correct escape) wrongly RAISED ``syntax_error`` -- backwards.
* ``_read_number_text`` only recognised the bare ``-`` character as the
  negative-number prefix, not its quoted-atom spelling ``'-'`` (the same
  atom name) -- diverging from Scryer, which accepts both.

Two cases that MUST keep failing (not erroring) guard against
over-correction: #47 (a well-typed but mismatching partial-list head) and
#87 (a self-referential ``[C|C]``) are both ``false.`` per ISO, with no
type check to trigger.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers

#: (row name, body binding R, what the engine prints)
ROWS = [
    # Number bound, Chars malformed -- must raise, used to fail silently.
    ("#9 proper list, bad 2nd elem",
     "catch(number_chars(1,[_,[]]), error(F, C), R = [F, C])",
     ["[type_error(character,[]),number_chars/2]"]),
    ("#41 Chars not a list",
     "catch(number_chars(1,1), error(F, C), R = [F, C])",
     ["[type_error(list,1),number_chars/2]"]),
    ("#42 improper tail, good head",
     "catch(number_chars(1,[a|2]), error(F, C), R = [F, C])",
     ["[type_error(list,[a|2]),number_chars/2]"]),
    ("#43 improper tail, unbound head",
     "catch(number_chars(1,[_|2]), error(F, C), R = [F, C])",
     ["[type_error(list,[_|2]),number_chars/2]"]),
    ("#44 partial tail, bad head",
     "catch(number_chars(1,[[]|_]), error(F, C), R = [F, C])",
     ["[type_error(character,[]),number_chars/2]"]),
    ("#45 improper tail AND bad head -- tail wins (Scryer-measured)",
     "catch(number_chars(1,[[]|2]), error(F, C), R = [F, C])",
     ["[type_error(list,[[]|2]),number_chars/2]"]),
    # Must still just FAIL, not raise -- a well-typed element that
    # mismatches, or a self-referential partial list, is not a type error.
    ("#47 partial list, mismatching but well-typed head", "number_chars(1,['.'|_]), R = true", []),
    ("#87 self-referential [C|C]", "number_chars(1,[C|C]), R = C", []),
    # The \0 escape, backwards.
    ("#89 0'\\0 with no closing backslash -- incomplete, must raise",
     # The formal alone: ISO leaves the context implementation defined
     # (Scryer's number_chars/2, Clausal's context(number_chars/2, [...]),
     # operator ruling 2026-10-24).
     r"catch(number_chars(N, ['0', '\'', '\\', '0']), error(F, _), R = F)",
     ["syntax_error(unexpected_end_of_file)"]),
    ("#86 0'\\0\\ complete escape -- must read as NUL",
     r"number_chars(R, ['0', '\'', '\\', '0', '\\'])",
     ["0"]),
    # The quoted-atom spelling of the negative sign.
    ("#54 quoted '-' atom as the negative sign",
     r"number_chars(R, ['\'', '-', '\'', '1'])",
     ["-1"]),
    # Any spelling of the quoted atom '-' is the sign: a continuation
    # escape (#63) or a hex escape.
    ("#63 '\\<newline>-' as the negative sign",
     r"number_chars(R, ['\'', '\\', '\n', '-', '\'', ' ', '3'])",
     ["-3"]),
    ("'\\x2d\\' as the negative sign",
     r"number_chars(R, ['\'', '\\', x, '2', d, '\\', '\'', '3'])",
     ["-3"]),
    # `- 1` IS the integer -1 in the source too (the syntax suite's #56):
    # it used to read as the compound -(1), which is not a number.
    ("#91 number_chars(- 1, \"- 1\")",
     'number_chars(- 1, "- 1"), R = true',
     ["true"]),
]

ROWS += [
    # Bind order must not matter: the same list, holes bound before or after.
    ("bind-order: hole bound before the call",
     "T = [], L = [_,[]|T], catch(number_chars(1,L), error(F, C), R = [F, C])",
     ["[type_error(character,[]),number_chars/2]"]),
    ("bind-order: hole bound after the list is built",
     "L = [_,[]|T], T = [], catch(number_chars(1,L), error(F, C), R = [F, C])",
     ["[type_error(character,[]),number_chars/2]"]),
    ("bind-order: tail bound to a list holding a bad element",
     "L = [X|T], T = [[]], catch(number_chars(1,L), error(F, C), R = [F, C])",
     ["[type_error(character,[]),number_chars/2]"]),
    # A partial list built by a DCG body is a partial list, not a non-list.
    ("DCG-built partial list is filled in",
     "phrase(one, L, T), number_chars(12, L), T = ['2'], R = true",
     ["true"]),
]

#: Rows where Ulrich's table and Scryer disagree: Ulrich wins (operator
#: ruling 2026-10-13), so these are pinned against the engine only.
ULRICH_ONLY = [
    # #82: a float no double holds is a representation error; Ulrich marks
    # syntax_error(...) "unexpected" (Scryer raises
    # syntax_error(infinite_float), Trealla representation_error(max_float)).
    ("#82 9.9e999 overflows",
     "catch(number_chars(N, ['9', '.', '9', e, '9', '9', '9']), error(F, C),"
     " R = [F, C])",
     ["[representation_error(max_float),number_chars/2]"]),
    ("#82 negative overflow",
     "catch(number_chars(N, ['-', '1', '.', '0', e, '4', '0', '0']),"
     " error(F, _), R = F)",
     ["representation_error(max_float)"]),
    # ... but a text that is no number is a syntax error first (ISO
    # 8.16.7), as it was before the overflow check (review 2026-11-03)
    ("#82 overflow then a letter",
     "catch(number_chars(N, ['9', '.', '9', e, '9', '9', '9', x]), error(F, _),"
     " R = F)",
     ["syntax_error(unexpected_char)"]),
    ("#82 overflow then layout",
     "catch(number_chars(N, ['9', '.', '9', e, '9', '9', '9', ' ']), error(F, _),"
     " R = F)",
     ["syntax_error(unexpected_char)"]),
    ("#82 number_codes too",
     "catch(number_codes(N, [0'9, 0'., 0'9, 0'e, 0'9, 0'9, 0'9]), error(F, _),"
     " R = F)",
     ["representation_error(max_float)"]),
]

PROGRAM = "one --> \"1\".\n" + "".join(
    f"r{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(ROWS)) + "".join(
    f"u{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(ULRICH_ONLY))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("nc_cont")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_nc_cont_ulrich_1013"
    (d / f"{name}.pl").write_text(PROGRAM)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 3) == ROWS[i][2]


@pytest.mark.parametrize("i", range(len(ULRICH_ONLY)),
                         ids=[r[0] for r in ULRICH_ONLY])
def test_engine_ulrich_only(pl_mod, i):
    assert _engine_answers(pl_mod, f"u{i}", 3) == ULRICH_ONLY[i][2]


def test_oracle(scryer):
    """The same rows against the clean Scryer build -- the binding oracle
    these defects were measured against, not just Ulrich's table (which
    marks more than one answer "good" for #45; Scryer only gives one)."""
    del scryer   # the fixture only asserts the binary is there
    got = _scryer_answers(PROGRAM, [(f"r{i}(R)", 3) for i in range(len(ROWS))])
    assert got == [r[2] for r in ROWS]
