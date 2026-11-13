# Build plan: Render backend and finals features

Date: 13 November 2026
Branch: `render-finals`
Source: the SpecLens finals roadmap (code gaps, Track A features, Render plan and build list).

## Goal

Move the backend from one Lightsail VM to Render, with Postgres, Key Value, a background worker, cron jobs and Cloudflare R2, and build the finals features: any spec and any part, a benchmark, masks with sizes in millimetres, visual memory, a quality dashboard, batch inspection and phone capture.

## Ground rules

- Local development and the test suite keep working with no cloud services. Every new backend has a local default:

  | Concern | Production | Local default |
  |---|---|---|
  | Database | Render Postgres (`DATABASE_URL`) | SQLite file in `var/` |
  | Photos, masks, crops | Cloudflare R2 (`R2_*`) | `var/workspace/` |
  | Rate limits | Render Key Value (`REDIS_URL`) | in-process counters |
  | Jobs | Render background worker (`SPECLENS_WORKER=external`) | the API runs jobs in a thread pool |

- The public HTTP contract stays the same. `/inspect` and `/compare` still answer with the finished result, so the page and its browser tests need no rewrite. In production these routes queue a job and wait for the worker, so the API process never calls the model.
- No test makes a billable model or Hindsight call.
- One commit per task: a subject line, a blank line, then a body that says what changed and why.

## Tasks

### Platform

1. **P1 Render image.** `backend/Dockerfile` without the frontend build stage, `GET /healthz` that touches nothing expensive, and `render.yaml`.
2. **P2 Database layer.** SQLAlchemy Core behind the existing `Store` methods, so the same code runs on SQLite and Postgres. Alembic migrations, applied on start-up and by Render's `preDeployCommand`. Real columns for owner, verdict, class, confidence, cost and latency, plus the full record as JSON. Spec text moves to a `spec_revisions` table and is restored on read. The overview route gains cursor paging.
3. **P3 Media store.** A `MediaStore` interface with a local backend and an R2 backend through boto3. The `/files/workspace/...` route checks the owner and streams the file, so the page's content security policy does not change.
4. **P4 Shared rate limits.** The hourly limits move behind a limiter interface: in-process counters locally, fixed-window counters in Key Value in production. Writes are refused if Key Value is unreachable.
5. **P5 Ledger and atomic budget.** A `model_calls` table replaces `var/ledger.jsonl` (existing rows are imported once). A one-row `budget` table holds spent and reserved amounts. Each model call reserves its expected cost with one conditional `UPDATE` before the call and settles after it, so parallel calls cannot overshoot.
6. **P6 Jobs and worker.** A `jobs` table, `python -m app.worker`, claiming with `FOR UPDATE SKIP LOCKED` on Postgres, retries with backoff, recovery of stale jobs, and job routes: create, read, and a server-sent event stream with a heartbeat.
7. **P7 Memory outbox.** A failed Hindsight sync leaves an outbox row that the worker retries with backoff. The Retry button stays.
8. **P8 Retention purge.** `python -m app.jobs.purge` deletes records, media and Hindsight documents older than `RETENTION_DAYS`.
9. **P9 Data move.** `scripts/migrate_to_render.py` copies the SQLite records and photos into Postgres and R2. The Vercel rewrite change is documented, not committed, because it must wait until the Render service exists.
10. **P10 Errors and logs.** Sentry when `SENTRY_DSN` is set, a request ID on every response, and JSON logs.
11. **P11 CI.** A second pytest run against a Postgres service container.
12. **P12 Delete and export.** `GET /api/workspace/export` and `DELETE /api/workspace/data` for the visitor, including their Hindsight banks.

### Product

13. **A1 Any spec, any part.** Reject classes, clauses, size limits and part width come from the specification: a deterministic parser by default, the model's taxonomy on request, and PDF import. Classes drive the model schema, the correction form and validation.
14. **A3 Masks and millimetres.** SAM 3.1 on Reject verdicts. The model also returns the part's box, which gives millimetres per pixel from the spec's part width. Defect length and area are compared with any size limit in the clause.
15. **A4 Visual memory.** A correction saves the defect crop. Recall attaches up to two crops after the photo, before the written standards.
16. **A2 Benchmark.** `scripts/benchmark.py` runs labelled cases with memory off and on, and reports precision, recall, F1, a confusion matrix and memory lift with bootstrap 95% intervals. Results are served from `/api/eval`. Running it is billable, so it only runs on request.
17. **A5 Quality dashboard.** `GET /api/workspace/dashboard` and a dashboard section: reject rate by day, defect Pareto, agreement with engineers, corrections per week, memory citations, cost and cache share.
18. **A6 Batch inspection.** Several photos become one job each, with live progress, a review queue sorted by confidence and CSV export.
19. **A8 Phone capture.** A web app manifest and a camera button.

## Deliberate differences from the roadmap

- Job progress is read from Postgres rather than Key Value pub/sub. At the expected load this is a few primary-key reads a second, and it removes a moving part.
- Photos are streamed by the API rather than redirected to presigned URLs, so the content security policy stays `img-src 'self'`. Presigned uploads remain a later step.
- The workspace page is extended with new components rather than rewritten around TanStack Query, to keep the existing browser tests valid.

## Verification

- `scripts/check.sh` (build, lint, pytest, Playwright) passes after every task.
- The database layer is also tested against a real Postgres server.
- No live model, Hindsight, Render or R2 call is made without the team's approval.

## After this branch

- Create the Render Blueprint from `render.yaml`, fill the secrets, and create the R2 bucket.
- Run `scripts/migrate_to_render.py`, then point the two rewrites in `frontend/vercel.json` at the Render API.
- Run the benchmark once with a budget the team approves.
