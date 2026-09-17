"""§4 q1 feasibility: can the importer's Database hold the EXPORTER's row?

If yes, "shared row" is a key insert, not new machinery -- and the importing
db's own `row(functor, arity)` becomes the answer to "where does this name's
predicate live", which is what the whole P1 reroute wants to be true.

Controls: (1) before planting, the importer's db must NOT know the key --
otherwise the test proves nothing; (2) a key never planted must stay unknown.
"""
import sys, tempfile, pathlib, textwrap
d = pathlib.Path(tempfile.mkdtemp())
(d / "xp.clausal").write_text(textwrap.dedent("""
    -module(xp, [edge])
    edge(1, 2),
    edge(2, 3),
"""))
(d / "im.clausal").write_text(textwrap.dedent("""
    -module(im, [two_hop])
    -import_from(xp, [edge])
    two_hop(X, Z) <- (edge(X, Y), edge(Y, Z)),
"""))
sys.path.insert(0, str(d))
import clausal  # noqa: F401
import xp, im

xdb = xp.__dict__["$module"].db
idb = im.__dict__["$module"].db

print("-- control 1: the importer's db must not already know edge/2 --")
print(f"   idb.row('edge', 2)        {idb.row('edge', 2)}   (expect None)")
assert idb.row("edge", 2) is None, "control failed: nothing to prove"

shared = xdb.row("edge", 2)
print(f"   exporter row              {shared!r}"[:100])
print(f"   its clause count          {len(shared.clauses)}")

print("\n-- plant the exporter's row in the importer's table --")
idb._rows[("edge", 2)] = shared
got = idb.row("edge", 2)
print(f"   idb.row('edge',2) is the exporter's row   {got is shared}")
print(f"   clauses visible through the importer      {len(got.clauses)}")
print(f"   got.db is the EXPORTER's db               {got.db is xdb}")
print(f"   got.db is the importer's db               {got.db is idb}")
print(f"   dispatch reachable                        {got.dispatch_fn is not None}")

print("\n-- does the ownership test 'row.db is not mine' work? --")
own = idb.row("two_hop", 2)
print(f"   importer's OWN predicate: row.db is idb   {own.db is idb}")
print(f"   imported predicate:       row.db is idb   {got.db is idb}  <- the 'belongs elsewhere' test")

print("\n-- control 2: an unplanted key stays unknown --")
print(f"   idb.row('never_planted', 9)   {idb.row('never_planted', 9)}   (expect None)")

print("\n-- and is_defined still reports on THIS db's own storage --")
print(f"   idb.is_defined('edge', 2)     {idb.is_defined('edge', 2)}")
print(f"   xdb.is_defined('edge', 2)     {xdb.is_defined('edge', 2)}")
