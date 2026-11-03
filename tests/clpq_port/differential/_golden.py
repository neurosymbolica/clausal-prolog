"""The golden files of the differential harness, and the comparison.

Two files, next to this module:

* ``golden_index.json``: text, one line per workload: the sha256 of the
  workload itself (so a changed generator is told apart from a changed
  port), of its observation and of its algorithm trace, the trace's length
  and its number of pivots.  A golden change shows in review as the lines
  of the workloads that changed.
* ``golden_observations.json.gz``: every workload's full observation, so a
  failure can show what changed, not only that something did.  Written
  with mtime 0, so regenerating an unchanged corpus rewrites the same bytes.

Traces are kept as hashes only: they run to tens of thousands of events
for the large workloads, and an observation diff or the pivot counts say
where to look.  To find where two trees' traces part, print one
workload's trace on each (``regenerate --trace ID``) and diff the two.
"""
import difflib
import gzip
import io
import json
import pathlib

from tests.clpq_port.differential._observe import digest, observe, record  # noqa: F401

HERE = pathlib.Path(__file__).resolve().parent
INDEX = HERE / "golden_index.json"
OBSERVATIONS = HERE / "golden_observations.json.gz"


def load():
    """(index, observations); empty where a file is missing."""
    index = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    observations = {}
    if OBSERVATIONS.exists():
        with gzip.open(OBSERVATIONS, "rt", encoding="utf-8") as handle:
            observations = json.load(handle)
    return index, observations


def save(index, observations):
    lines = [f"  {json.dumps(key)}: {json.dumps(index[key], sort_keys=True)}"
             for key in sorted(index)]
    INDEX.write_text("{\n" + ",\n".join(lines) + "\n}\n")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, compresslevel=9) as handle:
        handle.write(json.dumps(observations, sort_keys=True,
                                separators=(",", ":")).encode())
    OBSERVATIONS.write_bytes(buffer.getvalue())


def entry(workload, result):
    return {"workload": digest(workload),
            "observation": result["observation_sha256"],
            "trace": result["trace_sha256"],
            "events": result["trace_events"],
            "pivots": result["pivots"]}


def pretty(observation):
    return json.dumps(observation, indent=1, sort_keys=True).splitlines()


def observation_diff(expected, actual, context=2, limit=60):
    lines = list(difflib.unified_diff(pretty(expected), pretty(actual),
                                      "expected (golden)", "actual (port)",
                                      n=context, lineterm=""))
    if len(lines) > limit:
        lines = lines[:limit] + [f"... {len(lines) - limit} more diff lines"]
    return "\n".join(lines)


def compare(workloads, index, observations, shown=3):
    """Run every workload and compare with the golden records.  Returns
    (problems, details): one compiler-style line per differing workload,
    and the observation diffs of the first *shown* of them."""
    problems, details = [], []
    for workload in workloads:
        name = workload["id"]
        result, _ = record(workload)
        got = entry(workload, result)
        want = index.get(name)
        if want is None:
            problems.append(f"{name}: no golden record (regenerate)")
            continue
        if want["workload"] != got["workload"]:
            problems.append(f"{name}: the workload itself changed "
                            f"(the generator, not the port): regenerate")
            continue
        what = []
        if want["observation"] != got["observation"]:
            what.append("observation")
        if want["trace"] != got["trace"]:
            what.append(f"trace ({want['events']} -> {got['events']} events, "
                        f"{want['pivots']} -> {got['pivots']} pivots)")
        if not what:
            continue
        problems.append(f"{name}: {' and '.join(what)} differ")
        if "observation" in what[0] and len(details) < shown \
                and name in observations:
            details.append(f"--- {name}\n" + observation_diff(
                observations[name], result["observation"]))
    return problems, details


__all__ = ["compare", "entry", "load", "observe", "save"]
