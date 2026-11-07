# HTTP API reference

Every route the SpecLens server answers, with its input and output. The page uses only the routes under `/api/workspace` (`frontend/src/workspace/api.ts:3`).

## Basics

- **Base URL:** the same origin as the page. Locally that is `http://localhost:8770`. The live site is `https://speclens.pallabdas.me`.
- **Authentication:** there are no accounts. In local mode every route is open to anyone who can reach the server. In public mode the server sets a `speclens_workspace` cookie on the first response, and that cookie selects your records (`backend/app/public.py:89-93`, `backend/app/public.py:115-118`).
- **Scope:** most routes take `factory`, `part_family` and `spec_text`. Together they select one workspace. Leave them out to use `Bangalore Foods`, `Whole hazelnut` and the default specification (`backend/app/workspace/routes.py:25-26`, `backend/app/workspace/routes.py:50-56`).
- **Limits in public mode:** every POST counts toward 30 per browser and 120 per IP address per hour, a comparison counts as two, and a write from an origin outside `SPECLENS_ALLOWED_ORIGINS` gets 403 (`backend/app/public.py:99-108`).

## Workspace routes

| Method | Path | Outside calls | What it does | Defined in |
| --- | --- | --- | --- | --- |
| `GET` | `/api/workspace/status` | None | Reports configuration, spend and defaults | `backend/app/workspace/routes.py:103-108` |
| `GET` | `/api/workspace/samples` | None | Lists the six sample parts | `backend/app/workspace/routes.py:111-114` |
| `GET` | `/api/workspace/overview` | None | Returns all records and counts for a scope | `backend/app/workspace/routes.py:117-129` |
| `POST` | `/api/workspace/inspect` | 1 vision call, plus a recall with memory on | Inspects one part | `backend/app/workspace/routes.py:132-139` |
| `POST` | `/api/workspace/corrections` | Hindsight retain | Saves a correction, then sends it to memory | `backend/app/workspace/routes.py:165-175` |
| `POST` | `/api/workspace/corrections/{id}/sync` | Hindsight retain, unless already synced | Retries a pending correction | `backend/app/workspace/routes.py:178-186` |
| `POST` | `/api/workspace/recall` | Hindsight recall | Returns recalled standards for a scope | `backend/app/workspace/routes.py:198-203` |
| `POST` | `/api/workspace/reflect` | Hindsight reflect | Returns a written summary of the standards | `backend/app/workspace/routes.py:206-208` |
| `POST` | `/api/workspace/compare` | 2 vision calls and 1 recall | Inspects one part with and without memory | `backend/app/workspace/routes.py:211-218` |

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

Query parameters: `factory`, `part_family`, `spec_text`. There is no paging, and the lists are newest first.

| Field | Meaning |
| --- | --- |
| `scope_id`, `bank_id` | Scope hash and Hindsight bank name |
| `inspections`, `corrections`, `comparisons` | Full records for the scope. In public mode, only yours |
| `stats` | Counts: `inspections`, `corrections`, `synced`, `pending` |

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
