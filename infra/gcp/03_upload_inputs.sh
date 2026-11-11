#!/usr/bin/env bash
# Upload the two coach files so the VM can pull them inside Google's network.
# gcloud storage cp checks the CRC32C after upload, so a broken upload fails here.
source "$(dirname "$0")/lib.sh"

TAR="$REPO_ROOT/data/raw/glamira_ubl_oct2019_nov2019.tar.gz"
BIN="$REPO_ROOT/data/reference/IP-COUNTRY-REGION-CITY.BIN"

for file in "$TAR" "$BIN"; do
  [[ -f "$file" ]] || { echo "missing $file" >&2; exit 1; }
done

gcloud storage cp "$TAR" "gs://$GCS_BUCKET/raw/"
gcloud storage cp "$BIN" "gs://$GCS_BUCKET/reference/"
gcloud storage ls -l "gs://$GCS_BUCKET/raw/" "gs://$GCS_BUCKET/reference/"
