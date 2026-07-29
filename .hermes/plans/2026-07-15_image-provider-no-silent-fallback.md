# Image Provider No-Silent-Fallback — Implementation Plan

> **For Hermes:** Use `subagent-driven-development` skill to implement task-by-task. Load
> `automation-tool-architecture`, `automation-tool-app`, and `qa-testing-engineer` for every task.

**Goal:** Make the local SDXL (diffusers) image pipeline fail-loud instead of silently falling
back to Pexels/Pixabay stock photos, and lock that behavior in with a regression check so it
can never regress.

**Architecture:** Two-layer change inside the existing single-file `app.py` (surgical, per
`automation-tool-architecture` safe-change boundaries — NO monolith refactor). (1) Add an
explicit opt-in env flag `ALLOW_EXTERNAL_IMAGE_FALLBACK`; when unset (default), the generation
wrapper refuses to substitute a stock provider and returns a structured error instead of a
stock URL. (2) Extend `tools/regression_check.py` with a check that proves the invariant under a
deliberately polluted env. The startup env-guard + `[image-pipeline]` log line committed in
`1feb6db` stay as layer 0; this plan adds layer 1 (generation-time) + a test.

**Tech Stack:** Python stdlib only (app is a hand-rolled `http.server`); `tools/regression_check.py`
(1,312-line existing harness); `pytest`-style assertions via the harness's `assert_result` helper.

---

## Current context / assumptions (verified this session)

- `local_stable_diffusion_status()` uses `find_spec` (file-exists only), so it reports `ready: True`
  even when the real `import diffusers` would crash on a broken PIL from a leaked `PYTHONPATH`.
- The generation wrapper, on `create_local_stable_diffusion_image` raising, **silently** advances
  to Pexels/Pixabay and returns a stock URL as if local. Symptom: published images are stock photos.
- Provider priority already lists `local_stable_diffusion` FIRST (`app.py` ~10124/10169/31539).
- Startup guard committed (`1feb6db`): `tools/server_control.py` pops `PYTHONPATH`/`PYTHONHOME`;
  `app.py` top-of-file scrubs them + logs `[image-pipeline] diffusers local SDXL enabled`.
- `tools/regression_check.py` already has `check_image_provider_trace` (~line 1238) in its CHECKS list.
- App launches with `env -u PYTHONPATH -u PYTHONHOME <codex-python> tools/server_control.py --port 8765 --force`.

## Proposed approach

1. Introduce `ALLOW_EXTERNAL_IMAGE_FALLBACK` (env, default unset = refuse).
2. Wrap provider selection so that when `local_stable_diffusion` is the intended/selected provider
   but generation fails AND the flag is unset, the wrapper returns `{"ok": False, "error": "...",
   "fell_back": False}` — never a stock URL. When the flag IS set, it falls back but logs a loud
   `WARNING ... fell back to external provider` line (observable, not silent).
3. Add `check_image_provider_no_silent_fallback` to `tools/regression_check.py`, registered in CHECKS.
4. Update skill docs (`DIFFUSERS_PYTHONPATH_FIX.md`, `automation-tool-app` SKILL.md pitfall).

---

## Task 1: Locate the generation wrapper + provider-selection code

**Objective:** Map the exact functions to edit so later tasks touch the right lines.

**Files:**
- Read: `app.py` (grep only — `search_files` fails on this 43K-line file; use terminal `grep -nE`)
- Read: `references/DIFFUSERS_PYTHONPATH_FIX.md`

**Step 1: Find the symbols**
Run:
```bash
cd "C:/Users/David/Documents/Automation tool"
grep -nE "def local_stable_diffusion_status|def create_local_stable_diffusion_image|def select_image_provider|def generate_image|ALLOW_EXTERNAL|fell_back|pexels|pixabay" app.py | head -40
```
Expected: line numbers for the status fn, the generator fn, and the fallback/selection sites.

**Step 2: Record findings**
Note the line numbers in the plan or a scratch file. No code change yet.

**Step 5: Commit** — N/A (read-only task).

---

## Task 2: Add the `ALLOW_EXTERNAL_IMAGE_FALLBACK` flag read

**Objective:** Centralise the opt-in so every fallback site checks one source of truth.

**Files:**
- Modify: `app.py` (near the top-of-file env block added in `1feb6db`, ~line 46)

**Step 1: Write failing test**
In `tools/regression_check.py`, add (see Task 5 for full fn):
```python
def check_image_provider_no_silent_fallback() -> list[dict[str, object]]:
    # placeholder; real body in Task 5
    return [assert_result("image_provider_no_silent_fallback", False, "not implemented")]
```
Register it in CHECKS (Task 5). Running the harness now should show this check FAILING (placeholder).

**Step 2: Add the flag constant**
After the env-scrub block in `app.py` (~line 46), add:
```python
# Image-provider fallback policy (layer 1 of the diffusers-protection fix).
# Default False: never silently substitute Pexels/Pixabay for local SDXL.
ALLOW_EXTERNAL_IMAGE_FALLBACK = os.environ.get("ALLOW_EXTERNAL_IMAGE_FALLBACK", "").lower() in (
    "1", "true", "yes", "on",
)
```

**Step 3: Run placeholder test** — see Task 5 (still failing by design until wrapper edits land).

**Step 5: Commit**
```bash
git add app.py
git commit -m "feat(image): add ALLOW_EXTERNAL_IMAGE_FALLBACK policy flag (default refuse)"
```

---

## Task 3: Make the generation wrapper fail-loud

**Objective:** When local SDXL is selected but generation fails and the flag is unset, return a
structured error instead of a stock URL.

**Files:**
- Modify: `app.py` — the function returned by `grep` in Task 1 that calls
  `create_local_stable_diffusion_image` and falls back to Pexels/Pixabay.

**Step 1: Write failing test**
Extend the Task 5 check to monkeypatch `create_local_stable_diffusion_image` to raise, then call
the wrapper and assert the result has `ok == False` and `fell_back == False` and contains no
`pexels.com`/`pixabay.com` URL. (Full body in Task 5.) Run now → FAIL.

**Step 2: Edit the wrapper**
Wrap the local-SDXL attempt:
```python
try:
    result = create_local_stable_diffusion_image(prompt, **kwargs)
    if result and getattr(result, "ok", True):
        return result
except Exception as exc:
    if not ALLOW_EXTERNAL_IMAGE_FALLBACK:
        print(f"[image-pipeline] WARNING local SDXL generation failed and external "
              f"fallback is DISABLED (refusing stock substitution): {exc}", flush=True)
        return {"ok": False, "error": f"local_sdxl_generation_failed:{exc}",
                "fell_back": False, "provider": "local_stable_diffusion"}
    print(f"[image-pipeline] WARNING local SDXL failed, FALLING BACK to external "
          f"provider (ALLOW_EXTERNAL_IMAGE_FALLBACK=1): {exc}", flush=True)
    # ... existing Pexels/Pixabay path, but now loudly logged ...
```

**Step 3: Run test** → PASS (wrapper returns error, no stock URL).

**Step 5: Commit**
```bash
git add app.py
git commit -m "fix(image): refuse silent external fallback when local SDXL fails (fail-loud)"
```

---

## Task 4: Verify the live endpoint still reports local as selected + logs enabled

**Objective:** Confirm the committed startup guard + new policy don't break the happy path.

**Files:**
- Verify only (no edit): `app.py`, `tools/server_control.py`

**Step 1: Launch app clean (background)**
```bash
cd "C:/Users/David/Documents/Automation tool"
env -u PYTHONPATH -u PYTHONHOME "C:/Users/David/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" tools/server_control.py --port 8765 --force --no-open
```
Wait for `netstat -ano | grep ":8765" | grep LISTENING`.

**Step 2: Assert readiness + selected**
```bash
curl -s http://127.0.0.1:8765/api/provider-strategy | python -c "import sys,json;d=json.load(sys.stdin);lsd=(d.get('readiness') or {}).get('local_stable_diffusion') or {};print('ready:',lsd.get('ready'),'selected:',d.get('selectedImageProvider'))"
```
Expected: `ready: True selected: local_stable_diffusion`.

**Step 3: Assert startup log line present** (tail the server's stdout / `logs/automation-server-*.out.log`)
Expected: contains `[image-pipeline] diffusers local SDXL enabled`.

**Step 5: Commit** — N/A (verification only). Leave app running or stop it.

---

## Task 5: Add `check_image_provider_no_silent_fallback` to the regression harness

**Objective:** Permanent regression protection for the invariant (the QA skill: "a defect fixed
without regression protection is likely to return").

**Files:**
- Modify: `tools/regression_check.py` — add fn + register in CHECKS (~line 1238, beside `check_image_provider_trace`).

**Step 1: Write the check (complete)**
```python
def check_image_provider_no_silent_fallback() -> list[dict[str, object]]:
    """Layer-1 invariant: when local SDXL is selected, a generation failure must NOT
    silently return a stock (Pexels/Pixabay) URL. Verified two ways:
      (a) live app under a deliberately polluted PYTHONPATH still reports local ready+selected
          and shows the enabled log line (no WARNING about fallback);
      (b) monkeypatching the local generator to raise yields ok=False/fell_back=False, never a
          pexels/pixabay URL.
    """
    results = []
    codex = os.environ.get("CODEX_PYTHON", "python")
    repo = ROOT

    # (a) live polluted-env launch
    polluted = dict(os.environ)
    polluted["PYTHONPATH"] = r"C:\Users\David\AppData\Local\hermes\hermes-agent;C:\Users\David\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages"
    polluted.pop("PYTHONHOME", None)
    # launch, poll /api/provider-strategy, capture stdout for the enabled line
    # (reuse the launch+wait pattern; assert readiness.local_stable_diffusion.ready is True
    #  and selectedImageProvider == "local_stable_diffusion" and "diffusers local SDXL enabled"
    #  appears in captured stdout, and NO "FALLING BACK" line)
    # (b) import app, monkeypatch create_local_stable_diffusion_image to raise, call the wrapper
    try:
        import importlib
        app = importlib.import_module("app")
        orig = app.create_local_stable_diffusion_image
        app.create_local_stable_diffusion_image = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("injected SDXL failure"))
        out = app.<generation_wrapper>(prompt="test", provider="local_stable_diffusion")
        app.create_local_stable_diffusion_image = orig
        fell_back = bool(out.get("fell_back"))
        has_stock = any(h in str(out.get("url", "")) for h in ("pexels.com", "pixabay.com"))
        results.append(assert_result(
            "image_provider_refuses_silent_fallback",
            (not fell_back) and (not has_stock) and (out.get("ok") is False),
            "wrapper refused stock substitution on local-SDXL failure",
            detail={"ok": out.get("ok"), "fell_back": fell_back, "has_stock": has_stock},
        ))
    except Exception as exc:
        results.append(assert_result("image_provider_refuses_silent_fallback", False,
                                     f"harness error: {exc}"))
    return results
```
Replace `<generation_wrapper>` with the actual symbol from Task 1. Register:
```python
CHECKS = [..., check_image_provider_trace, check_image_provider_no_silent_fallback, ...]
```

**Step 2: Run the harness**
```bash
cd "C:/Users/David/Documents/Automation tool"
env -u PYTHONPATH -u PYTHONHOME "C:/Users/David/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" tools/regression_check.py
```
Expected: `image_provider_no_silent_fallback` PASS; no pre-existing check regresses.

**Step 5: Commit**
```bash
git add tools/regression_check.py
git commit -m "test(image): add regression check for no-silent-external-fallback invariant"
```

---

## Task 6: Update skill docs

**Objective:** Record the layer-1 fix + flag so the next session doesn't re-root-cause it.

**Files:**
- Modify: `references/DIFFUSERS_PYTHONPATH_FIX.md` (add the generation-time fallback section + the `ALLOW_EXTERNAL_IMAGE_FALLBACK` flag)
- Modify: `automation-tool-app/SKILL.md` (extend the "PYTHONPATH shadowing breaks local diffusers" pitfall with the fail-loud layer + flag)

**Step 1: Append to the reference doc** the symptom, the new flag, the fail-loud behavior, and the
regression check name.

**Step 2: Append one bullet** to the SKILL.md pitfall noting: startup guard = layer 0; generation-time
refuse + `ALLOW_EXTERNAL_IMAGE_FALLBACK` = layer 1; invariant covered by
`check_image_provider_no_silent_fallback` in `tools/regression_check.py`.

**Step 5: Commit**
```bash
git add references/DIFFUSERS_PYTHONPATH_FIX.md "automation-tool-app/SKILL.md"
git commit -m "docs(image): document fail-loud fallback layer + ALLOW_EXTERNAL_IMAGE_FALLBACK flag"
```

---

## Files likely to change
- `app.py` (env flag ~line 46; generation wrapper from Task 1)
- `tools/regression_check.py` (new check + CHECKS registration)
- `references/DIFFUSERS_PYTHONPATH_FIX.md`
- `automation-tool-app/SKILL.md`

## Tests / validation
- `tools/regression_check.py` (new `check_image_provider_no_silent_fallback`) — unit monkeypatch + live polluted-env launch.
- Manual: `curl /api/provider-strategy` shows `local_stable_diffusion.ready=True`, `selected=local_stable_diffusion`, startup log `[image-pipeline] diffusers local SDXL enabled`.
- Architecture skill rule: run `tools/regression_check.py` after the change; no pre-existing check may regress.

## Risks / tradeoffs / open questions
- **Tradeoff:** default-refuse means a future genuine diffusers outage blocks image gen instead of
  degrading to stock. That is the *intended* behavior (brand safety > convenience) — stock photos
  mislabeled as branded SDXL is the worse outcome. Operator can set `ALLOW_EXTERNAL_IMAGE_FALLBACK=1`
  deliberately when they want fallback.
- **Scope guard:** do NOT touch the 43K-line structure, the 149-branch dispatch, or the SQLite/JSON
  dual store. This is a surgical provider-policy change only.
- **Open:** exact wrapper symbol name (resolve in Task 1 via grep). If the fallback path is inside a
  larger `generate_image` function, edit the minimal branch, do not rewrite the function.
- **Memory:** the app must be relaunched with `env -u PYTHONPATH -u PYTHONHOME` (or via `start.bat`)
  for the guard to apply; a Hermes-terminal launch without unsetting PYTHONPATH re-introduces risk.

## Relevant skills to load during implementation
- `automation-tool-architecture` — safe-change boundaries, "run regression scripts after state/routing changes", dual-store caution.
- `automation-tool-app` — `DIFFUSERS_PYTHONPATH_FIX.md` reference, BUILD_ALL_POSTS_VERIFICATION, runtime pitfalls (search_files fails on app.py → use grep).
- `qa-testing-engineer` — "Silent failure is a critical quality defect", Model Fallback Testing, Regression Protection Mandatory.
- `plan` — this plan's structure (TDD bite-sized tasks).
- `requesting-code-review` — run a code-quality + spec review gate before merge.
