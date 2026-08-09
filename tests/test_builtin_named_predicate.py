"""A .clausal predicate named after a Python builtin must load and run.

The ``_make_functor_class_ast`` mint guard probed the head name with a bare
name lookup, which falls through the module dict to ``__builtins__``: a head
named ``reversed`` (or ``sorted``, ``filter``, ``next``, …) resolved to the
Python builtin, was not a ``PredicateMeta``, so the guard skipped minting and
the head call then invoked the real builtin — ``TypeError: reversed() takes
no keyword arguments`` at import time.

The guard now probes ``globals()`` membership instead, so only names actually
bound in the module dict (injected predicate builtins, imports, user defs,
earlier clauses) count as existing.  The documented rule that an in-module
non-``PredicateMeta`` binding is left alone (fail loudly rather than clobber
user code) is unchanged — see the guard's docstring in
``clausal/templating/term_rewriting.py``.
"""

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _load(tmp_path, source: str, name: str):
    path = os.path.join(str(tmp_path), f"{name}.clausal")
    with open(path, "w") as f:
        f.write(source)
    return _load_module(name, path)


def _module(mod):
    return mod.__dict__["$module"]


def test_rule_head_named_reversed_loads_and_solves(tmp_path):
    """The reported repro: a rule head shadowing a Python builtin."""
    src = (
        "-module(bnp_rev, [ reversed(X, Y) ])\n"
        "reversed(X, Y) <- (\n"
        "    Y == X * 2\n"
        ")\n"
    )
    mod = _load(tmp_path, src, "bnp_rev")
    sols = list(call("reversed", 3, 6, module=_module(mod)))
    assert len(sols) == 1


def test_fact_head_named_sorted_loads_and_queries(tmp_path):
    """Facts hit the same mint guard as rule heads."""
    src = (
        "-module(bnp_sorted, [ sorted(A, B) ])\n"
        "sorted(1, 2)\n"
        "sorted(3, 4)\n"
    )
    mod = _load(tmp_path, src, "bnp_sorted")
    sols = list(call("sorted", 3, 4, module=_module(mod)))
    assert len(sols) == 1


def test_in_module_binding_is_still_left_alone(tmp_path):
    """The documented edge case is preserved: a name the USER bound in the
    module is not clobbered by a same-named clause head — the load fails
    loudly instead of silently destroying the binding."""
    src = (
        "-module(bnp_shadow, [ ])\n"
        "helper = 5\n"
        "helper(A) <- (\n"
        "    A == 1\n"
        ")\n"
    )
    with pytest.raises(Exception):
        _load(tmp_path, src, "bnp_shadow")
