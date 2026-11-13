"""Copy SpecLens data from the Lightsail server into Render Postgres and Cloudflare R2.

Run it on a machine that has a copy of the server's var/ folder:

    DATABASE_URL=... R2_ENDPOINT=... R2_BUCKET=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... \\
      .venv/bin/python scripts/migrate_to_render.py --var path/to/var

It reads a temporary copy of speclens.sqlite3, so the source file is never changed. Records that already exist
in the target are skipped, so the script can be run again after a partial copy. It imports ledger.jsonl into the
target's model call history once. Photos in var/workspace go to R2 (or to --media-target for a local dry run).
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import sqlalchemy as sa  # noqa: E402

from app import db  # noqa: E402
from app.media import LocalMedia, content_type, media_from_env  # noqa: E402

RECORD_TABLES = (db.spec_revisions, db.inspections, db.corrections, db.comparisons, db.benchmark_runs)


def copy_records(source: sa.Engine, target: sa.Engine) -> dict:
    counts = {}
    for table in RECORD_TABLES:
        with source.connect() as c:
            rows = [dict(r._mapping) for r in c.execute(sa.select(table))]
        with target.begin() as c:
            existing = set(c.execute(sa.select(table.c.id)).scalars())
            fresh = [r for r in rows if r['id'] not in existing]
            if fresh:
                c.execute(table.insert(), fresh)
        counts[table.name] = len(fresh)
    return counts


def copy_ledger(ledger_file: Path, target: sa.Engine) -> int:
    from app.meta import ledger
    with target.begin() as c:
        if c.execute(sa.select(db.budget.c.imported_ledger).where(db.budget.c.id == 1)).scalar():
            return 0
        rows = ledger._legacy_rows(ledger_file)
        if rows:
            c.execute(db.model_calls.insert(), [ledger._row(r) for r in rows])
        c.execute(db.budget.update().where(db.budget.c.id == 1).values(
            imported_ledger=True, **ledger._totals(rows, db.budget)))
    return len(rows)


def copy_media(folder: Path, media) -> int:
    count = 0
    for path in sorted(folder.rglob('*')):
        if path.is_file() and not path.name.endswith('.part'):
            key = path.relative_to(folder).as_posix()
            media.put(key, path.read_bytes(), content_type(key))
            count += 1
    return count


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--var', type=Path, required=True, help="the server's var/ folder")
    parser.add_argument('--target', default='', help='target database URL (defaults to DATABASE_URL)')
    parser.add_argument('--media-target', type=Path, help='copy photos to this local folder instead of R2')
    args = parser.parse_args(argv)

    source_file = args.var / 'speclens.sqlite3'
    if not source_file.is_file():
        sys.exit(f'No database at {source_file}.')
    target_url = args.target or db.default_url()
    if target_url.startswith('sqlite') and not args.target:
        sys.exit('Set DATABASE_URL or --target to the Render Postgres URL.')
    media = LocalMedia(args.media_target) if args.media_target else media_from_env(Path(tempfile.mkdtemp()))
    if media.kind == 'local' and not args.media_target:
        sys.exit('Set the four R2_* variables, or pass --media-target for a local copy.')

    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / 'source.sqlite3'
        shutil.copy2(source_file, copy)
        for suffix in ('-wal', '-shm'):
            if (side := source_file.with_name(source_file.name + suffix)).exists():
                shutil.copy2(side, copy.with_name(copy.name + suffix))
        source = db.engine(copy)
        target = db.engine(target_url)
        summary = copy_records(source, target)
        source.dispose()
    summary['model_calls'] = copy_ledger(args.var / 'ledger.jsonl', target)
    summary['media_files'] = copy_media(args.var / 'workspace', media) if (args.var / 'workspace').is_dir() else 0
    print('Copied:', ', '.join(f'{k} {v}' for k, v in summary.items()))
    return summary


if __name__ == '__main__':
    main()
