"""Photos, masks and reference crops: a local folder in development, Cloudflare R2 in production.

R2 is used when R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are all set. Keys are short
relative names such as "insp-123.jpg" or "uploads/job-1"; they never come from a visitor unchecked.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.\-]*(/[A-Za-z0-9][A-Za-z0-9_.\-]*)*$')


def check_key(key: str) -> str:
    if not _KEY.fullmatch(key) or '..' in key or len(key) > 200:
        raise ValueError('Invalid media key.')
    return key


class MediaStore(Protocol):
    kind: str

    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> None: ...


class LocalMedia:
    kind = 'local'

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.root / check_key(key)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.part')
        temporary.write_bytes(data)
        temporary.replace(path)

    def get(self, key: str) -> bytes | None:
        path = self.path(key)
        return path.read_bytes() if path.is_file() else None

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


class R2Media:
    kind = 'r2'

    def __init__(self, bucket: str, *, endpoint: str = '', access_key: str = '', secret_key: str = '',
                 prefix: str = 'workspace/', client=None):
        self.bucket = bucket
        self.prefix = prefix
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=access_key,
                                  aws_secret_access_key=secret_key, region_name='auto',
                                  config=Config(retries={'max_attempts': 4, 'mode': 'standard'},
                                                connect_timeout=5, read_timeout=30))
        self.client = client

    def _name(self, key: str) -> str:
        return self.prefix + check_key(key)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._name(key), Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._name(key))
        except Exception as error:
            code = getattr(error, 'response', {}).get('Error', {}).get('Code')
            if code in ('NoSuchKey', '404', 'NotFound'):
                return None
            raise
        return response['Body'].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._name(key))


def media_from_env(local_root: Path) -> MediaStore:
    settings = {name: os.environ.get(name, '').strip() for name in
                ('R2_ENDPOINT', 'R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY')}
    if all(settings.values()):
        return R2Media(settings['R2_BUCKET'], endpoint=settings['R2_ENDPOINT'],
                       access_key=settings['R2_ACCESS_KEY_ID'], secret_key=settings['R2_SECRET_ACCESS_KEY'])
    return LocalMedia(local_root)


def content_type(key: str) -> str:
    return 'image/png' if key.endswith('.png') else 'image/jpeg'
