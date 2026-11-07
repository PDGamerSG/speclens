# Test plan

What SpecLens tests, how to run the tests, and what is not tested yet.

Automated tests make no live provider calls. The live checks in the last part of this plan do, and they cost money. Passing the automated tests says nothing about model accuracy, because the model and Hindsight are simulated.

## Test inventory

| Level | Tool | Location | What it covers |
| --- | --- | --- | --- |
| Backend | pytest | `tests/` | 74 test cases in 8 files: records, memory, prompts, HTTP validation, public boundaries, the earlier pipeline |
| Browser | Playwright, Chromium | `frontend/tests/` | 24 tests in 4 files, driving the real page, routes and SQLite |
| Types and build | TypeScript, Vite | `frontend/` | `tsc -b && vite build` (`frontend/package.json:8`) |
| Lint | oxlint | `frontend/` | `oxlint` (`frontend/package.json:9`) |
| Live integration | Python and Playwright scripts | `scripts/`, `frontend/scripts/` | Real calls to Meta and Hindsight. Run by hand |

The counts come from `pytest --collect-only` and from counting `test(` calls at this commit.

### How tests stay offline

- `tests/conftest.py:8-10` turns on `DEMO_MODE`, blanks `MODEL_API_KEY`, and uses a temporary `SPECLENS_VAR` unless you already exported one.
- Python tests replace the inspector with a function, or Hindsight with an `httpx.MockTransport` (`tests/test_workspace_api.py:17-22`).
- `tests/ui_server.py` starts the real app for the browser tests. It replaces only the outside calls, with a fake vision function and a mock Hindsight transport (`tests/ui_server.py:22-48`). The routes, the SQLite store and the page are real.
- `scripts/check.sh:5` also blanks the provider settings before it runs anything.

## Backend tests

| File | Cases | What it covers |
| --- | --- | --- |
| `tests/test_workspace.py` | 20 | Corrections survive a store restart. Scopes keep memory apart. A correction cannot be changed. Retain, recall and retry behavior. A failed recall stays visible. Only facts from known, synced corrections enter an inspection. Comparison disclosure of reused images. Hindsight configuration rules |
| `tests/test_public_workspace.py` | 11 | Visitors cannot read or correct each other's records. Memory banks follow the visitor. Blocked routes, request limits, cross-origin writes, cookie flags, exported owner IDs, the streaming body cap, and the legacy cookie |
| `tests/test_workspace_api.py` | 10 | Inspect, correct and reload over HTTP. Rejected uploads, unknown samples and short rules. Missing model key. Private files and path escapes. Sample provenance |
| `tests/test_prompt_cache.py` | 9 | Prompt order, stable memory bytes, the cache key, the system message, token reporting, a photo with no part, and cache statistics |
| `tests/test_core.py` | 12 | Earlier pipeline helpers: compositing, severity ladders, validators, duplicates, COCO encoding, part detection. Also cached token pricing and a ledger with a torn line |
| `tests/test_pipeline.py` | 9 | Box scaling and the mask rule in the inspector. A full run on a fake transport, stress reruns, part masks, and the earlier routes in demo mode |
| `tests/test_memory_evaluation.py` | 2 | The evaluation script keeps teaching images out, and counts false alarms |
| `tests/test_sample_labels.py` | 1 | Each white-print mask matches exactly the pixels that changed |

## Browser tests

Playwright runs one worker with a 30-second timeout, and keeps screenshots and traces on failure (`frontend/playwright.config.ts:5-6`).

| File | Tests | What it covers |
| --- | --- | --- |
| `frontend/tests/workspace.spec.ts` | 7 | The full loop: correct, retain, recall on a new part, compare. Phone navigation. Retrying an interrupted sync. Settings locked during an inspection. Reopening a saved comparison. Invalid uploads. Retrying a photo that failed to load |
| `frontend/tests/functions.spec.ts` | 5 | Upload and history export. Outline and zoom limits. Settings focus, Escape and persistence. Empty memory. Saved comparison export |
| `frontend/tests/output.spec.ts` | 9 | How decisions appear, a photo with no part, a very long reason on a phone, failure messages, one-page navigation, reduced motion, the phone first screen, and drag and drop |
| `frontend/tests/regressions.spec.ts` | 3 | The selected sample sets the expected decision. Recovery from a failed startup request. History scrolling on a narrow screen |

Some of these tests fake a server reply with `page.route`, to force states the simulated backend will not produce. For example, `frontend/tests/output.spec.ts:76-92` fakes the 502, 503, 429 and 402 replies, so it tests how the page shows them, not how the server raises them.

## How to run

Install once:

```bash
./scripts/setup.sh
(cd frontend && npx playwright install chromium)
```

Run everything, exactly as CI does:

```bash
./scripts/check.sh
```

`scripts/check.sh` runs the build, lint, pytest and the browser tests in that order, and stops at the first failure (`scripts/check.sh:3`, `scripts/check.sh:6-9`). It needs Bash, so run it on macOS, Linux or WSL.

Run one part:

```bash
.venv/bin/python -m pytest -q --tb=short
.venv/bin/python -m pytest tests/test_public_workspace.py -q
npm --prefix frontend run test:e2e
(cd frontend && npx playwright test tests/workspace.spec.ts)
npm --prefix frontend run build
npm --prefix frontend run lint
```

The browser tests use port 8771. Set `E2E_PORT` to change it (`frontend/playwright.config.ts:3`).

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main` (`.github/workflows/ci.yml:2-5`). One job, `verify`, runs on `ubuntu-latest` with a 15-minute limit and read-only repository access (`.github/workflows/ci.yml:6-11`):

1. Set up Python 3.13 and Node 22.
2. Install the Python packages and `npm ci`.
3. Install Chromium with its system packages.
4. Run `./scripts/check.sh`.
5. On failure, upload `frontend/test-results/` as `browser-failures`.

CI holds no provider keys and does not deploy.

## Live checks

These call the real services and cost money. Run them by hand, and do not expect a particular model decision. They check that the integration works, not that accuracy improved. None of them run in CI.

| Check | Vision calls | What it proves | Writes to |
| --- | --- | --- | --- |
| `scripts/system_check.py` | 4 | Status, baseline inspection, retain, cited recall, reflect, comparison, durable records, in a new workspace (`scripts/system_check.py:48-88`) | `var/checks/` |
| `scripts/evaluate_memory.py` | 9 | A small memory test on four synthetic cases from two held-aside source photos (`scripts/evaluate_memory.py:1-6`) | `var/evaluations/` |
| `frontend/scripts/live-smoke.mjs` | 5 at most (`frontend/scripts/live-smoke.mjs:23`) | The real page in a browser against the live site | `var/checks/live-smoke-<run>/` |
| `frontend/scripts/record-demo.mjs` | 4 | Records the narrated demo video (`frontend/scripts/record-demo.mjs:12`) | `var/submission/` |

```bash
.venv/bin/python scripts/system_check.py --base http://localhost:8770
node frontend/scripts/live-smoke.mjs
```

`frontend/scripts/live-smoke.mjs` runs 11 steps on a fresh run (`frontend/scripts/live-smoke.mjs:269-514`):

1. Public workspace and real provider configuration.
2. A sample inspection with memory off.
3. A human correction retained in Hindsight.
4. A different sample that recalls and cites the correction.
5. The Hindsight standards summary.
6. An uploaded photo inspection.
7. An unlabeled comparison and JSON export.
8. History search, full export, and reopening after a reload.
9. Zoom, the model outline, settings focus and Escape.
10. Phone navigation, settings and horizontal overflow.
11. A second browser that cannot read records, images or corrections.

It targets the public site unless you set `SPECLENS_BASE_URL`. Set `SPECLENS_RESUME_DIR` to repeat browser checks from a saved run with no new vision calls (`frontend/scripts/live-smoke.mjs:10-13`). Its `storage-state.private.json` file is a session credential, so keep it private (`frontend/scripts/live-smoke.mjs:6-8`).

[The verification record](../verification.md) holds results from past live runs, and `docs/evidence/` holds the raw reports.

## Not tested yet

- **Real providers in CI:** Meta and Hindsight are simulated in every automated test. An API change would show up only in a live check.
- **The budget guard on the server:** no Python test mentions the budget or `BudgetExceeded`. The 402 is tested only as a faked reply in the browser (`frontend/tests/output.spec.ts:82`).
- **Security header values:** the tests assert `X-Content-Type-Options` only (`tests/test_public_workspace.py:102`). The CSP, `X-Frame-Options`, `Referrer-Policy` and `Cache-Control` values have no assertion.
- **Rate limit expiry:** tests check that limits block requests, but not that the window clears after an hour.
- **Cookie lifetime:** no test checks the 30-day age or the fact that return visits do not renew it.
- **Routes left open in public mode:** `/api/health` is tested only in local mode (`tests/test_pipeline.py:103`). `/docs`, `/redoc` and `/openapi.json` have no test.
- **Docker and deployment:** CI does not build the image, and nothing tests `compose.yaml`, `compose.public.yaml` or `scripts/deploy-speclens.sh`. `docs/verification.md` records manual runs.
- **Windows:** CI runs on Ubuntu only, so `scripts/setup.ps1` and `scripts/dev.ps1` are not exercised.
- **Other browsers:** the Playwright config sets no `projects`, so only Chromium runs, and CI installs only Chromium (`frontend/playwright.config.ts:4-8`, `.github/workflows/ci.yml:28`).
- **Frontend unit tests:** there are none. `frontend/package.json` has no unit test runner, so the page is tested only through a browser.
- **Coverage:** the checks do not measure it, and no coverage tool is in `backend/requirements.txt` or `frontend/package.json`.
- **Load and concurrency:** no test runs parallel requests against SQLite or the limiter.
- **Accessibility audit:** browser tests use roles and labels, but no automated audit tool is in `frontend/package.json`.
