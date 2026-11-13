"""With REDIS_URL set, the hourly limits live in Key Value and hold across API instances."""
from fastapi.testclient import TestClient

import app.public as public
from test_workspace_api import setup_client


class FakeRedis:
    def __init__(self, down=False):
        self.values, self.down = {}, down

    def pipeline(self):
        return FakePipe(self)


class FakePipe:
    def __init__(self, redis):
        self.redis, self.ops = redis, []

    def incrby(self, name, n):
        self.ops.append(('incr', name, n))

    def decrby(self, name, n):
        self.ops.append(('incr', name, -n))

    def expire(self, name, seconds):
        self.ops.append(('expire', name, seconds))

    def execute(self):
        if self.redis.down:
            raise ConnectionError('Key Value is unreachable')
        out = []
        for op, name, n in self.ops:
            if op == 'incr':
                self.redis.values[name] = self.redis.values.get(name, 0) + n
                out.append(self.redis.values[name])
            else:
                out.append(True)
        return out


def test_two_api_instances_share_one_visitor_limit():
    shared = FakeRedis()
    first, second = public.RedisLimiter('redis://kv', client=shared), public.RedisLimiter('redis://kv', client=shared)
    assert first.allow([('visitor:a', 2), ('ip:1', 8)], 1)
    assert second.allow([('visitor:a', 2), ('ip:1', 8)], 1)
    assert not first.allow([('visitor:a', 2), ('ip:1', 8)], 1)
    ip_count = [v for k, v in shared.values.items() if ':ip:1:' in k][0]
    assert ip_count == 2, 'a refused call gives back its increments'


def test_a_comparison_costs_two_in_the_shared_limit():
    limiter = public.RedisLimiter('redis://kv', client=FakeRedis())
    assert limiter.allow([('visitor:a', 3), ('ip:1', 12)], 2)
    assert not limiter.allow([('visitor:a', 3), ('ip:1', 12)], 2)


def test_writes_stop_with_a_clear_error_when_key_value_is_down(tmp_path, monkeypatch):
    setup_client(tmp_path, monkeypatch)
    from app.main import app
    monkeypatch.setattr(public, 'PUBLIC_MODE', True)
    monkeypatch.setattr(public, '_redis', public.RedisLimiter('redis://kv', client=FakeRedis(down=True)))
    monkeypatch.setenv('REDIS_URL', 'redis://kv')
    client = TestClient(app)
    response = client.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'})
    assert response.status_code == 503
    assert 'limiter' in response.json()['detail']
    assert client.get('/api/workspace/overview').status_code == 200, 'reads do not need the limiter'
