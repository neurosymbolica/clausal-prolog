"""What does -import_from actually bind, and where does an imported call land?

Spec §4 q1 asks whether the replacement for the class should be delegation in
the Database, a per-module alias table, or a shared row. That question can only
be answered against what the import ACTUALLY does today, so: two modules, one
importing from the other, and look at every link in the chain.
"""
import sys, tempfile, pathlib, textwrap

d = pathlib.Path(tempfile.mkdtemp())
(d / "exporter.clausal").write_text(textwrap.dedent("""
    -module(exporter, [edge])
    edge(1, 2),
    edge(2, 3),

"""))
(d / "importer.clausal").write_text(textwrap.dedent("""
    -module(importer, [two_hop])
    -import_from(exporter, [edge])
    two_hop(X, Z) <- (edge(X, Y), edge(Y, Z)),
"""))
(d / "aliaser.clausal").write_text(textwrap.dedent("""
    -module(aliaser, [hop])
    -import_from(exporter, [alias(edge, link)])
    hop(X, Y) <- (link(X, Y)),
"""))
sys.path.insert(0, str(d))
import clausal  # noqa: F401
import exporter, importer, aliaser

def show(tag, obj):
    print(f"  {tag:34} {obj!r}")

print("== what the exporter binds at module level ==")
e = exporter.edge
show("type(exporter.edge)", type(e))
show("exporter.edge._fields", e._fields)
edb = exporter.__dict__["$module"].db
show("exporter db row('edge',2) is not None", edb.row("edge", 2) is not None)
show("exporter.edge._row is that row", e._row is edb.row("edge", 2))

print("\n== what the importer binds ==")
i = importer.edge
show("importer.edge IS exporter.edge", i is e)
idb = importer.__dict__["$module"].db
show("importer db row('edge',2)", idb.row("edge", 2))
show("importer.edge._row.db is exporter's db", i._row.db is edb)
show("dotted key 'exporter.edge' present", "exporter.edge" in importer.__dict__)

print("\n== the ALIASED import ==")
a = aliaser.link
show("aliaser.link IS exporter.edge", a is e)
show("aliaser.link.__name__", a.__name__)
show("'edge' bound in aliaser?", "edge" in aliaser.__dict__)
adb = aliaser.__dict__["$module"].db
show("aliaser db row('edge',2)", adb.row("edge", 2))
show("aliaser db row('link',2)", adb.row("link", 2))

print("\n== does the imported call actually work, and whose clauses? ==")
from clausal.logic.variables import Var
X, Z = Var(), Var()
print("   two_hop answers:", sorted((X.value, Z.value) for _ in importer.two_hop(X, Z)))
A, B = Var(), Var()
print("   hop answers    :", sorted((A.value, B.value) for _ in aliaser.hop(A, B)))

print("\n== how a goal resolves at runtime ==")
show("exporter.edge._get_dispatch(2)", exporter.edge._get_dispatch(2))
show("importer's own db dispatch for edge/2", idb._dispatch.get(("edge", 2)))
