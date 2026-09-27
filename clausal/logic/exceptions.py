"""clausal.logic.exceptions — logic-level exception handling (V2-14).

LogicException wraps a logic term for throw/catch control flow.
It is a Python Exception subclass, so:
- .clausal code uses catch(Goal, E, Recovery) / throw(Error)
- Python code can try: ... except LogicException as e: e.term
- Builtins can raise it with structured error terms

Structured error term helpers follow ISO Prolog conventions:
    error(type_error(Type, Culprit), Context)
    error(instantiation_error, Context)
    error(existence_error(ObjType, Culprit), Context)
    error(permission_error(Operation, ObjType, Culprit), Context)

Every term is a plain CELL (slice 2 of the Compound retirement,
2026-09-27): ``('error', ('type_error', 'atom', 1), Context)``.  Read one
from Python with ``clausal.cell_functor`` / ``clausal.cell_args``.
``Context`` is what Scryer puts there (operator ruling 2026-09-27: when
Scryer and SWI differ, Scryer): the predicate indicator of the builtin that
raised (``atom_length/2``), the missing indicator itself for a missing
procedure, or an unbound variable when there is none.  Explanatory prose
stays off the term, on the exception's ``.message``.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from clausal.logic.cells import chars as _chars  # stage 1: the chars carrier
from clausal.logic.atoms import is_atom, mint, spelling
from clausal.logic.variables import Var
from clausal.terms import Add, Compound, Div, FloorDiv, Mod, Mult, Negate, Pow, Sub
from clausal.terms import term_writeq

# ── The is/== hint ────────────────────────────────────────────────────────────
#
# `is/2` unifies, so ``R is 10000 // 4`` binds R to the *term* ``FloorDiv(10000,
# 4)``; ``==`` is the operator that evaluates.  That is deliberate, but `is` is
# spelled like Prolog's arithmetic-evaluation operator, so the term is written
# by accident and only surfaces later, where a number was required — as
# ``type_error(number, FloorDiv(...))``.  The culprit is in hand there, so say
# what it is.

#: The nodes ``==`` evaluates and ``is`` does not.  ``UnaryPlus`` is absent on
#: purpose: ``++X`` is this language's Python-interop marker, not arithmetic
#: (``DAYS is ++DELTA.days`` — reading a Python ``timedelta`` attribute — is
#: correct code).
ARITH_OPERATOR_TERMS = (Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)

#: Expected-types that mean "a number was required here".  ``evaluable`` is
#: excluded because its two raise sites in clpfd let arithmetic terms through
#: by construction, so it can never carry one as its culprit.
_NUMERIC_EXPECTATIONS = frozenset({"number", "integer"})

#: The half-sentence that turns the fact into an actionable one.  It states what
#: the two operators do — true whoever built the term, which matters because the
#: culprit need not have come from an `is` at all.
IS_VS_EQ_HINT = (
    "`is` unifies without evaluating: `X is <expr>` binds X to the term, "
    "`X == <expr>` binds X to its value"
)


def is_arith_operator_term(value: Any) -> bool:
    """True when *value* is an arithmetic operator term rather than a number."""
    return isinstance(value, ARITH_OPERATOR_TERMS)


def render_arith_operator_term(value: Any) -> str:
    """*value* in surface syntax (``10000 // 4``), or its repr if that fails.

    ``BinOp.__str__`` already spells the operator; the fallback exists because a
    diagnostic must not be able to raise on top of the error it is explaining.
    """
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - a hint may not out-fail its own error
        return repr(value)


def term_functor_args(term: Any) -> tuple[Any, tuple] | None:
    """``(functor, args)`` of a compound error-term node, or None.

    Reads a cell (the spelling every engine builder uses since slice 2 of
    the Compound retirement) and, at the Python boundary, a ``Compound`` a
    caller built by hand, alike.  An atom or any other shape is None.
    """
    if type(term) is tuple and term and type(term[0]) is str:
        return term[0], term[1:]
    if isinstance(term, Compound):
        return term.functor, tuple(term.args)
    return None


def arith_in_numeric_position_hint(term: Any) -> str | None:
    """The is/== note for ``error(type_error(number, <arith term>), _)``, else None.

    Reads only the term already carried by the exception — there is no record of
    which goal built the culprit, and none is needed: that it is an unevaluated
    operator term where a number was required is a structural fact.
    """
    outer = term_functor_args(term)
    if outer is None or outer[0] != "error" or len(outer[1]) != 2:
        return None
    inner = term_functor_args(outer[1][0])
    if inner is None or inner[0] != "type_error" or len(inner[1]) != 2:
        return None
    expected, culprit = inner[1]
    # THE FLIP (spec §6.4): the formal term's TYPE NAME is an ATOM -- read its
    # spelling.  A ``str`` is still accepted (a hand-built term, or one thrown
    # from ``.clausal`` under ``-double_quotes(chars)``); anything else, and
    # in particular an unhashable term, must not make the set membership below
    # raise on top of the error this note exists to explain.
    if is_atom(expected):
        expected = spelling(expected)
    if not isinstance(expected, str) or expected not in _NUMERIC_EXPECTATIONS:
        return None
    if not is_arith_operator_term(culprit):
        return None
    return (f"`{render_arith_operator_term(culprit)}` is an unevaluated "
            f"arithmetic term, not a number. {IS_VS_EQ_HINT}")


def render_error_term(term: Any) -> str:
    """The term as Scryer prints an uncaught error: ``writeq`` text with
    operators, e.g. ``error(type_error(evaluable,foo/0),(is)/2)``.

    Ruling R2 of the Compound retirement (2026-09-27): the message shows the
    TERM, not the Python object, so it reads the same whether the term is a
    ``Compound`` or a cell.  Building an exception must never itself raise,
    so a term the renderer cannot handle falls back to its ``repr``.

    Variables are named within the term (``local_vars``): a variable that
    occurs once prints ``_``, one that occurs more than once ``_1``, ``_2``,
    ...  Scryer prints its own internal ``_N`` there, but ``N`` would be the
    engine's global variable counter, and an error with no culprit indicator
    carries a fresh variable (``error(type_error(atom,1),_)``), so two raises
    of the same error would read differently.
    """
    try:
        return term_writeq(term, local_vars=True)
    except Exception:  # noqa: BLE001 - a message may not out-fail its error
        return repr(term)


class LogicException(Exception):
    """Exception carrying a logic term for throw/catch.

    ``.term`` is the thrown term.  ``.message`` is the explanatory prose, or
    None: the text a builder's raise site wrote after the indicator
    (``"solve/1: the goal is unbound"``), which stays off the term because
    the second argument of ``error/2`` is only what Scryer puts there.  Pass
    *message* to set it; otherwise it is the prose a builder recorded for
    *term* (:func:`error_prose`).  The rendered message is the term, then
    ``": "`` and the prose when there is any::

        Uncaught logic exception: error(instantiation_error,solve/1): the goal is unbound
    """

    def __init__(self, term: Any, message: str | None = None) -> None:
        self.term = term
        self.message = message if message is not None else error_prose(term)
        text = f"Uncaught logic exception: {render_error_term(term)}"
        if self.message:
            text = f"{text}: {self.message}"
        super().__init__(text)

    def __str__(self) -> str:
        """The stored message, plus the is/== note when the term earns it.

        Computed here rather than in ``__init__`` so that a LogicException a
        ``catch/3`` swallows — the common case, since these terms are control
        flow — pays nothing for a note nobody reads.  ``args[0]`` is left alone
        so the note cannot leak into a caught term via ``python_error_term``
        (``catch/3`` reads ``.term`` for a LogicException and only falls back to
        ``python_error_term`` for a stray Python exception).

        A ``__str__`` that can raise loses every traceback that touches it, so
        the hint is contained: no note is strictly better than no message.
        """
        message = super().__str__()
        try:
            note = arith_in_numeric_position_hint(self.term)
        except Exception:  # noqa: BLE001 - see the docstring
            return message
        return f"{message}\nnote: {note}" if note else message


class DispatchTargetError(LogicException):
    """A goal's callee resolved to something that is not a predicate at all.

    W3 of the PredicateMeta retirement (ruled 2026-09-22).  Raised by
    ``predicate._dispatch_at`` when the object a goal resolved to has no
    ``_get_dispatch`` -- a MODULE, most often, when a dotted name lands on a
    package instead of on a predicate inside it; any other Python value takes
    the same exit.  Before W3 that fell through to ``obj._get_dispatch()`` and
    surfaced as CPython's own ``AttributeError: module 'x.y' has no attribute
    '_get_dispatch'``, whose wording downstream gates had to match to
    classify the failure.  The CLASS NAME is the stable token now: it is in
    the rendered text (in the message itself, so a chained or re-raised copy
    still carries it), and the term is the ISO ``type_error(callable, Target)``
    so ``catch/3`` and every ``except LogicException`` see it as they see the
    atom case (``existence_error(procedure, ...)``, deliberately a DIFFERENT
    shape: "resolved to data" and "resolved to a module" are told apart by
    it).
    """


def python_error_term(exc: Exception) -> tuple:
    """Convert a Python exception to a catchable logic term.

    Produces ``ClassName(Message)`` — the cell ``('ClassName', Message)``
    whose functor is the exception class name and whose single argument is
    the message string.
    The functor is TitleCase, so no ``.clausal`` catcher can be WRITTEN
    against it (TitleCase in a Clausal position is a load-time error); the
    term is observable only through a catch-all variable, or via the
    ``.term`` of the ``LogicException`` it travels in::

        catch(Goal, _, Recovery)           % any exception
        catch(Goal, E, (write(E), fail))   % E = ValueError("...")

    A Python exception is caught by CLASS with a ``++`` catcher — the class
    reached through the module's import list or a builtin — which
    :func:`catch_match` matches against the live exception object::

        catch(Goal, ++ValueError, Recovery)        % isinstance, subclasses in
        catch(Goal, ++ValueError(M), Recovery)     % also binds M to the message

    This transliteration discards the exception OBJECT, so it cannot serve a
    ``++`` catcher on its own — :func:`catch_match` receives the live
    exception alongside this structural term (and unwraps the module-predicate
    boundary wrapper for it).
    """
    return (type(exc).__name__, str(exc))


def _dual_typed_match(exc: BaseException, cls: type) -> bool:
    """True when the logic ball *exc* is ALSO an instance of the non-logic
    exception class *cls* by a base of its own -- never for a class that is
    merely a base of ``LogicException`` itself (``Exception``,
    ``BaseException``), which every logic ball is an instance of."""
    return isinstance(exc, cls) and not issubclass(LogicException, cls)


def catch_match(catcher: Any, term: Any, exc: BaseException, trail: Any) -> bool:
    """Match a ``catch/3`` catcher against a raised exception.

    ``catcher`` is the evaluated catcher expression, ``term`` the structural
    ball (``LogicException.term``, or :func:`python_error_term` of a stray
    Python exception), ``exc`` the ORIGINAL exception object.

    A catcher that evaluated to a Python exception CLASS (``++ValueError``)
    matches by ``isinstance`` — subclasses in, Python semantics — and never a
    logic ``throw/1`` ball: its ``LogicException`` wrapper is excluded from
    both ++ arms unless the catcher names ``LogicException`` itself.  One that
    evaluated to an exception INSTANCE (``++ValueError(M)`` — the escape
    constructs the instance with ``M`` dereferenced) matches by isinstance on
    its type and unifies ``catcher.args`` against ``exc.args``, binding ``M``
    to the real message.  Anything else keeps the structural ``unify`` against
    ``term``, unchanged.

    Rationale: the transliterated ball defeats ``++`` (no object left to
    match) and a bare CamelCase functor catcher is an ISO translation hazard
    (initial-capital reads as a VARIABLE there, silently widening a specific
    catcher to a catch-all).  See
    todo/error-bridge-transliterates-python-exceptions-instead-of-using-plus-plus.md.
    """
    from clausal.logic.variables import deref, unify  # noqa: PLC0415

    catcher = deref(catcher)
    # A Python exception raised inside a module predicate reaches the
    # catcher chain wrapped (``_catchable_dispatch``: ``LogicException(
    # python_error_term(exc)) from exc``).  The wrapper carries the
    # transliterated ``ClassName(Message)`` term — a TitleCase spelling no
    # catcher can be written in any more — so a ``++`` catcher must see the
    # ORIGINAL exception: unwrap exactly that shape (a non-logic cause whose
    # class name is the wrapper's functor) and match the Python arms on it.
    #
    # The unwrap is scoped to catchers that are NOT themselves (a subclass
    # or instance of) ``LogicException``: the wrapper IS one, so
    # ``++LogicException`` keeps matching it — Python semantics, the way
    # ``++Exception`` matches the cause.
    cause = getattr(exc, "__cause__", None)
    catcher_is_logic = (
        (isinstance(catcher, type) and issubclass(catcher, LogicException))
        or isinstance(catcher, LogicException))
    if (not catcher_is_logic
            and isinstance(exc, LogicException)
            and isinstance(cause, BaseException)
            and not isinstance(cause, LogicException)
            and (term_functor_args(getattr(exc, "term", None))
                 or (None,))[0] == type(cause).__name__):
        exc = cause
    if isinstance(catcher, type) and issubclass(catcher, BaseException):
        # A ++ catcher is the PYTHON side of the boundary only: a logic
        # throw/1 ball travels as a LogicException, which subclasses
        # Exception, so a bare isinstance would let ``++Exception`` swallow
        # logic balls (roborev job 18). Those keep their own catch-all
        # spelling, ``catch(G, _, R)`` — a ++ class matches a logic ball
        # only when it names LogicException (or a subclass) explicitly --
        # or when the ball is ALSO an instance of that Python class, which a
        # DUAL-typed engine error is (since 2026-09-25 ``PredicateArityMismatchError``
        # is a LogicException and a TypeError, and ``PredicateNotFoundError``
        # a LogicException and a KeyError, so ``++TypeError`` / ``++KeyError``
        # keeps catching it).  A mere BASE of LogicException (``++Exception``,
        # ``++BaseException``) still never matches a logic ball.
        if isinstance(exc, LogicException) and not issubclass(
                catcher, LogicException):
            return _dual_typed_match(exc, catcher)
        return isinstance(exc, catcher)
    if isinstance(catcher, BaseException):
        if (isinstance(exc, LogicException)
                and not isinstance(catcher, LogicException)
                and not _dual_typed_match(exc, type(catcher))):
            return False
        if not isinstance(exc, type(catcher)):
            return False
        catcher_args = list(catcher.args)
        # stage 1: a Python exception's message (a str) crosses as TEXT
        exc_args = [_chars(a) if type(a) is str else a for a in exc.args]
        return len(catcher_args) == len(exc_args) and unify(
            catcher_args, exc_args, trail
        )
    return unify(catcher, term, trail)


#: A predicate indicator spelled as text: ``name/N``, or ``(op)/N`` for an
#: operator name as Scryer prints one.  An unparenthesised name has no
#: whitespace, parenthesis, ``/`` or ``:``, so free prose that merely contains
#: a slash (``a/b/2``, ``m:p/2``, or a pseudo indicator such as
#: ``reify(lt)/3``) never reads as an indicator.
_PI_TEXT = re.compile(r"(?:\((?P<op>[^\s()]+)\)|(?P<name>[^\s()/:]+))/(?P<arity>\d+)")


def indicator_from_text(text: str) -> tuple | None:
    """The indicator cell ``('/', Name, Arity)`` that *text* spells, or None.

    ``"atom_length/2"`` -> ``atom_length/2``; ``"(is)/2"`` and ``"is/2"``
    -> ``(is)/2``; ``"call/N"`` or ``"clpfd expression"`` -> None.
    """
    m = _PI_TEXT.fullmatch(text)
    if m is None:
        return None
    return ("/", mint(m.group("op") or m.group("name")), int(m.group("arity")))


def _is_indicator(term: Any) -> bool:
    fa = term_functor_args(term)
    return fa is not None and fa[0] == "/" and len(fa[1]) == 2


#: The prose a builder's raise site wrote, kept OFF the term (operator
#: ruling 2026-09-27: the second argument of ``error/2`` is what Scryer puts
#: there, the bare indicator).  A builder returns a plain cell, which cannot
#: carry an attribute, so the prose waits here, keyed by the term's identity,
#: for the ``LogicException`` that carries the term to pick it up as its
#: ``.message``.  Each entry holds the term itself, so its ``id`` cannot be
#: reused while the entry lives; the table is bounded (oldest out first) so a
#: term that is built and never raised, and whatever its culprit holds, is
#: kept alive for at most ``_PROSE_MAX`` later builds.
_PROSE: dict[int, tuple[Any, str]] = {}
_PROSE_MAX = 128
_PROSE_LOCK = threading.Lock()


def _with_prose(term: tuple, prose: str | None) -> tuple:
    if prose:
        with _PROSE_LOCK:
            _PROSE[id(term)] = (term, prose)
            while len(_PROSE) > _PROSE_MAX:
                del _PROSE[next(iter(_PROSE))]
    return term


def error_prose(term: Any) -> str | None:
    """The explanatory prose a builder recorded for *term*, or None."""
    with _PROSE_LOCK:
        entry = _PROSE.get(id(term))
    return entry[1] if entry is not None and entry[0] is term else None


def _context(context: Any) -> tuple[Any, str | None]:
    """``(Context, Prose)`` for a builder's *context*: the second argument
    of ``error/2`` as Scryer puts it there, and the explanatory text that
    goes to the Python exception instead.

    Raise sites pass TEXT, in one of three forms:

    * an indicator alone, ``"atom_length/2"`` -> ``atom_length/2``, no prose;
    * an indicator, ``": "``, prose, ``"solve/1: the goal is unbound"`` ->
      ``solve/1``, prose ``"the goal is unbound"``;
    * prose with no leading indicator, ``"clpfd expression"`` -> an unbound
      variable (Scryer's library code throws ``error(E, _)`` when there is
      no culprit indicator), prose the whole text; the empty text -> an
      unbound variable, no prose.

    Any other value (an indicator term, a variable, a context term a caller
    built) IS the second argument, with no prose.
    """
    if type(context) is str:
        if not context:
            return Var(), None
        head, sep, rest = context.partition(": ")
        pi = indicator_from_text(head)
        if pi is not None:
            return pi, (rest if sep and rest else None)
        return Var(), context
    if context is None:
        return Var(), None
    return context, None


def _error(formal: Any, context: Any) -> tuple:
    second, prose = _context(context)
    return _with_prose(("error", formal, second), prose)


# ── Structured error term helpers ─────────────────────────────────────────────


def _name_atom(name: Any) -> Any:
    """*name* as an ATOM when it is a spelling, unchanged otherwise.

    Spec §6.4: the type/domain/operation name in a formal error term is an
    atom.  These constructors are also reachable with a name that is not a
    spelling at all — ``throw/1`` can put any term in the type slot, and
    ``must_be/2`` forwards whatever the caller wrote — and building an
    exception must never itself raise, so a non-``str`` passes through as the
    term it is rather than tripping ``mint``'s type check.
    """
    return mint(name) if type(name) is str else name


def type_error(expected_type: str, culprit: Any, context: Any = "") -> tuple:
    """Build error(type_error(Type, Culprit), PI).

    Spec §6.4 (2026-09-06-atoms-as-cells-strings): the formal term's
    type/domain/operation NAMES are atoms, minted here so a ``catch/3``
    pattern written in source matches them.  *Culprit* is whatever term was
    at fault and is not touched.  *context* is the raise site's text
    (``"atom_length/2"``, ``"solve/1: why"``): its leading indicator becomes
    the second argument, as Scryer puts it, and any prose goes to the
    exception's ``.message`` (:func:`_context`); so for every builder below.
    """
    return _error(("type_error", _name_atom(expected_type), culprit), context)


def instantiation_error(context: Any = "") -> tuple:
    """Build error(instantiation_error, PI)."""
    return _error(mint("instantiation_error"), context)


def system_error(code: str, context: Any = "") -> tuple:
    """Build error(system_error(Code), PI).

    ISO 13211-1 §7.12.2 lists ``system_error`` for errors outside the
    standard's own catalogue — as a bare ATOM. This engine puts its own
    error CODE inside it, ``system_error(units_mismatch)``, so a ``catch/3``
    pattern can select one kind (``units_mismatch``, ``units_undetermined``,
    ``units_unsupported``, …) without matching every system error. That is
    a deliberate, recorded deviation (operator's ruling 2026-09-12 after
    discussion with Markus Triska): a portable ``error(system_error, _)``
    pattern does not match these terms. *Code* is minted as an atom like
    the names in :func:`type_error`; *context* as in :func:`type_error`.
    """
    return _error(("system_error", _name_atom(code)), context)


def existence_error(obj_type: str, culprit: Any, context: Any = "") -> tuple:
    """Build error(existence_error(ObjType, Culprit), PI).

    For a missing PROCEDURE, Scryer's second argument is the missing
    indicator itself, whichever builtin found it missing
    (``call(nosuch, 1)`` -> ``error(existence_error(procedure,nosuch/1),
    nosuch/1)``), so an indicator *culprit* is the second argument here too
    and the whole context text becomes prose.
    """
    formal = ("existence_error", _name_atom(obj_type), culprit)
    if obj_type == "procedure" and _is_indicator(culprit):
        prose = None
        if type(context) is str and context:
            head, sep, rest = context.partition(": ")
            same = indicator_from_text(head) == _as_cell(culprit)
            prose = (rest or None) if same else context
        return _with_prose(("error", formal, culprit), prose)
    return _error(formal, context)


def _as_cell(t: Any) -> Any:
    fa = term_functor_args(t)
    return t if fa is None else (fa[0], *fa[1])


def dangling_handle_indicator_and_why(
    module_name: str, name: str, arity: int, loaded: bool,
) -> tuple[tuple, str]:
    """The ``Name/Arity`` indicator and situation phrase for a MANGLED
    predicate-handle atom (``module<US>name``, W4's ``-hide`` spelling) that
    failed to resolve at a goal-dispatch entry point -- either its owning
    module was never loaded, or the module loaded but the predicate is not
    defined in it.

    Ruling 2026-09-24 (``todo/mangled-goal-culprit-terms-are-malformed-
    2026-09-23.md``): BOTH situations raise ``existence_error(procedure,
    Name/Arity)`` -- one vocabulary, ``procedure`` not ``module`` -- and are
    told apart only in the phrase this returns (which the caller folds into
    its own context string), never in the indicator.  *name* and
    *module_name* must already be the DEMANGLED halves (the caller's job,
    via ``atoms.demangle`` -- this function never sees the ``\\x1f``
    spelling and so cannot leak it): a catchable term must be a clean ground
    term, and no conforming program can write the mangled spelling anyway,
    so it must never appear in anything a ``catch/3`` pattern can match.
    """
    indicator = ("/", mint(name), arity)
    if loaded:
        why = f"{name}/{arity} is not defined in module {module_name!r}"
    else:
        why = (f"module {module_name!r} is not loaded, so the predicate "
               f"handle {name}/{arity} cannot resolve")
    return indicator, why


def string_goal_error(goal: str, extra_arity: int = 0,
                      context: str = "") -> tuple:
    """The error a STRING in goal position raises (Task 15 item 3, ruled
    2026-09-07).

    A string is the list of its char atoms, and a non-empty list is the
    compound ``'.'/2`` — so a string goal IS callable (``callable("foo")`` is
    true, §6.3) and what is wrong with it is that no procedure ``'.'/2`` is
    defined.  That makes it an ``existence_error(procedure, '.'/2)``, not the
    ``type_error(callable, …)`` the flip first gave it; the two answers
    together — "callable" and "not callable" for one term — could not both
    stand.  Scryer answers ``existence_error(procedure, './3')`` for
    ``call("foo", X)``, which is this rule with one folded argument.

    *extra_arity* is the number of arguments ``call/N`` folds onto the goal,
    so ``call("foo")`` names ``'.'/2`` and ``call("foo", X)`` names ``'.'/3``.
    The EMPTY string is ``[]``, the atom ``'[]'``, so it names ``'[]'/N``
    instead (Scryer: ``call("")`` → ``existence_error(procedure, []/0)``).

    *context* is the caller's position (``"call/N"``, ``"solve/1"``), kept so
    the diagnostic says where the string was written.

    The two cases get DIFFERENT prose (fix round 3, item 6): a non-empty
    string really is the list of its characters, but ``[]``/``""``/``()``/
    ``b""`` is the reserved atom ``'[]'`` and has no characters to speak of,
    so the "list of its characters" sentence read as nonsense for it.
    """
    if context == "call/N":
        # The builtin that raised is call/N at this N: ISO names it
        # (Scryer: ``call(_, 1)`` -> context ``call/2``).
        context = f"call/{extra_arity + 1}"
    if goal:
        name, arity = ".", 2 + extra_arity
        why = (f"a string goal is the list of its characters — the compound "
               f"{name!r}/{arity} — and no such procedure is defined")
    else:
        name, arity = "[]", extra_arity
        why = (f"the empty list is not a callable term — it is the atom "
               f"{name!r}, and no procedure {name!r}/{arity} is defined")
    indicator = ("/", mint(name), arity)
    return existence_error(
        "procedure", indicator,
        f"{context}: {why}; write the ATOM (a bare name, or mint(...) from "
        f"Python) or a cell goal such as ('name', Arg)",
    )


def permission_error(
    operation: str, obj_type: str, culprit: Any, context: Any = ""
) -> tuple:
    """Build error(permission_error(Op, ObjType, Culprit), PI)."""
    return _error(("permission_error", _name_atom(operation),
                   _name_atom(obj_type), culprit), context)


def domain_error(domain: str, culprit: Any, context: Any = "") -> tuple:
    """Build error(domain_error(Domain, Culprit), PI).

    ISO domain error: *culprit* is the right Python/logic type but its value is
    outside the set the operation admits (e.g. an unknown type name given to
    must_be/2, where the TYPE — not the term — is wrong)."""
    return _error(("domain_error", _name_atom(domain), culprit), context)


def evaluation_error(error_type: str, context: Any = "") -> tuple:
    """Build error(evaluation_error(ErrorType), PI).

    ISO evaluation errors: ``zero_divisor``, ``undefined``, ``float_overflow``,
    ``int_overflow``, ``underflow`` — a numeric operation is mathematically
    undefined for its operands (e.g. a non-invertible modular inverse)."""
    return _error(("evaluation_error", _name_atom(error_type)), context)
