import hashlib
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import boto3
import pytest
from alembic import command
from alembic.config import Config
from botocore.response import StreamingBody
from botocore.stub import Stubber
from sqlalchemy import MetaData, inspect, text

from northstar.config import Settings, StorageSettings
from northstar.db import make_engine
from northstar.storage import ObjectStore, StorageError
from northstar.storage_admin import export_legacy


def test_s3_wire_roundtrip_is_private_and_checks_content():
    store = ObjectStore(
        StorageSettings(bucket="private-test", access_key="test", secret_key="test")
    )
    store._client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    key, data = "originals/" + str(uuid4()), b"Private original"
    with Stubber(store.client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "private-test",
                "Key": key,
                "Body": data,
                "ContentType": "application/octet-stream",
            },
        )
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(BytesIO(data), len(data))},
            {"Bucket": "private-test", "Key": key},
        )
        stub.add_response("delete_object", {}, {"Bucket": "private-test", "Key": key})
        store.put(key, data)
        assert store.get(key, hashlib.sha256(data).hexdigest()) == data
        store.delete(key)
        stub.assert_no_pending_responses()


def test_corrupt_object_and_traversal_rejected(tmp_path):
    store = ObjectStore(StorageSettings(backend="filesystem", directory=str(tmp_path)))
    key = "originals/" + str(uuid4())
    store.put(key, b"changed")
    with pytest.raises(StorageError):
        store.get(key, hashlib.sha256(b"original").hexdigest())
    with pytest.raises(ValueError):
        store.put("../../outside", b"x")


def test_legacy_export_preserves_bytes_and_requires_reclassification(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'legacy-objects.db'}"
    monkeypatch.setenv("NORTHSTAR_ENVIRONMENT", "test")
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0007")
    settings = Settings(_env_file=None, environment="test", database_url=url)
    engine = make_engine(settings)
    metadata = MetaData()
    metadata.reflect(engine)
    identifier, data = str(uuid4()), b"Original policy bytes"
    try:
        with engine.begin() as connection:
            connection.execute(
                metadata.tables["knowledge_policies"]
                .insert()
                .values(id="legacy", enabled=True, revision=1)
            )
            connection.execute(
                metadata.tables["knowledge_documents"]
                .insert()
                .values(
                    id=identifier,
                    policy_id="legacy",
                    version=1,
                    filename="old.txt",
                    media_type="text/plain",
                    original_hash=hashlib.sha256(data).hexdigest(),
                    original=data,
                    status="READY",
                    warnings=[],
                    valid_from=datetime.now(UTC),
                    enabled=True,
                )
            )
        with pytest.raises(RuntimeError, match="Original export required"):
            command.upgrade(config, "head")
        command.upgrade(config, "0008")
        store = ObjectStore(settings.storage)
        assert export_legacy(engine, store) == 1
        assert export_legacy(engine, store) == 0
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT storage_key, original_hash, sensitivity, publication_status "
                    "FROM knowledge_documents"
                )
            ).one()
            assert store.get(row.storage_key, row.original_hash) == data
            assert row.sensitivity == "UNCLASSIFIED" and row.publication_status == "PENDING_REVIEW"
        assert "original" not in {
            c["name"] for c in inspect(engine).get_columns("knowledge_documents")
        }
        with pytest.raises(RuntimeError, match="backup"):
            command.downgrade(config, "0008")
    finally:
        engine.dispose()


@pytest.mark.integration
def test_live_minio_private_roundtrip():
    import os
    from urllib.error import HTTPError
    from urllib.request import urlopen

    if os.getenv("NORTHSTAR_TEST_MINIO") != "1":
        pytest.skip("Set NORTHSTAR_TEST_MINIO=1 with a disposable MinIO bucket to run")
    settings = Settings(storage={"backend": "s3"}).storage
    store = ObjectStore(settings)
    key, data = "originals/" + str(uuid4()), b"Synthetic object-storage integration probe"
    try:
        store.put(key, data)
        assert store.get(key, hashlib.sha256(data).hexdigest()) == data
        with pytest.raises(HTTPError) as response:
            urlopen(f"{settings.endpoint}/{settings.bucket}/{key}", timeout=5)
        assert response.value.code == 403
    finally:
        store.delete(key)
