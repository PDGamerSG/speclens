"""Retention purge: `python -m app.jobs.purge`. Render runs it nightly as the speclens-purge cron job.

Deletes records older than RETENTION_DAYS (default 90) with their photos, masks, crops and Hindsight
documents, and finished jobs older than seven days with any upload they left behind.
"""
from __future__ import annotations

import json
import logging
import os
import sys


def main() -> int:
    from ..observability import setup
    setup('purge')
    days = int(os.environ.get('RETENTION_DAYS', '90'))
    if days < 1:
        sys.exit('RETENTION_DAYS must be at least 1.')
    from ..workspace.routes import service
    summary = service.purge(days)
    logging.getLogger('speclens.purge').info('Purged records older than %d days: %s', days, json.dumps(summary))
    return 1 if summary['media_failed'] or summary['memory_failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
