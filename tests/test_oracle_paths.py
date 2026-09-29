"""Guard: no test hardcodes the work-in-progress Scryer checkout.

/workspace/scryer-prolog is built from uncommitted clpz work that drops
constraints, so an oracle pointed at it can agree with a wrong answer. The
path is defined once, in tests/_oracles.py (overridable via CLAUSAL_SCRYER).
"""
import pathlib

_TESTS = pathlib.Path(__file__).resolve().parent
_WIP = "/workspace/scryer-prolog" + "/target"   # split so this file does not match itself


def test_no_test_hardcodes_the_wip_scryer_path():
    files = [p for p in _TESTS.rglob("*") if p.is_file() and p.suffix in
             (".py", ".pl", ".seam", ".clausal", ".txt", ".toml", ".cfg", ".ini")]
    assert len(files) > 100, f"guard scanned only {len(files)} files under {_TESTS}"
    hits = [f"{p.relative_to(_TESTS)}:{n}"
            for p in files
            for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1)
            if _WIP in line]
    assert not hits, (
        "hardcoded WIP Scryer path; import SCRYER from tests._oracles instead:\n  "
        + "\n  ".join(hits))
