"""Site configuration for SIM-IO — loads from .env and env vars.

Loading order (highest priority first):
  1. SIM_* environment variables (if already set in the shell)
  2. t28-ioring-simulator/.env.local file (via dotenv)
  3. t28-ioring-simulator/.env file (via dotenv)
  3. SKILL auto-discovery for license vars (fallback, done in sim_run.py)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).resolve().parent
_SIM_IO = _PKG_DIR.parent


def _load_sim_env() -> None:
    """Load simulator .env files into os.environ without overriding existing vars."""
    for env_file in (_SIM_IO / ".env.local", _SIM_IO / ".env"):
        if not env_file.is_file():
            continue
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)


def _discover_mmsim_root() -> str:
    """Auto-discover MMSIM_ROOT by looking for spectre in Virtuoso's PATH.

    Uses SKILL to get the PATH from the running Virtuoso session, then
    searches for 'spectre' in the PATH entries to derive the MMSIM root.

    Returns the MMSIM root path, or empty string if not found.
    """
    try:
        from virtuoso_bridge import VirtuosoClient
        from sim_io.bridge.skill_call import skill_exec

        client = VirtuosoClient.from_env()
        path_result = skill_exec(client, 'getShellEnvVar("PATH")', timeout=10,
                                 context="mmsim_discovery_get_path", fail_ok=True)
        path_val = path_result.output.strip('"')
        if not path_val or path_val.lower() == "nil":
            return ""

        # Search PATH entries for spectre binary
        for entry in path_val.split(":"):
            entry = entry.strip()
            if not entry:
                continue
            # Typical MMSIM install: /path/to/MMSIM221/tools/bin/spectre
            # The MMSIM_ROOT is /path/to/MMSIM221
            if entry.endswith("/tools/bin") or entry.endswith("/tools/bin/64bit"):
                spectre_result = skill_exec(
                    client, f'isFile("{entry}/spectre")', timeout=10,
                    context="mmsim_discovery_check_spectre", fail_ok=True,
                )
                if spectre_result.output and "t" in spectre_result.output.lower():
                    mmsim_root = entry
                    if mmsim_root.endswith("/64bit"):
                        mmsim_root = mmsim_root[: mmsim_root.rfind("/64bit")]
                    if mmsim_root.endswith("/tools/bin"):
                        mmsim_root = mmsim_root[: mmsim_root.rfind("/tools/bin")]
                    logger.info("[site_config] Auto-discovered MMSIM_ROOT: %s", mmsim_root)
                    return mmsim_root
        return ""
    except Exception as e:
        logger.warning("[site_config] MMSIM auto-discovery failed: %s", e)
        return ""


@dataclass
class SiteConfig:
    """Site-specific configuration for netlist export and simulation.

    Populated from SIM_* env vars (shell > .env).  License vars fall back
    to SKILL auto-discovery in sim_run.py when left empty here.
    """

    cds_lib: str
    ic_root: str
    pdk_spectre_include: str
    pdk_io_spectre_include: str = ""
    lm_license_file: str = ""
    cds_lic_file: str = ""
    mmsim_root: str = ""

    @property
    def si_bin(self) -> str:
        return f"{self.ic_root}/tools/dfII/bin/si"

    @property
    def spectre_bin_path(self) -> str:
        """Full path to the spectre binary.

        Priority:
          1. mmsim_root/tools/bin/spectre  (if mmsim_root is set)
          2. ic_root/tools/bin/spectre     (fallback — some IC installs bundle spectre)
          3. Empty string                   (no known path)
        """
        if self.mmsim_root:
            return f"{self.mmsim_root}/tools/bin/spectre"
        # Fallback: some IC installs include spectre under IC_ROOT
        if self.ic_root:
            return f"{self.ic_root}/tools/bin/spectre"
        return ""

    @classmethod
    def from_env(cls) -> "SiteConfig":
        """Create SiteConfig from SIM_* env vars (.env loaded automatically).

        MMSIM_ROOT resolution:
          1. SIM_MMSIM_ROOT env var (explicit)
          2. Auto-discovery from Virtuoso's PATH via SKILL (if client available)
        """
        _load_sim_env()

        cds_lib = os.getenv("SIM_CDS_LIB", "") or os.getenv("CDS_LIB_PATH_28", "")
        ic_root = os.getenv("SIM_IC_ROOT", "")

        if not cds_lib:
            raise ValueError(
                "SIM_CDS_LIB not set. Add it to t28-ioring-simulator/.env, "
                "or set CDS_LIB_PATH_28 as a fallback."
            )
        if not ic_root:
            raise ValueError(
                "SIM_IC_ROOT not set. Add it to t28-ioring-simulator/.env or set the env var."
            )

        mmsim_root = os.getenv("SIM_MMSIM_ROOT", "")

        # Auto-discover MMSIM_ROOT from Virtuoso's PATH if not set
        if not mmsim_root:
            mmsim_root = _discover_mmsim_root()

        return cls(
            cds_lib=cds_lib,
            ic_root=ic_root,
            pdk_spectre_include=os.getenv("SIM_PDK_SPECTRE_INCLUDE", ""),
            pdk_io_spectre_include=os.getenv("SIM_PDK_IO_SPECTRE_INCLUDE", ""),
            lm_license_file=os.getenv("SIM_LM_LICENSE_FILE", ""),
            cds_lic_file=os.getenv("SIM_CDS_LIC_FILE", ""),
            mmsim_root=mmsim_root,
        )
