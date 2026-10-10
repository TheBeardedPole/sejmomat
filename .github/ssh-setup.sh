# Sourced by the deploy and SSH-test workflows. Prepares the key and sets
# RSYNC_SSH, SSH_TARGET and SSH_DIR from the SSH_* environment variables.
set -euo pipefail

: "${SSH_PRIVATE_KEY:?secret SSH_PRIVATE_KEY is not set}"
: "${SSH_HOST:?secret SSH_HOST (or FTP_SERVER) is not set}"
: "${SSH_USERNAME:?secret SSH_USERNAME is not set}"

mkdir -p ~/.ssh && chmod 700 ~/.ssh
printf '%s\n' "$SSH_PRIVATE_KEY" > ~/.ssh/deploy_key
chmod 600 ~/.ssh/deploy_key

if [ -n "${SSH_KNOWN_HOSTS:-}" ]; then
  # pinned host key: refuse to connect to anything else
  printf '%s\n' "$SSH_KNOWN_HOSTS" > ~/.ssh/known_hosts
  host_check=yes
else
  echo "::warning::SSH_KNOWN_HOSTS is not set: the server's host key is accepted without being checked."
  host_check=accept-new
fi

# Default folder on Hostinger: ~/domains/<domain>/public_html/
if [ -z "${SSH_DIR:-}" ]; then
  domain=$(printf '%s' "${SITE_URL:-}" | sed -E 's#^https?://##; s#/.*$##')
  : "${domain:?set the SSH_DIR variable (or SITE_URL) so the target folder is known}"
  SSH_DIR="domains/$domain/public_html/"
fi

RSYNC_SSH="ssh -p ${SSH_PORT:-65002} -i $HOME/.ssh/deploy_key -o StrictHostKeyChecking=$host_check -o BatchMode=yes -o ConnectTimeout=30"
SSH_TARGET="$SSH_USERNAME@$SSH_HOST"
