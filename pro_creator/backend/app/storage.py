from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import boto3
from botocore.client import Config

from app.config import (
    PROJECTS_DIR,
    PROJECTS_URL_BASE,
    S3_PUBLIC_URL,
    S3_ACCESS_KEY,
    S3_BUCKET,
    S3_ENDPOINT,
    S3_REGION,
    S3_SECRET_KEY,
    S3_USE_SSL,
    STORAGE_BACKEND,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StorageObject:
    key: str
    url: str


def project_key(project_id: str, relative_path: str) -> str:
    normalized = relative_path.lstrip("/")
    return f"{project_id}/{normalized}"


class StorageClient:
    def __init__(self) -> None:
        self.backend = STORAGE_BACKEND
        if self.backend == "s3":
            self._s3 = boto3.client(
                "s3",
                endpoint_url=S3_ENDPOINT,
                aws_access_key_id=S3_ACCESS_KEY,
                aws_secret_access_key=S3_SECRET_KEY,
                region_name=S3_REGION,
                use_ssl=S3_USE_SSL,
                config=Config(s3={"addressing_style": "path"}),
            )
        else:
            self._s3 = None

    def ensure_project_dirs(self, project_id: str) -> Path:
        if self.backend != "local":
            return PROJECTS_DIR / project_id
        project_path = PROJECTS_DIR / project_id
        (project_path / "audio").mkdir(parents=True, exist_ok=True)
        (project_path / "images").mkdir(parents=True, exist_ok=True)
        (project_path / "video").mkdir(parents=True, exist_ok=True)
        (project_path / "voice_profiles").mkdir(parents=True, exist_ok=True)
        (project_path / "script.txt").touch(exist_ok=True)
        (project_path / "scenes.json").touch(exist_ok=True)
        return project_path

    def write_text(self, key: str, content: str) -> None:
        if self.backend == "s3":
            self._s3.put_object(Bucket=S3_BUCKET, Key=key, Body=content.encode("utf-8"))
        else:
            path = PROJECTS_DIR / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def write_bytes(self, key: str, content: bytes, content_type: Optional[str] = None) -> None:
        if self.backend == "s3":
            extra = {"ContentType": content_type} if content_type else {}
            self._s3.put_object(Bucket=S3_BUCKET, Key=key, Body=content, **extra)
        else:
            path = PROJECTS_DIR / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def read_text(self, key: str) -> str:
        if self.backend == "s3":
            response = self._s3.get_object(Bucket=S3_BUCKET, Key=key)
            return response["Body"].read().decode("utf-8")
        path = PROJECTS_DIR / key
        if not path.exists():
            return ""
        return path.read_text()

    def read_bytes(self, key: str) -> bytes:
        if self.backend == "s3":
            response = self._s3.get_object(Bucket=S3_BUCKET, Key=key)
            return response["Body"].read()
        path = PROJECTS_DIR / key
        if not path.exists():
            return b""
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        if self.backend == "s3":
            try:
                self._s3.head_object(Bucket=S3_BUCKET, Key=key)
                return True
            except Exception:
                return False
        return (PROJECTS_DIR / key).exists()

    def delete_prefix(self, prefix: str) -> None:
        if self.backend == "s3":
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
                for obj in page.get("Contents", []):
                    self._s3.delete_object(Bucket=S3_BUCKET, Key=obj["Key"])
        else:
            path = PROJECTS_DIR / prefix
            if path.exists():
                for item in path.rglob("*"):
                    if item.is_file():
                        item.unlink()
                for item in sorted(path.rglob("*"), reverse=True):
                    if item.is_dir():
                        item.rmdir()

    def delete_key(self, key: str) -> None:
        if self.backend == "s3":
            self._s3.delete_object(Bucket=S3_BUCKET, Key=key)
        else:
            path = PROJECTS_DIR / key
            if path.exists():
                path.unlink()

    def list_keys(self, prefix: str) -> Iterable[str]:
        if self.backend == "s3":
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
                for obj in page.get("Contents", []):
                    yield obj["Key"]
        else:
            path = PROJECTS_DIR / prefix
            if not path.exists():
                return
            for item in path.rglob("*"):
                if item.is_file():
                    yield str(item.relative_to(PROJECTS_DIR))

    def public_url(self, key: str) -> str:
        if self.backend == "s3":
            if S3_PUBLIC_URL:
                return f"{S3_PUBLIC_URL}/{key}"
            return self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": key},
                ExpiresIn=3600,
            )
        return f"{PROJECTS_URL_BASE}/{key}"


storage_client = StorageClient()
