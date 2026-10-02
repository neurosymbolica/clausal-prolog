"""The test suite's one spelling of the SEAM source extension.

A test that writes seam (Python-syntax) source to a file, or globs for the
seam files it wrote, names the suffix through ``SEAM`` -- never as a literal
``".clausal"``.  ``SEAM`` reads ``clausal._suffixes``, so it is ``.seam``
both today (when ``.clausal`` and ``.seam`` both mean seam) and after the
extension flip (when ``.clausal`` means Clausal Prolog and seam is ``.seam``
alone).  A test that deliberately means Clausal Prolog keeps ``.clausal``.

In-repo seam fixture files keep their names until the flip renames them;
``seam_path`` finds one by stem under whichever seam suffix it has now.
"""

import os

from clausal._suffixes import CLAUSAL_SUFFIXES, SEAM_SUFFIX

#: The seam extension: ``.seam`` before and after the flip.
SEAM = SEAM_SUFFIX
assert SEAM in CLAUSAL_SUFFIXES, (SEAM, CLAUSAL_SUFFIXES)


def seam_path(path):
    """Resolve an in-repo seam fixture named with any seam suffix.

    ``path`` is a ``str`` or ``pathlib.Path`` naming a seam file by stem,
    ending in ``.clausal`` or ``.seam`` (any other path comes back
    unchanged).  Returns the existing
    file among the stem plus each of ``CLAUSAL_SUFFIXES`` (in finder
    order), of the same type as ``path``; if none exists, the stem plus
    ``SEAM``.
    """
    s = os.fspath(path)
    for suffix in (".clausal", SEAM):
        if s.endswith(suffix):
            stem = s[: -len(suffix)]
            break
    else:
        return path             # not a seam name (a .pl, a directory): as is
    for suffix in CLAUSAL_SUFFIXES:
        if os.path.exists(stem + suffix):
            found = stem + suffix
            break
    else:
        found = stem + SEAM
    return found if isinstance(path, str) else type(path)(found)


def seam_glob(directory, pattern="*", recursive=False):
    """Glob seam files under ``directory`` (a ``pathlib.Path``) for every
    seam suffix, sorted: ``pattern`` is the stem part, e.g. ``"*"``."""
    meth = directory.rglob if recursive else directory.glob
    return sorted({p for suffix in CLAUSAL_SUFFIXES for p in meth(pattern + suffix)})
