# SpecLens deployment

Public demo: https://speclens.pallabdas.me

Vercel serves the React interface. Its same-origin rewrites send `/api/*` and `/files/*` to the persistent FastAPI service at `https://speclens.13-236-192-155.sslip.io`. SQLite, uploaded images, and the model spend ledger remain on the existing server volume. Model and Hindsight keys stay on that server.

The dedicated AWS Lightsail instance is `chief-skill` in `ap-southeast-2a`: Ubuntu 24.04, the `small_3_2` bundle with 2 GB RAM and a 60 GB disk, priced at US$12/month before tax or excess usage. It has a 2 GB swap file for builds. Static IP `13.236.192.155` is attached as `chief-skill-ip`; keep it attached to avoid the charge for an unattached static IP.

These existing infrastructure names, key paths, Compose project, and volumes remain unchanged by the SpecLens product name.

The canonical public hostname is `speclens.pallabdas.me`. Namecheap has one CNAME with host `speclens`, target `373f7f09bde82a9c.vercel-dns-017.com.`, and Automatic TTL. The former A record was removed. Vercel manages the custom-domain certificate. Preserve all unrelated Namecheap records. The backend keeps its static IP and Caddy HTTPS aliases.

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

The public server limits POST requests to 30 per browser per hour and 120 per IP per hour. Behind Vercel, the server sees a Vercel address instead of the visitor's, so visitors can share that IP limit. These request limits are separate from the persisted vision budget and Hindsight billing. The default local mode remains a shared single-team workspace with `SPECLENS_PUBLIC=0`.

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

This new server starts with a fresh application volume. Local inspection history is not automatically uploaded. To migrate existing records, make a consistent backup of the complete local runtime directory with the local app stopped, then restore it into the server volume before starting the service.

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
