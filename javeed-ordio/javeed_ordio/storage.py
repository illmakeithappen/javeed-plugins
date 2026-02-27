from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def _json_load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def snapshot_root(artifact_root: Path) -> Path:
    path = artifact_root / "snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def plan_root(artifact_root: Path) -> Path:
    path = artifact_root / "plans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_root(artifact_root: Path) -> Path:
    path = artifact_root / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_snapshot(artifact_root: Path, snapshot: dict[str, Any], raw_payload: dict[str, Any]) -> Path:
    root = snapshot_root(artifact_root)
    sid = snapshot["snapshot_id"]
    target = root / sid
    (target / "raw").mkdir(parents=True, exist_ok=True)
    (target / "normalized").mkdir(parents=True, exist_ok=True)

    _json_dump(target / "normalized" / "snapshot.json", snapshot)
    for key, value in raw_payload.items():
        _json_dump(target / "raw" / f"{key}.json", value)

    manifest = {
        "snapshot_id": sid,
        "betrieb": snapshot.get("betrieb"),
        "from": snapshot.get("range", {}).get("from"),
        "to": snapshot.get("range", {}).get("to"),
        "generated_at": snapshot.get("generated_at"),
        "counts": snapshot.get("metadata", {}).get("counts", {}),
        "path": str(target.resolve()),
    }
    _json_dump(target / "manifest.json", manifest)
    _json_dump(root / "latest.json", manifest)
    return target


def list_snapshots(artifact_root: Path, limit: int = 20) -> list[dict[str, Any]]:
    root = snapshot_root(artifact_root)
    manifests: list[dict[str, Any]] = []

    for child in root.iterdir():
        if not child.is_dir():
            continue
        manifest_file = child / "manifest.json"
        if not manifest_file.exists():
            continue
        try:
            manifests.append(_json_load(manifest_file))
        except Exception:
            continue

    manifests.sort(key=lambda row: row.get("generated_at", ""), reverse=True)
    return manifests[:limit]


def get_snapshot_manifest(artifact_root: Path, snapshot_id: str | None = None) -> dict[str, Any]:
    root = snapshot_root(artifact_root)
    if snapshot_id:
        manifest_path = root / snapshot_id / "manifest.json"
    else:
        manifest_path = root / "latest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("snapshot manifest not found")
    return _json_load(manifest_path)


def load_snapshot(artifact_root: Path, snapshot_id: str | None = None) -> dict[str, Any]:
    manifest = get_snapshot_manifest(artifact_root, snapshot_id)
    sid = manifest["snapshot_id"]
    path = snapshot_root(artifact_root) / sid / "normalized" / "snapshot.json"
    if not path.exists():
        raise FileNotFoundError(f"snapshot payload not found: {sid}")
    return _json_load(path)


def save_plan(artifact_root: Path, plan: dict[str, Any]) -> Path:
    root = plan_root(artifact_root)
    pid = plan["plan_id"]
    target = root / pid
    target.mkdir(parents=True, exist_ok=True)
    _json_dump(target / "plan.json", plan)

    manifest = {
        "plan_id": pid,
        "snapshot_id": plan.get("snapshot_id"),
        "generated_at": plan.get("generated_at"),
        "profile": plan.get("profile"),
        "range": plan.get("range"),
        "counts": plan.get("metrics", {}),
        "path": str(target.resolve()),
    }
    _json_dump(target / "manifest.json", manifest)
    _json_dump(root / "latest.json", manifest)
    return target


def list_plans(artifact_root: Path, limit: int = 20) -> list[dict[str, Any]]:
    root = plan_root(artifact_root)
    manifests: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        manifest_file = child / "manifest.json"
        if not manifest_file.exists():
            continue
        try:
            manifests.append(_json_load(manifest_file))
        except Exception:
            continue
    manifests.sort(key=lambda row: row.get("generated_at", ""), reverse=True)
    return manifests[:limit]


def load_plan(artifact_root: Path, plan_id: str | None = None) -> dict[str, Any]:
    root = plan_root(artifact_root)
    if plan_id:
        manifest_path = root / plan_id / "manifest.json"
    else:
        manifest_path = root / "latest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("plan manifest not found")
    manifest = _json_load(manifest_path)
    pid = manifest["plan_id"]
    path = root / pid / "plan.json"
    if not path.exists():
        raise FileNotFoundError(f"plan payload not found: {pid}")
    return _json_load(path)


def save_report(artifact_root: Path, report_type: str, name: str, html: str, *, metadata: dict[str, Any]) -> Path:
    root = report_root(artifact_root) / report_type
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / f"{name}.html"
    file_path.write_text(html, encoding="utf-8")
    _json_dump(file_path.with_suffix(".meta.json"), metadata)
    return file_path
