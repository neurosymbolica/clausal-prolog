"""The C extensions build with MSVC, which no CI job runs before a release.

MSVC's C compiler, without /std:c11, rejects C11's ``_Thread_local``
(error C2054); the 1.2.0 release's Windows wheel failed on it.  Every
thread-local goes through ``CLAUSAL_THREAD_LOCAL`` (``_ft_compat.h``).
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPAT = REPO / "clausal" / "logic" / "variables" / "_ft_compat.h"


def _c_sources():
    for root in (REPO / "clausal", REPO / "packages"):
        if root.is_dir():
            yield from root.rglob("*.c")
            yield from root.rglob("*.h")


def test_no_c_source_spells_thread_local_with_the_c11_keyword():
    offenders = []
    for path in _c_sources():
        if path == COMPAT:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//", 1)[0]
            if "_Thread_local" in code and not code.lstrip().startswith("*"):
                offenders.append(f"{path.relative_to(REPO)}:{n}: {line.strip()}")
    assert not offenders, (
        "use CLAUSAL_THREAD_LOCAL (clausal/logic/variables/_ft_compat.h); "
        "MSVC rejects _Thread_local:\n" + "\n".join(offenders))


def test_the_macro_picks_declspec_thread_under_msvc():
    text = COMPAT.read_text(encoding="utf-8")
    assert "#if defined(_MSC_VER) && !defined(__clang__)" in text
    assert "#  define CLAUSAL_THREAD_LOCAL __declspec(thread)" in text
    assert "#  define CLAUSAL_THREAD_LOCAL _Thread_local" in text
