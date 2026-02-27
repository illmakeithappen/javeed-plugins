# Javeed Plugins

Claude Code / Cowork plugin marketplace for Javeed gastro venues.

## Plugins

### javeed-ordio

Shift allocation engine with 11 MCP tools, 5 slash commands, 7 skills (4 domain + 3 Cowork workflows), and constraint profiles for three venues (Rosa, Hin & Weg, Bacchus).

**MCP Tools**: sync_snapshot, list_snapshots, load_snapshot, list_plans, load_plan, save_plan, list_profiles, load_profile, generate_plan, evaluate_plan, compare_plans

**Cowork Skills**: cowork-planning (weekly workflow), cowork-optimization (profile comparison), cowork-gap-resolution (unfilled shift diagnosis)

## Installation

```bash
claude plugin marketplace add illmakeithappen/javeed-plugins
claude plugin install javeed-ordio
```

## Setup

The plugin connects to a remote MCP server. Set the API key:

```bash
export JAVEED_ORDIO_API_KEY="your-api-key"
```
