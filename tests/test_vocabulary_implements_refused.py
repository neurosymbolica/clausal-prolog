"""The "vocabulary-implements" idiom is a LOAD ERROR (operator ruling 2026-09-24).

``todo/done/vocabulary-implements-steal-has-no-row-form-2026-09-24.md``: module
A exports a predicate it only DECLARES; module B ``-import_from``'s it and
writes its clauses; importers of A's name then got B's clauses -- because
``compiler_v2`` step 4 MOVED the shared class off A's row onto B's.  After the
PredicateMeta flip the binding is a mangled atom and there is no class to
move, so the idiom would have stopped answering silently.  It is dropped: B's
load is refused at step 3d, before anything is written, with a remedy (define
it in B, export it from B, import it from B).

Pinned here:

* the refusal fires, with its message and remedy, for a declaration-only
  export AND a ``-dynamic`` one;
* in BOTH eras -- the import bound to a ``PredicateMeta`` class and to a
  mangled handle -- with the same text (the check reads rows, not classes);
* nothing is written: counted at the gate's one door, with a positive control;
* a same-spelling import at ANOTHER arity is not refused;
* the existing clobber refusal for a DEFINED export keeps its own message.
"""

from __future__ import annotations

import os
import sys
import textwrap
from types import SimpleNamespace

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle, mint
from clausal.logic.compiler_v2 import (
    _implements_an_imported_declaration, _import_from_origins,
    _refuse_foreign_writes,
)
from clausal.logic.database import Database, WRITE_LOAD_CLAUSES
from clausal.logic.predicate import PredicateMeta, is_declared_predicate
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.pythonic_ast.nodes import ImportFromDirective
from clausal.terms import Compound

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str, as_name: str | None = None):
    return _load_module(as_name or f"tests.fixtures.{stem}", _fixture_path(stem))


def _flat(exc) -> str:
    return " ".join(str(exc).split())


def _spy_load_writes(monkeypatch, marker: str) -> list:
    """Every ``load-clauses`` transaction opened by a load whose author (its
    source path) contains *marker*, counted at ``Database.mutate`` -- the one
    door every load write goes through."""
    opened: list = []
    real = Database.mutate

    def spy(self, functor, arity, *, author, kind, **kw):
        if kind == WRITE_LOAD_CLAUSES and marker in str(author):
            opened.append((functor, arity))
        return real(self, functor, arity, author=author, kind=kind, **kw)

    monkeypatch.setattr(Database, "mutate", spy)
    return opened


# ── End to end, today's era (class bindings) ─────────────────────────────────


def test_the_idiom_is_refused_at_load_with_a_remedy():
    vocab = _load_fixture("impclob_decl_vocab")
    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("impclob_implements_vocab")
    assert isinstance(vocab.impclob_verdict, PredicateMeta), (
        "this is the CLASS era; the mangled era is pinned below")
    msg = str(exc_info.value)
    first = msg.splitlines()[0]
    assert first == (
        "tests.fixtures.impclob_implements_vocab defines clauses for "
        "impclob_verdict/2, which it -import_from's from "
        "tests.fixtures.impclob_decl_vocab -- but "
        "tests.fixtures.impclob_decl_vocab only declares impclob_verdict/2; "
        "it does not define it.")
    flat = _flat(msg)
    assert "-> define impclob_verdict/2 in tests.fixtures.impclob_implements_vocab" in flat
    assert "export it from tests.fixtures.impclob_implements_vocab" in flat
    assert ("drop impclob_verdict from the "
            "-import_from(tests.fixtures.impclob_decl_vocab, [...]) list") in flat
    assert ("have the modules that use it import it from "
            "tests.fixtures.impclob_implements_vocab") in flat


def test_a_dynamic_declaration_is_refused_the_same_way():
    """``fnmismatch_schema`` declares ``fnm_verdict/2`` ``-dynamic`` with no
    clauses: a real, unowned row, not an absent one.  Still not a definition."""
    _load_fixture("fnmismatch_schema")
    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("fnmismatch_use")
    assert ("tests.fixtures.fnmismatch_schema only declares fnm_verdict/2"
            in _flat(exc_info.value))


def test_nothing_is_written_when_it_fires(monkeypatch):
    """``impclob_implements_vocab`` writes a LEGAL local predicate first, so a
    refusal fired inside the write loop would already have written it."""
    _load_fixture("impclob_decl_vocab")
    opened = _spy_load_writes(monkeypatch, "impclob_implements_vocab")
    with pytest.raises(SyntaxError):
        _load_fixture("impclob_implements_vocab")
    assert opened == [], f"the refused load wrote {opened}"


def test_positive_control_the_spy_sees_the_same_load_without_the_idiom(
        monkeypatch, tmp_path):
    source = open(_fixture_path("impclob_implements_vocab")).read()
    assert "impclob_verdict(ok, cited)," in source
    stripped = source.replace("impclob_verdict(ok, cited),\n", "")
    path = tmp_path / "impclob_iv_control.clausal"
    path.write_text(stripped)
    _load_fixture("impclob_decl_vocab")
    opened = _spy_load_writes(monkeypatch, "impclob_iv_control")
    _load_module("impclob_iv_control", str(path))
    assert ("impclob_iv_local", 1) in opened, opened


def test_the_remedy_shape_loads_and_answers():
    user = _load_fixture("impclob_verdict_user")
    x = Var()
    assert [walk(deref(x)) for _ in call(user.impclob_user_check, x)] == [
        mint("ok")]


# ── Both eras, through the real pre-pass ─────────────────────────────────────

_VOCAB = "_vocabdrop_decl_vocab"
_SCHEMA = "_vocabdrop_fnm_schema"


@pytest.fixture(scope="module")
def owners():
    """The two declaration shapes, loaded under the names their mangled
    handles carry, so an atom resolves through a real Database."""
    for name in (_VOCAB, _SCHEMA):
        sys.modules.pop(name, None)
    vocab = _load_module(_VOCAB, _fixture_path("impclob_decl_vocab"))
    schema = _load_module(_SCHEMA, _fixture_path("fnmismatch_schema"))
    yield {_VOCAB: (vocab, "impclob_verdict"), _SCHEMA: (schema, "fnm_verdict")}
    for name in (_VOCAB, _SCHEMA):
        sys.modules.pop(name, None)


def _eras(module, functor, owner_name):
    cls = module.__dict__[functor]
    assert isinstance(cls, PredicateMeta)
    return {"class": cls, "mangled": mangle(owner_name, functor)}


def _head(functor, arity):
    return SimpleNamespace(head=Compound(functor, tuple(
        f"a{i}" for i in range(arity))))


@pytest.mark.parametrize("owner_name", [_VOCAB, _SCHEMA])
@pytest.mark.parametrize("alias", [None, "local_alias"])
def test_the_pre_pass_refuses_in_both_eras_with_the_same_text(
        owners, owner_name, alias):
    module, functor = owners[owner_name]
    texts = {}
    for era, binding in _eras(module, functor, owner_name).items():
        # Population: the binding really is a predicate at /2 in this era,
        # so "no refusal" could not be a resolver answering nothing.
        assert is_declared_predicate(binding, arity=2), era
        spec = (functor, alias) if alias else functor
        local = alias or functor
        origins = _import_from_origins(
            [ImportFromDirective(module=owner_name, names=[spec])],
            {local: binding})
        assert origins[functor] == (owner_name, binding), era
        with pytest.raises(SyntaxError) as exc_info:
            _refuse_foreign_writes(
                Database(), [_head(functor, 2)], {local: binding}, origins,
                "/elsewhere/implementer.clausal", "some_implementer")
        texts[era] = str(exc_info.value)
    assert texts["class"] == texts["mangled"]
    assert f"{owner_name} only declares {functor}/2" in _flat(texts["class"])
    if alias:
        assert f"drop {functor} (imported as {alias})" in _flat(texts["class"])


@pytest.mark.parametrize("owner_name", [_VOCAB, _SCHEMA])
def test_another_arity_is_not_this_predicate_in_either_era(owners, owner_name):
    module, functor = owners[owner_name]
    for era, binding in _eras(module, functor, owner_name).items():
        origins = _import_from_origins(
            [ImportFromDirective(module=owner_name, names=[functor])],
            {functor: binding})
        # Positive control: the same origins refuse at the imported arity.
        assert _implements_an_imported_declaration(
            origins, {functor: binding}, functor, 2, "some_implementer"
        ) is not None, era
        for arity in (0, 1, 3):
            assert _implements_an_imported_declaration(
                origins, {functor: binding}, functor, arity,
                "some_implementer") is None, (era, arity)


_LOCAL = "_vocabdrop_local_def"


@pytest.fixture(scope="module")
def local_def(tmp_path_factory):
    """A module with its OWN ``impclob_verdict/2``, for the local binding."""
    path = tmp_path_factory.mktemp("vocabdrop") / "local_def.clausal"
    path.write_text(textwrap.dedent("""\
        -private([x, y])
        -module(local_def, [impclob_verdict/2])

        impclob_verdict(x, y),
        """))
    sys.modules.pop(_LOCAL, None)
    module = _load_module(_LOCAL, str(path))
    yield module
    sys.modules.pop(_LOCAL, None)


def test_a_local_predicate_under_an_aliased_imports_own_name_is_not_refused(
        owners, local_def):
    """``alias(f, G)`` leaves ``f`` free; a local ``f/2`` is this module's own
    predicate, so the canonical-name entry ``origins`` also carries must not
    refuse it.  (End to end, class era:
    ``test_a_local_definition_wins_a_clash_with_an_aliased_import``.)"""
    module, functor = owners[_VOCAB]
    imported = _eras(module, functor, _VOCAB)
    local = _eras(local_def, functor, _LOCAL)
    for era in ("class", "mangled"):
        assert is_declared_predicate(local[era], arity=2), era
        origins = _import_from_origins(
            [ImportFromDirective(module=_VOCAB, names=[(functor, "G")])],
            {"G": imported[era]})
        assert origins[functor] == (_VOCAB, imported[era]), era
        # Positive control: with the canonical name unbound, it IS refused.
        assert _implements_an_imported_declaration(
            origins, {"G": imported[era]}, functor, 2, "some_implementer"
        ) is not None, era
        assert _implements_an_imported_declaration(
            origins, {"G": imported[era], functor: local[era]}, functor, 2,
            "some_implementer") is None, era


def test_an_imported_atom_with_a_same_named_predicate_still_loads():
    """The live corpus shape (arity-0 vocabulary ATOM, arity-2 local
    predicate) is not the idiom: same name, different arity."""
    _load_fixture("impord_atomvocab")
    mod = _load_fixture("impord_atom_then_pred")
    k, v = Var(), Var()
    lm = mod.__dict__["$module"]
    assert sorted((walk(deref(k)), walk(deref(v)))
                  for _ in call("impord_qd", k, v, module=lm)) == [
        (mint("a"), 1), (mint("b"), 2)]


# ── The clobber refusal for a DEFINED export is unchanged ────────────────────


def test_a_defined_export_keeps_the_clobber_refusal_and_its_message():
    owner = _load_fixture("impclob_owner")
    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("impclob_redefine")
    msg = str(exc_info.value)
    assert msg.splitlines()[0] == (
        "tests.fixtures.impclob_redefine defines a clause for "
        "impclob_colour/1, which it -import_from's from "
        "tests.fixtures.impclob_owner.")
    assert "may not write impclob_colour/1" in msg
    assert "only declares" not in msg
    assert len(owner.impclob_colour._state_row().clauses) == 2


def test_an_import_from_the_module_itself_is_not_refused(owners):
    """The degenerate import-from-self names this module's own predicate, not
    somebody else's declaration -- the same exemption ``_belongs_elsewhere``
    makes for step 4a."""
    module, functor = owners[_VOCAB]
    for era, binding in _eras(module, functor, _VOCAB).items():
        origins = _import_from_origins(
            [ImportFromDirective(module=_VOCAB, names=[functor])],
            {functor: binding})
        assert _implements_an_imported_declaration(
            origins, {functor: binding}, functor, 2, _VOCAB) is None, era
        # Positive control: the same import into ANY other module is refused.
        assert _implements_an_imported_declaration(
            origins, {functor: binding}, functor, 2, "some_implementer"
        ) is not None, era
