#!/usr/bin/env bash
# Parallels Pro MCP Server — Diagnostic Script
set -euo pipefail

echo "=================================================="
echo "Parallels Pro MCP Server — Pre-flight Check"
echo "=================================================="

ALL_OK=0

# 1. macOS check
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "[FAIL] OS is not macOS: $(uname -s)"
    ALL_OK=1
else
    echo "[PASS] Host OS: macOS ($(uname -m))"
fi

# 2. Python check
if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "[PASS] Python 3 available: version $PY_VER"
else
    echo "[FAIL] Python 3 is not installed or not in PATH."
    ALL_OK=1
fi

# 3. prlctl check
if command -v prlctl >/dev/null 2>&1; then
    PRLCTL_VER=$(prlctl --version 2>/dev/null || echo "version unavailable")
    echo "[PASS] Found prlctl: $PRLCTL_VER"
elif [[ -x "/usr/local/bin/prlctl" ]]; then
    echo "[PASS] Found prlctl at /usr/local/bin/prlctl"
else
    echo "[FAIL] 'prlctl' not found. Ensure Parallels Desktop is installed."
    ALL_OK=1
fi

# 4. Parallels License check
if command -v prlsrvctl >/dev/null 2>&1; then
    LIC_INFO=$(prlsrvctl info --license 2>/dev/null || true)
    if echo "$LIC_INFO" | grep -iqE "edition=\"?(pro|business)\"?"; then
        echo "[PASS] Parallels License: Pro/Business Edition verified."
    else
        echo "[WARN] Parallels License: Could not verify Pro/Business edition."
        echo "       Note: 'prlctl exec' guest execution requires Pro or Business edition."
    fi
else
    echo "[WARN] 'prlsrvctl' not found to verify license."
fi

# 5. Parallels VM listing
if command -v prlctl >/dev/null 2>&1; then
    echo "[INFO] Querying registered VMs..."
    if prlctl list -a 2>/dev/null; then
        echo "[PASS] Parallels service is responding."
    else
        echo "[FAIL] Could not query VMs. Parallels Desktop may not be running."
        ALL_OK=1
    fi
fi

echo "=================================================="
if [[ $ALL_OK -eq 0 ]]; then
    echo "Status: READY - Environment is ready for Parallels Pro MCP Server."
    exit 0
else
    echo "Status: INCOMPLETE - Please address the issues listed above."
    exit 1
fi
