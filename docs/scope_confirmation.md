# Scope confirmation — Phase 0

Trạng thái: **đã xác nhận GO** (bốn mục bên dưới). Cloud (GCS, BigQuery) làm sau. Bước đang làm: Mongo local, nạp raw, IP lookup, crawl pilot.

Bằng chứng số liệu: `docs/data_quality_report.md` và `docs/null_profile.md`, một lần đọc hết `summary.bson` (41,432,473 document, 0 lỗi parse, 0 byte dư).

## Câu hỏi dashboard

| Câu hỏi | Trả lời bằng | Có trong raw? |
|---|---|---|
| Doanh thu Đức vs Pháp | `checkout_success` + IP → country, cộng `cart_products[].price` theo `currency` | IP có. Country chưa có. Giá nằm trong line item, không có top-level trên `checkout_success` |
| Nhẫn vs vòng tay | `product_id` → catalog `category` | Id có. Category không có. `cat_id` dùng được chỉ 258 document |

## Những gì dữ liệu thực sự là

- Mongodump `countly.summary`, không phải JSONL. Mongo collection vận hành sau này vẫn là `glamira_raw`. Field `collection` là event type.
- 41,432,473 document. Đây là số phải khớp khi load Mongo.
- `time_stamp` từ **2020-04-01 00:00:01 UTC** đến **2020-06-04 10:21:32 UTC**. Tên file nói Oct–Nov 2019. Làm việc theo khoảng đã đo.
- Mốc thời gian canonical là `time_stamp`. ObjectId lệch quá 1 ngày: 0. `local_time` lệch quá ±14 giờ trên 13.81% cặp.

## IP → country / city — GO

| Đo | Kết quả |
|---|---|
| Document có `ip` | 100% |
| IPv4 public (đưa vào BIN) | 41,422,559 (99.98%) |
| Private | 5,899 — bỏ qua |
| IPv6 | 4,009 — BIN không có IPv6, bỏ qua |
| Invalid | 6 — bỏ qua |
| BIN | IP2Location DB3 (type 3, 4 cột), 8,891,452 dòng IPv4, header ngày **2016-11-29**, 132,919,296 byte. Chưa lookup thử |

GO vì gần như mọi event, kể cả 26,079 `checkout_success`, có IPv4 public. Country DE/FR đủ ổn với DB 2016. City là best-effort vì DB cũ hơn event khoảng 3.5 năm.

Giả định:

- `time_stamp` là UTC. Country lấy từ IP, không lấy từ TLD (`glamira.de` không đồng nghĩa khách ở Đức).
- Doanh thu = tổng `cart_products[].price` của `checkout_success`, **tách theo** `currency`. Không tự quy đổi FX trong P05.
- Coverage bắt buộc ở checkpoint 8: `% event có ip`, `% lookup thành công`, top 10 country. Nếu country hit < 95% trên `checkout_success` thì dừng. Kết quả đo được: **99.16%** (25,860 / 26,079), xem `docs/ip_coverage.md`.

## Product id → name / category — GO

| Đo | Kết quả |
|---|---|
| `view_product_detail` có `product_id` | 10,944,427 / 10,944,427. Top-level id là string |
| URL `.html` trên detail | 99.31% |
| Distinct `product_id` | khoảng 17,068 (HyperLogLog, ±1%) |
| `checkout_success` có product link | 26,079 / 26,079, qua `cart_products`, không qua top-level `product_id` |
| `viewing_product_id` | 4.80% document, chủ yếu recommendation. Không phải khóa bán hàng |
| `cat_id` dùng được | 258. Bỏ |

Sample cấu trúc (80 `checkout_success` đầu file, chỉ tên field, file bắt đầu ở `time_stamp` lớn nhất): mọi line item có `product_id` int, `amount` int, `price` string, `currency` string. 80/80 không phải coverage toàn bộ. Checkpoint 9 sẽ đo % line item có đủ bốn field này.

Cách build URL:

1. Seed từ `view_product_detail`: cặp (`product_id` string, path `.html`).
2. Chuẩn hóa id trong cart từ int sang string rồi join cùng catalog.
3. Canonical host: `https://www.glamira.co.uk`. Giả định slug `.html` dùng chung giữa các TLD (các URL detail đã thấy có dạng `glamira-ring-….html`, trong khi URL listing thì dịch ngôn ngữ).
4. Pilot 100 URL trước. Nếu 404 trên `.co.uk` cao, crawl lại đúng host của event với cùng rate limit. Không crawl 41 triệu URL.

Crawl full khoảng 17k URL ở 1 request/giây là khoảng 5 giờ, cộng retry. User-Agent lấy từ `.env`. Dừng nếu site từ chối (429 kéo dài, robots chặn path sản phẩm).

Giả định:

- Category tiếng Anh trên `.co.uk` là nhãn cho dashboard (Rings, Bracelets, …).
- Một `product_id` là một SKU toàn hệ thống, không phải id theo từng store.

## Ngoài scope P05

GCS, Cloud Function, BigQuery, dbt, Looker, PostgreSQL, data Project 03–04.

## Chưa đo — không chặn GO

- Hit rate thật của BIN (checkpoint 8).
- `% checkout_success` có `price` trong từng line item, trên toàn bộ 26,079 đơn (sample mới 80).
- Distinct host vượt trần 500 của scanner. Top 20 host (`.de`, `.co.uk`, `.fr`, …) không bị ảnh hưởng.
- Unique `_id` trên toàn bộ 41M. 500,000 document đầu: 0 trùng. Index nguồn có `_id_`. Kiểm lại bằng unique index lúc load.

## Xác nhận

- [x] GO IP geolocation với BIN 2016, bỏ IPv6/private, country là metric chính, city là best-effort.
- [x] GO product crawl qua canonical `glamira.co.uk`, pilot 100 trước, rate limit 1 request/giây.
- [x] Chấp nhận khoảng dữ liệu 2020-04-01 → 2020-06-04 thay cho Oct–Nov 2019 trên tên file.
- [x] Doanh thu tách theo `currency`, không tự FX.

Sau khi tick, bước kế tiếp là môi trường `uv` và Mongo local. Chưa làm trong lần này.
