# -*- coding: utf-8 -*-
"""PYTEST_LIVE_SIDE_EFFECT_ISOLATION - deterministic barrier self-tests.

No real remote connection is ever made: every outbound attempt is refused before
DNS / connect.  The only real socket traffic is a loopback listener owned by the
test itself, reachable solely through @pytest.mark.allow_network(host, port).
"""
from __future__ import annotations

import asyncio
import http.client
import json
import os
import socket
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests import live_side_effect_barrier as lsb

REPO = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    # bind/listen are not blocked; only outbound connect/resolve/sendto are.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        return srv.getsockname()[1]


ALLOW_PORT = _free_port()


def _blocked(rec, *needles):
    hits = [a for a in rec if all(n in a["dest"] for n in needles)]
    assert hits, f"no recorded attempt for {needles}: {rec}"
    return hits


# ---------------------------------------------------------------- phase 1
def test_barrier_active_before_test_module_import():
    assert lsb.is_active()
    assert lsb.INSTALL_INFO["barrier_active_before_test_module_import"] is True, lsb.INSTALL_INFO
    assert lsb.NETWORK_DEFAULT == lsb.LOCALHOST_DEFAULT == lsb.COMFYUI_ACCESS == "DENY"
    assert os.environ["AT_GPU_TEST_BARRIER"] == "1"


# ---------------------------------------------------------------- phase 2 / 8 network
def test_outbound_socket_blocked():
    with lsb.expect_block() as rec:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(lsb.NetworkBlocked):
                s.connect(("203.0.113.10", 443))
            with pytest.raises(lsb.NetworkBlocked):
                s.connect_ex(("203.0.113.10", 80))
        finally:
            s.close()
        with pytest.raises(lsb.NetworkBlocked):
            socket.create_connection(("203.0.113.10", 443), timeout=1)
        with pytest.raises(lsb.NetworkBlocked):
            socket.getaddrinfo("example.com", 443)
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with pytest.raises(lsb.NetworkBlocked):
                u.sendto(b"x", ("203.0.113.10", 53))
        finally:
            u.close()
    _blocked(rec, "203.0.113.10:443")
    _blocked(rec, "example.com")
    assert all(a["expected"] for a in rec)


def test_localhost_comfyui_8188_blocked():
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.NetworkBlocked):
            socket.create_connection(("127.0.0.1", 8188), timeout=1)
        with pytest.raises(OSError):  # urllib wraps the refusal in URLError; still recorded
            urllib.request.urlopen("http://127.0.0.1:8188/prompt", timeout=1)
        with pytest.raises(lsb.NetworkBlocked):
            socket.create_connection(("localhost", 8188), timeout=1)
    hits = _blocked(rec, "127.0.0.1", "8188")
    assert all(h["category"] == "comfyui" for h in hits)


def test_plain_localhost_blocked_by_default():
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.NetworkBlocked):
            socket.create_connection(("127.0.0.1", ALLOW_PORT), timeout=1)
    assert _blocked(rec, f"127.0.0.1:{ALLOW_PORT}")[0]["category"] == "localhost"


def test_buffer_api_host_blocked_urllib():
    with lsb.expect_block() as rec:
        req = urllib.request.Request("https://api.buffer.com", data=b"{}", method="POST")
        with pytest.raises(urllib.error.URLError) as ei:
            urllib.request.urlopen(req, timeout=1)
        assert isinstance(ei.value.reason, lsb.NetworkBlocked)
    _blocked(rec, "api.buffer.com")


def test_openai_google_github_hosts_blocked_all_clients():
    with lsb.expect_block() as rec:
        import requests
        with pytest.raises(requests.exceptions.ConnectionError):
            requests.post("https://api.openai.com/v1/chat/completions", json={}, timeout=1)
        import httpx
        with pytest.raises(httpx.ConnectError):
            httpx.get("https://generativelanguage.googleapis.com/v1beta/models", timeout=1)
        conn = http.client.HTTPSConnection("api.github.com", 443, timeout=1)
        with pytest.raises(lsb.NetworkBlocked):
            conn.request("GET", "/user")
        import urllib3
        with pytest.raises(Exception):
            urllib3.PoolManager(retries=False).request("GET", "https://oauth2.googleapis.com/token", timeout=1)
    for host in ("api.openai.com", "generativelanguage.googleapis.com", "api.github.com", "oauth2.googleapis.com"):
        _blocked(rec, host)


def test_asyncio_and_httpx_async_blocked():
    async def go():
        with pytest.raises(lsb.NetworkBlocked):
            await asyncio.open_connection("203.0.113.11", 443)
        with pytest.raises(lsb.NetworkBlocked):
            await asyncio.open_connection("api.buffer.com", 443)
        loop = asyncio.get_running_loop()
        s = socket.socket()
        s.setblocking(False)
        try:
            with pytest.raises(lsb.NetworkBlocked):
                await loop.sock_connect(s, ("203.0.113.12", 443))
        finally:
            s.close()
        import httpx
        async with httpx.AsyncClient() as c:
            with pytest.raises(httpx.ConnectError):
                await c.get("https://api.openai.com/v1/models", timeout=1)

    with lsb.expect_block() as rec:
        asyncio.run(go())  # event-loop creation (socketpair self-pipe) must still work
    _blocked(rec, "203.0.113.11:443")
    _blocked(rec, "203.0.113.12:443")
    _blocked(rec, "api.openai.com")


def test_swallowed_exception_is_still_recorded():
    with lsb.expect_block() as rec:
        try:
            socket.create_connection(("203.0.113.13", 443), timeout=1)
        except Exception:
            pass  # code under test swallowing the refusal
    _blocked(rec, "203.0.113.13:443")
    # The same attempt outside expect_block() would be listed by unexpected_attempts()
    # and fail the session in pytest_sessionfinish.
    assert all(a["dest"] != "203.0.113.13:443" for a in lsb.unexpected_attempts(include_children=False))


@pytest.mark.allow_network("127.0.0.1", ALLOW_PORT)
def test_allow_network_marker_exact_host_port():
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", ALLOW_PORT))
        srv.listen(1)
        assert ("127.0.0.1", ALLOW_PORT) in lsb.allowed_destinations()
        c = socket.create_connection(("127.0.0.1", ALLOW_PORT), timeout=2)
        c.close()
        with lsb.expect_block() as rec:  # a different port on the same host is still denied
            with pytest.raises(lsb.NetworkBlocked):
                socket.create_connection(("127.0.0.1", ALLOW_PORT + 1 if ALLOW_PORT < 65535 else 1), timeout=1)
            with pytest.raises(lsb.NetworkBlocked):  # 'localhost' is a different host string
                socket.getaddrinfo("localhost", ALLOW_PORT)
        assert len(rec) == 2


def test_allow_network_does_not_leak_into_next_test():
    assert lsb.allowed_destinations() == set()
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", ALLOW_PORT))
        srv.listen(1)
        with lsb.expect_block() as rec:
            with pytest.raises(lsb.NetworkBlocked):
                socket.create_connection(("127.0.0.1", ALLOW_PORT), timeout=1)
    _blocked(rec, f"127.0.0.1:{ALLOW_PORT}")


# ---------------------------------------------------------------- phase 3 subprocess
@pytest.mark.parametrize("argv", [
    ["git", "push", "origin", "HEAD"],
    ["git", "-C", ".", "push", "--force"],
    ["git", "remote", "set-url", "origin", "https://example.invalid/x.git"],
    ["git", "remote", "add", "evil", "https://example.invalid/x.git"],
    ["git", "fetch", "origin"],
    ["git", "commit", "-m", "x"],
])
def test_git_remote_or_live_mutation_blocked(argv):
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.SubprocessBlocked):
            subprocess.run(argv, cwd=str(REPO), capture_output=True)
    assert rec and rec[0]["kind"] == "subprocess"


@pytest.mark.parametrize("argv", [
    ["gh", "pr", "create", "--fill"],
    ["gh", "repo", "edit"],
    ["gh", "api", "-X", "POST", "repos/x/y/issues"],
    ["gh", "release", "create", "v0"],
    ["gh", "workflow", "run", "x"],
])
def test_gh_remote_mutation_blocked(argv):
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.SubprocessBlocked):
            subprocess.check_output(argv)
        with pytest.raises(lsb.SubprocessBlocked):
            subprocess.call(" ".join(argv), shell=True)
    assert len(rec) == 2


def test_os_system_popen_exec_spawn_blocked():
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.SubprocessBlocked):
            os.system("git push origin HEAD")
        with pytest.raises(lsb.SubprocessBlocked):
            os.popen("gh pr merge 1")
        with pytest.raises(lsb.SubprocessBlocked):
            os.system("curl https://api.buffer.com")
        if hasattr(os, "spawnv"):
            with pytest.raises(lsb.SubprocessBlocked):
                os.spawnv(os.P_WAIT, "git", ["git", "push"])
        with pytest.raises(lsb.SubprocessBlocked):
            os.execv("git", ["git", "push"])  # refused before the process image is replaced
    assert len(rec) >= 4


def test_asyncio_subprocess_blocked():
    async def go():
        with pytest.raises(lsb.SubprocessBlocked):
            await asyncio.create_subprocess_exec("git", "push", "origin")
        with pytest.raises(lsb.SubprocessBlocked):
            await asyncio.create_subprocess_shell("gh release create v9")
    with lsb.expect_block() as rec:
        asyncio.run(go())
    assert len(rec) == 2


def test_gitpython_push_blocked():
    git = pytest.importorskip("git")
    from git import remote as r
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.SubprocessBlocked):
            r.Remote.push(object.__new__(r.Remote))
    assert rec


def test_generator_subprocess_blocked():
    from tests import gpu_test_barrier as g
    blocked = (lsb.SubprocessBlocked, g.GpuTestBarrierError)
    hits0 = g.block_hit_count()
    with lsb.expect_block() as rec:
        with pytest.raises(blocked):
            subprocess.run([sys.executable, str(REPO / "local_image_generator.py"), "--prompt", "x"],
                           cwd=str(REPO), capture_output=True)
        with pytest.raises(blocked):
            subprocess.Popen(["python", "ComfyUI/main.py", "--listen"])
        # our own layer refuses it as well (independent of the R3 GPU barrier)
        assert lsb.classify_command([sys.executable, "local_image_generator.py", "--prompt", "x"])
        assert lsb.classify_command(["python", "ComfyUI/main.py", "--listen"])
    assert len(rec) + (g.block_hit_count() - hits0) >= 2


def test_python_child_without_inheritance_blocked():
    with lsb.expect_block() as rec:
        for flag in ("-I", "-E", "-S"):
            with pytest.raises(lsb.SubprocessBlocked):
                subprocess.run([sys.executable, flag, "-c", "print(1)"], capture_output=True)
    assert len(rec) == 3


def test_harmless_git_allowed():
    for argv in (["git", "status", "--short"], ["git", "rev-parse", "HEAD"],
                 ["git", "log", "-1", "--format=%h"], ["git", "diff", "--stat"],
                 ["git", "show", "--stat", "--format=%h", "HEAD"], ["git", "branch", "--show-current"]):
        r = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True)
        assert r.returncode == 0, (argv, r.stderr)


def test_python_child_inherits_barrier(tmp_path):
    child_rec = tmp_path / "child_attempts.jsonl"
    env = dict(os.environ)
    env["BUFFER_API_KEY"] = "placeholder-not-a-credential"
    env["OPENAI_API_KEY"] = "placeholder-not-a-credential"
    env["AT_LIVE_BARRIER_RECORD"] = str(child_rec)
    code = textwrap.dedent("""
        import os, socket, subprocess, json
        out = {"barrier": os.environ.get("AT_GPU_TEST_BARRIER"),
               "creds": sorted(k for k in os.environ if k.startswith(("BUFFER", "OPENAI")))}
        try:
            socket.create_connection(("127.0.0.1", 8188), timeout=1); out["net"] = "CONNECTED"
        except PermissionError as e:
            out["net"] = type(e).__name__
        try:
            subprocess.run(["git", "push"]); out["push"] = "RAN"
        except PermissionError as e:
            out["push"] = type(e).__name__
        print("CHILD=" + json.dumps(out))
    """)
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    line = [x for x in r.stdout.splitlines() if x.startswith("CHILD=")]
    assert line, (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
    out = json.loads(line[0][6:])
    assert out == {"barrier": "1", "creds": [], "net": "NetworkBlocked", "push": "SubprocessBlocked"}
    recs = [json.loads(x) for x in child_rec.read_text(encoding="utf-8").splitlines()]
    assert {a["kind"] for a in recs} == {"network", "subprocess"}


# ---------------------------------------------------------------- collect-only bypass
def test_collect_only_import_time_side_effects_cannot_bypass(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "test_import_time_connect.py").write_text(
        "import socket\nsocket.create_connection(('127.0.0.1', 8188), timeout=1)\n"
        "def test_x():\n    pass\n", encoding="utf-8")
    (proj / "test_import_time_push.py").write_text(
        "import subprocess\nsubprocess.run(['git', 'push', 'origin', 'HEAD'])\n"
        "def test_y():\n    pass\n", encoding="utf-8")
    child_rec = tmp_path / "collect_attempts.jsonl"
    env = dict(os.environ)
    env["AT_LIVE_BARRIER_RECORD"] = str(child_rec)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "--rootdir", str(proj), str(proj)],
        cwd=str(proj), env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode != 0, r.stdout[-3000:]
    assert "NetworkBlocked" in r.stdout and "SubprocessBlocked" in r.stdout, r.stdout[-3000:]
    recs = [json.loads(x) for x in child_rec.read_text(encoding="utf-8").splitlines()]
    assert any(a["kind"] == "network" and "8188" in a["dest"] for a in recs)
    assert any(a["kind"] == "subprocess" and "push" in a["dest"] for a in recs)


def test_in_process_import_time_connect_blocked(tmp_path, monkeypatch):
    mod = tmp_path / "lsi_import_time_mod.py"
    mod.write_text("import socket\nsocket.create_connection(('api.buffer.com', 443))\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.NetworkBlocked):
            importlib.import_module("lsi_import_time_mod")
    _blocked(rec, "api.buffer.com")


# ---------------------------------------------------------------- phase 5 outputs
def test_production_output_roots_redirected():
    import app as app_mod
    import app_config
    import buffer_publish as bp
    import browser_publish as br
    tmp_roots = [str(lsb.TEMP_ROOT)]
    iso = os.environ.get("AT_TEST_ISOLATION_ROOT")
    if iso:
        tmp_roots.append(iso)
    for mod, attrs in (
        (app_mod, ["SOCIAL_OUTPUT_DIR", "TIKTOK_OUTPUT_DIR", "OUTPUT_DIR", "YOUTUBE_OUTPUT_DIR",
                   "STORY_HOOK_OUTPUT_DIR", "MANUAL_VIDEO_OUTPUT_DIR", "EXPERIMENT_OUTPUT_DIR",
                   "GITHUB_MEDIA_DIR", "PINNED_ASSET_OUTPUT_DIR", "CLOUDFLARE_MEDIA_DIR",
                   "PROMO_IMAGES_DIR", "GENERATED_PROMO_IMAGES_DIR", "TIKTOK_ASSET_DIR",
                   "GITHUB_MEDIA_REPO_DIR", "IMAGE_LAB_DIR"]),
        (app_config, ["SOCIAL_OUTPUT_DIR", "TIKTOK_OUTPUT_DIR", "OUTPUT_DIR"]),
        (bp, ["SOCIAL_OUTPUT_DIR", "TIKTOK_OUTPUT_DIR"]),
        (br, ["SOCIAL_OUTPUT_DIR"]),
    ):
        for a in attrs:
            if hasattr(mod, a):
                v = str(Path(getattr(mod, a)).resolve())
                assert any(v.startswith(str(Path(t).resolve())) for t in tmp_roots), (mod.__name__, a, v)
    from tools import identity_preservation as ip
    assert str(ip.default_log_path()).startswith(str(lsb.TEMP_ROOT))
    assert os.environ["AIVSB_TELEMETRY_PATH"].startswith(str(lsb.TEMP_ROOT))
    import logging
    import tools.agent_post_writer  # noqa: F401  (import-time FileHandler under logs/)
    hs = [h for h in logging.getLogger("automation.agent_post_writer").handlers if hasattr(h, "baseFilename")]
    ok = lambda f: str(f).startswith(str(lsb.TEMP_ROOT)) or str(f) == os.devnull or str(f).lower().replace("\\", "/").rstrip("/").endswith(("/nul", "/dev/null"))
    assert hs and all(ok(h.baseFilename) for h in hs), hs


def test_fixture_writes_land_under_temp_root():
    import app as app_mod
    tmp = str(Path(lsb.TEMP_ROOT).resolve()), str(Path(os.environ.get("AT_TEST_ISOLATION_ROOT", lsb.TEMP_ROOT)).resolve())
    for base, name in ((app_mod.SOCIAL_OUTPUT_DIR, "x_fixture_pack"), (app_mod.SOCIAL_OUTPUT_DIR, "ig_fixture_pack"),
                       (app_mod.TIKTOK_OUTPUT_DIR, "reel_fixture_pack")):
        d = Path(base) / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "metadata.json").write_text("{}", encoding="utf-8")
        assert str(d.resolve()).startswith(tmp), d


def test_live_output_write_refused():
    targets = [REPO / "social-posts" / "lsi_probe_never_created.json",
               REPO / "tiktok-posts" / "lsi_probe_never_created.json",
               REPO / "logs" / "identity_preservation" / "lsi_probe_never_created.jsonl",
               Path(lsb.LIVE_WRITE_ROOTS[0]) / "lsi_probe_never_created.png"]
    with lsb.expect_block() as rec:
        for t in targets:
            with pytest.raises(lsb.LiveWriteBlocked):
                t.write_text("x", encoding="utf-8")
            assert not t.exists()
        with pytest.raises(lsb.LiveWriteBlocked):
            os.mkdir(REPO / "social-posts" / "lsi_probe_dir_never_created")
    assert len(rec) == len(targets) + 1


# ---------------------------------------------------------------- phase 6 credentials
def test_no_external_credentials_in_test_process():
    from tests import live_side_effect_hooks as hooks
    assert hooks._CONFIG_CRED_NAMES == [], hooks._CONFIG_CRED_NAMES
    leftover = [k for k in lsb.external_credential_names() if k != "X_ACCESS_TOKEN"]
    # X_ACCESS_TOKEN may be set to the literal placeholder by tests/test_buffer_publish.py
    assert leftover == [], leftover
    if "X_ACCESS_TOKEN" in os.environ:
        assert os.environ["X_ACCESS_TOKEN"] == "test_token_for_parity"


def test_env_local_not_loaded():
    import app as app_mod
    before = dict(os.environ)
    app_mod.load_env_file()
    assert dict(os.environ) == before
    assert not Path(app_mod.ENV_FILE).exists()
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.CredentialFileBlocked):
            open(REPO / ".env.local", "rb").close()
    assert rec and rec[0]["dest"] == ".env.local"


# ---------------------------------------------------------------- phase 7 buffer
def test_buffer_unmocked_create_post_blocked_before_http(monkeypatch):
    import app as app_mod
    monkeypatch.setenv("BUFFER_API_KEY", "placeholder-not-a-credential")
    assert getattr(app_mod.create_buffer_post, "__module__", "") == "app"  # real, unmocked
    with lsb.expect_block() as rec:
        with pytest.raises(Exception) as ei:
            app_mod.create_buffer_post("lsi-channel", "barrier probe", [], mode="draft")
    net = [a for a in rec if a["kind"] == "network"]
    assert net and "api.buffer.com" in net[0]["dest"], rec
    # refused at create_connection/getaddrinfo, i.e. before DNS - no byte of HTTP left
    assert net[0]["where"] in ("socket.create_connection", "socket.getaddrinfo"), net
    chain = []
    e = ei.value
    while e is not None and len(chain) < 10:
        chain.append(e)
        e = getattr(e, "reason", None) or e.__cause__ or e.__context__
    assert any(isinstance(x, lsb.NetworkBlocked) for x in chain), chain


def test_buffer_publish_mock_still_present():
    src = (REPO / "tests" / "test_buffer_publish.py").read_text(encoding="utf-8")
    assert 'BP_COLLAB["create_buffer_post"] = fake_create_buffer_post' in src


def test_credential_name_classifier():
    for n in ("BUFFER_API_KEY", "BUFFER_STUDIO_API_KEY", "OPENAI_API_KEY", "GOOGLE_AI_API_KEY",
              "GEMINI_API_KEY", "GITHUB_TOKEN", "GITHUB_WRITE_TOKEN", "GH_TOKEN", "PATREON_CLIENT_SECRET",
              "PINTEREST_REFRESH_TOKEN", "CLICKUP_API_TOKEN", "CLOUDFLARE_R2_ACCESS_KEY_ID",
              "PEXELS_API_KEY", "PIXABAY_API_KEY", "YOUTUBE_DATA_API_KEY", "X_ACCESS_TOKEN"):
        assert lsb.is_external_credential_name(n), n
    for n in ("TIKTOK_ASSET_DIR", "GITHUB_MEDIA_REPO_DIR", "AT_GPU_TEST_BARRIER", "PATH",
              "PYTHONPATH", "CUDA_VISIBLE_DEVICES", "ENABLE_IDENTITY_PRESERVATION"):
        assert not lsb.is_external_credential_name(n), n
    assert lsb.STRIPPED_CREDENTIAL_NAMES == sorted(lsb.STRIPPED_CREDENTIAL_NAMES)
    assert os.environ["TIKTOK_ASSET_DIR"].startswith(str(lsb.TEMP_ROOT))
    assert os.environ["GITHUB_MEDIA_REPO_DIR"].startswith(str(lsb.TEMP_ROOT))


def test_every_secret_like_env_file_key_name_is_classified():
    # Key NAMES only (values never read into the test): every .env.local name that looks
    # like a secret must be stripped by the barrier if it ever appears in os.environ.
    secret_like = __import__("re").compile(r"(KEY|TOKEN|SECRET|PASSWORD|_ID)$")
    names = sorted(lsb._ENV_FILE_KEYS)
    missed = [n for n in names if secret_like.search(n) and not lsb.is_external_credential_name(n)
              and not n.startswith(("CLICKUP_TASK_LIST", "YOUTUBE_CHANNEL"))]
    assert missed == [], missed



# ======================================================================= ADDENDUM
def test_allowlist_rejects_wildcards_and_any_port():
    for host, port in (("*", 80), ("", 80), ("0.0.0.0", 80), ("::", 80), ("127.0.0.1", 0),
                       ("127.0.0.1", "8188"), ("127.0.0.1", True), ("127.0.0.*", 80), ("localhost-any", 1)):
        with pytest.raises(ValueError):
            with lsb.allow_network(host, port):
                pass
    assert lsb.allowed_destinations() == set()
    assert lsb.ALLOWLIST_SCOPE == "PER_TEST_EXACT_HOST_PORT"


def test_allowlist_leak_count_zero():
    assert lsb.ALLOWLIST_LEAKS == []
    assert lsb.allowed_destinations() == set()


def test_subprocess_popen_check_call_getoutput_git_push_blocked():
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.SubprocessBlocked):
            subprocess.Popen(["git", "push", "origin", "HEAD"])
        with pytest.raises(lsb.SubprocessBlocked):
            subprocess.check_call(["git", "push"])
        with pytest.raises(lsb.SubprocessBlocked):
            subprocess.getoutput("git push origin HEAD")
    assert len(rec) == 3


@pytest.mark.skipif(sys.platform != "win32", reason="_winapi exists on Windows only")
def test_winapi_createprocess_blocked():
    import _winapi
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.SubprocessBlocked):
            _winapi.CreateProcess(None, "git push origin HEAD", None, None, False, 0, None, None, None)
    assert rec and rec[0]["where"] == "_winapi.CreateProcess"


def test_spawned_child_interpreter_env_none_inherits_barrier(tmp_path):
    # multiprocessing 'spawn' children start a fresh interpreter that inherits os.environ,
    # i.e. PYTHONPATH -> tests/_barrier_site/sitecustomize.py and AT_GPU_TEST_BARRIER=1.
    # Effective child env (inherited or explicitly injected if a fixture reset os.environ).
    env = lsb._inherit_env(["python"], None) or os.environ
    assert str(lsb.SITE_DIR) in env["PYTHONPATH"].split(os.pathsep)
    assert env["AT_GPU_TEST_BARRIER"] == "1" and env.get("AT_LIVE_BARRIER_ROOT")
    # A spawned interpreter (what multiprocessing 'spawn' starts) launched with env=None
    # through Popen -> _winapi.CreateProcess has the barrier installed via sitecustomize.
    import subprocess
    code = ("import sys; m=sys.modules.get('tests.live_side_effect_barrier'); "
            "print('CHILD_BARRIER', bool(m and m.INSTALLED))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert "CHILD_BARRIER True" in r.stdout, (r.returncode, r.stderr[-400:])


def test_gitpython_real_remote_object_push_blocked(tmp_path):
    git = pytest.importorskip("git")
    repo = git.Repo.init(tmp_path / "r")          # local temp repo; `git init` outside the live repo
    remote = git.Remote(repo, "origin")            # no `git remote add` needed
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.SubprocessBlocked):
            remote.push()
    assert rec and "push" in rec[0]["where"]


def test_barrier_has_no_hardcoded_user_or_drive_paths():
    src = (REPO / "tests" / "live_side_effect_barrier.py").read_text(encoding="utf-8")
    import re as _re
    assert not _re.search(r"[A-Za-z]:\\\\", src)          # no drive letters
    assert "Documents" not in src and "Users" not in src and "/home/" not in src


def test_live_roots_derived_from_app_defaults():
    d = lsb.app_env_path_defaults()
    assert "CLOUDFLARE_MEDIA_DIR" in d                     # parsed, not hard-coded
    cf = os.path.normcase(os.path.abspath(d["CLOUDFLARE_MEDIA_DIR"]))
    assert cf in lsb.LIVE_WRITE_ROOTS


@pytest.mark.parametrize("flavour", ["posix", "windows"])
def test_redirect_targets_resolve_under_temp_root_simulated(flavour):
    from pathlib import PurePosixPath, PureWindowsPath
    root = PurePosixPath("/tmp/pytest-of-ci/at_live_barrier_x") if flavour == "posix" \
        else PureWindowsPath("C:/Temp/at_live_barrier_x")
    for attr, sub in lsb._ATTR_REDIRECTS.items():
        t = lsb.redirect_target(root, sub)
        assert type(t) is type(root)
        assert root in t.parents, (attr, t)
    for rel in lsb.REPO_OUTPUT_RELS:
        p = (PurePosixPath("/w/repo") if flavour == "posix" else PureWindowsPath("C:/w/repo")).joinpath(*rel.split("/"))
        assert ".." not in p.parts


def test_all_redirected_roots_resolve_under_temp_root():
    import app as app_mod
    tmp = [Path(lsb.TEMP_ROOT).resolve()]
    if os.environ.get("AT_TEST_ISOLATION_ROOT"):
        tmp.append(Path(os.environ["AT_TEST_ISOLATION_ROOT"]).resolve())
    under = lambda p: any(t == Path(p).resolve() or t in Path(p).resolve().parents for t in tmp)
    for a in ("SOCIAL_OUTPUT_DIR", "TIKTOK_OUTPUT_DIR", "CLOUDFLARE_MEDIA_DIR", "PROMO_IMAGES_DIR",
              "TIKTOK_ASSET_DIR", "GENERATED_PROMO_IMAGES_DIR", "GITHUB_MEDIA_REPO_DIR", "OUTPUT_DIR"):
        assert under(getattr(app_mod, a)), (a, getattr(app_mod, a))
    for env in ("CLOUDFLARE_MEDIA_DIR", "PROMO_IMAGES_DIR", "TIKTOK_ASSET_DIR", "GITHUB_MEDIA_REPO_DIR",
                "AIVSB_TELEMETRY_PATH", "IDENTITY_OBSERVABILITY_LOG"):
        assert under(os.environ[env]), env
    from tools import identity_preservation as ip
    assert under(ip.default_log_path())
    import logging, tools.agent_post_writer  # noqa: F401,E401
    files = [h.baseFilename for h in logging.getLogger("automation.agent_post_writer").handlers if hasattr(h, "baseFilename")]
    assert any(under(f) for f in files)
    # buffer-last-payload.json is written at ROOT by production code: refused, never created
    target = REPO / "buffer-last-payload.json"
    with lsb.expect_block() as rec:
        with pytest.raises(lsb.LiveWriteBlocked):
            open(target, "a").close()
    assert rec


def test_flag_values_honored_and_recorded():
    for k in lsb.RECORDED_FLAGS:
        assert not lsb.is_external_credential_name(k)
    from tests import live_side_effect_hooks as hooks
    assert set(hooks._SESSION_FLAGS) == set(lsb.RECORDED_FLAGS)
    for k, v in hooks._SESSION_FLAGS.items():
        assert v == lsb.INSTALL_INFO["flag_state_at_install"][k]


def test_r21_job_monitor_default_log_redirected_under_temp():
    w = pytest.importorskip("tools.structured_scene_location_r21_wiring")
    tgt = Path(w._DEFAULT_MONITOR_LOG).resolve()
    assert Path(lsb.TEMP_ROOT).resolve() in tgt.parents, "R21 monitor log not sandboxed"
