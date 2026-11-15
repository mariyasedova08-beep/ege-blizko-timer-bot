#!/usr/bin/env bash
# Dedicated, read-only diagnostic. Install only with separate administrator approval.
# Use a separate SSH key whose authorized_keys forced command points to this script.
set -Eeuo pipefail
[[ "$#" -eq 0 ]] || exit 1
[[ -z "${SSH_ORIGINAL_COMMAND:-}" || "${SSH_ORIGINAL_COMMAND}" == "lab-pr81-inventory" ]] || { echo 'INVENTORY_DENIED'; exit 1; }
cd /opt/bots/ege-blizko
for name in ege_lab_webapp.py ege_lab_substances.py ege_lab_inorganic_reactions.py ege_lab_exchange_matrix.py; do
  if [[ -f "$name" && -r "$name" && ! -L "$name" ]]; then
    sha256sum -- "$name"
  else
    printf 'MISSING_OR_UNREADABLE %s\n' "$name"
  fi
done
echo LAB_PR81_INVENTORY_READONLY_OK
