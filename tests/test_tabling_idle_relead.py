"""An idle re-lead of a dormant SCC member skips its fixpoint loop.

See ``todo/tabled-scc-relead-rederives-every-answer-cubic-on-a-ring-
2026-11-03.md`` and clausal/logic/tabling.py, "Idle re-leads" (operator ruling
2026-11-03, R12).  A re-lead whose clauses can read nothing that changed since
a quiet pass of theirs only replays its rows.  Every table must gain the same
rows in the same order as with the skip off (``CLAUSAL_TABLING_SEMINAIVE=0``),
with the same WFS truth values.
"""
import os

import pytest

from clausal.logic import database, tabling
from clausal.logic.database import Clause
from clausal.logic.solve import call, query_wfs
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module


def _ring(n):
    lines = ["-table(rpath/2)", ""]
    lines += [f"edge({i}, {(i + 1) % n})," for i in range(n)]
    lines += ["", "rpath(X, Y) <- edge(X, Y)",
              "rpath(X, Y) <- (\n    edge(X, Z),\n    rpath(Z, Y)\n)", ""]
    return "\n".join(lines)


_SCC_WFS = (
    "-table(pa/2)\n"
    "-table(pb/2)\n"
    "-table(win/1)\n"
    "-table(q/1)\n"
    "\n"
    "e(0, 1),\n"
    "e(1, 2),\n"
    "e(2, 0),\n"
    "e(2, 3),\n"
    "e(3, 4),\n"
    "e(4, 3),\n"
    "e(4, 5),\n"
    "\n"
    "pa(X, Y) <- e(X, Y)\n"
    "pa(X, Y) <- (\n"
    "    e(X, Z),\n"
    "    pb(Z, Y)\n"
    ")\n"
    "pb(X, Y) <- (\n"
    "    e(X, Z),\n"
    "    pa(Z, Y)\n"
    ")\n"
    "win(X) <- (\n"
    "    e(X, Y),\n"
    "    not win(Y)\n"
    ")\n"
    "q(X) <- (\n"
    "    pa(X, Y),\n"
    "    not win(Y)\n"
    ")\n"
)


def _load(tmp_path, name, text):
    src = tmp_path / f"{name}.seam"
    src.write_text(text)
    return load_clausal_module(str(src))


def _store(mod):
    """Every table: key, status, rows IN ORDER, conditions."""
    out = []
    for key, e in mod.__dict__["$module"].db.table_store.items():
        conds = ["F" if c is tabling._FAILED else
                 "T" if c is tabling._UNCONDITIONAL else repr(sorted(map(repr, c)))
                 for c in e.conditions]
        out.append((key[0], key[1], repr(key[2][:1]), e.status,
                    [repr(a) for a in e.answers], conds))
    return out


def _run(mod, name, x):
    y = Var()
    return [deref(y) for _ in call(name, x, y, module=mod.__dict__["$module"])]


def _both(monkeypatch, tmp_path, text, work):
    """Run *work(mod)* on a fresh load with the skip on, then off; return the
    two results and the number of idle re-leads with it on."""
    results = []
    idle = None
    for on in (True, False):
        monkeypatch.setattr(tabling, "_SEMINAIVE", on)
        before = tabling._idle_releads
        mod = _load(tmp_path, f"p{int(on)}", text)
        results.append((work(mod), _store(mod)))
        if on:
            idle = tabling._idle_releads - before
    return results[0], results[1], idle


@pytest.mark.parametrize("n", [3, 7, 20])
def test_a_ring_gives_the_same_answers_in_the_same_order(monkeypatch, tmp_path, n):
    def work(mod):
        return [_run(mod, "rpath", x) for x in (0, n // 2)]
    on, off, idle = _both(monkeypatch, tmp_path, _ring(n), work)
    assert on == off
    if n >= 7:
        assert idle > 0, "no re-lead was idle: the test exercises nothing"


def test_a_ring_skips_most_of_its_re_leads(monkeypatch, tmp_path):
    # n=30: 1,194 leader pushes with every re-lead re-running, 518 with idle
    # ones skipped (measured 2026-11-03).
    pushes = []
    for on in (True, False):
        monkeypatch.setattr(tabling, "_SEMINAIVE", on)
        mod = _load(tmp_path, f"r{int(on)}", _ring(30))
        p0 = tabling._leader_ctx.pushes
        assert sorted(_run(mod, "rpath", 0)) == list(range(30))
        pushes.append(tabling._leader_ctx.pushes - p0)
    assert pushes[0] * 2 < pushes[1], pushes


def test_mutual_recursion_and_wfs_are_unchanged(monkeypatch, tmp_path):
    def work(mod):
        lm = mod.__dict__["$module"]
        got = []
        for name in ("pa", "pb"):
            for x in range(6):
                got.append((name, x, _run(mod, name, x)))
        for name in ("win", "q"):
            for x in range(6):
                res = query_wfs((name, x), {}, lm)
                got.append((name, x, [str(r["_truth"]) for r in res]))
        y = Var()
        res = query_wfs(("q", y), {"Y": y}, lm)
        got.append([(repr(r["Y"]), str(r["_truth"])) for r in res])
        return got
    on, off, _ = _both(monkeypatch, tmp_path, _SCC_WFS, work)
    assert on == off


def test_the_stamp_moves_on_every_change_it_guards(tmp_path):
    # The three parts of the stamp (see "Idle re-leads").  A leader alone on
    # the stack, so _quiet_stamp gives a stamp at all.
    entry = tabling.TableEntry(("t", 1))
    tabling.push_leader(entry)
    try:
        s0 = tabling._quiet_stamp(entry)
        assert s0 is not None and s0 == tabling._quiet_stamp(entry)
        # A new row in any table.
        other = tabling.TableEntry(("u", 1))
        other.add_answer((1,))
        s1 = tabling._quiet_stamp(entry)
        assert s1 != s0
        # A duplicate row with the same (empty) delay set changes nothing.
        other.add_answer((1,))
        assert tabling._quiet_stamp(entry) == s1
        # A clause write.
        mod = _load(tmp_path, "dyn", "-dynamic(f/1)\nf(1),\n")
        db = mod.__dict__["$module"].db
        s2 = tabling._quiet_stamp(entry)
        db.assertz(Clause(("f", 2), ()))
        s3 = tabling._quiet_stamp(entry)
        assert s3 != s2
        # Another leader below: a different parent lead.
        tabling.pop_leader(entry)
        below = tabling.TableEntry(("v", 1))
        tabling._new_lead(below)
        tabling.push_leader(below)
        tabling.push_leader(entry)
        assert tabling._quiet_stamp(entry) != s3
        tabling.pop_leader(below)
        # Not the top of the stack: no stamp.
        tabling.push_leader(below)
        assert tabling._quiet_stamp(entry) is None
        tabling.pop_leader(below)
    finally:
        tabling.pop_leader(entry)


def test_a_clause_write_between_passes_is_seen(monkeypatch, tmp_path):
    # The database counter alone, without any table change.
    before = database._mutations
    mod = _load(tmp_path, "dyn2", "-dynamic(f/1)\nf(1),\n")
    mod.__dict__["$module"].db.assertz(Clause(("f", 3), ()))
    assert database._mutations != before


def test_off_switch_runs_every_re_lead(monkeypatch, tmp_path):
    monkeypatch.setattr(tabling, "_SEMINAIVE", False)
    before = tabling._idle_releads
    mod = _load(tmp_path, "off", _ring(20))
    assert sorted(_run(mod, "rpath", 0)) == list(range(20))
    assert tabling._idle_releads == before
