import pytest
from types import SimpleNamespace

from tools import ea4e90_durability_retention_guard as retention


def test_inside_tree_is_retained(tmp_path):
    tree = tmp_path / "evidence"
    tree.mkdir()
    evidence = tree / "capture.txt"
    evidence.write_text("retain", encoding="ascii")
    retention.retain_tree(tree, (tmp_path.resolve(),))
    assert evidence.read_text(encoding="ascii") == "retain"


def test_outside_tree_is_denied(tmp_path):
    with pytest.raises(RuntimeError, match="outside isolated roots"):
        retention.retain_tree(tmp_path.parent, (tmp_path.resolve(),))


def test_resolved_parent_escape_is_denied(tmp_path):
    with pytest.raises(RuntimeError, match="outside isolated roots"):
        retention.retain_tree(tmp_path / ".." / "outside", (tmp_path.resolve(),))


def test_pytest_reuses_created_root(tmp_path):
    factory = SimpleNamespace(_basetemp=None)
    config = SimpleNamespace(
        option=SimpleNamespace(basetemp=str(tmp_path)), _tmp_path_factory=factory
    )
    retention.pytest_sessionstart(SimpleNamespace(config=config))
    assert factory._basetemp == tmp_path.resolve()
