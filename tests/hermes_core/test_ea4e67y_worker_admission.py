from pathlib import Path

import pytest

from tools import ea4e67y_worker_admission as admission


@pytest.fixture
def launch(tmp_path):
    node = admission.WORKER + "RealSpawnTests::test_valid_probe_returns_started"
    return dict(node=node, argv=[str(admission.PYTHON), str(admission.HELPER), str(tmp_path / "worker.sqlite")],
                cwd=str(admission.ROOT), environment={"TEMP": str(tmp_path), "TMP": str(tmp_path)},
                basetemp=tmp_path, admitted={})


def test_valid_launch_is_only_a_plan(launch):
    state = admission.validate_worker_launch(**launch)
    assert state == Path(launch["argv"][-1])
    assert not state.exists()
    assert launch["admitted"] == {}


@pytest.mark.parametrize("case", ["node", "executable", "helper", "flags", "state", "cwd", "credential", "temp", "budget", "hash", "negative_count", "system_env", "alternate_stream"])
def test_rejects_unqualified_launch(case, launch, monkeypatch):
    if case == "node":
        launch["node"] = "unknown"
    elif case == "executable":
        launch["argv"][0] = "unqualified.exe"
    elif case == "helper":
        launch["argv"][1] = "unqualified.py"
    elif case == "flags":
        launch["argv"].insert(2, "--extra")
    elif case == "state":
        launch["argv"][-1] = str(admission.ROOT / "live.sqlite")
    elif case == "cwd":
        launch["cwd"] = str(launch["basetemp"])
    elif case == "credential":
        launch["environment"]["API_KEY"] = "synthetic-test-only"
    elif case == "temp":
        launch["environment"]["TEMP"] = str(admission.ROOT)
    elif case == "budget":
        launch["admitted"][launch["node"]] = 1
    elif case == "hash":
        monkeypatch.setattr(admission, "HELPER_SHA256", "0" * 64)
    elif case == "negative_count":
        launch["admitted"][launch["node"]] = -1
    elif case == "system_env":
        launch["environment"]["SYSTEMROOT"] = "unqualified-system-root"
    elif case == "alternate_stream":
        launch["argv"][-1] = str(launch["basetemp"] / "worker:stream.sqlite")
    with pytest.raises(ValueError):
        admission.validate_worker_launch(**launch)


def test_budget_and_identity_scope():
    assert len(admission.FLAGS) == 13
    assert admission.PROCESS_BUDGET == 14
    assert all("missing" not in node for node in admission.FLAGS)
