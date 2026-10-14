#!/usr/bin/env bash
# Run as the unprivileged prepodmin-deploy SSH account via forced command.
# It refuses all interactive SSH, scp, shell and tunneling operations.
set -euo pipefail
[[ "${SSH_ORIGINAL_COMMAND:-}" =~ ^sudo\ -n\ /usr/local/sbin/prepodmin-release\ ([a-f0-9]{40})$ ]] || {
  echo "Only reviewed PREPODMIN release SHA is permitted" >&2
  exit 126
}
SHA="${BASH_REMATCH[1]}"
exec sudo -n /usr/local/sbin/prepodmin-release "$SHA"
