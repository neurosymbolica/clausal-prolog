def test_run_clausal_does_not_corrupt_near_miss_tokens(run_clausal, tmp_path):
    """Regression for review round 1, Finding 2: the `_h1`/`_hN` placeholder
    substitution in the `run_clausal` fixture must be word-bounded. A plain
    `str.replace` would silently corrupt a near-miss substring — a variable
    literally spelled `_h10`, or an atom containing `path_hN` — rather than
    erroring, which is exactly the fail-open failure mode this control exists
    to catch. With the fix, both near-miss tokens must survive unmolested and
    only the exact `_h1` token (used here as the module-name placeholder) may
    be substituted.
    """
    src = (
        "-module(_h1, [p(X)])\n"
        "-double_quotes(chars)\n"
        "# near-miss tokens that must NOT be substituted: _h10, path_hN\n"
        "p(X) <- (X == 3 + 4)\n"
    )
    got = run_clausal(src, ("p",))
    assert got == ["7"]

    # This is the first run_clausal() call made in this test, so the fixture's
    # counter produced "_iso1" as the fresh module name — inspect what it
    # actually wrote to disk.
    written = (tmp_path / "_iso1.clausal").read_text()
    assert "-module(_iso1, [p(X)])" in written, written
    assert "_h10" in written, "near-miss token _h10 was corrupted:\n" + written
    assert "path_hN" in written, "near-miss token path_hN was corrupted:\n" + written
