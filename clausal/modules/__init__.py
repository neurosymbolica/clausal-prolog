"""clausal.modules — Python library wrappers for Clausal.

Wrappers for Python stdlib and third-party packages all live in the
``py`` subpackage (``clausal.modules.py.<name>``). For example::

    -import_from(py.uuid, [UUIDv4, UUIDStr])
    -import_from(py.torch, [tensor, zeros, randn])
    -import_from(py.sympy, [Simplify, Solve])

``.clausal`` files may also use the bare names (``-import_from(torch, ...)``,
``-import_from(sympy, ...)``); the compiler rewrites these to the
canonical ``py.<name>`` paths via ``_IMPORT_ALIASES`` in
``clausal/templating/term_rewriting.py``.

Extension distributions (clausal-torch, clausal-sympy, clausal-jax,
clausal-opencv, clausal-scipy, clausal-sklearn, clausal-spacy,
clausal-yaml) install their wrappers into ``clausal/modules/py/`` via
PEP 420 namespace-package contributions; this package's ``__path__``
is extended below to discover them.

A small number of Clausal-domain modules (``graphs``, ``imperial``,
``prolog``, ``units``) live directly under ``clausal/modules/`` rather
than the ``py/`` subpackage. These are first-class Clausal predicates,
not Python-library wrappers; they keep their bare-name location.
"""

# Extend __path__ so that separately-installed wrapper distributions
# (e.g. clausal-yaml) that place files under clausal/modules/ in
# site-packages are discoverable alongside the core source tree.
import os as _os, site as _site
for _sp in _site.getsitepackages():
    _candidate = _os.path.join(_sp, "clausal", "modules")
    if _os.path.isdir(_candidate) and _candidate not in __path__:
        __path__.append(_candidate)

# Discover editable installs: setuptools' modern editable finder (verified
# against setuptools >=64) registers a class in sys.meta_path; the
# NAMESPACES dict mapping fully-qualified package names to source
# directories lives on the finder *module* (reachable via
# sys.modules[finder.__module__]). Without this, `pip install -e
# packages/clausal-X` would not contribute its `clausal/modules/<name>.py`
# to clausal.modules.__path__.
import sys as _sys
for _finder in list(_sys.meta_path):
    _finder_module = _sys.modules.get(getattr(_finder, "__module__", None) or "")
    _namespaces = getattr(_finder_module, "NAMESPACES", None)
    if not isinstance(_namespaces, dict):
        continue
    for _candidate in _namespaces.get("clausal.modules", ()):
        if _candidate and _candidate not in __path__:
            __path__.append(_candidate)
del _os, _site, _sp, _sys, _finder, _finder_module, _namespaces, _candidate

