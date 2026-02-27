"""Input/output layer for the eval pipeline.

Public API:
    load_input(directory)       -- read CSV input dir -> (snapshot, profile, meta)
    write_output(plan, dir)     -- write enriched metrics.json to output dir
    extract_from_snapshot(...)  -- plugin snapshot dict -> CSV input files
    extract_from_db(...)        -- backend SQLite -> CSV input files
    render_xlsx(plan, path)     -- generate multi-sheet plan.xlsx workbook
"""

from .directives import load_directives, parse_directive, parse_vorgaben_llm
from .reader import load_input
from .writer import write_output

__all__ = [
    "load_directives",
    "load_input",
    "parse_directive",
    "parse_vorgaben_llm",
    "write_output",
]

# Lazy imports for optional heavy dependencies (sqlite3, openpyxl).
def extract_from_snapshot(*args, **kwargs):
    from .extractors import extract_from_snapshot as _fn
    return _fn(*args, **kwargs)

def extract_from_db(*args, **kwargs):
    from .extractors import extract_from_db as _fn
    return _fn(*args, **kwargs)

def render_xlsx(*args, **kwargs):
    from .xlsx import render_xlsx as _fn
    return _fn(*args, **kwargs)

def render_input_xlsx(*args, **kwargs):
    from .xlsx import render_input_xlsx as _fn
    return _fn(*args, **kwargs)

def persist_to_db(*args, **kwargs):
    from .db_loader import persist_to_db as _fn
    return _fn(*args, **kwargs)
