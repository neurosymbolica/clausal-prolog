"""The ``permission_error`` for writing a static procedure names the
declaration in the spelling of the surface the predicate is defined in.

Before the fix the message always said "declare it -dynamic(fixed/1)", the
seam spelling, even for a predicate a ``.clausal`` or ``.pl`` file defines,
where the declaration is ``:- dynamic(fixed/1).``.  The error TERM is
unchanged: ``error(permission_error(modify, static_procedure, fixed/1), Msg)``;
only ``Msg`` differs by surface.
"""
from __future__ import annotations

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.testing import load_clausal_module

from tests._suffix import SEAM

PROLOG = "fixed(1).\n"
SEAM_SRC = "fixed(1),\n"

ISO_HINT = ":- dynamic(fixed/1)."
SEAM_HINT = "-dynamic(fixed/1)"


def _load(tmp_path, suffix, prolog=PROLOG):
    path = tmp_path / f"static_hint{suffix}"
    path.write_text(SEAM_SRC if suffix == SEAM else prolog)
    return load_clausal_module(path)


def _refusal(mod, goal):
    """The ball and the message of the error *goal* raises."""
    with pytest.raises(LogicException) as info:
        list(solve(goal, module=mod))
    return info.value.term, info.value.message


@pytest.mark.parametrize("suffix, hint", [
    (".clausal", ISO_HINT),
    (".pl", ISO_HINT),
    (SEAM, SEAM_HINT),
])
@pytest.mark.parametrize("builtin", ["assertz", "asserta"])
def test_static_procedure_hint_names_the_surface(tmp_path, suffix, hint,
                                                  builtin):
    mod = _load(tmp_path, suffix)
    term, message = _refusal(mod, (builtin, ("fixed", 2)))
    assert term == ("error", ("permission_error", "modify", "static_procedure",
                              ("/", "fixed", 1)), ("/", builtin, 1))
    assert hint in message, message
    if hint == ISO_HINT:
        assert "-dynamic(" not in message, message


@pytest.mark.parametrize("suffix, hint", [
    (".clausal", ":- dynamic(nowhere/1)."),
    (".pl", ":- dynamic(nowhere/1)."),
    (SEAM, "-dynamic(nowhere/1)"),
])
def test_undeclared_procedure_hint_names_the_calling_surface(tmp_path,
                                                             suffix, hint):
    # A Prolog surface creates the procedure (ISO 7.5.2) unless the flag
    # says otherwise; with it off, the refusal names the declaration too.
    mod = _load(tmp_path, suffix, prolog=(
        ":- set_prolog_flag(assert_creates_dynamic, false).\n" + PROLOG))
    term, message = _refusal(mod, ("assertz", ("nowhere", 1)))
    assert term[1] == ("permission_error", "modify", "static_procedure",
                       ("/", "nowhere", 1))
    assert hint in message, message
    if suffix != SEAM:
        assert "-dynamic(" not in message, message
