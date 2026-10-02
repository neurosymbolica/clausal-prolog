"""File extensions the engine recognises as predicate-module source.

Two surfaces, each a tuple here, and every place that recognises a source
file by its extension consults these tuples (or ``end_module.surface_of``)
rather than spelling a suffix itself:

* ``CLAUSAL_SUFFIXES`` -- SEAM source (Python syntax), loaded by
  ``clausal.import_hook.PredicateLoader``: ``.seam`` (``SEAM_SUFFIX``).
* ``CLAUSAL_PROLOG_SUFFIXES`` -- the Clausal Prolog surface (cut-free,
  ISO-like), always loaded by the native front end: ``.clausal``.

``.pl`` is ISO Prolog source.  Until the extension flip ``.clausal`` was a
seam alias of ``.seam``; the flip moved it from ``CLAUSAL_SUFFIXES`` to
``CLAUSAL_PROLOG_SUFFIXES`` and renamed every seam file to ``.seam``.

This module has no imports on purpose: the lazy stub finder, the diagnostics
and the tools all need these names before ``clausal.import_hook`` is loaded.
"""

#: Extensions of a SEAM source file, in finder priority order (one since
#: the extension flip, so there is no same-directory tie to break).
CLAUSAL_SUFFIXES: tuple[str, ...] = (".seam",)

#: The SEAM's own extension: the one a message telling a reader where to
#: put seam code names.
SEAM_SUFFIX: str = ".seam"

#: Extension of a Prolog source file the import hook translates on load.
PROLOG_SUFFIX: str = ".pl"

#: Extensions of a CLAUSAL PROLOG source file (the cut-free ISO surface).
#: ``clausal.end_module.surface_of`` reads it, so a file here gets the
#: Clausal Prolog defaults (end_module required, cut refused, native
#: front end).
CLAUSAL_PROLOG_SUFFIXES: tuple[str, ...] = (".clausal",)

#: Every extension the import hook loads as a predicate module, in the
#: finder's order: the seam group, then the Prolog group (Clausal Prolog
#: before ``.pl``).
SOURCE_SUFFIXES: tuple[str, ...] = (*CLAUSAL_SUFFIXES,
                                    *CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX)


def prolog_suffixes() -> tuple[str, ...]:
    """The extensions of PROLOG-syntax source -- ``.pl`` and the Clausal
    Prolog surface -- in finder priority order: the Clausal Prolog suffixes
    FIRST, so ``name.clausal`` beats ``name.pl`` in one directory for every
    importer (operator ruling 2026-10-01; a ``.pl`` importer may use a
    Clausal Prolog module).  Read at each call (a function, not a constant)
    so a caller follows the tuples as they stand, including a test that
    simulates the extension flip by patching them."""
    return (*CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX)


def is_prolog_source(path) -> bool:
    """True when *path* names Prolog-syntax source (``.pl`` or the Clausal
    Prolog surface): never to be read as seam source."""
    return str(path).endswith(prolog_suffixes())


def suffix_list(suffixes) -> str:
    """``(".a", ".b", ".c")`` -> ``".a, .b or .c"``: a message's spelling of
    a suffix tuple, so prose that enumerates file kinds follows the tuples
    instead of naming one suffix and going stale at the extension flip."""
    suffixes = tuple(suffixes)
    if len(suffixes) <= 1:
        return "".join(suffixes)
    return ", ".join(suffixes[:-1]) + " or " + suffixes[-1]


def seam_suffixes_text() -> str:
    """The seam source extensions as prose, read at each call:
    ``".clausal or .seam"`` before the extension flip, ``".seam"`` after."""
    return suffix_list(CLAUSAL_SUFFIXES)


def strip_clausal_suffix(name: str) -> str:
    """Strip a SEAM suffix (one of ``CLAUSAL_SUFFIXES``): ``"m.seam"`` ->
    ``"m"``; anything else is unchanged."""
    for suffix in CLAUSAL_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name
