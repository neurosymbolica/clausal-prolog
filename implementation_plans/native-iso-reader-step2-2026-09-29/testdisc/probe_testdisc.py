""".pl test/1 discovery on the current (translator) path: file, directory and pytest modes.
The fixtures are stored as *.pl.in so a bare `pytest` from the repo root never collects their
planted red test; this script copies them to a temp dir and runs the three modes there.
Run from the worktree root. Expect each mode to report 4 tests (2 planted red) and a red exit."""
import os, pathlib, shutil, subprocess, sys, tempfile
ROOT = os.getcwd(); HERE = pathlib.Path(__file__).parent
tmp = pathlib.Path(tempfile.mkdtemp())
for f in HERE.glob("*.pl.in"):
    shutil.copy(f, tmp / f.name[:-3])
env = dict(os.environ, PYTHONPATH=ROOT)
py = os.path.join(ROOT, "venv", "bin", "python")
for label, cmd in [("file", [py, "-m", "clausal.testing", str(tmp / "disc_a.pl")]),
                   ("dir", [py, "-m", "clausal.testing", str(tmp)]),
                   ("pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp)])]:
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    last = [l for l in r.stdout.splitlines() if l.strip()][-1:]
    print(f"{label:6s} exit={r.returncode} {last}")
shutil.rmtree(tmp, ignore_errors=True)
