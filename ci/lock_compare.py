"""Lock equivalence check (test infrastructure). Run with the CI venv's python:
    <venv-python> ci/lock_compare.py requirements-ci.txt
Compares normalized name+version of every installed distribution against requirements-ci.txt,
verifies the spaCy model wheel hash separately (dist-info direct_url.json), reports extras.
Exit 1 on any missing locked package, version mismatch, or model-hash mismatch."""
import hashlib, json, platform, re, sys
from importlib import metadata

norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()
lock_path = sys.argv[1] if len(sys.argv) > 1 else "requirements-ci.txt"
raw = open(lock_path, "rb").read()
text = raw.decode("utf-8-sig")
locked, model = {}, None
for line in text.splitlines():
    s = line.strip()
    if not s or s.startswith(("#", "--")):
        continue
    s = s.split(";")[0].rstrip(" \\").strip()
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*(\S+)$", s)
    if m:
        locked[norm(m.group(1))] = m.group(2); continue
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*@\s*(\S+)$", s)
    if m:
        url = m.group(2); name = norm(m.group(1))
        ver = re.search(r"-(\d[^-/]*)-py3", url).group(1)
        h = re.search(r"sha256=([0-9a-f]{64})", url)
        locked[name] = ver; model = (name, url.split("#")[0], h.group(1) if h else None)
installed = {}
for d in metadata.distributions():
    n = norm(d.metadata["Name"] or "")
    if n: installed[n] = d.version
ignore = {"pip"}
missing = sorted(k for k in locked if k not in installed)
mism = sorted(f"{k} lock={locked[k]} installed={installed[k]}" for k in locked if k in installed and locked[k] != installed[k])
extra = sorted(k for k in installed if k not in locked and k not in ignore)
model_ok, model_installed_hash = False, None
if model:
    try:
        du = json.loads(metadata.distribution(model[0]).read_text("direct_url.json") or "{}")
        ai = du.get("archive_info", {})
        model_installed_hash = (ai.get("hashes", {}) or {}).get("sha256") or (ai.get("hash", "").split("=")[-1] or None)
        model_ok = du.get("url", "").split("#")[0] == model[1] and model_installed_hash == model[2]
    except Exception as exc:
        print("SPACY_MODEL_DIRECT_URL_ERROR", type(exc).__name__)
print(f"PYTHON_VERSION={platform.python_version()}")
print(f"PIP_VERSION={metadata.version('pip') if 'pip' in installed else 'NOT_INSTALLED'}")
print(f"LOCKFILE_SHA256={hashlib.sha256(raw).hexdigest()}")
print(f"SPACY_MODEL_WHEEL_SHA256={model[2] if model else 'NONE'} INSTALLED={model_installed_hash} MATCH={'YES' if model_ok else 'NO'}")
print(f"LOCKED={len(locked)} INSTALLED={len(installed)} MISSING={len(missing)} VERSION_MISMATCH={len(mism)} EXTRA={len(extra)}")
for x in missing: print("MISSING", x)
for x in mism: print("MISMATCH", x)
for x in extra: print("EXTRA", x, installed[x])
ok = not missing and not mism and model_ok
print(f"PIP_FREEZE_MATCHES_LOCK={'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
