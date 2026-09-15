"""One atom per unit, forever.

Before the rekey this guarded the precondition: if two distinct dimension KEYS
shared an identifier, keying ``_dims`` by atoms would silently merge them --
two units becoming one, with every dimensional check downstream wrong and
nothing raising.

After the rekey the keys ARE atoms, so that form of the property holds by
construction and the risk moves up one level: two distinct unit PREDICATES
resolving to the same atom. ``_unit_registry.register`` raises on exactly that
at import time; this test is the sweep that proves the whole vocabulary clears
it, rather than only the modules some other test happened to import.
"""
import collections
import importlib
import pkgutil

import clausal.modules.countries as countries
from clausal.modules import units
from clausal.terms import _unit_identifier


def _all_unit_objects():
    """Every unit predicate and currency, across the whole vocabulary."""
    objects = {}

    def collect(mod):
        for name in dir(mod):
            value = getattr(mod, name, None)
            # A unit predicate carries its own `_dims`; a currency is one
            # too. Must be a MAPPING: `_UnitsPredicate` itself is in `dir`,
            # and its `_dims` is a slot descriptor, which is not None and not
            # iterable -- the sweep has to reject it explicitly.
            dims = getattr(value, "_dims", None)
            if isinstance(dims, dict) or type(dims).__name__ == "mappingproxy":
                objects[id(value)] = value

    collect(units)
    for mod_info in pkgutil.iter_modules(countries.__path__):
        if mod_info.name.startswith("_"):
            continue
        collect(importlib.import_module(f"clausal.modules.countries.{mod_info.name}"))
    return list(objects.values())


def test_unit_atoms_are_unique_across_the_whole_vocabulary():
    objects = _all_unit_objects()
    # Positive control on the POPULATION. Without it a broken sweep that finds
    # nothing passes by measuring nothing -- the failure mode this lane has now
    # hit a dozen times.
    assert len(objects) > 200, f"only {len(objects)} unit objects found; the sweep is broken"

    by_atom = collections.defaultdict(list)
    for obj in objects:
        by_atom[_unit_identifier(obj)].append(obj)

    collisions = {
        atom: [getattr(o, "iso_code", None) or getattr(o, "_name", "?") for o in objs]
        for atom, objs in by_atom.items()
        if len(objs) > 1
    }
    assert not collisions, f"unit atoms are not unique: {collisions}"


def test_every_dims_key_is_an_atom_that_resolves():
    """The other half: every key actually appearing in a `_dims` is a str, and
    names a unit the registry knows."""
    from clausal.modules import _unit_registry

    seen = 0
    for obj in _all_unit_objects():
        for key in obj._dims:
            seen += 1
            assert type(key) is str, f"{obj!r} has a non-atom dimension key {key!r}"
            assert _unit_registry.info(key) is not None, f"unknown unit atom {key!r}"
    assert seen > 200, f"only {seen} dimension keys inspected; the sweep is broken"
