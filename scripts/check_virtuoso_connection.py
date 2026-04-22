#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check Virtuoso Connection - T28 Skill Script

Verifies that Virtuoso is reachable through virtuoso-bridge-lite.

Usage:
    python check_virtuoso_connection.py

Exit Codes:
    0 - Virtuoso is connected
    1 - Virtuoso not connected or error
    2 - Import/setup error
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Windows consoles default to cp/gbk; force UTF-8 so emojis in diagnostic
# output don't raise UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

# Add assets to path for local imports
skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))

# Load skill-local .env so checks don't depend on caller's cwd.
env_file = skill_dir / ".env"
if env_file.exists():
    load_dotenv(dotenv_path=env_file, override=False)
else:
    load_dotenv(override=False)


def _load_vb_env() -> None:
    """Pre-load virtuoso-bridge-lite connection config.

    Priority:
      1. $VB_ENV_FILE env var (explicit path)
      2. Nearest .env with VB vars, walking cwd upward (project-level)
      3. ~/.virtuoso-bridge/.env (user-level fallback)
    """
    # 1. Explicit override
    explicit = os.getenv("VB_ENV_FILE", "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            load_dotenv(dotenv_path=str(p), override=True)
            return

    # 2. Project-level
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


def check_via_virtuoso_bridge() -> tuple[bool, list]:
    """Check Virtuoso connection using virtuoso-bridge-lite.

    Returns:
        (success, report_lines) tuple
    """
    report = []
    report.append("Bridge Type: virtuoso-bridge-lite")
    report.append("")

    try:
        from virtuoso_bridge import VirtuosoClient
    except ImportError as e:
        report.append(f"Error: {type(e).__name__}: {e}")
        report.append("")
        report.append("❌ Virtuoso Connection: FAILED")
        report.append("• virtuoso-bridge is not installed")
        report.append("• Install with: pip install -e /path/to/virtuoso-bridge-lite")
        report.append("• See README.md > Prerequisites for full instructions")
        return False, report

    try:
        _load_vb_env()
        client = VirtuosoClient.from_env()
    except Exception as e:
        report.append(f"Error: {type(e).__name__}: {e}")
        report.append("")
        report.append("❌ Virtuoso Connection: FAILED")
        report.append("• Could not create VirtuosoClient")
        report.append("• Check ~/.virtuoso-bridge/.env (create with: virtuoso-bridge init)")
        report.append("• Start the tunnel with: virtuoso-bridge start")
        return False, report

    test_command = "(1+1)"
    try:
        result = client.execute_skill(test_command, timeout=20)
    except Exception as e:
        report.append(f"Error: {type(e).__name__}: {e}")
        report.append("")
        report.append("❌ Virtuoso Connection: FAILED")
        report.append("• Could not reach the Virtuoso daemon")
        report.append("• Run: virtuoso-bridge status")
        report.append("• Confirm the daemon SKILL is loaded in Virtuoso CIW")
        return False, report

    report.append(f"Test Command: {test_command}")
    report.append(f"Response: {result.output!r}  (ok={result.ok})")
    report.append("")

    if result.ok and (result.output or "").strip() == "2":
        report.append("✅ Virtuoso Connection: OK")
        report.append("• Bridge responded with correct result (2)")
        return True, report

    report.append("⚠️  Virtuoso Connection: UNCERTAIN")
    report.append(f"• Bridge responded: {result.output!r}")
    report.append("• Expected: '2'")
    report.append("• Connection may be working but response format unexpected")
    return False, report


def _resolve_vb_env_source() -> tuple[str, str]:
    """Return (label, path) of the .env file _load_vb_env() will use, or
    ('none', '') if no VB config is found anywhere."""
    explicit = os.getenv("VB_ENV_FILE", "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return "VB_ENV_FILE", str(p)

    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "VB_REMOTE_HOST" in text or "VB_LOCAL_PORT" in text:
                return "project-level", str(candidate)

    user_env = Path.home() / ".virtuoso-bridge" / ".env"
    if user_env.is_file():
        return "user-level", str(user_env)
    return "none", ""


def check_environment() -> list:
    """Report on virtuoso-bridge-lite installation and tunnel status."""
    report = ["", "=== Environment Check ===", ""]

    try:
        import virtuoso_bridge
        report.append(f"virtuoso-bridge version: {getattr(virtuoso_bridge, '__version__', 'unknown')}")
    except ImportError:
        report.append("virtuoso-bridge: NOT INSTALLED")
        report.append("  → Install with: pip install -e /path/to/virtuoso-bridge-lite")
        report.append("")
        return report

    label, path = _resolve_vb_env_source()
    if label == "none":
        report.append("VB .env: NOT FOUND in any of the expected locations")
        report.append("  Searched:")
        report.append("    - $VB_ENV_FILE")
        report.append("    - .env in cwd and parents (with VB_REMOTE_HOST or VB_LOCAL_PORT)")
        report.append("    - ~/.virtuoso-bridge/.env")
        report.append("  → Create one with: virtuoso-bridge init   (user-level)")
        report.append("     or place a .env in your project root")
    else:
        report.append(f"VB .env source: {label}")
        report.append(f"  path: {path}")

    report.append("")
    report.append("Tunnel / daemon state:")
    report.append("  Run 'virtuoso-bridge status' for full tunnel and daemon info.")
    report.append("")
    return report


def print_troubleshooting(success: bool) -> None:
    """Print troubleshooting hints based on the test result."""
    print("")
    print("=== Troubleshooting ===")
    print("")

    if success:
        print("✅ Virtuoso connection is working!")
        print("If tools still misbehave:")
        print("  1. Check tool timeout settings")
        print("  2. Verify library/cell/view names are correct")
        print("  3. Check Virtuoso memory/CPU usage")
        print("  4. Review Virtuoso log files for errors")
        return

    print("If connection failed:")
    print("  1. Check virtuoso-bridge status:")
    print("       virtuoso-bridge status")
    print("  2. Start or restart the tunnel:")
    print("       virtuoso-bridge start")
    print("       virtuoso-bridge restart")
    print("  3. Confirm the daemon SKILL file is loaded in Virtuoso CIW.")
    print("     'virtuoso-bridge start' prints the exact load() path.")
    print("  4. Check ~/.virtuoso-bridge/.env has VB_REMOTE_HOST / VB_REMOTE_USER etc.")
    print("  5. If the package is missing:")
    print("       pip install -e /path/to/virtuoso-bridge-lite")


def main():
    """Main entry point with full diagnostics."""
    print("🔧 Virtuoso Connection Check - Enhanced Diagnostics")
    print("=" * 60)
    print()

    env_report = check_environment()
    for line in env_report:
        print(line)

    success, report = check_via_virtuoso_bridge()

    print("")
    print("=== Test Report ===")
    for line in report:
        print(line)

    print_troubleshooting(success)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
