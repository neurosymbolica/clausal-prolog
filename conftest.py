"""Pytest plugin for .clausal test discovery.

Collects .clausal files and reports each test/1 clause as an individual
pytest test item. Tests appear as:

    clausal/examples/fibonacci.clausal::fib(5) = 5
"""

from __future__ import annotations

import sys
import pytest
from pathlib import Path

from clausal.testing import load_clausal_module, collect_tests, run_test

# Ensure test fixtures directory is importable (for -import_from directives
# between fixture files, e.g. expansion_importer.clausal).
_fixtures_dir = str(Path(__file__).parent / "tests" / "fixtures")
if _fixtures_dir not in sys.path:
    sys.path.insert(0, _fixtures_dir)


def pytest_collect_file(parent, file_path: Path):
    if file_path.suffix == ".clausal":
        return ClausalFile.from_parent(parent, path=file_path)


class ClausalFile(pytest.File):
    def collect(self):
        try:
            mod = load_clausal_module(self.path)
        except Exception as e:
            # Yield a single error item so the file appears as a failure
            # rather than crashing collection.
            yield ClausalItem.from_parent(
                self, name="<load>", mod=None, load_error=e
            )
            return
        self._mod = mod
        for desc in collect_tests(mod):
            yield ClausalItem.from_parent(self, name=desc, mod=mod)


class ClausalItem(pytest.Item):
    def __init__(self, name, parent, mod, load_error=None):
        super().__init__(name, parent)
        self._mod = mod
        self._load_error = load_error

    def runtest(self):
        if self._load_error is not None:
            raise ClausalTestFailure(
                f"Failed to load {self.path}: {self._load_error}"
            ) from self._load_error
        result = run_test(self._mod, self.name)
        if not result.passed:
            if result.error:
                raise ClausalTestFailure(
                    f"test({self.name!r}) raised: {result.error}"
                ) from result.error
            raise ClausalTestFailure(f"test({self.name!r}) failed (no solutions)")

    def repr_failure(self, excinfo):
        return str(excinfo.value)

    def reportinfo(self):
        return self.path, None, f"test({self.name!r})"


class ClausalTestFailure(Exception):
    pass
