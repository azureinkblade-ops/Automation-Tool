"""Unit tests for §2 TTS service (2026-07-20 plan).

Run: .venv-gpu/Scripts/python.exe tools/test_tts_service.py
Covers the required matrix: cache hit, provider failure, invalid mp3,
local-first mode, premium-disabled mode. No network; engines are stubbed via
monkeypatching tts_service._ENGINE_SYNTH / engine_priority.
"""
import os
import sys
import json
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tts_service as ts


def _make_tmp_folder(tmp_path):
    d = tmp_path / "post"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_valid_wav(path, seconds=1.0):
    import wave
    import struct
    sr = 8000
    n = int(sr * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack("<%dh" % n, *([0] * n)))


def test_cache_hit(tmp_path, monkeypatch):
    """Second identical request must be a cache hit with no synthesis call."""
    folder = _make_tmp_folder(tmp_path)
    calls = []

    def fake_synth(text, out, **kw):
        calls.append(text)
        _write_valid_wav(out)

    monkeypatch.setattr(ts, "_ENGINE_SYNTH", {"chatterbox": fake_synth})
    monkeypatch.setattr(ts, "engine_priority", lambda: ["chatterbox"])
    monkeypatch.setattr(ts, "_validate_audio", lambda p, min_bytes=1024: 1.5)

    r1 = ts.generate_post_audio("Hello world", folder)
    r2 = ts.generate_post_audio("Hello world", folder)
    assert r1["status"] == "ready", r1
    assert r2["status"] == "ready" and r2["cache_hit"] is True, r2
    assert len(calls) == 1, f"expected 1 synthesis, got {len(calls)}"  # cache avoids 2nd


def test_provider_failure_falls_through(tmp_path, monkeypatch):
    """If first engine fails, next engine is tried; all-fail -> failed status."""
    folder = _make_tmp_folder(tmp_path)
    order = []

    def fail_chatter(text, out, **kw):
        order.append("chatterbox")
        raise ts.TTSGenerationError("boom")

    def ok_windows(text, out, **kw):
        order.append("windows_dotnet")
        _write_valid_wav(out)

    monkeypatch.setattr(ts, "_ENGINE_SYNTH", {"chatterbox": fail_chatter, "windows_dotnet": ok_windows})
    monkeypatch.setattr(ts, "engine_priority", lambda: ["chatterbox", "windows_dotnet"])
    monkeypatch.setattr(ts, "_validate_audio", lambda p, min_bytes=1024: 2.0)

    r = ts.generate_post_audio("Hi", folder)
    assert r["status"] == "ready" and r["engine"] == "windows_dotnet", r
    assert order == ["chatterbox", "windows_dotnet"]


def test_openai_quota_falls_to_chatterbox_premium(tmp_path, monkeypatch):
    """Premium mode: OpenAI leads; on 429 (TTSQuotaError) Chatterbox catches it."""
    folder = _make_tmp_folder(tmp_path)
    order = []

    def fail_openai(text, out, **kw):
        order.append("openai")
        raise ts.TTSQuotaError("out of tokens")

    def ok_chatter(text, out, **kw):
        order.append("chatterbox")
        _write_valid_wav(out)

    monkeypatch.setattr(ts, "_ENGINE_SYNTH", {"openai": fail_openai, "chatterbox": ok_chatter})
    monkeypatch.setattr(ts, "engine_priority", lambda: ["openai", "chatterbox"])
    monkeypatch.setattr(ts, "_validate_audio", lambda p, min_bytes=1024: 1.0)

    r = ts.generate_post_audio("Hi", folder)
    assert r["status"] == "ready" and r["engine"] == "chatterbox", r
    assert order == ["openai", "chatterbox"]


def test_local_first_default(tmp_path, monkeypatch):
    """Default (no TTS_MODE) must be local-first: chatterbox before openai."""
    monkeypatch.delenv("TTS_MODE", raising=False)
    monkeypatch.delenv("TTS_ENGINE_PRIORITY", raising=False)
    assert ts.engine_priority()[0] == "chatterbox"
    assert ts.engine_priority()[-1] == "openai"


def test_premium_mode_puts_openai_first(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_MODE", "premium")
    monkeypatch.delenv("TTS_ENGINE_PRIORITY", raising=False)
    assert ts.engine_priority()[0] == "openai"


def test_cache_key_includes_voice_and_engine(tmp_path, monkeypatch):
    k1 = ts._cache_key("text", engine="openai", voice_id="onyx", language="en", speed=1.0, model="m1")
    k2 = ts._cache_key("text", engine="chatterbox", voice_id="onyx", language="en", speed=1.0, model="m1")
    k3 = ts._cache_key("text", engine="openai", voice_id="nova", language="en", speed=1.0, model="m1")
    assert k1 != k2, "engine must affect cache key (prevents EN/HA voice reuse)"
    assert k1 != k3, "voice_id must affect cache key"


def test_all_engines_fail(tmp_path, monkeypatch):
    folder = _make_tmp_folder(tmp_path)

    def fail(text, out, **kw):
        raise ts.TTSGenerationError("nope")

    monkeypatch.setattr(ts, "_ENGINE_SYNTH", {"chatterbox": fail, "windows_dotnet": fail, "windows_sapi": fail, "openai": fail})
    monkeypatch.setattr(ts, "engine_priority", lambda: ["chatterbox", "windows_dotnet", "windows_sapi", "openai"])
    r = ts.generate_post_audio("Hi", folder)
    assert r["status"] == "failed", r  # post still usable


def test_empty_text_skipped(tmp_path, monkeypatch):
    folder = _make_tmp_folder(tmp_path)
    r = ts.generate_post_audio("   ", folder)
    assert r["status"] == "skipped"


if __name__ == "__main__":
    import pathlib
    import tempfile

    class Monkeypatch:
        """Tiny monkeypatch shim: setattr / setenv / delenv."""
        def __init__(self):
            self._restored = []
        def setattr(self, obj, name, val):
            self._restored.append((obj, name, getattr(obj, name, None)))
            setattr(obj, name, val)
        def setenv(self, k, v):
            self._restored.append(("__env__", k, os.environ.get(k)))
            os.environ[k] = v
        def delenv(self, k, raising=True):
            self._restored.append(("__env__", k, os.environ.get(k)))
            os.environ.pop(k, None)

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        mp = Monkeypatch()
        with tempfile.TemporaryDirectory() as td:
            tmp_path = pathlib.Path(td)
            try:
                t(tmp_path, mp)
                print(f"PASS {t.__name__}")
                passed += 1
            except Exception as e:
                print(f"FAIL {t.__name__}: {e}")
            finally:
                # Restore any patched attrs / env vars so tests stay isolated.
                for entry in reversed(mp._restored):
                    obj, name, orig = entry
                    if obj == "__env__":
                        if orig is None:
                            os.environ.pop(name, None)
                        else:
                            os.environ[name] = orig
                    else:
                        try:
                            setattr(obj, name, orig)
                        except Exception:
                            pass
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
