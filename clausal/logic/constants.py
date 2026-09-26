"""Load-time support for -constants declarations.

A constant is a module global bound to a ground value before any clause
statement executes; clause construction embeds the value, so downstream
(indexing, solve, translation) never sees a name. This module supplies the
groundness gate the lowered assignment routes through — extended (2026-08-25)
to also FREEZE the value it gates: "constant" means constant, so a structured
constant (list/dict/set) must not be mutable from the Python side (most
commonly reached through a ``++`` escape holding a reference to the shared
term). See ``_freeze`` below and the Constants section of docs/syntax.md.
"""
from decimal import Decimal

from clausal.logic.variables import Var
from clausal.logic.predicate import is_term_instance
from clausal.terms import DictTerm, SetTerm


class ConstantNotGroundError(ValueError):
    """A -constants RHS produced a value containing an unbound variable."""


# ── Frozen structural subclasses ──────────────────────────────────────────────
#
# Type-PRESERVING freezing, not type-swapping: a frozen list is still a
# ``list`` (``isinstance(x, list)`` stays True), so unification, clause-head
# indexing, and the C unify extension (which tests structural class via
# ``PyList_Check``/``PyDict_Check``/``PyAnySet_Check`` — subclass-inclusive,
# not ``*_CheckExact`` — verified against clausal/logic/variables/_variables.c)
# all see no difference from a literal. Only the mutating methods are
# disabled, each raising ``TypeError`` naming the constant-immutability rule.


def _frozen_constant_mutation(self, *_args, **_kwargs):
    raise TypeError(
        "-constants: this value is a frozen constant (structured -constants "
        "values are immutable); mutation is not permitted — build a fresh, "
        "non-constant value instead of mutating the shared one")


class _FrozenList(list):
    """A -constants list value, frozen after the load-time groundness gate.

    ``copy.deepcopy``/``pickle`` round-trip to a PLAIN (unfrozen) ``list`` —
    see ``__reduce__``, and the module docstring's "the mutable-copy escape
    route" note — rather than failing or reconstructing another frozen
    instance. Without this, stdlib's default subclass reconstruction path
    rebuilds the object via ``append``/``extend``, which hits the very
    freeze error being escaped: a misleading "mutation is not permitted"
    from code that never asked to mutate the constant, only to copy it.
    """

    def __reduce__(self):
        return (list, (list(self),))


class _FrozenDict(dict):
    """A -constants dict value, frozen after the load-time groundness gate.

    See ``_FrozenList.__reduce__``: ``copy.deepcopy``/``pickle`` round-trip
    to a PLAIN (unfrozen) ``dict``.
    """

    def __reduce__(self):
        return (dict, (dict(self),))


class _FrozenSet(set):
    """A -constants set value, frozen after the load-time groundness gate.

    (Set-shaped ``++`` escape results only — a source-level ``{...}`` set
    literal in a -constants RHS lowers to ``SetTerm``, which is already
    immutable by construction; see ``_freeze``. A ``++``-built ``frozenset``
    is returned as-is, unwrapped — already immutable and hashable, so
    wrapping it in this mutable-set subclass would be a downgrade.)

    See ``_FrozenList.__reduce__``: ``copy.deepcopy``/``pickle`` round-trip
    to a PLAIN (unfrozen) ``set``.
    """

    def __reduce__(self):
        return (set, (set(self),))


for _cls, _mutators in (
    (_FrozenList, ("append", "extend", "insert", "__setitem__",
                   "__delitem__", "pop", "remove", "clear", "sort",
                   "reverse", "__iadd__", "__imul__")),
    (_FrozenDict, ("__setitem__", "__delitem__", "pop", "popitem",
                   "clear", "update", "setdefault", "__ior__")),
    (_FrozenSet, ("add", "discard", "remove", "pop", "clear", "update",
                  "intersection_update", "difference_update",
                  "symmetric_difference_update", "__ior__", "__iand__",
                  "__ixor__", "__isub__")),
):
    for _mutator in _mutators:
        setattr(_cls, _mutator, _frozen_constant_mutation)
del _cls, _mutators, _mutator


def _freeze(value):
    """Recursively freeze *value* into its immutable -constants form.

    Mirrors exactly the structural type a clause-body literal of the same
    source shape builds (list, ``DictTerm``, ``SetTerm``, tuple, functor
    instance) — freezing never changes *which* type a value is, only
    whether it can be mutated.

    ``DictTerm``'s ``.data`` is the one case where freezing can't happen
    through the public constructor: ``DictTerm.__init__`` takes a defensive
    ``dict(data)`` copy, so passing a ``_FrozenDict`` in gets silently
    downgraded back to a plain ``dict``. Freezing it is still possible —
    just not through ``__init__`` — by patching the ``_data`` slot directly
    after construction (``DictTerm`` has no custom ``__setattr__``, so this
    is an ordinary, unresisted slot assignment).

    ``SetTerm`` needs no freezing at all: it is backed by a ``frozenset``
    with no public mutator, immutable by construction.

    A compound-term (functor / ``PredicateMeta``) INSTANCE is converted to
    its cell, and its fields are frozen like any other interior.  This is
    not an optimisation, it is the type correction that makes the docstring
    claim above true: post-R6 a clause-body literal ``point(0, 0)`` builds
    the cell ``("point", 0, 0)``, while a ``-constant_value`` RHS runs
    before ``_process_declarations`` has unbound the functor class and so
    calls it, producing an instance.  The two do not unify, which was
    invisible while a bare reference folded through the clause builder (it
    converted on the way in) and became visible the moment ``++name`` --
    which hands the stored object straight to the goal -- was the only way
    to read a constant.
    """
    import clausal.logic.cells as _cells                       # noqa: PLC0415
    from clausal.logic.predicate import term_field_names       # noqa: PLC0415
    if isinstance(value, (_FrozenList, _FrozenDict, _FrozenSet)):
        return value  # already frozen
    if isinstance(value, DictTerm):
        if not isinstance(value.data, _FrozenDict):
            frozen_data = _FrozenDict(
                (_freeze(k), _freeze(v)) for k, v in value.data.items())
            value._data = frozen_data  # bypass __init__'s defensive copy
        return value
    if isinstance(value, SetTerm):
        return value  # frozenset-backed already; no public mutator
    if is_term_instance(value):
        return _cells.make_cell(
            type(value).__name__,
            *(_freeze(getattr(value, f)) for f in term_field_names(value)))
    if isinstance(value, tuple):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, list):
        return _FrozenList(_freeze(v) for v in value)
    if isinstance(value, dict):
        return _FrozenDict((_freeze(k), _freeze(v)) for k, v in value.items())
    if isinstance(value, frozenset):
        # Already immutable AND already hashable — _FrozenSet(set) is a
        # mutable-set subclass (unhashable, since ``set.__hash__`` is None),
        # so wrapping a frozenset in it would be a downgrade, not a freeze.
        # Elements of a frozenset must already be hashable (nothing further
        # to recurse into that could itself need freezing).
        return value
    if isinstance(value, set):
        return _FrozenSet(_freeze(v) for v in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def _contains_var(value) -> bool:
    if isinstance(value, Var):
        return True
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_var(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_var(k) or _contains_var(v)
                   for k, v in value.items())
    # Term objects (Compound, KWTerm, compile-time PredicateMeta instances,
    # Seg* containers): delegate to the canonical recursive ground check
    # instead of duck-typing an ``.args`` tuple — compile-time predicate
    # classes hold fields by name (``_fields``/``__slots__``), not a generic
    # ``.args``, so ``getattr(value, "args", None)`` silently missed them.
    # ``Compound.is_ground`` (terms.py:587) does the same delegation, lazily,
    # to dodge the circular import (this module is imported very early, from
    # import_hook.py, before clausal.logic.builtins exists).
    from clausal.logic.builtins._helpers import _is_ground  # noqa: PLC0415
    return not _is_ground(value)


def check_constant_ground(name: str, value):
    """Gate a -constants binding: check-and-freeze.

    Returns *value* recursively frozen (see ``_freeze``) iff it is ground;
    raises ``ConstantNotGroundError`` otherwise. The module global and the
    ``module_constant/3`` reflection registry both end up holding this same
    frozen value — see ``register_module_constant`` below.
    """
    if _contains_var(value):
        raise ConstantNotGroundError(
            f"-constants: `{name}` must be fully ground at load time; "
            f"got a value containing an unbound variable: {value!r}")
    return _freeze(value)


def _freeze_dict_term(data: dict):
    """Construct a ``DictTerm`` whose backing store is frozen from the
    start (``dt._data`` is a ``_FrozenDict``, not the plain ``dict``
    ``DictTerm.__init__`` would otherwise build).

    ``DictTerm.__init__`` takes a defensive ``dict(data)`` copy — the same
    constraint ``_freeze``'s ``DictTerm`` branch works around by patching
    ``._data`` after construction. Used by ``terms_to_ast.term_to_ast_expr``
    to reconstruct a frozen ``DictTerm`` for a compiled clause that
    references a -constants dict value: the RECONSTRUCTION a clause builds
    each time it runs must be frozen too, not only the module-global-held
    original — see the comment at that call site.
    """
    dt = DictTerm(data)
    dt._data = _FrozenDict(dt._data)
    return dt


def constant_functor_term(name: str, args, kwargs, namespace):
    """Build the term a ``-constants`` RHS functor call denotes.

    P3-2 Task 2 (THE FLIP).  A ``-constants`` right-hand side is evaluated
    ONCE, at exec time, on the ``-constants`` line itself -- not compiled per
    invocation the way a clause body is.  It used to emit a direct
    ``Point(0, 0)`` constructor call, which is now wrong twice over:

    * an IMPORTED data functor never binds a class in the importer at all
      (the owner's name is its interned spelling by the time the import
      runs), so the call raised ``TypeError: 'str' object is not callable``
      from the ``-constants`` line and the module failed to load;
    * a LOCALLY declared one happened to work only because the ``-module``
      rewrite's class block runs earlier in the same exec -- and it produced
      a class INSTANCE where every other reference to that functor in the
      module produces a cell.

    So the decision is made here, at exec time, on the same BINDING SHAPE
    rule the compiler uses (R6): a ``PredicateMeta`` binding is a predicate
    or a Python-minted functor and is CONSTRUCTED, exactly as before;
    anything else is data and becomes a cell, placed against the declared
    signature from *namespace*'s ``__clausal_functor_signatures__`` registry
    (which ``-import_from`` copies under the local spelling, so an imported
    functor and an aliased import both resolve).

    Slot 0 carries the OWNER's spelling: for a str binding that is the
    binding itself (an alias binds the owner's spelling under the local
    name), else the local *name*.

    Raises ``SyntaxError`` for an over-arity or unknown-field construction,
    matching the compile-time errors ``terms_to_ast._place_signature_slots``
    raises for the same mistakes in a clause body -- the same mistake should
    not be a clean error in one position and a mangled term in the other.
    """
    from clausal.logic.predicate import (
        build_term_cell, declared_head, is_declared_predicate_name,
        namespace_db,
    )

    binding = namespace.get(name)
    declared = declared_head(namespace, binding)
    if declared is not None:
        # A predicate this module body declared (``$declare_head``, W4b-3
        # slice 5): CONSTRUCTED against its recorded field names, exactly as
        # the rewriter's class was called here while a predicate was one.
        functor, fields, site = declared
        if not fields and not args and not kwargs:
            return functor
        return build_term_cell(functor, fields, args, dict(kwargs or {}),
                               site=site)
    if is_declared_predicate_name(
            binding, db=namespace_db(namespace)):
        return binding(*args, **kwargs)

    from clausal.logic.compiler.terms_to_ast import functor_signature_for  # noqa: PLC0415
    fields = functor_signature_for(name, namespace)   # P2: the Database first, then the exec-time map
    if fields is None:
        # No class and no declared signature: nothing to place against.  Let
        # the original call happen so the failure names the real problem
        # (an uncallable binding) at the line that caused it.
        return binding(*args, **kwargs)

    functor = binding if isinstance(binding, str) else name
    if len(args) > len(fields):
        raise SyntaxError(
            f"-constants: functor {functor}/{len(fields)} was constructed "
            f"with {len(args)} positional argument(s) but its signature "
            f"declares {len(fields)} field(s) {fields!r}"
        )
    slots = list(args) + [None] * (len(fields) - len(args))
    filled = [True] * len(args) + [False] * (len(fields) - len(args))
    for key, value in (kwargs or {}).items():
        if key not in fields:
            raise SyntaxError(
                f"-constants: functor {functor}/{len(fields)} was "
                f"constructed with field name {key!r} but its signature "
                f"declares fields {fields!r}"
            )
        index = fields.index(key)
        if filled[index]:
            raise SyntaxError(
                f"-constants: functor {functor}/{len(fields)} was "
                f"constructed with both a positional argument and keyword "
                f"`{key}=` for the same field {fields!r}"
            )
        slots[index] = value
        filled[index] = True
    if not all(filled):
        # A -constants value must be GROUND ($check_constant_ground gates it
        # immediately after this returns); an omitted slot would backfill
        # with a fresh Var in a clause body, which is precisely what a
        # constant may not hold.  Say so here, where the field is named.
        missing = [f for f, ok in zip(fields, filled) if not ok]
        raise SyntaxError(
            f"-constants: functor {functor}/{len(fields)} left field(s) "
            f"{missing!r} unfilled — a constant must be ground, so every "
            f"declared field needs a value"
        )
    return (functor, *slots)


def decimal_value(text: str):
    """The exact ``Decimal`` a declared decimal STRING names.

    ``-constant_number_units(fee, "292.00", usd)``. A written ``292.00`` is a
    Python float literal and has already lost its trailing zero by the time
    any ``Quantity`` exists -- it stores ``Decimal('292.0')`` -- so the scale
    the statute wrote cannot be recovered downstream. A string carries the
    digits verbatim.

    The counterpart of minor units, reached from the other side: a minor unit
    keeps "29200 cents" recoverable by declaring the SCALE, a decimal string
    keeps "292.00 dollars" exact by declaring the DIGITS.

    The transformer has already refused anything unparseable with a
    ``SyntaxError`` naming the directive, so this raise is the belt to that
    braces -- reached only if the two ever disagree, which is exactly when a
    silent failure would be worst.
    """
    from decimal import Decimal, InvalidOperation      # noqa: PLC0415
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    if is_chars(text):
        # Under ``-double_quotes(chars)`` (the engine default since the
        # 2026-09-26 flip) a written ``"292.00"`` is the chars CARRIER
        # ``('$chars', '292.00')``.  The digits are the same digits; only
        # the wrapping differs.  Measured 2026-09-26: without this arm every
        # currency/units TABLE of decimal strings in a chars-mode module
        # failed to load with ``('$chars', '292.00') is not a decimal number``.
        text = chars_text(text)
    elif (isinstance(text, tuple) and len(text) == 1
            and isinstance(text[0], str)):
        # A table row is a FACT, and the fact layer interns a bare string
        # argument as an ATOM -- the one-element tuple form. The single-value
        # path emits into an expression and keeps a `str`, so this helper is
        # reached with both spellings of the same written literal. Measured
        # 2026-09-12; accepting one and not the other made the table half
        # fail with `('292.00',) is not a decimal number`.
        text = text[0]
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(
            f"{text!r} is not a decimal number") from None


def check_currency_unit(name: str, unit, spelling: str):
    """Gate for ``-constant_number_currency``: *unit* must be MONEY.

    "Money" is a shape, not a type: **dims is a single currency at exponent
    one.** That admits a currency (``usd``) and a minor unit of one
    (``usd_cent``, which is ``Quantity(Decimal('0.01'), {usd: 1})``), and
    nothing else -- ``usd ** 2`` is an area in dollars and ``usd / second`` a
    rate, neither of which is an amount of money.

    Shape rather than type because the property the declaration ASSERTS is
    "this constant is money", and a minor unit satisfies it. Requiring the
    argument to *be* a currency split the two safety properties across two
    directives so that an author could have the currency gate or the
    minor-unit scale but never both -- and every one of the 139 identifiers
    the corpus migration is about is spelled ``_cents``/``_satang``/
    ``_pence``, so the gate would have covered the case the migration is
    least likely to produce (corpus-lane, 2026-09-11).

    The gap this closes is narrow and worth stating exactly, since two of the
    three obvious failures were already covered: a mistyped or unbound
    currency is a ``NameError``, because a currency identifier has to be
    BOUND to be written. What was not covered is a unit that loads perfectly
    well and is not money -- ``-constant_number_units(fee, 5000, metre)``
    yields ``Quantity(5000, metre)``, an int-valued length, in silence.

    Returns the unit so the caller can use this inline.
    """
    dims = getattr(unit, "_dims", None)
    if dims is None:
        dims = getattr(unit, "dims", None)
    if dims and len(dims) == 1:
        (key, exponent), = dims.items()
        from clausal.terms import _currency_info        # noqa: PLC0415
        if exponent == 1 and _currency_info(key) is not None:
            return unit
    raise TypeError(
        f"{spelling}: `{name}` declares money, but {unit!r} is not an amount "
        f"of money. The unit must be a currency or a minor unit of one — one "
        f"currency at exponent one — so a rate (`usd / second`) or a power "
        f"(`usd ** 2`) is not accepted either. Use -constant_number_units "
        f"for a quantity that is not money."
    )


def register_constant_units(module, name: str, number, units,
                            value=None) -> None:
    """Record what a ``-constant_number_units`` declaration SAID.

    *number* and *units* are the declared pair, lowered at compile time —
    not read back from the Quantity, which cannot yield them: a unit that is
    not the base of its own dimension rescales to that base, so ``30 day``
    becomes ``Quantity(2592000, second)`` and both the 30 and the ``day`` are
    unrecoverable. Backs ``constant_number_units/3`` (operator's ruling,
    2026-09-11: the predicate reports the DECLARED pair).

    *value* is the constant itself, and settles the NUMERIC KIND of what is
    recorded: **the declared magnitude is kept in the same kind the value
    uses.** A currency amount is an exact ``Decimal``, so the float the AST
    carried for ``19.99`` is converted rather than stored — otherwise the
    one channel whose whole job is fidelity to the declaration would be the
    one place money went binary. ``Decimal(str(f))`` (never ``Decimal(f)``)
    is exact for any literal a human wrote, since ``repr`` round-trips.

    Nothing else is touched: an ``int`` is already exact, and a non-currency
    float (``1.5 hour``) has no exactness claim to keep.
    """
    if isinstance(number, float) and isinstance(getattr(value, "value", None),
                                                Decimal):
        number = Decimal(str(number))
    module.constant_units[name] = (number, units)


def register_module_constant(module, name: str, value) -> None:
    """Record a declared ``-constants`` ``(name, value)`` pair on *module*.

    Backs ``module_constant/3`` reflection (docs/builtins.md). Called from
    generated code immediately after ``$check_constant_ground``, so *value*
    is already gated (ground) and frozen — the registry and the module
    global end up holding the identical object.

    Only a module's OWN ``-constants`` declarations are recorded here — an
    imported constant is not re-registered on the importer; it stays
    reachable through its owning module's ``module_constant/3`` instead
    (see docs/import.md). This function is only ever called from the
    lowering of a ``-constants`` directive itself (never from
    ``-import_from``/``-import_module`` handling), so that choice falls out
    of the call sites rather than needing a check here.
    """
    module.constants[name] = value
