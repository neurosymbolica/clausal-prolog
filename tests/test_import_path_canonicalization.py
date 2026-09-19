"""One .clausal file reached under two dotted names must be one compilation.

``pkg/soledom.clausal`` imported as both ``soledom`` (because ``pkg/`` is on
``sys.path``) and ``pkg.soledom`` used to compile *twice*, producing two
independent ``PredicateMeta`` classes for the same declared compound.  A term
built by one and matched against a pattern from the other simply yielded no
solution — the two terms render identically, so no diagnostic disagreed.  See
``todo/two-compilations-of-one-file-produce-terms-that-never-unify.md``.
"""

from __future__ import annotations

import importlib
import sys

import pytest

import clausal.import_hook  # noqa: F401  — installs the finders
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


SOLEDOM = """\
-module(soledom, [sole_verdict(STATUS, NOTE), ok, note1, decide_sole(IN, VERDICT)])

decide_sole(IN, VERDICT) <- (
    IN is ok,
    VERDICT is sole_verdict(ok, note1)
)
"""

VIA_FLAT = """\
-module(viaflat, [make(V)])

-import_from(soledom, [sole_verdict, ok, note1, decide_sole])

make(V) <- decide_sole(ok, V)
"""

VIA_DOTTED = """\
-module(viadotted, [classify(VERDICT, CLASS), matched])

-import_from(pkg.soledom, [sole_verdict, ok])

classify(VERDICT, matched) <- (
    VERDICT is sole_verdict(ok)
)
"""

_NAMES = ("soledom", "pkg", "pkg.soledom", "viaflat", "viadotted")


@pytest.fixture
def two_paths(tmp_path):
    """A package dir whose parent *and* itself are both on sys.path.

    That makes ``pkg/soledom.clausal`` reachable as ``soledom`` and as
    ``pkg.soledom`` — the two dotted names for one file.
    """
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.clausal").write_text("-module(pkg, [])\n")
    (pkg / "soledom.clausal").write_text(SOLEDOM)
    (tmp_path / "viaflat.clausal").write_text(VIA_FLAT)
    (tmp_path / "viadotted.clausal").write_text(VIA_DOTTED)

    saved_path = list(sys.path)
    saved_modules = {n: sys.modules[n] for n in _NAMES if n in sys.modules}
    for n in _NAMES:
        sys.modules.pop(n, None)
    sys.path.insert(0, str(pkg))
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        yield tmp_path
    finally:
        sys.path[:] = saved_path
        for n in _NAMES:
            sys.modules.pop(n, None)
        sys.modules.update(saved_modules)


def test_two_dotted_names_yield_one_module(two_paths):
    flat = importlib.import_module("soledom")
    dotted = importlib.import_module("pkg.soledom")
    assert flat is dotted


def test_two_dotted_names_yield_one_declared_compound(two_paths):
    flat = importlib.import_module("soledom")
    dotted = importlib.import_module("pkg.soledom")
    assert flat.sole_verdict is dotted.sole_verdict
    assert flat.ok is dotted.ok


def test_import_order_does_not_matter(two_paths):
    dotted = importlib.import_module("pkg.soledom")
    flat = importlib.import_module("soledom")
    assert flat is dotted
    assert flat.sole_verdict is dotted.sole_verdict


def test_term_built_under_one_name_matches_a_pattern_from_the_other(two_paths):
    """The bug as the application met it: zero solutions, no error."""
    producer = importlib.import_module("viaflat")
    consumer = importlib.import_module("viadotted")

    verdict = None
    v = Var()
    for _ in call("make", v, module=producer.__dict__["$module"]):
        verdict = deref(v)
        break
    assert verdict is not None, "producer failed to build a verdict"

    c = Var()
    classes = []
    for _ in call("classify", verdict, c, module=consumer.__dict__["$module"]):
        classes.append(deref(c))

    assert classes, (
        "classify() found no solution for a term that renders as "
        f"{verdict!r} — the two compilations' constructors did not unify"
    )


def test_eviction_from_sys_modules_recompiles(two_paths):
    """A stale registry entry must not resurrect an evicted module."""
    flat = importlib.import_module("soledom")
    del sys.modules["soledom"]
    again = importlib.import_module("soledom")
    assert again is not flat, "aliased to a module no longer in sys.modules"
    # ... and the reclaimed entry is the one later names dedupe against.
    dotted = importlib.import_module("pkg.soledom")
    assert dotted is again


def test_symlinked_package_is_the_same_package(tmp_path):
    """Dedup is by resolved path, so a symlinked directory is not a second copy."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.clausal").write_text("-module(pkg, [])\n")
    (pkg / "soledom.clausal").write_text(SOLEDOM)
    (tmp_path / "alias").symlink_to(pkg, target_is_directory=True)

    names = ("pkg", "pkg.soledom", "alias", "alias.soledom")
    saved_path = list(sys.path)
    saved_modules = {n: sys.modules[n] for n in names if n in sys.modules}
    for n in names:
        sys.modules.pop(n, None)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        assert importlib.import_module("pkg") is importlib.import_module("alias")
        real = importlib.import_module("pkg.soledom")
        via_link = importlib.import_module("alias.soledom")
        assert real is via_link
        # P3-2 Task 2 (R6): the identity probe reads a PREDICATE class.
        # ``sole_verdict`` is a data functor now, so its binding is the
        # interned spelling -- identical across independent compilations by
        # construction, which makes it useless as an identity witness.
        assert real.decide_sole is via_link.decide_sole
    finally:
        sys.path[:] = saved_path
        for n in names:
            sys.modules.pop(n, None)
        sys.modules.update(saved_modules)


def test_load_module_helper_does_not_claim_the_path(two_paths):
    """``_load_module`` compiles a private copy; a later import must not get it.

    Test isolation depends on ``_load_module`` producing a fresh compilation
    every call, so it deliberately stays out of the path registry.
    """
    from clausal.import_hook import _load_module

    private = _load_module("_priv_soledom",
                           str(two_paths / "pkg" / "soledom.clausal"))
    try:
        imported = importlib.import_module("soledom")
        assert imported is not private
        # R6, as above: a data functor's binding is the interned spelling and
        # cannot witness two separate compilations apart.  ``decide_sole``
        # has clauses, so it is still a per-compilation class.
        assert imported.decide_sole is not private.decide_sole
        # The dotted import still owns the path for every other dotted name.
        assert importlib.import_module("pkg.soledom") is imported
    finally:
        sys.modules.pop("_priv_soledom", None)
