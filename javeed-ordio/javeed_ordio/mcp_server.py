"""javeed-ordio MCP server.

Exposes tools for Ordio data sync, artifact persistence, profile management,
plan generation (via allocation_core), plan evaluation, and plan comparison.
"""
from __future__ import annotations

import argparse
import os
from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import (
    CompanyConfig,
    get_company_config,
    load_constraint_profiles,
    load_env,
    runtime_config,
)
from .ingest import SnapshotBuildInput, build_snapshot
from .ordio_client import ReadOnlyOrdioClient
from .storage import (
    list_plans as _list_plans,
    list_snapshots as _list_snapshots,
    load_plan as _load_plan,
    load_snapshot as _load_snapshot,
    save_plan as _save_plan,
    save_snapshot as _save_snapshot,
)

mcp = FastMCP(
    "javeed-ordio",
    host=os.getenv("HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", "8000")),
    instructions=(
        "Shift planning engine for Javeed gastro venues. "
        "Syncs Ordio workforce data, generates deterministic allocation plans, "
        "evaluates plan quality, and compares plans across constraint profiles. "
        "All Ordio access is read-only."
    ),
)

_ENV_FILE: str | None = None
_CLIENT: ReadOnlyOrdioClient | None = None


def _client() -> ReadOnlyOrdioClient:
    global _CLIENT
    if _CLIENT is None:
        load_env(_ENV_FILE or os.getenv("ORDIO_LITE_ENV_FILE"))
        cfg = runtime_config()
        _CLIENT = ReadOnlyOrdioClient(base_url=cfg.base_url)
    return _CLIENT


def _artifact_root():
    load_env(_ENV_FILE or os.getenv("ORDIO_LITE_ENV_FILE"))
    return runtime_config().artifact_root


# -- Data sync --

@mcp.tool()
def sync_snapshot(betrieb: str, start: str, end: str) -> dict[str, Any]:
    """Fetch Ordio data for a date range and store as a local snapshot.

    Returns snapshot manifest with snapshot_id, counts, and file path.
    """
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date > end_date:
        raise ValueError("start date is after end date")

    company = get_company_config(betrieb)
    raw_payload = _client().fetch_snapshot_payload(
        company, start_date=start_date, end_date=end_date,
    )
    snapshot = build_snapshot(
        SnapshotBuildInput(
            betrieb=betrieb,
            start_date=start_date,
            end_date=end_date,
            payload=raw_payload,
        )
    )
    target = _save_snapshot(_artifact_root(), snapshot, raw_payload)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "betrieb": betrieb,
        "range": snapshot["range"],
        "counts": snapshot["metadata"]["counts"],
        "path": str(target),
    }


# -- Snapshot CRUD --

@mcp.tool()
def list_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    """List local snapshot manifests, newest first."""
    return _list_snapshots(_artifact_root(), limit=limit)


@mcp.tool()
def load_snapshot(snapshot_id: str | None = None) -> dict[str, Any]:
    """Load a full snapshot JSON by ID (or latest if omitted)."""
    return _load_snapshot(_artifact_root(), snapshot_id=snapshot_id)


# -- Plan CRUD --

@mcp.tool()
def list_plans(limit: int = 20) -> list[dict[str, Any]]:
    """List local plan manifests, newest first."""
    return _list_plans(_artifact_root(), limit=limit)


@mcp.tool()
def load_plan(plan_id: str | None = None) -> dict[str, Any]:
    """Load a full plan JSON by ID (or latest if omitted)."""
    return _load_plan(_artifact_root(), plan_id=plan_id)


@mcp.tool()
def save_plan(plan_json: str) -> dict[str, Any]:
    """Persist a plan artifact from an external allocation run.

    Accepts plan as a JSON string. Returns the manifest with plan_id and path.
    """
    import json
    plan = json.loads(plan_json)
    if "plan_id" not in plan:
        from uuid import uuid4
        plan["plan_id"] = f"plan-{uuid4().hex[:12]}"
    target = _save_plan(_artifact_root(), plan)
    return {
        "plan_id": plan["plan_id"],
        "path": str(target),
    }


# -- Profile management --

@mcp.tool()
def list_profiles() -> dict[str, Any]:
    """List available constraint profiles with their descriptions."""
    profiles = load_constraint_profiles()
    result = {}
    for name, profile in profiles.items():
        result[name] = {
            "employee_count": len(profile.get("employee_rules", {})),
            "policy": profile.get("policy", {}),
        }
    return result


@mcp.tool()
def load_profile(profile_name: str) -> dict[str, Any]:
    """Load a constraint profile by name. Returns full profile JSON."""
    profiles = load_constraint_profiles()
    if profile_name not in profiles:
        available = list(profiles.keys())
        raise ValueError(
            f"Profile '{profile_name}' not found. Available: {available}"
        )
    return profiles[profile_name]


# -- Allocation engine --

@mcp.tool()
def generate_plan(
    range_from: str,
    range_to: str,
    profile_name: str = "default",
    snapshot_id: str | None = None,
    mechanism: str = "algo",
) -> dict[str, Any]:
    """Run the allocation engine on a snapshot and produce a plan artifact.

    Returns plan summary (assignments, unassigned, metrics, fairness).
    The full plan including evaluation_matrix is persisted to disk.
    Use load_plan() to retrieve the full plan if needed.
    """
    from allocation_core.mechanisms import run_mechanism

    snapshot = _load_snapshot(_artifact_root(), snapshot_id=snapshot_id)
    profiles = load_constraint_profiles()
    if profile_name not in profiles:
        available = list(profiles.keys())
        raise ValueError(
            f"Profile '{profile_name}' not found. Available: {available}"
        )
    profile = profiles[profile_name]

    plan = run_mechanism(
        mechanism,
        snapshot,
        range_from=range_from,
        range_to=range_to,
        profile_name=profile_name,
        profile=profile,
    )

    _save_plan(_artifact_root(), plan)

    # Strip evaluation_matrix and per-assignment alternatives to keep
    # the MCP response size manageable.
    summary = {k: v for k, v in plan.items() if k != "evaluation_matrix"}
    if "assignments" in summary:
        summary["assignments"] = [
            {k: v for k, v in a.items() if k != "alternatives"}
            for a in summary["assignments"]
        ]
    return summary


@mcp.tool()
def evaluate_plan(plan_id: str | None = None) -> dict[str, Any]:
    """Compute quality metrics for a plan: fill rate, fairness, scoring, coverage gaps.

    Uses the latest plan if plan_id is omitted.
    """
    from .eval_lite import evaluate_plan_lite

    plan = _load_plan(_artifact_root(), plan_id=plan_id)
    return evaluate_plan_lite(plan)


@mcp.tool()
def compare_plans(plan_id_a: str, plan_id_b: str) -> dict[str, Any]:
    """Compare two plans side by side: fill rates, fairness, scoring, slot-level divergence."""
    from .compare import compare_plans_impl

    plan_a = _load_plan(_artifact_root(), plan_id=plan_id_a)
    plan_b = _load_plan(_artifact_root(), plan_id=plan_id_b)
    return compare_plans_impl(plan_a, plan_b)


# -- Server entrypoints --

async def _run_http() -> None:
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, PlainTextResponse
    from starlette.routing import Route

    api_key = os.getenv("MCP_API_KEY")

    class BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != api_key:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    starlette_app = mcp.streamable_http_app()

    if api_key:
        starlette_app.add_middleware(BearerAuth)

    starlette_app.routes.append(
        Route("/health", lambda r: PlainTextResponse("ok"))
    )

    config = uvicorn.Config(
        starlette_app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        log_level="info",
    )
    await uvicorn.Server(config).serve()


def main() -> None:
    global _ENV_FILE

    parser = argparse.ArgumentParser(description="Run javeed-ordio MCP server")
    parser.add_argument("--env-file", default=None, help="Path to .env file")
    parser.add_argument(
        "--transport",
        default=None,
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport (default: streamable-http when PORT is set, else stdio)",
    )
    args = parser.parse_args()
    _ENV_FILE = args.env_file

    transport = args.transport
    if transport is None:
        transport = "streamable-http" if os.getenv("PORT") else "stdio"

    if transport == "streamable-http":
        import anyio
        anyio.run(_run_http)
    else:
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
