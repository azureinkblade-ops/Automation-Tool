"""Acceptance-only fake callback accounting; no live provider capability."""

import os
import hashlib
import json
from pathlib import Path

from tools.ea4e92c_provider_call_control import QualificationProviderGate, utc


class AccountedFakeProviderGate(QualificationProviderGate):
    def __init__(self, store, scope, *, forward, ledger, capture_path, clock):
        self.ledger = ledger
        self.capture_path = Path(capture_path)
        self.clock = clock
        super().__init__(store, scope, forward=self._accounted(forward))

    def _record(self, event_type):
        created_at = self.clock()
        utc(created_at)
        self.ledger.record_model_event(
            request_id="fake-provider:" + self.scope.run_id,
            receiver_id="opencode-cli-agent",
            model_invocation_attempt_id="fake-provider-attempt:" + self.scope.run_id,
            event_type=event_type,
            correlation_id=self.payload["execution_request_id"],
            created_at=created_at,
            model_binding_id=self.scope.model_binding_id,
            invocation_authorization_id=self.payload["invocation_authorization_id"],
        )

    def _accounted(self, forward):
        if not callable(forward):
            raise TypeError("injected fake transport required")

        def call(body):
            self._record("MODEL_INVOCATION_INTENT")
            self._record("MODEL_INVOCATION_ENTERED")
            try:
                response = forward(body)
                if not isinstance(response, bytes) or len(response) > 65536:
                    raise ValueError("invalid bounded fake response")
                # Exclusive creation preserves existing captures and failures.
                with self.capture_path.open("xb") as capture:
                    capture.write(response)
                    capture.flush()
                    os.fsync(capture.fileno())
                manifest = {
                    "capture_class": "FAKE_QUALIFICATION",
                    "scope_hash": self.payload["execution_request_id"],
                    "response_sha256": hashlib.sha256(response).hexdigest(),
                    "response_bytes": len(response),
                }
                with self.capture_path.with_suffix(".manifest.json").open("x", encoding="ascii") as metadata:
                    json.dump(manifest, metadata, sort_keys=True)
                    metadata.flush()
                    os.fsync(metadata.fileno())
                self._record("MODEL_INVOCATION_COMPLETED")
                return response
            except Exception:
                self._record("MODEL_INVOCATION_FAILED")
                raise

        return call

    def verify_capture(self):
        manifest = json.loads(self.capture_path.with_suffix(".manifest.json").read_text(encoding="ascii"))
        response = self.capture_path.read_bytes()
        expected = {
            "capture_class": "FAKE_QUALIFICATION",
            "scope_hash": self.payload["execution_request_id"],
            "response_sha256": hashlib.sha256(response).hexdigest(),
            "response_bytes": len(response),
        }
        if manifest != expected or len(response) > 65536:
            raise ValueError("fake capture integrity mismatch")
        return response
