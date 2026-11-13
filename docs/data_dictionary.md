# Data dictionary

Schema-on-read. Phần field raw lấy từ một lần quét hết `summary.bson`. Ba collection dưới đây nằm trên MongoDB VM (GCP), database `glamira`. Tra IP đã xong; crawl catalog chưa chạy — số `products` và tỉ lệ có tên điền sau `enrich product-status`.

Scan: **full member**. Yêu cầu: entire member. Documents: **41,432,473**. Thời điểm: 2026-11-11T03:10:55Z.

## File

| Path | Vai trò |
|---|---|
| `glamira_ubl_oct2019_nov2019.tar.gz` | gzip ustar, mongodump Countly |
| `dump/countly/summary.metadata.json` | options + indexes của collection nguồn |
| `dump/countly/summary.bson` | BSON documents, nối tiếp nhau |
| `data/reference/IP-COUNTRY-REGION-CITY.BIN` | IP2Location DB3. Tra IP → country, region, city |

## Collection trên Mongo (VM GCP)

| Tên | Số document | Ghi chú |
|---|---|---|
| `glamira.glamira_raw` | 41,432,473 | Một event. `_id` là ObjectId gốc. Index: `collection`, `time_stamp`, `ip`, `product_id` (sparse), `viewing_product_id` (sparse) |
| `glamira.ip_geo` | 3,239,628 | Một IP. `_id` là chuỗi IP. Join `glamira_raw.ip` = `ip_geo._id` |
| `glamira.products` | 0 (chưa crawl) | Seed 19,093 id trong `data/exports/product_urls.csv`. Một `product_id` một document sau crawl |

Đừng map field `collection` thành tên collection Mongo.

## Field raw đã gặp

Presence = số document có key, kể cả giá trị rỗng/null. Nullish nằm ở `docs/null_profile.md`.

| Field | Docs có key | % | Ghi chú Phase 0 |
|---|---:|---:|---|
| `_id` | 41,432,473 | 100.00% | ObjectId nguồn. Dùng làm khóa tự nhiên khi load. |
| `time_stamp` | 41,432,473 | 100.00% | Epoch giây (int). Mốc canonical; khớp ObjectId trong scan này. |
| `ip` | 41,432,473 | 100.00% | Public IPv4 41,422,559; IPv6 4,009. Không có country/city. |
| `user_agent` | 41,432,473 | 100.00% |  |
| `resolution` | 41,432,473 | 100.00% |  |
| `user_id_db` | 41,432,473 | 100.00% | Rỗng với khách chưa đăng nhập. |
| `device_id` | 41,432,473 | 100.00% | UUID thiết bị. |
| `api_version` | 41,432,473 | 100.00% |  |
| `store_id` | 41,432,473 | 100.00% | Mã cửa hàng, string. 86 giá trị trong scan này. |
| `local_time` | 41,432,473 | 100.00% | Wall clock string, không zero-pad. Không dùng làm mốc doanh thu. |
| `show_recommendation` | 41,432,473 | 100.00% |  |
| `current_url` | 41,432,473 | 100.00% | URL cửa hàng theo TLD. Trang sản phẩm thường chứa `.html`. |
| `referrer_url` | 41,432,473 | 100.00% |  |
| `email_address` | 41,432,473 | 100.00% | PII. Không đưa vào report hay git. |
| `collection` | 41,432,473 | 100.00% | Event type (view_product_detail, checkout, …). |
| `option` | 34,300,549 | 82.79% | Khi thì array, khi thì document. |
| `product_id` | 22,242,720 | 53.68% | Top-level là string khi có. Trong cart_products (sample checkout_success) là int. Không có name/category. |
| `cat_id` | 12,043,106 | 29.07% | Giá trị dùng được: 258. Không dùng làm category. |
| `collect_id` | 12,043,106 | 29.07% |  |
| `recommendation` | 10,944,427 | 26.42% |  |
| `utm_source` | 10,944,427 | 26.42% |  |
| `utm_medium` | 10,944,427 | 26.42% |  |
| `viewing_product_id` | 1,989,052 | 4.80% | Chủ yếu event recommendation, không phải trang detail. |
| `cart_products` | 457,696 | 1.10% | Array line item của checkout. `product_id` nằm ở phần tử con. |
| `recommendation_product_id` | 243,296 | 0.59% | Id phụ trên event recommendation. Không thay `product_id`. |
| `key_search` | 238,308 | 0.58% |  |
| `recommendation_clicked_position` | 204,773 | 0.49% |  |
| `price` | 187,901 | 0.45% | Số document bằng đúng `add_to_cart_action`. Không có ở top-level của `checkout_success`. |
| `currency` | 187,901 | 0.45% | Đi cùng top-level `price` trên add-to-cart. |
| `is_paypal` | 187,901 | 0.45% |  |
| `order_id` | 114,619 | 0.28% | Giá trị non-empty: 26,079, khớp số `checkout_success`. Key còn xuất hiện dạng rỗng trên `checkout`. |
| `recommendation_product_position` | 38,523 | 0.09% |  |

## Quy tắc làm sạch đã áp dụng

- Nullish: missing + BSON null + `""`.
- `product_id` chuẩn hóa về string khi extract catalog.
- IP private / empty / invalid không lookup BIN; vẫn có document trong `ip_geo` với `status` tương ứng.
- Join catalog trên `product_id` string (`products._id`).

## `glamira_raw` — một document một event

Field raw như bảng trên, cộng hai field kiểm toán lúc nạp:

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `_id` | ObjectId | ObjectId nguồn trong dump. Nạp lại không nhân đôi dòng |
| `_loaded_at` | datetime (UTC) | Một giá trị cho cả lần nạp |
| `_source_file` | string | Tên archive, `glamira_ubl_oct2019_nov2019.tar.gz` |

Index: `collection`, `time_stamp`, `ip`, `product_id` (sparse), `viewing_product_id` (sparse). Số document: 41,432,473.

## `ip_geo` — một document một IP

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `_id` | string | Địa chỉ IP. Khóa join |
| `status` | string | `ok`, `not_found`, `private`, `ipv6`, `invalid` |
| `country_code` | string | ISO 2 chữ, chỉ khi `status = ok` |
| `country_name` | string | |
| `region` | string | |
| `city` | string | Gần đúng |
| `events` | int | Số event từ IP này |
| `lookup_at` | datetime (UTC) | Thời điểm tra |

Nguồn: IP2Location DB3, header 2016-11-29. Country tin được; city gần đúng (bảng tra cũ hơn event khoảng 3,5 năm). DB3 không có vĩ độ/kinh độ. Số document: 3,239,628. `checkout_success` resolve 99.16% (25,860 / 26,079). Chi tiết: `docs/ip_coverage.md`.

## `products` — một document một product id

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `_id` | string | `product_id` dạng chữ. Khóa join |
| `product_id` | string | Trùng `_id` |
| `name` | string | JSON-LD `Product.name`, không có thì `h1` của trang |
| `category` | string | JSON-LD, không có thì breadcrumb cuối |
| `price` | string | Giá trên trang, giữ nguyên chữ |
| `currency` | string | Đơn vị tiền khi trang có |
| `description`, `image_url`, `brand`, `sku`, `material`, `color`, `availability`, `gtin`, `mpn`, `weight` | string | JSON-LD khi có |
| `url` | string | Trang đã mở thật (có thể là URL catalog) |
| `source_url` | string | URL trong seed CSV |
| `http_status` | int | HTTP status của trang |
| `error` | string | Lỗi fetch hoặc ghi chú fallback, không thì null |
| `crawled_at` | datetime (UTC) | Thời điểm crawl |

Seed: 19,093 id (`data/exports/product_urls.csv`). Collection trên VM hiện **0** document. Tỉ lệ có `name`: điền sau `enrich product-status` (kỳ vọng `missing_from_mongo=0`, mẫu số 19,093).

## Join

- Nước của một event: `glamira_raw.ip = ip_geo._id`.
- Sản phẩm của một event: `glamira_raw.product_id = products._id`. Với `checkout_success`, lấy `cart_products[].product_id` (int → string).

## Lỗi chất lượng đã biết

- Khoảng ngày thật là 2020-04-01 → 2020-06-04 UTC, không phải Oct–Nov 2019 như tên file.
- `checkout_success` không có `product_id` hay `price` ở top-level; cả hai nằm trong `cart_products`.
- Giá là chuỗi theo `currency`. P05 không quy đổi FX.
- Chi tiết: `docs/data_quality_report.md`.
