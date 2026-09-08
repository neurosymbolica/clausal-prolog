import os, subprocess, sys, tempfile
import pytest

SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"


@pytest.fixture
def scryer():
    if not os.path.exists(SCRYER):
        pytest.skip(f"scryer not built at {SCRYER}")

    def run(goal: str, program: str = "") -> str:
        d = tempfile.mkdtemp()
        pl = os.path.join(d, "w.pl")
        with open(pl, "w") as fh:
            fh.write(program)
        proc = subprocess.run([SCRYER, pl], input=goal + "\n",
                              capture_output=True, text=True, timeout=30)
        return proc.stdout.strip().splitlines()[-1].strip() if proc.stdout.strip() else ""
    return run


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
        path.write_text(src.replace("_h1", name).replace("_hN", name))
        mod = _load_module(name, str(path))
        v = Var()
        args = (v,) + tuple(Var() for _ in range(nargs - 1))
        return [repr(deref(v)) for _ in solve(goal_head + args, mod, Trail())]
    return run
