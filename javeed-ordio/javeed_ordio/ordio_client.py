from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from time import sleep
from typing import Any

import httpx

from .config import CompanyConfig
from .utils import to_iso_datetime

logger = logging.getLogger(__name__)

# Candidate status codes used in Ordio planning objects.
CANDIDATE_APPLIED = 1
CANDIDATE_WORKING = 2
CANDIDATE_WORKING_SEEKING_REPLACEMENT = 3
CANDIDATE_DECLINED = 4
CANDIDATE_CANCELLED = 9
CANDIDATE_REMOVED = 10

ACTIVE_CANDIDATE_STATUSES = {CANDIDATE_WORKING, CANDIDATE_WORKING_SEEKING_REPLACEMENT}
NEGATIVE_CANDIDATE_STATUSES = {CANDIDATE_DECLINED, CANDIDATE_CANCELLED, CANDIDATE_REMOVED}


@dataclass(frozen=True)
class ReadOperation:
    method: str
    path_template: str


READ_ONLY_OPERATIONS: dict[str, ReadOperation] = {
    "shifts_for_range": ReadOperation("GET", "/companies/{company}/shifts-for-range"),
    "search_shifts": ReadOperation("POST", "/companies/{company}/search-shifts"),
    "search_employees": ReadOperation("POST", "/companies/{company}/search-employees"),
    "employments": ReadOperation("GET", "/companies/{company}/employments"),
    "branches": ReadOperation("GET", "/companies/{company}/branches"),
    "absences": ReadOperation("GET", "/companies/{company}/absences"),
}


class ReadOnlyOrdioClient:
    """Strict read-only Ordio API client.

    Only the operation names listed in READ_ONLY_OPERATIONS are executable.
    Any unknown operation is rejected before any network request is sent.
    """

    def __init__(self, *, base_url: str, timeout_s: float = 30.0, retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.retries = max(1, retries)

    def _headers(self, cfg: CompanyConfig) -> dict[str, str]:
        return {
            "X-Api-Key": cfg.api_key,
            "Accept": "application/json",
        }

    def _request(
        self,
        *,
        operation: str,
        cfg: CompanyConfig,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        op = READ_ONLY_OPERATIONS.get(operation)
        if op is None:
            raise ValueError(f"Operation '{operation}' is not allowed in read-only mode")

        path = op.path_template.format(company=cfg.company_id)
        url = f"{self.base_url}{path}"

        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = httpx.request(
                    op.method,
                    url,
                    headers=self._headers(cfg),
                    params=params,
                    json=json_body,
                    timeout=self.timeout_s,
                )
                if resp.status_code >= 500 and attempt < self.retries - 1:
                    sleep(2**attempt)
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < self.retries - 1:
                    sleep(2**attempt)
                    continue
                raise
            except httpx.HTTPStatusError:
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("request failed without an explicit exception")

    def fetch_shifts_for_range(
        self,
        cfg: CompanyConfig,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        params = {
            "start": to_iso_datetime(start_date),
            "end": to_iso_datetime(end_date, end_of_day=True),
        }
        resp = self._request(operation="shifts_for_range", cfg=cfg, params=params)
        data = resp.json()
        return data if isinstance(data, list) else []

    def search_shifts(
        self,
        cfg: CompanyConfig,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        cursor: str | None = None
        items: list[dict[str, Any]] = []

        while True:
            body: dict[str, Any] = {
                "start": to_iso_datetime(start_date),
                "end": to_iso_datetime(end_date, end_of_day=True),
            }
            if cursor:
                body["cursor"] = cursor
            resp = self._request(operation="search_shifts", cfg=cfg, json_body=body)
            payload = resp.json() or {}
            items.extend(payload.get("items", []))
            if payload.get("has_more") and payload.get("cursor"):
                cursor = payload["cursor"]
            else:
                break

        return items

    def fetch_employees(self, cfg: CompanyConfig, *, ref_date: date | None = None) -> list[dict[str, Any]]:
        if ref_date is None:
            ref_date = date.today()
        body = {"date": to_iso_datetime(ref_date)}
        resp = self._request(operation="search_employees", cfg=cfg, json_body=body)
        data = resp.json() or {}
        return data.get("items", []) if isinstance(data, dict) else []

    def fetch_employments(self, cfg: CompanyConfig) -> dict[str, str]:
        resp = self._request(operation="employments", cfg=cfg)
        data = resp.json()
        if not isinstance(data, list):
            return {}
        mapping: dict[str, str] = {}
        for row in data:
            eid = row.get("id")
            name = row.get("name")
            if eid is None or name is None:
                continue
            mapping[str(eid)] = str(name)
        return mapping

    def fetch_branches(self, cfg: CompanyConfig) -> list[dict[str, Any]]:
        resp = self._request(operation="branches", cfg=cfg)
        data = resp.json()
        return data if isinstance(data, list) else []

    def fetch_absences(self, cfg: CompanyConfig, *, start_date: date, end_date: date) -> list[dict[str, Any]]:
        params = {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}
        resp = self._request(operation="absences", cfg=cfg, params=params)
        payload = resp.json()
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload, list):
            return payload
        return []

    def fetch_snapshot_payload(self, cfg: CompanyConfig, *, start_date: date, end_date: date) -> dict[str, Any]:
        shifts = self.fetch_shifts_for_range(cfg, start_date=start_date, end_date=end_date)
        if not shifts:
            # Some accounts have more complete payload through search-shifts.
            try:
                shifts = self.search_shifts(cfg, start_date=start_date, end_date=end_date)
            except Exception:
                logger.exception("search_shifts fallback failed")

        return {
            "shifts": shifts,
            "employees": self.fetch_employees(cfg, ref_date=start_date),
            "employments": self.fetch_employments(cfg),
            "branches": self.fetch_branches(cfg),
            "absences": self.fetch_absences(cfg, start_date=start_date, end_date=end_date),
        }
