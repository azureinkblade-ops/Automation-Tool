"""Tests for EA-4D.4F constrained Regional Hand Repair ComfyUI adapter."""

import pytest

from tools.regional_hand_repair_adapter import (
    ALLOWED_SCHEME,
    ALLOWED_HOST,
    ALLOWED_PORT,
    Endpoint,
    AdapterError,
    EndpointNotAllowedError,
    WorkflowNotAllowedError,
    TransportNotConfiguredError,
    RegionalHandRepairComfyUIAdapter,
    FakeComfyUITransport,
)
from tools.regional_hand_repair_workflow import build_frozen_template


@pytest.fixture
def fake_transport():
    return FakeComfyUITransport()


@pytest.fixture
def adapter(fake_transport):
    return RegionalHandRepairComfyUIAdapter(transport=fake_transport)


class TestEndpoint:
    def test_default_endpoint_is_allowed(self):
        ep = Endpoint(scheme="http", host="127.0.0.1", port=8188)
        assert ep.is_allowed()

    def test_non_loopback_host_not_allowed(self):
        ep = Endpoint(scheme="http", host="192.168.1.1", port=8188)
        assert not ep.is_allowed()

    def test_wrong_port_not_allowed(self):
        ep = Endpoint(scheme="http", host="127.0.0.1", port=9999)
        assert not ep.is_allowed()

    def test_https_not_allowed(self):
        ep = Endpoint(scheme="https", host="127.0.0.1", port=8188)
        assert not ep.is_allowed()

    def test_url(self):
        ep = Endpoint(scheme="http", host="127.0.0.1", port=8188)
        assert ep.url("/prompt") == "http://127.0.0.1:8188/prompt"


class TestAdapterConstruction:
    def test_default_endpoint(self, fake_transport):
        adapter = RegionalHandRepairComfyUIAdapter(transport=fake_transport)
        assert adapter.endpoint.scheme == ALLOWED_SCHEME
        assert adapter.endpoint.host == ALLOWED_HOST
        assert adapter.endpoint.port == ALLOWED_PORT

    def test_custom_endpoint(self, fake_transport):
        ep = Endpoint(scheme="http", host="127.0.0.1", port=8188)
        adapter = RegionalHandRepairComfyUIAdapter(transport=fake_transport, endpoint=ep)
        assert adapter.endpoint is ep

    def test_disallowed_endpoint_raises(self, fake_transport):
        with pytest.raises(EndpointNotAllowedError):
            RegionalHandRepairComfyUIAdapter(
                transport=fake_transport,
                endpoint=Endpoint(scheme="https", host="127.0.0.1", port=8188),
            )

    @pytest.mark.parametrize(
        "endpoint",
        [
            Endpoint(scheme="http", host="192.168.1.1", port=8188),
            Endpoint(scheme="http", host="127.0.0.1", port=9999),
        ],
    )
    def test_non_loopback_or_wrong_port_constructor_fails(
        self, fake_transport, endpoint
    ):
        with pytest.raises(EndpointNotAllowedError):
            RegionalHandRepairComfyUIAdapter(
                transport=fake_transport,
                endpoint=endpoint,
            )

    def test_no_transport(self):
        adapter = RegionalHandRepairComfyUIAdapter()
        assert not adapter.has_transport


class TestWorkflowValidation:
    def test_valid_workflow_passes(self, adapter):
        workflow = build_frozen_template()
        adapter.validate_workflow_envelope(workflow)

    def test_invalid_workflow_fails(self, adapter):
        workflow = build_frozen_template()
        workflow["nodes"]["X1"] = {"class_type": "CustomNode", "inputs": {}}
        with pytest.raises(WorkflowNotAllowedError):
            adapter.validate_workflow_envelope(workflow)

    def test_modified_template_fails(self, adapter):
        workflow = build_frozen_template()
        workflow["nodes"]["R7"]["inputs"]["latent_image"] = ["R6T", 0]
        with pytest.raises(WorkflowNotAllowedError):
            adapter.validate_workflow_envelope(workflow)

    @pytest.mark.parametrize(
        "mutation",
        [
            lambda workflow: workflow.clear(),
            lambda workflow: workflow["nodes"].update(
                {"X1": {"class_type": "ShellExecute", "inputs": {}}}
            ),
            lambda workflow: workflow["nodes"].update(
                {"X1": {"class_type": "SaveTextFile", "inputs": {}}}
            ),
            lambda workflow: workflow["nodes"]["R0"]["inputs"].update(
                {"ckpt_name": "unapproved-model.safetensors"}
            ),
            lambda workflow: workflow["nodes"]["R1"]["inputs"].update(
                {"lora_name": "unapproved-lora.safetensors"}
            ),
        ],
    )
    def test_arbitrary_capability_expansion_fails(self, adapter, mutation):
        workflow = build_frozen_template()
        mutation(workflow)
        with pytest.raises(WorkflowNotAllowedError):
            adapter.validate_workflow_envelope(workflow)


class TestSubmitWorkflow:
    def test_submit_valid_workflow(self, adapter, fake_transport):
        workflow = build_frozen_template()
        response = adapter.submit_workflow(workflow)
        assert "prompt_id" in response
        assert len(fake_transport.submissions) == 1

    def test_submit_invalid_workflow_raises(self, adapter, fake_transport):
        workflow = build_frozen_template()
        workflow["nodes"]["X1"] = {"class_type": "CustomNode", "inputs": {}}
        with pytest.raises(WorkflowNotAllowedError):
            adapter.submit_workflow(workflow)
        assert len(fake_transport.submissions) == 0

    def test_submit_without_transport_raises(self):
        adapter = RegionalHandRepairComfyUIAdapter()
        workflow = build_frozen_template()
        with pytest.raises(TransportNotConfiguredError):
            adapter.submit_workflow(workflow)


class TestGetHistory:
    def test_get_history(self, adapter, fake_transport):
        workflow = build_frozen_template()
        response = adapter.submit_workflow(workflow)
        history = adapter.get_history(response["prompt_id"])
        assert "outputs" in history


class TestGetView:
    def test_get_view(self, adapter, fake_transport):
        image = adapter.get_view("test.png")
        assert image == b"fake-image-bytes"


class TestFreeMemory:
    def test_free_memory(self, adapter, fake_transport):
        response = adapter.free_memory()
        assert response["status"] == "ok"
        assert len(fake_transport.free_calls) == 1

    def test_free_memory_without_transport_raises(self):
        adapter = RegionalHandRepairComfyUIAdapter()
        with pytest.raises(TransportNotConfiguredError):
            adapter.free_memory()


class TestFakeTransport:
    def test_submission_count(self, fake_transport):
        fake_transport.submit_workflow({"test": 1})
        fake_transport.submit_workflow({"test": 2})
        assert len(fake_transport.submissions) == 2

    def test_history_stored(self, fake_transport):
        response = fake_transport.submit_workflow({"test": 1})
        history = fake_transport.get_history(response["prompt_id"])
        assert "outputs" in history

    def test_free_calls_tracked(self, fake_transport):
        fake_transport.free_memory(unload_models=True, free_memory=True)
        assert len(fake_transport.free_calls) == 1
        assert fake_transport.free_calls[0]["unload_models"] is True
