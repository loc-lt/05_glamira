# Data dictionary

Schema-on-read. Phần "Field raw" mô tả **raw event** trong `summary.bson`. Phần "Collection sau load và enrich" mô tả 3 collection trên MongoDB VM sau checkpoint 7–11.

Scan: **full member**. Yêu cầu: entire member. Documents: **41,432,473**. Thời điểm: 2026-11-11T03:10:55Z.

## File nguồn

| Path | Vai trò |
|---|---|
| `glamira_ubl_oct2019_nov2019.tar.gz` | gzip ustar, mongodump Countly |
| `dump/countly/summary.metadata.json` | options + indexes của collection nguồn |
| `dump/countly/summary.bson` | BSON documents, nối tiếp nhau |
| `IP-COUNTRY-REGION-CITY.BIN` | IP2Location DB3, dùng để tra `ip_geo` (checkpoint 8) |

## Collection trên MongoDB (database `glamira`)

| Tên | Số document | Ghi chú |
|---|---:|---|
| `glamira_raw` | 41,432,473 | Một document = một event |
| `ip_geo` | 3,239,628 | Một document = một IP |
| `products` | 19,093 | Một document = một product id |

Đừng map field `collection` thành tên collection Mongo. Field đó là loại event.

## Field raw đã gặp

Presence = số document có key, kể cả giá trị rỗng/null. Nullish nằm ở `docs/null_profile.md`.

| Field | Docs có key | % | Ghi chú |
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

## Quy tắc làm sạch

- Nullish: missing + BSON null + `""`.
- `product_id` chuẩn hóa về string khi extract catalog.
- IP private / empty / invalid không lookup BIN.
- Join catalog trên `product_id` string.

## Collection sau load và enrich

### `glamira_raw` — một document = một event

Gồm các field raw ở trên, cộng thêm hai field ghi lại lần load:

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `_id` | ObjectId | ObjectId gốc trong dump. Load lại không bị trùng dòng |
| `_loaded_at` | datetime (UTC) | Mỗi lần load có một giá trị |
| `_source_file` | string | Tên file nén, `glamira_ubl_oct2019_nov2019.tar.gz` |

Index: `collection`, `time_stamp`, `ip`, `product_id` (sparse), `viewing_product_id` (sparse). Số document: 41,432,473.

### `ip_geo` — một document = một IP

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `_id` | string | Địa chỉ IP. Khóa join |
| `status` | string | `ok`, `not_found`, `private`, `ipv6`, `invalid` |
| `country_code` | string | Mã ISO 2 ký tự, chỉ có khi `status = ok` |
| `country_name` | string | Tên quốc gia |
| `region` | string | Vùng / bang |
| `city` | string | Thành phố, chỉ gần đúng |
| `events` | int | Số event đến từ IP này |
| `lookup_at` | datetime (UTC) | Thời điểm tra |

Nguồn: IP2Location DB3, header 2016-11-29. Country tin được; city chỉ gần đúng (bảng tra cũ hơn event khoảng 3,5 năm). DB3 không có vĩ độ/kinh độ. Số document: 3,239,628. Tỉ lệ resolve của `checkout_success`: 99.16%.

### `products` — một document = một product id

Do `python -m src.enrich.reactdata` điền, lấy từ `https://www.glamira.co.uk/productcustomizer/reactdata/index/id/<id>/?currency=GBP`, rồi thử `www.glamira.com` cho các id không có trên co.uk. Một vài document đầu tiên lấy từ bản crawl HTML (`src/enrich/crawl.py`) nên không có `source`.

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `_id` | string | `product_id` dạng string. Khóa join |
| `product_id` | string | Giống `_id` |
| `name` | string | Tên sản phẩm tiếng Anh, ví dụ `Engagement Ring Palmier`. Null khi `not_found` |
| `category` | string | Loại sản phẩm: `wedding_ring`, `ring`, `pendant`, `earring`, `bracelet`, `necklace`, `cufflink`, `nose_pin`, `brooch`, `wedding_set`, … (chép từ `product_type`; field `category_name` của JSON luôn rỗng). Null với món không phải trang sức mà site không gán loại (placeholder `--_select_--` hoặc `-1`, ví dụ `Shipping Label Fee`) |
| `product_type` | string | Cùng giá trị với `category` |
| `collection` | string | Bộ sưu tập thiết kế, ví dụ `halo` |
| `gender` | string | `women`, `men`, … |
| `attribute_set` | string | Ví dụ `diamonds` |
| `sku` | string | Mã thiết kế, ví dụ `PALMIER` |
| `price` | string | Giá gốc theo `currency` của cấu hình mặc định |
| `currency` | string | `GBP` trên co.uk |
| `min_price`, `max_price` | string | Khoảng giá trên mọi cấu hình |
| `image_url` | string | Ảnh đầu tiên của sản phẩm |
| `url` | string | URL JSON đã trả kết quả |
| `source_url` | string | URL trong file seed CSV |
| `source` | string | `reactdata` |
| `host` | string | Cửa hàng đã trả kết quả: `www.glamira.co.uk` hoặc `www.glamira.com` |
| `http_status` | int | 200, hoặc 404 với sản phẩm đã gỡ |
| `error` | string | `Product not found` khi đã gỡ, ngược lại null |
| `not_found` | bool | True khi không cửa hàng nào còn bán sản phẩm |
| `crawled_at` | datetime (UTC) | Thời điểm tải |

Số document: 19,093 (mỗi id trong seed một document). Có tên: 18,662 (97.74%). 431 sản phẩm còn lại không có tên, phần lớn là sản phẩm `not_found` (cả co.uk lẫn .com đều đã gỡ).

## Join

- Quốc gia của một event: `glamira_raw.ip = ip_geo._id`.
- Sản phẩm của một event: `glamira_raw.product_id = products._id`. Với `checkout_success`, dùng `cart_products[].product_id`, đổi từ int sang string.

## Vấn đề chất lượng đã biết

- Khoảng thời gian thật là 2020-04-01 → 2020-06-04 UTC, không phải Oct–Nov 2019 như tên file.
- `checkout_success` không có `product_id` hay `price` ở top-level; cả hai nằm trong `cart_products`.
- Giá là string theo từng `currency`. P05 không quy đổi tỉ giá.
- Chi tiết: `docs/data_quality_report.md`.
