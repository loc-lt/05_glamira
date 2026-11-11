#!/usr/bin/env bash
# Shared by every script in infra/gcp. Loads gcp.env and fails on missing values.
set -euo pipefail

GCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$GCP_DIR/../.." && pwd)"

if [[ ! -f "$GCP_DIR/gcp.env" ]]; then
  echo "missing $GCP_DIR/gcp.env. Run: bash infra/gcp/00_write_env.sh" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source "$GCP_DIR/gcp.env"
set +a

for name in GCP_PROJECT_ID GCP_REGION GCP_ZONE GCS_BUCKET GCP_SA_NAME VM_NAME VM_MACHINE_TYPE VM_DISK_SIZE VM_TAG; do
  if [[ -z "${!name:-}" || "${!name}" == *your-project-id* ]]; then
    echo "set $name in infra/gcp/gcp.env" >&2
    exit 1
  fi
done

SA_EMAIL="${GCP_SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
export GCP_DIR REPO_ROOT SA_EMAIL
