"""listing/1 on a SEAM module reads each clause as a term
(``clause_ops.clause_terms``, the conversion clause/2 uses) and prints it in
the seam's spelling: a partial list as ``[H, *T]``, never the compiler's head
pattern (``StarUnpack(...)``), a declared functor as ``f(...)``, never the
``Call(LoadName(...))`` node, and the clause's variables ``_0``, ``_1``, ...
by first occurrence, so a variable shared between head, compound arguments
and body shows as one name (it used to print as ``_`` inside a compound).
todo/done/listing-prints-head-patterns-and-loses-variable-sharing-2026-11-04.md.
"""
from __future__ import annotations

from itertools import count

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import solve

_PROGRAM = """\
-module({name}, [p(X, Y), w(X), go()])
-private([a, b, x, f(_, _), g(_), f(_), f(_, _, _)])
-dynamic(p/2)

p([H, *T], H - T),
p([a, [b, *T], *T], f("ab")),
p(f(X, g(X)), X),

p(X, Y) <- (X is [Y, *Z], w([x, *Z]))
p(X, Y) <- (Y == X + 1, not w(X))
p(X, Y) <- w(f(X, Y, X))

w(_),

go() <- listing(p/2)
"""

_EXPECTED = """\
% p/2 — 6 clause(s)
p([_0, *_1], _0 - _1).
p([a, [b, *_0], *_0], f("ab")).
p(f(_0, g(_0)), _0).
p(_0, _1) <- (_0 is [_1, *_2], w([x, *_2])).
p(_0, _1) <- (_1 == _0 + 1, not w(_0)).
p(_0, _1) <- w(f(_0, _1, _0)).
"""

_COUNTER = count()


def test_seam_listing_prints_terms_with_shared_variables(tmp_path, capsys):
    name = f"_listing_seam_{next(_COUNTER)}"
    path = tmp_path / f"{name}.seam"
    path.write_text(_PROGRAM.format(name=name), encoding="utf-8")
    mod = _load_module(name, str(path))
    capsys.readouterr()
    for _ in solve("go", mod):
        pass
    assert capsys.readouterr().out == _EXPECTED
