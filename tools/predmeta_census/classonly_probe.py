"""Enumerate EVERY attribute that lives on a predicate class, and split them
into (a) generated term protocol, (b) read-through onto the PredRow, (c)
CLASS-ONLY predicate state with no row home.

(c) is the set the retirement spec does not budget for: it claims the class
holds no state of its own. Found by hand so far: _index_plans(+_joint,
+_hierarchical), _tabled_home_db, _te_predicate_nodes. This asks the object.
"""
import sys, tempfile, pathlib, textwrap
from clausal.logic.predicate import PredicateMeta
from clausal.logic.database import PredRow

d = pathlib.Path(tempfile.mkdtemp())
(d / "probe_mod.clausal").write_text(textwrap.dedent("""
    -module(probe_mod, [edge, reach])
    edge(1, 2),
    edge(2, 3),
    edge(3, 4),
    reach(X, Y) <- (edge(X, Y)),
    reach(X, Z) <- (edge(X, Y), reach(Y, Z)),
"""))
sys.path.insert(0, str(d))
import clausal  # noqa: F401  (installs the import hook)
import probe_mod

cls = probe_mod.edge
print(f"probe predicate: {cls.__name__}/{len(cls._fields)}   metaclass={type(cls).__name__}")

readthrough = {n for n, v in vars(PredicateMeta).items() if isinstance(v, property)}
rowsurface = set(getattr(PredRow, "__slots__", ()) or ())
rowsurface |= {n for n, v in vars(PredRow).items() if isinstance(v, property)}
rowsurface |= {n for n in vars(PredRow) if not n.startswith("__")}

PROTOCOL = {"__init__", "__eq__", "__repr__", "__unify__", "__occurs_check__",
            "__iter__", "__match_args__", "__slots__", "__hash__", "_clausal_new",
            "__module__", "__qualname__", "__doc__", "__dict__", "__weakref__",
            "__dataclass_fields__"}

own = sorted(n for n in vars(cls) if n not in PROTOCOL and not n.startswith("__"))
print(f"\nattributes in vars(cls), protocol excluded: {len(own)}")
classonly = []
for n in own:
    where = ("read-through" if n in readthrough
             else "on PredRow" if n in rowsurface or n.lstrip("_") in rowsurface
             else "CLASS-ONLY")
    print(f"  {n:28} {where}")
    if where == "CLASS-ONLY":
        classonly.append(n)

# Attributes the METACLASS defines that are not properties and not protocol:
meta_extra = sorted(n for n, v in vars(PredicateMeta).items()
                    if not isinstance(v, property) and not n.startswith("__")
                    and not callable(v))
print(f"\nnon-property metaclass data attributes: {meta_extra}")

print(f"\nCLASS-ONLY on this predicate: {len(classonly)} -> {classonly}")

# The ones found by reading call sites, which may only appear after the
# compiler/tabling/term-expansion paths have run on a given predicate:
print("\nfound by reading call sites (may be absent on this probe predicate):")
for n in ("_index_plans", "_index_plans_joint", "_index_plans_hierarchical",
          "_tabled_home_db", "_te_predicate_nodes"):
    print(f"  {n:28} present now={hasattr(cls, n):5}  "
          f"read-through={n in readthrough}  on PredRow={n in rowsurface}")
