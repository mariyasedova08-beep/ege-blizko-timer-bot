#!/usr/bin/env bash
# One SSH public key; EXACTLY two approved release commands, each with pinned root-owned target.
set -Eeuo pipefail
umask 077
[[ "$#" == 0 ]] || { echo "DEPLOY_SSH_DENIED: arguments not supported" >&2; exit 1; }
case "${SSH_ORIGINAL_COMMAND:-}" in
  "release-ege-lab-mncr")
    exec sudo -n /usr/local/sbin/ege-lab-mncr-approved-release.sh EGE-LAB-MNCR-20261021-CHECKED
    ;;
  "release-ege-lab-keyboard")
    exec sudo -n /usr/local/sbin/ege-lab-keyboard-guarded-release.sh EGE-LAB-KEYBOARD-20261022-CHECKED
    ;;
  *)
    echo "DEPLOY_SSH_DENIED: unrecognized command" >&2
    exit 1
    ;;
esac
