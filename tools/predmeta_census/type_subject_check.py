"""Dataflow check over ALL 50 category-A sites (26 human-read + 24 auto).

Flags sites whose isinstance subject is a TYPE OBJECT -- `isinstance(type(x),
PredicateMeta)` asks "is x a term INSTANCE" (category G), the opposite question
from "is this NAME a predicate" (category A). The census's rule matched the
LINE; this one follows the local.

NEGATIVE CONTROL at the bottom: a synthetic A-shaped site must NOT be flagged,
and a synthetic G-shaped site MUST be.
"""
import ast, pathlib, sys, re, collections  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import census

def all_A_sites():
    human = [(f.rsplit(":", 1)[0], int(f.rsplit(":", 1)[1]))
             for f, v in census.VERDICTS.items() if v == "A"]
    auto = []
    for p in sorted(census.ROOT.rglob("*")):
        if p.suffix not in (".py", ".c", ".h") or not p.is_file():
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if census.PAT.search(line) and census.classify(line) == "A-predicate-test":
                auto.append((str(p.relative_to(census.ROOT.parent)), n))
    return sorted(set(human) | set(auto)), sorted(human), sorted(auto)

def enclosing(path, line):
    tree = ast.parse(pathlib.Path(path).read_text())
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best.lineno:
                    best = node
    return best

def analyse(func_node, line):
    """(subjects_on_line, locals_assigned_from_type)"""
    subjects = []
    for n in ast.walk(func_node):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "isinstance" and len(n.args) == 2
                and isinstance(n.args[1], ast.Name) and n.args[1].id == "PredicateMeta"
                and n.args[1].lineno == line):
            subjects.append(n.args[0])
    hoists = {}
    for n in ast.walk(func_node):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) \
           and isinstance(n.value.func, ast.Name) and n.value.func.id == "type":
            for t in n.targets:
                if isinstance(t, ast.Name):
                    hoists[t.id] = n.lineno
    return subjects, hoists

if __name__ == "__main__":
    ALL, HUM, AUTO = all_A_sites()
    print(f"category-A population: {len(ALL)}  (human-read {len(HUM)} + auto {len(AUTO)})")
    flagged = []
    examined = 0
    for f, l in ALL:
        node = enclosing(f, l)
        if node is None:
            continue
        examined += 1
        subs, hoists = analyse(node, l)
        for a in subs:
            direct = isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "type"
            hoisted = isinstance(a, ast.Name) and a.id in hoists
            if direct or hoisted:
                tag = "DIRECT type()" if direct else f"HOISTED: {a.id} = type(...) at line {hoists[a.id]}"
                flagged.append((f, l, tag, f in dict.fromkeys(x[0] for x in HUM) and (f, l) in HUM))
    print(f"sites examined: {examined}/{len(ALL)}")
    print(f"TYPE-SUBJECT (category G shape) sites found: {len(flagged)}")
    for f, l, tag, was_human in flagged:
        src = pathlib.Path(f).read_text().splitlines()[l-1].strip()
        print(f"  {f}:{l}  [{'human-read' if (f,l) in HUM else 'AUTO, never read'}]  {tag}")
        print(f"       {src[:110]}")

    # ---- controls -------------------------------------------------------
    print("\n-- controls --")
    tmp = pathlib.Path("/home/node/.claude/jobs/af5b4bbe/tmp/_ctl.py")
    tmp.write_text(
        "def f_A(module_dict, functor):\n"
        "    pred_cls = module_dict.get(functor)\n"
        "    if not isinstance(pred_cls, PredicateMeta):\n"
        "        return None\n"
        "def f_G(head):\n"
        "    cls = type(head)\n"
        "    if isinstance(cls, PredicateMeta):\n"
        "        return cls\n")
    for name, line, expect in (("f_A", 3, False), ("f_G", 7, True)):
        node = enclosing(str(tmp), line)
        subs, hoists = analyse(node, line)
        got = any((isinstance(a, ast.Name) and a.id in hoists) or
                  (isinstance(a, ast.Call) and getattr(a.func, "id", "") == "type") for a in subs)
        print(f"  control {name}: expected flagged={expect}  got={got}  "
              f"{'PASS' if got == expect else 'FAIL'}")
