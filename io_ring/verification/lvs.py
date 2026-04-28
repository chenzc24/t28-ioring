"""LVS summary parsing and report generation."""

from pathlib import Path

from io_ring.config import resolve_output_root


def _resolve_summary_file(subdir: str, filename: str) -> Path:
    """Resolve summary file path (from original runtime_t28.py)."""
    preferred = resolve_output_root() / subdir / filename
    if preferred.exists():
        return preferred
    return preferred


def _parse_lvs_summary(file_path: str) -> str:
    """Parse LVS summary (from original runtime_t28.py)."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        overall_results = ""
        cell_summary = ""
        summary_section = ""
        in_overall = False
        in_cell = False
        in_summary = False

        for i, line in enumerate(lines):
            if "OVERALL COMPARISON RESULTS" in line:
                in_overall = True
                overall_results += line
                continue
            if in_overall:
                overall_results += line
                if "CELL  SUMMARY" in line or "LVS PARAMETERS" in line:
                    in_overall = False

            if "CELL  SUMMARY" in line:
                in_cell = True
                cell_summary += line
                continue
            if in_cell:
                cell_summary += line
                if "LVS PARAMETERS" in line or "SUMMARY" in line:
                    in_cell = False

            if "SUMMARY" in line and (i + 1 < len(lines) and "Total CPU Time" in lines[i + 1]):
                in_summary = True
                summary_section += line
                continue
            if in_summary:
                summary_section += line
                if "Total Elapsed Time" in line:
                    in_summary = False

        result = ["LVS check result summary:", "=" * 50, ""]
        if overall_results:
            result.extend(["Overall comparison results:", overall_results, ""])
        if cell_summary:
            result.extend(["Cell summary:", cell_summary, ""])
        if summary_section:
            result.extend(["Execution summary:", summary_section, ""])

        if not overall_results and not cell_summary and not summary_section:
            return "LVS original summary content (first 100 lines):\n" + "=" * 50 + "\n" + "".join(lines[:100])
        return "\n".join(result)
    except Exception as e:
        return f"Failed to parse LVS summary file: {e}"
