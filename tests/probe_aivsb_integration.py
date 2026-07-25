"""
Read-only integration probe: does the AIVSB entity resolver -> telemetry sink
actually fire when a query reaches it as `entity_lookup`, through the REAL
app.py / scripts/aivsb code (no edits, no resolver/classifier changes)?

WHY THIS SHAPE (important):
The production chapter-image beat is a full sentence ("Kael stepped into
the forge..."), which `prompt_composer.py` classifies as `concept_retrieval`
-> the entity resolver is SKIPPED -> entity_resolution_events.jsonl stays empty.
That is why chapter-image runs never populate telemetry.

To exercise the resolver we must feed it a query that classifies as `entity_lookup`.
Two candidates were tested:

  (A) Bare character name passed as the composer beat, e.g. `beat="Kael"`
      via `compose_aivsb_scene_prompt`. FLAKY: `direct_scene` appends a
      default `viewer_emotion="unspecified"` to the beat, so the resolver
      actually receives `"Kael unspecified"`. That string sits ON the
      classifier's decision boundary -> sometimes `entity_lookup`, sometimes
      not -> the telemetry write is non-deterministic. NOT a dependable gate.

  (B) Bare character name fed directly to `run_retrieval` with
      `enable_entity_resolution=True`. RELIABLE: `classify("Kael")` -> entity_lookup
      deterministically (verified). This is the path this probe asserts on.

So this probe uses (B): it drives the same `KnowledgeRetrievalService` +
TelemetrySink that `semantic_passages` builds (env-gated, OFF by default),
and confirms a bare-name `entity_lookup` resolves and writes a JSONL event.
That proves the resolver+telemetry wiring is live. The composer-beat path (A)
is documented as flaky and intentionally NOT asserted as a hard gate.

This is READ-ONLY: imports the existing app.py / aivsb, sets the four AIVSB
env flags, strips the Hermes venv (numpy 2.4.3 in the Hermes venv has
.cp311 extensions incompatible with the codex runtime's Python 3.12; app.py
does this strip at import and the live server is fine, but standalone probes
must replicate it or numpy import breaks). The only file it writes is the
telemetry JSONL (system-under-test output).

Run with the CODEX RUNTIME python (the interpreter that runs app.py):
    set AIVSB_REASONING_ENABLED=on
    set AIVSB_ENTITY_RESOLUTION_ENABLED=on
    set AIVSB_SEMANTIC_RETRIEVAL_ENABLED=on
    set AIVSB_TELEMETRY_ENABLED=true
    set AIVSB_TELEMETRY_PATH=C:/aivsb_logs/entity_resolution_events.jsonl
    "<codex python>" tests/probe_aivsb_integration.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
APP_PATH = os.path.join(ROOT, "app.py")
AIVSB = r"C:\Users\David\Documents\Inkblade Author Studio\scripts\aivsb"
TELEMETRY_PATH = os.environ.get(
    "AIVSB_TELEMETRY_PATH", r"C:\aivsb_logs\entity_resolution_events.jsonl"
)
# Bare character name that reliably classifies as entity_lookup.
PROBE_QUERY = "Kael"


def _strip_hermes_venv() -> None:
    """Replicate app.py's sys.path hygiene so codex-runtime numpy/torch load."""
    hermes = r"C:\Users\David\AppData\Local\hermes\hermes-agent\venv"
    lowered = hermes.lower()
    sys.path = [p for p in sys.path if lowered not in p.lower()]


def _require_flags() -> list[str]:
    required = {
        "AIVSB_REASONING_ENABLED": "on",
        "AIVSB_ENTITY_RESOLUTION_ENABLED": "on",
        "AIVSB_SEMANTIC_RETRIEVAL_ENABLED": "on",
        "AIVSB_TELEMETRY_ENABLED": "true",
    }
    return [k for k, v in required.items()
            if os.environ.get(k, "").strip().lower() != v]


def main() -> int:
    _strip_hermes_venv()
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    missing = _require_flags()
    if missing:
        print(f"[probe] FAIL: missing/incorrect env flags: {missing}")
        return 2

    # Fresh telemetry file so we only see THIS run's events.
    try:
        if os.path.exists(TELEMETRY_PATH):
            os.remove(TELEMETRY_PATH)
    except OSError as exc:
        print(f"[probe] WARN: could not clear {TELEMETRY_PATH}: {exc}")

    # Import live app.py (the shared monolith) WITHOUT any edits.
    spec = importlib.util.spec_from_file_location("app_probe", APP_PATH)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)

    # Build the SAME service + sink that semantic_passages builds
    # (env-gated, OFF by default). This is the exact object the live
    # compose path attaches a TelemetrySink to.
    for p in (os.path.join(AIVSB, "reasoning"),
              os.path.join(AIVSB, "retrieval"), AIVSB):
        if p not in sys.path:
            sys.path.insert(0, p)
    svc_mod = importlib.import_module("retrieval.service")
    pipe = importlib.import_module("retrieval_pipeline")
    from retrieval.stage_c.telemetry_sink import TelemetrySink
    from reasoning.bible_context import BibleContext, Knowledge

    kb = Knowledge()
    ctx = BibleContext(kb)
    chunks = ctx._build_chunks()
    db_path = ctx._ensure_production_index(chunks, None)
    svc = svc_mod.KnowledgeRetrievalService(
        db_path=db_path, model_name=svc_mod.DEFAULT_MODEL
    )
    svc.telemetry_sink = TelemetrySink(TELEMETRY_PATH)

    # Reliable path (B): bare-name entity_lookup through run_retrieval.
    print(f"[probe] calling run_retrieval('{PROBE_QUERY}', entity_resolution=on) "
          f"[novel=en]")
    try:
        req = pipe.build_request_from_text(
            PROBE_QUERY, novel="en", db_path=db_path,
            enable_entity_resolution=True,
        )
        print(f"[probe]   classify -> query_type={req.query_type} "
              f"er_enabled={req.enable_entity_resolution}")
        res = pipe.run_retrieval(req, svc, db_path)
    except Exception as exc:  # defensive: a crash means the chain is broken
        import traceback
        traceback.print_exc()
        print(f"[probe] FAIL: run_retrieval raised: {exc!r}")
        return 3

    print(f"[probe]   retrieval results: {len(res)}")

    # Did the resolver write a character_match event for 'kael'?
    telemetry_wrote = False
    event = None
    if os.path.exists(TELEMETRY_PATH):
        with open(TELEMETRY_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("resolved_entity_id") == "kael":
                    telemetry_wrote = True
                    event = rec
                    break

    print()
    if telemetry_wrote:
        print("[probe] PASS: AIVSB resolver -> telemetry sink live "
              "(entity_lookup path)")
        print(f"[probe]   resolver event: {json.dumps(event, ensure_ascii=False)}")
        return 0
    print("[probe] FAIL: resolver did not write a kael character_match event")
    print(f"[probe]   query_type={req.query_type} "
          f"telemetry_file_exists={os.path.exists(TELEMETRY_PATH)}")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
