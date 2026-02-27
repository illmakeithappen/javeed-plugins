# javeed-ordio

Shift planning plugin for Javeed's gastro venues. Connects Claude to the Ordio workforce management API, providing deterministic allocation planning, coverage analysis, and Betriebsleiter review workflows -- all read-only.

## Ecosystem

This plugin is one piece of the Javeed planning system:

- **Ordio API** -- Source of truth for employees, shifts, applications, absences, wages
- **javeed-ordio plugin** (this project) -- Analysis and planning layer for Claude. Syncs data, generates plans, produces review documents.
- **Javeed App** -- Web UI where the Betriebsleiter reviews results, approves assignments, and manages the team

The plugin never writes back to Ordio. Plans and reports are local artifacts. After review, confirmed assignments are entered manually in Ordio by the Betriebsleiter.

For the full ecosystem diagram and architecture, see `skills/ordio-allocation/references/plugin-context.md`.

## What's Inside

### MCP Server (Python)

16 tools for snapshot management, allocation, reporting, and Q&A. Runs locally via stdio or remotely on Cloud Run via HTTP.

| Tool | Purpose |
|------|---------|
| `sync_snapshot` | Fetch Ordio data for a date range |
| `list_snapshots` / `snapshot_summary` | Browse and summarize snapshots |
| `get_open_shifts` / `get_applications` | Open shifts and applicant data |
| `get_employee_shift_profile` | Single employee deep-dive |
| `snapshot_report` / `snapshot_report_md` | HTML/Markdown snapshot reports |
| `generate_plan` | Run the deterministic allocator |
| `list_plans` / `plan_summary` | Browse and summarize plans |
| `plan_report` / `plan_report_md` | HTML/Markdown plan reports |
| `explain_plan_assignment` | Score breakdown for an assignment |
| `ask_plan` | Q&A about plan decisions |
| `list_profiles` | List constraint profiles |

### Commands (Slash Workflows)

| Command | What it does |
|---------|-------------|
| `/ordio-weekly` | Sync fresh data, produce KPIs, generate weekly reports |
| `/ordio-plan` | Generate allocation plan, review fairness, produce reports |
| `/ordio-gaps` | Analyze coverage gaps, recommend staffing outreach |
| `/ordio-employee` | Deep-dive into one employee's profile and anomalies |
| `/ordio-compare` | Compare allocation plans across constraint profiles |

### Skill (Domain Knowledge)

**ordio-allocation** -- Loaded automatically when discussing shift planning. Contains the allocation algorithm spec, constraint reference, review sheet format, and ecosystem context.

Reference documents in `skills/ordio-allocation/references/`:

| Document | Content |
|----------|---------|
| `algorithm.md` | Scoring formula, processing pipeline, fairness mechanisms, limitations |
| `constraints.md` | 16 hard blockers, soft modifiers, constraint profiles, preference parsing |
| `review-sheet.md` | Wochenplan-Freigabe UI spec: table format, reasoning templates, decision workflow |
| `plugin-context.md` | How this plugin fits into the Javeed ecosystem (Ordio API, plugin, app) |

## What You Can Customize

| Component | Location | How |
|-----------|----------|-----|
| **Constraint profiles** | `config/constraint_profiles.json` | Add new profiles, adjust employee rules, change policy flags |
| **Commands** | `commands/ordio-*.md` | Modify workflow steps, change output format, add new commands |
| **Skill knowledge** | `skills/ordio-allocation/` | Update domain descriptions, add reference docs |

The Python MCP server and allocator engine are not editable via Cowork -- they run as a process (local or remote).

## Setup

### Connection

**Remote (Cowork users):** The `.mcp.json` points to the Cloud Run deployment. Set the `JAVEED_ORDIO_API_KEY` env var to the bearer token.

**Local (development):** Install the package and run via stdio:
```bash
cd plugins/javeed-ordio
pip install -e .
javeed-ordio-mcp --transport stdio
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `JAVEED_ORDIO_API_KEY` | Remote only | Bearer token for Cloud Run MCP access |
| `ORDIO_LITE_ENV_FILE` | Local only | Path to `.env` file with Ordio API credentials |
| `ORDIO_LITE_ARTIFACT_DIR` | No | Directory for snapshots/plans/reports (default: `./artifacts`) |
| `ORDIO_LITE_DEFAULT_BETRIEB` | No | Default location (e.g., `rosa`, `hinweg`, `bacchus`) |
| `MCP_API_KEY` | Server only | Bearer token the server checks (set on Cloud Run) |

### Constraint Profiles

Three built-in profiles in `config/constraint_profiles.json`:
- `default` -- Generic fair distribution, no employee-specific rules
- `bacchus_march_2026` -- Bacchus, March 2026 (10 employee rules)
- `hinweg_march_2026` -- Hin&Weg, March 2026 (14 employee rules)

See `skills/ordio-allocation/references/constraints.md` for the full constraint reference.

## Usage

Typical workflow:

1. `/ordio-weekly hinweg 2026-03-01 2026-03-07` -- Sync and review the week
2. `/ordio-gaps` -- Find coverage holes
3. `/ordio-plan 2026-03-01 2026-03-07 hinweg_march_2026` -- Generate allocation
4. `/ordio-employee Annika` -- Check a specific employee
5. `/ordio-compare 2026-03-01 2026-03-07` -- Compare profiles side by side
