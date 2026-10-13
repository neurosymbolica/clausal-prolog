"""Translator-vs-native parity over the repository's ``.pl`` sources.

Slice 8.1 of the native ISO front-end plan, as re-planned 2026-10-12
(``implementation_plans/native-iso-reader-step2-2026-09-29.md`` §4): before
the ``.pl`` default can flip from the translator to the native front end,
every ``.pl`` source the repository holds is loaded under BOTH front ends
and the two are compared.

Each file is loaded twice, each time in its own subprocess, with
``CLAUSAL_PL_FRONTEND`` set and a private, empty ``PYTHONPYCACHEPREFIX``
per front end (the bytecode cache key is salted by front end already; a
separate cache makes a stale hit impossible rather than unlikely).  Every
row, a refusal included, proves its front end, its engine (under
``--root``) and its loader (:func:`_engine_problem`).  Each test and call
runs in a forked child killed after ``CALL_TIMEOUT``.  Compared, per file:

* load success or refusal (each side's error is kept for the report);
* the ``test/1``/``test/2`` verdicts, by test name;
* for a file without tests, the all-answers of each predicate the file
  defines with arity <= ``MAX_ARITY``, called with fresh variables, at most
  ``MAX_ANSWERS`` answers each, under a per-call timeout.  Answers are
  rendered with ``term_writeq`` (local variable names), so the two sides
  compare as Prolog text.

The harness fails closed: it prints how many files it read, how many it
compared and how deep (:data:`CATEGORIES`), and an N of 0 is an error.
``tests/fixtures/pl_parity_known.json`` lists each accepted difference with
its class and a hash of both values; ``pl_parity_native.json`` beside it
pins native's whole observation of every file and a hash of the
translator's.  ``--check`` exits non-zero on any disagreement
(:func:`check`): a new or vanished difference, a changed value in a pinned
row, any change in native's observation of any file -- a timeout included,
after one retry -- or in the translator's hash.  ``--update`` rewrites both
fixtures; ``--summary-md`` writes the report's generated number block.

Classes (the report's vocabulary):

* ``a`` translator bug -- native agrees with the oracle (Scryer/Trealla);
* ``b`` native gap -- the translator is right, native refuses or differs;
* ``c`` both wrong;
* ``d`` intentional, by a ruling (named in the fixture's note).

Usage::

    python -m clausal.tools.pl_parity [--root DIR] [--no-docs]
        [--json OUT.json] [--summary-md OUT.md]
        [--check FIXTURE.json | --update FIXTURE.json] [-j N]
    python -m clausal.tools.pl_parity --probe FILE   # one side, in a child
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

FRONTENDS = ("translator", "native")
LOADER_OF = {"translator": "PrologLoader", "native": "NativePrologLoader"}

#: Predicates of arity up to this are called with fresh variables.
MAX_ARITY = 3
#: Answers collected per call (a generator past this is cut, both sides).
MAX_ANSWERS = 200
#: Seconds per test or per predicate call, and per child process.  A
#: timeout is its own observation ("timeout"), never a pinned difference:
#: under ``-j`` load a slow native call (``which_fib_is_55``: 3.7 s alone)
#: must not read as a divergence.
CALL_TIMEOUT = float(os.environ.get("CLAUSAL_PARITY_CALL_TIMEOUT", "30"))
CHILD_TIMEOUT = 300.0

_JSON_MARK = "PL-PARITY-JSON:"

#: The repository's own ``.pl`` sources, by population.
POPULATIONS = (
    ("iso_l3", "tests/iso_l3/"),
    ("tests", "tests/"),
    ("library", "clausal/library/"),
    ("examples", "clausal/examples/"),
    ("tools", "clausal/"),
    ("plans", "implementation_plans/"),
)

_DOC_FENCE = re.compile(r"^```(?:prolog|pl)[ \t]*\n(.*?)^```", re.M | re.S)


# ── discovery ────────────────────────────────────────────────────────────────


@dataclass
class Source:
    path: str          # absolute
    rel: str           # repo-relative (docs: "docs/x.md#L12")
    population: str


def population_of(rel: str) -> str:
    for name, prefix in POPULATIONS:
        if rel.startswith(prefix):
            return name
    return "other"


def discover(root: Path) -> list[Source]:
    """Every tracked ``.pl`` file under *root* (``git ls-files``; a walk
    when *root* is not a git checkout)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.pl"],
            capture_output=True, text=True, check=True).stdout
        rels = [r for r in out.split("\0") if r]
    except (OSError, subprocess.CalledProcessError):
        rels = [str(p.relative_to(root)) for p in root.rglob("*.pl")
                if "venv" not in p.parts and "__pycache__" not in p.parts]
    return [Source(str(root / r), r, population_of(r)) for r in sorted(rels)]


def doc_snippets(root: Path, outdir: Path) -> list[Source]:
    """Each ```prolog / ```pl block of ``README.md`` and ``docs/*.md`` as a
    file in *outdir*
    (outside the tree: nothing is written into the repository)."""
    found = []
    mds = sorted((root / "docs").glob("*.md"))
    if (root / "README.md").exists():
        mds.insert(0, root / "README.md")
    for md in mds:
        text = md.read_text(encoding="utf-8")
        for m in _DOC_FENCE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            name = f"doc_{md.stem}_L{line}.pl".replace("-", "_")
            dest = outdir / name
            dest.write_text(m.group(1), encoding="utf-8")
            rel = md.relative_to(root).as_posix()
            found.append(Source(str(dest), f"{rel}#L{line}", "docs"))
    return found


# ── the child: one file, one front end ───────────────────────────────────────


class _Timeout(BaseException):
    """Raised by the alarm; a BaseException so no engine handler eats it."""


@contextlib.contextmanager
def _deadline(seconds: float):
    def fire(signum, frame):
        raise _Timeout()
    old = signal.signal(signal.SIGALRM, fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _first_line(e: BaseException) -> str:
    text = str(e).strip().splitlines()
    return f"{type(e).__name__}: {text[0] if text else ''}"


def _render(value) -> str:
    from clausal.logic.solve import _deref_walk_py  # noqa: PLC0415
    from clausal.terms import term_writeq  # noqa: PLC0415
    v = _deref_walk_py(value)
    try:
        return term_writeq(v, local_vars=True)
    except Exception:  # noqa: BLE001
        return repr(v)


def probe(path: str) -> dict:
    """Load *path* under the current ``CLAUSAL_PL_FRONTEND`` and observe it."""
    import clausal  # noqa: PLC0415
    from clausal.import_hook import pl_frontend  # noqa: PLC0415
    from clausal.testing import (  # noqa: PLC0415
        TestCollectionError, collect_tests, load_clausal_module, run_test)

    # Which engine and which front end, recorded BEFORE the load, so a
    # refusal proves them as well as a load does.
    out: dict = {"path": path, "frontend": pl_frontend(),
                 "clausal_file": os.path.abspath(clausal.__file__),
                 "loader": None, "skipped_arity": 0,
                 "load": "ok", "error": None, "tests": None,
                 "collect_error": None, "preds": None}
    # The file's directory, and the directory above each enclosing package
    # (``tpkg/x.pl`` imports ``tpkg/y``), as a test that imports it sets up.
    d = os.path.dirname(os.path.abspath(path))
    sys.path.insert(0, d)
    while any(os.path.exists(os.path.join(d, f"__init__{x}"))
              for x in (".py", ".pl", ".seam", ".clausal")):
        d = os.path.dirname(d)
        sys.path.insert(0, d)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink), \
                warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with _deadline(CHILD_TIMEOUT / 2):
                mod = load_clausal_module(path)
    except _Timeout:
        out.update(load="timeout", error="load timed out")
        return out
    except BaseException as e:  # noqa: BLE001 - a refusal is an observation
        out.update(load="refused", error=_first_line(e))
        return out
    loader = getattr(getattr(mod, "__spec__", None), "loader", None)
    out["loader"] = type(loader).__name__
    lm = mod.__dict__["$module"]

    try:
        names = collect_tests(mod)
    except TestCollectionError as e:
        out["collect_error"] = _first_line(e)
        names = []
    if names:
        out["tests"] = {name: _isolated(lambda n=name: _one_test(mod, n))
                        for name in names}
        from clausal.testing import _names_negative  # noqa: PLC0415
        out["negatives"] = [n for n in names if _names_negative(lm, n)]
        return out

    own = [k for k, cs in lm.db._clauses.items()
           if cs and isinstance(k, tuple) and len(k) == 2
           and isinstance(k[0], str) and not k[0].startswith("$")
           and k[0] not in ("test", "Test")]
    keys = sorted((k for k in own if k[1] <= MAX_ARITY),
                  key=lambda k: (k[0], k[1]))
    out["skipped_arity"] = len(own) - len(keys)
    out["preds"] = {f"{name}/{arity}": _isolated(
        lambda n=name, a=arity: _one_call(lm, n, a)) for name, arity in keys}
    return out


def _isolated(fn):
    """Run *fn* in a forked child and return its JSON-able result, or
    ``"timeout"`` after CALL_TIMEOUT (the child is killed), or
    ``"crash: signal N"``.

    Each test or call runs in its own copy of the loaded module: a call
    that never answers is killed outright instead of being interrupted by
    an exception raised inside the engine (measured 2026-10-12: an alarm
    raised inside a runaway native call left the process to segfault in
    the garbage collector on a LATER call), a crash costs one item, not
    the file, and state a call asserts does not leak into the next."""
    import select  # noqa: PLC0415
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:                                       # the child
        os.close(r)
        try:
            sink = io.StringIO()
            with contextlib.redirect_stdout(sink), \
                    contextlib.redirect_stderr(sink):
                value = fn()
        except BaseException as e:  # noqa: BLE001
            value = "error: " + _first_line(e)
        try:
            data = json.dumps(value).encode()
        except Exception:  # noqa: BLE001
            data = json.dumps("error: unserialisable result").encode()
        with os.fdopen(w, "wb") as f:
            f.write(data)
        os._exit(0)
    os.close(w)
    chunks, deadline = [], time.monotonic() + CALL_TIMEOUT
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                return "timeout"
            ready, _, _ = select.select([r], [], [], left)
            if ready:
                chunk = os.read(r, 1 << 16)
                if not chunk:
                    break
                chunks.append(chunk)
    finally:
        os.close(r)
    _, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        return f"crash: signal {os.WTERMSIG(status)}"
    try:
        return json.loads(b"".join(chunks) or b'"crash: no result"')
    except ValueError:
        return "crash: unreadable result"


def _one_test(mod, name):
    from clausal.testing import run_test  # noqa: PLC0415
    r = run_test(mod, name)
    return ("pass" if r.passed else "fail" if r.error is None
            else "error: " + _first_line(r.error))


def _one_call(lm, name, arity):
    """All answers (at most MAX_ANSWERS, then "...") of ``name/arity``
    called with fresh variables, or ``{"error": ..., "after": [...]}``."""
    from clausal.logic.solve import call  # noqa: PLC0415
    from clausal.logic.variables import Var  # noqa: PLC0415
    args = [Var() for _ in range(arity)]
    answers: list[str] = []
    try:
        for _ in call(name, *args, module=lm):
            answers.append(_render(args) if args else "true")
            if len(answers) >= MAX_ANSWERS:
                answers.append("...")
                break
    except Exception as e:  # noqa: BLE001
        return {"error": _first_line(e), "after": answers}
    return answers


# ── the parent: both front ends, then compare ────────────────────────────────


def run_side(src: Source, frontend: str, cache_root: Path,
             repo_root: Path) -> dict:
    cache_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPYCACHEPREFIX"] = str(cache_root / frontend)
    env["PYTHONPATH"] = str(repo_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.pop("CLAUSAL_SANDBOX", None)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "clausal.tools.pl_parity", "--probe",
             src.path],
            capture_output=True, text=True, env=env, cwd=str(cache_root),
            timeout=CHILD_TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"crash": "child timed out"}
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(_JSON_MARK):
            data = json.loads(line[len(_JSON_MARK):])
            problem = _engine_problem(data, frontend, repo_root)
            return {"crash": problem} if problem else data
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return {"crash": f"exit {proc.returncode}: " + " | ".join(tail)}


def _no_core_dumps():
    """A crashing child must not write a multi-gigabyte core into the tree
    (measured: 2.4 GB, 2026-10-12).  Set once in the parent, before the
    thread pool starts, and inherited by every child: a ``preexec_fn``
    under a threaded parent can deadlock."""
    import resource  # noqa: PLC0415
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _engine_problem(data: dict, frontend: str, root: Path) -> "str | None":
    """Why a child's observation cannot be trusted, or None.  Checked on
    every row, a refusal included: the front end the child resolved, the
    engine it imported (the venv's editable install resolves elsewhere
    without PYTHONPATH), and the loader that ran."""
    if data.get("frontend") != frontend:
        return (f"wrong front end: the child ran {data.get('frontend')!r} "
                f"under CLAUSAL_PL_FRONTEND={frontend}")
    cf = data.get("clausal_file") or ""
    try:
        Path(cf).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return f"wrong engine: the child imported {cf}, not one under {root}"
    if data.get("loader") not in (None, LOADER_OF[frontend]):
        return (f"wrong loader: {data['loader']} under "
                f"CLAUSAL_PL_FRONTEND={frontend}")
    return None


def _is_timeout(v) -> bool:
    return v == "timeout"


@dataclass
class Difference:
    rel: str
    kind: str          # load | tests | collect | answers | predicates | crash
    item: str          # the test or predicate, "" for the file
    translator: object
    native: object

    @property
    def key(self) -> str:
        return f"{self.rel}::{self.kind}::{self.item}"


def compare(rel: str, t: dict, n: dict) -> list[Difference]:
    diffs: list[Difference] = []
    if "crash" in t or "crash" in n:
        diffs.append(Difference(rel, "crash", "", t.get("crash"),
                                n.get("crash")))
        return diffs
    if t["load"] != n["load"]:
        diffs.append(Difference(rel, "load", "", _load_of(t), _load_of(n)))
        return diffs
    if t["load"] != "ok":
        return diffs                      # both refused: agreement
    if (t["collect_error"] is None) != (n["collect_error"] is None):
        diffs.append(Difference(rel, "collect", "", t["collect_error"],
                                n["collect_error"]))
    tt, nt = t["tests"] or {}, n["tests"] or {}
    for name in sorted(set(tt) | set(nt)):
        if _is_timeout(tt.get(name)) or _is_timeout(nt.get(name)):
            continue                      # an observation, not a difference
        if tt.get(name) != nt.get(name):
            diffs.append(Difference(rel, "tests", name, tt.get(name),
                                    nt.get(name)))
    tp, np_ = t["preds"], n["preds"]
    if tp is None or np_ is None:
        if (tp is None) != (np_ is None):
            diffs.append(Difference(rel, "predicates", "",
                                    "tests" if tp is None else "no tests",
                                    "tests" if np_ is None else "no tests"))
        return diffs
    for key in sorted(set(tp) | set(np_)):
        if key not in tp or key not in np_:
            diffs.append(Difference(rel, "predicates", key,
                                    "defined" if key in tp else "absent",
                                    "defined" if key in np_ else "absent"))
        elif _is_timeout(tp[key]) or _is_timeout(np_[key]):
            continue
        elif tp[key] != np_[key]:
            diffs.append(Difference(rel, "answers", key, tp[key], np_[key]))
    return diffs


def _load_of(side: dict) -> str:
    return "ok" if side["load"] == "ok" else f"{side['load']}: {side['error']}"


# ── the oracle ───────────────────────────────────────────────────────────────

SCRYER = os.environ.get("CLAUSAL_PARITY_SCRYER",
                        "/workspace/scryer-prolog/target/release/scryer-prolog")
TREALLA = os.environ.get("CLAUSAL_PARITY_TREALLA",
                         "/workspace/trealla-prolog/tpl")


def oracle_answers(path: str, pred: str, binary: str) -> "list[str] | str | None":
    """All answers of ``pred`` (``name/N``) under an ISO system, as
    ``writeq`` text of the argument list, or ``"error: ..."``; ``None``
    when the system is absent or the file does not load cleanly there."""
    if not os.path.exists(binary):
        return None
    name, arity = pred.rsplit("/", 1)
    args = ",".join(f"A{i}" for i in range(int(arity)))
    head = _module_prefix(path) + (
        f"{_qa(name)}({args})" if int(arity) else _qa(name))
    # A failure-driven loop: Scryer's core has no forall/2 or member/2
    # without a library import.
    goal = (f"catch(({head}, writeq([{args}]), nl, fail ; true), E, "
            f"(write('error: '), writeq(E), nl)), halt")
    proc = _run_oracle(binary, path, goal, 30)
    if proc is None:
        return None
    if oracle_loads(path, binary) is not True:
        return None
    # Scryer prints its singleton warnings on stdout, as % comments.
    lines = [ln for ln in proc.stdout.splitlines()
             if not ln.lstrip().startswith("%")]
    if lines and lines[0].startswith("error: "):
        return lines[0]
    return [_norm(x) for x in lines]


def oracle_tests(path: str, names: list[str], binary: str,
                 negatives=()) -> "dict | None":
    """``{name: "pass" | "fail" | "error(...)"}`` for each ``test/1`` name
    (and each ``test(Name, fail)`` name in *negatives*, which passes iff
    its goal has no solution), called through the file's module."""
    if not os.path.exists(binary):
        return None
    m = _module_prefix(path)
    checks = []
    for n in names:
        q = _qa(n)
        goal = (f"(\\+ {m}test({q}, fail) -> R = pass ; R = fail)"
                if n in negatives else
                f"({m}test({q}) -> R = pass ; R = fail)")
        checks.append(f"catch({goal}, E, R = error(E)), "
                      f"writeq({q}), write(' => '), writeq(R), nl")
    goal = ", ".join(checks) + ", halt" if checks else "halt"
    proc = _run_oracle(binary, path, goal, 60)
    if proc is None:
        return None
    out = {}
    for line in proc.stdout.splitlines():
        k, sep, v = line.partition(" => ")
        if sep:
            for n in names:
                if _qa(n) == k:
                    out[n] = v
    return out or None


#: Makes ``:- end_module(M).`` (Clausal's module terminator) a no-op for
#: an ISO system, as the engine's own oracle tests do.
END_MODULE_PRELUDE = (Path(__file__).resolve().parents[2] / "tests"
                      / "_scryer_end_module.pl")


def _run_oracle(binary, path, goal, timeout):
    """Consult *path* in *binary* and run *goal*, or None."""
    path = os.path.abspath(path)
    files = [path]
    try:
        if ("end_module" in Path(path).read_text(encoding="utf-8")
                and END_MODULE_PRELUDE.exists()):
            files.insert(0, str(END_MODULE_PRELUDE))
    except OSError:
        pass
    trealla = binary.endswith("tpl")
    argv = ([binary, "-q", *files, "-g", goal] if trealla
            else [binary, *files, "-g", goal, "-g", "halt"])
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL,
                              cwd=os.path.dirname(path))
    except (OSError, subprocess.TimeoutExpired):
        return None


def _module_prefix(path: str) -> str:
    """``"m:"`` for a file that opens with ``:- module(m, ...)``, else ""."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    mm = re.search(r"^:-\s*module\(\s*([a-z][A-Za-z0-9_]*)\s*,", text, re.M)
    return f"{mm.group(1)}:" if mm else ""


def _qa(name: str) -> str:
    if re.fullmatch(r"[a-z][A-Za-z0-9_]*", name):
        return name
    return "'" + name.replace("\\", "\\\\").replace("'", "\\'") + "'"


_VAR_TOKEN = re.compile(r"(?<![A-Za-z0-9_'])_[A-Za-z0-9_]*")


def _norm(text: str) -> str:
    """Comparable writeq text: spacing removed, and variables renamed by
    first appearance (Scryer prints ``_123``, Trealla ``_G1``, the engine
    ``_`` for a singleton and ``_1`` for a shared one)."""
    names: dict[str, str] = {}
    counter = [0]

    def rename(m):
        tok = m.group(0)
        if tok == "_" or tok not in names:
            counter[0] += 1
            new = f"_V{counter[0]}"
            if tok != "_":
                names[tok] = new
            return new
        return names[tok]
    text = _DQ.sub(_chars_list, text)
    text = _unquote_one_char_atoms(text)
    # Rename before the spaces go: ``_1 is 7`` must not read as ``_1is7``.
    return re.sub(r"\s+", "", _VAR_TOKEN.sub(rename, text))


_DQ = re.compile(r'"((?:[^"\\]|\\.)*)"')


_ESC = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
        "f": "\f", "v": "\v", "0": "\0", "\\": "\\", "'": "'",
        '"': '"', "`": "`"}


def _chars_list(m) -> str:
    """``"ab"`` -> ``[a,b]``: the engine's ``term_writeq`` prints a char
    list as Scryer's toplevel does, ``writeq/1`` in a ``-g`` goal does
    not."""
    body, chars, i = m.group(1), [], 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            chars.append(_ESC.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            chars.append(c)
            i += 1
    return "[" + ",".join(_char_atom(c) for c in chars) + "]"


def _char_atom(c: str) -> str:
    if c == "\n":
        return "'\\n'"
    if c == "\\":
        return "\\"
    if c == "'":
        return "'\\''"
    return c


def _unquote_one_char_atoms(text: str) -> str:
    """``'1'`` -> ``1``, ``'日本'`` -> ``日本``, ``'\\\\'`` -> ``\\``: Scryer and Trealla disagree on
    quoting ``'日'`` and symbol chars, so both sides compare unquoted.  A
    scanner, not a regex: ``'a','b'`` must not read ``','`` as an atom."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] != "'":
            out.append(text[i])
            i += 1
            continue
        j = i + 1
        while j < n:
            if text[j] == "\\":
                j += 2
            elif text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                j += 2
            elif text[j] == "'":
                break
            else:
                j += 1
        inner = text[i + 1:j]
        if len(inner) == 1 and inner not in "\\'":
            out.append(inner)
        elif (inner and not inner.isascii() and inner[0].isalpha()
              and not inner[0].isupper()
              and all(c.isalnum() or c == "_" for c in inner)):
            out.append(inner)              # Scryer: 日本, Trealla: '日本'

        elif inner == "\\\\":
            out.append("\\")
        else:
            out.append(text[i:j + 1])
        i = j + 1
    return "".join(out)


def oracle_loads(path: str, binary: str) -> "bool | None":
    """True when the ISO system consults *path* with nothing on stderr."""
    if not os.path.exists(binary):
        return None
    proc = _run_oracle(binary, path, "halt", 30)
    if proc is None:
        return None
    # A warning (Scryer's singleton report) is not a refusal; an error is.
    lines = (proc.stderr + proc.stdout).splitlines()
    return not any("error" in ln.lower() and not ln.lstrip().startswith("%")
                   for ln in lines)


def classify_auto(diff: Difference, src_path: str,
                  sides=None) -> "tuple[str, str] | None":
    """``(class, evidence)`` from the oracles (Scryer, then Trealla), or None
    when no oracle speaks.  Evidence for the fixture's class, never a
    substitute for it: the fixture is what the gate pins."""
    oracles = (("scryer", SCRYER), ("trealla", TREALLA))
    if diff.kind == "load":
        for label, binary in oracles:
            ok = oracle_loads(src_path, binary)
            if ok is None:
                continue
            t_ok, n_ok = diff.translator == "ok", diff.native == "ok"
            if ok == n_ok:
                return "a", f"{label} {'loads' if ok else 'refuses'} it, as native does"
            if ok == t_ok:
                return "b", f"{label} {'loads' if ok else 'refuses'} it, as the translator does"
        return None
    if diff.kind == "tests":
        for label, binary in oracles:
            negs = set()
            for side in sides or ():
                negs.update(side.get("negatives") or ())
            o = oracle_tests(src_path, [diff.item], binary, negs)
            if not o or diff.item not in o:
                continue
            v = o[diff.item]
            verdict = "pass" if v == "pass" else "fail" if v == "fail" else "error"
            t = str(diff.translator).split(":")[0]
            n = str(diff.native).split(":")[0]
            if verdict == n and verdict != t:
                return "a", f"{label}: {v}, as native"
            if verdict == t and verdict != n:
                return "b", f"{label}: {v}, as the translator"
            return "c", f"{label}: {v}"
        return None
    if diff.kind != "answers":
        return None
    for label, binary in oracles:
        o = oracle_answers(src_path, diff.item, binary)
        if o is None:
            continue
        t = diff.translator if isinstance(diff.translator, list) else None
        n = diff.native if isinstance(diff.native, list) else None
        tn = [_norm(x) for x in t] if t is not None else None
        nn = [_norm(x) for x in n] if n is not None else None
        if nn == o and tn != o:
            return "a", f"{label} agrees with native"
        if tn == o and nn != o:
            return "b", f"{label} agrees with the translator"
        if tn != o and nn != o:
            rows = lambda xs: sum(1 for i, x in enumerate(o)  # noqa: E731
                                  if i >= len(xs or []) or xs[i] != x)
            return "c", (f"{label} agrees with neither (native differs in "
                         f"{rows(nn)} of {len(o)} rows, the translator in "
                         f"{rows(tn)})")
    return None


# ── driver ───────────────────────────────────────────────────────────────────


@dataclass
class Run:
    read: int = 0
    compared: int = 0
    sources: list = field(default_factory=list)
    sides: dict = field(default_factory=dict)        # rel -> (t, n)
    diffs: list = field(default_factory=list)
    categories: dict = field(default_factory=dict)   # rel -> category
    timeouts: list = field(default_factory=list)     # "rel::side::item"
    retried: list = field(default_factory=list)      # "rel::side"
    root: str = ""
    work: str = ""


#: How deep a file's comparison went (the breakdown ``summary_lines``
#: prints: "compared" alone overstates the evidence).
CATEGORIES = (
    ("deep", "both loaded; at least one test or predicate compared on a "
             "non-error result"),
    ("errors_only", "both loaded; every compared item is an error on both "
                    "sides (e.g. a doc block that needs an earlier block)"),
    ("nothing", "both loaded; no test and no predicate of arity <= "
                f"{MAX_ARITY} to compare"),
    ("native_only", "only native loads it: load compared, answers pinned "
                    "for native alone"),
    ("translator_only", "only the translator loads it"),
    ("both_refused", "both refuse it"),
    ("crash", "a child crashed or proved the wrong engine"),
)


def _is_error(v) -> bool:
    return (isinstance(v, str) and v.startswith("error: ")) or (
        isinstance(v, dict) and "error" in v)


def category(t: dict, n: dict) -> str:
    if "crash" in t or "crash" in n:
        return "crash"
    tl, nl = t["load"] == "ok", n["load"] == "ok"
    if not tl and not nl:
        return "both_refused"
    if nl and not tl:
        return "native_only"
    if tl and not nl:
        return "translator_only"
    items = []
    for side_t, side_n in ((t.get("tests") or {}, n.get("tests") or {}),
                           (t.get("preds") or {}, n.get("preds") or {})):
        for k in set(side_t) & set(side_n):
            items.append((side_t[k], side_n[k]))
    items = [(a, b) for a, b in items
             if not _is_timeout(a) and not _is_timeout(b)]
    if not items:
        return "nothing"
    if all(_is_error(a) and _is_error(b) for a, b in items):
        return "errors_only"
    return "deep"


def run(root: Path, *, docs: bool = True, jobs: int = 4,
        only: "list[str] | None" = None, oracle: bool = True,
        pinned: "dict | None" = None) -> Run:
    """Observe every source under both front ends.

    With *pinned* (a loaded fixture, under ``--check``), a side that timed
    out where the fixture pins a value is run ONCE more, alone, before
    anything is compared: one retry absorbs load from ``-j``; a second
    timeout stands and goes red in :func:`check`."""
    _no_core_dumps()            # once, here: every child inherits it
    r = Run(root=str(root))
    work = Path(tempfile.mkdtemp(prefix="pl_parity_"))
    r.work = str(work)
    try:
        sources = discover(root)
        if docs:
            ddir = work / "docs"
            ddir.mkdir()
            sources += doc_snippets(root, ddir)
        if only:
            sources = [s for s in sources if any(o in s.rel for o in only)]
        r.sources = sources
        r.read = len(sources)
        cache = work / "pycache"

        def side(src, frontend):
            return normalize(run_side(src, frontend, cache, root), root, work)

        def both(src):
            return src, side(src, "translator"), side(src, "native")

        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
            for src, t, n in ex.map(both, sources):
                r.sides[src.rel] = (t, n)
        if pinned is not None:
            for src in sources:
                t, n = r.sides[src.rel]
                if _needs_retry(n, pinned["native"].get(src.rel)):
                    n = side(src, "native")
                    r.retried.append(f"{src.rel}::native")
                tsha = pinned["translator_sha"].get(src.rel)
                if (_timed_out_items(t) and tsha
                        and sha(pinned_view(t)) != tsha):
                    t = side(src, "translator")
                    r.retried.append(f"{src.rel}::translator")
                r.sides[src.rel] = (t, n)
        for src in sources:
            t, n = r.sides[src.rel]
            r.categories[src.rel] = category(t, n)
            if "crash" not in t and "crash" not in n:
                r.compared += 1
            r.diffs.extend(compare(src.rel, t, n))
            for label, s_ in (("translator", t), ("native", n)):
                r.timeouts += [f"{src.rel}::{label}::{k}"
                               for k in _timed_out_items(s_)]
        if oracle:
            # Oracle evidence while the doc snippets still exist.  Not run
            # under --check: it never decides pass/fail.
            paths = {s.rel: s.path for s in sources}
            for d in r.diffs:
                d.auto = classify_auto(d, paths[d.rel], r.sides[d.rel])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return r


def _timed_out_items(side: dict) -> list[str]:
    return [k for group in ("tests", "preds")
            for k, v in (side.get(group) or {}).items() if _is_timeout(v)]


def _needs_retry(now: dict, pinned: "dict | None") -> bool:
    """True when *now* timed out on an item the fixture pins a value for."""
    if pinned is None:
        return False
    for group in ("tests", "preds"):
        was = pinned.get(group) or {}
        for k, v in (now.get(group) or {}).items():
            if _is_timeout(v) and k in was and not _is_timeout(was[k]):
                return True
    return False


# ── pinning ──────────────────────────────────────────────────────────────────

_VOLATILE = (
    (re.compile(r"AttVar\(_\d+\)"), "AttVar(_)"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "0x?"),
    (re.compile(r"/tmp/pl_parity_[A-Za-z0-9_]+"), "<work>"),
)


def normalize(side: dict, root: Path, work: Path) -> dict:
    """*side* with machine-specific text replaced (the repository root, the
    temp directory, object addresses, variable ids), so an observation
    pins the same on every checkout."""
    roots = sorted({str(root), str(Path(root).resolve())}, key=len,
                   reverse=True)
    works = sorted({str(work), str(Path(work).resolve())}, key=len,
                   reverse=True)

    def fix(v):
        if isinstance(v, str):
            for w in works:
                v = v.replace(w, "<work>")
            for rt in roots:
                v = v.replace(rt, "<root>")
            for rx, rep in _VOLATILE:
                v = rx.sub(rep, v)
            return v
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        return v
    return fix(side)


def pinned_view(side: dict) -> dict:
    """The part of one side's observation the fixture pins: load and its
    error, collect error, verdicts and answers.  Timed-out items are kept
    as "timeout" and never compared."""
    if "crash" in side:
        return {"crash": side["crash"]}
    return {k: side.get(k) for k in
            ("load", "error", "collect_error", "tests", "preds")}


def sha(value) -> str:
    import hashlib  # noqa: PLC0415
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def load_fixture(path: Path) -> dict:
    """``{"known": {key: row}, "native": {rel: view},
    "translator_sha": {rel: sha}}``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    obs_path = path.with_name(data.get("observations",
                                       "pl_parity_native.json"))
    obs = (json.loads(obs_path.read_text(encoding="utf-8"))
           if obs_path.exists() else {"native": {}, "translator_sha": {}})
    return {"known": {e["key"]: e for e in data["known"]},
            "native": obs["native"], "translator_sha": obs["translator_sha"],
            "about": data.get("about", "")}


def _diff_items(pinned: dict, now: dict) -> list[str]:
    """Item-level changes between two pinned views (a timeout compares as
    the value "timeout")."""
    out = []
    for k in ("load", "error", "collect_error"):
        if pinned.get(k) != now.get(k):
            out.append(f"{k}: pinned={_short(pinned.get(k))} "
                       f"now={_short(now.get(k))}")
    for group in ("tests", "preds"):
        a, b = pinned.get(group) or {}, now.get(group) or {}
        if (pinned.get(group) is None) != (now.get(group) is None):
            out.append(f"{group}: pinned={_short(pinned.get(group))} "
                       f"now={_short(now.get(group))}")
            continue
        # A timeout is a VALUE here: a pinned answer that now times out is
        # red (after run()'s one retry), and so is a pinned timeout that now
        # terminates -- the fixture is updated on purpose, never drifts.
        for item in sorted(set(a) | set(b)):
            if a.get(item) != b.get(item):
                out.append(f"{group} {item}: pinned={_short(a.get(item))} "
                           f"now={_short(b.get(item))}")
    if "crash" in now or "crash" in pinned:
        if now.get("crash") != pinned.get("crash"):
            out.append(f"crash: pinned={pinned.get('crash')} "
                       f"now={now.get('crash')}")
    return out


def check(r: Run, fixture: dict) -> list[str]:
    """Every way the run disagrees with the fixture:

    * a difference the fixture does not list (NEW), or a listed one that no
      longer occurs (GONE);
    * a listed difference whose translator or native VALUE changed (a
      regression inside a pinned row goes red, not just a new row);
    * any change in native's own observation of any file (load, verdicts,
      answers), so a native regression in a native-only file goes red too;
    * any change in the translator's observation of a file (by hash)."""
    known = fixture["known"]
    problems = []
    seen = {}
    for d in r.diffs:
        seen[d.key] = d
        row = known.get(d.key)
        if row is None:
            problems.append(f"NEW difference: {d.key}  translator="
                            f"{_short(d.translator)}  native={_short(d.native)}")
            continue
        if row.get("native_sha") and sha(d.native) != row["native_sha"]:
            problems.append(f"CHANGED native value in pinned row {d.key}: "
                            f"now {_short(d.native)}")
        if (row.get("translator_sha")
                and sha(d.translator) != row["translator_sha"]):
            problems.append(f"CHANGED translator value in pinned row "
                            f"{d.key}: now {_short(d.translator)}")
    problems += [f"GONE (prune the fixture): {k}" for k in sorted(known)
                 if k not in seen]
    natives = fixture["native"]
    tshas = fixture["translator_sha"]
    for rel, (t, n) in sorted(r.sides.items()):
        if rel not in natives:
            problems.append(f"NEW file (not pinned): {rel}")
            continue
        for line in _diff_items(natives[rel], pinned_view(n)):
            problems.append(f"NATIVE CHANGED {rel}: {line}")
        if tshas.get(rel) and sha(pinned_view(t)) != tshas[rel]:
            problems.append(f"TRANSLATOR CHANGED {rel} (hash)")
    problems += [f"GONE file (prune the fixture): {rel}"
                 for rel in sorted(set(natives) - set(r.sides))]
    return problems


def update_fixture(r: Run, path: Path) -> list[str]:
    """Rewrite the fixture from *r*, keeping each known row's class and note
    (a new row gets class "?", which the gate refuses until it is set)."""
    old = load_fixture(path) if path.exists() else {
        "known": {}, "about": ""}
    known = []
    for d in r.diffs:
        prev = old["known"].get(d.key, {})
        known.append({"key": d.key, "class": prev.get("class", "?"),
                      "note": prev.get("note", ""),
                      "translator_sha": sha(d.translator),
                      "native_sha": sha(d.native)})
    obs_name = "pl_parity_native.json"
    path.write_text(json.dumps({"about": old.get("about", ""),
                                "observations": obs_name,
                                "known": known},
                               indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    path.with_name(obs_name).write_text(json.dumps({
        "about": "Native's pinned observation of every file, and a hash of "
                 "the translator's (clausal.tools.pl_parity --update).",
        "native": {rel: pinned_view(n) for rel, (t, n) in
                   sorted(r.sides.items())},
        "translator_sha": {rel: sha(pinned_view(t)) for rel, (t, n)
                           in sorted(r.sides.items())},
    }, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return [d.key for d in r.diffs if d.key not in old["known"]]


def _short(v, n: int = 160) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "..."


def category_counts(r: Run) -> dict:
    counts = {name: 0 for name, _ in CATEGORIES}
    for c in r.categories.values():
        counts[c] += 1
    return counts


def summary_lines(r: Run, known: "dict | None" = None) -> list[str]:
    by_pop: dict[str, int] = {}
    for s in r.sources:
        by_pop[s.population] = by_pop.get(s.population, 0) + 1
    c = category_counts(r)
    skipped = sum(n.get("skipped_arity", 0) for _, n in r.sides.values())
    lines = [f"pl_parity: {r.read} files read, {r.compared} compared "
             f"({', '.join(f'{k} {v}' for k, v in sorted(by_pop.items()))})",
             "pl_parity: depth: " + ", ".join(
                 f"{name} {c[name]}" for name, _ in CATEGORIES),
             f"pl_parity: {skipped} predicate(s) of arity > {MAX_ARITY} "
             "not called (native side)",
             f"pl_parity: {len(r.timeouts)} timed-out item(s) (limit "
             f"{CALL_TIMEOUT:g}s; never a translator-vs-native difference, "
             "but pinned like any value)",
             f"pl_parity: {len(r.diffs)} differences"]
    for t in r.timeouts:
        lines.append(f"pl_parity:   timeout {t}")
    if r.retried:
        lines.append(f"pl_parity: {len(r.retried)} side(s) re-run once "
                     "after a timeout where a value is pinned: "
                     + ", ".join(r.retried))
    if known is not None:
        counts: dict[str, int] = {}
        for d in r.diffs:
            cl = known.get(d.key, {}).get("class", "?")
            counts[cl] = counts.get(cl, 0) + 1
        lines.append("pl_parity: by class " + ", ".join(
            f"{k}={v}" for k, v in sorted(counts.items())))
    return lines


SUMMARY_BEGIN = "<!-- BEGIN pl_parity summary (generated) -->"
SUMMARY_END = "<!-- END pl_parity summary -->"


def summary_md(r: Run, known: "dict | None") -> str:
    """The parity report's numbers, as markdown between SUMMARY_BEGIN and
    SUMMARY_END: written by ``--summary-md``, pasted verbatim into the
    report, and compared with a fresh run by the gate test, so the report
    cannot drift from the tool."""
    by_pop: dict[str, int] = {}
    for src in r.sources:
        by_pop[src.population] = by_pop.get(src.population, 0) + 1
    c = category_counts(r)
    out = [SUMMARY_BEGIN,
           f"**{r.read} files read, {r.compared} compared** ("
           + ", ".join(f"{k} {v}" for k, v in sorted(by_pop.items()))
           + ").", "", "| depth | files | meaning |", "|---|---|---|"]
    out += [f"| {name} | {c[name]} | {what} |" for name, what in CATEGORIES]
    loads = {(a, b): 0 for a in (True, False) for b in (True, False)}
    for t, n in r.sides.values():
        if "crash" in t or "crash" in n:
            continue
        loads[(t["load"] == "ok", n["load"] == "ok")] += 1
    out += ["", "| translator \\ native | loads | refused |", "|---|---|---|",
            f"| **loads** | {loads[(True, True)]} | {loads[(True, False)]} |",
            f"| **refused** | {loads[(False, True)]} | "
            f"{loads[(False, False)]} |", ""]
    kinds: dict[str, int] = {}
    for d in r.diffs:
        kinds[d.kind] = kinds.get(d.kind, 0) + 1
    line = f"**{len(r.diffs)} differences"
    if known is not None:
        classes = {k: 0 for k in "abcd"}
        for d in r.diffs:
            cl = known.get(d.key, {}).get("class", "?")
            classes[cl] = classes.get(cl, 0) + 1
        line += ": " + ", ".join(f"({k}) {v}" for k, v in classes.items())
    out.append(line + ".** Kinds: " + ", ".join(
        f"{k} {v}" for k, v in sorted(kinds.items())) + ".")
    skipped = sum(n.get("skipped_arity", 0) for _, n in r.sides.values())
    out += ["", f"Timed out at {CALL_TIMEOUT:g} s: {len(r.timeouts)} item(s)"
            + (" (" + ", ".join(f"`{t}`" for t in r.timeouts) + ")"
               if r.timeouts else "") + ". Predicates of arity > "
            f"{MAX_ARITY} not called (native side): {skipped}.",
            SUMMARY_END]
    return "\n".join(out) + "\n"


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m clausal.tools.pl_parity",
        description="Load every .pl source under both .pl front ends and "
                    "compare load, test verdicts and answers.")
    ap.add_argument("--probe", metavar="FILE",
                    help="(child) observe FILE under the current front end")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--no-docs", action="store_true",
                    help="skip the ```prolog blocks of README.md and "
                         "docs/*.md")
    ap.add_argument("--only", action="append",
                    help="restrict to sources whose path contains this")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("--json", metavar="OUT", help="write every observation")
    ap.add_argument("--summary-md", metavar="OUT",
                    help="write the report's generated summary block "
                         "(classes need --check or --update's fixture)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", metavar="FIXTURE",
                      help="exit 1 on any disagreement with the fixture "
                           "(see check())")
    mode.add_argument("--update", metavar="FIXTURE",
                      help="rewrite the fixture and its observations file "
                           "from this run (new rows get class '?')")
    a = ap.parse_args(argv)

    if a.probe:
        data = probe(a.probe)
        sys.stdout.write(_JSON_MARK + json.dumps(data) + "\n")
        sys.stdout.flush()
        os._exit(0)                      # no atexit work in the child

    fixture = load_fixture(Path(a.check)) if a.check else None
    r = run(Path(a.root), docs=not a.no_docs, jobs=a.jobs, only=a.only,
            oracle=not a.check, pinned=fixture)
    for line in summary_lines(r, fixture and fixture["known"]):
        print(line)
    if a.json:
        Path(a.json).write_text(json.dumps({
            "read": r.read, "compared": r.compared,
            "categories": r.categories, "timeouts": r.timeouts,
            "sides": r.sides,
            "diffs": [dict(key=d.key, rel=d.rel, kind=d.kind, item=d.item,
                           translator=d.translator, native=d.native,
                           auto=getattr(d, "auto", None)) for d in r.diffs],
        }, indent=1, sort_keys=True, ensure_ascii=False))
    if a.summary_md:
        fx = fixture or (load_fixture(Path(a.update)) if a.update
                         and Path(a.update).exists() else None)
        Path(a.summary_md).write_text(
            summary_md(r, fx and fx["known"]), encoding="utf-8")
    if r.compared == 0:
        print("pl_parity: ERROR: 0 files compared -- refusing an empty run")
        return 2
    if a.update:
        new = update_fixture(r, Path(a.update))
        for k in new:
            print(f"pl_parity: new row, classify it: {k}")
        return 0
    if fixture is not None:
        problems = check(r, fixture)
        for p in problems:
            print(p)
        return 1 if problems else 0
    for d in r.diffs:
        print(f"  {d.key}\n    translator: {_short(d.translator)}\n"
              f"    native:     {_short(d.native)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
