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
* with the import bound to a mangled handle -- the only era after the
  W4b-2d flip (the ``[class]`` arm of the old both-eras parametrization is
  gone: the module dict no longer holds a class for it to take);
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
from clausal.logic.database import Database
from clausal.logic.predicate import is_declared_predicate
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, deref, walk
from clausal.pythonic_ast.nodes import ImportFromDirective
from tests.load_write_spy_support import record_load_writes
from tests._suffix import SEAM

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str, as_name: str | None = None):
    return _load_module(as_name or f"tests.fixtures.{stem}", _fixture_path(stem))


def _flat(exc) -> str:
    return " ".join(str(exc).split())


# ── End to end (handle bindings) ─────────────────────────────────────────────


def test_the_idiom_is_refused_at_load_with_a_remedy():
    vocab = _load_fixture("impclob_decl_vocab")
    with pytest.raises(SyntaxError) as exc_info:
        _load_fixture("impclob_implements_vocab")
    assert vocab.impclob_verdict == mangle(
        "tests.fixtures.impclob_decl_vocab", "impclob_verdict"), (
        "the exporter's binding is the mangled handle")
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
    writes = record_load_writes(monkeypatch)
    with pytest.raises(SyntaxError):
        _load_fixture("impclob_implements_vocab")
    assert writes.by("impclob_implements_vocab") == [], writes.opened


def test_positive_control_the_spy_sees_the_same_load_without_the_idiom(
        monkeypatch, tmp_path):
    source = open(_fixture_path("impclob_implements_vocab")).read()
    assert "impclob_verdict(ok, cited)," in source
    stripped = source.replace("impclob_verdict(ok, cited),\n", "")
    path = tmp_path / f"impclob_iv_control{SEAM}"
    path.write_text(stripped)
    _load_fixture("impclob_decl_vocab")
    writes = record_load_writes(monkeypatch)
    _load_module("impclob_iv_control", str(path))
    assert ("impclob_iv_local", 1) in writes.by("impclob_iv_control"), (
        writes.opened)


def test_the_remedy_shape_loads_and_answers():
    user = _load_fixture("impclob_verdict_user")
    x = Var()
    assert [walk(deref(x)) for _ in call(user.impclob_user_check, x)] == [
        mint("ok")]


# ── Through the real pre-pass ────────────────────────────────────────────────

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
    """The binding(s) to check.  Post-flip there is ONE era: the module dict
    binds the owner's mangled handle, which is asserted here so a binding of
    any other shape (a class era coming back, a stand-in) fails loudly
    rather than being checked as if it were the handle."""
    binding = module.__dict__[functor]
    assert binding == mangle(owner_name, functor), binding
    return {"mangled": binding}


def _head(functor, arity):
    return SimpleNamespace(head=(functor, *(
        f"a{i}" for i in range(arity))) if arity else functor)


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
                f"/elsewhere/implementer{SEAM}", "some_implementer")
        texts[era] = str(exc_info.value)
    assert list(texts) == ["mangled"]
    assert f"{owner_name} only declares {functor}/2" in _flat(texts["mangled"])
    if alias:
        assert f"drop {functor} (imported as {alias})" in _flat(texts["mangled"])


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
    path = tmp_path_factory.mktemp("vocabdrop") / f"local_def{SEAM}"
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
    for era in ("mangled",):
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
    assert len(owner.__dict__["$module"].db.row(
        "impclob_colour", 1).clauses) == 2


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


@pytest.fixture
def private_module():
    """Load a module under a PRIVATE name (the tests below mutate the owner's
    rows) -- a fixture stem, or any path via ``path=`` -- and drop every name
    it was asked for afterwards, whether the load succeeded or not."""
    loaded = []

    def load(stem: str | None, name: str, path: str | None = None):
        sys.modules.pop(name, None)
        loaded.append(name)
        return _load_module(name, path or _fixture_path(stem))

    yield load
    for name in loaded:
        sys.modules.pop(name, None)


def _importer(tmp_path, name: str, exporter: str, functor: str, fact: str):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(f"""\
        -private([ok, yes])
        -module({name}, [{name}_chk(R)])
        -import_from({exporter}, [{functor}])

        {fact},

        {name}_chk(R) <- {functor}(R, C_UNUSED)
        """))
    return str(path)


def test_a_dynamic_exporter_holding_runtime_clauses_is_refused_and_keeps_them(
        tmp_path, private_module):
    """Round-3 review: when the exporter's ``-dynamic`` row holds clauses
    asserted at RUNTIME, the gate permits the load write (rule 3: no load
    owns the row), and step 4 used to MOVE the exporter's shared class onto
    the importer's row -- the runtime clauses stayed behind and vanished
    from every caller through the class.  A load may not add clauses to
    another module's predicate: refused, with a message for THIS shape (not
    "only declares"), and nothing moved."""
    owner_name = "_vocabdrop_rt_schema"
    schema = private_module("fnmismatch_schema", owner_name)
    owner_db = schema.__dict__["$module"].db
    # A RUNTIME assert (the assertz/1 builtin, in the owner), not a load.
    assert list(call("assertz", ("fnm_verdict", mint("early"), ()),
                     module=schema.__dict__["$module"]))
    row = owner_db.row("fnm_verdict", 2)
    assert row.clauses and row.source is None, "not the shape under test"
    slm = schema.__dict__["$module"]
    x, y = Var(), Var()
    assert [walk(deref(x)) for _ in call("fnm_verdict", x, y, module=slm)] == [
        mint("early")], "the runtime clause must answer before the load, too"

    # At the check itself, through the exporter's own binding (the handle).
    texts = {}
    assert schema.fnm_verdict == mangle(owner_name, "fnm_verdict")
    for era, binding in {"mangled": schema.fnm_verdict}.items():
        origins = _import_from_origins(
            [ImportFromDirective(module=owner_name, names=["fnm_verdict"])],
            {"fnm_verdict": binding})
        assert origins["fnm_verdict"][1] is not None, era
        texts[era] = str(_implements_an_imported_declaration(
            origins, {"fnm_verdict": binding}, "fnm_verdict", 2,
            "some_implementer"))
    flat = _flat(texts["mangled"])
    assert ("whose fnm_verdict/2 is a -dynamic predicate holding 1 clause "
            "asserted at runtime") in flat
    assert "only declares" not in flat
    assert "a load cannot add clauses to another module's predicate" in (
        flat.lower())
    assert f"lands on {owner_name}'s row" in flat

    # End to end: refused, and the runtime clause still answers through the
    # exporter -- its row did not move.
    row_before = owner_db.row("fnm_verdict", 2)
    with pytest.raises(SyntaxError) as exc_info:
        private_module(None, "_vocabdrop_rt_use", path=_importer(
            tmp_path, "_vocabdrop_rt_use", owner_name, "fnm_verdict",
            "fnm_verdict(ok, [])"))
    assert "asserted at runtime" in _flat(exc_info.value)
    assert owner_db.row("fnm_verdict", 2) is row_before
    x, y = Var(), Var()
    assert [walk(deref(x)) for _ in call("fnm_verdict", x, y, module=slm)] == [
        mint("early")]


def test_an_exporter_row_a_load_wrote_and_emptied_keeps_the_clobber_message(
        tmp_path, private_module):
    """No clauses left, but a LOAD SOURCE: ``gate_alias_owner`` loads
    ``bo_p(1),`` into a ``-dynamic`` row, and the clause is retracted.  The
    gate permits the write (an owned row with nothing on it), so this is
    refused here -- with the clobber diagnostic, since the exporter did
    define the predicate."""
    owner_name = "_vocabdrop_emptied_owner"
    owner = private_module("gate_alias_owner", owner_name)
    row = owner.__dict__["$module"].db.row("bo_p", 1)
    assert row.source is not None and row.clauses, "not the shape under test"
    del row.ensure_clauses()[:]
    assert not row.clauses
    texts = {}
    assert owner.bo_p == mangle(owner_name, "bo_p")
    for era, binding in {"mangled": owner.bo_p}.items():
        origins = _import_from_origins(
            [ImportFromDirective(module=owner_name, names=["bo_p"])],
            {"bo_p": binding})
        assert origins["bo_p"][1] is not None, era
        texts[era] = _implements_an_imported_declaration(
            origins, {"bo_p": binding}, "bo_p", 1, "some_implementer")
        assert texts[era] is not None, era
    # No declaration-site line in either era (ruling B, 2026-09-24).
    assert " is declared at " not in str(texts["mangled"])
    first = str(texts["mangled"]).splitlines()[0]
    assert first == ("some_implementer defines a clause for bo_p/1, which it "
                     f"-import_from's from {owner_name}.")
    assert "only declares" not in str(texts["mangled"])
    # Through the same formatting as the gate's own clobber refusal: the
    # gate line rides at the end, naming the write and the owner.
    last = str(texts["mangled"]).splitlines()[-1].strip()
    assert last.startswith("compile_module step 4: ")
    assert "may not write bo_p/1: it is owned by " in last



def test_a_specialize_over_an_imported_mi_still_binds(monkeypatch,
                                                      private_module):
    """``-specialize`` over an imported MI installs its alias as a row of
    THIS module and answers through it; the refusal added for the steal
    must not catch it.  (It used to be pinned through a spy on the class's
    authorized ``_bind_row``; W4b-3 slice 4 installs with no class, so the
    row and the answer are what is pinned.)"""
    mod = private_module("specialize_natnum", "_vocabdrop_specialize_natnum")
    lm = mod.__dict__["$module"]
    row = lm.db.row("solve_count_natnum", 2)
    assert row is not None and row.db is lm.db and row.clauses
    n = Var()
    assert [walk(deref(n)) for _ in call(
        "solve_count_natnum", [["natnum", ["s", 0]]], n, module=lm)] == [2]


# ── An imported class at ANOTHER arity is not bound (round 5) ────────────────

_OWNERS = {
    # The exporter's p/1 is a -dynamic predicate holding only a RUNTIME clause.
    "runtime": ("-dynamic(r5p/1)\n-module({name}, [r5p/1])\n", "runtime"),
    # The exporter's p/1 is -dynamic, written by its LOAD, then emptied.
    "emptied": ("-dynamic(r5p/1)\n-module({name}, [r5p/1])\n-private([one])\n"
                "r5p(one),\n", "emptied"),
}


# B's own r5p/2, a body goal calling it, and a META-call of it (call/3).
_R5_USER_BODY = (
    "r5p(1, 2),\n\n"
    "r5chk(X, Y) <- r5p(X, Y)\n\n"
    "r5meta(X, Y) <- call(r5p, X, Y)\n")


def _assert_own_p2_answers_every_way(ulm):
    """Round-7 LOW 2: B's own ``r5p/2`` answers however it is reached -- an
    outside query (``solve`` of a goal term), ``solve.call`` by NAME in B, a
    body goal inside B, and a meta-call (``call/3``) inside B.  All four are
    UNQUALIFIED calls at an arity the name's binding (a's ``r5p/1``) is not
    at, so all four resolve in B's own row first (name+arity ruling)."""
    def answers(gen, x, y):
        return [(walk(deref(x)), walk(deref(y))) for _ in gen]

    x, y = Var(), Var()
    assert answers(solve(("r5p", x, y), ulm), x, y) == [(1, 2)], "solve"
    x, y = Var(), Var()
    assert answers(call("r5p", x, y, module=ulm), x, y) == [(1, 2)], "call"
    x, y = Var(), Var()
    assert answers(call("r5chk", x, y, module=ulm), x, y) == [(1, 2)], "body"
    # A meta-call by NAME from outside (the atom, as a handle-era term
    # would carry nothing else), in both eras.
    x, y = Var(), Var()
    assert answers(solve(("call", mint("r5p"), x, y), ulm), x, y) == [
        (1, 2)], "call/3 from a query"
    # The meta-call INSIDE B: its ``r5p`` argument was lowered when B's body
    # ran.  Pre-flip this leg was class-era only (the handle-era stand-in
    # rebound the name at step 3d, after that lowering, mixing eras); with
    # the real flip the name is a handle from the start, so it is faithful.
    x, y = Var(), Var()
    assert answers(call("r5meta", x, y, module=ulm), x, y) == [
        (1, 2)], "call/3 in a body"


def _write(tmp_path, name, text):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(text)
    return str(path)


@pytest.mark.parametrize("shape", sorted(_OWNERS))
def test_a_local_predicate_at_another_arity_than_an_imported_class_loads(
        tmp_path, monkeypatch, private_module, shape):
    """Round-5 review: B imports a's ``r5p/1`` CLASS and defines its OWN
    ``r5p/2``.  The pre-pass rightly says "not this predicate" (other arity)
    and the gate permits (a's row holds nothing a load owns), but step 4 used
    to bind a's class to B's ``r5p/2`` row -- which now raises -- and step 5
    would have installed B's dispatch on a's ``r5p/1`` row.  The head is B's
    own predicate: it loads, B's ``r5p/2`` answers, a's ``r5p/1`` is
    untouched.  Post-flip the name is bound to a's mangled handle (the old
    ``[class]`` arm, and the ``[mangled]`` arm's stand-in rebinding, are gone:
    the load binds the handle itself)."""
    import clausal.logic.compiler_v2 as cv2
    template, kind = _OWNERS[shape]
    owner_name = f"_vocabdrop_r5_owner_{shape}"
    use_name = f"_vocabdrop_r5_use_{shape}"
    owner = private_module(None, owner_name, path=_write(
        tmp_path, owner_name, template.format(name=owner_name)))
    olm = owner.__dict__["$module"]
    if kind == "runtime":
        assert list(call("assertz", ("r5p", 7), module=olm))
        expected_owner = [7]
    else:
        row = olm.db.row("r5p", 1)
        assert row.source is not None and row.clauses
        del row.ensure_clauses()[:]
        row.invalidate()
        expected_owner = []
    handle = mangle(owner_name, "r5p")
    assert owner.r5p == handle
    owner_row = olm.db.row("r5p", 1)
    assert owner_row is not None

    # Observed at step 3d: the imports are processed inside compile_module,
    # so this is the first point the module dict holds them, and everything
    # from the pre-pass on reads it.
    original = cv2._refuse_foreign_writes
    seen = []

    def refuse(db, predicate_nodes, module_dict, origins, author, module_name):
        if module_name == use_name:
            # Population: the name really is bound to a's p/1 HANDLE here --
            # the shape under test.
            seen.append(module_dict.get("r5p") == handle)
        return original(db, predicate_nodes, module_dict, origins, author,
                        module_name)

    monkeypatch.setattr(cv2, "_refuse_foreign_writes", refuse)
    use = private_module(None, use_name, path=_write(tmp_path, use_name, (
        f"-module({use_name}, [r5chk(X, Y), r5meta(X, Y)])\n"
        f"-import_from({owner_name}, [r5p])\n\n"
        + _R5_USER_BODY)))
    assert seen == [True], "the name was not bound to a's handle at step 3d"

    ulm = use.__dict__["$module"]
    _assert_own_p2_answers_every_way(ulm)
    assert ulm.db.row("r5p", 2).clauses
    # a's p/1: same row, same answers -- nothing moved, no dispatch landed.
    assert olm.db.row("r5p", 1) is owner_row
    z = Var()
    assert [walk(deref(z)) for _ in call("r5p", z, module=olm)] == expected_owner


def test_a_plain_exporter_s_loaded_clauses_do_not_stop_another_arity(
        tmp_path, monkeypatch, private_module):
    """The third exporter shape, a STATIC ``r5p/1`` with load clauses.  The
    class era used to refuse B's own ``r5p/2`` through the gate's blast radius
    (the shared class read a's owned ``r5p/1`` row); the handle era loaded it.
    Operator ruling 2026-09-24: it LOADS in both eras -- name and arity make a
    different predicate.  B's ``r5p/2`` answers, a's ``r5p/1`` is untouched."""
    import clausal.logic.compiler_v2 as cv2
    owner_name = "_vocabdrop_r5_owner_plain"
    use_name = "_vocabdrop_r5_use_plain"
    owner = private_module(None, owner_name, path=_write(
        tmp_path, owner_name,
        f"-module({owner_name}, [r5p/1])\n-private([one])\nr5p(one),\n"))
    olm = owner.__dict__["$module"]
    handle = mangle(owner_name, "r5p")
    assert owner.r5p == handle
    owner_row = olm.db.row("r5p", 1)
    assert owner_row.locked and owner_row.clauses, "not the shape under test"

    original = cv2._refuse_foreign_writes
    seen = []

    def refuse(db, predicate_nodes, module_dict, origins, author, module_name):
        if module_name == use_name:
            seen.append(module_dict.get("r5p") == handle)
        return original(db, predicate_nodes, module_dict, origins, author,
                        module_name)

    monkeypatch.setattr(cv2, "_refuse_foreign_writes", refuse)
    use = private_module(None, use_name, path=_write(tmp_path, use_name, (
        f"-module({use_name}, [r5chk(X, Y), r5meta(X, Y)])\n"
        f"-import_from({owner_name}, [r5p])\n\n"
        + _R5_USER_BODY)))
    assert seen == [True], "the name was not bound to a's handle at step 3d"
    _assert_own_p2_answers_every_way(use.__dict__["$module"])
    assert olm.db.row("r5p", 1) is owner_row
    z = Var()
    assert [walk(deref(z)) for _ in call("r5p", z, module=olm)] == [mint("one")]


def test_a_python_alias_module_re_exporting_a_clausal_predicate_is_not_python(
        tmp_path, monkeypatch, private_module):
    """Round-5 LOW: the ``clausal/modules/*.py`` pattern -- a Python module
    re-exporting a CLAUSAL predicate class.  The predicate has a real Clausal
    row (here a ``-dynamic`` row holding a runtime clause), so the message is
    the one for that row, never "created in Python module ..."."""
    owner_name = "_vocabdrop_r5_alias_owner"
    owner = private_module("fnmismatch_schema", owner_name)
    assert list(call("assertz", ("fnm_verdict", mint("early"), ()),
                     module=owner.__dict__["$module"]))
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "vocabdrop_alias_mod.py").write_text(
        f"from {owner_name} import fnm_verdict  # noqa: F401\n")
    sys.modules.pop("vocabdrop_alias_mod", None)
    try:
        with pytest.raises(SyntaxError) as exc_info:
            private_module(None, "_vocabdrop_alias_use", path=_importer(
                tmp_path, "_vocabdrop_alias_use", "vocabdrop_alias_mod",
                "fnm_verdict", "fnm_verdict(ok, [])"))
    finally:
        sys.modules.pop("vocabdrop_alias_mod", None)
    flat = _flat(exc_info.value)
    assert "created in Python module" not in flat
    assert "asserted at runtime" in flat


def test_a_python_alias_of_a_clausal_declaration_is_not_python(
        tmp_path, monkeypatch, private_module):
    """A Python module re-exporting a class a CLAUSAL module declared (a
    clause-free export: no real row yet, but the class names its Clausal
    module) gets the declaration message, not "created in Python module"."""
    owner_name = "_vocabdrop_r5_alias_decl"
    private_module("impclob_decl_vocab", owner_name)
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "vocabdrop_alias_decl.py").write_text(
        f"from {owner_name} import impclob_verdict  # noqa: F401\n")
    sys.modules.pop("vocabdrop_alias_decl", None)
    try:
        with pytest.raises(SyntaxError) as exc_info:
            private_module(None, "_vocabdrop_alias_decl_use", path=_importer(
                tmp_path, "_vocabdrop_alias_decl_use", "vocabdrop_alias_decl",
                "impclob_verdict", "impclob_verdict(ok, yes)"))
    finally:
        sys.modules.pop("vocabdrop_alias_decl", None)
    flat = _flat(exc_info.value)
    assert "created in Python module" not in flat
    assert "only declares impclob_verdict/2" in flat


def test_the_self_import_exemption_is_keyed_on_the_source_path(owners):
    """Round-6 LOW 2: the gate decides ownership by canonical SOURCE PATH
    (``write_refusal`` rule 1, "under any module name"), and so does the
    self-import exemption: one file loaded under another module name that
    imports the name from itself is not refused."""
    from clausal.logic.predicate import module_source_path
    module, functor = owners[_VOCAB]
    path = module_source_path(module)
    assert path and path.endswith("impclob_decl_vocab.clausal")
    for era, binding in _eras(module, functor, _VOCAB).items():
        origins = _import_from_origins(
            [ImportFromDirective(module=_VOCAB, names=[functor])],
            {functor: binding})
        # The same FILE under another module name: exempt.
        assert _implements_an_imported_declaration(
            origins, {functor: binding}, functor, 2,
            "_clausal_test_impclob_decl_vocab", author=path) is None, era
        # Positive control: another file under that name is refused.
        assert _implements_an_imported_declaration(
            origins, {functor: binding}, functor, 2,
            "_clausal_test_impclob_decl_vocab",
            author=f"/elsewhere/other{SEAM}") is not None, era

