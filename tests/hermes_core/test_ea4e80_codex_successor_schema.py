"""Non-live candidate identity checks; no executable or pin promotion."""
import pytest

from tools.hermes_core.codex_adapter import (
    PINNED_CODEX_SHA256, PINNED_CODEX_VERSION, PINNED_CLI_CONTRACT_ID,
    codex_cli_contract, codex_cli_contract_id,
    qualify_codex_result_schema_material,
)
from tools.hermes_core.codex_result_schema import (
    STRUCTURAL_POLICY_ID, CodexInstanceSchemaError, CodexResultSchemaLineage,
    build_instance_bound_result_schema, qualify_instance_bound_result_schema,
)

CANDIDATE_SHA = "081e4de4be8e38fac6ed4d95e3b1a0b9f6d31c090ddc36e1696b349fe406f575"
CANDIDATE_VERSION = "codex-cli 0.154.0-alpha.6.2"
CANDIDATE_CONTRACT = "c2d4912a32c00c49c1186a9d49bc7021581dbb86b9a013eaaaffd0eebd8d5a5d"
LINEAGE = CodexResultSchemaLineage("a" * 64, "b" * 64)


def qualification(candidate=True, **changes):
    values = dict(lineage=LINEAGE,
                  binary_sha256=CANDIDATE_SHA if candidate else PINNED_CODEX_SHA256,
                  binary_version=CANDIDATE_VERSION if candidate else PINNED_CODEX_VERSION,
                  cli_contract_id=CANDIDATE_CONTRACT if candidate else PINNED_CLI_CONTRACT_ID)
    values.update(changes)
    return qualify_instance_bound_result_schema(build_instance_bound_result_schema(LINEAGE), **values)


def test_candidate_contract_matches_production_computation():
    assert codex_cli_contract_id(codex_cli_contract(CANDIDATE_SHA, CANDIDATE_VERSION)) == CANDIDATE_CONTRACT
    assert CANDIDATE_CONTRACT != PINNED_CLI_CONTRACT_ID


def test_candidate_schema_passes_existing_structural_validator():
    schema = build_instance_bound_result_schema(LINEAGE)
    structural = qualify_codex_result_schema_material(schema)
    current = qualification()
    assert structural.schema_sha256 == current.instance_schema_sha256
    assert current.structural_policy_id == STRUCTURAL_POLICY_ID


def test_successor_changes_instance_identity_not_schema_or_lineage():
    old, new = qualification(False), qualification()
    assert old.qualification_id != new.qualification_id
    assert old.instance_schema_sha256 == new.instance_schema_sha256
    assert old.instance_lineage_hash == new.instance_lineage_hash
    assert old.structural_policy_id == new.structural_policy_id


def test_historical_instance_qualification_cannot_replay_on_successor():
    with pytest.raises(CodexInstanceSchemaError, match="qualification ID mismatch"):
        qualification(expected_qualification_id=qualification(False).qualification_id)


@pytest.mark.parametrize("changes", [
    {"binary_sha256": "c" * 64},
    {"binary_version": "codex-cli changed"},
    {"cli_contract_id": "d" * 64},
    {"lineage": CodexResultSchemaLineage("e" * 64, "f" * 64)},
    {"expected_structural_policy_id": "0" * 64},
])
def test_changed_binding_cannot_reuse_candidate_qualification(changes):
    with pytest.raises(CodexInstanceSchemaError):
        qualification(expected_qualification_id=qualification().qualification_id, **changes)
