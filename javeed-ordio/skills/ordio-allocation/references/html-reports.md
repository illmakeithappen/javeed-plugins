# HTML Report Artifacts

Two report types can be generated as standalone HTML files from plan and snapshot data. Each is a single self-contained HTML file (no external dependencies except Tailwind CDN) that can be opened in a browser.

## Report Types

### 1. Wochenplan-Freigabe (Weekly Plan Approval)

**Purpose**: Betriebsleiter reviews a generated plan, accepts/declines individual assignments.

**Template**: `${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/examples/wochenplan-freigabe.html`

**Data structure**: Embedded as `<script id="plan-data" type="application/json">` in the HTML.

Required fields:
```json
{
  "plan_id": "plan-...",
  "snapshot_id": "...",
  "betrieb": "Hin&Weg",
  "profile": "hinweg_march_2026",
  "range": { "from": "2026-02-23", "to": "2026-03-01" },
  "kpis": {
    "assigned_slots": 7,
    "unassigned_slots": 0,
    "fill_rate": 100,
    "assignment_kinds": { "applicant": 2, "recommendation_without_applicant": 5 }
  },
  "assignments": [
    {
      "assignment_id": "...",
      "date": "2026-02-23", "start": "10:00", "end": "13:00",
      "shift_type": "frueh", "working_area": "Kiosk",
      "employee": "Name", "is_applicant": true,
      "reasons": ["applied_for_shift", "remaining_target_hours"],
      "score_detail": { "rest": 24, "fairness": 18, "role": 10, "skill": 12, "fixed": 0, "preference": 0, "applicant": 80, "salary": 0 },
      "alternatives": [
        { "employee_name": "Alt Name", "score": 92, "is_applicant": false, "reasons": [...], "score_detail": {...} }
      ]
    }
  ]
}
```

**Key features**:
- Color-coded rows: green = applicant assigned, white = recommendation
- Expandable alternatives for each assignment
- Accept/decline buttons per row (interactive, state saved in DOM)
- Print-friendly layout
- Score breakdown visible on expand

### 2. Monatsuebersicht (Monthly Overview)

**Template**: `${CLAUDE_PLUGIN_ROOT}/skills/ordio-allocation/references/examples/monatsuebersicht.html`

**Data structure**: Embedded as `<script id="month-data" type="application/json">` in the HTML.

Required fields:
```json
{
  "snapshot_id": "...",
  "betrieb": "Hin&Weg",
  "month": "Maerz 2026",
  "range": { "from": "2026-03-01", "to": "2026-03-31" },
  "kpis": {
    "employees": 27,
    "active_employees": 14,
    "assigned_shifts": 83,
    "open_slots": 19,
    "applications": 95,
    "coverage_rate": 81.4
  },
  "open_by_day": [
    { "date": "2026-03-01", "open": 1, "applicants": 0 }
  ],
  "shift_types": { "frueh": { "assigned": 64, "open": 14 }, "spaet": { "assigned": 19, "open": 5 } },
  "employees": [
    {
      "name": "Name", "type": "Stud. Aushilfe", "type_key": "werki",
      "wage": 15, "max_salary": 1200, "cap_hours": 80,
      "hours": 84, "shifts": 13, "apps": 0, "absences": 1,
      "absence_note": "07.03.--15.03. Unbezahlter Urlaub",
      "skills": ["Kiosk", "Produktion / Backen"],
      "shift_dates": ["2026-03-02", "2026-03-04"]
    }
  ]
}
```

**Key features**:
- KPI dashboard (employees, shifts, coverage rate)
- Open shifts by day chart (bar chart with applicant overlay)
- Shift type breakdown (frueh vs spaet)
- Per-employee table: hours, shifts, salary utilization, absence notes
- Sortable columns
- Salary limit warnings (color-coded)

## How to Generate Reports

1. Read the template HTML file
2. Extract the data from MCP tool responses (`generate_plan`, `load_snapshot`, `evaluate_plan`)
3. Transform the data into the required JSON structure
4. Replace the `<script id="...-data">` block with the new JSON
5. Write the resulting HTML to a local file
6. Open with `open <path>` for the user

## Styling

Both templates use:
- Tailwind CSS (CDN in freigabe, inlined in monatsuebersicht)
- System font stack
- Print-friendly `@media print` rules
- Responsive layout (works on mobile)
- German labels throughout
