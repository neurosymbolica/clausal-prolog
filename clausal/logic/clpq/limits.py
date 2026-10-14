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
clpq_expansion          the terms one normal form makes in powers  nf
  clpq_max_expansion    and products of sums, counted before each
                        is built
clpq_expansion          the bits those terms' coefficients take,   nf
  clpq_max_expansion_bits  estimated before each is built
======================  =========================================  =======

The defaults are DEFAULTS; DEVIATIONS.md D24 has how they were measured.

Each count belongs to one call: a Meter on a context variable, so two
threads (or two asyncio tasks) never share one.  A metered call inside
another (a bb_inf woken in a search, a projection under a search) is
charged to its own meter and to every meter around it, so the outer cap
bounds the whole.

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
#: resource, except the second expansion cap, which raises clpq_expansion.
FLAGS = {
    "clpq_nodes": "clpq_max_nodes",
    "clpq_work": "clpq_max_work",
    "clpq_projection": "clpq_max_projection",
    "clpq_expansion": "clpq_max_expansion",
    "clpq_expansion_bits": "clpq_max_expansion_bits",
}

#: cap -> the resource its error names.
RESOURCES = {cap: cap for cap in FLAGS}
RESOURCES["clpq_expansion_bits"] = "clpq_expansion"

#: cap -> its default (DEVIATIONS.md D24: the largest use measured, and
#: the headroom over it).
DEFAULTS = {
    "clpq_nodes": 20_000,
    "clpq_work": 2_000_000,
    "clpq_projection": 4_000_000,
    "clpq_expansion": 20_000,
    "clpq_expansion_bits": 200_000_000,
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
    """The count of one call: *used* so far against the cap *cap*, and the
    meter of the call around it (*parent*), which is charged too."""
    __slots__ = ("cap", "what", "used", "parent")

    def __init__(self, cap, what, parent):
        self.cap = cap
        self.what = what
        self.used = 0
        self.parent = parent


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
            check(meter.cap, meter.used, meter.what)
            charged = True
        meter = meter.parent
    return charged


#: The caps a row written by a pivot counts against.
ROW_CAPS = ("clpq_work", "clpq_projection")


def charge_rows(units):
    """A pivot's back substitution did *units* of work: charge the open
    search and projection meters."""
    charge(units, ROW_CAPS)


def charge_projection(units):
    """Fourier-Motzkin will derive rows of *units* terms in all: charge the
    open projection meters.  Nothing when no projection runs."""
    charge(units, ("clpq_projection",))


_EXPANSION = ("clpq_expansion",)
_EXPANSION_BITS = ("clpq_expansion_bits",)


def charge_expansion(terms, bits, what):
    """An expansion will make *terms* terms whose coefficients take about
    *bits* bits: charge the open normal form's meters, or, outside one,
    check it alone against the caps."""
    if not charge(terms, _EXPANSION):
        check("clpq_expansion", terms, what)
    if not charge(bits, _EXPANSION_BITS):
        check("clpq_expansion_bits", bits, what + " (coefficient bits)")
