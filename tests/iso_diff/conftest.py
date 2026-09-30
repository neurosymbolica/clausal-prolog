"""The ``.pl`` files here are DATA for test_iso_diff.py, which runs each
(behind prelude.pl) through the native front end and through Scryer.
Collected as test files they would load under the default front end."""
import glob
import os

collect_ignore = [os.path.basename(p) for p in
                  glob.glob(os.path.join(os.path.dirname(__file__), "*.pl"))]
