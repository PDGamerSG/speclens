# HTTP API reference

This reference describes the original inspection/demo API under `/api/workspace`. The signed-in team domain uses `/api/workspace/pilot`; see the [Factory API reference](factory.md) for authentication, server-enforced roles, approved revisions, controlled captures, reviews, standards, validation and complete lot reports. Those factory rules take precedence over anonymous examples below when signed in.

## Basics

- **Base URL:** the same origin as the page. Locally that is `http://localhost:8770`. The live site is `https://speclens.pallabdas.me`.
- **Authentication:** anonymous public demos use the `speclens_workspace` visitor cookie. Factory accounts use a separate expiring/revocable `speclens_session` cookie and active team membership, including on old inspection/media/job routes. An invalid factory session returns 401 rather than falling back. With public mode off, anonymous development routes remain shared; factory access controls still apply.
- **Scope:** most routes take `factory`, `part_family` and `spec_text`. Together they select one workspace. Leave them out to use `Bangalore Foods`, `Whole hazelnut` and the default specification (`backend/app/workspace/routes.py:25-26`, `backend/app/workspace/routes.py:50-56`).
- **Limits in public mode:** non-factory POSTs except the free rule parser count toward 30 per browser and 120 per address per hour; a comparison counts as two. `/api/workspace/pilot/` uses separate auth/role controls and independent registration/login/join limits. Foreign writes outside exact allowed origins get 403.

## Workspace routes

| Method | Path | Outside calls | What it does | Defined in |
| --- | --- | --- | --- | --- |
| `GET` | `/healthz` | None | Load balancer probe; reads nothing | `backend/app/main.py`, `healthz` |
| `GET` | `/api/workspace/status` | None | Reports configuration, spend and defaults | `backend/app/workspace/routes.py`, `status` |
| `GET` | `/api/workspace/samples` | None | Lists the six sample parts | `routes.py`, `samples` |
| `GET` | `/api/workspace/overview` | None | One page of history for a scope, its corrections, comparisons, counts and reject classes. `limit` (1-500, default 100) and `before` (a `created_at` cursor) page the inspections | `routes.py`, `overview` |
| `POST` | `/api/workspace/inspect` | 1 vision call, a SAM mask per boxed defect, plus a recall with memory on | Inspects one part. With `SPECLENS_WORKER=external` it queues a job and waits for the worker | `routes.py`, `inspect_part` |
| `POST` | `/api/workspace/compare` | 2 vision calls and 1 recall | Inspects one part with and without memory | `routes.py`, `compare` |
| `POST` | `/api/workspace/jobs/inspect` | As `/inspect`, run later | Queues one inspection and answers `202` with the job. Optional `batch_id` (`batch-` and 8 to 32 hex characters) groups jobs | `routes.py`, `queue_inspection` |
| `POST` | `/api/workspace/jobs/compare` | As `/compare`, run later | Queues one comparison and answers `202` | `routes.py`, `queue_comparison` |
| `GET` | `/api/workspace/jobs/{id}` | None | A job's status, result or error | `routes.py`, `get_job` |
| `GET` | `/api/workspace/jobs/{id}/events` | None | Server-sent events: `status` on each change, then `done` or `failed`, with a 15 s ping | `routes.py`, `job_events` |
| `GET` | `/api/workspace/batches/{id}` | None | Every job in a batch, with counts and a `finished` flag | `routes.py`, `get_batch` |
| `POST` | `/api/workspace/corrections` | Hindsight retain | Saves a correction and a crop of the corrected region, then sends it to memory. `defect_type` must be one of the specification's classes | `routes.py`, `correct` |
| `POST` | `/api/workspace/corrections/{id}/sync` | Hindsight retain, unless already synced | Retries a pending correction | `routes.py`, `sync_correction` |
| `POST` | `/api/workspace/recall` | Hindsight recall | Returns recalled standards for a scope | `routes.py`, `recall` |
| `POST` | `/api/workspace/reflect` | Hindsight reflect | Returns a written summary of the standards | `routes.py`, `reflect` |
| `POST` | `/api/workspace/specs/parse` | None | Reads reject classes, clauses, limits and part width by rules. Not counted against the hourly limit | `routes.py`, `parse_specification` |
| `POST` | `/api/workspace/specs/extract` | 1 model call with `use_model=true` | Reads a PDF or text file, or text. With `use_model`, the model's reading is saved for that specification | `routes.py`, `extract_specification` |
| `GET` | `/api/workspace/dashboard` | None | Totals, daily decisions, defect Pareto, weekly corrections, cost and time for a scope over `days` (1-365, default 30) | `routes.py`, `quality_dashboard` |
| `GET` | `/api/workspace/export` | None | Every record the visitor stored, as a JSON download | `routes.py`, `export_data` |
| `DELETE` | `/api/workspace/data` | Hindsight bank deletes | With the body `{"confirm": "DELETE"}`, deletes the visitor's records, media and memory banks | `routes.py`, `delete_data` |
| `GET` | `/api/eval` | None | The latest live benchmark run, without per-case rows | `backend/app/main.py`, `get_eval` |

Every response carries `X-Request-ID`. A valid incoming ID is kept and stored on any job the request queues.

### `GET /api/workspace/status`

Returns configuration, not proof that a service is reachable. The container health check and the deploy script use this route (`Dockerfile:21`, `scripts/deploy-speclens.sh:130`).

| Field | Type | Meaning |
| --- | --- | --- |
| `ok` | boolean | Always `true` |
| `model_configured` | boolean | `MODEL_API_KEY` is set |
| `memory_configured` | boolean | Hindsight has a usable URL and, for the cloud, a key |
| `model` | string | `muse-spark-1.3` |
| `spent_usd`, `budget_usd` | number | Recorded vision spend and its limit |
| `cache` | object | `prompt_tokens`, `cached_tokens`, `hit_rate`, `saved_usd` (`backend/app/meta/ledger.py:64-78`) |
| `default_factory`, `default_part`, `default_spec` | string | Workspace defaults |

### `GET /api/workspace/samples`

Returns `{"samples": [...]}`. Each sample has `id`, `name`, `detail`, `source_group`, `expected_verdict` and `image_url`. The IDs are `natural-shell`, `white-print`, `fine-crack`, `small-hole`, `second-print` and `second-natural` (`backend/app/workspace/routes.py:34-47`).

### `GET /api/workspace/overview`

Query parameters: `factory`, `part_family`, `spec_text`; factory scope reads also accept `revision_id`. Inspections use `limit` (default 100, max 500) and `before`; the lists are newest first. Use complete lot export for factory evidence beyond the current page.

| Field | Meaning |
| --- | --- |
| `scope_id`, `bank_id` | Scope hash and Hindsight bank name |
| `inspections`, `corrections`, `comparisons` | Records for the scope, without the repeated specification text. In public mode, only yours. Comparisons are the latest 50 |
| `has_more`, `next_before` | Whether older inspections exist, and the cursor to pass as `before` |
| `taxonomy` | The specification's reject classes, clauses, limits and part width |
| `stats` | Counts: `inspections`, `corrections`, `comparisons`, `synced`, `pending` |

### `POST /api/workspace/inspect`

Send `multipart/form-data`.

| Field | Default | Rules |
| --- | --- | --- |
| `file` | None | JPG, PNG or WebP still photo, up to 8 MiB and 25 megapixels |
| `sample_id` | Empty | A sample ID. If you send both, the sample wins and `file` is ignored (`backend/app/workspace/routes.py:60`) |
| `factory` | `Bangalore Foods` | Up to 100 characters |
| `part_family` | `Whole hazelnut` | Up to 100 characters |
| `spec_text` | Default specification | Up to 12,000 characters |
| `memory_enabled` | `true` | With `true`, a failed recall returns 503 and no model call happens |

Returns 200 with an inspection record.

| Field | Meaning |
| --- | --- |
| `id` | `insp-` plus 16 hex characters |
| `verdict` | `good`, `defect` or `uncertain` |
| `defect`, `type` | Defect flag, and `good`, `hole`, `crack`, `cut` or `print` |
| `confidence`, `rationale` | The model's own estimate and its reason |
| `box_px` | `[x0, y0, x1, y1]` in pixels of the stored image, or `null` |
| `part_visible` | `false` if the photo does not clearly show the part |
| `image_url`, `image_width`, `image_height` | The stored JPEG and its size |
| `memory_enabled`, `memory_status`, `memories`, `bank_id` | `memory_status` is `disabled`, `empty` or `recalled`. Each memory has `id`, `text`, `source_id`, `type`, `reviewer`, `rule_text` and `source_inspection_id` |
| `ms`, `cost_usd`, `prompt_tokens`, `cached_tokens`, `model`, `created_at` | Time, cost and usage |
| `scope_id`, `factory`, `part_family`, `spec_text`, `owner_id` | The scope. `owner_id` is empty in local mode, and a hash of the cookie in public mode |
| `filename`, `image_sha256`, `source_kind`, `source_group`, `sample_id` | Where the photo came from. `source_kind` is `upload` or `synthetic_sample` |

Sources: `backend/app/workspace/service.py:44-52`, `backend/app/inspect/inspector.py:96-99`.

### `POST /api/workspace/corrections`

Send JSON.

| Field | Default | Rules |
| --- | --- | --- |
| `inspection_id` | Required | 1 to 80 characters. Must be an inspection you own |
| `verdict` | Required | `good` or `defect` |
| `defect_type` | Required | `good`, `hole`, `crack`, `cut` or `print`. `good` goes with verdict `good` only, and the others with `defect` only |
| `rule_text` | Required | 10 to 2,000 characters after trimming |
| `reviewer` | `Quality engineer` | 1 to 80 characters after trimming |

Returns 201 with the correction record, even when Hindsight fails. Read `sync_status` to find out: `synced`, or `pending` with the reason in `sync_error` (`backend/app/workspace/service.py:66-70`). The record also holds the original verdict, type and reasoning (`backend/app/workspace/store.py:101-110`).

A second correction for one inspection returns 409.

### `POST /api/workspace/corrections/{id}/sync`

Takes no fields. Returns 200 with the correction record. A failed retry also returns 200, so check `sync_status`. A correction that is already synced comes back unchanged (`backend/app/workspace/service.py:59-70`).

### `POST /api/workspace/recall`

Send JSON with `factory`, `part_family` and `spec_text`. All are optional.

Returns `{"bank_id": "...", "memories": [...]}`. Only facts tied to a synced correction in this scope appear. Each has `id`, `text`, `source_id` and `type` (`backend/app/workspace/routes.py:202-203`, `backend/app/workspace/memory.py:87-88`). The page does not call this route. `scripts/system_check.py` does.

### `POST /api/workspace/reflect`

Send the same JSON as `/recall`. Returns `summary`, `facts` and `bank_id` (`backend/app/workspace/memory.py:98`). Unlike recall, reflect has no empty result for a missing bank, so any Hindsight error returns 503 (`backend/app/workspace/memory.py:91-97`). The page keeps the button off until a correction is synced (`frontend/src/workspace/sections.tsx:57`).

### `POST /api/workspace/compare`

Send `multipart/form-data` with the same photo and scope fields as `/inspect`, without `memory_enabled`. Add `expected_verdict`: `good`, `defect` or empty.

Returns 200 with a comparison record (`backend/app/workspace/service.py:85-90`):

| Field | Meaning |
| --- | --- |
| `id` | `compare-` plus 16 hex characters |
| `baseline`, `with_memory` | Two full inspection records |
| `expected_verdict` | Your label, or `null` |
| `changed` | The two verdicts differ |
| `held_out` | The image was not used for a correction, and shares no source photo with one |
| `reuse_reason` | `reused_image`, `shared_source_photo` or `not_used_for_correction` |
| `note` | A fixed reminder that this is not a benchmark |

Each arm saves its own inspection. If the second arm fails, the first stays saved and no comparison is recorded (`backend/app/workspace/service.py:78-80`). The first arm's vision cost still counts.

## Files and the page

| Method | Path | What it does | Public mode | Defined in |
| --- | --- | --- | --- | --- |
| `GET` | `/` | Serves the page, if `frontend/dist` exists | Available | `backend/app/main.py:235-246` |
| `GET` | `/assets/*`, `/favicon.svg` | Serves built files | Available | `backend/app/main.py:237-241` |
| `GET` | `/files/fixtures/*` | Serves sample images | Available | `backend/app/main.py:214` |
| `GET` | `/files/workspace/{id}.jpg` | Serves an inspection photo to its owner, with `Cache-Control: no-store` | Available | `backend/app/main.py:223-233` |
| `GET` | `/files/parts/*`, `/files/runs/*`, `/files/inspections/*`, `/files/mvtec/*` | Serves media for the earlier run routes. The `mvtec` mount exists only if `data/mvtec` does | 404 | `backend/app/main.py:215-220` |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | FastAPI's generated API pages and schema | Local mode only. Public mode returns 404 | `backend/app/main.py:31`, `backend/app/public.py:126-129` |

## Other `/api` routes

`backend/app/main.py` also defines an earlier set of routes for a synthetic defect pipeline. The page does not use them. In public mode the middleware answers all of them with 404, except `/api/health` (`backend/app/public.py:95-98`).

| Method | Path | What it does | Public mode | Defined in |
| --- | --- | --- | --- | --- |
| `GET` | `/api/health` | Reports `ok`, `demo_mode`, `models`, `spent_usd`, `budget_usd` | Available | `backend/app/main.py:48-50` |
| `GET` | `/api/ledger` | Returns recent model calls and spend | 404 | `backend/app/main.py:53-55` |
| `GET` | `/api/default-spec` | Returns the default specification | 404 | `backend/app/main.py:58-60` |
| `POST` | `/api/taxonomy` | Turns a specification into defect classes | 404 | `backend/app/main.py:63-70` |
| `GET` | `/api/parts` | Lists good-part photos | 404 | `backend/app/main.py:73-75` |
| `POST` | `/api/parts` | Uploads good-part photos | 404 | `backend/app/main.py:78-86` |
| `POST` | `/api/runs` | Starts a synthetic defect run | 404 | `backend/app/main.py:89-100` |
| `GET` | `/api/runs` | Lists runs | 404 | `backend/app/main.py:103-105` |
| `GET` | `/api/runs/{rid}` | Returns one run | 404 | `backend/app/main.py:108-113` |
| `POST` | `/api/runs/{rid}/stress` | Reruns the stress test | 404 | `backend/app/main.py:116-126` |
| `GET` | `/api/runs/{rid}/events` | Streams run events with Server-Sent Events | 404 | `backend/app/main.py:129-152` |
| `GET` | `/api/runs/{rid}/export` | Downloads a COCO-format zip | 404 | `backend/app/main.py:155-162` |
| `POST` | `/api/inspect` | Earlier single inspection, with a mask when a box exists | 404 | `backend/app/main.py:165-202` |
| `GET` | `/api/eval` | Returns `docs/results/eval.json`, or an empty report if that file is missing | 404 | `backend/app/main.py:205-211` |

## Try it

These two calls are free. They make no model or memory requests.

```bash
curl -s https://speclens.pallabdas.me/api/workspace/status
curl -s https://speclens.pallabdas.me/api/workspace/samples
```

This call is billable. It makes one vision call on a server with `MODEL_API_KEY` set.

```bash
curl -s http://localhost:8770/api/workspace/inspect \
  -F sample_id=white-print -F memory_enabled=false
```

## Errors

Errors return JSON with a `detail` field. It is usually a string. Pydantic validation errors return a list of objects, each with a `msg`, which the page joins into one message (`frontend/src/workspace/api.ts:10-13`).

| Status | When | Source |
| --- | --- | --- |
| 400 | The file is not a readable JPG, PNG or WebP still photo, or it is over 25 megapixels | `backend/app/workspace/routes.py:75-83` |
| 402 | Recorded vision spend passed `BUDGET_USD` | `backend/app/workspace/routes.py:97-98`, `backend/app/meta/ledger.py:54-56` |
| 403 | Public mode: a write came from another origin | `backend/app/public.py:99-105` |
| 404 | The sample, inspection, correction or photo does not exist, or belongs to another visitor. Public mode also uses it for blocked routes | `backend/app/workspace/routes.py:63`, `backend/app/workspace/routes.py:168-169`, `backend/app/workspace/routes.py:181-182`, `backend/app/main.py:226-232`, `backend/app/public.py:95-98` |
| 409 | The inspection already has a correction | `backend/app/workspace/routes.py:174-175`, `backend/app/workspace/store.py:115-116` |
| 413 | The photo is over 8 MiB, or in public mode the request body is over 9 MiB | `backend/app/workspace/routes.py:71-72`, `backend/app/public.py:109-114` |
| 422 | A field failed validation, or neither a file nor a sample was sent | `backend/app/workspace/routes.py:51-56`, `backend/app/workspace/routes.py:70`, `backend/app/workspace/routes.py:142-162` |
| 429 | Public mode: the hourly limit is reached. `Retry-After` is 3600 | `backend/app/public.py:106-108` |
| 502 | The vision model call failed | `backend/app/workspace/routes.py:99-100` |
| 503 | `MODEL_API_KEY` is missing, or a required Hindsight call failed | `backend/app/workspace/routes.py:87-89`, `backend/app/workspace/routes.py:95-96` |

In a public request, the middleware checks run in this order: blocked route, other origin, hourly limit, declared body size (`backend/app/public.py:95-114`). A blocked route does not use up your limit, and any other POST does, even if it then fails validation.
