#!/usr/bin/env python3
"""Validate the unified T28 IO Ring _local/site.yaml configuration."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.t28_site_config import apply_site_config
from tools.t28_site_config import site as site_mod


def main() -> int:
    path = site_mod.site_config_path(REPO_ROOT)
    errors = site_mod.validate_site_config(REPO_ROOT)
    if errors:
        print("[ERROR] T28 site configuration is not ready.")
        print(f"Config path: {path}")
        for err in errors:
            print(f"  - {err}")
        return 1

    apply_site_config(REPO_ROOT)
    print("[OK] T28 site configuration is ready.")
    print(f"Config path: {path}")
    for name in (
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
    ):
        value = site_mod.read_config_value(name, REPO_ROOT)
        redacted = "<set>" if ("LICENSE" in name or "LIC_FILE" in name) and value else value
        print(f"  {name}={redacted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
