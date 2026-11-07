# Configuration

Every setting SpecLens reads, its default, and the file that reads it. Copy `.env.example` to `.env` for local development. `scripts/setup.sh` does this for you and limits the file to your user (`scripts/setup.sh:25-26`). Git ignores `.env` (`.gitignore:2`).

## How settings are loaded

- **Server:** `backend/app/config.py:10` calls `load_dotenv` on the `.env` file at the repository root. Values already in the environment win over `.env`, so a shell export or a Compose `environment:` entry takes priority (python-dotenv's default is `override=False`).
- **When values apply:** the server reads them once at startup, into module-level names (`backend/app/config.py:12-18`, `backend/app/public.py:18`, `backend/app/workspace/routes.py:28-32`). Restart the server after any change.
- **Load order:** `backend/app/public.py` and `backend/app/workspace/routes.py` call `os.environ` directly. They see `.env` values because `backend/app/main.py:19` loads `config.py` first.
- **Docker:** Compose passes `.env` to the container with `env_file` (`compose.yaml:6`). The file is not copied into the image (`.dockerignore:2`).
- **Browser:** no setting reaches the browser. No file in `frontend/src` reads `import.meta.env`, and `VITE_API_TARGET` is used only by the Vite dev proxy on your machine (`frontend/vite.config.ts:7`).
- **Flags:** `SPECLENS_PUBLIC` and `DEMO_MODE` turn on only when the value is exactly `1`. `true` or `yes` leave them off (`backend/app/public.py:18`, `backend/app/config.py:14`).

Sources: `backend/app/config.py`, `backend/app/public.py`, `backend/app/workspace/routes.py`, `compose.yaml`, `frontend/vite.config.ts`.

## Server settings

These are the settings the running app reads. "Code default" applies when the variable is not set anywhere. "`.env.example`" is what a fresh `.env` starts with.

| Variable | Code default | `.env.example` | Read by | What it does |
| --- | --- | --- | --- | --- |
| `MODEL_API_KEY` | Empty | Empty | `backend/app/config.py:13` | Key for the Meta Model API. Without it, `POST /api/workspace/inspect` and `/compare` return 503 (`backend/app/workspace/routes.py:87-89`) and `DEMO_MODE` turns on for the earlier routes |
| `MODEL_API_BASE_URL` | `https://api.meta.ai/v1` | Same | `backend/app/config.py:12` | Base URL for the Model API clients (`backend/app/meta/client.py:24-25`, `backend/app/meta/client.py:114`) |
| `BUDGET_USD` | `100` | `5` | `backend/app/config.py:16` | Stops new Meta calls once the ledger total passes this amount, in US dollars. It does not limit Hindsight costs. Must parse as a number, or the server fails at startup |
| `DEMO_MODE` | `0` | `0` | `backend/app/config.py:14` | Replays recorded data on the earlier `/api/*` routes (`backend/app/main.py:67-68`, `backend/app/main.py:170-174`, `backend/app/runs.py:132-133`). It is also on whenever `MODEL_API_KEY` is empty. The workspace routes ignore it: they never replay a result |
| `SPECLENS_PUBLIC` | Falls back to `CHIEF_SKILL_PUBLIC`, then `0` | `0` | `backend/app/public.py:18` | `1` turns on public mode: visitor cookies, request limits, security headers, and 404 for the earlier routes. Also clears the CORS allow list (`backend/app/main.py:33`) |
| `CHIEF_SKILL_PUBLIC` | `0` | Not listed | `backend/app/public.py:18` | Legacy name. Read only when `SPECLENS_PUBLIC` is not set at all, so the `0` in `.env.example` overrides it |
| `HINDSIGHT_BASE_URL` | Empty | `https://api.hindsight.vectorize.io` | `backend/app/workspace/routes.py:28` | Hindsight endpoint. If it is empty and `HINDSIGHT_API_KEY` is set, the server uses `https://api.hindsight.vectorize.io` (`backend/app/workspace/routes.py:29-30`) |
| `HINDSIGHT_API_KEY` | Empty | Empty | `backend/app/workspace/routes.py:29`, `backend/app/workspace/routes.py:32` | Sent as a bearer token when set (`backend/app/workspace/memory.py:26`). Hindsight Cloud counts as configured only with a key. A self-hosted URL counts as configured without one (`backend/app/workspace/memory.py:19-21`) |
| `SPECLENS_VAR` | `var` at the repository root | Not listed | `backend/app/config.py:18` | Directory for all runtime data. The Docker image and `compose.yaml` set it to `/app/var` (`Dockerfile:9`, `compose.yaml:8`) |

Two points catch people out:

- **The budget differs by source.** If `BUDGET_USD` is missing from `.env`, the limit is 100, not 5.
- **`DEMO_MODE=1` does not simulate inspections.** With a key set, the workspace still makes live calls. Without a key, it shows a setup error.

### What lives in `SPECLENS_VAR`

| Path | What it holds | Written by |
| --- | --- | --- |
| `speclens.sqlite3`, with `-wal` and `-shm` files | Inspections, corrections, comparisons | `backend/app/workspace/store.py:46-65` |
| `workspace/` | One JPEG per inspection | `backend/app/workspace/service.py:43` |
| `ledger.jsonl` | One line per model call, with cost | `backend/app/meta/ledger.py:13`, `backend/app/meta/ledger.py:87-89` |
| `parts/`, `runs/`, `inspections/` | Media for the earlier run routes | `backend/app/config.py:22-23` |

The live check scripts write under `var/` at the repository root, whatever `SPECLENS_VAR` says: `var/checks/` (`scripts/system_check.py:23`, `frontend/scripts/live-smoke.mjs:37`), `var/evaluations/` (`scripts/evaluate_memory.py:57`) and `var/submission/` (`frontend/scripts/record-demo.mjs:29`).

## Deployment settings

| Variable | Default | Set in | Read by | What it does |
| --- | --- | --- | --- | --- |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1,::1` (Uvicorn's own default) | `compose.public.yaml:7`, as `*` | Uvicorn, not the app code | Lets Uvicorn trust forwarded headers from Caddy. The app needs them for the real client address, which sets the IP limit, and for the `https` scheme, which sets the `Secure` cookie flag (`backend/app/public.py:83`, `backend/app/public.py:94`). Keep the host port on loopback when this is `*` |
| `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED` | Not set outside the image | `Dockerfile:9`, as `1` | Python | Standard Python options: no `.pyc` files, and logs appear at once |

The container port is fixed. Compose publishes `127.0.0.1:8770:8770` and the image starts Uvicorn on port 8770 (`compose.yaml:5`, `Dockerfile:22`), so `SPECLENS_PORT` has no effect there.

The deploy script takes command line options, not environment variables. Run `./scripts/deploy-speclens.sh --help` to list them (`scripts/deploy-speclens.sh:5-24`). The only variables it reads are the standard `HOME` and `TMPDIR` (`scripts/deploy-speclens.sh:28`, `scripts/deploy-speclens.sh:80`).

## Development settings

| Variable | Default | Read by | What it does |
| --- | --- | --- | --- |
| `SPECLENS_PORT` | `8770` | `scripts/dev.sh:5`, `scripts/dev.ps1:4` | Port for the local API server |
| `SPECLENS_PYTHON` | Not set | `scripts/setup.sh:7-8` | Python interpreter used to create `.venv`, in place of `uv` or `python3.13` |
| `VITE_API_TARGET` | `http://127.0.0.1:8770` | `frontend/vite.config.ts:7` | Where the Vite dev server sends `/api` and `/files`. `scripts/dev.sh --dev` sets it for you (`scripts/dev.sh:13`) |

## Test settings

| Variable | Default | Read by | What it does |
| --- | --- | --- | --- |
| `E2E_PORT` | `8771` | `frontend/playwright.config.ts:3`, `tests/ui_server.py:49` | Port for the browser test server |
| `CI` | Not set | `frontend/playwright.config.ts:7` | When set, Playwright refuses to reuse a server that is already running |

The test harness also sets server variables so that tests stay offline:

- `scripts/check.sh:5` blanks `MODEL_API_KEY`, `HINDSIGHT_API_KEY` and `HINDSIGHT_BASE_URL`, and sets `DEMO_MODE=1`.
- `tests/conftest.py:8-10` sets `DEMO_MODE=1`, blanks `MODEL_API_KEY`, and uses a temporary `SPECLENS_VAR` unless you already exported one.
- `tests/ui_server.py:7-9` does the same for the browser test server, and always uses a temporary `SPECLENS_VAR`.

## Live check settings

These affect scripts that make real, billable calls. CI does not run them.

| Variable | Default | Read by | What it does |
| --- | --- | --- | --- |
| `SPECLENS_BASE_URL` | The public site | `frontend/scripts/live-smoke.mjs:30`, `frontend/scripts/record-demo.mjs:31` | Site to check or record |
| `CHIEF_SKILL_BASE_URL` | Not set | `frontend/scripts/live-smoke.mjs:30` | Legacy name for `SPECLENS_BASE_URL` |
| `SPECLENS_RESUME_DIR` | Not set | `frontend/scripts/live-smoke.mjs:24` | Earlier run folder to resume from, with no new vision calls |
| `CHIEF_SKILL_RESUME_DIR` | Not set | `frontend/scripts/live-smoke.mjs:24` | Legacy name for `SPECLENS_RESUME_DIR` |
| `SPECLENS_RESUME_PHASE` | `all` | `frontend/scripts/live-smoke.mjs:28-29` | Part of a resumed run to repeat: `all`, `isolation` or `mobile` |
| `CHIEF_SKILL_RESUME_PHASE` | Not set | `frontend/scripts/live-smoke.mjs:28` | Legacy name for `SPECLENS_RESUME_PHASE` |
| `SPECLENS_DEMO_READY` | Not set | `frontend/scripts/record-demo.mjs:266` | Must be `1` before the demo recorder contacts the site |
| `SPECLENS_DEMO_VOICE` | `Karen` | `frontend/scripts/record-demo.mjs:30` | macOS `say` voice for the narration |

`scripts/system_check.py` and `scripts/evaluate_memory.py` take a `--base` option instead of a variable (`scripts/system_check.py:22`, `scripts/evaluate_memory.py:56`).

## Fixed values

These are constants in the code. Change the file to change them.

| Value | Setting | Defined in |
| --- | --- | --- |
| Requests per browser | 30 POST requests per hour | `backend/app/public.py:19-20` |
| Requests per IP address | 120 POST requests per hour, four times the browser limit | `backend/app/public.py:41` |
| Visitor cookie | `speclens_workspace`, 30 days | `backend/app/public.py:21`, `backend/app/public.py:93` |
| Public request body | 9 MiB | `backend/app/public.py:23` |
| Photo upload | 8 MiB, 25 megapixels, JPG, PNG or WebP | `backend/app/workspace/routes.py:27`, `backend/app/workspace/routes.py:75-80` |
| Text limits | Factory and part family 100 characters, specification 12,000 | `backend/app/workspace/routes.py:51` |
| Correction limits | Rule 10 to 2,000 characters, reviewer 1 to 80 | `backend/app/workspace/routes.py:146-147` |
| Default workspace | `Bangalore Foods`, `Whole hazelnut` | `backend/app/workspace/routes.py:25-26` |
| Default specification | Hazelnut specification HZ-QA-07 rev C | `backend/app/forge/spec.py:6-20` |
| Vision model | `muse-spark-1.3` | `backend/app/config.py:26` |
| Model prices | Per-token and per-image rates | `backend/app/config.py:32-37` |
| Model API timeout and retries | 180 seconds, 4 client retries, 3 attempts for 404 and 429 replies | `backend/app/meta/client.py:24`, `backend/app/meta/client.py:27`, `backend/app/meta/client.py:64` |
| Hindsight timeout | 120 seconds, 8 seconds to connect | `backend/app/workspace/memory.py:28` |
| Recalled facts | At most 12 per recall | `backend/app/workspace/memory.py:89` |

## Secrets

| Variable | Where to get it | Where to set it in production |
| --- | --- | --- |
| `MODEL_API_KEY` | A Meta Model API account. The steps to get one are not recorded in the repository | The runtime settings file. Upload it with `./scripts/deploy-speclens.sh --env-file <file>`. It lands at `/opt/chief-skill/shared/runtime.env` with mode `0600` (`scripts/deploy-speclens.sh:94-99`, `scripts/deploy-speclens.sh:116-119`) |
| `HINDSIGHT_API_KEY` | A Hindsight Cloud account, or the authentication of your own Hindsight server | The same runtime settings file |

Both keys stay on the server. The page only sees whether each service is configured (`backend/app/workspace/routes.py:105`). See [keys and secrets](security/threat-model.md#keys-and-secrets) for how they are protected and how to rotate them.
