"""Resource caps of the port: work 1.3.3 does without limit (DEVIATIONS.md
D24).  Past a cap the port raises `error(resource_error(R), _)`; it never
cuts a search short silently or answers in part (ruling D51).

========================  ===================  =========  ===============
resource R                what is counted      default    where
========================  ===================  =========  ===============
clpq_nodes                branch-and-bound     20000      branch_and_bound
                          nodes of one bb_inf
clpq_projection           rows one projection  50000      projection
                          writes: its pivots'
                          row rewrites and the
                          constraints Fourier-
                          Motzkin derives
clpq_power                terms the binomial   10000      normal_form
                          expansion of one
                          integer power makes
========================  ===================  =========  ===============

Each cap is the Prolog flag named in FLAGS, a positive integer, process
wide: `set_prolog_flag(clpq_max_nodes, 500000)`,
`current_prolog_flag(clpq_max_nodes, N)`.  The flags exist only under
`CLAUSAL_CLPQ=holzbaur` (clausal/logic/builtins/flags.py), so the legacy
switch's flags are unchanged.  From Python, `set_limit` and `limit`, which
work under either switch (the port's own tests import it under legacy).
"""
from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException, _error

#: resource -> its flag.
FLAGS = {
    "clpq_nodes": "clpq_max_nodes",
    "clpq_projection": "clpq_max_projection",
    "clpq_power": "clpq_max_power",
}

#: resource -> its default.  The headroom over the largest use the tests,
#: the examples and the benchmarks make is in DEVIATIONS.md D24.
DEFAULTS = {
    "clpq_nodes": 20_000,
    "clpq_projection": 50_000,
    "clpq_power": 10_000,
}

_LIMITS = dict(DEFAULTS)


def limit(resource):
    """The cap on *resource* now."""
    return _LIMITS[resource]


def set_limit(resource, value):
    """Set the cap on *resource* to the positive int *value*; returns the
    cap it replaces."""
    if type(value) is not int or value < 1:
        raise ValueError(f"the {resource} cap must be a positive int, "
                         f"not {value!r}")
    previous = _LIMITS[resource]
    _LIMITS[resource] = value
    return previous


def check(resource, used, what):
    """Raise `error(resource_error(R), _)` where *used* passes the cap on
    *resource*.  *what* says what was counted, for the message."""
    cap = _LIMITS[resource]
    if used > cap:
        raise LogicException(_error(
            ("resource_error", mint(resource)),
            f"clpq: {what} passed {cap} (the {FLAGS[resource]} flag)"))


#: The rows the projection running now has written, or None when no
#: projection runs.  bounded_simplex's back substitution charges its
#: rewrites here, Fourier-Motzkin its derived constraints
#: (projection.project_attributes starts and stops it).
projection_rows = None


def start_projection():
    """Start counting a projection's rows; returns the count to give back
    to stop_projection (a projection that runs inside another goes on
    counting the outer one's)."""
    global projection_rows
    previous = projection_rows
    if previous is None:
        projection_rows = 0
    return previous


def stop_projection(previous):
    global projection_rows
    if previous is None:
        projection_rows = None


def charge_projection(rows):
    """Add *rows* to the projection's count; past the clpq_projection cap,
    raise `resource_error(clpq_projection)`.  Nothing when no projection
    runs."""
    global projection_rows
    if projection_rows is None:
        return
    projection_rows += rows
    check("clpq_projection", projection_rows,
          "the rows one projection wrote")
