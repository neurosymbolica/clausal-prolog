import os, re, subprocess, tempfile
import pytest
from tests._oracles import SCRYER


# Scryer is the BINDING oracle for this suite, so its absence is a FAILURE,
# not a skip: 42 of the original 52 tests requested this fixture and every one
# of them carried its engine assertions in the same function, so a box without
# the binary skipped the engine coverage too and a broken `'=<'` still read
# green. The engine assertions now live in their own oracle-free tests (see
# tests/iso/test_iso_compare_scryer.py), and a run with no oracle at all has
# to say so out loud. Set CLAUSAL_ISO_ALLOW_NO_SCRYER=1 to opt out
# deliberately — that is the only way this turns back into a skip.
_ALLOW_NO_SCRYER = "CLAUSAL_ISO_ALLOW_NO_SCRYER"


@pytest.fixture
def scryer():
    if not os.path.exists(SCRYER):
        if os.environ.get(_ALLOW_NO_SCRYER):
            pytest.skip(f"scryer not built at {SCRYER}; {_ALLOW_NO_SCRYER} is set")
        pytest.fail(
            f"the Scryer oracle is not built at {SCRYER}. It is the binding "
            f"reference for this suite, so its absence fails rather than "
            f"skips; set {_ALLOW_NO_SCRYER}=1 to run engine-only.")

    def run(goal: str, program: str = "") -> str:
        d = tempfile.mkdtemp()
        pl = os.path.join(d, "w.pl")
        with open(pl, "w") as fh:
            fh.write(program)
        proc = subprocess.run([SCRYER, pl], input=goal + "\n",
                              capture_output=True, text=True, timeout=30)
        return proc.stdout.strip().splitlines()[-1].strip() if proc.stdout.strip() else ""
    return run


# Word-bounded so a near-miss token (e.g. a variable literally spelled `_h10`,
# or an atom containing `path_hN`) is left alone rather than silently corrupted.
_H1_PLACEHOLDER = re.compile(r"\b_h1\b")
_HN_PLACEHOLDER = re.compile(r"\b_hN\b")


@pytest.fixture
def run_clausal(tmp_path):
    # Assert the tree under test, per [[running-tests-in-bug-fix-clone]]: a probe
    # that does not do this silently measures the editable-installed canonical.
    import clausal
    assert os.getcwd() in clausal.__file__, clausal.__file__
    from clausal.import_hook import _load_module
    from clausal.logic.solve import solve
    from clausal.logic.variables import Trail, Var, deref
    counter = [0]

    def run(src: str, goal_head: tuple, nargs: int = 1) -> list[str]:
        counter[0] += 1
        name = f"_iso{counter[0]}"
        path = tmp_path / f"{name}.clausal"
        substituted = _H1_PLACEHOLDER.sub(name, src)
        substituted = _HN_PLACEHOLDER.sub(name, substituted)
        path.write_text(substituted)
        mod = _load_module(name, str(path))
        v = Var()
        args = (v,) + tuple(Var() for _ in range(nargs - 1))
        return [repr(deref(v)) for _ in solve(goal_head + args, mod, Trail())]
    return run
