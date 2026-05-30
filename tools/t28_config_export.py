#!/usr/bin/env python3
"""Export _local/site.yaml values as shell environment assignments."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.t28_site_config import apply_site_config, read_config_value


EXPORT_NAMES = (
    "AMS_OUTPUT_ROOT",
    "AMS_DRAFT_EDITOR",
    "AMS_LAYOUT_EDITOR",
    "VB_FS_MODE",
    "VB_DISABLE_CONTROL_MASTER",
    "CDS_LIB_PATH_28",
    "SIM_CDS_LIB",
    "SIM_IC_ROOT",
    "SIM_MMSIM_ROOT",
    "MGC_HOME",
    "PDK_LAYERMAP_28",
    "incFILE_28",
    "SIM_PDK_IO_SPECTRE_INCLUDE",
    "SIM_PDK_CORE_SPECTRE_INCLUDE",
    "SIM_PDK_CORE_SPECTRE_SECTIONS",
    "SIM_LM_LICENSE_FILE",
    "SIM_CDS_LIC_FILE",
    "LM_LICENSE_FILE",
    "CDS_LIC_FILE",
)


def _quote_powershell(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell", choices=("sh", "powershell"), default="sh")
    args = parser.parse_args()

    apply_site_config(REPO_ROOT, override=False, required=True)
    for name in EXPORT_NAMES:
        value = read_config_value(name, REPO_ROOT)
        if not value:
            continue
        if args.shell == "powershell":
            print(f"$env:{name}={_quote_powershell(value)}")
        else:
            print(f"export {name}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
