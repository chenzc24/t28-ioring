#!/bin/csh
# Shared environment variables for AMS-IO-Agent Calibre scripts
#
# All PDK/Calibre paths are overridable via environment variables.
# If a variable is already set (e.g. by your site cshrc or shell env),
# the hard-coded default below is skipped. Set them in one of:
#   1. Your login shell / site cshrc (recommended for shared servers)
#   2. A site_local.csh file next to this script (sourced if it exists)
#   3. The project .env file (CDS_LIB_PATH_28 only; others read at csh level)
#
# To create a site-local override:
#   cp site_local.csh.example site_local.csh
#   edit site_local.csh with your paths

# Determine script directory and project root
set SCRIPT_DIR = `dirname "$0"`
if ( "$SCRIPT_DIR" == "." ) then
    set SCRIPT_DIR = "$cwd"
else
    set SCRIPT_DIR = `cd "$SCRIPT_DIR"; pwd`
endif

# Project root: when uploaded to /tmp/ by virtuoso-bridge, keep SCRIPT_DIR as root
# since AMS_OUTPUT_ROOT and CDS_LIB_PATH are passed via environment. Otherwise go
# up 3 levels (calibre -> scripts -> src -> project root).
if ( "$SCRIPT_DIR" =~ /tmp/* ) then
    set PROJECT_ROOT = "$SCRIPT_DIR"
else
    set PROJECT_ROOT = "$SCRIPT_DIR"
    set PROJECT_ROOT = `dirname "$PROJECT_ROOT"`
    set PROJECT_ROOT = `dirname "$PROJECT_ROOT"`
    set PROJECT_ROOT = `dirname "$PROJECT_ROOT"`
endif

# ── Source site-local overrides (if present) ──────────────────────────────
# site_local.csh can set MGC_HOME, PDK_LAYERMAP_28, incFILE_28, etc.
# before the defaults below take effect. This is the easiest way to
# customize paths for your site without modifying this file.
if ( -f "$SCRIPT_DIR/site_local.csh" ) then
    source "$SCRIPT_DIR/site_local.csh"
endif

# ── Calibre installation root ─────────────────────────────────────────────
if ( ! $?MGC_HOME ) then
    setenv MGC_HOME /home/mentor/calibre/calibre2022/aoj_cal_2022.1_36.16
endif

# ── PDK layer maps ────────────────────────────────────────────────────────
# T28 layer map
if ( ! $?PDK_LAYERMAP_28 ) then
    setenv PDK_LAYERMAP_28 /home/process/tsmc28n/PDK_mmWave/iPDK_CRN28HPC+ULL_v1.8_2p2a_20190531/tsmcN28/tsmcN28.layermap
endif
# T180 layer map
if ( ! $?PDK_LAYERMAP_180 ) then
    setenv PDK_LAYERMAP_180 /home/process/tsmc180bcd_gen2_2022/PDK/TSMC180BCD/tsmc18/tsmc18.layermap
endif

# ── LVS include files ─────────────────────────────────────────────────────
# T28 LVS include file
if ( ! $?incFILE_28 ) then
    setenv incFILE_28 /home/process/tsmc28n/PDK_mmWave/iPDK_CRN28HPC+ULL_v1.8_2p2a_20190531/tsmcN28/../Calibre/lvs/source.added
endif
# T180 LVS include file
if ( ! $?incFILE_180 ) then
    setenv incFILE_180 /home/dmanager/shared_lib/TSMC180MS/calibre_rule/lvs/source.added
endif

# ── Path to cds.lib ───────────────────────────────────────────────────────
# The scripts will check in this order:
#   1. CDS_LIB_PATH_28 or CDS_LIB_PATH_180 (based on tech_node)
#   2. CDS_LIB_PATH (fallback for both nodes)
#   3. CDS_LIB_PATH_28/CDS_LIB_PATH_180 in $PROJECT_ROOT/.env file
#   4. CDS_LIB_PATH in $PROJECT_ROOT/.env file
#   5. Error if none found
#
# Technology node specific paths (recommended):
#setenv CDS_LIB_PATH_28 /path/to/your/T28/cds.lib
#setenv CDS_LIB_PATH_180 /path/to/your/T180/cds.lib
#
# Or set in project .env file:
# CDS_LIB_PATH_28=/absolute/path/to/T28/cds.lib
# CDS_LIB_PATH_180=/absolute/path/to/T180/cds.lib
#
# Fallback (if same cds.lib for both nodes):
#setenv CDS_LIB_PATH /path/to/your/cds.lib

# ── Calibre rule files (relative to calibre directory) ────────────────────
setenv CALIBRE_RULE_FILE_28 ${SCRIPT_DIR}/T28/_calibre_T28.rcx_
setenv CALIBRE_RULE_FILE_180 ${SCRIPT_DIR}/T180/_calibre_T180.rcx_

# LVS rule files (28nm / 180nm)
setenv LVS_RULE_FILE_28 ${SCRIPT_DIR}/T28/_calibre_T28.lvs_
setenv LVS_RULE_FILE_180 ${SCRIPT_DIR}/T180/_calibre_T180.lvs_

# DRC rule files (28nm / 180nm)
setenv DRC_RULE_FILE_28 ${SCRIPT_DIR}/T28/_drc_rule_T28_cell_
setenv DRC_RULE_FILE_180 ${SCRIPT_DIR}/T180/_drc_rule_T180_cell_

# ── Run directories ───────────────────────────────────────────────────────
setenv PEX_RUN_DIR ${PROJECT_ROOT}/output/pex
setenv DRC_RUN_DIR ${PROJECT_ROOT}/output/drc
setenv LVS_RUN_DIR ${PROJECT_ROOT}/output/lvs

# End of env_common.csh
