#!/usr/bin/env bash
# Run ON THE VM from the repo root. Pulls the two coach files from the bucket into data/.
# Usage: GCS_BUCKET=glamira-raw-data-... bash infra/gcp/vm/fetch_inputs.sh
set -euo pipefail
: "${GCS_BUCKET:?set GCS_BUCKET}"

mkdir -p data/raw data/reference data/staging data/exports
gcloud storage cp "gs://$GCS_BUCKET/raw/glamira_ubl_oct2019_nov2019.tar.gz" data/raw/
gcloud storage cp "gs://$GCS_BUCKET/reference/IP-COUNTRY-REGION-CITY.BIN" data/reference/
ls -l data/raw data/reference
df -h .
