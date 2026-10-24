"""The interactive ISO ``?-`` top-level: ``clausal FILE`` (and ``clausal
--toplevel``).

It reads a query up to its closing ``.`` (continuing across lines), runs it
in the loaded program's module, and prints answers as ``clausal -g`` does
(``cli._answer``), one at a time: the next solution is computed only when the
user asks for it.  The layout and keys follow Trealla's top-level::

    ?- member(X, [a,b,c]).
       X = a
    ;  X = b
    ;  X = c.

``;`` (or space, ``n``) next, ``f`` five more, ``#`` N more, ``a`` all, ``w``
/ ``p`` full / elided lists, ``h`` or ``?`` help, Enter or ``.`` stop.  When a
requested next solution does not exist the answer is ``false.``: the engine
does not tell the top-level that the shown answer was the last.

Not a terminal (piped stdin): no prompt and no key prompt; the first answer
of each query is printed.  An uncaught error is one line,
``error(Formal,Context).``  Ctrl-C during a search returns to ``?-``.
"""
from __future__ import annotations

import os
import sys

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX

PROMPT = "?- "
CONTINUATION = "|    "
INDENT = "   "
#: Lists longer than this are elided as ``[1,2,...|...]`` (Trealla: 100).
ELIDE_AFTER = 100
HISTORY_FILE = "~/.clausal_history"

HELP = """\
Action:
\tENTER,.     stop         - stop this query
\t;,SPACE,n   next         - display next solution
\tf           digit        - display 5 solutions
\t#           digit        - display # solutions (digits, then ENTER)
\ta           all          - display all solutions
\tw           write        - print answers in full
\tp           print        - elide long lists (the default)
\th,?         help         - display this help
"""


# ── reading a query ───────────────────────────────────────────────────────

_GRAPHIC = set("#$&*+-./:<=>?@^~\\")


def query_end(text: str) -> int | None:
    """The index just past the first end token in *text*, or None: a ``.``
    followed by layout, a ``%`` or the end of the text, outside quotes and
    comments, and not part of a longer symbol atom (``=..``) or a number
    (``1.5``)."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "%":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and text[i + 1:i + 2] == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                return None
            i = j + 2
            continue
        if c in "'\"`":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == c:
                    if text[j + 1:j + 2] == c:
                        j += 2
                        continue
                    break
                j += 1
            else:
                return None             # an open quote: read on
            i = j + 1
            continue
        if c == "0" and text[i + 1:i + 2] == "'" and i + 2 < n \
                and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            # 0'c character code: skip the quote and its character
            j = i + 2
            if text[j] == "\\":
                j += 1
            elif text[j] == "'" and text[j + 1:j + 2] == "'":
                j += 1
            i = j + 1
            continue
        if c in _GRAPHIC:
            j = i
            while j < n and text[j] in _GRAPHIC:
                j += 1
            run = text[i:j]
            if run.endswith(".") and (j >= n or text[j].isspace()
                                      or text[j] == "%"):
                # an end token only when the dot stands alone (``X = $.``
                # reads as one atom; the reader's own rule)
                if run == ".":
                    return j
            i = j
            continue
        i += 1
    return None


def _syntax_line(exc: BaseException) -> str:
    """A reader error as the one line a top-level prints."""
    from clausal.terms import term_writeq  # noqa: PLC0415
    term = getattr(exc, "term", None)
    if term is not None:
        return term_writeq(term)
    return f"error(syntax_error({exc}),read_term/3)"


# ── knowing an answer is the last ─────────────────────────────────────────

#: Goals with at most one solution, whatever their arguments.  The engine
#: does not report determinism to a caller (its FINAL step is not emitted by
#: any producer yet), so these are the only goals whose answer is printed
#: with its full stop at once; for any other the user is asked.
_DETERMINISTIC = {
    ("=", 2), ("\\=", 2), ("==", 2), ("\\==", 2), ("is", 2),
    ("=:=", 2), ("=\\=", 2), ("<", 2), (">", 2), ("=<", 2), (">=", 2),
    ("@<", 2), ("@>", 2), ("@=<", 2), ("@>=", 2), ("=..", 2),
    ("var", 1), ("nonvar", 1), ("atom", 1), ("number", 1), ("integer", 1),
    ("float", 1), ("atomic", 1), ("compound", 1), ("callable", 1),
    ("is_list", 1), ("ground", 1), ("functor", 3), ("copy_term", 2), ("atom_length", 2), ("atom_chars", 2),
    ("atom_codes", 2), ("number_codes", 2), ("number_chars", 2),
    ("write", 1), ("writeq", 1), ("print", 1), ("write_canonical", 1),
    ("nl", 0), ("true", 0), ("fail", 0), ("false", 0),
    # posting a constraint is deterministic
    ("dif", 2), ("in", 2), ("ins", 2), ("#=", 2), ("#\\=", 2), ("#<", 2),
    ("#>", 2), ("#=<", 2), ("#>=", 2),
}


def _has_cut(goal) -> bool:
    """A ``!`` among the conjuncts of *goal* (not inside a disjunction)."""
    while type(goal) is tuple and goal[0] == "," and len(goal) == 3:
        if goal[1] == "!" or _has_cut(goal[1]):
            return True
        goal = goal[2]
    return goal == "!"


def surely_deterministic(goal) -> bool:
    """True when *goal* is a conjunction of goals that cannot leave a choice
    (the table above), so its answer is the last one."""
    if goal in ("true", "fail", "false", "nl", "!"):
        return True
    if type(goal) is tuple:
        if goal[0] == "," and len(goal) == 3:
            # a cut in the conjunction commits the goals before it
            return (_has_cut(goal) or surely_deterministic(goal[1])
                    and surely_deterministic(goal[2]))
        return (goal[0], len(goal) - 1) in _DETERMINISTIC
    return False


# ── printing an answer ────────────────────────────────────────────────────


def _elide(t, depth=0):
    """*t* with each list past ``ELIDE_AFTER`` elements cut to its head and a
    ``|...`` tail, down a few levels of nesting.  A term with no long list
    is returned itself, so a cyclic answer keeps its shape."""
    if depth > 6:
        return t
    if type(t) is list:
        items = [_elide(x, depth + 1) for x in t[:ELIDE_AFTER]]
        if len(t) > ELIDE_AFTER:
            out = "$elided"
            for x in reversed(items):
                out = (".", x, out)
            return out
        if all(a is b for a, b in zip(items, t)):
            return t
        return items
    if type(t) is tuple and t and t[0] != "$chars":
        args = [_elide(x, depth + 1) for x in t[1:]]
        if all(a is b for a, b in zip(args, t[1:])):
            return t
        return (t[0], *args)
    return t


def format_answer(shown, trail, elide: bool = True) -> str:
    """``cli._answer`` with long lists elided."""
    from clausal import cli  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415

    if elide:
        shown = [(name, _elide(_deref_walk(v))) for name, v in shown]
    text = cli._answer(shown, trail)
    return text.replace("|'$elided']", "|...]")


# ── keys ──────────────────────────────────────────────────────────────────


class _Keys:
    """Single keystrokes from a terminal, in cbreak mode."""

    def __init__(self, fd: int):
        import termios  # noqa: PLC0415
        import tty  # noqa: PLC0415
        self._fd = fd
        self._termios = termios
        self._saved = termios.tcgetattr(fd)
        self._tty = tty

    def enter(self) -> None:
        """Keys arrive unbuffered and unechoed until ``leave``."""
        self._tty.setcbreak(self._fd, self._termios.TCSANOW)

    def leave(self) -> None:
        self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN,
                                self._saved)

    def read(self) -> str:
        data = os.read(self._fd, 1)
        if data == b"\x1b":
            # an escape sequence (arrow key...): swallow, ignore it
            import select  # noqa: PLC0415
            while select.select([self._fd], [], [], 0.02)[0]:
                os.read(self._fd, 1)
            return "\x1b"
        return data.decode("utf-8", "replace")


# ── the top-level ─────────────────────────────────────────────────────────


class Halt(Exception):
    def __init__(self, status: int = 0):
        self.status = status


class TopLevel:
    def __init__(self, module, path: str | None = None,
                 stdin=None, stdout=None, prolog: bool = False):
        from clausal import cli  # noqa: PLC0415
        self.module = module
        self.path = path
        self.prolog = prolog
        self.stdin = stdin or sys.stdin
        self.out = stdout or sys.stdout
        self.interactive = self._isatty(self.stdin)
        self._keys = None
        self._pending = ""
        self._asking = False
        self.elide = True
        self._cli = cli
        self.op_table = self._ops_of(path)

    @staticmethod
    def _isatty(f) -> bool:
        try:
            return f.isatty()
        except (AttributeError, ValueError):
            return False

    def _ops_of(self, path):
        source = ""
        if path:
            with open(path, encoding="utf-8") as f:
                source = f.read()
        return self._cli._goal_reader_ops(source)

    def _write(self, s: str) -> None:
        self.out.write(s)
        self.out.flush()

    # -- input

    def read_query(self) -> str | None:
        """The text of the next query, or None at end of input."""
        text = self._pending
        self._pending = ""
        while True:
            if text.strip():
                end = query_end(text)
                if end is not None:
                    self._pending = text[end:]
                    return text[:end]
            if self.interactive:
                self._write(PROMPT if not text.strip() else CONTINUATION)
            line = self.stdin.readline()
            if line == "":
                if self.interactive:
                    self._write("\n")
                return None
            text = text + line if text.strip() else line

    def _key(self) -> str:
        try:
            return self._keys.read()
        except KeyboardInterrupt:
            return "\x03"              # Ctrl-C at the prompt stops, never next

    # -- goals the top-level itself runs

    def _builtin(self, goal) -> bool:
        """halt/0,1 and consult/1 (``[File]``); True when handled."""
        if goal == "halt":
            raise Halt(0)
        if type(goal) is tuple and goal[0] == "halt" and len(goal) == 2:
            from clausal.logic.solve import _deref_walk  # noqa: PLC0415
            n = _deref_walk(goal[1])
            raise Halt(n if type(n) is int else 0)
        files = None
        if type(goal) is tuple and goal[0] == "consult" and len(goal) == 2:
            files = goal[1]
        elif type(goal) is list and goal:
            files = goal
        if files is None:
            return False
        for f in (files if type(files) is list else [files]):
            self.consult(f)
        self._write(INDENT + "true.\n")
        return True

    def consult(self, name) -> None:
        """Load *name* (``.clausal`` / ``.pl``, suffix optional) and make it
        the module queries run in."""
        from clausal.testing import load_clausal_module  # noqa: PLC0415
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        if type(name) is not str:
            raise LogicException(("error", ("type_error", "atom", name),
                                  ("consult", 1)))
        candidates = [name] + [name + s for s in
                               (PROLOG_SUFFIX, *CLAUSAL_PROLOG_SUFFIXES)]
        path = next((c for c in candidates if os.path.isfile(c)), None)
        if path is None:
            raise LogicException(("error",
                                  ("existence_error", "source_sink", name),
                                  ("consult", 1)))
        self.module = load_clausal_module(path)
        self.path = path
        self.op_table = self._ops_of(path)
        sys.path.insert(0, os.path.dirname(os.path.abspath(path)))

    def _refused(self, goal) -> bool:
        """A query on the restricted Clausal Prolog surface (the default) may
        not use ``!``, ``->`` or ``*->``, as a ``.clausal`` source may not;
        ``--prolog`` accepts them (operator ruling 2026-10-24)."""
        if self.prolog:
            return False
        stack = [goal]
        while stack:
            t = stack.pop()
            if t == "!":
                return True
            if type(t) is tuple:
                if t[0] in ("->", "*->") and len(t) == 3:
                    return True
                stack.extend(t[1:])
            elif type(t) is list:
                stack.extend(t)
        return False

    # -- running one query

    def run_query(self, text: str) -> None:
        from clausal import solve  # noqa: PLC0415
        try:
            goal, shown = self._cli._read_goal(text, self.op_table)
        except SyntaxError as exc:
            self._write(INDENT + _end(_syntax_line(exc)) + "\n")
            return
        if self._builtin(goal):
            return
        if self._refused(goal):
            self._write(INDENT + _end(
                "error(syntax_error(cut_free),read_term/3)")
                + "\n% !, -> and *-> are not Clausal Prolog; "
                  "start with --prolog to accept them\n")
            return
        try:
            self._answers(solve(("call", goal), module=self.module), shown,
                          surely_deterministic(goal))
        except Halt:
            raise
        except KeyboardInterrupt:
            self._write("\n% Execution Aborted\n")
        except BaseException as exc:  # noqa: BLE001 -- one line, not a traceback
            if isinstance(exc, (SystemExit, GeneratorExit)):
                raise
            self._write(INDENT + _end(self._cli._describe(exc)) + "\n")
            if os.environ.get("CLAUSAL_DEBUG"):
                import traceback  # noqa: PLC0415
                traceback.print_exc()

    def _answers(self, solutions, shown, last: bool = False) -> None:
        if not self.interactive:
            return self._answer_loop(solutions, shown, last)
        if self._keys is None:
            self._keys = _Keys(self.stdin.fileno())
        self._keys.enter()
        self._asking = False
        try:
            self._answer_loop(solutions, shown, last)
        except KeyboardInterrupt:
            if not self._asking:
                raise
            self._write("\n;  ... .\n")    # Ctrl-C at the prompt: stop
        finally:
            self._keys.leave()

    def _answer_loop(self, solutions, shown, last: bool) -> None:
        it = iter(solutions)
        n = 0                           # answers shown so far
        want = 1                        # answers to show before asking
        eager = False
        while True:
            try:
                trail = next(it)
            except StopIteration:
                self._write((";  " if n else INDENT) + "false.\n")
                return
            text = format_answer(shown, trail, self.elide)
            self._write((";  " if n else INDENT) + text)
            n += 1
            if last or not self.interactive:
                self._write(_dot(text) + "\n")
                return
            want -= 1
            self._asking = False
            if eager or want > 0:
                self._write("\n")
                continue
            self._asking = True
            while True:
                k = self._key()
                if k in ("\n", "\r", ".", "\x03", "\x04", "e", "\x1b"):
                    self._write("\n;  ... .\n")
                    return
                if k in (";", " ", "n"):
                    self._write("\n")
                    want = 1
                    break
                if k == "f":
                    self._write("\n")
                    want = 5
                    break
                if k == "a":
                    self._write("\n")
                    eager = True
                    break
                if k == "#":
                    digits = ""
                    while True:
                        d = self._key()
                        if d.isdigit():
                            digits += d
                            continue
                        break
                    self._write("\n")
                    want = int(digits) if digits else 1
                    break
                if k == "w":
                    self.elide = False
                    self._write("\n" + INDENT + "% printing in full\n")
                    self._write(INDENT + format_answer(shown, trail, False))
                    continue
                if k == "p":
                    self.elide = True
                    self._write("\n" + INDENT + "% eliding long lists\n")
                    self._write(INDENT + format_answer(shown, trail, True))
                    continue
                if k in ("h", "?"):
                    self._write("\n" + HELP)
                    self._write(INDENT + text)
                    continue
                # anything else: ignored, the prompt stays

    # -- the loop

    def run(self) -> int:
        _setup_history(self.interactive)
        try:
            while True:
                text = self.read_query()
                if text is None:
                    return 0
                try:
                    self.run_query(text)
                except KeyboardInterrupt:
                    self._write("\n")
        except Halt as h:
            return h.status
        finally:
            _save_history(self.interactive)


def _dot(text: str) -> str:
    return _end(text)[len(text):]


def _end(text: str) -> str:
    from clausal import cli  # noqa: PLC0415
    return cli._end_answer(text)


# ── history ───────────────────────────────────────────────────────────────


def _setup_history(interactive: bool) -> None:
    if not interactive:
        return
    try:
        import readline  # noqa: PLC0415
        readline.set_auto_history(False)
        path = os.path.expanduser(HISTORY_FILE)
        if os.path.exists(path):
            readline.read_history_file(path)
        readline.set_history_length(1000)
    except (ImportError, OSError):
        pass


def _save_history(interactive: bool) -> None:
    if not interactive:
        return
    try:
        import readline  # noqa: PLC0415
        readline.write_history_file(os.path.expanduser(HISTORY_FILE))
    except (ImportError, OSError):
        pass


def banner(out) -> None:
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415
    try:
        v = version("clausal")
    except PackageNotFoundError:
        v = "dev"
    out.write(f"Clausal Prolog v{v}. Type h at an answer for help, "
              f"halt. to exit.\n")


def main(module, path: str | None = None, prolog: bool = False) -> int:
    top = TopLevel(module, path, prolog=prolog)
    if top.interactive:
        banner(top.out)
    return top.run()


def user_module():
    """The module a ``clausal`` with no FILE runs queries in: an empty
    program, which ``consult/1`` replaces."""
    import tempfile  # noqa: PLC0415
    from clausal.testing import load_clausal_module  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "user" + PROLOG_SUFFIX)
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        return load_clausal_module(path)
