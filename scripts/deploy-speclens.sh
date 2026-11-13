#!/usr/bin/env bash
# Deploy the combined React/FastAPI service to the dedicated Lightsail server.
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: scripts/deploy-speclens.sh [options]

  --host HOST          SSH host (default: 13.236.192.155)
  --user USER          SSH user (default: ubuntu)
  --key PATH           SSH identity (default: ~/.ssh/chief-skill/chief-skill.pem)
  --env-file PATH      Copy a runtime environment file privately; required initially
  --hostname HOST      Backend HTTPS name (default: speclens.13-236-192-155.sslip.io)
  --alias HOST         Override aliases; repeat for each (empty disables aliases)
  --publish            Start Caddy and open this Lightsail instance's ports 80/443
  --instance NAME      Lightsail instance (default: chief-skill)
  --region REGION      AWS region (default: ap-southeast-2)
  -h, --help           Show this help

The default deployment binds the app to server localhost:8770 only.
Use --publish after the public session isolation and request limits are verified.
API credentials are transferred only through SSH and kept outside release files.
HELP
}

ssh_host=13.236.192.155
ssh_user=ubuntu
ssh_key="$HOME/.ssh/chief-skill/chief-skill.pem"
env_file=
hostname=speclens.13-236-192-155.sslip.io
alias_hostnames=(chief-skill.13-236-192-155.sslip.io)
aliases_overridden=0
publish=0
instance_name=chief-skill
aws_region=ap-southeast-2

while (($#)); do
  case "$1" in
    --host|--user|--key|--env-file|--hostname|--alias|--instance|--region)
      if (($# < 2)); then printf 'Missing value for %s\n' "$1" >&2; exit 2; fi
      case "$1" in
        --host) ssh_host=$2 ;;
        --user) ssh_user=$2 ;;
        --key) ssh_key=$2 ;;
        --env-file) env_file=$2 ;;
        --hostname) hostname=$2 ;;
        --alias)
          if ((!aliases_overridden)); then alias_hostnames=(); aliases_overridden=1; fi
          if [[ -n $2 ]]; then alias_hostnames+=("$2"); fi ;;
        --instance) instance_name=$2 ;;
        --region) aws_region=$2 ;;
      esac
      shift 2 ;;
    --publish) publish=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ $ssh_host =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || { printf 'Invalid SSH host.\n' >&2; exit 2; }
[[ $ssh_user =~ ^[a-z_][a-z0-9_-]*$ ]] || { printf 'Invalid SSH user.\n' >&2; exit 2; }
[[ $hostname =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || { printf 'Invalid HTTPS hostname.\n' >&2; exit 2; }
for alias_hostname in "${alias_hostnames[@]-}"; do
  [[ -z $alias_hostname || $alias_hostname =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || { printf 'Invalid alias hostname.\n' >&2; exit 2; }
done
[[ -r $ssh_key ]] || { printf 'SSH identity is not readable: %s\n' "$ssh_key" >&2; exit 2; }
if [[ -n $env_file && ! -r $env_file ]]; then
  printf 'Runtime environment file is not readable: %s\n' "$env_file" >&2
  exit 2
fi
for required_command in ssh scp tar; do
  command -v "$required_command" >/dev/null || { printf 'Missing command: %s\n' "$required_command" >&2; exit 2; }
done
if ((publish)); then
  command -v aws >/dev/null || { printf 'AWS CLI is required for --publish.\n' >&2; exit 2; }
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
release_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
deploy_temp=$(mktemp -d "${TMPDIR:-/tmp}/chief-skill-deploy.XXXXXX")
trap 'rm -rf -- "$deploy_temp"' EXIT
ssh_options=(-i "$ssh_key" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
ssh_target="$ssh_user@$ssh_host"
# Shown by /api/health so evaluation reports can name the code they ran against.
commit=$(git -C "$project_root" rev-parse HEAD 2>/dev/null || true)
if [[ -n $commit && -n $(git -C "$project_root" status --porcelain 2>/dev/null) ]]; then commit="$commit-dirty"; fi

tar -C "$project_root" \
  --exclude=.git --exclude=.env --exclude='.env.*' --exclude=.venv \
  --exclude=node_modules --exclude=dist --exclude=dist-static --exclude=.21st --exclude=.vercel \
  --exclude=__pycache__ --exclude=.pytest_cache --exclude=var --exclude=data \
  --exclude=runs --exclude=reports --exclude=research_notes --exclude=spikes \
  --exclude=test-results --exclude=playwright-report --exclude='*.sqlite3*' \
  -czf "$deploy_temp/source.tgz" .
scp "${ssh_options[@]}" "$deploy_temp/source.tgz" "$ssh_target:chief-skill-source-$release_id.tgz"
env_uploaded=0
if [[ -n $env_file ]]; then
  # Stream credentials directly into a private server file; do not log their contents.
  ssh "${ssh_options[@]}" "$ssh_target" \
    "umask 077; cat > chief-skill-env-$release_id" < "$env_file"
  env_uploaded=1
fi

ssh "${ssh_options[@]}" "$ssh_target" bash -s -- "$release_id" "$hostname" "$publish" "$env_uploaded" "$commit" "${alias_hostnames[@]-}" <<'REMOTE'
set -euo pipefail
release_id=$1
hostname=$2
publish=$3
env_uploaded=$4
commit=$5
shift 5
alias_hostnames=("$@")
release_dir="/opt/chief-skill/releases/$release_id"
shared_dir=/opt/chief-skill/shared
source_archive="$HOME/chief-skill-source-$release_id.tgz"
incoming_env="$HOME/chief-skill-env-$release_id"
trap 'rm -f -- "$source_archive" "$incoming_env"' EXIT
sudo install -d -m 0755 "$release_dir"
sudo install -d -m 0700 "$shared_dir"
if ((env_uploaded)); then
  sudo install -m 0600 -o root -g root "$incoming_env" "$shared_dir/runtime.env"
  rm -f -- "$incoming_env"
fi
if ! sudo test -s "$shared_dir/runtime.env"; then
  printf 'No runtime environment file exists. Redeploy with --env-file PATH.\n' >&2
  exit 1
fi
sudo tar -xzf "$source_archive" -C "$release_dir"
sudo ln -s "$shared_dir/runtime.env" "$release_dir/.env"
sudo SPECLENS_COMMIT="$commit" docker compose --project-name chief-skill -f "$release_dir/compose.yaml" \
  -f "$release_dir/compose.public.yaml" up --build --detach
ready=0
for ((attempt=0; attempt<45; attempt++)); do
  if curl --fail --silent --max-time 3 http://127.0.0.1:8770/api/workspace/status >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if ((!ready)); then
  printf 'The app did not become healthy. Inspect the chief-skill Compose service.\n' >&2
  exit 1
fi
sudo ln -sfn "$release_dir" /opt/chief-skill/current
sudo install -m 0644 "$release_dir/scripts/systemd/speclens-purge.service" /etc/systemd/system/speclens-purge.service
sudo install -m 0644 "$release_dir/scripts/systemd/speclens-purge.timer" /etc/systemd/system/speclens-purge.timer
sudo systemctl daemon-reload
sudo systemctl enable --now speclens-purge.timer
if ((publish)); then
  proxy_hosts="$hostname"
  for alias_hostname in "${alias_hostnames[@]-}"; do
    if [[ -n $alias_hostname && ", $proxy_hosts, " != *", $alias_hostname, "* ]]; then
      proxy_hosts="$proxy_hosts, $alias_hostname"
    fi
  done
  sudo tee "$shared_dir/Caddyfile" >/dev/null <<CADDY
$proxy_hosts {
    reverse_proxy 127.0.0.1:8770
}
CADDY
  sudo docker run --rm --volume "$shared_dir/Caddyfile:/etc/caddy/Caddyfile:ro" \
    caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
  if sudo docker container inspect chief-skill-https >/dev/null 2>&1; then
    sudo docker rm --force chief-skill-https >/dev/null
  fi
  sudo docker run --detach --name chief-skill-https --restart unless-stopped \
    --network host --volume chief-skill-caddy-data:/data --volume chief-skill-caddy-config:/config \
    --volume "$shared_dir/Caddyfile:/etc/caddy/Caddyfile:ro" \
    caddy:2-alpine caddy run --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
fi
printf 'Release %s is healthy on server localhost:8770.\n' "$release_id"
REMOTE

if ((publish)); then
  for public_port in 80 443; do
    aws lightsail open-instance-public-ports --region "$aws_region" --instance-name "$instance_name" \
      --port-info "fromPort=$public_port,toPort=$public_port,protocol=tcp" >/dev/null
  done
  printf 'HTTPS proxy started: https://%s\n' "$hostname"
  printf 'Verify the public page and /api/workspace/status after certificate issuance.\n'
else
  printf 'App remains private on the server. Use --publish when ready for public access.\n'
fi
