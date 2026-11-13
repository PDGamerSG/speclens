"""Photos live in a media store: a local folder in development, R2 in production, never a visitor-chosen path."""
import io

import pytest
from PIL import Image

from app.media import LocalMedia, R2Media, check_key, media_from_env


class FakeS3:
    class Missing(Exception):
        response = {'Error': {'Code': 'NoSuchKey'}}

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise self.Missing()
        return {'Body': io.BytesIO(self.objects[(Bucket, Key)][0])}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.mark.parametrize('key', ['../.env', '/etc/passwd', 'a/../b.jpg', '', '.hidden', 'a//b.jpg'])
def test_media_keys_cannot_escape_their_store(key):
    with pytest.raises(ValueError):
        check_key(key)


def test_local_media_round_trip(tmp_path):
    media = LocalMedia(tmp_path)
    media.put('uploads/job-1', b'bytes', 'image/jpeg')
    assert media.get('uploads/job-1') == b'bytes'
    media.delete('uploads/job-1')
    assert media.get('uploads/job-1') is None


def test_r2_media_uses_one_bucket_and_a_prefix():
    client = FakeS3()
    media = R2Media('speclens-media', client=client)
    media.put('insp-1.jpg', b'photo', 'image/jpeg')
    assert client.objects[('speclens-media', 'workspace/insp-1.jpg')] == (b'photo', 'image/jpeg')
    assert media.get('insp-1.jpg') == b'photo'
    assert media.get('insp-2.jpg') is None
    media.delete('insp-1.jpg')
    assert client.objects == {}


def test_r2_is_chosen_only_when_every_setting_is_present(tmp_path, monkeypatch):
    for name in ('R2_ENDPOINT', 'R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY'):
        monkeypatch.setenv(name, 'set')
    monkeypatch.setenv('R2_ENDPOINT', 'https://account.r2.cloudflarestorage.com')
    assert media_from_env(tmp_path).kind == 'r2'
    monkeypatch.setenv('R2_SECRET_ACCESS_KEY', '')
    assert media_from_env(tmp_path).kind == 'local'


def test_workspace_photos_are_served_from_the_media_store(tmp_path, monkeypatch):
    from test_workspace_api import png, setup_client
    client, routes = setup_client(tmp_path, monkeypatch)
    fake = FakeS3()
    routes.service.media = R2Media('bucket', client=fake)
    item = client.post('/api/workspace/inspect', files={'file': ('part.png', png(), 'image/png')},
                       data={'memory_enabled': 'false'}).json()
    assert ('bucket', f'workspace/{item["id"]}.jpg') in fake.objects
    photo = client.get(item['image_url'])
    assert photo.status_code == 200
    assert photo.headers['content-type'] == 'image/jpeg'
    assert Image.open(io.BytesIO(photo.content)).size == (100, 100)
    assert client.get('/files/workspace/insp-unknown.jpg').status_code == 404
    assert client.get('/files/workspace/..%2F.env').status_code == 404
