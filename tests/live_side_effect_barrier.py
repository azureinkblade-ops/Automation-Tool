# -*- coding: utf-8 -*-
"""PYTEST_LIVE_SIDE_EFFECT_ISOLATION - fail-closed live side-effect barrier for pytest.

Installed at IMPORT time of the repo-root conftest.py (and, defensively, at the
top of tests/conftest.py) so it is active BEFORE any test module is imported or
collected.  Controlled by AT_GPU_TEST_BARRIER=1 (the harness sets it; when the
variable is absent we still install, because a test run without the barrier is
never wanted - set AT_LIVE_BARRIER_DISABLE=1 only for emergency debugging and the
install refuses).

Layers (all test-side; no production code is modified):
  1. Network deny-by-default (socket.connect/connect_ex/create_connection/
     getaddrinfo/sendto, socketpair-safe, asyncio loop.create_connection/
     sock_connect/create_datagram_endpoint incl. Proactor, plus a sys.audit hook
     backstop on socket.connect/getaddrinfo/sendto for C-level callers).
     Localhost and ComfyUI (127.0.0.1:8188) are denied too.  Only an exact
     host:port allowed via @pytest.mark.allow_network(host, port) for that one test.
  2. Subprocess barrier (subprocess.Popen, run/call/check_output via Popen,
     os.system, os.popen, os.exec*, os.spawn*, os.posix_spawn*, os.startfile,
     asyncio.create_subprocess_exec/_shell, GitPython Remote.push/pull/fetch):
     git push / remote mutation / network git, all gh except --version, curl/wget
     style shell commands, the local SDXL generator script, and Python children
     that cannot inherit the barrier are refused.  Python children are forced to
     inherit it via PYTHONPATH=<tests/_barrier_site> (sitecustomize) +
     AT_GPU_TEST_BARRIER=1 + stripped credentials.
  3. Credential isolation: external-service keys removed from os.environ;
     reading any .env / .env.local inside the repo is refused (audit hook) and
     app.load_env_file is replaced by a no-op with app.ENV_FILE pointed at a
     non-existent temp path.
  4. Output isolation: production output roots are rebound to a temp root
     (env vars before app import + module attribute patches right after import),
     and a sys.audit write guard refuses any write/mkdir/rename/remove/copy into
     the live output roots.

Every blocked attempt raises LiveSideEffectBlocked AND is recorded (memory + a
JSONL record file shared with barrier-inheriting child processes), and
pytest_sessionfinish fails the session on any unexpected recorded attempt even
if the code under test swallowed the exception.

Pure pathlib/tempfile; no Windows-only paths.  Values of credentials are never
printed, hashed or logged - only key NAMES.
"""
from __future__ import annotations

import builtins
import contextlib
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
SITE_DIR = Path(__file__).resolve().parent / "_barrier_site"

NETWORK_DEFAULT = "DENY"
LOCALHOST_DEFAULT = "DENY"
COMFYUI_ACCESS = "DENY"

INSTALLED = False
INSTALL_INFO: dict[str, Any] = {}
TEMP_ROOT: Path | None = None
RECORD_FILE: Path | None = None
ATTEMPTS: list[dict[str, Any]] = []
STRIPPED_CREDENTIAL_NAMES: list[str] = []
LIVE_WRITE_ROOTS: list[str] = []
_PROTECTED_ENV_FILES: list[str] = []

_tls = threading.local()
_lock = threading.RLock()
_ALLOW: set[tuple[str, int]] = set()   # per-test exact (host, port)
_EXPECT_DEPTH = 0                        # >0 inside expect_block()

_ORIG: dict[str, Any] = {}


class LiveSideEffectBlocked(PermissionError):
    """Raised when test code attempts a live side effect under the barrier."""


class NetworkBlocked(LiveSideEffectBlocked):
    pass


class SubprocessBlocked(LiveSideEffectBlocked):
    pass


class LiveWriteBlocked(LiveSideEffectBlocked):
    pass


class CredentialFileBlocked(LiveSideEffectBlocked):
    pass


# ----------------------------------------------------------------------------- recording
def _reentrant() -> bool:
    return getattr(_tls, "busy", False)


@contextlib.contextmanager
def _busy():
    prev = getattr(_tls, "busy", False)
    _tls.busy = True
    try:
        yield
    finally:
        _tls.busy = prev


def _record(kind: str, dest: str, where: str, **extra: Any) -> dict[str, Any]:
    rec = {
        "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pid": os.getpid(),
        "kind": kind,
        "dest": str(dest)[:400],
        "where": where,
        "test": os.environ.get("PYTEST_CURRENT_TEST", ""),
        "expected": _EXPECT_DEPTH > 0 or bool(getattr(_tls, "expect", 0)),
    }
    rec.update(extra)
    with _busy():
        with _lock:
            ATTEMPTS.append(rec)
            target = RECORD_FILE
            if target is not None:
                try:
                    with _ORIG.get("open", builtins.open)(target, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                except Exception:
                    pass
    return rec


def unexpected_attempts(include_children: bool = True) -> list[dict[str, Any]]:
    seen = [a for a in ATTEMPTS if not a.get("expected")]
    if include_children and RECORD_FILE is not None and RECORD_FILE.exists():
        with _busy():
            for line in RECORD_FILE.read_text(encoding="utf-8").splitlines():
                try:
                    a = json.loads(line)
                except Exception:
                    continue
                if a.get("pid") != os.getpid() and not a.get("expected"):
                    seen.append(a)
    return seen


@contextlib.contextmanager
def expect_block():
    """Mark attempts inside the block as intentional (barrier self-tests)."""
    global _EXPECT_DEPTH
    start = len(ATTEMPTS)
    captured: list[dict[str, Any]] = []
    with _lock:
        _EXPECT_DEPTH += 1
    try:
        yield captured
    finally:
        with _lock:
            _EXPECT_DEPTH -= 1
        captured.extend(ATTEMPTS[start:])


@contextlib.contextmanager
def allow_network(host: str, port: int):
    """Exact host:port allowance; used by the allow_network marker fixture."""
    validate_allow_entry(host, port)
    key = (str(host), int(port))
    with _lock:
        _ALLOW.add(key)
    try:
        yield
    finally:
        with _lock:
            _ALLOW.discard(key)


ALLOWLIST_SCOPE = "PER_TEST_EXACT_HOST_PORT"
_WILDCARD_HOSTS = {"", "*", "0.0.0.0", "::", "[::]", "localhost-any", "any"}


def validate_allow_entry(host: Any, port: Any) -> None:
    """Exact host string + exact port only; no wildcard / any-port / localhost-wide grant."""
    if not isinstance(host, str) or host.strip().lower() in _WILDCARD_HOSTS or any(c in host for c in "*?/ "):
        raise ValueError(f"allow_network: host must be one exact host, got {host!r}")
    if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError(f"allow_network: port must be one exact int 1..65535, got {port!r}")


ALLOWLIST_LEAKS: list[Any] = []


def allowed_destinations() -> set[tuple[str, int]]:
    with _lock:
        return set(_ALLOW)


# ----------------------------------------------------------------------------- network
def _addr_text(address: Any) -> tuple[str, int | None, str]:
    if isinstance(address, tuple) and len(address) >= 2:
        host = address[0]
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        try:
            port = int(address[1])
        except Exception:
            port = None
        return str(host), port, f"{host}:{address[1]}"
    return str(address), None, str(address)


def _is_ipc(family: Any, address: Any) -> bool:
    af_unix = getattr(socket, "AF_UNIX", None)
    if af_unix is not None and family == af_unix:
        return True
    return isinstance(address, (str, bytes)) and not isinstance(address, tuple)


def _classify_dest(host: str, port: int | None) -> str:
    h = (host or "").lower().strip("[]")
    if port == 8188 or "comfy" in h:
        return "comfyui"
    if h in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "::") or h.startswith("127."):
        return "localhost"
    return "external"


def _in_socketpair() -> bool:
    return getattr(_tls, "socketpair", 0) > 0


def _net_check(host: str, port: int | None, where: str, text: str) -> None:
    if _in_socketpair() and _classify_dest(host, port) == "localhost":
        return  # internal loopback of socket.socketpair (asyncio self-pipe on Windows)
    with _lock:
        if port is not None and (host, int(port)) in _ALLOW:
            return
    cls = _classify_dest(host, port)
    _record("network", text, where, category=cls)
    raise NetworkBlocked(
        f"PYTEST_LIVE_SIDE_EFFECT_ISOLATION: network {where} -> {text} blocked "
        f"(category={cls}; NETWORK_DEFAULT=DENY; use @pytest.mark.allow_network(host, port))"
    )


def _patched_connect(self, address, *a, **k):
    if not _is_ipc(getattr(self, "family", None), address):
        host, port, text = _addr_text(address)
        _net_check(host, port, "socket.connect", text)
    with _busy_net():
        return _ORIG["sock_connect"](self, address, *a, **k)


def _patched_connect_ex(self, address, *a, **k):
    if not _is_ipc(getattr(self, "family", None), address):
        host, port, text = _addr_text(address)
        _net_check(host, port, "socket.connect_ex", text)
    with _busy_net():
        return _ORIG["sock_connect_ex"](self, address, *a, **k)


def _patched_sendto(self, data, *args):
    address = args[-1] if args else None
    if address is not None and not _is_ipc(getattr(self, "family", None), address):
        host, port, text = _addr_text(address)
        _net_check(host, port, "socket.sendto", text)
    with _busy_net():
        return _ORIG["sock_sendto"](self, data, *args)


def _patched_create_connection(address, *a, **k):
    host, port, text = _addr_text(address)
    _net_check(host, port, "socket.create_connection", text)
    with _busy_net():
        return _ORIG["create_connection"](address, *a, **k)


def _patched_getaddrinfo(host, port, *a, **k):
    h = host.decode("ascii", "replace") if isinstance(host, bytes) else str(host)
    try:
        p = int(port) if port not in (None, "") else None
    except Exception:
        p = None
    if host is not None:
        _net_check(h, p, "socket.getaddrinfo", f"{h}:{port}")
    with _busy_net():
        return _ORIG["getaddrinfo"](host, port, *a, **k)


def _patched_socketpair(*a, **k):
    _tls.socketpair = getattr(_tls, "socketpair", 0) + 1
    try:
        return _ORIG["socketpair"](*a, **k)
    finally:
        _tls.socketpair -= 1


@contextlib.contextmanager
def _busy_net():
    prev = getattr(_tls, "net_checked", False)
    _tls.net_checked = True
    try:
        yield
    finally:
        _tls.net_checked = prev


def _install_network() -> None:
    S = socket.socket
    _ORIG.setdefault("sock_connect", S.connect)
    _ORIG.setdefault("sock_connect_ex", S.connect_ex)
    _ORIG.setdefault("sock_sendto", S.sendto)
    _ORIG.setdefault("create_connection", socket.create_connection)
    _ORIG.setdefault("getaddrinfo", socket.getaddrinfo)
    _ORIG.setdefault("socketpair", socket.socketpair)
    S.connect = _patched_connect
    S.connect_ex = _patched_connect_ex
    S.sendto = _patched_sendto
    socket.create_connection = _patched_create_connection
    socket.getaddrinfo = _patched_getaddrinfo
    socket.socketpair = _patched_socketpair
    _install_asyncio()


def _install_asyncio() -> None:
    import asyncio
    import asyncio.base_events as be

    def wrap_async(owner, name, addr_of):
        orig = getattr(owner, name, None)
        if orig is None or getattr(orig, "_lsi_wrapped", False):
            return

        async def wrapper(self, *a, **k):
            target = addr_of(a, k)
            if target is not None:
                host, port, text = target
                _net_check(host, port, f"asyncio.{name}", text)
            return await orig(self, *a, **k)

        wrapper._lsi_wrapped = True  # type: ignore[attr-defined]
        setattr(owner, name, wrapper)

    def cc_addr(a, k):
        if k.get("sock") is not None and not a:
            return None
        if k.get("path") is not None:
            return None
        host = a[1] if len(a) > 1 else k.get("host")
        port = a[2] if len(a) > 2 else k.get("port")
        if host is None:
            return None
        try:
            p = int(port) if port is not None else None
        except Exception:
            p = None
        return str(host), p, f"{host}:{port}"

    def sc_addr(a, k):
        address = a[1] if len(a) > 1 else k.get("address")
        sock = a[0] if a else k.get("sock")
        if _is_ipc(getattr(sock, "family", None), address):
            return None
        return _addr_text(address)

    def dg_addr(a, k):
        remote = a[2] if len(a) > 2 else k.get("remote_addr")
        if remote is None:
            return None
        return _addr_text(remote)

    wrap_async(be.BaseEventLoop, "create_connection", cc_addr)
    wrap_async(be.BaseEventLoop, "create_datagram_endpoint", dg_addr)
    wrap_async(be.BaseEventLoop, "sock_connect", sc_addr)
    for modname, clsname in (("asyncio.selector_events", "BaseSelectorEventLoop"),
                             ("asyncio.proactor_events", "BaseProactorEventLoop")):
        try:
            mod = __import__(modname, fromlist=[clsname])
            wrap_async(getattr(mod, clsname), "sock_connect", sc_addr)
        except Exception:
            pass

    for name in ("create_subprocess_exec", "create_subprocess_shell"):
        orig = getattr(asyncio, name)
        if getattr(orig, "_lsi_wrapped", False):
            continue

        def make(orig=orig, name=name):
            async def wrapper(*a, **k):
                if name.endswith("exec"):
                    argv = [str(x) for x in a]
                    _subprocess_check(argv, False, f"asyncio.{name}")
                    k["env"] = _inherit_env(argv, k.get("env"))
                else:
                    _subprocess_check(a[0] if a else k.get("cmd"), True, f"asyncio.{name}")
                return await orig(*a, **k)
            wrapper._lsi_wrapped = True  # type: ignore[attr-defined]
            return wrapper
        setattr(asyncio, name, make())
        try:
            import asyncio.subprocess as asp
            setattr(asp, name, getattr(asyncio, name))
        except Exception:
            pass


# ----------------------------------------------------------------------------- credentials
_CRED_PREFIXES = (
    "BUFFER", "OPENAI", "GOOGLE", "GEMINI", "GITHUB", "GH_", "GITLAB", "ANTHROPIC",
    "AZURE_OPENAI", "AWS_", "HF_", "HUGGING", "ELEVENLABS", "REPLICATE", "STABILITY",
    "CLICKUP", "PATREON", "ROYALROAD", "ROYAL_ROAD", "INSTAGRAM", "FACEBOOK", "META_",
    "TIKTOK", "YOUTUBE", "X_", "TWITTER", "DISCORD", "SLACK", "REDDIT", "TELEGRAM",
    "NOTION", "CLOUDFLARE_API", "CLOUDFLARE_R2", "CLOUDFLARE_ACCOUNT", "CF_API", "R2_",
    "PEXELS", "PIXABAY", "UNSPLASH", "SUPABASE", "FIREBASE", "STRIPE",
    "PAYPAL", "SENDGRID", "MAILGUN", "SMTP", "TWILIO", "PINTEREST", "THREADS",
    "BLUESKY", "LINKEDIN", "XAI", "GROK", "MISTRAL", "COHERE", "DEEPSEEK", "OPENROUTER",
    "SUNO", "RUNWAY", "LUMA", "KLING", "IDEOGRAM", "FAL_", "LEONARDO",
)
_CRED_SUFFIX = re.compile(r"(API_?KEY|TOKEN|SECRET(_KEY)?|PASSWORD|PASSWD|CREDENTIALS?|AUTH|COOKIE|SESSION|PRIVATE_KEY|ACCESS_KEY(_ID)?|SECRET_ACCESS_KEY|CLIENT_ID|ACCOUNT_ID|APP_ID|WEBHOOK(_URL)?)$")
_CRED_KEEP = {"GH_PROMPT_DISABLED"}
_NON_SECRET_SUFFIXES = ("_DIR", "_PATH", "_ROOT", "_FILE", "_LOG")
# Our own non-secret control variables.
_SAFE_PREFIXES = ("AT_", "PYTEST", "PYTHON", "R3_", "RQ2_")


def is_external_credential_name(name: str) -> bool:
    n = name.upper()
    if n in _CRED_KEEP or n.startswith(_SAFE_PREFIXES):
        return False
    if n.startswith(_CRED_PREFIXES):
        # service-prefixed *configuration paths* (e.g. TIKTOK_ASSET_DIR) are not secrets
        return not n.endswith(_NON_SECRET_SUFFIXES)
    return bool(_CRED_SUFFIX.search(n))


def _env_file_key_names() -> list[str]:
    """Key NAMES only from repo .env/.env.local (values are never kept or printed)."""
    names: list[str] = []
    for fname in (".env.local", ".env"):
        p = REPO / fname
        if not p.is_file():
            continue
        try:
            with _ORIG.get("open", builtins.open)(p, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    key = s.split("=", 1)[0].strip()
                    if key.startswith("export "):
                        key = key[7:].strip()
                    if key:
                        names.append(key)
                    # `line`, `s` go out of scope; the value is never stored
        except Exception:
            pass
    return names


_ENV_FILE_KEYS: set[str] = set()


def strip_credentials(env: dict[str, str] | Any) -> list[str]:
    removed = []
    for k in list(env.keys()):
        if is_external_credential_name(k):
            removed.append(k)
            try:
                del env[k]
            except Exception:
                pass
    return removed


def external_credential_names(env: Any = None) -> list[str]:
    env = os.environ if env is None else env
    return sorted(k for k in env.keys() if is_external_credential_name(k))


# ----------------------------------------------------------------------------- subprocess
_GIT_NETWORK_OR_REMOTE = {"push", "send-pack", "fetch", "pull", "clone", "ls-remote",
                          "remote-http", "remote-https", "request-pull", "submodule",
                          "lfs", "credential", "credential-manager", "svn", "p4", "archive"}
_GIT_REMOTE_READONLY = {"", "-v", "--verbose", "get-url"}
_GIT_LIVE_REPO_MUTATING = {"commit", "stash", "reset", "checkout", "switch", "clean", "rebase",
                           "merge", "tag", "am", "apply", "cherry-pick", "revert", "rm", "mv",
                           "restore", "gc", "prune", "branch", "worktree", "config", "init",
                           "add", "notes", "update-ref", "filter-branch", "replace"}
_GH_ALLOWED = {"--version", "version", "--help", "help"}
_GENERATOR_TOKENS = ("local_image_generator", "sdxl_generate", "generate_image.py",
                     "comfyui", "comfy_ui", "stable-diffusion", "stable_diffusion", "main.py --listen")
_SHELL_NET_TOKENS = ("curl", "wget", "invoke-webrequest", "invoke-restmethod", "iwr ", "irm ",
                     "start-bitstransfer", "net.webclient", "httpclient", "ssh ", "scp ", "sftp ",
                     "rsync ", "ftp ", "nc ", "ncat ", "telnet ")


def _argv_of(args: Any) -> list[str]:
    if isinstance(args, (str, bytes, os.PathLike)):
        s = os.fsdecode(args) if not isinstance(args, str) else args
        try:
            return shlex.split(s, posix=(os.name != "nt"))
        except ValueError:
            return s.split()
    try:
        return [os.fsdecode(x) if isinstance(x, (bytes, os.PathLike)) else str(x) for x in args]
    except TypeError:
        return [str(args)]


def _base(exe: str) -> str:
    name = Path(exe.strip('"').strip("'")).name.lower()
    for ext in (".exe", ".cmd", ".bat", ".com"):
        if name.endswith(ext):
            name = name[: -len(ext)]
    return name


def _is_python(exe: str) -> bool:
    b = _base(exe)
    if b in ("py", "pythonw") or re.fullmatch(r"python(\d+(\.\d+)?)?[tw]?", b):
        return True
    try:
        return Path(exe).resolve() == Path(sys.executable).resolve()
    except Exception:
        return False


def _git_target_is_live_repo(argv: list[str], cwd: Any) -> bool:
    target = None
    i = 1
    while i < len(argv):
        if argv[i] == "-C" and i + 1 < len(argv):
            target = argv[i + 1]
            i += 2
            continue
        i += 1
    base = Path(target) if target else Path(os.fspath(cwd)) if cwd else Path.cwd()
    try:
        base = base.resolve()
        repo = REPO.resolve()
        return base == repo or repo in base.parents
    except Exception:
        return True


def _git_subcommand(argv: list[str]) -> tuple[str, list[str]]:
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path") and i + 1 < len(argv):
            i += 2
            continue
        if a.startswith("-"):
            if a in ("--version", "--help"):
                return a, argv[i + 1:]
            i += 1
            continue
        return a, argv[i + 1:]
    return "", []


def classify_command(argv: list[str], cwd: Any = None) -> str | None:
    """Return a refusal reason, or None if the command may run."""
    if not argv:
        return None
    exe = _base(argv[0])
    joined = " ".join(argv).lower().replace("\\", "/")
    if any(t in joined for t in _GENERATOR_TOKENS):
        return "local image generator / ComfyUI process"
    if exe in ("git", "git-receive-pack", "git-upload-pack", "git-remote-http", "git-remote-https"):
        sub, rest = _git_subcommand(argv)
        if exe != "git" or sub in _GIT_NETWORK_OR_REMOTE:
            return f"git {sub or exe} (remote/network git)"
        if sub == "remote":
            action = rest[0] if rest else ""
            if action not in _GIT_REMOTE_READONLY:
                return f"git remote {action} (remote mutation/network)"
        if sub in _GIT_LIVE_REPO_MUTATING and _git_target_is_live_repo(argv, cwd):
            if not (sub == "branch" and (not rest or rest[0] in ("--show-current", "-a", "-r", "--list", "-v", "-vv"))) \
               and not (sub == "config" and rest and rest[0] in ("--get", "--list", "-l", "--get-all", "--get-regexp")):
                return f"git {sub} against the live repo"
        return None
    if exe == "gh":
        sub = argv[1] if len(argv) > 1 else ""
        if sub in _GH_ALLOWED:
            return None
        return f"gh {sub} (GitHub CLI; remote API/mutation)"
    if exe in ("hub", "glab", "curl", "wget", "ssh", "scp", "sftp", "rsync", "ftp", "nc", "ncat", "telnet", "aria2c"):
        return f"{exe} (network client)"
    if exe in ("sh", "bash", "zsh", "dash", "cmd", "powershell", "pwsh", "wsl"):
        low = " " + joined + " "
        if re.search(r"(^|[\s;&|(\"'])git(\.exe)?\s+(push|send-pack|fetch|pull|clone|ls-remote|remote\s+(add|set-url|remove|rm|rename|set-head|set-branches|prune|update|show))\b", low):
            return "shell -> git remote/network"
        if re.search(r"(^|[\s;&|(\"'])gh(\.exe)?\s+(?!--version|version|help)\S+", low):
            return "shell -> gh"
        if any(t in low for t in _SHELL_NET_TOKENS):
            return "shell -> network client"
        if re.search(r"https?://", low):
            return "shell command with URL"
        # shell launching python cannot be forced to inherit the barrier when env is
        # explicitly scrubbed; os.environ already carries the barrier PYTHONPATH.
    if exe == "node" or exe == "npx" or exe == "npm":
        if any(t in joined for t in ("http://", "https://", "publish", "playwright")):
            return f"{exe} with network/browser automation"
    return None


def _child_python_flags_bypass(argv: list[str]) -> bool:
    for a in argv[1:]:
        if not a.startswith("-") or a == "-":
            break
        if a in ("-I", "-E", "-S") or (re.fullmatch(r"-[A-Za-z]+", a) and any(c in a[1:] for c in "IES")):
            return True
        if a in ("-c", "-m"):
            break
    return False


def _subprocess_check(args: Any, shell: bool, where: str, cwd: Any = None) -> list[str]:
    argv = _argv_of(args)
    reason = classify_command(argv, cwd)
    if reason is None and argv and _is_python(argv[0]) and _child_python_flags_bypass(argv):
        reason = "python child with -I/-E/-S cannot inherit the barrier"
    if reason:
        text = " ".join(argv)[:300]
        _record("subprocess", text, where, reason=reason)
        raise SubprocessBlocked(f"PYTEST_LIVE_SIDE_EFFECT_ISOLATION: {where} refused: {reason}: {text!r}")
    return argv


def barrier_child_env(base: Any = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    strip_credentials(env)
    env["AT_GPU_TEST_BARRIER"] = "1"
    env["AT_LIVE_BARRIER_CHILD"] = "1"
    env["AT_SD_ENABLED"] = "0"
    env["LOCAL_SD_ENABLED"] = "0"
    env["CUDA_VISIBLE_DEVICES"] = "-1"
    if TEMP_ROOT is not None:
        env["AT_LIVE_BARRIER_ROOT"] = str(TEMP_ROOT)
    if RECORD_FILE is not None:
        env.setdefault("AT_LIVE_BARRIER_RECORD", str(RECORD_FILE))
    pp = env.get("PYTHONPATH", "")
    parts = [p for p in pp.split(os.pathsep) if p]
    if str(SITE_DIR) not in parts:
        parts.insert(0, str(SITE_DIR))
    if str(REPO) not in parts:
        parts.append(str(REPO))
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env.pop("PYTHONNOUSERSITE", None)
    return env


def _inherit_env(argv: list[str], env: Any) -> Any:
    if env is None:
        if _environ_carries_barrier():
            return None  # inherits os.environ, which already carries the barrier
        return barrier_child_env()  # os.environ was reset by a fixture: inject explicitly
    return barrier_child_env(env)


def _environ_carries_barrier() -> bool:
    parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    return (str(SITE_DIR) in parts and os.environ.get("AT_GPU_TEST_BARRIER") == "1"
            and bool(os.environ.get("AT_LIVE_BARRIER_ROOT")))


def _patched_popen_init(self, args, *a, **k):
    shell = bool(k.get("shell", False))
    cwd = k.get("cwd")
    argv = _subprocess_check(args, shell, "subprocess.Popen", cwd)
    if len(a) < 10:  # env (10th positional) not passed positionally
        k["env"] = _inherit_env(argv, k.get("env"))
    return _ORIG["popen_init"](self, args, *a, **k)


def _wrap_os(name: str, kind: str):
    orig = getattr(os, name, None)
    if orig is None or getattr(orig, "_lsi_wrapped", False):
        return
    _ORIG["os." + name] = orig

    def wrapper(*a, **k):
        if kind == "cmd":
            _subprocess_check(a[0] if a else k.get("command", ""), True, f"os.{name}")
            return orig(*a, **k)
        if kind == "startfile":
            target = os.fspath(a[0]) if a else ""
            _record("subprocess", target, "os.startfile", reason="os.startfile")
            raise SubprocessBlocked(f"PYTEST_LIVE_SIDE_EFFECT_ISOLATION: os.startfile refused: {target!r}")
        # exec*/spawn*/posix_spawn*: recover (path, argv)
        args = list(a)
        if name.startswith("posix_spawn"):
            path, argv = args[0], list(args[1]) if len(args) > 1 else []
        else:
            if name.startswith("spawn"):
                args = args[1:]  # drop mode
            suffix = name[5:] if name.startswith("spawn") else name[4:]
            path = args[0] if args else ""
            if "v" in suffix:
                argv = list(args[1]) if len(args) > 1 else []
            else:
                argv = list(args[1:-1] if "e" in suffix else args[1:])
        argv = [os.fsdecode(path)] + [os.fsdecode(x) if isinstance(x, (bytes, os.PathLike)) else str(x) for x in argv[1:]]
        _subprocess_check(argv, False, f"os.{name}")
        return orig(*a, **k)

    wrapper._lsi_wrapped = True  # type: ignore[attr-defined]
    setattr(os, name, wrapper)


def _install_winapi() -> None:
    try:
        import _winapi  # Windows only
    except ImportError:
        return
    orig = getattr(_winapi, "CreateProcess", None)
    if orig is None or getattr(orig, "_lsi_wrapped", False):
        return
    _ORIG["_winapi.CreateProcess"] = orig

    def wrapper(app_name, cmd_line, *a, **k):
        text = cmd_line if isinstance(cmd_line, str) else (app_name or "")
        argv = _argv_of(text or "")
        if argv and app_name and not cmd_line:
            argv = [app_name]
        # CreateProcess(app, cmd, proc_attrs, thread_attrs, inherit, flags, env, cwd, startup)
        cwd = a[5] if len(a) > 5 else k.get("current_directory")
        reason = classify_command(argv, cwd)
        if reason is None and argv and _is_python(argv[0]) and _child_python_flags_bypass(argv):
            reason = "python child with -I/-E/-S cannot inherit the barrier"
        if reason:
            _record("subprocess", str(text)[:300], "_winapi.CreateProcess", reason=reason)
            raise SubprocessBlocked(f"PYTEST_LIVE_SIDE_EFFECT_ISOLATION: _winapi.CreateProcess refused: {reason}")
        if len(a) > 4 and a[4] is None and not _environ_carries_barrier():
            a = list(a)
            a[4] = barrier_child_env()  # direct callers (multiprocessing spawn) inherit too
        return orig(app_name, cmd_line, *a, **k)

    wrapper._lsi_wrapped = True  # type: ignore[attr-defined]
    _winapi.CreateProcess = wrapper


def _install_subprocess() -> None:
    _ORIG.setdefault("popen_init", subprocess.Popen.__init__)
    subprocess.Popen.__init__ = _patched_popen_init  # type: ignore[method-assign]
    # run/call/check_call/check_output/getoutput all funnel through Popen.__init__.
    for n in ("system",):
        _wrap_os(n, "cmd")
    # os.popen -> subprocess.Popen(shell=True): covered, but wrap to record the call site.
    _wrap_os("popen", "cmd")
    if hasattr(os, "startfile"):
        _wrap_os("startfile", "startfile")
    for n in dir(os):
        if re.fullmatch(r"exec(l|le|lp|lpe|v|ve|vp|vpe)|spawn(l|le|lp|lpe|v|ve|vp|vpe)|posix_spawnp?", n):
            _wrap_os(n, "exec")
    _install_winapi()
    _install_gitpython()


def _install_gitpython() -> None:
    import importlib.util
    try:
        if importlib.util.find_spec("git") is None:
            return
    except Exception:
        return
    try:
        import git  # GitPython (spawns `git version` - allowed)
        from git import remote as _r
    except Exception:
        return
    for meth in ("push", "pull", "fetch"):
        orig = getattr(_r.Remote, meth, None)
        if orig is None or getattr(orig, "_lsi_wrapped", False):
            continue

        def make(meth=meth):
            def wrapper(self, *a, **k):
                try:
                    rname = object.__getattribute__(self, "name")
                except Exception:
                    rname = "?"
                text = f"GitPython Remote.{meth} {rname}"
                _record("subprocess", text, f"git.Remote.{meth}", reason="GitPython remote op")
                raise SubprocessBlocked(f"PYTEST_LIVE_SIDE_EFFECT_ISOLATION: {text} refused")
            wrapper._lsi_wrapped = True  # type: ignore[attr-defined]
            return wrapper
        setattr(_r.Remote, meth, make())


# ----------------------------------------------------------------------------- outputs / audit
def _norm(p: Any) -> str | None:
    if isinstance(p, int):
        return None
    try:
        s = os.fsdecode(p)
    except Exception:
        return None
    try:
        return os.path.normcase(os.path.abspath(s))
    except Exception:
        return None


LIVE_WRITE_FILES: list[str] = []


EVIDENCE_DIRS: list[str] = []


def _under_live_root(path: str) -> str | None:
    for e in EVIDENCE_DIRS:  # harness evidence folder (reports/junit) - explicit, opt-in
        if path == e or path.startswith(e + os.sep):
            return None
    if path in LIVE_WRITE_FILES:
        return path
    for r in LIVE_WRITE_ROOTS:
        if path == r or path.startswith(r + os.sep):
            return r
    return None


def _open_is_write(mode: Any, flags: Any) -> bool:
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    if isinstance(flags, int):
        return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))
    return False


_WRITE_EVENTS_1 = {"os.mkdir", "os.remove", "os.rmdir", "os.truncate", "os.chmod", "os.utime",
                   "shutil.rmtree", "os.chown", "os.removexattr", "os.setxattr", "shutil.make_archive"}
_WRITE_EVENTS_2 = {"os.rename", "shutil.copyfile", "shutil.copytree", "shutil.move", "os.link", "os.symlink"}


# ------------------------------------------------------------ private Inkblade sibling data
# The Inkblade Author Studio tree (Studio Bible profiles/locations, AIVSB reasoning package) is
# private and absent in CI. Every access is counted; AT_INKBLADE_SIMULATE_ABSENT=1 makes it behave
# as missing (FileNotFoundError) without moving or renaming the real folder.
INKBLADE_MARKER = "inkblade author studio"
INKBLADE_ACCESSES: list[dict] = []
_INKBLADE_EVENTS = ("open", "os.listdir", "os.scandir")


def inkblade_simulated_absent() -> bool:
    return os.environ.get("AT_INKBLADE_SIMULATE_ABSENT", "") == "1"


def _inkblade_check(event: str, args: tuple) -> None:
    if event not in _INKBLADE_EVENTS or not args:
        return
    a = args[0]
    if isinstance(a, int) or a is None:
        return
    try:
        p = os.fsdecode(a) if not isinstance(a, str) else a
    except Exception:
        return
    if INKBLADE_MARKER not in p.replace("\\", "/").lower():
        return
    absent = inkblade_simulated_absent()
    INKBLADE_ACCESSES.append({"event": event, "path_tail": "/".join(Path(p).parts[-3:]),
                              "test": os.environ.get("PYTEST_CURRENT_TEST", ""), "simulated_absent": absent})
    if absent:
        raise FileNotFoundError(2, "simulated absent private Inkblade data (AT_INKBLADE_SIMULATE_ABSENT=1)", p)


def _is_inkblade_path(a) -> bool:
    if isinstance(a, int) or a is None:
        return False
    try:
        p = os.fsdecode(a) if not isinstance(a, (str, os.PathLike)) else os.fspath(a)
        return INKBLADE_MARKER in str(p).replace("\\", "/").lower()
    except Exception:
        return False


def _install_inkblade_absence() -> None:
    """AT_INKBLADE_SIMULATE_ABSENT=1: make every Inkblade path look missing to stat/exists/isdir
    (os.stat is not an audit event, and Windows' os.path.exists/isdir are C fast paths), so the
    simulation matches a machine where the folder does not exist. Nothing on disk is touched."""
    import ntpath, posixpath
    real_stat, real_lstat = os.stat, os.lstat

    def _gone(p):
        INKBLADE_ACCESSES.append({"event": "os.stat", "path_tail": "/".join(Path(os.fspath(p)).parts[-3:]),
                                  "test": os.environ.get("PYTEST_CURRENT_TEST", ""), "simulated_absent": True})
        raise FileNotFoundError(2, "simulated absent private Inkblade data (AT_INKBLADE_SIMULATE_ABSENT=1)", os.fspath(p))

    def stat(p, *a, **k):
        if _is_inkblade_path(p):
            _gone(p)
        return real_stat(p, *a, **k)

    def lstat(p, *a, **k):
        if _is_inkblade_path(p):
            _gone(p)
        return real_lstat(p, *a, **k)

    os.stat, os.lstat = stat, lstat
    for mod in (ntpath, posixpath):
        for name in ("exists", "lexists", "isdir", "isfile", "islink"):
            real = getattr(mod, name, None)
            if real is None:
                continue
            def make(real):
                def f(p, *a, **k):
                    if _is_inkblade_path(p):
                        INKBLADE_ACCESSES.append({"event": "os.path." + real.__name__, "path_tail": "/".join(Path(os.fspath(p)).parts[-3:]),
                                                  "test": os.environ.get("PYTEST_CURRENT_TEST", ""), "simulated_absent": True})
                        return False
                    return real(p, *a, **k)
                return f
            setattr(mod, name, make(real))
    INSTALL_INFO["inkblade_simulated_absent"] = True


def _audit(event: str, args: tuple) -> None:
    if not INSTALLED or _reentrant():
        return
    _inkblade_check(event, args)
    try:
        if event == "socket.connect":
            if getattr(_tls, "net_checked", False):
                return
            sock, address = args[0], args[1]
            if not _is_ipc(getattr(sock, "family", None), address):
                host, port, text = _addr_text(address)
                _net_check(host, port, "audit:socket.connect", text)
            return
        if event == "socket.getaddrinfo":
            if getattr(_tls, "net_checked", False):
                return
            host, port = args[0], args[1]
            if host is not None:
                h = host.decode("ascii", "replace") if isinstance(host, bytes) else str(host)
                try:
                    p = int(port) if port not in (None, "") else None
                except Exception:
                    p = None
                _net_check(h, p, "audit:socket.getaddrinfo", f"{h}:{port}")
            return
        if event == "socket.sendto":
            if getattr(_tls, "net_checked", False):
                return
            sock, address = args[0], args[1]
            if not _is_ipc(getattr(sock, "family", None), address):
                host, port, text = _addr_text(address)
                _net_check(host, port, "audit:socket.sendto", text)
            return
        if event == "open":
            path = _norm(args[0])
            if path is None:
                return
            if path in _PROTECTED_ENV_FILES:
                _record("credential_file", Path(path).name, "audit:open")
                raise CredentialFileBlocked(
                    f"PYTEST_LIVE_SIDE_EFFECT_ISOLATION: reading {Path(path).name} is refused under the barrier")
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else None
            if _open_is_write(mode, flags):
                root = _under_live_root(path)
                if root:
                    _record("live_write", path, "audit:open", root=root)
                    raise LiveWriteBlocked(f"PYTEST_LIVE_SIDE_EFFECT_ISOLATION: live output write refused: {path}")
            return
        if event in _WRITE_EVENTS_1 or event in _WRITE_EVENTS_2:
            cands = [args[0]] if event in _WRITE_EVENTS_1 else [args[1]] if event in ("shutil.copyfile", "shutil.copytree", "os.link", "os.symlink") else [args[0], args[1]]
            for c in cands:
                path = _norm(c)
                if path and _under_live_root(path):
                    _record("live_write", path, f"audit:{event}")
                    raise LiveWriteBlocked(f"PYTEST_LIVE_SIDE_EFFECT_ISOLATION: live output {event} refused: {path}")
    except LiveSideEffectBlocked:
        raise
    except Exception:
        return


_ENV_DEFAULT_RE = re.compile(
    r'^(?P<name>[A-Z_]+)\s*=\s*Path\(os\.environ\.get\(\s*"(?P<env>[A-Z_]+)"\s*,\s*r?"(?P<default>[^"]+)"\s*\)\)', re.M)
_OUTPUT_ENV_ROOTS = ("CLOUDFLARE_MEDIA_DIR", "PROMO_IMAGES_DIR", "TIKTOK_ASSET_DIR", "GITHUB_MEDIA_REPO_DIR")


def app_env_path_defaults() -> dict[str, str]:
    """Literal path defaults that app.py binds from os.environ.get(NAME, default) at import.

    Read from the app source text (never imported here) so the barrier carries no
    hard-coded user path or platform separator of its own.
    """
    out: dict[str, str] = {}
    src = REPO / "app.py"
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for m in _ENV_DEFAULT_RE.finditer(text):
        out[m.group("env")] = m.group("default")
    # Fallback literals on the same binding lines, e.g. PROMO_IMAGES_DIR's Path(r"...") branch.
    for line in text.splitlines():
        head = line.split("=", 1)[0].strip()
        if head in _OUTPUT_ENV_ROOTS:
            for i, lit in enumerate(re.findall(r'Path\(r?"([^"]+)"\)', line)):
                out.setdefault(f"{head}#literal{i}", lit)
    return out


def _compute_live_roots() -> list[Path]:
    defaults = app_env_path_defaults()
    roots: list[Path] = []
    for env in _OUTPUT_ENV_ROOTS:
        for val in (os.environ.get(env), defaults.get(env)):
            if val:
                roots.append(Path(val))
    for key, val in defaults.items():
        if "#literal" in key:
            roots.append(Path(val))
    tele = os.environ.get("AIVSB_TELEMETRY_PATH")
    if tele and not os.environ.get("AT_LIVE_BARRIER_CHILD"):
        roots.append(Path(tele).parent)
    for rel in REPO_OUTPUT_RELS:
        roots.append(REPO.joinpath(*rel.split("/")))
    return roots


REPO_OUTPUT_RELS = ("output", "logs", "social-posts", "tiktok-posts", "campaigns", "youtube-videos",
                    "story-hook-videos", "manual-video-packs", "manual-video-image-bank",
                    "experiment-post-packs", "docs/media", "pinned-profile-assets-output", "image-lab",
                    ".automation-media-repo")


def redirect_target(temp_root: Any, sub: str) -> Any:
    """Pure-path join (works for PurePosixPath and PureWindowsPath alike)."""
    return temp_root.joinpath("outputs", *sub.split("/"))


# Production module attributes rebound to the temp root right after import.
_ATTR_REDIRECTS = {
    "SOCIAL_OUTPUT_DIR": "social-posts", "TIKTOK_OUTPUT_DIR": "tiktok-posts",
    "OUTPUT_DIR": "campaigns", "YOUTUBE_OUTPUT_DIR": "youtube-videos",
    "STORY_HOOK_OUTPUT_DIR": "story-hook-videos", "MANUAL_VIDEO_OUTPUT_DIR": "manual-video-packs",
    "MANUAL_VIDEO_IMAGE_BANK_DIR": "manual-video-image-bank",
    "EXPERIMENT_OUTPUT_DIR": "experiment-post-packs", "GITHUB_MEDIA_DIR": "docs/media",
    "PINNED_ASSET_OUTPUT_DIR": "pinned-profile-assets-output", "IMAGE_LAB_DIR": "image-lab",
    "CLOUDFLARE_MEDIA_DIR": "CloudFlare", "PROMO_IMAGES_DIR": "CloudFlare",
    "GENERATED_PROMO_IMAGES_DIR": "CloudFlare/Generated", "TIKTOK_ASSET_DIR": "CloudFlare",
    "GITHUB_MEDIA_REPO_DIR": "automation-media-repo",
}
# Module-level str/Path default log paths under <repo>/logs that are read lazily at call
# time (env override unset because R21_* env vars are cleared for test runs).
_STR_ATTR_REDIRECTS = {
    "tools.structured_scene_location_r21_wiring": {"_DEFAULT_MONITOR_LOG": "logs/r21/r21_job_monitoring.jsonl"},
    "structured_scene_location_r21_wiring": {"_DEFAULT_MONITOR_LOG": "logs/r21/r21_job_monitoring.jsonl"},
}
_REDIRECT_MODULES = ("app_config", "app", "buffer_publish", "browser_publish", "promo_builder") + tuple(_STR_ATTR_REDIRECTS)


# Production modules that open a FileHandler under <repo>/logs at IMPORT time only when
# their logger has no handler yet; pre-attaching a temp-root handler makes them skip it.
_IMPORT_TIME_LOGGERS = {"automation.agent_post_writer": "agent_post_writer.log"}


def _preattach_module_log_handlers() -> None:
    import logging
    for name, fname in _IMPORT_TIME_LOGGERS.items():
        lg = logging.getLogger(name)
        if not lg.handlers and TEMP_ROOT is not None:
            h = logging.FileHandler(TEMP_ROOT / "logs" / fname, encoding="utf-8", delay=True)
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            lg.addHandler(h)


def redirect_module(mod: Any) -> list[str]:
    done = []
    if TEMP_ROOT is None or mod is None:
        return done
    out = TEMP_ROOT / "outputs"
    for attr, sub in _ATTR_REDIRECTS.items():
        if hasattr(mod, attr):
            cur = getattr(mod, attr)
            if isinstance(cur, Path):
                try:
                    if out in cur.resolve().parents or cur.resolve() == out:
                        continue  # already sandboxed
                except Exception:
                    pass
                # keep tests/conftest.py's own at_iso sandbox if it already rebound it
                if "at_iso_" in str(cur):
                    continue
                target = redirect_target(TEMP_ROOT, sub)
                target.mkdir(parents=True, exist_ok=True)
                setattr(mod, attr, target)
                done.append(attr)
    for attr, rel in _STR_ATTR_REDIRECTS.get(getattr(mod, "__name__", ""), {}).items():
        if hasattr(mod, attr):
            target = TEMP_ROOT.joinpath(*rel.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            cur = getattr(mod, attr)
            setattr(mod, attr, str(target) if isinstance(cur, str) else target)
            done.append(attr)
    if getattr(mod, "__name__", "") == "app":
        if hasattr(mod, "ENV_FILE"):
            mod.ENV_FILE = TEMP_ROOT / "no-env-file" / ".env.local"   # does not exist
        if hasattr(mod, "load_env_file") and not getattr(mod.load_env_file, "_lsi_wrapped", False):
            def _no_env_file() -> None:
                return None
            _no_env_file._lsi_wrapped = True  # type: ignore[attr-defined]
            mod.load_env_file = _no_env_file
            done.append("load_env_file")
    return done


class _RedirectFinder:
    """meta_path hook: rebind production output attributes right after import."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _REDIRECT_MODULES or getattr(_tls, "finding", False):
            return None
        _tls.finding = True
        try:
            import importlib.util
            spec = importlib.util.find_spec(fullname)
        finally:
            _tls.finding = False
        if spec is None or spec.loader is None:
            return None
        loader = spec.loader
        orig_exec = loader.exec_module

        class _L:
            def __getattr__(self, n):
                return getattr(loader, n)

            def create_module(self, s):
                return loader.create_module(s)

            def exec_module(self, module):
                orig_exec(module)
                redirect_module(module)
        spec.loader = _L()
        return spec


def redirect_loaded_modules() -> dict[str, list[str]]:
    res = {}
    for name in _REDIRECT_MODULES:
        m = sys.modules.get(name)
        if m is not None:
            res[name] = redirect_module(m)
    return res


# ----------------------------------------------------------------------------- install
def install(*, child: bool = False) -> dict[str, Any]:
    global INSTALLED, TEMP_ROOT, RECORD_FILE, LIVE_WRITE_ROOTS, _PROTECTED_ENV_FILES
    if INSTALLED:
        return INSTALL_INFO
    if os.environ.get("AT_LIVE_BARRIER_DISABLE") == "1":
        raise SystemExit("AT_LIVE_BARRIER_DISABLE=1 refused: PYTEST_LIVE_SIDE_EFFECT_ISOLATION is mandatory")
    _ORIG.setdefault("open", builtins.open)
    premods = sorted(m for m in sys.modules if m == "app" or m.startswith("tests.test_") or m.startswith("test_"))
    os.environ["AT_GPU_TEST_BARRIER"] = "1"
    os.environ["AT_SD_ENABLED"] = "0"
    os.environ["LOCAL_SD_ENABLED"] = "0"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    for k in [k for k in os.environ if k.upper().startswith("R21_")]:
        del os.environ[k]

    inherited_roots = os.environ.get("AT_LIVE_BARRIER_LIVE_ROOTS") if child else None
    if inherited_roots:
        LIVE_WRITE_ROOTS = sorted({r for r in inherited_roots.split(os.pathsep) if r})
    else:
        LIVE_WRITE_ROOTS = sorted({os.path.normcase(os.path.abspath(str(p))) for p in _compute_live_roots()})
    os.environ["AT_LIVE_BARRIER_LIVE_ROOTS"] = os.pathsep.join(LIVE_WRITE_ROOTS)
    ev = os.environ.get("AT_LIVE_BARRIER_EVIDENCE_DIR", "").strip()
    EVIDENCE_DIRS[:] = [os.path.normcase(os.path.abspath(ev))] if ev else []
    LIVE_WRITE_FILES[:] = [os.path.normcase(os.path.abspath(str(REPO / n))) for n in ("buffer-last-payload.json",)]
    _PROTECTED_ENV_FILES = [os.path.normcase(os.path.abspath(str(REPO / n))) for n in (".env.local", ".env")]
    _ENV_FILE_KEYS.update(_env_file_key_names())

    global STRIPPED_CREDENTIAL_NAMES
    STRIPPED_CREDENTIAL_NAMES = sorted(strip_credentials(os.environ))

    existing = os.environ.get("AT_LIVE_BARRIER_ROOT")
    if child and existing:
        TEMP_ROOT = Path(existing)
    else:
        TEMP_ROOT = Path(tempfile.mkdtemp(prefix="at_live_barrier_"))
    out = TEMP_ROOT / "outputs"
    (out / "CloudFlare" / "Generated").mkdir(parents=True, exist_ok=True)
    (TEMP_ROOT / "logs" / "identity_preservation").mkdir(parents=True, exist_ok=True)
    rec_env = os.environ.get("AT_LIVE_BARRIER_RECORD")
    RECORD_FILE = Path(rec_env) if (child and rec_env) else TEMP_ROOT / "barrier_attempts.jsonl"
    os.environ["AT_LIVE_BARRIER_ROOT"] = str(TEMP_ROOT)
    os.environ["AT_LIVE_BARRIER_RECORD"] = str(RECORD_FILE)

    # Production roots that are bound from env at app import -> temp (before app import).
    os.environ["CLOUDFLARE_MEDIA_DIR"] = str(out / "CloudFlare")
    os.environ["PROMO_IMAGES_DIR"] = str(out / "CloudFlare")
    os.environ["TIKTOK_ASSET_DIR"] = str(out / "CloudFlare")
    os.environ["GITHUB_MEDIA_REPO_DIR"] = str(out / "automation-media-repo")
    os.environ["AIVSB_TELEMETRY_PATH"] = str(TEMP_ROOT / "logs" / "aivsb" / "entity_resolution_events.jsonl")
    (TEMP_ROOT / "logs" / "aivsb").mkdir(parents=True, exist_ok=True)
    _preattach_module_log_handlers()
    os.environ["IDENTITY_OBSERVABILITY_LOG"] = str(TEMP_ROOT / "logs" / "identity_preservation" / "identity_observability.jsonl")


    # Child processes inherit the barrier through sitecustomize on PYTHONPATH.
    parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if str(SITE_DIR) not in parts:
        parts.insert(0, str(SITE_DIR))
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)

    _install_network()
    _install_subprocess()
    sys.addaudithook(_audit)
    if inkblade_simulated_absent():
        _install_inkblade_absence()
    if not any(isinstance(f, _RedirectFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _RedirectFinder())
    INSTALLED = True
    redirected = redirect_loaded_modules()
    INSTALL_INFO["flag_state_at_install"] = flag_state()
    INSTALL_INFO.update({
        "installed_at": time.time(),
        "child": child,
        "pid": os.getpid(),
        "test_modules_or_app_imported_before_install": premods,
        "barrier_active_before_test_module_import": not premods,
        "temp_root": str(TEMP_ROOT),
        "stripped_credential_names": STRIPPED_CREDENTIAL_NAMES,
        "redirected_preloaded": redirected,
    })
    return INSTALL_INFO


def _popen_guard_in_chain() -> bool:
    cur = subprocess.Popen.__init__
    if cur is _patched_popen_init:
        return True
    # tests/gpu_test_barrier.py wraps Popen.__init__ after us and delegates to our guard.
    g = sys.modules.get("tests.gpu_test_barrier")
    return bool(g is not None and getattr(g, "_ORIG_POPEN_INIT", None) is _patched_popen_init
                and cur is getattr(g, "_guarded_popen_init", None))


RECORDED_FLAGS = ("ENABLE_IDENTITY_PRESERVATION", "ENABLE_STRUCTURED_SCENE_LOCATION")


def flag_state() -> dict[str, str]:
    """Effective values of the two non-secret feature flags (never stripped)."""
    return {k: os.environ.get(k, "<unset>") for k in RECORDED_FLAGS}


def is_active() -> bool:
    return INSTALLED and socket.socket.connect is _patched_connect and \
        socket.getaddrinfo is _patched_getaddrinfo and _popen_guard_in_chain()
