"""Bridge utilities — re-exports from sub-modules for backward compatibility."""

from .check import _find_project_root, _load_skill_env, _load_vb_env, check_bridge_installed, _read_env_raw
from .client import (
    _get_client,
    _get_ssh,
    rb_exec,
    get_current_design,
    _escape_path_for_skill,
    _get_remote_bridge_dir,
    _cleanup_remote_il_files,
    _scp_upload,
    load_skill_file,
    save_current_cellview,
    ui_redraw,
    ui_zoom_absolute_scale,
    _default_view_type_for,
    open_cell_view_by_type,
    ge_open_window,
    open_cell_view,
)
from .ssh import (
    _download_via_cat,
    load_script_and_take_screenshot_verbose,
    load_script_and_take_screenshot,
    _get_calibre_remote_base,
    _upload_calibre_tree,
    _run_local_csh,
    _is_windows_path,
    _detect_fs_mode,
    _download_calibre_output,
    execute_csh_script,
)
