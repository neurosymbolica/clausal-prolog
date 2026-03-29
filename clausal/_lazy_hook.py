"""Lightweight stub that defers the real import hook until first use."""
from importlib.abc import MetaPathFinder
import importlib.util
import os
import sys


class _LazyHookFinder(MetaPathFinder):
    """Sits on sys.meta_path; replaces itself with the real finders on first hit."""

    _installing = False

    def find_spec(self, fullname, path, target=None):
        if self._installing:
            return None

        # Condition 1: py.X redirect (e.g. "py.re" -> clausal.modules.py.re)
        if fullname.startswith("py.") and "." not in fullname[3:]:
            return self._activate_and_retry(fullname, path, target)

        # Condition 2: bare top-level name that might be in clausal.modules
        if "." not in fullname:
            qualified = f"clausal.modules.{fullname}"
            try:
                if importlib.util.find_spec(qualified) is not None:
                    return self._activate_and_retry(fullname, path, target)
            except (ModuleNotFoundError, ValueError):
                pass

        # Condition 3: .clausal or .pl file on sys.path
        tail = fullname.rsplit(".", 1)[-1]
        search_dirs = path if path else sys.path
        for d in search_dirs:
            if (os.path.isfile(os.path.join(d, tail + ".clausal"))
                    or os.path.isfile(os.path.join(d, tail + ".pl"))):
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


sys.meta_path.insert(0, _LazyHookFinder())
