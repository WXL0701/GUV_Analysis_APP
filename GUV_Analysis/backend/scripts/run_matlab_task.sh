#!/usr/bin/env bash
set -euo pipefail

TASK_ID="$1"
RUN_ID="$2"
MODE="$3"
ND2_PATH="$4"
PARAMS_PATH="$5"
BASE_DIR="$6"

# Default values if env vars not set
PIPELINE_ROOT="${PIPELINE_ROOT:-/home/guv_Analysis/GUV_Analysis_APP/MATLAB_Package/GUV_Image_Processor_V1.1.2}"
MATLAB_BIN="${MATLAB_BIN:-matlab}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting MATLAB Task: $TASK_ID ($MODE)"
cd "$PIPELINE_ROOT"

# -batch executes command and prints to stdout (requires MATLAB R2019a+)
# For R2018a compatibility, use -nodisplay -nosplash -nodesktop -r
child_pid=""
_term() {
  if [[ -n "${child_pid:-}" ]]; then
    kill -TERM "$child_pid" 2>/dev/null || true
  fi
  kill -TERM 0 2>/dev/null || true
}
trap _term TERM INT

"$MATLAB_BIN" -nodisplay -nosplash -nodesktop -r "try, addpath(genpath('$PIPELINE_ROOT')); addpath(genpath('$SCRIPT_DIR')); run_matlab_task('$MODE','$ND2_PATH','$PARAMS_PATH','$BASE_DIR','$PIPELINE_ROOT'); catch e, disp(getReport(e)); exit(1); end; exit(0);" &
child_pid="$!"
wait "$child_pid"
