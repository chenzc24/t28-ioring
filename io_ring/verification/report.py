"""Shared report writing utility for DRC/LVS/PEX."""


def _write_report(title: str, content: str, output_file: str) -> tuple[bool, str]:
    """Write report file (from original runtime_t28.py)."""
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"{title}\n")
            f.write("=" * 50 + "\n\n")
            f.write(content)
        return True, f"Report generated: {output_file}"
    except Exception as e:
        return False, f"Error generating report: {e}"
