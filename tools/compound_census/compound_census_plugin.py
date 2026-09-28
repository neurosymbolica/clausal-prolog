"""Run-time census of ``KWTerm`` constructions and ``LogicException`` terms
(a pytest plugin).

MEASUREMENT ONLY.  Wraps ``KWTerm.__init__`` (C constructions go through
``tp_init`` too, so they are counted, attributed to the Python frame that
called into C) and ``LogicException.__init__``, and at session end writes a
JSON report to ``$CC_OUT``::

    CC_OUT=/tmp/cc.json PYTHONPATH=tools/compound_census \\
        python -m pytest tests -p compound_census_plugin -p no:cacheprovider ...

The ``Compound`` class is gone (the cell ``('f', 1, 2)`` is the term), so
there is nothing of it left to count at run time; the static half
(``census.py``) still reports any source that names it.  The report carries
every denominator: tests run, tests that constructed at least one
``KWTerm``, ``KWTerm`` constructions by site, and the type of every
``LogicException`` term.  Positive controls run at import (one of each
kind the report distinguishes); if any fails the
plugin raises instead of reporting, so a run can never print N=0 because the
wrapping silently missed.  ``engine`` records ``clausal.__file__`` so a run
against the wrong tree is visible.
"""

from __future__ import annotations

import collections
import json
import os
import sys

import pytest

import clausal
import clausal.terms as T
import clausal.logic.exceptions as EX
from clausal.logic.variables import deref

OUT = os.environ.get("CC_OUT")
ROOT = os.getcwd() + os.sep

kw_sites = collections.Counter()
err = collections.Counter()
per_test = collections.Counter()
state = {"test": None, "run": 0}


def _site(depth: int) -> str:
    f = sys._getframe(depth)
    while f is not None and f.f_code.co_filename.startswith("<"):
        f = f.f_back          # skip dataclass-generated / exec'd frames
    if f is None:
        return "?"
    fn = f.f_code.co_filename
    if fn.startswith(ROOT):
        fn = fn[len(ROOT):]
    return f"{fn}:{f.f_lineno}"


_k_init = T.KWTerm.__init__
_e_init = EX.LogicException.__init__


def _kwterm_init(self, functor, **kw):
    kw_sites[_site(2)] += 1
    if state["test"]:
        per_test[state["test"]] += 1
    _k_init(self, functor, **kw)


def _exc_init(self, *a, **k):
    _e_init(self, *a, **k)
    t = deref(getattr(self, "term", None))
    err["total"] += 1
    if type(t) is tuple:
        err["term_cell"] += 1
    else:
        err["term_" + type(t).__name__] += 1


T.KWTerm.__init__ = _kwterm_init
EX.LogicException.__init__ = _exc_init

# ── positive controls: each must move its counter, or the plugin refuses ────
# Every control builds its own objects, so none depends on what the engine
# still builds -- the retirement this measures changes that.
CONTROLS = {}
T.KWTerm("r", a=1)
CONTROLS["kwterm"] = sum(kw_sites.values())
EX.LogicException(("error", "x", "c"))
CONTROLS["logic_exception"] = err["total"]
CONTROLS["logic_exception_cell"] = err["term_cell"]
_expect = {"kwterm": 1, "logic_exception": 1, "logic_exception_cell": 1}
if CONTROLS != _expect:
    raise RuntimeError(f"compound census positive controls failed: "
                       f"{CONTROLS} != {_expect}")
for _c in (kw_sites, err):
    _c.clear()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    state["test"] = item.nodeid
    state["run"] += 1
    yield
    state["test"] = None


def report() -> dict:
    return {
        "engine": clausal.__file__,
        "controls": CONTROLS,
        "tests_run": state["run"],
        "tests_constructing": len(per_test),
        "kwterm_total": sum(kw_sites.values()),
        "kwterm_sites": kw_sites.most_common(),
        "logic_exceptions": dict(err),
    }


def pytest_sessionfinish(session, exitstatus):
    r = report()
    r["exitstatus"] = int(exitstatus)
    if OUT:
        with open(OUT, "w") as fh:
            json.dump(r, fh, indent=1)


def pytest_terminal_summary(terminalreporter):
    r = report()
    terminalreporter.write_line(
        f"compound census: KWTerm {r['kwterm_total']} constructions at "
        f"{len(r['kwterm_sites'])} sites; LogicException "
        f"{r['logic_exceptions'].get('total', 0)} "
        f"({r['logic_exceptions'].get('term_cell', 0)} with a cell term); "
        f"tests run {r['tests_run']}, constructing "
        f"{r['tests_constructing']}; engine {r['engine']}")
