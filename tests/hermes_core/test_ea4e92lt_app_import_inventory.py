"""Static inventory qualification; no imported source is executed."""

import hashlib

import pytest

from tools.ea4e92lt_app_import_inventory import inventory_local_imports


def test_recursive_local_imports_hash_source_without_execution(tmp_path):
    (tmp_path / "pkg").mkdir()
    source = b"import pkg.worker\nfrom pkg import helper\n"
    (tmp_path / "app.py").write_bytes(source)
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "worker.py").write_text(
        "from . import helper\nraise RuntimeError('must not execute')\n", encoding="utf-8")
    (tmp_path / "pkg" / "helper.py").write_text(
        "import pkg.worker\n", encoding="utf-8")
    result = inventory_local_imports(tmp_path, "app.py")
    paths = [file.path for file in result.files]
    assert paths == ["app.py", "pkg/__init__.py", "pkg/helper.py", "pkg/worker.py"]
    assert result.files[0].sha256 == hashlib.sha256(source).hexdigest()
    assert result.dynamic_import_sites == ()


def test_parent_relative_import_and_dynamic_sites_are_reported(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "sub").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "helper.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "work.py").write_text(
        "from .. import helper\nimport importlib\nimportlib.import_module(target)\n",
        encoding="utf-8")
    result = inventory_local_imports(tmp_path, "pkg/sub/work.py")
    assert "pkg/helper.py" in [file.path for file in result.files]
    assert result.dynamic_import_sites == ("pkg/sub/work.py:3",)


def test_literal_runtime_import_is_included_without_execution(tmp_path):
    (tmp_path / "app.py").write_text(
        "__import__('local')\n", encoding="utf-8")
    (tmp_path / "local.py").write_text(
        "raise RuntimeError('must not execute')\n", encoding="utf-8")
    result = inventory_local_imports(tmp_path, "app.py")
    assert [file.path for file in result.files] == ["app.py", "local.py"]
    assert result.dynamic_import_sites == ()


def test_external_imports_are_not_claimed_as_local(tmp_path):
    (tmp_path / "app.py").write_text(
        "import json\nfrom elsewhere import missing\n", encoding="utf-8")
    result = inventory_local_imports(tmp_path, "app.py")
    assert [file.path for file in result.files] == ["app.py"]


def test_outside_entry_and_bound_fail_closed(tmp_path):
    (tmp_path / "app.py").write_text("import local\n", encoding="utf-8")
    (tmp_path / "local.py").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="file bound"):
        inventory_local_imports(tmp_path, "app.py", max_files=1)
    with pytest.raises(ValueError, match="under the root"):
        inventory_local_imports(tmp_path, tmp_path.parent / "other.py")


def test_explicit_dynamic_module_is_included_and_missing_one_denied(tmp_path):
    (tmp_path / "app.py").write_text(
        "import importlib\nimportlib.import_module(factory_name)\n",
        encoding="utf-8")
    (tmp_path / "receiver.py").write_text(
        "raise RuntimeError('must not execute')\n", encoding="utf-8")
    result = inventory_local_imports(
        tmp_path, "app.py", additional_modules=("receiver",))
    assert [file.path for file in result.files] == ["app.py", "receiver.py"]
    assert result.dynamic_import_sites == ("app.py:2",)
    with pytest.raises(ValueError, match="unavailable"):
        inventory_local_imports(
            tmp_path, "app.py", additional_modules=("missing",))
    with pytest.raises(ValueError, match="unavailable"):
        inventory_local_imports(
            tmp_path, "app.py", additional_modules=("../receiver",))
