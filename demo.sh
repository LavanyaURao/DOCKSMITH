#!/bin/bash
# demo.sh — Runs all 8 demo scenarios from the spec.
# Must be run as root (isolation requires chroot/unshare).

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLE="$SCRIPT_DIR/sample_app"
IMAGE="myapp:latest"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}Error: demo.sh must be run as root (sudo ./demo.sh)${NC}"
        echo "Reason: container isolation (chroot/unshare) requires root."
        exit 1
    fi
}

step() {
    echo ""
    echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Demo $1: $2${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
}

pass() { echo -e "${GREEN}  ✓ PASS: $1${NC}"; }
fail() { echo -e "${RED}  ✗ FAIL: $1${NC}"; }

check_root

# ── Demo 1: Cold build (all CACHE MISS) ───────────────────────────────────────
step "1" "Cold build — all steps should show [CACHE MISS]"
docksmith rmi "$IMAGE" 2>/dev/null || true
docksmith build -t "$IMAGE" --no-cache "$SAMPLE"
pass "Cold build completed"

# ── Demo 2: Warm build (all CACHE HIT) ────────────────────────────────────────
step "2" "Warm build — all layer steps should show [CACHE HIT]"
docksmith build -t "$IMAGE" "$SAMPLE"
pass "Warm build completed (should have been near-instant)"

# ── Demo 3: Partial rebuild after file change ──────────────────────────────────
step "3" "Edit a source file → partial rebuild (affected step + below = MISS)"
echo "# modified $(date)" >> "$SAMPLE/app.py"
docksmith build -t "$IMAGE" "$SAMPLE"
# Restore the file
git -C "$SCRIPT_DIR" checkout -- "$SAMPLE/app.py" 2>/dev/null || \
    sed -i '$ d' "$SAMPLE/app.py"
pass "Partial rebuild completed"

# ── Demo 4: docksmith images ───────────────────────────────────────────────────
step "4" "docksmith images — should list myapp:latest"
docksmith images
pass "Images listed"

# ── Demo 5: Run container ─────────────────────────────────────────────────────
step "5" "docksmith run — container starts, produces output, exits"
docksmith run "$IMAGE"
pass "Container ran successfully"

# ── Demo 6: ENV override ──────────────────────────────────────────────────────
step "6" "ENV override with -e flag"
docksmith run -e APP_NAME=DemoUser -e VERSION=2.0.0 "$IMAGE"
pass "ENV override applied"

# ── Demo 7: Isolation check ───────────────────────────────────────────────────
step "7" "Isolation: file written inside container must NOT appear on host"
docksmith run "$IMAGE"
HOST_PATH="/tmp/container_test.txt"
if [[ -f "$HOST_PATH" ]]; then
    fail "ISOLATION BREACH: $HOST_PATH found on host!"
    exit 1
else
    pass "ISOLATION OK: $HOST_PATH does NOT exist on host"
fi

# ── Demo 8: rmi removes image ────────────────────────────────────────────────
step "8" "docksmith rmi — removes image and layer files"
docksmith rmi "$IMAGE"
echo ""
docksmith images
pass "Image removed"

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  All 8 demo scenarios completed!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
