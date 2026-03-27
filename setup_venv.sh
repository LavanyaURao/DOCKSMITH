#!/bin/bash
# setup_venv.sh — Create a virtual environment and install docksmith
# Run this from inside the docksmith/ project folder

set -e

echo "=== Setting up Docksmith virtual environment ==="
echo ""

# Create venv
python3 -m venv venv
echo "✓ Virtual environment created"

# Activate and install
source venv/bin/activate
pip install --upgrade pip -q
pip install -e . -q
echo "✓ Docksmith installed"

echo ""
echo "=== Done! ==="
echo ""
echo "To activate the venv next time:"
echo "  source venv/bin/activate"
echo ""
echo "Then use docksmith:"
echo "  sudo venv/bin/docksmith build -t myapp:latest sample_app/"
echo "  sudo venv/bin/docksmith run myapp:latest"
echo ""
echo "NOTE: build and run still need Linux (chroot/unshare)."
echo "On Mac, you can only install + edit code — not run containers."
