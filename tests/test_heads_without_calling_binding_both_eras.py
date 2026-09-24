"""W4b-2d task 5 (the flip dry run's R4): a clause HEAD is built without
calling the binding, in BOTH eras.

While a module body runs, every module-level head is ``$head(<binding>,
...)`` (``term_rewriting._head_ctor_ast`` -> ``predicate.head_cell``).  Today
the binding is a ``PredicateMeta`` class and is called exactly as before;
after the flip it is a predicate HANDLE (a mangled ``str``), which used to
raise ``'str' object is not callable`` at the fixture line, so a module
whose head names an IMPORTED predicate died before the mutation gate could
refuse it.

The handle era is exercised the way ``test_import_origins_both_eras`` does
it: load the owner for real, then replace its module attribute with
``mint_predicate_handle(owner_db, name)`` so the importer's ``-import_from``
binds the handle.  Every comparison also asserts that the class era answers
at all, so a check that quietly agrees with itself cannot pass.
"""

from __future__ import annotations

import os
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.predicate import (
    AmbiguousArityConstructionError, ClausalTermConstructionError, PredicateMeta, field_names_for, head_cell,
    mint_predicate_handle, resolve_predicate_row,
)
from clausal.logic.variables import Var, deref

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ERAS = ("class", "handle")


# ── the end-to-end loads: an importer's head names an imported predicate ────


@pytest.fixture
def fixture_modules():
    """Load fixtures under their ``tests.fixtures.*`` names, and put
    ``sys.modules`` back afterwards -- a flipped owner must not leak into a
    later test that imports it by name."""
    saved = {k: v for k, v in sys.modules.items()
             if k.startswith("tests.fixtures.")}

    def load(stem):
        return _load_module(f"tests.fixtures.{stem}",
                            os.path.join(FIXTURES, f"{stem}.clausal"))

    yield load
    for k in [k for k in sys.modules if k.startswith("tests.fixtures.")]:
        del sys.modules[k]
    sys.modules.update(saved)


def _flip(owner, name, arity):
    """Rebind *owner*'s attribute *name* to its predicate HANDLE."""
    cls = owner.__dict__[name]
    assert isinstance(cls, PredicateMeta), "the class era precondition"
    row = resolve_predicate_row(cls, arity=arity)
    db = row.db if row is not None else owner.__dict__["$module"].db
    owner.__dict__[name] = mint_predicate_handle(db, name)
    return owner.__dict__[name]


def _load_importer(load, era, owner_stem, name, arity, importer_stem):
    for k in [k for k in sys.modules if k.startswith("tests.fixtures.")]:
        del sys.modules[k]
    owner = load(owner_stem)
    if era == "handle":
        handle = _flip(owner, name, arity)
        assert type(handle) is str and handle == mangle(
            f"tests.fixtures.{owner_stem}", name)
    return load(importer_stem)


@pytest.mark.parametrize("era", ERAS)
@pytest.mark.parametrize("importer", ["impclob_redefine",
                                      "impclob_alias_redefine"])
def test_a_head_naming_an_imported_predicate_reaches_the_gate(
        fixture_modules, era, importer):
    """The gate's clobber refusal, not ``'str' object is not callable``."""
    with pytest.raises(SyntaxError) as exc_info:
        _load_importer(fixture_modules, era, "impclob_owner",
                       "impclob_colour", 1, importer)
    msg = str(exc_info.value)
    assert f"tests.fixtures.{importer} defines a clause for impclob_colour/1" \
        in msg, msg
    assert "impclob_owner" in msg
    assert "not callable" not in msg


@pytest.mark.parametrize("era", ERAS)
def test_an_imported_head_at_the_wrong_arity_raises_the_arity_error(
        fixture_modules, era):
    """``impord_narrow(ok, [])`` against an imported ``impord_narrow/1``: the
    class constructor's arity check, answered in both eras by
    ``build_term_cell``."""
    with pytest.raises(ClausalTermConstructionError) as exc_info:
        _load_importer(fixture_modules, era, "impord_arity_vocab",
                       "impord_narrow", 1, "impord_arity_clash")
    msg = str(exc_info.value)
    assert "impord_narrow/1" in msg
    assert "2 positional argument(s)" in msg
    assert "exactly one arity" in msg
    assert "impord_arity_clash.clausal:" in msg      # constructed at
    if era == "class":
        # The declaration SITE lives only on the class (todo: declaration
        # site); a handle's "registered by" reads <unknown> until it moves.
        assert "impord_arity_vocab.clausal:" in msg


@pytest.mark.parametrize("era", ERAS)
def test_implementing_a_declared_only_predicate_reaches_the_vocabulary_drop(
        fixture_modules, era):
    """Declare-then-import-then-define against a FIELDED declaration: the
    vocabulary drop's refusal (0c8f5839), in both eras -- not a TypeError
    from calling a str at the head."""
    with pytest.raises(SyntaxError) as exc_info:
        _load_importer(fixture_modules, era, "fnmismatch_schema",
                       "fnm_verdict", 2, "fnmismatch_use")
    msg = str(exc_info.value)
    assert ("tests.fixtures.fnmismatch_use defines clauses for fnm_verdict/2"
            in msg), msg
    assert "only declares fnm_verdict/2" in msg


@pytest.mark.parametrize("era", ERAS)
def test_implementing_an_arity_only_export_loads_in_both_eras(
        fixture_modules, era):
    """``impclob_verdict/2`` is a bare export entry (the ``gv_free`` idiom
    the vocabulary drop keeps): the importer's head is BUILT, not called,
    and the load goes through in both eras."""
    mod = _load_importer(fixture_modules, era, "impclob_decl_vocab",
                         "impclob_verdict", 2, "impclob_implements")
    assert mod is not None


# ── head_cell / field names on one owner, both bindings side by side ────────

_OWNER = "_heads5_owner"
_OWNER_SRC = textwrap.dedent("""\
    -module(_heads5_owner, [p(A), q(A, B), z(), dx/1, m(A), gy/1])
    -dynamic(e/2)
    -dynamic(f/2)
    -dynamic(m/2)
    -dynamic(n/1)

    p(1),
    q(1, 2),
    z(),
    m(1),
    f(P, Q) <- (p(P), p(Q))
    f(R, S) <- q(R, S)
    gy(W) <- p(W)
    n(U, V) <- q(U, V)
""")


@pytest.fixture(scope="module")
def owner(tmp_path_factory):
    path = tmp_path_factory.mktemp("heads5") / "_heads5_owner.clausal"
    path.write_text(_OWNER_SRC)
    sys.modules.pop(_OWNER, None)
    module = _load_module(_OWNER, str(path))
    yield module
    sys.modules.pop(_OWNER, None)


def _db(owner):
    return owner.__dict__["$module"].db


def _both(owner, name):
    cls = owner.__dict__[name]
    assert isinstance(cls, PredicateMeta), name
    return {"class": cls, "handle": mint_predicate_handle(_db(owner), name)}


def _shape(term):
    """A cell with its fresh variables replaced by a marker."""
    if isinstance(term, tuple):
        return tuple(_shape(x) for x in term)
    term = deref(term)
    return "<var>" if isinstance(term, Var) else term


def _without_registered_by(msg):
    return "\n".join(line for line in msg.splitlines()
                     if "registered by:" not in line)


@pytest.mark.parametrize("name,args,kwargs,expected", [
    ("p", (7,), {}, ("p", 7)),
    ("p", (), {"A": 7}, ("p", 7)),
    ("p", (), {}, ("p", "<var>")),
    ("q", (), {"B": 8}, ("q", "<var>", 8)),
    ("q", (7, 8), {}, ("q", 7, 8)),
])
def test_the_same_cell_in_both_eras(owner, name, args, kwargs, expected):
    built = {era: _shape(head_cell(b, *args, **dict(kwargs)))
             for era, b in _both(owner, name).items()}
    assert built == {"class": expected, "handle": expected}


@pytest.mark.parametrize("name,args,kwargs", [
    ("p", (1, 2), {}),                     # overflow
    ("q", (1, 2, 3), {}),                  # overflow
    ("q", (7,), {}),                       # short: ruling C refuses, no pad
    ("q", (), {"C": 1}),                   # a field it does not have
    ("q", (1,), {"arg_1": 1}),             # placeholder spelling
])
def test_the_same_construction_error_in_both_eras(owner, name, args, kwargs):
    msgs = {}
    for era, binding in _both(owner, name).items():
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            head_cell(binding, *args, **dict(kwargs))
        exc = exc_info.value
        msgs[era] = (_without_registered_by(str(exc)), exc.functor,
                     exc.arity, exc.supplied_fields, exc.registered_fields)
    assert msgs["class"] == msgs["handle"]


def test_a_zero_arity_head_is_the_atom_of_its_name(owner):
    both = _both(owner, "z")
    assert head_cell(both["class"]) is both["class"]    # unchanged
    assert head_cell(both["handle"]) == "z"             # the atom IS the str


def test_arity_only_placeholders_are_answered_for_a_handle(owner):
    """``dx/1`` in the export list and ``-dynamic(e/2)`` name an arity only.
    Their placeholder field names lived ONLY on the class."""
    db = _db(owner)
    for name, arity in (("dx", 1), ("e", 2)):
        both = _both(owner, name)
        placeholders = tuple(f"arg_{i}" for i in range(arity))
        assert both["class"]._fields == placeholders
        assert db.placeholder_fields(name, arity) == placeholders
        assert field_names_for(both["handle"], arity=arity) == placeholders
        assert field_names_for(both["handle"]) == placeholders
        # ``signature_for`` is not widened: its None still means "no names".
        assert db.signature_for(name, arity) is None
        # a plain name keeps its old answer
        assert field_names_for(name, arity=arity, db=db) is None
        kw = {placeholders[-1]: 5}
        assert (_shape(head_cell(both["class"], **dict(kw)))
                == _shape(head_cell(both["handle"], **dict(kw)))
                == (name, *(["<var>"] * (arity - 1)), 5))


@pytest.mark.parametrize("name,arity,derived", [
    ("f", 2, ("p", "q")),      # -dynamic(f/2), then clauses
    ("gy", 1, ("w",)),         # bare gy/1 export, then a clause
])
def test_after_a_clause_the_handle_answers_the_heads_names(
        owner, name, arity, derived):
    """The second state of an arity-only declaration: a clause unseats the
    placeholders, the class carries the head's derived names, and step 4
    stamps them as the row's signature -- which the handle reads first."""
    db = _db(owner)
    both = _both(owner, name)
    assert both["class"]._fields == derived            # the class era
    assert db.row(name, arity).signature == derived     # what the handle reads
    assert db.placeholder_fields(name, arity) is None
    assert field_names_for(both["handle"], arity=arity) == derived
    assert field_names_for(both["handle"]) == derived
    assert db.head_signatures(name) == {arity: derived}
    # a KEYWORD head -- the rewriter's default emission -- builds the same
    # cell in both eras, and a placeholder keyword is refused in both
    kw = {derived[-1]: 9}
    built = {era: _shape(head_cell(b, **dict(kw)))
             for era, b in both.items()}
    assert built["class"] == built["handle"] == (
        name, *(["<var>"] * (arity - 1)), 9)
    for binding in both.values():
        with pytest.raises(ClausalTermConstructionError):
            head_cell(binding, **{f"arg_{arity - 1}": 9})


def test_real_names_win_over_placeholders(owner):
    db = _db(owner)
    assert db.placeholder_fields("p", 1) is None       # not arity-only
    # -dynamic(m/2) with no names beside a named m/1
    assert db.placeholder_fields("m", 1) is None
    assert db.placeholder_fields("m", 2) == ("arg_0", "arg_1")


def test_a_name_at_two_arities_builds_at_the_written_one(owner):
    handle = mint_predicate_handle(_db(owner), "m")
    assert _shape(head_cell(handle, 1)) == ("m", 1)
    assert _shape(head_cell(handle, 1, 2)) == ("m", 1, 2)
    assert _shape(head_cell(handle, A=1)) == ("m", 1)
    assert _shape(head_cell(handle, arg_1=2)) == ("m", "<var>", 2)
    with pytest.raises(AmbiguousArityConstructionError,
                       match=r"m/1, m/2") as exc_info:
        head_cell(handle, 1, 2, 3)
    exc = exc_info.value
    assert isinstance(exc, ClausalTermConstructionError)   # still caught
    # No single registration to report -- not a 0-field one.
    assert exc.arity is None and exc.registered_fields is None
    assert exc.signatures == {1: ("A",), 2: ("arg_0", "arg_1")}
    assert exc.supplied_fields == ("arg_0", "arg_1", "arg_2")


def test_by_name_at_several_arities_answers_nothing_for_a_handle(owner):
    """``n/1`` is placeholder-only (``-dynamic``), ``n/2`` has a clause with
    real names.  By name, a handle does not answer one arity's placeholders
    as if they were the name's (roborev Low); by arity, each is exact."""
    handle = mint_predicate_handle(_db(owner), "n")
    assert field_names_for(handle) is None
    assert field_names_for(handle, arity=1) == ("arg_0",)
    assert field_names_for(handle, arity=2) == ("u", "v")
    # a fielded declaration still answers by name, as the class does
    both = _both(owner, "m")
    assert field_names_for(both["handle"]) == both["class"]._fields == ("A",)


def test_a_handle_naming_nothing_raises_loudly(owner):
    with pytest.raises(TypeError, match="names nothing"):
        head_cell(mint_predicate_handle(_db(owner), "no_such_pred"), 1)
    with pytest.raises(TypeError, match="not loaded"):
        head_cell(mangle("_heads5_not_loaded", "p"), 1)


def test_a_plain_str_binding_is_still_called(owner):
    """Only a mangled HANDLE takes the new arm; anything else is called as
    before and fails the way it always did."""
    with pytest.raises(TypeError, match="not callable"):
        head_cell("p", 1)
