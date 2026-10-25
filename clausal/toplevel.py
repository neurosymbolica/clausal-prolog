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
/ ``p`` full / elided lists, ``h`` or ``?`` help, Enter or ``.`` stop.  An
answer the engine knows is the last (``solve_with_last``) ends with its full
stop at once, as ``X = c.`` above; otherwise the user is asked, and when a
requested next solution does not exist the answer is ``false.``.

Not a terminal (piped stdin): no prompt and no key prompt; the first answer
of each query is printed.  An uncaught error is one line,
``error(Formal,Context).``  Ctrl-C during a search returns to ``?-``.
"""
from __future__ import annotations

import os
import sys

from clausal import toplevel_colour
from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX

PROMPT = "?- "
CONTINUATION = "|    "
INDENT = "   "
#: What the colour key types into the line (read_query takes it out).
COLOUR_MARK = "\x1f"
#: Lists longer than this are elided as ``[1,2,...|...]`` (Trealla: 100).
ELIDE_AFTER = 100
HISTORY_FILE = "~/.clausal_history"

HELP = """\
Action:
\tENTER,.     stop         - stop this query
\te           exit         - leave the top-level
\t;,SPACE,n   next         - display next solution
\tf           digit        - display 5 solutions
\t#           digit        - display # solutions (digits, then ENTER)
\ta           all          - display all solutions
\tw           write        - print answers in full
\tp           print        - elide long lists (the default)
\tc           colour       - cycle the colour scheme (also F2 or Ctrl-X c at ?-)
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
#: says itself when an answer is the last (``solve_with_last``); this table is
#: the fallback for what it does not prove, such as the goals after a
#: top-level ``!``.
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


def _conjuncts(goal) -> list:
    out = []
    while type(goal) is tuple and goal[0] == "," and len(goal) == 3:
        out.append(goal[1])
        goal = goal[2]
    out.append(goal)
    return out


def surely_deterministic(goal) -> bool:
    """True when *goal* is a conjunction of goals that cannot leave a choice
    (the table above), so its answer is the last one.  A top-level ``!``
    commits the goals before it: only those after the last one count."""
    parts = _conjuncts(goal)
    cuts = [i for i, g in enumerate(parts) if g == "!"]
    if cuts:
        parts = parts[cuts[-1] + 1:]
    return all(_deterministic_goal(g) for g in parts)


def _deterministic_goal(goal) -> bool:
    if goal in ("true", "fail", "false", "nl"):
        return True
    return (type(goal) is tuple and bool(goal)
            and (goal[0], len(goal) - 1) in _DETERMINISTIC)


# ── printing an answer ────────────────────────────────────────────────────


def _elide(t, depth=0, path=()):
    """*t* with each list past ``ELIDE_AFTER`` elements cut to its head and a
    ``|...`` tail, down a few levels of nesting.  A term with no long list
    is returned itself, so a cyclic answer keeps its shape."""
    if depth > 6 or id(t) in path:
        return t                        # too deep, or a cycle: left as is
    if type(t) in (list, tuple):
        path = path + (id(t),)
    if type(t) is list:
        items = [_elide(x, depth + 1, path) for x in t[:ELIDE_AFTER]]
        if len(t) > ELIDE_AFTER:
            out = "$elided"
            for x in reversed(items):
                out = (".", x, out)
            return out
        if all(a is b for a, b in zip(items, t)):
            return t
        return items
    if type(t) is tuple and t and t[0] != "$chars":
        args = [_elide(x, depth + 1, path) for x in t[1:]]
        if all(a is b for a, b in zip(args, t[1:])):
            return t
        return (t[0], *args)
    return t


def format_answer(shown, trail, elide: bool = True) -> str:
    """``cli._answer`` with long lists elided."""
    from clausal import cli  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415

    if elide:
        hidden = getattr(shown, "hidden", ())
        out = cli._Shown()
        for name, v in shown:
            w = _deref_walk(v)
            e = _elide(w)
            out.append((name, v if e is w else e))   # unchanged: as -g prints
        out.hidden = hidden
        shown = out
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
        self._prefill = ""
        self._bound = False
        self.colour = toplevel_colour.scheme_named(
            os.environ.get("CLAUSAL_COLOUR", "off"))
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

    # -- colour

    def _paint(self, text: str) -> str:
        if not self.interactive:
            return text
        return toplevel_colour.SCHEMES[self.colour].paint(text)

    def _redraw(self, prefix: str, text: str) -> None:
        """The answer line again in the current scheme, over the old one: the
        rows a long answer wrapped onto are cleared too."""
        import shutil  # noqa: PLC0415
        cols = max(shutil.get_terminal_size((80, 24)).columns, 1)
        rows = max((len(prefix) + len(text) - 1) // cols + 1, 1)
        up = f"\x1b[{rows - 1}A" if rows > 1 else ""
        self._write("\r" + up + "\x1b[J" + prefix + self._paint(text))

    def cycle_colour(self) -> str:
        """Switch to the next colour scheme; its name."""
        self.colour = (self.colour + 1) % len(toplevel_colour.SCHEMES)
        return toplevel_colour.SCHEMES[self.colour].name

    def _write(self, s: str) -> None:
        self.out.write(s)
        self.out.flush()

    # -- input

    def read_query(self) -> str | None:
        """The text of the next query, or None at end of input.  On a
        terminal the lines come through ``input`` (line editing, history);
        Ctrl-C drops the partial query and prompts again."""
        text = self._pending
        self._pending = ""
        if _layout_only(text):
            text = ""
        while True:
            if text.strip():
                end = query_end(text)
                if end is not None:
                    self._pending = text[end:]
                    self._remember(text[:end])
                    return text[:end]
            try:
                line = self._read_line(
                    PROMPT if not text.strip() else CONTINUATION)
            except KeyboardInterrupt:
                self._write("\n")
                text = ""
                continue
            if line is None:
                return None
            if COLOUR_MARK in line:
                # the colour key: switch scheme, then prompt again with the
                # line typed so far still in the editor
                name = self.cycle_colour()
                self._write(f"% colour: {name}\n")
                self._prefill = line.replace(COLOUR_MARK, "").rstrip("\n")
                continue
            text = text + line if text.strip() else line

    def _read_line(self, prompt: str) -> str | None:
        if self.interactive and self.stdin is sys.stdin:
            self._start_editing()
            try:
                return input(prompt) + "\n"
            except EOFError:
                self._write("\n")
                return None
        if self.interactive:
            self._write(prompt)
        line = self.stdin.readline()
        if line == "":
            if self.interactive:
                self._write("\n")
            return None
        return line

    def _start_editing(self) -> None:
        """Readline's keys for the colour switch, and the line typed before
        it was pressed."""
        try:
            import readline  # noqa: PLC0415
        except ImportError:
            return
        if not self._bound:
            self._bound = True
            if "libedit" in (readline.__doc__ or ""):
                # libedit (macOS's Python) takes other binding syntax and
                # may not run these macros: the colour key at ?- needs GNU
                # readline; `c` at the answer prompt works with either.
                readline.set_startup_hook(None)
                return
            # F2 and Ctrl-X c type the mark at the end of the line and
            # accept it (read_query then switches scheme and prompts again).
            for seq in (r'"\eOQ"', r'"\e[12~"', r'"\C-xc"'):
                readline.parse_and_bind(seq + r': "\C-e\C-v\x1f\C-m"')
        prefill, self._prefill = self._prefill, ""
        readline.set_startup_hook(
            (lambda: readline.insert_text(prefill)) if prefill else None)

    def _remember(self, query: str) -> None:
        """A completed query, on one line, into the readline history."""
        if not self.interactive:
            return
        try:
            import readline  # noqa: PLC0415
            one = " ".join(query.split())
            if one:
                readline.add_history(one)
        except ImportError:
            pass

    def _key(self) -> str:
        try:
            return self._keys.read()
        except KeyboardInterrupt:
            return "\x03"              # Ctrl-C at the prompt stops, never next

    # -- goals the top-level itself runs

    def _builtin(self, goal) -> bool:
        """halt/0,1 and consult/1 (``[File]``); True when handled."""
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        from clausal.logic.solve import _deref_walk  # noqa: PLC0415
        from clausal.logic.variables import Var  # noqa: PLC0415
        if goal == "halt":
            raise Halt(0)
        if type(goal) is tuple and goal[0] == "halt" and len(goal) == 2:
            n = _deref_walk(goal[1])
            if isinstance(n, Var):
                raise LogicException(("error", "instantiation_error",
                                      ("/", "halt", 1)))
            if type(n) is not int:
                raise LogicException(("error", ("type_error", "integer", n),
                                      ("/", "halt", 1)))
            raise Halt(n)
        files = None
        if type(goal) is tuple and goal[0] == "consult" and len(goal) == 2:
            files = goal[1]
        elif type(goal) is list and goal:
            files = goal
        if files is None:
            return False
        for f in (files if type(files) is list else [files]):
            self.consult(_deref_walk(f))
        self._write(INDENT + "true.\n")
        return True

    def consult(self, name) -> None:
        """Load *name* (``.clausal`` / ``.pl``, suffix optional) and make it
        the module queries run in."""
        from clausal.testing import load_clausal_module  # noqa: PLC0415
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        from clausal.logic.variables import Var  # noqa: PLC0415
        context = ("/", "consult", 1)
        if isinstance(name, Var):
            raise LogicException(("error", "instantiation_error", context))
        if type(name) is not str:
            raise LogicException(("error", ("type_error", "atom", name),
                                  context))
        candidates = [name] + [name + s for s in
                               (*CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX)]
        path = next((c for c in candidates if os.path.isfile(c)), None)
        if path is None:
            raise LogicException(("error",
                                  ("existence_error", "source_sink", name),
                                  context))
        module = load_clausal_module(path)      # a load error is the caller's
        self.module = module
        self.path = path
        self.op_table = self._ops_of(path)
        here = os.path.dirname(os.path.abspath(path))
        if here not in sys.path:
            sys.path.insert(0, here)

    def _refused(self, goal) -> bool:
        """A query may not use ``!``, ``->`` or ``*->`` in a goal position
        (not as data: ``X = '!'``) when the loaded file is Clausal Prolog or
        there is none; a ``.pl`` file, or ``--prolog``, accepts them
        (operator ruling 2026-10-24)."""
        if self.prolog or (self.path or "").endswith(PROLOG_SUFFIX):
            return False
        return _uses_control(goal)

    # -- running one query

    def run_query(self, text: str) -> None:
        from clausal import solve_with_last  # noqa: PLC0415
        try:
            goal, shown = self._cli._read_goal(text, self.op_table)
        except SyntaxError as exc:
            self._write(INDENT + _end(_syntax_line(exc)) + "\n")
            return
        try:
            if self._builtin(goal):
                return
            if self._refused(goal):
                self._write(INDENT + _end(
                    "error(syntax_error(cut_free),read_term/3)")
                    + "\n% !, -> and *-> are not accepted here; "
                      "start with --prolog (or load a .pl file) to accept "
                      "them\n")
                return
            self._answers(solve_with_last(("call", goal), module=self.module),
                          shown, surely_deterministic(goal))
        except Halt:
            raise
        except KeyboardInterrupt:
            self._write("\n% Execution Aborted\n")
        except BaseException as exc:  # noqa: BLE001 -- one line, not a traceback
            if isinstance(exc, (SystemExit, GeneratorExit)):
                raise
            self._write(INDENT + _end(_describe_error(exc)) + "\n")
            if os.environ.get("CLAUSAL_DEBUG"):
                import traceback  # noqa: PLC0415
                traceback.print_exc()

    def _answers(self, solutions, shown, det: bool = False) -> None:
        if not self.interactive:
            return self._answer_loop(solutions, shown, det)
        if self._keys is None:
            self._keys = _Keys(self.stdin.fileno())
        self._keys.enter()
        self._asking = False
        try:
            self._answer_loop(solutions, shown, det)
        except KeyboardInterrupt:
            if not self._asking:
                raise
            self._write("\n;  ... .\n")    # Ctrl-C at the prompt: stop
        finally:
            self._keys.leave()

    def _answer_loop(self, solutions, shown, det: bool) -> None:
        """*solutions* yields ``(trail, last)`` (``solve_with_last``); an
        answer is printed with its full stop when the engine knows it is the
        last, or when the goal can have at most one (*det*)."""
        it = iter(solutions)
        n = 0                           # answers shown so far
        want = 1                        # answers to show before asking
        eager = False
        while True:
            try:
                trail, last = next(it)
            except StopIteration:
                self._write((";  " if n else INDENT) + "false.\n")
                return
            text = format_answer(shown, trail, self.elide)
            prefix = ";  " if n else INDENT
            self._write(prefix + self._paint(text))
            n += 1
            if last or det or not self.interactive:
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
                if k == "e":
                    self._write("\n")
                    raise Halt(0)
                if k in ("\n", "\r", ".", "\x03", "\x04", "\x1b"):
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
                    prefix, text = INDENT, format_answer(shown, trail, False)
                    self._write(prefix + self._paint(text))
                    continue
                if k == "p":
                    self.elide = True
                    self._write("\n" + INDENT + "% eliding long lists\n")
                    prefix, text = INDENT, format_answer(shown, trail, True)
                    self._write(prefix + self._paint(text))
                    continue
                if k in ("h", "?"):
                    self._write("\n" + HELP)
                    self._write(prefix + self._paint(text))
                    continue
                if k == "c":
                    self.cycle_colour()
                    self._redraw(prefix, text)
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


def _describe_error(exc) -> str:
    """An uncaught exception as one line: ``error(Formal,Context)``, or
    ``throw(Ball)`` for a ball that is no error term (as Scryer prints it)."""
    from clausal import cli  # noqa: PLC0415
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    text = cli._describe(exc)
    if isinstance(exc, LogicException):
        from clausal.logic.solve import _deref_walk  # noqa: PLC0415
        ball = _deref_walk(exc.term)
        if not (type(ball) is tuple and len(ball) == 3 and ball[0] == "error"):
            return f"throw({text})"
    return text


#: Goals whose arguments (by position) are goals, for ``_uses_control``.
_GOAL_ARGS = {
    (",", 2): (0, 1), (";", 2): (0, 1), ("\\+", 1): (0,), ("call", 1): (0,),
    ("once", 1): (0,), ("ignore", 1): (0,), ("findall", 3): (1,),
    ("findall", 4): (1,), ("forall", 2): (0, 1), ("catch", 3): (0, 2),
    ("bagof", 3): (1,), ("setof", 3): (1,), ("aggregate_all", 3): (1,),
}


def _uses_control(goal) -> bool:
    """``!``, ``->`` or ``*->`` in a goal position of *goal*."""
    if goal == "!":
        return True
    if type(goal) is not tuple or not goal:
        return False
    if goal[0] in ("->", "*->") and len(goal) == 3:
        return True
    if goal[0] == "^" and len(goal) == 3:       # V^Goal under bagof/setof
        return _uses_control(goal[2])
    for i in _GOAL_ARGS.get((goal[0], len(goal) - 1), ()):
        if _uses_control(goal[1 + i]):
            return True
    return False


def _layout_only(text: str) -> bool:
    """*text* is only layout and ``%`` comments (what follows a query's end
    on its line)."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "%":
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                return False
            i = j + 2
        else:
            return False
    return True


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
