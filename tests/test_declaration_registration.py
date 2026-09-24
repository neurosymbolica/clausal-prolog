"""W4b-1: every engine minter's declaration reaches a registry, so
``field_names_for`` can answer from a NAME after W4b-2 takes the class away.

Three gaps are closed here.  The two routes that were ALREADY covered are
pinned too, so a later change that removes the coverage fails here rather
than silently leaving a name unanswerable."""
from clausal.logic.database import Database
from clausal.logic.predicate import field_names_for


def _specialize_items_fixture(module_dict):
    """One ``SpecializeItem`` naming a real, already-compiled MI class.

    ``analyze_mi`` needs clauses shaped like a genuine meta-interpreter
    (base + recursive, ``match_clause``, a recursive self-call) -- hand
    assembling that shape would just re-implement
    ``clausal.examples.metainterpreters``.  Reusing ``solve_count`` from
    there is the smallest fixture that actually satisfies ``analyze_mi``,
    and it is the same class ``tests/fixtures/specialize_natnum.clausal``
    specializes end-to-end in ``test_specialization_pipeline.py``.
    """
    import clausal.examples.metainterpreters as mi_mod
    from clausal.pythonic_ast.nodes import SpecializeDirective as SpecializeItem

    module_dict["solve_count"] = mi_mod.solve_count
    return [
        SpecializeItem(
            mi_name="solve_count",
            source_program="natnum_program",
            new_name="solve_count_preregistered",
        )
    ]


def _expected_specializations(items, module_dict):
    """(new_name, fields) pairs the fixture's items ought to register."""
    from clausal.logic.specialization import analyze_mi, _specialized_fields

    out = []
    for item in items:
        mi_cls = module_dict[item.mi_name]
        pattern = analyze_mi(mi_cls)
        fields = tuple(_specialized_fields(pattern))
        out.append((item.new_name, fields))
    return out


def test_preregistered_specialization_is_registered(tmp_path):
    from clausal.logic.compiler_v2 import _preregister_specializations
    from clausal.logic.specialization import _specialized_fields  # noqa: F401
    db = Database()
    module_dict = {}
    items = _specialize_items_fixture(module_dict)
    _preregister_specializations(items, module_dict, db)
    for name, fields in _expected_specializations(items, module_dict):
        assert db.signature_for(name, len(fields)) == fields, name


def test_term_expansion_class_is_registered():
    """term_expansion/4 is minted into a synthetic LogicModule; its own db
    must know the declaration."""
    from clausal.logic.term_expansion import _term_expansion_module
    lm = _term_expansion_module({})
    assert lm.db.signature_for("term_expansion", 4) == (
        "term", "expansion", "module_before", "module_after")


def test_specialize_route_still_registers_through_register_signature():
    """ALREADY COVERED (specialization.py:388) -- pinned by driving the REAL
    route, not a hand-built stand-in.

    A hand call to ``db.register_signature(...)`` only proves
    ``database.py``'s own plumbing works -- nobody is changing that.  This
    drives ``specialize_mi`` (the public entry point, called by
    ``compiler_v2`` at Step 5) through to ``_install_specialized``, which is
    the actual site that writes ``db.register_signature(new_name, arity,
    tuple(fields))`` at specialization.py:388.  Fix round 1: verified by
    temporarily commenting out that line -- this test went red; restoring
    it, green again (see task-2-report.md)."""
    from clausal.logic.database import Module
    from clausal.logic.specialization import analyze_mi, specialize_mi
    from clausal.logic.variables import Var
    import clausal.examples.metainterpreters as mi_mod

    x = Var()
    natnum_program = [
        [["natnum", 0], []],
        [["natnum", ["s", x]], [["natnum", x]]],
    ]
    module = Module("t_pin_register_signature",
                    module_dict={"__name__": "t_pin_register_signature"})
    db = module.db
    pattern = analyze_mi(mi_mod.solve)
    # solve/2 specialized drops PROGRAM and keeps GOALS.  A literal, not the
    # implementation's own _specialized_fields, so the pin cannot agree with
    # the code by construction.
    fields = ("GOALS",)
    result = specialize_mi(
        pattern, natnum_program, "solve_pin_natnum", db=db,
    )
    assert db.row("solve_pin_natnum", len(fields)) is not None
    assert result._row is db.row("solve_pin_natnum", len(fields))
    assert db.signature_for("solve_pin_natnum", len(fields)) == fields
    assert field_names_for("solve_pin_natnum", arity=len(fields),
                            db=db) == fields


def test_a_bare_name_colliding_with_a_builtin_answers_none_not_the_builtin_fields():
    """W4b-1 fix round 1 (review): pins the OPPOSITE of what this test used
    to assert.  The retired version (``test_builtins_answer_from_the_
    builtin_registry_with_no_db``) pinned a ``_BUILTIN_FIELDS`` fallback in
    ``_field_names_for_name`` -- arm 3 answering a builtin's fields for its
    bare name with no db/namespace at all.  That fallback had zero
    production callers and a real defect: post atoms-as-str, a bare string
    reaches ``field_names_for`` constantly, and any string that happens to
    spell a registered builtin (``'when'``, ``'freeze'``, ``'call_nth'``)
    was answered as though it were a DECLARED FUNCTOR rather than an
    ordinary atom -- confirmed to crash or silently mis-shape five
    independent call sites the moment W4b-1 Task 5 migrated them onto this
    accessor.  The fallback is removed; this test pins that a bare name
    colliding with a builtin now answers ``None``, the same answer any
    other undeclared atom gets."""
    from clausal.logic.builtins import _BUILTIN_FIELDS
    (functor, arity), fields = next(iter(_BUILTIN_FIELDS.items()))
    assert field_names_for(functor, arity=arity) is None
    assert field_names_for(functor, arity=arity) != fields
    # The specific case the coordinator reproduced: 'when' must not answer
    # the builtin registry's ('condition', 'goal').
    assert field_names_for("when", arity=2) is None
    assert field_names_for("when", arity=2) != ("condition", "goal")
