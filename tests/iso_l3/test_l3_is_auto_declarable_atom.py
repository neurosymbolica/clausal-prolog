"""``is_auto_declarable_atom`` is the public, name-level half of the native
``.pl`` front end's auto-declaration rule, and ``DirectiveContext.auto_declare``
routes through it (one source of truth).

(a) For each name of a mixed list -- plain data atoms, builtin goals,
evaluables, reserved truth values -- the function agrees with what a REAL
native load binds: a probe module of ``root_export(N).`` facts, where the
name is used only as data, has the attribute exactly when the function says
yes.  Both answers are checked to be non-trivial (some yes, some no).

(b) Replacing the public function changes what ``auto_declare`` declares.
"""
from __future__ import annotations

import pytest

from clausal.tools import iso_l3_directives as d
from clausal.tools.iso_l3 import lower_source
from clausal.tools.iso_l3_directives import is_auto_declarable_atom

NAMES = ("limit", "fail", "max", "pi", "true", "in", "halt", "nan", "inf",
         "append")


def test_agrees_with_a_native_load(native):
    predicted = {n: is_auto_declarable_atom(n) for n in NAMES}
    # The list must exercise both answers, or agreement proves nothing.
    assert any(predicted.values()) and not all(predicted.values()), predicted
    body = "".join(f"root_export('{n}').\n" for n in NAMES)
    mod = native.load("autodecl_probe", body)
    # module_binds, not hasattr: getattr on a .pl module answers an unbound
    # atom-shaped name with its atom (ruling 2026-10-01), so hasattr no
    # longer tells a bound name from an unbound one.
    from clausal import module_binds
    loaded = {n: module_binds(mod, n) for n in NAMES}
    assert loaded == predicted
    # The per-file record names exactly the declared ones too.
    auto = set(lower_source(body, "autodecl_probe.pl").context.auto_atoms)
    assert auto == {n for n, yes in predicted.items() if yes}


def test_known_answers():
    assert is_auto_declarable_atom("limit")
    assert not is_auto_declarable_atom("halt")      # a builtin goal
    assert not is_auto_declarable_atom("max")       # an evaluable, arity 2
    assert not is_auto_declarable_atom("pi")        # an evaluable, arity 0
    assert not is_auto_declarable_atom("true")      # reserved truth value
    assert not is_auto_declarable_atom("in")        # a Python keyword
    assert not is_auto_declarable_atom("Limit")     # not lowercase


def test_auto_declare_routes_through_the_public_function(monkeypatch):
    src = "root_export(limit).\nroot_export(other).\n"
    assert set(lower_source(src, "p.pl").context.auto_atoms) == {"limit",
                                                                 "other"}
    monkeypatch.setattr(d, "is_auto_declarable_atom",
                        lambda n: n != "limit")
    assert lower_source(src, "p.pl").context.auto_atoms == ["other"]
