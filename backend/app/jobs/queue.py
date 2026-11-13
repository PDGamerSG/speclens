"""A job queue in the database, so a job is never lost and any worker can take it.

The API writes a job and returns. A worker claims it with FOR UPDATE SKIP LOCKED on Postgres; a conditional
UPDATE makes the claim safe on SQLite too. Retryable failures go back to the queue with backoff, and a job whose
worker died is picked up again after STALE_AFTER seconds.

SPECLENS_WORKER=inline (the default) runs jobs in a thread pool inside the API, for local use and tests.
SPECLENS_WORKER=external leaves them to `python -m app.worker`, which is how Render runs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import sqlalchemy as sa

from .. import db
from ..workspace.store import now

log = logging.getLogger('speclens.jobs')
MAX_ATTEMPTS = 3
STALE_AFTER = 600
BACKOFF = 10
PUBLIC_FIELDS = ('id', 'kind', 'batch_id', 'status', 'result', 'error', 'attempts', 'created_at')


def mode() -> str:
    return 'external' if os.environ.get('SPECLENS_WORKER', 'inline').strip() == 'external' else 'inline'


class JobFailed(Exception):
    def __init__(self, status_code: int, detail: str, retryable: bool = False):
        super().__init__(detail)
        self.status_code, self.detail, self.retryable = status_code, detail, retryable


class JobQueue:
    def __init__(self, engine: Callable[[], sa.Engine], runner: Callable[[dict], dict] | None = None,
                 *, workers: int = 4):
        self._engine = engine
        self.runner = runner
        self._pool: ThreadPoolExecutor | None = None
        self._workers = workers

    @property
    def engine(self) -> sa.Engine:
        return self._engine()

    # Writing and reading -----------------------------------------------------------------------------------

    def submit(self, kind: str, payload: dict, owner_id: str = '', batch_id: str | None = None,
               id: str | None = None) -> dict:
        t = time.time()
        job = {'id': id or f'job-{uuid.uuid4().hex[:20]}', 'kind': kind, 'owner_id': owner_id, 'batch_id': batch_id,
               'status': 'queued', 'payload': payload, 'attempts': 0, 'run_after': t, 'created_at': now(),
               'updated_at': t}
        with self.engine.begin() as c:
            c.execute(db.jobs.insert().values(**job))
        if mode() == 'inline' and self.runner is not None:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(self._workers, thread_name_prefix='speclens-job')
            self._pool.submit(self.process, job['id'])
        return job

    def get(self, id: str) -> dict | None:
        with self.engine.connect() as c:
            row = c.execute(sa.select(db.jobs).where(db.jobs.c.id == id)).first()
        return dict(row._mapping) if row else None

    def batch(self, batch_id: str) -> list[dict]:
        with self.engine.connect() as c:
            rows = c.execute(sa.select(db.jobs).where(db.jobs.c.batch_id == batch_id)
                             .order_by(db.jobs.c.created_at, db.jobs.c.id)).all()
        return [dict(r._mapping) for r in rows]

    @staticmethod
    def public(job: dict) -> dict:
        return {k: job.get(k) for k in PUBLIC_FIELDS}

    # Working -----------------------------------------------------------------------------------------------

    def claim(self, id: str | None = None) -> dict | None:
        jobs = db.jobs
        t = time.time()
        with self.engine.begin() as c:
            query = sa.select(jobs.c.id).where(jobs.c.status == 'queued', jobs.c.run_after <= t)
            if id is not None:
                query = query.where(jobs.c.id == id)
            query = query.order_by(jobs.c.run_after).limit(1)
            if c.dialect.name == 'postgresql':
                query = query.with_for_update(skip_locked=True)
            found = c.execute(query).scalar()
            if found is None:
                return None
            claimed = c.execute(jobs.update().where(jobs.c.id == found, jobs.c.status == 'queued').values(
                status='running', locked_at=t, updated_at=t, attempts=jobs.c.attempts + 1))
            if claimed.rowcount != 1:
                return None
            return dict(c.execute(sa.select(jobs).where(jobs.c.id == found)).one()._mapping)

    def complete(self, id: str, result: dict) -> None:
        with self.engine.begin() as c:
            c.execute(db.jobs.update().where(db.jobs.c.id == id).values(
                status='done', result=result, error=None, locked_at=None, updated_at=time.time()))

    def fail(self, job: dict, error: JobFailed) -> str:
        """Requeue a retryable failure with backoff, or mark the job failed. Returns the new status."""
        retry = error.retryable and job['attempts'] < MAX_ATTEMPTS
        t = time.time()
        status = 'queued' if retry else 'failed'
        with self.engine.begin() as c:
            c.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(
                status=status, error={'status_code': error.status_code, 'detail': error.detail},
                run_after=t + BACKOFF * 2 ** (job['attempts'] - 1) if retry else job['run_after'],
                locked_at=None, updated_at=t))
        return status

    def process(self, id: str | None = None) -> dict | None:
        """Claim one job (a given one, or the next due), run it and record the outcome."""
        job = self.claim(id)
        return None if job is None else self.run_claimed(job)

    def run_claimed(self, job: dict) -> dict:
        try:
            self.complete(job['id'], self.runner(job))
        except JobFailed as error:
            self.fail(job, error)
        except Exception:  # an unexpected bug must not leave the job running forever
            log.exception('Job %s failed unexpectedly', job['id'])
            self.fail(job, JobFailed(500, 'The job failed unexpectedly. Try again.', retryable=False))
        return self.get(job['id'])

    def recover_stale(self) -> int:
        """Jobs whose worker stopped mid-run go back to the queue, or fail after MAX_ATTEMPTS."""
        jobs = db.jobs
        t = time.time()
        with self.engine.begin() as c:
            requeued = c.execute(jobs.update().where(
                jobs.c.status == 'running', jobs.c.locked_at < t - STALE_AFTER, jobs.c.attempts < MAX_ATTEMPTS,
            ).values(status='queued', run_after=t, locked_at=None, updated_at=t)).rowcount
            c.execute(jobs.update().where(
                jobs.c.status == 'running', jobs.c.locked_at < t - STALE_AFTER,
            ).values(status='failed', locked_at=None, updated_at=t,
                     error={'status_code': 500, 'detail': 'The worker stopped during this job.'}))
        return requeued

    async def wait(self, id: str, timeout: float, interval: float = 0.25) -> dict:
        """Wait for a job to finish without holding a thread. Returns the job as last read."""
        deadline = time.monotonic() + timeout
        while True:
            job = await asyncio.to_thread(self.get, id)
            if job is None or job['status'] in ('done', 'failed') or time.monotonic() >= deadline:
                return job
            await asyncio.sleep(interval)
