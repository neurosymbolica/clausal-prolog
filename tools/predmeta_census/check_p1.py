"""Machine-check the P1 per-site table against the census and the tree.

P0's lesson was that a number and its prose drift apart when only prose records
the verdicts. This checks three things and PRINTS THE SIZE OF EACH, because an
extraction that silently yields nothing is this lane's dominant failure mode:

  1. every category-A site the census knows about appears in P1_SITES.tsv
  2. every row in P1_SITES.tsv still points at a line containing PredicateMeta
  3. no row carries a disposition outside the documented set

Category A is the UNION of two populations, which is the correction this pass
made: the 26 sites human-read at P0 (census.VERDICTS) AND the 24 the census
classified "A-predicate-test" from the VARIABLE NAME alone and never read.

Run with --controls to watch each check go red on purpose.
"""
from __future__ import annotations
import pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import census  # noqa: E402

TABLE = HERE / "P1_SITES.tsv"
DISPOSITIONS = {"R", "R!", "R-enum", "S", "Q", "X4", "X4+Q", "NO",
                "G", "C", "C/G", "B", "D", "LAYER", "P4"}


def census_A_sites() -> set[tuple[str, int]]:
    human = {(k.rsplit(":", 1)[0], int(k.rsplit(":", 1)[1]))
             for k, v in census.VERDICTS.items() if v == "A"}
    auto = set()
    for p in sorted(census.ROOT.rglob("*")):
        if p.suffix not in (".py", ".c", ".h") or not p.is_file():
            continue
        rel = str(p.relative_to(census.ROOT.parent))
        for n, line in enumerate(
                p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if census.PAT.search(line) and census.classify(line) == "A-predicate-test":
                auto.add((rel, n))
    return human | auto


def table_rows(path: pathlib.Path = TABLE):
    rows = []
    for raw in path.read_text().splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        parts = raw.split("\t")
        rows.append((parts[0], int(parts[1]), parts[2], parts[3],
                     parts[5] if len(parts) > 5 else None))
    return rows


def run(table_path: pathlib.Path = TABLE, root: pathlib.Path | None = None) -> int:
    # THE TREE THIS CHECKER LIVES IN, not census.ROOT's. census.ROOT points at
    # /workspace/clausal (canonical), so validating there passed while the
    # WORKTREE's line numbers had drifted 19 of 50 rows out of date -- a
    # checker that reported PASS about a tree nobody was editing.
    # Two trees, on purpose. The census's key space is the CANONICAL tree, which
    # this lane does not edit, so (file, line) stays a stable identity. The
    # WORKING tree is where the sites actually get changed, and its line numbers
    # drift with every edit -- 19 of 50 rows had drifted before the snippet
    # column existed, and this checker reported PASS throughout, because it was
    # validating the tree nobody was editing.
    root = root or census.ROOT.parent
    work = pathlib.Path(__file__).resolve().parents[2]
    sites = census_A_sites()
    rows = table_rows(table_path)
    listed = {(f, l) for f, l, *_ in rows}

    print(f"census category-A sites : {len(sites)}")
    print(f"rows in {table_path.name:22}: {len(rows)}")
    if not sites or not rows:
        print("  ABORT: one of the two extractions is EMPTY -- nothing was checked.")
        return 1

    missing = sorted(sites - listed)
    extra = sorted(listed - sites)
    print(f"  in census, absent from table : {len(missing)}")
    for f, l in missing:
        print(f"      MISSING {f}:{l}")
    print(f"  in table, absent from census : {len(extra)}")
    for f, l in extra:
        print(f"      EXTRA   {f}:{l}")

    stale, moved = [], []
    for row in rows:
        f, l = row[0], row[1]
        snippet = row[4] if len(row) > 4 else None
        lines = (root / f).read_text(encoding="utf-8", errors="replace").splitlines()
        wlines = (work / f).read_text(encoding="utf-8", errors="replace").splitlines()
        if snippet:
            # The SNIPPET is the anchor; the line number is a hint that drifts
            # whenever anything earlier in the file changes.
            if l <= len(lines) and lines[l - 1].strip() == snippet:
                continue
            hits = [i + 1 for i, c in enumerate(wlines) if c.strip() == snippet]
            if len(hits) == 1:
                moved.append((f, l, hits[0]))
            else:
                stale.append((f, l))
        elif l > len(lines) or "PredicateMeta" not in lines[l - 1]:
            stale.append((f, l))
    print(f"  rows whose snippet sits at a DIFFERENT line in the working tree : {len(moved)}")
    for f, l, n in moved:
        print(f"      MOVED   {f}:{l} -> {n}")
    print(f"  rows whose snippet is GONE or ambiguous : {len(stale)}")
    for f, l in stale:
        print(f"      STALE   {f}:{l}")

    human = {(k.rsplit(":", 1)[0], int(k.rsplit(":", 1)[1]))
             for k, v in census.VERDICTS.items() if v == "A"}
    badsrc = [(f, l, s) for f, l, s, *_ in rows
              if s != ("H" if (f, l) in human else "M")]
    print(f"  rows whose source column disagrees with the census : {len(badsrc)}")
    for f, l, s in badsrc:
        print(f"      SRC     {f}:{l} claims {s}")

    baddisp = [(f, l, d) for f, l, _, d, *_ in rows if d not in DISPOSITIONS]
    print(f"  rows with an unknown disposition : {len(baddisp)}")
    for f, l, d in baddisp:
        print(f"      BAD     {f}:{l} -> {d!r}")

    dupes = len(rows) - len(listed)
    print(f"  duplicate rows : {dupes}")

    bad = len(missing) + len(extra) + len(stale) + len(baddisp) + dupes + len(badsrc)
    print(f"\n{'PASS' if bad == 0 else 'FAIL'}: {bad} problem(s)")
    return 0 if bad == 0 else 1


def controls() -> int:
    """Break each check on purpose and watch it go red."""
    import tempfile
    ok = True
    good = TABLE.read_text()
    rows = [r for r in good.splitlines() if r and not r.startswith("#")]
    cases = {
        "drop a row": "\n".join(rows[:-1]),
        "invent a row": "\n".join(rows + ["clausal/logic/database.py\t1\tH\tR\tnot an A site"]),
        "point at a line with no PredicateMeta": "\n".join(
            [rows[0].split("\t")[0] + "\t1\tH\tR\tdeliberately stale"] + rows[1:]),
        "unknown disposition": "\n".join(
            ["\t".join(rows[0].split("\t")[:3] + ["ZZ", "bogus"])] + rows[1:]),
        "wrong source column": "\n".join(
            ["\t".join(rows[0].split("\t")[:2]
                       + [("M" if rows[0].split("\t")[2] == "H" else "H")]
                       + rows[0].split("\t")[3:])] + rows[1:]),
    }
    for name, body in cases.items():
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as fh:
            fh.write(body)
            tmp = pathlib.Path(fh.name)
        print(f"\n--- control: {name} (expect FAIL) ---")
        rc = run(tmp)
        print(f"    -> {'PASS as expected' if rc != 0 else 'CONTROL DID NOT FIRE'}")
        ok &= rc != 0
    print(f"\n--- control: the real table (expect PASS) ---")
    rc = run(TABLE)
    ok &= rc == 0
    print(f"\nCONTROLS {'ALL BEHAVED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(controls() if "--controls" in sys.argv else run())
