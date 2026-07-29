"""A real Python module whose body raises ImportError.

Used to prove the Clausal loader does not swallow or reformat a genuine
ImportError originating inside a Python module.
"""
from impexp_definitely_not_a_real_package_zzz import thing  # noqa: F401

helper = None
