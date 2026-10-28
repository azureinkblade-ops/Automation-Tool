"""Source-only recipe checks; no build, container, or model is invoked."""

from pathlib import Path

from tools.ea4e92rm_container_smoke import EXPECTED_MODEL_FILES
from tools.ea4e92sb_local_model_smoke import IMAGE
from tools.ea4e92um_model_build_context import expected_recipe_bytes


RECIPE = Path(__file__).parents[2] / "tools" / "ea4e92ul_model_image.Dockerfile"


def test_recipe_copies_only_reviewed_model_files_from_pinned_base():
    lines = RECIPE.read_text(encoding="ascii").splitlines()
    assert lines == expected_recipe_bytes(EXPECTED_MODEL_FILES).decode("ascii").splitlines()
    assert lines[0] == f"FROM {IMAGE}"
    assert len({name for name, _ in EXPECTED_MODEL_FILES}) == 6


def test_recipe_runs_only_inventory_and_hash_verification():
    lines = RECIPE.read_text(encoding="ascii").splitlines()
    assert all(line.startswith(("FROM ", "COPY ")) for line in lines[:-1])
    assert lines[-1].startswith('RUN set -eu; test "$(find /models -type f | wc -l)" -eq 6; ')
    assert lines[-1].endswith(" | sha256sum -c -")
    assert lines[-1].count("/models/") == 6
