"""Private original-file storage. Keys are opaque; no public/presigned URLs are issued."""

import hashlib
import re
from pathlib import Path

from northstar.config import StorageSettings
from northstar.domain import DomainError


class StorageError(DomainError):
    def __init__(self):
        super().__init__("object_storage_unavailable", "Original-file storage is unavailable.", 503)


def validate_key(key):
    if not re.fullmatch(r"originals/[a-f0-9-]{36}", key):
        raise ValueError("Invalid object key")


class ObjectStore:
    def __init__(self, settings: StorageSettings):
        self.settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            s = self.settings
            self._client = boto3.client(
                "s3",
                endpoint_url=s.endpoint,
                region_name=s.region,
                aws_access_key_id=s.access_key.get_secret_value() if s.access_key else None,
                aws_secret_access_key=s.secret_key.get_secret_value() if s.secret_key else None,
                config=Config(
                    connect_timeout=5,
                    read_timeout=15,
                    retries={"max_attempts": 2},
                    s3={"addressing_style": "path"},
                ),
            )
        return self._client

    def put(self, key: str, data: bytes):
        validate_key(key)
        try:
            if self.settings.backend == "filesystem":
                path = Path(self.settings.directory) / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            else:
                extra = {}
                if self.settings.encryption:
                    extra["ServerSideEncryption"] = self.settings.encryption
                if self.settings.kms_key_id:
                    extra["SSEKMSKeyId"] = self.settings.kms_key_id
                self.client.put_object(
                    Bucket=self.settings.bucket,
                    Key=key,
                    Body=data,
                    ContentType="application/octet-stream",
                    **extra,
                )
        except Exception:
            raise StorageError() from None

    def get(self, key: str, expected_hash: str) -> bytes:
        validate_key(key)
        try:
            if self.settings.backend == "filesystem":
                with (Path(self.settings.directory) / key).open("rb") as source:
                    data = source.read(5 * 1024 * 1024 + 1)
            else:
                body = self.client.get_object(Bucket=self.settings.bucket, Key=key)["Body"]
                try:
                    data = body.read(5 * 1024 * 1024 + 1)
                finally:
                    body.close()
            if len(data) > 5 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected_hash:
                raise ValueError("Object integrity mismatch")
            return data
        except Exception:
            raise StorageError() from None

    def delete(self, key: str):
        validate_key(key)
        try:
            if self.settings.backend == "filesystem":
                (Path(self.settings.directory) / key).unlink(missing_ok=True)
            else:
                self.client.delete_object(Bucket=self.settings.bucket, Key=key)
        except Exception:
            raise StorageError() from None


def store_for(sessions) -> ObjectStore:
    return sessions.kw["info"]["object_store"]


def settings_for(sessions):
    return sessions.kw["info"]["settings"]
