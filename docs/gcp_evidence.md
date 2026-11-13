# GCP evidence

Paste the real output of each command here after every checkpoint.
Never paste passwords, billing account numbers, emails, or URIs that contain a password.

## Checkpoint 4 — project, APIs, bucket

- Project id: `glamira-p05-loclt`
- Region / zone: `asia-southeast1` / `asia-southeast1-b`
- Bucket: `glamira-raw-data-asia-southeast1-glamira-p05-loclt`

```text
# gcloud services list --enabled --filter="name:(compute OR storage OR bigquery)" --format="value(config.name)"
bigquery.googleapis.com
bigqueryconnection.googleapis.com
bigquerydatapolicy.googleapis.com
bigquerydatatransfer.googleapis.com
bigquerymigration.googleapis.com
bigqueryreservation.googleapis.com
bigquerystorage.googleapis.com
compute.googleapis.com
storage-api.googleapis.com
storage-component.googleapis.com
storage.googleapis.com

# gsutil ls -l gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/smoke/
      5297  2026-11-11T13:14:34Z  gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/smoke/scope_confirmation.md
TOTAL: 1 objects, 5297 bytes (5.17 KiB)
```

## Inputs on GCS

```text
# gcloud storage ls -l gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/raw/ gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/reference/
5495914358  2026-11-11T13:40:55Z  gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/raw/glamira_ubl_oct2019_nov2019.tar.gz
TOTAL: 1 objects, 5495914358 bytes (5.12GiB)
 143974289  2026-11-11T13:41:03Z  gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/reference/IP-COUNTRY-REGION-CITY.BIN
TOTAL: 1 objects, 143974289 bytes (137.30MiB)
```

## Checkpoint 6 — MongoDB VM reachable from my machine

- VM: `glamira-mongo`, `e2-standard-4`, 100 GB, Ubuntu 24.04, MongoDB 8.0
- External IP: `34.21.248.100` (ephemeral; changes if the VM is stopped)
- Firewall: `glamira-mongo-from-my-ip`, tcp:27017 from `113.177.138.20/32`

```text
# ping from my machine (pymongo admin ping + server_info version)
LOCAL_PING {'ok': 1.0} 8.0.38
```

## Checkpoint 7 — load of 41 million rows

```text
# last lines of data/staging/load_vm.log on the VM
scanned=41,432,473 inserted=41,432,473 duplicates=0 mongo_count=41,432,473 completed=True disk_stop=False elapsed=2720.4s
ip counts: data/staging/ip_event_counts.tsv (3,239,628 distinct)
count check: source=41,432,473 mongo=41,432,473 MATCH

# collStats / estimated_document_count on the VM
glamira_raw 41432473

# one document showing _loaded_at and _source_file
{'_id': ObjectId('5ed8cb2bc671fc36b74653ad'), 'collection': 'view_product_detail', '_loaded_at': datetime.datetime(2026, 11, 12, 15, 7, 0, 796000), '_source_file': 'glamira_ubl_oct2019_nov2019.tar.gz'}

# index list
['_id_', 'collection_1', 'ip_1', 'product_id_1', 'time_stamp_1', 'viewing_product_id_1']
```

`_id` keeps the source ObjectId, so re-running the load does not duplicate rows.

## Checkpoint 8 — IP

```text
# ip_geo collStats / estimated_document_count on the VM
ip_geo 3239628

# docs/ip_coverage.md
Events with an IP string          41,432,473
Distinct IP strings                3,239,628
Events with public IPv4           41,422,559
Events whose public IPv4 resolved 40,966,752
Resolve rate on public IPv4            98.90%
checkout_success events               26,079
checkout_success resolved             25,860
checkout_success resolve rate          99.16%

# gcloud storage ls -l gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/exports/
   1604005  2026-11-13T09:25:51Z  gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/exports/product_urls.csv
TOTAL: 1 objects, 1604005 bytes (1.53MiB)
# ip_geo.csv is not on GCS yet — that file is written by `enrich export-csv ip_geo` (bài 17), after crawl.
```

## Checkpoint 9 — product URL seed

```text
# VM: uv run python -m src.cli enrich extract-products
scanned=24,192,540 kept=21,942,848 products=19,093 wrote data/exports/product_urls.csv
  view_product_detail: scanned=10,944,427 kept=10,839,287
  select_product_option: scanned=8,844,342 kept=8,732,891
  select_product_option_quality: scanned=2,231,825 kept=2,200,561
  add_to_cart_action: scanned=187,991 kept=169,259
  back_to_product_action: scanned=561 kept=522
  product_detail_recommendation_visible: scanned=1,302,362 kept=0
  product_detail_recommendation_noticed: scanned=490,788 kept=0
  view_all_recommend: scanned=33,664 kept=0
  product_view_all_recommend_clicked: scanned=16,682 kept=0

# wc -l data/exports/product_urls.csv
19094
# header + 19093 data rows

# cut -d, -f1 data/exports/product_urls.csv | sort | uniq -d | wc -l
0

# gcloud storage ls -l gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/exports/
   1604005  2026-11-13T09:25:51Z  gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/exports/product_urls.csv
```

## Checkpoint 11 — products

```text
# product-status output: expected missing_from_mongo=0
# products countDocuments on the VM: expected 19093
# number with a name:
# gcloud storage ls gs://<bucket>/exports/products.csv
```

Not filled: crawl has not run. VM `products` count is currently `0`.
