#!/usr/bin/env bash
#
# SC-8 scheduled orchestration wrapper (orchestration only — no backup logic here).
#
# Invokes the existing, tested SC-8 command surface:
#   1. tools/db_health_gate.py --enforce-no-mirrors
#   2. tools/db_backup_rotate.py  (only when the gate exits 0)
#
# It NEVER invokes db_restore.py (restore is strictly manual).
#
# For every run it records, to migration-backups/sc8-logs/sc8-<ts>.log:
#   - execution timestamp
#   - the health gate stdout, stderr, and exit code
#   - the backup stdout, stderr, and exit code (only if the gate passed)
#
# Exit code policy (so the Hermes scheduler can alert on failure):
#   passes the health gate's exit code if the gate failed,
#   otherwise the backup's exit code if the backup failed,
#   otherwise 0.
#
# All paths are converted to native Windows form via cygpath so the venv
# python (a Windows executable) receives valid arguments under MSYS bash.

set -u

# Resolve the repo root from this script's location (tools/ -> repo root).
REPO="$(cd "$(dirname "$0")/.." && pwd)"

# Venv python + scripts, as native Windows paths (avoids POSIX-path mangling
# when a Windows Python is launched from MSYS bash).
PY="$(cygpath -w "$REPO/.venv-gpu/Scripts/python.exe")"
GATE="$(cygpath -w "$REPO/tools/db_health_gate.py")"
BACKUP="$(cygpath -w "$REPO/tools/db_backup_rotate.py")"
LOGDIR="$REPO/migration-backups/sc8-logs"
mkdir -p "$LOGDIR"

TS="$(date +%Y%m%dT%H%M%S)"
LOGFILE="$LOGDIR/sc8-$TS.log"

# Start the structured log
{
  echo "timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "repo: $REPO"
  echo "------------------------------------------------------------"
} > "$LOGFILE"

# --- 1) health gate ---------------------------------------------------------
GATE_OUT="$(mktemp)"
GATE_ERR="$(mktemp)"
"$PY" "$GATE" --enforce-no-mirrors > "$GATE_OUT" 2> "$GATE_ERR"
GATE_RC=$?
{
  echo "[health-gate] exit=$GATE_RC"
  echo "--- stdout ---"; cat "$GATE_OUT"
  echo "--- stderr ---"; cat "$GATE_ERR"
  echo "------------------------------------------------------------"
} >> "$LOGFILE"

if [ "$GATE_RC" -ne 0 ]; then
  rm -f "$GATE_OUT" "$GATE_ERR"
  echo "SC8 gate: FAIL (exit=$GATE_RC); backup skipped. See $LOGFILE"
  exit "$GATE_RC"
fi

# --- 2) backup (only after a clean gate) ------------------------------------
BAK_OUT="$(mktemp)"
BAK_ERR="$(mktemp)"
"$PY" "$BACKUP" --keep 20 --max-age-days 30 \
  > "$BAK_OUT" 2> "$BAK_ERR"
BAK_RC=$?
{
  echo "[backup] exit=$BAK_RC"
  echo "--- stdout ---"; cat "$BAK_OUT"
  echo "--- stderr ---"; cat "$BAK_ERR"
  echo "------------------------------------------------------------"
} >> "$LOGFILE"

rm -f "$GATE_OUT" "$GATE_ERR" "$BAK_OUT" "$BAK_ERR"

if [ "$BAK_RC" -ne 0 ]; then
  echo "SC8 backup: FAIL (exit=$BAK_RC); gate was clean. See $LOGFILE"
  exit "$BAK_RC"
fi

echo "SC8 daily: gate PASS, backup OK. Log $LOGFILE"
exit 0
