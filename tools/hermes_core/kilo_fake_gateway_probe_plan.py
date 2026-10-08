"""Non-launchable plan for a future inert fake-gateway container probe."""

import hashlib
import re


GATEWAY_IMAGE = ("ea4e92ex-fake-gateway@sha256:"
                 "ba59552b483c3fb3a13880da33197f29cada670b80c38862eaa587bed84c3787")
GATEWAY_PLATFORM_MANIFEST = "sha256:7d812fc364c8f4dd47e6b25f83d4074c212fa5ad348d4cda9251b8734557420b"
CLIENT_IMAGE = "sha256:5086932cce035664aee758f4e136262e4e787338b12a1070fc11a84b66e77682"
BODY = b'{"model":"ea4e-inert"}'
CLIENT_SCRIPT = (
    "const http=require('node:http');"
    "const body=Buffer.from('{\"model\":\"ea4e-inert\"}');"
    "const expected='data: {\"choices\":[{\"delta\":{\"content\":\"EA4E_INERT_OK\"}}]}\\n\\n'"
    "+'data: [DONE]\\n\\n';"
    "const req=http.request({hostname:'ea4e-fake-gateway',port:8181,"
    "path:'/v1/chat/completions',method:'POST',headers:{"
    "'Content-Type':'application/json','Content-Length':body.length}},res=>{"
    "let out='';res.setEncoding('utf8');res.on('data',chunk=>{out+=chunk;"
    "if(out.length>512)req.destroy();});res.on('end',()=>{"
    "if(res.statusCode===200&&out===expected)console.log('FAKE_RESPONSE_MATCH');"
    "else process.exitCode=2;});});"
    "req.setTimeout(20000,()=>req.destroy());"
    "req.on('error',()=>{process.exitCode=2;});req.end(body);"
)


def build_fake_gateway_probe_plan(run_id: str) -> dict:
    """Return exact Docker-shaped argv, without running any command."""
    if type(run_id) is not str or re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
        raise ValueError("run identity denied")
    network = f"ea4e-fake-{run_id}"
    gateway = f"ea4e-fake-gateway-{run_id}"
    client = f"ea4e-fake-client-{run_id}"
    common = [
        "--network", network, "--pull", "never", "--platform", "linux/amd64",
        "--restart", "no", "--user", "node", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--pids-limit", "32", "--memory", "256m", "--cpus", "0.25",
        "--label", f"hermes.ea4e.run={run_id}",
    ]
    return {
        "schema_id": "hermes.ea4e-fake-gateway-probe/v1",
        "run_id": run_id,
        "gateway_image": GATEWAY_IMAGE,
        "gateway_platform_manifest": GATEWAY_PLATFORM_MANIFEST,
        "client_image": CLIENT_IMAGE,
        "network_name": network,
        "gateway_name": gateway,
        "client_name": client,
        "network_create": ["docker", "network", "create", "--driver", "bridge",
                           "--internal", "--label", f"hermes.ea4e.run={run_id}", network],
        "gateway_create": ["docker", "container", "create", "--name", gateway,
                           *common, "--network-alias", "ea4e-fake-gateway",
                           GATEWAY_IMAGE],
        "client_create": ["docker", "container", "create", "--name", client,
                          *common, "--entrypoint", "node", CLIENT_IMAGE,
                          "-e", CLIENT_SCRIPT],
        "expected_event": {"event": "FAKE_REQUEST_PENDING",
                           "body_bytes": len(BODY),
                           "body_sha256": hashlib.sha256(BODY).hexdigest()},
        "expected_client_log": "FAKE_RESPONSE_MATCH\n",
        "release_signal": "SIGUSR2",
        "cleanup": "exact_created_container_ids_then_exact_created_network_id_only",
        "max_containers": 2,
        "max_networks": 1,
        "probe_authorized": False,
        "receiver_executed": False,
        "model_invoked": False,
        "production_ready": False,
    }
