"""Command line entrypoint. Phase 0 commands are under `explore`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.config import Settings
from src.enrich.crawl import crawl_seed
from src.enrich.export_csv import export_collection, product_status
from src.enrich.extract_products import extract_products
from src.enrich.ip_lookup import load_ip_geo
from src.explore.profile import profile_tar
from src.explore.render import render_data_dictionary, render_null_profile, render_quality_report
from src.ingest.load_mongo import load_tar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.cli")
    sub = parser.add_subparsers(dest="group", required=True)

    explore = sub.add_parser("explore", help="Phase 0 scans over the mongodump")
    commands = explore.add_subparsers(dest="command", required=True)

    null_cmd = commands.add_parser("null-profile", help="Write nullish %% by event type")
    _add_scan_args(null_cmd)
    null_cmd.add_argument("--out", default="docs/null_profile.md")
    null_cmd.set_defaults(handler=_null_profile)

    quality_cmd = commands.add_parser(
        "quality-report",
        help="Write the quality report, null profile, and Phase 0 dictionary",
    )
    _add_scan_args(quality_cmd)
    quality_cmd.add_argument("--out", default="docs/data_quality_report.md")
    quality_cmd.add_argument("--null-out", default="docs/null_profile.md")
    quality_cmd.add_argument("--dictionary-out", default="docs/data_dictionary.md")
    quality_cmd.add_argument("--stats-out", default="data/staging/profile_stats.json")
    quality_cmd.set_defaults(handler=_quality_report)

    ingest = sub.add_parser("ingest", help="Load the mongodump into MongoDB")
    ingest_cmds = ingest.add_subparsers(dest="command", required=True)
    load_cmd = ingest_cmds.add_parser("load-mongo", help="Stream summary.bson into glamira_raw")
    _add_scan_args(load_cmd)
    load_cmd.add_argument("--limit", type=int, default=0, help="Stop after N documents. 0 loads the member.")
    load_cmd.set_defaults(progress_every=100_000)
    load_cmd.set_defaults(handler=_load_mongo)

    enrich = sub.add_parser("enrich", help="IP lookup and product crawl")
    enrich_cmds = enrich.add_subparsers(dest="command", required=True)
    ip_cmd = enrich_cmds.add_parser("ip", help="Lookup distinct IPs and write coverage")
    ip_cmd.add_argument("--counts", default="data/staging/ip_event_counts.tsv")
    ip_cmd.add_argument("--checkout-counts", default="data/staging/checkout_success_ips.tsv")
    ip_cmd.add_argument("--out", default="docs/ip_coverage.md")
    ip_cmd.set_defaults(handler=_enrich_ip)
    extract_cmd = enrich_cmds.add_parser(
        "extract-products",
        help="Build one product URL per id from the coach event list",
    )
    extract_cmd.add_argument("--per-event", type=int, default=0, help="0 reads every document of each event.")
    extract_cmd.add_argument("--out", default="data/exports/product_urls.csv")
    extract_cmd.set_defaults(handler=_extract_products)
    crawl_cmd = enrich_cmds.add_parser("crawl", help="Fetch canonical product pages")
    crawl_cmd.add_argument("--seed", default="data/exports/product_urls.csv")
    crawl_cmd.add_argument("--limit", type=int, default=100, help="First N seed rows. 0 reads the whole seed.")
    crawl_cmd.add_argument("--out", default="docs/crawl_pilot.md")
    crawl_cmd.set_defaults(handler=_enrich_crawl)
    export_cmd = enrich_cmds.add_parser("export-csv", help="Write ip_geo or products to CSV beside Mongo")
    export_cmd.add_argument("collection", choices=("ip_geo", "products"))
    export_cmd.add_argument("--out", default=None, help="Defaults to data/exports/<collection>.csv")
    export_cmd.set_defaults(handler=_export_csv)
    status_cmd = enrich_cmds.add_parser("product-status", help="Compare products in Mongo with the seed")
    status_cmd.add_argument("--seed", default="data/exports/product_urls.csv")
    status_cmd.set_defaults(handler=_product_status)

    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _add_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path",
        default=None,
        help="Path to the tar.gz. Defaults to DATA_TAR_PATH from the environment or .env.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=0,
        help="Stop after N documents. 0 (default) reads the whole summary.bson member.",
    )
    parser.add_argument("--member-suffix", default="summary.bson")
    parser.add_argument("--progress-every", type=int, default=1_000_000)


def _resolve_path(raw: str | None) -> str:
    if raw:
        return raw
    settings = Settings.from_env()
    if not settings.data_tar_path:
        raise FileNotFoundError(
            "missing archive path: pass --path or set DATA_TAR_PATH in .env"
        )
    return settings.data_tar_path


def _null_profile(args: argparse.Namespace) -> int:
    profile = profile_tar(
        _resolve_path(args.path),
        sample_size=args.sample_size,
        progress_every=args.progress_every,
        member_suffix=args.member_suffix,
    )
    _write(args.out, render_null_profile(profile))
    print(f"wrote {args.out} ({profile.docs_scanned:,} docs)")
    return 0


def _quality_report(args: argparse.Namespace) -> int:
    profile = profile_tar(
        _resolve_path(args.path),
        sample_size=args.sample_size,
        progress_every=args.progress_every,
        member_suffix=args.member_suffix,
    )
    _write(args.out, render_quality_report(profile))
    _write(args.null_out, render_null_profile(profile))
    _write(args.dictionary_out, render_data_dictionary(profile))
    if args.stats_out:
        _write(args.stats_out, json.dumps(profile.to_dict(), indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {args.out}, {args.null_out}, {args.dictionary_out} "
        f"({profile.docs_scanned:,} docs)"
    )
    return 0


def _load_mongo(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    result = load_tar(
        _resolve_path(args.path),
        settings,
        limit=args.limit or args.sample_size,
        progress_every=args.progress_every,
    )
    print(
        f"scanned={result.docs_scanned:,} inserted={result.inserted:,} "
        f"duplicates={result.duplicates:,} mongo_count={result.mongo_count:,} "
        f"completed={result.completed_member} disk_stop={result.stopped_for_disk} "
        f"elapsed={result.elapsed_seconds:.1f}s"
    )
    if result.completed_member:
        print(f"ip counts: {result.ip_count_path} ({result.distinct_ips:,} distinct)")
        verdict = "MATCH" if result.count_matches else "MISMATCH"
        print(f"count check: source={result.docs_scanned:,} mongo={result.mongo_count:,} {verdict}")
        if not result.count_matches:
            return 3
    return 0 if not result.stopped_for_disk else 2


def _enrich_ip(args: argparse.Namespace) -> int:
    coverage = load_ip_geo(
        Settings.from_env(),
        counts_path=args.counts,
        checkout_path=args.checkout_counts,
        out_md=args.out,
    )
    print(
        f"public resolve {coverage.resolved_pct:.2f}% "
        f"checkout_success {coverage.checkout_pct:.2f}% "
        f"wrote {args.out}"
    )
    return 0


def _extract_products(args: argparse.Namespace) -> int:
    from src.db import get_client

    settings = Settings.from_env()
    raw = get_client(settings)[settings.mongo_db][settings.mongo_collection_raw]
    result = extract_products(
        raw,
        base_url=settings.crawl_base_url,
        per_event=args.per_event,
        out_csv=args.out,
    )
    print(
        f"scanned={result.scanned:,} kept={result.kept:,} "
        f"products={result.products:,} wrote {result.path}"
    )
    for event, (seen, kept) in result.by_event.items():
        print(f"  {event}: scanned={seen:,} kept={kept:,}")
    return 0


def _enrich_crawl(args: argparse.Namespace) -> int:
    result = crawl_seed(
        Settings.from_env(),
        seed_path=args.seed,
        limit=args.limit,
        out_md=args.out,
    )
    print(
        f"attempted={result.attempted} http_200={result.http_200} "
        f"parsed={result.parsed} ({result.parse_rate:.2f}%) "
        f"failed_com={result.failed_com} failed_uk={result.failed_uk} wrote {args.out}"
    )
    return 0


def _export_csv(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    out = args.out or f"data/exports/{args.collection}.csv"
    rows = export_collection(settings, args.collection, out)
    print(f"wrote {out} ({rows:,} rows)")
    return 0


def _product_status(args: argparse.Namespace) -> int:
    status = product_status(Settings.from_env(), args.seed)
    print(
        f"seed={status.seed:,} products={status.documents:,} named={status.named:,} "
        f"({status.named_pct:.2f}%) missing_from_mongo={status.missing:,}"
    )
    return 0 if status.missing == 0 else 4


def _write(path: str, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
