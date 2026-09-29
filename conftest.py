"""Pytest plugin for .clausal test discovery and docs code-block testing.

Collects .clausal files (and their ``.seam`` alias), and Prolog ``.pl`` files
through the experimental Prolog importer, and reports each test/1 clause as an
individual pytest test item (a file that fails to load or translate is one
failing ``<load>`` item):

    clausal/examples/fibonacci.clausal::fib(5) = 5

Also collects ```clausal blocks in docs/*.md files and reports each
test/1 clause (or a compile-check for blocks without tests) as an item:

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

from clausal._suffixes import SOURCE_SUFFIXES
from clausal.testing import (
    TestCollectionError,
    collect_tests,
    load_clausal_module,
    opts_out_of_collection,
    run_test,
)
from clausal.tools.clear_pycache import clear_pycache

# Ensure test fixtures directory is importable (for -import_from directives
# between fixture files, e.g. expansion_importer.clausal).
_fixtures_dir = str(Path(__file__).parent / "tests" / "fixtures")
if _fixtures_dir not in sys.path:
    sys.path.insert(0, _fixtures_dir)

_docs_dir = Path(__file__).parent / "docs"

# Prolog source shipped as package DATA, not tests: the toklex grammar specs
# and the export preludes.  The plugin collects .pl files, and these do not go
# through the .pl importer (they are read by their own tools), so collecting
# them would report translator errors about files nobody imports.  Each file
# also carries the ``% clausal: no-collect`` marker, which is what keeps the
# CLI runner off them when it scans ``clausal/`` (this conftest is above that
# scan root, so its list does not apply there).
collect_ignore_glob = [
    "clausal/tools/toklex/specs/*.pl",
    "clausal/tools/prolog_preludes/*.pl",
]

# Fenced ```clausal ... ``` blocks in markdown.
_CLAUSAL_FENCE_RE = re.compile(r"```clausal\n(.*?)```", re.DOTALL)

# Session-scoped home for doc-block compile buffers.  The blocks used to be
# NamedTemporaryFiles unlinked at collection time, which is why a failing doc
# block could only report a bare "no solutions": ``diagnose_failure`` takes
# ``path`` to reify the source, quote the failing conjunct and name its
# variables, and by item runtime there was no path left to pass.  Keeping the
# files for the session buys the full diagnosis; ``pytest_sessionfinish``
# removes the directory.  (A run with more than 16 *failing* blocks will
# thrash the 16-entry ``_REIFY_CACHE`` — an efficiency note only, and only on
# the failure path.)
_doc_block_dir: Path | None = None


def _doc_block_home() -> Path:
    global _doc_block_dir
    if _doc_block_dir is None:
        _doc_block_dir = Path(tempfile.mkdtemp(prefix="clausal-doc-blocks-"))
    return _doc_block_dir


def pytest_sessionfinish(session, exitstatus):
    global _doc_block_dir
    if _doc_block_dir is not None:
        import shutil

        shutil.rmtree(_doc_block_dir, ignore_errors=True)
        _doc_block_dir = None


@pytest.fixture(autouse=True, scope="session")
def _clear_pycache_before_tests():
    """Remove all __pycache__ dirs at the start of the test session."""
    clear_pycache()


# A fixture opts out of automatic collection with the no-collect marker —
# for files that are *meant* to fail at load (diagnostic regression fixtures).
# The marker and its check live in clausal.testing so the CLI runner honours
# the same opt-out (see clausal.testing.opts_out_of_collection).
_opts_out_of_collection = opts_out_of_collection


def pytest_collect_file(parent, file_path: Path):
    if file_path.suffix in SOURCE_SUFFIXES:
        if _opts_out_of_collection(file_path):
            return None
        return ClausalFile.from_parent(parent, path=file_path)
    if file_path.suffix == ".md":
        try:
            file_path.relative_to(_docs_dir)
            return DocMdFile.from_parent(parent, path=file_path)
        except ValueError:
            pass


# ── .clausal / .seam / .pl file collection ───────────────────────────────────


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
        try:
            descs = collect_tests(mod)
        except TestCollectionError as e:
            # An unsupported test(Name, Option): the whole file is refused,
            # as for a load error, never a silently skipped clause.
            yield ClausalItem.from_parent(
                self, name="<collect>", mod=None, load_error=e
            )
            return
        for desc in descs:
            yield ClausalItem.from_parent(self, name=desc, mod=mod)


def _with_diagnosis(message: str, result) -> str:
    """Attach a goal-level diagnosis under a plugin failure *message*.

    Appended, never substituted: the headline is what names the test in a CI
    log and in ``-q`` summary lines, so it has to survive verbatim; the
    diagnosis is detail underneath it, indented the same way the CLI report
    indents it (``clausal.testing._failure_lines``) so both readers see one
    format.  A diagnostic that could attribute nothing renders no lines at
    all, and an empty block under a headline reads as a broken report — so in
    that case the message is left exactly as it was.
    """
    lines = result.diagnostic.lines() if result.diagnostic is not None else []
    return "\n".join([message, *lines]) if lines else message


class ClausalItem(pytest.Item):
    def __init__(self, name, parent, mod, load_error=None):
        super().__init__(name, parent)
        self._mod = mod
        self._load_error = load_error

    def runtest(self):
        if self._load_error is not None:
            verb = "collect tests from" if self.name == "<collect>" else "load"
            raise ClausalTestFailure(
                f"Failed to {verb} {self.path}: {self._load_error}"
            ) from self._load_error
        # ``diagnose=True``: a bare "no solutions" is close to no signal, and
        # pytest is where CI and most day-to-day runs read failures — the
        # detail must not be a privilege of the CLI runner.  ``path`` is what
        # lets the diagnosis quote the goal in its own source syntax and name
        # its variables (clausal.testing._reified_goals).  Cost is bounded to
        # the failure path: run_test only diagnoses a test that already failed.
        result = run_test(self._mod, self.name, path=self.path, diagnose=True)
        if not result.passed:
            if result.error:
                raise ClausalTestFailure(
                    _with_diagnosis(
                        f"{_spelled(self.name, result)} raised: {result.error}",
                        result,
                    )
                ) from result.error
            if result.negative:
                raise ClausalTestFailure(
                    f"test({self.name!r}, fail) succeeded (its goal has a "
                    "solution; a `fail` test passes only when it has none)"
                )
            raise ClausalTestFailure(
                _with_diagnosis(
                    f"test({self.name!r}) failed (no solutions)", result
                )
            )

    def repr_failure(self, excinfo):
        return str(excinfo.value)

    def reportinfo(self):
        return self.path, None, f"test({self.name!r})"


class ClausalTestFailure(Exception):
    pass


def _spelled(name, result) -> str:
    """The test as its clause spells it: ``test(N)`` or ``test(N, fail)``."""
    return f"test({name!r}, fail)" if result.negative else f"test({name!r})"


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


def _is_snippet_block(content: str) -> bool:
    """True if the block consists entirely of --8<-- snippet includes."""
    lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
    return bool(lines) and all(line.startswith("--8<--") for line in lines)


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

            if _is_snippet_block(content):
                yield DocItem.from_parent(
                    self,
                    name=f"L{lineno} [snippet]",
                    mod=None,
                    desc=None,
                    lineno=lineno,
                    snippet=True,
                )
                continue

            buf = io.StringIO()
            # Session-lived compile buffer (not an unlinked NamedTemporaryFile)
            # so DocItem.runtest can hand the path to diagnose_failure — see
            # _doc_block_home above.  Named after the md file and block line so
            # a quoted path in a report reads back to its source block.
            try:  # flatten docs-relative path: guide/intro.md -> guide_intro
                stem = "_".join(
                    self.path.relative_to(_docs_dir).with_suffix("").parts)
            except ValueError:
                stem = self.path.stem
            tmp_path = _doc_block_home() / f"{stem}_L{lineno}.clausal"
            tmp_path.write_text(content)

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

            try:
                descs = collect_tests(mod)
            except TestCollectionError as e:
                yield DocItem.from_parent(
                    self,
                    name=f"L{lineno} [collect error]",
                    mod=None,
                    desc=None,
                    lineno=lineno,
                    load_error=e,
                    load_output=buf.getvalue(),
                )
                continue
            if descs:
                for desc in descs:
                    yield DocItem.from_parent(
                        self,
                        name=f"L{lineno}: {desc}",
                        mod=mod,
                        desc=desc,
                        lineno=lineno,
                        load_output=buf.getvalue(),
                        src_path=tmp_path,
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
                 load_error=None, load_output="", skipped=False,
                 snippet=False, src_path=None):
        super().__init__(name, parent)
        self._mod = mod
        self._desc = desc
        self._lineno = lineno
        self._load_error = load_error
        self._load_output = load_output
        self._skipped = skipped
        self._snippet = snippet
        self._src_path = src_path

    def runtest(self):
        if self._skipped:
            pytest.skip("marked # skip")

        if self._snippet:
            return  # tested via the source fixture file

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
            # Same contract as ClausalItem.runtest: diagnosis on the failure
            # path only, quoting goals from the block's session-lived compile
            # buffer (``src_path``) so the report names the failing conjunct
            # and its source variables — a rotted tutorial example gets the
            # same signal as a rotted test file.
            result = run_test(self._mod, self._desc,
                              path=self._src_path, diagnose=True)
        output = buf.getvalue()
        if output:
            self.add_report_section("call", "stdout", output)

        if not result.passed:
            if result.error:
                raise DocTestFailure(
                    _with_diagnosis(
                        f"{_spelled(self._desc, result)} raised: "
                        f"{result.error}", result
                    )
                ) from result.error
            if result.negative:
                raise DocTestFailure(
                    f"test({self._desc!r}, fail) succeeded (its goal has a "
                    "solution; a `fail` test passes only when it has none)"
                )
            raise DocTestFailure(
                _with_diagnosis(
                    f"test({self._desc!r}) has no solutions", result
                )
            )

    def repr_failure(self, excinfo):
        return str(excinfo.value)

    def reportinfo(self):
        return self.path, self._lineno - 1, f"L{self._lineno}"


class DocTestFailure(Exception):
    pass
