# PR81 Timeweb read-only inventory — administrator setup checklist

This is a **proposal**, not a performed installation. The lab is NOT deployed.

1. Review `deploy/ege-lab-pr81-readonly-inventory.sh` for read-only commands.
2. On Timeweb, create a **separate unprivileged account** `ege-lab-inventory`, without sudo, write access or membership in deployment groups. Grant read-only access **only** to the four lab files and their parent directories. Ensure those files contain no secrets.
3. Generate a **dedicated keypair** on a trusted admin machine, never commit or paste the private key. Configure its public key with an `authorized_keys` forced command that invokes the root-owned immutable reviewed copy of the inventory script; disable forwarding/PTY with `restrict` and `command=...`. Do NOT modify the existing deployment key.
4. Put the new private key in protected GitHub environment `ege-lab-production` under `TIMEWEB_LAB_INVENTORY_KEY`. Set `TIMEWEB_LAB_INVENTORY_USER=ege-lab-inventory`; keep existing pinned `TIMEWEB_HOST` and `TIMEWEB_KNOWN_HOSTS` unchanged.
5. Review PR84. Merging its workflow into main **does not publish** the lab. Only manually dispatch the inventory workflow on main once GitHub environment access is approved. Expected output: only SHA-256 values / missing-file markers.
6. Compare server hashes with PR81, then independently test applicability against live local changes before designing backup, rollback, and publication.

Safety: Never grant shell or sudo via this key. Do not weaken `ege-lab-restricted-ssh-entry-v2.sh`. A hash mismatch is expected if live Timeweb contains uncommitted patches; do not overwrite it. No deploy until an explicit new approval.
