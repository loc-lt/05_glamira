# GCP evidence

Paste the real output of each command here after every checkpoint.
Never paste passwords, billing account numbers, emails, or URIs that contain a password.

## Checkpoint 4 — project, APIs, bucket

- Project id:
- Region / zone: `asia-southeast1` / `asia-southeast1-b`
- Bucket:

```text
# output: gcloud services list --enabled (compute / storage / bigquery)

# output: gsutil ls -l gs://<bucket>/smoke/
```

## Inputs on GCS

```text
# output: gcloud storage ls -l gs://<bucket>/raw/ gs://<bucket>/reference/
# expected: 5495914358 bytes for the tar, 143974289 bytes for the BIN
```

## Checkpoint 6 — MongoDB VM reachable from my machine

- VM: `glamira-mongo`, `e2-standard-4`, 100 GB, Ubuntu 24.04, MongoDB 8.0
- Firewall: `glamira-mongo-from-my-ip`, tcp:27017 from a single `/32` IP

```text
# ping output from my machine: {'ok': 1.0} and version 8.0.x
```

## Checkpoint 7 — load of 41 million rows

```text
# last line of data/staging/load_vm.log: count check: source=41,432,473 mongo=41,432,473 MATCH
# countDocuments output: expected glamira_raw 41432473
# one document showing _loaded_at and _source_file
# index list
```

`_id` keeps the source ObjectId, so re-running the load does not duplicate rows.

## Checkpoint 8 — IP

```text
# ip_geo countDocuments: expected 3239628
# checkout_success resolve rate: expected 99.16%
# gcloud storage ls gs://<bucket>/exports/ip_geo.csv
```

## Checkpoint 9 — product URL seed

```text
# wc -l data/exports/product_urls.csv: expected 19094 (header + 19093)
# duplicate ids: expected 0
```

## Checkpoint 11 — products

```text
# product-status output: expected missing_from_mongo=0
# products countDocuments on the VM: expected 19093
# number with a name:
# gcloud storage ls gs://<bucket>/exports/products.csv
```
