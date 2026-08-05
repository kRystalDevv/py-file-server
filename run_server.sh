#!/usr/bin/env bash
# 63xky File Server Launcher (Linux/Ubuntu)
# Easy start menu for Local, LAN, or Public sharing.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -x "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
else
    PYTHON_BIN="python3"
fi

print_header() {
    echo
    echo "========================================================="
    echo "63xky File Server Launcher"
    echo "Easy start menu for Local, LAN, or Public sharing"
    echo "========================================================="
    echo
}

check_prerequisites() {
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        echo "[ERROR] Python 3 is not installed or not available on PATH."
        echo "[ACTION] Run ./setup.sh, then try again."
        return 1
    fi
    if [ ! -f "$SCRIPT_DIR/fileserver.py" ]; then
        echo "[ERROR] fileserver.py was not found in:"
        echo "        $SCRIPT_DIR"
        echo "[ACTION] Run this script from the project folder."
        return 1
    fi
    return 0
}

show_examples() {
    echo
    echo "Simple command examples:"
    echo "  python3 fileserver.py --mode local"
    echo "  python3 fileserver.py --mode lan --port 8080"
    echo "  python3 fileserver.py --mode public --directory ./files"
    echo
}

pause_if_interactive() {
    if [ -t 0 ]; then
        read -rp "Press Enter to continue..." _ || true
    fi
}

after_run() {
    local exit_code="$1"
    if [ "$exit_code" -ne 0 ]; then
        echo
        echo "[ERROR] The server stopped with an error."
        echo "[TIP] Run ./setup.sh first if dependencies are missing."
        pause_if_interactive
        exit 1
    fi
    echo
    echo "========================================================="
    echo "Server process ended normally."
    echo "========================================================="
    pause_if_interactive
    exit 0
}

launch_selected() {
    local mode="$1" port="$2" share_dir="$3" no_browser="$4"

    echo
    echo "========================================================="
    echo "Starting file server"
    echo "========================================================="
    echo "Mode: $mode"
    if [ -n "$port" ]; then
        echo "Port: $port"
    else
        echo "Port: default"
    fi
    if [ -n "$share_dir" ]; then
        echo "Shared folder: \"$share_dir\""
    else
        echo "Shared folder: current folder"
    fi
    if [ "$no_browser" = "1" ]; then
        echo "Browser auto-open: disabled"
    else
        echo "Browser auto-open: enabled"
    fi

    if [ "$mode" = "public" ] && ! command -v cloudflared >/dev/null 2>&1; then
        echo "[WARN] cloudflared is not currently available in PATH."
        echo "[WARN] Public mode may fail until cloudflared is installed."
    fi
    echo

    local args=(--mode "$mode")
    [ -n "$port" ] && args+=(--port "$port")
    [ -n "$share_dir" ] && args+=(--directory "$share_dir")
    [ "$no_browser" = "1" ] && args+=(--no-browser)

    echo "[INFO] Command: $PYTHON_BIN fileserver.py ${args[*]}"
    echo
    "$PYTHON_BIN" fileserver.py "${args[@]}"
    after_run "$?"
}

custom_setup() {
    echo
    echo "================================"
    echo "Custom setup wizard"
    echo "================================"
    echo
    echo "Pick mode:"
    echo "  [1] local"
    echo "  [2] lan"
    echo "  [3] public"
    read -rp "Mode (1-3, default 2): " mode_choice
    mode_choice="${mode_choice:-2}"

    local mode=""
    case "$mode_choice" in
        1) mode="local" ;;
        2) mode="lan" ;;
        3) mode="public" ;;
        *)
            echo "[WARN] Invalid mode choice. Returning to main menu."
            echo
            return
            ;;
    esac

    read -rp "Port (press Enter for default): " port
    if [ -n "$port" ] && ! [[ "$port" =~ ^[0-9]+$ ]]; then
        echo "[WARN] Port must contain only numbers. Using default."
        port=""
    fi

    read -rp "Folder to share (press Enter for current folder): " share_dir
    if [ -n "$share_dir" ] && [ ! -d "$share_dir" ]; then
        echo "[WARN] Folder does not exist: \"$share_dir\""
        echo "[WARN] Using current folder instead."
        share_dir=""
    fi

    local no_browser="0"
    read -rp "Do not open browser automatically? (y/N): " no_browser_choice
    if [[ "$no_browser_choice" =~ ^[Yy]$ ]]; then
        no_browser="1"
    fi

    launch_selected "$mode" "$port" "$share_dir" "$no_browser"
}

menu() {
    while true; do
        echo "Choose how you want to run your file server:"
        echo
        echo "  [1] Local only (safest) - only this PC can open the server"
        echo "  [2] LAN sharing - devices on your Wi-Fi/LAN can open the server"
        echo "  [3] Public internet - creates a Cloudflare public link"
        echo "  [4] Custom setup (choose mode, port, folder, browser behavior)"
        echo "  [5] Show simple examples"
        echo "  [0] Exit"
        echo
        read -rp "Enter your choice (0-5): " choice

        case "$choice" in
            1) launch_selected "local" "" "" "0" ;;
            2) launch_selected "lan" "" "" "0" ;;
            3) launch_selected "public" "" "" "0" ;;
            4) custom_setup ;;
            5) show_examples ;;
            0)
                echo
                echo "Exiting launcher."
                exit 0
                ;;
            *)
                echo
                echo "[WARN] Invalid choice. Please type 0, 1, 2, 3, 4, or 5."
                echo
                ;;
        esac
    done
}

main() {
    print_header
    if ! check_prerequisites; then
        pause_if_interactive
        exit 1
    fi

    if [ "$#" -gt 0 ]; then
        echo "[INFO] Advanced mode detected. Starting with arguments you provided."
        echo "[INFO] Command: $PYTHON_BIN fileserver.py $*"
        echo
        "$PYTHON_BIN" fileserver.py "$@"
        after_run "$?"
    fi

    menu
}

main "$@"
