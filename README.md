# Glamira Project 05 — Data Source

Batch pipeline that turns the Glamira behaviour-log dump into three queryable MongoDB collections on GCP:

- **`glamira_raw`**: every event from the mongodump, loaded unchanged.
- **`ip_geo`**: country, region and city for each distinct IP.
- **`products`**: name, type and price for each product id seen in the logs.

Project 06 builds on these collections. BigQuery, dbt and Looker are out of scope here.

| Result | Value |
|---|---:|
| Events loaded (`glamira_raw`) | 41,432,473 (equals the source count) |
| Distinct IPs resolved (`ip_geo`) | 3,239,628 |
| `checkout_success` events with a country | 25,860 / 26,079 (99.16%) |
| Product ids (`products`) | 19,093 |
| Products with a name | 18,662 (97.7%); the other 431 are removed from the store |
| Real event time range | 2020-04-01 → 2020-06-04 UTC (the file name says Oct–Nov 2019) |

## Architecture

```
 laptop (uv, gcloud, Chrome)                         GCP project (asia-southeast1)
 ───────────────────────────                         ──────────────────────────────────────────
 glamira_ubl_*.tar.gz ──┐                             GCS bucket (private)
 IP-COUNTRY-…BIN ───────┴── 03_upload_inputs.sh ───▶   raw/  reference/  exports/
                                                          │ fetch_inputs.sh (service account, no key)
 Phase 0 scan (explore) ──▶ docs/*.md                     ▼
                                                     VM glamira-mongo (e2-standard-4, 100 GB)
 product crawl (Playwright + Chrome) ─── SSH tunnel ─▶   MongoDB 8.0, auth on
   localhost:27018 ─────────────────────────────────▶    db glamira: glamira_raw, ip_geo, products
                                                          ▲ ingest load-mongo, enrich ip,
                                                            extract-products, export-csv (run on the VM)
```

Heavy, data-local work (loading 41 M events, IP lookup, CSV export) runs **on the VM**, next to MongoDB. The product crawl runs **on the laptop**: the store's CDN blocks datacenter traffic and plain HTTP clients, so it needs a real Chrome on a home network. The crawl reaches MongoDB through an SSH tunnel, so a new home or office IP does not need a firewall change.

## Data flow

| Step | Command | Reads | Writes |
|---|---|---|---|
| Profile the dump | `explore null-profile`, `explore quality-report` | tar.gz (streamed, never extracted) | `docs/null_profile.md`, `docs/data_quality_report.md` |
| Load raw events | `ingest load-mongo` | tar.gz | `glamira_raw` + 5 indexes, `_loaded_at`, `_source_file` |
| IP geolocation | `enrich ip` | distinct `glamira_raw.ip`, IP2Location BIN | `ip_geo`, `docs/ip_coverage.md` |
| Product URL seed | `enrich extract-products` | product events in `glamira_raw` | `data/exports/product_urls.csv` (one URL per product id), copied to GCS |
| Product crawl | `python -m src.enrich.reactdata` | seed CSV, store JSON endpoint | `products`, `docs/crawl_react.md` |
| Completeness check | `enrich product-status` | seed CSV, `products` | exit 0 when every seed id is in Mongo |
| Export | `enrich export-csv ip_geo` / `products` | collections | CSV, then copied to `gs://<bucket>/exports/` |

Every step can be re-run. Documents keep their source `_id` (ObjectId for events, the IP for `ip_geo`, the product id for `products`), so a second run upserts or skips rows and never duplicates them.

## How the hard parts work

- **Streaming the 31 GB dump.** `src/stream/tar_bson.py` reads the gzip tar member by member, including GNU base-256 size headers. `src/stream/bson_lite.py` splits the member on each document's int32 length prefix and reads only top-level fields. Nothing is written to disk. Distinct counts use a HyperLogLog sketch (`src/explore/sketch.py`), so memory stays flat.
- **Loading.** `insert_many(ordered=False)` in batches of 10,000. Duplicate-key errors on re-runs are counted and skipped. The run ends with a count check against the source.
- **IP lookup.** The service gets distinct IPs from Mongo. Private, loopback, IPv6 and invalid addresses are stored with a `status` and are not looked up. Public IPv4 addresses go through the IP2Location DB3 BIN, a sorted range table searched by binary search.
- **Product crawl.** For each product id, the crawler opens `https://www.glamira.co.uk/productcustomizer/reactdata/index/id/<id>/?currency=GBP` in Chrome. robots.txt allows this path. Ids missing on co.uk are retried on `www.glamira.com`; a 404 on both stores marks the product `not_found`.
  - Failures escalate: retry in the same tab, then reopen the tabs and slow down, then relaunch Chrome.
  - The crawl resumes from MongoDB state: products already named or `not_found` are skipped. Network loss, a laptop reboot or a VM stop costs nothing.

## Repository layout

```
src/
  cli.py                  entry point: explore | ingest | enrich
  config.py, db.py        .env settings, Mongo client
  stream/                 tar + BSON streaming (stdlib only)
  explore/                Phase 0 profile, HyperLogLog, Markdown renderers
  ingest/load_mongo.py    dump → glamira_raw
  enrich/
    ip_lookup.py          IP → ip_geo
    urls.py               product URL rules
    extract_products.py   seed CSV from glamira_raw
    reactdata.py          product crawl (JSON endpoint, used for the final data)
    crawl.py              first HTML crawl (pilot, kept for the record)
    export_csv.py         CSV export, product-status
infra/gcp/
  gcp.env.example         project, region, bucket, VM settings (copy to gcp.env)
  00_write_env.sh … 04_vm.sh   project + APIs, bucket, upload, VM + firewall
  vm/install_mongo.sh     run on the VM: MongoDB 8.0 with auth
  vm/fetch_inputs.sh      run on the VM: pull the inputs from GCS
  tunnel.sh               SSH tunnel localhost:27018 → VM:27017, reopens on drop
  resume.sh               start of every session: VM up, tunnel up, .env checked
  reconnect.sh            open 27017 to the current IP (if not using the tunnel)
tests/                    unittest, no network and no Mongo needed
docs/                     checkpoint deliverables (below)
```

## Setup

Requirements: Python 3.12+ with [uv](https://docs.astral.sh/uv/), the Google Cloud SDK (`gcloud`), tmux, and Google Chrome (crawl machine only).

```bash
uv sync
uv run python -m unittest discover -s tests       # 43 tests, about 0.1 s
cp .env.example .env                               # paths, MONGO_URI, crawl settings
cp infra/gcp/gcp.env.example infra/gcp/gcp.env     # project id, bucket, VM
```

The coach's two input files are **not** in git. Put them at:

- `data/raw/glamira_ubl_oct2019_nov2019.tar.gz`: the mongodump.
- `data/reference/IP-COUNTRY-REGION-CITY.BIN`: IP2Location DB3, header dated 2016-11-29.

Never commit `.env`, `infra/gcp/gcp.env` or anything under `data/`; `.gitignore` covers them.

## Run

**1. Phase 0 (laptop, no Mongo).**

```bash
uv run python -m src.cli explore null-profile
uv run python -m src.cli explore quality-report
```

**2. GCP (laptop).** The billing account must be linked to the project in the console first.

```bash
bash infra/gcp/00_write_env.sh
bash infra/gcp/01_project.sh       # gcloud project, APIs, VM service account
bash infra/gcp/02_bucket.sh        # private bucket + smoke upload
bash infra/gcp/03_upload_inputs.sh # tar.gz + BIN → gs://<bucket>/
bash infra/gcp/04_vm.sh            # VM + firewall (27017 open to this IPv4 only)
```

**3. Load and enrich (on the VM, inside tmux).**

```bash
bash infra/gcp/vm/install_mongo.sh
bash infra/gcp/vm/fetch_inputs.sh
uv run python -m src.cli ingest load-mongo
uv run python -m src.cli enrich ip
uv run python -m src.cli enrich extract-products
gcloud storage cp data/exports/product_urls.csv gs://<bucket>/exports/
```

**4. Product crawl (laptop).**

```bash
bash infra/gcp/resume.sh                          # VM running, tunnel up, .env → 127.0.0.1:27018
gcloud storage cp gs://<bucket>/exports/product_urls.csv data/exports/
uv run python -m src.enrich.reactdata --limit 0   # whole seed; Ctrl+C and re-run any time
uv run python -m src.enrich.reactdata --report-only
uv run python -m src.cli enrich product-status    # expect missing_from_mongo=0
```

Useful flags: `--retry-missing` asks again for products marked `not_found`. `--refresh-old` re-fetches documents from the HTML pilot and placeholder categories. `--min-delay` / `--max-delay` set the pause between requests.

**5. Export (on the VM).**

```bash
uv run python -m src.cli enrich export-csv ip_geo
uv run python -m src.cli enrich export-csv products
gcloud storage cp data/exports/*.csv gs://<bucket>/exports/
```

**Cost.** Stop the VM when you are not using it: `gcloud compute instances stop glamira-mongo --zone asia-southeast1-b`. The disk and data stay; `resume.sh` starts the VM again.

## Checkpoints and evidence

| # | Deliverable | Where |
|---|---|---|
| 1 | Null % by event type | `docs/null_profile.md` (full scan, 41,432,473 documents) |
| 2 | Data quality report | `docs/data_quality_report.md` |
| 3 | Scope confirmation | `docs/scope_confirmation.md` (GO for IP lookup and product crawl) |
| 4 | GCP project + bucket | `infra/gcp/01_project.sh`, `02_bucket.sh`; output in `docs/gcp_evidence.md` |
| 5 | Python environment | `pyproject.toml`, `uv.lock` |
| 6–7 | MongoDB VM + raw load | `glamira_raw` = 41,432,473, equal to the source; `docs/gcp_evidence.md` |
| 8 | IP geolocation | `docs/ip_coverage.md`: 98.90% of public-IPv4 events, 99.16% of `checkout_success` |
| 9 | Product URL seed | 19,093 product ids, one URL each |
| 10 | Crawl pilot | `docs/crawl_pilot.md` (100 products, HTML crawl) |
| 11 | Full crawl + dictionary + export | `docs/crawl_react.md`, `docs/data_dictionary.md`, CSVs on GCS |
| — | Handoff | `docs/handoff_to_project06.md` |

## Decisions and deviations

- **MongoDB 8.0 on a Compute Engine VM** (the coach's setup suggests 16–32 GB RAM): data stays in one region next to the bucket, and the load reads the dump from local disk.
- **Collection names**: `glamira_raw`, `ip_geo`, `products`. The raw field `collection` is an event type, not a Mongo collection.
- **Product source**: the HTML product pages were used for the pilot only. They were slow and the CDN blocked them under load. The final data comes from the store's reactdata JSON endpoint, which robots.txt allows and which returns name, type, price and SKU. `category` is the JSON's `product_type`, because its `category_name` is empty. Non-jewellery items such as `Shipping Label Fee` get `category = null`.
- **No currency conversion** in this project. Prices are strings in the event's or product's `currency`.

## Known data limits

- The real date range (April–June 2020) does not match the file name.
- `checkout_success` has no top-level `product_id`; use `cart_products[].product_id` (int → string) to join to `products._id`.
- IP2Location DB3 dates from 2016: the country is reliable, the city is approximate, and there is no latitude/longitude.
- 431 product ids no longer exist on any store; they are kept with `not_found = true`.

Details: `docs/data_quality_report.md`, `docs/data_dictionary.md`.
