"""ISO term input (ISO 13211-1 §8.14.1): ``read/1,2`` and ``read_term/2,3``
over the stream table, with the native ISO reader.

``read_term(S, T, Opts)`` reads one term -- up to and including its end
token ``.`` -- from the text input stream *S* and unifies it with *T*.  The
end token's trailing layout character stays in the stream (as Scryer leaves
it: ``read(T), get_char(C)`` after ``foo. bar.`` gives ``C = ' '``).  At the
end of the stream the term is the atom ``end_of_file``.  The term is read
with the process's run-time operator table (what ``op/3`` as a goal and a
file's global ``op/3`` directives build) -- a COPY of it, so a ``:- op(...)``
read as data changes nothing -- and ``"..."`` under the reading module's
``double_quotes`` flag (``chars``, the default, ``codes`` or ``atom``).

Options (each ``domain_error(read_option, O)`` otherwise):

* ``variables(Vs)``: the term's variables in first-occurrence order
  (anonymous ``_`` included);
* ``variable_names(Ps)``: ``Name = Var`` for each named variable (``_X``
  included, ``_`` not);
* ``singletons(Ps)``: the named variables that occur once.

A syntax error is ``error(syntax_error(Kind), context(read_term/3, Details))``,
with Scryer's ``Kind`` and the line, column, expected and found token in
``Details`` (operator ruling 2026-10-24, ``exceptions.syntax_error_exception``); the stream is
left after the offending item's end token (the reader resyncs on it), so the
next read goes on with the next term.  A term that is not a term -- the
stream's remaining text without an end token -- is a syntax error too, and
the read after it gives ``end_of_file``.

Stream errors are the stream builtins' (``streams_io.py``): an unbound stream
is ``instantiation_error``, an output stream ``permission_error(input,
stream, S)``, a binary one ``permission_error(input, binary_stream, S)``,
reading past the end of a stream opened with ``eof_action(error)``
``permission_error(input, past_end_of_stream, S)``.
"""

from __future__ import annotations

from clausal.logic import streams as _st
from clausal.logic.atoms import mint
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error,
    syntax_error_exception,
)
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.builtins._registry import _db_builtin
from clausal.logic.builtins.streams_io import (
    _culprit, check_past_eof, input_text, io_errors, option_items,
)

_READ = "read_term/3"
_OPTION_NAMES = ("variables", "variable_names", "singletons")


# ── the stream reader ───────────────────────────────────────────────────────


def read_item(s: _st.Stream):
    """Read one item from the text input stream *s* with a fresh
    ``PrologReader`` over a copy of the run-time operator table.  Returns
    the reader's item (``Clause``/``Directive``/``Query``/``DCGRule``), a
    ``SyntaxIssue``, or ``EOF``.  Everything up to the end token is
    consumed; the rest of the text read ahead is pushed back."""
    from clausal.tools.prolog_operators import runtime_op_table  # noqa: PLC0415
    from clausal.tools.prolog_reader import PrologReader  # noqa: PLC0415
    from clausal.tools.prolog_tokenizer import PL_SOURCE_NESTED_COMMENTS  # noqa: PLC0415
    from clausal.tools.toklex import EOF, NEED_MORE  # noqa: PLC0415

    reader = PrologReader(op_table=runtime_op_table().copy(),
                          nested_comments=PL_SOURCE_NESTED_COMMENTS)
    fed: list = []
    total = 0
    closed = False
    while True:
        chunk = "" if closed else s.read_chunk()
        if chunk == "":
            if closed:
                item = EOF          # defensive: a closed lexer always ends
                break
            reader.close()
            closed = True
        else:
            reader.feed(chunk)
            fed.append(chunk)
            total += len(chunk)
        item = reader.read_term()
        if item is NEED_MORE:
            continue
        break
    text = "".join(fed)
    consumed = total if item is EOF else min(reader.last_item_end, total)
    s.consume(text[:consumed])
    s.unread(text[consumed:])
    return item


# ── reader cells -> engine terms ────────────────────────────────────────────


def _build(cell, variables: dict, dq: str):
    """The engine term of a reader cell: ``VarRef`` -> one ``Var`` per
    index, ``'.'/2`` chains -> lists (partial lists for a variable tail),
    ``"..."`` under the ``double_quotes`` mode *dq*."""
    from clausal.tools.prolog_reader import VarRef  # noqa: PLC0415
    if type(cell) is VarRef:
        v = variables.get(cell.i)
        if v is None:
            v = variables[cell.i] = Var()
        return v
    if type(cell) is tuple:
        if len(cell) == 2 and cell[0] == "$chars" and type(cell[1]) is str:
            return _string(cell[1], dq)
        if len(cell) == 3 and cell[0] == ".":
            return _cons(cell, variables, dq)
        return (cell[0], *(_build(x, variables, dq) for x in cell[1:]))
    if type(cell) is list:
        return [_build(x, variables, dq) for x in cell]
    return cell


def _string(text: str, dq: str):
    if dq == "codes":
        return [ord(c) for c in text]
    if dq == "atom":
        return mint(text) if text else ""
    return ("$chars", text)


def _cons(cell, variables: dict, dq: str):
    """``'.'(H, T)`` chains as the engine spells them: a list when the tail
    is one, a partial list when it is a variable, and for any other tail
    (``[a|b]``) the cons cells ``'.'(H, T)`` themselves -- the engine's
    spelling of an improper list, as the native front end lowers one
    (``iso_l3._cons``; ``clausal/terms.py`` "an IMPROPER list")."""
    from clausal.tools.prolog_reader import VarRef  # noqa: PLC0415
    from clausal.terms import SegList, ConcreteSeg, VarSeg  # noqa: PLC0415
    heads = []
    t = cell
    while type(t) is tuple and len(t) == 3 and t[0] == ".":
        heads.append(_build(t[1], variables, dq))
        t = t[2]
    if type(t) is VarRef:
        return SegList([ConcreteSeg(heads), VarSeg(_build(t, variables, dq))])
    tail = _build(t, variables, dq)
    if type(tail) is list:
        return heads + tail
    if type(tail) is tuple and len(tail) == 2 and tail[0] == "$chars":
        return heads + list(tail[1])
    out = tail
    for h in reversed(heads):
        out = (".", h, out)
    return out


def _count_refs(cell, counts: dict) -> None:
    from clausal.tools.prolog_reader import VarRef  # noqa: PLC0415
    stack = [cell]
    while stack:
        x = stack.pop()
        if type(x) is VarRef:
            counts[x.i] = counts.get(x.i, 0) + 1
        elif type(x) is tuple:
            if len(x) == 2 and x[0] == "$chars":
                continue
            stack.extend(x[1:])
        elif type(x) is list:
            stack.extend(x)


def _item_term(item):
    """The whole term an item was read from (a directive or query gets its
    prefix operator back)."""
    kind = type(item).__name__
    term = item.term
    if kind == "Directive":
        return (":-", term)
    if kind == "Query":
        return ("?-", term)
    return term


# ── options ─────────────────────────────────────────────────────────────────


def _read_options(options) -> list:
    """``[(name, arg), ...]`` of a read-option list."""
    out = []
    for o in option_items(options, _READ):
        if type(o) is tuple and len(o) == 2 and o[0] in _OPTION_NAMES:
            out.append((o[0], o[1]))
            continue
        raise LogicException(domain_error("read_option", o, _READ))
    return out


def _read_term(db, stream_term, term, options, trail):
    from clausal.logic.builtins.flags import flag_value  # noqa: PLC0415
    from clausal.tools.toklex import EOF  # noqa: PLC0415

    stream_term = deref(stream_term)
    s = input_text(stream_term, _READ)
    opts = _read_options(options)
    check_past_eof(s, stream_term, _READ)
    dq = flag_value(db, "double_quotes") if db is not None else "chars"
    with io_errors(_READ):
        item = read_item(s)
    if item is EOF:
        s.past_eof = True
        value = "end_of_file"
        variables: dict = {}
        names: dict = {}
        counts: dict = {}
    elif type(item).__name__ == "SyntaxIssue":
        raise syntax_error_exception(item, _READ)
    else:
        cell = _item_term(item)
        variables = {}
        value = _build(cell, variables, dq)
        # The reader names an anonymous variable '_' too; it is no name.
        names = {i: n for i, n in item.var_names.items() if n != "_"}
        counts = {}
        _count_refs(cell, counts)
    mark = trail.mark()
    ok = unify(term, value, trail)
    for name, arg in opts:
        if not ok:
            break
        if name == "variables":
            result = [variables[i] for i in sorted(variables)]
        elif name == "variable_names":
            result = [("=", names[i], variables[i])
                      for i in sorted(variables) if i in names]
        else:
            result = [("=", names[i], variables[i])
                      for i in sorted(variables)
                      if i in names and counts.get(i) == 1]
        ok = unify(arg, result, trail)
    if ok:
        yield None
    trail.undo(mark)


# ── the builtins ────────────────────────────────────────────────────────────


@_db_builtin("read_term", 3, fields=("stream", "term", "options"),
             db_optional=True)
def _make_read_term__3(db):
    def read_term__3(stream, term, options, trail, k):
        """read_term(Stream, Term, Options) -- ISO 8.14.1."""
        return _read_term(db, stream, term, options, trail)
    return read_term__3


@_db_builtin("read_term", 2, fields=("term", "options"), db_optional=True)
def _make_read_term__2(db):
    def read_term__2(term, options, trail, k):
        """read_term(Term, Options) -- from the current input stream."""
        return _read_term(db, _culprit(_st.current_input()), term, options, trail)
    return read_term__2


@_db_builtin("read", 2, fields=("stream", "term"), db_optional=True)
def _make_read__2(db):
    def read__2(stream, term, trail, k):
        """read(Stream, Term) -- ``read_term(Stream, Term, [])``."""
        return _read_term(db, stream, term, [], trail)
    return read__2


@_db_builtin("read", 1, fields=("term",), db_optional=True)
def _make_read__1(db):
    def read__1(term, trail, k):
        """read(Term) -- ``read_term(Term, [])`` on the current input."""
        return _read_term(db, _culprit(_st.current_input()), term, [], trail)
    return read__1


# ``db_optional``: a read needs no database beyond the module's
# double_quotes flag (``chars`` without one), so the db-less class table may
# build these (``_registry._stateless_dispatch``).

__all__ = ["read_item"]
