"""Bounded CLI metadata probes; never supply a receiver task or credentials."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


BINARY = Path(r"C:\Users\David\.vscode\extensions\kilocode.kilo-code-7.6.2-win32-x64\bin\kilo.exe")
EXPECTED_HASH = "5d54b522d8a59228951d141cd70438c29115963ecb38d7cdfcf313f59c0f865b"


def qualify():
    with BINARY.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != EXPECTED_HASH:
        raise RuntimeError("Successor identity changed; do not probe")
    results = []
    with tempfile.TemporaryDirectory(prefix="ea4e67-metadata-") as directory:
        env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
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
        }
        for arguments in (("--version",), ("run", "--help")):
            result = subprocess.run(
                [str(BINARY), *arguments], cwd=directory, env=env,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=15, shell=False,
            )
            results.append({"arguments": arguments, "exit_code": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})
    if any(result["exit_code"] != 0 for result in results):
        raise RuntimeError("Metadata probe failed; do not promote successor")
    if results[0]["stdout"].strip() != "7.6.2":
        raise RuntimeError("CLI version mismatch; do not promote successor")
    help_text = results[1]["stdout"] + results[1]["stderr"]
    for required in ("--format", "--pure", "--agent", "--model", "json"):
        if required not in help_text:
            raise RuntimeError(f"Required CLI option missing: {required}")
    return {"binary_sha256": actual, "probes": results}


def main():
    print(json.dumps(qualify(), indent=2))


if __name__ == "__main__":
    main()
