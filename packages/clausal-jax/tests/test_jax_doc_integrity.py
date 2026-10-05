"""Doc-snippet integrity + coverage checks for clausal-jax's own docs/.

Mirrors core's tests/test_doc_snippet_*.py against this package's docs.
Shared check logic lives in clausal/tools/doc_snippet_check.py (in core).
"""

from pathlib import Path

from clausal.tools.doc_snippet_check import (
    check_clausal_fixtures_have_tests,
    check_files_exist,
    check_no_raw_untested_blocks,
    check_no_skip_blocks,
    check_sections_exist,
    collect_snippet_refs,
)

_PKG_ROOT = Path(__file__).resolve().parent.parent
_DOCS_DIR = _PKG_ROOT / "docs"

# 103 partial display fragments and pseudo-code in jax docs that don't
# compile standalone. These were already uncompilable before extraction —
# counted in core's pre-migration test_no_raw_untested_blocks failure.
# Allowlist, not aspiration: do not grow. Cleanup tracked at
# implementation_plans/package_extraction/todo/jax_doc_cleanup.md.
_KNOWN_UNCOMPILABLE = {
    ("jax.md", 12),
    ("jax.md", 67),
    ("jax.md", 106),
    ("jax.md", 183),
    ("jax.md", 191),
    ("jax.md", 198),
    ("jax.md", 207),
    ("jax.md", 214),
    ("jax.md", 223),
    ("jax.md", 234),
    ("jax.md", 243),
    ("jax.md", 253),
    ("jax.md", 267),
    ("jax.md", 278),
    ("jax.md", 290),
    ("jax.md", 301),
    ("jax.md", 309),
    ("jax.md", 319),
    ("jax.md", 331),
    ("jax.md", 346),
    ("jax.md", 355),
    ("jax.md", 374),
    ("jax.md", 380),
    ("jax.md", 388),
    ("jax.md", 394),
    ("jax.md", 400),
    ("jax.md", 409),
    ("jax.md", 437),
    ("jax.md", 461),
    ("jax.md", 645),
    ("jax.md", 672),
    ("jax.md", 682),
    ("jax.md", 717),
    ("jax.md", 726),
    ("jax.md", 733),
    ("jax.md", 746),
    ("jax.md", 779),
    ("jax.md", 812),
    ("jax.md", 837),
    ("jax.md", 884),
    ("jax.md", 920),
    ("jax.md", 1016),
    ("jax.md", 1023),
    ("jax.md", 1139),
    ("jax.md", 1158),
    ("jax.md", 1168),
    ("jax_equinox.md", 18),
    ("jax_equinox.md", 43),
    ("jax_equinox.md", 82),
    ("jax_equinox.md", 95),
    ("jax_equinox.md", 104),
    ("jax_equinox.md", 135),
    ("jax_equinox.md", 149),
    ("jax_equinox.md", 165),
    ("jax_equinox.md", 182),
    ("jax_equinox.md", 196),
    ("jax_equinox.md", 210),
    ("jax_equinox.md", 224),
    ("jax_equinox.md", 263),
    ("jax_equinox.md", 288),
    ("jax_equinox.md", 320),
    ("jax_equinox.md", 385),
    ("jax_flax.md", 16),
    ("jax_flax.md", 80),
    ("jax_flax.md", 119),
    ("jax_flax.md", 137),
    ("jax_flax.md", 154),
    ("jax_flax.md", 177),
    ("jax_flax.md", 196),
    ("jax_flax.md", 290),
    ("jax_nn.md", 18),
    ("jax_nn.md", 134),
    ("jax_nn.md", 241),
    ("jax_optax.md", 20),
    ("jax_optax.md", 52),
    ("jax_optax.md", 114),
    ("jax_optax.md", 130),
    ("jax_optax.md", 143),
    ("jax_optax.md", 178),
    ("jax_optax.md", 188),
    ("jax_optax.md", 243),
    ("jax_optax.md", 267),
    ("jax_optax.md", 280),
    ("jax_optax.md", 292),
    ("jax_optax.md", 302),
    ("jax_optax.md", 338),
    ("jax_random.md", 14),
    ("jax_random.md", 31),
    ("jax_random.md", 38),
    ("jax_random.md", 44),
    ("jax_random.md", 52),
    ("jax_random.md", 59),
    ("jax_random.md", 67),
    ("jax_random.md", 76),
    ("jax_random.md", 115),
    ("jax_random.md", 120),
    ("jax_random.md", 130),
    ("jax_random.md", 140),
    ("jax_scipy.md", 15),
    ("jax_sharding.md", 15),
    ("jax_transforms.md", 18),
    ("jax_tree.md", 18),
    ("jax_tree.md", 240),
}


def test_all_snippet_files_exist():
    refs = collect_snippet_refs(_DOCS_DIR)
    missing = check_files_exist(refs, _PKG_ROOT)
    assert not missing, (
        "Snippet references point to missing files:\n" + "\n".join(missing)
    )


def test_all_snippet_sections_exist():
    refs = collect_snippet_refs(_DOCS_DIR)
    missing = check_sections_exist(refs, _PKG_ROOT)
    assert not missing, (
        "Snippet references point to missing sections:\n" + "\n".join(missing)
    )


def test_clausal_fixtures_have_tests():
    refs = collect_snippet_refs(_DOCS_DIR)
    untested = check_clausal_fixtures_have_tests(refs, _PKG_ROOT)
    assert not untested, (
        "Referenced .clausal fixture files have no Test clauses:\n"
        + "\n".join(untested)
    )


def test_no_skip_blocks():
    violations = check_no_skip_blocks(_DOCS_DIR)
    assert not violations, (
        f"Found {len(violations)} # skip block(s):\n" + "\n".join(violations)
    )


def test_no_raw_untested_blocks():
    violations = check_no_raw_untested_blocks(
        _DOCS_DIR, known_uncompilable=_KNOWN_UNCOMPILABLE
    )
    assert not violations, (
        f"Found {len(violations)} ```seam block(s) that fail to compile "
        f"and have no Test clause or --8<-- reference:\n"
        + "\n".join(violations)
    )
