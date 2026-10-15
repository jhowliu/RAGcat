"""Object storage port: S3 in AWS, a local folder in development.

Both adapters hand the browser the same presigned-POST shape, so the upload code in the web
app does not change between environments.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import boto3

from ragcat.shared.config import Settings
from ragcat.shared.errors import Forbidden, ValidationError


class ObjectStore(Protocol):
    def presign_upload(self, key: str, content_type: str, max_bytes: int) -> dict[str, Any]: ...
    def get(self, key: str) -> bytes: ...
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def url_for(self, key: str) -> str: ...


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LocalObjectStore:
    UPLOAD_URL = "/dev/s3/upload"
    OBJECT_URL = "/dev/objects/"

    def __init__(self, root: Path, secret: str) -> None:
        self.root = root / "objects"
        self.root.mkdir(parents=True, exist_ok=True)
        self._secret = secret.encode()

    def _sign(self, *parts: str) -> str:
        return hmac.new(self._secret, "|".join(parts).encode(), hashlib.sha256).hexdigest()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValidationError("Invalid object key")
        return path

    def presign_upload(self, key: str, content_type: str, max_bytes: int, expires_in: int = 900) -> dict[str, Any]:
        expires = int(time.time()) + expires_in
        fields = {
            "key": key,
            "Content-Type": content_type,
            "x-max-bytes": str(max_bytes),
            "x-expires": str(expires),
        }
        fields["x-signature"] = self._sign(key, content_type, fields["x-max-bytes"], fields["x-expires"])
        return {"method": "POST", "url": self.UPLOAD_URL, "fields": fields, "expires_at": _iso(expires)}

    def accept_upload(self, fields: dict[str, str], data: bytes, content_type: str) -> str:
        """Enforce the same rules an S3 POST policy would; returns the object key."""
        key = fields.get("key", "")
        expected = self._sign(key, fields.get("Content-Type", ""), fields.get("x-max-bytes", ""), fields.get("x-expires", ""))
        if not hmac.compare_digest(expected, fields.get("x-signature", "")):
            raise Forbidden("Upload policy signature does not match")
        if int(fields["x-expires"]) < time.time():
            raise Forbidden("Upload policy expired")
        if content_type != fields["Content-Type"]:
            raise Forbidden("Content-Type does not match the upload policy")
        if not 0 < len(data) <= int(fields["x-max-bytes"]):
            raise Forbidden("File size is outside the upload policy")
        self.put(key, data, content_type)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        folder = self._path(prefix.rstrip("/"))
        if folder.is_dir():
            for file in sorted(folder.rglob("*"), reverse=True):
                file.unlink() if file.is_file() else file.rmdir()
            folder.rmdir()

    def url_for(self, key: str) -> str:
        return self.OBJECT_URL + key

    def file_path(self, key: str) -> Path:
        return self._path(key)


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.bucket
        self.s3 = boto3.client("s3", region_name=settings.region)

    def presign_upload(self, key: str, content_type: str, max_bytes: int, expires_in: int = 900) -> dict[str, Any]:
        post = self.s3.generate_presigned_post(
            Bucket=self.bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, max_bytes]],
            ExpiresIn=expires_in,
        )
        return {"method": "POST", "url": post["url"], "fields": post["fields"], "expires_at": _iso(int(time.time()) + expires_in)}

    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, CacheControl="public, max-age=31536000, immutable")

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})

    def url_for(self, key: str) -> str:
        # TODO(infra): switch to CloudFront signed URLs under /pages/* once the distribution exists.
        return self.s3.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600)
