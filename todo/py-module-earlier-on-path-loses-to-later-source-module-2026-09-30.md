# A `.py` module earlier on sys.path loses to a `.clausal`/`.seam`/`.pl` module later

Found while fixing per-entry precedence between `.clausal`/`.seam` and `.pl`
(branch fix/finder-precedence-per-path-entry-2026-09-30).

`sys.meta_path` is `[PredicateFinder, ModulesFinder, ..., PathFinder, ...]`.
PredicateFinder walks the whole path before PathFinder is asked, so with
`PYTHONPATH=C:B`, `C/pkg/__init__.py` and `B/pkg/__init__.clausal`,
`find_spec("pkg")` is B's `.clausal`. Python's contract says C's `.py` wins.
Pinned as-is by
`tests/test_finder_precedence_per_path_entry.py::test_py_package_earlier_still_loses_to_clausal_later`.

Design question (not decided): should PredicateFinder, per entry, defer when
that entry holds a Python module/package (e.g. ask
`importlib.machinery.FileFinder`/`PathFinder.find_spec(name, [entry])` for a
non-namespace spec) before moving to the next entry? Same-directory
`.clausal` over `.py` would stay. Risk: any tree that relies on a later
`.clausal` overriding an earlier `.py` of the same name (sys.path[0] = the
script or cwd is the usual earlier entry). Needs a census of such pairs
before changing.
