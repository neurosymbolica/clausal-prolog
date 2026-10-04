"""clausal.modules.py — canonical Python library wrappers.

Each wrapper module is named after the Python library it wraps. Stdlib
wrappers (``csv``, ``datetime``, ``json``, ``os``, ``random``, ``re``,
``uuid``, etc.) ship with core Clausal. Third-party wrappers (``torch``,
``sympy``, ``jax``, ``opencv``, ``scipy_*``, ``sklearn``, ``spacy``,
``yaml``) ship in separately installable extension distributions
(clausal-torch, clausal-sympy, …) that contribute files into this
subpackage via PEP 420 namespace packaging.
"""

from __future__ import annotations

# Extend __path__ so that separately-installed wrapper distributions
# (e.g. clausal-torch) that place files under clausal/modules/py/ in
# site-packages are discoverable alongside the core source tree.
_sp = _candidate = _finder = _finder_module = _namespaces = None
import os as _os, site as _site
for _sp in _site.getsitepackages():
    _candidate = _os.path.join(_sp, "clausal", "modules", "py")
    if _os.path.isdir(_candidate) and _candidate not in __path__:
        __path__.append(_candidate)

# Discover editable installs: setuptools' modern editable finder (verified
# against setuptools >=64) registers a class in sys.meta_path; the
# NAMESPACES dict mapping fully-qualified package names to source
# directories lives on the finder *module* (reachable via
# sys.modules[finder.__module__]). Without this, `pip install -e
# packages/clausal-X` would not contribute its `clausal/modules/py/<name>.py`
# to clausal.modules.py.__path__.
import sys as _sys
for _finder in list(_sys.meta_path):
    _finder_module = _sys.modules.get(getattr(_finder, "__module__", None) or "")
    _namespaces = getattr(_finder_module, "NAMESPACES", None)
    if not isinstance(_namespaces, dict):
        continue
    for _candidate in _namespaces.get("clausal.modules.py", ()):
        if _candidate and _candidate not in __path__:
            __path__.append(_candidate)
del _os, _site, _sp, _sys, _finder, _finder_module, _namespaces, _candidate

from decimal import Decimal as _Decimal
from fractions import Fraction as _Fraction
from typing import Callable

from clausal.logic.trampoline import DONE


# ── Shared base adapter ─────────────────────────────────────────────────────


class ModulePredicate:
    """Base adapter providing ``_get_dispatch()`` for module predicates.

    Every ``py.*`` module needs a tiny adapter class so the Clausal runtime
    can look up the dispatch function for a given arity.  This base class
    captures the pattern that was previously copy-pasted into every module.

    Usage::

        hash = ModulePredicate("hash")
        hash._register(3, simple_to_trampoline(_hash_3))
    """

    __slots__ = ("_name", "_module", "_dispatch_fns", "_dispatch_wrapper")

    def __init__(self, name: str, *, module: str = "") -> None:
        self._name = name
        self._module = module
        self._dispatch_fns: dict[int, Callable] = {}
        self._dispatch_wrapper: Callable | None = None

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        # Always route through the arity-checking dispatcher so wrong-arity is
        # a consistent, catchable error (F005) and stdlib exceptions raised by
        # the implementation are converted to catchable terms (F004). Compiled
        # goals call _get_dispatch per invocation, so cache the wrapper —
        # _multi_dispatch reads _dispatch_fns at call time, so later
        # _register calls are still honoured.
        wrapper = self._dispatch_wrapper
        if wrapper is None:
            wrapper = self._dispatch_wrapper = _catchable_dispatch(
                self._multi_dispatch
            )
        return wrapper

    def _multi_dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            # Unregistered arity is an existence error, not a silent failure —
            # consistent whether the predicate has one arity or several (F005).
            from clausal.logic.atoms import mint
            from clausal.logic.exceptions import (
                LogicException, existence_error,
            )
            indicator = ("/", mint(self._name), arity)
            raise LogicException(existence_error("procedure", indicator))
        yield from fn(this_generator, _proceed, _fail, _catcher, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        prefix = f"{self._module}." if self._module else ""
        return f"{prefix}{self._name}/{arities}"


def _catchable_dispatch(dispatch_fn):
    """Wrap a module-predicate dispatch so stdlib exceptions are catchable.

    Module predicates are driven by the top-level trampoline, so a raw Python
    exception raised inside the implementation propagates *outside* any
    enclosing catch/3 Python try-block and escapes solve() uncaught — unlike a
    ``++`` thunk, whose errors the compiler converts. Only ``LogicException``
    is routed through the catcher chain. Convert every other exception to a
    ``LogicException`` carrying ``python_error_term(exc)`` so catch/3 catches
    module-predicate errors the same way it catches ``throw/1`` (F004).
    """
    def wrapped(this_generator, _proceed, _fail, _catcher, *args):
        from clausal.logic.exceptions import LogicException, python_error_term
        try:
            yield from dispatch_fn(this_generator, _proceed, _fail, _catcher, *args)
        except LogicException:
            raise
        except Exception as exc:  # noqa: BLE001 — deliberate boundary conversion
            raise LogicException(python_error_term(exc)) from exc
    return wrapped


def simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(arg1, ..., argN, trail, k) → trampoline protocol.

    Simple-mode functions yield ``None`` for each solution.  The wrapper
    translates to the trampoline protocol where solutions are ``(parent, None)``
    and termination is ``(parent, DONE)``.

    The ``k`` (continuation) parameter is passed as ``None`` since
    trampoline-mode predicates don't use continuations.
    """
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        for _ in simple_fn(*args, None):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


def to_text(val):
    """The plain ``str`` a ``py.*`` wrapper argument denotes, or ``None``.

    Spec §9.4: a wrapper that takes text accepts an **atom** or a **string**,
    and both convert to the same ``str``.  THE FLIP
    (2026-09-06-atoms-as-cells-strings) made routing this through ``str()``
    a live footgun: ``str(("bar",))`` is the Python tuple *repr*
    ``"('bar',)"``, so a wrapper that coerced that way would silently use a
    repr as a filename, a regex, a logger name or a SQL string — during the
    flip that is exactly how a file literally named ``(':memory:',)`` got
    created in the repo root.  Every text coercion in a wrapper routes here.

    - a ``str`` → itself;
    - an ATOM ``("bar",)`` → its spelling;
    - a ``SegString`` / any object with a ``__walk__`` that yields a ``str``
      (a partial string that is now complete) → that ``str``;
    - a list/tuple of char atoms → the string it denotes;
    - a CELL of arity >= 1 → ``None``: a compound is not text.  It does not
      raise here — every caller already documents and implements a fallback
      for "not text" (``logging`` writes the term with the engine's own
      writer, :func:`require_text` raises a type_error), and a raise
      would reach past all of them: ``info(Logger, foo(1))`` must log
      ``foo(1)``, not throw.  The one position where a non-text argument is
      unambiguously an error — a sqlite path/alias/SQL/table — raises at the
      CALL SITE (``py/sqlite.py``'s ``_text``, which is loud on ``None``);
    - anything else (an unbound ``Var``, a number, a non-char list, …) →
      ``None``, likewise.

    What this never does is answer with a Python ``repr``.
    """
    # STAGE 1 of the atoms-as-str flip: the chars carrier ('$chars', text)
    # IS text -- every py-module text position reads it as its str.
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    from clausal.logic.variables import deref as _d  # noqa: PLC0415
    _v = _d(val)
    if is_chars(_v):
        return chars_text(_v)
    if type(val) is str:
        return val                     # STAGE 2: an ATOM -- its spelling is the text (spec §3)
    from clausal.logic.atoms import is_atom as _is_atom, spelling as _spelling
    from clausal.logic.variables import deref
    val = deref(val)
    if type(val) is str:
        return val
    if _is_atom(val):
        return _spelling(val)          # a TEXT position: the atom's spelling -- ``shell(true)`` runs the program `true` (D35)
    walk = getattr(val, "__walk__", None)
    if callable(walk):
        walked = walk()
        if type(walked) is str:
            return walked
        val = walked
    if isinstance(val, tuple) and val and type(val[0]) is str:
        # A cell of arity >= 1: a compound term, not text.  The caller's
        # fallback decides what to do with it — never a repr from here.
        return None
    if isinstance(val, (list, tuple)):
        if not val:
            return ""
        from clausal.logic.runtime._seg_helpers import maybe_promote_to_str
        promoted = maybe_promote_to_str([deref(e) for e in val])
        if is_chars(promoted):
            return chars_text(promoted)    # stage 1: the promotion funnel answers the carrier
        if type(promoted) is str:
            return promoted
    return None


_OPTION_MISSING = object()


class _Symbol(str):
    """A symbolic NAME a py-module hands back (see :func:`symbol`).  Only
    :func:`text_result` reads the tag: it turns the value into the ATOM, a
    plain interned ``str``.  No term ever holds one (the leak rule)."""
    __slots__ = ()


def symbol(name: str) -> str:
    """Tag *name* as a SYMBOLIC identifier for :func:`text_result`: the result
    crosses as an ATOM, not text -- "atom out, text in" (Python-boundary
    spec 2026-09-21; ruled 2026-10-04 for adapter results).  For an
    enum-like name a library hands back: a device platform (``cpu``), a mesh
    axis name, a log level.  Free-form strings (contents, paths, printed
    representations, user data) stay untagged and cross as text.

    Only the RESULT is tagged: an adapter's inputs keep accepting text and
    atoms (``to_text``), and a check-mode result (:func:`unify_result`)
    accepts the text spelling of a symbolic name too."""
    return _Symbol(name)


def has_symbol(v) -> bool:
    """True if *v*, or a list/dict/DictTerm value inside it (the containers
    :func:`text_result` converts), is a :func:`symbol`.  Not a tuple: a
    tuple is a cell and is never converted."""
    if type(v) is _Symbol:
        return True
    if type(v) is list:
        return any(has_symbol(e) for e in v)
    if type(v) is dict:
        return any(has_symbol(e) for e in v.values())
    from clausal.terms import DictTerm  # noqa: PLC0415
    if isinstance(v, DictTerm):
        return any(has_symbol(e) for e in v.data.values())
    return False


def symbols_as_text(v):
    """*v* with every :func:`symbol` in it as TEXT -- the spelling a caller
    may hand in for it (text in)."""
    if type(v) is _Symbol:
        from clausal.logic.cells import chars  # noqa: PLC0415
        return chars(str.__str__(v))
    if type(v) is list:
        return [symbols_as_text(e) for e in v]
    if type(v) is dict:
        return {k: symbols_as_text(e) for k, e in v.items()}
    from clausal.terms import DictTerm  # noqa: PLC0415
    if isinstance(v, DictTerm):
        return DictTerm({k: symbols_as_text(e) for k, e in v.data.items()})
    return text_result(v)


def unify_result(term, v, trail) -> bool:
    """Unify *term* with the py-module result *v* as :func:`text_result`
    makes it.  When *v* holds a :func:`symbol` and that fails, *term* may
    still be its TEXT spelling (``device_platform(D, "cpu")`` as well as
    ``device_platform(D, cpu)``): text in, atom out."""
    from clausal.logic.variables import unify  # noqa: PLC0415
    if not has_symbol(v):
        return unify(term, text_result(v), trail)
    mark = trail.mark()
    if unify(term, text_result(v), trail):
        return True
    trail.undo(mark)
    return unify(term, symbols_as_text(v), trail)


def text_result(v):
    """A py-module RESULT as a term (stage 1 of the atoms-as-str flip, spec
    2026-09-18): a Python str is TEXT, and text is the chars carrier
    ``('$chars', s)``; a :func:`symbol` is the ATOM (a plain interned
    ``str``); a list, dict or DictTerm converts its VALUES (dict keys stay
    what the module made them); everything else is itself.  A tuple is left
    alone -- in term-land a tuple is a cell, whose functor is a str that
    must not be touched."""
    if type(v) is str:
        from clausal.logic.cells import chars  # noqa: PLC0415
        return chars(v)
    if type(v) is _Symbol:
        import sys  # noqa: PLC0415
        return sys.intern(str.__str__(v))
    if type(v) is list:
        return [text_result(e) for e in v]
    if type(v) is dict:
        return {k: text_result(e) for k, e in v.items()}
    from clausal.terms import DictTerm  # noqa: PLC0415
    if isinstance(v, DictTerm):
        return DictTerm({k: text_result(e) for k, e in v.data.items()})
    return v


def option(mapping, name, default=None):
    """The value an options dict holds under the option *name*, or *default*.

    Spec §6.8: a dict literal written in source has ATOM keys —
    ``{url: "…"}`` compiles its key through ``mint``, and ``D.url`` looks up
    ``("url",)``.  A dict built on the PYTHON side (``DictTerm({"url": …})``
    in a test, or a JSON object before §9.2 mints it) has ``str`` keys.  A
    wrapper's option table has to read both, or a source-written options dict
    silently reads as empty and the predicate fails with no diagnosis.

    A third spelling since the ``-double_quotes`` default flipped to chars
    (2026-09-26): ``{"cwd": DIR}`` in a module that declares no mode has a
    STRING key, the chars carrier ``('$chars', 'cwd')``.  An option key is a
    NAME whichever way it was quoted, so the lookup compares by text and
    accepts all three -- measured 2026-09-26: without this, ``process_create``
    with ``{"input": ...}`` ran with no stdin and raised nothing.

    The atom is tried first, because that is what a program actually writes;
    the ``str`` spelling is the Python-side fallback.  *name* is the plain
    spelling — callers never build the key themselves.
    """
    got = _option_lookup(mapping, name)
    # stage 1: a module's own str DEFAULT is text, so it crosses as the carrier
    return text_result(default) if got is _OPTION_MISSING else got


def _option_lookup(mapping, name):
    """*mapping*'s value under the option NAME in any of its three spellings
    -- the atom, the chars carrier, the plain ``str`` -- or ``_OPTION_MISSING``."""
    # ``key_of``, not ``mint``: an option named ``[]`` is the atom ``'[]'``,
    # whose ``mint`` answer is the unhashable empty LIST and would crash the
    # lookup outright (fix round 2, item 2).
    from clausal.logic.atoms import key_of  # noqa: PLC0415
    from clausal.logic.cells import chars  # noqa: PLC0415
    # Since stage 2 of the atoms-as-str flip ``key_of(name)`` IS the interned
    # ``str`` for every name but ``'[]'`` (which keys as NIL), so the plain
    # ``name`` probe is distinct only for that one spelling; it stays for it.
    for key in (key_of(name), chars(name), name):
        got = mapping.get(key, _OPTION_MISSING)
        if got is not _OPTION_MISSING:
            return got
    return _OPTION_MISSING


def has_option(mapping, name) -> bool:
    """Whether an options dict carries *name* under any of its spellings.

    The companion to :func:`option` for the ``"x" in opts`` shape, where a
    missing key and a key holding ``None`` must stay distinguishable.  The
    same three spellings as :func:`option`.
    """
    return _option_lookup(mapping, name) is not _OPTION_MISSING


def text_or_str(val):
    """The ``str`` a wrapper argument denotes, falling back to ``str(val)``.

    The shape every ``py.*`` wrapper needs at a text position that never
    promised a type contract — a header value, a CSV cell, an environment
    value, a URL part, a logger name.  Text (a string or an ATOM, spec §9.4)
    crosses through :func:`to_text`; anything else keeps the ``str()``
    rendering those positions have always had.

    The point is that ``str()`` is the FALLBACK and never the coercion: after
    THE FLIP (2026-09-06-atoms-as-cells-strings) an atom is the arity-0 cell
    ``("bar",)``, so a bare ``str(val)`` would splice the Python tuple repr
    ``"('bar',)"`` into a URL, a CSV file or a log line.

    Eight per-module copies of exactly this had accumulated
    (``csv._field_text`` and ``_deref_row``'s inline twin, ``http._hdr_text``,
    ``logging._text``, ``process._env_text``/``_arg_text``,
    ``url._part_text``, ``uuid._name_text``); every one of them calls here
    now, and a new wrapper should too rather than growing a ninth.

    The sibling shape — text, or a ``type_error(text, …)`` — is
    :func:`require_text`.  The one deliberate non-adopter of
    either is ``sqlite._text``, which RAISES on a non-text argument because a
    sqlite path/alias/SQL/table is unambiguously text.
    """
    text = to_text(val)
    if text is not None:
        return text
    from clausal.logic.variables import deref  # noqa: PLC0415
    return str(deref(val))


def require_text(val, pred, arg=1):
    """The ``str`` a wrapper's text argument denotes; raises when it is not text.

    The companion to :func:`text_or_str` for a position that has a type
    contract: a path, a URL, a host, a command, an algorithm name, a JSON or
    CSV document.  There is no sensible ``str()`` rendering of a compound
    there, so (RULED 2026-10-02) a bound value that is not text raises
    ``type_error(text, Culprit)`` and an unbound one ``instantiation_error``
    -- see :func:`expect_type`.  It never answers ``None`` any more.

    Spec §9.4: text is a string or an ATOM and both convert to the same
    ``str``, so ``read_file('/tmp/x', T)``, ``read_file("/tmp/x", T)`` and a
    ``-double_quotes(chars)`` string all reach the library identically.  THE
    FLIP (2026-09-06-atoms-as-cells-strings) is why this has to be a funnel
    and not an ``isinstance`` gate: under ``-double_quotes(atom)`` a
    source-written ``"…"`` IS the arity-0 cell, so a bare
    ``expect_type(x, str, …)`` would reject every documented call.

    *pred* is the registered predicate name/arity (e.g. ``"read_file/2"``)
    and *arg* the 1-based argument position; the error carries both.

    Ten modules had grown their own copy (``csv``, ``files``, ``hash``,
    ``hmac``, ``http``, ``json``, ``os``, ``process``, ``tcp``, ``url``);
    they all call here now.  The check runs on the DEREFERENCED value so the
    culprit is the term and not the box.
    """
    text = to_text(val)
    if text is not None:
        return text
    from clausal.logic.variables import deref  # noqa: PLC0415
    expect_type(deref(val), str, pred, arg=arg)   # raises: not text
    raise AssertionError("unreachable: expect_type raised")


def to_bytes(val):
    """Convert text (a string or an ATOM, spec §9.4) or bytes to bytes, else None."""
    if isinstance(val, bytes):
        return val
    text = to_text(val)
    if text is not None:
        return text.encode("utf-8")
    return None


# ── Argument checks: wrong type, unbound, out of domain ────────────────────
#
# RULED 2026-10-02: a py-interop predicate handed an argument of the WRONG
# TYPE entirely (``date_add(90, TD, R)``) RAISES ``type_error(Type, Culprit)``
# with the predicate as context; an unbound argument where a value is
# required raises ``instantiation_error`` (:func:`expect_type`,
# :func:`require_text`).  A right-typed value the library rejects as out of
# range or invalid (month 13, an unknown hash name, malformed JSON) RAISES
# ``domain_error(Domain, Culprit)`` (:func:`raise_domain_error`).
#
# Before the rulings each of these failed the goal -- a bare "no"
# indistinguishable from a goal with no solution -- and recorded a
# diagnostic note that only the ``clausal.testing`` failure re-run read.
# Every such site raises now, so the note machinery (``note_mismatch``,
# ``note_rejected_call``, ``collect_type_mismatch_notes``) is gone: the
# error term carries what the note used to say.

#: The numbers a py-interop numeric argument accepts: the engine's numeric
#: tower.  ``bool`` is excluded by :func:`expect_type`, since true/false are
#: atoms (D35), not integers.
NUMBER_TYPES = (int, float, _Decimal, _Fraction)


def _type_name(types) -> str:
    """The ISO type name for an ``isinstance`` spec, where ISO has one
    (``integer``, ``float``, ``number``, ``list``), else the adapter's own
    (``text`` for a string-or-atom position, ``date``, ``timedelta``,
    ``uuid``, ``dict``, ``socket`` ...)."""
    ts = types if isinstance(types, tuple) else (types,)
    if set(ts) >= {int, float}:
        return "number"
    if str in ts:
        return "text"          # a string or an ATOM (spec §9.4), or bytes
    t = ts[0]
    if t is int:
        return "integer"
    if t.__name__ == "DictTerm" or t is dict:
        return "dict"
    return t.__name__.lower()


def expect_type(value, types, pred, *, type_name=None, arg=None,
                culprit=_OPTION_MISSING, expected=None) -> bool:
    """Type check for a py-interop INPUT argument: True, or it raises.

    - *value* an instance of *types* -> ``True`` (``bool`` never passes as
      an ``int``: true/false are atoms, D35);
    - *value* unbound -> ``instantiation_error`` -- the argument is required;
    - otherwise -> ``type_error(Type, Culprit)``, context *pred*.

    Call it only on an argument the predicate needs bound in the mode it is
    in: an output position, or a mode the predicate can still run in with the
    argument unbound, is decided by the caller before it gets here.

    *type_name* is the error's type; by default it is derived from *types*
    (:func:`_type_name`).  *culprit* is the term the error carries when the
    value the predicate computed with is not itself the term the caller
    wrote (datetime's module seam converts a date TERM to a Python date).
    *arg* is the 1-based argument position, carried in the message.
    *expected* is accepted for older callers and ignored.
    """
    if isinstance(value, types) and not (
            type(value) is bool and bool not in (
                types if isinstance(types, tuple) else (types,))):
        return True
    # Import on the failure path only — the success path above is hot
    # (every well-typed interop call passes through it).
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error,
    )
    from clausal.logic.variables import is_var  # noqa: PLC0415
    context = f"{pred}: argument {arg}" if arg is not None else pred
    if is_var(value):
        raise LogicException(instantiation_error(context))
    raise LogicException(type_error(
        type_name or _type_name(types),
        value if culprit is _OPTION_MISSING else culprit,
        context))


def raise_domain_error(domain, culprit, pred, *, arg=None):
    """Raise ``error(domain_error(Domain, Culprit), Context)`` for *pred*.

    For a right-typed argument whose VALUE the predicate or the library
    behind it rejects (RULED 2026-10-02): month 13, an unknown hash
    algorithm, malformed JSON text, iterations <= 0.  *domain* is ISO's
    name where ISO has one (``not_less_than_zero``) and the wrapper's own
    otherwise (``hash_algorithm``, ``csv_record``, ``url``).  *culprit* is the
    TERM the caller wrote (the dereferenced argument, not the ``str`` it
    converted to), and *arg* the 1-based position, carried in the message.
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, domain_error,
    )
    context = f"{pred}: argument {arg}" if arg is not None else pred
    raise LogicException(domain_error(domain, culprit, context)) from None


# ── File-system and network failures (RULED 2026-10-02) ────────────────────
#
# A file-system or network failure in an adapter RAISES an ISO error term
# instead of failing the goal.  ISO 13211-1 8.11.5.3 (open/4) is the model
# for a path: j) a source/sink that does not exist is
# ``existence_error(source_sink, S)``; k) one that exists but cannot be
# opened is ``permission_error(open, source_sink, S)``.  A predicate whose
# MEANING is a test (``file_exists/1``) does not come here: its failure is
# the answer.

import errno as _errno

#: errno -> the ``system_error`` code for a network condition ISO has no
#: term for.  Scryer's ``socket_client_open/3`` and ``http_open/3`` FAIL on
#: all of these (only NotFound and PermissionDenied get a term there), so
#: the codes are this engine's own, in the ``system_error(units_mismatch)``
#: convention (exceptions.system_error).
_NETWORK_CODES = {
    _errno.ECONNREFUSED: "connection_refused",
    _errno.ECONNRESET: "connection_reset",
    _errno.ECONNABORTED: "connection_aborted",
    _errno.EPIPE: "broken_pipe",
    _errno.EHOSTUNREACH: "host_unreachable",
    _errno.ENETUNREACH: "network_unreachable",
    _errno.ENETDOWN: "network_unreachable",
    _errno.EADDRINUSE: "address_in_use",
    _errno.EADDRNOTAVAIL: "address_not_available",
}

#: The same conditions by exception CLASS, for an instance with no errno.
_NETWORK_CLASSES = (
    (ConnectionRefusedError, "connection_refused"),
    (ConnectionResetError, "connection_reset"),
    (ConnectionAbortedError, "connection_aborted"),
    (BrokenPipeError, "broken_pipe"),
)

#: errno -> ``resource_error(R)``.  ``file_descriptors`` is Scryer's term for
#: an exhausted descriptor table (``open/4``'s fallback branch).
_RESOURCE_CODES = {
    _errno.EMFILE: "file_descriptors",
    _errno.ENFILE: "file_descriptors",
    _errno.ENOSPC: "disk_space",
    _errno.EDQUOT: "disk_space",
    _errno.ENOMEM: "memory",
}

#: errno values that mean "this object exists but the operation is not
#: permitted on it" -> ``permission_error(Action, source_sink, Culprit)``.
_PERMISSION_ERRNOS = frozenset({
    _errno.EACCES, _errno.EPERM, _errno.EROFS,
    _errno.EISDIR,        # a directory where a file is needed
    _errno.EEXIST,        # creating what is already there
    _errno.ENOTEMPTY,     # removing a directory that is not empty
    _errno.ETXTBSY,
})


def os_error_term(exc, culprit, pred, *, action="open", arg=None,
                  path=None):
    """The ISO error term for an ``OSError`` raised by an adapter's
    file-system or network call (RULED 2026-10-02).

    *culprit* is the TERM the caller wrote (the path, URL or host), *pred*
    the predicate indicator text (``"read_file/2"``), *action* the ISO
    permission action that fits the operation (``open`` to read, write or
    list; ``modify`` to delete or rename; ``create`` to make a directory or
    a process), and *path* the ``str`` the culprit denotes, used only to
    tell the two meanings of ENOTDIR apart.

    - ENOENT (``FileNotFoundError``) and a DNS "no such host"
      -> ``existence_error(source_sink, Culprit)`` (ISO 8.11.5.3 j);
    - ENOTDIR: a path that goes THROUGH a file does not exist ->
      ``existence_error``; a path that names an existing non-directory
      where a directory is needed is there but cannot be used ->
      ``permission_error``;
    - EACCES/EPERM/EROFS, EISDIR, EEXIST, ENOTEMPTY ->
      ``permission_error(Action, source_sink, Culprit)`` (ISO 8.11.5.3 k:
      the object exists, the operation is not permitted on it);
    - a timeout -> ``resource_error(timeout)``;
    - EMFILE/ENFILE -> ``resource_error(file_descriptors)`` (Scryer),
      ENOSPC -> ``resource_error(disk_space)``, ENOMEM ->
      ``resource_error(memory)``;
    - a network condition -> ``system_error(Code)``, Code one of
      ``connection_refused``, ``connection_reset``, ``connection_aborted``,
      ``broken_pipe``, ``host_unreachable``, ``network_unreachable``,
      ``address_in_use``, ``address_not_available``, ``host_lookup_failed``
      (a DNS failure other than "no such host"), ``tls_failure``;
    - any other errno -> ``system_error(E)``, E the errno's symbolic name in
      lower case (``eio``, ``exdev``); no errno -> ``system_error(io_error)``.

    The OS message goes into the exception's prose, never into the term.
    """
    import socket as _socket_mod  # noqa: PLC0415
    import ssl as _ssl_mod  # noqa: PLC0415
    from clausal.logic.exceptions import (  # noqa: PLC0415
        _error, existence_error, permission_error, system_error,
    )
    from clausal.logic.atoms import mint as _mint  # noqa: PLC0415
    reason = getattr(exc, "strerror", None) or str(exc) or type(exc).__name__
    context = f"{pred}: {reason}"
    if arg is not None:
        context = f"{pred}: argument {arg}: {reason}"

    def resource(name):
        return _error(("resource_error", _mint(name)), context)

    if isinstance(exc, _socket_mod.gaierror):
        if exc.errno in (_socket_mod.EAI_NONAME,
                         getattr(_socket_mod, "EAI_NODATA", None)):
            return existence_error("source_sink", culprit, context)
        return system_error("host_lookup_failed", context)
    if isinstance(exc, TimeoutError):          # socket.timeout, ETIMEDOUT
        return resource("timeout")
    if isinstance(exc, _ssl_mod.SSLError):     # errno is an SSL code, not errno
        return system_error("tls_failure", context)
    code = getattr(exc, "errno", None)
    if code is None:
        # Raised by class with no errno (``http.client.RemoteDisconnected``
        # is a ConnectionResetError built from a message alone): the class
        # says what happened.
        for cls, name in _NETWORK_CLASSES:
            if isinstance(exc, cls):
                return system_error(name, context)
    if code == _errno.ENOENT:
        return existence_error("source_sink", culprit, context)
    if code == _errno.ENOTDIR:
        import os as _os_mod  # noqa: PLC0415
        if path is not None and _os_mod.path.lexists(path):
            return permission_error(action, "source_sink", culprit, context)
        return existence_error("source_sink", culprit, context)
    if code in _PERMISSION_ERRNOS:
        return permission_error(action, "source_sink", culprit, context)
    if code in _RESOURCE_CODES:
        return resource(_RESOURCE_CODES[code])
    if code in _NETWORK_CODES:
        return system_error(_NETWORK_CODES[code], context)
    if code == _errno.ETIMEDOUT:
        return resource("timeout")
    if isinstance(code, int) and code in _errno.errorcode:
        return system_error(_errno.errorcode[code].lower(), context)
    return system_error("io_error", context)


def raise_os_error(exc, culprit, pred, *, action="open", arg=None, path=None):
    """Raise :func:`os_error_term` for *exc* (RULED 2026-10-02)."""
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    raise LogicException(os_error_term(
        exc, culprit, pred, action=action, arg=arg, path=path)) from exc


def raise_http_status(status, culprit, pred, *, reason=None):
    """Raise the ISO error for an HTTP error status (>= 400) answering a
    request for the URL *culprit* (RULED 2026-10-02).

    - 404 Not Found, 410 Gone -> ``existence_error(source_sink, Url)``: the
      resource does not exist (ISO 8.11.5.3 j, as for a missing file);
    - 401 Unauthorized, 403 Forbidden, 407 Proxy Authentication Required ->
      ``permission_error(open, source_sink, Url)``: it exists and may not be
      opened (8.11.5.3 k);
    - any other status S -> ``system_error(http_status(S))``.

    Scryer's ``http_open/3`` has no term to match: it reports every status
    as a VALUE (the ``status_code(S)`` option), which is what this engine's
    ``request/3`` does too; only the predicates that answer a body alone
    (``get``, ``post``, ``json_get``, ``json_post``) come here.
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, existence_error, permission_error, system_error,
    )
    from clausal.logic.atoms import mint as _mint  # noqa: PLC0415
    context = f"{pred}: HTTP {status}" + (f" {reason}" if reason else "")
    if status in (404, 410):
        term = existence_error("source_sink", culprit, context)
    elif status in (401, 403, 407):
        term = permission_error("open", "source_sink", culprit, context)
    else:
        term = system_error((_mint("http_status"), status), context)
    raise LogicException(term) from None


# ── Malformed input text (RULED 2026-10-02: raise) ─────────────────────────
#
# Text an adapter READS from a source -- an HTTP response body, a YAML
# file -- that is not in the expected encoding or grammar raises
# ``syntax_error(Kind)``, ISO's term for input text read/1 cannot parse
# (7.12.2 i).  Scryer raises the same family for bytes that are not UTF-8
# on a text stream: ``get_char/2`` on such a file throws
# ``error(syntax_error(invalid_data), get_char/2)``.  Kinds used here:
#
# - ``invalid_data``  -- bytes that are not UTF-8 text (Scryer's term);
# - ``invalid_json``  -- text that is not JSON;
# - ``invalid_yaml``  -- text that is not YAML.


def syntax_error_term(kind, pred, reason=None):
    """``error(syntax_error(Kind), Pred)`` with *reason* as the prose."""
    from clausal.logic.exceptions import _error  # noqa: PLC0415
    from clausal.logic.atoms import mint as _mint  # noqa: PLC0415
    context = f"{pred}: {reason}" if reason else pred
    return _error(("syntax_error", _mint(kind)), context)


def raise_syntax_error(kind, pred, reason=None, *, cause=None):
    """Raise :func:`syntax_error_term` (RULED 2026-10-02)."""
    from clausal.logic.exceptions import LogicException  # noqa: PLC0415
    raise LogicException(syntax_error_term(kind, pred, reason)) from cause



# ── Stdlib import helper ─────────────────────────────────────────────────────


def _import_stdlib(name):
    """Import a stdlib/third-party module, bypassing clausal's ModulesFinder.

    Prevents circular imports when a ``py/*.py`` implementation file has
    the same name as the Python module it wraps (e.g. ``py/uuid.py``
    wrapping stdlib ``uuid``).
    """
    import importlib
    from clausal.import_hook import ModulesFinder

    ModulesFinder._resolving.add(name)
    try:
        return importlib.import_module(name)
    finally:
        ModulesFinder._resolving.discard(name)
