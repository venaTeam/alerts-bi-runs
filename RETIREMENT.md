# Retirement: development and operations moved to admin

The 2026-10-12 consolidation moves maintained engine source, migrations, scheduling, registry,
mock tooling and shared/operations library production to
[alerts-bi-admin](https://github.com/venaTeam/alerts-bi-admin). Portal remains separate.

Use `alerts-bi-admin serve`, `run`, `db setup`, `db status`, `weekly`, `weekly-status`,
`report`, `registry check`, and `verify-acceptance`. The new admin image serves the UI and
supplies migration/weekly jobs. No runs package, image or checkout is needed by that release.

This repository preserves historical source and release provenance. Do not create new engine
features, migrations, library releases or deployments here. The replacement PRs must be merged
and deployed, consumers transferred, and a scheduled cycle verified before archival.

The unit/build CI workflow is now owned by admin. Its replacement checks the application,
engine and library source together; this repository no longer runs the old producer build.

See admin's pinned `docs/upstream/runs-retirement.md` for exact cutover and rollback steps.
Do not run two schedulers, downgrade/reset SQL, or delete historical releases. Archival needs
explicit authorization after the agreed rollback period. This PR does not stop existing services.
