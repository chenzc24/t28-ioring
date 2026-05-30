"""SSH/file transfer and Calibre csh execution utilities."""

from __future__ import annotations

import os
import shlex
import time
from pathlib import Path
from typing import Optional

from .check import _load_vb_env, _read_env_raw
from .client import (
    _escape_path_for_skill,
    _get_client,
    _get_ssh,
    rb_exec,
)


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
        remote_png = f"{_get_calibre_remote_base()}/screenshot_{local_save.name}"
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

    # Ensure the remote screenshot directory exists before hiWindowSaveImage
    # tries to write into it, otherwise Virtuoso fails with "no permission".
    if remote_mode:
        ssh = _get_ssh()
        remote_dir = os.path.dirname(remote_png)
        ssh.run_command(f"mkdir -p {shlex.quote(remote_dir)}", timeout=15)

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
def _get_calibre_remote_base() -> str:
    """User-scoped remote base to avoid /tmp permission collisions on shared EDA servers.

    Appends ``_${VB_REMOTE_USER}`` so each SSH user gets an isolated directory
    under /tmp.  Falls back to the un-suffixed path only when the username is
    unavailable (should not happen in normal operation).
    """
    _load_vb_env()
    user = os.environ.get("VB_REMOTE_USER", "").strip()
    suffix = f"_{user}" if user else ""
    return f"/tmp/vb_t28_calibre{suffix}"


def _upload_calibre_tree(ssh, calibre_dir: Path, remote_base: str, timeout: int = 120) -> Optional[str]:
    """Upload every file under calibre_dir to remote_base, preserving structure.

    Uses ssh.upload_file() which streams via tar pipe (no command-line length
    limit).  Strips \\r from script files during packing.

    Returns None on success, or an error string on failure.
    """
    import time as _time
    import tarfile, io

    # Collect all files, strip \r from scripts, pack into ONE tar.gz
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in calibre_dir.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(calibre_dir).as_posix()
            content = f.read_bytes()
            if f.suffix in (".csh", ".sh", ".il", ".skill"):
                content = content.replace(b"\r", b"")
            info = tarfile.TarInfo(name=rel)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

    buf.seek(0)
    # Stage in the project output directory instead of system %TEMP% to avoid
    # Windows temp-file ACL issues, antivirus locks, and paths with spaces.
    _staging = Path(os.environ.get("AMS_OUTPUT_ROOT", os.getcwd())) / ".calibre_staging"
    _staging.mkdir(parents=True, exist_ok=True)
    tmp_path = _staging / f"calibre_upload_{os.getpid()}.tar.gz"
    tmp_path.write_bytes(buf.read())

    try:
        # upload_file() streams via `tar cf - <file> | ssh "tar xf - -C <dir>"`
        # so the remote file ends up at <remote_base>/<tmp_filename>.
        remote_tar_name = tmp_path.name
        up = ssh.upload_file(tmp_path, f"{remote_base}/{remote_tar_name}", timeout=timeout)
        rc = getattr(up, "returncode", 1)
        if rc != 0:
            err = (getattr(up, "stderr", "") or "").strip()
            return f"tarball upload failed: {err}"

        # Unpack on remote (retry on transient failures)
        remote_tar = f"{remote_base}/{remote_tar_name}"
        max_retries = 3
        last_err = ""
        for attempt in range(1, max_retries + 1):
            try:
                unpack = ssh.run_command(
                    f"mkdir -p {shlex.quote(remote_base)} && "
                    f"tar xzf {shlex.quote(remote_tar)} -C {shlex.quote(remote_base)}",
                    timeout=60,
                )
                if getattr(unpack, "returncode", 1) == 0:
                    # Clean up remote tarball
                    ssh.run_command(f"rm -f {shlex.quote(remote_tar)}", timeout=10)
                    return None
                last_err = (getattr(unpack, "stderr", "") or "").strip()
            except Exception as e:
                last_err = str(e)
            if attempt < max_retries:
                wait = min(5 * (2 ** (attempt - 1)), 30)
                print(f"[upload_calibre_tree] unpack attempt {attempt}/{max_retries} failed: {last_err[:200]}")
                _time.sleep(wait)

        return f"remote unpack failed after {max_retries} attempts: {last_err}"
    finally:
        tmp_path.unlink(missing_ok=True)


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
      - Windows-style local path -> remote (Linux Calibre can't see `C:\\...`)
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


def _download_calibre_output(ssh, remote_root: str, local_root: str, timeout: int = 180,
                            max_retries: int = 2, retry_delay: int = 10) -> Optional[str]:
    """Pull `drc/` and `lvs/` subtrees and top-level `*_report*` files from
    `remote_root` back to `local_root`. Returns None on success, or an error
    string. Missing remote subdirs are silently skipped.

    Retries up to ``max_retries`` times when downloaded directories are empty,
    to handle Calibre writing summary files with a slight delay after the csh
    script returns.
    """
    import time as _time

    local_root_p = Path(local_root).expanduser().resolve(strict=False)
    local_root_p.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 2):          # 1 initial + max_retries
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

        # Verify that at least one summary file landed in each subdirectory.
        all_ok = True
        for subdir in ("drc", "lvs"):
            local_sub = local_root_p / subdir
            if local_sub.is_dir():
                has_content = any(local_sub.iterdir())
                if not has_content:
                    all_ok = False
                    break

        if all_ok:
            return None

        # Empty directory detected — retry after a short wait.
        if attempt <= max_retries:
            print(f"[download] retry {attempt}/{max_retries}: "
                  f"output dirs empty, waiting {retry_delay}s before retry...")
            _time.sleep(retry_delay)

    return None


def execute_csh_script(script_path: str, *args, timeout: int = 600) -> str:
    """Upload the calibre csh script tree and run it on the EDA server.

    Execution path:
      1. SSH direct: runs synchronously via ssh.run_command with env vars.
      2. Local csh (fallback): runs on the local machine (rarely works).

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

    # ── Resolve user-scoped remote base (avoids /tmp collision on shared servers) ─
    remote_base = _get_calibre_remote_base()

    # ── Upload all calibre scripts as a single tarball ─────────────────────────
    upload_err = _upload_calibre_tree(ssh, calibre_dir, remote_base, timeout=120)
    if upload_err:
        local = _run_local_csh(script_path, args, timeout)
        if not str(local).startswith("Local csh execution failed"):
            return local
        return f"Remote upload failed: {upload_err}; fallback local: {local}"

    remote_script = f"{remote_base}/{script.relative_to(calibre_dir).as_posix()}"
    args_str = " ".join(shlex.quote(str(a)) for a in args)
    local_ams_root = os.environ.get("AMS_OUTPUT_ROOT", "").strip()

    mode = _detect_fs_mode(ssh, local_ams_root)
    cell_tag = _re.sub(r"[^A-Za-z0-9_.-]", "_", str(args[1]) if len(args) >= 2 else "run") or "run"

    if mode == "remote":
        remote_ams_root = f"{remote_base}/output_{cell_tag}"
        ssh.run_command(f"mkdir -p {shlex.quote(remote_ams_root)}/drc {shlex.quote(remote_ams_root)}/lvs", timeout=10)
        print(f"[execute_csh_script] fs_mode=remote  remote AMS_OUTPUT_ROOT={remote_ams_root}")
    else:
        remote_ams_root = local_ams_root
        print(f"[execute_csh_script] fs_mode=shared  AMS_OUTPUT_ROOT={local_ams_root}")

    # Read CDS_LIB_PATH_28 directly from the project .env file (raw dotenv parse)
    # instead of os.environ — Git bash on Windows converts /home/... paths to
    # C:\Program Files\Git\home\... which breaks on the remote Linux server.
    cds_lib = _read_env_raw("CDS_LIB_PATH_28")

    # Build env args for `env` command (explicit, works regardless of login shell)
    env_parts = []
    if remote_ams_root:
        env_parts.append(f"AMS_OUTPUT_ROOT={shlex.quote(remote_ams_root)}")
    if cds_lib:
        env_parts.append(f"CDS_LIB_PATH_28={shlex.quote(cds_lib)}")
    env_prefix = " ".join(env_parts) + " " if env_parts else ""

    log_file = f"{remote_base}/{cell_tag}_run.log"

    # ── SSH direct path ────────────────────────────────────────────────────────
    # Use csh -f to skip .cshrc (avoid interference from user login scripts)
    # and ensure the calibre scripts' own environment setup takes effect cleanly.
    print("[execute_csh_script] using SSH direct path")
    remote_cmd = (
        f"chmod +x {shlex.quote(remote_script)} && "
        f"env {env_prefix}csh -f {shlex.quote(remote_script)} {args_str}"
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

    # Try to fetch the remote run log for diagnostics
    log_content = ""
    try:
        log_res = ssh.run_command(
            f"cat {shlex.quote(log_file)} 2>/dev/null | tail -80", timeout=30
        )
        log_content = getattr(log_res, "stdout", "") or ""
    except Exception:
        pass

    local = _run_local_csh(script_path, args, timeout)
    if not str(local).startswith("Local csh execution failed"):
        return local
    parts = [
        f"Remote csh execution failed (rc={rc}):",
        f"stdout: {stdout.strip()}",
        f"stderr: {stderr.strip()}",
    ]
    if log_content.strip():
        parts.append(f"--- remote log (last 80 lines) ---\n{log_content.strip()}")
    parts.append(f"fallback local: {local}")
    return "\n".join(parts)
