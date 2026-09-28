"""Exclude prolog_golden files from being collected as runnable tests.

The .clausal files are translator output snapshots — they test that the
Prolog→Clausal translator produces deterministic output, not that the output
is executable.  The golden snapshot tests in test_prolog_golden.py handle
validation.  The .pl sources are the translator's INPUTS; the plugin collects
.pl files, but these are exercised by test_prolog_import.py (which requires
only that some of each file's tests pass), not run clause by clause.
"""
collect_ignore_glob = ["*.clausal", "*.pl"]
