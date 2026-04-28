"""VirtuosoClient wrapper functions for SKILL execution and cellView management."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .check import _load_vb_env


def _get_client():
    """Return a VirtuosoClient configured via virtuoso-bridge-lite's env.

    Raises ImportError with an actionable install hint if the package is missing.
    """
    try:
        from virtuoso_bridge import VirtuosoClient  # type: ignore
    except ImportError as e:
        raise ImportError(
            "virtuoso-bridge is not installed.\n"
            "Install it from the virtuoso-bridge-lite source directory:\n"
            "  pip install -e /path/to/virtuoso-bridge-lite\n"
            "See README.md > Prerequisites for full setup instructions.\n"
            f"Original error: {e}"
        )
    _load_vb_env()
    return VirtuosoClient.from_env()


def _get_ssh():
    """Return an SSHClient from virtuoso-bridge-lite for direct file transfer / shell.

    Used by execute_csh_script() to upload and run Calibre scripts on the EDA server
    without going through Virtuoso's SKILL csh() interpreter.
    """
    try:
        from virtuoso_bridge import SSHClient  # type: ignore
    except ImportError as e:
        raise ImportError(
            "virtuoso-bridge is not installed. See README.md > Prerequisites.\n"
            f"Original error: {e}"
        )
    _load_vb_env()
    return SSHClient.from_env()


def rb_exec(skill: str, timeout: int = 30) -> str:
    """Execute SKILL code via virtuoso-bridge-lite VirtuosoClient.

    Returns the SKILL result string (already clean — no control characters).
    Returns a human-readable error string if execution fails.
    """
    try:
        result = _get_client().execute_skill(skill, timeout=timeout)
        return result.output or ""
    except json.JSONDecodeError:
        raise
    except Exception as e:
        return f"Bridge execution error: {str(e)}"


def get_current_design() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (lib, cell, view) for the current edit cellView.

    Returns (None, None, None) if nothing is open or the bridge is unreachable.
    """
    try:
        skill_code = 'sprintf(nil "%s" ddGetObjReadPath(dbGetCellViewDdId(geGetEditCellView())))'
        ret = rb_exec(skill_code, timeout=30)
        if not ret:
            return None, None, None
        parts = ret.split('/')
        if len(parts) < 4:
            return None, None, None
        return parts[-4], parts[-3], parts[-2]
    except Exception:
        return None, None, None


# ===================== Helpers =====================
def _escape_path_for_skill(path: str) -> str:
    """Escape path for use inside a SKILL string literal."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _get_remote_bridge_dir() -> str:
    """Resolve the remote bridge work directory used by VirtuosoClient."""
    try:
        from virtuoso_bridge import VirtuosoClient  # type: ignore
        client = VirtuosoClient.from_env()
        tunnel = getattr(client, "_tunnel", None)
        if tunnel is not None:
            remote_dir = getattr(tunnel, "remote_work_dir", None)
            if remote_dir:
                return remote_dir
    except Exception:
        pass
    return "/tmp/virtuoso_bridge"


def _cleanup_remote_il_files() -> None:
    """Delete stale .il files from the remote bridge work directory.

    Prevents old scripts from being loaded when SSH uploads silently fail
    (e.g. Windows ControlMaster mux_client_request_session errors).
    Safe to call even when no SSH tunnel is active.
    """
    try:
        ssh = _get_ssh()
        remote_dir = _get_remote_bridge_dir()
        ssh.run_command(f"rm -f {remote_dir}/*.il")
    except Exception:
        pass


def _scp_upload(local_path: str, remote_path: str) -> bool:
    """Upload a file via scp with ControlMaster disabled.

    Fallback upload method when the VirtuosoClient daemon upload fails
    due to Windows ControlMaster mux_client_request_session errors.
    """
    try:
        ssh = _get_ssh()
        host = ssh.remote_host
        user = os.environ.get("VB_REMOTE_USER", "")
        if user:
            target = f"{user}@{host}:{remote_path}"
        else:
            target = f"{host}:{remote_path}"
        result = subprocess.run(
            ["scp", "-o", "ControlMaster=no", "-o", "BatchMode=yes",
             "-o", "StrictHostKeyChecking=no", str(local_path), target],
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False


def load_skill_file(file_path: str, timeout: int = 60) -> bool:
    """Upload the .il file to the remote server (if SSH tunnel active) and load it
    in Virtuoso CIW. Returns True on success.

    Three-phase approach for reliability on Windows:
    1. Upload via VirtuosoClient.load_il() (daemon handles SSH upload + load).
    2. If daemon upload fails, use scp (ControlMaster=no) as fallback upload,
       then load via direct execute_skill('load(...)').
    3. If scp also fails, try rb_exec('load(...)') as last resort using whatever
       file exists on the remote (previously uploaded or scp'd).

    Safety measures against stale remote files:
    - Fix B: Cleans up old .il files from the remote directory before uploading.
    - Fix A: Uses unique remote filenames (timestamp+UUID) so each task gets
      an isolated path.
    """
    # Fix B: Clean up stale .il files from previous tasks
    _cleanup_remote_il_files()

    # Upload the .il file directly — the generator already adds a timestamp
    # to the filename, so no need for a separate timestamped local copy.
    src = Path(file_path).resolve()

    remote_dir = _get_remote_bridge_dir()
    remote_file = f"{remote_dir}/{src.name}"

    try:
        # Phase 1: Try daemon upload + load
        client = _get_client()
        result = client.load_il(str(src), timeout=timeout)
        if getattr(result, "ok", False):
            return True
    except Exception:
        pass

    # Phase 2: Daemon upload failed — use scp fallback + direct load
    if _scp_upload(str(src), remote_file):
        try:
            client = _get_client()
            load_cmd = f'load("{remote_file}")'
            result2 = client.execute_skill(load_cmd, timeout=timeout)
            if getattr(result2, "ok", False):
                return True
        except Exception:
            pass

    # Phase 3: Last resort — try rb_exec which uses the VirtuosoClient
    # TCP socket directly (bypasses SSH upload entirely)
    try:
        client = _get_client()
        load_result = client.execute_skill(f'load("{remote_file}")', timeout=timeout)
        resp = getattr(load_result, "response", "") or str(load_result)
        if resp.strip().lower() == "t":
            return True
    except Exception:
        pass

    return False


def save_current_cellview(timeout: int = 30) -> bool:
    """Save the current edit cellView. Returns True on success."""
    ret = rb_exec('dbSave(cv)', timeout=timeout)
    cleaned = (ret or '').strip().lower()
    return cleaned == 't' or 'ok' in cleaned


def ui_redraw(timeout: int = 10) -> None:
    rb_exec('hiRedraw()', timeout=timeout)


def ui_zoom_absolute_scale(scale: float, timeout: int = 10) -> None:
    rb_exec(f'hiZoomAbsoluteScale(geGetEditCellViewWindow(cv) {scale})', timeout=timeout)


def _default_view_type_for(view: str) -> str:
    """Map logical view to viewType used by dbOpenCellViewByType.

    e.g. layout -> maskLayout, schematic -> schematic.
    """
    v = (view or "").strip().lower()
    if v.startswith("layout"):
        return "maskLayout"
    if v == "schematic":
        return "schematic"
    return view


def open_cell_view_by_type(
    lib: str,
    cell: str,
    view: str = "layout",
    view_type: Optional[str] = None,
    mode: str = "w",
    timeout: int = 30,
) -> bool:
    """Open a specific cellView in Virtuoso via dbOpenCellViewByType."""
    if not view_type:
        view_type = _default_view_type_for(view)
    lib_s = lib.replace('"', '\\"')
    cell_s = cell.replace('"', '\\"')
    view_s = view.replace('"', '\\"')
    vtype_s = (view_type or "").replace('"', '\\"')
    mode_s = (mode or "w").replace('"', '\\"')
    skill = f'cv = dbOpenCellViewByType("{lib_s}" "{cell_s}" "{view_s}" "{vtype_s}" "{mode_s}")'
    try:
        ret = rb_exec(skill, timeout=timeout)
        cleaned = (ret or "").strip().lower()
        return cleaned != "nil" and len(cleaned) > 0
    except Exception:
        return False


def ge_open_window(
    lib: str,
    cell: str,
    view: str = "layout",
    view_type: Optional[str] = None,
    mode: str = "a",
    timeout: int = 30,
) -> bool:
    """Open a window in Virtuoso using geOpen to display a cellView."""
    if not view_type:
        view_type = _default_view_type_for(view)
    lib_s = lib.replace('"', '\\"')
    cell_s = cell.replace('"', '\\"')
    view_s = view.replace('"', '\\"')
    vtype_s = (view_type or "").replace('"', '\\"')
    mode_s = (mode or "a").replace('"', '\\"')
    skill = (
        f'window = geOpen(?lib "{lib_s}" ?cell "{cell_s}" ?view "{view_s}" '
        f'?viewType "{vtype_s}" ?mode "{mode_s}")'
    )
    try:
        ret = rb_exec(skill, timeout=timeout)
        cleaned = (ret or "").strip().lower()
        return cleaned != "nil" and len(cleaned) > 0
    except Exception:
        return False


def open_cell_view(
    lib: str,
    cell: str,
    view: str = "layout",
    timeout: int = 30,
) -> bool:
    """Open a specific cellView in Virtuoso via dbOpenCellView."""
    lib_s = lib.replace('"', '\\"')
    cell_s = cell.replace('"', '\\"')
    view_s = view.replace('"', '\\"')
    skill = f'cv = dbOpenCellView("{lib_s}" "{cell_s}" "{view_s}")'
    try:
        ret = rb_exec(skill, timeout=timeout)
        cleaned = (ret or "").strip().lower()
        return cleaned != "nil" and len(cleaned) > 0
    except Exception:
        return False
