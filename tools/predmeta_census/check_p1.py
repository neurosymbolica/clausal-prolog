"""Machine-check the P1 per-site table against the census and the tree.

P0's lesson was that a number and its prose drift apart when only prose records
the verdicts. This checks three things and PRINTS THE SIZE OF EACH, because an
extraction that silently yields nothing is this lane's dominant failure mode:

  1. every category-A site the census knows about appears in P1_SITES.tsv
  2. every row in P1_SITES.tsv still points at a line containing PredicateMeta
     -- EXCEPT a CLOSED row (``-done`` or ``R-fallback``), where the check
     FLIPS and is made over the site's REGION in the WORKING tree rather than
     over a literal line.  See ``closed_row_verdict``.
  3. no row carries a disposition outside the documented set
  4. a row's canonical line sits inside the def its QUALNAME column names
     (live rows only; a closed row's line is an identity, not a pointer)

The REGION of a row is its enclosing def, and it is located by the row's
QUALNAME column (column 7), not by the canonical line.  Landing day
2026-09-17 showed why: the canonical tree became the branch, every line above
a site shifted, and ``qualname_at(canonical, line)`` for three CLOSED rows
resolved to a NEIGHBOURING def -- one false UNDONE (an R-enum-done row judged
over a live Q row's def) and one false STALE (an S-done row whose old line now
sat at module level).  A closed row cannot be re-anchored by its line, because
its site is gone from the canonical tree; the def name survives.  Rows without
the column fall back to the line, as before.

Category A is the UNION of two populations, which is the correction this pass
made: the 26 sites human-read at P0 (census.VERDICTS) AND the 24 the census
classified "A-predicate-test" from the VARIABLE NAME alone and never read --
UNION the table's own closed rows, so check 1 survives landing day (see
``census_A_sites``).

Run with --controls to watch each check go red on purpose.
"""
from __future__ import annotations
import ast, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import census  # noqa: E402

TABLE = HERE / "P1_SITES.tsv"
# ``-done``: the site was rerouted and keeps NO class read (P1 Task 3, spec
# 2026-09-17 §2.2).  ``R-fallback``: rerouted row-FIRST, with a class fallback
# deliberately kept and REPORTED (roborev L5 + final review I2, 2026-09-17) --
# the shape ``_find_pred_cls``, ``_GlobalsDb.signature_for``,
# ``_note_generic_compound_confusion`` and compiler_v2's ``-dynamic`` site all
# have.  Both are CLOSED rows: check 2 runs backwards for them, but it asks a
# different question of each.
DONE = {"R-done", "R!-done", "S-done", "R-enum-done"}
FALLBACK = {"R-fallback"}
CLOSED = DONE | FALLBACK
DISPOSITIONS = {"R", "R!", "R-enum", "S", "Q", "X4", "X4+Q", "NO",
                "G", "C", "C/G", "B", "D", "LAYER", "P4"} | CLOSED


def table_rows(path: pathlib.Path = TABLE):
    rows = []
    for raw in path.read_text().splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        parts = raw.split("\t")
        rows.append((parts[0], int(parts[1]), parts[2], parts[3],
                     parts[5] if len(parts) > 5 else None,
                     parts[6] if len(parts) > 6 and parts[6] else None))
    return rows


def row_qual(root: pathlib.Path, f: str, l: int, qual_col: "str | None"):
    """The def a row's site lives in: the QUALNAME column when recorded,
    else the def enclosing the canonical line (the pre-column behaviour)."""
    return qual_col.split(".") if qual_col else qualname_at(root / f, l)


def census_A_sites(rows=None) -> set[tuple[str, int]]:
    """The category-A population: census verdicts, the mechanical classifier,
    and the table's own CLOSED rows.

    That last union is what makes check 1 survive LANDING DAY (final review
    I4).  ``census.ROOT`` is the canonical tree, which still holds the
    pre-reroute spelling of every site; the moment these commits land there,
    the SEVEN mechanically-sourced closed rows (measured; an earlier note said
    six) stop classifying as "A-predicate-test" in that tree and would drop
    out of the population --
    turning them into "in table, absent from census" and the checker red for
    having been LANDED.  A closed row's identity lives in this table and in
    the census's own key space, so the table is part of the population.
    """
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
    landed = {(f, l) for f, l, _s, d, _sn, _q in (rows or []) if d in CLOSED}
    return human | auto | landed


# ── the site's REGION, and what may remain in it ────────────────────────────


def qualname_at(path: pathlib.Path, line: int) -> "list[str] | None":
    """The def/class path enclosing *line* in *path* (canonical tree)."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    best: "list[str] | None" = None

    def walk(node, prefix):
        nonlocal best
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                qual = prefix + [child.name]
                if child.lineno <= line <= (child.end_lineno or child.lineno):
                    if best is None or len(qual) > len(best):
                        best = qual
                walk(child, qual)
            else:
                walk(child, prefix)

    walk(tree, [])
    return best


def region_of(path: pathlib.Path, qual: "list[str]") -> "tuple[int, int] | None":
    """``(first, last)`` lines of *qual* in *path* (working tree), or None."""
    scope = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    node = None
    for name in qual:
        node = next(
            (c for c in ast.iter_child_nodes(scope)
             if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)) and c.name == name),
            None)
        if node is None:
            return None
        scope = node
    return (node.lineno, node.end_lineno)


_SUBJECT = re.compile(r"isinstance\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*PredicateMeta")


def subject_of(snippet: str) -> "str | None":
    """The name the snippet's membership test is ABOUT."""
    m = _SUBJECT.search(snippet)
    return m.group(1) if m else None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def closed_row_verdict(work_file: pathlib.Path, region, snippet, disposition,
                       accounted: "set[int]") -> "str | None":
    """Why this CLOSED row is not closed after all, or None if it is.

    NOT a literal-line absence test (roborev L5): a reformat of the very same
    membership test would make the recorded line vanish and the row would
    report itself closed while the test sat there, one space different.  So
    the question is asked of the site's REGION -- its enclosing def in the
    WORKING tree, located by the qualified name the CANONICAL line sits in:

    * ``-done``: no category-A membership test may remain in the region.  Two
      detectors, because neither alone is enough.  ``census.classify`` is the
      census's own rule and sees any of the subject names it knows; it is
      blind to a site like the ``R-enum`` one, whose subject is a
      comprehension variable -- so the row's OWN subject, parsed out of its
      snippet, is searched for as well, over the region's text with
      whitespace squashed, which is what makes a reformat visible.  Lines
      that belong to ANOTHER row in the table (its snippet, located in this
      working tree) are excluded: several rows share one enclosing def, and a
      LIVE row's site is not evidence about a closed one.
    * ``R-fallback``: the opposite question.  The class read is KEPT here on
      purpose, so it must be PRESENT -- the row's subject still read as a
      class (``x._attr``, ``getattr(x, ...)``, or an isinstance) -- and so
      must the row read that makes the site row-FIRST.  A weaker instrument
      than the ``-done`` one by nature: it proves the shape is still there,
      not that nothing else changed.  Stated, not hidden.
    """
    lines = work_file.read_text(encoding="utf-8", errors="replace").splitlines()
    first, last = region
    body = lines[first - 1:last]
    text = _squash("\n".join(body))
    # ... and the same region with every LIVE row's own line removed, which is
    # what the two ``-done`` detectors are asked over: several rows share one
    # enclosing def, and another row's site is not evidence about this one.
    mine = _squash("\n".join(c for n, c in enumerate(body, first)
                             if n not in accounted))
    subject = subject_of(snippet or "")

    if disposition in FALLBACK:
        if subject is None:
            return "snippet names no subject, so the fallback cannot be checked"
        reads_class = re.search(
            rf"getattr\(\s*{subject}\b|\b{subject}\s*\.\s*_|"
            rf"isinstance\(\s*{subject}\s*,\s*PredicateMeta", text)
        if not reads_class:
            return f"no class read of {subject!r} left -- this is a plain -done row now"
        if not re.search(r"\.row\(|_row\b", text):
            return "no row read in the region -- the site is not row-first"
        return None

    offenders = [
        n for n in range(first, last + 1)
        if census.PAT.search(lines[n - 1])
        and census.classify(lines[n - 1]) == "A-predicate-test"
        and n not in accounted
    ]
    if offenders:
        return (f"category-A membership test still in the region at working-tree "
                f"line(s) {offenders}")
    if subject and re.search(
            rf"isinstance\(\s*{subject}\s*,\s*PredicateMeta", mine):
        return (f"the row's own membership test on {subject!r} is still in the "
                f"region (reformatted, but there)")
    return None


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
    rows = table_rows(table_path)
    sites = census_A_sites(rows)
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

    # Lines in the working tree that belong to a LIVE row -- excluded from a
    # closed row's region, because several rows share one enclosing def.
    #
    # KEYED BY REGION, not by file (control caught this): two rows in the same
    # file can carry the SAME snippet text (compiler_v2 851 and 882 are both
    # ``if isinstance(cls, PredicateMeta):``), so a file-wide text match let a
    # live twin excuse the very line a closed row is judged on -- the checker
    # then passed a table that marked a live site done.  A live row excuses a
    # line only inside its OWN enclosing def.
    accounted: "dict[tuple[str, tuple], set[int]]" = {}
    for f, l, _s, disposition, snippet, qual_col in rows:
        if disposition in CLOSED or not snippet:
            continue
        wlines = (work / f).read_text(encoding="utf-8", errors="replace").splitlines()
        qual = row_qual(root, f, l, qual_col)
        region = region_of(work / f, qual) if qual else None
        hits = {i + 1 for i, c in enumerate(wlines) if c.strip() == snippet}
        if region is not None:
            hits = {n for n in hits if region[0] <= n <= region[1]}
        accounted.setdefault((f, tuple(qual or ())), set()).update(hits)

    stale, moved, undone, misplaced = [], [], [], []
    done_rows = fallback_rows = 0
    for row in rows:
        f, l = row[0], row[1]
        disposition = row[3]
        snippet = row[4]
        qual_col = row[5]
        lines = (root / f).read_text(encoding="utf-8", errors="replace").splitlines()
        wlines = (work / f).read_text(encoding="utf-8", errors="replace").splitlines()
        if disposition in CLOSED:
            # THE FLIPPED CHECK, over the site's REGION in the WORKING tree.
            #
            # WORKING TREE ONLY, deliberately (review round 1).  The canonical
            # anchor is what a non-closed row is held to, and it is right for a
            # row whose site is still there.  Holding a CLOSED row to it as well
            # would turn this checker red on landing day: the moment these
            # commits reach the canonical tree, the site leaves that tree too,
            # and a check that demanded both would call the row stale for
            # having been landed.  The row's identity survives on the (file,
            # line) pair and the census, which is where it has always lived.
            if disposition in FALLBACK:
                fallback_rows += 1
            else:
                done_rows += 1
            if not snippet or "PredicateMeta" not in snippet:
                stale.append((f, l))
                continue
            qual = row_qual(root, f, l, qual_col)
            region = region_of(work / f, qual) if qual else None
            if region is None:
                # no such def in the working tree (or, without the column,
                # the canonical line sits at module level)
                stale.append((f, l))
                continue
            why = closed_row_verdict(work / f, region, snippet, disposition,
                                     accounted.get((f, tuple(qual)), set()))
            if why:
                undone.append((f, l, why))
            continue
        if qual_col and qualname_at(root / f, l) != qual_col.split("."):
            # check 4: a LIVE row's canonical line must sit inside the def
            # the row says it is in -- the column and the line disagree.
            misplaced.append((f, l, qual_col))
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
    print(f"  rows marked done (site rerouted, no class read)   : {done_rows}")
    print(f"  rows marked R-fallback (row-first, class fallback) : {fallback_rows}")
    print(f"  rows still expected to test PredicateMeta : "
          f"{len(rows) - done_rows - fallback_rows}")
    print(f"  closed rows whose region says otherwise : {len(undone)}")
    for f, l, why in undone:
        print(f"      UNDONE  {f}:{l} -- {why}")
    print(f"  rows whose snippet sits at a DIFFERENT line in the working tree : {len(moved)}")
    for f, l, n in moved:
        print(f"      MOVED   {f}:{l} -> {n}")
    print(f"  rows whose snippet is GONE or ambiguous : {len(stale)}")
    for f, l in stale:
        print(f"      STALE   {f}:{l}")
    print(f"  live rows whose canonical line is outside the recorded def : "
          f"{len(misplaced)}")
    for f, l, q in misplaced:
        print(f"      DEF     {f}:{l} is not in {q}")

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

    bad = (len(missing) + len(extra) + len(stale) + len(baddisp) + dupes
           + len(badsrc) + len(undone) + len(misplaced))
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
    # The control for the FLIPPED half of check 2: claim a live site is done.
    live = next(r for r in rows
                if r.split("\t")[3] not in CLOSED and len(r.split("\t")) > 5
                and subject_of(r.split("\t")[5]))
    cases["mark a live site done"] = "\n".join(
        ["\t".join(live.split("\t")[:3] + ["R-done"] + live.split("\t")[4:])]
        + [r for r in rows if r != live])
    # THE CONTROL FOR THE REGION CHECK ITSELF (roborev L5): the same live site,
    # marked done, with its snippet REFORMATTED -- same test, different
    # spelling, so the literal line the old checker looked for is nowhere in
    # the tree.  Absence of the literal must NOT read as "rerouted".
    parts = live.split("\t")
    reformatted = _squash(parts[5]).replace(
        "isinstance(", "isinstance( ").replace(", PredicateMeta", " , PredicateMeta")
    assert reformatted != parts[5]
    cases["mark a live site done with a REFORMATTED snippet"] = "\n".join(
        ["\t".join(parts[:3] + ["R-done"] + [parts[4], reformatted] + parts[6:])]
        + [r for r in rows if r != live])
    # THE CONTROLS FOR THE QUALNAME COLUMN (landing day 2026-09-17): a live
    # row whose recorded def is not the one its canonical line sits in, and a
    # closed row whose recorded def does not exist in the working tree.
    assert len(parts) > 6 and parts[6], "the live control row has no qualname column"
    cases["record the WRONG def on a live row"] = "\n".join(
        ["\t".join(parts[:6] + ["no_such_def"])] + [r for r in rows if r != live])
    dead0 = next(r for r in rows if r.split("\t")[3] in CLOSED)
    dparts = dead0.split("\t")
    assert len(dparts) > 6 and dparts[6], "the closed control row has no qualname column"
    cases["close a row under a def that does not exist"] = "\n".join(
        ["\t".join(dparts[:6] + ["no_such_def"])] + [r for r in rows if r != dead0])
    # ... and its mirror: a row marked closed whose snippet is not a
    # PredicateMeta test at all, which would make the region check meaningless.
    dead = next(r for r in rows if r.split("\t")[3] in CLOSED)
    cases["mark a row done on a snippet that never tested PredicateMeta"] = "\n".join(
        ["\t".join(dead.split("\t")[:5] + ["x = 1  # not a membership test"])]
        + [r for r in rows if r != dead])
    # ... and an R-fallback row whose class read is gone is not an R-fallback.
    fb = next(r for r in rows if r.split("\t")[3] in FALLBACK)
    fbparts = fb.split("\t")
    cases["claim R-fallback for a site with no class read"] = "\n".join(
        ["\t".join(fbparts[:3] + ["R-fallback"]
                   + [fbparts[4], "if isinstance(nosuchname, PredicateMeta):"])]
        + [r for r in rows if r != fb])
    for name, body in cases.items():
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as fh:
            fh.write(body)
            tmp = pathlib.Path(fh.name)
        print(f"\n--- control: {name} (expect FAIL) ---")
        rc = run(tmp)
        print(f"    -> {'FAILED as expected' if rc != 0 else 'CONTROL DID NOT FIRE'}")
        ok &= rc != 0
    print("\n--- control: the real table (expect PASS) ---")
    rc = run(TABLE)
    ok &= rc == 0
    print(f"\nCONTROLS {'ALL BEHAVED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(controls() if "--controls" in sys.argv else run())
