"""Tests for EA-4D.4F Regional Hand Repair pilot composition root."""

import os
import tempfile
import pytest

from tools.regional_hand_repair_pilot import (
    PilotConfig,
    RegionalHandRepairPilotRoot,
    create_pilot_root,
)


class TestPilotConfig:
    def test_default_config_is_inactive(self):
        config = PilotConfig()
        assert not config.is_active()

    def test_enabled_config_is_active(self):
        config = PilotConfig(enabled=True)
        assert config.is_active()

    def test_default_endpoint(self):
        config = PilotConfig()
        assert config.comfyui_endpoint == "http://127.0.0.1:8188"


class TestPilotRoot:
    def test_create_inactive_root(self):
        root = create_pilot_root(enabled=False)
        assert not root.is_active
        root.close()

    def test_create_active_root(self):
        root = create_pilot_root(enabled=True)
        assert root.is_active
        root.close()

    def test_create_with_custom_db_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            root = create_pilot_root(enabled=True, evidence_db_path=db_path)
            assert root.is_active
            root.close()

    def test_evidence_store_lazy_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            root = create_pilot_root(enabled=True, evidence_db_path=db_path)
            store = root._get_evidence_store()
            assert store is not None
            root.close()

    def test_submission_orchestrator_lazy_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            root = create_pilot_root(enabled=True, evidence_db_path=db_path)
            orchestrator = root._get_submission_orchestrator()
            assert orchestrator is not None
            root.close()

    def test_verification_orchestrator_lazy_init(self):
        root = create_pilot_root(enabled=True)
        orchestrator = root._get_verification_orchestrator()
        assert orchestrator is not None
        root.close()

    def test_cleanup_orchestrator_lazy_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            root = create_pilot_root(enabled=True, evidence_db_path=db_path)
            orchestrator = root._get_cleanup_orchestrator()
            assert orchestrator is not None
            root.close()
