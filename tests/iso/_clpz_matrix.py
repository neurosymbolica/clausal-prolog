"""The CLP(Z) propagation matrix: generated cases, the one ``.pl`` program
both engines run, and the parsers that turn each engine's output into
comparable answers.

Imported by ``test_clpz_propagation_matrix_scryer.py``; usable on its own
(``python -m tests.iso._clpz_matrix [large]``) to print the disagreements.

A *case* is one clause body: domain declarations, bindings and narrowings
of the variables, and one posted constraint, in a generated order (each
variable is bound or narrowed BEFORE or AFTER the constraint is posted).
Its answer is ``fail``, ``ex|<error term>`` or ``ok|<dom1>|<dom2>|...``,
each ``<dom>`` an integer or ``fd_dom/2``'s domain.  Scryer also labels
every case whose domains are finite and small, which gives the exact
solution set: a domain may be narrower than Scryer's and still right, but
never narrower than the solutions.

The generator is seeded and deterministic: the same size gives the same
cases in the same order, so a case's id (``k<index>``) and text are stable.
"""

from __future__ import annotations

import itertools
import random
import re

BIG = 2 ** 70

BINARY = ["+", "-", "*", "//", "div", "mod", "rem", "^", "min", "max"]
UNARY = ["abs", "neg"]
RELATIONS = ["#=", "#\\=", "#<", "#=<", "#>", "#>="]

DOMAINS = [
    "-3..3", "0..5", "1..4", "-6.. -2", "-5..5", "0..sup", "inf..0",
    "1\\/3\\/5", "-4.. -1\\/2..4", "0..0", f"{BIG}..{BIG + 3}", None, None,
]
EXPONENT_DOMAINS = ["0..3", "-1..3", "2..2", "0..sup", "-2..2", "1..2", None]
VALUES = [-7, -4, -3, -2, -1, 0, 0, 1, 2, 3, 4, 5, 7, 12, BIG, -BIG]


def expr_text(op, a, b=None):
    if op in ("min", "max"):
        return f"{op}({a},{b})"
    if op == "abs":
        return f"abs({a})"
    if op == "neg":
        return f"-({a})"
    if op in ("div", "mod", "rem"):
        return f"({a}) {op} ({b})"
    return f"({a}){op}({b})"


class Case:
    """One generated row: ``vars`` are the variable names in output order,
    ``body`` the goals in order."""

    def __init__(self, family, vars_, body):
        self.family = family
        self.vars = vars_
        self.body = body
        self.index = None

    @property
    def text(self):
        return ", ".join(self.body)

    @property
    def id(self):
        return f"k{self.index}"


def _dom_goal(var, dom):
    return f"{var} in {dom}"


def _narrow_goal(rng, var):
    c = rng.choice([-3, -1, 0, 1, 2, 4])
    kind = rng.choice(["#>", "#<", "#\\=", "in"])
    if kind == "in":
        return f"{var} in {c} .. {c + rng.choice([0, 1, 3])}"
    return f"{var} {kind} {c}"


SMALL_VALUES = [-2, -1, 0, 1, 2, 3, 5]


def _schedule(rng, constraint, var_doms, *, act_vars=None, small=()):
    """Domain declarations, bindings and narrowings, each before or after
    the constraint, in a random order."""
    pre, post = [], []
    for var, dom in var_doms.items():
        if dom is not None:
            (pre if rng.random() < 0.75 else post).append(_dom_goal(var, dom))
    for var in (act_vars or list(var_doms)):
        kind = rng.choice(["none", "bind", "bind", "narrow"])
        if kind == "none":
            continue
        # an exponent is never bound to a bignum: 2^(2^70) is not built
        pool = SMALL_VALUES if var in small else VALUES
        goal = (f"{var} = {rng.choice(pool)}" if kind == "bind"
                else _narrow_goal(rng, var))
        (pre if rng.random() < 0.5 else post).append(goal)
    rng.shuffle(pre)
    rng.shuffle(post)
    return pre + [constraint] + post


def _pick_dom(rng, op, var, exponent_var):
    if op == "^" and var == exponent_var:
        return rng.choice(EXPONENT_DOMAINS)
    return rng.choice(DOMAINS)


def _relation_text(rel, lhs, rhs):
    return f"{lhs} {rel} {rhs}"


def generate(scale=1, seed=20261028):
    rng = random.Random(seed)
    cases = []

    # 1. Every operator x relation x side, random domains and schedules.
    for op in BINARY + UNARY:
        for rel in RELATIONS:
            for side in ("lhs", "rhs"):
                for _ in range(5 * scale):
                    e = expr_text(op, "X", "Y")
                    rel_txt = (_relation_text(rel, "Z", e) if side == "lhs"
                               else _relation_text(rel, e, "Z"))
                    vs = ["X", "Y", "Z"] if op in BINARY else ["X", "Z"]
                    doms = {v: _pick_dom(rng, op, v, "Y") for v in vs}
                    cases.append(Case(f"op:{op}:{rel}", vs, _schedule(
                        rng, rel_txt, doms, small=("Y",) if op == "^" else ())))

    # 2. Late against early binding: for #= on each operator, two of the
    #    variables bound to values (before or after the post), the third
    #    left with a domain; then every order of binding all three.
    for op in BINARY + UNARY:
        vs = ["X", "Y", "Z"] if op in BINARY else ["X", "Z"]
        e = expr_text(op, "X", "Y")
        for _ in range(4 * scale):
            vals = {v: rng.choice([-3, -2, -1, 0, 1, 2, 3, 5, 7]) for v in vs}
            if op == "^":
                vals["Y"] = rng.choice([0, 1, 2, 3])
            if rng.random() < 0.5:   # make it consistent where we can
                vals["Z"] = _eval(op, vals["X"], vals.get("Y"))
                if vals["Z"] is None:
                    vals["Z"] = 1
            free = rng.choice(vs)
            for timing in ("pre", "post"):
                bind = [f"{v} = {vals[v]}" for v in vs if v != free]
                body = (bind + [f"Z #= {e}"] if timing == "pre"
                        else [f"Z #= {e}"] + bind)
                cases.append(Case(f"bind2:{op}:{timing}", vs, body))
            for perm in itertools.permutations(vs):
                for split in range(len(vs) + 1):
                    bind = [f"{v} = {vals[v]}" for v in perm]
                    body = bind[:split] + [f"Z #= {e}"] + bind[split:]
                    cases.append(Case(f"order:{op}", vs, body))

    # 3. Nested combinations of two operators.
    ops2 = BINARY + UNARY
    for _ in range(120 * scale):
        o1, o2 = rng.choice(ops2), rng.choice(ops2)
        inner = expr_text(o1, "X", "Y")
        e = expr_text(o2, inner, "W") if rng.random() < 0.5 else expr_text(o2, "W", inner)
        rel = rng.choice(RELATIONS)
        vs = ["X", "Y", "W", "Z"]
        doms = {v: rng.choice(DOMAINS[:10]) for v in vs}
        if "^" in (o1, o2):
            doms["Y"] = rng.choice(EXPONENT_DOMAINS[:6])
            doms["W"] = rng.choice(EXPONENT_DOMAINS[:6])
        # under ^ every operand may become an exponent: no bignum bindings
        small = ("X", "Y", "W") if "^" in (o1, o2) else ()
        cases.append(Case(f"nested:{o1}:{o2}:{rel}", vs, _schedule(
            rng, _relation_text(rel, "Z", e), doms, small=small)))

    # 4. Reification: B #<==> C, B #==> C, C #==> B, B #\/ C, C1 #\/ C2,
    #    with B bound early and late.
    for _ in range(60 * scale):
        rel = rng.choice(RELATIONS)
        op = rng.choice(["+", "-", "*", "abs", "min", "max", "mod"])
        rhs = rng.choice(["Y", "Y + 1", expr_text(op, "Y", "2"), "2"])
        c = f"(X {rel} {rhs})"
        form = rng.choice(["<==>", "==>", "<==", "\\/", "pair"])
        if form == "<==>":
            con = f"B #<==> {c}"
        elif form == "==>":
            con = f"B #==> {c}"
        elif form == "<==":
            con = f"{c} #==> B"
        elif form == "\\/":
            con = f"B #\\/ {c}"
        else:
            rel2 = rng.choice(RELATIONS)
            con = f"{c} #\\/ (Y {rel2} X)"
        vs = ["B", "X", "Y"]
        doms = {"B": rng.choice(["0..1", None]),
                "X": rng.choice(DOMAINS[:10]), "Y": rng.choice(DOMAINS[:10])}
        body = _schedule(rng, con, doms, act_vars=["X", "Y"])
        bval = rng.choice([None, 0, 1])
        if bval is not None:
            at = rng.choice([0, len(body)])
            body.insert(at, f"B = {bval}")
        cases.append(Case(f"reif:{form}", vs, body))

    # 5. Hand-picked edges: division by zero, inf/sup, bignums, the known
    #    late-binding product.
    edges = [
        (["R", "T"], ["R*T #= 14", "T = 7"]),
        (["R", "T"], ["T = 7", "R*T #= 14"]),
        (["X"], ["X #= 1 // 0"]),
        (["X"], ["X #= 1 div 0"]),
        (["X"], ["X #= 1 mod 0"]),
        (["X"], ["X #= 1 rem 0"]),
        (["X", "Y"], ["X #= 7 // Y", "Y = 0"]),
        (["X", "Y"], ["X #= 7 mod Y", "Y = 0"]),
        (["X", "Y"], ["Y in 0..0", "X #= 7 // Y"]),
        (["X", "Y"], ["Y in -1..1", "X #= 7 // Y"]),
        (["X", "Y"], ["X #= 0 ^ Y", "Y = -1"]),
        (["X", "Y"], ["X #= 2 ^ Y", "Y = -1"]),
        (["X", "Y"], ["X #= 1 ^ Y", "Y = -1"]),
        (["X", "Y"], ["X #= (-1) ^ Y", "Y = -1"]),
        (["X"], ["X #= 2 ^ 70"]),
        (["X", "Y"], ["X #= Y * Y", f"X = {BIG * BIG}"]),
        (["X", "Y"], ["X #= Y + 1", f"Y in {BIG}..sup"]),
        (["X", "Y"], ["X #= 2 ^ Y", f"X = {BIG}"]),
        (["X", "Y"], ["X #= Y ^ 2", "X = 49"]),
        (["X", "Y"], ["X #= Y ^ 2", "X in 50..60"]),
        (["X", "Y"], ["X #= abs(Y)", "X = 3"]),
        (["X", "Y"], ["X #= -Y", "Y in inf..3"]),
        (["X", "Y"], ["X #> Y", "Y in 0..sup"]),
        (["X", "Y"], ["X * X #= Y", "Y in 2..3"]),
        (["X", "Y"], ["X #= Y mod 3"]),
        (["X", "Y"], ["X #= Y rem -3"]),
        (["X", "Y"], ["X #= Y // 3", "X = 2"]),
        (["X", "Y"], ["X #= Y div 3", "X = -2"]),
        (["X", "Y"], ["X #= min(Y, 3)", "X = 5"]),
        (["X", "Y"], ["X #= max(Y, 3)", "X = 5"]),
        (["X", "Y", "Z"], ["X + Y #= Z", "X in 0..3", "Y in 0..3", "Z = 0"]),
        (["X", "Y", "Z"], ["X * Y #= Z", "X in 1..3", "Y in 1..3", "Z = 5"]),
    ]
    for vs, body in edges:
        cases.append(Case("edge", vs, body))

    for i, c in enumerate(cases):
        c.index = i
    return cases


def _eval(op, x, y):
    """A reference value for consistent bindings (None when undefined)."""
    try:
        if op == "+": return x + y
        if op == "-": return x - y
        if op == "*": return x * y
        if op == "//": return int(x / y) if y else None
        if op == "div": return x // y if y else None
        if op == "mod": return x % y if y else None
        if op == "rem": return x - y * int(x / y) if y else None
        if op == "^": return x ** y if y >= 0 else None
        if op == "min": return min(x, y)
        if op == "max": return max(x, y)
        if op == "abs": return abs(x)
        if op == "neg": return -x
    except (ZeroDivisionError, OverflowError):
        return None
    return None


PRELUDE = """\
:- use_module(library(clpz)).
:- use_module(library(lists)).
show(N) :- catch((case(N, Vs) -> R = ok(Vs) ; R = fail), E, R = ex(E)),
    write(N), write('|'), out(R), nl.
out(fail) :- write(fail).
out(ex(E)) :- write(ex), write('|'), writeq(E).
out(ok(Vs)) :- write(ok), outv(Vs).
outv([]).
outv([V|Vs]) :- write('|'), ( integer(V) -> write(V) ; fd_dom(V, D), write(D) ), outv(Vs).
small([], _).
small([V|Vs], S0) :- fd_size(V, S), integer(S), S1 is S0 * S, S1 =< 4000, small(Vs, S1).
truth(N) :- write(t), write(N), write('|'),
    catch(( \\+ (case(N, Vs), \\+ small(Vs, 1)) ->
              findall(Vs, (case(N, Vs), label(Vs)), Ss), write(Ss)
          ; write(big) ), _, write(err)), nl.
window([], _).
window([V|Vs], W) :- ( integer(V) -> true ; NW is -W, V in NW..W ), window(Vs, W).
wtruth(N, W) :- write(w), write(N), write('|'),
    catch(( findall(Vs, (case(N, Vs), window(Vs, W), label(Vs)), Ss), write(Ss)
          ), _, write(err)), nl.
wloop([]).
wloop([N-W|Ns]) :- wtruth(N, W), wloop(Ns).
loop(K, N) :- ( K > N -> true ; show(K), K1 is K + 1, loop(K1, N) ).
tloop(K, N) :- ( K > N -> true ; truth(K), K1 is K + 1, tloop(K1, N) ).
"""


def program(cases):
    lines = [PRELUDE]
    for c in cases:
        lines.append(f"case({c.index}, [{','.join(c.vars)}]) :- {c.text}.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- parsing

_INT = r"-?\s*\d+|inf|sup"
_PIECE = re.compile(rf"^\s*({_INT})\s*(?:\.\.\s*({_INT}))?\s*$")


def _bound(tok):
    tok = tok.replace(" ", "")
    if tok == "inf":
        return float("-inf")
    if tok == "sup":
        return float("inf")
    return int(tok)


def parse_dom(text):
    """``1..3\\/5`` -> ((1, 3), (5, 5)), merged and sorted."""
    ivs = []
    for piece in text.split("\\/"):
        m = _PIECE.match(piece)
        if not m:
            raise ValueError(f"unparsed domain {text!r}")
        lo = _bound(m.group(1))
        hi = _bound(m.group(2)) if m.group(2) else lo
        ivs.append((lo, hi))
    ivs.sort()
    merged = []
    for lo, hi in ivs:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return tuple(merged)


def parse_answer(text):
    """``ok|..|..`` -> ("ok", (dom, ...)); ``fail`` -> ("fail",);
    ``ex|E`` -> ("ex", formal, context)."""
    text = text.strip()
    if text == "fail":
        return ("fail",)
    if text.startswith("ex|"):
        err = re.sub(r"\s+", "", text[3:])
        m = re.match(r"^error\((.*),([^,]*)\)$", err)
        formal = err
        if err.startswith("error("):
            formal = _first_arg(err[len("error("):])
        return ("ex", formal, err)
    if text.startswith("ok"):
        parts = text.split("|")[1:]
        return ("ok", tuple(parse_dom(p) for p in parts))
    return ("raw", text)


def _first_arg(s):
    depth = 0
    for i, ch in enumerate(s):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return s[:i]
            depth -= 1
        elif ch == "," and depth == 0:
            return s[:i]
    return s


def parse_lines(out, prefix=""):
    res = {}
    for line in out.splitlines():
        if prefix:
            if not line.startswith(prefix):
                continue
            line = line[len(prefix):]
        k, sep, rest = line.partition("|")
        if sep and k.strip().isdigit():
            res[int(k)] = rest
    return res


def parse_truth(text):
    """``[[1,2],[3,4]]`` -> list of tuples; ``big``/``err`` -> None."""
    text = text.strip()
    if text in ("big", "err") or not text.startswith("["):
        return None
    nums = text.replace("[", " [ ").replace("]", " ] ").replace(",", " ")
    rows, cur, depth = [], [], 0
    for tok in nums.split():
        if tok == "[":
            depth += 1
            if depth == 2:
                cur = []
        elif tok == "]":
            if depth == 2:
                rows.append(tuple(cur))
            depth -= 1
        else:
            cur.append(int(tok))
    return rows


# ------------------------------------------------------------- comparing

def _contains(dom, v):
    return any(lo <= v <= hi for lo, hi in dom)


def _subset(d1, d2):
    """d1 within d2 (interval lists)."""
    return all(any(l2 <= l1 and h1 <= h2 for l2, h2 in d2) for l1, h1 in d1)


def classify(clausal, scryer, truth, clausal_text=None, scryer_text=None):
    """One of: agree, print (the same answer written differently), weaker,
    stronger (checked against the solutions when Scryer could label the
    case), unsound, fail_vs_ok (Clausal fails where Scryer narrows, with no
    solution set to check against), error, error_context, mixed, raw."""
    if clausal == scryer:
        if clausal_text is not None and scryer_text is not None and \
                re.sub(r"\s+", "", clausal_text) != re.sub(r"\s+", "", scryer_text):
            return "print"
        return "agree"
    ck, sk = clausal[0], scryer[0]
    if "raw" in (ck, sk):
        return "raw"
    if ck == "ex" or sk == "ex":
        if ck == "ex" and sk == "ex" and clausal[1] == scryer[1]:
            return "error_context"
        return "error"
    if ck == "fail" and sk == "ok":
        if truth == []:
            return "stronger"
        return "unsound" if truth else "fail_vs_ok"
    if ck == "ok" and sk == "fail":
        return "weaker"
    cd, sd = clausal[1], scryer[1]
    if truth:
        for i, d in enumerate(cd):
            for row in truth:
                if not _contains(d, row[i]):
                    return "unsound"
    if all(_subset(c, s) for c, s in zip(cd, sd)):
        return "stronger"
    if all(_subset(s, c) for c, s in zip(cd, sd)):
        return "weaker"
    return "mixed"


def run_scryer_matrix(cases, path, run_scryer, chunk=500, timeout=600):
    """Scryer's answers and solution sets, ``({index: answer}, {index:
    solutions})``.  Run in chunks, so a case Scryer cannot finish costs its
    chunk (those rows read ``raw|...``), not the run."""
    import subprocess
    with open(path, "w") as fh:
        fh.write(program(cases))
    answers, truths = {}, {}
    for start in range(0, len(cases), chunk):
        end = min(start + chunk, len(cases)) - 1
        try:
            proc = run_scryer(path, [f"loop({start}, {end})",
                                     f"tloop({start}, {end})"], timeout=timeout)
            out = proc.stdout
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        answers.update(parse_lines(out))
        truths.update(parse_lines(out, "t"))
    return answers, truths


def window_truth(cases, ids, path, run_scryer, timeout=600):
    """Scryer's solutions of each case in *ids* with every variable also
    in -W..W (W shrinking with the number of variables): not the whole
    solution set of an unbounded case, but every solution it holds must
    lie in an answer's domains -- the check for a row where Clausal
    narrows further than Scryer and Scryer cannot label the case."""
    if not ids:
        return {}
    by_index = {c.index: c for c in cases}
    pairs = []
    for i in ids:
        n = len(by_index[i].vars)
        pairs.append(f"{i}-{ {1: 60, 2: 40, 3: 14, 4: 7}.get(n, 5) }")
    with open(path, "w") as fh:
        fh.write(program(cases))
    proc = run_scryer(path, [f"wloop([{','.join(pairs)}])"], timeout=timeout)
    return parse_lines(proc.stdout, "w")


def run_clausal_matrix(cases, path, name="_clpz_matrix", case_timeout=20):
    import contextlib
    import io
    from clausal.import_hook import _load_module
    from clausal.logic.solve import solve
    from clausal.logic.variables import Trail
    with open(path, "w") as fh:
        fh.write(program(cases))
    import signal
    import threading
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # the cases' singleton B
        mod = _load_module(name, str(path))
    alarm = threading.current_thread() is threading.main_thread()

    def _timeout(signum, frame):
        raise TimeoutError("case timed out")
    old = signal.signal(signal.SIGALRM, _timeout) if alarm else None
    out = {}
    try:
        for c in cases:
            buf = io.StringIO()
            try:
                if alarm:
                    signal.alarm(case_timeout)
                with contextlib.redirect_stdout(buf):
                    for _ in solve(("show", c.index), mod, Trail()):
                        break
                line = buf.getvalue().strip()
                out[c.index] = line.partition("|")[2] if line else "raw|no output"
            except Exception as exc:   # an engine crash is a row, not a stop
                out[c.index] = f"raw|python {type(exc).__name__}: {exc}"
            finally:
                if alarm:
                    signal.alarm(0)
    finally:
        if alarm:
            signal.signal(signal.SIGALRM, old)
    return out
