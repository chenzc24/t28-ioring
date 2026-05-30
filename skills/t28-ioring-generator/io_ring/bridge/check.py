"""Bridge environment loading and installation check."""

import os
from pathlib import Path

from dotenv import load_dotenv


def _find_project_root() -> str:
    """Walk up from the skill root to find the project root (directory with .venv or .git).

    Skips the skill root itself (identified by SKILL.md) to avoid stopping prematurely
    when the skill directory happens to be nested inside another project.
    """
    start = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidate = start
    for _ in range(20):  # safety limit
        # Skip the skill root itself (contains SKILL.md)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            parent = os.path.dirname(candidate)
            if parent != candidate:
                candidate = parent
                continue
        if os.path.isdir(os.path.join(candidate, ".venv")) or os.path.isdir(os.path.join(candidate, ".git")):
            return candidate
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    return start


def _load_skill_env() -> None:
    """Load .env from project root and skill root (deterministic, independent of cwd).

    Resolution order:
      1. Project root .env (if .venv or .git found above skill root)
      2. Skill root .env (fallback)
      3. cwd .env (dotenv default)

    Project root takes priority for shared config (VB_*, AMS_*).
    Skill root can override for skill-specific values.
    override=False means first-set-wins — project root values are not clobbered.
    """
    project_root = _find_project_root()
    project_env = os.path.join(project_root, ".env")
    if os.path.exists(project_env):
        load_dotenv(dotenv_path=project_env, override=False)

    skill_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    skill_env = os.path.join(skill_root, ".env")
    if os.path.exists(skill_env) and skill_env != project_env:
        load_dotenv(dotenv_path=skill_env, override=False)

    # Fallback: let dotenv search from cwd
    if not os.path.exists(project_env) and not os.path.exists(skill_env):
        load_dotenv(override=False)


_load_skill_env()


def _load_vb_env() -> None:
    """Pre-load virtuoso-bridge-lite connection config so VirtuosoClient.from_env()
    finds the expected variables regardless of cwd.

    Lookup priority (first match wins):
      1. $VB_ENV_FILE env var  — explicit path to a .env file
      2. Nearest .env containing VB_REMOTE_HOST / VB_LOCAL_PORT, searching cwd
         and its parents  — project-level config
      3. ~/.virtuoso-bridge/.env  — user-level fallback (virtuoso-bridge init)

    This matters because T28's own .env may live in cwd (when scripts are run
    from the skill root) — without this pre-load, a cwd .env without VB vars
    would shadow the real config.
    """
    # 1. Explicit override
    explicit = os.getenv("VB_ENV_FILE", "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            load_dotenv(dotenv_path=str(p), override=True)
            return

    # 2. Project-level: walk up from cwd looking for a .env with VB vars
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "VB_REMOTE_HOST" in text or "VB_LOCAL_PORT" in text:
                load_dotenv(dotenv_path=str(candidate), override=True)
                return

    # 3. User-level fallback
    user_env = Path.home() / ".virtuoso-bridge" / ".env"
    if user_env.is_file():
        load_dotenv(dotenv_path=str(user_env), override=True)


def check_bridge_installed() -> tuple[bool, str]:
    """Check whether virtuoso-bridge-lite is importable without calling it.

    Returns (True, version_string) on success, or (False, error_message).
    Use this for early validation in scripts before starting long operations.
    """
    try:
        import virtuoso_bridge
        ver = getattr(virtuoso_bridge, "__version__", "unknown")
        return True, ver
    except ImportError as e:
        return False, (
            "virtuoso-bridge is not installed in this Python environment.\n"
            "Install it into the T28 skill's .venv:\n"
            "  .venv/bin/pip install -e /path/to/virtuoso-bridge-lite\n"
            "See README.md > Installation > Step 2.\n"
            f"Original error: {e}"
        )


def _read_env_raw(key: str) -> str:
    """Read a variable directly from a .env file without going through os.environ.

    Git bash on Windows converts Unix paths like /home/... to Windows
    paths (C:\\Program Files\\Git\\home\\...) before Python sees them, which breaks
    remote Linux commands.  Parsing the .env file with dotenv_values() returns the
    raw string exactly as written.

    Search order:
      1. Walk up from cwd looking for a .env that has this key
      2. Skill root .env (relative to this file)
      3. ~/.virtuoso-bridge/.env
      4. os.environ as last resort (correct when not launched from Git Bash)
    """
    from dotenv import dotenv_values

    # 1. Walk up from cwd
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".env"
        if not candidate.is_file():
            continue
        try:
            vals = dotenv_values(str(candidate))
        except Exception:
            continue
        if key in vals:
            return (vals[key] or "").strip()

    # 2. Skill root .env (relative to this file's location)
    skill_root = Path(__file__).resolve().parent.parent.parent
    skill_env = skill_root / ".env"
    if skill_env.is_file():
        try:
            vals = dotenv_values(str(skill_env))
            if key in vals:
                return (vals[key] or "").strip()
        except Exception:
            pass

    # 3. User-level fallback
    home_env = Path.home() / ".virtuoso-bridge" / ".env"
    if home_env.is_file():
        try:
            vals = dotenv_values(str(home_env))
            if key in vals:
                return (vals[key] or "").strip()
        except Exception:
            pass

    # 4. os.environ fallback (correct when Python is invoked directly, not via Git Bash)
    env_val = os.environ.get(key, "").strip()
    return env_val
