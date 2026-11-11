"""Markdown renderers for Phase 0. Aggregates only — no raw emails, IPs, or URLs."""

from __future__ import annotations

from datetime import datetime, timezone

from src.explore.profile import CRITICAL_FIELDS, EXTRA_FIELDS, TRACKED_FIELDS, Profile


def render_null_profile(profile: Profile) -> str:
    overall = _overall_nullish(profile)
    lines = [
        "# Null profile theo event type",
        "",
        _scan_banner(profile),
        "",
        "## Định nghĩa",
        "",
        "- **Nullish** = field vắng mặt, BSON `null`, hoặc string rỗng `\"\"`.",
        "- `false`, `0`, object rỗng `{}` và array rỗng `[]` **không** tính là nullish.",
        "- String `\"false\"` là giá trị có mặt (xem histogram trong quality report).",
        "- Cột trong bảng là **% nullish**. `100%` nghĩa là event đó không dùng field.",
        "- `collection` trong bảng là **loại event**, không phải tên Mongo collection.",
        "",
        "## Toàn bộ sample đã quét",
        "",
        _field_table("all events", profile.docs_scanned, overall, CRITICAL_FIELDS),
        "",
        _field_table("all events — field phụ", profile.docs_scanned, overall, EXTRA_FIELDS),
        "",
        "## Theo event (`collection`)",
        "",
        "Event sắp theo số document giảm dần.",
        "",
        _event_table(profile, CRITICAL_FIELDS),
        "",
        _event_table(profile, EXTRA_FIELDS),
        "",
        "## Reproduce",
        "",
        "```bash",
        "python3 -m src.cli explore null-profile --sample-size 0 --out docs/null_profile.md",
        "```",
        "",
        "`--sample-size 0` đọc hết member BSON. Smoke test: `--sample-size 500000`.",
        "",
    ]
    return "\n".join(lines)


def render_quality_report(profile: Profile) -> str:
    overall = _overall_nullish(profile)
    lines = [
        "# Data quality report — Glamira UBL",
        "",
        _scan_banner(profile),
        "",
        "## 1. Nguồn",
        "",
        f"- Archive: `{profile.source}`",
        f"- Nén gzip: {_bytes(profile.compressed_bytes)}",
        f"- Member: `{profile.member_name or '(chưa đọc header)'}`",
        f"- Kích thước member (uncompressed): {_bytes(profile.member_size)}",
        f"- BSON đã đọc: {_bytes(profile.bson_bytes)} trong {profile.docs_scanned:,} documents",
        f"- Leftover trong member sau khi đọc hết: {profile.leftover_bytes}",
        "",
        "File tên `glamira_ubl_oct2019_nov2019.tar.gz` là **mongodump**, không phải JSONL:",
        "",
        "```text",
        "dump/",
        "dump/countly/",
        "dump/countly/summary.metadata.json",
        "dump/countly/summary.bson",
        "```",
        "",
        "Metadata ghi index nguồn `countly.summary`: `_id`, `time_stamp` (-1), `device_id`.",
        "Tên Mongo collection vận hành của Project 05 vẫn là `glamira_raw`. Field `collection` bên trong document là **event type**.",
        "",
        "## 2. Thể tích và tốc độ",
        "",
        f"- Documents scanned: **{profile.docs_scanned:,}**",
        f"- Số event type: **{len(profile.event_counts):,}**",
        f"- Thời gian scan: {profile.elapsed_seconds:,.1f}s "
        f"({_rate(profile):,.0f} docs/s)",
        f"- Parse errors: {profile.parse_errors:,}",
        "",
    ]
    if profile.error_samples:
        lines.append("Mẫu lỗi parser (không gồm payload):")
        lines.append("")
        for sample in profile.error_samples:
            lines.append(f"- `{sample}`")
        lines.append("")

    lines.extend(
        [
            "## 3. Phân bố event",
            "",
            "| Event | Docs | % |",
            "|---|---:|---:|",
        ]
    )
    for event, count in profile.event_counts.items():
        lines.append(f"| `{_cell(event)}` | {count:,} | {_pct(count, profile.docs_scanned)} |")
    lines.extend(["", "## 4. Nullish trên toàn bộ scan", ""])
    lines.append(_field_table("all", profile.docs_scanned, overall, TRACKED_FIELDS))
    lines.extend(
        [
            "",
            "Bảng theo từng event nằm ở `docs/null_profile.md` (cùng một lần scan).",
            "",
            "## 5. Kiểu giá trị dễ gây hiểu nhầm",
            "",
            "Các field này đổi kiểu theo event. `missing` = không có key.",
            "",
        ]
    )
    for name, kinds in profile.variants.items():
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append("| Kind | Docs | % |")
        lines.append("|---|---:|---:|")
        for kind, count in sorted(kinds.items(), key=lambda item: -item[1]):
            lines.append(f"| `{kind}` | {count:,} | {_pct(count, profile.docs_scanned)} |")
        lines.append("")

    lines.extend(["## 6. Giá trị thấp cardinality", ""])
    for name, values in profile.value_counts.items():
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append("| Value | Docs | % |")
        lines.append("|---|---:|---:|")
        for label, count in values.items():
            lines.append(f"| `{_cell(label)}` | {count:,} | {_pct(count, profile.docs_scanned)} |")
        lines.append("")

    lines.extend(
        [
            "## 7. Thời gian",
            "",
            f"- `time_stamp` min: {_fmt_ts(profile.ts_min)} (`{profile.ts_min}`)",
            f"- `time_stamp` max: {_fmt_ts(profile.ts_max)} (`{profile.ts_max}`)",
            f"- `local_time` không parse được (có mặt nhưng sai format): {profile.local_unparsed:,}",
            f"- Cặp so sánh được (`time_stamp` và `local_time` đều có): {profile.local_compared:,}",
            f"- Lệch ngoài [-14h, +14h]: {profile.offset_out_of_range:,}",
            "",
            "`local_time` được parse như wall-clock rồi gắn UTC để tính hiệu "
            "`local_time - time_stamp`. Histogram giờ là ứng viên timezone, chưa phải kết luận.",
            "",
            "| Offset hours | Docs | % của cặp so sánh |",
            "|---:|---:|---:|",
        ]
    )
    compared = profile.local_compared or 0
    for hour, count in sorted(profile.offset_hours.items()):
        lines.append(f"| {hour:+d} | {count:,} | {_pct(count, compared)} |")
    lines.extend(
        [
            "",
            "Mode offset theo `store_id` (top store theo volume, chỉ store có cặp thời gian):",
            "",
            "| store_id | Docs | Mode offset | Share tại mode |",
            "|---|---:|---:|---:|",
        ]
    )
    for store_id, count in list(profile.store_counts.items())[:15]:
        mode = profile.store_offset_mode.get(store_id)
        if not mode:
            continue
        lines.append(
            f"| `{_cell(store_id)}` | {count:,} | {int(mode['mode_hour']):+d}h | "
            f"{float(mode['mode_share']) * 100:.1f}% |"
        )
    lines.extend(
        [
            "",
            f"- ObjectId time vs `time_stamp` lệch > 1 ngày: {profile.oid_skew_over_1d:,} "
            f"/ {profile.oid_compared:,} cặp",
            "",
            "## 8. Cardinality",
            "",
            "Ước lượng HyperLogLog (p=14, sai số khoảng ±1%). Không phải exact distinct.",
            "",
            "| Field | Ước lượng distinct (giá trị non-empty) |",
            "|---|---:|",
        ]
    )
    for name, estimate in profile.hll.items():
        lines.append(f"| `{name}` | {estimate:,} |")
    lines.extend(
        [
            "",
            f"- Exact `store_id`: {len(profile.store_counts):,}",
            "- Host của `current_url` bị trần 500 tên. Con số chạm trần không phải cardinality. "
            "Top host bên dưới vẫn đúng vì các domain lớn xuất hiện từ đầu file.",
            "",
            "Top host:",
            "",
            "| Host | Docs |",
            "|---|---:|",
        ]
    )
    for host, count in list(profile.hosts.items())[:20]:
        lines.append(f"| `{_cell(host)}` | {count:,} |")
    lines.extend(
        [
            "",
            "## 9. IP",
            "",
            "| Class | Docs | % |",
            "|---|---:|---:|",
        ]
    )
    for label, count in sorted(profile.ip_class.items(), key=lambda item: -item[1]):
        lines.append(f"| `{label}` | {count:,} | {_pct(count, profile.docs_scanned)} |")
    lines.extend(
        [
            "",
            "Public = IPv4 unicast không thuộc dải private/loopback/link-local/multicast. "
            "Chỉ nhóm này nên đưa vào IP2Location.",
            "",
            "## 10. Product linkage",
            "",
            f"- Document có `cart_products` không rỗng hoặc không null: {profile.cart_present:,}",
            f"- Trong đó có `product_id` bên trong phần tử: {profile.cart_with_product_id:,}",
            "",
            "Một document được tính là có product link khi top-level `product_id` hoặc "
            "`viewing_product_id` non-empty, hoặc cart có `product_id`.",
            "",
            "| Event | Docs | Có product link | URL có `.html` | `product_id` nhưng URL không `.html` |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for event, count in profile.event_counts.items():
        lines.append(
            f"| `{_cell(event)}` | {count:,} | "
            f"{_pct(profile.product_link_by_event.get(event, 0), count)} | "
            f"{_pct(profile.html_by_event.get(event, 0), count)} | "
            f"{_pct(profile.pid_without_html.get(event, 0), count)} |"
        )
    lines.extend(
        [
            "",
            "## 11. Duplicate `_id`",
            "",
            f"- Exact check trên **{profile.exact_dup_prefix_n:,}** document đầu: "
            f"**{profile.exact_dup_prefix_dups:,}** `_id` trùng.",
            "- Nguồn `summary.metadata.json` có index `_id_`. Dump từ Mongo thường không nhân bản `_id`.",
            "- Toàn bộ 41M id không được nhét vào RAM (máy đang có áp lực bộ nhớ). "
            "Unique index sẽ được kiểm lại lúc load Mongo.",
            "",
            "## 12. PII",
            "",
            "Document có thể chứa `email_address`, IP và URL kèm query. "
            "Scanner không copy email hay user-agent. "
            "`show_recommendation` chỉ giữ `true` / `false`; phần còn lại gộp thành `(other)`. "
            "Report này chỉ có count, host, store id và event name. "
            "Không commit archive, BIN, hay extract thô.",
            "",
            "## 13. Đọc số liệu",
            "",
            *_conclusions(profile),
            "",
            "## 14. Reproduce",
            "",
            "```bash",
            "python3 -m src.cli explore quality-report \\",
            "  --sample-size 0 \\",
            "  --out docs/data_quality_report.md \\",
            "  --null-out docs/null_profile.md",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_data_dictionary(profile: Profile) -> str:
    lines = [
        "# Data dictionary — draft Phase 0",
        "",
        "Schema-on-read. Bản này chỉ mô tả **raw event** nhìn thấy trong `summary.bson`. "
        "Field enrich (`geo_*`, catalog) sẽ được thêm sau checkpoint 8–11.",
        "",
        _scan_banner(profile),
        "",
        "## File",
        "",
        "| Path | Vai trò |",
        "|---|---|",
        "| `glamira_ubl_oct2019_nov2019.tar.gz` | gzip ustar, mongodump Countly |",
        "| `dump/countly/summary.metadata.json` | options + indexes của collection nguồn |",
        "| `dump/countly/summary.bson` | BSON documents, nối tiếp nhau |",
        "| `IP-COUNTRY-REGION-CITY.BIN` | IP2Location-style BIN, chưa dùng ở Phase 0 |",
        "",
        "## Collection dự kiến (chưa load)",
        "",
        "| Tên | Trạng thái | Ghi chú |",
        "|---|---|---|",
        "| `glamira.glamira_raw` | chưa load | một document = một event |",
        "| `glamira.products` | chưa crawl | checkpoint 11 |",
        "",
        "Đừng map field `collection` thành tên collection Mongo.",
        "",
        "## Field raw đã gặp",
        "",
        "Presence = số document có key, kể cả giá trị rỗng/null. "
        "Nullish nằm ở `docs/null_profile.md`.",
        "",
        "| Field | Docs có key | % | Ghi chú Phase 0 |",
        "|---|---:|---:|---|",
    ]
    cat_usable = profile.docs_scanned - _overall_nullish(profile).get("cat_id", 0)
    order_usable = profile.docs_scanned - _overall_nullish(profile).get("order_id", 0)
    price_docs = profile.key_docs.get("price", 0)
    add_to_cart = profile.event_counts.get("add_to_cart_action", 0)
    price_note = "Có top-level trên một phần event."
    if price_docs and price_docs == add_to_cart:
        price_note = (
            "Số document bằng đúng `add_to_cart_action`. "
            "Không có ở top-level của `checkout_success`."
        )
    notes = {
        "_id": "ObjectId nguồn. Dùng làm khóa tự nhiên khi load.",
        "time_stamp": "Epoch giây (int). Mốc canonical; khớp ObjectId trong scan này.",
        "local_time": "Wall clock string, không zero-pad. Không dùng làm mốc doanh thu.",
        "ip": (
            f"Public IPv4 {profile.ip_class.get('public', 0):,}; "
            f"IPv6 {profile.ip_class.get('ipv6', 0):,}. Không có country/city."
        ),
        "collection": "Event type (view_product_detail, checkout, …).",
        "product_id": "Top-level là string khi có. Trong cart_products (sample checkout_success) là int. Không có name/category.",
        "viewing_product_id": "Chủ yếu event recommendation, không phải trang detail.",
        "current_url": "URL cửa hàng theo TLD. Trang sản phẩm thường chứa `.html`.",
        "cart_products": "Array line item của checkout. `product_id` nằm ở phần tử con.",
        "option": "Khi thì array, khi thì document.",
        "store_id": f"Mã cửa hàng, string. {len(profile.store_counts)} giá trị trong scan này.",
        "device_id": "UUID thiết bị.",
        "email_address": "PII. Không đưa vào report hay git.",
        "cat_id": f"Giá trị dùng được: {cat_usable:,}. Không dùng làm category.",
        "user_id_db": "Rỗng với khách chưa đăng nhập.",
        "price": price_note,
        "currency": "Đi cùng top-level `price` trên add-to-cart.",
        "order_id": (
            f"Giá trị non-empty: {order_usable:,}, khớp số `checkout_success`. "
            "Key còn xuất hiện dạng rỗng trên `checkout`."
        ),
        "recommendation_product_id": "Id phụ trên event recommendation. Không thay `product_id`.",
    }
    for key, count in profile.key_docs.items():
        lines.append(
            f"| `{key}` | {count:,} | {_pct(count, profile.docs_scanned)} | {notes.get(key, '')} |"
        )
    if profile.extra_untracked_keys:
        lines.extend(
            [
                "",
                f"Có thêm {profile.extra_untracked_keys:,} lần xuất hiện của key vượt cap "
                f"{300} key khác nhau. Xem `parse` log nếu cap bị chạm.",
            ]
        )
    lines.extend(
        [
            "",
            "## Quy tắc làm sạch đã chốt cho các bước sau",
            "",
            "- Nullish: missing + BSON null + `\"\"`.",
            "- `product_id` chuẩn hóa về string khi extract catalog.",
            "- IP private / empty / invalid không lookup BIN.",
            "- Join catalog dự kiến trên `product_id` string.",
            "",
        ]
    )
    return "\n".join(lines)


def _conclusions(profile: Profile) -> list[str]:
    span = f"{_fmt_ts(profile.ts_min)} → {_fmt_ts(profile.ts_max)}"
    compared = profile.local_compared or 1
    wild = profile.offset_out_of_range
    public = profile.ip_class.get("public", 0)
    ipv6 = profile.ip_class.get("ipv6", 0)
    success = profile.event_counts.get("checkout_success", 0)
    detail = profile.event_counts.get("view_product_detail", 0)
    return [
        f"- Archive đọc hết, leftover {profile.leftover_bytes} byte, parse errors {profile.parse_errors}. "
        f"Số document nguồn để đối chiếu Mongo là **{profile.docs_scanned:,}**.",
        f"- `time_stamp` nằm trong **{span}**. Tên file ghi Oct–Nov 2019; dữ liệu đo được là khoảng này.",
        f"- ObjectId và `time_stamp` lệch quá 1 ngày: {profile.oid_skew_over_1d:,} / {profile.oid_compared:,}. "
        "Mốc canonical là `time_stamp`.",
        f"- `local_time` lệch quá ±14 giờ trên {wild:,} cặp ({_pct(wild, compared)}). "
        "Mode theo `store_id` thường chỉ quanh 60%. Không dùng `local_time` để tính doanh thu.",
        f"- IP public IPv4: {public:,} ({_pct(public, profile.docs_scanned)}). "
        f"IPv6: {ipv6:,}. BIN coach là IPv4.",
        f"- `product_id` top-level khoảng {profile.hll.get('product_id', 0):,} distinct (HLL). "
        f"`view_product_detail` có product link {_pct(profile.product_link_by_event.get('view_product_detail', 0), detail)}.",
        f"- `checkout_success`: {success:,} document, product link "
        f"{_pct(profile.product_link_by_event.get('checkout_success', 0), success)}. "
        "Id bán hàng nằm trong `cart_products`, không phải top-level `product_id`.",
        "- `cat_id` gần như không có giá trị. Category cho dashboard phải lấy từ crawl.",
    ]


def _overall_nullish(profile: Profile) -> dict[str, int]:
    totals = {name: 0 for name in TRACKED_FIELDS}
    for bucket in profile.nullish.values():
        for name in TRACKED_FIELDS:
            totals[name] += bucket.get(name, 0)
    return totals


def _event_table(profile: Profile, fields: tuple[str, ...]) -> str:
    header = "| Event | Docs | " + " | ".join(f"`{name}`" for name in fields) + " |"
    rule = "|---|---:" + "|---:" * len(fields) + "|"
    rows = [header, rule]
    for event, count in profile.event_counts.items():
        bucket = profile.nullish.get(event, {})
        cells = " | ".join(_pct(bucket.get(name, count), count) for name in fields)
        rows.append(f"| `{_cell(event)}` | {count:,} | {cells} |")
    return "\n".join(rows)


def _field_table(label: str, docs: int, nullish: dict[str, int], fields: tuple[str, ...]) -> str:
    rows = [
        f"| Field | Nullish ({label}) | % |",
        "|---|---:|---:|",
    ]
    for name in fields:
        count = nullish.get(name, 0)
        rows.append(f"| `{name}` | {count:,} | {_pct(count, docs)} |")
    return "\n".join(rows)


def _scan_banner(profile: Profile) -> str:
    scope = "full member" if profile.completed_member else "partial scan"
    requested = (
        "entire member"
        if profile.sample_size_requested == 0
        else f"sample {profile.sample_size_requested:,}"
    )
    warning = ""
    if not profile.completed_member:
        warning = (
            "\n\n> **Partial scan.** Số liệu dưới đây không phải toàn bộ archive. "
            "Đừng dùng bảng này cho quyết định GO cho đến khi chạy `--sample-size 0`."
        )
    return (
        f"Scan: **{scope}**. Yêu cầu: {requested}. "
        f"Documents: **{profile.docs_scanned:,}**. "
        f"Thời điểm: {profile.scanned_at}."
        f"{warning}"
    )


def _pct(count: int, total: int) -> str:
    if total <= 0:
        return "—"
    return f"{(100.0 * count / total):.2f}%"


def _fmt_ts(timestamp: int | None) -> str:
    if timestamp is None:
        return "—"
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _bytes(size: int) -> str:
    if size < 0:
        return "n/a"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _rate(profile: Profile) -> float:
    if profile.elapsed_seconds <= 0:
        return 0.0
    return profile.docs_scanned / profile.elapsed_seconds


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
