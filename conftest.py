"""Pytest plugin for .clausal test discovery and docs code-block testing.

Collects .clausal files and reports each test/1 clause as an individual
pytest test item:

    clausal/examples/fibonacci.clausal::fib(5) = 5

Also collects ```clausal blocks in docs/*.md files and reports each
Test/1 clause (or a compile-check for blocks without tests) as an item:

    docs/tutorial.md::L52: sum [1,2,3,4] = 10
    docs/tutorial.md::L87 [compile]
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path

import pytest

from clausal.testing import load_clausal_module, collect_tests, run_test
from clausal.tools.clear_pycache import clear_pycache

# Ensure test fixtures directory is importable (for -import_from directives
# between fixture files, e.g. expansion_importer.clausal).
_fixtures_dir = str(Path(__file__).parent / "tests" / "fixtures")
if _fixtures_dir not in sys.path:
    sys.path.insert(0, _fixtures_dir)

_docs_dir = Path(__file__).parent / "docs"

# Fenced ```clausal ... ``` blocks in markdown.
_CLAUSAL_FENCE_RE = re.compile(r"```clausal\n(.*?)```", re.DOTALL)


@pytest.fixture(autouse=True, scope="session")
def _clear_pycache_before_tests():
    """Remove all __pycache__ dirs at the start of the test session."""
    clear_pycache()


def pytest_collect_file(parent, file_path: Path):
    if file_path.suffix == ".clausal":
        return ClausalFile.from_parent(parent, path=file_path)
    if file_path.suffix == ".md":
        try:
            file_path.relative_to(_docs_dir)
            return DocMdFile.from_parent(parent, path=file_path)
        except ValueError:
            pass


# ── .clausal file collection ──────────────────────────────────────────────────


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


# ── docs/*.md code-block collection ──────────────────────────────────────────


def _extract_clausal_blocks(md_path: Path) -> list[tuple[int, str]]:
    """Return (line_number, content) pairs for each ```clausal block."""
    text = md_path.read_text()
    results = []
    for m in _CLAUSAL_FENCE_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        results.append((line_no, m.group(1)))
    return results


def _should_skip(content: str) -> bool:
    """True if the block starts with a # skip comment."""
    first_line = content.lstrip().split("\n", 1)[0].strip()
    return first_line in ("# skip", "# clausal: skip")


class DocMdFile(pytest.File):
    def collect(self):
        blocks = _extract_clausal_blocks(self.path)
        for lineno, content in blocks:
            if _should_skip(content):
                yield DocItem.from_parent(
                    self,
                    name=f"L{lineno} [skip]",
                    mod=None,
                    desc=None,
                    lineno=lineno,
                    skipped=True,
                )
                continue

            buf = io.StringIO()
            with tempfile.NamedTemporaryFile(
                suffix=".clausal",
                mode="w",
                delete=False,
            ) as f:
                f.write(content)
                tmp_path = Path(f.name)

            try:
                with contextlib.redirect_stdout(buf):
                    mod = load_clausal_module(tmp_path)
            except Exception as e:
                yield DocItem.from_parent(
                    self,
                    name=f"L{lineno} [compile error]",
                    mod=None,
                    desc=None,
                    lineno=lineno,
                    load_error=e,
                    load_output=buf.getvalue(),
                )
                continue
            finally:
                tmp_path.unlink(missing_ok=True)

            descs = collect_tests(mod)
            if descs:
                for desc in descs:
                    yield DocItem.from_parent(
                        self,
                        name=f"L{lineno}: {desc}",
                        mod=mod,
                        desc=desc,
                        lineno=lineno,
                        load_output=buf.getvalue(),
                    )
            else:
                yield DocItem.from_parent(
                    self,
                    name=f"L{lineno} [compile]",
                    mod=mod,
                    desc=None,
                    lineno=lineno,
                    load_output=buf.getvalue(),
                )


class DocItem(pytest.Item):
    def __init__(self, name, parent, mod, desc, lineno,
                 load_error=None, load_output="", skipped=False):
        super().__init__(name, parent)
        self._mod = mod
        self._desc = desc
        self._lineno = lineno
        self._load_error = load_error
        self._load_output = load_output
        self._skipped = skipped

    def runtest(self):
        if self._skipped:
            pytest.skip("marked # skip")

        if self._load_output:
            self.add_report_section("call", "stdout", self._load_output)

        if self._load_error is not None:
            raise DocTestFailure(
                f"Failed to compile block at line {self._lineno}:\n"
                f"{self._load_error}"
            ) from self._load_error

        if self._desc is None:
            # Compile-only check — loading without error is sufficient.
            return

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = run_test(self._mod, self._desc)
        output = buf.getvalue()
        if output:
            self.add_report_section("call", "stdout", output)

        if not result.passed:
            if result.error:
                raise DocTestFailure(
                    f"Test({self._desc!r}) raised: {result.error}"
                ) from result.error
            raise DocTestFailure(
                f"Test({self._desc!r}) has no solutions"
            )

    def repr_failure(self, excinfo):
        return str(excinfo.value)

    def reportinfo(self):
        return self.path, self._lineno - 1, f"L{self._lineno}"


class DocTestFailure(Exception):
    pass
