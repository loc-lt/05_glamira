#!/usr/bin/env bash
# Copy gcp.env.example → gcp.env and fill Project ID from gcloud when possible.
set -euo pipefail
GCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLE="$GCP_DIR/gcp.env.example"
ENV_FILE="$GCP_DIR/gcp.env"

if [[ ! -f "$EXAMPLE" ]]; then
  echo "missing $EXAMPLE" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$EXAMPLE" "$ENV_FILE"
  echo "created $ENV_FILE"
fi

project=""
if command -v gcloud >/dev/null 2>&1; then
  project="$(gcloud config get-value project 2>/dev/null || true)"
  if [[ "$project" == "(unset)" ]]; then
    project=""
  fi
fi

if [[ -n "$project" ]]; then
  python3 - "$ENV_FILE" "$project" << 'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
project = sys.argv[2]
text = path.read_text(encoding="utf-8")
lines = []
for line in text.splitlines():
    if line.startswith("GCP_PROJECT_ID="):
        line = f"GCP_PROJECT_ID={project}"
    elif line.startswith("GCS_BUCKET=") and "your-project-id" in line:
        line = line.replace("your-project-id", project)
    lines.append(line)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
  echo "filled GCP_PROJECT_ID=$project"
else
  echo "gcloud has no project. Set GCP_PROJECT_ID in $ENV_FILE"
  echo "Console: project picker → ID. Machine: gcloud config get-value project"
fi

echo
echo "----- $ENV_FILE -----"
grep -v '^#' "$ENV_FILE" | grep -v '^$'
echo "---------------------"
if grep -q 'your-project-id' "$ENV_FILE"; then
  echo "still your-project-id: set GCP_PROJECT_ID and the GCS_BUCKET suffix" >&2
  exit 1
fi
echo "done. Do not commit this file."
