from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
ARCHIVE = TOOLS / "ffmpeg-8.1.1-essentials_build.zip"
ALT_ARCHIVE = TOOLS / "ffmpeg-release-essentials.zip"
TARGET = TOOLS / "ffmpeg"
URL = "https://github.com/GyanD/codexffmpeg/releases/download/8.1.1/ffmpeg-8.1.1-essentials_build.zip"
SHA256 = "6f58ce889f59c311410f7d2b18895b33c03456463486f3b1ebc93d97a0f54541"


def download() -> None:
    TOOLS.mkdir(exist_ok=True)
    if ARCHIVE.exists():
        return
    if ALT_ARCHIVE.exists():
        shutil.copy2(ALT_ARCHIVE, ARCHIVE)
        return
    local_archive = find_local_archive()
    if local_archive:
        return
    print("Downloading FFmpeg essentials build...")
    request = urllib.request.Request(URL, headers={"User-Agent": "AutomationTool/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        ARCHIVE.write_bytes(response.read())


def verify() -> None:
    if not ARCHIVE.exists():
        return
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if digest.lower() != SHA256:
        raise SystemExit(f"FFmpeg ZIP checksum did not match. Got {digest}.")


def find_local_archive() -> Path | None:
    candidates = []
    for path in TOOLS.iterdir() if TOOLS.exists() else []:
        name = path.name.lower()
        if path.is_file() and (
            name.endswith(".zip")
            or name.endswith(".tar")
            or name.endswith(".tar.gz")
            or name.endswith(".tgz")
            or name.endswith(".tar.xz")
            or name.endswith(".txz")
        ):
            candidates.append(path)
    return candidates[0] if candidates else None


def extract() -> Path:
    temp = TOOLS / "_ffmpeg_extract"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)
    archive = ARCHIVE if ARCHIVE.exists() else find_local_archive()
    if not archive:
        raise SystemExit("No FFmpeg archive found in tools.")
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(temp)
    else:
        with tarfile.open(archive) as tf:
            try:
                tf.extractall(temp, filter="data")
            except TypeError:
                tf.extractall(temp)
    ffmpeg_found = next(temp.rglob("ffmpeg.exe"), None)
    if ffmpeg_found:
        bin_dir = TARGET / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        for exe_name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
            exe = next(temp.rglob(exe_name), None)
            if exe:
                shutil.copy2(exe, bin_dir / exe_name)
        shutil.rmtree(temp)
        return bin_dir / "ffmpeg.exe"
    roots = [path for path in temp.iterdir() if path.is_dir()]
    if not roots:
        raise SystemExit("Could not find an FFmpeg folder inside the archive.")
    if TARGET.exists():
        for child in roots[0].iterdir():
            destination = TARGET / child.name
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination, ignore_errors=True)
                else:
                    destination.unlink(missing_ok=True)
            shutil.move(str(child), str(destination))
    else:
        shutil.move(str(roots[0]), str(TARGET))
    shutil.rmtree(temp)
    ffmpeg = TARGET / "bin" / "ffmpeg.exe"
    if not ffmpeg.exists():
        raise SystemExit(
            "The archive did not contain a Windows ffmpeg.exe. "
            "It may be a source-code tarball. Please use the Windows essentials build ZIP."
        )
    return ffmpeg


def main() -> None:
    download()
    verify()
    ffmpeg = extract()
    result = subprocess.run([str(ffmpeg), "-version"], capture_output=True, text=True, check=False)
    print((result.stdout or result.stderr).splitlines()[0])
    print(f"FFmpeg is ready at {ffmpeg}")


if __name__ == "__main__":
    main()
