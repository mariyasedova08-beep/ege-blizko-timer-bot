#!/usr/bin/env bash
# Forced SSH command for the SINGLE pinned Mn/Cr laboratory release.
# Install root:root mode 0755 at /usr/local/libexec/ege-lab-release-entry.
# authorized_keys: command="/usr/local/libexec/ege-lab-release-entry",restrict ssh-ed25519 ...
# The deploy account cannot execute a shell or request other commands with this key.
set -Eeuo pipefail
umask 077
[[ "${SSH_ORIGINAL_COMMAND:-}" == "release-ege-lab-mncr" ]] || {
  echo "DEPLOY_SSH_DENIED: unrecognized command" >&2
  exit 1
}
[[ "$#" == 0 ]] || exit 1
exec sudo -n /usr/local/sbin/ege-lab-mncr-approved-release.sh EGE-LAB-MNCR-20261021-CHECKED
