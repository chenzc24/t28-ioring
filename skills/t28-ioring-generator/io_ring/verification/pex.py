"""PEX capacitance extraction and report generation."""

from pathlib import Path


def parse_pex_capacitance(netlist_file: Path) -> str:
    """
    Directly extract all content between mgc_rve_cell_start and mgc_rve_cell_end in PEX netlist file, output as-is.
    """
    if not netlist_file.exists():
        return "PEX netlist file not found, unable to extract content."
    try:
        with open(netlist_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        in_cell = False
        cell_content = []
        for line in lines:
            if line.startswith('mgc_rve_cell_start'):
                in_cell = True
                cell_content.append(line)
                continue
            if line.startswith('mgc_rve_cell_end'):
                cell_content.append(line)
                in_cell = False
                break  # Only extract the first cell block
            if in_cell:
                cell_content.append(line)
        if not cell_content:
            return "No content found between mgc_rve_cell_start and mgc_rve_cell_end in PEX netlist."
        return "\nPEX main cell original content excerpt:\n" + ''.join(cell_content)
    except Exception as e:
        return f"Failed to extract PEX netlist content: {e}"
