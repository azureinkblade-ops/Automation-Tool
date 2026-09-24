"""Exact Kilo 7.7.9 metadata probe; never submit a task or model request."""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


BINARY = Path(
    r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.9-win32-x64\bin\kilo.exe"
)
EXPECTED_HASH = "9ef2ca9633cece72293d269502bee16720d9179990c1b65abc0599c6d356bd07"
EXPECTED_VERSION = "7.7.9"
ALLOWED_ARGUMENTS = (("--version",), ("run", "--help"))
REQUIRED_RUN_OPTIONS = ("--format", "--pure", "--agent", "--model", "json")


def _sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def qualify():
    """Run two bounded metadata commands only after exact file revalidation."""
    if _sha256(BINARY) != EXPECTED_HASH:
        raise RuntimeError("Successor identity changed; do not probe")

    with tempfile.TemporaryDirectory(prefix="ea4e92ah-kilo779-metadata-") as directory:
        environment = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
            "HOME": directory,
            "USERPROFILE": directory,
            "TEMP": directory,
            "TMP": directory,
            "PATH": str(BINARY.parent),
            "KILO_CONFIG_DIR": directory,
            "OPENCODE_CONFIG_DIR": directory,
            "OPENCODE_TEST_HOME": directory,
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "KILO_PURE": "1",
            "OPENCODE_PURE": "1",
            "NO_COLOR": "1",
        }
        results = []
        for arguments in ALLOWED_ARGUMENTS:
            if _sha256(BINARY) != EXPECTED_HASH:
                raise RuntimeError("Successor identity changed; do not probe")
            completed = subprocess.run(
                [str(BINARY), *arguments],
                cwd=directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                shell=False,
            )
            if _sha256(BINARY) != EXPECTED_HASH:
                raise RuntimeError("Successor identity changed during probe")
            if completed.returncode != 0:
                raise RuntimeError("Metadata probe failed; do not promote successor")
            output = completed.stdout + completed.stderr
            if len(output) > 65536:
                raise RuntimeError("Metadata output exceeds review limit")
            if arguments == ("--version",):
                if completed.stdout.strip() != EXPECTED_VERSION:
                    raise RuntimeError("CLI version mismatch; do not promote successor")
            elif any(option not in output for option in REQUIRED_RUN_OPTIONS):
                raise RuntimeError("Required CLI option missing")
            results.append({
                "arguments": list(arguments),
                "exit_code": completed.returncode,
                "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            })
    return {
        "binary_path": str(BINARY),
        "binary_sha256": EXPECTED_HASH,
        "binary_version": EXPECTED_VERSION,
        "probes": results,
    }
