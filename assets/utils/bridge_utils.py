from __future__ import annotations

from typing import Optional, Tuple
import os
import json
import shlex
from pathlib import Path

from dotenv import load_dotenv


def _load_skill_env() -> None:
    """Load .env from skill root (deterministic, independent of cwd)."""
    skill_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_file = os.path.join(skill_root, ".env")
    if os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file, override=False)
    else:
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


def load_skill_file(file_path: str, timeout: int = 60) -> bool:
    """Upload the .il file to the remote server (if SSH tunnel active) and load it
    in Virtuoso CIW. Returns True on success.

    Uses VirtuosoClient.load_il(), which handles the SSH upload automatically when a
    tunnel is active, then executes load("/remote/path") in Virtuoso.
    """
    try:
        result = _get_client().load_il(file_path, timeout=timeout)
        return bool(getattr(result, "ok", False))
    except Exception:
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


def _download_via_cat(ssh, remote_path: str, local_path: Path, timeout: int = 60) -> Optional[str]:
    """Download a binary file using 'base64 remote_path' over ssh.run_command().

    Uses the reliable echo-base64-pipe channel instead of scp, which times out
    on Windows when multiple connections are opened in quick succession.
    Returns None on success, or an error string.
    """
    import base64
    try:
        r = ssh.run_command(f"base64 {shlex.quote(remote_path)}", timeout=timeout)
        rc = getattr(r, "returncode", 1)
        if rc != 0:
            return f"base64 cat failed (rc={rc}): {(getattr(r,'stderr','') or '').strip()}"
        b64_data = (getattr(r, "stdout", "") or "").strip()
        if not b64_data:
            return f"no data returned for {remote_path}"
        raw = base64.b64decode(b64_data)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(raw)
        return None
    except Exception as e:
        return f"download_via_cat failed: {e}"


def load_script_and_take_screenshot_verbose(
    screenshot_script_path: str, save_path: str, timeout: int = 20
) -> tuple[bool, str]:
    """Upload screenshot.il to the remote server, load it in Virtuoso, take the
    screenshot, then download the PNG back to save_path (remote mode) or verify
    it exists in-place (shared-FS mode).

    Returns (success, error_message).
    """
    local_save = Path(save_path).expanduser().resolve(strict=False)

    # Detect remote mode from the save path itself (most reliable) or env override.
    # A Windows-style absolute path can never be written to by a remote Linux process.
    fs_mode_override = os.environ.get("VB_FS_MODE", "").strip().lower()
    if fs_mode_override in ("shared", "remote"):
        remote_mode = fs_mode_override == "remote"
    else:
        remote_mode = _is_windows_path(str(local_save))

    if remote_mode:
        remote_png = f"/tmp/vb_t28_calibre/screenshot_{local_save.name}"
    else:
        remote_png = str(local_save).replace("\\", "/")

    out = _escape_path_for_skill(remote_png)
    try:
        client = _get_client()
    except Exception as e:
        return False, f"bridge init failed: {e}"

    try:
        load_result = client.load_il(screenshot_script_path, timeout=timeout)
    except Exception as e:
        return False, f"load failed: {e}"

    if not getattr(load_result, "ok", False):
        errs = getattr(load_result, "errors", None) or []
        return False, f"load failed: {'; '.join(errs) or 'unknown error'}"

    take_ret = rb_exec(f'takeScreenshot("{out}")', timeout=timeout)
    if take_ret and ("error" in take_ret.lower() or "undefined function" in take_ret.lower()):
        return False, f"takeScreenshot failed: {take_ret}"

    if remote_mode:
        # Download via base64-over-ssh (avoids scp which times out on Windows).
        try:
            ssh = _get_ssh()
            err = _download_via_cat(ssh, remote_png, local_save, timeout=60)
            if err:
                return False, f"screenshot download failed: {err}"
        except Exception as e:
            return False, f"screenshot download failed: {e}"

    if not local_save.exists():
        return False, "screenshot file not created"
    return True, ""


def load_script_and_take_screenshot(screenshot_script_path: str, save_path: str, timeout: int = 20) -> bool:
    """Backward-compatible wrapper returning only the success flag."""
    ok, _ = load_script_and_take_screenshot_verbose(screenshot_script_path, save_path, timeout=timeout)
    return ok


# ===================== Calibre csh execution =====================
_CALIBRE_REMOTE_BASE = "/tmp/vb_t28_calibre"


def _upload_calibre_tree(ssh, calibre_dir: Path, remote_base: str, timeout: int = 60) -> Optional[str]:
    """Upload every file under calibre_dir to remote_base, preserving structure.

    Returns None on success, or an error string on failure.
    """
    import tempfile

    # Collect all files, strip CRLF from shell/SKILL scripts, pack into ONE tar
    # to avoid multiple SSH connections (each new connection takes 5-30s on Windows).
    import tarfile, io
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in calibre_dir.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(calibre_dir).as_posix()
            content = f.read_bytes()
            if f.suffix in (".csh", ".sh", ".il", ".skill") and b"\r\n" in content:
                content = content.replace(b"\r\n", b"\n")
            info = tarfile.TarInfo(name=rel)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

    buf.seek(0)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
        tmp.write(buf.read())
        tmp_path = Path(tmp.name)

    try:
        remote_cmd = f"mkdir -p {shlex.quote(remote_base)} && tar xzf - -C {shlex.quote(remote_base)}"
        # Upload via a single ssh.upload_file to the remote untar command
        up = ssh.upload_file(tmp_path, f"{remote_base}/_upload.tar.gz", timeout=timeout)
        if getattr(up, "returncode", 1) != 0:
            err = (getattr(up, "stderr", "") or "").strip()
            tmp_path.unlink(missing_ok=True)
            return f"tarball upload failed: {err}"
        # Unpack on remote
        unpack = ssh.run_command(
            f"mkdir -p {shlex.quote(remote_base)} && tar xzf {shlex.quote(remote_base+'/_upload.tar.gz')} -C {shlex.quote(remote_base)}",
            timeout=30,
        )
        if getattr(unpack, "returncode", 1) != 0:
            tmp_path.unlink(missing_ok=True)
            return f"remote unpack failed: {(getattr(unpack,'stderr','') or '').strip()}"
    finally:
        tmp_path.unlink(missing_ok=True)

    return None


def _run_local_csh(script_path: str, args, timeout: int) -> str:
    """Local subprocess fallback used only when SSH execution fails entirely."""
    try:
        import subprocess
        abs_script_path = os.path.abspath(script_path)
        cmd = ["/bin/csh", abs_script_path] + [str(arg) for arg in args]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8:replace"
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = process.communicate(timeout=timeout)
        if process.returncode == 0:
            return stdout or "t"
        return f"Local csh execution failed: {stderr or stdout}"
    except Exception as e:
        return f"Local csh execution failed: {e}"


def _is_windows_path(p: str) -> bool:
    """Detect `C:\\...`-style absolute Windows paths."""
    return bool(p) and len(p) >= 2 and p[1] == ":" and p[0].isalpha()


def _detect_fs_mode(ssh, local_ams_root: str) -> str:
    """Return 'shared' or 'remote'.

    Override with VB_FS_MODE=shared|remote. Otherwise auto-detect:
      - Windows-style local path → remote (Linux Calibre can't see `C:\\...`)
      - Probe remote for `test -d <local_ams_root>`; shared if it exists,
        remote otherwise.
    """
    forced = os.environ.get("VB_FS_MODE", "").strip().lower()
    if forced in ("shared", "remote"):
        return forced
    if _is_windows_path(local_ams_root):
        return "remote"
    if ssh is None or not local_ams_root:
        return "shared"
    try:
        result = ssh.run_command(
            f"test -d {shlex.quote(local_ams_root)} && echo VB_SHARED_YES || echo VB_SHARED_NO",
            timeout=10,
        )
        out = (getattr(result, "stdout", "") or "").strip()
        return "shared" if "VB_SHARED_YES" in out else "remote"
    except Exception:
        return "remote"


def _download_calibre_output(ssh, remote_root: str, local_root: str, timeout: int = 180) -> Optional[str]:
    """Pull `drc/` and `lvs/` subtrees and top-level `*_report*` files from
    `remote_root` back to `local_root`. Returns None on success, or an error
    string. Missing remote subdirs are silently skipped.
    """
    try:
        listing = ssh.run_command(
            f"ls -d {shlex.quote(remote_root)}/drc {shlex.quote(remote_root)}/lvs 2>/dev/null",
            timeout=60,
        )
        present = [
            line.strip()
            for line in (getattr(listing, "stdout", "") or "").splitlines()
            if line.strip()
        ]
    except Exception as e:
        return f"list failed: {e}"

    local_root_p = Path(local_root).expanduser().resolve(strict=False)
    local_root_p.mkdir(parents=True, exist_ok=True)

    for remote_dir in present:
        name = remote_dir.rsplit("/", 1)[-1]
        local_target = local_root_p / name
        local_target.mkdir(parents=True, exist_ok=True)
        try:
            res = ssh.download_file(remote_dir, local_target, timeout=timeout, recursive=True)
            rc = getattr(res, "returncode", 1)
            if rc != 0:
                err = (getattr(res, "stderr", "") or "").strip()
                return f"download {remote_dir} failed (rc={rc}): {err}"
        except Exception as e:
            return f"download {remote_dir} failed: {e}"
    return None


def _read_env_raw(key: str) -> str:
    """Read a variable directly from the project .env file without going through
    os.environ.  Git bash on Windows converts Unix paths like /home/... to Windows
    paths (C:\\Program Files\\Git\\home\\...) before Python sees them, which breaks
    remote Linux commands.  Parsing the .env file with dotenv_values() returns the
    raw string exactly as written.
    """
    # Walk up from cwd looking for a .env that has this key
    from dotenv import dotenv_values
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
    # Fallback: try home .virtuoso-bridge/.env
    home_env = Path.home() / ".virtuoso-bridge" / ".env"
    if home_env.is_file():
        try:
            vals = dotenv_values(str(home_env))
            if key in vals:
                return (vals[key] or "").strip()
        except Exception:
            pass
    return ""


def _skill_strip_crlf_remote(filenames: list[str], base: str = _CALIBRE_REMOTE_BASE) -> None:
    """Use SKILL system() to strip CRLF from already-uploaded scripts on the remote.
    This is the reliable fallback when the tar upload path couldn't strip CRLF.
    """
    for fname in filenames:
        path = f"{base}/{fname}"
        # tr -d '\r' is unambiguous across all sed/tr versions; sed \r can fail
        # depending on locale.  Rewrite to tmp then move back atomically.
        rb_exec(
            f'system("tr -d \'\\\\r\' < {path} > {path}.lf && mv {path}.lf {path} 2>/dev/null")',
            timeout=10,
        )


def _run_calibre_async(
    remote_script: str,
    env_prefix: str,
    args_str: str,
    remote_ams_root: str,
    log_file: str,
    done_file: str,
    poll_secs: float = 5.0,
    timeout: int = 600,
) -> tuple[int, str]:
    """Run a Calibre csh script via SKILL system() in the background.

    Because system() is synchronous and blocks the Virtuoso SKILL interpreter
    (causing the RAMIC IPC daemon to drop), we run the csh with '&' so the
    shell returns immediately, then poll via short system("test -f DONE") calls.

    The csh wrapper writes the exit code to done_file when it finishes.
    Returns (rc, message).
    """
    import time
    import re as _re

    # Sanitize paths for shell embedding — no quotes or special chars
    for p in (remote_script, log_file, done_file):
        if _re.search(r"[\s;|&$]", p):
            return 1, f"unsafe path for async execution: {p!r}"

    # Remove stale done_file if it exists
    rb_exec(f'system("rm -f {done_file}")', timeout=10)

    # Launch async: subshell runs csh + captures exit code, then writes done_file
    async_cmd = (
        f"sh -c '{env_prefix} csh {remote_script} {args_str} "
        f"> {log_file} 2>&1; echo $? > {done_file}' &"
    )
    launch_rc = rb_exec(f'system("{async_cmd}")', timeout=15)
    print(f"[calibre_async] launched (system rc={launch_rc!r}), polling every {poll_secs}s ...")

    # Poll until done_file appears
    elapsed = 0.0
    while elapsed < timeout:
        time.sleep(poll_secs)
        elapsed += poll_secs
        done_check = rb_exec(f'system("test -f {done_file}")', timeout=10)
        if done_check == "0":
            break
        if int(elapsed) % 30 == 0:
            print(f"[calibre_async] still running ... ({int(elapsed)}s)")
    else:
        return 1, f"timeout after {timeout}s"

    # Read the exit code from done_file (content is "0\n" or "1\n" etc.)
    pass_check = rb_exec(f'system("grep -qx 0 {done_file}")', timeout=10)
    rc = 0 if pass_check == "0" else 1

    # Download output subtrees from remote_ams_root to local AMS_OUTPUT_ROOT
    local_ams = os.environ.get("AMS_OUTPUT_ROOT", "").strip()
    if local_ams:
        try:
            ssh = _get_ssh()
            err = _download_calibre_output(ssh, remote_ams_root, local_ams, timeout=180)
            if err:
                print(f"[calibre_async] warn: {err}")
        except Exception as e:
            print(f"[calibre_async] warn: download failed: {e}")

    return rc, log_file


def execute_csh_script(script_path: str, *args, timeout: int = 300) -> str:
    """Upload the calibre csh script tree and run it on the EDA server.

    Execution path (tried in order):
      1. SKILL async (preferred): launches csh in background via SKILL system() &,
         polls for completion — keeps the Virtuoso IPC alive throughout.
      2. SSH direct (fallback): runs synchronously via ssh.run_command.
      3. Local csh (last resort): runs on the Windows machine (rarely works).

    Two filesystem modes for the output directory:
      - shared: Calibre writes to AMS_OUTPUT_ROOT directly (NFS mount).
      - remote: Calibre writes to /tmp/... ; results are downloaded afterward.
    """
    import re as _re

    script = Path(script_path).resolve()
    if not script.exists():
        return f"Script not found: {script}"

    calibre_dir = script.parent

    try:
        ssh = _get_ssh()
    except Exception as e:
        print(f"[execute_csh_script] SSH unavailable, falling back to local: {e}")
        return _run_local_csh(script_path, args, timeout)

    # ── Upload all calibre scripts as a single tarball (Fix D) ────────────────
    upload_err = _upload_calibre_tree(ssh, calibre_dir, _CALIBRE_REMOTE_BASE, timeout=60)
    if upload_err:
        local = _run_local_csh(script_path, args, timeout)
        if not str(local).startswith("Local csh execution failed"):
            return local
        return f"Remote upload failed: {upload_err}; fallback local: {local}"

    # Strip any residual CRLF via SKILL (belt-and-suspenders) using stable TCP
    _skill_strip_crlf_remote([script.name, "env_common.csh"])

    remote_script = f"{_CALIBRE_REMOTE_BASE}/{script.relative_to(calibre_dir).as_posix()}"
    args_str = " ".join(shlex.quote(str(a)) for a in args)
    local_ams_root = os.environ.get("AMS_OUTPUT_ROOT", "").strip()

    mode = _detect_fs_mode(ssh, local_ams_root)
    cell_tag = _re.sub(r"[^A-Za-z0-9_.-]", "_", str(args[1]) if len(args) >= 2 else "run") or "run"
    if mode == "remote":
        remote_ams_root = f"{_CALIBRE_REMOTE_BASE}/output_{cell_tag}"
        rb_exec(f'system("mkdir -p {remote_ams_root}/drc {remote_ams_root}/lvs")', timeout=10)
        print(f"[execute_csh_script] fs_mode=remote  remote AMS_OUTPUT_ROOT={remote_ams_root}")
    else:
        remote_ams_root = local_ams_root
        print(f"[execute_csh_script] fs_mode=shared  AMS_OUTPUT_ROOT={local_ams_root}")

    # Read CDS_LIB_PATH_28 directly from the project .env file (raw dotenv parse)
    # instead of os.environ — Git bash on Windows converts /home/... paths to
    # C:\Program Files\Git\home\... which breaks on the remote Linux server.
    cds_lib = _read_env_raw("CDS_LIB_PATH_28")
    env_prefix = ""
    if remote_ams_root:
        env_prefix += f"AMS_OUTPUT_ROOT={remote_ams_root} "
    if cds_lib:
        env_prefix += f"CDS_LIB_PATH_28={cds_lib} "

    log_file  = f"{_CALIBRE_REMOTE_BASE}/{cell_tag}_run.log"
    done_file = f"{_CALIBRE_REMOTE_BASE}/{cell_tag}_done.txt"

    # ── Try SKILL async path first (Fix A) ────────────────────────────────────
    skill_ok = False
    try:
        probe = _get_client().execute_skill("(1+1)", timeout=5)
        skill_ok = bool(getattr(probe, "ok", False))
    except Exception:
        pass

    rc = 1
    if skill_ok:
        print("[execute_csh_script] using SKILL async path (non-blocking)")
        rc, _ = _run_calibre_async(
            remote_script, env_prefix, args_str,
            remote_ams_root, log_file, done_file,
            poll_secs=8.0, timeout=timeout,
        )
        if rc == 0:
            return "t"
        # Fall through to SSH path on non-zero rc
        print(f"[execute_csh_script] SKILL async rc={rc}, retrying via SSH")

    # ── SSH direct path (fallback) ─────────────────────────────────────────────
    print("[execute_csh_script] using SSH direct path")
    remote_cmd = (
        f"chmod +x {shlex.quote(remote_script)} && "
        f"{env_prefix}csh {shlex.quote(remote_script)} {args_str}"
    )
    try:
        result = ssh.run_command(remote_cmd, timeout=timeout)
    except Exception as e:
        local = _run_local_csh(script_path, args, timeout)
        if not str(local).startswith("Local csh execution failed"):
            return local
        return f"Remote execution error: {e}; fallback local: {local}"

    rc = getattr(result, "returncode", 1)
    stdout = getattr(result, "stdout", "") or ""
    stderr = getattr(result, "stderr", "") or ""

    # In remote mode, always try to fetch outputs (success or failure) so the
    # caller can parse partial results / logs on failure too.
    if mode == "remote" and local_ams_root:
        dl_err = _download_calibre_output(
            ssh, remote_ams_root, local_ams_root, timeout=max(60, min(timeout, 300))
        )
        if dl_err:
            print(f"[execute_csh_script] warn: {dl_err}")

    if rc == 0:
        return stdout or "t"

    local = _run_local_csh(script_path, args, timeout)
    if not str(local).startswith("Local csh execution failed"):
        return local
    return (
        f"Remote execution failed (rc={rc}):\n"
        f"stdout: {stdout.strip()}\n"
        f"stderr: {stderr.strip()}\n"
        f"fallback local: {local}"
    )
