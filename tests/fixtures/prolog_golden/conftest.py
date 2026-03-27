"""Exclude prolog_golden .clausal files from being collected as runnable tests.

These files are translator output snapshots — they test that the Prolog→Clausal
translator produces deterministic output, not that the output is executable.
The golden snapshot tests in test_prolog_golden.py handle validation.
"""
collect_ignore_glob = ["*.clausal"]
