"""Operator ruling 2026-09-30: a seam ``-import_from(M, [name])`` against a
``.pl`` module M that neither defines ``name`` as a predicate (at any arity)
nor binds it resolves to the ATOM ``name`` -- data needs no declaration, and
a ``.pl`` export list holds only ``name/arity`` predicates.

On d7f1a837 the import raised ``ImportError: cannot import name 'cite' ...
citations exports: citation/2`` unless the ``.pl`` file happened to use
``cite(...)`` as data itself.  A name that IS bound by M keeps the ordinary
path; a ``.clausal`` target is unchanged (it exports data explicitly).

Every ``.pl`` case runs under both front ends (``CLAUSAL_PL_FRONTEND``).
"""
import sys
import textwrap
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.lint_warnings import ClausalImportedDataNameWarning

FRONT_ENDS = ("translator", "native")

CITATIONS = """\
    :- module(citations, [citation/2]).
    citation(xx_art1, [label-'Art 1', ref-'x']).
    helper(K) :- citation(K, _).
"""

RULES = """\
    :- module(rules, [verdict/2]).
    verdict(P, v(ok, [cite(xx_art1)])) :- P = p.
"""


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    """A fresh package ``<tag>`` holding ``dom/citations.pl`` and
    ``dom/rules.pl``, loaded under front end *fe*; ``load(name, src)`` loads
    a seam module of the package."""
    made = []

    def _make(fe, tag):
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", fe)
        monkeypatch.syspath_prepend(str(tmp_path))
        root = tmp_path / tag
        (root / "dom").mkdir(parents=True)
        (root / "__init__.py").write_text("")
        (root / "dom" / "__init__.py").write_text("")
        (root / "dom" / "citations.pl").write_text(textwrap.dedent(CITATIONS))
        (root / "dom" / "rules.pl").write_text(textwrap.dedent(RULES))
        made.append(tag)

        def load(name, src, ext="seam"):
            path = root / f"{name}.{ext}"
            path.write_text(textwrap.dedent(src).replace("PKG", tag))
            return _load_module(f"{tag}.{name}", str(path))
        return load

    yield _make
    for tag in made:
        for key in [k for k in sys.modules
                    if k == tag or k.startswith(tag + ".")]:
            sys.modules.pop(key, None)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_data_name_imports_as_its_atom_and_matches_the_rulebase(pkg, fe):
    load = pkg(fe, f"dn_witness_{fe}")
    mod = load("score", """\
        -import_from(PKG.dom.citations, [cite])
        -import_from(PKG.dom.rules, [verdict, p])
        from clausal.logic.atoms import mint

        def atom():
            return cite

        def found(key):
            return [C for C in --match(++mint(key), C)]

        match(K, C) <- (verdict(p, T), arg(2, T, [C]), '=..'(C, [cite, K]))
    """)
    loader = type(sys.modules[f"dn_witness_{fe}.dom.citations"].__loader__)
    assert loader.__name__ == {"native": "NativePrologLoader",
                               "translator": "PrologLoader"}[fe]
    assert mod.atom() == "cite" and type(mod.atom()) is str
    (term,) = mod.found("xx_art1")
    # The rulebase's cite(xx_art1) is the cell ('cite', 'xx_art1'); the one
    # built from the imported atom is the same term.
    assert term == ("cite", "xx_art1")
    assert (mod.atom(), "xx_art1") == term
    assert mod.found("nope") == []


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_an_aliased_data_name_binds_the_original_atom(pkg, fe):
    load = pkg(fe, f"dn_alias_{fe}")
    mod = load("al", """\
        -import_from(PKG.dom.citations, [alias(cite, c)])
        def atom():
            return c
    """)
    assert mod.atom() == "cite"


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_an_exported_predicate_still_imports_the_predicate(pkg, fe):
    load = pkg(fe, f"dn_exported_{fe}")
    mod = load("ex", """\
        -import_from(PKG.dom.citations, [citation, cite])
        def keys():
            return [K for K in --citation(K, _)]
        def atom():
            return cite
    """)
    assert mod.keys() == ["xx_art1"]
    assert mod.atom() == "cite"


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_defined_unexported_predicate_is_unchanged(pkg, fe):
    """Not data: ``helper`` is a predicate of the module, so the ruling does
    not apply and the import takes the path it took before (on d7f1a837 the
    module binds its unexported predicates, so this import succeeds and
    binds the predicate -- never the atom)."""
    load = pkg(fe, f"dn_unexported_{fe}")
    mod = load("un", """\
        -import_from(PKG.dom.citations, [helper])
        def binding():
            return helper
        def keys():
            return [K for K in --helper(K)]
    """)
    assert mod.binding() != "helper"
    assert mod.keys() == ["xx_art1"]


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_an_indicator_never_resolves_to_data(pkg, fe):
    """``name/N`` names a PREDICATE; a missing one is still an error."""
    load = pkg(fe, f"dn_indicator_{fe}")
    with pytest.raises(ImportError, match="cannot import name 'cite'"):
        load("ind", """\
            -import_from(PKG.dom.citations, [cite/1])
        """)


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_near_miss_of_a_predicate_warns_once_naming_it(pkg, fe):
    load = pkg(fe, f"dn_typo_{fe}")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = load("ty", """\
            -import_from(PKG.dom.citations, [citaton])
            -import_from(PKG.dom.citations, [citaton])
            def atom():
                return citaton
        """)
    hits = [w for w in caught
            if issubclass(w.category, ClausalImportedDataNameWarning)]
    assert len(hits) == 1, [str(w.message) for w in caught]
    assert "`citation`" in str(hits[0].message)
    assert "citaton" in str(hits[0].message)
    assert mod.atom() == "citaton"


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_data_name_far_from_every_predicate_does_not_warn(pkg, fe):
    load = pkg(fe, f"dn_nowarn_{fe}")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load("nw", """\
            -import_from(PKG.dom.citations, [cite, helpr_x, ab])
        """)
    assert not [w for w in caught
                if issubclass(w.category, ClausalImportedDataNameWarning)]


def test_the_near_miss_bound():
    from clausal.pl_data_imports import near_predicates
    preds = {"citation", "helper", "cited"}
    assert near_predicates("citaton", preds) == ["citation"]      # deletion
    assert near_predicates("ciattion", preds) == ["citation"]     # transposition
    assert near_predicates("cite", preds) == ["cited"]            # one edit
    assert near_predicates("cit", preds) == []                    # too short
    assert near_predicates("elper", preds) == ["helper"]
    assert near_predicates("hlpr", preds) == []                   # two edits, short


def test_a_clausal_target_is_unchanged(tmp_path, monkeypatch):
    """A ``.clausal`` module exports data explicitly; a name it does not
    export stays an ImportError."""
    monkeypatch.syspath_prepend(str(tmp_path))
    root = tmp_path / "dn_clausal"
    root.mkdir()
    (root / "__init__.py").write_text("")
    (root / "citations.clausal").write_text(
        "-module(citations, [citation(KEY, META), yy_art1])\n"
        "citation(yy_art1, 1),\n")
    body = root / "body.seam"
    body.write_text("-import_from(dn_clausal.citations, [cite])\n")
    try:
        with pytest.raises(ImportError, match="cannot import name 'cite'"):
            _load_module("dn_clausal.body", str(body))
    finally:
        for key in [k for k in sys.modules if k.startswith("dn_clausal")]:
            sys.modules.pop(key, None)


def test_a_python_target_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "dn_pymod.py").write_text("x = 1\n")
    body = tmp_path / "dn_pybody.seam"
    body.write_text("-import_from(dn_pymod, [cite])\n")
    try:
        with pytest.raises(ImportError, match="cannot import name 'cite'"):
            _load_module("dn_pybody", str(body))
    finally:
        sys.modules.pop("dn_pymod", None)
        sys.modules.pop("dn_pybody", None)
