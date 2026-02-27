"""Parse employee directives (Vorgaben) into structured employee_rules.

Two paths:
  1. LLM path (primary): parse_vorgaben_llm() -- raw German text → one Claude call → structured rules
  2. CSV path (fallback): load_directives() -- directives.csv with regex parsing
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from .schemas import pipe_split

logger = logging.getLogger(__name__)

# Active rule fields — the fields build_profile() keeps in employee_rules.
# (Dead fields like base_weekly_hours, max_additional_weekly_hours are stripped.)
_ACTIVE_RULE_FIELDS = [
    "target_weekly_hours",
    "max_monthly_hours",
    "max_weekly_hours",
    "max_additional_monthly_hours",
    "no_additional_shifts",
    "disable_max_hours",
    "preferred_working_areas",
    "preferred_shift_types",
    "notes",
]

_DEFAULT_PROFILES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "plugins"
    / "javeed-ordio"
    / "config"
    / "constraint_profiles.json"
)

# Fields the algorithm consumes from employee_rules
_RULE_FIELDS = [
    "target_weekly_hours",
    "max_monthly_hours",
    "max_weekly_hours",
    "max_additional_monthly_hours",
    "no_additional_shifts",
    "disable_max_hours",
    "preferred_working_areas",
    "preferred_shift_types",
    "notes",
]

def build_profile(
    profile_name: str,
    *,
    profiles_path: Path | None = None,
    vorgaben_text: str | None = None,
    employee_names: list[str] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Build a complete profile dict from a constraint profile + optional vorgaben.

    Steps:
      1. Load constraint_profiles.json from *profiles_path* (or default location).
      2. Look up *profile_name*; fall back to "default" if not found.
      3. Extract ``policy`` (full pass-through, no filtering).
      4. Extract ``employee_rules``, keeping only ``_ACTIVE_RULE_FIELDS`` per employee.
      5. Build ``_rule_sources`` with every kept field tagged as ``"ordio"``.
      6. If *vorgaben_text* is provided (with *employee_names*), call
         ``parse_vorgaben_llm()`` to merge management directives, filtering
         results to ``_ACTIVE_RULE_FIELDS`` as well.
      7. Return the assembled profile dict.

    Parameters
    ----------
    profile_name : str
        Key in constraint_profiles.json (e.g. ``"bacchus_march_2026"``).
    profiles_path : Path, optional
        Override the path to constraint_profiles.json.
    vorgaben_text : str, optional
        Raw German management directives to merge via LLM.
    employee_names : list[str], optional
        Known employee names (required when *vorgaben_text* is provided).
    model : str, optional
        Override Claude model for vorgaben parsing.

    Returns
    -------
    dict
        ``{"profile_name", "description", "policy", "employee_rules", "_rule_sources"}``
    """
    path = profiles_path or _DEFAULT_PROFILES_PATH
    with open(path, encoding="utf-8") as fh:
        all_profiles = json.load(fh)

    # Look up or fall back to default
    if profile_name in all_profiles:
        raw = all_profiles[profile_name]
    else:
        logger.warning(
            "Profile '%s' not found in %s — falling back to 'default'",
            profile_name, path,
        )
        profile_name = "default"
        raw = all_profiles["default"]

    # Policy: full pass-through
    policy = dict(raw.get("policy", {}))

    # Employee rules: filter to _ACTIVE_RULE_FIELDS only
    employee_rules: dict[str, dict[str, Any]] = {}
    rule_sources: dict[str, dict[str, str]] = {}

    for emp, fields in raw.get("employee_rules", {}).items():
        filtered = {k: v for k, v in fields.items() if k in _ACTIVE_RULE_FIELDS}
        if filtered:
            employee_rules[emp] = filtered
            rule_sources[emp] = {k: "ordio" for k in filtered}

    # Merge vorgaben if provided
    if vorgaben_text and employee_names:
        _, vorgaben_rules, vorgaben_sources = parse_vorgaben_llm(
            vorgaben_text,
            employee_names,
            existing_rules=employee_rules,
            model=model,
        )
        # Merge vorgaben results, filtering to active fields
        for emp, fields in vorgaben_rules.items():
            filtered = {k: v for k, v in fields.items() if k in _ACTIVE_RULE_FIELDS}
            if filtered:
                employee_rules.setdefault(emp, {}).update(filtered)
                emp_sources = rule_sources.setdefault(emp, {})
                for k in filtered:
                    emp_sources[k] = vorgaben_sources.get(emp, {}).get(k, "vorgaben")

    return {
        "profile_name": profile_name,
        "description": raw.get("description", ""),
        "policy": policy,
        "employee_rules": employee_rules,
        "_rule_sources": rule_sources,
    }


_VORGABEN_PROMPT = """\
Du bist ein Schichtplanungs-Assistent. Erstelle einheitliche Mitarbeiter-Regeln aus \
zwei Quellen: bestehende System-Regeln (Ordio) und Management-Vorgaben (Notizen).

Bekannte Mitarbeiter:
{employee_names}

{existing_rules_section}

Management-Vorgaben:
---
{text}
---

Aufgabe: Erstelle fuer jeden Mitarbeiter, der Regeln hat (aus Ordio ODER Vorgaben), \
ein einheitliches Regel-Objekt. Jedes Feld bekommt einen "source"-Tag:
- "ordio" = unveraendert aus dem bestehenden System
- "vorgaben" = neu oder geaendert durch die Management-Vorgaben

Ordne Vorgaben dem passenden Mitarbeiter zu (fuzzy Name-Matching erlaubt). \
Wenn eine Vorgabe keinem bestimmten Mitarbeiter zugeordnet werden kann, verwende \
den Schluessel "_global".

Ausgabe-Schema (JSON-Objekt):
{{
  "Mitarbeitername": {{
    "feldname": {{"value": <wert>, "source": "ordio"|"vorgaben"}},
    ...
  }}
}}

Verfuegbare Felder:
- "target_weekly_hours": number (Ziel-Stunden/Woche)
- "max_monthly_hours": number (Obergrenze Stunden/Monat)
- "max_weekly_hours": number (Obergrenze Stunden/Woche)
- "max_additional_monthly_hours": number (max. zusaetzliche Stunden/Monat)
- "no_additional_shifts": boolean (keine weiteren Schichten)
- "disable_max_hours": boolean (Obergrenzen deaktivieren)
- "preferred_shift_types": array (z.B. ["mittel", "spaet"])
- "preferred_working_areas": array (z.B. ["theke", "service"])
- "notes": string (Freitext)

Nur gesetzte Felder angeben. Zahlen als Zahlen, nicht als Strings.
Antworte NUR mit dem JSON-Objekt, kein weiterer Text.\
"""


def parse_vorgaben_llm(
    text: str,
    employee_names: list[str],
    existing_rules: dict[str, dict] | None = None,
    *,
    model: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    """Parse Vorgaben text + existing Ordio rules into unified employee_rules via Claude.

    One API call that sees the full picture: existing DB rules + executive notes.
    Returns unified rules with per-field source tracking.

    Parameters
    ----------
    text : str
        Raw unstructured German text with management directives.
    employee_names : list[str]
        Known employee full names for matching.
    existing_rules : dict, optional
        Current employee_rules from profile.json (Ordio source).
    model : str, optional
        Override Claude model (default: ANTHROPIC_MODEL env var or claude-sonnet-4-20250514).

    Returns
    -------
    raw_directives : list[dict]
        Synthetic directive rows for audit/display.
    employee_rules : dict[str, dict]
        Unified rules keyed by employee name.
    rule_sources : dict[str, dict[str, str]]
        Per-field source tracking: {name: {field: "ordio"|"vorgaben"}}.
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set -- cannot parse vorgaben via LLM")

    if not model:
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    # Build existing rules section for prompt
    if existing_rules:
        lines = ["Bestehende System-Regeln (Ordio):"]
        for name, rules in existing_rules.items():
            lines.append(f"  {name}: {json.dumps(rules, ensure_ascii=False)}")
        existing_rules_section = "\n".join(lines)
    else:
        existing_rules_section = "Bestehende System-Regeln (Ordio): keine"

    prompt = _VORGABEN_PROMPT.format(
        employee_names="\n".join(f"- {n}" for n in employee_names),
        existing_rules_section=existing_rules_section,
        text=text.strip(),
    )

    client = anthropic.Anthropic(api_key=api_key, timeout=60.0)
    for _attempt in range(3):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 529) and _attempt < 2:
                import time
                wait = 2 ** (_attempt + 1)
                logger.warning("API %s, retrying in %ds ...", exc.status_code, wait)
                time.sleep(wait)
            else:
                raise

    raw_text = message.content[0].text if message.content else ""
    logger.info("Vorgaben LLM parse: %d input chars → %d output chars (model=%s)",
                len(text), len(raw_text), model)

    # Extract JSON from response
    raw_result = _extract_json_object(raw_text)

    # Split value+source tagged output into separate dicts
    employee_rules: dict[str, dict[str, Any]] = {}
    rule_sources: dict[str, dict[str, str]] = {}

    for name, fields in raw_result.items():
        if not isinstance(fields, dict):
            continue
        clean: dict[str, Any] = {}
        sources: dict[str, str] = {}

        for k, v in fields.items():
            if k not in _RULE_FIELDS:
                continue

            # Handle {value, source} tagged format
            if isinstance(v, dict) and "value" in v:
                val = v["value"]
                src = v.get("source", "vorgaben")
            else:
                # Untagged fallback: treat as vorgaben
                val = v
                src = "vorgaben"

            coerced = _coerce_field(k, val)
            if coerced is not None:
                clean[k] = coerced
                sources[k] = src

        if clean:
            employee_rules[name] = clean
            rule_sources[name] = sources

    # Build synthetic raw_directives for audit display
    raw_directives: list[dict[str, str]] = []
    idx = 1
    for name, fields in employee_rules.items():
        parts = []
        for k, v in fields.items():
            src = rule_sources.get(name, {}).get(k, "?")
            parts.append(f"{k}={v} [{src}]")
        raw_directives.append({
            "id": f"D-{idx:03d}",
            "text": ", ".join(parts),
            "employees": "" if name == "_global" else name,
            "source": "vorgaben_llm",
        })
        idx += 1

    return raw_directives, employee_rules, rule_sources


def _coerce_field(field: str, value: Any) -> Any:
    """Coerce a field value to its expected type, or return None if invalid."""
    if value is None:
        return None
    if field in ("preferred_shift_types", "preferred_working_areas"):
        return value if isinstance(value, list) else [value]
    if field in ("no_additional_shifts", "disable_max_hours"):
        return bool(value)
    if field == "notes":
        return str(value)
    # Numeric fields
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_json_object(text: str) -> dict:
    """Extract a JSON object from LLM response text."""
    # Strip markdown code fences
    if "```" in text:
        for part in text.split("```")[1:]:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                text = cleaned
                break

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        logger.warning("No JSON object found in LLM response")
        return {}

    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse LLM JSON: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# CSV fallback path (regex-based)
# ---------------------------------------------------------------------------


def parse_directive(text: str) -> dict[str, Any]:
    """Parse a single German directive text into structured employee-rule fields.

    Returns a dict of rule fields that can be merged into an employee_rules entry.
    Unrecognised text is stored under ``notes``.
    """
    from allocation_core.preferences import _norm_text

    if not text or not text.strip():
        return {}

    norm = _norm_text(text)
    result: dict[str, Any] = {}
    matched = False

    # "keine weiteren/zusaetzlichen/extra Schichten"
    if re.search(r"keine.*(?:weiteren|zusaetzlich|extra).*schichten", norm):
        result["no_additional_shifts"] = True
        matched = True

    # "maximal zu der festen Schicht noch Xh/Monat zusaetzlich"
    # Matches both "noch 8h/Monat zusaetzlich" and "6h pro Monat zusaetzlich"
    m = re.search(r"(?:noch|zusaetzlich)\s+(\d+)\s*h.*(?:monat|woche)", norm)
    if not m:
        m = re.search(r"(\d+)\s*h.*(?:monat|woche).*zusaetzlich", norm)
    if m and "zusaetzlich" in norm:
        unit = "monat" if "monat" in norm[m.start():] else "woche"
        if unit == "monat":
            result["max_additional_monthly_hours"] = int(m.group(1))
        else:
            result["max_additional_monthly_hours"] = round(int(m.group(1)) * 4.33, 1)
        matched = True

    # "nicht mehr als Xh/Woche" or "maximal Xh/Woche"
    m = re.search(r"(?:nicht mehr als|maximal)\s+(\d+)\s*h\s*/?\s*woche", norm)
    if m:
        result["max_weekly_hours"] = int(m.group(1))
        matched = True

    # "maximal Xh/Monat"
    m = re.search(r"(?:nicht mehr als|maximal)\s+(\d+)\s*h\s*/?\s*monat", norm)
    if m:
        result["max_monthly_hours"] = int(m.group(1))
        matched = True

    # "ca. Xh/Woche" (target, not max) -- only if not already matched as max
    if "max_weekly_hours" not in result:
        m = re.search(r"(?:ca\.?\s*)?(\d+)\s*h\s*/?\s*woche", norm)
        if m:
            result["target_weekly_hours"] = int(m.group(1))
            matched = True

    # "ca. Xh/Monat" (target, not max) -- only if not already matched as max or additional cap
    if "max_monthly_hours" not in result and "max_additional_monthly_hours" not in result:
        m = re.search(r"(?:ca\.?\s*)?(\d+)\s*h\s*/?\s*monat", norm)
        if m:
            result["target_weekly_hours"] = round(int(m.group(1)) / 4.33, 1)
            matched = True

    # "nur Mittelschichten / Fruehschichten / Spaetschichten"
    m = re.search(r"nur\s+(mittel|frueh|spaet)schichten", norm)
    if m:
        result["preferred_shift_types"] = [m.group(1)]
        matched = True

    # "plus eine Mittelschicht pro Woche" -- specific shift addition pattern
    m = re.search(r"plus\s+eine?\s+(mittel|frueh|spaet)schicht", norm)
    if m:
        result["preferred_shift_types"] = [m.group(1)]
        matched = True

    # Area preference: "fuer/in die Theke/Kueche/Service/Bar/Kiosk"
    m = re.search(r"(?:fuer|in)\s+(?:die\s+)?(theke|kueche|service|bar|kiosk)", norm)
    if m:
        result["preferred_working_areas"] = [m.group(1)]
        matched = True

    # Free-text passthrough: store original text as notes if nothing matched
    if not matched:
        result["notes"] = text.strip()

    return result


def load_directives(path: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    """Read directives.csv and return (raw_directives, merged_employee_rules).

    Parameters
    ----------
    path : Path
        Path to the directives.csv file.

    Returns
    -------
    raw_directives : list[dict]
        The raw CSV rows (id, text, employees, source) for audit/display.
    employee_rules : dict[str, dict]
        Merged rule dicts keyed by employee name.  When multiple directives
        reference the same employee, later directives override earlier ones
        for the same field.  Global directives (empty employees column) are
        stored under the key ``"_global"``.
    """
    raw: list[dict[str, str]] = []
    rules: dict[str, dict[str, Any]] = {}

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw.append(dict(row))
            parsed = parse_directive(row.get("text", ""))
            if not parsed:
                continue

            employees_str = row.get("employees", "").strip()
            if not employees_str:
                # Global directive -- store under _global
                existing = rules.setdefault("_global", {})
                existing.update(parsed)
            else:
                for name in pipe_split(employees_str):
                    existing = rules.setdefault(name, {})
                    existing.update(parsed)

    return raw, rules
