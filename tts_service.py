"""TTS service for normal-post voiceover assets (2026-07-20 plan §2).

Ownership boundary (approved review):
- promo_copy.py  -> text + voice-STYLE generation ONLY (no file I/O, no providers).
- tts_service.py -> provider selection, synthesis, cache, validation, failure handling.
- post_artifacts.py -> artifact paths, manifest updates, URL generation.
- app.py (social_post_builder) -> orchestration.

Engine priority is configuration-driven and LOCAL-FIRST by default so we never
spend on the paid/quota-limited OpenAI provider unless the user explicitly opts
into premium quality or every local engine fails.

Chatterbox (local, free, MIT) is the designated fallback when OpenAI returns an
out-of-tokens / quota error (HTTP 429). In premium mode OpenAI leads; on a 429 we
fall through to Chatterbox and the other local engines.

The module imports ``app`` lazily inside functions to avoid a circular import at
module load time (app imports tts_service for orchestration).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

# Bump when voice normalization / synthesis changes so cached files are not
# reused across incompatible versions (prevents EN/HA sharing the same voice).
AUDIO_NORMALIZATION_VERSION = 1

# Local-first default. Override with TTS_ENGINE_PRIORITY (comma list) or
# TTS_MODE=premium (puts openai first) / TTS_MODE=local_first (default).
_DEFAULT_PRIORITY = ["chatterbox", "windows_dotnet", "windows_sapi", "openai"]


def engine_priority() -> list[str]:
    env = os.environ.get("TTS_ENGINE_PRIORITY", "").strip()
    if env:
        return [e.strip().lower() for e in env.split(",") if e.strip()]
    if os.environ.get("TTS_MODE", "local_first").strip().lower() == "premium":
        return ["openai", "chatterbox", "windows_dotnet", "windows_sapi"]
    return list(_DEFAULT_PRIORITY)


class TTSQuotaError(Exception):
    """Raised when a paid provider is out of tokens / quota (e.g. OpenAI 429)."""


class TTSGenerationError(Exception):
    """Raised for non-quota synthesis failures."""


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_key(text: str, *, engine: str, voice_id: str, language: str,
              speed: float, model: str | None) -> str:
    # Text alone is NOT sufficient: voice can change while text is identical.
    payload = json.dumps(
        {
            "normalized_text": text.strip(),
            "engine": engine,
            "voice_id": voice_id,
            "language": language,
            "speed": round(float(speed), 3),
            "model": model or "",
            "normalization_version": AUDIO_NORMALIZATION_VERSION,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _cache_path(folder: "os.PathLike | str", key: str) -> Path:
    from pathlib import Path
    return Path(folder) / f".tts_cache" / f"{key}.mp3"


# ---------------------------------------------------------------------------
# Validation (atomic + real checks)
# ---------------------------------------------------------------------------

def _validate_audio(path: "os.PathLike | str", min_bytes: int = 1024) -> float:
    """Return duration_seconds (>0) or raise TTSGenerationError.

    Verifies the file exists, is large enough, decodes, and has positive
    duration. Does NOT accept a stale temp file as final.
    """
    from pathlib import Path
    p = Path(path)
    if not p.exists() or p.stat().st_size < min_bytes:
        raise TTSGenerationError(f"audio missing or too small: {p}")
    app = _app()
    if not app.media_ok(p, "a:0"):
        raise TTSGenerationError(f"audio failed decode check: {p}")
    duration = _probe_duration(app, p)
    if duration <= 0:
        raise TTSGenerationError(f"audio duration not positive: {p}")
    return duration


def _probe_duration(app, path: "os.PathLike | str") -> float:
    ffmpeg_exe = app.find_ffmpeg_executable()
    ffprobe = str(Path(str(ffmpeg_exe)).with_name("ffprobe.exe"))
    run = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(run.stdout.strip() or 0.0)
    except ValueError:
        return 0.0


def _app():
    import app  # lazy import; avoids circular import at load time
    return app


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

def _synthesize_chatterbox(text: str, out_wav: "os.PathLike | str",
                           ref_wav: str | None = None) -> None:
    app = _app()
    venv_py = app.ROOT / ".venv-chatterbox" / "Scripts" / "python.exe"
    helper = app.ROOT / "tools" / "chatterbox_gen.py"
    if not venv_py.exists() or not helper.exists():
        raise TTSGenerationError("chatterbox venv or helper missing")
    text_file = Path(out_wav).with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8")
    cmd = [str(venv_py), str(helper), str(out_wav), str(text_file)]
    if ref_wav and Path(ref_wav).exists():
        cmd.append(str(ref_wav))
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    run = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
    if run.returncode != 0 or not Path(out_wav).exists():
        raise TTSGenerationError(f"chatterbox failed: {run.stderr.strip()[:200]}")


def _synthesize_openai(text: str, out_mp3: "os.PathLike | str") -> None:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise TTSGenerationError("OPENAI_API_KEY not set")
    model = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    voice = os.environ.get("OPENAI_TTS_VOICE", "onyx")
    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "instructions": "Narrate like a polished fantasy web novel audiobook. Use natural pacing, clear diction, subtle emotion, and brief dramatic pauses.",
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    # Retry transient failures (timeouts, 5xx, Cloudflare 524) with capped
    # attempts + backoff. 429 (out-of-tokens/quota) is NOT retried -- it raises
    # TTSQuotaError so the caller falls through to Chatterbox immediately.
    last_exc: Exception | None = None
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                Path(out_mp3).write_bytes(resp.read())
            return
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise TTSQuotaError(f"OpenAI out of tokens/quota: {exc}")
            # Retryable server/Cloudflare errors (e.g. 524 = origin timeout, 502, 503, 504).
            last_exc = TTSGenerationError(f"OpenAI HTTP {exc.code}: {exc}")
        except Exception as exc:  # network / timeout (urllib raises URLError, socket.timeout)
            last_exc = TTSGenerationError(f"OpenAI request failed: {exc}")
        if attempt < max_attempts:
            time.sleep(min(2 ** attempt, 8))  # 2s, 4s, 8s backoff
    raise last_exc or TTSGenerationError("OpenAI request failed (unknown)")


def _synthesize_windows(text: str, out_wav: "os.PathLike | str",
                        engine: str = "windows_dotnet") -> None:
    app = _app()
    narration_file = Path(out_wav).with_suffix(".txt")
    narration_file.write_text(text, encoding="utf-8")
    wav = Path(out_wav)
    ps_quote = lambda v: "'" + str(v).replace("'", "''") + "'"
    if engine == "windows_sapi":
        powershell = f"""
$text = Get-Content -LiteralPath {ps_quote(narration_file)} -Raw -Encoding UTF8;
$voice = New-Object -ComObject SAPI.SpVoice;
$stream = New-Object -ComObject SAPI.SpFileStream;
$stream.Open({ps_quote(wav)}, 3, $false);
$voice.AudioOutputStream = $stream;
$voice.Speak($text) | Out-Null;
$stream.Close();
"""
    else:
        voice_filter = '$voice = $speak.VoiceInfo.Name'
        powershell = f"""
Add-Type -AssemblyName System.Speech;
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;
$speak.Rate = 0;
$speak.Volume = 100;
{voice_filter};
$speak.SetOutputToWaveFile({ps_quote(wav)});
$speak.Speak((Get-Content -LiteralPath {ps_quote(narration_file)} -Raw -Encoding UTF8));
$speak.Dispose();
"""
    run = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", powershell],
        capture_output=True, text=True, check=False,
    )
    if run.returncode != 0 or not wav.exists():
        raise TTSGenerationError(f"windows speech failed: {(run.stderr or run.stdout).strip()[:200]}")


_ENGINE_SYNTH = {
    "chatterbox": lambda text, out, **kw: _synthesize_chatterbox(text, out, ref_wav=kw.get("ref_wav")),
    "openai": lambda text, out, **kw: _synthesize_openai(text, out),
    "windows_dotnet": lambda text, out, **kw: _synthesize_windows(text, out, engine="windows_dotnet"),
    "windows_sapi": lambda text, out, **kw: _synthesize_windows(text, out, engine="windows_sapi"),
}

_DEFAULT_VOICE = {
    "chatterbox": "chatterbox_default",
    "openai": os.environ.get("OPENAI_TTS_VOICE", "onyx"),
    "windows_dotnet": "en-US",
    "windows_sapi": "en-US",
}

# Map an engine to its output extension before mp3 conversion.
_RAW_EXT = {"chatterbox": ".wav", "windows_dotnet": ".wav", "windows_sapi": ".wav", "openai": ".mp3"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_post_audio(text: str, folder: "os.PathLike | str", *,
                         voice_id: str | None = None,
                         language: str = "en",
                         speed: float = 1.0,
                         model: str | None = None,
                         abbr: str | None = None) -> dict:
    """Generate (or fetch from cache) a voiceover mp3 for ``text``.

    Returns a structured status dict (never raises for provider failures --
    those are reported in ``status``/``error`` so the post build still succeeds):
        {
          "status": "ready" | "skipped" | "failed",
          "path": "...", "url": "...", "engine": "...", "voice_id": "...",
          "duration_seconds": float, "cache_hit": bool,
          "content_hash": "...", "error": None | str,
        }
    """
    from pathlib import Path
    folder = Path(folder)
    base = {
        "status": "failed", "path": "", "url": "", "engine": "",
        "voice_id": "", "duration_seconds": 0.0, "cache_hit": False,
        "content_hash": "", "error": None,
    }
    if not text or not text.strip():
        return {**base, "status": "skipped", "error": "empty text"}

    text_norm = text.strip()
    # Try engines in configured priority; Chatterbox catches OpenAI 429 because
    # it follows openai in premium mode.
    for engine in engine_priority():
        voice = voice_id or _DEFAULT_VOICE.get(engine, "default")
        key = _cache_key(text_norm, engine=engine, voice_id=voice,
                         language=language, speed=speed, model=model)
        cached = _cache_path(folder, key)
        if cached.exists() and cached.stat().st_size >= 1024:
            try:
                dur = _validate_audio(cached)
                return {
                    **base, "status": "ready", "path": str(cached),
                    "url": _local_url(folder, cached), "engine": engine,
                    "voice_id": voice, "duration_seconds": dur,
                    "cache_hit": True, "content_hash": key,
                }
            except Exception:
                pass  # stale cache entry; regenerate below

        # Ensure the cache directory exists before writing the temp raw file.
        cached.parent.mkdir(parents=True, exist_ok=True)
        raw_ext = _RAW_EXT.get(engine, ".wav")
        tmp_raw = cached.with_name(f"{key}.tmp{raw_ext}")
        final = cached
        try:
            _ENGINE_SYNTH[engine](text_norm, tmp_raw, ref_wav=os.environ.get("CHATTERBOX_REF_WAV"))
        except TTSQuotaError as exc:
            # Out of tokens on a paid provider -> fall through to next engine
            # (Chatterbox in premium mode), per the approved fallback rule.
            base["error"] = str(exc)
            continue
        except Exception as exc:
            base["error"] = f"{engine}: {exc}"
            continue

        # Convert raw -> mp3 (openai already mp3) with atomic rename.
        try:
            if engine != "openai":
                _convert_to_mp3(tmp_raw, final)
            else:
                tmp_raw.replace(final)
        except Exception as exc:
            base["error"] = f"{engine} convert: {exc}"
            continue

        try:
            dur = _validate_audio(final)
        except Exception as exc:
            base["error"] = f"{engine} validate: {exc}"
            continue
        # Cleanup temp raw if distinct.
        if tmp_raw.exists() and tmp_raw != final:
            try:
                tmp_raw.unlink()
            except Exception:
                pass
        return {
            **base, "status": "ready", "path": str(final),
            "url": _local_url(folder, final), "engine": engine,
            "voice_id": voice, "duration_seconds": dur,
            "cache_hit": False, "content_hash": key,
        }

    # All engines failed -> post still usable, audio just absent.
    return {**base, "status": "failed",
            "error": base.get("error") or "all TTS engines failed"}


def _convert_to_mp3(src: "os.PathLike | str", dst: "os.PathLike | str") -> None:
    app = _app()
    ffmpeg_exe = app.find_ffmpeg_executable()
    tmp = Path(dst).with_name(Path(dst).name + ".tmp.mp3")
    run = subprocess.run(
        [ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-c:a", "libmp3lame", "-b:a", "128k", str(tmp)],
        capture_output=True, text=True, check=False,
    )
    if run.returncode != 0 or not tmp.exists():
        raise TTSGenerationError(f"mp3 convert failed: {run.stderr.strip()[:200]}")
    tmp.replace(dst)  # atomic


def _local_url(folder: "os.PathLike | str", path: "os.PathLike | str") -> str:
    # The cached mp3 lives on local disk; the dashboard is served over http://,
    # so a file:// URL is unplayable in-browser. Route through /api/post-audio
    # (which enforces path confinement) using the content hash from the filename.
    try:
        from post_artifacts import post_audio_url
        content_hash = Path(path).stem.split(".tmp", 1)[0]
        url = post_audio_url(folder, content_hash)
        if url:
            return url
    except Exception:
        pass
    # Fallback: raw file URI (used by non-browser consumers / tests).
    try:
        return Path(path).as_uri()
    except Exception:
        return str(path)
