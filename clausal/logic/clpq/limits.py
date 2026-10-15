"""Resource caps of the port: work 1.3.3 does without limit (DEVIATIONS.md
D24).  Past a cap the port raises `error(resource_error(R), _)`; it never
cuts a search short silently or answers in part (ruling D51).

======================  =========================================  =======
resource R and flag     what is counted, per call                  where
======================  =========================================  =======
clpq_nodes              the nodes of one bb_inf search             bb
  clpq_max_nodes
clpq_work               the work of one bb_inf search's pivots:    bb, bv
  clpq_max_work         the rows their back substitution reads,
                        and the size of the rows it writes
                        (bounded_simplex.row_size)
clpq_projection         the same work for one projection, and the  project,
  clpq_max_projection   rows Fourier-Motzkin derives (charged      fourmotz,
                        before they are made)                      bv
clpq_expansion          the terms one constraint's normal form     nf
  clpq_max_expansion    makes in powers and products of sums,
                        counted before each is built, and carried
                        across a delayed constraint's wake-ups
clpq_expansion          the bits those terms' coefficients take,   nf
  clpq_max_expansion_bits  and the coefficients powers of numbers,
                        roots and big products build, estimated
                        before each is built; past COSTLY_BITS a
                        coefficient counts its cost
                        (coefficient_charge)
clpq_expansion          the bits of the largest coefficient one    nf
  clpq_max_coefficient_bits  power, root or product builds,
                        estimated before it is built (one integer
                        of n bits costs about n^1.6 to build, so
                        the total alone is not enough)
======================  =========================================  =======

The defaults are DEFAULTS; DEVIATIONS.md D24 has how they were measured.

Each count belongs to one call: the work on a Meter (which reads its cap
when its call starts) on a context variable, so two threads (or two
asyncio tasks) never share one; an expansion on an Expansion its normal
form or repair keeps to itself.  A metered call inside another (a bb_inf
woken in a search, a projection under a search) is charged to its own
meter and to every meter around it, so the outer cap bounds the whole.

A program reads and sets the caps with the Prolog flags of FLAGS, under
`CLAUSAL_CLPQ=holzbaur` only (clausal/logic/builtins/flags.py); in the
sandbox the flags are read-only, to the program and to its load-time
directives, and the host sets the caps from Python with `set_limit`.
`set_limit` and `limit` work under either switch.
"""
from contextvars import ContextVar

from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException, _error

#: cap -> the flag that reads and sets it.  A cap is named by its
#: resource, except the second and third expansion caps, which raise
#: clpq_expansion.
FLAGS = {
    "clpq_nodes": "clpq_max_nodes",
    "clpq_work": "clpq_max_work",
    "clpq_projection": "clpq_max_projection",
    "clpq_expansion": "clpq_max_expansion",
    "clpq_expansion_bits": "clpq_max_expansion_bits",
    "clpq_coefficient_bits": "clpq_max_coefficient_bits",
}

#: cap -> the resource its error names.
RESOURCES = {cap: cap for cap in FLAGS}
RESOURCES["clpq_expansion_bits"] = "clpq_expansion"
RESOURCES["clpq_coefficient_bits"] = "clpq_expansion"

#: cap -> its default (DEVIATIONS.md D24: the largest use measured, and
#: the headroom over it).
DEFAULTS = {
    "clpq_nodes": 20_000,
    "clpq_work": 4_000_000,
    "clpq_projection": 4_000_000,
    "clpq_expansion": 40_000,
    "clpq_expansion_bits": 200_000_000,
    "clpq_coefficient_bits": 20_000_000,
}

_LIMITS = dict(DEFAULTS)


def limit(cap):
    """The cap *cap* now."""
    return _LIMITS[cap]


def set_limit(cap, value):
    """Set the cap *cap* to the positive int *value*; returns the value it
    replaces.  The host's way to set a cap: under the sandbox a program
    cannot."""
    if type(value) is not int or value < 1:
        raise ValueError(f"the {cap} cap must be a positive int, "
                         f"not {value!r}")
    previous = _LIMITS[cap]
    _LIMITS[cap] = value
    return previous


def check(cap, used, what):
    """Raise `error(resource_error(R), _)` where *used* passes the cap
    *cap*; R is the cap's resource.  *what* says what was counted, for
    the message."""
    value = _LIMITS[cap]
    if used > value:
        raise LogicException(_error(
            ("resource_error", mint(RESOURCES[cap])),
            f"clpq: {what} passed {value} (the {FLAGS[cap]} flag)"))


class Meter:
    """The count of one call: *used* so far against the cap *cap*, whose
    value *limit* is read when the call starts, and the meter of the call
    around it (*parent*), which is charged too.  *threshold* is what a
    hot path compares *used* with after adding to it in place: *limit*,
    or -1 inside another meter, whose charge takes the slow path
    (rows_charged)."""
    __slots__ = ("cap", "what", "used", "parent", "limit", "threshold")

    def __init__(self, cap, what, parent):
        self.cap = cap
        self.what = what
        self.used = 0
        self.parent = parent
        self.limit = _LIMITS[cap]
        self.threshold = self.limit if parent is None else -1


def _passed(meter):
    """Raise `error(resource_error(R), _)`: *meter* has passed its cap."""
    raise LogicException(_error(
        ("resource_error", mint(RESOURCES[meter.cap])),
        f"clpq: {meter.what} passed {meter.limit} "
        f"(the {FLAGS[meter.cap]} flag)"))


#: The meter of the innermost metered call running in this context.
_METER = ContextVar("clpq_meter", default=None)


def start(cap, what):
    """Open a meter for one call on *cap*; returns the token for stop."""
    return _METER.set(Meter(cap, what, _METER.get()))


def stop(token):
    """Close the meter *token* opened."""
    _METER.reset(token)


def metering():
    """True while a meter is open: a hot path tests this before it counts."""
    return _METER.get() is not None


def charge(units, caps):
    """Charge *units* to every open meter on one of *caps*, the innermost
    and the ones around it; raise at the first that passes its cap.  True
    when a meter was charged."""
    charged = False
    meter = _METER.get()
    while meter is not None:
        if meter.cap in caps:
            meter.used += units
            if meter.used > meter.limit:
                _passed(meter)
            charged = True
        meter = meter.parent
    return charged


#: The caps a row written by a pivot counts against.
ROW_CAPS = ("clpq_work", "clpq_projection")


def charge_rows(units):
    """A pivot's back substitution did *units* of work: charge the open
    search and projection meters."""
    charge(units, ROW_CAPS)


def current_meter():
    """The innermost open meter, or None: a hot path reads it once."""
    return _METER.get()


def charge_rows_to(meter, units):
    """charge_rows, from the open meter *meter* (current_meter) outwards.
    Every meter is on a ROW_CAPS cap (start is called on no other)."""
    while meter is not None:
        meter.used += units
        if meter.used > meter.limit:
            _passed(meter)
        meter = meter.parent


def rows_charged(meter, units):
    """The back substitution has added *units* to the innermost open meter
    *meter* in place, and found it past its threshold (past its cap, or
    inside another meter): raise for it, or charge the meters around it.
    Its hot path is the add and one comparison (review N2)."""
    if meter.used > meter.limit:
        _passed(meter)
    charge_rows_to(meter.parent, units)


def charge_projection(units):
    """Fourier-Motzkin will derive rows of *units* terms in all: charge the
    open projection meters.  Nothing when no projection runs."""
    charge(units, ("clpq_projection",))


class Expansion:
    """The terms and coefficient bits one normal form, or one repair, has
    expanded so far.  Made only when an expansion is charged (a linear
    constraint never needs one).  A repair of a delayed constraint starts
    from what that constraint's earlier wake-ups spent (CARRIED), so the
    count persists across them."""
    __slots__ = ("terms", "bits")

    def __init__(self, terms=0, bits=0):
        self.terms = terms
        self.bits = bits


def charge_expansion(terms, bits, what, expansion=None):
    """An expansion will make *terms* terms whose coefficients take about
    *bits* bits: add them to *expansion*, the count of the call making it,
    and raise `resource_error(clpq_expansion)` past either cap; with no
    *expansion*, check this one alone."""
    if expansion is not None:
        expansion.terms += terms
        expansion.bits += bits
        terms = expansion.terms
        bits = expansion.bits
    check("clpq_expansion", terms, what)
    check("clpq_expansion_bits", bits, what + " (coefficient bits)")


#: Past this many bits, a coefficient costs more than its bits: one built
#: by a power or a product charges the clpq_expansion_bits cap
#: coefficient_charge(bits), bits * bits / COSTLY_BITS (review R2c: the
#: coefficient cap bounds one, and sixteen powers each under it took 76
#: s under the total, counted linearly).  Building n bits costs about
#: n^1.6, so the square overcharges a big one; at the default caps the
#: total then admits one coefficient near the coefficient cap, and about
#: 13 s (on 32 idle cores) of coefficients of any one size.
COSTLY_BITS = 2_500_000


def coefficient_charge(bits):
    """The bits one coefficient of about *bits* bits (a log2) charges the
    clpq_expansion_bits cap: *bits*, and bits * bits / COSTLY_BITS past
    COSTLY_BITS."""
    bits = int(bits)
    if bits <= COSTLY_BITS:
        return bits
    return bits * bits // COSTLY_BITS


def check_coefficient(bits, what):
    """A power will build one coefficient of about *bits* bits: raise
    `resource_error(clpq_expansion)` past the clpq_coefficient_bits cap.
    Building an integer of n bits costs about n^1.6 (review R2:
    `(3*Y)^(10^8)` took 131 s under the bits cap), so this bounds the
    largest coefficient as well as charge_expansion bounds them all."""
    check("clpq_coefficient_bits", bits, what + " (one coefficient's bits)")


def charge_coefficients(count, bits, what, expansion=None):
    """*count* coefficients of about *bits* bits each (a log2, the largest)
    will be built: raise `resource_error(clpq_expansion)` where one passes
    the clpq_coefficient_bits cap (check_coefficient), or where their
    coefficient_charge passes the clpq_expansion_bits cap on *expansion*,
    the count of the call building them (charge_expansion).  Powers of
    numbers, roots and products charge so (review R2b, R2c)."""
    check_coefficient(bits, what)
    charge_expansion(0, count * coefficient_charge(bits), what, expansion)


#: Inside the run of a delayed goal (delayed_goals.run): the (terms, bits)
#: that goal's constraint has expanded over its wake-ups so far, which its
#: repair starts from and the goal it delays again carries on.  None
#: outside a run.
CARRIED = ContextVar("clpq_carried_expansion", default=None)
