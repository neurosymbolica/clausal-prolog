"""Re-measure Audit 3's 'silently wrong' row on the OLD .pl path (prolog_to_clausal).

Run from the worktree root:
  ./venv/bin/python implementation_plans/native-iso-reader-step2-2026-09-29/translator_probe/probe_translator.py
Each case: the translated seam text line that matters, then the answers through the REAL PrologLoader.
"""
import sys, os, importlib, pathlib, shutil, warnings
warnings.filterwarnings("ignore")
ROOT = os.getcwd(); HERE = pathlib.Path(__file__).parent
sys.path.insert(0, ROOT); sys.path.insert(0, str(HERE))
import clausal
assert clausal.__file__.startswith(ROOT), clausal.__file__
for p in HERE.rglob("__pycache__"): shutil.rmtree(p, ignore_errors=True)
from clausal.tools.prolog_to_clausal import prolog_to_clausal
from clausal.tools.prolog_dialect import Dialect
from clausal.logic.solve import query
from clausal.logic.variables import Var

def show_translation(mod, grep):
    src = (HERE / "tpkg" / f"{mod}.pl").read_text()
    try:
        out = prolog_to_clausal(src, dialect=Dialect.scryer_reader())
    except Exception as e:
        print(f"  translate RAISED {type(e).__name__}: {str(e)[:160]}"); return
    for line in out.splitlines():
        if any(g in line for g in grep): print("  seam:", line.strip()[:150])

def answers(mod, pred):
    try:
        m = importlib.import_module(f"tpkg.{mod}")
    except Exception as e:
        return f"LOAD RAISED {type(e).__name__}: {str(e).splitlines()[0][:200]}"
    X = Var()
    try:
        return [s["X"] for s in query((pred, X), {"X": X}, m)]
    except Exception as e:
        return f"QUERY RAISED {type(e).__name__}: {str(e).splitlines()[0][:200]}"

cases = [
  ("sw_arith",  ["mx", "mn", "ab"], ["max", "min", "abs"],    "expect [5] [3] [4]"),
  ("sw_setof",  ["s", "b"],         ["setof", "bagof"],       "expect ONE answer [1,2,3] each"),
  ("sw_profile",["t"],              ["get"],                  "look for a silent rename profile_get -> get"),
  ("sw_euro",   ["c"],              ["euro", "import"],       "expect [euro] (imported atom)"),
  ("sw_kitpath",["z"],              ["import", "use_module"], "expect [5] (unquoted path)"),
  ("sw_kitpath_q",["z"],            ["import", "use_module"], "expect [5] (quoted path)"),
]
for mod, preds, grep, expect in cases:
    print(f"== {mod}: {expect}")
    show_translation(mod, grep)
    for p in preds:
        print(f"  {p}/1 ->", answers(mod, p))
