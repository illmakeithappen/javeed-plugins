from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass(frozen=True)
class CompanyConfig:
    betrieb: str
    api_key: str
    company_id: str


@dataclass(frozen=True)
class RuntimeConfig:
    base_url: str
    artifact_root: Path
    default_betrieb: str | None


def load_env(dotenv_path: str | Path | None = None) -> None:
    path = Path(dotenv_path) if dotenv_path else None
    if path and path.exists():
        load_dotenv(path)
        return
    load_dotenv()


def runtime_config() -> RuntimeConfig:
    base_url = os.getenv("ORDIO_LITE_BASE_URL", "https://api.ordio.com/api/v3").rstrip("/")
    artifact_root = Path(os.getenv("ORDIO_LITE_ARTIFACT_DIR", "./artifacts")).expanduser().resolve()
    default_betrieb = os.getenv("ORDIO_LITE_DEFAULT_BETRIEB")
    artifact_root.mkdir(parents=True, exist_ok=True)
    return RuntimeConfig(base_url=base_url, artifact_root=artifact_root, default_betrieb=default_betrieb)


def get_company_config(betrieb: str) -> CompanyConfig:
    key_var = f"ORDIO_API_KEY_{betrieb.upper()}"
    company_var = f"ORDIO_COMPANY_ID_{betrieb.upper()}"
    api_key = os.getenv(key_var, "").strip()
    company_id = os.getenv(company_var, "").strip()
    if not api_key or not company_id:
        available = list_configured_betriebe()
        raise ValueError(
            f"Missing Ordio credentials for '{betrieb}'. "
            f"Expected env vars {key_var} and {company_var}. "
            f"Configured betriebe: {available or 'none'}"
        )
    return CompanyConfig(betrieb=betrieb, api_key=api_key, company_id=company_id)


def list_configured_betriebe() -> list[str]:
    result: list[str] = []
    for name, value in os.environ.items():
        if not name.startswith("ORDIO_API_KEY_") or not value.strip():
            continue
        suffix = name[len("ORDIO_API_KEY_") :]
        company_var = f"ORDIO_COMPANY_ID_{suffix}"
        if os.getenv(company_var, "").strip():
            result.append(suffix.lower())
    return sorted(set(result))


def load_constraint_profiles(profile_file: Path | None = None) -> dict[str, Any]:
    if profile_file is None:
        profile_file = Path(__file__).resolve().parent.parent / "config" / "constraint_profiles.json"
    if not profile_file.exists():
        return {}
    with profile_file.open("r", encoding="utf-8") as fh:
        return json.load(fh)
