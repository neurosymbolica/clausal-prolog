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
from clausal.logic.database import Database
from clausal.logic.predicate import PredicateMeta, is_declared_predicate
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, deref, walk
from clausal.pythonic_ast.nodes import ImportFromDirective
from clausal.terms import Compound
from tests.load_write_spy_support import record_load_writes

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str, as_name: str | None = None):
    return _load_module(as_name or f"tests.fixtures.{stem}", _fixture_path(stem))


def _flat(exc) -> str:
    return " ".join(str(exc).split())


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
    writes = record_load_writes(monkeypatch)
    with pytest.raises(SyntaxError):
        _load_fixture("impclob_implements_vocab")
    assert writes.by("impclob_implements_vocab") == [], writes.opened


def test_positive_control_the_spy_sees_the_same_load_without_the_idiom(
        monkeypatch, tmp_path):
    source = open(_fixture_path("impclob_implements_vocab")).read()
    assert "impclob_verdict(ok, cited)," in source
    stripped = source.replace("impclob_verdict(ok, cited),\n", "")
    path = tmp_path / "impclob_iv_control.clausal"
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
    path = tmp_path / f"{name}.clausal"
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
    assert list(call("assertz", Compound("fnm_verdict", (mint("early"), ())),
                     module=schema.__dict__["$module"]))
    row = owner_db.row("fnm_verdict", 2)
    assert row.clauses and row.source is None, "not the shape under test"
    x, y = Var(), Var()
    assert [walk(deref(x)) for _ in call(schema.fnm_verdict, x, y)] == [
        mint("early")], "the runtime clause must answer before the load, too"

    # BOTH ERAS at the check itself.
    texts = {}
    for era, binding in {"class": schema.fnm_verdict,
                         "mangled": mangle(owner_name, "fnm_verdict")}.items():
        origins = _import_from_origins(
            [ImportFromDirective(module=owner_name, names=["fnm_verdict"])],
            {"fnm_verdict": binding})
        assert origins["fnm_verdict"][1] is not None, era
        texts[era] = str(_implements_an_imported_declaration(
            origins, {"fnm_verdict": binding}, "fnm_verdict", 2,
            "some_implementer"))
    assert texts["class"] == texts["mangled"]
    flat = _flat(texts["class"])
    assert ("whose fnm_verdict/2 is a -dynamic predicate holding 1 clause "
            "asserted at runtime") in flat
    assert "only declares" not in flat
    assert "a load cannot add clauses to another module's predicate" in (
        flat.lower())
    assert f"lands on {owner_name}'s row" in flat

    # End to end: refused, and the runtime clause still answers through the
    # exporter -- the class did not move.
    cls_row_before = schema.fnm_verdict._row
    with pytest.raises(SyntaxError) as exc_info:
        private_module(None, "_vocabdrop_rt_use", path=_importer(
            tmp_path, "_vocabdrop_rt_use", owner_name, "fnm_verdict",
            "fnm_verdict(ok, [])"))
    assert "asserted at runtime" in _flat(exc_info.value)
    assert schema.fnm_verdict._row is cls_row_before
    x, y = Var(), Var()
    assert [walk(deref(x)) for _ in call(schema.fnm_verdict, x, y)] == [
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
    for era, binding in {"class": owner.bo_p,
                         "mangled": mangle(owner_name, "bo_p")}.items():
        origins = _import_from_origins(
            [ImportFromDirective(module=owner_name, names=["bo_p"])],
            {"bo_p": binding})
        assert origins["bo_p"][1] is not None, era
        texts[era] = _implements_an_imported_declaration(
            origins, {"bo_p": binding}, "bo_p", 1, "some_implementer")
        assert texts[era] is not None, era
    strip = lambda t: "\n".join(l for l in str(t).splitlines()
                                if " is declared at " not in l)
    assert strip(texts["class"]) == strip(texts["mangled"])
    first = str(texts["class"]).splitlines()[0]
    assert first == ("some_implementer defines a clause for bo_p/1, which it "
                     f"-import_from's from {owner_name}.")
    assert "only declares" not in str(texts["class"])
    # Through the same formatting as the gate's own clobber refusal: the
    # gate line rides at the end, naming the write and the owner.
    last = str(texts["class"]).splitlines()[-1].strip()
    assert last.startswith("compile_module step 4: ")
    assert "may not write bo_p/1: it is owned by " in last


def test_an_authorized_bind_never_moves_a_predicate_off_another_database():
    """The steal itself is gone: ``_bind_row(..., authorized=True)`` onto a
    class already reading ANOTHER Database's real row raises instead of
    moving it (it used to move -- the idiom's mechanism).  An unauthorized
    bind still leaves the class where it is, silently, and a first bind off
    the private detached row is still free."""
    from clausal.logic.predicate import make_predicate
    owner_db, other_db = Database(), Database()
    cls = make_predicate("vocabdrop_steal_probe", ["x"])
    assert cls._row is None or cls._row.detached
    cls._bind_row(owner_db, "vocabdrop_steal_probe", 1)       # first bind: free
    home = cls._row
    assert home is owner_db.row("vocabdrop_steal_probe", 1)

    with pytest.raises(RuntimeError, match="never changes its defining module"):
        cls._bind_row(other_db, "vocabdrop_steal_probe", 1, authorized=True)
    assert cls._row is home

    cls._bind_row(other_db, "vocabdrop_steal_probe", 1)       # policed: no-op
    assert cls._row is home


def test_a_python_module_exporting_a_predicate_class_gets_its_own_message(
        tmp_path, monkeypatch, private_module):
    """Round-4 review: a ``.clausal`` file importing a ``make_predicate``
    class from a PYTHON module and writing its clauses used to work (the
    class's first bind was off its detached row).  One defining module still
    holds -- refused -- but the message must not be ``.clausal``-shaped
    ("only declares", "-module export list"): the exporter is Python."""
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "vocabdrop_pyexp.py").write_text(textwrap.dedent("""\
        from clausal.logic.predicate import make_predicate
        vocabdrop_pyverdict = make_predicate("vocabdrop_pyverdict", ["a", "b"])
        """))
    sys.modules.pop("vocabdrop_pyexp", None)
    import vocabdrop_pyexp  # noqa: F401 -- the exporter is loaded, as in use
    try:
        assert isinstance(vocabdrop_pyexp.vocabdrop_pyverdict, PredicateMeta)
        with pytest.raises(SyntaxError) as exc_info:
            private_module(None, "_vocabdrop_py_use", path=_importer(
                tmp_path, "_vocabdrop_py_use", "vocabdrop_pyexp",
                "vocabdrop_pyverdict", "vocabdrop_pyverdict(ok, yes)"))
    finally:
        sys.modules.pop("vocabdrop_pyexp", None)
    flat = _flat(exc_info.value)
    assert ("vocabdrop_pyverdict/2 is a predicate class created in Python "
            "module vocabdrop_pyexp") in flat
    assert "or have vocabdrop_pyexp define it" in flat
    assert "only declares" not in flat
    assert "-module export list" not in flat
    assert "asserted at runtime" not in flat


def test_a_specialize_over_an_imported_mi_still_binds(monkeypatch,
                                                      private_module):
    """``-specialize`` makes its alias the compiled face of this module's row
    with an AUTHORIZED ``_bind_row``; the raise added for the steal must not
    catch it.  Population asserted: the authorized bind really ran."""
    from clausal.logic.predicate import PredicateMeta as _PM
    real = _PM.__dict__["_bind_row"]
    authorized_binds = []

    def spy(cls, db, functor, arity, authorized=False):
        if authorized and functor == "solve_count_natnum":
            authorized_binds.append((functor, arity))
        return real(cls, db, functor, arity, authorized)

    monkeypatch.setattr(_PM, "_bind_row", spy)
    mod = private_module("specialize_natnum", "_vocabdrop_specialize_natnum")
    assert authorized_binds, "the -specialize authorized bind never ran"
    lm = mod.__dict__["$module"]
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


def _assert_own_p2_answers_every_way(ulm, era="class"):
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
    if era == "class":
        # The meta-call INSIDE B: its ``r5p`` argument was lowered when B's
        # body ran, i.e. to the class today.  The handle-era leg rebinds the
        # name only at step 3d, after that lowering, so this route would mix
        # eras (a class in the term, a handle in the namespace) -- it is
        # checked in the class era, where it is faithful.
        x, y = Var(), Var()
        assert answers(call("r5meta", x, y, module=ulm), x, y) == [
            (1, 2)], "call/3 in a body"


def _write(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(text)
    return str(path)


@pytest.mark.parametrize("era", ["class", "mangled"])
@pytest.mark.parametrize("shape", sorted(_OWNERS))
def test_a_local_predicate_at_another_arity_than_an_imported_class_loads(
        tmp_path, monkeypatch, private_module, shape, era):
    """Round-5 review: B imports a's ``r5p/1`` CLASS and defines its OWN
    ``r5p/2``.  The pre-pass rightly says "not this predicate" (other arity)
    and the gate permits (a's row holds nothing a load owns), but step 4 used
    to bind a's class to B's ``r5p/2`` row -- which now raises -- and step 5
    would have installed B's dispatch on a's ``r5p/1`` row.  The head is B's
    own predicate: it loads, B's ``r5p/2`` answers, a's ``r5p/1`` is
    untouched.  In the handle era the name is bound to a's mangled handle."""
    import clausal.logic.compiler_v2 as cv2
    template, kind = _OWNERS[shape]
    owner_name = f"_vocabdrop_r5_owner_{shape}_{era}"
    use_name = f"_vocabdrop_r5_use_{shape}_{era}"
    owner = private_module(None, owner_name, path=_write(
        tmp_path, owner_name, template.format(name=owner_name)))
    olm = owner.__dict__["$module"]
    if kind == "runtime":
        assert list(call("assertz", Compound("r5p", (7,)), module=olm))
        expected_owner = [7]
    else:
        row = olm.db.row("r5p", 1)
        assert row.source is not None and row.clauses
        del row.ensure_clauses()[:]
        row.invalidate()
        expected_owner = []
    owner_row = owner.r5p._row
    assert owner_row is olm.db.row("r5p", 1)

    # Observed (and, for the handle era, rebound) at step 3d: the imports are
    # processed inside compile_module, so this is the first point the
    # module dict holds them, and everything from the pre-pass on reads it.
    original = cv2._refuse_foreign_writes
    seen = []

    def refuse(db, predicate_nodes, module_dict, origins, author, module_name):
        if module_name == use_name:
            # Population: the name really is bound to a's p/1 CLASS here --
            # the shape under test -- before any era rebinding.
            seen.append(module_dict.get("r5p") is owner.r5p)
            if era == "mangled":
                handle = mangle(owner_name, "r5p")
                module_dict["r5p"] = handle
                origins["r5p"] = (owner_name, handle)
        return original(db, predicate_nodes, module_dict, origins, author,
                        module_name)

    monkeypatch.setattr(cv2, "_refuse_foreign_writes", refuse)
    use = private_module(None, use_name, path=_write(tmp_path, use_name, (
        f"-module({use_name}, [r5chk(X, Y), r5meta(X, Y)])\n"
        f"-import_from({owner_name}, [r5p])\n\n"
        + _R5_USER_BODY)))
    assert seen == [True], "the name was not bound to a's class at step 4"

    ulm = use.__dict__["$module"]
    _assert_own_p2_answers_every_way(ulm, era)
    assert ulm.db.row("r5p", 2).clauses
    # a's p/1: same row, same answers -- nothing moved, no dispatch landed.
    assert owner.r5p._row is owner_row
    z = Var()
    assert [walk(deref(z)) for _ in call(owner.r5p, z)] == expected_owner


@pytest.mark.parametrize("era", ["class", "mangled"])
def test_a_plain_exporter_s_loaded_clauses_do_not_stop_another_arity(
        tmp_path, monkeypatch, private_module, era):
    """The third exporter shape, a STATIC ``r5p/1`` with load clauses.  The
    class era used to refuse B's own ``r5p/2`` through the gate's blast radius
    (the shared class read a's owned ``r5p/1`` row); the handle era loaded it.
    Operator ruling 2026-09-24: it LOADS in both eras -- name and arity make a
    different predicate.  B's ``r5p/2`` answers, a's ``r5p/1`` is untouched."""
    import clausal.logic.compiler_v2 as cv2
    owner_name = f"_vocabdrop_r5_owner_plain_{era}"
    use_name = f"_vocabdrop_r5_use_plain_{era}"
    owner = private_module(None, owner_name, path=_write(
        tmp_path, owner_name,
        f"-module({owner_name}, [r5p/1])\n-private([one])\nr5p(one),\n"))
    owner_row = owner.r5p._row
    assert owner_row.locked and owner_row.clauses, "not the shape under test"

    original = cv2._refuse_foreign_writes
    seen = []

    def refuse(db, predicate_nodes, module_dict, origins, author, module_name):
        if module_name == use_name:
            seen.append(module_dict.get("r5p") is owner.r5p)
            if era == "mangled":
                handle = mangle(owner_name, "r5p")
                module_dict["r5p"] = handle
                origins["r5p"] = (owner_name, handle)
        return original(db, predicate_nodes, module_dict, origins, author,
                        module_name)

    monkeypatch.setattr(cv2, "_refuse_foreign_writes", refuse)
    use = private_module(None, use_name, path=_write(tmp_path, use_name, (
        f"-module({use_name}, [r5chk(X, Y), r5meta(X, Y)])\n"
        f"-import_from({owner_name}, [r5p])\n\n"
        + _R5_USER_BODY)))
    assert seen == [True], "the name was not bound to a's class at step 3d"
    _assert_own_p2_answers_every_way(use.__dict__["$module"], era)
    assert owner.r5p._row is owner_row
    z = Var()
    assert [walk(deref(z)) for _ in call(owner.r5p, z)] == [mint("one")]


def test_a_python_alias_module_re_exporting_a_clausal_predicate_is_not_python(
        tmp_path, monkeypatch, private_module):
    """Round-5 LOW: the ``clausal/modules/*.py`` pattern -- a Python module
    re-exporting a CLAUSAL predicate class.  The predicate has a real Clausal
    row (here a ``-dynamic`` row holding a runtime clause), so the message is
    the one for that row, never "created in Python module ..."."""
    owner_name = "_vocabdrop_r5_alias_owner"
    owner = private_module("fnmismatch_schema", owner_name)
    assert list(call("assertz", Compound("fnm_verdict", (mint("early"), ())),
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


def test_a_python_made_class_on_a_real_clausal_row_is_not_python(
        monkeypatch, private_module):
    """The row decides first: a class made in Python (``make_predicate``,
    whose ``__module__`` is not a Clausal module) that is BOUND to a real
    Clausal row is a Clausal predicate, however it is re-exported."""
    from clausal.logic.predicate import make_predicate
    owner = private_module("impclob_decl_vocab", "_vocabdrop_r5_real_row")
    owner_db = owner.__dict__["$module"].db
    cls = make_predicate("vocabdrop_mp", ["a", "b"])
    cls._bind_row(owner_db, "vocabdrop_mp", 2)
    assert not cls._row.detached and not cls._row.clauses
    assert cls._row.source is None
    fake = type(sys)("vocabdrop_py_reexporter")
    fake.vocabdrop_mp = cls
    monkeypatch.setitem(sys.modules, "vocabdrop_py_reexporter", fake)
    origins = _import_from_origins(
        [ImportFromDirective(module="vocabdrop_py_reexporter",
                             names=["vocabdrop_mp"])],
        {"vocabdrop_mp": cls})
    text = _flat(_implements_an_imported_declaration(
        origins, {"vocabdrop_mp": cls}, "vocabdrop_mp", 2, "some_implementer"))
    assert "created in Python module" not in text
    assert "only declares vocabdrop_mp/2" in text


def test_a_python_made_class_with_clauses_on_its_detached_row_is_python(
        monkeypatch):
    """Round-6 LOW 1: a class made in Python holding clauses on its PRIVATE
    detached row has no Clausal row at all -- the detached row is checked
    first, so it gets the Python message, not "a -dynamic predicate holding
    runtime clauses" (there is no exporter row to hold them)."""
    from clausal.logic.database import Clause
    from clausal.logic.predicate import make_predicate
    cls = make_predicate("vocabdrop_detached", ["a"])
    cls._assertz(Clause(head=Compound("vocabdrop_detached", (1,)), body=[]))
    assert cls._row.detached and cls._row.clauses, "not the shape under test"
    fake = type(sys)("vocabdrop_py_detached")
    fake.vocabdrop_detached = cls
    monkeypatch.setitem(sys.modules, "vocabdrop_py_detached", fake)
    origins = _import_from_origins(
        [ImportFromDirective(module="vocabdrop_py_detached",
                             names=["vocabdrop_detached"])],
        {"vocabdrop_detached": cls})
    text = _flat(_implements_an_imported_declaration(
        origins, {"vocabdrop_detached": cls}, "vocabdrop_detached", 1,
        "some_implementer"))
    assert ("vocabdrop_detached/1 is a predicate class created in Python "
            "module vocabdrop_py_detached") in text
    assert "asserted at runtime" not in text


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
            author="/elsewhere/other.clausal") is not None, era


def test_the_other_arity_test_reads_the_bound_rows_arity_not_the_fields():
    """Round-6 LOW 3: a class can be bound at an arity its ``_fields`` do not
    spell (a name at two arities re-binds it within its database).  The
    bound ROW's key is the arity that counts."""
    from clausal.logic.predicate import (
        is_foreign_class_at_other_arity, make_predicate,
    )
    owner_db, other_db = Database(), Database()
    cls = make_predicate("vocabdrop_two_arities", ["a"])
    cls._bind_row(owner_db, "vocabdrop_two_arities", 1)
    cls._bind_row(owner_db, "vocabdrop_two_arities", 3)     # same db: moves
    assert cls._row.key == ("vocabdrop_two_arities", 3)
    assert len(cls._fields) == 1
    assert is_foreign_class_at_other_arity(cls, other_db, 3) is False
    assert is_foreign_class_at_other_arity(cls, other_db, 1) is True
    # Its own database is never "foreign"; an unbound class never is either.
    assert is_foreign_class_at_other_arity(cls, owner_db, 1) is False
    assert is_foreign_class_at_other_arity(
        make_predicate("vocabdrop_unbound", ["a"]), other_db, 2) is False


@pytest.mark.parametrize("b_arity", [1, 2])
def test_a_class_whose_fields_and_row_disagree_never_hits_the_internal_raise(
        tmp_path, private_module, b_arity):
    """Round-7 LOW 1: one arity source.  a exports ``r7q/1`` (a load clause),
    and a's class -- minted with ONE field -- is then re-bound within a's own
    database to a's ``r7q/2`` row.  Before, the pre-pass read ``_fields`` (1)
    and step 4 read the row (2), so B writing ``r7q/2`` slipped past every
    refusal into step 4's authorized bind and the INTERNAL ``RuntimeError``.
    Now both read the row, and B's load ends in a user-facing load error at
    either arity, with nothing of a's moved:

    * ``r7q/2`` -- the class's row: the imported predicate, clause-free and
      never loaded, so the drop-the-idiom refusal;
    * ``r7q/1`` -- a's EXPORTED, adopted, load-owned row: the clobber
      refusal (it is the imported predicate at that arity)."""
    owner_name = f"_vocabdrop_r7_owner_{b_arity}"
    use_name = f"_vocabdrop_r7_use_{b_arity}"
    owner = private_module(None, owner_name, path=_write(
        tmp_path, owner_name,
        f"-module({owner_name}, [r7q/1])\n-private([one])\nr7q(one),\n"))
    olm = owner.__dict__["$module"]
    cls = owner.r7q
    cls._bind_row(olm.db, "r7q", 2)                 # same db: allowed
    # The move carries ``locked``/``source`` over; clear them so a's r7q/2 is
    # a clause-free row no load owns -- the shape the gate PERMITS, which is
    # what used to reach step 4's bind.
    cls._row.locked = False
    cls._row.source = None
    assert len(cls._fields) == 1 and cls._row.key == ("r7q", 2)
    assert cls._row.db is olm.db and not cls._row.clauses
    fact = "r7q(5, 6)," if b_arity == 2 else "r7q(5),"
    path = _write(tmp_path, use_name, (
        f"-module({use_name}, [])\n"
        f"-import_from({owner_name}, [r7q])\n\n{fact}\n"))
    with pytest.raises(SyntaxError) as exc_info:     # never RuntimeError
        private_module(None, use_name, path=path)
    text = _flat(exc_info.value)
    if b_arity == 2:
        assert f"{owner_name} only declares r7q/2" in text
    else:
        assert "may not write r7q/1" in text
    assert cls._row.key == ("r7q", 2) and cls._row.db is olm.db
    assert not cls._row.clauses
    assert len(olm.db.row("r7q", 1).clauses) == 1
