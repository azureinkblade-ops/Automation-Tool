"""Prepare a credential-free Kilo probe and serve an inert loopback provider.

This tool never launches Kilo and never forwards a provider request.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


MODEL = "openai-compatible/ea4e-inert"
MODEL_ID = "ea4e-inert"
DUMMY_KEY = "EA4E_INERT_ONLY"
MARKER = "EA4E_INERT_OK"
MAX_BODY_BYTES = 65536
REPO_ROOT = Path(__file__).resolve().parent.parent


def pinned_binary() -> tuple[Path, str]:
    source = ast.parse((REPO_ROOT / "tools/hermes_core/kilo_adapter.py").read_text(encoding="utf-8"))
    values = {}
    for node in source.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {"PINNED_KILO_PATH", "PINNED_KILO_SHA256"}:
                values[target.id] = ast.literal_eval(node.value)
    return Path(values["PINNED_KILO_PATH"]), values["PINNED_KILO_SHA256"]


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def prepare(root: Path, port: int, *, binary: Path | None = None, expected_sha: str | None = None) -> Path:
    """Create only new, isolated probe files; never launch the receiver."""
    root = Path(root).resolve()
    if root.exists() or _under(root, REPO_ROOT) or not 1 <= port <= 65535:
        raise ValueError("probe root must be new, outside the repository, with a valid port")
    if binary is None or expected_sha is None:
        binary, expected_sha = pinned_binary()
    binary = Path(binary).resolve(strict=True)
    hasher = hashlib.sha256()
    with binary.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != expected_sha.lower():
        raise ValueError("pinned Kilo binary hash mismatch")

    home = root / "home"
    config_dir = root / "config"
    agent_id = "hermes-ea4e-kilo-receiver"
    agent_dir = home / ".kilo" / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    config_dir.mkdir()
    (home / "tmp").mkdir()
    agent = {
        "name": agent_id,
        "description": "Inert EA-4E provider probe; no tools or real model",
        "permission": {"*": "deny"},
    }
    (agent_dir / f"{agent_id}.jsonc").write_text(json.dumps(agent, indent=2) + "\n", encoding="ascii")
    config = {
        "model": MODEL,
        "provider": {
            "openai-compatible": {
                "options": {"apiKey": DUMMY_KEY, "baseURL": f"http://127.0.0.1:{port}/v1"},
                "models": {MODEL_ID: {"name": "EA-4E inert probe", "tool_call": False,
                                      "limit": {"context": 8192, "output": 64}}},
            }
        },
    }
    config_text = json.dumps(config, sort_keys=True)
    (config_dir / "kilo.jsonc").write_text(config_text + "\n", encoding="ascii")
    env = {
        "HOME": str(home), "USERPROFILE": str(home),
        "HOMEDRIVE": home.drive, "HOMEPATH": str(home)[len(home.drive):],
        "APPDATA": str(root / "appdata"), "LOCALAPPDATA": str(root / "localappdata"),
        "XDG_CONFIG_HOME": str(config_dir), "XDG_DATA_HOME": str(root / "data"),
        "XDG_CACHE_HOME": str(root / "cache"), "KILO_HOME": str(home),
        "KILO_CONFIG_DIR": str(config_dir), "KILO_CONFIG_CONTENT": config_text,
        "KILO_PURE": "1", "OPENCODE_PURE": "1", "OPENCODE_TEST_HOME": str(home),
        "OPENCODE_CONFIG_DIR": str(config_dir), "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
        "TEMP": str(home / "tmp"), "TMP": str(home / "tmp"),
        "PATH": str(binary.parent),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "PROCESSOR_ARCHITECTURE": os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64"),
    }
    plan = {
        "binary_sha256": digest,
        "argv": [str(binary), "run", "--format", "json", "--pure", "--agent", agent_id,
                 "--model", MODEL, f"Reply with exactly {MARKER}. Do not use tools."],
        "cwd": str(root), "env": env,
        "credential_class": "DUMMY_LOCAL_ONLY",
        "launch_authorized": False,
        "network_isolation_verified": False,
        "real_provider_calls_authorized": False,
    }
    output = root / "launch-plan.json"
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return output


def fake_response(method: str, path: str, payload: object) -> tuple[int, str, bytes]:
    """Pure response builder; no socket or provider capability."""
    if method == "GET" and path == "/v1/models":
        body = {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}
        return 200, "application/json", json.dumps(body).encode("ascii")
    if method != "POST" or path != "/v1/chat/completions" or not isinstance(payload, dict):
        return 404, "application/json", b'{"error":{"message":"inert endpoint only"}}'
    if payload.get("model") != MODEL_ID:
        return 400, "application/json", b'{"error":{"message":"unknown inert model"}}'
    response = {"id": "ea4e-inert", "object": "chat.completion", "created": 0,
                "model": MODEL_ID, "choices": [{"index": 0, "message": {"role": "assistant",
                "content": MARKER}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
    if payload.get("stream") is True:
        chunk = {"id": "ea4e-inert", "object": "chat.completion.chunk", "created": 0,
                 "model": MODEL_ID, "choices": [{"index": 0,
                 "delta": {"role": "assistant", "content": MARKER}, "finish_reason": None}]}
        finish = {"id": "ea4e-inert", "object": "chat.completion.chunk", "created": 0,
                  "model": MODEL_ID, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        body = f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(finish)}\n\ndata: [DONE]\n\n"
        return 200, "text/event-stream", body.encode("ascii")
    return 200, "application/json", json.dumps(response).encode("ascii")


class InertProviderHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        pass

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def _handle(self, method: str) -> None:
        # Never retain, print, or forward request content or authorization values.
        path = urlsplit(self.path).path
        if self.headers.get("Authorization") != f"Bearer {DUMMY_KEY}":
            status, content_type, body = 401, "application/json", b'{"error":{"message":"unauthorized"}}'
            stream = None
        else:
            length_text = self.headers.get("Content-Length", "0")
            if not length_text.isdecimal() or int(length_text) > MAX_BODY_BYTES:
                status, content_type, body = 413, "application/json", b'{"error":{"message":"body too large"}}'
                stream = None
            else:
                raw = self.rfile.read(int(length_text))
                try:
                    payload = json.loads(raw) if raw else None
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = None
                stream = payload.get("stream") if isinstance(payload, dict) else None
                status, content_type, body = fake_response(method, path, payload)
        print(json.dumps({"method": method, "path": path, "status": status,
                          "stream": stream}), flush=True)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--root", required=True, type=Path)
    prep.add_argument("--port", required=True, type=int)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.action == "prepare":
        print(prepare(args.root, args.port))
        return
    with ThreadingHTTPServer(("127.0.0.1", args.port), InertProviderHandler) as server:
        print(json.dumps({"loopback_port": server.server_port, "forwards": False}), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
