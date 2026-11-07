#!/usr/bin/env bash
# Create the secret Vercel sends to the API, and store it on both sides without printing it.
# Run this from an up-to-date checkout that is linked to the Vercel project.
set -euo pipefail

instance_name=chief-skill
aws_region=ap-southeast-2
ssh_target=ubuntu@13.236.192.155
ssh_key="$HOME/.ssh/chief-skill/chief-skill.pem"
vercel_scope=pallab-das-projects-d3f377fd
shared_env=/opt/chief-skill/shared/runtime.env

for required_command in aws npx openssl python3 ssh; do
  command -v "$required_command" >/dev/null || { printf 'Missing command: %s\n' "$required_command" >&2; exit 2; }
done
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Lightsail SSH access is short lived, so refresh it first.
python3 - "$instance_name" "$aws_region" <<'PY'
import json, os, subprocess, sys
from pathlib import Path

instance, region = sys.argv[1:3]
result = subprocess.run(['aws', 'lightsail', 'get-instance-access-details', '--instance-name', instance,
                         '--protocol', 'ssh', '--region', region, '--output', 'json'],
                        capture_output=True, text=True, check=True)
access = json.loads(result.stdout)['accessDetails']
directory = Path.home() / '.ssh' / 'chief-skill'
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
for name, value in [('chief-skill.pem', access['privateKey']), ('chief-skill.pem-cert.pub', access['certKey'])]:
    target = directory / name
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as handle:
        handle.write(value)
PY

secret=$(openssl rand -hex 32)

printf 'Saving the secret on the API server...\n'
printf '%s\n' "$secret" | ssh -i "$ssh_key" -o IdentitiesOnly=yes -o ConnectTimeout=15 "$ssh_target" bash -c "'
  set -euo pipefail
  IFS= read -r value
  sudo sed -i \"/^SPECLENS_PROXY_SECRET=/d\" $shared_env
  printf \"SPECLENS_PROXY_SECRET=%s\n\" \"\$value\" | sudo tee -a $shared_env >/dev/null
  cd /opt/chief-skill/current
  sudo docker compose --project-name chief-skill -f compose.yaml -f compose.public.yaml up --detach --force-recreate speclens
'"

printf 'Saving the secret in Vercel...\n'
for target in production preview; do
  printf '%s' "$secret" | npx --yes vercel@latest env add SPECLENS_PROXY_SECRET \
    --environment "$target" --sensitive --force --yes --scope "$vercel_scope"
done

printf 'Publishing the frontend so it uses the secret...\n'
npx --yes vercel@latest deploy --prod --yes --scope "$vercel_scope"
printf 'Done. The hourly address limit now counts each visitor.\n'
