"""Background worker: `python -m app.worker`.

Claims queued jobs and runs them, WORKER_CONCURRENCY at a time (default 4; each job mostly waits on the model).
Every minute it returns stale jobs to the queue and retries memory syncs that are due. On SIGTERM it stops
claiming and lets running jobs finish, which fits inside Render's shutdown grace period.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .observability import request_id, setup

log = logging.getLogger('speclens.worker')
IDLE_SLEEP = 0.5
HOUSEKEEPING_EVERY = 60


class Worker:
    def __init__(self, jobs, service, *, concurrency: int = 4):
        self.jobs = jobs
        self.service = service
        self.concurrency = concurrency
        self.stopping = threading.Event()
        self.slots = threading.Semaphore(concurrency)

    def housekeeping(self) -> None:
        if requeued := self.jobs.recover_stale():
            log.warning('Returned %d stale jobs to the queue', requeued)
        outcome = self.service.drain_outbox()
        if any(outcome.values()):
            log.info('Memory outbox: %d synced, %d still pending', outcome['synced'], outcome['pending'])

    def run_one(self) -> bool:
        """Claim and run one job in this thread. Returns False when the queue was empty."""
        job = self.jobs.claim()
        if job is None:
            return False
        self.slots.acquire()
        self._run(job)
        return True

    def serve(self) -> None:
        last_housekeeping = 0.0
        with ThreadPoolExecutor(self.concurrency, thread_name_prefix='speclens-worker') as pool:
            while not self.stopping.is_set():
                if time.monotonic() - last_housekeeping > HOUSEKEEPING_EVERY:
                    last_housekeeping = time.monotonic()
                    try:
                        self.housekeeping()
                    except Exception:
                        log.exception('Housekeeping failed')
                if not self.slots.acquire(timeout=IDLE_SLEEP):
                    continue
                job = None
                try:
                    job = self.jobs.claim()
                except Exception:
                    log.exception('Could not claim a job')
                if job is None:
                    self.slots.release()
                    self.stopping.wait(IDLE_SLEEP)
                    continue
                pool.submit(self._run, job)
        log.info('Worker stopped')

    def _run(self, job: dict) -> None:
        token = request_id.set(job['payload'].get('request_id') or job['id'])
        try:
            started = time.monotonic()
            finished = self.jobs.run_claimed(job)
            log.info('Job %s (%s) %s in %.1fs', job['id'], job['kind'], finished['status'], time.monotonic() - started)
        finally:
            request_id.reset(token)
            self.slots.release()


def main() -> None:
    setup('worker')
    from .workspace.routes import jobs, service
    worker = Worker(jobs, service, concurrency=int(os.environ.get('WORKER_CONCURRENCY', '4')))
    signal.signal(signal.SIGTERM, lambda *_: worker.stopping.set())
    signal.signal(signal.SIGINT, lambda *_: worker.stopping.set())
    log.info('Worker started with %d slots', worker.concurrency)
    worker.serve()


if __name__ == '__main__':
    main()
