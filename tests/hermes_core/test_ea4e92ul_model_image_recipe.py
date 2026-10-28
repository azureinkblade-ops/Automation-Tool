"""Source-only recipe checks; no build, container, or model is invoked."""

from pathlib import Path

from tools.ea4e92rm_container_smoke import EXPECTED_MODEL_FILES
from tools.ea4e92sb_local_model_smoke import IMAGE


RECIPE = Path(__file__).parents[2] / "tools" / "ea4e92ul_model_image.Dockerfile"


def test_recipe_copies_only_reviewed_model_files_from_pinned_base():
    lines = RECIPE.read_text(encoding="ascii").splitlines()
    assert lines == [
        f"FROM {IMAGE}",
        *(f"COPY {name} /models/{name}" for name, _ in EXPECTED_MODEL_FILES),
    ]
    assert len({name for name, _ in EXPECTED_MODEL_FILES}) == 6


def test_recipe_has_no_runtime_or_network_instruction():
    lines = RECIPE.read_text(encoding="ascii").splitlines()
    assert all(line.startswith(("FROM ", "COPY ")) for line in lines)
