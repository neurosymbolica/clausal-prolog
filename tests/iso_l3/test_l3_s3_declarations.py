"""Slice 3: declarations on the native ``.pl`` front end (plan
native-iso-reader-step2 §4 Slice 3, §5 D4/D5 as ruled 2026-09-30).

* Clausal Prolog is NOT strict: every atom and data functor a file uses is
  auto-declared -- bound to its spelling, so a seam importer can name it --
  and the declared set's SIZE is one INFO line per load.  A data functor
  gets no field signature from its use (``assertz`` of one of its terms must
  keep creating a dynamic procedure, as ISO 7.5.2 and the flag allow).
* ``:- constructors([pt(x, y)]).`` is OPTIONAL and only gives a data functor
  its FIELD NAMES (the seam's -private/-module template).  Exported as
  ``pt/2`` in module/2, it reaches -module as its template.
* An atom entry in a use_module/2 list imports nothing (D11(a), slice 2).

Every load clears ``__pycache__`` and asserts the native loader ran over a
non-zero population (the ``native`` fixture) -- except the cache test, which
keeps it on purpose.
"""
from __future__ import annotations

import importlib
import logging
import os
import shutil
import sys
import textwrap
import warnings

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
S3 = os.path.join(HERE, "s3")


def _write(native, rel: str, text: str) -> None:
    path = native.tmp / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    native._names.append(rel.rsplit(".", 1)[0].replace("/", "."))


def _refusal(native, name, text):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, textwrap.dedent(text))
    assert name not in sys.modules
    return ei.value


# ── auto-declaration ──


DATA_ONLY = """\
    :- module(s3_data, [mk/1, sel/2, q/1]).
    mk(X) :- X = attribute(color, red).
    sel(attribute(K, _), K).
    q(Y) :- mk(A), sel(A, Y).
    """


def test_a_data_functor_used_only_as_data_loads_and_builds_data(native, ans):
    """The pilot's existence_error(procedure, attribute/2) class: a functor
    that is only ever DATA, with no declaration anywhere."""
    mod = native.load("s3_data", textwrap.dedent(DATA_ONLY))
    assert ans(mod, "mk") == [("attribute", "color", "red")]
    assert ans(mod, "q") == ["color"]
    assert ans(mod, "sel", 2, ("attribute", "size", 3)) == ["size"]
    st = mod.__loader__.l3_stats
    assert st["auto_declared"] == {"atoms": 2, "functors": 1}, st
    assert (mod.color, mod.red, mod.attribute) == ("color", "red", "attribute")


def test_the_declared_set_size_is_an_info_line_not_a_warning(native, caplog):
    caplog.set_level(logging.DEBUG, logger="clausal.pl_frontend")
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        native.load("s3_info", textwrap.dedent(DATA_ONLY))
    lines = [r for r in caplog.records if r.name == "clausal.pl_frontend"]
    info = [r.getMessage() for r in lines if r.levelno == logging.INFO]
    assert len(info) == 1, info
    assert info[0].endswith(
        "s3_info.pl: auto-declared 3 names (2 atoms, 1 data functors)"), info
    debug = [r.getMessage() for r in lines if r.levelno == logging.DEBUG]
    assert debug and "color, red; data functors: attribute/2" in debug[0]
    assert not [w for w in got if "auto-declared" in str(w.message)]


def test_a_seam_module_imports_what_a_pl_module_auto_declared(native, ans):
    """The declaration is the .pl module's import surface: before slice 3
    this was ImportError (cannot import name 'color')."""
    native.load("s3_data2", textwrap.dedent(DATA_ONLY).replace(
        "s3_data", "s3_data2"))
    mod = native.load("s3_seamuse", textwrap.dedent("""\
        -module(s3_seamuse, [c/1, k/1])
        -import_from(s3_data2, [color, red, q])
        c(C) <- (C is color)
        k(K) <- (q(K), K == color)
        """), suffix=".seam")
    assert ans(mod, "c") == ["color"]
    assert ans(mod, "k") == ["color"]


def test_names_that_mean_something_else_are_not_declared(native, ans):
    """A head, a goal, an imported predicate (here passed as a closure), a
    builtin, an evaluable, a dynamic procedure and an assertz target keep
    their meaning: none is bound as an atom over it."""
    _write(native, "s3_lib.pl", """\
        :- module(s3_lib, [twice/2]).
        twice(X, Y) :- Y is 2 * X.
        """)
    mod = native.load("s3_keep", textwrap.dedent("""\
        :- module(s3_keep, [dbl/1, succs/1, grow/1, more/1, mx/1, h/1]).
        :- use_module(s3_lib, [twice/2]).
        :- dynamic(seen/1).
        dbl(L) :- maplist(twice, [1, 2], L).
        succs(L) :- maplist(succ, [1, 2], L).
        grow(Y) :- T = counted(7), assertz(T), counted(Y).
        more(X) :- assertz(seen(x)), seen(X).
        mx(M) :- M is max(3, 4).
        h(h).
        h(dbl).
        """))
    assert ans(mod, "dbl") == [[2, 4]]
    assert ans(mod, "succs") == [[2, 3]]
    assert ans(mod, "grow") == [7]
    assert ans(mod, "more") == ["x"]
    assert ans(mod, "mx") == [4]
    assert ans(mod, "h") == ["h", "dbl"]
    ctx_atoms = mod.__loader__.l3_stats["auto_declared"]
    # x is the only name here with no other meaning.
    assert ctx_atoms == {"atoms": 1, "functors": 0}, ctx_atoms
    assert mod.x == "x"


def test_a_cache_hit_recovers_the_same_declarations(tmp_path, monkeypatch, ans):
    """The cache-hit path re-lowers the directives only; the declarations
    come from the clauses' cells, so it must see the same population."""
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    (tmp_path / "s3_cached.pl").write_text(
        textwrap.dedent(DATA_ONLY).replace("s3_data", "s3_cached"))
    stats = []
    try:
        for _ in range(2):
            sys.modules.pop("s3_cached", None)
            importlib.invalidate_caches()
            mod = importlib.import_module("s3_cached")
            stats.append(dict(mod.__loader__.l3_stats))
            assert mod.color == "color" and ans(mod, "q") == ["color"]
    finally:
        sys.modules.pop("s3_cached", None)
    assert stats[0]["skipped"] == 0 and stats[1]["skipped"] == 3, stats
    assert stats[0]["auto_declared"] == stats[1]["auto_declared"] == {
        "atoms": 2, "functors": 1}


# ── constructors/1 ──


GEO = """\
    :- module(s3_geo, [pt/2, origin/1, sig/1, ub/1, segsig/1, mkseg/1]).
    :- constructors([pt(x, y), seg(start, stop)]).
    origin(pt(0, 0)).
    mkseg(S) :- S = seg(pt(0, 0), pt(1, 1)).
    sig(N) :- signature(pt, 2, N).
    ub(K) :- unbound_keys(pt(1, _), K).
    segsig(N) :- signature(seg, 2, N).
    """


def test_a_constructor_builds_data_and_carries_its_field_names(native, ans):
    mod = native.load("s3_geo", textwrap.dedent(GEO))
    assert ans(mod, "origin") == [("pt", 0, 0)]
    assert ans(mod, "mkseg") == [("seg", ("pt", 0, 0), ("pt", 1, 1))]
    assert ans(mod, "sig") == [["x", "y"]]
    assert ans(mod, "ub") == [["y"]]
    assert ans(mod, "segsig") == [["start", "stop"]]
    # Exported as pt/2, it is DATA: bound to its spelling, not a predicate.
    assert mod.pt == "pt"
    assert mod.__clausal_functor_signatures__ == {
        "pt": ("x", "y"), "seg": ("start", "stop")}


@pytest.mark.parametrize("imp", [":- use_module(s3_geo2, [pt/2, origin/1]).",
                                 ":- use_module(s3_geo2)."])
def test_an_exported_constructor_is_imported_with_its_fields(native, ans, imp):
    _write(native, "s3_geo2.pl", GEO.replace("s3_geo", "s3_geo2"))
    mod = native.load("s3_geouse", textwrap.dedent(f"""\
        :- module(s3_geouse, [t/1, s/1, u/1]).
        {imp}
        t(X) :- origin(pt(X, _)).
        s(N) :- signature(pt, 2, N).
        u(P) :- P = pt(3, 4).
        """))
    assert ans(mod, "t") == [0]
    assert ans(mod, "s") == [["x", "y"]]
    assert ans(mod, "u") == [("pt", 3, 4)]


def test_a_seam_importer_builds_the_exported_constructor(native, ans):
    _write(native, "s3_geo3.pl", GEO.replace("s3_geo", "s3_geo3"))
    mod = native.load("s3_geoseam", textwrap.dedent("""\
        -module(s3_geoseam, [t/1, s/1, u/1])
        -import_from(s3_geo3, [pt, origin])
        t(X) <- origin(pt(X, _))
        s(N) <- signature(pt, 2, N)
        u(P) <- (P is pt(3, 4))
        """), suffix=".seam")
    assert ans(mod, "t") == [0]
    assert ans(mod, "s") == [["x", "y"]]
    assert ans(mod, "u") == [("pt", 3, 4)]


@pytest.mark.parametrize("decl, fragment", [
    ("constructors([foo])", "foo has no fields; an atom needs no declaration"),
    ("constructors([pt/2])", "write the template pt(f1, f2)"),
    ("constructors([pt(x, X)])", "the field name _ is not a lowercase"),
    ("constructors([pt(x, x)])", "repeats a field name"),
    ("constructors([seg(from, to)])", "the field name from is not"),
    ("constructors(['Pt'(x)])", "Pt cannot name a constructor"),
    ("constructors([pt(x, y), pt(a, b)])", "declared twice with different"),
])
def test_constructors_refusals_name_their_line(native, decl, fragment):
    err = _refusal(native, "s3_badctor", f"a.\n:- {decl}.\n")
    assert err.lineno == 2, err
    assert fragment in str(err), str(err)


def test_a_constructor_defined_by_clauses_is_refused(native):
    err = _refusal(native, "s3_ctorpred", """\
        :- constructors([pt(x, y)]).
        pt(1, 2).
        """)
    assert err.lineno == 1
    assert "pt/2 is declared a constructor (data) and is also defined" \
        in str(err)


def test_atoms_1_is_not_part_of_the_language(native):
    err = _refusal(native, "s3_atoms", "a.\n:- atoms([red]).\n")
    assert "unknown directive atoms/1" in str(err)


# ── the package facade (an atom imported from a package) ──


V = object()

CALLS = [("cmp", V), ("kind_of", V, V), ("tagged", V), ("ox", V), ("sig", V),
         ("ub", V), ("attr_val", V, V), ("made", V)]

_OWN = ("s3main", "s3pkg", "s3twmain", "s3tw", "s3seamuse")


def _forget():
    for n in list(sys.modules):
        if n.split(".")[0] in _OWN:
            sys.modules.pop(n, None)


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    shutil.copytree(os.path.join(S3, "native"), tmp_path / "native")
    shutil.copytree(os.path.join(S3, "twin"), tmp_path / "twin")
    monkeypatch.syspath_prepend(str(tmp_path / "native"))
    monkeypatch.syspath_prepend(str(tmp_path / "twin"))
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    _forget()
    importlib.invalidate_caches()
    yield tmp_path
    _forget()


def _all(mod, call):
    from clausal.logic.solve import call as run
    from clausal.logic.variables import Var, deref, walk
    name, *pattern = call
    args = [Var() if a is V else a for a in pattern]
    free = [a for a, p in zip(args, pattern) if p is V]
    return [tuple(walk(deref(v)) for v in free)
            for _ in run(name, *args, module=mod)]


def test_a_test_module_imports_an_atom_from_a_package_facade(pkg):
    from clausal import import_hook as ih
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        main = importlib.import_module("s3main")
    facade = sys.modules["s3pkg"]
    kinds = sys.modules["s3pkg.kinds"]
    for m in (main, facade, kinds):
        assert type(m.__loader__) is ih.NativePrologLoader
        assert m.__loader__.l3_stats["read"] > 0
    assert _all(main, ("cmp", V)) == [(1,)]
    assert _all(main, ("tagged", V)) == [(("tag", "class_comparison"),)]
    # The facade USES the atom (its import-list entry), so declares it.
    assert facade.class_comparison == "class_comparison"


def test_the_package_answers_as_its_seam_twin(pkg):
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        main = importlib.import_module("s3main")
        twin = importlib.import_module("s3twmain")
    for call in CALLS:
        got, want = _all(main, call), _all(twin, call)
        assert got, call            # a non-empty population per predicate
        assert got == want, (call, got, want)


def test_a_seam_module_imports_the_atom_from_the_native_facade(pkg):
    (pkg / "native" / "s3seamuse.seam").write_text(textwrap.dedent("""\
        -module(s3seamuse, [t/1])
        -import_from(s3pkg, [class_comparison, classify])
        t(X) <- classify(X, class_comparison)
        """))
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        mod = importlib.import_module("s3seamuse")
    assert _all(mod, ("t", V)) == [(1,)]
