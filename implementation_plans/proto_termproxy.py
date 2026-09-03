"""TermProxy existence proof: lazy Python view over tagged-tuple terms.

Cells: ("functor", arg1, ..., argn) / (tuple, e1, ..., en). Proxies wrap a
DEREF-WALKED SNAPSHOT taken at yield time (immutable; backtracking can't
touch it). Materialization is explicit and error-chained to the source query.
"""
import datetime

REGISTRY = {}   # functor name -> (real class, field names)

class PredicateMeta(type):
    def __new__(mcs, name, bases, ns):
        cls = super().__new__(mcs, name, bases, ns)
        if "_fields" in ns:
            REGISTRY[name] = (cls, tuple(ns["_fields"]))
        return cls
    def __instancecheck__(cls, obj):          # <-- the seam-compat hook
        if type(obj) is TermProxy:
            return object.__getattribute__(obj, "_cell")[0] == cls.__name__
        return super().__instancecheck__(cls if False else obj)

class ClausalMaterializationError(Exception):
    pass

def _render(cell):                             # stand-in for the reified renderer
    if isinstance(cell, tuple):
        if cell[0] is tuple:
            return "(" + ", ".join(_render(a) for a in cell[1:]) + ")"
        return f"{cell[0]}({', '.join(_render(a) for a in cell[1:])})"
    return repr(cell)

class TermProxy:
    __slots__ = ("_cell", "_origin")           # frozen: no setters exist
    def __init__(self, cell, origin=None):
        object.__setattr__(self, "_cell", cell)
        object.__setattr__(self, "_origin", origin)
    def __setattr__(self, k, v):
        raise AttributeError("Clausal answer terms are immutable snapshots")
    @property
    def functor(self): return self._cell[0]
    def __getattr__(self, name):               # lazy field access by signature
        cell = object.__getattribute__(self, "_cell")
        _, fields = REGISTRY[cell[0]]
        try:
            i = fields.index(name)
        except ValueError:
            raise AttributeError(f"{cell[0]} has no field {name!r}") from None
        v = cell[1 + i]
        if isinstance(v, tuple) and v and isinstance(v[0], str):
            return TermProxy(v, object.__getattribute__(self, "_origin"))
        return v
    def construct(self):                       # explicit, validated, provenance-chained
        cell, origin = self._cell, self._origin
        cls, fields = REGISTRY[cell[0]]
        args = [a.construct() if type(a) is TermProxy else
                (TermProxy(a).construct() if isinstance(a, tuple) and a and isinstance(a[0], str) else a)
                for a in cell[1:]]
        try:
            return cls(*args)
        except Exception as e:
            raise ClausalMaterializationError(
                f"while materializing {_render(cell)}"
                + (f"\n  answer to query: {origin}" if origin else "")) from e
    def __repr__(self): return f"<term {_render(self._cell)}>"
    def __eq__(self, o): return type(o) is TermProxy and self._cell == o._cell
    def __hash__(self): return hash(self._cell)

# ── user-side classes (validating!) ──
class date(metaclass=PredicateMeta):
    _fields = ("y", "m", "d")
    def __init__(s, y, m, d): s.value = datetime.date(y, m, d)   # validates
class booking(metaclass=PredicateMeta):
    _fields = ("who", "when")
    def __init__(s, who, when): s.who, s.when = who, when

# ── engine yields a snapshot proxy (deref-walked cell) ──
good = TermProxy(("booking", "ada", ("date", 2026, 9, 3)),  origin="bookings(ada, D)")
bad  = TermProxy(("booking", "ada", ("date", 2026, 2, 31)), origin="bookings(ada, D)")

# 1. existing isinstance/match-case code works UNCHANGED on the proxy
print("isinstance(proxy, booking):", isinstance(good, booking))
match good:
    case booking(who=w, when=d):
        print("MATCH_CLASS on proxy: who =", w, "| when =", d, "| when.y =", d.y)

# 2. no eager conversion: nested access is lazy, terms are frozen
try: good.who = "eve"
except AttributeError as e: print("mutation blocked:", e)

# 3. explicit materialization; the invalid date fails WITH provenance
print("construct(good):", good.construct().when.value)
try:
    bad.construct()
except ClausalMaterializationError as e:
    print("construct(bad) chained error:\n  ", e, "\n   caused by:", repr(e.__cause__))
