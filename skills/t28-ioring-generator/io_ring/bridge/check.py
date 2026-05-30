"""Bridge environment loading and installation check."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _find_project_root() -> str:
    """Walk up from the skill root to find the repository root."""
    start = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidate = start
    for _ in range(20):
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            parent = os.path.dirname(candidate)
            if parent != candidate:
                candidate = parent
                continue
        if (
            os.path.isdir(os.path.join(candidate, ".git"))
            or os.path.isdir(os.path.join(candidate, "_local"))
            or os.path.isdir(os.path.join(candidate, "skills"))
        ):
            return candidate
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    return start


def _add_project_root_to_path(project_root: str) -> None:
    if project_root and project_root not in sys.path:
        sys.path.insert(0, project_root)


def _load_unified_site_config(project_root: str | None = None, *, required: bool = False) -> None:
    """Load repo-root ``_local/site.yaml``."""
    root = project_root or _find_project_root()
    _add_project_root_to_path(root)
    try:
        from tools.t28_site_config import apply_site_config
    except Exception:
        if required:
            raise
        return
    try:
        apply_site_config(root, override=False, required=required)
    except Exception as exc:
        raise RuntimeError(f"Failed to load _local/site.yaml: {exc}") from exc


def _load_skill_env() -> None:
    """Load only the repository-local T28 site config."""
    _load_unified_site_config(_find_project_root(), required=False)


_load_skill_env()


def _load_vb_env() -> None:
    """Load the official virtuoso-bridge connection config.

    T28 site configuration is not read from ``.env`` files. Bridge connection
    variables come from either ``VB_ENV_FILE`` or ``~/.virtuoso-bridge/.env``,
    which is created by ``virtuoso-bridge init``.
    """
    explicit = os.getenv("VB_ENV_FILE", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            load_dotenv(dotenv_path=str(path), override=True)
            return

    user_env = Path.home() / ".virtuoso-bridge" / ".env"
    if user_env.is_file():
        load_dotenv(dotenv_path=str(user_env), override=True)


def check_bridge_installed() -> tuple[bool, str]:
    """Check whether virtuoso-bridge-lite is importable without calling it."""
    try:
        import virtuoso_bridge

        ver = getattr(virtuoso_bridge, "__version__", "unknown")
        return True, ver
    except ImportError as exc:
        return False, (
            "virtuoso-bridge is not installed in this Python environment.\n"
            "Install it into the shared project .venv:\n"
            "  pip install -e /path/to/virtuoso-bridge-lite\n"
            "See README.md > Quick Setup.\n"
            f"Original error: {exc}"
        )


def _read_env_raw(key: str) -> str:
    """Read a config value without shell path conversion.

    Remote Linux paths such as ``/home/...`` must come from ``_local/site.yaml``
    or explicit process environment variables, not skill-local ``.env`` files.
    """
    project_root = _find_project_root()
    _add_project_root_to_path(project_root)
    try:
        from tools.t28_site_config import read_config_value

        value = read_config_value(key, project_root)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(key, "").strip()
