"""Shared allocation core logic for backend and MCP allocators."""

from .allocator import explain_assignment, generate_plan
from .preferences import evaluate_shift_preferences, parse_simple_shift_preferences
from .roles import compute_role_match_score
from .time_utils import calc_shift_hours, parse_hhmm_to_minutes, shift_labels, time_overlap

# io module — lazy re-exports (avoids importing sqlite3/openpyxl at import time)
from .io import extract_from_db, extract_from_snapshot, load_input, write_output

__all__ = [
    "calc_shift_hours",
    "compute_role_match_score",
    "evaluate_shift_preferences",
    "explain_assignment",
    "extract_from_db",
    "extract_from_snapshot",
    "generate_plan",
    "load_input",
    "parse_hhmm_to_minutes",
    "parse_simple_shift_preferences",
    "shift_labels",
    "time_overlap",
    "write_output",
]
