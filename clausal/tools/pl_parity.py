"""Translator-vs-native parity over the repository's ``.pl`` sources.

Slice 8.1 of the native ISO front-end plan, as re-planned 2026-10-12
(``implementation_plans/native-iso-reader-step2-2026-09-29.md`` §4): before
the ``.pl`` default can flip from the translator to the native front end,
every ``.pl`` source the repository holds is loaded under BOTH front ends
and the two are compared.

Each file is loaded twice, each time in its own subprocess, with
``CLAUSAL_PL_FRONTEND`` set and a private, empty ``PYTHONPYCACHEPREFIX``
per front end (the bytecode cache key is salted by front end already; a
separate cache makes a stale hit impossible rather than unlikely).  The
child asserts which loader ran.  Compared, per file:

* load success or refusal (each side's error is kept for the report);
* the ``test/1``/``test/2`` verdicts, by test name;
* for a file without tests, the all-answers of each predicate the file
  defines with arity <= ``MAX_ARITY``, called with fresh variables, at most
  ``MAX_ANSWERS`` answers each, under a per-call timeout.  Answers are
  rendered with ``term_writeq`` (local variable names), so the two sides
  compare as Prolog text.

The harness fails closed: it prints how many files it read and how many it
compared, and an N of 0 is an error.  A known-difference fixture
(``tests/fixtures/pl_parity_known.json``) lists each accepted difference
with its class; ``--check`` exits non-zero on any difference the fixture
does not list, and on any listed one that has gone (so the fixture is
pruned as the gaps close).

Classes (the report's vocabulary):

* ``a`` translator bug -- native agrees with the oracle (Scryer/Trealla);
* ``b`` native gap -- the translator is right, native refuses or differs;
* ``c`` both wrong;
* ``d`` intentional, by a ruling (named in the fixture's note).

Usage::

    python -m clausal.tools.pl_parity [--root DIR] [--no-docs]
        [--json OUT.json] [--report OUT.md] [--check FIXTURE.json] [-j N]
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
import warnings
from dataclasses import dataclass, field
from pathlib import Path

FRONTENDS = ("translator", "native")
LOADER_OF = {"translator": "PrologLoader", "native": "NativePrologLoader"}

#: Predicates of arity up to this are called with fresh variables.
MAX_ARITY = 3
#: Answers collected per call (a generator past this is cut, both sides).
MAX_ANSWERS = 200
#: Seconds per test or per predicate call, and per child process.
CALL_TIMEOUT = 5.0
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
    """Each ```prolog / ```pl block of ``docs/*.md`` as a file in *outdir*
    (outside the tree: nothing is written into the repository)."""
    found = []
    for md in sorted((root / "docs").glob("*.md")):
        text = md.read_text(encoding="utf-8")
        for m in _DOC_FENCE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            name = f"doc_{md.stem}_L{line}.pl".replace("-", "_")
            dest = outdir / name
            dest.write_text(m.group(1), encoding="utf-8")
            found.append(Source(str(dest), f"docs/{md.name}#L{line}", "docs"))
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
    from clausal.import_hook import pl_frontend  # noqa: PLC0415
    from clausal.testing import (  # noqa: PLC0415
        TestCollectionError, collect_tests, load_clausal_module, run_test)

    out: dict = {"path": path, "frontend": pl_frontend(), "loader": None,
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
        verdicts = {}
        for name in names:
            try:
                with contextlib.redirect_stdout(sink), \
                        contextlib.redirect_stderr(sink), \
                        _deadline(CALL_TIMEOUT):
                    r = run_test(mod, name)
                verdicts[name] = ("pass" if r.passed else
                                  "fail" if r.error is None else
                                  "error: " + _first_line(r.error))
            except _Timeout:
                verdicts[name] = "timeout"
            except BaseException as e:  # noqa: BLE001
                verdicts[name] = "error: " + _first_line(e)
        out["tests"] = verdicts
        from clausal.testing import _names_negative  # noqa: PLC0415
        out["negatives"] = [n for n in names if _names_negative(lm, n)]
        return out

    out["preds"] = _answers(lm, sink)
    return out


def _answers(lm, sink) -> dict:
    """``{"name/N": [answer, ...] | "error: ..." | "timeout"}`` for each
    predicate the module's own database defines, arity <= MAX_ARITY."""
    from clausal.logic.solve import call  # noqa: PLC0415
    from clausal.logic.variables import Var  # noqa: PLC0415

    keys = sorted((k for k, cs in lm.db._clauses.items()
                   if cs and isinstance(k, tuple) and len(k) == 2
                   and isinstance(k[0], str) and not k[0].startswith("$")
                   and k[1] <= MAX_ARITY and k[0] not in ("test", "Test")),
                  key=lambda k: (k[0], k[1]))
    result: dict = {}
    for name, arity in keys:
        args = [Var() for _ in range(arity)]
        answers: list[str] = []
        gen = None
        try:
            with contextlib.redirect_stdout(sink), \
                    contextlib.redirect_stderr(sink), _deadline(CALL_TIMEOUT):
                gen = call(name, *args, module=lm)
                for _ in gen:
                    answers.append(_render(args) if args else "true")
                    if len(answers) >= MAX_ANSWERS:
                        answers.append("...")
                        break
            result[f"{name}/{arity}"] = answers
        except _Timeout:
            result[f"{name}/{arity}"] = {"timeout": answers}
        except BaseException as e:  # noqa: BLE001
            result[f"{name}/{arity}"] = {"error": _first_line(e),
                                         "after": answers}
        finally:
            if gen is not None:
                with contextlib.suppress(BaseException):
                    gen.close()
    return result


# ── the parent: both front ends, then compare ────────────────────────────────


def run_side(src: Source, frontend: str, cache_root: Path,
             repo_root: Path) -> dict:
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
            capture_output=True, text=True, env=env, cwd=str(repo_root),
            timeout=CHILD_TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"crash": "child timed out"}
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(_JSON_MARK):
            data = json.loads(line[len(_JSON_MARK):])
            want = LOADER_OF[frontend]
            if data.get("loader") not in (None, want):
                return {"crash": f"wrong front end: {data['loader']} "
                                 f"under CLAUSAL_PL_FRONTEND={frontend}"}
            return data
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return {"crash": f"exit {proc.returncode}: " + " | ".join(tail)}


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


def run(root: Path, *, docs: bool = True, jobs: int = 4,
        only: "list[str] | None" = None) -> Run:
    r = Run()
    work = Path(tempfile.mkdtemp(prefix="pl_parity_"))
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

        def both(src):
            return src, run_side(src, "translator", cache, root), \
                run_side(src, "native", cache, root)

        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
            for src, t, n in ex.map(both, sources):
                r.sides[src.rel] = (t, n)
                if "crash" not in t and "crash" not in n:
                    r.compared += 1
                r.diffs.extend(compare(src.rel, t, n))
        # Oracle evidence while the doc snippets still exist.
        paths = {s.rel: s.path for s in sources}
        for d in r.diffs:
            d.auto = classify_auto(d, paths[d.rel], r.sides[d.rel])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return r


def load_fixture(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {e["key"]: e for e in data["known"]}


def check(r: Run, known: dict) -> list[str]:
    """Problems: a difference the fixture does not list, or a listed one
    that no longer occurs."""
    seen = {d.key for d in r.diffs}
    problems = [f"NEW difference: {d.key}  translator={_short(d.translator)}"
                f"  native={_short(d.native)}"
                for d in r.diffs if d.key not in known]
    problems += [f"GONE (prune the fixture): {k}" for k in sorted(known)
                 if k not in seen]
    return problems


def _short(v, n: int = 160) -> str:
    s = v if isinstance(v, str) else json.dumps(v)
    return s if len(s) <= n else s[:n] + "..."


def summary_lines(r: Run, known: "dict | None" = None) -> list[str]:
    by_pop: dict[str, int] = {}
    for s in r.sources:
        by_pop[s.population] = by_pop.get(s.population, 0) + 1
    lines = [f"pl_parity: {r.read} files read, {r.compared} compared "
             f"({', '.join(f'{k} {v}' for k, v in sorted(by_pop.items()))})",
             f"pl_parity: {len(r.diffs)} differences"]
    if known is not None:
        counts: dict[str, int] = {}
        for d in r.diffs:
            c = known.get(d.key, {}).get("class", "?")
            counts[c] = counts.get(c, 0) + 1
        lines.append("pl_parity: by class " + ", ".join(
            f"{k}={v}" for k, v in sorted(counts.items())))
    return lines


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m clausal.tools.pl_parity",
        description="Load every .pl source under both .pl front ends and "
                    "compare load, test verdicts and answers.")
    ap.add_argument("--probe", metavar="FILE",
                    help="(child) observe FILE under the current front end")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--no-docs", action="store_true",
                    help="skip the ```prolog blocks of docs/*.md")
    ap.add_argument("--only", action="append",
                    help="restrict to sources whose path contains this")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("--json", metavar="OUT", help="write every observation")
    ap.add_argument("--check", metavar="FIXTURE",
                    help="exit 1 on a difference the fixture does not list "
                         "or a listed one that is gone")
    a = ap.parse_args(argv)

    if a.probe:
        data = probe(a.probe)
        sys.stdout.write(_JSON_MARK + json.dumps(data) + "\n")
        sys.stdout.flush()
        os._exit(0)                      # no atexit work in the child

    r = run(Path(a.root), docs=not a.no_docs, jobs=a.jobs, only=a.only)
    known = load_fixture(Path(a.check)) if a.check else None
    for line in summary_lines(r, known):
        print(line)
    if a.json:
        Path(a.json).write_text(json.dumps({
            "read": r.read, "compared": r.compared,
            "sides": r.sides,
            "diffs": [dict(key=d.key, rel=d.rel, kind=d.kind, item=d.item,
                           translator=d.translator, native=d.native,
                           auto=getattr(d, "auto", None)) for d in r.diffs],
        }, indent=1, sort_keys=True))
    if r.compared == 0:
        print("pl_parity: ERROR: 0 files compared -- refusing an empty run")
        return 2
    if known is not None:
        problems = check(r, known)
        for p in problems:
            print(p)
        return 1 if problems else 0
    for d in r.diffs:
        print(f"  {d.key}\n    translator: {_short(d.translator)}\n"
              f"    native:     {_short(d.native)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
