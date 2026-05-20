#!/usr/bin/env bash
set -uo pipefail

interval="${AIDD_BINDER_MONITOR_INTERVAL:-60}"
log_file="${AIDD_BINDER_MONITOR_LOG:-/tmp/aidd-binder-monitor.log}"
run_once="${AIDD_BINDER_MONITOR_ONCE:-0}"

if [[ $# -eq 0 ]]; then
  set -- pdl1_binder_out pdl1_binder_out_simple
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."

while true; do
  {
    date -Is
    for output_dir in "$@"; do
      [[ -d "$output_dir" ]] || continue
      echo "== ${output_dir} =="
      printf "files: "
      find "$output_dir" -maxdepth 3 -type f | wc -l
      printf "pdb_files: "
      find "$output_dir" -maxdepth 3 -type f -name "*.pdb" | wc -l
      rg -n "Traceback|ERROR|Error|WARNING:.*not found|IndexError|CUDA out of memory" "$output_dir" || true
      OUTPUT_DIR="$output_dir" uv run python -c 'import asyncio, json, os
from agent.tools.binder_design_tool import binder_design_handler

text, ok = asyncio.run(
    binder_design_handler(
        {
            "operation": "rank_candidates",
            "outputs_dir": os.environ["OUTPUT_DIR"],
            "top_k": 3,
        }
    )
)
payload = json.loads(text)
print(
    {
        "ok": ok,
        "candidates": payload.get("candidate_count"),
        "passed": payload.get("passed_count"),
        "rejected": payload.get("rejected_count"),
        "top": [c.get("name") for c in payload.get("top_candidates", [])],
    }
)'
    done
    echo
  } >> "$log_file" 2>&1
  [[ "$run_once" == "1" ]] && break
  sleep "$interval"
done
