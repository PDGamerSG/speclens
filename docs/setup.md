# Running and deploying Chief Skill

## Local installation

Install Node.js 22.12+ and Python 3.13+, or install uv so the setup script can obtain Python 3.13. Run `./scripts/setup.sh`, edit the generated `.env`, then run `./scripts/dev.sh`. Open http://localhost:8770.

The browser does not accept API keys. Set `MODEL_API_KEY`, `HINDSIGHT_BASE_URL`, and `HINDSIGHT_API_KEY` on the backend. Hindsight Cloud commonly uses `https://api.hindsight.vectorize.io`; use the endpoint given to your account. Restart after editing `.env`.

For a self-hosted Hindsight server, point `HINDSIGHT_BASE_URL` at that server and use its authentication configuration. The Hindsight process has its own model configuration and costs.

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

The Compose port is bound to localhost. Put an authenticated HTTPS reverse proxy in front when hosting remotely. The app has no user authentication: factory scopes separate memory and records within one team, and do not implement access control between users.

Use a persistent volume mounted at `/app/var`, or set `SPECLENS_VAR` to a persistent writable directory. This holds `speclens.sqlite3`, inspection media, and the model ledger. An ephemeral serverless filesystem will lose these records. Never commit `.env` or runtime data.

A health endpoint is available at `/api/workspace/status`; it reports configuration, not proof that either external service is reachable. Run `scripts/system_check.py` to test live retain, recall, reflection, and vision requests.

## Backup and restore

For a simple consistent snapshot, stop the app while copying its data volume. For Compose:

```bash
docker compose stop speclens
docker compose cp speclens:/app/var ./speclens-backup
docker compose start speclens
```

For a local run, stop the process and copy `var/` while it is stopped, including SQLite’s WAL/SHM files if present. Keep the entire directory together. Restore it as `SPECLENS_VAR` before starting the app. Hindsight banks live in Hindsight and require their own provider backup policy.

## Connection checks

Run the app, then:

```bash
.venv/bin/python scripts/system_check.py --base http://localhost:8770
```

The script creates a uniquely named workspace so its correction does not enter your normal quality memory. It makes live, billable calls. Reports go under `var/checks/` and remain private. A successful check proves integration behavior, not an accuracy gain.
