"""``-import_from(clausal.logic.clpfd, [label])`` bound the Python function
``clausal.logic.clpfd.label(vars, trail)`` over the builtin label/1, so the
call ``label([X])`` raised DispatchTargetError ("resolved to a function
value, not a predicate").  An engine name that implements a builtin now
imports as the builtin's goal object; one that is not a builtin stays the
Python value."""
from __future__ import annotations

import itertools

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

_N = itertools.count()


@pytest.mark.parametrize("names", [
    "[label]", "[in_domain, label]", "[fd_eq, label]",
    "[alias(label, lab)]",
])
def test_importing_a_builtin_from_clpfd(tmp_path, names):
    call = "lab" if "lab)" in names else "label"
    name = f"_eng_import_{next(_N)}"
    p = tmp_path / f"{name}.seam"
    p.write_text(f"-import_from(clausal.logic.clpfd, {names})\n"
                 f"g(X) <- (in_domain(X, 1, 2), {call}([X]))\n")
    m = _load_module(name, str(p))
    v = Var()
    assert [_deref_walk(v) for _ in solve(("g", v), m.__clausal_module__)] == [1, 2]
    if "fd_eq" in names:
        from clausal.logic import clpfd
        assert vars(m)["fd_eq"] is clpfd.fd_eq
