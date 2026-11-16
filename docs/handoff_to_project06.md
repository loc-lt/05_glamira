# Handoff to Project 06

## What exists

| Collection (`glamira` on the GCP MongoDB VM) | Documents | Grain |
|---|---:|---|
| `glamira_raw` | 41,432,473 | One event |
| `ip_geo` | 3,239,628 | One IP |
| `products` | 19,093 | One product id |

## Files on GCS

| Path | Content |
|---|---|
| `gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/raw/glamira_ubl_oct2019_nov2019.tar.gz` | Original mongodump |
| `gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/reference/IP-COUNTRY-REGION-CITY.BIN` | IP2Location DB3 |
| `gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/exports/product_urls.csv` | One URL per product id (crawl seed) |
| `gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/exports/ip_geo.csv` | Copy of `ip_geo` |
| `gs://glamira-raw-data-asia-southeast1-glamira-p05-loclt/exports/products.csv` | Copy of `products` |

## How to join

- Country of an event: `glamira_raw.ip = ip_geo._id`.
- Product of an event: `glamira_raw.product_id = products._id`. For `checkout_success`, use `cart_products[].product_id` converted from int to string.
- Revenue: sum of `cart_products[].price` on `checkout_success`, split by `currency`.

## Limits

- IP database is DB3 from 2016-11-29: no latitude/longitude, city is approximate.
- Prices are not converted between currencies.
- Products with a name: 18662.
- Real data range: 2020-04-01 → 2020-06-04 UTC.

## Re-run

See `README.md`. Every step is idempotent: re-loading skips duplicate `_id`s, IP lookup and crawl upsert by `_id`.
