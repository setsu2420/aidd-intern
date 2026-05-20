#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <container-image>" >&2
  exit 64
fi

image="$1"
host="${AIDD_INTERN_PROTEINMCP_HOST:-192.168.4.6}"
workdir="${AIDD_INTERN_WORKDIR:-/home/xxue/aidd-intern}"
ssh_opts=(
  -o BatchMode=yes
  -o StrictHostKeyChecking=no
)

if [[ "${AIDD_INTERN_PROTEINMCP_CHECK:-}" == "1" ]]; then
  exec ssh "${ssh_opts[@]}" "$host" '
    if docker ps >/dev/null 2>&1; then
      echo docker
    elif command -v apptainer >/dev/null 2>&1; then
      echo apptainer
    else
      echo "no docker access and no apptainer on ProteinMCP host" >&2
      exit 127
    fi
  '
fi

remote_cmd=$(printf \
  'cd %q && if docker ps >/dev/null 2>&1; then exec docker run -i --rm --user "$(id -u):$(id -g)" --gpus all --ipc=host -v %q:%q -w %q %q; elif command -v apptainer >/dev/null 2>&1; then exec apptainer run --nv --bind %q:%q docker://%q; else echo "no docker access and no apptainer on ProteinMCP host" >&2; exit 127; fi' \
  "$workdir" \
  "$workdir" \
  "$workdir" \
  "$workdir" \
  "$image" \
  "$workdir" \
  "$workdir" \
  "$image")

exec ssh "${ssh_opts[@]}" "$host" "$remote_cmd"
