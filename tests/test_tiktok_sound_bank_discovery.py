"""Regression tests: TikTok sound discovery uses the canonical sound bank.

Hotfix context: the reusable soundtrack MP3s no longer live in the CloudFlare
media folder. They live in a read-only bank under the project root
(TIKTOK_SOUND_BANK_DIR, default ROOT / "tiktok-sound-bank").

Before the fix, sound discovery read only TIKTOK_ASSET_DIR (CloudFlare), which
exists but holds no audio, so the short-form builders raised
"No TikTok sound files were found."

These tests assert:

  A. TIKTOK_SOUND_BANK_DIR is defined and points under the project root.
  B. list_tiktok_assets() finds bank MP3s when TIKTOK_ASSET_DIR is EMPTY.
  C. list_tiktok_assets() finds bank MP3s when TIKTOK_ASSET_DIR is MISSING
     (i.e. CloudFlare is not required at all).
  D. weekly_promo_audio_files() includes bank MP3s (live TikTok audio path).
  E. Discovery is read-only: the bank directory is never written to.
  F. Asset-dir audio is still discovered, and duplicates are not doubled up.

Run: python tests/test_tiktok_sound_bank_discovery.py   (from repo root)
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}{(' :: ' + detail) if detail else ''}")
        FAILURES.append(label)


class _Patched:
    """Temporarily point the app's TikTok dirs at scratch locations."""

    def __init__(self, *, bank: Path | None = None, asset: Path | None = None):
        self.bank = bank
        self.asset = asset

    def __enter__(self):
        self._old_bank = app.TIKTOK_SOUND_BANK_DIR
        self._old_asset = app.TIKTOK_ASSET_DIR
        if self.bank is not None:
            app.TIKTOK_SOUND_BANK_DIR = self.bank
        if self.asset is not None:
            app.TIKTOK_ASSET_DIR = self.asset
        return self

    def __exit__(self, *exc):
        app.TIKTOK_SOUND_BANK_DIR = self._old_bank
        app.TIKTOK_ASSET_DIR = self._old_asset
        return False


def _make_bank(root: Path, names=("alpha.mp3", "beta.mp3")) -> Path:
    bank = root / "tiktok-sound-bank"
    bank.mkdir(parents=True, exist_ok=True)
    for name in names:
        (bank / name).write_bytes(b"ID3fake-mp3-bytes")
    return bank


def test_bank_constant_defined() -> None:
    print("\n[A] TIKTOK_SOUND_BANK_DIR is defined under the project root")
    check("constant exists", hasattr(app, "TIKTOK_SOUND_BANK_DIR"))
    bank = app.TIKTOK_SOUND_BANK_DIR
    check("is a Path", isinstance(bank, Path), repr(bank))
    check("is absolute", bank.is_absolute(), str(bank))
    check(
        "lives under project ROOT",
        str(bank).lower().startswith(str(app.ROOT).lower()),
        f"{bank} not under {app.ROOT}",
    )
    check("named tiktok-sound-bank", bank.name == "tiktok-sound-bank", bank.name)


def test_discovery_with_empty_asset_dir() -> None:
    print("\n[B] list_tiktok_assets() finds bank MP3s when asset dir is empty")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bank = _make_bank(root)
        asset = root / "cloudflare-empty"
        asset.mkdir()
        with _Patched(bank=bank, asset=asset):
            sounds = app.list_tiktok_assets().get("sounds", [])
        names = sorted(item["name"] for item in sounds)
        check("found 2 sounds", len(sounds) == 2, f"got {len(sounds)}")
        check("names match bank", names == ["alpha.mp3", "beta.mp3"], str(names))
        check(
            "paths resolve to bank",
            all(Path(item["path"]).parent == bank for item in sounds),
            str([item["path"] for item in sounds]),
        )


def test_discovery_without_cloudflare() -> None:
    print("\n[C] Discovery works with NO asset dir at all (CloudFlare absent)")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bank = _make_bank(root)
        missing = root / "does-not-exist-cloudflare"
        with _Patched(bank=bank, asset=missing):
            assets = app.list_tiktok_assets()
            sounds = assets.get("sounds", [])
            check("asset dir really missing", not missing.exists())
            check("still found sounds", len(sounds) == 2, f"got {len(sounds)}")
            check(
                "no bogus image groups",
                assets.get("imageGroups") == [] and assets.get("videos") == [],
            )
            # The builders' guard is `if not sounds: raise RuntimeError(...)`.
            check("builder guard would not trip", bool(sounds))


def test_weekly_promo_audio_includes_bank() -> None:
    print("\n[D] weekly_promo_audio_files() includes the bank (live audio path)")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bank = _make_bank(root)
        with _Patched(bank=bank):
            files = app.weekly_promo_audio_files()
        names = {path.name for path in files}
        check("alpha.mp3 discovered", "alpha.mp3" in names, str(names))
        check("beta.mp3 discovered", "beta.mp3" in names, str(names))
        with _Patched(bank=bank):
            choice = app.choose_rotating_weekly_promo_audio()
        check("rotation returns a real file", choice is not None and choice.is_file(), str(choice))


def test_discovery_is_read_only() -> None:
    print("\n[E] Sound discovery never writes into the bank")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bank = _make_bank(root)
        asset = root / "cloudflare-empty"
        asset.mkdir()
        before = {p.name: p.read_bytes() for p in bank.iterdir()}
        with _Patched(bank=bank, asset=asset):
            for _ in range(5):
                app.list_tiktok_assets()
                app.weekly_promo_audio_files()
                app.choose_rotating_weekly_promo_audio()
        after = {p.name: p.read_bytes() for p in bank.iterdir()}
        check("no files added or removed", sorted(before) == sorted(after), str(sorted(after)))
        check("file contents unchanged", before == after)


def test_asset_dir_audio_still_found() -> None:
    print("\n[F] Asset-dir audio still discovered, no duplicates")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bank = _make_bank(root, names=("alpha.mp3",))
        asset = root / "cloudflare"
        asset.mkdir()
        (asset / "legacy.mp3").write_bytes(b"ID3legacy")
        with _Patched(bank=bank, asset=asset):
            sounds = app.list_tiktok_assets().get("sounds", [])
        names = sorted(item["name"] for item in sounds)
        check("both sources present", names == ["alpha.mp3", "legacy.mp3"], str(names))
        paths = [item["path"] for item in sounds]
        check("no duplicate paths", len(paths) == len(set(paths)), str(paths))


def test_real_bank_has_mp3s() -> None:
    print("\n[G] The real on-disk bank is populated (smoke)")
    bank = app.TIKTOK_SOUND_BANK_DIR
    if not bank.exists():
        print(f"  SKIP  bank not present at {bank}")
        return
    mp3s = sorted(p.name for p in bank.glob("*.mp3"))
    check("real bank has mp3s", len(mp3s) > 0, str(mp3s))
    sounds = app.list_tiktok_assets().get("sounds", [])
    check("live discovery non-empty", len(sounds) > 0, f"got {len(sounds)}")


def main() -> int:
    print("TikTok sound-bank discovery regression tests")
    print(f"ROOT = {app.ROOT}")
    print(f"TIKTOK_SOUND_BANK_DIR = {app.TIKTOK_SOUND_BANK_DIR}")
    print(f"TIKTOK_ASSET_DIR = {app.TIKTOK_ASSET_DIR}")
    test_bank_constant_defined()
    test_discovery_with_empty_asset_dir()
    test_discovery_without_cloudflare()
    test_weekly_promo_audio_includes_bank()
    test_discovery_is_read_only()
    test_asset_dir_audio_still_found()
    test_real_bank_has_mp3s()
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
