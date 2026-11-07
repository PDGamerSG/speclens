# Running and deploying SpecLens

## Local installation

Install Node.js 22.12+ and Python 3.13+, or install uv so the setup script can obtain Python 3.13. Run `./scripts/setup.sh`, edit the generated `.env`, then run `./scripts/dev.sh`. Open http://localhost:8770.

The browser does not accept API keys. Set `MODEL_API_KEY`, `HINDSIGHT_BASE_URL`, and `HINDSIGHT_API_KEY` on the backend. Hindsight Cloud commonly uses `https://api.hindsight.vectorize.io`; use the endpoint given to your account. Restart after editing `.env`.

For a self-hosted Hindsight server, point `HINDSIGHT_BASE_URL` at that server and use its authentication configuration. The Hindsight process has its own model configuration and costs.

Local mode defaults to `SPECLENS_PUBLIC=0`. Browsers share a single team’s workspace; factory and specification scopes organize its records and memory.

`SPECLENS_PUBLIC` is the current setting; the legacy `CHIEF_SKILL_PUBLIC` setting is accepted only when `SPECLENS_PUBLIC` is absent.

`BUDGET_USD` limits the vision client using the persisted spend ledger; it does not cap Hindsight billing. The default example is $5. It is a local guard, not a reservation system for simultaneous calls.

## Windows

Install Python 3.13 and Node.js 22.12+, then use PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Edit .env with the server credentials.
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

Open http://localhost:8770. These commands are provided for Windows; the verified local build uses macOS and Python 3.13.

## Containers

The Dockerfile builds the React interface and packages it with FastAPI. From the repository root:

```bash
cp .env.example .env
# Edit .env, then protect it.
chmod 600 .env
docker compose up --build -d
docker compose logs -f speclens
```

The Compose port is bound to localhost. For remote access to the default single-team mode, put an authenticated HTTPS reverse proxy in front. Public visitor isolation is enabled separately by the public deployment overlay below.

Use a persistent volume mounted at `/app/var`, or set `SPECLENS_VAR` to a persistent writable directory. This holds `speclens.sqlite3`, inspection media, and the model ledger. An ephemeral serverless filesystem will lose these records. Never commit `.env` or runtime data.

A health endpoint is available at `/api/workspace/status`; it reports configuration, not proof that either external service is reachable. Run `scripts/system_check.py` to test live retain, recall, reflection, and vision requests.

## Public demo

Vercel serves the interface and proxies same-origin API and media requests to the persistent Lightsail backend. See the [deployment guide](deployment.md) for frontend publication and backend updates.

[Open the public demo](https://speclens.pallabdas.me). Public mode gives each browser an HttpOnly cookie and separates its inspection data and Hindsight banks from other visitors, including when factory names match. Use the same browser with its cookies intact to revisit history. Clearing cookies or switching browser profiles starts a new visitor workspace.

Public mode allows 30 POST requests per browser per hour and 120 per IP per hour, and a comparison counts as two. These limits apply to requests, including corrections and comparisons; they are separate from the server’s vision budget and Hindsight billing.

The [deployment script and server guide](deployment.md) use both Compose files:

```bash
docker compose --project-name chief-skill -f compose.yaml -f compose.public.yaml up --build -d
```

`compose.public.yaml` sets `SPECLENS_PUBLIC=1` and `FORWARDED_ALLOW_IPS=*`. The app’s host port remains bound to localhost; Caddy supplies the HTTPS proxy metadata. Keep that loopback binding when trusting forwarded headers.

## Backup and restore

For a simple consistent snapshot, stop the app while copying its data volume. From the public deployment’s release directory, use its project name and both Compose files:

```bash
docker compose --project-name chief-skill -f compose.yaml -f compose.public.yaml stop speclens
docker compose --project-name chief-skill -f compose.yaml -f compose.public.yaml cp speclens:/app/var ./speclens-backup
docker compose --project-name chief-skill -f compose.yaml -f compose.public.yaml start speclens
```

For a default local Compose installation, omit `--project-name chief-skill` and `-f compose.public.yaml`. The [server backup guide](deployment.md#persistent-data-and-recovery) includes the required server paths and private backup permissions.

For a local run, stop the process and copy `var/` while it is stopped, including SQLite’s WAL/SHM files if present. Keep the entire directory together. Restore it as `SPECLENS_VAR` before starting the app. Hindsight banks live in Hindsight and require their own provider backup policy.

## Connection checks

Run the app, then:

```bash
.venv/bin/python scripts/system_check.py --base http://localhost:8770
```

The script creates a uniquely named workspace so its correction does not enter your normal quality memory. It makes live, billable calls. Reports go under `var/checks/` and remain private. A successful check proves integration behavior, not an accuracy gain.
