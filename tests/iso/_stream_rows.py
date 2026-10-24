"""Shared plumbing for the stream oracle tests (``test_streams_scryer.py``,
``test_read_term_scryer.py``): one ``.pl`` program per row, run under
Clausal (in-process, the native front end) and under Scryer, its stdout
compared line by line.

A row is the body of ``main/0``; the prelude gives it ``t/1`` (run a goal,
print ``ok``, ``failed`` or the error's FORMAL term -- the context is
implementation-defined, so it is not compared) and ``p/1`` (``writeq`` and a
newline).  ``FILE`` in a row is replaced by a temp file path under the
test's ``tmp_path``.
"""

from __future__ import annotations

import contextlib
import io
import os
import re

from tests._oracles import run_scryer

PRELUDE = """\
t(G) :- catch((G -> write(ok) ; write(failed)), error(E, _), writeq(E)), nl.
p(X) :- writeq(X), nl.
"""

_VAR = re.compile(r"\b_G?[0-9]+\b")
_STREAM = re.compile(r"'\$stream'\((0x)?[0-9a-f]+\)")


def normalise(text: str) -> list:
    """Output lines with variable names (``_123`` -> ``_``) and stream
    terms (``'$stream'(7)`` -> ``'$stream'(_)``) made uniform."""
    return [_STREAM.sub("'$stream'(_)", _VAR.sub("_", line.rstrip()))
            for line in text.strip().splitlines()]


def program(row: str, file_path: str) -> str:
    body = row.strip().rstrip(".").replace("FILE", f"'{file_path}'")
    return PRELUDE + "main :-\n  " + body + ".\n"


def run_clausal(tmp_path, name: str, text: str) -> str:
    """Load *text* as a ``.pl`` module and run ``main/0`` once, returning
    what it wrote to the current output (stdout).  The stream table is
    reset afterwards so a row cannot leak a stream into the next."""
    from clausal.import_hook import _load_module
    from clausal.logic import streams
    from clausal.logic.exceptions import LogicException, render_error_term
    from clausal.logic.solve import solve
    from clausal.logic.variables import Trail

    path = tmp_path / f"{name}.pl"
    path.write_text(text, encoding="utf-8")
    buf = io.StringIO()
    try:
        mod = _load_module(name, str(path))
        with contextlib.redirect_stdout(buf):
            try:
                for _ in solve("main", mod, Trail()):
                    break
            except LogicException as e:
                buf.write(f"UNCAUGHT {render_error_term(e.term)}\n")
    finally:
        streams.reset_for_tests()
    return buf.getvalue()


def run_oracle(tmp_path, name: str, text: str) -> str:
    """The same program under Scryer: ``main/0`` runs from an
    ``initialization/1`` directive (which the native front end refuses, so
    the Clausal copy does without it)."""
    path = tmp_path / f"{name}_scryer.pl"
    path.write_text(text + ":- initialization(main).\n", encoding="utf-8")
    proc = run_scryer(path, timeout=60)
    return proc.stdout


def file_for(tmp_path, name: str) -> str:
    return os.fspath(tmp_path / f"{name}.txt")
