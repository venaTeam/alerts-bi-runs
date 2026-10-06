# Alerts BI runs

This repository owns alert analysis, the run trigger API, weekly scheduling, migrations,
and the versioned shared Python packages. It was extracted from `venaTeam/alerts-bi`
commit `c518eeaeb5a3ecb35b5348828300454379e7d535` with its Git history preserved.

The portal and operator app have independent repositories and executables. Canonical
system specifications live in [alerts-bi-design](https://github.com/venaTeam/alerts-bi-design);
this repository keeps a pinned snapshot in `docs/upstream/`.

Measures one team's alerting for one week and hands that team a concrete list of what to
fix.

A run selects **one** team, reads its last 168 hours from Elasticsearch, applies the
deterministic rule set, measures how much of its own inventory the team hides from its
dashboards, asks an on-prem model about everything the rules could not decide, persists the
result to SQL Server, and renders a scorecard from the stored rows.

**The tool reports numbers; people draw conclusions.** Every figure in the scorecard is a
statement about a single week. There is no comparison against a previous run, no trend, no
baseline and no cross-team leaderboard — by design. The read-only
[review portal](https://github.com/venaTeam/alerts-bi-portal) shows each team's published weeks over time, still
without deltas or conclusions.

[`docs/upstream/alerts_bi_design.md`](docs/upstream/alerts_bi_design.md) is the canonical specification.
[`docs/upstream/outputs.md`](docs/upstream/outputs.md) explains what a run emits, and
[`docs/upstream/openshift-deployment.md`](docs/upstream/openshift-deployment.md) covers running it on a cluster.
[`docs/upstream/alerts_bi_flow.md`](docs/upstream/alerts_bi_flow.md) describes one run end to end, and
[`docs/upstream/alerts_bi_implementation_plan.md`](docs/upstream/alerts_bi_implementation_plan.md) describes
what to build. Where this README and the design differ, the design wins.

The implementation language is **Python** (design section 7.7). The superseded JavaScript
implementation was the behavioural reference for the port and is preserved at the
`javascript-mvp` tag. Both were run over the same fixture and compared row for row before
it was removed; design section 7.7 records the result.

---

## Prerequisites

- **Python 3.12 or later**
- [`uv`](https://docs.astral.sh/uv/) for dependency management and the committed lockfile
- Docker, for the Elasticsearch, Kibana and SQL Server stack

Node.js is **not** required for anything: build, tests, mock seeding and runtime are all
Python.

## Quick start

```bash
uv sync --frozen --all-packages
```

```bash
cp .env.example .env
```

Set `MSSQL_SA_PASSWORD` and `SQL_PASSWORD` to the same value in `.env` — SQL Server
requires at least 8 characters with upper, lower, digit and symbol. The Compose file
refuses to start without it rather than falling back to a default password.

```bash
docker compose up -d
```

That starts Elasticsearch 8.15 (`localhost:9200`), Kibana (`localhost:5601`) and SQL
Server 2022 (`localhost:1433`). Wait for all three to report healthy:

```bash
docker compose ps
```

Load the mock dataset and apply the migrations:

```bash
RESET=1 uv run python scripts/generate_mock_alerts.py
```

```bash
uv run alerts-bi-runs db migrate
```

Run a team:

```bash
uv run alerts-bi-runs run --team checkout-api --run-at 2026-08-25T18:00:00Z --fake-llm
```

The scorecard and the three CSV exports are written under `out/<run id prefix>/`.

`--run-at` is needed against the mock because its dataset is generated on a fixed clock
(2026-08-25T18:00:00Z). A production run omits it and uses the current time.

---

## Commands

| Command | What it does |
|---|---|
| `alerts-bi-runs run --team <id>` | Analyse one team, persist the run, render the report |
| `alerts-bi-runs report --run-id <id>` | Re-render a stored run without recomputing anything |
| `alerts-bi-runs report --team <id>` | Re-render that team's most recent completed run |
| `alerts-bi-runs db migrate` | Create the database if absent and apply pending migrations |
| `alerts-bi-runs db status` | Show the current revision and whether each migration still matches its checksum |
| `alerts-bi-runs db reset-test` | Drop and recreate **only** the configured disposable test database |
| `alerts-bi-runs verify-acceptance` | Compare persisted rows and CSVs against the hand-reviewed manifest |
| `alerts-bi-runs serve` | Serve the HTTP trigger surface (see below) |
| `alerts-bi-runs db grant-reader` | Optional legacy utility to create a restricted login for direct access to portal views |
| `alerts-bi-runs weekly` | Run and publish every due Monday week of every enrolled team |
| `alerts-bi-runs weekly-status` | Each enrolled team's latest published week and last schedule outcome |
| `alerts-bi-runs registry check` | Validate the team registry before deploying an edit |
| `alerts-bi-runs db setup` | Apply pending migrations; idempotent, for an init container |

### `run` options

| Flag | Meaning |
|---|---|
| `--team <id>` | Required. A run never defaults to all teams. |
| `--run-at <iso>` | Freeze `run_at`. Defaults to now. |
| `--out <dir>` | Output directory. Default `out/<run id prefix>`. |
| `--fake-llm` | Use the deterministic fake client instead of the on-prem model. |
| `--no-llm` | Skip assessment entirely; eligible identities become `unassessed`. |
| `--registry <path>` | Registry file. Default `config/teams.json`. |
| `--database <name>` | Target database. Default `SQL_DATABASE`. |

`--fake-llm` stamps its own `model_version` onto the run record, so a mock run can never be
mistaken for a live one.

---

## The HTTP trigger surface

A convenience wrapper around the same pipeline the CLI drives, so a run can be started from
a browser instead of a shell in the repository.

```bash
uv run alerts-bi-runs serve
```

Then open <http://127.0.0.1:8000>, pick a team and press Run. The response **is** that run's
scorecard.

| Route | What it does |
|---|---|
| `GET /` | Team list and a run form |
| `GET /healthz` | Liveness, with Elasticsearch and SQL Server reported separately |
| `GET /teams` | The registry's teams as JSON |
| `POST /runs` | Run one team; returns the scorecard HTML |
| `GET /runs/<run_id>` | Re-render that run's scorecard from SQL |
| `GET /runs/latest?team=<id>` | The team's most recent completed run |
| `GET /runs/<run_id>/<file>.csv` | One of the three CSV exports |
| `GET /docs`, `/redoc`, `/openapi.json` | Generated API documentation and schema |

`POST /runs` takes a JSON body: `team` (required), `run_at` (optional ISO 8601) and `llm`
(`live`, `fake` or `off`, mirroring the CLI's default, `--fake-llm` and `--no-llm`). Send
`Accept: application/json` to get a summary with links instead of the scorecard HTML.

```bash
curl -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"team":"checkout-api","run_at":"2026-08-25T18:00:00Z","llm":"fake"}' http://127.0.0.1:8000/runs
```

```bash
curl -o scorecard.html -X POST -H "Content-Type: application/json" -d '{"team":"checkout-api","llm":"fake"}' http://127.0.0.1:8000/runs
```

The request and response shapes are declared as Pydantic models, so the OpenAPI document is
generated from the code rather than maintained beside it: interactive documentation at
`/docs` and `/redoc`, the schema at `/openapi.json`.

The surface adds no analysis. It loads the registry, calls the same `execute_run` and
`persist_run` the CLI calls, writes the same four files under `out/`, and renders reports
from committed SQL rows. A run still names one team and never defaults to all of them.

Built with **FastAPI** on **uvicorn**. The run endpoint is a plain `def`, so FastAPI
dispatches its minutes of blocking Elasticsearch and SQL work to the thread pool instead of
stalling the event loop.

Runs are **serialized**: a second request while one is running gets `409`, because two runs
of the same team and clock derive one deterministic `run_id` and would race to replace each
other's rows.

**There is no authentication.** Every request triggers real Elasticsearch reads and real SQL
writes, and a `live` run can call the on-prem model. The listener binds to `127.0.0.1` by
default; `--host` widens it, and on a shared machine that exposes an unauthenticated write
endpoint to the network.

---

## Automatic weekly reviews

Enrolled teams are reviewed and published every week without anyone running them (design
section 7.11). Every team's week is **Monday 00:00 UTC to Monday 00:00 UTC**.

### Adding a team

1. Add its entry to `config/teams.json` - operators, optional panels - with
   `"weekly_review": { "enabled": true }`, and bump `registry_version`.
2. Validate the file:

```bash
uv run alerts-bi-runs registry check
```

3. Deploy it. The next scheduled run reviews the team's most recent completed week and
   publishes it; from then on every week follows. Earlier weeks are not backfilled.

### What runs

```bash
uv run alerts-bi-runs weekly
```

Run it as often as you like - on OpenShift a CronJob runs it daily. It only does what is due:

- each enrolled team's completed Monday weeks since its latest published one, oldest first;
- a week is **published** automatically when it is healthy (the model assessed every alert);
- an unhealthy week is **held** and retried every day; the healthy weeks after it are run and
  **stored**. If it is still unhealthy three days after it was first held, it is **published
  anyway** with a note to readers saying how many alerts the automated review could not assess;
- a week older than 84 days is **expired** - its data is past retention - and the next week is
  published across the gap;
- a team whose published history is not on the Monday boundary is **blocked** until you align
  it.

It exits non-zero whenever something needs a person. See where every team stands:

```bash
uv run alerts-bi-runs weekly-status
```

Resolve a held week by publishing its run yourself after checking it, or skip it by
publishing the next week with `--allow-gap`. `--dry-run` shows what is due without running
anything, `--team` narrows to enrolled teams, and `--as-of` fixes "now" for the mock:

```bash
uv run alerts-bi-runs weekly --as-of 2026-08-25T18:00:00Z --fake-llm
```

---

## Portal and operator administration

Install and run [alerts-bi-portal](https://github.com/venaTeam/alerts-bi-portal) and
[alerts-bi-admin](https://github.com/venaTeam/alerts-bi-admin) from their own repositories.
Manual publication, withdrawal and finding decisions use `alerts-bi-admin publish`,
`unpublish`, `publications`, `decide` and `decisions`. The `alerts-bi` compatibility alias
only exposes this repository's run commands; moved commands explain the new executable.
All applications use the same SQL database. Only this repository applies migrations.
The weekly runner continues to publish automatically through the operations library.

---

## What a run produces

Exactly four files, and no others:

- `scorecard.html` — self-contained, no scripts and no external resources
- `daily_metrics.csv`
- `rule_counts.csv`
- `alert_worklist.csv`

All four are rendered **only from committed SQL rows**. Nothing is recomputed from
Elasticsearch, and nothing is rendered from in-memory pipeline results. Rendering is a
separate, retryable step, so a display failure after a successful run loses nothing:

```bash
uv run alerts-bi-runs report --run-id <run id>
```

[`docs/upstream/outputs.md`](docs/upstream/outputs.md) documents all four: the scorecard section by section,
every column of every CSV, the API's JSON shapes, and what the outputs deliberately do not
say. The essentials are below.

### Reading the numbers

Two counts always travel together. `alerts` is the raw row count — pipeline and dashboard
load. `distinct_alerts` is the count of distinct `application + key_field` identities — how
many things actually fired. One stuck v1 alert is roughly 288 rows a day and one distinct
alert; a team genuinely flooding the pipeline looks completely different. A team needs the
first number to care and the second to act.

**Every distinct figure is published as a per-day rate**, never as a window total, because
a 7-day total is 7× a 1-day total for arithmetic reasons alone.

**v1 and v2 row counts are never added together.** Grafana writes a row on every
evaluation of a firing rule, and the evaluation cadence differs between the two schemas, so
the same alert yields a very different row count in each. Moving one alert between schemas
therefore changes its row count without anyone improving anything.

`good` is `assessed_good`. It is never `alerts - flagged`, because that would count
everything nobody examined as fine. `unassessed` is reported next to it and should be zero.

---

## Configuration

All configuration is environment-based; see `.env.example` for the full list. `.env` is
never committed.

| Variable | Purpose |
|---|---|
| `ES_URL`, `ES_USERNAME`, `ES_PASSWORD` | Elasticsearch endpoint and basic auth |
| `ES_PAGE_SIZE` | Page size for point-in-time pagination |
| `SQL_HOST`, `SQL_PORT`, `SQL_USER`, `SQL_PASSWORD` | SQL Server connection, via SQLAlchemy over `mssql+pymssql` |
| `SQL_DATABASE` | Persistent store, default `alerts_bi_dev` |
| `SQL_TEST_DATABASE` | Disposable test database, default `alerts_bi_test` |
| `LLM_ENABLED` | Must be true for a run to call the on-prem model |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | On-prem OpenAI-compatible endpoint |
| `LLM_TIMEOUT_MS` | Per-attempt timeout; a timeout consumes one of the three attempts |
| `LLM_MAX_BATCH_SIZE` | May lower the 200-alert ceiling, never raise it |
| `API_HOST`, `API_PORT` | Where `alerts-bi-runs serve` listens; `--host` / `--port` override |
| `API_REGISTRY_PATH`, `API_DATABASE`, `API_OUT_DIR` | Surface overrides for the registry, target database and report directory |

For an on-prem cluster with a private CA, set `ES_CA_CERT` to the bundle path; the
Elasticsearch Python client takes it directly.

Alert documents, credentials and complete LLM payloads never appear in logs. Logs carry
identifiers, hashes, counts, timings and redacted errors. Auditable payloads are stored in
SQL only.

---

## The team registry

Ownership is **supplied, never inferred**. `config/teams.json` maps each team to its exact
v1 `operator` values and its v2 `operator`, and is validated in full against
the schema packaged in `alerts_bi_operations/resources/teams.schema.json` before any Elasticsearch query runs.

```json
{
  "team_id": "checkout-api",
  "display_name": "Checkout API",
  "v1_operators": ["checkout", "Checkout-API"],
  "v2_operator": "checkout-api",
  "panels": [{ "panel_id": "checkout-api-v1-main", "schema": "v1", "sql": "SELECT ..." }]
}
```

Operator matching is exact and **case-sensitive**, which is why a team using both
`checkout` and `Checkout-API` must list both. No operator may belong to two teams, though
one team may carry the same string as both its v1 and v2 operator. Every run records the
registry version, the SHA-256 of the complete registry file, and an immutable snapshot of
the selected entry, so the ownership used is reproducible even after the registry is
edited.

Panels are optional and are used for exactly one thing: finding the predicates by which a
team filters its own alerts out of its own dashboards. **A panel never establishes
ownership** and never narrows the alerts a run counts.

---

## Testing

```bash
uv run pytest tests/unit
```

```bash
uv run pytest tests/integration
```

```bash
uv run pytest tests/acceptance
```

Unit tests need nothing running. Integration and acceptance tests need Docker Compose up
and the mock dataset loaded; they skip with an explanatory message otherwise, rather than
failing.

Integration and acceptance tests use the **disposable** `alerts_bi_test` database, which
they recreate. `alerts-bi-runs db reset-test` refuses any target that is not the configured test database
and additionally requires `test` in the name, so a mistyped environment variable cannot
take out the development store.

Tests never call the network for LLM assessment. They use a deterministic fake client
scripted by `(batch_id, attempt)`, which is what makes "the second attempt succeeds" and
"all three attempts fail" expressible without timing or randomness. Live endpoint
validation is separate and opt-in.

### Large weekly event volumes

The production path processes Elasticsearch pages incrementally (design section 7.15).
It retains representative documents and compact exact facts instead of the full raw
week. Memory still grows with distinct alert identities, diagnostic scopes, predicate
combinations and active clear cycles; it is not capped solely by `ES_PAGE_SIZE`.

`ES_PAGE_SIZE` remains 1,000 by default. HTTP compression is enabled and exact total
hits are requested on the first page only. `es.read_progress` logs counts roughly every
30 seconds while pages are consumed. `es.read_schema` records `search_seconds`
(round trips, including transfer and client decoding), `cluster_seconds` (sum of ES
`took`), `normalize_seconds`, `consume_seconds`, and `elapsed_seconds`. Cluster work
is inside search time; subtracting it does not isolate network time from decoding.

A repeatable Python-only scale probe uses the existing mock definitions without
connecting to Elasticsearch, SQL Server or the model:

```bash
uv run python scripts/benchmark_streaming.py --events 300000 --mode materialized
uv run python scripts/benchmark_streaming.py --events 300000 --mode streaming
uv run python scripts/benchmark_streaming.py --events 2000000 --mode streaming
```

Run each mode in a fresh process. It prints peak process resident memory and times
for fixture construction, JSON decoding and analysis separately. It checks the event
count but is not a substitute for acceptance verification or production measurements.

### Acceptance verification

```bash
uv run alerts-bi-runs verify-acceptance
```

Runs the six acceptance teams and compares the persisted SQL rows and the rendered CSV
exports against `test/fixtures/expected-results.json`.

That manifest is **hand-authored** from the fixture definitions in
`scripts/acceptance_teams.py`, with the derivation of every number recorded alongside it.
The pipeline does not generate its own oracle: an oracle produced by the code under test
would agree with any bug that happened to be self-consistent.

The full checks (`uv run ruff format --check .`, `uv run ruff check .`,
`uv run mypy src`, all three test suites, plus acceptance verification) are what "done"
means here.

---

## The mock environment

### Evaluating the LLM review upgrade

Prompt `1.2.0` added scope-aware evidence guidance and checks for inapplicable citations. It is
a candidate for live quality evaluation; passing protocol tests does not establish better
judgment. The current prompt is `1.3.0` (ruleset `1.1.0`), which carries the same guidance
plus the R6 catalogue line. The [upgrade plan](docs/upstream/llm_review_upgrade_plan.md) records release gates and
[design section 7.13](docs/upstream/alerts_bi_design.md#713-llm-review-quality-evaluation-and-durable-audit)
specifies audit/recovery behavior.

Apply migration `004_llm_review_audit` (and the later `005_team_summary`, `006_r6_episodes`,
`007_portal_daily` and `008`, which changes `portal_reviews.basis_changed` to compare the
team's own registry entry) through the normal `alerts-bi-runs db migrate` command
before running the upgraded live pipeline (the deployment init container runs setup).
It stores requests before calls, preserves successful responses across interrupted runs,
and records uncertain interrupted attempts against the three-attempt budget. A later explicit
retry after exhaustion gets a new recorded cycle. The four report files and portal API stay
unchanged. Audit tables are operator-only and retain full documents; use existing SQL access
and backup controls, not ordinary logs, for review evidence.

Run the isolated benchmark without calling any model:

```powershell
uv run python scripts/evaluate_llm.py --mode fake --caps 1 10 --repeats 2 --out out/evaluations/smoke.json
```

It defaults to development cases, both full and factored documents, and normal/reversed
within-partition ordering. Supported caps are 1 through 200; default trials use
1/10/25/50/100/200. The checked-in 14-case corpus is draft, synthetic and small. A reported
`max_actual_batch=2` does not validate capacity at 200. The default all-good fake exercises
the harness and deliberately misses labelled violations; its precision is undefined.
Inspect per-group uncertainty and subgroup counts, not just an overall score. Explanations
still need blinded human review; summaries do not grade the truth of free text.

For an exploratory on-prem trial, configure the existing endpoint credentials, a stable
`LLM_MODEL_REVISION` when `LLM_MODEL` is a mutable alias, and an already migrated audit database:

```powershell
$env:LLM_LIVE_TEST = 'true'
uv run python scripts/evaluate_llm.py --mode live --database alerts_bi_dev --caps 1 --allow-draft
```

The explicit `--allow-draft` is needed until independent reviewers adjudicate the labels.
Evaluation scopes never read or write the production verdict cache or publish a run.
The command stops the matrix after a failed attempt unless `--continue-after-failure` is
explicitly supplied. Each completed trial saves a summary; raw requests/responses stay in
the SQL audit. No result automatically enables a model or satisfies release gates.

Use `--cases` for a separately reviewed manifest, keep families and actual groups within one
split, freeze development decisions, then use `--split holdout`. Each case supplies either a
synthetic `definition` (see the checked-in manifest) or a complete frozen `source` representative,
which is preserved exactly. Keep private case manifests outside Git. Annotations carry accepted
`principles`, `confidences`, `evidence_fields` and a `rationale`; `review_state=reviewed` requires
named `reviewers`. Include independently sampled `no_violation` cases to detect misses; confirm/
dismiss clicks alone cover only findings and are not automatically gold labels.
To compare a saved baseline
prompt, pass its UTF-8 file with `--system-prompt` and its distinct `--prompt-version`; compare
summary files with `--compare`. This keeps the current strict validator, so this comparison
isolates prompt/model changes rather than reproducing the old implementation's weaker
validator. Reproducing that old pipeline requires its matching source revision.

`LLM_MAX_COMPLETION_TOKENS=0` preserves omission of that SDK parameter. Only set a positive
value after testing support and capacity on the endpoint. Usage/cached-token fields stay null
when unavailable. Review baseline/candidate explanations and large/long representative groups
before selecting a production cap or deployment; keep the prior release/model available for
rollback of future runs. Published reviews and historical verdicts are never rewritten.

### Seeding the normal acceptance fixture

`scripts/generate_mock_alerts.py` seeds `appchi-v1` and `appchi-v2` from a seeded RNG on a
fixed clock, so the dataset is reproducible.

**A normal rerun appends another copy of every row.** Use `RESET=1` for a clean reload,
which deletes and recreates both indices with explicit mappings. The reset refuses any
endpoint that is not an explicit local mock, so a mistyped `ES_URL` cannot delete a real
index.

```bash
RESET=1 uv run python scripts/generate_mock_alerts.py
```

```bash
STATS_ONLY=1 uv run python scripts/generate_mock_alerts.py
```

Seven teams carry realistic data across the migration phases. Six `acceptance-*` teams
(`acceptance-core`, `-batching`, `-suppression`, `-blast-radius`, `-fire-patterns` and
`-unseen`) carry fixtures pinned to exact timestamps and exact expected outcomes; they exist
so the acceptance manifest can be computed by hand.

`scripts/es_scale_probe.py` is read-only and sizes the problem:

```bash
uv run python scripts/es_scale_probe.py --team checkout-api --run-at 2026-08-25T18:00:00Z
```

Its figures are approximate HyperLogLog++ cardinalities. The pipeline never uses them: it
pages every matching row and counts identities exactly, because a reported metric may not
be approximate.

---

## Architecture

```text
src/          analysis, run API, CLI, scheduling, persistence, migrations
compat/src/db/ledger.py        minimal shim for immutable historical migration imports
packages/shared/            alerts-bi-shared: SQL config, pure domain/UI building blocks
packages/operations/        alerts-bi-operations: registry, publication, decisions, reporting
config/teams.json           runtime registry values (set an explicit path outside this repo)
scripts/                    mock generation, probes, evaluation and streaming benchmark
tests/                      runs and shared-package unit/integration/acceptance checks
test/fixtures/              hand-authored acceptance oracle, unchanged by the extraction
docs/upstream/              pinned canonical design/contract documentation
```

`uv sync --frozen --all-packages` installs the workspace packages together. Build releasable
wheels with `uv build --all-packages`; consumers pin versioned wheels and never import
this checkout at runtime. The run identifier's application version remains `0.1.0`:
repository extraction does not change analysis, prompt bytes or stored identities.
Applied Alembic revision modules and their SQL files are unchanged; the tiny `src` shim
exists only to preserve their historical imports. New code imports `alerts_bi_runs`.

Both alerting guides ship inside the runs wheel. Default prompt construction uses package
resources and works from any working directory; guide text and prompt hashes remain pinned.
Registry values, output directories and optional dotenv input remain operator-supplied.

### Things worth knowing before changing anything

- **The window is exact and half-open.** `run_at` is captured once; the range is
  `[run_at - 168h, run_at)`. A mid-day run touches eight UTC dates, so the first and last
  daily buckets are partial and carry their real covered hours.
- **The run id is deterministic**, derived from team, window, registry hash and versions.
  Re-running the same team over a frozen `run_at` replaces its own rows rather than
  accumulating near-duplicates.
- **Core rules run on every raw row**, then aggregate to identity. Findings stay on the
  rows that matched and are never projected onto other rows or dates.
- **Any core finding anywhere in the window withholds the whole identity from the model.**
  V2 readiness gaps do not.
- **A batch gets three total attempts**, retried byte-for-byte as a whole. After the third
  failure every alert in it becomes `unassessed` with the shared reason. Alerts are never
  retried individually, and a partial response is never accepted.
- **Suppression resolves every ambiguity to `unmeasured`.** It feeds `flagged`, so a
  scoping predicate misread as suppression would mark good alerts bad — the most expensive
  error this design can make.

---

## Not in the MVP

Deliberately, and recorded in design section 7.4: any comparison between runs in the
scorecard or exports (the one scoped exception is the estimated time to retire v1 on the team
summary, design section 7.14), a cross-team leaderboard, historical backfill, the
company-wide unattributed-alert audit, panel discovery or live Grafana variable retrieval,
and a BI-side migration-invariant alert identity.

The first post-MVP step, the frontend, is delivered as the read-only review portal (design
section 7.10). The next is deterministic historical backfill oldest-first with no LLM calls.


Application code lives directly in `src/`. Local tests import `src`, while setuptools
maps that directory to the service's distinct installed Python package. The console
command and Docker listener are unchanged. `uv sync --frozen` installs the editable
mapping; `uv build` produces the independently installable wheel and source archive.
