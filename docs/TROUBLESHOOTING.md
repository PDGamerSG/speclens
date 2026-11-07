# Troubleshooting

Fixes for problems people hit when they set up, run, test or deploy SpecLens. Each entry names the symptom as you see it, the cause, and the fix.

The page shows the server's own error text in a red alert (`frontend/src/workspace/api.ts:8-15`), so the headings below use the same words. [The API reference](api/README.md#errors) lists every status code.

## Setup

### `Install Python 3.13+ or uv, then run setup again.`

`scripts/setup.sh` needs Python 3.13 or later, or `uv` to fetch it (`scripts/setup.sh:6-17`). Install one, or point the script at an interpreter:

```bash
SPECLENS_PYTHON=/path/to/python3.13 ./scripts/setup.sh
```

### `SpecLens requires Python 3.13+. Recreate .venv with a supported Python.`

An older `.venv` already exists, and the script checks its version (`scripts/setup.sh:18`). Delete it and run setup again.

```bash
rm -rf .venv
./scripts/setup.sh
```

### `npm ci` fails or Vite refuses to run

The lockfile pins Vite 8, which needs Node.js 20.19 or later on the 20 line, or 22.12 or later (`frontend/package-lock.json`). The project uses Node 22 in CI and in the image (`.github/workflows/ci.yml:21`, `Dockerfile:1`). `frontend/package.json` sets no `engines` field, so npm may not warn you first. Install Node.js 22.12 or later.

### `Run ./scripts/setup.sh first.`

`scripts/dev.sh` found no `.venv` (`scripts/dev.sh:6-9`). Run `./scripts/setup.sh`.

### `Build the interface first: cd frontend && npm run build`

`scripts/dev.sh` found no `frontend/dist/index.html` (`scripts/dev.sh:18-21`). Build the page, or run `./scripts/dev.sh --dev` to use the Vite dev server instead.

### `http://localhost:8770/` returns `{"detail":"Not Found"}`

The server adds the `/` route only when `frontend/dist` exists at startup (`backend/app/main.py:237-248`). This happens when you start Uvicorn by hand before building. Build the page, then restart the server.

### Port 8770 is already in use

Another process holds the port. Pick a different one (`scripts/dev.sh:5`):

```bash
SPECLENS_PORT=8780 ./scripts/dev.sh
```

`--dev` passes the same port to the Vite proxy (`scripts/dev.sh:13`). The Docker setup always uses 8770 (`compose.yaml:5`), so stop the other process in that case.

### The server stops at startup with a `ValueError` or `PermissionError`

Two settings are read at startup. `BUDGET_USD` must parse as a number (`backend/app/config.py:16`). `SPECLENS_VAR` must point to a directory the server can write to, because it creates its folders on import (`backend/app/config.py:22-23`). Fix the value in `.env` and restart.

### A change to `.env` has no effect

The server reads settings once at startup. Restart it. A value already exported in your shell also wins over `.env` (see [how settings are loaded](CONFIGURATION.md#how-settings-are-loaded)).

## Inspections

### `Live inspection needs MODEL_API_KEY on the server.`

`MODEL_API_KEY` is empty, so the server returns 503 (`backend/app/workspace/routes.py:87-89`). The page also shows a setup banner (`frontend/src/workspace/Workspace.tsx:191`). Add the key to `.env` and restart.

`DEMO_MODE=1` does not avoid this. Workspace routes never replay recorded results (see [server settings](CONFIGURATION.md#server-settings)).

### `Connect Hindsight in the server settings to use memory, or switch memory off for a baseline inspection.`

Hindsight is not configured, and the **Use quality memory** switch starts on (`backend/app/workspace/memory.py:24-25`, `frontend/src/workspace/Workspace.tsx:40`). Either set `HINDSIGHT_BASE_URL` and `HINDSIGHT_API_KEY` and restart, or turn the switch off to inspect without memory. Hindsight Cloud needs a key. A self-hosted server may not (`backend/app/workspace/memory.py:19-21`).

The same check applies to **Run comparison**, which always runs a memory arm (`backend/app/workspace/service.py:78-80`). If the baseline arm ran first, that one inspection stays in your history even though the comparison failed.

### `The vision model could not complete this inspection.`

The Model API returned an error, or the reply was not valid JSON, so the server returned 502 (`backend/app/workspace/routes.py:99-100`, `backend/app/meta/client.py:84-87`). Check `MODEL_API_KEY` and `MODEL_API_BASE_URL`. The last lines of the ledger show the status and error for each failed call (`backend/app/meta/client.py:71-73`):

```bash
tail -n 5 var/ledger.jsonl
```

### `Meta API budget guard: spent $X of $Y`

Recorded spend passed `BUDGET_USD`, so the server returns 402 (`backend/app/meta/ledger.py:54-56`, `backend/app/workspace/routes.py:97-98`). Spend comes from `var/ledger.jsonl`, so a restart does not reset it (`backend/app/meta/ledger.py:38-43`). Raise `BUDGET_USD` and restart. **Workspace settings** shows the current spend (`frontend/src/workspace/SettingsDialog.tsx:46`).

### `Choose an image smaller than 8 MB.`

The photo is over the limit (`backend/app/workspace/routes.py:71-72`, `frontend/src/workspace/photo.ts:4`). Resize it. In public mode, the whole request body is also capped at 9 MiB (`backend/app/public.py:23`).

### `Upload a JPG, PNG or WebP still photo.` or a similar photo error

The server accepts JPEG, PNG and WebP, rejects animated images, and limits photos to 25 megapixels (`backend/app/workspace/routes.py:75-80`). A file that will not decode gets `This file is not a readable image.` (`backend/app/workspace/routes.py:82-83`). Convert the photo to a still JPG or PNG.

### The decision is **Review part** with "The part is not clear in this photo"

This is an answer, not a failure. The model reported that the photo does not clearly show the part, and the inspector removed any defect or box (`backend/app/inspect/inspector.py:70-72`, `backend/app/inspect/inspector.py:88-89`). Use a sharp, top-down photo of one part. You can also record the decision yourself with **Correct this decision** (`frontend/src/workspace/Ticket.tsx:66`).

### The inspection takes a long time

The Model API client waits up to 180 seconds per attempt and retries (`backend/app/meta/client.py:24`, `backend/app/meta/client.py:64-76`). Memory adds a Hindsight recall first, which can take up to 120 seconds (`backend/app/workspace/memory.py:28`). A comparison makes two inspections, one after the other.

## Memory

### `Correction saved here. Memory sync is pending; retry it from Quality memory.`

The correction is safe in SQLite, but Hindsight did not confirm it (`backend/app/workspace/service.py:66-70`). Open **Quality memory** and click **Retry sync** on the card. The card shows the reason (`frontend/src/workspace/sections.tsx:44-47`):

| Reason on the card | Cause and fix |
| --- | --- |
| `Hindsight rejected the server credentials.` | 401 or 403. Update `HINDSIGHT_API_KEY` and restart (`backend/app/workspace/memory.py:44-45`) |
| `Hindsight is busy.` | 429. Retry shortly (`backend/app/workspace/memory.py:46-47`) |
| `Hindsight could not complete this request.` | Any other failure. Check `HINDSIGHT_BASE_URL` and the connection (`backend/app/workspace/memory.py:48-49`) |
| `Hindsight did not confirm the correction.` | The reply had no `success: true` (`backend/app/workspace/memory.py:68-69`) |

### A saved correction is not recalled on the next part

Check these in order:

1. **Sync status.** Only corrections marked **In memory** can be recalled (`backend/app/workspace/service.py:28`).
2. **Workspace.** Factory, part family and specification must all match the correction. Editing the specification starts a separate memory (`backend/app/workspace/store.py:32-38`).
3. **Memory switch.** It must be on (`frontend/src/workspace/Ticket.tsx:46-49`).
4. **Hindsight's answer.** Recall is a search, and it returns at most 12 facts (`backend/app/workspace/memory.py:89`). Facts with no matching synced correction are dropped (`backend/app/workspace/service.py:29-32`).

### `This inspection already has a correction.`

Each inspection takes one correction, and corrections cannot be edited (`backend/app/workspace/store.py:115-116`). Inspect the part again and correct that new inspection.

### **Summarize standards** is disabled

The button stays off until at least one correction is in memory (`frontend/src/workspace/sections.tsx:57`).

## Public site

### `This public workspace has reached its hourly request limit.`

Public mode allows 30 POST requests per browser per hour and 120 per IP address (`backend/app/public.py:19-20`, `backend/app/public.py:41`). The window slides, so requests free up one at a time as they turn an hour old. A shared office network shares the IP limit.

### My history is gone

History belongs to the browser cookie and to the workspace fields. Check these:

- **Same workspace?** The page shows only records for the current factory, part family and specification (`backend/app/workspace/routes.py:117-122`). Open **Workspace settings** and restore them.
- **Same browser and hostname?** Another browser, or another hostname, has its own cookie.
- **Cookie still there?** Clearing cookies starts a new workspace. The cookie lasts 30 days from when it was set, and return visits do not renew it (`backend/app/public.py:96-98`).

Records from a lost cookie stay in the database, but no route can reach them. There is no recovery link.

### `Open this workspace directly to make changes.`

The request's `Origin` does not match the host the server sees, so public mode returned 403 (`backend/app/public.py:80-86`). Two setups cause this:

- A page on another site posting to the API.
- Running `./scripts/dev.sh --dev` with `SPECLENS_PUBLIC=1`. The Vite proxy rewrites the host to the backend (`frontend/vite.config.ts:9`), so it no longer matches the browser's `Origin`.

To test public mode locally, build the page and open the server's own port.

### Public mode runs, but every visitor shares one IP limit, or the cookie is not `Secure`

Uvicorn is not trusting the proxy's forwarded headers, so it sees the proxy as the client and `http` as the scheme (`backend/app/public.py:87`, `backend/app/public.py:98`). Start the app with both Compose files, because `compose.public.yaml` sets `FORWARDED_ALLOW_IPS` (`compose.public.yaml:7`).

## Checks

### `./scripts/check.sh` fails with `.venv/bin/python: No such file or directory`

The check script and the browser test server both use `.venv` (`scripts/check.sh:8`, `frontend/playwright.config.ts:7`). Run `./scripts/setup.sh` first.

### Playwright says the browser executable does not exist

Install Chromium once:

```bash
(cd frontend && npx playwright install chromium)
```

### Browser tests behave strangely, or the test server will not start

Outside CI, Playwright reuses any server already on port 8771 (`frontend/playwright.config.ts:7`). A stale server gives stale results. Stop it, or use another port:

```bash
E2E_PORT=8781 npm --prefix frontend run test:e2e
```

### The checks do not run on Windows

`scripts/check.sh` is a Bash script, and the Playwright server command uses the `.venv/bin` path (`frontend/playwright.config.ts:7`). `scripts/setup.ps1` and `scripts/dev.ps1` cover install and run only. Use WSL or a Linux machine for the full checks.

## Docker and deployment

### `docker compose up` stops because `.env` is missing

`compose.yaml` requires the file (`compose.yaml:6`). Run `cp .env.example .env`, add the keys, and try again.

### The container cannot write to its data folder

The image runs as user `speclens`, UID 10001, and prepares `/app/var` for it (`Dockerfile:17-18`). The named volume in `compose.yaml` works as is. If you mount a host folder there, give that user write access.

### My data disappeared after a deploy

Compose names the volume after the project. The public deployment uses the fixed project name `chief-skill` (`scripts/deploy-speclens.sh:126-127`). Running Compose on the server without `--project-name chief-skill` creates a new, empty volume. The data is still in the original volume. Never use `docker compose down --volumes` for a normal update. See [persistent data and recovery](deployment.md#persistent-data-and-recovery).

### `SSH identity is not readable`

The key file is missing, or you lack read access (`scripts/deploy-speclens.sh:66`). Lightsail access can be temporary. [Server access](deployment.md#server-access) shows how to refresh it, and `--key` chooses another file.

### `No runtime environment file exists. Redeploy with --env-file PATH.`

The server has no saved settings file yet (`scripts/deploy-speclens.sh:120-123`). Pass it on the first deploy:

```bash
./scripts/deploy-speclens.sh --env-file .env
```

### `The app did not become healthy.`

`/api/workspace/status` did not answer within 45 attempts (`scripts/deploy-speclens.sh:128-139`). The `current` link stays on the previous release, but the new container has already replaced the old one. On the server, check the service with the commands under [persistent data and recovery](deployment.md#persistent-data-and-recovery), then read its logs.

### `AWS CLI is required for --publish.`

`--publish` opens the instance's ports through the AWS CLI (`scripts/deploy-speclens.sh:74-76`, `scripts/deploy-speclens.sh:166-170`). Install and sign in to the CLI. A private deploy needs only SSH.

### The site does not load over HTTPS right after publishing

Caddy needs a moment to get a certificate after ports 80 and 443 open, and the script says so (`scripts/deploy-speclens.sh:171-172`). Wait, then check:

```bash
curl --fail https://speclens.pallabdas.me/api/workspace/status
```

### `/api/workspace/status` says the services are fine, but inspections fail

The status route reports configuration only. It does not call Meta or Hindsight (`backend/app/workspace/routes.py:103-108`). To test the real connections, run `scripts/system_check.py`. It makes billable calls (see the [test plan](testing/test-plan.md#live-checks)).
