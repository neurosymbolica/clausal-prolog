"""clausal.logic.predicate — Predicate-as-Class via PredicateMeta.

PredicateMeta turns a class into a first-class predicate:
  - Class-level clause storage, dispatch, and signature
  - Locking to prevent cross-module mutation
  - __call__ override for partial term creation (missing fields → Var())
  - __init__, __eq__, __repr__, __match_args__ — no @dataclass needed

Usage:
    class fib(metaclass=PredicateMeta):
        _fields = ('n', 'f')

    # fib is a class (not a singleton instance)
    # fib(n=0) creates a term with f=Var()
    # fib._clauses, fib._get_dispatch(), fib._assertz(clause), etc.
"""

from __future__ import annotations

import dataclasses
import os
import re
import sys
import textwrap
from typing import Any, Callable


_MISSING = object()  # sentinel for "field not provided"


# ── Attributable term-construction errors ────────────────────────────────────
#
# Constructing a term whose keyword names do not match the bound class's
# ``_fields`` used to surface as a bare, context-free
#
#     TypeError: __init__() got an unexpected keyword argument 'arg_1'
#
# with no functor, no field names and no source location.  See
# ``todo/functor-field-name-mismatch-diagnostic.md``.  Two distinct authoring
# mistakes produce that identical message, and the error below names which one
# it is, because that is what lets an author pick a *different* fix instead of
# re-rolling the same one.

# ``arg_0`` .. ``arg_N`` — the placeholder field names a directive-minted class
# carries until a real clause unseats it (see ``_unseat_directive_minted`` in
# clausal/templating/term_rewriting.py).
_PLACEHOLDER_FIELD_RE = re.compile(r"\Aarg_\d+\Z")

# Directory of the ``clausal`` package, used to skip engine frames when
# attributing a source site to user code.
_CLAUSAL_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# How far to walk the stack looking for a user frame before giving up.
_SITE_SEARCH_DEPTH = 12


def _looks_like_logic_var(name: str) -> bool:
    """True for a Clausal logic-variable spelling (``_x`` or ``ALLCAPS``).

    Mirrors ``clausal.templating.term_rewriting._is_logic_var_name``; kept
    local so this module stays free of a templating import.
    """
    if name == "_" or name.startswith("__"):
        return False
    if name.startswith("_"):
        return True
    return name.isupper()


def _all_placeholders(names: tuple[str, ...]) -> bool:
    """True if *names* is non-empty and entirely ``arg_N`` placeholders."""
    return bool(names) and all(_PLACEHOLDER_FIELD_RE.match(n) for n in names)


def _source_site(depth: int) -> tuple[str, int] | None:
    """Return ``(filename, lineno)`` of the nearest user frame above *depth*.

    A ``.clausal`` frame is preferred; otherwise the first frame outside the
    ``clausal`` package wins, so a term built from Python is attributed to the
    Python caller rather than to engine internals.  Returns ``None`` when the
    stack yields nothing useful.
    """
    try:
        frame = sys._getframe(depth)  # noqa: SLF001
    except ValueError:  # pragma: no cover — stack shallower than expected
        return None
    for _ in range(_SITE_SEARCH_DEPTH):
        if frame is None:
            return None
        filename = frame.f_code.co_filename
        if filename.endswith(".clausal") or not filename.startswith(
            _CLAUSAL_PKG_DIR
        ):
            return (filename, frame.f_lineno)
        frame = frame.f_back
    return None


def _format_site(site: tuple[str, int] | None) -> str:
    return f"{site[0]}:{site[1]}" if site else "<unknown>"


def _format_fields(names: tuple[str, ...]) -> str:
    return f"({', '.join(names)})"


def _camel_case(name: str) -> str:
    """``ash_query_key`` → ``AshQueryKey`` — a legal -import_from alias."""
    return "".join(part.title() for part in name.split("_") if part) or "Alias"


class ClausalTermConstructionError(TypeError):
    """A term was built with field names its bound class does not have.

    A ``TypeError`` subclass so existing ``except TypeError`` handlers keep
    working.  Carries the functor, both field-name tuples, and both source
    locations as attributes for programmatic consumers.
    """

    def __init__(
        self,
        message: str,
        *,
        functor: str,
        arity: int,
        supplied_fields: tuple[str, ...],
        registered_fields: tuple[str, ...],
        registered_at: tuple[str, int] | None,
        constructed_at: tuple[str, int] | None,
    ) -> None:
        super().__init__(message)
        self.functor = functor
        self.arity = arity
        self.supplied_fields = supplied_fields
        self.registered_fields = registered_fields
        self.registered_at = registered_at
        self.constructed_at = constructed_at


def _construction_hint(
    functor: str,
    supplied: tuple[str, ...],
    registered: tuple[str, ...],
) -> str:
    """Name the *class* of authoring mistake behind a field-name mismatch."""
    if not registered:
        # The bound class is a 0-arity ATOM but arguments were supplied.  Under
        # the snake_case convention a vocabulary atom and a predicate routinely
        # share a spelling; the import binds last and wins.  See "Phenomenon A"
        # in implementation_plans/dict-atom-keys-vs-predicates.md.
        confidence = (
            "almost certainly"
            if all(_looks_like_logic_var(n) for n in supplied)
            else "likely"
        )
        n = len(supplied)
        body = (
            f"{functor} resolved to a 0-arity atom, but it was called with "
            f"{n} argument(s) — {confidence} an imported atom is shadowing a "
            f"same-named predicate. A module that both exports the predicate "
            f"{functor}/{n} and imports the atom {functor} binds the atom "
            f"last, so every call constructs the atom. Fix: un-export "
            f"{functor}/{n}, or import the atom under an alias — "
            f"-import_from(vocab, [alias({functor}, {_camel_case(functor)})]) "
            f"— or keep the key a string."
        )
    elif len(supplied) > len(registered):
        # More arguments than the class has fields.  Arity — unlike field
        # names — is the functor's cross-module contract, so this is never a
        # cosmetic disagreement: some declaration of this name is wrong.
        body = (
            f"{functor} takes {len(registered)} argument(s) but "
            f"{len(supplied)} were supplied. A functor name has exactly one "
            f"arity in Clausal, so a second declaration of {functor} with a "
            f"different arity — or an imported {functor} of another arity "
            f"shadowing this one — cannot be reconciled. Fix: give every "
            f"declaration and clause head of {functor} the same number of "
            f"arguments, or rename one of them."
        )
    elif _all_placeholders(supplied) or _all_placeholders(registered):
        body = (
            "a functor minted by a directive keeps placeholder arg_N names "
            "until a real clause unseats it — -dynamic(f/N) with no clause in "
            "that file leaves the class named (arg_0, ..). Check whether both "
            "modules declare the same functor, and whether an -import_from "
            "rebinds this name after the local declaration: the import wins, "
            "so later constructions use the local field names against the "
            "foreign class. Fix: declare the functor in exactly one module "
            "and import it."
        )
    else:
        body = (
            "the two declarations of this functor disagree on argument names. "
            "Check whether both modules declare it — an -import_from rebinds "
            "the name after a local -module/-private declaration, so later "
            "constructions use the local field names against the foreign "
            "class. Fix: declare the functor in exactly one module and "
            "import it."
        )
    return textwrap.fill(
        f"({body})",
        width=79,
        initial_indent="  ",
        subsequent_indent="   ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def _term_construction_error(
    cls: Any, kwargs: dict, constructed_at: tuple[str, int] | None
) -> ClausalTermConstructionError:
    """Build the attributable error for a field-name mismatch on *cls*."""
    functor = cls.__name__
    registered = tuple(cls._fields)
    supplied = tuple(kwargs)
    registered_at = getattr(cls, "_registered_at", None)
    message = (
        f"functor {functor}/{len(registered)} was constructed with field names "
        f"{_format_fields(supplied)}\n"
        f"but its class was registered with {_format_fields(registered)}\n"
        f"  registered by: {_format_site(registered_at)}\n"
        f"  constructed at: {_format_site(constructed_at)}\n"
        f"{_construction_hint(functor, supplied, registered)}"
    )
    return ClausalTermConstructionError(
        message,
        functor=functor,
        arity=len(registered),
        supplied_fields=supplied,
        registered_fields=registered,
        registered_at=registered_at,
        constructed_at=constructed_at,
    )


def _overflow_supplied_fields(
    registered: tuple[str, ...], n_args: int
) -> tuple[str, ...]:
    """Field names *n_args* positional arguments would have been given.

    The positions that fit take the class's own names; the surplus take the
    ``arg_N`` placeholders the rewriter would have derived for them, so an
    arity overflow reads the same way as the keyword-path mismatch.
    """
    return tuple(registered[:n_args]) + tuple(
        f"arg_{i}" for i in range(len(registered), n_args)
    )


def _term_arity_error(
    cls: Any, n_args: int, kwargs: dict, constructed_at: tuple[str, int] | None
) -> ClausalTermConstructionError:
    """Build the attributable error for positional overflow on *cls*.

    ``PredicateMeta.__call__`` used to *drop* positional arguments past
    ``len(_fields)``, so ``some_atom(A, B)`` on a zero-arity class returned a
    silently wrong term.  That is worse than the keyword path's bare
    ``TypeError``: there is no exception at all to repair against.
    """
    functor = cls.__name__
    registered = tuple(cls._fields)
    supplied = _overflow_supplied_fields(registered, n_args) + tuple(
        k for k in kwargs if k not in registered[:n_args]
    )
    registered_at = getattr(cls, "_registered_at", None)
    message = (
        f"functor {functor}/{len(registered)} was constructed with {n_args} "
        f"positional argument(s)\n"
        f"but its class was registered with {len(registered)} field(s) "
        f"{_format_fields(registered)}\n"
        f"  registered by: {_format_site(registered_at)}\n"
        f"  constructed at: {_format_site(constructed_at)}\n"
        f"{_construction_hint(functor, supplied, registered)}"
    )
    return ClausalTermConstructionError(
        message,
        functor=functor,
        arity=len(registered),
        supplied_fields=supplied,
        registered_fields=registered,
        registered_at=registered_at,
        constructed_at=constructed_at,
    )


def _warn_atom_identity_enabled() -> bool:
    """True when the opt-in atom-identity diagnostic is on.

    Gated on ``CLAUSAL_WARN_ATOM_IDENTITY`` (``1``/``true``/``yes``/``on``).
    Read live at *class-creation* time only — never on the unify hot path —
    so the diagnostic ``__unify__`` is installed on an atom class only when
    the flag was set as that class was minted.  When off, zero-field atom
    classes carry no ``__unify__`` at all and the hot path is unchanged.
    """
    return os.environ.get("CLAUSAL_WARN_ATOM_IDENTITY", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


# One-shot dedup of (name, owner_a, owner_b) triples already warned about.
_atom_identity_warned: set = set()


def _make_atom_identity_unify(cls):
    """Build a diagnostic ``__unify__`` for a zero-field (atom) class.

    Installed only when ``CLAUSAL_WARN_ATOM_IDENTITY`` is set.  Semantics are
    identity-preserving — it never changes *whether* unification succeeds:

      * ``other is cls`` → succeed (same behaviour as the default identity
        comparison the C unifier would otherwise apply to atoms).
      * ``other`` is a *different* zero-field atom class with the *same*
        ``__name__`` → emit a one-shot ``ClausalAtomIdentityMismatchWarning``
        naming both owning modules, then fail (unchanged behaviour, now
        diagnosable).
      * anything else → ``NotImplemented`` so the C unifier's normal fallback
        (symmetric ``__unify__`` / identity compare) decides.
    """
    def __unify__(other, trail):  # noqa: N807 — invoked as cls.__unify__(t2, trail)
        if other is cls:
            return True
        if isinstance(other, PredicateMeta) and not other._fields \
                and other.__name__ == cls.__name__ and other is not cls:
            owner_a = getattr(cls, "__module__", "<unknown>")
            owner_b = getattr(other, "__module__", "<unknown>")
            key = (cls.__name__, owner_a, owner_b) if owner_a <= owner_b \
                else (cls.__name__, owner_b, owner_a)
            if key not in _atom_identity_warned:
                _atom_identity_warned.add(key)
                import warnings  # noqa: PLC0415
                from clausal.logic.compiler_v2 import (  # noqa: PLC0415
                    ClausalAtomIdentityMismatchWarning,
                )
                warnings.warn(
                    f"atom `{cls.__name__}` compared across modules with "
                    f"distinct module-local identity: `{owner_a}` vs "
                    f"`{owner_b}`.  These are separate classes and do not "
                    f"unify (query will have no solution).  Share one "
                    f"definition via -import_from(defining_module, "
                    f"[{cls.__name__}]) instead of re-declaring it.",
                    ClausalAtomIdentityMismatchWarning,
                    stacklevel=2,
                )
            return False
        return NotImplemented
    return __unify__



_init_cache: dict[tuple[str, ...], Callable] = {}


def _make_init(fields: tuple[str, ...]):
    """Generate an __init__ that accepts fields as keyword args with _MISSING default."""
    cached = _init_cache.get(fields)
    if cached is not None:
        return cached
    if not fields:
        def __init__(self):
            pass
        _init_cache[fields] = __init__
        return __init__
    params = ", ".join(f"{f}=_MISSING" for f in fields)
    assigns = "\n    ".join(f"self.{f} = {f}" for f in fields)
    code = f"def __init__(self, {params}):\n    {assigns}"
    globs = {"_MISSING": _MISSING}
    exec(code, globs)  # noqa: S102
    fn = globs["__init__"]
    _init_cache[fields] = fn
    return fn


def _term_iter(self):
    """Iterate solutions for this term as a goal.

    Enables ``for trail in greeting(X := Var()): print(deref(X))``.
    """
    from clausal.logic.solve import solve  # noqa: PLC0415
    return solve(self)


def _make_eq(fields: tuple[str, ...]):
    """Generate an __eq__ that compares field values."""
    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented
        return all(getattr(self, f) == getattr(other, f) for f in fields)
    return __eq__


def _make_unify(fields: tuple[str, ...]):
    """Generate a ``__unify__`` that recursively unifies corresponding fields.

    Called by the C ``do_unify`` when two PredicateMeta instances of the
    same type appear on both sides of a unification.
    """
    def __unify__(self, other, trail):
        if type(self) is not type(other):
            return NotImplemented
        from clausal.logic.variables import unify  # noqa: PLC0415
        for f in fields:
            if not unify(getattr(self, f), getattr(other, f), trail):
                return False
        return True
    return __unify__


def _make_occurs_check(fields: tuple[str, ...]):
    """Generate an ``__occurs_check__`` that recurses into field values.

    Called by the C ``do_occurs_check`` for PredicateMeta instances. Without
    it, occurs-check falls through to ``return 0`` and unify_with_occurs_check
    would build a cyclic term through a predicate term (A01-F001).
    """
    def __occurs_check__(self, var):
        from clausal.logic.variables import occurs_check  # noqa: PLC0415
        return any(occurs_check(var, getattr(self, f)) for f in fields)
    return __occurs_check__


def _make_repr(fields: tuple[str, ...]):
    """Generate an instance __repr__: ``fib(n=1, f=2)``."""
    def __repr__(self):
        cls_name = type(self).__name__
        parts = ", ".join(f"{f}={getattr(self, f)!r}" for f in fields)
        return f"{cls_name}({parts})"
    return __repr__


class PredicateMeta(type):
    """Metaclass that turns a class with ``_fields`` into a predicate.

    The class body should define ``_fields`` as a tuple of field name strings.
    PredicateMeta generates ``__init__``, ``__eq__``, ``__repr__``,
    ``__match_args__``, and ``__slots__`` from that tuple — no ``@dataclass``
    needed.

    It also adds predicate dispatch machinery:
      _clauses, _dispatch_fn, _lazy_recompile, _signature, _locked
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict,
        **kwargs: Any,
    ) -> PredicateMeta:
        fields: tuple[str, ...] = namespace.get("_fields", ())

        # __slots__ for lightweight instances
        namespace["__slots__"] = fields
        namespace["__match_args__"] = fields

        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Instance protocols — generated from _fields
        cls.__init__ = _make_init(fields)
        cls.__eq__ = _make_eq(fields)
        cls.__repr__ = _make_repr(fields)
        cls.__hash__ = None  # mutable terms shouldn't be hashable
        cls.__iter__ = _term_iter
        if fields:
            cls.__unify__ = _make_unify(fields)
            cls.__occurs_check__ = _make_occurs_check(fields)
        # For zero-field classes (atoms), skip __unify__/__occurs_check__: the
        # class IS the value, so identity comparison (C line 886: t1 == t2) and
        # the fallback PyObject_RichCompareBool handle unification correctly,
        # and an atom can never contain a Var.
        elif _warn_atom_identity_enabled():
            # Opt-in diagnostic only (CLAUSAL_WARN_ATOM_IDENTITY): install a
            # __unify__ that warns when this atom is compared against a
            # same-named atom of a different owning module.  Identity-preserving
            # (see _make_atom_identity_unify).  Guarded so the flag-off hot path
            # installs nothing and is byte-for-byte the original behaviour.
            cls.__unify__ = _make_atom_identity_unify(cls)

        # Where this class was registered, for the field-name mismatch
        # diagnostic.  Frame 1 is the .clausal module body running the
        # generated ``class <functor>(metaclass=PredicateMeta)`` block (or the
        # Python caller of ``make_predicate``).  Skipped when a field of that
        # name exists, since __slots__ would have made it a descriptor.
        if "_registered_at" not in fields:
            cls._registered_at = _source_site(1)

        return cls

    def __init__(cls, name: str, bases: tuple, namespace: dict, **kwargs: Any) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        # Predicate machinery — per-class, not inherited
        cls._clauses: list = []
        cls._dispatch_fn: Callable | None = None
        cls._lazy_recompile: Callable | None = None
        cls._signature: tuple[str, ...] | None = None
        cls._locked: bool = False  # starts unlocked; lock after module load

    # ── Term construction ─────────────────────────────────────────────────

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Create a term instance, filling missing fields with fresh Var().

        For zero-arity predicates (atoms), returns the class itself —
        the class IS the atom value.  ``red() is red`` holds.

        - Positional args are mapped to fields in order.
        - Keyword args: any field not provided gets a fresh Var().
        - If no args at all, all fields get Var() (fully unbound term).
        """
        if not cls._fields and not args and not kwargs:
            return cls

        fields = cls._fields

        if args:
            # Positional overflow used to be DROPPED here (``if i <
            # len(fields)``), so a call with too many arguments returned a
            # wrong term instead of raising — strictly worse than the keyword
            # path's TypeError, because there was nothing to repair against.
            # One length check replaces the former per-argument comparison, so
            # the hot path is if anything marginally cheaper.
            if len(args) > len(fields):
                raise _term_arity_error(
                    cls, len(args), kwargs, _source_site(1)
                )
            for i, val in enumerate(args):
                kwargs[fields[i]] = val

        instance = cls.__new__(cls)
        try:
            cls.__init__(instance, **kwargs)
        except TypeError:
            # A bare "unexpected keyword argument" here names neither the
            # functor nor either field-name tuple nor any source location, so
            # nothing in it identifies a target to repair.  Re-raise with all
            # of that attached — but only when the kwargs really are unknown
            # fields; any other TypeError from __init__ is passed through.
            if all(k in fields for k in kwargs):
                raise
            raise _term_construction_error(
                cls, kwargs, _source_site(1)
            ) from None

        # Replace _MISSING with fresh Var()
        from clausal.logic.variables import Var  # noqa: PLC0415
        for f in fields:
            if getattr(instance, f) is _MISSING:
                object.__setattr__(instance, f, Var())

        return instance

    # ── Predicate properties ──────────────────────────────────────────────

    @property
    def _functor(cls) -> str:
        return cls.__name__

    @property
    def _arity(cls) -> int:
        return len(cls._fields)

    # ── Clause management ─────────────────────────────────────────────────

    def _assertz(cls, clause: Any) -> None:
        """append clause at end; invalidate compiled dispatch."""
        if cls._locked:
            raise RuntimeError(
                f"Predicate {cls.__name__}/{cls._arity} is locked. "
                "Use dynamic() to allow runtime assertion."
            )
        cls._clauses.append(clause)
        cls._dispatch_fn = None

    def _asserta(cls, clause: Any) -> None:
        """Prepend clause at front; invalidate compiled dispatch."""
        if cls._locked:
            raise RuntimeError(
                f"Predicate {cls.__name__}/{cls._arity} is locked. "
                "Use dynamic() to allow runtime assertion."
            )
        cls._clauses.insert(0, clause)
        cls._dispatch_fn = None

    def _retract(cls, head: Any) -> bool:
        """Remove first clause whose head equals head (structural equality).

        Returns True if a clause was removed, False if none matched.
        """
        if cls._locked:
            raise RuntimeError(
                f"Predicate {cls.__name__}/{cls._arity} is locked. "
                "Use dynamic() to allow runtime retraction."
            )
        for i, clause in enumerate(cls._clauses):
            if clause.head == head:
                del cls._clauses[i]
                cls._dispatch_fn = None
                return True
        return False

    # ── Dispatch ──────────────────────────────────────────────────────────

    def _get_dispatch(cls) -> Callable:
        """Return the compiled dispatch function.

        If dispatch_fn was cleared by assertz/retract and a lazy recompile
        callback is registered, recompiles on demand.
        """
        if cls._dispatch_fn is None:
            if cls._lazy_recompile is not None:
                cls._dispatch_fn = cls._lazy_recompile()
            else:
                raise NotImplementedError(
                    f"Predicate {cls.__name__}/{cls._arity} has no compiled "
                    "dispatch function. The compiler must be run first."
                )
        return cls._dispatch_fn

    # ── Locking ───────────────────────────────────────────────────────────

    def _lock(cls) -> None:
        """Lock the predicate, preventing runtime assertz/retract."""
        cls._locked = True

    def _unlock(cls) -> None:
        """Unlock the predicate, allowing runtime assertz/retract."""
        cls._locked = False

    def __repr__(cls) -> str:
        if not cls._fields:
            return cls.__name__
        compiled = "compiled" if cls._dispatch_fn is not None else "uncompiled"
        n = len(cls._clauses)
        locked = ", locked" if cls._locked else ""
        return (
            f"<Predicate {cls.__name__}/{cls._arity}, "
            f"{n} clause(s), {compiled}{locked}>"
        )


# ── Python reference implementations (kept as fallbacks) ─────────────────────


def _is_term_instance_py(obj: Any) -> bool:
    """True if obj is a term instance with named fields (not a type/class).

    Works for both PredicateMeta instances and @dataclass instances.
    """
    if isinstance(obj, type):
        return False
    if isinstance(type(obj), PredicateMeta):
        return True
    return dataclasses.is_dataclass(obj)


def _is_atom_py(obj: Any) -> bool:
    """True if obj is a zero-arity PredicateMeta class (a declared atom)."""
    return isinstance(obj, PredicateMeta) and not obj._fields


def _term_field_names_py(obj: Any) -> tuple[str, ...]:
    """Return field name strings for a term instance."""
    cls = type(obj)
    if isinstance(cls, PredicateMeta):
        return cls._fields
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return tuple(f.name for f in dataclasses.fields(obj))
    raise TypeError(f"Not a term instance: {obj!r}")


# ── C-accelerated versions (with Python fallback) ────────────────────────────

is_term_instance = _is_term_instance_py
is_atom = _is_atom_py
term_field_names = _term_field_names_py

try:
    from clausal.logic.variables._variables import (
        _register_predicate_meta,
        is_term_instance,
        term_field_names,
        is_atom,
    )
    _register_predicate_meta(PredicateMeta)
except ImportError:
    pass


# ── By-identity atom references from generated code ──────────────────────────
#
# An atom is a class, so the natural way for generated code to name one is a
# bare ``Name`` resolved in the compiled function's globals.  That is wrong for
# an atom the compiler received as a live OBJECT (a ``DictTerm`` key/value built
# in Python or in another module and then baked into a query template): the
# template's globals are the *callee's* namespace, where the same spelling is
# very often bound to something else — under the snake_case convention, a
# same-named predicate.  The lookup then silently substitutes that other object.
# See ``todo/query-template-rebinds-atom-dict-keys.md``.
#
# ``register_atom_identity`` (compile time) + ``atom_by_id`` (run time, injected
# into every compiled predicate's globals as ``$atom``) pin such an atom by
# identity instead.  The table's strong reference is deliberate: it keeps the
# atom — and therefore its ``id`` — alive for the life of the process, so a
# token embedded in generated code can never be recycled onto another object.
# It is bounded by the number of distinct atoms ever lowered this way, and
# atoms are module-level classes that outlive compilation regardless.
_ATOM_IDENTITY_TABLE: dict[int, Any] = {}


def register_atom_identity(atom: Any) -> int:
    """Register *atom* for by-identity reference; return its token.

    Idempotent — the same atom always yields the same token.
    """
    token = id(atom)
    _ATOM_IDENTITY_TABLE[token] = atom
    return token


def atom_by_id(token: int) -> Any:
    """Return the atom registered under *token* (generated code: ``$atom``)."""
    return _ATOM_IDENTITY_TABLE[token]


def make_predicate(name: str, fields: list[str]) -> "PredicateMeta":
    """Dynamically create a PredicateMeta class.

    Useful in tests and runtime code that needs a predicate without a
    module-level class definition::

        foo = make_predicate("foo", ["a", "b"])
        foo._assertz(Clause(head=foo(a=Var(), b=Var()), body=[...]))
        compile_predicate("foo", 2, foo._clauses, pred_cls=foo)
        fn = foo._get_dispatch()
    """
    return PredicateMeta(name, (), {"_fields": tuple(fields)})


def make_atom(name: str) -> "PredicateMeta":
    """Create a zero-arity PredicateMeta atom.

    The returned class IS the atom value: ``a = make_atom("a"); a() is a``.
    Each call creates a NEW class — call once and reuse the result.

    equivalent to ``make_predicate(name, [])``.
    """
    return make_predicate(name, [])


__all__ = ["PredicateMeta", "_MISSING", "is_term_instance", "is_atom",
           "term_field_names", "make_predicate", "make_atom",
           "register_atom_identity", "atom_by_id"]
