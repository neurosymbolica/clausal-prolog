import sys, os, tempfile, datetime
sys.path.insert(0, "/workspace/clausal-bug-fix/.claude/worktrees/iso-l3")
import clausal
from clausal.import_hook import _load_module
from clausal import Var
from clausal.logic.seam import once_bind, export

SRC = ("-module(do, [unsorted, sorted_dates, date(Y, M, D)])\n"
       "unsorted([date(2026,1,15), date(2026,1,2), date(2026,1,9), "
       "date(2025,12,31), date(2026,2,1)]),\n"
       "sorted_dates(S) <- (unsorted(L), msort(L, S)),\n")
d = tempfile.mkdtemp(); p = os.path.join(d, "do.clausal")
open(p, "w").write(SRC)
try:
    mod = _load_module("do", p)
    V = Var(); ok = once_bind(("sorted_dates", V), mod.__dict__)
    got = export(V)
    print("engine msort/2 on date cells:")
    for c in got: print("   ", c)
    want = [("date",2025,12,31),("date",2026,1,2),("date",2026,1,9),
            ("date",2026,1,15),("date",2026,2,1)]
    print("\nchronological:", got == want)
except Exception as e:
    print(f"{type(e).__name__}: {str(e)[:220]}")
