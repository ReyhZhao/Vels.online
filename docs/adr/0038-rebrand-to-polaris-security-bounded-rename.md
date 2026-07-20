# Rebrand the platform to "Polaris Security" — a bounded rename

The MSSP platform is renamed to **Polaris Security** (shorthand `polaris` for the repo and
container images). The rename is deliberately **bounded** to the cosmetic and build layers;
runtime state identifiers and the serving domain are left untouched, because a naive
`vels` → `polaris` sweep would rename the live database cluster and its backup path for no
user-facing benefit.

**Renamed** (cheap, visible): the git repo/directory (`vels_online` → `polaris`), Docker image
paths (`.../vels/{backend,frontend,mobile}` → `.../polaris/*`), the Helm `Chart.yaml` name and
`Ingress` metadata name (`vels-online` → `polaris`), and all human-facing branding (README, the
UI hero/footer text, the `SPECTACULAR_SETTINGS` API title, email display names).

**Left unchanged** (risky runtime state / external contracts): the CNPG cluster
`cluster-velsonline`, database/owner `velsonline`, and the app's DB-creds secret
`cluster-velsonline-app`; the `s3://vels-cnpg-backups/` backup path; the Vault/ExternalSecret
paths `kv/velsonline`; the Authentik **OIDC client** (kept working — only its display name is
cosmetic); and the **`vels.online` serving domain** (per ADR-0037, the app stays at the apex
for now). The product is therefore *branded* "Polaris Security" but still *served at*
`vels.online` — brand and domain need not match.

## Consequences

- No database migration, no secret re-provisioning, no auth reconfiguration are triggered by
  the rename.
- A residue of invisible `velsonline` identifiers remains inside Helm/CNPG/Vault. Migrating
  those (and the domain) to `polaris` is a separate, independently-scheduled task, not a
  blocker for the rebrand.
