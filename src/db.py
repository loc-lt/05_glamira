"""Mongo client. The URI lives in `.env`: no auth for local mongod, a user and
`authSource=admin` for the GCP VM."""

from __future__ import annotations

from pymongo import MongoClient
from pymongo.collection import Collection

from src.config import Settings


def get_client(settings: Settings) -> MongoClient:
    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is empty. Set it in .env.")
    return MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)


def raw_collection(settings: Settings, client: MongoClient | None = None) -> Collection:
    handle = client if client is not None else get_client(settings)
    handle.admin.command("ping")
    return handle[settings.mongo_db][settings.mongo_collection_raw]
