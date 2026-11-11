#!/usr/bin/env bash
# Checkpoint 4b: private bucket, VM service account may read/write it, smoke upload with gsutil.
source "$(dirname "$0")/lib.sh"

if gcloud storage buckets describe "gs://$GCS_BUCKET" >/dev/null 2>&1; then
  echo "bucket exists: gs://$GCS_BUCKET"
else
  gcloud storage buckets create "gs://$GCS_BUCKET" \
    --location="$GCP_REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi

gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectAdmin" >/dev/null

# The coach's checkpoint is "gsutil cp works". A small committed file is enough.
gsutil cp "$REPO_ROOT/docs/scope_confirmation.md" "gs://$GCS_BUCKET/smoke/scope_confirmation.md"
gsutil ls -l "gs://$GCS_BUCKET/smoke/"
