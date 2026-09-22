"""W4b-1 fix round 1 (review): ``field_names_for``'s arm 3 used to fall
through to a ``_BUILTIN_FIELDS`` scan when nothing else answered.  A bare
string that happens to spell a registered builtin -- ``'when'``,
``'freeze'``, ``'call_nth'`` -- was therefore answered as a DECLARED
FUNCTOR (its builtin field names) rather than as the ordinary atom it is
everywhere else.  Post atoms-as-str, a bare string reaches
``field_names_for`` constantly, and this fallback crashed or silently
mis-shaped five independent call sites the moment W4b-1 Task 5 migrated
them onto the accessor -- five sites tripping on the same fallback is the
accessor's defect, not five call-site bugs.  The fallback is removed
(``clausal/logic/predicate.py``, ``_field_names_for_name``); this file pins
the corrected behaviour at the two migrated call sites that have no other
dedicated test file:

- ``_is_const_element`` (``clausal/logic/compiler/_lower_goalop_shared.py``)
- ``_cell_slot_names`` (``clausal/logic/goal_expansion.py``)

The third site, ``_construct_named`` (``functor/3``/``unpack/2``), already
has a home in ``tests/test_functor_construction_declared_term.py`` and is
pinned there instead.  ``field_names_for`` itself is re-pinned in
``tests/test_declaration_registration.py``
(``test_a_bare_name_colliding_with_a_builtin_answers_none_not_the_builtin_fields``).

Watched red first against the pre-fix accessor, reproducing exactly what
the coordinator reported:

    _is_const_element('when')             -> False   (should be True)
    _cell_slot_names('when', 2, ns)        -> ('condition', 'goal')   (should be ())
"""
from clausal.logic.compiler._lower_goalop_shared import _is_const_element
from clausal.logic.goal_expansion import _cell_slot_names
from clausal.logic.predicate import field_names_for


def test_field_names_for_does_not_answer_for_a_bare_builtin_name():
    """The root-cause pin, restated at the accessor itself: a bare name
    that collides with a registered builtin is not a declared functor."""
    assert field_names_for("when", arity=2) is None
    assert field_names_for("freeze", arity=2) is None
    assert field_names_for("call_nth", arity=2) is None
    # Control: a name that is genuinely nowhere still answers None too --
    # the fix must not turn "answers None" into something ELSE going wrong.
    assert field_names_for("not_a_builtin_or_anything_else") is None


def test_is_const_element_treats_a_builtin_shaped_atom_as_const():
    """``_is_const_element('when')`` must answer exactly like any other
    plain atom (``True`` -- a zero-arity atom is a fold-eligible constant),
    not ``False`` from a spurious ``field_names_for`` match on the builtin
    registry.  Before the fix this returned ``False``, because
    ``field_names_for('when')`` answered ``('condition', 'goal')`` (a
    non-empty, non-None tuple), so ``fields == ()`` was False and the
    function returned early instead of falling through to the atom check."""
    assert _is_const_element("when") is True
    # A genuinely ordinary atom, for comparison -- must agree.
    assert _is_const_element("foo") is True


def test_cell_slot_names_does_not_leak_builtin_fields_for_a_same_named_module_entry():
    """A module dict entry bound under a name that collides with a builtin
    (``{'when': 'when'}`` -- the auto-binding regex-group lookup's own
    shape, an atom bound to itself) must answer ``()`` -- "nothing names
    the field, so answer no names" -- never the builtin's real parameter
    names.  Before the fix this answered ``('condition', 'goal')``: the
    arity-2 ``field_names_for('when', arity=2)`` call inside
    ``_cell_slot_names`` reached the (now-removed) ``_BUILTIN_FIELDS``
    lookup, which happily matched ``when/2`` regardless of what the module
    actually declared under that name."""
    assert _cell_slot_names("when", 2, {"when": "when"}) == ()
    # A functor colliding with a builtin at the WRONG arity must still
    # answer () -- was already correct pre-fix, pinned so a future change
    # cannot reintroduce the arity-blind form of the same bug.
    assert _cell_slot_names("when", 5, {"when": "when"}) == ()
    # No module_dict at all -- must not raise, must answer ().
    assert _cell_slot_names("when", 2, None) == ()
