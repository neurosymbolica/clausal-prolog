"""File extensions the engine recognises as predicate-module source.

``.clausal`` and ``.seam`` are aliases for one another: both carry the same
Python-seam syntax and go through the same loader, so every place that
recognises a predicate module by its extension consults these tuples rather
than spelling ``".clausal"`` itself.  ``.pl`` is Prolog source, translated on
the way in (see ``clausal.import_hook.PrologLoader``).

This module has no imports on purpose: the lazy stub finder, the diagnostics
and the tools all need these names before ``clausal.import_hook`` is loaded.
"""

#: Extensions of a Clausal predicate-module source file, in finder priority
#: order.  Order matters where two files share a stem in one directory.
CLAUSAL_SUFFIXES: tuple[str, ...] = (".clausal", ".seam")

#: Extension of a Prolog source file the import hook translates on load.
PROLOG_SUFFIX: str = ".pl"

#: Every extension the import hook loads as a predicate module.
SOURCE_SUFFIXES: tuple[str, ...] = (*CLAUSAL_SUFFIXES, PROLOG_SUFFIX)


def strip_clausal_suffix(name: str) -> str:
    """``"m.clausal"`` / ``"m.seam"`` → ``"m"``; anything else is unchanged."""
    for suffix in CLAUSAL_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name
