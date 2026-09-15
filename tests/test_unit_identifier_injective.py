"""The rekey's precondition: one atom per dimension, forever.

If two distinct dimension keys ever share an identifier, rekeying ``_dims`` to
atoms SILENTLY MERGES THEM -- two different units become one, and every
dimensional check downstream is wrong without erroring anywhere. Measured
2026-09-15: 262 keys -> 262 identifiers, 0 collisions.
"""
import collections
import importlib
import pkgutil

import clausal.modules.countries as countries
from clausal.modules import units
from clausal.terms import _unit_identifier


def _all_dimension_keys():
    keys = {}

    def collect(mod):
        for name in dir(mod):
            value = getattr(mod, name, None)
            dims = getattr(value, "_dims", None)
            if isinstance(dims, dict) or type(dims).__name__ == "mappingproxy":
                for key in dims:
                    keys[id(key)] = key
            if getattr(value, "is_currency", False):
                keys[id(value)] = value

    collect(units)
    for mod_info in pkgutil.iter_modules(countries.__path__):
        if mod_info.name.startswith("_"):
            continue
        collect(importlib.import_module(f"clausal.modules.countries.{mod_info.name}"))
    return list(keys.values())


def test_unit_identifiers_are_injective():
    keys = _all_dimension_keys()
    # Positive control on the POPULATION. Without it a broken sweep that finds
    # nothing passes by measuring nothing -- the failure mode this lane has now
    # hit a dozen times.
    assert len(keys) > 200, f"only {len(keys)} dimension keys found; the sweep is broken"

    by_identifier = collections.defaultdict(list)
    for key in keys:
        by_identifier[_unit_identifier(key)].append(key)

    collisions = {
        identifier: [getattr(k, "iso_code", None) or getattr(k, "_name", "?") for k in ks]
        for identifier, ks in by_identifier.items()
        if len(ks) > 1
    }
    assert not collisions, f"dimension atoms are not unique: {collisions}"
