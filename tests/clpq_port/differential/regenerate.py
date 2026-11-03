"""Record the differential harness's golden files from the port as it is.

    PYTHONPATH=. python -m tests.clpq_port.differential.regenerate [--full] [--check]

Default: the default corpus; --full: the full corpus (minutes).  Records
of workloads not regenerated are kept, so a default run does not drop the
full corpus's.  It prints every workload whose record changes.

--check writes nothing: it runs the corpus and lists every workload that
differs from the golden files (the test's comparison, for a branch).

--trace ID writes nothing: it prints the algorithm trace of workload ID,
one event a line, to diff against the same on another tree.

Regenerating is a DELIBERATE act: a changed record is a changed answer or
a changed decision of the algorithm, a potential deviation from 1.3.3
(see the docstring of test_differential_golden.py).
"""
import argparse
import json
import sys
import time

from tests.clpq_port.differential import _golden
from tests.clpq_port.differential._observe import record
from tests.clpq_port.differential._workloads import corpus


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--trace", metavar="ID")
    arguments = parser.parse_args(argv)
    workloads = corpus(full=arguments.full)
    if arguments.trace:
        found = [w for w in corpus(full=True) if w["id"] == arguments.trace]
        if not found:
            print(f"no workload {arguments.trace}")
            return 2
        _, trace = record(found[0])
        for event in trace:
            print(json.dumps(event))
        return 0
    index, observations = _golden.load()
    if arguments.check:
        started = time.time()
        problems, details = _golden.compare(workloads, index, observations)
        for line in problems:
            print(line)
        for detail in details:
            print(detail)
        print(f"{len(problems)} of {len(workloads)} workloads differ "
              f"({time.time() - started:.0f} s)")
        return 1 if problems else 0
    changed = 0
    started = time.time()
    for workload in workloads:
        result, _ = record(workload)
        new = _golden.entry(workload, result)
        old = index.get(workload["id"])
        if old != new:
            changed += 1
            print(f"{workload['id']}: {'new' if old is None else 'changed'}")
        index[workload["id"]] = new
        observations[workload["id"]] = result["observation"]
    _golden.save(index, observations)
    print(f"{len(workloads)} workloads recorded, {changed} new or changed "
          f"({time.time() - started:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
