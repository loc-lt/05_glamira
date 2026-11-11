# Data quality report — Glamira UBL

Scan: **full member**. Yêu cầu: entire member. Documents: **41,432,473**. Thời điểm: 2026-11-11T03:10:55Z.

## 1. Nguồn

- Archive: `./data/raw/glamira_ubl_oct2019_nov2019.tar.gz`
- Nén gzip: 5.12 GB
- Member: `dump/countly/summary.bson`
- Kích thước member (uncompressed): 31.23 GB
- BSON đã đọc: 31.23 GB trong 41,432,473 documents
- Leftover trong member sau khi đọc hết: 0

File tên `glamira_ubl_oct2019_nov2019.tar.gz` là **mongodump**, không phải JSONL:

```text
dump/
dump/countly/
dump/countly/summary.metadata.json
dump/countly/summary.bson
```

Metadata ghi index nguồn `countly.summary`: `_id`, `time_stamp` (-1), `device_id`.
Tên Mongo collection vận hành của Project 05 vẫn là `glamira_raw`. Field `collection` bên trong document là **event type**.

## 2. Thể tích và tốc độ

- Documents scanned: **41,432,473**
- Số event type: **27**
- Thời gian scan: 2,623.1s (15,795 docs/s)
- Parse errors: 0

## 3. Phân bố event

| Event | Docs | % |
|---|---:|---:|
| `view_listing_page` | 11,259,694 | 27.18% |
| `view_product_detail` | 10,944,427 | 26.42% |
| `select_product_option` | 8,844,342 | 21.35% |
| `select_product_option_quality` | 2,231,825 | 5.39% |
| `view_static_page` | 1,451,565 | 3.50% |
| `view_landing_page` | 1,434,230 | 3.46% |
| `product_detail_recommendation_visible` | 1,302,362 | 3.14% |
| `view_home_page` | 1,053,420 | 2.54% |
| `listing_page_recommendation_visible` | 718,048 | 1.73% |
| `product_detail_recommendation_noticed` | 490,780 | 1.18% |
| `view_shopping_cart` | 343,077 | 0.83% |
| `landing_page_recommendation_visible` | 314,999 | 0.76% |
| `search_box_action` | 238,308 | 0.58% |
| `add_to_cart_action` | 187,901 | 0.45% |
| `product_detail_recommendation_clicked` | 179,228 | 0.43% |
| `view_my_account` | 112,066 | 0.27% |
| `checkout` | 88,540 | 0.21% |
| `landing_page_recommendation_noticed` | 58,186 | 0.14% |
| `listing_page_recommendation_noticed` | 39,819 | 0.10% |
| `view_all_recommend` | 33,664 | 0.08% |
| `checkout_success` | 26,079 | 0.06% |
| `listing_page_recommendation_clicked` | 25,545 | 0.06% |
| `landing_page_recommendation_clicked` | 20,128 | 0.05% |
| `product_view_all_recommend_clicked` | 16,682 | 0.04% |
| `view_sorting_relevance` | 15,284 | 0.04% |
| `sorting_relevance_click_action` | 1,713 | 0.00% |
| `back_to_product_action` | 561 | 0.00% |

## 4. Nullish trên toàn bộ scan

| Field | Nullish (all) | % |
|---|---:|---:|
| `ip` | 0 | 0.00% |
| `product_id` | 19,189,753 | 46.32% |
| `viewing_product_id` | 39,443,421 | 95.20% |
| `current_url` | 0 | 0.00% |
| `cat_id` | 41,432,215 | 100.00% |
| `cart_products` | 40,974,777 | 98.90% |
| `device_id` | 0 | 0.00% |
| `local_time` | 240 | 0.00% |
| `email_address` | 39,443,921 | 95.20% |
| `referrer_url` | 3,783,396 | 9.13% |
| `user_id_db` | 39,440,191 | 95.19% |
| `store_id` | 0 | 0.00% |
| `time_stamp` | 0 | 0.00% |
| `option` | 7,131,924 | 17.21% |
| `order_id` | 41,406,394 | 99.94% |
| `collect_id` | 38,802,627 | 93.65% |
| `show_recommendation` | 7,766,850 | 18.75% |
| `user_agent` | 3 | 0.00% |
| `resolution` | 240 | 0.00% |

Bảng theo từng event nằm ở `docs/null_profile.md` (cùng một lần scan).

## 5. Kiểu giá trị dễ gây hiểu nhầm

Các field này đổi kiểu theo event. `missing` = không có key.

### `product_id`

| Kind | Docs | % |
|---|---:|---:|
| `str` | 22,242,720 | 53.68% |
| `missing` | 19,189,753 | 46.32% |

### `viewing_product_id`

| Kind | Docs | % |
|---|---:|---:|
| `missing` | 39,443,421 | 95.20% |
| `str` | 1,989,052 | 4.80% |

### `show_recommendation`

| Kind | Docs | % |
|---|---:|---:|
| `str` | 33,665,623 | 81.25% |
| `null` | 7,766,848 | 18.75% |
| `empty_str` | 2 | 0.00% |

### `recommendation`

| Kind | Docs | % |
|---|---:|---:|
| `missing` | 30,488,046 | 73.58% |
| `bool` | 10,944,359 | 26.41% |
| `null` | 68 | 0.00% |

### `utm_source`

| Kind | Docs | % |
|---|---:|---:|
| `missing` | 30,488,046 | 73.58% |
| `bool` | 10,856,180 | 26.20% |
| `str` | 88,175 | 0.21% |
| `null` | 68 | 0.00% |
| `empty_str` | 4 | 0.00% |

### `utm_medium`

| Kind | Docs | % |
|---|---:|---:|
| `missing` | 30,488,046 | 73.58% |
| `bool` | 10,853,638 | 26.20% |
| `str` | 90,717 | 0.22% |
| `null` | 68 | 0.00% |
| `empty_str` | 4 | 0.00% |

### `option`

| Kind | Docs | % |
|---|---:|---:|
| `arr` | 22,208,495 | 53.60% |
| `doc` | 12,092,054 | 29.18% |
| `missing` | 7,131,924 | 17.21% |

### `cart_products`

| Kind | Docs | % |
|---|---:|---:|
| `missing` | 40,974,777 | 98.90% |
| `arr` | 364,982 | 0.88% |
| `empty_arr` | 92,714 | 0.22% |

## 6. Giá trị thấp cardinality

### `show_recommendation`

| Value | Docs | % |
|---|---:|---:|
| `true` | 33,586,437 | 81.06% |
| `(null)` | 7,766,848 | 18.75% |
| `false` | 79,029 | 0.19% |
| `(empty)` | 2 | 0.00% |
| `(other)` | 157 | 0.00% |

### `api_version`

| Value | Docs | % |
|---|---:|---:|
| `1.0` | 41,432,473 | 100.00% |

## 7. Thời gian

- `time_stamp` min: 2020-04-01 00:00:01 UTC (`1585699201`)
- `time_stamp` max: 2020-06-04 10:21:32 UTC (`1591266092`)
- `local_time` không parse được (có mặt nhưng sai format): 0
- Cặp so sánh được (`time_stamp` và `local_time` đều có): 41,432,233
- Lệch ngoài [-14h, +14h]: 5,723,092

`local_time` được parse như wall-clock rồi gắn UTC để tính hiệu `local_time - time_stamp`. Histogram giờ là ứng viên timezone, chưa phải kết luận.

| Offset hours | Docs | % của cặp so sánh |
|---:|---:|---:|
| -14 | 11,571 | 0.03% |
| -13 | 14,327 | 0.03% |
| -12 | 91,807 | 0.22% |
| -11 | 2,660,100 | 6.42% |
| -10 | 13,577,135 | 32.77% |
| -9 | 2,624,911 | 6.34% |
| -8 | 118,036 | 0.28% |
| -7 | 2,672,594 | 6.45% |
| -6 | 188,711 | 0.46% |
| -5 | 1,007,742 | 2.43% |
| -4 | 1,344,817 | 3.25% |
| -3 | 228,644 | 0.55% |
| -2 | 714,745 | 1.73% |
| -1 | 21,457 | 0.05% |
| +0 | 199,573 | 0.48% |
| +1 | 1,334,794 | 3.22% |
| +2 | 6,489,364 | 15.66% |
| +3 | 1,436,564 | 3.47% |
| +4 | 78,360 | 0.19% |
| +5 | 24,016 | 0.06% |
| +6 | 4,461 | 0.01% |
| +7 | 136,794 | 0.33% |
| +8 | 301,083 | 0.73% |
| +9 | 32,536 | 0.08% |
| +10 | 329,485 | 0.80% |
| +11 | 6,384 | 0.02% |
| +12 | 55,837 | 0.13% |
| +13 | 2,047 | 0.00% |
| +14 | 1,246 | 0.00% |

Mode offset theo `store_id` (top store theo volume, chỉ store có cặp thời gian):

| store_id | Docs | Mode offset | Share tại mode |
|---|---:|---:|---:|
| `6` | 5,162,382 | -10h | 62.5% |
| `7` | 3,359,850 | -11h | 58.7% |
| `12` | 2,509,355 | -10h | 60.5% |
| `41` | 2,360,349 | -4h | 31.1% |
| `14` | 1,866,741 | -10h | 61.0% |
| `8` | 1,680,873 | -10h | 57.1% |
| `19` | 1,537,060 | -10h | 60.5% |
| `29` | 1,412,478 | -2h | 52.3% |
| `51` | 1,378,809 | -9h | 62.7% |
| `11` | 1,246,968 | -10h | 65.9% |
| `62` | 1,242,371 | -5h | 76.6% |
| `46` | 1,067,004 | -10h | 61.1% |
| `17` | 995,588 | -9h | 51.7% |
| `10` | 875,918 | -10h | 60.9% |
| `45` | 871,743 | -10h | 58.2% |

- ObjectId time vs `time_stamp` lệch > 1 ngày: 0 / 41,432,473 cặp

## 8. Cardinality

Ước lượng HyperLogLog (p=14, sai số khoảng ±1%). Không phải exact distinct.

| Field | Ước lượng distinct (giá trị non-empty) |
|---|---:|
| `ip_public` | 3,211,388 |
| `device_id` | 7,674,188 |
| `product_id` | 17,068 |
| `viewing_product_id` | 14,717 |
| `user_id_db` | 27,405 |

- Exact `store_id`: 86
- Host của `current_url` bị trần 500 tên. Con số chạm trần không phải cardinality. Top host bên dưới vẫn đúng vì các domain lớn xuất hiện từ đầu file.

Top host:

| Host | Docs |
|---|---:|
| `www.glamira.de` | 5,151,363 |
| `www.glamira.co.uk` | 3,318,659 |
| `www.glamira.fr` | 2,508,952 |
| `www.glamira.com` | 2,413,812 |
| `www.glamira.it` | 1,866,321 |
| `www.glamira.es` | 1,680,379 |
| `www.glamira.se` | 1,536,764 |
| `www.glamira.com.au` | 1,412,296 |
| `www.glamira.ro` | 1,378,254 |
| `www.glamira.nl` | 1,246,485 |
| `www.glamira.com.mx` | 1,242,128 |
| `www.glamira.ch` | 1,093,683 |
| `www.glamira.ca` | 1,070,266 |
| `www.glamira.hu` | 1,066,373 |
| `www.glamira.com.tr` | 994,959 |
| `www.glamira.be` | 915,742 |
| `www.glamira.cz` | 871,445 |
| `www.glamira.pl` | 860,990 |
| `www.glamira.dk` | 852,561 |
| `www.glamira.cl` | 786,534 |

## 9. IP

| Class | Docs | % |
|---|---:|---:|
| `public` | 41,422,559 | 99.98% |
| `private` | 5,899 | 0.01% |
| `ipv6` | 4,009 | 0.01% |
| `invalid` | 6 | 0.00% |

Public = IPv4 unicast không thuộc dải private/loopback/link-local/multicast. Chỉ nhóm này nên đưa vào IP2Location.

## 10. Product linkage

- Document có `cart_products` không rỗng hoặc không null: 457,696
- Trong đó có `product_id` bên trong phần tử: 364,982

Một document được tính là có product link khi top-level `product_id` hoặc `viewing_product_id` non-empty, hoặc cart có `product_id`.

| Event | Docs | Có product link | URL có `.html` | `product_id` nhưng URL không `.html` |
|---|---:|---:|---:|---:|
| `view_listing_page` | 11,259,694 | 0.00% | 0.01% | 0.00% |
| `view_product_detail` | 10,944,427 | 100.00% | 99.31% | 0.69% |
| `select_product_option` | 8,844,342 | 100.00% | 98.98% | 1.02% |
| `select_product_option_quality` | 2,231,825 | 100.00% | 98.81% | 1.19% |
| `view_static_page` | 1,451,565 | 0.00% | 0.22% | 0.00% |
| `view_landing_page` | 1,434,230 | 0.00% | 0.00% | 0.00% |
| `product_detail_recommendation_visible` | 1,302,362 | 100.00% | 98.36% | 0.00% |
| `view_home_page` | 1,053,420 | 0.00% | 0.00% | 0.00% |
| `listing_page_recommendation_visible` | 718,048 | 0.00% | 0.02% | 0.00% |
| `product_detail_recommendation_noticed` | 490,780 | 100.00% | 98.11% | 0.00% |
| `view_shopping_cart` | 343,077 | 72.98% | 0.00% | 0.00% |
| `landing_page_recommendation_visible` | 314,999 | 0.00% | 0.00% | 0.00% |
| `search_box_action` | 238,308 | 0.00% | 16.72% | 0.00% |
| `add_to_cart_action` | 187,901 | 100.00% | 89.69% | 10.31% |
| `product_detail_recommendation_clicked` | 179,228 | 100.00% | 98.79% | 0.00% |
| `view_my_account` | 112,066 | 0.00% | 0.02% | 0.00% |
| `checkout` | 88,540 | 100.00% | 0.00% | 0.00% |
| `landing_page_recommendation_noticed` | 58,186 | 0.00% | 0.00% | 0.00% |
| `listing_page_recommendation_noticed` | 39,819 | 0.00% | 0.02% | 0.00% |
| `view_all_recommend` | 33,664 | 100.00% | 0.00% | 100.00% |
| `checkout_success` | 26,079 | 100.00% | 0.01% | 0.00% |
| `listing_page_recommendation_clicked` | 25,545 | 0.00% | 0.00% | 0.00% |
| `landing_page_recommendation_clicked` | 20,128 | 0.00% | 0.00% | 0.00% |
| `product_view_all_recommend_clicked` | 16,682 | 100.00% | 0.00% | 0.00% |
| `view_sorting_relevance` | 15,284 | 0.00% | 0.00% | 0.00% |
| `sorting_relevance_click_action` | 1,713 | 0.00% | 0.00% | 0.00% |
| `back_to_product_action` | 561 | 100.00% | 0.00% | 100.00% |

## 11. Duplicate `_id`

- Exact check trên **500,000** document đầu: **0** `_id` trùng.
- Nguồn `summary.metadata.json` có index `_id_`. Dump từ Mongo thường không nhân bản `_id`.
- Toàn bộ 41M id không được nhét vào RAM (máy đang có áp lực bộ nhớ). Unique index sẽ được kiểm lại lúc load Mongo.

## 12. PII

Document có thể chứa `email_address`, IP và URL kèm query. Scanner không copy email hay user-agent. `show_recommendation` chỉ giữ `true` / `false`; phần còn lại gộp thành `(other)`. Report này chỉ có count, host, store id và event name. Không commit archive, BIN, hay extract thô.

## 13. Đọc số liệu

- Archive đọc hết, leftover 0 byte, parse errors 0. Số document nguồn để đối chiếu Mongo là **41,432,473**.
- `time_stamp` nằm trong **2020-04-01 00:00:01 UTC → 2020-06-04 10:21:32 UTC**. Tên file ghi Oct–Nov 2019; dữ liệu đo được là khoảng này.
- ObjectId và `time_stamp` lệch quá 1 ngày: 0 / 41,432,473. Mốc canonical là `time_stamp`.
- `local_time` lệch quá ±14 giờ trên 5,723,092 cặp (13.81%). Mode theo `store_id` thường chỉ quanh 60%. Không dùng `local_time` để tính doanh thu.
- IP public IPv4: 41,422,559 (99.98%). IPv6: 4,009. BIN coach là IPv4.
- `product_id` top-level khoảng 17,068 distinct (HLL). `view_product_detail` có product link 100.00%.
- `checkout_success`: 26,079 document, product link 100.00%. Id bán hàng nằm trong `cart_products`, không phải top-level `product_id`.
- `cat_id` gần như không có giá trị. Category cho dashboard phải lấy từ crawl.

## 14. Reproduce

```bash
python3 -m src.cli explore quality-report \
  --sample-size 0 \
  --out docs/data_quality_report.md \
  --null-out docs/null_profile.md
```
