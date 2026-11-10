"""Central settings. Phase 0 reads paths from the environment or `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs into the environment without overriding existing vars."""
    env_path = path if path is not None else Path(".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


@dataclass(frozen=True)
class Settings:
    data_tar_path: str | None
    ip_bin_path: str | None
    mongo_uri: str | None
    mongo_db: str
    mongo_collection_raw: str
    mongo_collection_products: str
    ingest_batch_size: int
    crawl_rate_limit_per_sec: float
    crawl_base_url: str
    crawl_user_agent: str

    @classmethod
    def from_env(cls, dotenv: Path | None = None) -> Settings:
        load_dotenv(dotenv)
        return cls(
            data_tar_path=_env("DATA_TAR_PATH"),
            ip_bin_path=_env("IP_BIN_PATH"),
            mongo_uri=_env("MONGO_URI"),
            mongo_db=_env("MONGO_DB", "glamira") or "glamira",
            mongo_collection_raw=_env("MONGO_COLLECTION_RAW", "glamira_raw") or "glamira_raw",
            mongo_collection_products=_env("MONGO_COLLECTION_PRODUCTS", "products")
            or "products",
            ingest_batch_size=int(_env("INGEST_BATCH_SIZE", "10000") or "10000"),
            crawl_rate_limit_per_sec=float(_env("CRAWL_RATE_LIMIT_PER_SEC", "1.0") or "1.0"),
            crawl_base_url=_env("CRAWL_BASE_URL", "https://www.glamira.co.uk")
            or "https://www.glamira.co.uk",
            crawl_user_agent=_env("CRAWL_USER_AGENT", "GlamiraStudentProject/1.0")
            or "GlamiraStudentProject/1.0",
        )
