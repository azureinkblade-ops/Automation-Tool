"""Bounded Kilo 7.7.2 metadata probes; never submit a task or credentials."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


BINARY = Path(
    r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.7.2-win32-x64\bin\kilo.exe"
)
EXPECTED_HASH = "3dca5f2eb8cc2d875e8cdef756f77347d4899247c318bf2a018d39e0184455cd"
EXPECTED_VERSION = "7.7.2"
ALLOWED_ARGUMENTS = (("--version",), ("run", "--help"))
REQUIRED_RUN_OPTIONS = ("--format", "--pure", "--agent", "--model", "json")


def _sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def qualify():
    actual = _sha256(BINARY)
    if actual != EXPECTED_HASH:
        raise RuntimeError("Successor identity changed; do not probe")

    results = []
    with tempfile.TemporaryDirectory(prefix="ea4e92t-kilo772-metadata-") as directory:
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
        for arguments in ALLOWED_ARGUMENTS:
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
            results.append(
                {
                    "arguments": list(arguments),
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )

    if _sha256(BINARY) != actual:
        raise RuntimeError("Successor identity changed during probe")
    if any(result["exit_code"] != 0 for result in results):
        raise RuntimeError("Metadata probe failed; do not promote successor")
    if results[0]["stdout"].strip() != EXPECTED_VERSION:
        raise RuntimeError("CLI version mismatch; do not promote successor")
    help_text = results[1]["stdout"] + results[1]["stderr"]
    for required in REQUIRED_RUN_OPTIONS:
        if required not in help_text:
            raise RuntimeError(f"Required CLI option missing: {required}")
    return {
        "binary_path": str(BINARY),
        "binary_sha256": actual,
        "binary_version": EXPECTED_VERSION,
        "probes": results,
    }


def main():
    print(json.dumps(qualify(), indent=2))


if __name__ == "__main__":
    main()
