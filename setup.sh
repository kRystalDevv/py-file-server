#!/usr/bin/env bash
# 63xky File Server environment installer (Linux/Ubuntu)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
SETUP_FAILED=0
REQUIREMENTS_OK=0
IS_ROOT=0
[ "$(id -u)" = "0" ] && IS_ROOT=1

print_header() {
    echo
    echo "================================"
    echo "Robust environment installer (Ubuntu/Debian)"
    echo "================================"
    echo
}

run_privileged() {
    if [ "$IS_ROOT" = "1" ]; then
        "$@"
        return $?
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        echo "[ERROR] This step needs root privileges and 'sudo' is not installed."
        echo "[ACTION] Re-run as root, or install sudo, then try again."
        return 1
    fi
    echo "[INFO] Running: sudo $*"
    sudo "$@"
}

pause_if_interactive() {
    if [ -t 0 ]; then
        read -rp "Press Enter to continue..." _ || true
    fi
}

detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64) echo "amd64" ;;
        aarch64|arm64) echo "arm64" ;;
        *) echo "" ;;
    esac
}

is_cloudflared_available() {
    command -v cloudflared >/dev/null 2>&1 && cloudflared --version >/dev/null 2>&1
}

install_cloudflared_apt_repo() {
    command -v curl >/dev/null 2>&1 || return 1
    local codename
    codename="$( (. /etc/os-release 2>/dev/null && echo "$VERSION_CODENAME") )"
    if [ -z "$codename" ]; then
        codename="$(lsb_release -cs 2>/dev/null || true)"
    fi
    [ -z "$codename" ] && return 1

    run_privileged mkdir -p /usr/share/keyrings || return 1
    if ! curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | run_privileged tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null; then
        return 1
    fi
    local repo_line="deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $codename main"
    if ! echo "$repo_line" | run_privileged tee /etc/apt/sources.list.d/cloudflared.list >/dev/null; then
        return 1
    fi
    run_privileged apt-get update || return 1
    run_privileged apt-get install -y cloudflared || return 1
    is_cloudflared_available
}

install_cloudflared_direct() {
    command -v curl >/dev/null 2>&1 || return 1
    local arch
    arch="$(detect_arch)"
    [ -z "$arch" ] && { echo "[WARN] Unsupported CPU architecture for direct cloudflared download."; return 1; }

    local tmp_dir
    tmp_dir="$(mktemp -d)"
    local deb_path="$tmp_dir/cloudflared-linux-${arch}.deb"
    local url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}.deb"

    if ! curl -fsSL --max-time 180 -o "$deb_path" "$url"; then
        rm -rf "$tmp_dir"
        return 1
    fi
    if ! run_privileged dpkg -i "$deb_path"; then
        run_privileged apt-get -f install -y || true
    fi
    rm -rf "$tmp_dir"
    is_cloudflared_available
}

ensure_cloudflared() {
    echo
    echo "================================"
    echo "Ensuring cloudflared is installed"
    echo "================================"

    if is_cloudflared_available; then
        echo "[INFO] cloudflared is already available."
        return 0
    fi

    echo "[INFO] cloudflared not detected. Trying method 1/2: Cloudflare apt repository."
    if install_cloudflared_apt_repo; then
        return 0
    fi

    echo "[WARN] Method 1 failed. Trying method 2/2: direct .deb download."
    if install_cloudflared_direct; then
        return 0
    fi

    echo "[ERROR] All cloudflared installation methods failed."
    return 1
}

is_python_available() {
    command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1
}

ensure_python() {
    echo
    echo "================================"
    echo "Ensuring Python, venv, and pip are installed"
    echo "================================"

    if is_python_available && python3 -c "import venv" >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then
        echo "[INFO] Python 3, venv, and pip are already available."
        return 0
    fi

    if ! command -v apt-get >/dev/null 2>&1; then
        echo "[ERROR] apt-get not found. This script supports Ubuntu/Debian-based systems."
        echo "[ACTION] Install python3, python3-venv, and python3-pip using your distro's package manager."
        return 1
    fi

    echo "[INFO] Installing python3, python3-venv, and python3-pip via apt."
    run_privileged apt-get update || true
    if ! run_privileged apt-get install -y python3 python3-venv python3-pip; then
        echo "[ERROR] Failed to install Python packages via apt."
        return 1
    fi

    is_python_available
}

install_requirements() {
    echo
    echo "================================"
    echo "Installing Python requirements"
    echo "================================"

    if [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
        echo "[ERROR] requirements.txt not found in: $SCRIPT_DIR"
        return 1
    fi

    if [ ! -x "$VENV_DIR/bin/python" ]; then
        echo "[INFO] Creating virtual environment at .venv (Ubuntu's system Python is externally managed)."
        if ! python3 -m venv "$VENV_DIR"; then
            echo "[ERROR] Failed to create virtual environment."
            return 1
        fi
    fi

    local venv_python="$VENV_DIR/bin/python"
    local try=1
    until "$venv_python" -m pip install --upgrade pip >/dev/null 2>&1; do
        if [ "$try" -ge 3 ]; then
            echo "[ERROR] Failed to upgrade pip after 3 attempts."
            return 1
        fi
        try=$((try + 1))
        echo "[WARN] pip upgrade failed. Retrying ($try/3)..."
        sleep 3
    done

    try=1
    until "$venv_python" -m pip install -r requirements.txt >/dev/null 2>&1; do
        if [ "$try" -ge 3 ]; then
            echo "[ERROR] Failed to install requirements after 3 attempts."
            return 1
        fi
        try=$((try + 1))
        echo "[WARN] requirements install failed. Retrying ($try/3)..."
        sleep 3
    done

    REQUIREMENTS_OK=1
    return 0
}

final_validation() {
    echo
    echo "================================"
    echo "Final validation"
    echo "================================"

    local validation_failed=0
    local venv_python="$VENV_DIR/bin/python"

    if is_cloudflared_available; then
        echo "[OK] cloudflared is callable."
    else
        echo "[ERROR] cloudflared is not callable."
        validation_failed=1
    fi

    if is_python_available; then
        echo "[OK] python3 is callable."
    else
        echo "[ERROR] python3 is not callable."
        validation_failed=1
    fi

    if [ -x "$venv_python" ] && "$venv_python" -m pip --version >/dev/null 2>&1; then
        echo "[OK] pip is available in .venv."
    else
        echo "[ERROR] pip is not available in .venv."
        validation_failed=1
    fi

    if [ -x "$venv_python" ] && "$venv_python" -c "import flask, waitress" >/dev/null 2>&1; then
        echo "[OK] flask and waitress import successfully in .venv."
    else
        echo "[ERROR] flask/waitress are not importable in .venv."
        validation_failed=1
    fi

    if [ "$REQUIREMENTS_OK" = "1" ]; then
        echo "[OK] requirements.txt dependencies installed."
    else
        echo "[ERROR] requirements.txt dependencies were not confirmed as installed."
        validation_failed=1
    fi

    if [ "$validation_failed" = "1" ]; then
        echo "[ERROR] Environment validation failed."
        return 1
    fi

    echo "[OK] Environment validation passed."
    return 0
}

main() {
    print_header

    if [ "$IS_ROOT" = "0" ]; then
        echo "[INFO] Not running as root. Steps that need privileges will prompt via sudo."
    fi

    if ! ensure_cloudflared; then
        echo "[WARN] cloudflared step did not complete successfully."
        SETUP_FAILED=1
    fi

    if ! ensure_python; then
        echo "[WARN] Python step did not complete successfully."
        SETUP_FAILED=1
    fi

    if ! install_requirements; then
        echo "[WARN] requirements step did not complete successfully."
        SETUP_FAILED=1
    fi

    if ! final_validation; then
        SETUP_FAILED=1
    fi

    if [ "$SETUP_FAILED" = "1" ]; then
        echo
        echo "================================"
        echo "Setup failed. See errors above."
        echo "================================"
        pause_if_interactive
        exit 1
    fi

    echo
    echo "================================"
    echo "Setup completed successfully."
    echo "Environment is ready. Use ./run_server.sh to start the server."
    echo "================================"
    echo "[INFO] Optional: install python3-tk for the graphical folder picker"
    echo "       (sudo apt-get install -y python3-tk)."
    pause_if_interactive
    exit 0
}

main "$@"
