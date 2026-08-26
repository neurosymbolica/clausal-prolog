"""Slice G regression tests — compiled functions must carry the source
``lineno`` of the originating ``.clausal`` body term so Python tracebacks
point at meaningful source positions, not line 0.
"""

from __future__ import annotations

import traceback

import pytest


def _build(tmp_path, name, body):
    """Write a ``.clausal`` file with *body* appended to a 2-line header,
    load it, and return (logic_module, source_path).  The first body line
    lands on line 3, which callers use as the expected ``lineno``."""
    from clausal.import_hook import _load_module

    src = tmp_path / f"{name}.clausal"
    src.write_text("# line 1\n# line 2\n" + body)
    mod = _load_module(name, str(src))
    return mod.__dict__["$module"], src


def _compiled_funcdef_lineno(exc, predicate_name_marker):
    """Walk *exc*'s traceback and return the lineno of the frame whose
    code object's ``co_name`` matches *predicate_name_marker*.

    The compiled predicate ``FunctionDef`` lives under filename
    ``"<template>"`` (the placeholder used by ``compile`` for the
    generated AST).  This is the frame whose ``lineno`` ought to point
    at the originating ``.clausal`` body goal once Slice G is wired
    through.  Returns ``None`` if no such frame exists.
    """
    tb = exc.__traceback__
    while tb is not None:
        co = tb.tb_frame.f_code
        if co.co_filename == "<template>" and predicate_name_marker in co.co_name:
            return tb.tb_lineno
        tb = tb.tb_next
    return None


class TestSourceLocations:
    """Each test compiles a small predicate, triggers a runtime error in
    the compiled body, and asserts the innermost generated-frame lineno
    matches the source line of the offending body goal."""

    def test_div_by_zero_traceback_points_at_source_line(self, tmp_path):
        """A Python escape that raises should report the body line, not 0."""
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call

        # Source: ++(1/0) raises ZeroDivisionError on line 3.
        src = tmp_path / "g_divzero.clausal"
        src.write_text(
            "# line 1\n"
            "# line 2\n"
            "DivZero(X) <- (X is ++(1 / 0))\n"
        )
        mod = _load_module("g_divzero", str(src))
        logic_mod = mod.__dict__["$module"]

        with pytest.raises(ZeroDivisionError) as exc_info:
            list(call("DivZero", None, module=logic_mod))

        # Diagnostic: walk the entire traceback so we can see exactly
        # which frames the compiled body produces.
        import traceback
        frames = traceback.extract_tb(exc_info.value.__traceback__)
        diag = "\n".join(
            f"  {fr.filename}:{fr.lineno} in {fr.name}" for fr in frames
        )
        lineno = _compiled_funcdef_lineno(exc_info.value, "DivZero")
        # Body goal is on line 3; expect compiled frame to report line 3.
        assert lineno == 3, (
            f"expected compiled traceback to point at line 3 "
            f"(the `X is ++(1 / 0)` goal); got {lineno!r}\nframes:\n{diag}"
        )


def _assert_frame_line(exc, marker, expected_line):
    frames = traceback.extract_tb(exc.__traceback__)
    diag = "\n".join(f"  {fr.filename}:{fr.lineno} in {fr.name}" for fr in frames)
    lineno = _compiled_funcdef_lineno(exc, marker)
    assert lineno == expected_line, (
        f"expected compiled frame (marker={marker!r}) at line "
        f"{expected_line}; got {lineno!r}\nframes:\n{diag}"
    )


class TestSourceLocationsG6:
    """G6 — one case per construct shape.  Each compiles a predicate
    whose body-goal line is known (line 3, via the shared header), then
    triggers a runtime exception and asserts the compiled frame's
    ``lineno`` matches.

    Shapes that *silently fail* (unification mismatch, missing-predicate
    call) are not exception-path cases and are deliberately not covered
    here — documented inline where relevant.
    """

    def test_evaluate_raises(self, tmp_path):
        from clausal.logic.solve import call

        logic_mod, _ = _build(tmp_path, "g_eval", "EvalRaise(X) <- eval_(++([][0]), X)\n")
        with pytest.raises(IndexError) as exc_info:
            list(call("EvalRaise", None, module=logic_mod))
        _assert_frame_line(exc_info.value, "EvalRaise", 3)

    def test_reified_ite_then_branch_raises(self, tmp_path):
        from clausal.logic.solve import call

        logic_mod, _ = _build(
            tmp_path,
            "g_reified_ite",
            "ReifiedITE(X) <- if_(1 == 1, (X is ++(1/0)), X is 0)\n",
        )
        with pytest.raises(ZeroDivisionError) as exc_info:
            list(call("ReifiedITE", None, module=logic_mod))
        _assert_frame_line(exc_info.value, "ReifiedITE", 3)

    def test_general_ite_cond_raises(self, tmp_path):
        from clausal.logic.solve import call

        # Non-ground condition forces the general (non-reified) ITE path.
        logic_mod, _ = _build(
            tmp_path,
            "g_general_ite",
            "GeneralITE(X) <- if_(++(1/0) == 1, X is 1, X is 2)\n",
        )
        with pytest.raises(ZeroDivisionError) as exc_info:
            list(call("GeneralITE", None, module=logic_mod))
        _assert_frame_line(exc_info.value, "GeneralITE", 3)

    def test_catch_goal_raises(self, tmp_path):
        from clausal.logic.solve import call

        # catch/3 with a *Python* exception the clausal catcher can't
        # match — should propagate and blame the catch line.
        logic_mod, _ = _build(
            tmp_path,
            "g_catch_goal",
            'CatchGoal(X) <- catch((X is ++(1/0)), "unrelated", X is 0)\n',
        )
        with pytest.raises(ZeroDivisionError) as exc_info:
            list(call("CatchGoal", None, module=logic_mod))
        _assert_frame_line(exc_info.value, "CatchGoal", 3)

    def test_findall_inner_raises(self, tmp_path):
        from clausal.logic.solve import call

        logic_mod, _ = _build(
            tmp_path,
            "g_findall",
            "FindAllRaise(BAG) <- findall(Y, (Y is ++(1/0)), BAG)\n",
        )
        with pytest.raises(ZeroDivisionError) as exc_info:
            list(call("FindAllRaise", None, module=logic_mod))
        _assert_frame_line(exc_info.value, "FindAllRaise", 3)

    def test_goal_lambda_body_raises(self, tmp_path):
        """The goal-lambda's compiled ``FunctionDef`` (``_lambdaN``) is
        the frame we're checking — the enclosing predicate call frame
        is consumed by ``call_goal``'s trampoline and doesn't appear in
        the traceback."""
        from clausal.logic.solve import call

        logic_mod, _ = _build(
            tmp_path,
            "g_lambda",
            "LambdaRaise(X) <- call_goal((V <- (V is ++(1/0))), X)\n",
        )
        with pytest.raises(ZeroDivisionError) as exc_info:
            list(call("LambdaRaise", None, module=logic_mod))
        _assert_frame_line(exc_info.value, "_lambda", 3)

    def test_sub_predicate_call_raises(self, tmp_path):
        """Raise deep in a callee reached via a caller's call site.  The
        callee's compiled frame should report its own body line.  The
        enclosing caller frame is consumed by the trampoline driver and
        is not present on the traceback — verified experimentally; not
        a source-location bug."""
        from clausal.logic.solve import call

        logic_mod, _ = _build(
            tmp_path,
            "g_subcall",
            "Callee(X) <- (X is ++(1/0))\n"
            "Caller(X) <- Callee(X)\n",
        )
        with pytest.raises(ZeroDivisionError) as exc_info:
            list(call("Caller", None, module=logic_mod))
        _assert_frame_line(exc_info.value, "Callee", 3)
