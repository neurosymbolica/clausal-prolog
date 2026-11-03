"""Lists a clause head builds after its body, and the programs that read them.

``mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).`` meets an unbound
third argument, so the head match defers ``[N|T]`` and builds it at the
solution, after the body has bound ``T`` (``_head_list_unify_output``,
clausal/logic/runtime/_list_unify.c).  How it builds that list decides
whether building N elements costs N or N^2; see
todo/a-list-a-clause-head-builds-after-its-body-copies-the-tail-quadratic-2026-11-03.md.

Everything runs through the engine, as Clausal Prolog: the program below is
written to a temporary ``.clausal`` file, and each row is timed INSIDE it
with ``statistics(cpu_time, T)``, so Python start-up and answer conversion
are not counted.

Builders (one list each, the same N elements N, N-1, ..., 1):

* ``mk``  -- ``mk(N, Tail, L)``, the list in the head, built after the body;
  ``Tail`` is ``[]`` (nil), a fresh variable (open) or ``foo`` (improper).
* ``inc`` -- ``inc([H|T], [H1|T1]) :- H1 is H+1, inc(T, T1).``, the map
  every program writes, over the nil list ``mk`` built (nil tail only).

Readers, each timed on the list ``mk`` built (and a second, equal list
for ``=``, ``==`` and ``compare``):

* nil: length/2, nth1/3 (the last element), member/2 (the last element),
  append/3, msort/2, sum_list/2, findall/3 over member/2, findall/3 copying
  the list, ==, =, compare/3, copy_term/2, term_to_atom/2,
  write_to_string/2, and a clause recursing down it with ``[_|T]``;
* open and improper: the ones that are defined on such a list
  (==, =, compare/3, copy_term/2, findall/3 copying it, term_to_atom/2,
  write_to_string/2, and the recursion, last because on an open list it
  binds the tail).

Run from the repo root::

    python benchmarks/bench_head_list_build.py                 # 1k 4k 16k
    python benchmarks/bench_head_list_build.py 1000 4000 16000 64000
    python benchmarks/bench_head_list_build.py 1000 4000 --repeat 3  # min of 3
    python benchmarks/bench_head_list_build.py --profile nil 8000

Each (tail, size) row runs in its own process, capped at ``--mem`` GB of
address space (default 4) and ``--budget`` seconds (default 300), so a
quadratic row stops instead of taking the machine with it: before the fix
of the todo above, ``mk(64000, [], L)`` alone held over 30 GB (each level
keeps its own copy of the rest).  A row that hits a cap shows as
``mem>``/``time>``; the larger sizes of that tail are then skipped.  The
peak resident memory of each row is reported as ``peak_rss_mb``.
"""
from __future__ import annotations

import argparse
import cProfile
import os
import pstats
import json
import resource
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

_COMMON = r"""
mk(0, L, L).
mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).

inc([], []).
inc([H|T], [H1|T1]) :- H1 is H+1, inc(T, T1).

walk([]).
walk([_|T]) :- walk(T).

walk_improper(foo).
walk_improper([_|T]) :- walk_improper(T).

tail_of(nil, []).
tail_of(open, _).
tail_of(improper, foo).

% The builds alone, for --profile.
build(Tail, N) :- tail_of(Tail, Z), mk(N, Z, _).
build_inc(N) :- mk(N, [], L), inc(L, _).
"""

# (reader, goal) per tail, in the order they run.  L and L2 are two equal
# lists mk/3 built (sharing the tail Z when it is open).  Each goal is timed
# inline (statistics/2 around it in the clause body), never through call/1,
# which would compile the goal -- and the list in it -- as a query first.
READERS = {
    "nil": [
        ("build", "mk(N, Z, L)"),
        ("build_inc", "inc(L, _)"),
        ("length", "length(L, _)"),
        ("nth1", "nth1(N, L, _)"),
        ("member", "member(1, L)"),
        ("append", "append(L, [x], _)"),
        ("msort", "msort(L, _)"),
        ("sum_list", "sum_list(L, _)"),
        ("findall_member", "findall(X, member(X, L), _)"),
        ("findall_copy", "findall(L, true, _)"),
        ("identical", "L == L2"),
        ("unify", "L = L2"),
        ("compare", "compare(_, L, L2)"),
        ("copy_term", "copy_term(L, _)"),
        ("term_to_atom", "term_to_atom(L, _)"),
        ("write_to_string", "write_to_string(L, _)"),
        ("recurse", "walk(L)"),
    ],
    "open": [
        ("build", "mk(N, Z, L)"),
        ("identical", "L == L2"),
        ("unify", "L = L2"),
        ("compare", "compare(_, L, L2)"),
        ("copy_term", "copy_term(L, _)"),
        ("findall_copy", "findall(L, true, _)"),
        ("term_to_atom", "term_to_atom(L, _)"),
        ("write_to_string", "write_to_string(L, _)"),
        ("recurse", "walk(L)"),                 # last: binds Z = []
    ],
    "improper": [
        ("build", "mk(N, Z, L)"),
        ("identical", "L == L2"),
        ("unify", "L = L2"),
        ("compare", "compare(_, L, L2)"),
        ("copy_term", "copy_term(L, _)"),
        ("findall_copy", "findall(L, true, _)"),
        ("term_to_atom", "term_to_atom(L, _)"),
        ("write_to_string", "write_to_string(L, _)"),
        ("recurse", "walk_improper(L)"),
    ],
}


def _program():
    clauses = [_COMMON]
    for tail, readers in READERS.items():
        out = ", ".join(f"{name}-S{i}" for i, (name, _) in enumerate(readers))
        body = [f"tail_of({tail}, Z)"]
        for i, (name, goal) in enumerate(readers):
            body.append(f"statistics(cpu_time, A{i}), {goal}, "
                        f"statistics(cpu_time, B{i}), S{i} is B{i} - A{i}")
            if name == "build":
                body.append("mk(N, Z, L2)")
        clauses.append(f"bench({tail}, N, [{out}]) :-\n    "
                       + ",\n    ".join(body) + ".\n")
    return "\n".join(clauses)


PROGRAM = _program()

TAILS = ("nil", "open", "improper")


def load():
    from clausal.testing import load_clausal_module
    fd, path = tempfile.mkstemp(suffix=".clausal", prefix="bench_head_list_")
    with os.fdopen(fd, "w") as f:
        f.write(PROGRAM)
    try:
        return load_clausal_module(path)
    finally:
        os.unlink(path)


def run_row(m, tail, n):
    """``{reader: seconds}`` for one tail and size, timed in the engine."""
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var, deref
    from clausal.terms import spelling
    r = Var()
    for _ in solve(("bench", tail, n, r), m):
        out = {}
        for pair in deref(r):
            pair = deref(pair)
            out[spelling(deref(pair[1]))] = float(deref(pair[2]))
        return out
    raise RuntimeError(f"bench({tail}, {n}) failed")


def table(results, sizes):
    for tail in TAILS:
        rows = results.get(tail)
        if not rows:
            continue
        names: list = []
        for row in rows.values():
            names.extend(k for k in row if k not in names)
        print(f"\n## tail = {tail}   (seconds of cpu time in the engine; "
              f"peak_rss_mb in MB)\n")
        print("| reader | " + " | ".join(f"N={n}" for n in sizes) + " |")
        print("|---|" + "---|" * len(sizes))
        for name in names:
            cells = []
            for n in sizes:
                v = rows.get(n, {}).get(name)
                if v is None:
                    cells.append("--")
                elif isinstance(v, str):
                    cells.append(v)
                elif name == "peak_rss_mb":
                    cells.append(f"{v:.0f}")
                else:
                    cells.append(f"{v:.4f}")
            print(f"| {name} | " + " | ".join(cells) + " |")


def profile(m, tail, n, top=15):
    from clausal.logic.solve import solve
    goal = ("build_inc", n) if tail == "inc" else ("build", tail, n)
    prof = cProfile.Profile()
    prof.enable()
    for _ in solve(goal, m):
        break
    prof.disable()
    pstats.Stats(prof).sort_stats("tottime").print_stats(top)


def run_capped(tail, n, mem_gb, budget):
    """One row in a child process under the caps: ``(row, None)`` or
    ``(None, reason)``."""
    def limit():
        cap = int(mem_gb * 2**30)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    cmd = [sys.executable, os.path.abspath(__file__), "--row", tail, str(n)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=budget, preexec_fn=limit)
    except subprocess.TimeoutExpired:
        return None, f"time>{budget:.0f}s"
    if out.returncode != 0:
        if "MemoryError" in out.stderr or out.returncode < 0:
            return None, f"mem>{mem_gb:g}GB"
        raise RuntimeError(f"row {tail} {n} failed:\n{out.stderr[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1]), None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sizes", nargs="*", type=int, default=[1000, 4000, 16000])
    ap.add_argument("--tails", default=",".join(TAILS))
    ap.add_argument("--budget", type=float, default=300.0,
                    help="seconds one row may take")
    ap.add_argument("--mem", type=float, default=4.0,
                    help="GB of address space one row may use")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run each row this many times; report the minimum")
    ap.add_argument("--profile", nargs=2, metavar=("TAIL", "N"),
                    help="cProfile one build: TAIL is nil/open/improper/inc")
    ap.add_argument("--row", nargs=2, metavar=("TAIL", "N"),
                    help=argparse.SUPPRESS)       # the child of run_capped
    args = ap.parse_args(argv)
    sys.setrecursionlimit(100000)
    if args.row:
        m = load()
        row = run_row(m, args.row[0], int(args.row[1]))
        row["peak_rss_mb"] = resource.getrusage(
            resource.RUSAGE_SELF).ru_maxrss / 1024
        print(json.dumps(row))
        return
    if args.profile:
        profile(load(), args.profile[0], int(args.profile[1]))
        return
    results: dict = {}
    for tail in args.tails.split(","):
        stopped = None
        for n in args.sizes:
            if stopped:
                results.setdefault(tail, {})[n] = {"build": stopped}
                continue
            t0 = time.perf_counter()
            row, why = None, None
            for _ in range(max(1, args.repeat)):
                one, why = run_capped(tail, n, args.mem, args.budget)
                if one is None:
                    row = None
                    break
                row = one if row is None else {
                    k: min(v, one.get(k, v)) for k, v in row.items()}
            wall = time.perf_counter() - t0
            if row is None:
                print(f"{tail} N={n}: {why}", file=sys.stderr, flush=True)
                stopped = "skipped"
                results.setdefault(tail, {})[n] = {"build": why}
                continue
            print(f"{tail} N={n}: build {row['build']:.3f}s, peak "
                  f"{row['peak_rss_mb']:.0f} MB, {wall:.1f}s wall",
                  file=sys.stderr, flush=True)
            results.setdefault(tail, {})[n] = row
    table(results, args.sizes)


if __name__ == "__main__":
    main()
