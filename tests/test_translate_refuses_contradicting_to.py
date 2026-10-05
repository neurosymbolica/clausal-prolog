"""``clausal.tools.translate``: a ``--to`` that contradicts the file's surface
is a usage error.

``--to`` used to win over the extension.  After the extension flip
``.clausal`` is Clausal Prolog (ISO syntax) and seam source is ``.seam``, so
``translate fam.clausal --to swi`` fed Prolog to the seam parser (a Python
``SyntaxError``) and ``translate s.seam --to clausal`` fed seam to the Prolog
reader (a ``ParseError``).  Both are now refused up front, exit 2, naming the
surface and the ``--to`` that fits.  Stdin and an extension that names no
surface still trust ``--to``.
"""

from __future__ import annotations

import io
import sys

import pytest

from clausal.tools.translate import main

CLAUSAL_PROLOG = ":- module(fam, [p/1]).\np(1).\n:- end_module(fam).\n"
ISO_PROLOG = "p(1).\n"
SEAM = "p(1),\nq(X) <- p(X)\n"


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


@pytest.mark.parametrize("name, text, to, says", [
    ("fam.clausal", CLAUSAL_PROLOG, "swi", "is Prolog (.clausal)"),
    ("fam.clausal", CLAUSAL_PROLOG, "iso", "is Prolog (.clausal)"),
    ("s.pl", ISO_PROLOG, "scryer", "is Prolog (.pl)"),
    ("s.seam", SEAM, "clausal", "is seam source (.seam)"),
])
@pytest.mark.parametrize("roundtrip", [False, True])
def test_a_contradicting_to_is_a_usage_error(tmp_path, capsys, name, text,
                                             to, says, roundtrip):
    argv = [_write(tmp_path, name, text), "--to", to]
    if roundtrip:
        argv.append("--roundtrip")
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert says in err and f"--to {to}" in err, err
    assert "omit --to" in err, err


@pytest.mark.parametrize("name, text, to, want", [
    ("fam.clausal", CLAUSAL_PROLOG, "clausal", "p(1),"),   # Prolog -> seam
    ("s.pl", ISO_PROLOG, "clausal", "p(1),"),
    ("s.seam", SEAM, "swi", "q(X) :-"),                    # seam -> Prolog
    ("fam.clausal", CLAUSAL_PROLOG, None, "p(1),"),        # detected
    ("s.seam", SEAM, None, "q(X) :-"),
])
def test_a_matching_or_absent_to_translates(tmp_path, capsys, name, text,
                                            to, want):
    argv = [_write(tmp_path, name, text)] + (["--to", to] if to else [])
    assert main(argv) == 0
    assert want in capsys.readouterr().out


def test_stdin_trusts_to(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("p(1),\n"))
    assert main(["--to", "swi"]) == 0
    assert "p(1)." in capsys.readouterr().out


def test_an_extension_naming_no_surface_trusts_to(tmp_path, capsys):
    assert main([_write(tmp_path, "rules.txt", "p(1),\n"), "--to", "swi"]) == 0
    assert "p(1)." in capsys.readouterr().out
