"""ISO stream selection, control and character/byte I/O (ISO 13211-1
§8.11--8.13): ``open/3,4``, ``close/1,2``, ``current_input/1``,
``current_output/1``, ``set_input/1``, ``set_output/1``,
``flush_output/0,1``, ``at_end_of_stream/0,1``, ``set_stream_position/2``,
``stream_property/2``, ``get_char/1,2``, ``get_code/1,2``,
``peek_char/1,2``, ``peek_code/1,2``, ``put_char/1,2``, ``put_code/1,2``,
``get_byte/1,2``, ``peek_byte/1,2``, ``put_byte/1,2``, ``nl/1``, ``tab/2``.

The table itself is :mod:`clausal.logic.streams`; the writers' stream forms
(``write/2`` ... ``write_term/3``, ``format/3``) are in ``io.py`` next to
their current-output forms, and ``read/1,2`` / ``read_term/2,3`` in
``read_term.py``.

Error terms are ISO's (checked against Scryer, 2026-10-24), with the
builtin's indicator as the context:

* a stream-or-alias argument: unbound -> ``instantiation_error``; neither
  an atom nor a stream term -> ``domain_error(stream_or_alias, S)``; an
  atom that is no alias, or a closed stream -> ``existence_error(stream,
  S)``;
* the wrong direction -> ``permission_error(input, stream, S)`` /
  ``permission_error(output, stream, S)``; the wrong kind ->
  ``permission_error(input|output, binary_stream|text_stream, S)``;
  reading past the end of a stream whose ``eof_action`` is ``error`` ->
  ``permission_error(input, past_end_of_stream, S)``;
* ``open/4``: ``domain_error(source_sink, F)``, ``domain_error(io_mode,
  M)``, ``domain_error(stream_option, O)``, ``uninstantiation_error(S)``,
  ``existence_error(source_sink, F)``, ``permission_error(open,
  source_sink, F | alias(A) | reposition(true))``;
* the character/byte arguments: ``type_error(in_character, C)``,
  ``type_error(character, C)``, ``type_error(integer, C)``,
  ``representation_error(in_character_code | character_code)``,
  ``type_error(in_byte, B)``, ``type_error(byte, B)``.

In the sandbox every predicate here is refused (``clausal.sandbox``'s
``DENIED_BUILTINS``) like the writers are.
"""

from __future__ import annotations

import contextlib
from typing import Any

from clausal.logic import streams as _st
from clausal.logic.atoms import mint
from clausal.logic.exceptions import (
    LogicException, _error, domain_error, existence_error,
    instantiation_error, permission_error, representation_error,
    system_error, type_error,
)
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins.chars import _atom_to_str


# ── argument helpers ────────────────────────────────────────────────────────


@contextlib.contextmanager
def io_errors(ctx: str):
    """THE place an OS-level failure of a stream operation becomes a Prolog
    error: ``OSError`` (a full disk, a closed descriptor), ``ValueError``
    (a Python file closed underneath the stream, stdin captured by a test
    harness) and ``AttributeError`` (``sys.stdin`` set to None) raise
    ``error(system_error(io), PI)`` with the builtin as the context."""
    try:
        yield
    except LogicException:
        raise
    except (OSError, ValueError, AttributeError) as e:
        raise LogicException(system_error(
            "io", f"{ctx}: {type(e).__name__}: {e}")) from None


def source_sink_name(term) -> "str | None":
    """The file name a source/sink argument denotes: an atom's spelling,
    or (as Scryer accepts) the text of a string, a list of one-char atoms
    or a list of character codes; None for anything else."""
    name = _atom_to_str(term)
    if name is not None and term != []:
        return name
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    if is_chars(term):
        return chars_text(term)
    if type(term) is list and term:
        items = [deref(x) for x in term]
        if all(type(x) is str and len(x) == 1 for x in items):
            return "".join(items)
        if all(type(x) is int and not isinstance(x, bool)
               and 0 <= x <= 0x10FFFF for x in items):
            return "".join(map(chr, items))
    return None


def resolve_stream(term, ctx: str) -> _st.Stream:
    """The open stream *term* (dereffed) names, as a stream-or-alias."""
    if is_var(term):
        raise LogicException(instantiation_error(ctx))
    if _st.is_stream_term(term):
        s = _st.by_term(term)
        if s is None:
            raise LogicException(existence_error("stream", term, ctx))
        return s
    name = _atom_to_str(term)
    if name is None:
        raise LogicException(domain_error("stream_or_alias", term, ctx))
    s = _st.by_alias(name)
    if s is None:
        raise LogicException(existence_error("stream", term, ctx))
    return s


def output_text(term, ctx: str) -> _st.Stream:
    """*term* resolved, checked to be an output text stream."""
    s = resolve_stream(term, ctx)
    if not s.is_output:
        raise LogicException(permission_error("output", "stream", term, ctx))
    if s.is_binary:
        raise LogicException(permission_error("output", "binary_stream", term, ctx))
    return s


def output_binary(term, ctx: str) -> _st.Stream:
    s = resolve_stream(term, ctx)
    if not s.is_output:
        raise LogicException(permission_error("output", "stream", term, ctx))
    if not s.is_binary:
        raise LogicException(permission_error("output", "text_stream", term, ctx))
    return s


def input_text(term, ctx: str) -> _st.Stream:
    s = resolve_stream(term, ctx)
    if not s.is_input:
        raise LogicException(permission_error("input", "stream", term, ctx))
    if s.is_binary:
        raise LogicException(permission_error("input", "binary_stream", term, ctx))
    return s


def input_binary(term, ctx: str) -> _st.Stream:
    s = resolve_stream(term, ctx)
    if not s.is_input:
        raise LogicException(permission_error("input", "stream", term, ctx))
    if not s.is_binary:
        raise LogicException(permission_error("input", "text_stream", term, ctx))
    return s


def check_past_eof(s: _st.Stream, term, ctx: str) -> None:
    """Apply the stream's ``eof_action`` before a read: ``error`` raises,
    ``reset`` clears the past-end state, ``eof_code`` reads on (and gets
    the end-of-file code again)."""
    if s.past_eof:
        if s.eof_action == "error":
            raise LogicException(permission_error(
                "input", "past_end_of_stream", term, ctx))
        if s.eof_action == "reset":
            s.past_eof = False


def current_output_text(ctx: str) -> _st.Stream:
    """The current output stream, checked to be a text stream (the
    writers' and ``nl/0``'s target)."""
    s = _st.current_output()
    if s.is_binary:
        raise LogicException(permission_error(
            "output", "binary_stream", _culprit(s), ctx))
    return s


def _culprit(s: _st.Stream):
    """How the one-argument forms name their implicit stream in an error:
    a standard stream by its alias (``user_output``, as Scryer), any other
    by its stream term."""
    return s.aliases[0] if s.std is not None else s.term


def option_items(val, ctx: str) -> list:
    """The elements of an ISO option list, each dereffed: an unbound or
    partial list and an unbound element are ``instantiation_error``, a
    non-list ``type_error(list, L)``."""
    val = deref(val)
    if is_var(val):
        raise LogicException(instantiation_error(ctx))
    if type(val) is not list:
        from clausal.terms import SegList  # noqa: PLC0415
        if isinstance(val, SegList):
            walked = val._walk_raw()
            if isinstance(walked, SegList):
                raise LogicException(instantiation_error(ctx))
            val = walked
        if type(val) is not list:
            raise LogicException(type_error("list", val, ctx))
    items = []
    for x in val:
        x = deref(x)
        if is_var(x):
            raise LogicException(instantiation_error(ctx))
        items.append(x)
    return items


def _bool_atom(val) -> "bool | None":
    """The Boolean of the atom *val*: the truth atoms ``true``/``false``
    are the Python objects ``True``/``False`` (``clausal.logic.atoms``), a
    term built by hand may carry the spelling."""
    if val is True or val is False:
        return val
    if type(val) is str:
        if val == "true":
            return True
        if val == "false":
            return False
    return None


def _char_of(val, ctx: str, *, allow_eof: bool) -> None:
    """Check an output character argument (``put_char``), or an input one
    (``get_char``/``peek_char``: a var, a char or ``end_of_file``)."""
    if is_var(val):
        if allow_eof:
            return
        raise LogicException(instantiation_error(ctx))
    if type(val) is str and (len(val) == 1 or (allow_eof and val == "end_of_file")):
        return
    raise LogicException(type_error(
        "in_character" if allow_eof else "character", val, ctx))


def _valid_code(c: int) -> bool:
    return 0 <= c <= 0x10FFFF and not 0xD800 <= c <= 0xDFFF


def _check_in_code(val, ctx: str) -> None:
    """``get_code``/``peek_code``'s code argument: a var, or an integer that
    is a character code or -1."""
    if is_var(val):
        return
    if type(val) is not int or isinstance(val, bool):
        raise LogicException(type_error("integer", val, ctx))
    if val != -1 and not _valid_code(val):
        raise LogicException(representation_error("in_character_code", ctx))


def _check_out_code(val, ctx: str) -> int:
    if is_var(val):
        raise LogicException(instantiation_error(ctx))
    if type(val) is not int or isinstance(val, bool):
        raise LogicException(type_error("integer", val, ctx))
    if not _valid_code(val):
        raise LogicException(representation_error("character_code", ctx))
    return val


def _check_in_byte(val, ctx: str) -> None:
    if is_var(val):
        return
    if type(val) is not int or isinstance(val, bool) or not -1 <= val <= 255:
        raise LogicException(type_error("in_byte", val, ctx))


def _check_out_byte(val, ctx: str) -> int:
    if is_var(val):
        raise LogicException(instantiation_error(ctx))
    if type(val) is not int or isinstance(val, bool) or not 0 <= val <= 255:
        raise LogicException(type_error("byte", val, ctx))
    return val


def _unify_yield(a, b, trail):
    mark = trail.mark()
    if unify(a, b, trail):
        yield None
    trail.undo(mark)


# ── open/3,4 ────────────────────────────────────────────────────────────────

_OPEN = "open/4"


def _open(source, mode, stream, options, trail):
    source = deref(source)
    mode = deref(mode)
    stream = deref(stream)
    if is_var(source) or is_var(mode):
        raise LogicException(instantiation_error(_OPEN))
    opts = option_items(options, _OPEN)
    mode_name = _atom_to_str(mode)
    if mode_name is None:
        raise LogicException(type_error("atom", mode, _OPEN))
    file_name = source_sink_name(source)
    if file_name is None:
        raise LogicException(domain_error("source_sink", source, _OPEN))
    if mode_name not in _st.MODES:
        raise LogicException(domain_error("io_mode", mode, _OPEN))
    if not is_var(stream):
        raise LogicException(_error(("uninstantiation_error", stream), _OPEN))
    kind = "text"
    aliases: list = []
    eof_action = "eof_code"
    reposition = None
    for o in opts:
        if type(o) is tuple and len(o) == 2:
            name, arg = o[0], deref(o[1])
            if is_var(arg) and name in ("type", "alias", "eof_action", "reposition"):
                # ISO 8.11.5.3 a (a partial option): Scryer and SWI agree.
                raise LogicException(instantiation_error(_OPEN))
            if name == "type" and arg in ("text", "binary"):
                kind = arg
                continue
            if name == "alias":
                alias = _atom_to_str(arg)
                if alias is not None:
                    aliases.append(alias)
                    continue
            if name == "eof_action" and arg in _st.EOF_ACTIONS:
                eof_action = arg
                continue
            if name == "reposition" and _bool_atom(arg) is not None:
                reposition = _bool_atom(arg)
                continue
        raise LogicException(domain_error("stream_option", o, _OPEN))
    try:
        s = _st.open_stream(file_name, mode_name, kind=kind, aliases=aliases,
                            eof_action=eof_action, reposition=reposition)
    except _st.AliasInUse as e:
        raise LogicException(permission_error(
            "open", "source_sink", ("alias", e.alias), _OPEN)) from None
    except _st.OpenFailed as e:
        if e.why == "existence":
            raise LogicException(existence_error(
                "source_sink", source, _OPEN)) from None
        raise LogicException(permission_error(
            "open", "source_sink", source, _OPEN)) from None
    except ValueError:
        raise LogicException(permission_error(
            "open", "source_sink", ("reposition", "true"), _OPEN)) from None
    mark = trail.mark()
    if unify(stream, s.term, trail):
        yield None
    trail.undo(mark)


@_builtin("open", 4)
def _open__4(source, mode, stream, options, trail, k):
    """open(SourceSink, Mode, Stream, Options) -- ISO 8.11.5."""
    return _open(source, mode, stream, options, trail)


@_builtin("open", 3)
def _open__3(source, mode, stream, trail, k):
    """open(SourceSink, Mode, Stream) -- ``open(SourceSink, Mode, Stream, [])``."""
    return _open(source, mode, stream, [], trail)


# ── close/1,2 ───────────────────────────────────────────────────────────────

_CLOSE = "close/2"


def _close(stream, options):
    stream = deref(stream)
    if is_var(stream):
        raise LogicException(instantiation_error(_CLOSE))
    force = False
    for o in option_items(options, _CLOSE):
        if type(o) is tuple and len(o) == 2 and o[0] == "force":
            b = _bool_atom(deref(o[1]))
            if b is not None:
                force = b
                continue
        raise LogicException(domain_error("close_option", o, _CLOSE))
    s = resolve_stream(stream, _CLOSE)
    with io_errors(_CLOSE):
        _st.close_stream(s, force=force)
    yield None


@_builtin("close", 2)
def _close__2(stream, options, trail, k):
    """close(Stream, Options) -- ISO 8.11.6; ``force(true)`` ignores an
    error closing the file.  Closing a standard stream has no effect."""
    return _close(stream, options)


@_builtin("close", 1)
def _close__1(stream, trail, k):
    """close(Stream) -- ``close(Stream, [])``."""
    return _close(stream, [])


# ── current / set input and output ──────────────────────────────────────────


def _current(stream, s, trail, ctx):
    stream = deref(stream)
    if not is_var(stream) and not _st.is_stream_term(stream):
        raise LogicException(domain_error("stream", stream, ctx))
    return _unify_yield(stream, s.term, trail)


@_builtin("current_input", 1)
def _current_input__1(stream, trail, k):
    """current_input(Stream) -- ISO 8.11.1: the current input stream.  An
    alias is not a stream term here: ``domain_error(stream, S)``."""
    return _current(stream, _st.current_input(), trail, "current_input/1")


@_builtin("current_output", 1)
def _current_output__1(stream, trail, k):
    """current_output(Stream) -- ISO 8.11.2."""
    return _current(stream, _st.current_output(), trail, "current_output/1")


@_builtin("set_input", 1)
def _set_input__1(stream, trail, k):
    """set_input(Stream) -- ISO 8.11.3; an output stream is
    ``permission_error(input, stream, S)``."""
    stream = deref(stream)
    s = resolve_stream(stream, "set_input/1")
    if not s.is_input:
        raise LogicException(permission_error("input", "stream", stream, "set_input/1"))
    _st.set_current_input(s)
    yield None


@_builtin("set_output", 1)
def _set_output__1(stream, trail, k):
    """set_output(Stream) -- ISO 8.11.4; an input stream is
    ``permission_error(output, stream, S)``."""
    stream = deref(stream)
    s = resolve_stream(stream, "set_output/1")
    if not s.is_output:
        raise LogicException(permission_error("output", "stream", stream, "set_output/1"))
    _st.set_current_output(s)
    yield None


# ── flush_output, at_end_of_stream, set_stream_position ─────────────────────


@_builtin("flush_output", 0)
def _flush_output__0(trail, k):
    """flush_output -- ISO 8.11.7: flush the current output stream; an OS
    error (a full disk) is ``system_error(io)``."""
    with io_errors("flush_output/0"):
        _st.current_output().flush()
    yield None


@_builtin("flush_output", 1)
def _flush_output__1(stream, trail, k):
    """flush_output(Stream) -- ISO 8.11.7."""
    stream = deref(stream)
    s = resolve_stream(stream, "flush_output/1")
    if not s.is_output:
        raise LogicException(permission_error(
            "output", "stream", stream, "flush_output/1"))
    with io_errors("flush_output/1"):
        s.flush()
    yield None


@_builtin("at_end_of_stream", 0)
def _at_end_of_stream__0(trail, k):
    """at_end_of_stream -- ISO 8.11.8, of the current input stream."""
    with io_errors("at_end_of_stream/0"):
        at_end = _st.current_input().end_of_stream() != "not"
    if at_end:
        yield None


@_builtin("at_end_of_stream", 1)
def _at_end_of_stream__1(stream, trail, k):
    """at_end_of_stream(Stream) -- ISO 8.11.8: true iff the stream has the
    property ``end_of_stream(at)`` or ``end_of_stream(past)`` (so it fails
    for an output stream, which has neither)."""
    s = resolve_stream(deref(stream), "at_end_of_stream/1")
    with io_errors("at_end_of_stream/1"):
        at_end = s.is_input and s.end_of_stream() != "not"
    if at_end:
        yield None


@_builtin("set_stream_position", 2)
def _set_stream_position__2(stream, position, trail, k):
    """set_stream_position(Stream, Position) -- ISO 8.11.9.  Position is a
    term ``stream_property(S, position(P))`` gave; a stream whose
    ``reposition`` property is false is ``permission_error(reposition,
    stream, S)``."""
    ctx = "set_stream_position/2"
    stream = deref(stream)
    position = deref(position)
    # The position is checked before the stream (Scryer's order).
    if is_var(position):
        raise LogicException(instantiation_error(ctx))
    if not _st.is_position_term(position):
        raise LogicException(domain_error("stream_position", position, ctx))
    s = resolve_stream(stream, ctx)
    if not s.reposition:
        raise LogicException(permission_error("reposition", "stream", stream, ctx))
    try:
        s.seek_to(position)
    except (OSError, ValueError):
        # A well-shaped position the file refuses (a hand-built cookie):
        # ISO 8.11.9.3 b, not a position of this stream.
        raise LogicException(domain_error("stream_position", position, ctx)) from None
    yield None


# ── stream_property/2 ───────────────────────────────────────────────────────

_PROPERTY_NAMES = {
    "file_name": 1, "mode": 1, "input": 0, "output": 0, "alias": 1,
    "position": 1, "end_of_stream": 1, "eof_action": 1, "reposition": 1,
    "type": 1,
}


def _properties(s: _st.Stream) -> list:
    """The property terms of *s*, in ISO 7.10.2.13's order."""
    props: list = []
    if s.file_name is not None:
        props.append(("file_name", mint(s.file_name)))
    props.append(("mode", s.mode))
    props.append("input" if s.is_input else "output")
    for a in s.aliases:
        props.append(("alias", a))
    pos = s.position()
    if pos is not None:
        props.append(("position", pos))
    props.append(("end_of_stream", s.end_of_stream()))
    props.append(("eof_action", s.eof_action))
    props.append(("reposition", True if s.reposition else False))
    props.append(("type", s.kind))
    return props


def _property_shape_ok(p) -> bool:
    if type(p) is str:
        return _PROPERTY_NAMES.get(p) == 0
    if type(p) is tuple and len(p) == 2:
        return _PROPERTY_NAMES.get(p[0]) == 1
    return False


@_builtin("stream_property", 2)
def _stream_property__2(stream, prop, trail, k):
    """stream_property(Stream, Property) -- ISO 8.11.8: enumerates the
    open streams and their properties.  Stream may be unbound, a stream
    term or (as Scryer and SWI accept) an alias; Property unbound or one of
    ``file_name/1``, ``mode/1``, ``input``, ``output``, ``alias/1``,
    ``position/1``, ``end_of_stream/1``, ``eof_action/1``, ``reposition/1``,
    ``type/1`` -- anything else is ``domain_error(stream_property, P)``."""
    ctx = "stream_property/2"
    stream = deref(stream)
    prop = deref(prop)
    if not is_var(prop) and not _property_shape_ok(prop):
        raise LogicException(domain_error("stream_property", prop, ctx))
    if is_var(stream):
        candidates = _st.open_streams()
    else:
        if not _st.is_stream_term(stream) and _atom_to_str(stream) is None:
            raise LogicException(domain_error("stream", stream, ctx))
        candidates = [resolve_stream(stream, ctx)]
    for s in candidates:
        with io_errors(ctx):
            props = _properties(s)
        for p in props:
            mark = trail.mark()
            # A given stream (a term or an alias) is left as given.
            if (not is_var(stream) or unify(stream, s.term, trail)) \
                    and unify(prop, p, trail):
                yield None
            trail.undo(mark)


# ── character input and output (8.12) ───────────────────────────────────────


def _get_char(stream_term, char, trail, ctx, *, peek: bool):
    s = input_text(stream_term, ctx)
    _char_of(char, ctx, allow_eof=True)
    check_past_eof(s, stream_term, ctx)
    with io_errors(ctx):
        c = s.peek() if peek else s.get()
    return _unify_yield(char, "end_of_file" if c is None else c, trail)


@_builtin("get_char", 2)
def _get_char__2(stream, char, trail, k):
    """get_char(Stream, Char) -- ISO 8.12.1; ``end_of_file`` at the end."""
    return _get_char(deref(stream), deref(char), trail, "get_char/2", peek=False)


@_builtin("get_char", 1)
def _get_char__1(char, trail, k):
    """get_char(Char) -- from the current input stream."""
    return _get_char(_culprit(_st.current_input()), deref(char), trail,
                     "get_char/1", peek=False)


@_builtin("peek_char", 2)
def _peek_char__2(stream, char, trail, k):
    """peek_char(Stream, Char) -- ISO 8.12.2: the next char, not consumed."""
    return _get_char(deref(stream), deref(char), trail, "peek_char/2", peek=True)


@_builtin("peek_char", 1)
def _peek_char__1(char, trail, k):
    """peek_char(Char) -- from the current input stream."""
    return _get_char(_culprit(_st.current_input()), deref(char), trail,
                     "peek_char/1", peek=True)


def _get_code(stream_term, code, trail, ctx, *, peek: bool):
    s = input_text(stream_term, ctx)
    _check_in_code(code, ctx)
    check_past_eof(s, stream_term, ctx)
    with io_errors(ctx):
        c = s.peek() if peek else s.get()
    return _unify_yield(code, -1 if c is None else ord(c), trail)


@_builtin("get_code", 2)
def _get_code__2(stream, code, trail, k):
    """get_code(Stream, Code) -- ISO 8.12.1; -1 at the end."""
    return _get_code(deref(stream), deref(code), trail, "get_code/2", peek=False)


@_builtin("get_code", 1)
def _get_code__1(code, trail, k):
    """get_code(Code) -- from the current input stream."""
    return _get_code(_culprit(_st.current_input()), deref(code), trail,
                     "get_code/1", peek=False)


@_builtin("peek_code", 2)
def _peek_code__2(stream, code, trail, k):
    """peek_code(Stream, Code) -- ISO 8.12.2."""
    return _get_code(deref(stream), deref(code), trail, "peek_code/2", peek=True)


@_builtin("peek_code", 1)
def _peek_code__1(code, trail, k):
    """peek_code(Code) -- from the current input stream."""
    return _get_code(_culprit(_st.current_input()), deref(code), trail,
                     "peek_code/1", peek=True)


def _put_char(stream_term, char, ctx):
    s = output_text(stream_term, ctx)
    _char_of(char, ctx, allow_eof=False)
    with io_errors(ctx):
        s.write(char)
    yield None


@_builtin("put_char", 2)
def _put_char__2(stream, char, trail, k):
    """put_char(Stream, Char) -- ISO 8.12.3."""
    return _put_char(deref(stream), deref(char), "put_char/2")


@_builtin("put_char", 1)
def _put_char__1(char, trail, k):
    """put_char(Char) -- to the current output stream."""
    return _put_char(_culprit(_st.current_output()), deref(char), "put_char/1")


def _put_code(stream_term, code, ctx):
    s = output_text(stream_term, ctx)
    c = _check_out_code(code, ctx)
    with io_errors(ctx):
        s.write(chr(c))
    yield None


@_builtin("put_code", 2)
def _put_code__2(stream, code, trail, k):
    """put_code(Stream, Code) -- ISO 8.12.3."""
    return _put_code(deref(stream), deref(code), "put_code/2")


@_builtin("put_code", 1)
def _put_code__1(code, trail, k):
    """put_code(Code) -- to the current output stream."""
    return _put_code(_culprit(_st.current_output()), deref(code), "put_code/1")


@_builtin("nl", 1)
def _nl__1(stream, trail, k):
    """nl(Stream) -- ISO 8.12.3: a newline on Stream."""
    s = output_text(deref(stream), "nl/1")
    with io_errors("nl/1"):
        s.write("\n")
    yield None


@_builtin("tab", 2)
def _tab__2(stream, n, trail, k):
    """tab(Stream, N) -- N spaces on Stream (not ISO; Scryer/SWI have it)."""
    s = output_text(deref(stream), "tab/2")
    n_val = deref(n)
    if is_var(n_val):
        raise LogicException(instantiation_error("tab/2"))
    if type(n_val) is not int or isinstance(n_val, bool):
        raise LogicException(type_error("integer", n_val, "tab/2"))
    with io_errors("tab/2"):
        s.write(" " * n_val)
    yield None


# ── byte input and output (8.13) ────────────────────────────────────────────


def _get_byte(stream_term, byte, trail, ctx, *, peek: bool):
    s = input_binary(stream_term, ctx)
    _check_in_byte(byte, ctx)
    check_past_eof(s, stream_term, ctx)
    with io_errors(ctx):
        b = s.peek() if peek else s.get()
    return _unify_yield(byte, -1 if b is None else b, trail)


@_builtin("get_byte", 2)
def _get_byte__2(stream, byte, trail, k):
    """get_byte(Stream, Byte) -- ISO 8.13.1; -1 at the end."""
    return _get_byte(deref(stream), deref(byte), trail, "get_byte/2", peek=False)


@_builtin("get_byte", 1)
def _get_byte__1(byte, trail, k):
    """get_byte(Byte) -- from the current input stream."""
    return _get_byte(_culprit(_st.current_input()), deref(byte), trail,
                     "get_byte/1", peek=False)


@_builtin("peek_byte", 2)
def _peek_byte__2(stream, byte, trail, k):
    """peek_byte(Stream, Byte) -- ISO 8.13.2."""
    return _get_byte(deref(stream), deref(byte), trail, "peek_byte/2", peek=True)


@_builtin("peek_byte", 1)
def _peek_byte__1(byte, trail, k):
    """peek_byte(Byte) -- from the current input stream."""
    return _get_byte(_culprit(_st.current_input()), deref(byte), trail,
                     "peek_byte/1", peek=True)


def _put_byte(stream_term, byte, ctx):
    s = output_binary(stream_term, ctx)
    b = _check_out_byte(byte, ctx)
    with io_errors(ctx):
        s.write_bytes(bytes((b,)))
    yield None


@_builtin("put_byte", 2)
def _put_byte__2(stream, byte, trail, k):
    """put_byte(Stream, Byte) -- ISO 8.13.3."""
    return _put_byte(deref(stream), deref(byte), "put_byte/2")


@_builtin("put_byte", 1)
def _put_byte__1(byte, trail, k):
    """put_byte(Byte) -- to the current output stream."""
    return _put_byte(_culprit(_st.current_output()), deref(byte), "put_byte/1")


__all__ = [
    "resolve_stream", "output_text", "output_binary", "input_text",
    "input_binary", "check_past_eof", "current_output_text", "option_items",
    "io_errors", "source_sink_name",
]
