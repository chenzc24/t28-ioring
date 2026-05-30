"""DRC summary parsing and report generation."""

from pathlib import Path

from io_ring.config import resolve_output_root


def _resolve_summary_file(subdir: str, filename: str) -> Path:
    """Resolve summary file path (from original runtime_t28.py)."""
    preferred = resolve_output_root() / subdir / filename
    if preferred.exists():
        return preferred
    return preferred


def _parse_drc_summary(file_path: str) -> str:
    """Parse DRC summary (from original runtime_t28.py)."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        start_idx = None
        for i, line in enumerate(lines):
            if "RULECHECK RESULTS STATISTICS (BY CELL)" in line:
                start_idx = i
                break
        if start_idx is None:
            return "DRC statistics section (BY CELL) not found."
        return "\nDRC original statistics content excerpt:\n" + "".join(lines[start_idx:])
    except Exception as e:
        return f"Failed to extract DRC statistics content: {e}"
