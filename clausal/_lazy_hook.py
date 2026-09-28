"""Lightweight stub that defers the real import hook until first use."""
from importlib.abc import MetaPathFinder
import importlib.util
import os
import sys
import threading

from clausal._suffixes import SOURCE_SUFFIXES


class _LazyHookFinder(MetaPathFinder):
    """Sits on sys.meta_path; replaces itself with the real finders on first hit."""

    _installing = False

    # Names whose Condition-2 probe is currently in flight on this thread.
    #
    # ``importlib.util.find_spec("clausal.modules.<name>")`` imports the parent
    # packages of that dotted name in order to read their ``__path__``.  When
    # ``clausal`` itself is absent from ``sys.modules`` — e.g. a test cleared it,
    # or an ``import clausal`` failed after this stub was installed — that parent
    # import comes straight back through ``sys.meta_path`` as the *bare* name
    # ``clausal``, which re-enters Condition 2 and probes
    # ``clausal.modules.clausal``, which imports ``clausal`` again … until
    # ``RecursionError`` takes the whole process down.  Declining a name we are
    # already probing breaks the cycle: returning None only says "not mine", so
    # the remaining finders still resolve it (or raise the normal
    # ``ModuleNotFoundError``).
    #
    # Mirrors ``ModulesFinder._resolving`` in clausal/import_hook.py, but kept
    # per-thread so a concurrent importer of the same name is not wrongly
    # declined a spec it is entitled to.
    _probing = threading.local()

    def _in_flight(self) -> set[str]:
        names = getattr(self._probing, "names", None)
        if names is None:
            names = self._probing.names = set()
        return names

    def find_spec(self, fullname, path, target=None):
        if self._installing:
            return None

        # Condition 1: py.X redirect (e.g. "py.re" -> clausal.modules.py.re)
        if fullname.startswith("py.") and "." not in fullname[3:]:
            return self._activate_and_retry(fullname, path, target)

        # Condition 2: bare top-level name that might be in clausal.modules
        if "." not in fullname:
            in_flight = self._in_flight()
            if fullname in in_flight:
                return None
            qualified = f"clausal.modules.{fullname}"
            in_flight.add(fullname)
            try:
                found = importlib.util.find_spec(qualified) is not None
            except (ModuleNotFoundError, ValueError):
                found = False
            finally:
                in_flight.discard(fullname)
            if found:
                return self._activate_and_retry(fullname, path, target)

        # Condition 3: .clausal (or .seam), or .pl, file on sys.path -- or a
        # package directory whose ``__init__`` is one (``tail/__init__.clausal``).
        # Without the package form, PathFinder claimed such a directory as a
        # PEP 420 namespace package when it was imported before
        # ``clausal.import_hook`` had loaded: no ``__init__`` ran, so no
        # ``__clausal_module__`` and no ``-import_from`` of its siblings.
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        for d in search_dirs:
            if not isinstance(d, str):
                continue
            if any(os.path.isfile(os.path.join(d, tail + suffix))
                   for suffix in SOURCE_SUFFIXES):
                return self._activate_and_retry(fullname, path, target)
            pkg_dir = os.path.join(d, tail)
            if os.path.isdir(pkg_dir) and any(
                    os.path.isfile(os.path.join(pkg_dir, "__init__" + suffix))
                    for suffix in SOURCE_SUFFIXES):
                return self._activate_and_retry(fullname, path, target)

        return None

    def _activate_and_retry(self, fullname, path, target):
        if self._installing:
            return None
        self._installing = True
        try:
            import clausal.import_hook  # noqa: F401 -- registers real finders
            # Remove ourselves from sys.meta_path
            sys.meta_path[:] = [f for f in sys.meta_path if f is not self]
        finally:
            self._installing = False
        # Re-dispatch through the now-installed real finders
        return importlib.util.find_spec(fullname)


def _install_finder():
    """Install the stub at most once per process.

    A ``sys.modules`` sweep of ``clausal*`` makes the next ``import clausal``
    re-execute this module with a *fresh* class object while the previous
    stub instance — of the now-orphaned previous class — is still on
    ``sys.meta_path``, so an unconditional insert accumulates one stub per
    sweep.  Duplicates never cycle (each stub's in-flight guard declines its
    own second entry) but every extra stub adds one nested Condition-2 probe
    layer to every failing bare import, so unbounded accumulation still
    converges on ``RecursionError``.

    Reuse is matched by exact class identity, then by module + qualname for
    the re-executed-module case; a subclass carries its own qualname, so it
    is never silently reused.
    """
    for finder in sys.meta_path:
        cls = type(finder)
        if cls is _LazyHookFinder or (
                cls.__module__ == __name__
                and cls.__qualname__ == _LazyHookFinder.__qualname__):
            return finder
    finder = _LazyHookFinder()
    sys.meta_path.insert(0, finder)
    return finder


_install_finder()
