# SpecLens deployment

Public demo: https://speclens.pallabdas.me

Vercel serves the React interface. Its same-origin rewrites send `/api/*` and `/files/*` to the persistent FastAPI service at `https://speclens.13-236-192-155.sslip.io`. SQLite, uploaded images, and the model spend ledger remain on the existing server volume. Model and Hindsight keys stay on that server.

The dedicated AWS Lightsail instance is `chief-skill` in `ap-southeast-2a`: Ubuntu 24.04, the `small_3_2` bundle with 2 GB RAM and a 60 GB disk, priced at US$12/month before tax or excess usage. It has a 2 GB swap file for builds. Static IP `13.236.192.155` is attached as `chief-skill-ip`; keep it attached to avoid the charge for an unattached static IP.

These existing infrastructure names, key paths, Compose project, and volumes remain unchanged by the SpecLens product name.

The canonical public hostname is `speclens.pallabdas.me`. Namecheap has one CNAME with host `speclens`, target `373f7f09bde82a9c.vercel-dns-017.com.`, and Automatic TTL. The former A record was removed. Vercel manages the custom-domain certificate. Preserve all unrelated Namecheap records. The backend keeps its static IP and Caddy HTTPS aliases.

## Moving the backend to Render

`render.yaml` describes the target: the API (`speclens-api`), a background worker (`speclens-worker`), a nightly purge (`speclens-purge`), Postgres (`speclens-db`) and Key Value (`speclens-kv`), all in the `singapore` region. Photos go to Cloudflare R2, because Render services have no lasting disk. Vercel keeps serving the page. The Lightsail server stays live until the cut-over below is done and checked.

The copy helper below currently covers legacy demo tables and media, not `pilot_*` identities, memberships, sessions/invitations or factory records. These steps alone are insufficient after factory data exists. Keep the current backend active until a tested full factory migration preserves those tables, their owner relationships, operational counts and media. This limitation concerns a future SQLite-to-Postgres move; migration 0003 on the existing Lightsail database remains additive.

1. Create an R2 bucket named `speclens-media` and an R2 API token with read and write access to that bucket only. Note the account endpoint, `https://<account id>.r2.cloudflarestorage.com`.
2. In Render, choose **New > Blueprint**, select this repository, and apply `render.yaml`. Render asks for each `sync: false` secret: `MODEL_API_KEY`, `HINDSIGHT_API_KEY`, `SPECLENS_PROXY_SECRET`, the two R2 keys and `SENTRY_DSN` (leave it empty if there is no Sentry project). Use the same proxy secret that Vercel holds.
3. In the `speclens-config` environment group, set `R2_ENDPOINT` to the account endpoint.
4. Wait for the first deploy. `preDeployCommand` runs `python -m app.db upgrade`, so the tables exist before the API starts. Open the service URL Render shows for `speclens-api`, followed by `/healthz`.
5. Copy the data from Lightsail. Download the server's `var/` folder, then run:

   ```bash
   DATABASE_URL='<external Postgres URL from Render>' R2_ENDPOINT=... R2_BUCKET=speclens-media \
   R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... .venv/bin/python scripts/migrate_to_render.py --var path/to/var
   ```

   The script reads a temporary copy of the SQLite file, skips records the target already has, and can be run again.
6. In `frontend/vercel.json`, change both rewrite destinations from `https://speclens.13-236-192-155.sslip.io` to that Render service URL, then deploy the frontend.
7. Inspect a sample on the live site, correct it, and confirm the correction reaches Hindsight. Keep Lightsail running for a week as the rollback: reverting step 6 restores it.

Render deploys only commits whose GitHub checks pass (`autoDeployTrigger: checksPass`). The finals setup costs about $32 a month on the Hobby workspace: two `0.5c-512mb` services at $7, Postgres `0.1c-256mb` at $6 plus $0.30 per GB, and Key Value `256mb` at $10. R2 is free up to 10 GB.

## Vercel production

The project is `speclens` under `pallab-das-projects-d3f377fd`. Its root directory is `frontend`, with Node 22, framework Vite, build command `npm run build`, and output `dist`. The public Vercel alias is https://speclens-lake.vercel.app.

From the repository root:

```bash
npx --yes vercel@latest link --yes --project speclens --scope pallab-das-projects-d3f377fd
npx --yes vercel@latest deploy --prod --yes --scope pallab-das-projects-d3f377fd
```

The project is connected to `PDGamerSG/speclens`; pushes deploy the frontend from its configured root directory. GitHub Actions runs its independent checks. `.vercelignore` excludes runtime data, backend files, local environment files, and dependencies from the frontend upload. `frontend/vercel.json` defines API/media rewrites, the SPA fallback, security headers, and no-store API/media responses.

The backend runtime file sets `SPECLENS_ALLOWED_ORIGINS` to exact approved frontend origins, including `https://speclens.pallabdas.me` and `https://speclens-lake.vercel.app`. Existing same-origin requests still work; other origins remain blocked. Add a new origin explicitly before using another deployment URL for writes. Production aliases are public, while preview and immutable deployment URLs retain Vercel authentication protection.

## Visitor workspaces

Public mode assigns each browser an HttpOnly cookie. Its visitor identity scopes inspection records, corrections, comparisons, uploaded media, and Hindsight banks, so visitors with the same factory and part names still have separate data. Use the same browser with its cookies intact to revisit saved history. Clearing cookies or switching browser profiles starts a new visitor workspace.

The current cookie is `speclens_workspace`. On the same hostname, a valid legacy cookie migrates to that name while preserving the exact visitor identity and stored records. The legacy cookie is then expired.

Both `speclens.13-236-192-155.sslip.io` and `chief-skill.13-236-192-155.sslip.io` remain aliases without redirects. Browser cookies belong to their hostname, so revisit the same hostname for visitor history created there. Cookies created on the custom domain continue through the Vercel proxy to the same persistent backend. Moving between different hostnames starts a separate visitor workspace. The canonical public hostname is `speclens.pallabdas.me`.

The public server limits non-factory POST requests to 30 per browser per hour and 120 per IP per hour, and a comparison counts as two. The free rule parser is exempt. Factory routes under `/api/workspace/pilot/` are exempt from that demo quota; registration/login/join have separate durable auth limits. Behind Vercel, the server connects to a Vercel address, so Vercel forwards the visitor's address in `x-real-ip` and proves it with the `x-speclens-proxy-secret` header. Run `./scripts/set-proxy-secret.sh` once to create that secret and store it in Vercel and on the server. Without a matching secret, the limit counts the connecting address, and a forged `x-real-ip` is ignored. These request limits are separate from the persisted vision budget and Hindsight billing. With `SPECLENS_PUBLIC=0`, only the anonymous demo remains shared; factory sign-in, ownership and role checks remain active.

## Server access

SSH username: `ubuntu`. The deployment machine stores the temporary Lightsail private key at `~/.ssh/chief-skill/chief-skill.pem` and its matching SSH certificate at `~/.ssh/chief-skill/chief-skill.pem-cert.pub`. Both files must have mode `0600`; the containing directory must have mode `0700`. These files stay outside the repository. Temporary access may need refreshing through AWS Lightsail's `get-instance-access-details` API; capture its response privately, never paste its output into logs or a terminal.

Refresh access without printing key material:

```bash
python3 - <<'PY'
import json, os, subprocess
from pathlib import Path

result = subprocess.run([
    'aws', 'lightsail', 'get-instance-access-details',
    '--instance-name', 'chief-skill', '--protocol', 'ssh',
    '--region', 'ap-southeast-2', '--output', 'json',
], capture_output=True, text=True, check=True)
access = json.loads(result.stdout)['accessDetails']
directory = Path.home() / '.ssh' / 'chief-skill'
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(directory, 0o700)
for name, value in [
    ('chief-skill.pem', access['privateKey']),
    ('chief-skill.pem-cert.pub', access['certKey']),
]:
    target = directory / name
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        handle.write(value)
    os.chmod(target, 0o600)
PY
```

```bash
ssh -i ~/.ssh/chief-skill/chief-skill.pem -o IdentitiesOnly=yes ubuntu@13.236.192.155
```

Docker, the Buildx plugin, and Docker Compose are installed. The provisioning step leaves the Lightsail firewall open only for SSH on port 22. The application always binds to `127.0.0.1:8770` on the host, including after publication.

## Deploy privately

From the repository root, deploy with public visitor isolation enabled:

```bash
./scripts/deploy-speclens.sh --env-file .env
```

The script archives the current working tree, so reviewed changes do not need a commit before deployment. It excludes environment files, Git history, local dependencies, and runtime data. It transfers the runtime environment file separately over SSH without printing its contents. The server keeps that file at `/opt/chief-skill/shared/runtime.env`, owned by root with mode `0600`, outside release directories and the Docker image.

The environment file must provide the server's model and Hindsight settings and a deliberate API budget. Keep API keys out of browser variables, source files, shell arguments, and build logs. The Docker build does not receive runtime credentials.

Each source release is extracted under `/opt/chief-skill/releases/`. Docker Compose uses both `compose.yaml` and `compose.public.yaml`, builds the frontend and backend, starts the service with the fixed project name `chief-skill`, and checks `/api/workspace/status`. `/opt/chief-skill/current` points to the latest healthy release. This endpoint confirms server configuration; it does not make a live external model or memory request.

The existing Lightsail deployment supports the finals features using SQLite, local media and inline jobs. The API drains due retries and recovers jobs after a restart without a separate worker. Deploying also installs `speclens-purge.timer`, which runs retention cleanup at 20:30 UTC (02:00 IST), using `RETENTION_DAYS` or its 90-day default. Check it with `sudo systemctl status speclens-purge.timer` and read cleanup results with `sudo journalctl -u speclens-purge.service`. Render remains an optional later migration; keep Vercel's rewrites on Lightsail while it is the active backend.

The public overlay sets `SPECLENS_PUBLIC=1` and `FORWARDED_ALLOW_IPS=*`. Caddy forwards HTTPS request metadata to the app, whose host port stays bound to `127.0.0.1:8770`. Keep that loopback binding when trusting forwarded headers.

`SPECLENS_PUBLIC` takes precedence over the legacy `CHIEF_SKILL_PUBLIC` fallback. New deployments should use the current setting.

To inspect the private deployment in a browser:

```bash
ssh -i ~/.ssh/chief-skill/chief-skill.pem -o IdentitiesOnly=yes \
  -L 8870:127.0.0.1:8770 ubuntu@13.236.192.155
```

Open `http://localhost:8870`. Verify session isolation, request limits, the sample inspection flow, and the expected live-provider behavior before publication.

## Backend HTTPS and updates

Once the public app is verified:

```bash
./scripts/deploy-speclens.sh --publish
```

This deploys the current source using the saved runtime environment file, starts the Caddy container, and opens only this instance's TCP ports 80 and 443 through the AWS CLI. Allow certificate issuance to complete, then verify the page and API:

```bash
curl --fail https://speclens.13-236-192-155.sslip.io/api/workspace/status
```

Open `https://speclens.13-236-192-155.sslip.io` to check the backend directly. Use the same server deployment command for later backend updates. Use the Vercel commands above for frontend publication. Include `--env-file .env` only when changing runtime settings. Run `./scripts/deploy-speclens.sh --help` for host, key, hostname, instance, and region overrides.

The server deployment script uses the backend sslip.io hostname and preserves the earlier `chief-skill` alias by default. The frontend custom domain stays on Vercel. To replace that list, repeat `--alias HOST` for each desired alias; use `--alias ""` to disable aliases. `--hostname HOST` changes the primary name. Domain-only changes reuse the running app image and persistent data: validate the updated Caddyfile and reload Caddy instead of rebuilding the service. The active proxy configuration is `/opt/chief-skill/shared/Caddyfile`.

The AWS CLI must be authenticated to publish. SSH access alone is sufficient for a private deployment. If source publication or Git commits are subject to a review or timing rule, that rule is separate from deployment; this script does not stage, commit, or push anything.

## Persistent data and recovery

The fixed Compose project uses the named Docker volume `chief-skill_speclens-data`, mounted at `/app/var`. It contains SQLite, inspection media, uploaded images, and the model spend ledger. The service uses a single container and single volume; updates briefly replace the running container. The data survives container replacement, image rebuilds, instance restarts, and instance stops. Deleting the Lightsail instance or the Docker volume can destroy it. Hindsight retains its own remote banks; it does not replace the local audit records.

The initial installation created a fresh application volume; updates reuse it. Local inspection history is not automatically uploaded. To migrate existing records, make a consistent backup of the complete local runtime directory with the local app stopped, then restore it into the server volume before starting the service.

For a consistent server backup, stop the application while archiving the volume. Run these commands on the server; the backup may include private inspection records and must be kept private:

```bash
sudo install -d -m 0700 /opt/chief-skill/backups
sudo docker compose --project-name chief-skill -f /opt/chief-skill/current/compose.yaml \
  -f /opt/chief-skill/current/compose.public.yaml stop speclens
sudo docker run --rm --volume chief-skill_speclens-data:/data:ro \
  --volume /opt/chief-skill/backups:/backup alpine:3 \
  sh -c 'umask 077; tar -czf /backup/workspace.tgz -C /data .'
sudo docker compose --project-name chief-skill -f /opt/chief-skill/current/compose.yaml \
  -f /opt/chief-skill/current/compose.public.yaml start speclens
```

Copy the backup off the instance over SSH. Keep the SQLite database and its associated WAL/SHM files together. Never use `docker compose down --volumes` for a normal update. The Caddy volumes `chief-skill-caddy-data` and `chief-skill-caddy-config` preserve certificate state across proxy replacement.

For service status, run these commands on the server:

```bash
sudo docker compose --project-name chief-skill -f /opt/chief-skill/current/compose.yaml \
  -f /opt/chief-skill/current/compose.public.yaml ps
sudo docker ps --filter name=chief-skill-https
```

The server incurs ongoing Lightsail charges until it is deleted. Stopping it preserves its disk and does not end those charges. Take and verify an off-server backup before deleting it.

## Factory workspace release, migration and retention

The factory release adds named local accounts, team membership, hashed sessions/invitations/auth counters, and versioned operational JSON records through additive Alembic migration **0003**. Existing anonymous inspections/corrections/comparisons remain in place. Both SQLite and Postgres use the same schema; opening the application engine automatically upgrades it, and `python -m app.db upgrade` can apply the migration explicitly. The new API does not need an identity-provider subscription.

Treat first startup of the new image as a database migration. Prepare a consistent backup and a rollback target **before** running the deployment script or starting that image:

1. Record the reviewed source commit/release path, currently running image and database revision. Pause writes and allow queued/running inspections to finish. Stop the API, any external worker and the scheduled purge while taking the snapshot. On Lightsail use the complete-volume backup procedure above, with a unique timestamped archive rather than overwriting the only previous backup. On Postgres use a consistent database backup plus the corresponding private media snapshot. Keep runtime settings and the prior image/source separately; do not print secrets.
2. Verify that the archive can be listed and restored into a separate private directory/volume. Run SQLite `PRAGMA integrity_check` on the restored copy, or verify a Postgres restore. Record counts for inspections, corrections, comparisons, jobs and existing `pilot_*` tables/kinds if present. Inventory media file counts and hashes. Keep the snapshot, counts and backup checksum off-server with restricted access. A source archive or a running-volume `cp` alone is not a consistent operational-data backup.
3. Deploy the authorized release through the existing command above. Keep the API and worker on the same code/schema, and do not change the volume/project name. Check logs for migration `0003`; verify the actual `alembic_version` and that all preexisting row counts remain intact. Compare factory kinds/member counts and media inventory on an update that already contains factory records. Resume the purge only after its factory-retention behavior is confirmed.
4. Verify `/healthz`, `/api/workspace/status`, public samples and frontend asset version without provider calls. On the same approved frontend origin verify `/api/workspace/pilot/session` returns signed-out fields without a cookie and protected overview returns 401. Use the offline automated suites for mutation/role/retake checks; reserve live provider smoke tests for the intended integration checks. A healthy endpoint or frontend push is not proof that the backend migration and static version are live.
5. Record release identity, backup identity/checksum, before/after counts, migration revision and verification results. Reopen writes once those checks agree. Subsequent frontend publication should match the verified backend contract; keep deployment status separate from Git publication status.

Read the restored SQLite backup without opening the application engine, for example:

```python
import sqlite3

connection = sqlite3.connect('file:/private/restore/speclens.sqlite3?mode=ro', uri=True)
assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print('schema', connection.execute('SELECT version_num FROM alembic_version').fetchone()[0])
tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
for name in ('inspections', 'corrections', 'comparisons', 'jobs', 'pilot_users',
             'pilot_teams', 'pilot_memberships', 'pilot_records'):
    if name in tables:
        print(name, connection.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0])
if 'pilot_records' in tables:
    print('kinds', connection.execute('SELECT kind,COUNT(*) FROM pilot_records GROUP BY kind').fetchall())
connection.close()
```

Replace the example private restore path with the restored copy; it is not a command to run against a live writable file. Counts contain no bearer tokens, but the database/archive contains password hashes, membership and private evidence and must remain private.

For rollback, stop the new API/worker/purge, preserve a separate consistent copy of the failed release's current state, and restore the matching pre-release database **and media** snapshot with the prior application image/source into an isolated recovery target. Verify schema, counts, media and health before redirecting traffic. Changes accepted after the snapshot need explicit reconciliation; restoring a backup does not preserve them automatically. Hindsight is remote state and is not rolled back by a local-volume restore. Prefer a forward fix when compatible. Do not run an Alembic downgrade, drop `pilot_*` tables, clear the volume, or start an older image blindly against the upgraded live database to undo this release.

### Proxy, account and retention checks

`SPECLENS_ALLOWED_ORIGINS` must contain the exact HTTPS frontend origins. Vercel rewrites can give the backend a different Host from the browser Origin, so configure both the custom domain and intended Vercel alias. The factory origin guard requires the same scheme, rejects suffix matches and cross-site writes, and does not trust an arbitrary forwarded host to authorize an origin. Keep forwarded HTTPS metadata correct so `speclens_session` is Secure. A session is valid for seven days; invitation tokens for 48 hours. Registration/login/join limits remain enabled when the demo limiter is disabled.

Factory operational records and their inspection/media evidence are excluded from the anonymous age purge. `RETENTION_DAYS` defaults to **90 days for anonymous demo evidence**. Finished technical jobs and upload objects can be cleaned after seven days while captures/reviews and saved factory evidence remain. Do not describe session expiry, job cleanup or an inactive member as evidence deletion.

An active admin can explicitly delete team operational data through `DELETE /api/workspace/data` with `{"confirm":"DELETE"}` after queued/running jobs finish. Configured Hindsight bank deletion runs before local removal; a remote failure leaves records available for retry. Check returned cleanup failure counts and server logs for media failures. The operation clears operational pilot records, inspections/corrections/comparisons, relevant jobs and media; **users, teams, memberships, sessions, invitations and auth-limit records remain**. It is not account erasure. Backups and provider retention are separate, and the repository records no provider-wide retention guarantee.

There is no built-in password reset/recovery, MFA, SSO or verified email. Keep at least two trusted admins and establish an operator recovery/retention process appropriate to the deployment. Lifecycle activity is not tamper-proof security auditing. See the [factory guide](factory-guide.md), [factory API](api/factory.md) and [threat model](security/threat-model.md).
